# -*- coding: utf-8 -*-
"""P3 检索增强（RAG）测试

覆盖：
  - 知识库切片的完整性与溯源字段
  - Embedder 的确定性与归一化（索引可复现的前提）
  - 向量库的增删查与 metadata 过滤
  - 混合检索：语义 + 关键词，以及关键词通道的兜底作用
  - RAG 关闭时的降级路径（不能让系统崩）
  - 上下文构造的编号/来源/chunk_id 溯源契约
  - 架构适应度：domain 层不得依赖 rag /
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.rag import context as ctxmod
from app.rag import indexer
from app.rag.embedder import HashingEmbedder, char_ngrams, normalize_text
from app.rag.hybrid import BM25, HybridRetriever, expand_query
from app.rag.retriever import Evidence
from app.rag.vector_store import Chunk, MemoryVectorStore

BACKEND = Path(__file__).resolve().parents[1]


# ===========================================================================
# 4.1 知识库切片
# ===========================================================================
class TestKnowledgeBase:
    @pytest.fixture(scope="class")
    def chunks(self):
        return indexer.load_chunks(get_settings().rag_kb_path)

    def test_切片文件存在且不为空(self, chunks):
        assert len(chunks) > 0, "请先运行 scripts/build_kb.py"

    def test_切片类型齐全(self, chunks):
        types = {c.doc_type for c in chunks}
        for t in ("herb", "food_medicine", "constitution", "symptom", "safety"):
            assert t in types, f"缺少 {t} 类型切片"

    def test_每片都有溯源字段(self, chunks):
        for c in chunks[:50]:
            assert c.chunk_id, "chunk_id 是溯源主键"
            assert c.source, "必须标注来源"
            assert c.text.strip(), "正文不得为空"

    def test_chunk_id唯一(self, chunks):
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "chunk_id 必须唯一"

    def test_高危药材切片带黑名单标记(self, chunks):
        black = [c for c in chunks if c.metadata.get("is_blacklisted")]
        assert black, "知识库里应当有被标记为高危的药材"
        for c in black:
            assert "禁止" in c.text or "高危" in c.text

    def test_体质切片包含症状词_否则检索对不上用户语言(self, chunks):
        """用户说「怕冷」而不是「阳虚质」，知识库必须两边都有"""
        yang = next(c for c in chunks if c.chunk_id == "constitution:阳虚质")
        assert "怕冷" in yang.text or "畏寒" in yang.text

    def test_药食同源切片带禁忌与人群(self, chunks):
        foods = [c for c in chunks if c.doc_type == "food_medicine"]
        assert len(foods) >= 100
        with_meta = [c for c in foods if c.metadata.get("contraindications")
                     or c.metadata.get("special_groups")]
        assert with_meta, "至少要有一部分条目标注了禁忌/人群"


# ===========================================================================
# 4.2.2 向量化
# ===========================================================================
class TestEmbedder:
    def test_归一化后模长为1(self):
        emb = HashingEmbedder(dim=64)
        v = emb.embed_one("阳虚质 畏寒怕冷")
        assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6

    def test_相同输入结果可复现(self):
        """索引可复现的前提：不能用带随机种子的内置 hash"""
        a, b = HashingEmbedder(dim=64), HashingEmbedder(dim=64)
        assert a.embed_one("怕冷") == b.embed_one("怕冷")

    def test_空文本不炸(self):
        emb = HashingEmbedder(dim=64)
        v = emb.embed_one("")
        assert len(v) == 64

    def test_字面重叠越相似度越高(self):
        emb = HashingEmbedder(dim=128)
        base = emb.embed_one("阳虚质 畏寒怕冷 手脚冰凉")
        near = emb.embed_one("阳虚质 畏寒怕冷")
        far = emb.embed_one("清热解毒 消肿排脓")
        d_near = sum(x * y for x, y in zip(base, near))
        d_far = sum(x * y for x, y in zip(base, far))
        assert d_near > d_far

    def test_文本归一化去标点(self):
        assert normalize_text("黄芪，9-30g。") == "黄芪9-30g"

    def test_字符bigram(self):
        assert char_ngrams("怕冷", 2) == ["怕冷"]


# ===========================================================================
# 4.2.3 向量存储
# ===========================================================================
def _mk_chunks(n: int, doc_type: str = "herb") -> list[Chunk]:
    return [
        Chunk(chunk_id=f"{doc_type}:{i}", doc_type=doc_type,
              title=f"条目{i}", text=f"内容{i}", source="test",
              metadata={"idx": i, "doc_type": doc_type})
        for i in range(n)
    ]


class TestVectorStore:
    def test_增删查(self):
        s = MemoryVectorStore()
        chunks = _mk_chunks(5)
        s.add(chunks, [embedding_for(i) for i in range(5)])
        assert s.count() == 5
        hits = s.search(embedding_for(2), top_k=2)
        assert hits and hits[0].chunk_id == "herb:2"

    def test_metadata过滤生效(self):
        s = MemoryVectorStore()
        s.add(_mk_chunks(3, "herb"), [embedding_for(i) for i in range(3)])
        s.add(_mk_chunks(3, "symptom"), [embedding_for(i) for i in range(3)])
        assert s.count() == 6
        hits = s.search(embedding_for(1), top_k=5, where={"doc_type": "symptom"})
        assert all(h.chunk_id.startswith("symptom") for h in hits)

    def test_同id覆盖而非重复(self):
        s = MemoryVectorStore()
        c = [Chunk(chunk_id="x", text="原文", doc_type="herb", metadata={})]
        s.add(c, [embedding_for(0)])
        c2 = [Chunk(chunk_id="x", text="新文", doc_type="herb", metadata={})]
        s.add(c2, [embedding_for(1)])
        assert s.count() == 1
        assert s.get("x").text == "新文"

    def test_落盘后可恢复(self, tmp_path):
        s = MemoryVectorStore()
        s.add(_mk_chunks(4), [embedding_for(i) for i in range(4)])
        p = tmp_path / "idx.jsonl"
        s.save(p)
        s2 = MemoryVectorStore.load(p)
        assert s2.count() == 4
        assert s2.get("herb:0").text == "内容0"


def embedding_for(i: int, dim: int = 8) -> list[float]:
    """构造一个可预测的单位向量，第 i 维为 1"""
    v = [0.0] * dim
    v[i % dim] = 1.0
    return v


# ===========================================================================
# 4.3 混合检索
# ===========================================================================
class TestBM25:
    def test_命中词排前面(self):
        corpus = ["阳虚质 畏寒怕冷 手脚冰凉", "湿热质 面垢油光 口苦", "气虚质 乏力 气短"]
        bm = BM25(corpus)
        scores = bm.scores("畏寒怕冷")
        assert scores[0] == max(scores)

    def test_查询词不在语料时全为0(self):
        bm = BM25(["阳虚质 畏寒"])
        assert all(s == 0 for s in bm.scores("完全不相关的词"))

    def test_查询扩展带出同义词(self):
        expanded = expand_query("我怕冷")
        assert len(expanded) >= 2
        assert any("畏寒" in e for e in expanded)


class TestHybridRetriever:
    @pytest.fixture(scope="class")
    def retriever(self):
        indexer.reset_cache()
        idx = indexer.build_index(force=True)
        if idx is None:
            pytest.skip("知识库索引不可用")
        return idx.retriever

    def test_用户口语能命中体质条目(self, retriever):
        """用户不会说「阳虚质」，只会说「怕冷」"""
        hits = retriever.retrieve("我特别怕冷，手脚冰凉", top_k=5)
        assert hits, "必须有召回"
        top_ids = [h.chunk_id for h in hits[:3]]
        assert any("阳虚" in cid or "阳虚" in h.text
                   for cid, h in zip(top_ids, hits[:3]))

    def test_同义表述也能召回(self, retriever):
        hits = retriever.retrieve("晚上睡不着", top_k=5)
        assert any("失眠" in h.chunk_id or "阴虚" in h.chunk_id for h in hits)

    def test_返回结构满足溯源契约(self, retriever):
        hits = retriever.retrieve("怕冷", top_k=3)
        for h in hits:
            assert isinstance(h, Evidence)
            assert h.chunk_id and h.source and h.text

    def test_doc_type过滤(self, retriever):
        if not hasattr(retriever, "explain"):
            pytest.skip("检索器不支持过滤")
        hits = retriever.retrieve("怕冷", top_k=10, filters={"doc_type": "symptom"})
        assert all(h.metadata.get("doc_type") == "symptom" for h in hits)

    def test_空查询返回空(self, retriever):
        assert retriever.retrieve("", top_k=3) == []

    def test_两路对比可解释(self, retriever):
        if not hasattr(retriever, "explain"):
            pytest.skip("检索器不支持 explain")
        exp = retriever.explain("怕冷手脚冰凉", top_k=3)
        assert "semantic" in exp and "keyword" in exp and "fused" in exp
        assert exp["fused"], "融合结果不得为空"

    def test_关键词通道救了语义通道(self, retriever):
        """离线降级下语义通道噪声明显，靠关键词通道兜底——这是混合的意义"""
        if not hasattr(retriever, "explain"):
            pytest.skip("检索器不支持 explain")
        exp = retriever.explain("怕冷手脚冰凉", top_k=3)
        kw_ids = [h["chunk_id"] for h in exp["keyword"]]
        assert any("阳虚" in cid or "手脚冰凉" in cid or "畏寒" in cid for cid in kw_ids), \
            "关键词通道必须能命中体质/症状条目"


# ===========================================================================
# 4.4 上下文注入与降级
# ===========================================================================
class TestContext:
    def test_格式化带编号与chunk_id(self):
        evs = [
            Evidence(chunk_id="constitution:阳虚质", text="阳气不足，畏寒怕冷",
                     score=0.9, source="GB/T 46939"),
            Evidence(chunk_id="symptom:手脚冰凉", text="四肢不温",
                     score=0.8, source="通行表述"),
        ]
        text = ctxmod.format_context(evs)
        assert "[1]" in text and "[2]" in text
        assert "constitution:阳虚质" in text

    def test_空证据返回空串(self):
        assert ctxmod.format_context([]) == ""
        assert ctxmod.context_block("") == ""

    def test_上下文有长度上限(self):
        evs = [Evidence(chunk_id=f"c{i}", text="长文本" * 200, score=0.5, source="s")
               for i in range(10)]
        text = ctxmod.format_context(evs, max_chars=500)
        assert len(text) <= 900  # 上限 + 编号/来源的行 overhead

    def test_引用约束话术要求编号标注(self):
        assert "[" in ctxmod.CITATION_INSTRUCTION
        assert "不得" in ctxmod.CITATION_INSTRUCTION

    def test_RAG关闭时不注入上下文(self, monkeypatch):
        monkeypatch.setattr(ctxmod, "retrieve_evidence", lambda *a, **k: [])
        text, cites = ctxmod.build_context("怕冷")
        assert text == "" and cites == []


# ===========================================================================
# 4.5 / 架构适应度
# ===========================================================================
class TestRagApiAndFitness:
    def test_status接口(self, client):
        r = client.get("/api/v1/rag/status")
        assert r.status_code == 200
        body = r.json()["data"]
        assert "enabled" in body and "available" in body

    def test_search接口(self, client):
        r = client.get("/api/v1/rag/search", params={"q": "怕冷", "top_k": 3})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["count"] >= 0
        for h in body["hits"]:
            assert h["chunk_id"] and h["source"]

    def test_search按类型过滤(self, client):
        r = client.get("/api/v1/rag/search",
                       params={"q": "怕冷", "doc_type": "symptom", "top_k": 5})
        assert r.status_code == 200
        for h in r.json()["data"]["hits"]:
            assert h["doc_type"] == "symptom" or h["metadata"].get("doc_type") == "symptom"

    def test_领域层不得依赖rag(self):
        """架构适应度：domain 是零框架依赖层，不得引用 rag / chromadb"""
        import ast

        domain = BACKEND / "app" / "domain"
        bad = []
        for p in domain.rglob("*.py"):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] in ("chromadb",) or "app.rag" in a.name:
                            bad.append(f"{p}:{node.lineno}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if "app.rag" in node.module or node.module.split(".")[0] == "chromadb":
                        bad.append(f"{p}:{node.lineno}")
        assert not bad, f"domain 层禁止依赖 rag/chromadb：{bad}"

    def test_索引元数据可观测(self):
        status = indexer.rag_status()
        if status.get("available"):
            assert status["chunks"] > 0
            assert status["embedder"]
            assert status["vector_store"]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
