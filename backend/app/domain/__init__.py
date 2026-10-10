# -*- coding: utf-8 -*-
"""领域层（BC3/BC4/BC7）

依赖方向铁律（系统架构设计.md 3.2）：
  本包**禁止** import langgraph / langchain / sqlalchemy / fastapi / 任何 LLM SDK。
  该约束由 tests/test_architecture.py 作为架构适应度函数自动校验。
"""
from . import constitution, recommendation, safety

__all__ = ["constitution", "recommendation", "safety"]
