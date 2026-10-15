# -*- coding: utf-8 -*-
"""勾选第四阶段（RAG 知识检索增强）已完成条目，并刷新进度统计。

与 update_checklist_p2.py / p4.py 同风格：只改复选框与统计行，不动正文。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/ -> backend/ -> 项目根
TARGET = ROOT / "开发步骤清单.md"

# 本轮实际完成
DONE = [
    "4.1.1", "4.1.2", "4.1.3", "4.1.4",
    "4.2.1", "4.2.2", "4.2.3", "4.2.4", "4.2.5",
    "4.3.1", "4.3.2", "4.3.3", "4.3.4",
    "4.4.1", "4.4.2", "4.4.3", "4.4.4",
    "4.5.1", "4.5.2", "4.5.3",
]

# 与清单原文口径不一致或有实现约定，需要写清楚说明的条目
PARTIAL_NOTE = {
    "4.1.1": "（604 味唯一药材切为结构化 Markdown + JSONL，非 828 条原始记录；"
             "828→604 去重依据见 docs/数据去重报告.md）",
    "4.1.2": "（106 种，以 backend/data/food_medicine_106.json 为准；"
             "国家目录 9 个字段的逐条人工核验尚未完成，verified 仍为 false）",
    "4.1.3": "（九种体质 + 常见症状映射；GB/T 46939—2025 原文未获取，"
             "判定逻辑按公开分级计分口径实现）",
    "4.2.1": "（chromadb 1.5.9 持久化模式；未装时自动降级为内存向量库）",
    "4.2.2": "（三档：sentence-onnx / tfidf-char / hashing-bigram，自动降级链）",
    "4.3.1": "（实现为 app/rag/retriever.py 端口 + app/rag/hybrid.py 混合检索器）",
    "4.3.2": "（语义通道在 hashing/tfidf 档下为字面相似，故权重下调，见 _weights()）",
    "4.3.3": "（语义 + BM25 关键词，RRF(k=60) 融合；附同义词扩展表）",
    "4.4.3": "（药膳节点检索食材切片注入 retrieved_evidence）",
    "4.5.3": "（A/B 对比脚本 scripts/ab_rag_compare.py，报告见 docs/RAG_有无对比.md）",
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
    text = re.sub(r"已完成\s*\d+\s*/\s*\d+", f"已完成 {done} / {total}", text)
    # 清单文首没有进度行时补一条，保证进度有唯一载体
    marker = "进度跟踪见 docs/阶段性开发报告_P0P1.md。"
    if marker in text and "当前进度：" not in text:
        text = text.replace(marker, marker + f"\n> **当前进度：已完成 {done} / {total} 项"
                            f"（第四阶段 RAG 已完成）**", 1)
    elif "当前进度：已完成" in text:
        text = re.sub(r"当前进度：已完成\s*\d+\s*/\s*\d+",
                      f"当前进度：已完成 {done} / {total}", text)

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] 勾选 {changed} 项；进度 {done}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
