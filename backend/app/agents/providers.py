# -*- coding: utf-8 -*-
""" provider 实现：ollama / OpenAI 兼容（deepseek、zhipu）/ mock

所有实现统一走 OpenAI 兼容协议，降低方差；Ollama 使用其原生 /api/chat 接口。
统一通过 httpx 调用，**不引入任何厂商 SDK** —— 这正是「供应商解耦」的落地方式
（少一个 SDK 依赖，就少一处被锁定的风险）。
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from .base import BaseLLMProvider, LLMError, LLMResponse, Message


def _trace() -> str:
    return uuid.uuid4().hex[:16]


class OpenAICompatProvider(BaseLLMProvider):
    """DeepSeek / 智谱 等 OpenAI 兼容协议的 provider"""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _build_payload(
        self, messages: list[Message], temperature: float, max_tokens: int, stream: bool
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> LLMResponse:
        if not self.available():
            raise LLMError(f"{self.name} 未配置 API Key", provider=self.name, retryable=False)
        started = time.perf_counter()
        payload = self._build_payload(messages, temperature, max_tokens, stream=False)
        try:
            with httpx.Client(timeout=timeout) as cli:
                resp = cli.post(
                    f"{self.base_url}/chat/completions",
                    json=payload, headers=self._headers(),
                )
        except httpx.HTTPError as e:
            raise LLMError(f"{self.name} 网络请求失败：{e}", provider=self.name)
        if resp.status_code != 200:
            retryable = resp.status_code in (429, 500, 502, 503, 504)
            raise LLMError(
                f"{self.name} 返回 {resp.status_code}：{resp.text[:200]}",
                provider=self.name, retryable=retryable,
            )
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise LLMError(f"{self.name} 响应格式异常：{str(data)[:200]}", provider=self.name)
        usage = data.get("usage", {}) or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
            trace_id=_trace(),
        )

    def chat_stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> Iterator[str]:
        if not self.available():
            raise LLMError(f"{self.name} 未配置 API Key", provider=self.name, retryable=False)
        payload = self._build_payload(messages, temperature, max_tokens, stream=True)
        with httpx.Client(timeout=timeout) as cli, cli.stream(
            "POST", f"{self.base_url}/chat/completions",
            json=payload, headers=self._headers(),
        ) as resp:
            if resp.status_code != 200:
                raise LLMError(
                    f"{self.name} 流式返回 {resp.status_code}",
                    provider=self.name,
                    retryable=resp.status_code in (429, 500, 502, 503, 504),
                )
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    delta = obj["choices"][0].get("delta", {}) or {}
                    piece = delta.get("content") or ""
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if piece:
                    yield piece


class OllamaProvider(BaseLLMProvider):
    """本地 Ollama（离线兜底，答辩断网演示用）"""

    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as cli:
                r = cli.get(f"{self.base_url}/api/tags")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> LLMResponse:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            with httpx.Client(timeout=timeout) as cli:
                resp = cli.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as e:
            raise LLMError(f"ollama 连接失败（是否已启动 ollama serve？）：{e}", provider="ollama")
        if resp.status_code != 200:
            raise LLMError(
                f"ollama 返回 {resp.status_code}：{resp.text[:200]}", provider="ollama"
            )
        data = resp.json()
        text = (data.get("message") or {}).get("content", "") or ""
        return LLMResponse(
            text=text,
            provider="ollama",
            model=self.model,
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
            trace_id=_trace(),
        )

    def chat_stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        with httpx.Client(timeout=timeout) as cli, cli.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            if resp.status_code != 200:
                raise LLMError(f"ollama 流式返回 {resp.status_code}", provider="ollama")
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = (obj.get("message") or {}).get("content") or ""
                if piece:
                    yield piece
                if obj.get("done"):
                    break


class MockProvider(BaseLLMProvider):
    """离线自检 provider —— 不联网、不花钱、不会因为没装 Ollama 就跑不通

    它的价值：让「不含 LLM 的那部分逻辑」（判定引擎、安全层、药材库、问诊落库）
    可以被完整地自动化测试与演示。
    """

    name = "mock"

    def __init__(self, model: str = "mock-rule-engine"):
        self.model = model

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        system = next((m.content for m in messages if m.role == "system"), "")
        started = time.perf_counter()
        return LLMResponse(
            text=self._mock_answer(system, last_user),
            provider="mock",
            model=self.model,
            prompt_tokens=self.count_tokens("".join(m.content for m in messages)),
            completion_tokens=self.count_tokens(self._mock_answer(system, last_user)),
            latency_ms=int((time.perf_counter() - started) * 1000),
            trace_id=_trace(),
        )

    def chat_stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> Iterator[str]:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        system = next((m.content for m in messages if m.role == "system"), "")
        for ch in self._mock_answer(system, last_user):
            yield ch

    # ---------------- mock 规则 ----------------
    @staticmethod
    def _mock_answer(system: str, user_text: str) -> str:
        if "追问" in system or "追问" in user_text[:200]:
            return (
                "还想再确认两点：\n"
                "1. 你平时大便成形吗？还是偏稀或黏腻？\n"
                "2. 你吃完饭后容易腹胀，或四肢沉重不愿动吗？"
            )
        return (
            "说明：当前运行在离线自检模式（mock provider），"
            "未调用真实大模型。体质判定与安全过滤均由确定性规则完成，"
            "结果本身不受影响；通俗化话术需配置真实 LLM 后才会生成。"
        )
