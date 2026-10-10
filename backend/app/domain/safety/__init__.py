# -*- coding: utf-8 -*-
"""BC7 安全合规（横切关注点，不反向依赖任何业务上下文）"""
from .constants import (
    BLACKLIST_HERBS,
    BLACKLIST_REPLACEMENT,
    DISCLAIMER,
    EMERGENCY_KEYWORDS,
    FORBIDDEN_TERMS,
    INCOMPATIBLE_PAIRS,
    SPECIAL_GROUPS,
    RECIPE_DISCLAIMER,
)
from .guard import (
    SafetyVerdict,
    Trigger,
    WhitelistChecker,
    assert_groups_valid,
    check_herbs,
    check_input,
    check_output,
    detect_emergency,
    detect_special_groups,
    filter_medical_terms,
    find_incompatibility,
    is_blacklisted,
    validate_free_text_free_of_emergency,
)

__all__ = [
    "BLACKLIST_HERBS", "BLACKLIST_REPLACEMENT", "DISCLAIMER", "RECIPE_DISCLAIMER",
    "EMERGENCY_KEYWORDS", "FORBIDDEN_TERMS", "INCOMPATIBLE_PAIRS", "SPECIAL_GROUPS",
    "SafetyVerdict", "Trigger", "WhitelistChecker", "assert_groups_valid",
    "check_herbs", "check_input", "check_output", "detect_emergency",
    "detect_special_groups", "filter_medical_terms", "find_incompatibility",
    "is_blacklisted", "validate_free_text_free_of_emergency",
]
