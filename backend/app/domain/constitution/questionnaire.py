# -*- coding: utf-8 -*-
"""九种体质常量与问卷定义

标准依据：**GB/T 46939—2025《中医体质分类与判定》**（2026-04-01 实施，
取代 ZYYXH/T157-2009 行业标准）—— 见 系统架构设计.md C4 / ADR-002。

⚠️ 待确认项 U2/D7：标准**全文**（各亚量表逐条题目原文）本工作区尚未获取，
   本问卷的题面依据九种体质「典型体感问题」的通行表述编写，
   已标记 `verified=False`。取得标准原文后只需替换 QUESTIONNAIRE 内容，
   计分算法（engine.py 的 原始分→转化分）保持不变。
"""
from __future__ import annotations

from dataclasses import dataclass

# ===========================================================================
# 九种体质
# ===========================================================================
PINGHE = "平和质"
QI_XU = "气虚质"
YANG_XU = "阳虚质"
YIN_XU = "阴虚质"
TAN_SHI = "痰湿质"
SHI_RE = "湿热质"
XUE_YU = "血瘀质"
QI_YU = "气郁质"
TE_BING = "特禀质"

NINE_CONSTITUTIONS: list[str] = [
    PINGHE, QI_XU, YANG_XU, YIN_XU, TAN_SHI, SHI_RE, XUE_YU, QI_YU, TE_BING,
]

# 八种偏颇体质（平和质之外的全部）
BIASED_CONSTITUTIONS: list[str] = [c for c in NINE_CONSTITUTIONS if c != PINGHE]

# 每个维度的显示信息
CONSTITUTION_INFO: dict[str, dict[str, str]] = {
    PINGHE: {"desc": "阴阳气血调和，体态适中、面色红润、精力充沛", "tendency": "脏腑功能协调"},
    QI_XU: {"desc": "元气不足，疲乏、气短、自汗", "tendency": "肌肉松软、声音低弱"},
    YANG_XU: {"desc": "阳气不足，畏寒怕冷、手足不温", "tendency": "喜热饮、精神不振"},
    YIN_XU: {"desc": "阴液亏少，口燥咽干、手足心热", "tendency": "形体偏瘦、盗汗"},
    TAN_SHI: {"desc": "痰湿凝聚，形体肥胖、腹部肥满、口黏苔腻", "tendency": "身重不爽、痰多"},
    SHI_RE: {"desc": "湿热内蕴，面垢油光、口苦苔黄腻", "tendency": "易生痤疮、便黏滞"},
    XUE_YU: {"desc": "血行不畅，肤色晦暗、易有瘀斑", "tendency": "口唇色暗、痛有定处"},
    QI_YU: {"desc": "气机郁滞，神情抑郁、忧虑脆弱", "tendency": "胸胁胀满、善太息"},
    TE_BING: {"desc": "先天失常，生理缺陷或过敏反应", "tendency": "易过敏、鼻塞喷嚏"},
}

# ===========================================================================
# 计分配置（GB/T 46939—2025「等级计分算法」）
# ===========================================================================

# 五级评分：没有(1) 很少(2) 有时(3) 经常(4) 总是(5)
SCORE_LABELS: dict[int, str] = {1: "没有", 2: "很少", 3: "有时", 4: "经常", 5: "总是"}

# 偏颇体质判定阈值
THRESHOLD_YES = 40.0        # 转化分 ≥ 40 判定「是」
THRESHOLD_TENDENCY = 30.0   # 30 ≤ 转化分 < 40 判定「倾向是」
# 平和质判定阈值（需同时满足其他 8 种均低于某阈值）
THRESHOLD_PINGHE_YES = 60.0
THRESHOLD_PINGHE_BASIC = 60.0
THRESHOLD_OTHER_BASIC = 40.0

MAX_SECONDARY = 2           # 兼夹体质最多 2 个
FOLLOWUP_MARGIN = 8.0       # 前两名得分差低于该值时，认为需要 AI 追问以明确


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    dimension: str
    text: str
    core: bool = False       # True 表示属于「快速版」必答题（每维度 1 题）
    reverse: bool = False    # 反向计分（暂未使用，保留给标准原文接入）


@dataclass(frozen=True, slots=True)
class Dimension:
    key: str
    name: str
    questions: tuple[Question, ...]


