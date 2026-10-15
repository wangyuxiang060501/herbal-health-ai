# -*- coding: utf-8 -*-
"""4.2.4 知识库导入脚本：文档 → 切片 → 向量化 → 存储

用法：
    python scripts/build_index.py                 # 构建并落盘
    python scripts/build_index.py --force         # 忽略磁盘缓存重建
    python scripts/build_index.py --verify        # 构建后跑检索自检（4.5.1）
    python scripts/build_index.py --query "怕冷"  # 单条查询调试
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.rag import indexer  # noqa: E402

# 自检用例（4.5.1）：故意包含「用户说法 ≠ 知识库用语」的样本，
# 用来证明关键词通道与同义词扩展确实起作用
VERIFY_CASES = [
    ("怕冷手脚冰凉", "阳虚质"),
    ("总是觉得没力气", "气虚质"),
    ("晚上睡不着", "不寐/阴虚"),
    ("脸上容易长痘出油", "湿热质"),
    ("皮肤容易出现淤青", "血瘀质"),
    ("附子能不能吃", "高危药材"),
    ("痰多身体沉重", "痰湿质"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="忽略磁盘缓存重建")
    parser.add_argument("--verify", action="store_true", help="构建后跑检索自检")
    parser.add_argument("--query", default="", help="单条查询调试")
    args = parser.parse_args()

    s = get_settings()
    print(f"[配置] embedder={s.rag_embedder}  vector_store={s.rag_vector_store}  kb={s.rag_kb_path}")

    idx = indexer.build_index(force=args.force)
    if idx is None:
        print("[FAIL] 索引构建失败：请先运行 python scripts/build_kb.py")
        return 1

    print(f"[OK] 索引构建完成：{idx.store.count()} 片 · embedder={idx.embedder.name} "
          f"(dim={idx.embedder.dimension}) · store={idx.store.name}")
    if indexer.persist_index(idx):
        print(f"[OK] 已落盘：{s.rag_index_path}")
    else:
        print("[INFO] 该组合不落盘，运行时构建")

    if args.query:
        hits = idx.retriever.retrieve(args.query, top_k=5)
        print(f"\n查询：{args.query}")
        for h in hits:
            print(f"  {h.score:.4f}  {h.chunk_id:<28} {h.text[:60]}")
        return 0

    if args.verify:
        print("\n=== 检索自检（4.5.1）===")
        ok = 0
        for q, expect in VERIFY_CASES:
            hits = idx.retriever.retrieve(q, top_k=3)
            top = hits[0].chunk_id if hits else "（无召回）"
            hit_expect = expect.split("/")[0]
            passed = any(hit_expect in (h.chunk_id + (h.text or "")) for h in hits)
            ok += passed
            print(f"  {'✓' if passed else '✗'} {q:<14} → top1={top:<26} 期望含「{expect}」")
            if not passed and hits:
                print(f"      实际 top3：{[h.chunk_id for h in hits]}")
        print(f"\n自检通过 {ok}/{len(VERIFY_CASES)}")
        print("\n=== 混合检索两路对比（证明关键词通道有效）===")
        for q in ["怕冷手脚冰凉", "晚上睡不着"]:
            exp = idx.retriever.explain(q, top_k=3)  # type: ignore[attr-defined]
            print(f"  查询「{q}」扩展为 {exp['expanded']}")
            print(f"    语义通道 top3：{[h['chunk_id'] for h in exp['semantic']]}")
            print(f"    关键词通道 top3：{[h['chunk_id'] for h in exp['keyword']]}")
            print(f"    融合后 top3：{[h['chunk_id'] for h in exp['fused']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
