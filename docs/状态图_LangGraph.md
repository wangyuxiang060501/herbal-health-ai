# 问诊状态图（LangGraph）—— 论文第四章配图源码

> 本文件由代码自动导出，**不要手改**。
> 导出来源：`backend/app/orchestration/graph.py::mermaid()`，节点标签查 `nodes.py::NODE_LABELS`。
> 重要性：论文里的流程图与线上跑的图是同一份定义，避免「图上画的和代码跑的不一致」。

## mermaid

```mermaid
stateDiagram-v2
    state "① 症状采集与输入安全初筛" as collect_symptoms
    state "② 体质判定引擎（确定性）" as constitution_engine
    state "③ Agent1 追问生成" as follow_up
    state "④ Agent2 药材匹配" as herb_match
    state "⑤ 安全交叉校验" as safety_check
    state "⑥ Agent3 药膳生成" as food_recipe
    state "⑦ 结果组织与免责注入" as present
    state "↺ 重配计数（有界）" as recheck_counter
    state "✖ 安全策略中止" as safety_abort

    [*] --> collect_symptoms
    state fork1 <<choice>>
    collect_symptoms --> fork1
    fork1 --> safety_abort: 急症命中
    fork1 --> constitution_engine: 正常

    state fork2 <<choice>>
    constitution_engine --> fork2
    fork2 --> follow_up: 信息不足 且 追问轮次<2
    fork2 --> herb_match: 信息充足
    follow_up --> [*]: 追问≤3问/≤2轮，等待用户补充（Checkpointer 存快照）

    herb_match --> safety_check: 候选药材（仅106白名单）
    state fork3 <<choice>>
    safety_check --> fork3
    fork3 --> recheck_counter: 候选不足（可重配）
    recheck_counter --> herb_match: 重新配伍（最多2次）
    fork3 --> food_recipe: 通过/已替换（P3开关）
    fork3 --> safety_abort: 输出侧阻断
    food_recipe --> present
    present --> [*]: 体质倾向+药材+免责声明
    safety_abort --> [*]: 红色警示 + 引导就医
```

## LangGraph 自导出（交叉验证用）

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	collect_symptoms(collect_symptoms)
	constitution_engine(constitution_engine)
	follow_up(follow_up)
	herb_match(herb_match)
	safety_check(safety_check)
	food_recipe(food_recipe)
	present(present)
	safety_abort(safety_abort)
	recheck_counter(recheck_counter)
	__end__([<p>__end__</p>]):::last
	__start__ --> collect_symptoms;
	collect_symptoms -. &nbsp;diagnose&nbsp; .-> constitution_engine;
	collect_symptoms -.-> safety_abort;
	constitution_engine -.-> follow_up;
	constitution_engine -. &nbsp;match&nbsp; .-> herb_match;
	food_recipe --> present;
	herb_match --> safety_check;
	recheck_counter --> herb_match;
	safety_check -. &nbsp;recipe&nbsp; .-> food_recipe;
	safety_check -.-> present;
	safety_check -. &nbsp;recheck&nbsp; .-> recheck_counter;
	safety_check -. &nbsp;abort&nbsp; .-> safety_abort;
	follow_up --> __end__;
	present --> __end__;
	safety_abort --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```

## 节点结构（JSON）

```json
{
  "engine": "langgraph",
  "nodes": [
    {
      "id": "collect_symptoms",
      "label": "① 症状采集与输入安全初筛"
    },
    {
      "id": "constitution_engine",
      "label": "② 体质判定引擎（确定性）"
    },
    {
      "id": "follow_up",
      "label": "③ Agent1 追问生成"
    },
    {
      "id": "herb_match",
      "label": "④ Agent2 药材匹配"
    },
    {
      "id": "safety_check",
      "label": "⑤ 安全交叉校验"
    },
    {
      "id": "food_recipe",
      "label": "⑥ Agent3 药膳生成"
    },
    {
      "id": "present",
      "label": "⑦ 结果组织与免责注入"
    },
    {
      "id": "safety_abort",
      "label": "✖ 安全策略中止"
    },
    {
      "id": "recheck_counter",
      "label": "↺ 重配计数（有界）"
    },
    {
      "id": "START",
      "label": "START"
    },
    {
      "id": "END",
      "label": "END"
    }
  ],
  "edges": [
    {
      "from": "START",
      "to": "collect_symptoms"
    },
    {
      "from": "herb_match",
      "to": "safety_check"
    },
    {
      "from": "food_recipe",
      "to": "present"
    },
    {
      "from": "present",
      "to": "END"
    },
    {
      "from": "safety_abort",
      "to": "END"
    },
    {
      "from": "follow_up",
      "to": "END"
    },
    {
      "from": "recheck_counter",
      "to": "herb_match"
    }
  ],
  "conditional_edges": [
    {
      "from": "collect_symptoms",
      "branches": [
        {
          "when": "safety_abort",
          "to": "safety_abort"
        },
        {
          "when": "diagnose",
          "to": "constitution_engine"
        }
      ]
    },
    {
      "from": "constitution_engine",
      "branches": [
        {
          "when": "follow_up",
          "to": "follow_up"
        },
        {
          "when": "match",
          "to": "herb_match"
        }
      ]
    },
    {
      "from": "safety_check",
      "branches": [
        {
          "when": "recheck",
          "to": "recheck_counter"
        },
        {
          "when": "abort",
          "to": "safety_abort"
        },
        {
          "when": "recipe",
          "to": "food_recipe"
        },
        {
          "when": "present",
          "to": "present"
        }
      ]
    }
  ]
}
```
