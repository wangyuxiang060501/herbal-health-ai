# -*- coding: utf-8 -*-
"""问诊闭环集成测试（P1）

注意：测试环境 LLM_PROVIDER=mock，全程离线，不依赖 Ollama 是否启动。
正因为 Agent 编排做到了 provider 解耦，这条测试才能在任何机器上跑通。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def client():
    return TestClient(app)


FULL_YANGXU = {
    "阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5,
    "气虚质_1": 2, "气虚质_2": 2, "气虚质_3": 2,
    "阴虚质_1": 1, "阴虚质_2": 1, "阴虚质_3": 1,
    "痰湿质_1": 1, "痰湿质_2": 1, "痰湿质_3": 1,
    "湿热质_1": 1, "湿热质_2": 1, "湿热质_3": 1,
    "血瘀质_1": 1, "血瘀质_2": 1, "血瘀质_3": 1,
    "气郁质_1": 1, "气郁质_2": 1, "气郁质_3": 1,
    "特禀质_1": 1, "特禀质_2": 1, "特禀质_3": 1,
    "平和质_1": 3, "平和质_2": 3, "平和质_3": 3,
}


class TestEmergencyBlocking:

    def test_急症描述终止问诊(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start",
                       json={"chief_complaint": "我最近胸痛，呼吸困难"})
            assert r.status_code == 200          # 业务语义，不是 HTTP 错误
            body = r.json()
            assert body["code"] == 40301
            assert "120" in body["message"]

    def test_急症询问已入库留痕(self):
        with client() as c:
            c.post("/api/v1/consultation/start", json={"chief_complaint": "咳血了"})
            history = c.get("/api/v1/user/history").json()["data"]
            assert any(h["status"] == "blocked_emergency" for h in history)


class TestClosedLoop:

    def test_完整问卷一次成工出结论(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "怕冷手脚冰凉，容易累",
                "questionnaire": FULL_YANGXU,
            })
            body = r.json()
            assert body["code"] == 0
            d = body["data"]
            assert d["phase"] == "completed"
            assert d["constitution"]["primary"] == "阳虚质"
            assert d["constitution"]["deterministic"] is True
            assert 0 < len(d["recommend"]["herbs"]) <= 6
            # 推荐必须全部是白名单成员
            for h in d["recommend"]["herbs"]:
                assert h["in_whitelist"] is True
            # 免责声明必须在
            assert "免责声明" in d["interpretation"] or "免责" in d["interpretation"]

    def test_信息不足进入追问_答完后闭环(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "我最近容易累，还怕冷",
                "questionnaire": {"阳虚质_1": 5, "气虚质_1": 4},
            })
            d = r.json()["data"]
            assert d["phase"] == "follow_up"
            assert d["follow_up_round"] == 1
            assert 1 <= len(d["follow_up_questions"]) <= 3
            assert d["follow_up_source"].startswith(("llm", "template"))

            cid = d["consultation_id"]
            r2 = c.post(f"/api/v1/consultation/{cid}/answer",
                        json={"answer": "大便偏稀不太成型，吃一点就饱，经常胀气"})
            d2 = r2.json()["data"]
            assert d2["phase"] in ("follow_up", "completed")
            # 最多两轮追问，之后必须收敛出结论
            if d2["phase"] == "follow_up":
                assert d2["follow_up_round"] == 2
                r3 = c.post(f"/api/v1/consultation/{cid}/answer",
                            json={"answer": "好的，没有其他不舒服"})
                assert r3.json()["data"]["phase"] == "completed"

    def test_特殊人群标记被识别并生效(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "我怀孕三个月了，最近总没力气",
                "questionnaire": FULL_YANGXU,
            })
            d = r.json()["data"]
            assert "孕妇" in d["special_groups"]

    def test_特殊人群下推荐不含禁用品种(self):
        with client() as c:
            blood = {
                "血瘀质_1": 5, "血瘀质_2": 5, "血瘀质_3": 5,
                "气虚质_1": 2, "气虚质_2": 1, "气虚质_3": 1,
                "阳虚质_1": 2, "阳虚质_2": 1, "阳虚质_3": 1,
                "阴虚质_1": 2, "阴虚质_2": 1, "阴虚质_3": 1,
                "痰湿质_1": 2, "痰湿质_2": 1, "痰湿质_3": 1,
                "湿热质_1": 1, "湿热质_2": 1, "湿热质_3": 1,
                "气郁质_1": 2, "气郁质_2": 1, "气郁质_3": 1,
                "特禀质_1": 1, "特禀质_2": 1, "特禀质_3": 1,
                "平和质_1": 3, "平和质_2": 3, "平和质_3": 3,
            }
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "皮肤容易青紫",
                "questionnaire": blood,
                "special_groups": ["孕妇"],
            })
            herbs = [h["name"] for h in r.json()["data"]["recommend"]["herbs"]]
            assert "桃仁" not in herbs      # 孕妇禁用
            assert "西红花" not in herbs
            assert "当归" not in herbs

    def test_问诊详情可回看(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "怕冷怕凉",
                "questionnaire": FULL_YANGXU,
            })
            cid = r.json()["data"]["consultation_id"]
            detail = c.get(f"/api/v1/consultation/{cid}").json()["data"]
            assert detail["id"] == cid
            assert detail["status"] == "completed"
            assert detail["messages"], "对话记录必须落库"

    def test_不存在的问诊返回404(self):
        with client() as c:
            r = c.get("/api/v1/consultation/not-exist-id")
            assert r.json()["code"] == 404

    def test_趋势数据可用(self):
        with client() as c:
            c.post("/api/v1/consultation/start", json={
                "chief_complaint": "怕冷", "questionnaire": FULL_YANGXU,
            })
            trend = c.get("/api/v1/user/trend").json()["data"]
            assert trend
            assert len(trend[-1]["scores"]) == 9      # 九维齐全


class TestSSE:

    def test_流式输出事件序列(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "怕冷", "questionnaire": FULL_YANGXU,
            })
            cid = r.json()["data"]["consultation_id"]
            with c.stream(
                "GET", f"/api/v1/consultation/{cid}/stream", params={"phase": "recommend"}
            ) as resp:
                text = resp.read()
            assert b"event: meta" in text
            assert b"event: delta" in text
            assert b"event: done" in text
