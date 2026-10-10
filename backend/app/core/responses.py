# -*- coding: utf-8 -*-
"""统一响应封装与业务异常体系（对应 系统架构设计.md 4.5）"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")

# ---------------------------------------------------------------------------
# 统一响应
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None


class PagedData(BaseModel, Generic[T]):
    total: int = 0
    page: int = 1
    size: int = 20
    items: list[Any] = Field(default_factory=list)


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}


def paged(items: list, total: int, page: int, size: int) -> dict:
    return ok({"total": total, "page": page, "size": size, "items": items})


# ---------------------------------------------------------------------------
# 业务异常
# ---------------------------------------------------------------------------

# 业务错误码
CODE_BAD_REQUEST = 400
CODE_UNAUTHORIZED = 401
CODE_NOT_FOUND = 404
CODE_RATE_LIMIT = 429
CODE_EMERGENCY_BLOCKED = 40301      # 急症拦截
CODE_SAFETY_BLOCKED = 40302         # 安全拦截（黑名单/非白名单）
CODE_LLM_UNAVAILABLE = 50301        # LLM provider 不可用
CODE_BUDGET_EXCEEDED = 50302        # 预算超限


class AppException(Exception):
    """业务异常基类"""

    code: int = CODE_BAD_REQUEST
    default_message: str = "请求错误"
    http_status: int = 400

    def __init__(self, message: str | None = None, data: Any = None):
        self.message = message or self.default_message
        self.data = data
        super().__init__(self.message)


class NotFoundException(AppException):
    code = CODE_NOT_FOUND
    default_message = "资源不存在"
    http_status = 404


class UnauthorizedException(AppException):
    code = CODE_UNAUTHORIZED
    default_message = "未认证"
    http_status = 401


class EmergencyBlocked(AppException):
    """急症关键词命中 → 终止问诊，引导就医"""

    code = CODE_EMERGENCY_BLOCKED
    default_message = "检测到急症描述，问诊已终止"
    http_status = 200  # 以业务语义返回，前端据此弹出红色警示而非报错


class SafetyBlocked(AppException):
    """安全拦截（高危药材 / 非白名单）"""

    code = CODE_SAFETY_BLOCKED
    default_message = "安全校验未通过"
    http_status = 200


class LLMUnavailable(AppException):
    code = CODE_LLM_UNAVAILABLE
    default_message = "大模型服务暂不可用"
    http_status = 503


class BudgetExceeded(AppException):
    code = CODE_BUDGET_EXCEEDED
    default_message = "本月 LLM 预算已用尽，已切换降级 provider"
    http_status = 200


def register_exception_handlers(app) -> None:
    from .logging import get_logger

    logger = get_logger("app.error")

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException):
        logger.warning(
            "业务异常",
            extra={"extra_fields": {"path": request.url.path, "code": exc.code, "msg": exc.message}},
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=fail(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception(
            "未捕获异常",
            extra={"extra_fields": {"path": request.url.path, "type": type(exc).__name__}},
        )
        return JSONResponse(status_code=500, content=fail(500, "服务器内部错误"))
