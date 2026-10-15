# -*- coding: utf-8 -*-
"""6.1.4 / 6.2 性能与优化的回归护栏

这些用例不追求"测出性能数字"（数字由 `scripts/bench_api.py` 产出），
而是**锁死两个已被实测证明有效的优化不被改回去**：

  1. SQLite 必须开 WAL + busy_timeout —— 否则并发写直接 500
  2. 常用查询字段必须有索引 —— 否则历史/趋势接口退化为全表扫描

以及一条真实的并发冒烟：多线程同时问诊，不能有 5xx。
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.core.database import engine, init_db
from app.main import app

API = "/api/v1"

YANGXU = {
    "阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5,
    "气虚质_1": 4, "气虚质_2": 3, "气虚质_3": 3,
    "阴虚质_1": 1, "阴虚质_2": 1, "阴虚质_3": 1,
    "痰湿质_1": 1, "痰湿质_2": 1, "痰湿质_3": 1,
    "湿热质_1": 1, "湿热质_2": 1, "湿热质_3": 1,
    "血瘀质_1": 1, "血瘀质_2": 1, "血瘀质_3": 1,
    "气郁质_1": 1, "气郁质_2": 1, "气郁质_3": 1,
    "特禀质_1": 1, "特禀质_2": 1, "特禀质_3": 1,
    "平和质_1": 3, "平和质_2": 3, "平和质_3": 3,
}


def c() -> TestClient:
    return TestClient(app)


class TestSqliteConcurrency:
    """6.2.2 —— 未开 WAL 时并发 16 打 100 次问诊会出现 `database is locked` 500"""

    @pytest.mark.skipif(not os.environ.get("DATABASE_URL", "sqlite").startswith("sqlite"),
                        reason="仅 SQLite 需要 WAL")
    def test_主库开启_WAL(self, db):
        mode = db.execute(text("PRAGMA journal_mode")).scalar()
        assert str(mode).lower() == "wal", f"journal_mode={mode}，未启用 WAL"

    @pytest.mark.skipif(not os.environ.get("DATABASE_URL", "sqlite").startswith("sqlite"),
                        reason="仅 SQLite 需要 busy_timeout")
    def test_写锁等待已设置(self, db):
        timeout = db.execute(text("PRAGMA busy_timeout")).scalar()
        assert int(timeout or 0) >= 1000, f"busy_timeout={timeout}，遇到写锁会立即报错"


class TestIndexes:
    """6.2.2 索引：历史列表与趋势图按 created_at 排序，没有索引就是全表扫描"""

    def test_问诊表有时间索引(self):
        init_db()          # 触发补索引迁移（幂等）
        names = {i["name"] for i in inspect(engine).get_indexes("consultations")}
        assert "ix_consultations_created_at" in names, f"实际索引：{names}"

    def test_消息表有会话轮次复合索引(self):
        init_db()
        names = {i["name"] for i in inspect(engine).get_indexes("messages")}
        assert "ix_messages_cid_round" in names, f"实际索引：{names}"

    def test_安全日志有规则与时间索引(self):
        init_db()
        idx = {i["name"] for i in inspect(engine).get_indexes("safety_logs")}
        assert "ix_safety_logs_rule" in idx, f"实际索引：{idx}"


class TestHotCache:
    """6.2.1 热点数据缓存：必须真的命中，且数据变更后可失效"""

    def test_第二次调用命中缓存(self, db):
        from app.services import herb_service

        herb_service.categories.cache_clear()
        a = herb_service.categories(db)
        b = herb_service.categories(db)
        assert a == b, "缓存返回的结果必须与首次一致"
        st = herb_service.categories.cache_stats()
        assert st["hits"] >= 1, f"第二次调用未命中缓存：{st}"

    def test_Session_不参与缓存键(self, db):
        """★ 防回归：把 Session 算进键会导致命中率恒为 0"""
        from app.core.database import SessionLocal
        from app.services import herb_service

        herb_service.meridians.cache_clear()
        herb_service.meridians(db)
        s2 = SessionLocal()
        try:
            herb_service.meridians(s2)          # 不同的 Session 实例
        finally:
            s2.close()
        st = herb_service.meridians.cache_stats()
        assert st["hits"] >= 1, f"换一个 Session 就没命中，说明 Session 进了缓存键：{st}"

    def test_统一清空生效(self, db):
        from app.core.cache import cache_clear_all
        from app.services import herb_service

        herb_service.categories(db)
        cache_clear_all()
        assert herb_service.categories.cache_stats()["size"] == 0

    def test_缓存接口可观测(self):
        with c() as cl:
            d = cl.get(f"{API}/meta/cache").json()["data"]
            assert isinstance(d, dict)


class TestConcurrentSmoke:
    """真实并发冒烟：多线程同时问诊不得出现 5xx"""

    def test_并发问诊不返回5xx(self):
        n, workers = 12, 6
        payload = {"chief_complaint": "冬天怕冷手脚冰凉，容易累",
                   "questionnaire": YANGXU}
        codes: list[int] = []

        def one(_):
            with c() as cl:
                r = cl.post(f"{API}/consultation/start", json=payload)
                return r.status_code

        with ThreadPoolExecutor(max_workers=workers) as pool:
            codes = list(pool.map(one, range(n)))

        bad = [x for x in codes if x >= 500]
        assert not bad, f"并发下出现服务端错误：{bad}（全部状态码 {codes}）"
        assert len(codes) == n

    def test_并发只读接口不返回5xx(self):
        def one(i):
            with c() as cl:
                return cl.get(f"{API}/herbs", params={"page": (i % 3) + 1}).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(one, range(24)))
        assert all(x < 500 for x in codes), f"只读接口并发报错：{codes}"
