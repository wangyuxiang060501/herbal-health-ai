# -*- coding: utf-8 -*-
"""P6 收尾：勾选 5.4.1（用户模块联调）、1.3.3/1.3.4（Alembic）

勾选依据（可复跑验证）：
  - 5.4.1  后端 /api/v1/auth（register/login/refresh/profile）+ JWT 双令牌 +
           前端 store/拦截器/密码登录页接入；tests/test_auth.py 15 项全绿，
           全量 241 passed。注：access token 为短寿命 JWT，"刷新"走
           refresh token 旋转换新，无独立刷新令牌表（无状态方案，见
           app/core/security.py docstring）。
  - 1.3.3  backend/alembic.ini + migrations/（env.py 注入应用配置与元数据，
           SQLite 启用 render_as_batch）。
  - 1.3.4  首个迁移 60a09271bd5b（7 表 + 17 索引），空库
           upgrade → downgrade → upgrade 闭环已实测一致。

用法：python scripts/update_checklist_p6.py
"""
from __future__ import annotations

import re
from pathlib import Path

CHECKLIST = Path(__file__).resolve().parents[2] / "开发步骤清单.md"

NOTES = {
    "1.3.3": "（backend/alembic.ini + migrations/，env.py 复用应用配置与 ORM 元数据，SQLite 走 batch 模式）",
    "1.3.4": "（首个迁移 60a09271bd5b：7 表 + 17 索引；空库 upgrade→downgrade→upgrade 闭环实测一致；存量库可 alembic stamp head 对齐）",
    "5.4.1": "（后端 /api/v1/auth 注册/登录/刷新/资料 + bcrypt/PyJWT 双令牌；历史与趋势按登录态隔离、匿名口径向后兼容；前端真实登录注册 + 401 静默刷新重放；tests/test_auth.py 15 项全绿，全量 241 passed）",
}


def main() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for item, note in NOTES.items():
        pattern = re.compile(r"- \[ \] \*\*" + re.escape(item) + r"\*\* (.+)")
        m = pattern.search(text)
        if not m:
            print(f"[跳过] {item} 未找到未勾选条目（可能已勾选）")
            continue
        replacement = f"- [x] **{item}** {m.group(1)}{note}"
        text = text[: m.start()] + replacement + text[m.end():]
        print(f"[勾选] {item}")
    # 进度行：127 -> 130
    text = text.replace("已完成 127 / 157 项（第四阶段 RAG 已完成）",
                        "已完成 130 / 157 项（P6：认证联调 + Alembic 迁移已完成）")
    CHECKLIST.write_text(text, encoding="utf-8")
    print(f"已写入 {CHECKLIST}")


if __name__ == "__main__":
    main()
