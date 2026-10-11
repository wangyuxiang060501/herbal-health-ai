# -*- coding: utf-8 -*-
"""症状抽取 —— 自由文本 → 问卷结构化答案（规则层 · 确定性）

放在 services 层而非 domain 层：FREE_TEXT_HINTS 是工程启发式（可调参），
不属于 GB/T 46939—2025 判定标准的一部分。

抽取结果永远只作为「补充」，不覆盖用户显式填写的问卷：
    - start：setdefault（问卷优先）
    - answer：max（后一轮补充可以加强已有信号）

被 consultation_service 与 orchestration.nodes 共同引用，保证
「线性流水线」与「LangGraph 状态图」两条执行路径行为一致。
"""
from __future__ import annotations

from typing import Sequence

from app.domain.constitution.questionnaire import (
    ALL_QUESTIONS,
    PINGHE,
    QUESTIONNAIRE,
    SCORE_LABELS,
)

# 关键词 → 结构化答案映射（取同类关键词中的最高分）
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
    "很累": {"气虚质_1": 4},
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


def blend_answers(base: dict[str, int], text: str, *, override: bool = False) -> dict[str, int]:
    """把自由文本信号并入已有问卷

    Args:
        base: 已有答案
        override: True 时文本信号取 max 覆盖（多轮追问场景）；
                  False 时仅在题目未答时补充（首轮主诉场景，问卷优先）
    """
    out = dict(base or {})
    for qid, score in extract_answers_from_text(text).items():
        if override:
            out[qid] = max(out.get(qid, 0), score)
        else:
            out.setdefault(qid, score)
    return out


def missing_dimensions(answers: dict[str, int]) -> list[str]:
    """返回完全未作答的体质维度（平和质不计入阻塞）"""
    missing = []
    for dim_key, dim in QUESTIONNAIRE.items():
        if not any(q.id in answers for q in dim.questions):
            missing.append(dim_key)
    return missing


def answered_summary(answers: dict[str, int]) -> str:
    """已作答题目的可读摘要（≥3 分视为阳性），供 Prompt 输入"""
    lines = []
    for qid, score in sorted(answers.items()):
        q = ALL_QUESTIONS.get(qid)
        if q and score >= 3:
            lines.append(f"- {q.text}：{SCORE_LABELS.get(score, score)}")
    return "\n".join(lines)


# 模板兜底追问（LLM 不可用时使用）
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


def template_questions(missing: Sequence[str], limit: int = 3) -> list[str]:
    """按缺失维度生成模板问题（平和质优先级最低）"""
    ordered = [d for d in missing if d != PINGHE][:limit] or list(missing)[:limit]
    return [f"{i}. {TEMPLATE_FOLLOWUP.get(d, d)}" for i, d in enumerate(ordered, 1)]
