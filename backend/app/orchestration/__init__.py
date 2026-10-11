# -*- coding: utf-8 -*-
"""P2 · LangGraph 多智能体编排层

拓扑（ADR-006 集中式编排）：START → ①症状采集 → ②体质判定引擎（确定性）
   → ③Agent1 追问 / ④Agent2 药材匹配 → ⑤安全交叉校验
   → ⑥Agent3 药膳生成（P3 开关）→ ⑦结果组织 → END

依赖方向铁律：`app/orchestration` 可以依赖 `app/domain`，反之禁止。
"""
from __future__ import annotations

from app.orchestration import edges, nodes, runner, state

__all__ = ["edges", "nodes", "runner", "state"]
