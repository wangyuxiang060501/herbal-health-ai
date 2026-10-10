# -*- coding: utf-8 -*-
"""Prompt 模板库 —— 集中管理、版本化，禁止散落在业务代码里"""
from .constitution import SYSTEM_PROMPT as AGENT1_SYSTEM
from .constitution import build_follow_up_messages, build_interpret_messages
from .food_recipe import build_recipe_messages
from .herb_match import build_herb_explain_messages

__all__ = [
    "AGENT1_SYSTEM",
    "build_follow_up_messages",
    "build_interpret_messages",
    "build_herb_explain_messages",
    "build_recipe_messages",
]