def _q(dim: str, idx: int, text: str, core: bool = False) -> Question:
    return Question(id=f"{dim}_{idx}", dimension=dim, text=text, core=core)


# ===========================================================================
# 问卷本体：9 个维度 × 3 题 = 27 题
#   - 完整版 27 题（约 3-5 分钟）
#   - 快速版 9 题（仅 core=True），命中的最终效果「5-8 个问题 + AI 追问」形态
# ===========================================================================
QUESTIONNAIRE: dict[str, Dimension] = {
    QI_XU: Dimension(QI_XU, "气虚质", (
        _q(QI_XU, 1, "你容易疲乏，总觉得没力气吗？", core=True),
        _q(QI_XU, 2, "你容易气短，稍微活动就喘不上气吗？"),
        _q(QI_XU, 3, "你活动量稍大就容易出虚汗吗？"),
    )),
    YANG_XU: Dimension(YANG_XU, "阳虚质", (
        _q(YANG_XU, 1, "你平时手脚发凉、怕冷吗？", core=True),
        _q(YANG_XU, 2, "你的胃脘部、背部或腰膝容易怕冷吗？"),
        _q(YANG_XU, 3, "你衣服总比别人穿得多，比别人更怕冷吗？"),
    )),
    YIN_XU: Dimension(YIN_XU, "阴虚质", (
        _q(YIN_XU, 1, "你常感到手心脚心发热，或脸上烘热吗？", core=True),
        _q(YIN_XU, 2, "你常感到口燥咽干、眼睛干涩吗？"),
        _q(YIN_XU, 3, "你夜间睡觉时容易出汗（盗汗）吗？"),
    )),
    TAN_SHI: Dimension(TAN_SHI, "痰湿质", (
        _q(TAN_SHI, 1, "你常感觉胸闷或腹部胀满吗？", core=True),
        _q(TAN_SHI, 2, "你感觉身体沉重不轻松，腹部肥满松软吗？"),
        _q(TAN_SHI, 3, "你常常痰多，或觉得嘴里黏腻不清爽吗？"),
    )),
    SHI_RE: Dimension(SHI_RE, "湿热质", (
        _q(SHI_RE, 1, "你的面部容易出油、鼻部油光发亮吗？", core=True),
        _q(SHI_RE, 2, "你容易长痤疮（青春痘）或皮肤瘙痒吗？"),
        _q(SHI_RE, 3, "你常感到口苦、口臭或嘴里有异味吗？"),
    )),
    XUE_YU: Dimension(XUE_YU, "血瘀质", (
        _q(XUE_YU, 1, "你的皮肤容易在不经意间出现青紫瘀斑吗？", core=True),
        _q(XUE_YU, 2, "你的面色偏晦暗，或容易出现褐斑吗？"),
        _q(XUE_YU, 3, "你的口唇颜色偏暗（发紫、发暗）吗？"),
    )),
    QI_YU: Dimension(QI_YU, "气郁质", (
        _q(QI_YU, 1, "你常感到闷闷不乐、情绪低落吗？", core=True),
        _q(QI_YU, 2, "你常感到焦虑紧张，或无缘无故叹气吗？"),
        _q(QI_YU, 3, "你容易受到惊吓，或常感到害怕吗？"),
    )),
    TE_BING: Dimension(TE_BING, "特禀质", (
        _q(TE_BING, 1, "你容易对药物、食物、花粉、尘螨等过敏吗？", core=True),
        _q(TE_BING, 2, "你的皮肤容易起荨麻疹或其他皮疹吗？"),
        _q(TE_BING, 3, "你没有感冒时也常打喷嚏、鼻塞、流鼻涕吗？"),
    )),
    PINGHE: Dimension(PINGHE, "平和质", (
        _q(PINGHE, 1, "你精力充沛，能轻松应付日常工作生活吗？", core=True),
        _q(PINGHE, 2, "你能较快适应外界环境的变化吗？"),
        _q(PINGHE, 3, "你睡眠质量好，很少生病吗？"),
    )),
}

ALL_QUESTIONS: dict[str, Question] = {
    q.id: q for dim in QUESTIONNAIRE.values() for q in dim.questions
}

QUESTION_COUNT = len(ALL_QUESTIONS)


def core_question_ids() -> list[str]:
    return [q.id for q in ALL_QUESTIONS.values() if q.core]
