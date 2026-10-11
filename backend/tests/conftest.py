# -*- coding: utf-8 -*-
"""pytest 公共夹具

测试原则（起步路线.md 六 的「核心模块覆盖」口径）：
  覆盖率数字不是目标，**安全不变量与确定性判定必须测透**。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("LLM_PROVIDER", "mock")     # 测试绝不联网
os.environ.setdefault("LLM_FALLBACK_CHAIN", "mock")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_ROOT / 'tests' / '_test.db'}")
os.environ.setdefault("MONTHLY_BUDGET_CNY", "200")
# LangGraph Checkpointer 也落测试目录，避免污染开发库 /var/app.db
os.environ.setdefault("CHECKPOINT_DB_PATH",
                      str(BACKEND_ROOT / "tests" / "_langgraph_ckpt.sqlite"))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.services import data_loader  # noqa: E402
from app.domain.safety.guard import WhitelistChecker  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    init_db()
    from scripts.import_data import complement_from_whitelist, import_herbs, import_whitelist

    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM herbs"))
        db.execute(text("DELETE FROM food_medicine_whitelist"))
        db.commit()
        import_whitelist(db, False)
        import_herbs(db, False)
        complement_from_whitelist(db)
    finally:
        db.close()
    yield
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def whitelist() -> WhitelistChecker:
    return data_loader.get_whitelist_checker()


@pytest.fixture()
def whitelist_index():
    return data_loader.get_whitelist_index()
