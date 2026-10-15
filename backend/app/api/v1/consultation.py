# -*- coding: utf-8 -*-
"""BC2 问诊接口 —— P2：LangGraph 多智能体编排

 POST /api/v1/consultation/start              开始问诊（问卷 + 主诉）
 POST /api/v1/consultation/stream             SSE 边跑图边推（节点级 meta 事件）
 POST /api/v1/consultation/{id}/answer        提交追问回答
 GET  /api/v1/consultation/{id}               问诊详情
 GET  /api/v1/consultation/{id}/stream        SSE 流式（事后播放结论）
 GET  /api/v1/consultation/graph              状态图结构与 mermaid
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
from app.api.deps import get_optional_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.responses import ok
from app.domain.constitution import engine as ce
from app.models.entities import User
from app.schemas import ConsultationAnswerIn, ConsultationStartIn
from app.services import consultation_service as cs

logger = get_logger("api.consultation")
router = APIRouter(prefix="/consultation", tags=["问诊会话（核心闭环）"])

MAX_SIZE_CANDIDATE = 12


@router.post("/start", summary="开始问诊")
def start(
    payload: ConsultationStartIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    outcome = cs.start_consultation(
        db,
        chief_complaint=payload.chief_complaint,
        questionnaire=payload.questionnaire,
        special_groups=payload.special_groups,
        user_id=user.id if user else None,
        top_n=min(payload.top_n, MAX_SIZE_CANDIDATE),
    )
    return ok(outcome.to_dict())


@router.post("/stream", summary="SSE：边跑状态图边推送（节点级事件）")
def stream_start(
    payload: ConsultationStartIn,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """节点级 meta 事件（`系统架构设计.md` 8.2 / 清单 3.4.8）

        event: node    {"node","label","summary"}   节点执行（可画进度条）
        event: meta    {"provider","model"}         LLM 实际来源
        event: delta   {"text"}                     结论分段播放
        event: question{"text"}                     追问问题
        event: done    {"consultation_id","phase","primary","herbs"}
        event: error   {"code","message"}
    """
    def gen():
        for ev in cs.start_consultation_stream(
            db,
            chief_complaint=payload.chief_complaint,
            questionnaire=payload.questionnaire,
            special_groups=payload.special_groups,
            user_id=user.id if user else None,
            top_n=min(payload.top_n, MAX_SIZE_CANDIDATE),
            enable_recipe=getattr(payload, "enable_recipe", False),
        ):
            yield (f"event: {ev['event']}\n"
                   f"data: {json.dumps(ev['data'], ensure_ascii=False)}\n\n")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/graph", summary="问诊状态图（LangGraph 拓扑可视化）")
def graph(format: str = Query("json", pattern="^(json|mermaid)$")):
    """返回状态图结构与 mermaid 源码 —— 论文第四章配图的唯一来源"""
    from app.orchestration import graph as og

    structure = og.graph_structure()
    if format == "mermaid":
        return ok({**structure, "mermaid": og.mermaid(),
                   "langgraph_mermaid": og.langgraph_mermaid()})
    return ok(structure)


@router.post("/{consultation_id}/answer", summary="提交追问回答")
def answer(
    consultation_id: str, payload: ConsultationAnswerIn, db: Session = Depends(get_db)
):
    outcome = cs.answer_consultation(
        db, consultation_id=consultation_id, answer=payload.answer,
        top_n=min(payload.top_n, MAX_SIZE_CANDIDATE),
        enable_recipe=payload.enable_recipe,
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
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # 5.4.1 数据隔离：登录看自己的，匿名看匿名记录，互不串
    if user is not None:
        return ok(cs.list_history(db, limit=limit, user_id=user.id))
    return ok(cs.list_history(db, limit=limit, anonymous=True))


@router.get("/user/trend", summary="体质变化趋势")
def trend(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if user is not None:
        return ok(cs.constitution_trend(db, limit=limit, user_id=user.id))
    return ok(cs.constitution_trend(db, limit=limit, anonymous=True))
