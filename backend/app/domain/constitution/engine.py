# -*- coding: utf-8 -*-
"""BC3 体质辨识 —— 确定性判定引擎（ADR-002）

核心设计：**不用 LLM 做辨证**。
GB/T 46939—2025 给的是等级计分算法（原始分 → 转化分 → 阈值判定），
实现为纯函数后具备三大性质，恰好是论文可以直接写的设计亮点：

  1. 可复现 —— 同一份问卷答案必得同一份结果（temperature 无关）
  2. 可解释 —— 每条得分都能回溯到具体题目与答案（evidence 链）
  3. 可单测 —— 无需 mock LLM，离线可测（见 tests/test_constitution_engine.py）

对外契约 ConstitutionResult（系统架构设计.md 4.1-①）
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .questionnaire import (
    BIASED_CONSTITUTIONS,
    CONSTITUTION_INFO,
    FOLLOWUP_MARGIN,
    MAX_SECONDARY,
    NINE_CONSTITUTIONS,
    PINGHE,
    QUESTION_COUNT,
    QUESTIONNAIRE,
    SCORE_LABELS,
    THRESHOLD_OTHER_BASIC,
    THRESHOLD_PINGHE_YES,
    THRESHOLD_TENDENCY,
    THRESHOLD_YES,
    ALL_QUESTIONS,
)

STANDARD_NAME = "GB/T 46939—2025"
ITEM_SOURCE_NOTE = (
    "量表题面依据九种体质通行表述编写，待与 GB/T 46939—2025 标准原文逐条核对后替换（待确认项 U2/D7）"
)


# ===========================================================================
# 结果结构
# ===========================================================================


@dataclass(slots=True)
class DimensionScore:
    dimension: str
    raw_score: int = 0            # 原始分
    answered: int = 0             # 该维度实际作答题目数
    converted_score: float = 0.0  # 转化分 0-100
    judged: str = "未测评"         # 是 | 倾向是 | 否 | 未测评
    desc: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ConstitutionResult:
    primary: str
    secondary: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)      # 九维转化分
    details: dict[str, dict] = field(default_factory=dict)      # 逐维度明细
    evidence: list[str] = field(default_factory=list)
    standard: str = STANDARD_NAME
    confidence_flag: str = "倾向性判定"      # 固定措辞，禁止「你就是XX体质」
    deterministic: bool = True               # 恒 True，区分规则结论与 LLM 话术
    primary_label: str = ""                  # 「判定为是 / 倾向」的规范化表述
    needs_follow_up: bool = False            # 是否需要 AI 追问补信息
    follow_up_reason: str = ""
    answered_total: int = 0
    insufficient_info: bool = False
    rule_table_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "ConstitutionResult":
        """从持久化/跨层传递的 dict 还原（未知键忽略，缺失键取默认值）

        用途：LangGraph Checkpointer 落盘后重放、以及编排层从 ConsultationState
        中取出 constitution 交给下游匹配器。保持「领域对象不进状态」的约束。
        """
        valid = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (raw or {}).items() if k in valid})


def _normalize_answers(answers: Mapping[str, Any]) -> dict[str, int]:
    """把答案规整为 {question_id: 1..5}，过滤非法值与未知题号"""
    clean: dict[str, int] = {}
    for qid, val in answers.items():
        if qid not in ALL_QUESTIONS:
            continue
        try:
            score = int(val)
        except (TypeError, ValueError):
            continue
        if 1 <= score <= 5:
            clean[qid] = score
    return clean


def _converted_score(raw: int, n: int) -> float:
    """GB/T 转化分公式：转化分 = [(原始分 - 条目数) / (条目数 × 4)] × 100"""
    if n <= 0:
        return 0.0
    return round(((raw - n) / (n * 4)) * 100, 1)


def _judge(dim: str, converted: float, answered: int) -> str:
    if answered <= 0:
        return "未测评"
    if dim == PINGHE:
        if converted >= THRESHOLD_PINGHE_YES:
            return "是"
        if converted >= THRESHOLD_TENDENCY:
            return "倾向是"
        return "否"
    if converted >= THRESHOLD_YES:
        return "是"
    if converted >= THRESHOLD_TENDENCY:
        return "倾向是"
    return "否"


def score_dimensions(answers: Mapping[str, Any]) -> dict[str, DimensionScore]:
    """逐维度计算原始分 / 转化分 / 判定"""
    clean = _normalize_answers(answers)
    result: dict[str, DimensionScore] = {}

    for dim_key, dim in QUESTIONNAIRE.items():
        raw = 0
        answered = 0
        for q in dim.questions:
            if q.id in clean:
                raw += clean[q.id]
                answered += 1
        converted = _converted_score(raw, answered)
        info = CONSTITUTION_INFO[dim_key]
        result[dim_key] = DimensionScore(
            dimension=dim_key,
            raw_score=raw,
            answered=answered,
            converted_score=converted,
            judged=_judge(dim_key, converted, answered),
            desc=info["desc"],
        )
    return result


def build_evidence(answers: Mapping[str, Any], limit: int = 12) -> list[str]:
    """抽取评分 ≥3（有时/经常/总是）的答案作为推理依据的生成材料"""
    clean = _normalize_answers(answers)
    lines: list[str] = []
    for qid, score in clean.items():
        if score < 3:
            continue
        q = ALL_QUESTIONS[qid]
        lines.append(f"「{q.text}」回答：{SCORE_LABELS[score]} → 指向{q.dimension}特征")
    # 稳定排序，保证可复现
    return sorted(lines)[:limit]


# ===========================================================================
# 主入口
# ===========================================================================


def score(questionnaire: Mapping[str, Any], rule_table_version: str = "") -> ConstitutionResult:
    """纯函数：输入问卷答案，输出 ConstitutionResult

    不变量：
      - primary 必 ∈ 九种标准体质
      - scores 九个键齐全
      - 同一输入必得同一输出
    """
    details_raw = score_dimensions(questionnaire)
    clean = _normalize_answers(questionnaire)
    scores = {k: v.converted_score for k, v in details_raw.items()}
    details = {k: v.to_dict() for k, v in details_raw.items()}
    evidence = build_evidence(questionnaire)
    answered_total = len(clean)

    biased = {k: v for k, v in scores.items() if k in BIASED_CONSTITUTIONS}
    assessed_biased = {k: v for k, v in biased.items() if details_raw[k].answered > 0}

    pinghe_score = scores[PINGHE]
    pinghe_assessed = details_raw[PINGHE].answered > 0

    primary = PINGHE
    secondary: list[str] = []
    primary_label = ""
    needs_follow_up = False
    follow_up_reason = ""
    insufficient_info = False

    if not assessed_biased:
        # 完全没有偏颇维度数据 —— 不强行辨证
        insufficient_info = True
        needs_follow_up = True
        follow_up_reason = "尚未采集到可用于体质判定的有效信息，需继续问诊"
        primary = PINGHE if (not pinghe_assessed or pinghe_score >= THRESHOLD_PINGHE_YES) else PINGHE
        primary_label = "信息不足，暂不判定"
    else:
        ranked = sorted(assessed_biased.items(), key=lambda kv: (-kv[1], kv[0]))
        top_key, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

        if top_score >= THRESHOLD_TENDENCY:
            primary = top_key
            primary_label = "判定为是" if top_score >= THRESHOLD_YES else "倾向为"
            secondary = [
                k for k, s in ranked[1:]
                if s >= THRESHOLD_TENDENCY and k != primary
            ][:MAX_SECONDARY]
            # 前两名接近 → 信息不足以区分主体质，需要追问
            if len(ranked) > 1 and (top_score - runner_up) < FOLLOWUP_MARGIN:
                needs_follow_up = True
                follow_up_reason = (
                    f"{primary}（{top_score}分）与{ranked[1][0]}（{runner_up}分）接近，"
                    f"建议补充问诊以明确主体质"
                )
        else:
            # 全部偏颇维度 <30 → 平和
            primary = PINGHE
            if pinghe_assessed and pinghe_score >= THRESHOLD_PINGHE_YES:
                primary_label = "判定为平和质"
            else:
                primary_label = "基本倾向平和质（偏颇体质得分均未达阈值）"
                if pinghe_assessed and pinghe_score < THRESHOLD_PINGHE_YES:
                    needs_follow_up = True
                    follow_up_reason = "偏颇体质均未达阈值但平和质得分偏低，建议补充问诊确认"

    # 补充：整体信息量不足（回答题数偏少）也应触发追问
    if answered_total < len(NINE_CONSTITUTIONS):
        needs_follow_up = True
        if not follow_up_reason:
            follow_up_reason = (
                f"仅回答 {answered_total}/{QUESTION_COUNT} 题，"
                f"建议补齐问卷或由 AI 追问以支撑判定"
            )

    return ConstitutionResult(
        primary=primary,
        secondary=secondary,
        scores={k: scores[k] for k in NINE_CONSTITUTIONS},
        details={k: details[k] for k in NINE_CONSTITUTIONS},
        evidence=evidence,
        primary_label=primary_label,
        needs_follow_up=needs_follow_up,
        follow_up_reason=follow_up_reason,
        answered_total=answered_total,
        insufficient_info=insufficient_info,
        rule_table_version=rule_table_version,
    )


def to_trend_row(result: ConstitutionResult, at: str) -> dict:
    """体质趋势数据源（供 ECharts 折线图）"""
    return {"date": at, "primary": result.primary, **result.scores}


def interpret_to_words(result: ConstitutionResult) -> str:
    """把判定结果转成倾向性表述的中文短句（不含诊断用语）

    注意：这个函数产出的是**规则层的确定性文本**，
    最终的通俗化话术由 LLM 完成（职责划分见 ADR-002）。
    """
    name = result.primary
    info = CONSTITUTION_INFO[name]
    base = f"根据问卷计分，您的体质倾向于「{name}」"
    if result.secondary:
        base += f"，兼有{ '、'.join(result.secondary) }的表现"
    base += f"。{name}的常见特征为：{info['desc']}。"
    if result.needs_follow_up:
        base += f"（{result.follow_up_reason}）"
    return base


def interpret_to_words_from_dict(d: dict) -> str:
    """从已序列化的 ConstitutionResult（DB JSON）还原倾向性表述"""
    if not d or not d.get("primary"):
        return "该问诊尚未产出体质判定结论。"
    primary = d.get("primary", "")
    secondary = list(d.get("secondary") or [])
    label = d.get("primary_label") or "倾向性判定"
    result = ConstitutionResult(
        primary=primary,
        secondary=secondary,
        scores=d.get("scores") or {},
        details=d.get("details") or {},
        evidence=d.get("evidence") or [],
        primary_label=label,
        needs_follow_up=bool(d.get("needs_follow_up")),
        follow_up_reason=d.get("follow_up_reason") or "",
        answered_total=int(d.get("answered_total") or 0),
        standard=d.get("standard") or STANDARD_NAME,
    )
    return interpret_to_words(result)


def validate_all_nine_keys(result: ConstitutionResult) -> bool:
    return set(result.scores.keys()) == set(NINE_CONSTITUTIONS)


def missing_question_ids(answers: Mapping[str, Any]) -> Sequence[str]:
    clean = _normalize_answers(answers)
    return [qid for qid in ALL_QUESTIONS if qid not in clean]
