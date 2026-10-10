# -*- coding: utf-8 -*-
"""LLMClient —— 统一调用门面（多 provider + 重试 + 降级链 + 用量计量）

用法：
    client = get_llm_client()
    resp = client.chat([Message(role="user", content="...")])
    for piece in client.chat_stream(messages):
        ...

业务代码只认这个门面，provider 由 .env 的 LLM_PROVIDER 决定，切换不改业务代码。
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Sequence

from app.core.config import get_settings
from app.core.logging import get_logger

from .base import BaseLLMProvider, LLMError, LLMResponse, Message
from .providers import MockProvider, OllamaProvider, OpenAICompatProvider
from .usage import UsageMeter

logger = get_logger("llm.client")

settings = get_settings()


def build_providers() -> dict[str, BaseLLMProvider]:
    return {
        "ollama": OllamaProvider(settings.ollama_base_url, settings.ollama_model),
        "mock": MockProvider(),
        "deepseek": OpenAICompatProvider(
            "deepseek", settings.deepseek_base_url, settings.deepseek_api_key,
            settings.deepseek_model,
        ),
        "zhipu": OpenAICompatProvider(
            "zhipu", settings.zhipu_base_url, settings.zhipu_api_key, settings.zhipu_model,
        ),
    }


class LLMClient:
    """门面：provider 编排 + 重试 + 降级 + 成本护栏"""

    def __init__(
        self,
        primary: str | None = None,
        fallback_chain: Sequence[str] | None = None,
        meter: UsageMeter | None = None,
    ):
        self.providers = build_providers()
        self.primary = primary or settings.llm_provider
        self.fallback_chain = list(fallback_chain if fallback_chain is not None
                                   else settings.fallback_providers)
        self.meter = meter or UsageMeter(
            monthly_budget_cny=settings.monthly_budget_cny,
            price_per_1k_prompt_cny=settings.price_per_1k_prompt_cny,
            price_per_1k_completion_cny=settings.price_per_1k_completion_cny,
        )

    # ---------------- provider 顺序 ----------------
    def _order(self) -> list[str]:
        order = [self.primary]
        for p in self.fallback_chain:
            if p not in order:
                order.append(p)
        return [p for p in order if p in self.providers]

    def active_provider_name(self) -> str:
        budget = self.meter.status()
        if budget.exceeded:
            # 预算用尽 → 跳过付费 provider
            for p in self._order():
                if p in ("ollama", "mock"):
                    return p
        return self.primary

    def health(self) -> dict:
        return {
            "primary": self.primary,
            "fallback_chain": self.fallback_chain,
            "order": self._order(),
            "available": {
                name: prov.available() for name, prov in self.providers.items()
            },
            "budget": self.meter.status().to_dict(),
            "stats": self.meter.stats(),
        }

    # ---------------- 调用 ----------------
    def chat(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        key_step: bool = False,
    ) -> LLMResponse:
        msgs = list(messages)
        temp = settings.llm_temperature if temperature is None else temperature
        max_tok = settings.llm_max_tokens if max_tokens is None else max_tokens

        last_err: LLMError | None = None
        for idx, name in enumerate(self._order()):
            provider = self.providers[name]
            if not provider.available():
                logger.info("provider 不可用，跳过", extra={"extra_fields": {"provider": name}})
                continue
            model = self._resolve_model(name, key_step)
            if model and model != provider.model:
                provider.model = model
            try:
                resp = self._with_retry(provider, msgs, temp, max_tok)
            except LLMError as e:
                logger.warning(
                    "provider 调用失败，尝试降级",
                    extra={"extra_fields": {"provider": name, "error": str(e)[:120]}},
                )
                last_err = e
                continue
            resp.fallback_used = idx > 0
            cost = self.meter.record(resp)
            logger.info(
                "llm.call",
                extra={"extra_fields": {
                    "provider": resp.provider, "model": resp.model,
                    "tokens": resp.total_tokens, "latency_ms": resp.latency_ms,
                    "cost_cny": round(cost, 6), "trace_id": resp.trace_id,
                }},
            )
            return resp

        raise LLMError(
            f"全部 provider 调用失败：{last_err}" if last_err else "无可用 provider",
            provider=self.primary, retryable=False,
        )

    def chat_stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        msgs = list(messages)
        temp = settings.llm_temperature if temperature is None else temperature
        max_tok = settings.llm_max_tokens if max_tokens is None else max_tokens

        started = time.perf_counter()
        total = 0
        for idx, name in enumerate(self._order()):
            provider = self.providers[name]
            if not provider.available():
                continue
            try:
                for piece in provider.chat_stream(msgs, temperature=temp, max_tokens=max_tok):
                    total += provider.count_tokens(piece)
                    yield piece
            except LLMError as e:
                if idx == len(self._order()) - 1:
                    raise
                logger.warning("流式调用失败，尝试降级",
                               extra={"extra_fields": {"provider": name, "error": str(e)[:120]}})
                continue
            self.meter.record(LLMResponse(
                text="", provider=name, model=provider.model, completion_tokens=total,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ))
            return

    def count_tokens(self, text: str) -> int:
        return self.providers[self.primary].count_tokens(text)

    # ---------------- 内部 ----------------
    def _resolve_model(self, provider_name: str, key_step: bool) -> str | None:
        if provider_name == "deepseek":
            if key_step and settings.use_reasoner_for_key_steps:
                return settings.deepseek_reasoner_model
            return settings.deepseek_model
        if provider_name == "ollama":
            return settings.ollama_model
        if provider_name == "zhipu":
            return settings.zhipu_model
        return None

    def _with_retry(
        self, provider: BaseLLMProvider, messages: list[Message],
        temperature: float, max_tokens: int,
    ) -> LLMResponse:
        attempts = max(1, settings.llm_max_retries + 1)
        last: LLMError | None = None
        for i in range(attempts):
            try:
                return provider.chat(
                    messages, temperature=temperature,
                    max_tokens=max_tokens, timeout=settings.llm_timeout,
                )
            except LLMError as e:
                last = e
                if not e.retryable or i == attempts - 1:
                    break
                sleep_s = min(2 ** i, 8)
                logger.info("重试中",
                            extra={"extra_fields": {"provider": provider.name, "attempt": i + 1}})
                time.sleep(sleep_s)
        assert last is not None
        raise last


_CLIENT: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = LLMClient()
    return _CLIENT


def reset_llm_client() -> None:
    """测试用：重建单例"""
    global _CLIENT
    _CLIENT = None
