# -*- coding: utf-8 -*-
"""6.4.1 导出 OpenAPI 规范（接口文档的机器可读版本）

Swagger UI 是给人看的（/docs），这份 JSON 是给论文附录和 CI 用的：

    python scripts/export_openapi.py                 # → docs/openapi.json
    python scripts/export_openapi.py --markdown      # 顺带生成 Markdown 速查表

用法建议：论文附录贴 Markdown 版，仓库里存 JSON 版，
两者都由代码导出，**不会和实现对不上**（手写文档最容易过时）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_FALLBACK_CHAIN", "mock")

from app.main import app  # noqa: E402


def markdown_table(spec: dict) -> str:
    lines = [
        "# API 接口速查",
        "",
        f"- 标题：{spec['info']['title']}",
        f"- 版本：{spec['info']['version']}",
        f"- 接口数：{len(spec['paths'])}",
        "",
        "> 由 `scripts/export_openapi.py` 从代码导出，与实现同步。",
        "",
        "| 方法 | 路径 | 说明 | 分组 |",
        "| --- | --- | --- | --- |",
    ]
    for path, ops in sorted(spec["paths"].items()):
        for method, op in ops.items():
            if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            summary = (op.get("summary") or "").replace("|", "\\|")
            tags = "、".join(op.get("tags", []))
            lines.append(f"| {method.upper()} | `{path}` | {summary} | {tags} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/openapi.json")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    spec = app.openapi()
    out = Path(args.out)
    if not out.is_absolute():
        out = BACKEND_ROOT.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] OpenAPI 已导出：{out}（{len(spec['paths'])} 个路径）")

    if args.markdown:
        md = out.with_name("API接口速查.md")
        md.write_text(markdown_table(spec), encoding="utf-8")
        print(f"[OK] Markdown 速查表：{md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
