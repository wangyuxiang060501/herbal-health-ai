# -*- coding: utf-8 -*-
"""4.2.4 知识库索引：切片 → 向量化 → 存储

**一个容易踩的坑**：向量必须和「生成它时的 embedder 状态」绑定。
TF-IDF 的 vocabulary / IDF 是 fit 出来的，如果只存向量、查询时新 fit 一个
embedder，查询向量和索引向量就不在同一个空间里，检索结果全是错的。

所以索引落盘时同时保存 embedder 元数据：
  - hashing → 保存 idf 表（可 JSON 序列化）
  - tfidf / sentence → 不做落盘，进程启动时现场构建（会在 status 里标注）

对外只暴露 `get_retriever()`，业务层无需知道用了哪种实现。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import get_settings
from ..core.logging import get_logger
from .embedder import Embedder, HashingEmbedder, build_embedder
from .hybrid import HybridRetriever
from .retriever import Retriever, WhitelistRetriever
from .vector_store import Chunk, MemoryVectorStore, VectorStore, build_vector_store

logger = get_logger("rag.indexer")


@dataclass
class RagIndex:
    store: VectorStore
    embedder: Embedder
    retriever: Retriever
    meta: dict = field(default_factory=dict)

    def to_status(self) -> dict:
        return {
            "available": True,
            "chunks": self.store.count(),
            "embedder": self.embedder.name,
            "dimension": self.embedder.dimension,
            "vector_store": self.store.name,
            **self.meta,
        }


_CACHE: RagIndex | None = None
_FAILED = False


def load_chunks(path: str | Path) -> list[Chunk]:
    p = Path(path)
    if not p.is_absolute():
        # 相对路径按 backend 目录解析
        p = Path(__file__).resolve().parents[2] / p
    if not p.exists():
        return []
    chunks = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.from_dict(json.loads(line)))
    return chunks


def _index_dir() -> Path:
    return Path(get_settings().rag_index_path).parent


def _weights(embedder: Embedder) -> tuple[float, float]:
    """两路融合权重：按 embedder 能力给，而不是拍脑袋给固定值

    hashing / tfidf 是**字面相似**而非语义相似，语义通道对「怕冷→畏寒」
    这类同义表述无能为力，召回里会有明显噪声（实测「怕冷手脚冰凉」的
    语义 top3 是使君子/黄连/密蒙花）。所以这两种 embedder 下降低语义权重，
    主要靠关键词通道 + 同义词扩展兜底。真语义模型（sentence-onnx）才两路并重。
    """
    if embedder.name in ("hashing-bigram", "tfidf-char"):
        return 0.4, 1.0
    return 1.0, 1.0


def _make_retriever(store: VectorStore, embedder: Embedder,
                    chunks: list[Chunk] | None = None) -> HybridRetriever:
    w_s, w_k = _weights(embedder)
    return HybridRetriever(store, embedder, chunks,
                           semantic_weight=w_s, keyword_weight=w_k)


def build_index(*, force: bool = False) -> RagIndex | None:
    """从切片产物构建索引

    force=True 时忽略磁盘缓存，重新构建（改了切片或 embedder 后用）。
    """
    s = get_settings()
    chunks = load_chunks(s.rag_kb_path)
    if not chunks:
        logger.warning("RAG 切片为空，请先运行 scripts/build_kb.py",
                       extra={"extra_fields": {"path": s.rag_kb_path}})
        return None

    corpus = [c.title + " " + c.text for c in chunks]
    embedder = build_embedder(s.rag_embedder, corpus=corpus, model_path=s.rag_model_path)

    # 向量库：Chroma 自带持久化，Memory 走 JSONL。
    # 两者的已有索引都能直接复用（count 对得上就不重建），
    # 前提是 embedder 状态一致——hashing/tfidf 的 fit 是确定性的，
    # 相同语料必然得到相同 idf，所以每次启动重新 fit 即可对齐。
    store = build_vector_store(
        s.rag_vector_store,
        persist_dir=s.rag_chroma_dir,
        index_path=s.rag_index_path,
        collection=s.rag_collection,
    )

    meta: dict = {}
    if force or store.count() != len(chunks):
        vectors = embedder.embed(corpus)
        store.add(chunks, vectors)
        meta["built"] = True
        logger.info("RAG 索引构建完成",
                    extra={"extra_fields": {"chunks": len(chunks),
                                            "embedder": embedder.name,
                                            "dim": embedder.dimension,
                                            "store": store.name}})
        # 内存库需要显式落盘；Chroma 自己持久化
        if persist_index(RagIndex(store, embedder,
                              _make_retriever(store, embedder, chunks), {})):
            meta["persisted_to"] = s.rag_index_path
    else:
        meta["reused_existing"] = True
        logger.info("RAG 索引复用已有向量库",
                    extra={"extra_fields": {"chunks": store.count(), "store": store.name}})

    return RagIndex(store, embedder, _make_retriever(store, embedder, chunks), meta)


def persist_index(index: RagIndex) -> bool:
    """落盘（仅 hashing + memory 组合；其他组合返回 False 并在日志说明）"""
    if not isinstance(index.store, MemoryVectorStore):
        logger.info("当前向量库由后端自行持久化，无需落盘",
                    extra={"extra_fields": {"store": index.store.name}})
        return False
    if not isinstance(index.embedder, HashingEmbedder):
        logger.info("当前 embedder 状态不可序列化，跳过落盘（运行时构建）",
                    extra={"extra_fields": {"embedder": index.embedder.name}})
        return False

    index_path = Path(get_settings().rag_index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index.store.save(index_path)
    meta = {
        "embedder": index.embedder.name,
        "dimension": index.embedder.dimension,
        "chunks": index.store.count(),
        "persistable": True,
        "idf": {str(k): v for k, v in getattr(index.embedder, "_idf", {}).items()},
    }
    index_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def get_retriever() -> Retriever | None:
    """业务层唯一入口：拿不到知识库时返回 None，由调用方决定是否降级

    降级路径（ADR-005）：RAG 不可用 → 退回 WhitelistRetriever（结构化精确检索），
    保证「检索增强」缺失时系统功能不中断。
    """
    global _CACHE, _FAILED
    s = get_settings()
    if not s.rag_enabled:
        return None
    if _CACHE is not None:
        return _CACHE.retriever
    if _FAILED:
        return None
    try:
        _CACHE = build_index()
        if _CACHE is None:
            _FAILED = True
            return None
        return _CACHE.retriever
    except Exception as e:  # noqa: BLE001
        _FAILED = True
        logger.warning("RAG 索引不可用，降级到结构化检索",
                       extra={"extra_fields": {"error": str(e)[:160]}})
        return None


def fallback_retriever() -> WhitelistRetriever:
    """RAG 不可用时的兜底：106 白名单精确检索"""
    from ..services import data_loader

    return data_loader.get_whitelist_retriever()


def reset_cache() -> None:
    """测试/重建索引用：清空进程内缓存"""
    global _CACHE, _FAILED
    _CACHE = None
    _FAILED = False


def rag_status() -> dict:
    """供 `/api/v1/rag/status` 展示：让"当前到底用的什么检索"可观测"""
    s = get_settings()
    base = {
        "enabled": s.rag_enabled,
        "kb_path": s.rag_kb_path,
        "configured_embedder": s.rag_embedder,
        "configured_vector_store": s.rag_vector_store,
        "top_k": s.rag_top_k,
    }
    if not s.rag_enabled:
        return {**base, "available": False, "reason": "RAG 已在配置中关闭"}
    try:
        idx = get_cached_index()
        if idx is None:
            return {**base, "available": False,
                    "reason": "知识库索引不可用，已降级为结构化精确检索"}
        return {**base, **idx.to_status()}
    except Exception as e:  # noqa: BLE001
        return {**base, "available": False, "reason": str(e)[:160]}


def get_cached_index() -> RagIndex | None:
    if _CACHE is None and not _FAILED:
        get_retriever()
    return _CACHE
