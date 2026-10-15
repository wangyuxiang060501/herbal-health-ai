# -*- coding: utf-8 -*-
"""4.2.3 向量存储模块

同样是可替换端口：
  - `MemoryVectorStore`  纯 Python（可选 numpy 加速），索引落盘为 JSONL，零依赖
  - `ChromaVectorStore`  Chroma 持久化客户端（依赖 chromadb，论文方案）

两者对上层暴露同一接口，切换只改配置 `RAG_VECTOR_STORE`。
索引里同时保存**向量与原文**，因此检索结果永远能给出可溯源的 chunk_id。
"""
from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Chunk:
    """一条知识切片（与 `scripts/build_kb.py` 产出的 jsonl 字段一致）"""

    chunk_id: str
    doc_type: str = ""
    title: str = ""
    text: str = ""
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Chunk":
        return Chunk(
            chunk_id=d.get("chunk_id", ""),
            doc_type=d.get("doc_type", ""),
            title=d.get("title", ""),
            text=d.get("text", ""),
            source=d.get("source", ""),
            metadata=d.get("metadata") or {},
        )


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    score: float
    chunk: Chunk | None = None


class VectorStore(ABC):
    """向量库端口"""

    #: 实现名，写入索引元数据
    name: str = "abstract"

    @abstractmethod
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(self, vector: list[float], *, top_k: int = 5,
               where: dict | None = None) -> list[SearchHit]:
        """余弦相似度检索；`where` 为 metadata 等值过滤（AND 语义）"""

    @abstractmethod
    def count(self) -> int:
        ...

    def _match(self, metadata: dict, where: dict | None) -> bool:
        if not where:
            return True
        for k, v in where.items():
            if metadata.get(k) != v:
                return False
        return True


def _dot(a: list[float], b: list[float]) -> float:
    """余弦（输入已归一化时即点积）。numpy 可用时走 numpy，否则纯 Python。"""
    try:
        import numpy as np  # noqa: WPS433

        va = np.asarray(a, dtype=np.float32)
        vb = np.asarray(b, dtype=np.float32)
        return float(np.dot(va, vb))
    except Exception:
        return math.fsum(x * y for x, y in zip(a, b))


class MemoryVectorStore(VectorStore):
    """内存向量库 + JSONL 落盘

    723 片 × 512 维的暴力检索在纯 Python 下约几十毫秒，
    对本项目规模完全够用；换成 Chroma 只是把这段换成 ANN 索引。
    """

    name = "memory"

    def __init__(self):
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []
        self._by_id: dict[str, int] = {}

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks 与 vectors 长度不一致")
        for c, v in zip(chunks, vectors):
            if c.chunk_id in self._by_id:
                idx = self._by_id[c.chunk_id]
                self._chunks[idx] = c
                self._vectors[idx] = v
            else:
                self._by_id[c.chunk_id] = len(self._chunks)
                self._chunks.append(c)
                self._vectors.append(v)

    def search(self, vector: list[float], *, top_k: int = 5,
               where: dict | None = None) -> list[SearchHit]:
        scores: list[tuple[float, int]] = []
        for i, v in enumerate(self._vectors):
            if not self._match(self._chunks[i].metadata, where):
                continue
            s = _dot(vector, v)
            if s > 0:
                scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], self._chunks[x[1]].chunk_id))
        return [
            SearchHit(chunk_id=self._chunks[i].chunk_id, score=round(s, 4), chunk=self._chunks[i])
            for s, i in scores[:top_k]
        ]

    def count(self) -> int:
        return len(self._chunks)

    def get(self, chunk_id: str) -> Chunk | None:
        idx = self._by_id.get(chunk_id)
        return self._chunks[idx] if idx is not None else None

    def all(self) -> list[Chunk]:
        return list(self._chunks)

    # ---------------- 持久化 ----------------
    def save(self, path: str | Path) -> None:
        """索引落盘：一行一片（向量与原文一起，便于重建/校验）"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for c, v in zip(self._chunks, self._vectors):
                f.write(json.dumps(
                    {"chunk": c.to_dict(), "vector": [round(x, 5) for x in v]},
                    ensure_ascii=False,
                ) + "\n")

    @staticmethod
    def load(path: str | Path) -> "MemoryVectorStore":
        p = Path(path)
        store = MemoryVectorStore()
        if not p.exists():
            return store
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                store.add([Chunk.from_dict(d["chunk"])], [d["vector"]])
        return store


class ChromaVectorStore(VectorStore):
    """Chroma 持久化向量库（论文方案）

    chromadb 未安装或初始化失败时，由 `build_vector_store()` 自动降级到
    MemoryVectorStore——保证知识库功能在离线环境也能演示。
    """

    name = "chroma"

    def __init__(self, persist_dir: str, collection: str = "tcm_kb"):
        import chromadb

        self._dir = persist_dir
        self._collection_name = collection
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        # metadata 只接受标量，列表要转成逗号串
        metas = []
        for c in chunks:
            m = {"doc_type": c.doc_type, "title": c.title, "source": c.source}
            for k, v in (c.metadata or {}).items():
                if isinstance(v, (str, int, float, bool)):
                    m[k] = v
                elif isinstance(v, list):
                    m[k] = ",".join(str(x) for x in v)
            metas.append(m)
        self._col.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=metas,
        )

    def search(self, vector: list[float], *, top_k: int = 5,
               where: dict | None = None) -> list[SearchHit]:
        res = self._col.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[SearchHit] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, cid in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            chunk = Chunk(
                chunk_id=cid,
                doc_type=meta.get("doc_type", ""),
                title=meta.get("title", ""),
                text=docs[i] if i < len(docs) else "",
                source=meta.get("source", ""),
                metadata={k: v for k, v in meta.items()
                          if k not in ("doc_type", "title", "source")},
            )
            # chroma cosine 距离 → 相似度
            score = 1.0 - (dists[i] if i < len(dists) else 0.0)
            hits.append(SearchHit(chunk_id=cid, score=round(score, 4), chunk=chunk))
        return hits

    def count(self) -> int:
        return self._col.count()


def build_vector_store(kind: str, *, persist_dir: str = "",
                       index_path: str = "", collection: str = "tcm_kb") -> VectorStore:
    """工厂：按配置构造向量库，不可用时自动降级到内存实现"""
    kind = (kind or "auto").lower()
    if kind in ("chroma", "auto") and persist_dir:
        try:
            return ChromaVectorStore(persist_dir, collection)
        except Exception:
            # 降级：离线环境也能跑
            pass
    if index_path and Path(index_path).exists():
        return MemoryVectorStore.load(index_path)
    return MemoryVectorStore()
