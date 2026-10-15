# -*- coding: utf-8 -*-
"""BC6 历史档案接口（MVP 单用户模式）

 GET /api/v1/user/history    问诊历史列表
 GET /api/v1/user/trend      体质变化趋势（九维转化分）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.core.database import get_db
from app.core.responses import ok
from app.models.entities import User
from app.services import consultation_service as cs

router = APIRouter(prefix="/user", tags=["历史档案（BC6）"])


@router.get("/history", summary="问诊历史")
def history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # 与 /consultation/user/history 同口径：登录看自己的，匿名看匿名记录
    if user is not None:
        return ok(cs.list_history(db, limit=limit, user_id=user.id))
    return ok(cs.list_history(db, limit=limit, anonymous=True))


@router.get("/trend", summary="体质变化趋势")
def trend(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if user is not None:
        return ok(cs.constitution_trend(db, limit=limit, user_id=user.id))
    return ok(cs.constitution_trend(db, limit=limit, anonymous=True))
