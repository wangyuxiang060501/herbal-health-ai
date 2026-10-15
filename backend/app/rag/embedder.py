# -*- coding: utf-8 -*-
"""4.2.2 文本向量化模块

设计要点：**向量化是可替换的能力，不是写死的依赖**。

论文/清单里写的是 Chroma + bge-small-zh-v1.5，但本机网络受限，
中文嵌入模型不一定下载得下来。所以这里定义 `Embedder` 端口并给出三种实现：

  - `HashingEmbedder`     零依赖：字符 n-gram 哈希 + TF 加权 + L2 归一化
  - `TfidfEmbedder`       依赖 scikit-learn：语料级 IDF 加权，字面重叠更准
  - `SentenceEmbedder`    依赖 ONNX 模型：真正的语义向量（bge-small-zh-v1.5 等）

三者对上层暴露同一接口，切换只改配置 `RAG_EMBEDDER`。
注意前两种是**字面/统计相似**，不是语义相似——所以检索必须走
`HybridRetriever` 的关键词通道兜底，详见 `hybrid.py`。
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter

# 中文/ASCII 之外的噪声（标点、空白）统一剔除，避免影响 n-gram
_NOISE = re.compile(r"[\s，。；：、（）()《》「」\"'，．・—/\\|]+")
# 连字符：数字之间的要保留（用量区间「9-30g」是有意义的信息），其余当噪声去掉
_DASH = re.compile(r"(?<!\d)-(?!\d)")


def normalize_text(text: str) -> str:
    """归一化：去标点空白、英文转小写。

    不做中文分词——字符 n-gram 对短文本更稳，也避免引入 jieba 依赖。
    """
    t = _NOISE.sub("", text or "")
    t = _DASH.sub("", t)
    return t.lower()


def char_ngrams(text: str, n: int = 2) -> list[str]:
    """字符 n-gram（默认 bigram）。中文里 bigram 已能表达大部分词面特征。"""
    t = normalize_text(text)
    if len(t) < n:
        return [t] if t else []
    return [t[i:i + n] for i in range(len(t) - n + 1)]


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class Embedder(ABC):
    """向量化端口"""

    #: 实现名，写入索引元数据，便于溯源「这个索引是谁建的」
    name: str = "abstract"

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表（已归一化）"""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashingEmbedder(Embedder):
    """零依赖哈希嵌入（hashing trick）

    把字符 bigram 哈希到固定维度并累加 TF，再做 L2 归一化。
    优点：不需要任何模型/网络，723 片索引毫秒级构建，结果完全可复现。
    局限：**只认字面重叠**。「怕冷」和「畏寒」字面不同，向量不相似——
    这是为什么检索要配合关键词通道与同义词表，见 `hybrid.py`。
    """

    name = "hashing-bigram"

    def __init__(self, dim: int = 512, ngram: int = 2, use_idf: bool = False):
        self._dim = dim
        self._ngram = ngram
        self._use_idf = use_idf
        self._idf: dict[int, float] = {}
        self._fitted = False

    @property
    def dimension(self) -> int:
        return self._dim

    def _hash(self, gram: str) -> int:
        # 稳定哈希：不用内置 hash（Python 字符串 hash 带随机种子，进程间不可复现）
        return int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16) % self._dim

    def fit(self, corpus: list[str]) -> None:
        """可选的 IDF 拟合：让「的」「功效」这类高频无区分度的 gram 权重降低"""
        n_docs = len(corpus)
        df: Counter = Counter()
        for doc in corpus:
            for h in {self._hash(g) for g in char_ngrams(doc, self._ngram)}:
                df[h] += 1
        self._idf = {h: math.log((n_docs + 1) / (c + 1)) + 1.0 for h, c in df.items()}
        self._fitted = True

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self._dim
            counter = Counter(self._hash(g) for g in char_ngrams(text, self._ngram))
            for idx, tf in counter.items():
                w = 1.0 + math.log(tf)  # 次线性 TF，避免长文本压过短文本
                if self._use_idf and self._fitted:
                    w *= self._idf.get(idx, math.log(len(texts) + 1) + 1.0)
                vec[idx] += w
            out.append(_l2(vec))
        return out


