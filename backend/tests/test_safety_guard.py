# -*- coding: utf-8 -*-
"""安全层测试 —— 不可豁免的安全不变量

其中 `test_附子必须被推荐层拒绝` 是 **架构验收测试**（ADR-004）：
它验证的不是数据，而是「828 查询层与 106 推荐层的隔离是否真的生效」。
"""
from __future__ import annotations

from app.domain.safety import guard as sg
from app.domain.safety.constants import DISCLAIMER


class TestEmergency:
    """第一道闸：急症拦截"""

    def test_胸痛必须拦截(self):
        v = sg.check_input("我最近胸痛，呼吸困难")
        assert v.verdict == "block"
        assert v.triggers[0].rule == "急症关键词"

    def test_咯血晕厥呼吸困难逐一被拦(self):
        for text in ["咯血了怎么办", "突然晕厥", "喘不上气", "意识丧失"]:
            v = sg.check_input(text)
            assert v.verdict == "block", f"{text} 未被拦截"

    def test_普通描述不误伤(self):
        v = sg.check_input("我最近容易疲乏，有点怕冷")
        assert v.verdict == "pass"

    def test_拦截后不产出任何药材推荐(self):
        """急症拦截的语义是终止问诊，不是给出打折方案"""
        v = sg.check_input("胸痛")
        assert v.blocked
        assert all(t.action == "block" for t in v.triggers)


class TestBlacklist:
    """第二道闸：黑名单 + 白名单硬校验"""

    def test_附子必须被推荐层拒绝(self, whitelist):
        """★ 架构验收测试（起步路线.md 1.5-③ / ADR-004）"""
        passed, v = sg.check_herbs(["附子"], whitelist)
        assert "附子" not in passed
        # 且必须给出替换建议
        trigger = next(t for t in v.triggers if t.matched == "附子")
        assert trigger.action == "replace"
        assert trigger.replacement, "黑名单命中必须给出替换品种"
        assert whitelist.contains(trigger.replacement), "替换品种必须也在白名单内"

    def test_一批高压食材全部拒绝或被替换(self, whitelist):
        for bad in ["附子", "川乌", "半夏", "朱砂", "马钱子", "雄黄"]:
            passed, _ = sg.check_herbs([bad], whitelist)
            assert bad not in passed, f"{bad} 进入了推荐结果"

    def test_非白名单药材不得进入推荐(self, whitelist):
        """828 查询层的普通药材，即使无毒也不得入膳"""
        passed, v = sg.check_herbs(["柴胡"], whitelist)
        assert "柴胡" not in passed
        assert any(t.rule == "非药食同源品种" for t in v.triggers)

    def test_白名单药材全部放行(self, whitelist):
        good = ["黄芪", "党参", "山药", "茯苓", "薏苡仁", "枸杞子"]
        passed, v = sg.check_herbs(good, whitelist)
        assert set(passed) == set(good)
        assert v.verdict == "pass"

    def test_候选中的白名单不变量(self, whitelist):
        """通过校验的每一项，都必须能在白名单中反查到规范名"""
        mixed = ["附子", "黄芪", "当归", "麻黄", "百合"]
        passed, _ = sg.check_herbs(mixed, whitelist)
        for name in passed:
            assert whitelist.contains(name)


class TestSpecialGroups:
    """特殊人群保护"""

    def test_孕妇过滤禁用品种(self, whitelist):
        passed, v = sg.check_herbs(["当归", "黄芪"], whitelist, ["孕妇"])
        assert "当归" not in passed
        assert "黄芪" in passed
        assert any(t.rule == "特殊人群保护" for t in v.triggers)

    def test_哺乳期过滤麦芽(self, whitelist):
        passed, _ = sg.check_herbs(["麦芽", "山药"], whitelist, ["哺乳期"])
        assert "麦芽" not in passed
        assert "山药" in passed

    def test_儿童过滤白果(self, whitelist):
        passed, _ = sg.check_herbs(["白果"], whitelist, ["儿童"])
        assert "白果" not in passed

    def test_自动识别文本中的孕妇标记(self):
        assert "孕妇" in sg.detect_special_groups("我现在怀着孕，能吃这个吗")
        assert "孕妇" in sg.detect_special_groups("我怀孕三个月了")
        assert "儿童" in sg.detect_special_groups("我女儿五岁")
        assert "慢性病患者" in sg.detect_special_groups("我有高血压，长期服药")


