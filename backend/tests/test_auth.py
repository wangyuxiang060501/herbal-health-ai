# -*- coding: utf-8 -*-
"""5.4.1 用户认证测试 —— 注册 / 登录 / JWT 刷新 / 数据隔离

测试口径与既有集成测试一致：只走 HTTP（TestClient）。
关键不变量：
  A. 口令绝不落明文、绝不回显；
  B. access / refresh 令牌分工明确，不可混用；
  C. 登录用户的历史互相隔离，匿名模式行为与认证上线前完全一致（向后兼容）。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

API = "/api/v1"


def c() -> TestClient:
    return TestClient(app)


def _phone() -> str:
    """每个用例独立手机号，避免唯一约束串扰（测试库是全会话共享的）"""
    # 注意必须是 11 位纯数字：uuid.hex 含 a-f，直接 int() 会得出 10-15 两位数
    return "139" + "".join(str(int(ch, 16) % 10) for ch in uuid.uuid4().hex[:8])


def _register(cl: TestClient, phone: str, password: str = "secret66", nickname: str = "甲"):
    r = cl.post(f"{API}/auth/register",
                json={"phone": phone, "password": password, "nickname": nickname})
    assert r.status_code == 200 and r.json()["code"] == 0, r.json()
    return r.json()["data"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestRegister:
    def test_注册成功返回令牌对与资料(self):
        with c() as cl:
            data = _register(cl, _phone())
            assert data["access_token"] and data["refresh_token"]
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0
            assert data["user"]["nickname"] == "甲"
            # 口令绝不回显
            assert "password" not in str(data).lower()

    def test_重复手机号拒绝注册(self):
        with c() as cl:
            phone = _phone()
            _register(cl, phone)
            r = cl.post(f"{API}/auth/register",
                        json={"phone": phone, "password": "secret66"})
            assert r.json()["code"] == 400
            assert "已注册" in r.json()["message"]

    def test_非法手机号与过短密码被参数校验拦截(self):
        with c() as cl:
            r1 = cl.post(f"{API}/auth/register",
                         json={"phone": "12345", "password": "secret66"})
            assert r1.status_code == 422
            r2 = cl.post(f"{API}/auth/register",
                         json={"phone": _phone(), "password": "123"})
            assert r2.status_code == 422


class TestLogin:
    def test_登录成功(self):
        with c() as cl:
            phone = _phone()
            _register(cl, phone)
            r = cl.post(f"{API}/auth/login", json={"phone": phone, "password": "secret66"})
            assert r.json()["code"] == 0
            assert r.json()["data"]["access_token"]

    def test_密码错误统一话术_不暴露手机号是否存在(self):
        with c() as cl:
            phone = _phone()
            _register(cl, phone)
            r1 = cl.post(f"{API}/auth/login", json={"phone": phone, "password": "bad-pass"})
            r2 = cl.post(f"{API}/auth/login", json={"phone": _phone(), "password": "bad-pass"})
            # 「号不存在」与「密码错」必须返回**完全相同**的响应（防枚举）
            assert r1.status_code == r2.status_code == 401
            assert r1.json()["message"] == r2.json()["message"]

    def test_口令只存散列(self, db):
        from sqlalchemy import select

        from app.models.entities import User
        with c() as cl:
            phone = _phone()
            _register(cl, phone, password="secret66")
        user = db.scalar(select(User).where(User.phone == phone))
        assert user.password_hash.startswith("$2")  # bcrypt 标识
        assert "secret66" not in user.password_hash


class TestToken:
    def test_无令牌访问资料接口_401(self):
        with c() as cl:
            r = cl.get(f"{API}/auth/profile")
            assert r.status_code == 401

    def test_过期令牌_401(self):
        from datetime import timedelta

        import jwt as pyjwt

        from app.core.config import settings
        with c() as cl:
            data = _register(cl, _phone())
            uid = data["user"]["id"]
            secret = settings.jwt_secret_key or settings.app_secret_key
            expired = pyjwt.encode(
                {"sub": str(uid), "typ": "access",
                 "iat": __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - timedelta(hours=3),
                 "exp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - timedelta(hours=1)},
                secret, algorithm=settings.jwt_algorithm,
            )
            r = cl.get(f"{API}/auth/profile", headers=_auth(expired))
            assert r.status_code == 401

    def test_篡改令牌_401(self):
        with c() as cl:
            data = _register(cl, _phone())
            forged = data["access_token"][:-4] + "AAAA"
            r = cl.get(f"{API}/auth/profile", headers=_auth(forged))
            assert r.status_code == 401

    def test_refresh令牌不能访问业务接口(self):
        with c() as cl:
            data = _register(cl, _phone())
            r = cl.get(f"{API}/auth/profile", headers=_auth(data["refresh_token"]))
            assert r.status_code == 401

    def test_刷新旋转出新令牌对且可用(self):
        with c() as cl:
            data = _register(cl, _phone())
            r = cl.post(f"{API}/auth/refresh",
                        json={"refresh_token": data["refresh_token"]})
            assert r.json()["code"] == 0
            new = r.json()["data"]
            assert new["access_token"] != data["access_token"]
            p = cl.get(f"{API}/auth/profile", headers=_auth(new["access_token"]))
            assert p.status_code == 200


class TestHistoryIsolation:
    """5.4.1 联调核心：登录后问诊归属个人，历史/趋势互相隔离"""

    YANGXU = {f"阳虚质_{i}": 5 for i in (1, 2, 3)} | {
        f"{t}_{i}": 1
        for t in ("阴虚质", "痰湿质", "湿热质", "血瘀质", "气郁质", "特禀质")
        for i in (1, 2, 3)
    } | {f"气虚质_{i}": 3 for i in (1, 2, 3)} | {f"平和质_{i}": 3 for i in (1, 2, 3)}

    def _start(self, cl, complaint: str, token: str | None = None):
        headers = _auth(token) if token else {}
        r = cl.post(f"{API}/consultation/start", headers=headers, json={
            "chief_complaint": complaint,
            "questionnaire": self.YANGXU,
            "special_groups": [],
        })
        assert r.json()["code"] == 0, r.json()
        return r.json()["data"]["consultation_id"]

    def test_用户A的记录B与匿名都不可见(self):
        with c() as cl:
            a = _register(cl, _phone(), nickname="A")
            b = _register(cl, _phone(), nickname="B")
            cid_a = self._start(cl, "手脚冰凉，怕冷", a["access_token"])
            cid_anon = self._start(cl, "口干舌燥")  # 匿名问诊

            hist_a = cl.get(f"{API}/consultation/user/history",
                            headers=_auth(a["access_token"])).json()["data"]
            hist_b = cl.get(f"{API}/consultation/user/history",
                            headers=_auth(b["access_token"])).json()["data"]
            hist_anon = cl.get(f"{API}/consultation/user/history").json()["data"]

            ids_a = {h["id"] for h in hist_a}
            ids_b = {h["id"] for h in hist_b}
            ids_anon = {h["id"] for h in hist_anon}

            assert cid_a in ids_a
            assert cid_a not in ids_b, "B 不应看到 A 的问诊"
            assert cid_a not in ids_anon, "匿名列表不应混入登录用户的记录"
            assert cid_anon in ids_anon
            assert cid_anon not in ids_a, "登录用户不应看到匿名记录"

    def test_趋势同样按身份隔离(self):
        with c() as cl:
            a = _register(cl, _phone(), nickname="趋势A")
            # 其他用例可能已产生匿名完成记录，只能比「前后增量」不能比绝对值
            anon_before = len(cl.get(f"{API}/consultation/user/trend").json()["data"])
            cid = self._start(cl, "乏力气短，容易感冒", a["access_token"])
            detail = cl.get(f"{API}/consultation/{cid}").json()["data"]
            assert detail["status"] == "completed"

            trend_a = cl.get(f"{API}/consultation/user/trend",
                             headers=_auth(a["access_token"])).json()["data"]
            anon_after = len(cl.get(f"{API}/consultation/user/trend").json()["data"])
            assert any(t["primary"] for t in trend_a), "A 的趋势应有数据"
            assert anon_after == anon_before, "A 的问诊不应进入匿名趋势"

    def test_匿名模式向后兼容_无令牌全流程不受影响(self):
        """认证上线前的既有行为：无令牌问诊 → 匿名历史可见（既有集成测试的依赖）"""
        with c() as cl:
            cid = self._start(cl, "睡眠差，易醒")
            hist = cl.get(f"{API}/consultation/user/history").json()["data"]
            assert cid in {h["id"] for h in hist}


class TestAuthArchitecture:
    """架构红线：认证逻辑不得侵入 domain 层（与 AST 分层测试同口径）"""

    def test_domain层不依赖认证与jwt(self):
        import ast
        from pathlib import Path

        domain = Path(__file__).resolve().parent.parent / "app" / "domain"
        forbidden = {"jwt", "bcrypt", "app.core.security", "app.services.auth_service"}
        for py in domain.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {a.name for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                hit = {n for n in names if any(n == f or n.startswith(f + ".") for f in forbidden)}
                assert not hit, f"{py.name} 违规依赖 {hit}"
