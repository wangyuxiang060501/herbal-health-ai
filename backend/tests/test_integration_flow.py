# -*- coding: utf-8 -*-
"""6.1.2 API 集成测试 —— 完整业务流程

与单测的区别：这里**只走 HTTP**，从 `/api/v1/meta` 一路打到 `/consultation/{id}`，
验证的是「各层装配起来之后还对不对」，而不是某个函数的返回值。

刻意覆盖的三条主线：
  A. 主链路：问卷 → 判定 → 推荐 → 药膳 → 历史 → 详情
  B. 异常分支：急症截断、追问轮次、不存在的 id
  C. 数据一致性：列表页与详情页对同一味药材的说法必须自洽
"""
from __future__ import annotations

from fastapi.testclient import TestClient

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


class TestMetaAndHerbChain:
    """元数据 → 药材库：查询层的读路径"""

    def test_数据集概况与药材列表口径一致(self):
        """概况里的「唯一药材数」必须等于列表接口实际能查到的条数"""
        with c() as cl:
            meta = cl.get(f"{API}/meta/dataset").json()["data"]
            lst = cl.get(f"{API}/herbs?size=1").json()["data"]
            expect = meta["query_layer"]["unique_herbs"]
            # 列表是「唯一药材 + 白名单补齐」后的入库总量
            assert lst["total"] >= expect
            assert lst["total"] == expect + len(meta["query_layer"]["whitelist_complement"])

    def test_搜索结果可被详情接口逐条打开(self):
        with c() as cl:
            hits = cl.get(f"{API}/herbs/search?q=黄芪").json()["data"]
            assert hits, "搜索「黄芪」不应为空"
            for h in hits[:3]:
                d = cl.get(f"{API}/herbs/{h['id']}").json()["data"]
                assert d["name"] == h["name"]
                # 详情页必须带 usage_policy，这是「可查」与「可荐」的分水岭
                assert "usage_policy" in d

    def test_类别与归经筛选都不返回空(self):
        with c() as cl:
            cats = cl.get(f"{API}/herbs/categories").json()["data"]
            assert cats
            r = cl.get(f"{API}/herbs?category={cats[0]['name']}&size=5").json()["data"]
            assert r["items"]


class TestMainFlow:
    """A. 主链路端到端"""

    def test_问卷到结果到药膳到历史(self):
        with c() as cl:
            # 1) 问诊
            r = cl.post(f"{API}/consultation/start", json={
                "chief_complaint": "冬天怕冷手脚冰凉，容易累",
                "questionnaire": YANGXU,
            })
            assert r.status_code == 200
            body = r.json()
            assert body["code"] == 0, body.get("message")
            cid = body["data"]["consultation_id"]

            # 2) 详情：判定 + 推荐 + 免责声明都在
            d = cl.get(f"{API}/consultation/{cid}").json()["data"]
            assert d["constitution"]["primary"] == "阳虚质"
            assert d["disclaimer"], "免责声明不可缺失"
            assert d["recommend"]["herbs"], "应产出推荐"

            # 3) 推荐药材必须全部在 106 白名单内（红线，HTTP 层再兜一次）
            names = [h["name"] for h in d["recommend"]["herbs"]]
            probe = cl.post(f"{API}/safety/probe-herbs",
                            json={"herb_names": names}).json()["data"]
            assert set(probe["passed"]) == set(names), (
                f"推荐里混入了不可入膳品种：{set(names) - set(probe['passed'])}")

            # 4) 历史里能找到这条
            hist = cl.get(f"{API}/consultation/user/history?limit=20").json()["data"]
            ids = [x.get("id") or x.get("consultation_id") for x in hist]
            assert cid in ids, "问诊应出现在历史列表"

            # 5) 趋势接口可用
            trend = cl.get(f"{API}/consultation/user/trend").json()["data"]
            assert isinstance(trend, (list, dict))

    def test_结果页带回_RAG_引用(self):
        """P3：引用回溯必须在 HTTP 层可见，而不只是进程内 state 里有"""
        with c() as cl:
            r = cl.post(f"{API}/consultation/start", json={
                "chief_complaint": "怕冷手脚冰凉",
                "questionnaire": YANGXU,
            }).json()["data"]
            d = cl.get(f"{API}/consultation/{r['consultation_id']}").json()["data"]
            assert "rag_citations" in d, "详情接口必须暴露 rag_citations"
            # 知识库可用时应有引用；不可用时至少字段存在且不炸
            if d.get("rag_citations"):
                assert {"chunk_id", "title"} <= set(d["rag_citations"][0])

    def test_状态图可导出_mermaid(self):
        with c() as cl:
            r = cl.get(f"{API}/consultation/graph?format=mermaid")
            assert r.status_code == 200
            assert "stateDiagram" in r.json()["data"]["mermaid"]


class TestBranchAndError:
    """B. 异常分支"""

    def test_急症输入被截断且不产出推荐(self):
        with c() as cl:
            r = cl.post(f"{API}/consultation/start",
                        json={"chief_complaint": "突然胸痛，喘不上气"})
            assert r.json()["code"] == 40301
            assert not r.json()["data"].get("recommend", {}).get("herbs")

    def test_信息不足先追问而不是硬判(self):
        with c() as cl:
            r = cl.post(f"{API}/consultation/start", json={
                "chief_complaint": "有点累",
                "questionnaire": {"阳虚质_1": 5, "气虚质_1": 4},
            }).json()["data"]
            assert r["phase"] == "follow_up"
            assert r["follow_up_questions"], "追问必须有具体问题"

    def test_不存在的问诊_id_返回404而不是500(self):
        with c() as cl:
            r = cl.get(f"{API}/consultation/not-a-real-id")
            assert r.status_code in (200, 404)
            if r.status_code == 200:
                assert r.json()["code"] == 404

    def test_参数非法时返回4xx而不是崩溃(self):
        with c() as cl:
            for bad in [{"chief_complaint": ""}, {"questionnaire": "not-a-dict"}]:
                r = cl.post(f"{API}/consultation/start", json=bad)
                assert r.status_code in (200, 400, 422), f"{bad} 导致异常状态码"


class TestRagEndpoints:
    """P3 检索接口在 HTTP 层可用"""

    def test_status_返回可观测信息(self):
        with c() as cl:
            d = cl.get(f"{API}/rag/status").json()["data"]
            assert "enabled" in d and "top_k" in d

    def test_search_对口语查询有召回(self):
        with c() as cl:
            d = cl.get(f"{API}/rag/search?q=怕冷手脚冰凉").json()["data"]
            assert d["hits"], "口语查询不应零召回"

    def test_explain_给出两路通道对比(self):
        with c() as cl:
            d = cl.get(f"{API}/rag/explain?q=晚上睡不着").json()["data"]
            assert {"semantic", "keyword", "fused"} <= set(d), d
