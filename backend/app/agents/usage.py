# -*- coding: utf-8 -*-
"""Token 用量计量与成本护栏（ADR-003）

功能：
  1. 按次记录 provider / model / tokens / latency / cost
  2. 按自然月聚合成本
  3. 80% 预算告警，100% 自动降级（由 LLMClient 执行降级动作）
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .base import LLMResponse


@dataclass(slots=True)
class BudgetStatus:
    month: str                     # YYYY-MM
    used_cny: float = 0.0
    budget_cny: float = 0.0
    ratio: float = 0.0
    alert: bool = False            # ≥80%
    exceeded: bool = False         # ≥100%

    def to_dict(self) -> dict:
        return {
            "month": self.month, "used_cny": round(self.used_cny, 4),
            "budget_cny": self.budget_cny, "ratio": round(self.ratio, 4),
            "alert": self.alert, "exceeded": self.exceeded,
        }


@dataclass(slots=True)
class UsageMeter:
    """进程内计量器（持久化由 service 层落 usage_logs 表）"""

    monthly_budget_cny: float = 200.0
    price_per_1k_prompt_cny: float = 0.002
    price_per_1k_completion_cny: float = 0.008
    _records: list[LLMResponse] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def cost_of(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens / 1000 * self.price_per_1k_prompt_cny
            + completion_tokens / 1000 * self.price_per_1k_completion_cny
        )

    def record(self, resp: LLMResponse) -> float:
        cost = self.cost_of(resp.prompt_tokens, resp.completion_tokens)
        with self._lock:
            self._records.append(resp)
        return cost

    def month_used(self, month: str | None = None) -> float:
        m = month or datetime.now().strftime("%Y-%m")
        total = 0.0
        with self._lock:
            records = list(self._records)
        for r in records:
            total += self.cost_of(r.prompt_tokens, r.completion_tokens)
        return total if month is None else self._filter_month_cost(records, m)

    def _filter_month_cost(self, records: Iterable[LLMResponse], month: str) -> float:
        # 内存记录不含时间戳，退化为「全部算当月」——精确月度统计以 DB 的 usage_logs 为准
        return sum(self.cost_of(r.prompt_tokens, r.completion_tokens) for r in records)

    def status(self) -> BudgetStatus:
        m = datetime.now().strftime("%Y-%m")
        used = self.month_used(m)
        ratio = used / self.monthly_budget_cny if self.monthly_budget_cny else 0.0
        return BudgetStatus(
            month=m, used_cny=used, budget_cny=self.monthly_budget_cny, ratio=ratio,
            alert=ratio >= 0.8, exceeded=ratio >= 1.0,
        )

    def stats(self) -> dict:
        with self._lock:
            records = list(self._records)
        by_provider: dict[str, dict] = {}
        for r in records:
            item = by_provider.setdefault(
                r.provider, {"calls": 0, "tokens": 0, "latency_ms": 0, "errors": 0}
            )
            item["calls"] += 1
            item["tokens"] += r.total_tokens
            item["latency_ms"] += r.latency_ms
        for k, item in by_provider.items():
            if item["calls"]:
                item["avg_latency_ms"] = item["latency_ms"] // item["calls"]
        return {
            "total_calls": len(records),
            "by_provider": by_provider,
            "budget": self.status().to_dict(),
        }
