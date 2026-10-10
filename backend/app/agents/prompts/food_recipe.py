# -*- coding: utf-8 -*-
"""Agent3 · 药膳方案生成 Prompt

⚠️ 本模块为 **P3 阶段** 预留（对应开发阶段第四/五阶段）。
当前 P0+P1 交付范围不含药膳方案生成（recipes），接口契约已按
系统架构设计.md 4.1-③ 定义，待接入。
"""
from __future__ import annotations

SYSTEM_PROMPT = """你是中医药智慧康养系统的药膳方案助手（P3 阶段启用）。

硬性约束：
1. 药膳属普通食品，**配方药材必须来自给定的候选清单**，不得引入清单外的药材。
2. 每次输出恰好 2 套方案，类型在「汤 / 粥 / 茶」之间轮换。
3. 每套方案必须包含：名称、适配体质、配方（含用量）、制作步骤（具体到火候与时间）、
   食用指导（频次与周期）、禁忌提示。
4. 服用周期不得超过 2-4 周，必须提示服后暂停。
5. 制作步骤需保证普通家用厨具可完成。
6. 结尾必须附免责声明。"""


def build_recipe_messages(
    candidates: list[dict],
    primary: str,
    retrieved_evidence: list[dict] | None = None,
    special_groups: list[str] | None = None,
) -> list[dict[str, str]]:
    allowed = "\n".join(f"- {c['name']}（建议用量 {c.get('dosage','')}）" for c in candidates)
    rag = ""
    if retrieved_evidence:
        rag = "\n\n可参考的文献片段（引用时须标注 chunk_id）：\n" + "\n".join(
            f"[{e.get('chunk_id')}] {e.get('text', '')[:200]}" for e in retrieved_evidence
        )
    special = f"\n用户属于特殊人群：{'、'.join(special_groups or [])}。" if special_groups else ""
    user = f"""用户体质倾向：{primary}。{special}

可用药材（仅限这些，不可新增）：
{allowed}
{rag}

请生成 2 套药膳方案 + 1 个代茶饮，输出 JSON：
{{
  "recipes": [
    {{"name":"", "type":"汤|粥|茶", "fit_constitution":"",
      "ingredients":[{{"name":"","amount":""}}],
      "steps":[""], "guidance":{{"frequency":"","duration":""}}}}
  ],
  "tea": {{"name":"", "formula":[""], "steps":[""]}},
  "warnings": {{"taboo_foods":[""], "forbidden_groups":[""], "cycle_notice":""}}
}}"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
