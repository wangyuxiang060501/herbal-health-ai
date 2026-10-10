# -*- coding: utf-8 -*-
"""FastAPI 应用入口"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.responses import register_exception_handlers

setup_logging()
settings = get_settings()
logger = get_logger("app.main")

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "基于多智能体协同与检索增强生成（RAG）的中医药智慧康养系统。\n\n"
        "**安全红线**：本系统仅提供日常食疗养生方向参考，**不做疾病诊断**；"
        "推荐的药材严格限定于国家卫健委 106 种药食同源目录。"
    ),
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup() -> None:
    from app.core.database import engine
    from app.models.entities import Base  # noqa: F401 注册模型

    # SQLite 开发期自动建表；MySQL 场景建议改用 Alembic 迁移
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    logger.info(
        "应用启动",
        extra={"extra_fields": {
            "env": settings.app_env, "llm_provider": settings.llm_provider,
            "api_prefix": settings.api_prefix, "version": __version__,
        }},
    )


@app.get("/", summary="健康检查")
def root():
    return {
        "app": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
        "notice": "本系统仅提供日常食疗养生方向参考，不做疾病诊断。",
    }


@app.get("/health", summary="健康探针")
def health():
    return {"status": "ok", "version": __version__}
