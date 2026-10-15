# -*- coding: utf-8 -*-
"""认证接口（清单 5.4.1）

 POST /api/v1/auth/register   注册（手机号 + 密码，注册即登录）
 POST /api/v1/auth/login      登录
 POST /api/v1/auth/refresh    刷新令牌对（旋转刷新）
 GET  /api/v1/auth/profile    当前用户资料（需登录）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.responses import ok
from app.models.entities import User
from app.schemas import LoginIn, RefreshIn, RegisterIn
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["用户认证（5.4.1）"])


@router.post("/register", summary="注册")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    return ok(auth_service.register(
        db, phone=payload.phone, password=payload.password, nickname=payload.nickname
    ), message="注册成功")


@router.post("/login", summary="登录")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    return ok(auth_service.login(
        db, phone=payload.phone, password=payload.password
    ), message="登录成功")


@router.post("/refresh", summary="刷新令牌")
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    return ok(auth_service.refresh(db, refresh_token=payload.refresh_token))


@router.get("/profile", summary="当前用户资料")
def profile(user: User = Depends(get_current_user)):
    return ok({
        "id": user.id,
        "phone": user.phone,
        "nickname": user.nickname,
        "special_groups": user.special_groups,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    })
