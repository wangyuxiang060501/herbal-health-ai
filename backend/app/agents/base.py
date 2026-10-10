# -*- coding: utf-8 -*-
"""LLM 端口定义（BC9）

约束（对应 起步路线.md 二 / 系统架构设计.md 4.2）：
  **任何 Agent / Service 代码都不得直接 import 任一 provider 的 SDK。**
  业务只依赖 LLMClient.chat / chat_stream / count_tokens 三个方法。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Message:
    role: str                      # system | user | assistant
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMResponse:
    text: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    trace_id: str = ""
    fallback_used: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMError(Exception):
    """provider 调用失败"""
    def __init__(self, message: str, provider: str = "", retryable: bool = True):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class BaseLLMProvider(ABC):
    """所有 provider 的统一接口"""

    name: str = "base"
    model: str = ""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 60,
    ) -> Iterator[str]:
        """逐段产出文本（供 SSE 打字机）"""

    def count_tokens(self, text: str) -> int:
        """粗略估算：中文按 1 字 ≈ 1 token，英文/数字按 4 字符 ≈ 1 token"""
        if not text:
            return 0
        cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        rest = len(text) - cn
        return cn + (rest // 4)

    def available(self) -> bool:
        """该 provider 在当前环境下是否可用（缺 Key / 服务未启动 → False）"""
        return True
