# -*- coding: utf-8 -*-
"""API 公共依赖：当前用户解析（清单 5.4.1）

设计：认证是**可选**的。
  - 未登录（无 Authorization 头）：匿名模式，与 MVP 行为完全一致；
  - 已登录：问诊记录归属 user_id，历史/趋势只看自己的数据。
这样旧客户端与既有集成测试（全程无令牌）行为不变，平滑升级。
"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import UnauthorizedException
from app.core.security import user_id_from_token
from app.models.entities import User
from app.services import auth_service


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedException("Authorization 头格式应为 Bearer <token>")
    return token.strip()


def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """匿名/登录双模：无令牌返回 None，有令牌必须合法（否则 401）"""
    token = _extract_token(request)
    if token is None:
        return None
    user = auth_service.get_user(db, user_id_from_token(token))
    if user is None:
        raise UnauthorizedException("账户不存在或已注销")
    return user


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """强制登录：用于 /auth/profile 等纯账户接口"""
    user = get_optional_user(request, db)
    if user is None:
        raise UnauthorizedException("请先登录")
    return user
