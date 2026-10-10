# -*- coding: utf-8 -*-
"""Pydantic 请求 / 响应模型"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------- 药材 ----------------
class HerbOut(BaseModel):
    id: int
    name: str
    category: str = ""
    meridian: str = ""
    effect: str = ""
    component: str = ""
    dosage: str = ""
    is_food_medicine: bool = False
    source_note: str = ""
    is_blacklisted: bool = False
    usage_policy: str = ""
    has_conflict: bool = False
    merged_from: int = 1


class CategoryOut(BaseModel):
    name: str
    count: int


class MeridianOut(BaseModel):
    name: str
    count: int


# ---------------- 问诊 ----------------
class ConsultationStartIn(BaseModel):
    chief_complaint: str = Field("", description="用户自由描述的主诉")
    questionnaire: dict[str, int] = Field(
        default_factory=dict, description="{question_id: 1-5 分}"
    )
    special_groups: list[str] = Field(
        default_factory=list, description="孕妇 / 哺乳期 / 儿童 / 慢性病患者"
    )
    top_n: int = 6


class ConsultationAnswerIn(BaseModel):
    answer: str = Field(..., description="用户对追问的回答")
    top_n: int = 6


class ConsultationOut(BaseModel):
    consultation_id: str
    phase: str
    status: str
    follow_up_questions: list[str] = Field(default_factory=list)
    follow_up_source: str = ""
    follow_up_round: int = 0
    message: str = ""
    constitution: dict[str, Any] | None = None
    recommend: dict[str, Any] | None = None
    interpretation: str = ""
    special_groups: list[str] = Field(default_factory=list)
    safety: dict[str, Any] | None = None
    disclaimer: str = ""


# ---------------- 安全自检（论文实验 / 答辩演示用） ----------------
class SafetyProbeIn(BaseModel):
    herb_names: list[str] = Field(default_factory=list, description="待校验的候选药材")
    special_groups: list[str] = Field(default_factory=list)


class OutputProbeIn(BaseModel):
    text: str
