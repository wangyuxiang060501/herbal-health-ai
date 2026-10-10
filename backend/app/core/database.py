# -*- coding: utf-8 -*-
"""数据库引擎与会话

设计要点（对应 系统架构设计.md 5.2.5）：
  - SQLite 起步 → MySQL 8.0 平滑迁移（同为 SQLAlchemy URL，仅换连接串）
  - 依赖注入 get_db()，业务层不感知引擎细节
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    url = settings.database_url
    _ensure_sqlite_dir(url)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """ORM 基类"""


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover
    """SQLite 下开启外键约束（MySQL 默认开启，保持两端行为一致）"""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（开发期用；正式环境走 Alembic 迁移）"""
    import app.models  # noqa: F401  注册全部模型到 Base.metadata

    Base.metadata.create_all(bind=engine)
