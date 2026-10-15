# -*- coding: utf-8 -*-
"""4.4 RAG 上下文构造：把检索结果变成可注入 Prompt 的、可溯源的文本

两件事必须同时做到，否则 RAG 就白做了：
  1. **可溯源**：每片带编号和 chunk_id，要求 LLM 引用来源，便于人工核对
     （4.5.2 验证「回答引用了知识库而非编造」就是靠这个）；
  2. **可降级**：RAG 不可用时返回空上下文，Prompt 结构不变，业务照跑。
"""
from __future__ import annotations

from ..core.config import get_settings
from ..core.logging import get_logger
from .indexer import fallback_retriever, get_retriever
from .retriever import Evidence

logger = get_logger("rag.context")

#: 注入 Prompt 时对 LLM 的约束话术——要求它引用而不能自由发挥
CITATION_INSTRUCTION = (
    "以下是知识库中检索到的相关条目，仅供你参考。\n"
    "硬性要求：\n"
    "1. 只能使用这些条目中明确出现的信息，不得自行补充知识库外的药理或疗效说法；\n"
    "2. 用到某条信息时，在句末用方括号标注其编号，例如「[2]」；\n"
    "3. 若条目内容与你的表述冲突，以条目为准；\n"
    "4. 若这些条目不足以支撑回答，就如实说明信息不足，不要编造。\n"
)


def retrieve_evidence(query: str, *, doc_types: list[str] | None = None,
                      top_k: int | None = None) -> list[Evidence]:
    """按文档类型过滤检索；RAG 不可用时返回空列表"""
    s = get_settings()
    if not s.rag_enabled:
        return []
    retriever = get_retriever()
    if retriever is None:
        return []
    k = top_k or s.rag_top_k
    try:
        hits = retriever.retrieve(query, top_k=k * 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("检索失败，本次不注入上下文",
                       extra={"extra_fields": {"error": str(e)[:120]}})
        return []
    if doc_types:
        wanted = set(doc_types)
        filtered = [h for h in hits if h.metadata.get("doc_type") in wanted]
        # 过滤后太少则保留原结果，避免"过滤把有用信息也滤没了"
        hits = filtered if len(filtered) >= 2 else hits
    return hits[:k]


def format_context(evidences: list[Evidence], *, max_chars: int = 1200) -> str:
    """把证据格式化成 Prompt 片段（带编号 + 来源 + chunk_id）

    `max_chars` 是硬上限，防止长条目把 token 预算吃光。
    """
    if not evidences:
        return ""
    lines = []
    used = 0
    for i, e in enumerate(evidences, start=1):
        text = (e.text or "").strip()
        if not text:
            continue
        room = max_chars - used
        if room <= 60:  # 剩下的空间连一句都放不下，就停
            break
        if len(text) > room:
            text = text[:room] + "…"
        src = e.source or "未标注来源"
        lines.append(f"[{i}] {text}\n    来源：{src}（chunk_id: {e.chunk_id}）")
        used += len(text)
    return "\n".join(lines)


def build_context(query: str, *, doc_types: list[str] | None = None,
                  top_k: int | None = None, max_chars: int = 1200) -> tuple[str, list[dict]]:
    """一步到位：检索 + 格式化

    返回 (上下文文本, citations)，citations 可直接进 API 响应供前端展示。
    """
    evidences = retrieve_evidence(query, doc_types=doc_types, top_k=top_k)
    text = format_context(evidences, max_chars=max_chars)
    citations = [
        {
            "chunk_id": e.chunk_id,
            "title": e.metadata.get("title", ""),
            "doc_type": e.metadata.get("doc_type", ""),
            "source": e.source,
            "score": e.score,
        }
        for e in evidences
    ]
    return text, citations


def context_block(text: str) -> str:
    """把上下文包成完整的 Prompt 段落（含引用约束）；无内容时返回空串"""
    if not text.strip():
        return ""
    return f"{CITATION_INSTRUCTION}\n{text}\n"