class TestIncompatibility:
    """十八反十九畏"""

    def test_甘草与甘遂不可同用(self, whitelist):
        passed, v = sg.check_herbs(["甘草", "甘遂"], whitelist)
        # 甘遂本身就在黑名单里，先被拦；甘草应保留
        assert "甘遂" not in passed

    def test_十八反配伍能被识别(self, whitelist):
        """丁香 × 郁金：若两者都在白名单内，必须被配伍规则拆开"""
        assert whitelist.contains("丁香")
        passed, v = sg.check_herbs(["丁香", "郁金"], whitelist)
        if whitelist.contains("郁金"):
            assert "郁金" in passed or "丁香" in passed
            assert not ("郁金" in passed and "丁香" in passed)

    def test_乌头类别名归一(self):
        from app.domain.safety.constants import normalize_for_incompatibility

        assert normalize_for_incompatibility("附子") == "乌头"
        assert normalize_for_incompatibility("川乌") == "乌头"


class TestOutput:
    """第三道闸：输出侧"""

    def test_诊断性术语被替换(self):
        clean, triggers = sg.filter_medical_terms("这个方子可以治疗你的失眠")
        assert "治疗" not in clean
        assert "调理" in clean
        assert triggers

    def test_疗效承诺被降格(self):
        clean, _ = sg.filter_medical_terms("这个方案保证有效，可以治愈")
        assert "治愈" not in clean
        assert "保证有效" not in clean

    def test_免责声明不可缺失(self):
        clean, v = sg.check_output("你的体质倾向于阳虚质。")
        assert DISCLAIMER in clean
        assert v.disclaimer_required is True

    def test_免责声明不被重复追加(self):
        text = f"建议多吃温热食物。\n\n⚠️ 免责声明：{DISCLAIMER}"
        clean, _ = sg.check_output(text)
        assert clean.count(DISCLAIMER) == 1

    def test_急症词表本身无重复(self):
        from app.domain.safety.constants import EMERGENCY_KEYWORDS

        assert len(EMERGENCY_KEYWORDS) == len(set(EMERGENCY_KEYWORDS))


class TestWhitelistAlias:
    """别名匹配 —— 防「误杀合法药材」（安全闸的假阴性）

    目录里「枣（大枣、酸枣、黑枣）」「姜（生姜、干姜）」这类条目，
    如果只按括号前主名匹配，用户/模型说「大枣」「干姜」会被判为
    「非药食同源品种」而拦掉。这不是安全，是漏推荐。
    """

    def test_括号内别名可命中(self, whitelist):
        for alias, expect_base in [("大枣", "枣"), ("酸枣", "枣"), ("黑枣", "枣"),
                                   ("生姜", "姜"), ("干姜", "姜"), ("桂圆", "龙眼肉")]:
            assert whitelist.contains(alias), f"{alias} 应可命中"
            assert whitelist.canonical(alias).startswith(expect_base)

    def test_别名字段可命中(self, whitelist):
        """如「代代花」别名「枳壳花」、「薏苡仁」别名「薏米」"""
        for alias, canon in [("枳壳花", "代代花"), ("薏米", "薏苡仁"),
                             ("枸杞", "枸杞子"), ("薯蓣", "山药")]:
            assert whitelist.contains(alias), f"{alias} 应可命中"
            assert whitelist.canonical(alias) == canon

    def test_规格限定词不得被当成别名(self, whitelist):
        """「杏仁（甜、苦）」「肉苁蓉（荒漠）」的括号是规格，不是别名"""
        for token in ["荒漠", "甜", "苦"]:
            assert not whitelist.contains(token), f"「{token}」是规格限定词，不应入白名单"

    def test_别名不放松安全边界(self, whitelist):
        """扩别名的前提：黑名单与 828 普通药材仍必须被拒"""
        for bad in ["附子", "川乌", "半夏", "朱砂", "柴胡", "麻黄"]:
            assert not whitelist.contains(bad), f"{bad} 不应在白名单内"

    def test_别名表不含规范名自身(self, whitelist):
        aliases = whitelist.aliases
        assert not (set(aliases) & whitelist.names), "别名表里混入了规范名"
        assert len(aliases) >= 40, f"别名条数偏少：{len(aliases)}"


class TestWhitelistData:
    """白名单数据本身的自检"""

    def test_恰好_106_条(self, whitelist):
        assert len(whitelist) == 106

    def test_白名单中不含任何黑名单药材(self, whitelist):
        from app.domain.safety.constants import BLACKLIST_HERBS

        leaked = [b for b in BLACKLIST_HERBS if whitelist.contains(b)]
        assert not leaked, f"白名单被污染：{leaked}"

    def test_白名单名称全部非空且唯一(self, whitelist):
        names = whitelist.names
        assert all(n.strip() for n in names)
        assert len(names) == 106
