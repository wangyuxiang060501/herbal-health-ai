# -*- coding: utf-8 -*-
"""BC2 问诊会话服务 —— P1 核心闭环

流水线：
    输入 → ①输入侧安全闸（急症拦截）
         → ②信息充分性判断（确定性引擎）
         → 不足 → LLM 生成追问（≤3 问 / ≤2 轮）
         → 充分 → ③体质判定（确定性，非 LLM）
                → ④药材匹配（仅 106 白名单）
                → ⑤输出侧安全闸（术语过滤 + 免责声明注入）
                → ⑥落库（consultations / messages / safety_logs）

职责划分（ADR-002）：
    LLM 只做两件事 —— ① 生成追问 ② 通俗化转述。
    判定、过滤、安全一律走规则，失败不影响主流程（LLM 不可用时降级为模板话术）。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import LLMError, Message
from app.agents.llm_client import get_llm_client
from app.agents.prompts import build_follow_up_messages, build_interpret_messages
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.responses import EmergencyBlocked, NotFoundException
from app.domain.constitution import engine as ce
from app.domain.constitution.questionnaire import (
    ALL_QUESTIONS,
    CONSTITUTION_INFO,
    NINE_CONSTITUTIONS,
    PINGHE,
    QUESTIONNAIRE,
    SCORE_LABELS,
)
from app.domain.recommendation import matcher as hm
from app.domain.safety import guard as sg
from app.models.entities import Consultation, Message as MessageRow, SafetyLog
from app.services import data_loader

logger = get_logger("services.consultation")
settings = get_settings()

MAX_FOLLOWUP_ROUNDS = 2


# ===========================================================================
# 自由文本 → 问卷结构化答案（关键词启发）
#   说明：这是规则层的确定性抽取，保证无 LLM 也能推进；
#        未来可替换为 LLM 抽取 + 规则校验（LLM 负责语言理解，规则负责兜底）
# ===========================================================================
FREE_TEXT_HINTS: dict[str, dict[str, int]] = {
    # 阳虚
    "怕冷": {"阳虚质_1": 5, "阳虚质_3": 4},
    "手脚冰凉": {"阳虚质_1": 5},
    "手脚发凉": {"阳虚质_1": 5},
    "四肢不温": {"阳虚质_1": 4},
    "腰膝酸冷": {"阳虚质_2": 4},
    "喜热饮": {"阳虚质_1": 4},
    # 气虚
    "没力气": {"气虚质_1": 5},
    "容易累": {"气虚质_1": 5},
    "疲乏": {"气虚质_1": 5},
    "乏力": {"气虚质_1": 5},
    "气短": {"气虚质_2": 5},
    "出虚汗": {"气虚质_3": 5},
    "易感冒": {"气虚质_1": 4},
    # 阴虚
    "五心烦热": {"阴虚质_1": 5},
    "手脚心热": {"阴虚质_1": 5},
    "口干": {"阴虚质_2": 4},
    "咽燥": {"阴虚质_2": 4},
    "盗汗": {"阴虚质_3": 5},
    "眼干": {"阴虚质_2": 4},
    # 痰湿
    "腹胀": {"痰湿质_1": 4},
    "胸闷": {"痰湿质_1": 4},
    "身体沉重": {"痰湿质_2": 5},
    "痰多": {"痰湿质_3": 5},
    "肥胖": {"痰湿质_2": 4},
    "大便黏": {"痰湿质_3": 4},
    "舌苔厚腻": {"痰湿质_3": 4},
    # 湿热
    "出油": {"湿热质_1": 5},
    "油光": {"湿热质_1": 5},
    "痤疮": {"湿热质_2": 5},
    "长痘": {"湿热质_2": 5},
    "口苦": {"湿热质_3": 5},
    "口臭": {"湿热质_3": 5},
    # 血瘀
    "瘀斑": {"血瘀质_1": 5},
    "淤青": {"血瘀质_1": 5},
    "面色晦暗": {"血瘀质_2": 5},
    "嘴唇发暗": {"血瘀质_3": 5},
    "痛经": {"血瘀质_2": 4},
    # 气郁
    "心情低落": {"气郁质_1": 5},
    "情绪低落": {"气郁质_1": 5},
    "压力大": {"气郁质_2": 4},
    "焦虑": {"气郁质_2": 4},
    "爱叹气": {"气郁质_2": 4},
    "易受惊": {"气郁质_3": 4},
    # 特禀
    "过敏": {"特禀质_1": 5},
    "荨麻疹": {"特禀质_2": 5},
    "鼻炎": {"特禀质_3": 4},
    "打喷嚏": {"特禀质_3": 4},
    # 平和（正向条目的弱化表达）
    "精力充沛": {"平和质_1": 5},
    "很少生病": {"平和质_3": 5},
    "睡眠好": {"平和质_3": 5},
}


def extract_answers_from_text(text: str) -> dict[str, int]:
    """从自由文本抽取结构化答案（取同类关键词中的最高分）"""
    found: dict[str, int] = {}
    if not text:
        return found
    for kw, mapping in FREE_TEXT_HINTS.items():
        if kw in text:
            for qid, score in mapping.items():
                found[qid] = max(found.get(qid, 0), score)
    return found


# ===========================================================================
# 输出结构
# ===========================================================================


@dataclass
class ConsultationOutcome:
    consultation_id: str
    phase: str                       # follow_up | completed | blocked
    status: str
    follow_up_questions: list[str] = field(default_factory=list)
    follow_up_source: str = ""       # llm | template
    follow_up_round: int = 0
    message: str = ""
    constitution: dict | None = None
    recommend: dict | None = None
    interpretation: str = ""
    special_groups: list[str] = field(default_factory=list)
    safety: dict | None = None
    disclaimer: str = ""

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
            "special_groups": self.special_groups,
            "safety": self.safety,
            "disclaimer": self.disclaimer,
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
    if hasattr(obj, "to_dict"):
        return json.dumps(obj.to_dict(), ensure_ascii=False)
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return str(obj)


def _load_questionnaire(raw: str) -> dict[str, int]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


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


def _missing_dimensions(answers: dict[str, int]) -> list[str]:
    missing = []
    for dim_key, dim in QUESTIONNAIRE.items():
        if not any(q.id in answers for q in dim.questions):
            missing.append(dim_key)
    return missing


def _answered_summary(answers: dict[str, int]) -> str:
    lines = []
    for qid, score in sorted(answers.items()):
        q = ALL_QUESTIONS.get(qid)
        if q and score >= 3:
            lines.append(f"- {q.text}：{SCORE_LABELS.get(score, score)}")
    return "\n".join(lines)


TEMPLATE_FOLLOWUP: dict[str, str] = {
    "气虚质": "你平时容易疲乏、爬楼或走路快了就气短吗？",
    "阳虚质": "你平时手脚发凉、比别人更怕冷吗？",
    "阴虚质": "你常感到口干咽燥，或手心脚心发热、夜间出汗吗？",
    "痰湿质": "你常感觉身体沉重、腹部胀满、痰多或口中黏腻吗？",
    "湿热质": "你面部容易出油、长痘，或有口苦口臭的情况吗？",
    "血瘀质": "你的皮肤容易出现青紫瘀斑，或面色、口唇偏暗吗？",
    "气郁质": "你最近情绪低落、压力大、爱叹气的情况多吗？",
    "特禀质": "你容易对食物、药物、花粉等过敏，或常鼻塞打喷嚏吗？",
    "平和质": "你精力充沛、睡眠质量好、很少生病吗？",
}


def _generate_follow_up(
    result: ce.ConstitutionResult,
    answers: dict[str, int],
    chief_complaint: str,
    missing: list[str],
    special_groups: list[str],
    round_no: int,
) -> tuple[list[str], str, str]:
    """返回 (问题列表, 来源 llm|template, 开场白)"""
    # 优先用 LLM 生成自然的追问；任何异常都降级为模板，保证流程不中断
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_follow_up_messages(
                chief_complaint, _answered_summary(answers), missing,
                special_groups, round_no,
            )
        ]
        resp = client.chat(msgs, key_step=True)
        questions = [ln.strip() for ln in resp.text.splitlines() if ln.strip()][:3]
        if questions:
            intro = "根据你描述的情况，我还想再确认几个细节："
            return questions, f"llm:{resp.provider}:{resp.model}", intro
    except LLMError as e:
        logger.warning("追问生成失败，降级为模板", extra={"extra_fields": {"error": str(e)[:120]}})
    except Exception as e:  # noqa: BLE001 兜底，任何异常都不能中断问诊
        logger.warning("追问生成异常，降级为模板",
                       extra={"extra_fields": {"error": str(e)[:120]}})

    # 模板兜底：question_id 无关，按缺失维度给最高优先级的问题
    ordered_dims = [d for d in missing if d != PINGHE][:3] or missing[:3]
    questions = [
        f"{i}. {TEMPLATE_FOLLOWUP[d]}" for i, d in enumerate(ordered_dims, 1)
    ]
    return questions, "template", "还想再了解几点，帮你把体质判断得更准一些："


def _interpret_with_llm(result: ce.ConstitutionResult) -> tuple[str, str]:
    """通俗化。返回 (文本, 来源 llm|rule)"""
    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_interpret_messages(
                result.primary, result.secondary, result.evidence, result.primary_label,
            )
        ]
        resp = client.chat(msgs, key_step=True)
        if resp.text.strip():
            return resp.text.strip(), f"llm:{resp.provider}:{resp.model}"
    except Exception as e:  # noqa: BLE001
        logger.warning("通俗化失败，使用规则表述",
                       extra={"extra_fields": {"error": str(e)[:120]}})
    return ce.interpret_to_words(result), "rule"


def _explain_herbs_with_llm(result: ce.ConstitutionResult, candidates: list[dict],
                            special_groups: list[str]) -> str:
    from app.agents.prompts import build_herb_explain_messages

    try:
        client = get_llm_client()
        msgs = [
            Message(role=m["role"], content=m["content"])
            for m in build_herb_explain_messages(candidates, result.primary, special_groups)
        ]
        resp = client.chat(msgs)
        if resp.text.strip():
            return resp.text.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("药材解读失败，降级为规则文本",
                       extra={"extra_fields": {"error": str(e)[:120]}})
    lines = [f"{c['name']}（{c.get('dosage','')}）：{c.get('reason','')}" for c in candidates]
    return "\n".join(lines)


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
) -> ConsultationOutcome:
    cid = _new_id()
    answers: dict[str, int] = dict(questionnaire or {})

    # 主诉中的关键词并入问卷（让一句话起手也能跑通）
    if chief_complaint:
        for qid, score in extract_answers_from_text(chief_complaint).items():
            answers.setdefault(qid, score)

    groups = list(special_groups or [])
    groups += sg.detect_special_groups(chief_complaint)
    groups = sorted(set(sg.assert_groups_valid(groups)))

    # ---- ① 输入侧安全闸 ----
    input_verdict = sg.check_input(chief_complaint)
    consultation = Consultation(
        id=cid, user_id=user_id,
        status="blocked_emergency" if input_verdict.blocked else "in_progress",
        chief_complaint=chief_complaint,
        special_groups=_dump(groups),
        questionnaire=_dump(answers),
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
            data={
                "consultation_id": cid,
                "verdict": input_verdict.to_dict(),
            },
        )

    return _advance(db, consultation, answers, groups, top_n=top_n, round_no=0)


def answer_consultation(
    db: Session, *, consultation_id: str, answer: str, top_n: int = 6
) -> ConsultationOutcome:
    consultation = db.get(Consultation, consultation_id)
    if consultation is None:
        raise NotFoundException("问诊记录不存在")
    if consultation.status.startswith("blocked"):
        raise EmergencyBlocked("该问诊已被安全策略终止，请重新开始一次问诊")

    answers = _load_questionnaire(consultation.questionnaire)
    for qid, score in extract_answers_from_text(answer).items():
        answers[qid] = max(answers.get(qid, 0), score)

    round_no = consultation.follow_up_rounds
    _add_message(db, consultation.id, "user", answer, round_no=round_no)
    consultation.chief_complaint = (
        f"{consultation.chief_complaint}\n用户补充：{answer}".strip()
    )
    groups = json.loads(consultation.special_groups or "[]")
    db.flush()
    return _advance(db, consultation, answers, groups, top_n=top_n, round_no=round_no + 1)


def _advance(
    db: Session,
    consultation: Consultation,
    answers: dict[str, int],
    groups: list[str],
    *,
    top_n: int,
    round_no: int,
) -> ConsultationOutcome:
    # ---- ② 确定性体质判定 ----
    result = ce.score(answers, rule_table_version=settings.rule_table_version)
    consultation.questionnaire = _dump(answers)
    consultation.constitution = _dump(result)
    consultation.follow_up_rounds = round_no

    missing = _missing_dimensions(answers)

    # ---- 信息不足 → 追问（≤2 轮）----
    if result.needs_follow_up and round_no < MAX_FOLLOWUP_ROUNDS:
        questions, source, intro = _generate_follow_up(
            result, answers, consultation.chief_complaint, missing, groups, round_no + 1
        )
        consultation.status = "follow_up"
        _add_message(db, consultation.id, "ai", "\n".join(questions), round_no=round_no + 1)
        db.commit()
        return ConsultationOutcome(
            consultation_id=consultation.id,
            phase="follow_up",
            status="follow_up",
            follow_up_questions=questions,
            follow_up_source=source,
            follow_up_round=round_no + 1,
            message=intro,
            constitution=_preview_constitution(result),
            special_groups=groups,
            disclaimer=sg.DISCLAIMER,
        )

    # ---- ③④ 药材匹配（仅 106 白名单）----
    checker = data_loader.get_whitelist_checker()
    index = data_loader.get_whitelist_index()
    match = hm.match_herbs(
        result, checker, whitelist_index=index,
        chief_complaint=consultation.chief_complaint,
        special_groups=groups, top_n=top_n,
    )
    consultation.herbal_match = _dump(match)

    # ---- ⑤ 输出侧安全闸 ----
    interpretation, _src = _interpret_with_llm(result)
    interpretation, out_verdict = sg.check_output(interpretation)
    _log_safety(db, consultation.id, out_verdict.triggers)

    candidates = [c.to_dict() for c in match.candidates]
    explanation = _explain_herbs_with_llm(result, candidates, groups)
    explanation, _ = sg.check_output(explanation, with_recipe_disclaimer=True)

    final_verdict = match.safety or sg.SafetyVerdict()
    consultation.safety_verdict = _dump({
        "match": final_verdict.to_dict(),
        "output": out_verdict.to_dict(),
    })
    consultation.status = "completed"
    _add_message(db, consultation.id, "ai", interpretation, round_no=round_no)
    db.commit()

    return ConsultationOutcome(
        consultation_id=consultation.id,
        phase="completed",
        status="completed",
        follow_up_round=round_no,
        message="已完成体质辨识与药膳方向推荐",
        constitution=result.to_dict(),
        recommend={
            "herbs": candidates,
            "rejected": [r.to_dict() for r in match.rejected],
            "explanation": explanation,
            "rule_table_version": match.rule_table_version,
            "evidence": [
                data_loader.get_whitelist_retriever().get(c["name"]).to_dict()
                for c in candidates
                if data_loader.get_whitelist_retriever().get(c["name"])
            ],
        },
        interpretation=interpretation,
        special_groups=groups,
        safety=final_verdict.to_dict(),
        disclaimer=sg.DISCLAIMER,
    )


def _preview_constitution(result: ce.ConstitutionResult) -> dict:
    """追问阶段也返回当前倾向（不强行辨证，标记为不置信）"""
    return {
        "primary": result.primary,
        "primary_label": "暂未判定（信息不足）",
        "secondary": [],
        "scores": result.scores,
        "deterministic": True,
        "insufficient_info": True,
        "answered_total": result.answered_total,
        "evidence": result.evidence,
    }


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
        "special_groups": json.loads(c.special_groups or "[]"),
        "questionnaire": json.loads(c.questionnaire or "{}"),
        "constitution": _safe_json(c.constitution),
        "recommend": _safe_json(c.herbal_match),
        "recipe": _safe_json(c.recipe),
        "safety": _safe_json(c.safety_verdict),
        "messages": [
            {"role": m.role, "content": m.content, "round": m.round_no,
             "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S")}
            for m in msgs
        ],
    }


def _safe_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


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
            "chief_complaint": c.chief_complaint[:80],
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
    return {k: v for k, v in CONSTITUTION_INFO.items()}
