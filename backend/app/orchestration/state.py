# -*- coding: utf-8 -*-
"""LangGraph 会话状态契约 —— ConsultationState

对应 `系统架构设计.md` 4.6 + `开发步骤清单.md` 3.4.1。

设计约束：
  1. **可序列化**：状态里只放 dict / list / str / int / bool，
     绝不放 ORM 对象或领域 dataclass —— 否则 SQLite Checkpointer 无法落盘。
  2. **归约器显式声明**：多节点写入同一字段时必须配 reducer，
     否则 LangGraph 默认「后写覆盖」，会丢掉先前节点的结果。
  3. **领域层零侵入**：本模块可以 import domain，反方向禁止。
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

MAX_FOLLOWUP_ROUNDS = 2      # 追问轮次上限（`项目分析文档.md` 10.2「1-2 轮」）
MAX_SAFETY_RECHECK = 2       # 安全替换后重新配伍的次数上限（防死循环）
FINAL_NODE = "__final__"     # stream 结束哨兵：携带合并后的完整终态


# ---------------------------------------------------------------------------
# 归约器
# ---------------------------------------------------------------------------


def merge_answers(left: dict[str, int], right: dict[str, int] | None) -> dict[str, int]:
    """问卷答案合并：同题取较高分（后一轮的补充可以加强信号，不覆盖已有高分）"""
    if not right:
        return dict(left or {})
    out = dict(left or {})
    for k, v in right.items():
        try:
            v_int = int(v)
        except (TypeError, ValueError):
            continue
        out[k] = max(out.get(k, 0), v_int)
    return out


def merge_unique(left: list, right: list | None) -> list:
    """去重保序合并（special_groups / asked_questions）"""
    out = list(left or [])
    for x in right or []:
        if x not in out:
            out.append(x)
    return out


def append_list(left: list, right: list | None) -> list:
    """追加（safety_flags / trace —— 允许重复，因为要保留时序）"""
    return list(left or []) + list(right or [])


# ---------------------------------------------------------------------------
# 状态本体
# ---------------------------------------------------------------------------


class ConsultationState(TypedDict, total=False):
    """一次问诊的完整状态

    约定：所有键都允许缺失（total=False），由编排层保证进入终态时的完备性。
    """

    # --- 输入 ---
    session_id: str
    user_id: int | None
    user_input: str                 # 本轮用户输入（主诉 / 追问答案）
    top_n: int
    enable_recipe: bool             # 是否启用 Agent3 药膳生成（P3）

    # --- 采集（collect_symptoms 写入）---
    chief_complaint: str
    questionnaire: Annotated[dict[str, int], merge_answers]
    special_groups: Annotated[list[str], merge_unique]
    input_verdict: dict | None      # 输入侧安全判定
    missing_dimensions: list[str]

    # --- 轮次控制 ---
    follow_up_rounds: int
    asked_questions: Annotated[list[str], merge_unique]
    safety_recheck: int

    # --- 产物 ---
    constitution: dict | None       # ConstitutionResult JSON
    herbs: dict | None              # HerbMatchResult JSON
    recipe: dict | None             # RecipePlan JSON（P3）
    follow_up_questions: list[str]
    follow_up_source: str           # llm:<provider>:<model> | template
    interpretation: str
    interpretation_source: str
    herb_explanation: str

    # --- RAG 引用（P3，各 LLM 节点按需追加，供前端展示"这句依据哪条知识"）---
    rag_citations: Annotated[list[dict], append_list]
    rag_available: bool

    # --- 安全 ---
    safety_flags: Annotated[list[dict], append_list]
    safety_verdict: dict | None
    blocked: bool
    block_reason: str
    block_kind: str                 # emergency | safety

    # --- 终态 ---
    phase: str                      # follow_up | completed | blocked
    completed: bool
    disclaimer: str

    # --- 可观测性（SSE meta 事件 + 论文配图数据来源）---
    trace: Annotated[list[dict], append_list]


def new_state(
    session_id: str,
    *,
    user_input: str = "",
    questionnaire: dict[str, int] | None = None,
    special_groups: list[str] | None = None,
    user_id: int | None = None,
    top_n: int = 6,
    enable_recipe: bool = False,
    follow_up_rounds: int = 0,
    chief_complaint: str = "",
) -> ConsultationState:
    """构造初始状态（唯一入口，避免散落各处手写 dict）"""
    return ConsultationState(
        session_id=session_id,
        user_id=user_id,
        user_input=user_input,
        chief_complaint=chief_complaint or user_input,
        questionnaire=dict(questionnaire or {}),
        special_groups=list(special_groups or []),
        top_n=top_n,
        enable_recipe=enable_recipe,
        follow_up_rounds=follow_up_rounds,
        asked_questions=[],
        safety_flags=[],
        trace=[],
        blocked=False,
        completed=False,
        phase="",
    )


def trace_entry(node: str, label: str, **extra: Any) -> dict:
    """节点轨迹条目（供 SSE meta 事件与事后复盘）"""
    from datetime import datetime

    item = {"node": node, "label": label, "at": datetime.now().strftime("%H:%M:%S")}
    item.update(extra)
    return item
