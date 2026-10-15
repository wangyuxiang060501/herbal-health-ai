# -*- coding: utf-8 -*-
"""元信息接口 —— 数据分层概况、九种体质、问卷、LLM 与健康状态

这些接口既是前端的数据源，也是**答辩演示 / 论文实验**时讲清楚
「数据怎么分层、LLM 怎么解耦」的抓手。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.agents.llm_client import get_llm_client
from app.core.config import get_settings
from app.core.responses import ok
from app.domain.constitution.engine import ITEM_SOURCE_NOTE, STANDARD_NAME
from app.domain.constitution.questionnaire import (
    CONSTITUTION_INFO,
    QUESTION_COUNT,
    QUESTIONNAIRE,
    SCORE_LABELS,
)
from app.services import data_loader

router = APIRouter(prefix="/meta", tags=["元信息"])
router_settings = get_settings()


@router.get("/dataset", summary="双层数据集概况")
def dataset():
    return ok(data_loader.dataset_stats())


@router.get("/questionnaire", summary="体质问卷结构")
def questionnaire(mode: str = "full"):
    """mode=full 返回 27 题；mode=quick 只返回每维度 1 题（9 题快速版）"""
    dims = []
    total = 0
    for key, dim in QUESTIONNAIRE.items():
        qs = [q for q in dim.questions if mode != "quick" or q.core]
        total += len(qs)
        dims.append({
            "dimension": key,
            "name": dim.name,
            "desc": CONSTITUTION_INFO[key]["desc"],
            "questions": [
                {"id": q.id, "text": q.text, "core": q.core} for q in qs
            ],
        })
    return ok({
        "standard": STANDARD_NAME,
        "item_source_note": ITEM_SOURCE_NOTE,
        "mode": mode,
        "total_questions": total,
        "scale": [{"value": v, "label": lab} for v, lab in SCORE_LABELS.items()],
        "dimensions": dims,
    })


@router.get("/cache", summary="热点缓存命中率（6.2.1）")
def cache_stats():
    """让「缓存到底有没有生效」可观测 —— 没命中率的缓存等于没加"""
    from app.core.cache import cache_stats_all

    return ok(cache_stats_all())


@router.get("/constitutions", summary="九种体质说明")
def constitutions():
    return ok(CONSTITUTION_INFO)


@router.get("/llm", summary="LLM provider 状态与用量")
def llm_status():
    return ok(get_llm_client().health())


@router.get("/config", summary="运行期配置摘要（不含密钥）")
def config_summary():
    s = get_settings()
    return ok({
        "app_name": s.app_name,
        "app_env": s.app_env,
        "api_prefix": s.api_prefix,
        "database_url": s.database_url.split("://")[0] + "://***",
        "llm_provider": s.llm_provider,
        "llm_model": s.llm_model,
        "fallback_chain": s.fallback_providers,
        "monthly_budget_cny": s.monthly_budget_cny,
        "rule_table_version": s.rule_table_version,
        "questionnaire_size": QUESTION_COUNT,
        "standard": STANDARD_NAME,
    })
