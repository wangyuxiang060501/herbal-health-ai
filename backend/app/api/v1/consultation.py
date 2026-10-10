# -*- coding: utf-8 -*-
"""BC2 问诊接口 —— P1 闭环

 POST /api/v1/consultation/start              开始问诊（问卷 + 主诉）
 POST /api/v1/consultation/{id}/answer        提交追问回答
 GET  /api/v1/consultation/{id}               问诊详情
 GET  /api/v1/consultation/{id}/stream        SSE 流式（P1：流式播放通俗化结论）
 GET  /api/v1/user/history                    问诊历史
 GET  /api/v1/user/trend                      体质趋势
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.base import Message
from app.agents.llm_client import get_llm_client
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.responses import ok
from app.domain.constitution import engine as ce
from app.schemas import ConsultationAnswerIn, ConsultationStartIn
from app.services import consultation_service as cs

logger = get_logger("api.consultation")
router = APIRouter(prefix="/consultation", tags=["问诊会话（核心闭环）"])

MAX_SIZE_CANDIDATE = 12


@router.post("/start", summary="开始问诊")
def start(payload: ConsultationStartIn, db: Session = Depends(get_db)):
    outcome = cs.start_consultation(
        db,
        chief_complaint=payload.chief_complaint,
        questionnaire=payload.questionnaire,
        special_groups=payload.special_groups,
        top_n=min(payload.top_n, MAX_SIZE_CANDIDATE),
    )
    return ok(outcome.to_dict())


@router.post("/{consultation_id}/answer", summary="提交追问回答")
def answer(
    consultation_id: str, payload: ConsultationAnswerIn, db: Session = Depends(get_db)
):
    outcome = cs.answer_consultation(
        db, consultation_id=consultation_id, answer=payload.answer,
        top_n=min(payload.top_n, MAX_SIZE_CANDIDATE),
    )
    return ok(outcome.to_dict())


@router.get("/{consultation_id}", summary="问诊详情")
def detail(consultation_id: str, db: Session = Depends(get_db)):
    return ok(cs.consultation_detail(db, consultation_id))


@router.get("/{consultation_id}/stream", summary="SSE 流式输出")
def stream(
    consultation_id: str,
    phase: str = Query("interpretation", pattern="^(interpretation|recommend)$"),
    db: Session = Depends(get_db),
):
    """SSE 事件契约（系统架构设计.md 4.5）：
        event: delta  {"text": "..."}
        event: meta   {"provider":..., "tokens":...}
        event: done   {"consultation_id":...}
        event: error  {"code":..., "message":...}
    """
    detail_data = cs.consultation_detail(db, consultation_id)
    base_text = _build_stream_text(detail_data, phase)

    def event_gen():
        import json as _json

        yield f"event: meta\ndata: {_json.dumps({'phase': phase, 'length': len(base_text)}, ensure_ascii=False)}\n\n"
        try:
            client = get_llm_client()
            messages = [Message(role="user", content=f"请把下面这段内容润色为自然口语输出：\n{base_text}")]
            for piece in client.chat_stream(messages):
                yield f"event: delta\ndata: {_json.dumps({'text': piece}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001 SSE 流不可中断为 500
            logger.warning("SSE 流式失败，退化为规则文本",
                           extra={"extra_fields": {"error": str(e)[:120]}})
            for ch in base_text:
                yield f"event: delta\ndata: {_json.dumps({'text': ch}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {_json.dumps({'consultation_id': consultation_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _build_stream_text(detail_data: dict, phase: str) -> str:
    """生成待流式播放的文本：优先取最后一次 AI 结论，否则退化为规则表述"""
    recommend = detail_data.get("recommend") or {}
    if phase == "recommend":
        lines = [
            f"{h['name']}（{h.get('dosage', '')}）：{h.get('reason', '')}"
            for h in (recommend.get("herbs") or [])
        ]
        return "\n".join(lines) or "暂无推荐药材。"

    last_ai = next(
        (m["content"] for m in reversed(detail_data.get("messages") or []) if m["role"] == "ai"),
        "",
    )
    return last_ai or ce.interpret_to_words_from_dict(detail_data.get("constitution") or {})


@router.get("/user/history", summary="问诊历史")
def history(
    limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)
):
    return ok(cs.list_history(db, limit=limit))


@router.get("/user/trend", summary="体质变化趋势")
def trend(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return ok(cs.constitution_trend(db, limit=limit))
