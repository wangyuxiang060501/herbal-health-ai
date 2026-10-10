# -*- coding: utf-8 -*-
"""BC3 体质辨识上下文（确定性规则引擎，不使用 LLM）"""
from .engine import (
    ITEM_SOURCE_NOTE,
    STANDARD_NAME,
    ConstitutionResult,
    DimensionScore,
    build_evidence,
    interpret_to_words,
    interpret_to_words_from_dict,
    missing_question_ids,
    score,
    score_dimensions,
    to_trend_row,
    validate_all_nine_keys,
)
from .questionnaire import (
    ALL_QUESTIONS,
    BIASED_CONSTITUTIONS,
    CONSTITUTION_INFO,
    NINE_CONSTITUTIONS,
    PINGHE,
    QI_XU,
    QI_YU,
    QUESTION_COUNT,
    QUESTIONNAIRE,
    SCORE_LABELS,
    SHI_RE,
    TAN_SHI,
    TE_BING,
    XUE_YU,
    YANG_XU,
    YIN_XU,
    Question,
    core_question_ids,
)

__all__ = [
    "STANDARD_NAME", "ITEM_SOURCE_NOTE", "ConstitutionResult", "DimensionScore",
    "score", "score_dimensions", "build_evidence", "interpret_to_words",
    "missing_question_ids", "to_trend_row", "validate_all_nine_keys",
    "ALL_QUESTIONS", "BIASED_CONSTITUTIONS", "CONSTITUTION_INFO", "NINE_CONSTITUTIONS",
    "PINGHE", "QI_XU", "QI_YU", "QUESTION_COUNT", "QUESTIONNAIRE", "SCORE_LABELS",
    "SHI_RE", "TAN_SHI", "TE_BING", "XUE_YU", "YANG_XU", "YIN_XU", "Question",
    "core_question_ids",
]
