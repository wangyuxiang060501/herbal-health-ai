# -*- coding: utf-8 -*-
"""数据库引擎与会话

设计要点（对应 系统架构设计.md 5.2.5）：
  - SQLite 起步 → MySQL 8.0 平滑迁移（同为 SQLAlchemy URL，仅换连接串）
  - 依赖注入 get_db()，业务层不感知引擎细节
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, text
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
    """SQLite 连接级 PRAGMA

    三条各有来由，都对应实测出来的问题：
      foreign_keys=ON  —— MySQL 默认开启，保持两端行为一致
      journal_mode=WAL —— 读写不再互斥。默认 rollback journal 模式下，
                          任何写事务都会锁住整库，并发一上来直接 500
      busy_timeout     —— 拿到锁之前的等待时间。不设的话 SQLite 遇到锁立即报
                          `database is locked`，而不是等一会
    实测（6.1.4）：并发 16 打 100 次问诊，未开 WAL+busy_timeout 时出现 3 次 500；
    开启后 0 次。WAL 只在 SQLite 生效，换 MySQL 不受影响。
    """
    if not settings.database_url.startswith("sqlite"):
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=8000")
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


def _migrate_add_columns() -> None:
    """轻量补列：`create_all` 不会给已存在的表加新列

    开发期迭代加字段时必然遇到（本次 P3 给 consultations 加 rag_citations）。
    正式环境应走 Alembic，这里只是避免"升级后老库直接崩"。
    """
    from sqlalchemy import inspect, text

    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "consultations" not in tables:
            return
        cols = {c["name"] for c in insp.get_columns("consultations")}
        if "rag_citations" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE consultations ADD COLUMN rag_citations TEXT DEFAULT '[]'"
                ))
    except Exception:  # pragma: no cover - 迁移失败不应阻断启动
        pass


# 6.2.2 新增索引（与 entities.py 中的 __table_args__ 保持一致）
# create_all 只建缺失的表，不会给已存在的表补索引，所以这里显式补一次。
_EXTRA_INDEXES: list[tuple[str, str]] = [
    ("ix_consultations_created_at",
     "CREATE INDEX IF NOT EXISTS ix_consultations_created_at "
     "ON consultations (created_at)"),
    ("ix_consultations_user_created",
     "CREATE INDEX IF NOT EXISTS ix_consultations_user_created "
     "ON consultations (user_id, created_at)"),
    ("ix_messages_cid_round",
     "CREATE INDEX IF NOT EXISTS ix_messages_cid_round "
     "ON messages (consultation_id, round_no)"),
    ("ix_safety_logs_created_at",
     "CREATE INDEX IF NOT EXISTS ix_safety_logs_created_at "
     "ON safety_logs (created_at)"),
    ("ix_safety_logs_rule",
     "CREATE INDEX IF NOT EXISTS ix_safety_logs_rule ON safety_logs (rule)"),
]


def _migrate_add_indexes() -> None:
    """给老库补 6.2.2 的索引（幂等，用 IF NOT EXISTS）"""
    from sqlalchemy import inspect

    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        for name, ddl in _EXTRA_INDEXES:
            table = ddl.split(" ON ", 1)[1].split(" ", 1)[0]
            if table not in tables:
                continue
            existing = {i["name"] for i in insp.get_indexes(table)}
            if name in existing:
                continue
            with engine.begin() as conn:
                conn.execute(text(ddl))
    except Exception:  # pragma: no cover - 索引缺失只影响性能，不应阻断启动
        pass


def init_db() -> None:
    """建表（开发期用；正式环境走 Alembic 迁移）"""
    import app.models  # noqa: F401  注册全部模型到 Base.metadata

    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()
    _migrate_add_indexes()
