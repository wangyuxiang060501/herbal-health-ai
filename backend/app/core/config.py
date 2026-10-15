# -*- coding: utf-8 -*-
"""全局配置（Pydantic Settings，从 .env 读取）"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # -> backend/
PROJECT_ROOT = BACKEND_ROOT.parent                 # -> herb-health-ai/
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------- 基础 ----------------
    app_name: str = "中医药智慧康养系统"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    # ---------------- 数据库 ----------------
    database_url: str = "sqlite:///D:/herbal/var/app.db"
    # LangGraph Checkpointer 快照库（会话中断恢复，3.6.3）
    checkpoint_db_path: str = "D:/herbal/var/langgraph_ckpt.sqlite"

    # ---------------- LLM provider ----------------
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:8b"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
    llm_timeout: int = 60
    llm_max_retries: int = 2

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    use_reasoner_for_key_steps: bool = False

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4-flash"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"

    llm_fallback_chain: str = "ollama,mock"

    # ---------------- 成本护栏 ----------------
    monthly_budget_cny: float = 200.0
    price_per_1k_prompt_cny: float = 0.002
    price_per_1k_completion_cny: float = 0.008

    # ---------------- 数据文件 ----------------
    herbs_raw_path: str = "data/tcm_828_herbs.json"
    herbs_clean_path: str = "data/tcm_herbs_clean.json"
    whitelist_path: str = "data/food_medicine_106.json"
    rule_table_version: str = "v0.1-draft"

    # ---------------- RAG 检索增强（P3） ----------------
    rag_enabled: bool = True
    rag_kb_path: str = "data/kb/chunks.jsonl"          # 切片产物（build_kb.py 产出）
    rag_embedder: str = "auto"                          # auto|sentence|tfidf|hashing
    rag_vector_store: str = "auto"                      # auto|chroma|memory
    rag_index_path: str = "D:/herbal/var/rag_index.jsonl"
    rag_chroma_dir: str = "D:/herbal/var/chroma"
    rag_collection: str = "tcm_kb"
    rag_model_path: str = "D:/herbal/var/models/bge-small-zh"
    rag_top_k: int = 5
    # 注入 Agent Prompt 的上下文片段数（过大易超 token 预算）
    rag_context_chunks: int = 4

    # ---------------- 安全 ----------------
    persist_blocked_consultation: bool = True
    app_secret_key: str = "change-me-in-production"

    # ---------------- 派生属性 ----------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fallback_providers(self) -> list[str]:
        return [p.strip() for p in self.llm_fallback_chain.split(",") if p.strip()]

    def abs_data_path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else (BACKEND_ROOT / p)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
