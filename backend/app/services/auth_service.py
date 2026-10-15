# -*- coding: utf-8 -*-
"""认证业务：注册 / 登录 / 令牌刷新 / 资料（清单 5.4.1）

安全口径：
  - 登录失败统一报「手机号或密码错误」，不区分「号不存在」与「密码错」，
    防止手机号枚举探测。
  - 口令只存 bcrypt 散列，任何接口、日志都不得出现明文。
  - 注册即登录：直接返回令牌对，减少一次往返。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.responses import AppException, UnauthorizedException
from app.core.security import (
    create_token_pair,
    hash_password,
    user_id_from_token,
    verify_password,
)
from app.models.entities import User

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _profile(user: User) -> dict:
    return {
        "id": user.id,
        "phone": user.phone,
        "nickname": user.nickname,
        "special_groups": user.special_groups,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _with_tokens(user: User) -> dict:
    return {"user": _profile(user), **create_token_pair(user.id)}


def register(db: Session, *, phone: str, password: str, nickname: str = "") -> dict:
    phone = phone.strip()
    if not PHONE_RE.match(phone):
        raise AppException("手机号格式不正确")
    exists = db.scalar(select(User.id).where(User.phone == phone))
    if exists is not None:
        raise AppException("该手机号已注册，请直接登录")
    try:
        pwd_hash = hash_password(password)
    except ValueError as e:
        raise AppException(str(e))
    user = User(
        phone=phone,
        nickname=nickname.strip() or "养生爱好者",
        password_hash=pwd_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _with_tokens(user)


def login(db: Session, *, phone: str, password: str) -> dict:
    user = db.scalar(select(User).where(User.phone == phone.strip()))
    # 统一失败话术：不透露「手机号是否存在」
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedException("手机号或密码错误")
    return _with_tokens(user)


def refresh(db: Session, *, refresh_token: str) -> dict:
    uid = user_id_from_token(refresh_token, expected_type="refresh")
    user = db.get(User, uid)
    if user is None:
        raise UnauthorizedException("账户不存在或已注销")
    # 旋转刷新：每次刷新都签发新令牌对，旧 refresh token 自然过期作废
    return _with_tokens(user)


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)
