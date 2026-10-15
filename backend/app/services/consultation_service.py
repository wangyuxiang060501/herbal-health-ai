# -*- coding: utf-8 -*-
"""BC2 问诊会话服务 —— P2 版本：LangGraph 状态机驱动

职责划分（ADR-002 / ADR-006）：
    service 层  —— 数据库读写、事务、异常语义（抛 Geschäft 异常）
    orchestration —— 状态推进（BC3/BC4/安全节点由 LangGraph 图编排）

    两者之间只传 dict，**service 不手写流水线**。

流水线（graph.py 中的图，二者必须保持一致）：
    START → ①collect_symptoms（症状采集 + 输入侧安全闸）
          → ②constitution_engine（GB/T 46939—2025 确定性判定，非 LLM）
          → 信息不足 → ③follow_up（Agent1 追问，≤2 轮）→ END 等待用户
          → 信息充足 → ④herb_match（Agent2，候选限定 106 白名单）
          → ⑤safety_check（交叉复核 + 输出侧过滤）
          → ⑥food_recipe（Agent3，P3 开关）→ ⑦present → END

LLM 只做两件事：追问生成、结果通俗化。判定/过滤/安全一律走规则；
任何 LLM 失败都降级为模板，不允许中断主流程。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.responses import EmergencyBlocked, NotFoundException
from app.domain.constitution import engine as ce
from app.domain.constitution.questionnaire import (
    CONSTITUTION_INFO,
    NINE_CONSTITUTIONS,
)
from app.domain.safety import guard as sg
from app.models.entities import Consultation, Message as MessageRow, SafetyLog
from app.orchestration.nodes import NODE_LABELS
from app.orchestration.runner import run_consultation, stream_consultation
from app.orchestration.state import FINAL_NODE, MAX_FOLLOWUP_ROUNDS, new_state
from app.services import data_loader
from app.services.symptom_extraction import (  # 向后兼容：旧引用路径仍可用
    FREE_TEXT_HINTS,
    TEMPLATE_FOLLOWUP,
    answered_summary,
    extract_answers_from_text,
    missing_dimensions,
)

logger = get_logger("services.consultation")
settings = get_settings()


# ===========================================================================
# 输出结构
# ===========================================================================


@dataclass
class ConsultationOutcome:
    consultation_id: str
    phase: str                       # follow_up | completed | blocked
    status: str
    follow_up_questions: list[str] = field(default_factory=list)
    follow_up_source: str = ""       # llm:<provider>:<model> | template
    follow_up_round: int = 0
    message: str = ""
    constitution: dict | None = None
    recommend: dict | None = None
    interpretation: str = ""
    recipe: dict | None = None
    special_groups: list[str] = field(default_factory=list)
    safety: dict | None = None
    disclaimer: str = ""
    trace: list[dict] = field(default_factory=list)
    rag_citations: list[dict] = field(default_factory=list)   # P3：RAG 引用来源

    def to_dict(self) -> dict:
        return {
            "consultation_id": self.consultation_id,
            "phase": self.phase,
            "status": self.status,
            "follow_up_questions": self.follow_up_questions,
            "follow_up_source": self.follow_up_source,
            "follow_up_round": self.follow_up_round,
            "message": self.message,
            "constitution": self.constitution,
            "recommend": self.recommend,
            "interpretation": self.interpretation,
            "recipe": self.recipe,
            "special_groups": self.special_groups,
            "safety": self.safety,
            "disclaimer": self.disclaimer,
            "trace": self.trace,
            "rag_citations": self.rag_citations,
        }


# ===========================================================================
# 内部工具
# ===========================================================================


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return str(obj)


def _safe_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _load_questionnaire(raw: str) -> dict[str, int]:
    data = _safe_json(raw)
    return data if isinstance(data, dict) else {}


def _add_message(db: Session, cid: str, role: str, content: str, round_no: int = 0) -> None:
    db.add(MessageRow(
        consultation_id=cid, role=role, content=content, round_no=round_no
    ))


def _log_safety(db: Session, cid: str, triggers: Sequence[sg.Trigger]) -> None:
    for t in triggers:
        db.add(SafetyLog(
            consultation_id=cid, rule=t.rule, matched=t.matched,
            action=t.action, replacement=t.replacement, detail=t.detail,
        ))


def _log_safety_dicts(db: Session, cid: str, flags: Sequence[dict]) -> None:
    """记录交叉复核 / 输出侧的 flag（已经 to_dict 过的）"""
    for f in flags:
        db.add(SafetyLog(
            consultation_id=cid,
            rule=str(f.get("rule", "")),
            matched=str(f.get("matched", "")),
            action=str(f.get("action", "")),
            replacement=str(f.get("replacement", "")),
            detail=str(f.get("detail", f.get("dropped", "") or ""))[:2000],
        ))


def _normalize_groups(groups: Sequence[str], text: str = "") -> list[str]:
    merged = list(groups or []) + sg.detect_special_groups(text)
    return sorted(set(sg.assert_groups_valid(merged)))


STATUS_BY_PHASE = {
    "follow_up": "follow_up",
    "completed": "completed",
    "blocked": "blocked_safety",
}


# ===========================================================================
# 主流程
# ===========================================================================


def start_consultation(
    db: Session,
    *,
    chief_complaint: str = "",
    questionnaire: dict[str, int] | None = None,
    special_groups: list[str] | None = None,
    user_id: int | None = None,
    top_n: int = 6,
    enable_recipe: bool = False,
) -> ConsultationOutcome:
    cid = _new_id()
    groups = _normalize_groups(list(special_groups or []), chief_complaint)

    # 图之前先做一次输入侧安全判定：决定是否落 blocked 状态的记录行
    # （与 collect_symptoms_node 调用同一个 sg.check_input，结果必然一致）
    input_verdict = sg.check_input(chief_complaint)

    consultation = Consultation(
        id=cid, user_id=user_id,
        status="blocked_emergency" if input_verdict.blocked else "in_progress",
        chief_complaint=chief_complaint,
        special_groups=_dump(groups),
        questionnaire=_dump(dict(questionnaire or {})),
        safety_verdict=_dump(input_verdict),
    )
    db.add(consultation)
    _add_message(db, cid, "user", chief_complaint or "（开始问诊）")
    db.flush()
    _log_safety(db, cid, input_verdict.triggers)

    if input_verdict.blocked:
        db.commit()
        raise EmergencyBlocked(
            sg.EMERGENCY_ADVICE,
            data={"consultation_id": cid, "verdict": input_verdict.to_dict()},
        )

    state = new_state(
        cid,
        user_input=chief_complaint,
        questionnaire=questionnaire,
        special_groups=groups,
        user_id=user_id,
        top_n=top_n,
        enable_recipe=enable_recipe,
        follow_up_rounds=0,
        chief_complaint=chief_complaint,
    )
    final = run_consultation(state, thread_id=cid)
    return _persist_and_build(db, consultation, final)


def answer_consultation(
    db: Session, *, consultation_id: str, answer: str,
    top_n: int = 6, enable_recipe: bool = False,
) -> ConsultationOutcome:
    consultation = db.get(Consultation, consultation_id)
    if consultation is None:
        raise NotFoundException("问诊记录不存在")
    if consultation.status.startswith("blocked"):
        raise EmergencyBlocked("该问诊已被安全策略终止，请重新开始一次问诊")

    round_no = consultation.follow_up_rounds
    _add_message(db, consultation.id, "user", answer, round_no=round_no)
    db.flush()

    state = new_state(
        consultation.id,
        user_input=answer,
        questionnaire=_load_questionnaire(consultation.questionnaire),
        special_groups=_safe_json(consultation.special_groups) or [],
        top_n=top_n,
        enable_recipe=enable_recipe,
        follow_up_rounds=round_no,
        chief_complaint=consultation.chief_complaint or "",
    )
    final = run_consultation(state, thread_id=consultation.id)

    # 追问答案里出现急症表述 → 中途阻断（图已把 block_kind 标好）
    if final.get("blocked") and final.get("block_kind") == "emergency":
        consultation.status = "blocked_emergency"
        consultation.safety_verdict = _dump(final.get("input_verdict"))
        _log_safety_dicts(db, consultation.id, [{"rule": "急诊-追问轮", "action": "block"}])
        db.commit()
        raise EmergencyBlocked(
            sg.EMERGENCY_ADVICE,
            data={"consultation_id": consultation.id,
                  "verdict": final.get("input_verdict")},
        )

    return _persist_and_build(db, consultation, final)


def _persist_and_build(
    db: Session, consultation: Consultation, final: dict
) -> ConsultationOutcome:
    """把图终态落库 + 组装 API 输出 —— service 层唯一的写库出口"""
    cid = consultation.id
    phase = final.get("phase") or ("completed" if final.get("completed") else "follow_up")
    rounds = int(final.get("follow_up_rounds") or 0)
    constitution = final.get("constitution")
    herbs = final.get("herbs") or {}
    groups = list(final.get("special_groups") or [])

    consultation.chief_complaint = final.get("chief_complaint", consultation.chief_complaint)
    consultation.questionnaire = _dump(final.get("questionnaire") or {})
    consultation.special_groups = _dump(groups)
    consultation.constitution = _dump(constitution)
    consultation.herbal_match = _dump(herbs)
    consultation.recipe = _dump(final.get("recipe"))
    consultation.follow_up_rounds = rounds
    consultation.safety_verdict = _dump({
        "input": final.get("input_verdict"),
        "cross": final.get("safety_flags") or [],
    })
    consultation.status = STATUS_BY_PHASE.get(phase, "in_progress")
    # RAG 引用来源落库：结果页刷新后仍能看到"这句依据哪条知识"
    consultation.rag_citations = _dump(final.get("rag_citations") or [])

    _log_safety_dicts(db, cid, final.get("safety_flags") or [])

    ai_text = _ai_text(phase, final)
    _add_message(db, cid, "ai", ai_text, round_no=rounds)
    db.commit()

    if phase == "follow_up":
        return ConsultationOutcome(
            consultation_id=cid, phase=phase, status=consultation.status,
            follow_up_questions=list(final.get("follow_up_questions") or []),
            follow_up_source=final.get("follow_up_source", ""),
            follow_up_round=rounds,
            message="还想再了解几点，帮你把体质判断得更准一些：",
            constitution=_preview_constitution(final.get("constitution") or {}),
            special_groups=groups,
            disclaimer=sg.DISCLAIMER,
            trace=list(final.get("trace") or []),
            rag_citations=list(final.get("rag_citations") or []),
        )

    if phase == "blocked":
        return ConsultationOutcome(
            consultation_id=cid, phase=phase, status=consultation.status,
            message=final.get("block_reason", "已触发安全策略"),
            follow_up_round=rounds,
            special_groups=groups,
            disclaimer=sg.DISCLAIMER,
            trace=list(final.get("trace") or []),
            rag_citations=list(final.get("rag_citations") or []),
        )

    return ConsultationOutcome(
        consultation_id=cid, phase="completed", status=consultation.status,
        follow_up_round=rounds,
        message="已完成体质辨识与药膳方向推荐",
        constitution=constitution,
        recommend=_build_recommend(herbs, final),
        interpretation=final.get("interpretation", ""),
        recipe=final.get("recipe"),
        special_groups=groups,
        safety=(herbs or {}).get("safety"),
        disclaimer=sg.DISCLAIMER,
        trace=list(final.get("trace") or []),
        rag_citations=list(final.get("rag_citations") or []),
    )


def _ai_text(phase: str, final: dict) -> str:
    if phase == "follow_up":
        return "\n".join(final.get("follow_up_questions") or [])
    if phase == "blocked":
        return final.get("block_reason", "")
    return final.get("interpretation", "") or final.get("herb_explanation", "")


def _build_recommend(herbs: dict, final: dict) -> dict:
    retriever = data_loader.get_whitelist_retriever()
    candidates = list(herbs.get("candidates") or [])
    return {
        "herbs": candidates,
        "rejected": list(herbs.get("rejected") or []),
        "explanation": final.get("herb_explanation", ""),
        "rule_table_version": herbs.get("rule_table_version", settings.rule_table_version),
        "cross_checked": bool(herbs.get("cross_checked")),
        "evidence": [
            retriever.get(c["name"]).to_dict()
            for c in candidates
            if retriever.get(c["name"])
        ],
    }


def _preview_constitution(const: dict) -> dict:
    """追问阶段也返回当前倾向（不强行辨证，标记为不置信）"""
    return {
        "primary": const.get("primary") or "平和质",
        "primary_label": "暂未判定（信息不足）",
        "secondary": [],
        "scores": const.get("scores") or {},
        "deterministic": True,
        "insufficient_info": True,
        "answered_total": const.get("answered_total", 0),
        "evidence": const.get("evidence") or [],
    }


# ===========================================================================
# SSE 流式：节点级 meta 事件（系统架构设计 8.2 / 3.4.8）
# ===========================================================================


def start_consultation_stream(
    db: Session,
    *,
    chief_complaint: str = "",
    questionnaire: dict[str, int] | None = None,
    special_groups: list[str] | None = None,
    user_id: int | None = None,
    top_n: int = 6,
    enable_recipe: bool = False,
) -> Iterator[dict]:
    """边跑图边产出 SSE 事件

    事件类型：
        event: node   {"node","label",...}   节点开始/完成（trade_trace）
        event: meta   {"provider","model"}   LLM 来源
        event: delta  {"text"}               最终结论分段播放
        event: done   {...}                  终态摘要
        event: error  {"code","message"}
    """
    cid = _new_id()
    groups = _normalize_groups(list(special_groups or []), chief_complaint)
    input_verdict = sg.check_input(chief_complaint)

    consultation = Consultation(
        id=cid, user_id=user_id,
        status="blocked_emergency" if input_verdict.blocked else "in_progress",
        chief_complaint=chief_complaint,
        special_groups=_dump(groups),
        questionnaire=_dump(dict(questionnaire or {})),
        safety_verdict=_dump(input_verdict),
    )
    db.add(consultation)
    _add_message(db, cid, "user", chief_complaint or "（开始问诊）")
    db.flush()
    _log_safety(db, cid, input_verdict.triggers)

    if input_verdict.blocked:
        db.commit()
        yield {"event": "error", "data": {"code": "EMERGENCY_BLOCKED",
                                          "message": sg.EMERGENCY_ADVICE,
                                          "consultation_id": cid}}
        return

    state = new_state(
        cid, user_input=chief_complaint, questionnaire=questionnaire,
        special_groups=groups, user_id=user_id, top_n=top_n,
        enable_recipe=enable_recipe, follow_up_rounds=0,
        chief_complaint=chief_complaint,
    )

    final: dict = {}
    for node_name, patch in stream_consultation(state, thread_id=cid):
        if node_name == FINAL_NODE:
            final = patch
            continue
        yield {
            "event": "node",
            "data": {
                "node": node_name,
                "label": NODE_LABELS.get(node_name, node_name),
                "summary": _patch_summary(patch),
            },
        }
        source = patch.get("follow_up_source") or patch.get("interpretation_source")
        if source:
            parts = source.split(":")
            yield {"event": "meta", "data": {
                "provider": parts[1] if len(parts) > 1 else source,
                "model": parts[2] if len(parts) > 2 else "",
            }}

    outcome = _persist_and_build(db, consultation, final)

    text = outcome.interpretation or outcome.message
    for piece in _chunk(text, 48):
        yield {"event": "delta", "data": {"text": piece}}
    if outcome.follow_up_questions:
        for q in outcome.follow_up_questions:
            yield {"event": "question", "data": {"text": q}}
    yield {"event": "done", "data": {
        "consultation_id": cid,
        "phase": outcome.phase,
        "primary": (outcome.constitution or {}).get("primary", ""),
        "herbs": [h["name"] for h in (outcome.recommend or {}).get("herbs", [])],
    }}


def _patch_summary(patch: dict) -> dict:
    """把 node 写回的状态压成可展示的摘要（不含长文本）

    节点把细节放在 trace 条目的 extra 字段里，这里取出来给前端做进度条。
    """
    out: dict = {}
    for key in ("primary", "source", "needs_follow_up", "blocked", "phase"):
        if key in patch:
            out[key] = patch[key]

    trace = patch.get("trace") or []
    if trace:
        entry = trace[-1]
        for key in ("answered", "missing", "candidates", "rejected", "kept",
                    "dropped", "count", "source", "primary", "needs_follow_up"):
            if key in entry:
                out[key] = entry[key]
        if entry.get("label2"):
            out["primary_label"] = entry["label2"]
    return out


def _chunk(text: str, size: int) -> Iterator[str]:
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i:i + size]


# ===========================================================================
# 查询
# ===========================================================================


def get_consultation(db: Session, consultation_id: str) -> Consultation:
    c = db.get(Consultation, consultation_id)
    if c is None:
        raise NotFoundException("问诊记录不存在")
    return c


def consultation_detail(db: Session, consultation_id: str) -> dict:
    c = get_consultation(db, consultation_id)
    msgs = db.execute(
        select(MessageRow).where(MessageRow.consultation_id == consultation_id)
        .order_by(MessageRow.id)
    ).scalars().all()
    return {
        "id": c.id,
        "status": c.status,
        "chief_complaint": c.chief_complaint,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "special_groups": _safe_json(c.special_groups) or [],
        "questionnaire": _load_questionnaire(c.questionnaire),
        "constitution": _safe_json(c.constitution),
        "recommend": _safe_json(c.herbal_match),
        "recipe": _safe_json(c.recipe),
        "safety": _safe_json(c.safety_verdict),
        # 老库可能还没有这一列（见 database._migrate_add_columns），用 getattr 容错
        "rag_citations": _safe_json(getattr(c, "rag_citations", "") or "[]") or [],
        "messages": [
            {"role": m.role, "content": m.content, "round": m.round_no,
             "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S")}
            for m in msgs
        ],
    }


def list_history(db: Session, *, limit: int = 20, user_id: int | None = None) -> list[dict]:
    stmt = select(Consultation).order_by(Consultation.created_at.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(Consultation.user_id == user_id)
    rows = db.execute(stmt).scalars().all()
    out = []
    for c in rows:
        const = _safe_json(c.constitution) or {}
        out.append({
            "id": c.id,
            "status": c.status,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "primary": const.get("primary") or "未判定",
            "chief_complaint": (c.chief_complaint or "")[:80],
        })
    return out


def constitution_trend(db: Session, *, limit: int = 20) -> list[dict]:
    """体质趋势（多期九维转化分）—— ECharts 数据源"""
    stmt = (
        select(Consultation)
        .where(Consultation.status == "completed")
        .order_by(Consultation.created_at.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    trend = []
    for c in rows:
        const = _safe_json(c.constitution) or {}
        scores = const.get("scores") or {}
        trend.append({
            "date": c.created_at.strftime("%Y-%m-%d"),
            "primary": const.get("primary", ""),
            "scores": {k: scores.get(k, 0.0) for k in NINE_CONSTITUTIONS},
        })
    return trend


def constitution_summary() -> dict:
    """九种体质说明（前端结果页 / Trend 图例用）"""
    return dict(CONSTITUTION_INFO)


__all__ = [
    "ConsultationOutcome",
    "MAX_FOLLOWUP_ROUNDS",
    "FREE_TEXT_HINTS",
    "TEMPLATE_FOLLOWUP",
    "extract_answers_from_text",
    "missing_dimensions",
    "answered_summary",
    "start_consultation",
    "answer_consultation",
    "start_consultation_stream",
    "consultation_detail",
    "list_history",
    "constitution_trend",
    "constitution_summary",
]
