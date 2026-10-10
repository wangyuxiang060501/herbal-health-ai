# -*- coding: utf-8 -*-
"""BC6 历史档案接口（MVP 单用户模式）

 GET /api/v1/user/history    问诊历史列表
 GET /api/v1/user/trend      体质变化趋势（九维转化分）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.services import consultation_service as cs

router = APIRouter(prefix="/user", tags=["历史档案（BC6）"])


@router.get("/history", summary="问诊历史")
def history(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return ok(cs.list_history(db, limit=limit))


@router.get("/trend", summary="体质变化趋势")
def trend(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return ok(cs.constitution_trend(db, limit=limit))
