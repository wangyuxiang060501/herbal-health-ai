# 中医药智慧康养系统

> 题目：**基于多智能体协同与检索增强生成的中医药智慧康养系统的设计与实现**
> 当前阶段：**P0 地基 + P1 核心闭环 + P2 多智能体编排 + P3 RAG 检索增强 + P4 前端 H5 已完成**
> 清单进度：**108 / 157**；剩余整块内容为第六阶段（测试与优化 / 部署）

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
| **前端 H5** | ✅ | Vue 3 + Vant 4，**10 个页面 + 6 个组件**，移动端适配，SSE 打字机 + 九维雷达图 |
| **RAG 知识库** | ✅ | **734 片**切片（药材 604 / 药食同源 106 / 体质 9 / 症状 11 / 安全规则 4） |
| **RAG 检索** | ✅ | 语义（hashing-bigram，512 维）+ BM25 关键词，**RRF(k=60) 融合**，同义词扩展；自检 **7/7** |
| **引用回溯** | ✅ | Prompt 强制 `[n]` 标注，`rag_citations` 落库并回传前端，结果页「知识依据」卡片可点跳转 |
| 测试 | ✅ | 后端 **177** + 前端 **23** = **200 个用例** |

详细内容见 [`docs/阶段性开发报告_P0P1.md`](docs/阶段性开发报告_P0P1.md)、
[`docs/阶段性开发报告_P2.md`](docs/阶段性开发报告_P2.md)、
[`docs/阶段性开发报告_P3.md`](docs/阶段性开发报告_P3.md)、
[`docs/阶段性开发报告_P4.md`](docs/阶段性开发报告_P4.md)。
有/无 RAG 的真实对比实验见 [`docs/RAG_有无对比.md`](docs/RAG_有无对比.md)。

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

# 4) 构建 RAG 知识库与向量索引（P3）
python scripts/build_kb.py            # 生成 data/kb/chunks.jsonl（734 片）
python scripts/build_index.py --verify   # 建索引并跑 7 条检索自检

# 5) 启动服务
uvicorn app.main:app --reload --port 8000
# → 打开 http://127.0.0.1:8000/docs

# 6) 启动前端 H5（另开一个终端）
cd ../frontend && npm install && npm run dev
# → 打开 http://localhost:5173
```

> ⚠️ 本机构建/测试 esbuild 会因 `Access is denied` 无法删除系统 TEMP 文件，
> 需先 `mkdir -p .tmp` 并把 `TMP`/`TEMP` 指向 `frontend/.tmp` 再执行 `npm run build` / `npm test`。
> 详见 [`frontend/README.md`](frontend/README.md)。

不想开服务？直接跑端到端演示脚本：

```bash
cd backend
python scripts/demo_consultation.py            # 默认用本机 Ollama
python scripts/demo_consultation.py --provider mock   # 完全离线
```

跑测试：

```bash
cd backend && python -m pytest tests -q        # 177 passed
cd ../frontend && npm test                     # 23 passed
```

看状态图 / 检索诊断：

```bash
curl "http://127.0.0.1:8000/api/v1/consultation/graph?format=mermaid"
curl "http://127.0.0.1:8000/api/v1/rag/status"                    # 当前用的哪档 embedder / 向量库
curl "http://127.0.0.1:8000/api/v1/rag/explain?query=怕冷手脚冰凉"  # 语义 / 关键词 / 融合三路对比
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
│   │   ├── rag/             ★ P3 检索层
│   │   │   ├── retriever.py    Retriever 协议 / Evidence / WhitelistRetriever
│   │   │   ├── embedder.py     三档 embedder（sentence-onnx / tfidf / hashing）+ 降级链
│   │   │   ├── vector_store.py Chroma / Memory 两档向量库 + 降级
│   │   │   ├── hybrid.py       同义词扩展 + BM25 + RRF 混合检索
│   │   │   ├── indexer.py      索引构建 / 持久化 / 状态 / 降级
│   │   │   └── context.py      上下文拼装 + 引用指令（强制 [n] 标注）
│   │   └── core/            配置 / 数据库 / 日志 / 统一响应
│   ├── data/                双层数据集（含溯源标注）+ kb/ 知识库切片
│   ├── scripts/             数据体检 / 去重 / 导入 / 建库 / 建索引 / A-B 对比 / 演示
│   └── tests/               177 个用例
├── frontend/                ★ P4 前端 H5（Vue 3 + Vant 4）
│   └── src/
│       ├── views/           10 个页面（首页/药材库/详情/测试/结果/药膳/我的/记录/登录/关于）
│       ├── components/      6 个组件（TabBar/Disclaimer/HerbCard/RecipeCard/StreamChat/LoadingState）
│       ├── composables/     useSSE（POST 型 SSE，原生 EventSource 不支持 POST）
│       ├── stores/          user（本地身份）/ consult（问卷草稿）
│       └── api/             统一请求层 + 业务码常量
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
4. **RAG 默认跑在降级档**（`hashing-bigram` + Chroma）。要上真语义检索，需另装
   `scikit-learn`（`tfidf-char`）或下载 ONNX 句向量模型并把 `RAG_MODEL_PATH` 指过去
   （见 `backend/requirements-full.txt`）。**`hashing` 是字面相似而非语义相似**，
   「怕冷→畏寒」这类同义全靠 BM25 关键词通道兜底，这个取舍在论文里要讲清楚。
5. **论文里不要写「828 味药材知识库」**：知识库是 604 味唯一药材切片 + 106 药食同源，共 734 片。
