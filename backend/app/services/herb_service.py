# -*- coding: utf-8 -*-
"""BC5 药材知识服务（查询层）—— 只读，绝不参与推荐"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.cache import ttl_cache
from app.core.logging import get_logger
from app.domain.safety.constants import BLACKLIST_HERBS
from app.models.entities import Herb

logger = get_logger("services.herb")

# 6.2.1 缓存策略：只缓存**聚合统计**，不缓存列表与 ORM 实例。
#  - 类别/归经统计：每次打开药材库筛选面板都要全表 group by / 全字段扫描，最值得缓存
#  - 列表/搜索：分页参数组合多、命中率低，且已有索引，缓存收益不抵内存占用
#  - ORM 实例：会话关闭后会 DetachedInstanceError，一律不进缓存
_CACHE_TTL = 300.0      # 5 分钟；药材数据导入后基本不变


def list_herbs(
    db: Session,
    *,
    page: int = 1,
    size: int = 20,
    category: str | None = None,
    meridian: str | None = None,
    only_food_medicine: bool = False,
) -> tuple[list[Herb], int]:
    stmt = select(Herb)
    cnt_stmt = select(func.count(Herb.id))
    conditions = []
    if category:
        conditions.append(Herb.category == category)
    if meridian:
        conditions.append(Herb.meridian.contains(meridian))
    if only_food_medicine:
        conditions.append(Herb.is_food_medicine.is_(True))
    if conditions:
        stmt = stmt.where(*conditions)
        cnt_stmt = cnt_stmt.where(*conditions)

    total = db.execute(cnt_stmt).scalar_one()
    items = db.execute(
        stmt.order_by(Herb.id).offset((page - 1) * size).limit(size)
    ).scalars().all()
    return list(items), total


def search_herbs(db: Session, q: str, *, size: int = 20) -> list[Herb]:
    q = (q or "").strip()
    if not q:
        return []
    stmt = (
        select(Herb)
        .where(
            or_(
                Herb.name.contains(q),
                Herb.effect.contains(q),
                Herb.category.contains(q),
                Herb.component.contains(q),
            )
        )
        .order_by(Herb.id)
        .limit(size)
    )
    return list(db.execute(stmt).scalars().all())


def get_herb(db: Session, herb_id: int) -> Herb | None:
    return db.get(Herb, herb_id)


def get_herb_by_name(db: Session, name: str) -> Herb | None:
    stmt = select(Herb).where(Herb.name == name)
    return db.execute(stmt).scalar_one_or_none()


@ttl_cache(ttl=_CACHE_TTL, maxsize=16, ignore_types=(Session,))
def categories(db: Session) -> list[dict]:
    rows = db.execute(
        select(Herb.category, func.count(Herb.id)).group_by(Herb.category)
    ).all()
    return [{"name": c or "未分类", "count": n} for c, n in sorted(rows, key=lambda r: -r[1])]


@ttl_cache(ttl=_CACHE_TTL, maxsize=16, ignore_types=(Session,))
def meridians(db: Session) -> list[dict]:
    """归经无法直接 group（字段是自由字符串），做一次拆分统计"""
    rows = db.execute(select(Herb.meridian)).scalars().all()
    counter: dict[str, int] = {}
    for raw in rows:
        text = (raw or "").replace("经", "")
        for token in text:
            if token.strip():
                counter[token] = counter.get(token, 0) + 1
    return [{"name": f"{k}经", "count": v} for k, v in sorted(counter.items(), key=lambda x: -x[1])]


def to_dict(herb: Herb) -> dict:
    return {
        "id": herb.id,
        "name": herb.name,
        "category": herb.category,
        "meridian": herb.meridian,
        "effect": herb.effect,
        "component": herb.component,
        "dosage": herb.dosage,
        "is_food_medicine": herb.is_food_medicine,
        "source_note": herb.source_note,
        "is_blacklisted": herb.name in BLACKLIST_HERBS,
        "has_conflict": herb.has_conflict,
        "merged_from": herb.merged_from,
        # 这是「查得到」与「敢推荐」的分界：前端据此决定是否显示「可用于药膳」
        "usage_policy": (
            "可用于药膳（属 106 种药食同源）" if herb.is_food_medicine
            else "仅供知识查询，不得进入药膳方案"
        ),
    }
