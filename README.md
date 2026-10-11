# 中医药智慧康养系统

> 题目：**基于多智能体协同与检索增强生成的中医药智慧康养系统的设计与实现**
> 当前阶段：**P0 地基 + P1 核心闭环 + P2 多智能体编排（后端）已完成**，前端待 P4

系统定位一句话：**把"需要专业中医师才能做的事"变成"手机上 5 分钟就能做的事"**，
且严格守住两条红线——**不做疾病诊断**、**推荐的药材必须全部属于国家 106 种药食同源目录**。

---

## 一、本阶段交付了什么

| 能力 | 状态 | 一句话 |
|---|---|---|
| 双层数据集 | ✅ | 828 条原始记录 → **604 味唯一药材**（去重合并）+ **106 种药食同源白名单** |
| 数据体检 | ✅ | 四项检查全部有数字结论，体检/去重报告在 `docs/` |
| 药材查询 API | ✅ | 列表/搜索/筛选/详情，带「可用于药膳 / 仅供查询」区分 |
| LLM 抽象层 | ✅ | `ollama`（默认，本机 qwen3:8b）/ `deepseek` / `zhipu` / `mock` 四 provider + 降级链 + 成本护栏 |
| 安全合规层 | ✅ | 急症拦截 · 黑名单替换 · 白名单硬校验 · 十八反十九畏 · 特殊人群 · 术语过滤 · 免责声明 |
| 体质判定引擎 | ✅ | GB/T 46939—2025 等级计分，**确定性纯函数**，可复现可单测 |
| 药材匹配推荐 | ✅ | 体质→药材规则表（9 体质 × 10 味）+ 主诉症状加成，**强制过安全层** |
| **LangGraph 多智能体编排** | ✅ | 集中式状态机：7 业务节点 + 3 条条件边 + SQLite Checkpointer |
| 会话快照 / 中断恢复 | ✅ | 同一 session 可续跑，DB 问卷快照为第二道保险 |
| 节点级 SSE | ✅ | `node / meta / delta / question / done / error` 事件 |
| 状态图可视化 | ✅ | `GET /api/v1/consultation/graph` —— 论文配图由代码导出 |
| 问诊闭环 | ✅ | 问卷 → 追问（≤2 轮）→ 判定 → 推荐 → 落库 → SSE 流式 |
| 测试 | ✅ | **135 个用例全绿**（含「附子必拒」「追问有上界」架构验收测试） |

详细内容见 [`docs/阶段性开发报告_P0P1.md`](docs/阶段性开发报告_P0P1.md)
与 [`docs/阶段性开发报告_P2.md`](docs/阶段性开发报告_P2.md)。

---

## 二、五分钟跑起来

```bash
# 1) 准备环境（已验证：Python 3.13）
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r backend/requirements.txt

# 2) 配置环境变量
cp .env.example .env        # 默认 LLM_PROVIDER=ollama（本机需已启动 ollama serve 且装有 qwen3:8b）
                            # 若本机无 Ollama，把 LLM_PROVIDER 改成 mock 即可全离线跑通

# 3) 导入双层数据
cd backend && python scripts/import_data.py --reset

# 4) 启动服务
uvicorn app.main:app --reload --port 8000
# → 打开 http://127.0.0.1:8000/docs
```

不想开服务？直接跑端到端演示脚本：

```bash
cd backend
python scripts/demo_consultation.py            # 默认用本机 Ollama
python scripts/demo_consultation.py --provider mock   # 完全离线
```

跑测试：

```bash
cd backend && python -m pytest tests -q        # 135 passed
```

看状态图：

```bash
curl "http://127.0.0.1:8000/api/v1/consultation/graph?format=mermaid"
```

---

## 三、两条不可逾越的红线（以及怎么证明）

### 1. 推荐的每一味药，都必须能吃到

药膳属**普通食品**，法定只能使用卫健委《既是食品又是中药材的物质目录》内的品种。
所以系统里有两套数据，用途严格隔离（ADR-004）：

