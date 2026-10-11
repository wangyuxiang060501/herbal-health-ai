# -*- coding: utf-8 -*-
"""LangGraph 节点实现（开发步骤清单 3.4.2-3.4.6）

节点清单与架构图对应（`系统架构设计.md` 2.3）：

    collect_symptoms    → ① 输入侧采集 + 急症初筛（规则）
    constitution_engine → ② 体质判定（GB/T 46939—2025 确定性算法，非 LLM）
    follow_up           → ③ Agent1 问诊对话 Agent（LLM，可降级模板）
    herb_match          → ④ Agent2 药材匹配（候选限定 106 白名单）
    safety_check        → ⑤ 安全校验节点（独立交叉复核 + 输出侧过滤）
    food_recipe         → ⑥ Agent3 药膳生成（P3，默认关闭）
    present             → ⑦ 结果组织 + 免责声明注入
    safety_abort        → 终止分支（红色警示）

分工原则（ADR-002）：
    ②⑤ 是规则节点（确定性、可复现）；
    ③④⑥ 是 LLM 节点（失败一律降级，不允许中断主流程）。
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import LLMError, Message
from app.agents.llm_client import get_llm_client
from app.agents.prompts import (
    build_follow_up_messages,
    build_herb_explain_messages,
    build_interpret_messages,
    build_recipe_messages,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.constitution import engine as ce
from app.domain.constitution.questionnaire import PINGHE
from app.domain.recommendation import matcher as hm
from app.domain.safety import guard as sg
from app.orchestration.state import (
    MAX_FOLLOWUP_ROUNDS,
    MAX_SAFETY_RECHECK,
    ConsultationState,
    trace_entry,
)
from app.services import data_loader
from app.services import symptom_extraction as se

logger = get_logger("orchestration.nodes")
settings = get_settings()

# 节点中文名表：供 SSE meta 事件与状态图导出共用（单一事实来源）
NODE_LABELS: dict[str, str] = {
    "collect_symptoms": "① 症状采集与输入安全初筛",
    "constitution_engine": "② 体质判定引擎（确定性）",
    "follow_up": "③ Agent1 追问生成",
    "herb_match": "④ Agent2 药材匹配",
    "safety_check": "⑤ 安全交叉校验",
    "food_recipe": "⑥ Agent3 药膳生成",
    "present": "⑦ 结果组织与免责注入",
    "recheck_counter": "↺ 重配计数（有界）",
    "safety_abort": "✖ 安全策略中止",
}


def _t(node: str, **extra: Any) -> dict:
    return trace_entry(node, NODE_LABELS.get(node, node), **extra)


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else ""


# ===========================================================================
# ① collect_symptoms_node —— 开发步骤清单 3.4.2
# ===========================================================================


def collect_symptoms_node(state: ConsultationState) -> dict:
    """把本轮用户输入并入会话状态

    - 自由文本关键词 → 结构化问卷（首轮不覆盖显式问卷，追问轮取 max 加强）
    - 特殊人群识别（孕妇 / 哺乳期 / 儿童 / 慢性病）
    - 输入侧安全闸：急症表述直接 block
    """
    user_input = state.get("user_input") or ""
    round_no = int(state.get("follow_up_rounds") or 0)

    # 主诉累积：首轮即 user_input，后续轮追加「用户补充：」
    chief = state.get("chief_complaint") or ""
    if round_no > 0 and user_input:
        chief = f"{chief}\n用户补充：{user_input}".strip()
    elif round_no == 0 and user_input:
        chief = chief or user_input

    # 自由文本 → 问卷（首轮 setdefault：显式问卷优先）
    answers = se.blend_answers(
        state.get("questionnaire") or {}, user_input, override=(round_no > 0)
    )

    # 特殊人群
    groups = list(state.get("special_groups") or [])
    groups += sg.detect_special_groups(user_input)
    groups = sorted(set(sg.assert_groups_valid(groups)))

    # 输入侧安全闸
    verdict = sg.check_input(chief)

    missing = se.missing_dimensions(answers)

    patch: dict = {
        "chief_complaint": chief,
        "questionnaire": answers,
        "special_groups": groups,
        "input_verdict": verdict.to_dict(),
        "missing_dimensions": missing,
        "trace": [_t("collect_symptoms", answered=len(answers), missing=len(missing),
                     blocked=verdict.blocked)],
    }
    if verdict.blocked:
        patch.update({
            "blocked": True,
            "block_kind": "emergency",
            "block_reason": sg.EMERGENCY_ADVICE,
            "phase": "blocked",
        })
    return patch


# ===========================================================================
# ② constitution_engine_node —— 确定性判定（替代原 Agent1 diagnose）
# ===========================================================================


def constitution_engine_node(state: ConsultationState) -> dict:
    """体质判定走 GB/T 46939—2025 等级计分，纯函数、可复现、不调用 LLM"""
    result = ce.score(
        state.get("questionnaire") or {},
        rule_table_version=settings.rule_table_version,
    )
    return {
        "constitution": result.to_dict(),
        "trace": [_t("constitution_engine", primary=result.primary,
                     label2=result.primary_label,
                     needs_follow_up=result.needs_follow_up)],
    }


# ===========================================================================
# ③ follow_up_node —— Agent1 问诊对话 Agent
# ===========================================================================


def _llm_follow_up(state: ConsultationState, missing: list[str]) -> tuple[list[str], str]:
    """返回 (问题列表, 来源)。任何异常都降级为模板"""
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_follow_up_messages(
                state.get("chief_complaint", ""),
                se.answered_summary(state.get("questionnaire") or {}),
                missing,
                state.get("special_groups") or [],
                int(state.get("follow_up_rounds") or 0) + 1,
            )
        ]
        resp = client.chat(msgs, key_step=True)
        questions = [ln.strip() for ln in resp.text.splitlines() if ln.strip()][:3]
        if questions:
            return questions, f"llm:{resp.provider}:{resp.model}"
    except LLMError as e:
        logger.warning("追问生成失败，降级模板", extra={"extra_fields": {"error": str(e)[:120]}})
    except Exception as e:  # noqa: BLE001
        logger.warning("追问生成异常，降级模板", extra={"extra_fields": {"error": str(e)[:120]}})
    return se.template_questions(missing), "template"


def follow_up_node(state: ConsultationState) -> dict:
    missing = list(state.get("missing_dimensions") or [])
    questions, source = _llm_follow_up(state, missing)
    return {
        "follow_up_questions": questions,
        "follow_up_source": source,
        "asked_questions": questions,
        "follow_up_rounds": int(state.get("follow_up_rounds") or 0) + 1,
        "phase": "follow_up",
        "disclaimer": sg.DISCLAIMER,
        "trace": [_t("follow_up", source=source, count=len(questions))],
    }


# ===========================================================================
# ④ herb_match_node —— Agent2 药材匹配
# ===========================================================================


def _as_constitution_result(raw: dict | None) -> ce.ConstitutionResult:
    if not raw:
        return ce.ConstitutionResult(primary="平和质", scores={})
    return ce.ConstitutionResult.from_dict(raw)


def herb_match_node(state: ConsultationState) -> dict:
    result = _as_constitution_result(state.get("constitution"))
    checker = data_loader.get_whitelist_checker()
    index = data_loader.get_whitelist_index()

    if state.get("safety_recheck"):
        logger.info("第 %s 次安全复核后重新配伍", state["safety_recheck"])

    match = hm.match_herbs(
        result,
        checker,
        whitelist_index=index,
        chief_complaint=state.get("chief_complaint", ""),
        special_groups=state.get("special_groups") or [],
        top_n=int(state.get("top_n") or 6),
    )

    # LLM 解读（失败降级为规则文本）
    candidates = [c.to_dict() for c in match.candidates]
    explanation = _explain_herbs(result, candidates, state.get("special_groups") or [])

    return {
        "herbs": match.to_dict(),
        "herb_explanation": explanation,
        "trace": [_t("herb_match", candidates=len(candidates),
                     rejected=len(match.rejected))],
    }


def _explain_herbs(result: ce.ConstitutionResult, candidates: list[dict],
                   groups: list[str]) -> str:
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_herb_explain_messages(candidates, result.primary, groups)
        ]
        resp = client.chat(msgs)
        if resp.text.strip():
            return resp.text.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("药材解读失败，降级规则文本",
                       extra={"extra_fields": {"error": str(e)[:120]}})
    return "\n".join(
        f"{c['name']}（{c.get('dosage', '')}）：{c.get('reason', '')}"
        for c in candidates
    )


# ===========================================================================
# ⑤ safety_check_node —— 独立交叉复核 + 输出侧过滤
# ===========================================================================


def safety_check_node(state: ConsultationState) -> dict:
    """终态前最后一道闸

    与 herb_match 内部的安全检查是**两个不同的检查点**：
      - herb_match：对「截断前的完整候选列表」做第一次过滤；
      - safety_check：对「最终呈现给用户的结果」做第二次复核，
        包括 matcher 可能新引入的替换品种、以及 LLM 生成的自由文本。
    """
    checker = data_loader.get_whitelist_checker()
    groups = state.get("special_groups") or []
    herbs = state.get("herbs") or {}
    candidates = list(herbs.get("candidates") or [])

    dropped: list[dict] = []
    flags: list[dict] = []

    # --- 1) 逐项复核：必须在白名单内且不被黑名单命中 ---
    kept: list[dict] = []
    for c in candidates:
        name = c.get("name", "")
        if sg.is_blacklisted(name) or not checker.contains(name):
            dropped.append({"name": name, "why": "交叉复核未通过：不在 106 白名单或属黑名单"})
            continue
        kept.append(c)

    # --- 2) 特殊人群禁忌复核 ---
    for c in list(kept):
        ban_groups = set(c.get("special_groups") or [])
        hit = ban_groups & set(groups)
        if hit:
            kept.remove(c)
            dropped.append({"name": c.get("name", ""), "why": f"与特殊人群冲突：{'、'.join(sorted(hit))}"})

    # --- 3) 十八反十九畏（终态名单上的组合禁忌）---
    names = [c["name"] for c in kept]
    conflict = sg.find_incompatibility(names)
    if conflict:
        a, b, why = conflict
        kept = [c for c in kept if c["name"] != b]
        dropped.append({"name": b, "why": f"配伍禁忌：{a} 与 {b} —— {why}", "replacement": ""})

    if dropped:
        flags.append({"rule": "cross_check", "action": "reject", "dropped": dropped})

    # --- 4) 输出侧：术语过滤 + 免责注入 ---
    result = _as_constitution_result(state.get("constitution"))
    interpretation, itp_src = _interpret(result)
    interpretation, out_verdict = sg.check_output(interpretation)
    explanation, _ = sg.check_output(
        state.get("herb_explanation", ""), with_recipe_disclaimer=True
    )
    for t in out_verdict.triggers:
        flags.append({"rule": t.rule, "matched": t.matched, "action": t.action,
                      "replacement": t.replacement, "detail": t.detail})
    if out_verdict.blocked:
        return {
            "blocked": True,
            "block_kind": "safety",
            "block_reason": "输出内容触发安全策略，已终止本次推荐",
            "safety_flags": flags,
            "phase": "blocked",
            "trace": [_t("safety_check", dropped=len(dropped), blocked=True)],
        }

    # 写回最终候选
    new_herbs = dict(herbs)
    new_herbs["candidates"] = kept
    new_herbs["cross_checked"] = True

    patch: dict = {
        "herbs": new_herbs,
        "interpretation": interpretation,
        "interpretation_source": itp_src,
        "herb_explanation": explanation,
        "safety_flags": flags,
        "safety_verdict": (state.get("input_verdict") or {}),
        "trace": [_t("safety_check", kept=len(kept), dropped=len(dropped))],
    }

    # 复核后发现候选被清空/过少 → 触发重配（由条件边决定）
    if len(kept) < 2:
        patch["safety_recheck"] = int(state.get("safety_recheck") or 0)
    return patch


def _interpret(result: ce.ConstitutionResult) -> tuple[str, str]:
    """通俗化：LLM 优先，失败降级为规则表述"""
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_interpret_messages(
                result.primary, result.secondary, result.evidence, result.primary_label
            )
        ]
        resp = client.chat(msgs, key_step=True)
        if resp.text.strip():
            return resp.text.strip(), f"llm:{resp.provider}:{resp.model}"
    except Exception as e:  # noqa: BLE001
        logger.warning("通俗化失败，使用规则表述",
                       extra={"extra_fields": {"error": str(e)[:120]}})
    return ce.interpret_to_words(result), "rule"


# ===========================================================================
# ⑥ food_recipe_node —— Agent3 药膳生成（P3，默认关闭）
# ===========================================================================


def food_recipe_node(state: ConsultationState) -> dict:
    result = _as_constitution_result(state.get("constitution"))
    herbs = state.get("herbs") or {}
    candidates = herbs.get("candidates") or []
    evidence = (herbs.get("evidence") or [])

    recipe_text = ""
    source = "rule"
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_recipe_messages(
                candidates, result.primary, evidence, state.get("special_groups") or []
            )
        ]
        resp = client.chat(msgs, key_step=True)
        recipe_text = resp.text.strip()
        source = f"llm:{resp.provider}:{resp.model}"
    except Exception as e:  # noqa: BLE001
        logger.warning("药膳生成失败", extra={"extra_fields": {"error": str(e)[:120]}})

    recipe_text, _ = sg.check_output(recipe_text, with_recipe_disclaimer=True)
    return {
        "recipe": {"plan": recipe_text, "source": source,
                   "enabled": bool(state.get("enable_recipe"))},
        "trace": [_t("food_recipe", source=source, chars=len(recipe_text))],
    }


# ===========================================================================
# ⑦ present_node —— 结果组织
# ===========================================================================


def present_node(state: ConsultationState) -> dict:
    return {
        "phase": "completed",
        "completed": True,
        "disclaimer": sg.DISCLAIMER,
        "trace": [_t("present")],
    }


# ===========================================================================
# 终止分支
# ===========================================================================


def safety_abort_node(state: ConsultationState) -> dict:
    return {
        "phase": "blocked",
        "completed": False,
        "disclaimer": sg.DISCLAIMER,
        "trace": [_t("safety_abort", kind=state.get("block_kind", ""))],
    }


__all__ = [
    "NODE_LABELS",
    "collect_symptoms_node",
    "constitution_engine_node",
    "follow_up_node",
    "herb_match_node",
    "safety_check_node",
    "food_recipe_node",
    "present_node",
    "safety_abort_node",
    "MAX_FOLLOWUP_ROUNDS",
    "MAX_SAFETY_RECHECK",
    "PINGHE",
    "_json_dump",
]
