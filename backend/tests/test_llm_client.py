# -*- coding: utf-8 -*-
"""LLM 网关测试 —— 验证「换 provider 不改业务代码」"""
from __future__ import annotations

from app.agents.base import LLMResponse, Message
from app.agents.llm_client import LLMClient
from app.agents.providers import MockProvider
from app.agents.usage import UsageMeter


class TestMockProvider:

    def test_离线可用(self):
        p = MockProvider()
        assert p.available()
        resp = p.chat([Message(role="user", content="你好")])
        assert isinstance(resp.text, str) and resp.text

    def test_流式可迭代(self):
        p = MockProvider()
        chunks = list(p.chat_stream([Message(role="user", content="你好")]))
        assert chunks
        assert "".join(chunks)

    def test_token估算(self):
        p = MockProvider()
        assert p.count_tokens("") == 0
        assert p.count_tokens("中文四个字") == 5      # 中文按字数计


class TestLLMFacade:

    def test_默认使用mock_不联网(self):
        client = LLMClient(primary="mock", fallback_chain=[])
        # 断言：除 mock 外其他 provider 不可用时不阻塞
        health = client.health()
        assert health["primary"] == "mock"
        assert health["available"]["mock"] is True

    def test_调用成功并记录用量(self):
        client = LLMClient(primary="mock", fallback_chain=[])
        resp = client.chat([Message(role="user", content="请介绍你自己")])
        assert resp.provider == "mock"
        stats = client.meter.stats()
        assert stats["total_calls"] >= 1

    def test_主provider不可用自动降级(self):
        """构造一个「总是失败」的 provider，验证降级链"""
        from app.agents.base import BaseLLMProvider, LLMError

        class BrokenProvider(BaseLLMProvider):
            name = "broken"

            def chat(self, messages, **kw):
                raise LLMError("必然失败", provider="broken", retryable=False)

            def chat_stream(self, messages, **kw):
                raise LLMError("必然失败", provider="broken", retryable=False)

        client = LLMClient(primary="mock", fallback_chain=[])
        client.providers["broken"] = BrokenProvider()
        client.primary = "broken"
        client.fallback_chain = ["mock"]
        resp = client.chat([Message(role="user", content="hi")])
        assert resp.provider == "mock"
        assert resp.fallback_used is True

    def test_全部失败抛出LLMError(self):
        from app.agents.base import BaseLLMProvider, LLMError

        class Broken(BaseLLMProvider):
            name = "broken2"

            def chat(self, messages, **kw):
                raise LLMError("挂了", provider="broken2", retryable=False)

            def chat_stream(self, messages, **kw):
                raise LLMError("挂了", provider="broken2", retryable=False)

        client = LLMClient(primary="mock", fallback_chain=[])
        client.providers = {"broken2": Broken()}
        client.primary = "broken2"
        client.fallback_chain = []
        try:
            client.chat([Message(role="user", content="hi")])
        except LLMError:
            pass
        else:  # pragma: no cover
            raise AssertionError("应当抛出 LLMError")


class TestUsageMeter:

    def test_成本计算(self):
        m = UsageMeter(monthly_budget_cny=100, price_per_1k_prompt_cny=0.002,
                       price_per_1k_completion_cny=0.008)
        cost = m.cost_of(1000, 1000)
        assert abs(cost - 0.01) < 1e-9

    def test_预算告警与超限(self):
        m = UsageMeter(monthly_budget_cny=0.01)
        m.record(LLMResponse(prompt_tokens=1000, completion_tokens=1000, provider="mock"))
        st = m.status()
        assert st.exceeded is True
        assert st.alert is True

    def test_未超预算不告警(self):
        m = UsageMeter(monthly_budget_cny=1000)
        m.record(LLMResponse(prompt_tokens=10, completion_tokens=10, provider="mock"))
        assert m.status().alert is False
