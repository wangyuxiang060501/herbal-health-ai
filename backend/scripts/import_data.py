# -*- coding: utf-8 -*-
"""数据导入脚本 —— 把双层数据集写入数据库

  - 查询层 herbs         ← data/tcm_herbs_clean.json（604 味唯一药材）
  - 推荐层 whitelist     ← data/food_medicine_106.json（106 种药食同源）
  - herbs.is_food_medicine ← 按名称与白名单匹配后打标（次要收益：前端可显示「可用于药膳」）

用法：
    python scripts/import_data.py            # 增量导入（已存在则更新）
    python scripts/import_data.py --reset    # 先清空两张表再导入
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import SessionLocal, engine, init_db  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.models.entities import (  # noqa: E402
    Base, FoodMedicineWhitelist, Herb,
)
from app.services import data_loader  # noqa: E402

logger = get_logger("scripts.import_data")

HERB_SOURCE_NOTE = data_loader.HERB_SOURCE_NOTE


def import_whitelist(db, reset: bool) -> int:
    if reset:
        db.execute(delete(FoodMedicineWhitelist))
        db.commit()
    records = data_loader.load_whitelist_records()
    count = 0
    for r in records:
        existing = db.execute(
            select(FoodMedicineWhitelist).where(FoodMedicineWhitelist.name == r["name"])
        ).scalar_one_or_none()
        payload = dict(
            alias=r.get("alias", ""),
            batch=r.get("batch", 0),
            batch_source=r.get("batch_source", ""),
            category=r.get("category", ""),
            nature_flavor=r.get("nature_flavor", ""),
            meridians=r.get("meridians", ""),
            effects=r.get("effects", ""),
            dosage=r.get("dosage", ""),
            contraindications=json.dumps(r.get("contraindications", []), ensure_ascii=False),
            special_groups=json.dumps(r.get("special_groups", []), ensure_ascii=False),
            verified=bool(r.get("verified", False)),
            source=r.get("source", ""),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            db.add(FoodMedicineWhitelist(name=r["name"], **payload))
        count += 1
    db.commit()
    return count


def import_herbs(db, reset: bool) -> tuple[int, int]:
    if reset:
        db.execute(delete(Herb))
        db.commit()
    herbs = data_loader.load_clean_herbs()
    wl_names = data_loader.whitelist_names()
    wl_base = {n.split("（")[0]: n for n in wl_names}

    count = 0
    food_count = 0
    for h in herbs:
        name = h["name"].strip()
        is_food = name in wl_names or name in wl_base
        food_count += 1 if is_food else 0
        existing = db.execute(select(Herb).where(Herb.name == name)).scalar_one_or_none()
        payload = dict(
            category=h.get("category", ""),
            meridian=h.get("meridian", ""),
            effect=h.get("effect", ""),
            component=h.get("component", ""),
            dosage=h.get("dosage", ""),
            is_food_medicine=is_food,
            source_note=HERB_SOURCE_NOTE,
            merged_from=int(h.get("merged_from", 1)),
            has_conflict=bool(h.get("conflicts")),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            db.add(Herb(name=name, **payload))
        count += 1
    db.commit()
    return count, food_count


def complement_from_whitelist(db) -> int:
    """补齐：106 白名单中未出现在原始查询层的药材，补写为百科条目

    这 22 味（如荷叶、橘皮、铁皮石斛、地黄）是国家法定可食用品种，
    但开源药材数据里没有。补写时必须**如实标注来源**，不能和爬来的数据混为一谈。
    """
    added = 0
    herbs = data_loader.load_clean_herbs()
    existing_names = {h["name"].strip() for h in herbs}
    for w in data_loader.load_whitelist_records():
        name = w["name"]
        base = name.split("（")[0]
        if name in existing_names or base in existing_names:
            continue
        row = db.execute(select(Herb).where(Herb.name == name)).scalar_one_or_none()
        payload = dict(
            category=w.get("category", ""),
            meridian=w.get("meridians", ""),
            effect=w.get("effects", ""),
            component=f"性味：{w.get('nature_flavor', '')}" if w.get("nature_flavor") else "",
            dosage=w.get("dosage", ""),
            is_food_medicine=True,
            source_note=(
                f"来源：卫健委药食同源目录第 {w.get('batch', '')} 批"
                f"（原始药材数据集未收录，本条目由白名单补齐）"
            ),
            merged_from=1,
            has_conflict=False,
        )
        if row:
            for k, v in payload.items():
                setattr(row, k, v)
        else:
            db.add(Herb(name=name, **payload))
            added += 1
    db.commit()
    return added


def main():
    from app.core.cache import cache_clear_all

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="清空 herbs / whitelist 后重新导入")
    args = parser.parse_args()

    init_db()  # 保证表存在
    db = SessionLocal()
    try:
        wl_n = import_whitelist(db, args.reset)
        herb_n, food_n = import_herbs(db, args.reset)
        added = complement_from_whitelist(db)
        total_herbs = db.execute(select(Herb)).scalars().all()
        print(f"[OK] 白名单 {wl_n} 条已写入 food_medicine_whitelist")
        print(f"[OK] 药材 {herb_n} 条写入 herbs，其中 is_food_medicine=true 的 {food_n} 条")
        print(f"[OK] 白名单补齐 +{added} 条（原药材数据集未收录的法定可食用品种）")
        print(f"[OK] 查询层合计 {len(total_herbs)} 味药材")
        print(f"[OK] 数据库：{engine.url}")
        # 数据变了，聚合统计缓存必须失效，否则接口还在返回导入前的类别/归经数
        n = cache_clear_all()
        print(f"[OK] 已清空 {n} 处热点缓存（类别/归经/数据集概况）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
