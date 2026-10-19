# 中医药智慧康养系统

> 基于多智能体协同与检索增强生成的中医药智慧康养系统

## 🚀 一键启动（推荐）

### 前置条件
- 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Windows/Mac/Linux 均可）

### 启动步骤

```bash
# 1. 克隆项目
git clone https://gitee.com/wang-yuxiang123123/zhihuizhongyi.git
cd zhihuizhongyi

# 2. 一键启动
docker compose up -d --build

# 3. 打开浏览器
#    访问 http://localhost
```

### 常用命令
```bash
docker compose up -d          # 启动
docker compose down           # 停止
docker compose restart        # 重启
docker compose logs -f        # 查看日志
docker compose up -d --build  # 重新构建
```

---

## 📱 功能一览

| 功能 | 说明 |
|---|---|
| 🏥 **体质测试** | 27 题标准化问卷 → 九种体质判定 → 九维雷达图 |
| 🤖 **AI 药膳** | 根据体质调用 LLM 生成个性化食疗方案 |
| 🌿 **药材库** | 626 味药材百科查询，支持搜索/筛选 |
| 🔒 **安全合规** | 急症拦截 · 白名单校验 · 输出过滤 |
| 📊 **问诊记录** | 历史记录查看 · 体质变化趋势图 |
| 🔐 **用户系统** | 注册/登录 · 数据隔离 |

---

## 🏗️ 技术架构

```
前端 (Vue 3 + Vant 4)  →  后端 (FastAPI + LangGraph)  →  Ollama / DeepSeek
     10 页面                    7 智能体节点                   LLM 推理
     SSE 流式                   RAG 检索增强                   药膳生成
     九维雷达图                 安全合规三层闸
```

---

## 📁 项目结构

```
├── backend/                 # 后端服务
│   ├── app/                 # FastAPI 应用
│   │   ├── domain/          # 领域层（体质判定、药材匹配、安全合规）
│   │   ├── orchestration/   # LangGraph 多智能体编排
│   │   ├── rag/             # RAG 检索层
│   │   └── api/             # REST + SSE 接口
│   ├── data/                # 药材数据集
│   └── tests/               # 241 个测试用例
├── frontend/                # 前端 H5
│   └── src/
│       ├── views/           # 10 个页面
│       └── components/      # 6 个组件
├── docker-compose.yml       # 一键启动配置
└── deploy/                  # 部署配置
```

---

## 📊 关键数据

| 指标 | 数值 |
|---|---|
| 药材数据 | 604 味唯一药材 + 106 种药食同源 |
| RAG 知识库 | 734 片切片 |
| 后端测试 | 241 用例，覆盖率 87% |
| 体质判定 | GB/T 46939—2025 确定性计分 |

---

## ⚠️ 注意事项

- 本系统**不做疾病诊断**，推荐药材仅限国家药食同源目录
- 默认使用 mock LLM（完全离线），如需 AI 药膳功能需配置 Ollama 或 DeepSeek API
- 首次启动需要构建镜像，约需 3-5 分钟

---

## 📄 开源协议

MIT License