class TfidfEmbedder(Embedder):
    """scikit-learn TF-IDF（字符 n-gram）

    比哈希嵌入更准：IDF 在真实语料上拟合，且不做哈希降维（无冲突）。
    依赖 scikit-learn，未安装时 `is_available()` 返回 False，由工厂自动降级。
    """

    name = "tfidf-char"

    def __init__(self, dim: int = 1024, ngram_range: tuple[int, int] = (2, 3)):
        self._dim = dim
        self._ngram_range = ngram_range
        self._vec = None

    @property
    def dimension(self) -> int:
        return self._dim

    @staticmethod
    def is_available() -> bool:
        try:
            import sklearn  # noqa: F401
            return True
        except Exception:
            return False

    def fit(self, corpus: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vec = TfidfVectorizer(
            analyzer="char",
            ngram_range=self._ngram_range,
            max_features=self._dim,
            lowercase=True,
            sublinear_tf=True,
        )
        self._vec.fit([normalize_text(c) for c in corpus])
        self._dim = len(self._vec.vocabulary_)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._vec is None:
            raise RuntimeError("TfidfEmbedder 必须先 fit(corpus)")
        mat = self._vec.transform([normalize_text(t) for t in texts])
        dense = mat.toarray()
        return [_l2(row.tolist()) for row in dense]


class SentenceEmbedder(Embedder):
    """ONNX 句向量（bge-small-zh-v1.5 一类的中文模型）

    这是论文里写明的方案。需要：
      - onnxruntime
      - 一个 ONNX 格式的中文句向量模型（含 tokenizer 词表）

    模型缺失时 `is_available()` 返回 False，工厂自动降级到哈希/TF-IDF，
    **不會让系统起不来**。
    """

    name = "sentence-onnx"

    def __init__(self, model_path: str, dim: int = 512):
        self._path = model_path
        self._dim = dim
        self._session = None
        self._vocab: dict[str, int] = {}
        self._tokenizer = None

    @property
    def dimension(self) -> int:
        return self._dim

    @staticmethod
    def is_available(model_path: str) -> bool:
        from pathlib import Path

        if not Path(model_path).exists():
            return False
        try:
            import onnxruntime  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self) -> None:
        import json
        from pathlib import Path

        import onnxruntime as ort

        model_dir = Path(self._path)
        onnx_file = model_dir / "model.onnx" if model_dir.is_dir() else model_dir
        self._session = ort.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
        vocab_file = (model_dir if model_dir.is_dir() else model_dir.parent) / "vocab.txt"
        if vocab_file.exists():
            for i, line in enumerate(vocab_file.read_text(encoding="utf-8").splitlines()):
                tok = line.strip()
                if tok:
                    self._vocab[tok] = i
        # 维度以模型输出为准
        out_shape = self._session.get_outputs()[0].shape
        if len(out_shape) >= 2 and isinstance(out_shape[-1], int):
            self._dim = out_shape[-1]

    def _encode_text(self, text: str) -> tuple[list[int], list[int], list[int]]:
        """极简 WordPiece：按字切分 + 词表查表；未登录字走 [UNK]"""
        unk = self._vocab.get("[UNK]", 100)
        cls = self._vocab.get("[CLS]", 101)
        sep = self._vocab.get("[SEP]", 102)
        ids = [cls]
        for ch in normalize_text(text):
            if ch in self._vocab:
                ids.append(self._vocab[ch])
            else:
                # 尝试逐字回退：中文单字一般都在词表里
                ids.append(unk)
        ids.append(sep)
        n = len(ids)
        return ids, [0] * n, [1] * n

    def embed(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        if self._session is None:
            self._load()
        max_len = 512
        input_ids, token_types, attention = [], [], []
        for t in texts:
            ids, tt, am = self._encode_text(t)
            ids, tt, am = ids[:max_len], tt[:max_len], am[:max_len]
            pad = max_len - len(ids)
            input_ids.append(ids + [0] * pad)
            token_types.append(tt + [0] * pad)
            attention.append(am + [0] * pad)

        feeds = {
            self._session.get_inputs()[0].name: np.array(input_ids, dtype=np.int64),
            self._session.get_inputs()[1].name: np.array(token_types, dtype=np.int64),
            self._session.get_inputs()[2].name: np.array(attention, dtype=np.int64),
        }
        out = self._session.run(None, feeds)[0]
        # mean pooling（按 attention mask）
        mask = np.array(attention, dtype=np.float32)[:, :, None]
        emb = (out * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
        return [_l2(row.tolist()) for row in emb]


def build_embedder(kind: str, *, corpus: list[str] | None = None,
                   model_path: str = "") -> Embedder:
    """工厂：按配置构造 embedder，不可用时自动降级

    降级链（在配置里显式声明，便于论文里写「成本/可用性护栏」）：
        sentence-onnx → tfidf-char → hashing-bigram
    """
    kind = (kind or "auto").lower()
    order = {
        "sentence": ["sentence", "tfidf", "hashing"],
        "tfidf": ["tfidf", "hashing"],
        "hashing": ["hashing"],
        "auto": ["sentence", "tfidf", "hashing"],
    }.get(kind, [kind, "hashing"])

    for cand in order:
        if cand == "sentence":
            if model_path and SentenceEmbedder.is_available(model_path):
                emb = SentenceEmbedder(model_path)
                emb.embed([" warmup"])
                return emb
        elif cand == "tfidf":
            if TfidfEmbedder.is_available() and corpus:
                emb = TfidfEmbedder()
                emb.fit(corpus)
                return emb
        elif cand == "hashing":
            emb = HashingEmbedder(use_idf=bool(corpus))
            if corpus:
                emb.fit(corpus)
            return emb
    raise RuntimeError(f"没有可用的 embedder：{kind}")
