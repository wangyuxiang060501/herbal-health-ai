# -*- coding: utf-8 -*-
"""把 P2 阶段已完成的事项在开发步骤清单里勾上

用法：python scripts/update_checklist_p2.py
一次性的施工台账工具（不计入测试）。 unmount 之前会备份到 tmp/。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # -> D:/herbal
CHECKLIST = ROOT / "开发步骤清单.md"

# ---- 本轮（P2 LangGraph 编排）完成的任务 ----
DONE_STEPS = [
    "3.4.1", "3.4.2", "3.4.3", "3.4.4", "3.4.5", "3.4.6", "3.4.7", "3.4.8",
    "3.6.1", "3.6.2", "3.6.3",
]

# 与 P2 强相关的其他条目
EXTRA_TASKS = {
    "3.4": "LangGraph 状态图",
}


def mark(step: str, lines: list[str]) -> bool:
    pat = re.compile(rf"^(\s*- \[) \] \*\*{re.escape(step)}\*\*")
    for i, ln in enumerate(lines):
        if pat.match(ln):
            lines[i] = pat.sub(r"\1x] **" + step + "**", ln, count=1)
            return True
    return False


def main() -> None:
    raw = CHECKLIST.read_text(encoding="utf-8")
    lines = raw.split("\n")
    hit = []
    for step in DONE_STEPS:
        if mark(step, lines):
            hit.append(step)
    text = "\n".join(lines)

    # 更新统计行：形如「已完成 47/157」
    done = text.count("- [x]")
    total = text.count("- [x]") + text.count("- [ ]")
    text = re.sub(r"已完成\s*\d+\s*/\s*\d+", f"已完成 {done}/{total}", text)
    text = re.sub(r"进度[：:]\s*\d+\s*/\s*\d+", f"进度：{done}/{total}", text)

    shutil.copy(CHECKLIST, CHECKLIST.with_suffix(".bak.md"))
    CHECKLIST.write_text(text, encoding="utf-8")
    print(f"已勾选：{', '.join(hit)}")
    print(f"进度更新为 {done}/{total}")


if __name__ == "__main__":
    main()
