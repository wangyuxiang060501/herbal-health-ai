# -*- coding: utf-8 -*-
"""4.1 知识库构建：把双层数据集 + 体质标准 + 安全规则转成可检索的知识文档

产出两份东西，用途不同：
  1) `data/kb/*.md`      —— 人类可读的 Markdown 知识文档（可人工核对、可入 Git）
  2) `data/kb/chunks.jsonl` —— 切片产物（一行一片），供向量化脚本消费

**切片策略（清单 4.1.4）**：按「条目」切分而非按字数切分。
药材条目本身就是天然的语义单元，硬按字数切会把「归经」和「用量」割裂到两片，
检索时召回的片段会残缺。每片保留完整元数据，便于溯源与过滤。

用法：
    python scripts/build_kb.py                 # 全量重建
    python scripts/build_kb.py --no-markdown   # 只产 chunks.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.domain.constitution.questionnaire import CONSTITUTION_INFO  # noqa: E402
from app.domain.recommendation.rule_table import CONSTITUTION_HERB_RULES  # noqa: E402
from app.domain.safety import constants as sc  # noqa: E402
from app.services import data_loader  # noqa: E402

KB_DIR = BACKEND / "data" / "kb"
CHUNKS = KB_DIR / "chunks.jsonl"


# ===========================================================================
# 切片构造
# ===========================================================================

def _chunk(chunk_id: str, doc_type: str, title: str, text: str,
           metadata: dict, source: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_type": doc_type,
        "title": title,
        "text": text.strip(),
        "metadata": metadata,
        "source": source,
    }


def herb_chunks() -> list[dict]:
    """604 味药材百科：一药一片"""
    out = []
    wl_names = data_loader.whitelist_names()
    for h in data_loader.load_clean_herbs():
        name = h["name"]
        is_food = name in wl_names
        parts = [f"{name}属于{h['category'] or '未分类'}。"]
        if h.get("meridian"):
            parts.append(f"归{h['meridian']}。")
        if h.get("effect"):
            parts.append(f"功效：{h['effect']}。")
        if h.get("component"):
            parts.append(f"主要成分：{h['component']}。")
        if h.get("dosage"):
            parts.append(f"常用量：{h['dosage']}。")
        # 安全与使用范围：这是最该被检索到的信息
        if h.get("name") in set(sc.BLACKLIST_HERBS):
            parts.append("该品种属于高危药材，禁止进入任何药膳或食疗方案。")
        elif is_food:
            parts.append("该品种属于国家药食同源目录，可用于日常食养。")
        else:
            parts.append("该品种不属于药食同源目录，仅供知识查询，不得用于药膳方案。")
        if h.get("conflicts"):
            parts.append("注意：原始数据中存在不同来源的分类冲突，使用时须与《中国药典》核对。")

        out.append(_chunk(
            chunk_id=f"herb:{name}",
            doc_type="herb",
            title=name,
            text="".join(parts),
            metadata={
                "herb": name,
                "category": h.get("category", ""),
                "meridian": h.get("meridian", ""),
                "dosage": h.get("dosage", ""),
                "is_food_medicine": is_food,
                "is_blacklisted": name in set(sc.BLACKLIST_HERBS),
                "has_conflict": bool(h.get("conflicts")),
                "verified": False,
            },
            source=data_loader.HERB_SOURCE_NOTE,
        ))
    return out


def food_chunks() -> list[dict]:
    """106 味药食同源档案：一味一片（含性味/禁忌/人群，是推荐安全性的依据）"""
    out = []
    for r in data_loader.load_whitelist_records():
        name = r["name"]
        parts = [f"{name}是国家药食同源目录品种（第{r.get('batch','')}批）。"]
        if r.get("alias"):
            parts.append(f"别名：{r['alias']}。")
        if r.get("nature_flavor"):
            parts.append(f"性味：{r['nature_flavor']}。")
        if r.get("meridians"):
            parts.append(f"归经：{r['meridians']}。")
        if r.get("effects"):
            parts.append(f"功效：{r['effects']}。")
        if r.get("dosage"):
            parts.append(f"常用量：{r['dosage']}。")
        contra = r.get("contraindications") or []
        if contra:
            parts.append(f"禁忌：{'；'.join(contra)}。")
        groups = r.get("special_groups") or []
        if groups:
            parts.append(f"特殊人群：{'；'.join(groups)}。")

        out.append(_chunk(
            chunk_id=f"food:{name}",
            doc_type="food_medicine",
            title=name,
            text="".join(parts),
            metadata={
                "herb": name,
                "category": r.get("category", ""),
                "batch": r.get("batch", ""),
                "is_food_medicine": True,
                "contraindications": contra,
                "special_groups": groups,
                "verified": bool(r.get("verified", False)),
            },
            source=f"{data_loader.WHITELIST_SOURCE_NOTE}·{r.get('batch_source','')}".strip("·"),
        ))
    return out


# 症状表现 → 体质：这是**知识库内容**，不是代码常量。
# 放在这里而非代码里，是为了能被人工核对、能被检索、能在论文里作为知识条目呈现。
# 每条 (症状簇, 主要体质, 伴随表现)
SYMPTOM_CONSTITUTION_MAP: list[tuple[str, str, list[str]]] = [
    ("畏寒怕冷", "阳虚质", ["手脚冰凉", "喜热饮", "精神不振", "腰膝冷痛"]),
    ("手脚冰凉", "阳虚质", ["畏寒", "四肢不温", "面色苍白"]),
    ("乏力疲乏", "气虚质", ["没力气", "气短", "自汗", "易感冒", "食欲不振"]),
    ("失眠", "阴虚质", ["不寐", "睡不着", "多梦", "心烦", "手足心热"]),
    ("口干咽燥", "阴虚质", ["口燥咽干", "盗汗", "眼睛干涩", "便秘"]),
    ("肥胖痰多", "痰湿质", ["形体肥胖", "腹部肥满", "口黏苔腻", "身体沉重", "胸闷"]),
    ("长痘出油", "湿热质", ["痤疮", "面垢油光", "口苦口臭", "小便黄", "皮肤瘙痒"]),
    ("瘀斑晦暗", "血瘀质", ["肤色晦暗", "淤青", "口唇色暗", "痛经", "痛有定处"]),
    ("情绪低落", "气郁质", ["郁闷", "胸胁胀满", "善太息", "焦虑", "压力大", "失眠"]),
    ("过敏", "特禀质", ["鼻塞喷嚏", "荨麻疹", "哮喘", "起疹子"]),
    ("精力充沛", "平和质", ["睡眠良好", "适应力强", "面色红润", "体态适中"]),
]


def constitution_chunks() -> list[dict]:
    """九种体质：一体质一片（定义 + 表现 + 常见症状词 + 常用食养药材）

    关键：**把症状词写进文本**。用户不会说「阳虚质」，只会说「怕冷」，
    知识库若只写体质术语，检索就永远对不上用户语言。
    """
    out = []
    herb_by_const = {
        c: [hr.name for hr in rules]
        for c, rules in CONSTITUTION_HERB_RULES.items()
    }
    # 反查：每个体质挂哪些症状词
    symptoms_by_const: dict[str, list[str]] = {}
    for sym, const, related in SYMPTOM_CONSTITUTION_MAP:
        symptoms_by_const.setdefault(const, []).append(sym)
        symptoms_by_const[const].extend(related)

    for name, info in CONSTITUTION_INFO.items():
        parts = [f"{name}：{info['desc']}。", f"常见表现倾向：{info['tendency']}。"]
        syms = sorted(set(symptoms_by_const.get(name, [])))
        if syms:
            parts.append(f"常见症状与体感：{'、'.join(syms)}。")
        herbs = herb_by_const.get(name) or []
        if herbs:
            parts.append(f"日常食养常用药材：{'、'.join(herbs[:8])}（均为药食同源品种）。")
        out.append(_chunk(
            chunk_id=f"constitution:{name}",
            doc_type="constitution",
            title=name,
            text="".join(parts),
            metadata={
                "constitution": name,
                "herbs": herbs,
                "symptoms": syms,
                "verified": False,
            },
            source="GB/T 46939—2025《中医体质分类与判定》· 九种体质通行表述",
        ))
    return out


def symptom_chunks() -> list[dict]:
    """症状条目：一症状一片，直接对应用户主诉语言

    用户主诉是「晚上睡不着」而不是「阴虚质」，
    这类切片让检索能**从用户语言直接命中体质方向**。
    """
    herb_by_const = {
        c: [hr.name for hr in rules]
        for c, rules in CONSTITUTION_HERB_RULES.items()
    }
    out = []
    for sym, const, related in SYMPTOM_CONSTITUTION_MAP:
        herbs = (herb_by_const.get(const) or [])[:5]
        text = (f"出现「{sym}」这类表现，常见与{const}相关；"
                f"伴随表现包括：{'、'.join(related)}。"
                + (f"日常食养可参考：{'、'.join(herbs)}。" if herbs else "")
                + "最终判定须以标准化体质问卷计分为准，不能仅凭单一症状下结论。")
        out.append(_chunk(
            chunk_id=f"symptom:{sym}",
            doc_type="symptom",
            title=sym,
            text=text,
            metadata={
                "symptom": sym,
                "constitution": const,
                "related": related,
                "herbs": herbs,
                "verified": False,
            },
            source="中医体质常见表现通行表述（须与 GB/T 46939—2025 核对）",
        ))
    return out


def safety_chunks() -> list[dict]:
    """安全规则：按主题切若干片"""
    out = []
    black = sorted(set(sc.BLACKLIST_HERBS))
    repl = sc.BLACKLIST_REPLACEMENT
    repl_text = "；".join(f"{k}→{v}" for k, v in repl.items() if k in set(black))

    out.append(_chunk(
        chunk_id="safety:blacklist",
        doc_type="safety",
        title="高危药材黑名单",
        text=f"以下药材属于高危品种，禁止进入任何药膳或食疗方案：{'、'.join(black)}。"
             f"若方案中出现这些品种，系统应拒绝或替换为药食同源品种。推荐替换关系：{repl_text}。",
        metadata={"rule": "blacklist", "count": len(black), "verified": False},
        source="系统安全合规层（规则常量）",
    ))

    emergency = getattr(sc, "EMERGENCY_KEYWORDS", None) or getattr(sc, "EMERGENCY_PATTERNS", [])
    if emergency:
        sample = list(emergency)[:24] if not isinstance(emergency, dict) else list(emergency.keys())[:24]
        out.append(_chunk(
            chunk_id="safety:emergency",
            doc_type="safety",
            title="急症识别与就医引导",
            text="当用户描述中出现以下急症相关表述时，系统必须立即终止问诊并引导就医，"
                 f"不得给出任何体质判定或食疗建议。关键词包括：{'、'.join(str(x) for x in sample)}等。"
                 "处理原则：安全第一，建议立即就医或拨打 120。",
            metadata={"rule": "emergency", "verified": False},
            source="系统安全合规层（规则常量）",
        ))

    # INCOMPATIBLE_PAIRS: list[tuple[药A, 药B, 规则名]]
    incompat = getattr(sc, "INCOMPATIBLE_PAIRS", []) or []
    if incompat:
        pairs = "；".join(f"{a}与{b}（{rule}）" for a, b, rule in incompat)
        out.append(_chunk(
            chunk_id="safety:incompatibility",
            doc_type="safety",
            title="配伍禁忌（十八反十九畏）",
            text=f"配伍时需回避以下组合：{pairs}。"
                 "推荐方案中的药材组合若命中上述任一组合，应提示调整或剔除其中一味。",
            metadata={"rule": "incompatibility", "count": len(incompat), "verified": False},
            source="中医药配伍禁忌通行表述（十八反十九畏）",
        ))

    # 特殊人群禁忌
    forbidden = getattr(sc, "SPECIAL_GROUP_FORBIDDEN", {}) or {}
    if forbidden:
        segs = []
        for group, herbs in forbidden.items():
            if herbs:
                segs.append(f"{group}应避免：{'、'.join(herbs)}")
        if segs:
            out.append(_chunk(
                chunk_id="safety:special_groups",
                doc_type="safety",
                title="特殊人群用药禁忌",
                text="；".join(segs) + "。推荐时必须先识别用户是否属于上述人群，再做人群禁忌校验。",
                metadata={"rule": "special_groups", "verified": False},
                source="系统安全合规层（规则常量）",
            ))
    return out


# ===========================================================================
# Markdown 文档输出（便于人工核对）
# ===========================================================================

def write_markdown(chunks: list[dict]) -> None:
    by_type: dict[str, list[dict]] = {}
    for c in chunks:
        by_type.setdefault(c["doc_type"], []).append(c)

    files = {
        "herb": "01-药材百科.md",
        "food_medicine": "02-药食同源档案.md",
        "constitution": "03-九种体质.md",
        "symptom": "04-症状与体质.md",
        "safety": "05-安全规则.md",
    }
    titles = {
        "herb": "# 药材百科（604 味，去重后）",
        "food_medicine": "# 药食同源档案（106 味）",
        "constitution": "# 九种体质",
        "symptom": "# 症状与体质（用户主诉 → 体质方向）",
        "safety": "# 安全规则",
    }
    for doc_type, fname in files.items():
        items = by_type.get(doc_type, [])
        if not items:
            continue
        lines = [titles[doc_type], ""]
        lines.append(f"> 共 {len(items)} 条 · 由 `scripts/build_kb.py` 自动生成，请勿手改。")
        lines.append("")
        for c in items:
            lines.append(f"## {c['title']}")
            lines.append("")
            lines.append(c["text"])
            lines.append("")
            lines.append(f"<!-- chunk_id: {c['chunk_id']} -->")
            lines.append("")
        (KB_DIR / fname).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-markdown", action="store_true", help="只产 chunks.jsonl")
    args = parser.parse_args()

    KB_DIR.mkdir(parents=True, exist_ok=True)

    chunks = (herb_chunks() + food_chunks() + constitution_chunks()
              + symptom_chunks() + safety_chunks())
    with CHUNKS.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    if not args.no_markdown:
        write_markdown(chunks)

    # 概况输出
    stat: dict[str, int] = {}
    for c in chunks:
        stat[c["doc_type"]] = stat.get(c["doc_type"], 0) + 1
    total_chars = sum(len(c["text"]) for c in chunks)
    print(f"[OK] 切片 {len(chunks)} 片 → {CHUNKS}")
    for k, v in sorted(stat.items()):
        print(f"     {k:<16} {v} 片")
    print(f"     总字符数 {total_chars}，平均 {total_chars // max(len(chunks), 1)} 字/片")
    if not args.no_markdown:
        print(f"[OK] Markdown 文档 → {KB_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
