# -*- coding: utf-8 -*-
"""安全自检接口

设计动机：把「附子必拒」「急症必拦」这类**不可豁免的安全不变量**，
从只能跑 pytest 的断言，变成可以随时 curl / 演示 स्व自查的接口。
答辩现场被问「你怎么证明安全层生效」时，直接打这几个接口即可。

 POST /api/v1/safety/probe-herbs   候选药材 → 白名单/黑名单/配伍/人群裁决
 POST /api/v1/safety/probe-output  文本 → 术语过滤 + 免责声明注入
 GET  /api/v1/safety/rules         规则常量摘要
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ok
from app.domain.safety import guard as sg
from app.domain.safety.constants import (
    BLACKLIST_HERBS,
    DISCLAIMER,
    EMERGENCY_KEYWORDS,
    FORBIDDEN_TERMS,
    INCOMPATIBLE_PAIRS,
    SPECIAL_GROUPS,
    SPECIAL_GROUP_FORBIDDEN,
)
from app.schemas import OutputProbeIn, SafetyProbeIn
from app.services import data_loader

router = APIRouter(prefix="/safety", tags=["安全合规（BC7）"])


@router.post("/probe-herbs", summary="候选药材安全裁决")
def probe_herbs(payload: SafetyProbeIn):
    checker = data_loader.get_whitelist_checker()
    passed, verdict = sg.check_herbs(
        payload.herb_names, checker, payload.special_groups
    )
    return ok({
        "passed": passed,
        "verdict": verdict.to_dict(),
        "invariant": "passed 列表中的每一个名称都保证 ∈ 106 白名单",
    })


@router.post("/probe-output", summary="输出文本安全过滤")
def probe_output(payload: OutputProbeIn):
    clean, verdict = sg.check_output(payload.text)
    return ok({"clean": clean, "verdict": verdict.to_dict()})


@router.get("/rules", summary="安全规则摘要")
def rules():
    return ok({
        "emergency_keywords_count": len(EMERGENCY_KEYWORDS),
        "blacklist_count": len(BLACKLIST_HERBS),
        "blacklist_sample": BLACKLIST_HERBS[:12],
        "whitelist_count": len(data_loader.get_whitelist_checker()),
        "incompatible_pairs_count": len(INCOMPATIBLE_PAIRS),
        "forbidden_terms_count": len(FORBIDDEN_TERMS),
        "special_groups": SPECIAL_GROUPS,
        "special_group_forbidden": SPECIAL_GROUP_FORBIDDEN,
        "disclaimer": DISCLAIMER,
    })
