# -*- coding: utf-8 -*-
"""编排层门面 —— service 层唯一入口

职责边界：
    service（consultation_service）负责「数据库读写 + 事务」；
    orchestration 负责「状态推进」。两者之间只传 dict。

这样 LangGraph 不感知 SQLAlchemy，Checkpointer 也不感知业务数据，
两边都能独立单测。
"""
from __future__ import annotations

from typing import Iterator

from app.orchestration import graph as og
from app.orchestration.state import ConsultationState

__all__ = ["run_consultation", "stream_consultation", "LANGGRAPH_AVAILABLE"]


def LANGGRAPH_AVAILABLE() -> bool:  # noqa: N802
    return og.LANGGRAPH_AVAILABLE


def run_consultation(state: ConsultationState | dict, *, thread_id: str) -> dict:
    """执行到 END，返回终态 dict"""
    return og.run(dict(state), thread_id=thread_id)


def stream_consultation(
    state: ConsultationState | dict, *, thread_id: str
) -> Iterator[tuple[str, dict]]:
    """节点级流式产出：(node_name, patch)"""
    yield from og.stream(dict(state), thread_id=thread_id)
