# -*- coding: utf-8 -*-
"""BC4 药膳推荐 —— 药材匹配器（候选来自规则表，再过安全层）

流程：
    体质结果 → 规则表打分（主体质满权重 / 兼夹体质 0.6 折减）
             → 主诉症状加成
             → 聚合排序
             → **强制过安全层**（黑名单 / 106 白名单 / 十八反十九畏 / 特殊人群）
             → HerbMatchResult

不变量（对应 系统架构设计.md 4.1-②）：
  - candidates[].in_whitelist 恒为 True
  - 任何被拦截的药材必须进 rejected 并说明原因（必要时给出替换）
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from ..constitution.engine import ConstitutionResult
from ..safety.guard import SafetyVerdict, WhitelistChecker, check_herbs
from .rule_table import (
    CONSTITUTION_HERB_RULES,
    RULE_TABLE_VERSION,
    SYMPTOM_HERB_HINTS,
    HerbRule,
)

SECONDARY_DISCOUNT = 0.6
SYMPTOM_BONUS = 0.5
# 主诉直供保底槽位：体质基线得分普遍高于症状加成，若不做保底，
# 用户明确说「失眠」却可能永远排不进推荐。这里强制为「直接命中主诉」的药材留出名额。
RESERVED_SYMPTOM_SLOTS = 2


@dataclass(slots=True)
class CandidateHerb:
    name: str
    score: float = 0.0
    in_whitelist: bool = True
    reason: str = ""
    dosage: str = ""
    category: str = ""
    contraindications: list[str] = field(default_factory=list)
    special_groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RejectedHerb:
    name: str
    reason: str
    replacement: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class HerbMatchResult:
    candidates: list[CandidateHerb] = field(default_factory=list)
    rejected: list[RejectedHerb] = field(default_factory=list)
    rule_table_version: str = RULE_TABLE_VERSION
    safety: SafetyVerdict | None = None
    enriched_from: str = "whitelist"

    def to_dict(self) -> dict:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "rejected": [r.to_dict() for r in self.rejected],
            "rule_table_version": self.rule_table_version,
            "safety": self.safety.to_dict() if self.safety else None,
            "enriched_from": self.enriched_from,
        }


def _collect_raw_candidates(result: ConstitutionResult) -> dict[str, dict]:
    """按体质规则表聚合原始候选（未排序）"""
    bag: dict[str, dict] = {}

    def put(rule: HerbRule, base_weight: float, source: str):
        if rule.weight <= 0:
            return
        item = bag.setdefault(
            rule.name,
            {"name": rule.name, "score": 0.0, "reasons": [], "sources": set()},
        )
        item["score"] += rule.weight * base_weight
        item["reasons"].append(f"{source}：{rule.reason}")
        item["sources"].add(source)

    primary_rules = CONSTITUTION_HERB_RULES.get(result.primary, ())
    for r in primary_rules:
        put(r, 1.0, f"主体质·{result.primary}")

    for sec in result.secondary:
        for r in CONSTITUTION_HERB_RULES.get(sec, ()):
            put(r, SECONDARY_DISCOUNT, f"兼夹·{sec}")

    return bag


def _apply_symptom_hints(bag: dict[str, dict], chief_complaint: str) -> list[str]:
    """按主诉中的关键词加成，返回命中的关键词"""
    hits: list[str] = []
    if not chief_complaint:
        return hits
    for keyword, rules in SYMPTOM_HERB_HINTS.items():
        if keyword in chief_complaint:
            hits.append(keyword)
            for r in rules:
                if r.weight <= 0:
                    continue
                item = bag.setdefault(
                    r.name,
                    {"name": r.name, "score": 0.0, "reasons": [], "sources": set()},
                )
                item["score"] += r.weight * SYMPTOM_BONUS
                item["reasons"].append(f"主诉「{keyword}」：{r.reason}")
                item["sources"].add(f"症状·{keyword}")
    return hits


def match_herbs(
    result: ConstitutionResult,
    whitelist: WhitelistChecker,
    whitelist_index: dict[str, dict] | None = None,
    chief_complaint: str = "",
    special_groups: Sequence[str] = (),
    top_n: int = 6,
) -> HerbMatchResult:
    """体质 → 候选药材（已过安全层）

    Args:
        result: 体质判定结果
        whitelist: 106 白名单校验器
        whitelist_index: {药材规范名: 白名单记录}，用于补充用量/禁忌字段
        chief_complaint: 用户主诉自由文本
        special_groups: 特殊人群标记
        top_n: 返回候选数量上限
    """
    bag = _collect_raw_candidates(result)
    _apply_symptom_hints(bag, chief_complaint)

    # 按得分降序、同分按名称稳定排序（保证可复现）
    ordered = sorted(bag.values(), key=lambda x: (-round(x["score"], 4), x["name"]))
    raw_names = [item["name"] for item in ordered]
    score_map = {item["name"]: item for item in ordered}

    passed, verdict = check_herbs(raw_names, whitelist, special_groups)
    passed_set = set(passed)

    def _is_symptom_hit(item: dict) -> bool:
        return any(s.startswith("症状·") for s in item.get("sources", ()))

    scored = [item for item in ordered if item["name"] in passed_set]
    base_items = [i for i in scored if not _is_symptom_hit(i)]
    hint_items = [i for i in scored if _is_symptom_hit(i)]

    # 保底：先取体质基线，再补主诉直供，最后回填（仍按得分排序输出）
    selected: list[dict] = base_items[: max(0, top_n - RESERVED_SYMPTOM_SLOTS)]
    picked = {i["name"] for i in selected}
    for h in hint_items[:RESERVED_SYMPTOM_SLOTS]:
        if h["name"] not in picked:
            selected.append(h)
            picked.add(h["name"])
    for x in scored:
        if len(selected) >= top_n:
            break
        if x["name"] not in picked:
            selected.append(x)
            picked.add(x["name"])
    selected.sort(key=lambda x: (-round(x["score"], 4), x["name"]))
    ordered_names = [i["name"] for i in selected]

    candidates: list[CandidateHerb] = []
    for name in ordered_names:
        meta = (whitelist_index or {}).get(name, {})
        src = score_map.get(name)
        score = round(src["score"], 3) if src else 0.0
        reasons = list(src["reasons"]) if src else []
        candidates.append(
            CandidateHerb(
                name=name,
                score=score,
                in_whitelist=True,
                reason="；".join(reasons),
                dosage=meta.get("dosage", ""),
                category=meta.get("category", ""),
                contraindications=meta.get("contraindications", []),
                special_groups=meta.get("special_groups", []),
            )
        )
    candidates = candidates[:top_n]

    rejected: list[RejectedHerb] = []
    for t in verdict.triggers:
        if t.action == "replace":
            rejected.append(RejectedHerb(name=t.matched, reason="高危药材黑名单命中",
                                         replacement=t.replacement))
        elif t.action == "reject" and t.rule == "非药食同源品种":
            rejected.append(RejectedHerb(name=t.matched, reason="不属于 106 种药食同源目录"))
        elif t.action == "reject" and t.rule == "特殊人群保护":
            rejected.append(RejectedHerb(name=t.matched, reason=t.detail or "特殊人群不宜使用"))
        elif t.action == "reject" and "配伍禁忌" in t.rule:
            rejected.append(RejectedHerb(name=t.matched, reason=t.rule + "：" + t.detail))

    return HerbMatchResult(
        candidates=candidates,
        rejected=rejected,
        rule_table_version=RULE_TABLE_VERSION,
        safety=verdict,
    )


def recommend(
    result: ConstitutionResult,
    whitelist: WhitelistChecker,
    *,
    whitelist_index: dict[str, dict] | None = None,
    chief_complaint: str = "",
    special_groups: Sequence[str] = (),
    top_n: int = 6,
) -> Any:
    """兼容别名"""
    return match_herbs(
        result, whitelist, whitelist_index, chief_complaint,
        list(special_groups), top_n,
    )
