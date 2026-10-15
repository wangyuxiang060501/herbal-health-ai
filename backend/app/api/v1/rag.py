# -*- coding: utf-8 -*-
"""P3 RAG 检索接口

 GET /api/v1/rag/status   知识库索引状态（用了哪种 embedder / 多少片 / 是否降级）
 GET /api/v1/rag/search   混合检索（语义 + 关键词），返回可溯源条目
 GET /api/v1/rag/explain  两路召回对比（论文用：证明混合检索确实有效）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.rag import indexer
from app.rag.context import retrieve_evidence

router = APIRouter(prefix="/rag", tags=["RAG 知识检索（P3）"])


@router.get("/status", summary="知识库索引状态")
def status():
    return ok(indexer.rag_status())


@router.get("/search", summary="混合检索")
def search(
    q: str = Query(..., min_length=1, description="查询词，可以是症状描述或药材名"),
    top_k: int = Query(5, ge=1, le=20),
    doc_type: str | None = Query(None, description="按文档类型过滤：herb/food_medicine/constitution/symptom/safety"),
    db: Session = Depends(get_db),
):
    hits = retrieve_evidence(q, doc_types=[doc_type] if doc_type else None, top_k=top_k)
    return ok({
        "query": q,
        "count": len(hits),
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "text": h.text,
                "score": h.score,
                "source": h.source,
                "title": h.metadata.get("title", ""),
                "doc_type": h.metadata.get("doc_type", ""),
                "metadata": h.metadata,
            }
            for h in hits
        ],
    })


@router.get("/explain", summary="两路召回对比（证明混合检索有效）")
def explain(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
):
    """分别给出语义通道、关键词通道与融合结果

    论文里"为什么需要混合检索"这一节，可以直接贴这里的输出：
    离线降级时语义通道对「怕冷→畏寒」这类同义无能为力，靠关键词通道兜底。
    """
    idx = indexer.get_cached_index()
    if idx is None:
        return ok({"available": False, "reason": "RAG 索引不可用"})
    retriever = idx.retriever
    if not hasattr(retriever, "explain"):
        return ok({"available": False, "reason": "当前检索器不支持两路对比"})
    return ok({"available": True, **retriever.explain(q, top_k=top_k)})
