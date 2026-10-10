# -*- coding: utf-8 -*-
"""BC5 药材知识接口（查询层，只读）

 GET /api/v1/herbs              列表（分页 + 类别/归经筛选 + 只看药食同源）
 GET /api/v1/herbs/search       关键词搜索
 GET /api/v1/herbs/categories   类别列表
 GET /api/v1/herbs/meridians    归经统计
 GET /api/v1/herbs/{id}         详情
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import NotFoundException, ok, paged
from app.services import herb_service

router = APIRouter(prefix="/herbs", tags=["药材知识（查询层）"])


@router.get("", summary="药材列表")
def list_herbs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None, description="如：补虚药"),
    meridian: str | None = Query(None, description="如：脾"),
    only_food_medicine: bool = Query(False, description="仅返回 106 种药食同源"),
    db: Session = Depends(get_db),
):
    items, total = herb_service.list_herbs(
        db, page=page, size=size, category=category,
        meridian=meridian, only_food_medicine=only_food_medicine,
    )
    return paged([herb_service.to_dict(h) for h in items], total, page, size)


@router.get("/categories", summary="药材类别列表")
def categories(db: Session = Depends(get_db)):
    return ok(herb_service.categories(db))


@router.get("/meridians", summary="归经统计")
def meridians(db: Session = Depends(get_db)):
    return ok(herb_service.meridians(db))


@router.get("/search", summary="药材搜索")
def search(
    q: str = Query(..., min_length=1, description="关键词：名称/功效/类别/成分"),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items = herb_service.search_herbs(db, q, size=size)
    if not items:
        raise NotFoundException(f"未找到与「{q}」相关的药材")
    return ok([herb_service.to_dict(h) for h in items])


@router.get("/{herb_id}", summary="药材详情")
def detail(herb_id: int, db: Session = Depends(get_db)):
    herb = herb_service.get_herb(db, herb_id)
    if herb is None:
        raise NotFoundException(f"药材 {herb_id} 不存在")
    return ok(herb_service.to_dict(herb))
