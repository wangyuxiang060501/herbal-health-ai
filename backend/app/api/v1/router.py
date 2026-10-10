# -*- coding: utf-8 -*-
"""/api/v1 路由汇总"""
from __future__ import annotations

from fastapi import APIRouter

from . import consultation, herbs, meta, safety, user

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(herbs.router)
api_router.include_router(consultation.router)
api_router.include_router(user.router)
api_router.include_router(safety.router)

__all__ = ["api_router"]
