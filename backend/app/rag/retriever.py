# -*- coding: utf-8 -*-
"""BC8 知识检索端口（阶段一：结构化精确检索）

对应 ADR-005 的**阶段 1（MVP）**：
  药材的性味/归经/用量是「封闭事实」，用 SQL / 索引精确取值，
  比向量相似度更可靠、可溯源；向量 RAG（Chroma）属于 P3 阶段
  （见 requirements-full.txt），届时 ChromaRetriever 实现同一 Retriever 接口即可替换，
  业务代码零改动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class Evidence:
    chunk_id: str = ""
    text: str = ""
    score: float = 1.0
    source: str = ""
    metadata: dict = None  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "text": self.text, "score": self.score,
            "source": self.source, "metadata": self.metadata or {},
        }


class Retriever(ABC):
    """检索端口（BC8 → BC2/BC4）"""

    @abstractmethod
    def retrieve(self, query: str, *, top_k: int = 5, filters: dict | None = None) -> list[Evidence]:
        ...


class WhitelistRetriever(Retriever):
    """阶段一实现：对 106 白名单做精确/包含式检索，带 chunk_id 溯源

    虽然它不做向量化，但**提前把溯源契约（chunk_id / source / metadata）跑通**，
    P3 换成 Chroma 时前端与 citations 逻辑无需改动。
    """

    def __init__(self, records: list[dict]):
        self._records = records
        self._by_name = {r["name"]: r for r in records if r.get("name")}
        self._by_base = {}
        for r in records:
            self._by_base.setdefault(r["name"].split("（")[0], r)

    def retrieve(self, query: str, *, top_k: int = 5, filters: dict | None = None) -> list[Evidence]:
        q = (query or "").strip()
        if not q:
            return []
        hits: list[Evidence] = []
        for name, rec in self._by_base.items():
            if name in q or q in name:
                hits.append(self._record_to_evidence(rec, 1.0))
                continue
            alias = rec.get("alias", "")
            if alias and (alias in q or q in alias):
                hits.append(self._record_to_evidence(rec, 0.9))
                continue
            effects = rec.get("effects", "")
            if q in effects:
                hits.append(self._record_to_evidence(rec, 0.6))
        category = (filters or {}).get("category")
        if category:
            hits = [h for h in hits if category in h.metadata.get("category", "")]
        hits.sort(key=lambda e: (-e.score, e.chunk_id))
        return hits[:top_k]

    def get(self, name: str) -> Evidence | None:
        rec = self._by_name.get(name) or self._by_base.get(name.split("（")[0].strip())
        return self._record_to_evidence(rec, 1.0) if rec else None

    def _record_to_evidence(self, rec: dict, score: float) -> Evidence:
        return Evidence(
            chunk_id=f"herb:{rec.get('name','')}",
            text=f"{rec.get('name','')}　{rec.get('nature_flavor','')}　归{rec.get('meridians','')}；"
                 f"功效：{rec.get('effects','')}；常用量：{rec.get('dosage','')}",
            score=score,
            source=f"卫健委药食同源目录（第{rec.get('batch','')}批）·《中国药典》",
            metadata={
                "herb": rec.get("name", ""),
                "category": rec.get("category", ""),
                "batch": rec.get("batch", ""),
                "verified": rec.get("verified", False),
            },
        )
