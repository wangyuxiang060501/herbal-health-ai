# -*- coding: utf-8 -*-
"""4.3 检索器：语义检索 + 关键词检索的混合（RRF 融合）

为什么必须混合？
  本项目的 embedder 在离线降级时是**字面相似**而非语义相似
  （见 `embedder.py` 的说明）。用户说「怕冷」，知识库里写的是「畏寒」，
  纯向量检索会漏掉。因此这里额外加一条 BM25 关键词通道，
  并用 **RRF（Reciprocal Rank Fusion）** 融合两路排名。

RRF 的好处是不需要两路分数可比：
  score(d) = Σ  w_i / (k + rank_i(d))     （k=60 为通行取值）
只依赖排名，天然规避「余弦 0.3 和 BM25 8.7 怎么加权」的问题。
"""
from __future__ import annotations

import math
from collections import Counter

from .embedder import Embedder, char_ngrams
from .retriever import Evidence, Retriever
from .vector_store import Chunk, SearchHit, VectorStore

# ---------------------------------------------------------------------------
# 同义词扩展：弥补字面相似模型的语义盲区
# 只做**单向归一**到知识库用语，不做自由联想，避免引入错误召回
# ---------------------------------------------------------------------------
SYNONYMS: dict[str, list[str]] = {
    "怕冷": ["畏寒", "阳虚"],
    "畏寒": ["怕冷", "阳虚"],
    "手脚冰凉": ["四肢不温", "阳虚"],
    "失眠": ["不寐", "睡眠"],
    "睡不着": ["不寐", "失眠"],
    "没力气": ["乏力", "气虚"],
    "乏力": ["没力气", "气虚"],
    "疲劳": ["乏力", "气虚"],
    "累": ["乏力", "气虚"],
    "出汗": ["自汗", "盗汗"],
    "盗汗": ["阴虚"],
    "口干": ["口燥咽干", "阴虚"],
    "上火": ["湿热", "阴虚"],
    "长痘": ["痤疮", "湿热"],
    "肥胖": ["痰湿", "形体肥胖"],
    "痰多": ["痰湿"],
    "胸闷": ["痰湿", "气郁"],
    "郁闷": ["气郁"],
    "压力大": ["气郁"],
    "脸色暗": ["血瘀", "晦暗"],
    "淤青": ["血瘀", "瘀斑"],
    "过敏": ["特禀"],
    "消化不好": ["脾虚", "气虚"],
    "拉肚子": ["泄泻", "脾虚"],
    "便秘": ["肠燥", "阴虚"],
}

RRF_K = 60


class BM25:
    """极简 BM25，term = 字符 bigram

    用 bigram 而非分词，避免引入 jieba 依赖，同时对中文短文本足够。
    """

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(char_ngrams(d)) for d in corpus]
        self.doc_len = [sum(c.values()) for c in self.docs]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.N = len(self.docs)
        self.df: Counter = Counter()
        for c in self.docs:
            self.df.update(c.keys())

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def scores(self, query: str) -> list[float]:
        q_terms = Counter(char_ngrams(query))
        out = [0.0] * self.N
        for term, qtf in q_terms.items():
            idf = self._idf(term)
            for i, doc in enumerate(self.docs):
                tf = doc.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avg_len or 1.0))
                out[i] += idf * (tf * (self.k1 + 1)) / (denom or 1.0)
        return out


def expand_query(query: str) -> list[str]:
    """查询扩展：原查询 + 命中的同义词（原查询权重最高）"""
    out = [query]
    for word, syns in SYNONYMS.items():
        if word in query:
            out.append(" ".join(syns))
    return out


