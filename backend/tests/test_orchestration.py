# -*- coding: utf-8 -*-
"""P2 多智能体编排测试（开发步骤清单 3.4 / 3.6）

测试原则：`起步路线.md` 六 —— 覆盖率不是目标，**不变量必须锁死**。
这里锁死的是：
  1. 图结构与论文配图一致（节点/条件边不漂移）
  2. 路由函数是纯函数（同状态必同结果）
  3. 追问轮次有上界（曾经因为 rounds 不递增而无限追问）
  4. 安全性：急症必拦、交叉复核必剔黑名单
  5. 架构约束：domain 层不许碰 LangGraph
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.constitution.questionnaire import QUESTIONNAIRE
from app.domain.safety import guard as sg
from app.main import app
from app.orchestration import graph as og
from app.orchestration.edges import (
    ROUTE_COLLECT,
    ROUTE_CONSTITUTION,
    ROUTE_SAFETY,
    route_after_collect,
    route_after_constitution,
    route_after_safety,
)
from app.orchestration.nodes import (
    NODE_LABELS,
    collect_symptoms_node,
    safety_check_node,
)
from app.orchestration.state import (
    FINAL_NODE,
    MAX_FOLLOWUP_ROUNDS,
    ConsultationState,
    merge_answers,
    merge_unique,
    new_state,
)


def client():
    return TestClient(app)


def full_questionnaire(top: str = "阳虚质", high: int = 5, low: int = 1) -> dict:
    """九维度全答 questionnaire（top 维度打高分，其余低分）"""
    q: dict[str, int] = {}
    for dim in QUESTIONNAIRE:
        score = high if dim == top else low
        for item in QUESTIONNAIRE[dim].questions:
            q[item.id] = score
    return q


# ===========================================================================
# 一、归约器
# ===========================================================================


class TestReducers:
    def test_答案合并取高分(self):
        assert merge_answers({"气虚质_1": 3}, {"气虚质_1": 5}) == {"气虚质_1": 5}
        assert merge_answers({"气虚质_1": 5}, {"气虚质_1": 3}) == {"气虚质_1": 5}

    def test_答案合并不丢旧键(self):
        assert merge_answers({"气虚质_1": 4}, {"阳虚质_1": 5}) == {
            "气虚质_1": 4, "阳虚质_1": 5
        }

    def test_去重保序合并(self):
        assert merge_unique(["孕妇"], ["孕妇", "儿童"]) == ["孕妇", "儿童"]
        assert merge_unique(["儿童"], ["孕妇"]) == ["儿童", "孕妇"]

    def test_空输入不炸(self):
        assert merge_answers({}, None) == {}
        assert merge_unique([], None) == []


# ===========================================================================
# 二、路由纯函数
# ===========================================================================


class TestRouting:
    def test_急症命中直接中止(self):
        assert route_after_collect({"blocked": True}) == "safety_abort"

    def test_未命中进入判定节点(self):
        assert route_after_collect({"blocked": False}) == "diagnose"

    def test_信息不足且轮次未满走追问(self):
        assert route_after_constitution(
            {"constitution": {"needs_follow_up": True}, "follow_up_rounds": 0}
        ) == "follow_up"

    def test_轮次用尽不再追问(self):
        """这是曾经的真实缺陷：rounds 不递增导致无限追问"""
        assert route_after_constitution(
            {"constitution": {"needs_follow_up": True},
             "follow_up_rounds": MAX_FOLLOWUP_ROUNDS}
        ) == "match"

    def test_信息充足直接匹配(self):
        assert route_after_constitution(
            {"constitution": {"needs_follow_up": False}, "follow_up_rounds": 0}
        ) == "match"

    def test_候选不足且未用尽重配次数则重配(self):
        assert route_after_safety({"herbs": {"candidates": []}, "safety_recheck": 0}) == "recheck"

    def test_重配次数用尽则出结果_防死循环(self):
        assert route_after_safety(
            {"herbs": {"candidates": []}, "safety_recheck": 2}
        ) == "present"

    def test_输出侧阻断走中止(self):
        assert route_after_safety({"blocked": True}) == "abort"

    def test_开启药膳开关走Agent3(self):
        assert route_after_safety(
            {"herbs": {"candidates": [{"name": "山药"}, {"name": "茯苓"}]},
             "enable_recipe": True}
        ) == "recipe"

    def test_路由表与图上的目标节点一致(self):
        """防止改了路由表忘记改图，造成「图上画的」与「实际跑的」不一致"""
        names = set(og._node_funcs())
        for mapping in (ROUTE_COLLECT, ROUTE_CONSTITUTION, ROUTE_SAFETY):
            for target in mapping.values():
                target_node = "herb_match" if target == "match" else target
                assert target_node in names or target_node == "recheck_counter"


# ===========================================================================
# 三、图结构（论文配图 = 代码导出，不允许手写漂移）
# ===========================================================================


class TestGraphStructure:
    def test_七个业务节点齐全(self):
        funcs = og._node_funcs()
        for n in ("collect_symptoms", "constitution_engine", "follow_up",
                  "herb_match", "safety_check", "food_recipe", "present",
                  "safety_abort", "recheck_counter"):
            assert n in funcs, f"缺节点 {n}"

    def test_每个节点都有中文标签(self):
        for n in og._node_funcs():
            assert NODE_LABELS.get(n), f"节点 {n} 缺中文标签"

    def test_mermaid包含关键分支(self):
        m = og.mermaid()
        assert m.startswith("stateDiagram-v2")
        for kw in ("collect_symptoms", "constitution_engine", "herb_match",
                   "safety_check", "present", "follow_up"):
            assert kw in m
        assert "106白名单" in m.replace(" ", "")

    def test_编译产物可导出自身结构(self):
        """LangGraph 自导出的图能过 __interrupt__ 之外的编译校验"""
        if not og.LANGGRAPH_AVAILABLE:
            pytest.skip("未安装 langgraph")
        m = og.langgraph_mermaid()
        assert "collect_symptoms" in m

    def test_graph_structure_json(self):
        s = og.graph_structure()
        assert s["engine"] == "langgraph"
        ids = {n["id"] for n in s["nodes"]}
        assert {"collect_symptoms", "safety_check", "END"} <= ids
        assert any(c["from"] == "safety_check" for c in s["conditional_edges"])


# ===========================================================================
# 四、单个节点
# ===========================================================================


class TestNodes:
    def test_采集节点_从自由文本抽取并识别人群(self):
        st = new_state("s1", user_input="我怀着孕，最近手脚冰凉还很累")
        patch = collect_symptoms_node(st)
        assert patch["questionnaire"]["阳虚质_1"] == 5      # 手脚冰凉
        assert patch["questionnaire"]["气虚质_1"] >= 4      # 很累
        assert "孕妇" in patch["special_groups"]
        assert patch["missing_dimensions"]

    def test_采集节点_急症输入被标记(self):
        st = new_state("s2", user_input="胸痛持续不缓解，呼吸困难")
        patch = collect_symptoms_node(st)
        assert patch["blocked"] is True
        assert patch["block_kind"] == "emergency"

    def test_交叉复核剔除黑名单(self):
        """herb_match 内部查过一次；这里是终态前的第二次复核"""
        st = ConsultationState(
            session_id="s3", follow_up_rounds=0, safety_recheck=0,
            special_groups=[], questionnaire={},
            herbs={"candidates": [
                {"name": "山药", "special_groups": [], "dosage": "15g"},
                {"name": "附子", "special_groups": [], "dosage": ""},   # 黑名单
                {"name": "党参", "special_groups": [], "dosage": "9g"},
            ]},
            herb_explanation="建议遵医嘱服用",
        )
        patch = safety_check_node(st)
        kept = [c["name"] for c in patch["herbs"]["candidates"]]
        assert "附子" not in kept, "黑名单药材必须被交叉复核拦下"
        assert "山药" in kept
        assert patch["herbs"]["cross_checked"] is True
        assert patch["safety_flags"], "剔除行为必须留痕"

    def test_交叉复核处理特殊人群禁忌(self):
        st = ConsultationState(
            session_id="s4", follow_up_rounds=0, safety_recheck=0,
            special_groups=["孕妇"], questionnaire={}, herbs={"candidates": [
                {"name": "山药", "special_groups": [], "dosage": ""},
                {"name": "当归", "special_groups": ["孕妇"], "dosage": ""},
                {"name": "党参", "special_groups": [], "dosage": ""},
            ]},
            herb_explanation="")
        patch = safety_check_node(st)
        kept = [c["name"] for c in patch["herbs"]["candidates"]]
        assert "当归" not in kept, "与孕妇禁忌冲突的药材必须剔除"

    def test_输出侧注入免责声明(self):
        st = ConsultationState(
            session_id="s5", follow_up_rounds=0, safety_recheck=0,
            special_groups=[], questionnaire={},
            herbs={"candidates": [
                {"name": "山药", "special_groups": []},
                {"name": "党参", "special_groups": []},
            ]},
            herb_explanation="山药健脾，党参补气")
        patch = safety_check_node(st)
        assert sg.DISCLAIMER in patch["interpretation"], "结论必须带免责声明"


# ===========================================================================
# 五、端到端闭环
# ===========================================================================


class TestGraphFlow:
    def test_完整问卷一次性完成(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "chief_complaint": "我怕冷手脚冰凉",
                "questionnaire": full_questionnaire("阳虚质"),
            })
            assert r.status_code == 200
            d = r.json()["data"]
            assert d["phase"] == "completed"
            trace = [t["node"] for t in d["trace"]]
            assert trace == [
                "collect_symptoms", "constitution_engine",
                "herb_match", "safety_check", "present",
            ]
            assert d["constitution"]["primary"] == "阳虚质"
            assert d["recommend"]["cross_checked"] is True
            assert len(d["recommend"]["herbs"]) > 0

    def test_推荐药材全部在白名单(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "questionnaire": full_questionnaire("气虚质")})
            herbs = r.json()["data"]["recommend"]["herbs"]
            for h in herbs:
                assert not sg.is_blacklisted(h["name"])
                assert h["in_whitelist"] is True

    def test_追问最多两轮后必出结论(self):
        """回归：曾经 follow_up_rounds 不递增，导致永远停在追问"""
        with client() as c:
            r = c.post("/api/v1/consultation/start",
                       json={"chief_complaint": "我最近总感觉累"})
            d = r.json()["data"]
            assert d["phase"] == "follow_up"
            cid = d["consultation_id"]

            r = c.post(f"/api/v1/consultation/{cid}/answer", json={"answer": "大便偏稀"})
            d2 = r.json()["data"]
            assert d2["follow_up_round"] == 2 or d2["phase"] == "completed"

            r = c.post(f"/api/v1/consultation/{cid}/answer", json={"answer": "还怕冷"})
            d3 = r.json()["data"]
            assert d3["phase"] == "completed", "第 3 次交互必须出结果，不得再追问"
            assert d3["recommend"] is not None

    def test_急症拦截并落阻断状态(self):
        with client() as c:
            r = c.post("/api/v1/consultation/start",
                       json={"chief_complaint": "胸痛呼吸困难持续不缓解"})
            assert r.json()["code"] == 40301
            cid = r.json()["data"]["consultation_id"]
            detail = c.get(f"/api/v1/consultation/{cid}").json()["data"]
            assert detail["status"] == "blocked_emergency"
            # 阻断后不能再回答
            r = c.post(f"/api/v1/consultation/{cid}/answer", json={"answer": "还好"})
            assert r.json()["code"] == 40301

    def test_同一会话信息不丢失(self):
        """3.6.3 会话恢复：问卷快照每轮同步落库"""
        with client() as c:
            r = c.post("/api/v1/consultation/start", json={
                "questionnaire": {"阳虚质_1": 5, "阳虚质_2": 5}})
            d = r.json()["data"]
            if d["phase"] == "follow_up":
                cid = d["consultation_id"]
                c.post(f"/api/v1/consultation/{cid}/answer", json={"answer": "还怕冷"})
                det = c.get(f"/api/v1/consultation/{cid}").json()["data"]
                assert det["questionnaire"]["阳虚质_1"] == 5
                assert det["questionnaire"]["阳虚质_2"] == 5


# ===========================================================================
# 六、SSE 与可视化端点
# ===========================================================================


class TestStreamAndGraphAPI:
    def test_图结构端点(self):
        with client() as c:
            r = c.get("/api/v1/consultation/graph")
            assert r.status_code == 200
            assert r.json()["data"]["engine"] == "langgraph"

    def test_图结构端点返回mermaid(self):
        with client() as c:
            r = c.get("/api/v1/consultation/graph", params={"format": "mermaid"})
            assert r.status_code == 200
            assert "stateDiagram-v2" in r.json()["data"]["mermaid"]

    def test_SSE_推送节点级事件(self):
        with client() as c:
            r = c.post("/api/v1/consultation/stream", json={
                "questionnaire": full_questionnaire("阳虚质")})
            assert r.status_code == 200
            body = r.text
            events = [ln.replace("event: ", "").strip()
                      for ln in body.splitlines() if ln.startswith("event:")]
            assert "node" in events
            assert events[-1] == "done"
            assert "collect_symptoms" in body and "safety_check" in body

    def test_SSE_急症返回error事件(self):
        with client() as c:
            r = c.post("/api/v1/consultation/stream",
                       json={"chief_complaint": "突发剧烈胸痛伴大汗"})
            assert r.status_code == 200
            assert "event: error" in r.text

    def test_图stream产出终态哨兵(self):
        """stream 以 FINAL_NODE 收尾，service 层无需自己合并 patch"""
        st = new_state("direct-stream", questionnaire=full_questionnaire("阳虚质"))
        final = None
        for node_name, patch in og.stream(st, thread_id="direct-stream"):
            if node_name == FINAL_NODE:
                final = patch
        assert final is not None, "stream 必须产出 FINAL_NODE 终态"
        assert final.get("completed") is True
        assert final["herbs"]["cross_checked"] is True


# ===========================================================================
# 七、架构适应度函数
# ===========================================================================


def forbidden_imports(root: Path, package: str) -> list[str]:
    """AST 级依赖检查：只看真实 import，注释/文档字符串里提到不算"""
    hits: list[str] = []
    for p in root.rglob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.Import):
                mod = ",".join(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            if mod and mod.split(".")[0] == package:
                hits.append(f"{p}:{getattr(node, 'lineno', 0)} {mod}")
    return sorted(hits)


class TestArchitectureFitness:
    def test_领域层零框架依赖(self):
        """系统架构设计 3.4 铁律：domain 不许碰 LangGraph / SQLAlchemy / FastAPI"""
        domain = Path(__file__).resolve().parent.parent / "app" / "domain"
        for pkg in ("langgraph", "sqlalchemy", "fastapi", "openai", "langchain"):
            assert not forbidden_imports(domain, pkg), \
                f"domain 层禁止 import {pkg}：{forbidden_imports(domain, pkg)}"

    def test_service层不手写流水线(self):
        """业务逻辑必须写在图里，service 只允许调用 runner"""
        svc = (Path(__file__).resolve().parent.parent / "app" / "services"
               / "consultation_service.py").read_text(encoding="utf-8")
        assert "run_consultation(" in svc
        # service 不得再直接调用 match_herbs / ce.score —— 那是节点的活
        assert "hm.match_herbs(" not in svc
        assert "ce.score(" not in svc

    def test_编排层不碰数据库(self):
        """编排层只推进状态，落库是 service 的活"""
        orch = Path(__file__).resolve().parent.parent / "app" / "orchestration"
        for pkg in ("sqlalchemy", "fastapi"):
            assert not forbidden_imports(orch, pkg), \
                f"编排层禁止依赖 {pkg}：{forbidden_imports(orch, pkg)}"

    def test_编排层不反向依赖service(self):
        """允许 services.data_loader（纯数据读取），禁止 consultation_service

        后者会造成 services.__init__ → consultation_service → orchestration 的循环。
        """
        # 自检：helper 本身不能把任意包判成违规
        assert forbidden_imports(
            Path(__file__).resolve().parent.parent / "app" / "orchestration",
            "nonexistent_pkg_xyz",
        ) == []
        orch = Path(__file__).resolve().parent.parent / "app" / "orchestration"
        bad: list[str] = []
        for p in orch.rglob("*.py"):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                    "consultation_service"
                ):
                    bad.append(f"{p}:{node.lineno}")
        assert not bad, f"编排层禁止 import consultation_service：{bad}"
