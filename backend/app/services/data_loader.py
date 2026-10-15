# -*- coding: utf-8 -*-
"""数据加载服务 —— 双层数据的运行时入口

  - 查询层 herbs（604 味唯一药材，只读展示）
  - 推荐层 food_medicine_whitelist（106 种，硬白名单）

职责：从 JSON 文件读入、构建内存索引、提供 WhitelistChecker / Retriever 实例。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.core.cache import ttl_cache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.safety.constants import BLACKLIST_HERBS
from app.domain.safety.guard import WhitelistChecker, _paren_tokens
from app.rag.retriever import WhitelistRetriever

logger = get_logger("services.data")
settings = get_settings()

HERB_SOURCE_NOTE = "数据来源：开源参考仓库 herb-llm-agent（tcm_828_herbs.json），仅供参考，须与《中国药典》核对"
WHITELIST_SOURCE_NOTE = "来源：国家卫生健康委《既是食品又是中药材的物质目录》"


def _read_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def load_clean_herbs() -> list[dict]:
    """查询层：清洗后的药材（604 味唯一）"""
    return _read_json(settings.abs_data_path(settings.herbs_clean_path))


@lru_cache
def load_raw_herbs() -> list[dict]:
    return _read_json(settings.abs_data_path(settings.herbs_raw_path))


@lru_cache
def load_whitelist_records() -> list[dict]:
    payload = _read_json(settings.abs_data_path(settings.whitelist_path))
    return payload["items"] if isinstance(payload, dict) else payload


@lru_cache
def build_whitelist_aliases() -> dict[str, str]:
    """别名 → 规范名

    数据来源有两条，且必须区分对待（详见 WhitelistChecker 文档）：
      1. 记录的 alias 字段（35 条有值，人工整理，权威）
      2. 仅当 alias 字段非空时，才把「姜（生姜、干姜）」括号内的词也当别名
         —— 因为「杏仁（甜、苦）」「肉苁蓉（荒漠）」的括号是规格限定，不是别名
    """
    aliases: dict[str, str] = {}
    for r in load_whitelist_records():
        name = r["name"]
        raw = (r.get("alias") or "").strip()
        if not raw:
            continue
        tokens = [t.strip() for t in re.split(r"[、,，/]", raw)]
        if "（" in name:
            tokens += _paren_tokens(name)
        for t in tokens:
            if len(t) >= 2:
                aliases.setdefault(t, name)
    return aliases


@lru_cache
def get_whitelist_checker() -> WhitelistChecker:
    return WhitelistChecker((r["name"] for r in load_whitelist_records()),
                            build_whitelist_aliases())


@lru_cache
def get_whitelist_index() -> dict[str, dict]:
    return {r["name"]: r for r in load_whitelist_records()}


@lru_cache
def get_whitelist_retriever() -> WhitelistRetriever:
    return WhitelistRetriever(load_whitelist_records())


def whitelist_names() -> set[str]:
    return {r["name"] for r in load_whitelist_records()}


@lru_cache
def whitelist_missing_in_query_layer() -> list[str]:
    """106 白名单中，未被原始药材数据集收录的品种（需补写为百科条目）"""
    names = {h["name"].strip() for h in load_clean_herbs()}
    return [
        r["name"] for r in load_whitelist_records()
        if r["name"] not in names and r["name"].split("（")[0] not in names
    ]


@ttl_cache(ttl=300.0, maxsize=8)
def dataset_stats() -> dict:
    """供 /api/v1/meta/dataset 展示的双层数据概况"""
    herbs = load_clean_herbs()
    raw = load_raw_herbs()
    wl = load_whitelist_records()
    missing = whitelist_missing_in_query_layer()
    black_in_herbs = sorted({h["name"] for h in herbs if h["name"] in set(BLACKLIST_HERBS)})
    return {
        "query_layer": {
            "name": "药材百科查询层",
            "file": settings.herbs_clean_path,
            "unique_herbs": len(herbs),
            "raw_records": len(raw),
            "note": "原始 828 条记录去重合并后的唯一药材数；「828」是记录数不是品种数。"
                    f"另有 {len(missing)} 味法定可食用品种原数据未收录，由 106 白名单补齐，"
                    f"入库后查询层合计 {len(herbs) + len(missing)} 味。",
            "source": HERB_SOURCE_NOTE,
            "whitelist_complement": missing,
            "blacklist_herbs_present": black_in_herbs,
            "blacklist_count": len(black_in_herbs),
        },
        "recommendation_layer": {
            "name": "药膳推荐白名单层",
            "file": settings.whitelist_path,
            "count": len(wl),
            "batches": {
                b: len([r for r in wl if r["batch"] == b]) for b in sorted({r["batch"] for r in wl})
            },
            "verified": len([r for r in wl if r.get("verified")]),
            "unverified": len([r for r in wl if not r.get("verified")]),
            "source": WHITELIST_SOURCE_NOTE,
        },
        "isolation_invariant": {
            "description": "推荐结果中的药材必须全部 ∈ 106 白名单；"
                           "828/604 查询层的处方药材只可展示，不得进入方案",
            "automated_test": "tests/test_safety_guard.py::TestBlacklist::test_附子必须被推荐层拒绝",
        },
    }
