# -*- coding: utf-8 -*-
"""
828 味药材数据「去重 / 合并」管线
================================================================================
背景（体检发现，见 docs/数据体检报告.md）：
  原始 JSON 名义 828 条，但唯一名称只有 604 个 —— 存在 206 组重名、共 430 条记录：
    - 8 组内容完全相同（可直接去重）
    - 198 组**内容互相冲突**（同一味药在不同章节被重复收录，且类别/归经/成分不一致）
  典型：续断既被标为「补虚药」又被标为「活血化瘀药」；附子有两个不同的成分列表。

合并策略（确定性，可复现）：
  - name        ：作为主键
  - category    ：取出现次数最多者；次数相同取首次出现（保持确定性）
  - meridian    ：取出现次数最多者
  - dosage      ：取出现次数最多者
  - effect      ：取最长者（信息更完整）
  - component   ：逗号/顿号分隔后取并集，按首次出现顺序保留，去重
  - 冲突字段     ：记录到 conflicts，供人工复核

输出：
  - backend/data/tcm_herbs_clean.json   清洗后的查询层数据（唯一名称）
  - docs/数据去重报告.md                 冲突明细

用法：
    python scripts/clean_dataset.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "tcm_828_herbs.json"
CLEAN_FILE = ROOT / "data" / "tcm_herbs_clean.json"
REPORT = ROOT.parent / "docs" / "数据去重报告.md"

FIELDS = ["name", "category", "meridian", "effect", "component", "dosage"]
SPLIT_RE = re.compile(r"[、,，;；/]+")


def group_rows(rows: list[dict]) -> dict[str, list[tuple[int, dict]]]:
    g: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, r in enumerate(rows):
        name = str(r.get("name", "")).strip()
        if name:
            g[name].append((i, r))
    return g


def most_common(values: list[str]) -> tuple[str, bool]:
    """返回（取值，是否存在分歧）。并列时取首次出现值以保证确定性。"""
    vals = [v for v in values if v]
    if not vals:
        return "", False
    counter = Counter(vals)
    top = max(counter.values())
    conflicted = len(counter) > 1
    for v in vals:  # 首次出现者优先
        if counter[v] == top:
            return v, conflicted
    raise AssertionError


def union_components(values: list[str]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for v in values:
        for tok in SPLIT_RE.split(v or ""):
            tok = tok.strip()
            if tok and tok not in seen_set:
                seen_set.add(tok)
                seen.append(tok)
    return seen


def merge(name: str, entries: list[tuple[int, dict]]) -> dict:
    idxs = [i for i, _ in entries]
    rows = [r for _, r in entries]
    conflicts: list[str] = []

    category, c1 = most_common([str(r.get("category", "")).strip() for r in rows])
    meridian, c2 = most_common([str(r.get("meridian", "")).strip() for r in rows])
    dosage, c3 = most_common([str(r.get("dosage", "")).strip() for r in rows])
    for f, flag in (("category", c1), ("meridian", c2), ("dosage", c3)):
        if flag:
            conflicts.append(f)

    effects = [str(r.get("effect", "")).strip() for r in rows]
    effect = max(effects, key=len) if effects else ""
    if len(set(e for e in effects if e)) > 1:
        conflicts.append("effect")

    comp_values = [str(r.get("component", "")).strip() for r in rows]
    components = union_components(comp_values)
    if len(set(v for v in comp_values if v)) > 1:
        conflicts.append("component")

    return {
        "name": name,
        "category": category,
        "meridian": meridian,
        "effect": effect,
        "component": "、".join(components),
        "dosage": dosage,
        "merged_from": len(rows),
        "source_indexes": idxs,
        "conflicts": sorted(set(conflicts)),
    }


def main():
    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    grouped = group_rows(raw)

    clean = []
    for name in sorted(grouped.keys()):
        clean.append(merge(name, grouped[name]))

    CLEAN_FILE.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dup_groups = {k: v for k, v in grouped.items() if len(v) > 1}
    exact = sum(
        1 for v in dup_groups.values()
        if len({json.dumps(r, ensure_ascii=False, sort_keys=True) for _, r in v}) == 1
    )
    conflicted_records = [c for c in clean if c["conflicts"]]

    print(f"[OK] 原始 {len(raw)} 条 → 清洗后 {len(clean)} 条唯一药材")
    print(f"     重名组 {len(dup_groups)} 组（完全相同 {exact} 组，内容冲突 {len(dup_groups)-exact} 组）")
    print(f"     含字段分歧、建议人工复核的条目：{len(conflicted_records)} 条")
    print(f"[OK] 写出 {CLEAN_FILE}")

    # ---------------- 报告 ----------------
    lines = [
        "# 828 味药材数据去重 / 合并报告",
        "",
        f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}  ",
        f"> 输入：`backend/data/tcm_828_herbs.json`（{len(raw)} 条，来源：参考仓库 "
        f"`zisu7/herb-llm-agent` 的 `static/tcm_828_herbs.json`）  ",
        f"> 输出：`backend/data/tcm_herbs_clean.json`（**{len(clean)} 条唯一药材**）",
        "",
        "## 〇、为什么要做这一步",
        "",
        "体检脚本（`check_dataset.py`）发现：原始 828 条中**唯一名称仅 604 个**。"
        "这不是 828 味药材，而是「828 条记录」——同一味药因被多个章节重复收录而出现多条，"
        "且内容互不一致。若直接导入并展示，用户会在药材列表里看到两个「续断」，"
        "且一个是补虚药、一个是活血化瘀药。",
        "",
        "| 项 | 数量 |",
        "|---|---|",
        f"| 原始记录数 | {len(raw)} |",
        f"| 唯一药材数 | {len(clean)} |",
        f"| 重名组数 | {len(dup_groups)} |",
        f"| 　其中内容完全相同 | {exact} |",
        f"| 　其中内容存在冲突 | {len(dup_groups) - exact} |",
        f"| 建议人工复核的条目 | {len(conflicted_records)} |",
        "",
        "## 一、合并策略（确定性，可复现）",
        "",
        "| 字段 | 规则 |",
        "|---|---|",
        "| `category` / `meridian` / `dosage` | 取出现次数最多者；并列时取首次出现 |",
        "| `effect` | 取最长值（信息更完整） |",
        "| `component` | 各来源成分清单取并集，按首次出现顺序去重 |",
        "| `merged_from` / `source_indexes` | 保留来源记录数与原索引，便于溯源 |",
        "| `conflicts` | 记录发生分歧的字段名，供人工复核 |",
        "",
        "## 二、建议人工复核的冲突条目",
        "",
        "| 药材 | 来源条数 | 冲突字段 |",
        "|---|---|---|",
    ]
    for c in conflicted_records:
        lines.append(f"| {c['name']} | {c['merged_from']} | {'、'.join(c['conflicts'])} |")
    lines += [
        "",
        "> 复核建议：优先按《中国药典》2020 版一部确定 `category` / `dosage`；"
        "`component` 取并集一般无害，可视篇幅取舍。",
        "",
        "## 三、对项目的实际影响",
        "",
        "- **对外口径需修正**：「828 味药材百科」应改为「**604 味唯一药材**」，"
        "或如实表述为「原始 828 条记录，去重合并后 604 味」。"
        "论文与答辩材料中不应再使用 828 作为药材品种数——这是一个可被现场核验的数字。"
        "- **推荐层不受影响**：推荐白名单是独立的 106 种国家目录，与这批数据无关。"
        "- **导入脚本已切换**：`import_data.py` 使用清洗后的 `tcm_herbs_clean.json`，"
        "原始文件保留作溯源凭证。",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 去重报告已写出：{REPORT}")


if __name__ == "__main__":
    main()
