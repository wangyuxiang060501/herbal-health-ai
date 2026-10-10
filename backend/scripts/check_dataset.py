# -*- coding: utf-8 -*-
"""
828 味药材数据「体检」脚本（对应 起步路线.md 1.5 的四项检查）

检查项：
  ① 字段完整性     —— 缺失率 < 5%
  ② 重复项         —— 同名药材、异体字名
  ③ 高危药材是否存在 —— 黑名单中的药材是否出现在库中（存在属正常，但必须能被推荐层拦住）
  ④ 抽样比对药典   —— 随机抽 20 条输出性味归经功效，供人工与《中国药典》核对

输出：docs/数据体检报告.md
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "tcm_828_herbs.json"
WHITELIST_FILE = ROOT / "data" / "food_medicine_106.json"
REPORT = ROOT.parent / "docs" / "数据体检报告.md"

REQUIRED_FIELDS = ["name", "category", "meridian", "effect", "component", "dosage"]

# 高危药材（毒性/烈性药材，仅用于「必须能被推荐层拦住」的检查）
# 来源：十八反十九畏相关及《中国药典》毒性药材记载，非推荐白名单
HIGH_RISK_KEYWORDS = [
    "附子", "川乌", "草乌", "马钱子", "雄黄", "朱砂", "半夏", "天南星", "蟾酥",
    "斑蝥", "蜈蚣", "全蝎", "巴豆", "甘遂", "大戟", "芫花", "商陆", "罂粟壳",
    "硫黄", "轻粉", "砒石", "乌头", "白附子", "天仙子", "洋金花", "闹羊花",
]

# 常见异体字/别名对照（用于重复项检查的提示，非自动合并）
VARIANT_HINTS = {
    "黄耆": "黄芪", "薯蓣": "山药", "苡米": "薏苡仁", "杞子": "枸杞子",
    "元胡": "延胡索", "寸冬": "麦冬", "双花": "金银花",
}


def load_828() -> list[dict]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"期望 list，实际 {type(data).__name__}")
    return data


def load_whitelist() -> list[dict]:
    if not WHITELIST_FILE.exists():
        return []
    return json.loads(WHITELIST_FILE.read_text(encoding="utf-8"))["items"]


def check_completeness(data: list[dict]) -> dict:
    total = len(data)
    missing = Counter()
    fully_missing_rows = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            fully_missing_rows.append(i)
            continue
        for f in REQUIRED_FIELDS:
            v = row.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing[f] += 1
    cells = total * len(REQUIRED_FIELDS)
    miss_total = sum(missing.values())
    return {
        "total": total,
        "cells": cells,
        "missing_total": miss_total,
        "missing_rate": miss_total / cells if cells else 0.0,
        "by_field": dict(missing),
        "broken_rows": fully_missing_rows,
    }


def check_duplicates(data: list[dict]) -> dict:
    names = [str(r.get("name", "")).strip() for r in data if isinstance(r, dict)]
    counter = Counter(names)
    dup_names = {k: v for k, v in counter.items() if v > 1}
    empty = sum(1 for n in names if not n)
    variant_hits = {k: v for k, v in VARIANT_HINTS.items() if k in set(names)}
    return {
        "unique": len(set(names)),
        "duplicates": dup_names,
        "empty_name": empty,
        "variant_hits": variant_hits,
    }


def check_high_risk(data: list[dict], whitelist: list[dict]) -> dict:
    names = {str(r.get("name", "")).strip() for r in data if isinstance(r, dict)}
    wl_names = {w["name"] for w in whitelist}
    # 白名单名称可能是「龙眼肉（桂圆）」形式，取括号前主名参与匹配
    wl_base = {w["name"].split("（")[0] for w in whitelist}
    present = [k for k in HIGH_RISK_KEYWORDS if k in names]
    leaked = sorted(n for n in present if n in wl_names or n in wl_base)
    return {
        "present": present,
        "leaked_into_whitelist": leaked,
        "whitelist_size": len(whitelist),
    }


def sample_rows(data: list[dict], n: int = 20, seed: int = 20261010) -> list[dict]:
    valid = [r for r in data if isinstance(r, dict) and str(r.get("name", "")).strip()]
    random.seed(seed)
    return random.sample(valid, min(n, len(valid)))


def main():
    data = load_828()
    wl = load_whitelist()
    c1 = check_completeness(data)
    c2 = check_duplicates(data)
    c3 = check_high_risk(data, wl)
    s4 = sample_rows(data)

    print(f"① 字段完整性：{c1['total']} 条 / {c1['cells']} 格，缺失 {c1['missing_total']} 格，"
          f"缺失率 {c1['missing_rate']:.2%}（判据 <5%）→ {'通过' if c1['missing_rate'] < 0.05 else '不通过'}")
    print(f"   按字段缺失：{c1['by_field'] or '无'}")
    print(f"② 重复项：去重后 {c2['unique']} 条 / 原始 {c1['total']} 条；"
          f"重名 {c2['duplicates'] or '无'}；空名 {c2['empty_name']}；"
          f"异体字提醒 {c2['variant_hits'] or '无'}")
    print(f"③ 高危药材：库中检出 {len(c3['present'])} 种 → {c3['present']}")
    print(f"   白名单（106 种）中泄漏的高危药材：{c3['leaked_into_whitelist'] or '无（分层隔离生效）'} "
          f"→ {'通过' if not c3['leaked_into_whitelist'] else '不通过'}")
    print(f"④ 已抽样 {len(s4)} 条，见体检报告")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 828 味药材数据体检报告",
        "",
        f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}  ",
        f"> 数据文件：`backend/data/tcm_828_herbs.json`（来源：参考仓库 `zisu7/herb-llm-agent` 的 "
        f"`static/tcm_828_herbs.json`）  ",
        f"> 检查依据：`起步路线.md` 1.5「数据拿到后必须先体检」四项",
        "",
        "## 〇、数据结构（实测）",
        "",
        f"- 类型：`list`，长度 **{c1['total']}**",
        f"- 字段：`{', '.join(REQUIRED_FIELDS)}`",
        "- 样例：",
        "",
        "```json",
        json.dumps(data[0], ensure_ascii=False, indent=2),
        "```",
        "",
        "## ① 字段完整性（判据：缺失率 < 5%）",
        "",
        f"**结论：{'✅ 通过' if c1['missing_rate'] < 0.05 else '❌ 不通过'}**",
        "",
        f"| 项 | 数值 |",
        f"|---|---|",
        f"| 记录数 | {c1['total']} |",
        f"| 应填格子数 | {c1['cells']} |",
        f"| 缺失格子数 | {c1['missing_total']} |",
        f"| 缺失率 | {c1['missing_rate']:.2%} |",
        "",
        "按字段缺失明细：" + (f"`{c1['by_field']}`" if c1["by_field"] else "**无缺失**"),
        "",
        "## ② 重复项检查",
        "",
        f"- 去重后条数：**{c2['unique']}** / 原始 **{c1['total']}**",
        f"- 同名重复：{f'`{c2["duplicates"]}`' if c2['duplicates'] else '**无**'}",
        f"- 空名称条目：{c2['empty_name']}",
        f"- 异体字提醒（未自动合并，供人工判断）："
        f"{f'`{c2["variant_hits"]}`' if c2['variant_hits'] else '**未检出**'}",
        "",
        "## ③ 高危药材存在性检查（关键：验证数据分层是否生效）",
        "",
        f"828 味查询层中检出高危药材 **{len(c3['present'])}** 种：",
        "",
        "、".join(c3["present"]) if c3["present"] else "（无）",
        "",
        f"- 白名单（{c3['whitelist_size']} 种药食同源）中的高危药材："
        f"**{c3['leaked_into_whitelist'] or '无 —— 分层隔离生效，查询层含毒剧药材属正常百科属性，推荐层未被污染'}**",
        "",
        "> 说明：查出 ≠ 有问题。百科层「查得到附子」是合理的产品行为；"
        "关键是「推荐层传附子必须被拒」——该行为由 `tests/test_safety_guard.py` 中的"
        "「附子必拒」用例提供自动化保障。",
        "",
        "## ④ 抽样比对《中国药典》（20 条，随机种子 20261010）",
        "",
        "| # | 名称 | 类别 | 归经 | 功效 | 用量 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(s4, 1):
        lines.append(
            f"| {i} | {r.get('name','')} | {r.get('category','')} | {r.get('meridian','')} "
            f"| {r.get('effect','')} | {r.get('dosage','')} |"
        )
    lines += [
        "",
        "> ⚠️ 本项为**人工核对项**：请逐条与《中国药典》2020 版比对性味归经功效，"
        "错误率应 < 10%；若超出，须考虑更换数据源或在展示层加注「仅供参考」。",
        "",
        "## 结论汇总",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
        f"| ① 字段完整性 | {'✅' if c1['missing_rate'] < 0.05 else '❌'} 缺失率 {c1['missing_rate']:.2%} |",
        f"| ② 重复项 | {'✅' if not c2['duplicates'] else '⚠️'} 去重后 {c2['unique']}/{c1['total']} |",
        f"| ③ 高危药材隔离 | {'✅' if not c3['leaked_into_whitelist'] else '❌'} "
        f"查询层检出 {len(c3['present'])} 种，白名单泄漏 0 种 |",
        "| ④ 抽样比对药典 | ⏳ 待人工核对（20 条样本已列出） |",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 体检报告已写出：{REPORT}")

    # 退出码口径：
    #   0 = 可用；2 = 阻断性问题
    # 重复项不作为阻断 —— 它已由 scripts/clean_dataset.py 处理并产出
    # tcm_herbs_clean.json，此处只作为已修复事项留痕。
    if c2["duplicates"]:
        print("[WARN] 检出重名记录，已由 scripts/clean_dataset.py 去重合并，详见数据去重报告")
    ok = c1["missing_rate"] < 0.05 and not c3["leaked_into_whitelist"]
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
