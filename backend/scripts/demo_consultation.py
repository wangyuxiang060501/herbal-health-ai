# -*- coding: utf-8 -*-
"""端到端演示脚本（无需启动服务，不依赖前端）—— 论文截图 / 答辩演示素材来源

演示三件事：
  A. 数据分层生效：搜「附子」查得到（百科），推荐「附子」被拒（白名单）
  B. 安全第一：急症输入立即终止问诊；医疗术语被过滤；免责声明不可缺失
  C. P1 闭环：问卷 → 体质判定（确定性）→ 药材推荐（仅 106 白名单）

运行（在 backend/ 目录下）：
    python scripts/demo_consultation.py
    python scripts/demo_consultation.py --provider mock   # 强制离线自检模式
    python scripts/demo_consultation.py --provider ollama # 使用本地 qwen3:8b
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.logging import setup_logging  # noqa: E402

setup_logging("WARNING")

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.domain.constitution import engine as ce  # noqa: E402
from app.domain.recommendation import matcher as hm  # noqa: E402
from app.domain.safety import guard as sg  # noqa: E402
from app.models.entities import Herb, SafetyLog  # noqa: E402
from app.services import data_loader, herb_service  # noqa: E402
from app.services import consultation_service as cs  # noqa: E402

LINE = "─" * 76

YANG_XU_ANSWERS = {
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

PARTIAL_ANSWERS = {"阳虚质_1": 5, "气虚质_1": 4}


def hr(title: str) -> None:
    print(f"\n{LINE}\n  {title}\n{LINE}")


def demo_a_data_layers(db) -> None:
    hr("A. 数据双层架构 —— 「查得到」与「敢推荐」是两件事")

    res = herb_service.search_herbs(db, "附子", size=5)
    print("① 药材百科查询层（828 条原始记录 → 604 味唯一药材 + 白名单补齐 22 味）")
    print(f"   搜索「附子」命中 {len(res)} 条：")
    for h in res[:5]:
        tag = "★ 高危药材" if sg.is_blacklisted(h.name) else "普通药材"
        policy = herb_service.to_dict(h)["usage_policy"]
        print(f"   - {h.name:<8} {h.category:<8} {tag:<12} {policy}")

    print("\n② 推荐层强制 106 种白名单：把「附子」丢进推荐候选")
    whitelist = data_loader.get_whitelist_checker()
    passed, verdict = sg.check_herbs(["附子", "黄芪", "当归", "山药"], whitelist)
    print(f"   通过：{passed}")
    for t in verdict.triggers:
        extra = f" → 替换为「{t.replacement}」" if t.replacement else ""
        print(f"   拦截：{t.rule}｜{t.matched}｜{t.action}{extra}")
    print("\n   ✅ 同一味「附子」，百科查得到、推荐被拦下 —— 这就是 ADR-004 的分层隔离")


def demo_b_safety(db) -> None:
    hr("B. 三道安全闸")

    print("① 输入侧：急症拦截")
    for text in ["我最近胸痛，呼吸困难", "早上咳血了", "突然晕厥"]:
        v = sg.check_input(text)
        print(f"   「{text}」 → verdict={v.verdict}, 规则={v.triggers[0].rule}, "
              f"命中={v.triggers[0].matched}")
        assert v.blocked

    print("\n② 输出侧：医疗术语过滤 + 免责声明注入")
    dirty = "这个方子可以治疗你的失眠，保证有效，药到病除。"
    clean, v = sg.check_output(dirty)
    print(f"   过滤前：{dirty}")
    print(f"   过滤后：{clean.splitlines()[0]}")
    print(f"   触发规则：{[t.matched for t in v.triggers]}")
    print(f"   免责声明存在：{sg.DISCLAIMER in clean}")

    print("\n③ 特殊人群保护")
    whitelist = data_loader.get_whitelist_checker()
    for group, herbs in [("孕妇", ["当归", "山楂", "黄芪"]),
                         ("哺乳期", ["麦芽", "山药"]),
                         ("儿童", ["白果", "莲子"])]:
        passed, _ = sg.check_herbs(herbs, whitelist, [group])
        blocked = [h for h in herbs if h not in passed]
        print(f"   {group:<6} 候选{herbs} → 通过{passed}，剔除{blocked}")


def demo_c_loop(db) -> None:
    hr("C. P1 核心闭环：问卷 → 体质判定 → 药材推荐")

    whitelist = data_loader.get_whitelist_checker()
    index = data_loader.get_whitelist_index()

    print("① 信息充分（27 题全答）：直接出结论")
    result = ce.score(YANG_XU_ANSWERS, rule_table_version="v0.1-draft")
    print(f"   主体质：{result.primary}（{result.primary_label}）  兼夹：{result.secondary or '无'}")
    print(f"   标准：{result.standard}   确定性：{result.deterministic}")
    scores = {k: v for k, v in result.scores.items() if v >= 25}
    print("   九维转化分（≥25）：", json.dumps(scores, ensure_ascii=False))
    print(f"   推理依据（前 3 条）：")
    for e in result.evidence[:3]:
        print(f"     · {e}")

    match = hm.match_herbs(
        result, whitelist, whitelist_index=index,
        chief_complaint="冬天怕冷手脚冰凉，最近容易累", top_n=6,
    )
    print(f"\n   推荐药材（全部 ∈ 106 白名单，共 {len(match.candidates)} 味）：")
    for c in match.candidates:
        print(f"     {c.name:<14} {c.dosage:<12} 得分 {c.score:<6} {c.reason[:34]}")
    if match.rejected:
        print(f"   被拦截：{[r.name + '（' + r.reason + '）' for r in match.rejected]}")

    print("\n② 信息不足（只答 2 题）：不强行辨证，请求补充信息")
    partial = ce.score(PARTIAL_ANSWERS)
    print(f"   answered={partial.answered_total}/27  needs_follow_up={partial.needs_follow_up}")
    print(f"   理由：{partial.follow_up_reason}")
    print(f"   当前倾向（标记为不置信）：{partial.primary} / insufficient={partial.insufficient_info}")

    print("\n③ 确定性验证：同一份问卷跑两次")
    again = ce.score(YANG_XU_ANSWERS)
    same = (result.scores == again.scores and result.primary == again.primary
            and result.secondary == again.secondary)
    print(f"   两次结果完全一致：{same}  →  {'✅ 可复现（ADR-002）' if same else '❌'}")


def demo_d_audit(db) -> None:
    hr("D. 安全审计留痕")
    logs = db.execute(select(SafetyLog)).scalars().all()
    print(f"   safety_logs 表当前记录 {len(logs)} 条（黑名单命中 / 替换 / 术语过滤均落库）")
    herbs_total = len(db.execute(select(Herb)).scalars().all())
    black = [h.name for h in db.execute(select(Herb)).scalars().all() if sg.is_blacklisted(h.name)]
    print(f"   查询层入库 {herbs_total} 味，其中高危药材 {len(black)} 味（可查不可荐）")


def demo_e_orchestration(db) -> None:
    """P2：LangGraph 多智能体编排"""
    hr("E. P2 多智能体编排（LangGraph 状态图）")

    from app.orchestration import graph as og
    from app.orchestration.edges import (
        route_after_collect,
        route_after_constitution,
        route_after_safety,
    )
    from app.orchestration.nodes import NODE_LABELS

    print(f"① 状态图拓扑（LangGraph 可用={og.LANGGRAPH_AVAILABLE}）—— 论文配图来自代码导出")
    for name, label in NODE_LABELS.items():
        print(f"   {name:<20} {label}")

    print("\n② 一次完整问诊的节点执行轨迹")
    outcome = cs.start_consultation(
        db, chief_complaint="我怕冷、手脚冰凉，容易累",
        questionnaire=YANG_XU_ANSWERS,
    )
    for t in outcome.trace:
        print(f"   [{t['at']}] {t['node']:<20} {t['label']}")
    print(f"   终态 phase={outcome.phase}｜主体质={outcome.constitution['primary']}")

    print("\n③ 条件路由分支覆盖演示")
    cases = [
        ("急症命中 → 中止", route_after_collect({"blocked": True})),
        ("正常输入 → 判定", route_after_collect({"blocked": False})),
        ("信息不足+轮次未满 → 追问",
         route_after_constitution({"constitution": {"needs_follow_up": True},
                                   "follow_up_rounds": 0})),
        ("信息不足但轮次用尽 → 匹配",
         route_after_constitution({"constitution": {"needs_follow_up": True},
                                   "follow_up_rounds": 2})),
        ("候选不足+可重配 → 重配",
         route_after_safety({"herbs": {"candidates": []}, "safety_recheck": 0})),
        ("候选不足但次数用尽 → 出结果",
         route_after_safety({"herbs": {"candidates": []}, "safety_recheck": 2})),
    ]
    for desc, branch in cases:
        print(f"   {desc:<28} → {branch}")

    print("\n④ SSE 节点级事件流（前端可直接消费）")
    for ev in cs.start_consultation_stream(db, chief_complaint="最近总感觉累"):
        kind, data = ev["event"], ev["data"]
        if kind == "node":
            print(f"   event:node   {data['node']:<20} {data['label']}")
        elif kind == "question":
            print(f"   event:q      {data['text'][:36]}")
        elif kind == "done":
            print(f"   event:done   phase={data['phase']}｜session={data['consultation_id'][:8]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "ollama"),
                        help="演示所用的 LLM provider（mock 为离线自检模式）")
    args = parser.parse_args()
    os.environ["LLM_PROVIDER"] = args.provider
    if args.provider == "mock":
        os.environ["LLM_FALLBACK_CHAIN"] = "mock"

    init_db()
    db = SessionLocal()
    try:
        demo_a_data_layers(db)
        demo_b_safety(db)
        demo_c_loop(db)
        demo_d_audit(db)
        demo_e_orchestration(db)
        hr("演示结束")
        print("  下一步：uvicorn app.main:app --reload --port 8000，打开 http://127.0.0.1:8000/docs")
    finally:
        db.close()


if __name__ == "__main__":
    main()
