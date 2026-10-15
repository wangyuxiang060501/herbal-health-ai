# -*- coding: utf-8 -*-
"""认证安全基元：bcrypt 口令散列 + JWT 令牌签发/校验（清单 5.4.1 后端部分）

选型说明（论文可引用）：
  - 口令散列用 **bcrypt** 而不是 MD5/SHA-1：自带随机盐 + 可调 cost，
    抗彩虹表与暴力破解；不引入 passlib（其 1.7.4 与 bcrypt>=4.1 有兼容问题），
    直接调 bcrypt 官方 API。
  - 令牌用 **JWT（HS256）**：无状态、免服务端会话存储，适合本系统
    「单实例 SQLite」的部署形态；代价是无法单点吊销，因此
    access token 寿命压短（默认 2h），refresh token 承担续期。
  - 令牌成对签发：access（短寿命，走 Authorization 头）+ refresh（长寿命，
    仅用于 /auth/refresh）。claim `typ` 区分二者，防止 refresh token
    被当成 access token 直接访问业务接口。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.responses import UnauthorizedException

ACCESS = "access"
REFRESH = "refresh"

# bcrypt 算法本身只取口令前 72 字节，超长部分被静默截断——
# 这意味着 "a"*72 + "x" 与 "a"*72 + "y" 被视为同一口令。显式拒绝更安全。
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise ValueError("密码过长（utf-8 编码后超过 72 字节）")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        # 散列串损坏 / 格式非法时按校验失败处理，不暴露内部错误
        return False


def _secret() -> str:
    # 未单独配置 jwt_secret_key 时回落到 app_secret_key，保证开发环境开箱可用；
    # 生产环境应在 .env 中配置独立强随机值（.env.example 已给出说明）。
    return settings.jwt_secret_key or settings.app_secret_key


def _create_token(subject: int, typ: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(subject),
        "typ": typ,
        "iat": now,
        "exp": now + expires,
        # 唯一令牌 ID：同一秒内签发的令牌载荷不再相同（刷新旋转可观测），
        # 也为将来「吊销列表」预留锚点。
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, _secret(), algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, ACCESS, timedelta(minutes=settings.jwt_access_expire_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, REFRESH, timedelta(days=settings.jwt_refresh_expire_days)
    )


def create_token_pair(user_id: int) -> dict[str, Any]:
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
        "expires_in": settings.jwt_access_expire_minutes * 60,
    }


def decode_token(token: str, *, expected_type: str = ACCESS) -> dict[str, Any]:
    """解码并校验令牌；任何失败统一抛 401，不向外部分辨具体原因（防探测）"""
    try:
        claims = jwt.decode(
            token, _secret(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        raise UnauthorizedException("登录状态已失效，请重新登录")
    if claims.get("typ") != expected_type:
        # refresh token 不能当 access token 用，反之亦然
        raise UnauthorizedException("令牌类型不正确")
    return claims


def user_id_from_token(token: str, *, expected_type: str = ACCESS) -> int:
    claims = decode_token(token, expected_type=expected_type)
    try:
        return int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise UnauthorizedException("令牌载荷非法")
