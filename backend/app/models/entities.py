# -*- coding: utf-8 -*-
"""ORM 模型們

表结构依据：`项目分析文档.md` 十二章 + `系统架构设计.md` 6.3 的增量：
  - herbs                 + is_food_medicine 标记 + source_note（溯源/仅供参考标注）
  - food_medicine_whitelist  新增（106 味白名单 × 9 字段 + 批次溯源）
  - safety_logs           新增（黑名单命中与替换审计）
  - usage_logs            新增（LLM token 用量与成本计量）
  - consultations         constitution 列存 ConstitutionResult JSON（支撑趋势图）
  - messages              追问对话记录
  - users                 MVP 不启用（单用户/匿名模式），表结构预留
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间"
    )


class User(Base, TimestampMixin):
    """用户表 —— MVP 阶段不启用（单用户/匿名模式），结构预留给 D2 解禁后使用"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), default="养生爱好者")
    password_hash: Mapped[str] = mapped_column(String(128), default="")
    special_groups: Mapped[str] = mapped_column(
        Text, default="[]", comment='JSON 数组：孕妇/哺乳期/儿童/慢性病患者'
    )

    consultations: Mapped[list["Consultation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Herb(Base, TimestampMixin):
    """药材查询层 —— 604 味唯一药材（828 条原始记录去重合并后）

    关键不变量：本表**只读展示**，绝不参与推荐。
    """

    __tablename__ = "herbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="", index=True, comment="如：补虚药")
    meridian: Mapped[str] = mapped_column(String(64), default="", index=True, comment="归经")
    effect: Mapped[str] = mapped_column(Text, default="", comment="功效")
    component: Mapped[str] = mapped_column(Text, default="", comment="主要成分")
    dosage: Mapped[str] = mapped_column(String(64), default="", comment="常用量")

    # --- 增量字段：数据分层标记 ---
    is_food_medicine: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True,
        comment="是否属于 106 种药食同源目录（决定能否进入推荐层）"
    )
    source_note: Mapped[str] = mapped_column(
        String(255), default="",
        comment="数据溯源标注，如「来源：开源仓库 herb-llm-agent，仅供参考」"
    )
    merged_from: Mapped[int] = mapped_column(
        Integer, default=1, comment="由多少条原始记录合并而来（>1 表示存在重名冲突）"
    )
    has_conflict: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="合并时是否存在字段分歧，需人工复核"
    )


class FoodMedicineWhitelist(Base, TimestampMixin):
    """106 种药食同源白名单 —— 推荐层的唯一合法来源（安全关键数据）

    法规依据：卫健委《既是食品又是中药材的物质目录》（截至 2026-05，4 批 106 种）。
    """

    __tablename__ = "food_medicine_whitelist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    alias: Mapped[str] = mapped_column(String(128), default="")
    batch: Mapped[int] = mapped_column(Integer, nullable=False, comment="第几批公布（1-4）")
    batch_source: Mapped[str] = mapped_column(String(255), default="", comment="批次出处")
    category: Mapped[str] = mapped_column(String(64), default="")
    nature_flavor: Mapped[str] = mapped_column(String(64), default="", comment="性味")
    meridians: Mapped[str] = mapped_column(String(128), default="", comment="归经")
    effects: Mapped[str] = mapped_column(Text, default="", comment="功效")
    dosage: Mapped[str] = mapped_column(String(64), default="", comment="常用量")
    contraindications: Mapped[str] = mapped_column(
        Text, default="[]", comment="JSON 数组：禁忌"
    )
    special_groups: Mapped[str] = mapped_column(
        Text, default="[]", comment="JSON 数组：慎用/禁用人群"
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已人工逐条核对《中国药典》"
    )
    source: Mapped[str] = mapped_column(String(255), default="")


class Consultation(Base, TimestampMixin):
    """问诊记录"""

    __tablename__ = "consultations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID / session_id")
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="in_progress", index=True,
        comment="in_progress | follow_up | completed | blocked_emergency | blocked_safety"
    )
    chief_complaint: Mapped[str] = mapped_column(Text, default="", comment="用户主诉")
    questionnaire: Mapped[str] = mapped_column(
        Text, default="{}", comment="问卷答案快照 JSON（每轮 answer 同步落库，防缓存丢失）"
    )
    special_groups: Mapped[str] = mapped_column(Text, default="[]", comment="JSON 数组")
    follow_up_rounds: Mapped[int] = mapped_column(Integer, default=0, comment="追问轮次上限 2")
    constitution: Mapped[str] = mapped_column(
        Text, default="", comment="ConstitutionResult JSON（含九维转化分，支撑趋势图）"
    )
    herbal_match: Mapped[str] = mapped_column(Text, default="", comment="HerbMatchResult JSON")
    recipe: Mapped[str] = mapped_column(Text, default="", comment="RecipePlan JSON（P3 阶段启用）")
    safety_verdict: Mapped[str] = mapped_column(Text, default="", comment="SafetyVerdict JSON")

    user: Mapped[User | None] = relationship(back_populates="consultations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )


class Message(Base, TimestampMixin):
    """问诊对话记录（追问 / 回答）"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consultation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("consultations.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="ai | user | system")
    content: Mapped[str] = mapped_column(Text, default="")
    round_no: Mapped[int] = mapped_column(Integer, default=0)

    consultation: Mapped[Consultation] = relationship(back_populates="messages")


class SafetyLog(Base, TimestampMixin):
    """安全审计日志：急症拦截 / 黑名单命中 / 药材替换"""

    __tablename__ = "safety_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consultation_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False, comment="命中的规则名")
    matched: Mapped[str] = mapped_column(String(255), default="", comment="命中的内容")
    action: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="block | flag | replace | filter"
    )
    replacement: Mapped[str] = mapped_column(String(64), default="", comment="替换为何种药材")
    detail: Mapped[str] = mapped_column(Text, default="")


class UsageLog(Base, TimestampMixin):
    """LLM 调用 usage 计量（成本护栏数据源）"""

    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    consultation_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
