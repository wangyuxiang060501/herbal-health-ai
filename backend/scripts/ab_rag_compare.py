# -*- coding: utf-8 -*-
"""4.5.3 有/无 RAG 的 A/B 对比实验（真实 LLM，非模拟）

同一份输入跑两遍，唯一变量是 RAG_ENABLED：
  A 组（RAG on） ：Prompt 中注入知识库检索上下文，并要求用 [n] 标注出处
  B 组（RAG off）：不注入上下文，其余 Prompt / 温度 / 模型完全一致

观测指标（可写进论文 5.x 实验章节）：
  1. 引用标记数      —— 回答里 [n] 的出现次数
  2. 有据药材数      —— 回答提到的药材中，能在「本期召回切片」里找到出处的数量
  3. 无据药材数      —— 回答提到、但本期召回切片里没有的药材（幻觉风险指标）
  4. 白名单合规      —— 回答提到的药材是否全部落在 106 药食同源目录
  5. 长度与具体性    —— 字数、是否出现用量/用法等可执行信息

运行（backend/ 目录）：
  python scripts/ab_rag_compare.py
  python scripts/ab_rag_compare.py --markdown docs/RAG_有无对比.md   # 同时导出 Markdown
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.logging import setup_logging  # noqa: E402

setup_logging("ERROR")

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal, init_db  # noqa: E402
from app.rag import indexer  # noqa: E402
from app.services import consultation_service as cs  # noqa: E402
from app.services import data_loader  # noqa: E402

LINE = "─" * 78

# 固定的阳虚质问卷（与 demo_consultation.py 一致，保证两组输入完全相同）
ANSWERS = {
    "阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5,
    "气虚质_1": 4, "气虚质_2": 3, "气虚质_3": 3,
    "阴虚质_1": 1, "阴虚质_2": 2, "阴虚质_3": 1,
    "痰湿质_1": 2, "痰湿质_2": 1, "痰湿质_3": 1,
    "湿热质_1": 1, "湿热质_2": 1, "湿热质_3": 1,
    "血瘀质_1": 2, "血瘀质_2": 1, "血瘀质_3": 1,
    "气郁质_1": 2, "气郁质_2": 2, "气郁质_3": 1,
    "特禀质_1": 1, "特禀质_2": 1, "特禀质_3": 1,
    "平和质_1": 3, "平和质_2": 3, "平和质_3": 3,
}

COMPLAINT = "冬天特别怕冷，手脚冰凉，最近总觉得没力气"

CITE_RE = re.compile(r"\[(\d+)\]")


def build_herb_vocab() -> set[str]:
    """药材名词典：106 白名单（含别名）+ 知识库 herb/food 切片名

    刻意**不**纳入 symptom: / constitution: 条目——「手脚冰凉」「阳虚质」
    不是药材，算进「提到药材数」会把指标带偏。
    """
    vocab: set[str] = set()
    bases: set[str] = set()
    try:
        wl = get_whitelist()
        vocab |= set(wl.names)
        vocab |= set(wl.aliases.keys())
        bases = {n.split("（")[0].strip() for n in wl.names}
        vocab |= bases
    except Exception:  # noqa: BLE001
        pass
    vocab |= _names_from_kb()
    # 再并入查询层 604 味药材，这样才能检出「不在 106 目录」的越界品种
    try:
        for h in data_loader.load_clean_herbs():
            n = (h.get("name") or "").strip()
            if n:
                vocab.add(n)
    except Exception:  # noqa: BLE001
        pass
    # 单字词只保留白名单主名（如「姜」「枣」），其余要求 ≥2 字，避免噪声
    return {n for n in vocab if n and (len(n) >= 2 or n in bases)}


def _names_from_kb() -> set[str]:
    """从知识库切片里剥出药材名（只取 herb: / food:，排除 symptom: / constitution:）"""
    names: set[str] = set()
    p = BACKEND_ROOT / "data" / "kb" / "chunks.jsonl"
    if not p.exists():
        return names
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            cid = json.loads(line).get("chunk_id", "")
        except Exception:  # noqa: BLE001
            continue
        if ":" not in cid:
            continue
        kind, rest = cid.split(":", 1)
        if kind in ("herb", "food"):
            names.add(rest.split("#", 1)[0])
    return names


def cited_source_names(citations: list[dict], vocab: set[str]) -> set[str]:
    """本期召回切片对应的药材名（只算 herb/food，且按白名单规范名归一）"""
    out: set[str] = set()
    try:
        wl = get_whitelist()
    except Exception:  # noqa: BLE001
        wl = None
    for c in citations:
        cid = c.get("chunk_id", "")
        if ":" not in cid:
            continue
        kind, rest = cid.split(":", 1)
        if kind not in ("herb", "food"):
            continue
        name = rest.split("#", 1)[0]
        out.add(name)
        # 「姜（生姜、干姜）」这类规范名要展开成别名，否则模型说「干姜」算不出出处
        if wl is not None:
            canon = wl.canonical(name)
            if canon:
                for alias, target in wl.aliases.items():
                    if target == canon:
                        out.add(alias)
                out.add(canon.split("（")[0].strip())
    return {n for n in out if n in vocab}


def analyse(text: str, vocab: set[str], grounded: set[str]) -> dict:
    if not text:
        return {"chars": 0, "cites": 0, "herbs": [], "grounded": 0, "ungrounded": []}
    cites = CITE_RE.findall(text)
    herbs = sorted({n for n in vocab if n in text}, key=len, reverse=True)
    # 长名优先去重叠（「生姜」与「姜」同时命中时保留更具体的）
    picked: list[str] = []
    for h in herbs:
        if not any(h in p for p in picked):
            picked.append(h)
    grounded_hits = [h for h in picked if any(h in g or g in h for g in grounded)]
    ungrounded = [h for h in picked if h not in grounded_hits]
    return {
        "chars": len(text),
        "cites": len(cites),
        "herbs": picked,
        "grounded": len(grounded_hits),
        "ungrounded": ungrounded,
    }


def run_group(db, *, rag_on: bool) -> tuple[dict, object]:
    s = get_settings()
    s.rag_enabled = rag_on
    indexer.reset_cache()
    outcome = cs.start_consultation(
        db, chief_complaint=COMPLAINT, questionnaire=ANSWERS,
    )
    return outcome.to_dict(), outcome


def get_whitelist():
    return data_loader.get_whitelist_checker()


def whitelist_ok(names: list[str]) -> tuple[bool, list[str]]:
    try:
        checker = get_whitelist()
    except Exception:  # noqa: BLE001
        return True, []
    bad = [n for n in names if not checker.contains(n)]
    return (not bad), bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", default="", help="同时把结果导出为 Markdown 文件")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        print(LINE)
        print("  4.5.3 有/无 RAG 对比实验")
        print(f"  输入（两组完全一致）：{COMPLAINT}")
        print(LINE)

        vocab = build_herb_vocab()

        # A 组：RAG 开
        a_dict, a_obj = run_group(db, rag_on=True)
        # B 组：RAG 关
        b_dict, b_obj = run_group(db, rag_on=False)

        a_cit = a_dict.get("rag_citations") or []
        b_cit = b_dict.get("rag_citations") or []
        a_grounded = cited_source_names(a_cit, vocab)
        b_grounded = cited_source_names(b_cit, vocab)

        a = analyse(a_dict.get("interpretation", "") or "", vocab, a_grounded)
        b = analyse(b_dict.get("interpretation", "") or "", vocab, b_grounded)

        a_ok, a_bad = whitelist_ok(a["herbs"])
        b_ok, b_bad = whitelist_ok(b["herbs"])

        rows = [
            ("RAG 状态", "开启（注入检索上下文）", "关闭（无上下文）"),
            ("召回切片数", str(len(a_cit)), str(len(b_cit))),
            ("体质判定", str(a_dict.get("constitution", {}).get("primary", "-")),
             str(b_dict.get("constitution", {}).get("primary", "-"))),
            ("解读字数", str(a["chars"]), str(b["chars"])),
            ("引用标记 [n] 数", str(a["cites"]), str(b["cites"])),
            ("检出药材数", str(len(a["herbs"])), str(len(b["herbs"]))),
            ("其中能在召回切片中找到出处", str(a["grounded"]), str(b["grounded"])),
            ("其中不在 106 目录",
             "、".join(a_bad) or "无", "、".join(b_bad) or "无"),
        ]

        print(f"\n{'指标':<16}{'A 组（RAG 开）':<24}{'B 组（RAG 关）':<24}")
        print("─" * 78)
        for k, x, y in rows:
            print(f"{k:<16}{x:<24}{y:<24}")

        print(f"\nA 组召回切片（{len(a_cit)}）：")
        for c in a_cit[:8]:
            print(f"   · [{c.get('chunk_id','')}] {c.get('title','')} "
                  f"（{c.get('source','')}） score={c.get('score',0):.4f}")
        print(f"\nA 组检出药材：{a['herbs']}")
        print(f"  其中不在 106 目录：{a_bad or '无'}")
        print(f"\nB 组检出药材：{b['herbs']}")
        print(f"  其中不在 106 目录：{b_bad or '无'}")

        print(f"\n{'─' * 78}\n  A 组解读全文\n{'─' * 78}")
        print(a_dict.get("interpretation", ""))
        print(f"\n{'─' * 78}\n  B 组解读全文\n{'─' * 78}")
        print(b_dict.get("interpretation", ""))

        conclusion = []
        if a["cites"] > b["cites"]:
            conclusion.append(
                f"引用标记 A 组 {a['cites']} 个 vs B 组 {b['cites']} 个 —— "
                "RAG 使回答可追溯到具体知识切片")
        if a["grounded"] > b["grounded"]:
            conclusion.append(
                f"有出处药材 A 组 {a['grounded']} 味 vs B 组 {b['grounded']} 味 —— "
                "关闭 RAG 时药材全部无出处，属模型自由生成")
        if a_ok and b_ok:
            conclusion.append(
                "两组检出的药材均未越出 106 药食同源目录 —— "
                "白名单硬校验与 RAG 无关，独立生效（RAG 只影响「有没有依据」，不影响「许不许推荐」）")
        conclusion.append(
            "指标局限：检出基于 106 目录 + 604 味药材词典的字符串匹配，"
            "像「红枣」这类未收录的口语称呼不在检测范围内，需在论文中如实说明")
        print(f"\n{'─' * 78}\n  结论\n{'─' * 78}")
        for i, c in enumerate(conclusion, 1):
            print(f"  {i}. {c}")

        if args.markdown:
            out = Path(args.markdown)
            if not out.is_absolute():
                out = BACKEND_ROOT.parent / out
            out.parent.mkdir(parents=True, exist_ok=True)
            md = [
                "# 有/无 RAG 对比实验（4.5.3）",
                "",
                f"- 输入（两组完全一致）：{COMPLAINT}",
                f"- 模型：`{get_settings().llm_provider}` / `{get_settings().llm_model}`",
                "- 唯一变量：`RAG_ENABLED`",
                "",
                "| 指标 | A 组（RAG 开） | B 组（RAG 关） |",
                "| --- | --- | --- |",
            ]
            for k, x, y in rows:
                md.append(f"| {k} | {x} | {y} |")
            md += ["", "## A 组召回切片", ""]
            for c in a_cit[:10]:
                md.append(f"- `{c.get('chunk_id','')}` {c.get('title','')}"
                          f"（{c.get('source','')}）score={c.get('score',0):.4f}")
            md += ["", "## A 组解读（RAG 开）", "",
                   "```", a_dict.get("interpretation", ""), "```",
                   "", "## B 组解读（RAG 关）", "",
                   "```", b_dict.get("interpretation", ""), "```",
                   "", "## 结论", ""]
            md += [f"{i}. {c}" for i, c in enumerate(conclusion, 1)]
            out.write_text("\n".join(md), encoding="utf-8")
            print(f"\n[OK] Markdown 已导出：{out}")

        # 复原配置，避免影响后续调用
        get_settings().rag_enabled = True
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
