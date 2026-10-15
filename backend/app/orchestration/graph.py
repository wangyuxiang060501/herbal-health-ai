# -*- coding: utf-8 -*-
"""状态图装配与编译（开发步骤清单 3.4.8）

LangGraph 是本进程唯一的编排引擎（ADR-006）。编译产物为单例，
同时支持同步执行（invoke）与节点级流式（stream）。
"""
from __future__ import annotations

from typing import Any, Iterator

from app.core.logging import get_logger
from app.orchestration.edges import (
    ROUTE_COLLECT,
    ROUTE_CONSTITUTION,
    ROUTE_SAFETY,
    route_after_collect,
    route_after_constitution,
    route_after_safety,
)
from app.orchestration.nodes import NODE_LABELS
from app.orchestration.state import FINAL_NODE, ConsultationState

logger = get_logger("orchestration.graph")

try:  # LangGraph 软依赖
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


def recheck_counter_node(state: ConsultationState) -> dict:
    """重配计数（单一职责节点，使「循环次数有界」这件事在图上一眼可见）"""
    return {"safety_recheck": int(state.get("safety_recheck") or 0) + 1}


# ===========================================================================
# 图定义
# ===========================================================================

NODES: dict[str, Any] = {}
EDGES: list[tuple[str, str]] = [
    ("START", "collect_symptoms"),
    ("herb_match", "safety_check"),
    ("food_recipe", "present"),
    ("present", "END"),
    ("safety_abort", "END"),
    ("follow_up", "END"),
    ("recheck_counter", "herb_match"),
]
CONDITIONAL_EDGES: list[tuple[str, Any, dict[str, str]]] = [
    ("collect_symptoms", route_after_collect, ROUTE_COLLECT),
    ("constitution_engine", route_after_constitution, ROUTE_CONSTITUTION),
    ("safety_check", route_after_safety, ROUTE_SAFETY),
]
# 路由重载：recheck 不是直接连 herb_match，而是先过计数器节点
ROUTE_SAFETY_GRAPH = dict(ROUTE_SAFETY)
ROUTE_SAFETY_GRAPH["recheck"] = "recheck_counter"


def _node_funcs() -> dict[str, Any]:
    from app.orchestration import nodes as n

    return {
        "collect_symptoms": n.collect_symptoms_node,
        "constitution_engine": n.constitution_engine_node,
        "follow_up": n.follow_up_node,
        "herb_match": n.herb_match_node,
        "safety_check": n.safety_check_node,
        "food_recipe": n.food_recipe_node,
        "present": n.present_node,
        "safety_abort": n.safety_abort_node,
        "recheck_counter": recheck_counter_node,
    }


def build_graph(checkpointer: Any | None = None):
    """构造并编译状态图"""
    if not LANGGRAPH_AVAILABLE:
        raise RuntimeError("langgraph 未安装，请 pip install langgraph")

    builder = StateGraph(ConsultationState)
    for name, fn in _node_funcs().items():
        builder.add_node(name, fn)

    builder.add_edge(START, "collect_symptoms")
    builder.add_conditional_edges("collect_symptoms", route_after_collect, ROUTE_COLLECT)
    builder.add_conditional_edges(
        "constitution_engine", route_after_constitution, ROUTE_CONSTITUTION
    )
    builder.add_edge("herb_match", "safety_check")
    builder.add_conditional_edges("safety_check", route_after_safety, ROUTE_SAFETY_GRAPH)
    builder.add_edge("food_recipe", "present")
    builder.add_edge("present", END)
    builder.add_edge("safety_abort", END)
    builder.add_edge("follow_up", END)
    builder.add_edge("recheck_counter", "herb_match")

    return builder.compile(checkpointer=checkpointer)


# --- 单例 ---

_GRAPH: Any | None = None


