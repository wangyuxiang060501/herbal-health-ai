# 前端 H5（Vue 3 + Vant 4）

移动端优先的中医药智慧康养 H5，对应《开发步骤清单》第五阶段。

## 技术栈

| 用途 | 选型 |
| --- | --- |
| 框架 | Vue 3（`<script setup>`）+ Vite 5 |
| UI | Vant 4（全量引入） |
| 状态 | Pinia |
| 路由 | Vue Router 4（路由懒加载，构建时分包） |
| HTTP | Axios（`/api/v1` 前缀，dev 期由 Vite 代理到后端 8000） |
| 图表 | ECharts 5（九维体质雷达图、体质趋势） |
| 图片导出 | html2canvas（药膳卡片保存为图片，动态 import 分包） |
| 适配 | postcss-px-to-viewport-8-plugin，设计稿 375px → vw |
| 测试 | Vitest + @vue/test-utils + happy-dom |

## 启动

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

后端需同时运行（默认 `http://127.0.0.1:8000`），Vite 已配置 `/api` 代理：

```bash
cd backend && python -m uvicorn app.main:app --port 8000
```

### ⚠️ 本机构建必须重定向临时目录

esbuild 在本机会因 `Access is denied` 无法删除系统 TEMP 文件，构建/测试前需要：

```bash
mkdir -p .tmp
TMP="D:\\herbal\\frontend\\.tmp" TEMP="D:\\herbal\\frontend\\.tmp" npm run build
TMP="D:\\herbal\\frontend\\.tmp" TEMP="D:\\herbal\\frontend\\.tmp" npm test
```

否则会看到 `[vite:esbuild-transpile] remove ... Access is denied`——此时代码本身没问题，
只是最后的临时文件清理步骤失败。

## 目录结构

```
src/
├── api/index.js           统一请求层 + 业务码常量
├── composables/useSSE.js  POST 型 SSE 客户端（原生 EventSource 不支持 POST）
├── components/            TabBar / DisclaimerModal / HerbCard / RecipeCard
│                          / StreamChat / LoadingState
├── views/                 Home / HerbList / HerbDetail / Test / Result
│                          / Recipe / Mine / HistoryDetail / Login / About
├── router/index.js        路由 + 免责声明守卫
├── stores/                user（本地身份）/ consult（问卷草稿与结果）
└── styles/global.css      设计变量与基础样式
```

## 页面与已联调接口

| 页面 | 路由 | 主要接口 |
| --- | --- | --- |
| 首页 | `/` | `meta/dataset`、`meta/constitutions`、`meta/llm` |
| 药材库 | `/herbs` | `herbs`（分页/筛选）、`herbs/search`、`herbs/categories`、`herbs/meridians` |
| 药材详情 | `/herbs/:id` | `herbs/{id}`、`safety/probe-herbs` |
| 体质测试 | `/test` | `meta/questionnaire`、`consultation/stream`（SSE） |
| 结果页 | `/result/:id` | `consultation/{id}` |
| 药膳页 | `/recipe/:id` | `consultation/{id}` |
| 我的 | `/mine` | `consultation/user/history`、`consultation/user/trend` |
| 记录详情 | `/history/:id` | `consultation/{id}` |
| 关于 | `/about` | `meta/dataset`、`meta/config`、`safety/rules`、`consultation/graph` |

## 关键实现说明

**SSE 流式**：后端流式接口是 `POST /api/v1/consultation/stream`，原生 `EventSource` 只支持 GET，
因此 `useSSE.js` 用 `fetch + ReadableStream` 手工解析 SSE 帧，并处理了分块跨帧（粘包/半包）。
节点级 `node` 事件直接驱动进度展示，不是前端伪造的假进度。

**业务码透出**：急症拦截（40301）、安全拦截（40302）等业务异常以 **HTTP 200** 返回，
只在响应体 `code` 字段体现。Axios 拦截器解包业务码，前端据此弹红色警示而非通用错误提示。

**安全相关展示**：药材详情页真实调用 `safety/probe-herbs` 展示裁决结果
（附子等品种显示"不得进入药膳方案"及替换品种）；结果页展示被拦截记录。

**问卷**：9 维度 × 3 题共 27 题，题面与 1–5 级评分标签全部来自
`GET /api/v1/meta/questionnaire`，前端不硬编码题目，标准原文更新后无需改前端。

## 已知限制

- **后端暂无用户认证**（`/api/v1/auth` 属后续阶段），登录/注册页只写入浏览器本地存储，
  用于区分个人历史记录，不涉及密码与真实短信。
- **真机测试未完成**（iOS Safari / Android Chrome），目前只在构建与组件测试层面验证。
- 药膳生成（Agent3）由后端 `enable_recipe` 开关控制，测试页可手动开启；
  关闭时药膳页给出基于推荐药材的代茶饮组合。

## 测试

```bash
TMP="D:\\herbal\\frontend\\.tmp" TEMP="D:\\herbal\\frontend\\.tmp" npm test
```

覆盖：6 个公共组件的渲染与状态分支、10 个页面的挂载（用于抓运行时错误）、
SSE 帧解析（含跨帧粘包、abort、急症 error 事件）。
