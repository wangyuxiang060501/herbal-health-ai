# -*- coding: utf-8 -*-
"""Agent1 · 问诊对话 Prompt（追问生成 + 结果通俗化）

依据 ADR-002：Agent1 **不再承担体质辨证**（那件事由确定性规则引擎完成），
它的职责收缩为两件 LLM 擅长的事：
  ① 针对信息不足处生成追问（≤3 个问题）
  ② 把规则引擎的结论转成通俗话术（不得改变结论本身）
"""
from __future__ import annotations

SYSTEM_PROMPT = """你是中医药智慧康养系统的问诊助手，职责是**补充采集信息**与**通俗转述**，不是做诊断。

硬性约束（违反即输出无效）：
1. 禁止输出疾病诊断结论，禁止使用「治疗、治愈、确诊、处方、特效」等表述。
2. 禁止说「你就是XX体质」，只能说「倾向于」「明显偏向」。
3. 每次追问最多 3 个问题，问题要具体、可被一句自然语言回答。
4. 不得推荐处方药，药材建议仅限于国家卫健委「既是食品又是中药材的物质目录」内的品种。
5. 用户描述急重症（胸痛、呼吸困难、咯血、晕厥等）时，立即停止追问并引导其就医。
6. 全程使用简体中文，语气亲切，避免堆砌术语。"""


def build_follow_up_messages(
    chief_complaint: str,
    answered_summary: str,
    missing_dimensions: list[str],
    special_groups: list[str],
    round_no: int,
) -> list[dict[str, str]]:
    special = f"用户对特殊人群标记：{'、'.join(special_groups)}。" if special_groups else ""
    user = f"""用户的初始描述：{chief_complaint or '（无）'}

用户已回答的要点：
{answered_summary or '（暂无）'}

目前信息不足，需要你补充了解。请以如下维度为线索生成 1-3 个追问问题：
{'、'.join(missing_dimensions) or '一般生活习惯'}

要求：
- 这是第 {round_no} 轮追问，语气自然，不要在问题里暴露「维度」这个词
- 每个问题占一行，用「1. 2. 3.」编号
- {special}
- 只输出问题本身，不要寒暄，不要给出任何结论"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_interpret_messages(
    primary: str,
    secondary: list[str],
    evidence: list[str],
    primary_label: str,
    standard: str = "GB/T 46939—2025",
) -> list[dict[str, str]]:
    evidence_text = "\n".join(f"- {e}" for e in evidence) or "（无明显条目）"
    user = f"""规则引擎已给出体质判定结论，请把它转述成普通人读得懂的话。

【判定结论】（不可更改）
- 主体质：{primary}（{primary_label}）
- 兼夹体质：{'、'.join(secondary) or '无'}
- 判定依据标准：{standard}

【用户问卷中指向该结论的回答】
{evidence_text}

输出要求（严格按顺序，控制在 200 字以内）：
1. 用「你的体质倾向于……」开头，禁止使用「你就是XX体质」
2. 说明这个体质的日常典型表现（2-3 句，通俗描述，不用术语堆砌）
3. 给出 2-3 条日常起居/饮食方向的建议（方向性，不说具体用量）
4. 结尾必须原样附带这句免责声明：
「本结论仅基于中医体质理论做日常食疗方向参考，不属于疾病诊断，不能替代执业医师诊疗。」"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
