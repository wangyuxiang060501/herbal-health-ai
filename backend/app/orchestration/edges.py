# -*- coding: utf-8 -*-
"""条件边路由（开发步骤清单 3.4.7）

三条**)条件路由，全部是「读状态的纯函数」——不查库、不调 LLM，
保证图结构的可测试性：给定同一状态，路由结果必然相同。
"""
from __future__ import annotations

from app.orchestration.state import MAX_FOLLOWUP_ROUNDS, MAX_SAFETY_RECHECK, ConsultationState

# 分支名 → 目标节点（单一事实来源，被 graph.py 导入）
ROUTE_COLLECT = {"safety_abort": "safety_abort", "diagnose": "constitution_engine"}
ROUTE_CONSTITUTION = {"follow_up": "follow_up", "match": "herb_match"}
ROUTE_SAFETY = {
    "recheck": "herb_match",
    "abort": "safety_abort",
    "recipe": "food_recipe",
    "present": "present",
}


def route_after_collect(state: ConsultationState) -> str:
    """急症命中 → 直接中止；否则进入体质判定"""
    return "safety_abort" if state.get("blocked") else "diagnose"


def route_after_constitution(state: ConsultationState) -> str:
    """信息不足且未达追问轮次上限 → Agent1 追问；否则进入药材匹配"""
    const = state.get("constitution") or {}
    rounds = int(state.get("follow_up_rounds") or 0)
    if const.get("needs_follow_up") and rounds < MAX_FOLLOWUP_ROUNDS:
        return "follow_up"
    return "match"


def route_after_safety(state: ConsultationState) -> str:
    """安全复核后的去向

    recheck —— 候选被交叉复核清空/不足，且重配次数未用尽 → 回药材匹配节点重配
    abort   —— 输出侧触发阻断级规则
    recipe  —— 开启 P3 药膳生成
    present —— 正常出结果
    """
    if state.get("blocked"):
        return "abort"

    herbs = state.get("herbs") or {}
    kept = len(herbs.get("candidates") or [])
    recheck = int(state.get("safety_recheck") or 0)
    if kept < 2 and recheck < MAX_SAFETY_RECHECK:
        return "recheck"
    return "recipe" if state.get("enable_recipe") else "present"


def bump_recheck(state: ConsultationState) -> dict:
    """走 recheck 边时递增计数，防止 infinite loop"""
    return {"safety_recheck": int(state.get("safety_recheck") or 0) + 1}
