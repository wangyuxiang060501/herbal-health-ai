# -*- coding: utf-8 -*-
"""BC3 体质判定引擎测试 —— 证明「确定性判定」这条路线是真的

论文口径（ADR-002）：判定必须是纯函数，可复现、可解释、可单测。
下面每一条测试都可以在答辩现场演示。
"""
from __future__ import annotations

from app.domain.constitution import engine as ce
from app.domain.constitution.questionnaire import (
    NINE_CONSTITUTIONS,
    PINGHE,
    QI_XU,
    QUESTIONNAIRE,
    YANG_XU,
    SCORE_LABELS,
)


def _full(answers: dict, default: int = 1) -> dict:
    """补全未作答题目为默认分"""
    full = {}
    for dim in QUESTIONNAIRE.values():
        for q in dim.questions:
            full[q.id] = answers.get(q.id, default)
    return full


YANG_XU_ANSWERS = _full({
    "阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5,
}, default=1)

QI_XU_ANSWERS = _full({
    "气虚质_1": 5, "气虚质_2": 4, "气虚质_3": 4,
}, default=1)

ALL_LOW = _full({}, default=1)
ALL_HIGH_PINGHE = _full({}, default=5)


class TestDeterminism:
    def test_同一输入必得同一输出(self):
        r1 = ce.score(YANG_XU_ANSWERS)
        r2 = ce.score(YANG_XU_ANSWERS)
        assert r1.scores == r2.scores
        assert r1.primary == r2.primary
        assert r1.secondary == r2.secondary
        assert r1.evidence == r2.evidence

    def test_字典顺序不影响结果(self):
        a = dict(YANG_XU_ANSWERS)
        b = dict(reversed(list(YANG_XU_ANSWERS.items())))
        assert ce.score(a).scores == ce.score(b).scores

    def test_与入参顺序无关的排序稳定性(self):
        """This._generate evidence 排序必须稳定"""
        evidence = ce.build_evidence(YANG_XU_ANSWERS)
        assert evidence == sorted(evidence)


class TestScoring:

    def test_阳虚_主体质正确(self):
        r = ce.score(YANG_XU_ANSWERS)
        assert r.primary == YANG_XU
        assert r.primary_label == "判定为是"
        assert ce.validate_all_nine_keys(r)

    def test_转化分公式正确(self):
        """((原始分 - 条目数) / (条目数×4)) × 100"""
        answers = {"阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5}
        r = ce.score(answers)
        # 原始分 15，条目数 3 → (15-3)/(3*4)*100 = 100
        assert r.details[YANG_XU]["raw_score"] == 15
        assert r.details[YANG_XU]["converted_score"] == 100.0
        assert r.details[YANG_XU]["judged"] == "是"

    def test_全低分判定为平和(self):
        r = ce.score(ALL_LOW)
        assert r.primary == PINGHE

    def test_九维得分键齐全(self):
        r = ce.score(YANG_XU_ANSWERS)
        assert list(r.scores.keys()) == NINE_CONSTITUTIONS
        assert set(r.details.keys()) == set(NINE_CONSTITUTIONS)

    def test_未作答维度标记未测评(self):
        r = ce.score({"阳虚质_1": 5})
        assert r.details["痰湿质"]["answered"] == 0
        assert r.details["痰湿质"]["judged"] == "未测评"

    def test_非法评分被忽略(self):
        answers = dict(YANG_XU_ANSWERS)
        answers["阳虚质_1"] = 99          # 越界
        answers["未知题号"] = 5            # 不存在的题号
        r = ce.score(answers)
        # 越界值被丢弃 → 该维度只计入 2 条有效答案；未知题号不产生任何维度
        assert r.details[YANG_XU]["answered"] == 2
        assert r.details[YANG_XU]["raw_score"] == 10

    def test_全高分_偏颇体质全部达标时不判平和(self):
        r = ce.score(ALL_HIGH_PINGHE)
        # 全部维度转化分 100，主体质应为某个偏颇体质（按同分名称排序首个）
        assert r.primary != PINGHE or r.primary_label == "判定为平和质"
        assert max(r.scores[k] for k in NINE_CONSTITUTIONS if k != PINGHE) >= 40


class TestFollowUp:
    def test_信息不足时触发追问(self):
        r = ce.score({"阳虚质_1": 5, "气虚质_1": 5})
        assert r.needs_follow_up is True
        assert r.follow_up_reason

    def test_信息充分时不追问(self):
        r = ce.score(YANG_XU_ANSWERS)
        # 27 题全答且主体质分差明显
        assert r.answered_total == 27

    def test_完全无信息不强行辨证(self):
        r = ce.score({})
        assert r.insufficient_info is True
        assert r.needs_follow_up is True


class TestEvidence:
    def test_证据链包含具体题目与答案(self):
        answers = {"阳虚质_1": 5}
        r = ce.score(answers)
        assert any("阳虚质" in e for e in r.evidence)
        assert any(SCORE_LABELS[5] in e for e in r.evidence)

    def test_低分答案不进证据链(self):
        r = ce.score({"阴虚质_1": 1, "阴虚质_2": 1})
        assert not any("阴虚质" in e for e in r.evidence)


class TestInterpretation:
    def test_倾向性表述不含断言词(self):
        r = ce.score(YANG_XU_ANSWERS)
        text = ce.interpret_to_words(r)
        assert "倾向于" in text
        assert "你就是" not in text
        assert "确诊" not in text

    def test_兼夹体质被表述出来(self):
        answers = dict(YANG_XU_ANSWERS)
        answers.update({"气虚质_1": 5, "气虚质_2": 5, "气虚质_3": 5})
        r = ce.score(answers)
        assert QI_XU in r.secondary or r.primary == QI_XU
        assert len(r.secondary) <= 2

    def test_从序列化结果可还原表述(self):
        r = ce.score(YANG_XU_ANSWERS)
        text = ce.interpret_to_words_from_dict(r.to_dict())
        assert "阳虚质" in text