class HybridRetriever(Retriever):
    """混合检索器（实现 `Retriever` 端口，可直接替换 WhitelistRetriever）"""

    def __init__(self, store: VectorStore, embedder: Embedder,
                 chunks: list[Chunk] | None = None,
                 semantic_weight: float = 1.0, keyword_weight: float = 1.0,
                 top_k_semantic: int = 20, top_k_keyword: int = 20):
        self.store = store
        self.embedder = embedder
        self.w_s = semantic_weight
        self.w_k = keyword_weight
        self.k_s = top_k_semantic
        self.k_k = top_k_keyword

        # BM25 需要完整语料。Chroma 不提供"列出全部"接口，
        # 所以由 indexer 显式传入切片列表，不能依赖 store。
        if chunks is None:
            chunks = store.all() if hasattr(store, "all") else []
        self.chunks: list[Chunk] = list(chunks)
        self._by_id = {c.chunk_id: c for c in chunks}
        self.bm25 = BM25([c.title + " " + c.text for c in chunks]) if chunks else None

    # ---------------- 单通道 ----------------
    def _semantic(self, query: str, top_k: int, where: dict | None) -> list[SearchHit]:
        if self.store.count() == 0:
            return []
        vec = self.embedder.embed_one(query)
        return self.store.search(vec, top_k=top_k, where=where)

    def _keyword(self, query: str, top_k: int, where: dict | None) -> list[SearchHit]:
        if not self.bm25 or not self.chunks:
            return []
        # 多查询（含同义扩展）取各片最高分
        best: dict[str, float] = {}
        for q in expand_query(query):
            for i, s in enumerate(self.bm25.scores(q)):
                if s <= 0:
                    continue
                c = self.chunks[i]
                if where and not all(c.metadata.get(k) == v for k, v in where.items()):
                    continue
                if s > best.get(c.chunk_id, 0.0):
                    best[c.chunk_id] = s
        ranked = sorted(best.items(), key=lambda x: (-x[1], x[0]))[:top_k]
        return [
            SearchHit(chunk_id=cid, score=round(score, 4), chunk=self._by_id.get(cid))
            for cid, score in ranked
        ]

    # ---------------- 融合 ----------------
    @staticmethod
    def _rrf(rank_lists: list[list[SearchHit]], weights: list[float]) -> list[SearchHit]:
        fused: dict[str, float] = {}
        first: dict[str, SearchHit] = {}
        for hits, w in zip(rank_lists, weights):
            for rank, h in enumerate(hits):
                fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + w / (RRF_K + rank + 1)
                first.setdefault(h.chunk_id, h)
        out = []
        for cid, s in sorted(fused.items(), key=lambda x: (-x[1], x[0])):
            h = first[cid]
            out.append(SearchHit(chunk_id=cid, score=round(s, 6), chunk=h.chunk))
        return out

    def retrieve(self, query: str, *, top_k: int = 5,
                 filters: dict | None = None) -> list[Evidence]:
        q = (query or "").strip()
        if not q:
            return []
        semantic = self._semantic(q, self.k_s, filters)
        keyword = self._keyword(q, self.k_k, filters)
        fused = self._rrf([semantic, keyword], [self.w_s, self.w_k])

        out: list[Evidence] = []
        for h in fused[:top_k]:
            c = h.chunk or self._by_id.get(h.chunk_id)
            if not c:
                continue
            out.append(Evidence(
                chunk_id=c.chunk_id,
                text=c.text,
                score=h.score,
                source=c.source,
                metadata={
                    **c.metadata,
                    "doc_type": c.doc_type,
                    "title": c.title,
                },
            ))
        return out

    def explain(self, query: str, *, top_k: int = 5,
                filters: dict | None = None) -> dict:
        """调试/论文用：分别给出两路召回与融合结果，证明混合确实有效"""
        q = (query or "").strip()
        s = self._semantic(q, top_k, filters)
        k = self._keyword(q, top_k, filters)
        fused = self._rrf([s, k], [self.w_s, self.w_k])[:top_k]
        return {
            "query": q,
            "expanded": expand_query(q),
            "semantic": [{"chunk_id": h.chunk_id, "score": h.score} for h in s],
            "keyword": [{"chunk_id": h.chunk_id, "score": h.score} for h in k],
            "fused": [{"chunk_id": h.chunk_id, "score": h.score} for h in fused],
        }
