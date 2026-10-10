# -*- coding: utf-8 -*-
"""API 集成测试 —— 与 SQLAlchemy fixtures 协作

覆盖：药材接口（正/反两面）、安全自检接口、历史与趋势。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def get_client():
    return TestClient(app)


class TestHerbsAPI:

    def test_列表分页(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs", params={"page": 1, "size": 10})
            assert r.status_code == 200
            body = r.json()
            assert body["code"] == 0
            assert len(body["data"]["items"]) == 10
            assert body["data"]["total"] > 600

    def test_分类别筛选(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs", params={"category": "补虚药", "size": 5})
            items = r.json()["data"]["items"]
            assert items
            assert all(i["category"] == "补虚药" for i in items)

    def test_只看药食同源(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs", params={"only_food_medicine": "true", "size": 20})
            items = r.json()["data"]["items"]
            assert items
            assert all(i["is_food_medicine"] for i in items)

    def test_搜毒剧药材_查得到但禁用于药膳(self):
        """★ P0 验收：818/626 查询层的两面性"""
        with get_client() as c:
            r = c.get("/api/v1/herbs/search", params={"q": "附子"})
            assert r.status_code == 200
            item = r.json()["data"][0]
            assert "附子" in item["name"]
            assert item["is_food_medicine"] is False
            assert item["is_blacklisted"] is True
            assert "不得进入药膳方案" in item["usage_policy"]

    def test_搜白名单药材_标记可用于药膳(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs/search", params={"q": "黄芪"})
            item = r.json()["data"][0]
            assert item["is_food_medicine"] is True

    def test_搜索无结果返回业务404(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs/search", params={"q": "不存在的药材XYZ"})
            assert r.status_code == 404
            assert r.json()["code"] == 404

    def test_详情接口(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs/1")
            assert r.status_code == 200
            assert r.json()["data"]["name"]

    def test_详情不存在(self):
        with get_client() as c:
            r = c.get("/api/v1/herbs/999999")
            assert r.json()["code"] == 404

    def test_类别与归经统计(self):
        with get_client() as c:
            cats = c.get("/api/v1/herbs/categories").json()["data"]
            mer = c.get("/api/v1/herbs/meridians").json()["data"]
            assert cats and mer
            assert cats[0]["count"] > 0


class TestSafetyAPI:

    def test_附子被拒_黄芪放行(self):
        with get_client() as c:
            r = c.post("/api/v1/safety/probe-herbs",
                       json={"herb_names": ["附子", "黄芪", "山药"]})
            data = r.json()["data"]
            assert "附子" not in data["passed"]
            assert "黄芪" in data["passed"]

    def test_规则摘要可读(self):
        with get_client() as c:
            d = c.get("/api/v1/safety/rules").json()["data"]
            assert d["whitelist_count"] == 106
            assert d["blacklist_count"] > 30

    def test_输出术语过滤接口(self):
        with get_client() as c:
            r = c.post("/api/v1/safety/probe-output",
                       json={"text": "这个方子可以治疗胃病，保证有效"})
            clean = r.json()["data"]["clean"]
            assert "治疗" not in clean
            assert "保证有效" not in clean


class TestMetaAPI:

    def test_双层数据概况(self):
        with get_client() as c:
            d = c.get("/api/v1/meta/dataset").json()["data"]
            assert d["recommendation_layer"]["count"] == 106
            assert d["query_layer"]["raw_records"] == 828
            assert d["query_layer"]["unique_herbs"] == 604

    def test_问卷结构完整版与快速版(self):
        with get_client() as c:
            full = c.get("/api/v1/meta/questionnaire").json()["data"]
            quick = c.get("/api/v1/meta/questionnaire", params={"mode": "quick"}).json()["data"]
            assert full["total_questions"] == 27
            assert quick["total_questions"] == 9

    def test_九种体质(self):
        with get_client() as c:
            d = c.get("/api/v1/meta/constitutions").json()["data"]
            assert len(d) == 9
            assert "平和质" in d
