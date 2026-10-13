# -*- coding: utf-8 -*-
"""勾选第五阶段（前端 H5）已完成条目，并刷新进度统计。

与 update_checklist_p2.py 同风格：只改复选框与统计行，不动正文。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/ -> backend/ -> 项目根
TARGET = ROOT / "开发步骤清单.md"

# 本轮实际完成（不含真机测试、后端认证等未完成项）
DONE = [
    "5.1.1", "5.1.2", "5.1.3", "5.1.4", "5.1.5", "5.1.6",
    "5.2.1", "5.2.2", "5.2.3", "5.2.4", "5.2.5", "5.2.6",
    "5.3.1", "5.3.2", "5.3.3", "5.3.4", "5.3.5", "5.3.6",
    "5.3.7", "5.3.8", "5.3.9", "5.3.10",
    "5.4.2", "5.4.3", "5.4.4",
    "5.5.1", "5.5.3", "5.5.4",
]

# 部分完成：需要写实现说明，不能简单打勾
PARTIAL_NOTE = {
    "5.1.5": "（已实现统一响应解包与业务码透出；Token 注入待后端认证接口就绪）",
    "5.1.6": "（已实现「免责声明未确认 → 先确认」守卫；登录跳转待后端认证就绪）",
    "5.3.1": "（首页含统计入口与九体质卡片；轮播图未做，改以药材/体质入口替代）",
    "5.4.3": "（开始问诊 / 提交回答 / SSE 流式已联调）",
    "5.5.3": "（下拉刷新、分页加载已实现；长按等高级手势未做）",
    "5.5.4": "（路由懒加载已由构建分包验证；图片懒加载无图片资源故未启用）",
}


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    lines = text.split("\n")
    changed = 0

    for i, line in enumerate(lines):
        m = re.match(r"^- \[ \] \*\*(\d+\.\d+\.\d+)\*\*", line)
        if not m:
            continue
        num = m.group(1)
        if num in DONE:
            suffix = PARTIAL_NOTE.get(num, "")
            lines[i] = line.replace("- [ ]", "- [x]", 1) + suffix
            changed += 1

    text = "\n".join(lines)

    # 刷新统计行
    total = len(re.findall(r"^- \[[ x]\] \*\*\d+\.\d+\.\d+\*\*", text, flags=re.M))
    done = len(re.findall(r"^- \[x\] \*\*\d+\.\d+\.\d+\*\*", text, flags=re.M))
    text = re.sub(
        r"已完成\s*\d+\s*/\s*\d+",
        f"已完成 {done} / {total}",
        text,
    )

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] 勾选 {changed} 项；进度 {done}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
