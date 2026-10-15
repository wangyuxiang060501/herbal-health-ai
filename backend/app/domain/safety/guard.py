# -*- coding: utf-8 -*-
"""BC7 安全合规 —— 裁决引擎（纯领域逻辑，无框架依赖）

三道安全闸（对应 系统架构设计.md 6.1）：
  check_input  —— 输入侧：急症拦截、特殊人群识别
  check_herbs  —— 知识侧：黑名单拦截 / 106 白名单硬校验 / 十八反十九畏 / 特殊人群过滤
  check_output —— 输出侧：医疗术语过滤 + 免责声明注入（不可被 LLM 删改）

对外契约 SafetyVerdict（系统架构设计.md 4.1-④）：
  {
    "verdict": "pass | flag | block",
    "triggers": [{"rule","matched","action","replacement"}],
    "disclaimer_required": true,
    "log_ref": "safety_log:..."
  }
"""
from __future__ import annotations

import re
import uuid
from typing import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Sequence

from .constants import (
    BLACKLIST_HERBS,
    BLACKLIST_REPLACEMENT,
    DISCLAIMER,
    EMERGENCY_ADVICE,
    EMERGENCY_KEYWORDS,
    FORBIDDEN_TERMS,
    INCOMPATIBLE_PAIRS,
    RECIPE_DISCLAIMER,
    SPECIAL_GROUPS,
    SPECIAL_GROUP_FORBIDDEN,
    SPECIAL_GROUP_KEYWORDS,
    normalize_for_incompatibility,
)

# ===========================================================================
# 数据结构
# ===========================================================================


@dataclass(slots=True)
class Trigger:
    rule: str
    matched: str
    action: str                     # block | flag | replace | filter
    replacement: str = ""
    detail: str = ""


@dataclass(slots=True)
class SafetyVerdict:
    verdict: str = "pass"           # pass | flag | block
    triggers: list[Trigger] = field(default_factory=list)
    disclaimer_required: bool = True
    log_ref: str = ""

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "triggers": [
                {
                    "rule": t.rule, "matched": t.matched, "action": t.action,
                    **({"replacement": t.replacement} if t.replacement else {}),
                    **({"detail": t.detail} if t.detail else {}),
                }
                for t in self.triggers
            ],
            "disclaimer_required": self.disclaimer_required,
            "log_ref": self.log_ref,
        }


def _new_log_ref() -> str:
    return f"safety_log:{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


# ===========================================================================
# 第一道闸：输入侧
# ===========================================================================


def detect_emergency(text: str) -> str | None:
    """命中急症关键词则返回命中词，否则 None"""
    if not text:
        return None
    for kw in EMERGENCY_KEYWORDS:
        if kw in text:
            return kw
    return None


def detect_special_groups(text: str) -> list[str]:
    """从自由文本中识别特殊人群标记"""
    found: list[str] = []
    if not text:
        return found
    for group, kws in SPECIAL_GROUP_KEYWORDS.items():
        if any(k in text for k in kws):
            found.append(group)
    return found


def check_input(text: str) -> SafetyVerdict:
    """输入侧安全校验：急症 → block"""
    v = SafetyVerdict(log_ref=_new_log_ref())
    hit = detect_emergency(text)
    if hit:
        v.verdict = "block"
        v.triggers.append(
            Trigger(rule="急症关键词", matched=hit, action="block", detail=EMERGENCY_ADVICE)
        )
    return v


# ===========================================================================
# 第二道闸：知识侧（药材）
# ===========================================================================


def is_blacklisted(name: str) -> bool:
    n = name.strip()
    return any(n == b or b in n for b in BLACKLIST_HERBS)


def find_incompatibility(names: Sequence[str]) -> tuple[str, str, str] | None:
    """在候选药材集合中查找十八反/十九畏冲突"""
    normalized = [normalize_for_incompatibility(n.strip()) for n in names]
    norm_set = set(normalized)
    for a, b, rule in INCOMPATIBLE_PAIRS:
        na, nb = normalize_for_incompatibility(a), normalize_for_incompatibility(b)
        if na in norm_set and nb in norm_set:
            # 回原始名
            orig_a = names[normalized.index(na)]
            orig_b = names[normalized.index(nb)]
            return orig_a, orig_b, rule
    return None


_PAREN_RE = re.compile(r"[（(]([^）)]*)[）)]")


def _paren_tokens(name: str) -> list[str]:
    """剥出括号内的候选别名（仅兜底用；要求 ≥2 字，避免「甜/苦」这类单字规格）"""
    out: list[str] = []
    for m in _PAREN_RE.finditer(name):
        for tok in re.split(r"[、,，/]", m.group(1)):
            tok = tok.strip()
            if len(tok) >= 2:
                out.append(tok)
    return out


