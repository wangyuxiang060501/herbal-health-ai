# -*- coding: utf-8 -*-
"""架构适应度函数（系统架构设计.md 8.2）

这些测试是「守卫」而非业务用例：一旦有人破坏了分层，测试立即失败。
"""
from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parent.parent / "app" / "domain"
FORBIDDEN_IN_DOMAIN = [
    "langgraph", "langchain", "sqlalchemy", "fastapi", "httpx",
    "openai", "zhipuai", "dashscope", "sentence_transformers", "chromadb",
    "pydantic",
]


def _iter_py_files(root: Path):
    for f in root.rglob("*.py"):
        if f.name.startswith("_"):
            continue
        yield f


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


class TestDependencyDirection:

    def test_领域层不得依赖任何外部框架(self):
        violations = []
        for f in _iter_py_files(DOMAIN_ROOT):
            for mod in _imports_of(f):
                root_mod = mod.split(".")[0]
                if root_mod in FORBIDDEN_IN_DOMAIN:
                    violations.append(f"{f.relative_to(DOMAIN_ROOT)} -> {mod}")
        assert not violations, "领域层依赖方向被破坏：\n" + "\n".join(violations)

    def test_领域层不依赖LLM的SDK(self):
        """「业务代码零 provider 依赖」是可_EXECUTED 的断言，不只是口号"""
        for f in _iter_py_files(DOMAIN_ROOT):
            for mod in _imports_of(f):
                assert mod.split(".")[0] not in ("zhipuai", "openai", "dashscope"), \
                    f"{f.name} 引入了 LLM SDK：{mod}"

    def test_领域层相对与应用层不反向依赖(self):
        for f in _iter_py_files(DOMAIN_ROOT):
            src = f.read_text(encoding="utf-8")
            assert "from app.services" not in src, f"{f.name} 反向依赖了 services"
            assert "from app.api" not in src, f"{f.name} 反向依赖了 api"

    def test_推荐服务不直接引用查询层仓储(self):
        """推荐层只会经由 WhitelistChecker 拿到数据，不得直接查 herbs 表"""
        matcher = DOMAIN_ROOT / "recommendation" / "matcher.py"
        src = matcher.read_text(encoding="utf-8")
        for mod in _imports_of(matcher):
            assert "herb_service" not in mod, "推荐层禁止直连查询层仓储"


class TestSafetyConstantIntegrity:

    def test_黑名单与白名单无交集(self):
        from app.domain.safety.constants import BLACKLIST_HERBS
        from app.services import data_loader

        wl = data_loader.get_whitelist_checker()
        leaked = [b for b in BLACKLIST_HERBS if wl.contains(b)]
        assert not leaked, f"黑名单药材出现在白名单：{leaked}"

    def test_替换品全部合法(self):
        from app.domain.safety.constants import BLACKLIST_REPLACEMENT
        from app.services import data_loader

        wl = data_loader.get_whitelist_checker()
        bad = {k: v for k, v in BLACKLIST_REPLACEMENT.items() if not wl.contains(v)}
        assert not bad, f"替换目标不在白名单：{bad}"

    def test_术语替换映射无自反(self):
        from app.domain.safety.constants import FORBIDDEN_TERMS

        for bad, good in FORBIDDEN_TERMS.items():
            assert bad != good
            assert bad not in good, f"替换结果仍含禁用词：{bad} -> {good}"

    def test_急症建议包含急救电话(self):
        from app.domain.safety.constants import EMERGENCY_ADVICE

        assert "120" in EMERGENCY_ADVICE