| 层 | 数据 | 用途 |
|---|---|---|
| 查询层 | 604 味药材百科（828 条原始记录去重后） | 搜索、查看性味归经功效 —— **只读，绝不进方案** |
| 推荐层 | 106 种药食同源白名单 | 体质匹配、药膳推荐 —— **硬白名单，非此即禁** |

自动化证明（这条测试是整套架构的验收门槛）：

```
tests/test_safety_guard.py::TestBlacklist::test_附子必须被推荐层拒绝
```

也可以随时在线自查：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/safety/probe-herbs \
     -H "Content-Type: application/json" \
     -d '{"herb_names":["附子","黄芪","当归"]}'
# → passed: ["肉桂","黄芪","当归"]；附子被拦并替换为肉桂
```

### 2. 体质判定必须可复现

判定**不用 LLM**（ADR-002）。GB/T 46939—2025 给的是确定性等级计分算法，
实现为纯函数后：同一份问卷必得同一份结果，且每条得分都能回溯到具体题目。

```
tests/test_constitution_engine.py::TestDeterminism
tests/test_constitution_engine.py::TestScoring::test_转化分公式正确
```

---

## 四、目录结构

```
herb-health-ai/
├── backend/
│   ├── app/
│   │   ├── domain/          ★ 领域层：零框架依赖（AST 测试会强制检查）
│   │   │   ├── constitution/    体质判定引擎 + 27 题问卷
│   │   │   ├── recommendation/  体质→药材规则表 + 匹配器
│   │   │   └── safety/          三道安全闸 + 规则常量
│   │   ├── orchestration/   ★ P2 编排层：LangGraph 状态机
│   │   │   ├── state.py         ConsultationState（TypedDict + 归约器）
│   │   │   ├── nodes.py         7 业务节点（②③⑤ 规则 / ③④⑥ LLM）
│   │   │   ├── edges.py         3 条条件路由（纯函数）
│   │   │   ├── graph.py         装配 + Checkpointer + mermaid 导出
│   │   │   └── runner.py        service 层唯一入口
│   │   ├── agents/          LLM 网关（多 provider + 重试降级 + 用量计费）
│   │   │   └── prompts/     Agent1/2/3 Prompt 模板（集中管理）
│   │   ├── api/v1/          REST + SSE 路由
│   │   ├── services/        业务服务（只做数据库读写，不写流水线）
│   │   ├── models/          ORM（herbs / whitelist / consultations / safety_logs / usage_logs）
│   │   ├── rag/             检索端口（阶段一：结构化精确检索）
│   │   └── core/            配置 / 数据库 / 日志 / 统一响应
│   ├── data/                双层数据集（含溯源标注）
│   ├── scripts/             数据体检 / 去重 / 导入 / 演示
│   └── tests/               135 个用例
├── frontend/                P4 阶段开工（接口均已就绪）
├── docs/                    体检报告 · 去重报告 · 阶段性开发报告 · 状态图
└── _ref/                    参考仓库（.gitignore 已排除）
```

**依赖方向铁律**：领域层禁止 import `langgraph / langchain / sqlalchemy / fastapi / 任何 LLM SDK`。
这条不是文档里的一句话，是 `tests/test_architecture.py` 里会失败的断言。

---

## 五、重要提醒（动手前必读）

1. **「828 味药材」这个说法必须改**：828 是原始记录条数，去重后唯一药材只有 **604 味**
   （另有 22 味法定可食用品种由白名单补齐，入库合计 626 味）。论文和答辩 PPT 里不要再把 828 当品种数，
   这是一个会被现场核验的数字。
2. **106 条白名单的性味/归经/功效/用量/禁忌是初稿**，全部 `verified=false`，使用前必须人工逐条核对
   （`起步路线.md` 1.4：106 × 9 = 954 个格子，这是论文第四章含金量最高的部分）。
3. **GB/T 46939—2025 标准原文尚未获取**，问卷题面按九种体质通行表述编写，取得原文后只需替换
   `app/domain/constitution/questionnaire.py` 的 `QUESTIONNAIRE`，计分算法无需改动。
