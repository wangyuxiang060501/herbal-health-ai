# -*- coding: utf-8 -*-
"""AI 接入层：LLM 网关（BC9）+ Prompt 模板库"""
from . import prompts
from .base import BaseLLMProvider, LLMError, LLMResponse, Message
from .llm_client import LLMClient, get_llm_client, reset_llm_client
from .providers import MockProvider, OllamaProvider, OpenAICompatProvider
from .usage import BudgetStatus, UsageMeter

__all__ = [
    "prompts",
    "BaseLLMProvider", "LLMError", "LLMResponse", "Message",
    "LLMClient", "get_llm_client", "reset_llm_client",
    "MockProvider", "OllamaProvider", "OpenAICompatProvider",
    "UsageMeter", "BudgetStatus",
]