def get_checkpointer():
    """SQLite Checkpointer（3.6.1-3.6.3 会话快照 / 中断恢复）

    失败时降级为 MemorySaver，保证服务不因 checkpoint 故障而不可用。
    """
    try:
        import sqlite3
        from pathlib import Path

        from langgraph.checkpoint.sqlite import SqliteSaver

        from app.core.config import get_settings

        db_path = Path(get_settings().checkpoint_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 不用 SqliteSaver.from_conn_string：它返回 context manager，
        # 退出 with 就关连接，而图是长生命周期单例。改为自建连接。
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        # 与主库同样的并发处理：WAL + 写锁等待。问诊图每个节点都要写快照，
        # 并发下这里是除主库之外第二个 `database is locked` 的来源。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        saver = SqliteSaver(conn)
        saver.setup()
        logger.info("LangGraph checkpointer: sqlite(%s)", db_path)
        return saver
    except Exception as e:  # noqa: BLE001
        logger.warning("SQLite checkpointer 不可用，降级 MemorySaver：%s", str(e)[:120])
        return MemorySaver()


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(checkpointer=get_checkpointer())
    return _GRAPH


def reset_graph() -> None:
    global _GRAPH
    _GRAPH = None


# ===========================================================================
# 执行入口
# ===========================================================================


def run(state: dict, *, thread_id: str) -> dict:
    """同步执行到 END，返回最终状态"""
    graph = get_graph()
    return graph.invoke(state, config={"configurable": {"thread_id": thread_id}})


def stream(state: dict, *, thread_id: str) -> Iterator[tuple[str, dict]]:
    """按节点流式产出 (node_name, state_patch)，供 SSE meta 事件使用

    结尾额外产出一条 (FINAL_NODE, 完整终态)，避免调用方自己合并 patch。
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    for chunk in graph.stream(state, config=config, stream_mode="updates"):
        if isinstance(chunk, dict):
            for node_name, patch in chunk.items():
                if isinstance(patch, dict):
                    yield node_name, patch
    yield FINAL_NODE, graph.get_state(config).values


# ===========================================================================
# 可视化（论文配图）
# ===========================================================================


def graph_structure() -> dict:
    """返回节点/边结构（含中文标签），便于前端绘图与测试断言"""
    return {
        "engine": "langgraph" if LANGGRAPH_AVAILABLE else "fallback",
        "nodes": [
            {"id": k, "label": NODE_LABELS.get(k, k)}
            for k in list(_node_funcs()) + ["START", "END"]
        ],
        "edges": [{"from": a, "to": b} for a, b in EDGES],
        "conditional_edges": [
            {
                "from": src,
                "branches": [{"when": k, "to": v} for k, v in mapping.items()],
            }
            for src, _fn, mapping in [
                ("collect_symptoms", route_after_collect, ROUTE_COLLECT),
                ("constitution_engine", route_after_constitution, ROUTE_CONSTITUTION),
                ("safety_check", route_after_safety, ROUTE_SAFETY_GRAPH),
            ]
        ],
    }


def mermaid() -> str:
    """中文标注的状态图 —— 可直接贴进论文第四章 / mermaid 渲染器"""
    lines = ["stateDiagram-v2"]
    for name, label in NODE_LABELS.items():
        lines.append(f'    state "{label}" as {name}')
    lines.append("")
    lines.append("    [*] --> collect_symptoms")
    lines.append("    state fork1 <<choice>>")
    lines.append("    collect_symptoms --> fork1")
    lines.append("    fork1 --> safety_abort: 急症命中")
    lines.append("    fork1 --> constitution_engine: 正常")
    lines.append("")
    lines.append("    state fork2 <<choice>>")
    lines.append("    constitution_engine --> fork2")
    lines.append("    fork2 --> follow_up: 信息不足 且 追问轮次<2")
    lines.append("    fork2 --> herb_match: 信息充足")
    lines.append("    follow_up --> [*]: 追问≤3问/≤2轮，等待用户补充（Checkpointer 存快照）")
    lines.append("")
    lines.append("    herb_match --> safety_check: 候选药材（仅106白名单）")
    lines.append("    state fork3 <<choice>>")
    lines.append("    safety_check --> fork3")
    lines.append("    fork3 --> recheck_counter: 候选不足（可重配）")
    lines.append("    recheck_counter --> herb_match: 重新配伍（最多2次）")
    lines.append("    fork3 --> food_recipe: 通过/已替换（P3开关）")
    lines.append("    fork3 --> safety_abort: 输出侧阻断")
    lines.append("    food_recipe --> present")
    lines.append("    present --> [*]: 体质倾向+药材+免责声明")
    lines.append("    safety_abort --> [*]: 红色警示 + 引导就医")
    return "\n".join(lines)


def langgraph_mermaid() -> str:
    """LangGraph 自身导出的 mermaid（用于交叉验证图结构无误）"""
    if not LANGGRAPH_AVAILABLE:
        return ""
    try:
        return build_graph().get_graph().draw_mermaid()
    except Exception:  # noqa: BLE001
        return ""
