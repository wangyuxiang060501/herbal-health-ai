# 前端 H5（P4 阶段）

## 状态：未开工

本目录当前只有占位文件。按 `起步路线.md` 五的 18 周路线图，前端属于 **P4（W9–W11）**，
本轮交付范围为 **P0 地基 + P1 核心闭环（后端）**，故未实现页面。

## 开工时从哪里拿资料

后端已经把地基铺好，前端开工时不需要猜接口：

| 需求 | 现成资源 |
|---|---|
| 接口契约 | 启动后端后打开 `http://127.0.0.1:8000/docs`（Swagger 已全量可用） |
| 问卷结构（27 题 / 9 题快速版） | `GET /api/v1/meta/questionnaire[?mode=quick]` |
| 九种体质说明文案 | `GET /api/v1/meta/constitutions` |
| 药材列表/搜索/筛选 | `GET /api/v1/herbs`、`/search`、`/categories`、`/meridians` |
| 问诊闭环 | `POST /api/v1/consultation/start` → `POST /{id}/answer` |
| 流式打字机 | `GET /api/v1/consultation/{id}/stream?phase=interpretation\|recommend` |
| 历史与趋势图 | `GET /api/v1/user/history`、`GET /api/v1/user/trend` |
| 数据分层展示逻辑 | 返回值中的 `is_food_medicine` / `usage_policy` 字段 |

## 计划中的页面（`最终效果与使用步骤.md` 为 UI 验收基线）

首页 · 体质测试页 · AI 追问页（SSE 打字机）· 体质结果页（9 维雷达图）·
药膳推荐页 · 药材库页 · 我的（含趋势图）· 问诊记录详情

技术栈：Vue 3 + Vant 4 + Pinia + Vite + ECharts（见 `开发步骤清单.md` 附录）。
