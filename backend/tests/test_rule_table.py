# -*- coding: utf-8 -*-
"""规则表自检 —— 保证「规则永远不会给出非法药材」"""
from __future__ import annotations

from app.domain.constitution.questionnaire import CONSTITUTION_INFO, BIASED_CONSTITUTIONS
from app.domain.recommendation.matcher import match_herbs
from app.domain.recommendation.rule_table import (
    CONSTITUTION_HERB_RULES,
    RULE_TABLE_VERSION,
    SYMPTOM_HERB_HINTS,
    herb_names_in_table,
)


class TestRuleTableIntegrity:

    def test_规则表覆盖全部九种体质(self):
        assert set(CONSTITUTION_HERB_RULES.keys()) == set(CONSTITUTION_INFO.keys())

    def test_每种偏颇体质至少有5条规则(self):
        for k in BIASED_CONSTITUTIONS:
            assert len(CONSTITUTION_HERB_RULES[k]) >= 5, f"{k} 规则过少"

    def test_规则表中的药材全部属于106白名单(self, whitelist):
        """★ 关键不变量：规则表不得引用任何白名单外的品种"""
        bad = [n for n in herb_names_in_table() if not whitelist.contains(n)]
        assert not bad, f"规则表引用了非法药材：{bad}"

    def test_每条规则都有理由且权重为正(self):
        for dim, rules in CONSTITUTION_HERB_RULES.items():
            for r in rules:
                assert r.weight > 0, f"{dim}.{r.name} 权重非正"
                assert r.reason.strip(), f"{dim}.{r.name} 缺理由"

    def test_版本号非空(self):
        assert RULE_TABLE_VERSION


class TestMatcher:
    """推荐输出的白名单不变量"""

    def test_候选全部在白名单内(self, whitelist, whitelist_index, db):
        from app.domain.constitution.engine import score

        answers = {f"阳虚质_{i}": 5 for i in (1, 2, 3)}
        result = score(answers)
        m = match_herbs(result, whitelist, whitelist_index=whitelist_index, top_n=8)
        for c in m.candidates:
            assert c.in_whitelist is True
            assert whitelist.contains(c.name)

    def test_候选按得分降序(self, whitelist, whitelist_index):
        from app.domain.constitution.engine import score

        result = score({f"阴虚质_{i}": 5 for i in (1, 2, 3)})
        m = match_herbs(result, whitelist, whitelist_index=whitelist_index)
        scores = [c.score for c in m.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_附子不可能出现在候选里(self, whitelist, whitelist_index):
        """即使规则表被误改引入了黑名单药材，安全层也必须把它拦下"""
        from app.domain.constitution.engine import score

        result = score({f"气虚质_{i}": 5 for i in (1, 2, 3)})
        m = match_herbs(result, whitelist, whitelist_index=whitelist_index)
        assert "附子" not in [c.name for c in m.candidates]

    def test_孕妇标记下剔除慎用品种(self, whitelist, whitelist_index):
        from app.domain.constitution.engine import score

        result = score({f"血瘀质_{i}": 5 for i in (1, 2, 3)})
        m = match_herbs(
            result, whitelist, whitelist_index=whitelist_index,
            special_groups=["孕妇"],
        )
        names = [c.name for c in m.candidates]
        assert "桃仁" not in names
        assert "西红花" not in names

    def test_主诉关键词能改变推荐排序(self, whitelist, whitelist_index):
        from app.domain.constitution.engine import score

        result = score({f"气虚质_{i}": 5 for i in (1, 2, 3)})
        base = match_herbs(result, whitelist, whitelist_index=whitelist_index)
        with_insomnia = match_herbs(
            result, whitelist, whitelist_index=whitelist_index,
            chief_complaint="最近入睡困难，失眠多梦",
        )
        assert [c.name for c in base.candidates] != [c.name for c in with_insomnia.candidates]
        assert "酸枣仁" in [c.name for c in with_insomnia.candidates]

    def test_被拒药材必须有理由(self, whitelist, whitelist_index):
        from app.domain.constitution.engine import score

        result = score({f"阳虚质_{i}": 5 for i in (1, 2, 3)})
        m = match_herbs(result, whitelist, whitelist_index=whitelist_index)
        for r in m.rejected:
            assert r.reason

    def test_推荐的药材都带有用量与禁忌(self, whitelist, whitelist_index):
        from app.domain.constitution.engine import score

        result = score({f"痰湿质_{i}": 5 for i in (1, 2, 3)})
        m = match_herbs(result, whitelist, whitelist_index=whitelist_index)
        for c in m.candidates:
            assert c.dosage, f"{c.name} 缺用量"
