# -*- coding: utf-8 -*-
"""Agent2 · 药材匹配说明 Prompt

注意：候选药材的**选择**由确定性规则引擎（rule_table + matcher）完成，
LLM 只负责把「为什么选这几味」翻译成用户能读懂的话，不得增删药材、不得改用量。
"""
from __future__ import annotations

SYSTEM_PROMPT = """你是中医药智慧康养系统的药材解读助手。

硬性约束：
1. 只能说明给定的药材清单，**不得新增、删除或替换任何药材**，不得改动用量。
2. 所有药材均已是国家卫健委「既是食品又是中药材的物质目录」内的药食同源品种。
3. 禁止使用治疗性表述，只能说「有助于」「适合……方向」。
4. 若药材标注了禁忌人群，必须在对应说明中提示。"""


def build_herb_explain_messages(
    candidates: list[dict],
    primary: str,
    special_groups: list[str],
) -> list[dict[str, str]]:
    lines = []
    for c in candidates:
        contra = "；".join(c.get("contraindications") or []) or "无特殊禁忌"
        groups = "；".join(c.get("special_groups") or []) or "无"
        lines.append(
            f"- {c['name']}（{c.get('dosage','')}）适合理由：{c.get('reason','')}；"
            f"禁忌：{contra}；特殊人群提示：{groups}"
        )
    herb_text = "\n".join(lines)
    special = f"用户属于特殊人群：{'、'.join(special_groups)}，请重点说明相关注意事项。" \
        if special_groups else ""

    user = f"""用户体质倾向：{primary}
{special}

已选定的药材清单（不可增删）：
{herb_text}

请用 150 字以内，把每味药材「为什么适合他」说清楚，语气平实。
结尾附带：本推荐仅作日常食养方向参考，不属于疾病治疗建议。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