class WhitelistChecker:
    """106 种白名单校验器 —— 推荐层的唯一合法来源

    不变量：**任何进入推荐结果的药材，in_whitelist 必须恒为 True。**

    别名问题（2026-10 修）：目录里存在两类括号，语义完全不同——
      别名型：「姜（生姜、干姜）」「枣（大枣、酸枣、黑枣）」「龙眼肉（桂圆）」
      限定型：「杏仁（甜、苦）」「肉苁蓉（荒漠）」——括号里是规格而非别名
    只按「取括号前主名」匹配的话，用户或模型说「大枣」「干姜」会被误判为
    「不在药食同源目录」而拦掉，属于安全闸的**假阴性**（误杀合法药材）。
    所以别名必须由数据源显式给出（aliases 参数），括号一律不自动猜；
    只有在调用方不传 aliases 时才退化解析括号作为兜底。
    """

    def __init__(self, names: Iterable[str],
                 aliases: Mapping[str, str] | None = None):
        self._names: set[str] = {n.strip() for n in names if n and n.strip()}
        # 主名 / 别名 → 规范名
        self._base: dict[str, str] = {}
        for n in self._names:
            base = n.split("（")[0].strip()
            self._base.setdefault(base, n)
            self._base.setdefault(n, n)
        if aliases is None:
            for n in self._names:
                for tok in _paren_tokens(n):
                    self._base.setdefault(tok, n)
        else:
            for alias, canonical in aliases.items():
                a = alias.strip()
                if a and len(a) >= 2:
                    self._base.setdefault(a, canonical.strip() or alias)

    def __len__(self) -> int:
        return len(self._names)

    @property
    def names(self) -> set[str]:
        return set(self._names)

    @property
    def aliases(self) -> dict[str, str]:
        """别名 → 规范名（不含规范名自身），供调试与论文展示"""
        return {k: v for k, v in self._base.items() if k not in self._names}

    def contains(self, name: str) -> bool:
        n = name.strip()
        return n in self._names or n in self._base

    def canonical(self, name: str) -> str | None:
        """返回白名单中的规范名，不在白名单则返回 None"""
        n = name.strip()
        if n in self._names:
            return n
        return self._base.get(n)


def check_herbs(
    candidate_names: Sequence[str],
    whitelist: WhitelistChecker,
    special_groups: Sequence[str] = (),
) -> tuple[list[str], SafetyVerdict]:
    """知识侧校验。返回 (通过校验的药材列表, SafetyVerdict)

    规则优先级：
      1) 黑名单命中       → 拦截并记录 replacement（flag）
      2) 非白名单成员     → 拦截（flag，视为『不可入膳』）
      3) 特殊人群禁用     → 剔除（flag）
      4) 十八反十九畏冲突 → 剔除后者（flag）
    """
    v = SafetyVerdict(log_ref=_new_log_ref())
    passed: list[str] = []

    for raw in candidate_names:
        name = raw.strip()
        if not name:
            continue

        # 1) 黑名单
        if is_blacklisted(name):
            repl = BLACKLIST_REPLACEMENT.get(name, "")
            v.verdict = "flag"
            v.triggers.append(
                Trigger(rule="高危药材黑名单", matched=name, action="replace",
                        replacement=repl,
                        detail=f"该药材为处方毒性药材，禁止入膳" + (f"，已建议替换为{repl}" if repl else ""))
            )
            if repl and repl not in passed and whitelist.contains(repl):
                passed.append(repl)
            continue

        # 2) 白名单硬校验 —— 这是「查询层 vs 推荐层」的分界线
        canonical = whitelist.canonical(name)
        if canonical is None:
            v.verdict = "flag"
            v.triggers.append(
                Trigger(rule="非药食同源品种", matched=name, action="reject",
                        detail="药膳属普通食品，法定仅可使用卫健委 106 种药食同源物质；"
                               "该药材可在药材百科查询，但不得进入推荐方案")
            )
            continue

        # 3) 特殊人群禁用
        hit_group = None
        for g in special_groups:
            if canonical in SPECIAL_GROUP_FORBIDDEN.get(g, []):
                hit_group = g
                break
        if hit_group:
            v.verdict = "flag"
            v.triggers.append(
                Trigger(rule="特殊人群保护", matched=f"{hit_group}·{canonical}",
                        action="reject", detail=f"{hit_group}不宜使用该药材，已剔除")
            )
            continue

        passed.append(canonical)

    # 4) 配伍禁忌（十八反十九畏）
    conflict = find_incompatibility(passed)
    if conflict:
        a, b, rule = conflict
        passed.remove(b)
        v.verdict = "flag"
        v.triggers.append(
            Trigger(rule=f"{rule}配伍禁忌", matched=f"{a} × {b}", action="reject",
                    detail=f"{a}与{b}属{rule}，已移除后者")
        )

    return passed, v


# ===========================================================================
# 第三道闸：输出侧
# ===========================================================================


def filter_medical_terms(text: str) -> tuple[str, list[Trigger]]:
    """替换诊断性/疗效承诺类表述。返回 (过滤后文本, 触发记录)"""
    if not text:
        return text, []
    triggers: list[Trigger] = []
    out = text
    for bad, good in FORBIDDEN_TERMS.items():
        if bad in out:
            cnt = out.count(bad)
            out = out.replace(bad, good)
            triggers.append(
                Trigger(rule="医疗术语过滤", matched=bad, action="filter",
                        replacement=good, detail=f"替换 {cnt} 处")
            )
    return out, triggers


def check_output(text: str, with_recipe_disclaimer: bool = False) -> tuple[str, SafetyVerdict]:
    """输出侧校验：术语过滤 + 强制免责声明"""
    v = SafetyVerdict(log_ref=_new_log_ref())
    clean, triggers = filter_medical_terms(text)
    if triggers:
        v.verdict = "flag"
        v.triggers.extend(triggers)

    disclaimer = RECIPE_DISCLAIMER if with_recipe_disclaimer else DISCLAIMER
    if disclaimer not in clean:
        clean = f"{clean.rstrip()}\n\n⚠️ 免责声明：{disclaimer}"
    return clean, v


# ===========================================================================
# 便捷组合
# ===========================================================================


def validate_free_text_free_of_emergency(text: str) -> None:
    """供 service 层直接抛异常的便捷入口"""
    hit = detect_emergency(text)
    if hit:
        from app.core.responses import EmergencyBlocked

        raise EmergencyBlocked(
            EMERGENCY_ADVICE,
            data={"rule": "急症关键词", "matched": hit, "action": "block"},
        )


def assert_groups_valid(groups: Sequence[str]) -> list[str]:
    """过滤非法的人群标记"""
    return [g for g in groups if g in SPECIAL_GROUPS]
