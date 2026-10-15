# -*- coding: utf-8 -*-
"""勾选第六阶段（测试、优化与部署）+ 本轮顺带补齐的条目，并刷新进度统计。

与 p2/p3/p4.py 同风格：只改复选框与统计行，不动正文。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/ -> backend/ -> 项目根
TARGET = ROOT / "开发步骤清单.md"

# 本轮实际完成
DONE = [
    # 第一阶段：Docker 环境（P5 补齐）
    "1.4.1", "1.4.2",
    # 第五阶段残留
    "5.4.5",
    # 6.1 测试
    "6.1.1", "6.1.2", "6.1.3", "6.1.4",
    # 6.2 优化
    "6.2.1", "6.2.2", "6.2.3", "6.2.4",
    # 6.3 部署
    "6.3.1", "6.3.2", "6.3.3",
    # 6.4 文档
    "6.4.1", "6.4.2", "6.4.3", "6.4.4",
    # 6.5 最终验证
    "6.5.1",
]

# 需要写清楚实现约定或保留意见的条目
PARTIAL_NOTE = {
    "1.4.1": "（backend/Dockerfile：构建期生成知识库切片，运行时数据挂卷，HEALTHCHECK 复用 /health）",
    "1.4.2": "（docker-compose.yml 开发版：前端 Vite dev server + 后端 --reload）",
    "5.4.5": "（网络断开/超时、服务端错误已处理：SSE 空闲超时 + 早期失败自动重试；"
             "Token 过期处理待后端认证接口就绪）",
    "6.1.1": "（pytest 覆盖率 **87%**（2972 行 / 387 未覆盖），超 70% 目标；后端 226 个用例全绿）",
    "6.1.2": "（tests/test_integration_flow.py：只走 HTTP 的主链路 + 异常分支 + RAG 接口）",
    "6.1.3": "（tests/test_security.py：SQL 注入 / XSS / 提示词注入 / 医疗术语过滤；"
             "含「前端不得使用 v-html」架构测试）",
    "6.1.4": "（scripts/bench_api.py 起真实 uvicorn 做并发压测；报告 docs/性能测试报告.md）",
    "6.2.1": "（改为进程内 TTL+LRU 缓存聚合统计，未引入 Redis —— 单机 MVP 收益不抵运维成本，"
             "接口预留可替换）",
    "6.2.2": "（新增 5 个索引 + SQLite WAL/busy_timeout；并发 16×100 成功率 97→100，"
             "p50 1129ms→395ms）",
    "6.2.3": "（vite manualChunks 拆 echarts/html2canvas/vant/vue 四包；路由懒加载 P4 已完成）",
    "6.2.4": "（useSSE 空闲超时 45s + 早期失败重试 1 次；**已收到数据后绝不重放请求**，避免重复问诊记录）",
    "6.3.1": "（docker-compose.prod.yml：backend + frontend(nginx) + certbot；"
             "backend 不暴露宿主机端口）",
    "6.3.2": "（deploy/nginx.conf：静态文件 + /api 反代；**SSE 必须 proxy_buffering off**）",
    "6.3.3": "（deploy/init-ssl.sh：HTTP-01 申请 Let's Encrypt，certbot 容器每 12h 续期）",
    "6.4.1": "（FastAPI 自动生成 Swagger + openapi_tags 分组说明；"
             "另由 scripts/export_openapi.py 导出 docs/openapi.json 与 API接口速查.md）",
    "6.4.2": "（docs/数据库设计.md：mermaid ER 图 + 索引清单 + 迁移策略）",
    "6.4.3": "（docs/系统架构设计.md 原有 11 章 + 新增第十二章「实现对照」）",
    "6.4.4": "（docs/用户使用手册.md：面向最终用户，含常见问题与数据局限说明）",
    "6.5.1": "（后端 226 个用例全绿；前端 23+5 个用例因本机 esbuild 故障未能重跑，见报告第八节）",
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

    total = len(re.findall(r"^- \[[ x]\] \*\*\d+\.\d+\.\d+\*\*", text, flags=re.M))
    done = len(re.findall(r"^- \[x\] \*\*\d+\.\d+\.\d+\*\*", text, flags=re.M))
    text = re.sub(r"已完成\s*\d+\s*/\s*\d+", f"已完成 {done} / {total}", text)
    if "当前进度：已完成" in text:
        text = re.sub(r"当前进度：已完成\s*\d+\s*/\s*\d+",
                      f"当前进度：已完成 {done} / {total}", text)

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] 勾选 {changed} 项；进度 {done}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
