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

# 6.4.1 接口文档：分组说明写进 openapi_tags，
# 这样 /docs 里每个模块自带"这一组是干什么的、有什么约束"，不用另写一份 Word。
OPENAPI_TAGS = [
    {
        "name": "问诊会话（核心闭环）",
        "description": (
            "问卷 → 体质判定 → 追问 → 推荐 → 药膳 的完整闭环，由 LangGraph 状态机驱动。\n\n"
            "**业务码提示**：急症拦截与安全拦截返回 **HTTP 200** 但 `code=40301 / 40302`，"
            "不是 HTTP 错误——前端需要解包 `code` 才能正确提示用户。"
        ),
    },
    {
        "name": "药材知识（查询层）",
        "description": (
            "604 味药材的百科查询。**只读**。\n\n"
            "⚠️ 这里的品种**不代表可以入膳**：能否入膳看 `usage_policy`，"
            "只有落在 106 种药食同源目录内的才可进推荐方案（ADR-004 数据分层）。"
        ),
    },
    {
        "name": "RAG 知识检索（P3）",
        "description": (
            "734 片知识库的检索接口。`/rag/explain` 会分别给出语义通道、"
            "关键词通道与融合结果，用于验证混合检索确实有效。"
        ),
    },
    {
        "name": "安全合规（BC7）",
        "description": (
            "三道安全闸的自查入口：`probe-herbs` 裁决候选药材，`probe-output` 过滤输出文本。\n\n"
            "**不变量**：`probe-herbs` 返回的 `passed` 列表中每一项都保证 ∈ 106 白名单。"
        ),
    },
    {
        "name": "元信息",
        "description": "数据集概况、问卷结构、九种体质、LLM 状态、缓存命中率。",
    },
    {
        "name": "历史档案（BC6）",
        "description": "问诊历史列表与体质变化趋势。",
    },
]

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    summary="多智能体协同 + RAG 的中医药智慧康养系统",
    description=(
        "基于多智能体协同与检索增强生成（RAG）的中医药智慧康养系统。\n\n"
        "## 两条不可逾越的红线\n\n"
        "1. **不做疾病诊断** —— 输出侧强制过滤诊断性/疗效承诺类表述，"
        "并注入不可删除的免责声明；命中急症关键词立即终止问诊并提示就医。\n"
        "2. **推荐药材必须 ∈ 国家 106 种药食同源目录** —— 查询层（604 味）与"
        "推荐层（106 种）严格隔离，非白名单品种一律不得进入方案。\n\n"
        "## 架构速览\n\n"
        "`domain`（零框架依赖）← `orchestration`（LangGraph）← `services` ← `api`，"
        "`rag` 作为检索端口被编排层调用。领域层禁止依赖任何框架，"
        "这条约束由架构测试强制（见 README「依赖方向铁律」）。"
    ),
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "毕业设计项目", "url": "http://127.0.0.1:8000/docs"},
    license_info={"name": "仅供毕业设计与学习使用"},
    docs_url="/docs",
    redoc_url="/redoc",
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
