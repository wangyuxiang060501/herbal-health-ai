# API 接口速查

- 标题：中医药智慧康养系统
- 版本：0.2.0-p2
- 接口数：29

> 由 `scripts/export_openapi.py` 从代码导出，与实现同步。

| 方法 | 路径 | 说明 | 分组 |
| --- | --- | --- | --- |
| GET | `/` | 健康检查 |  |
| GET | `/api/v1/consultation/graph` | 问诊状态图（LangGraph 拓扑可视化） | 问诊会话（核心闭环） |
| POST | `/api/v1/consultation/start` | 开始问诊 | 问诊会话（核心闭环） |
| POST | `/api/v1/consultation/stream` | SSE：边跑状态图边推送（节点级事件） | 问诊会话（核心闭环） |
| GET | `/api/v1/consultation/user/history` | 问诊历史 | 问诊会话（核心闭环） |
| GET | `/api/v1/consultation/user/trend` | 体质变化趋势 | 问诊会话（核心闭环） |
| GET | `/api/v1/consultation/{consultation_id}` | 问诊详情 | 问诊会话（核心闭环） |
| POST | `/api/v1/consultation/{consultation_id}/answer` | 提交追问回答 | 问诊会话（核心闭环） |
| GET | `/api/v1/consultation/{consultation_id}/stream` | SSE 流式输出 | 问诊会话（核心闭环） |
| GET | `/api/v1/herbs` | 药材列表 | 药材知识（查询层） |
| GET | `/api/v1/herbs/categories` | 药材类别列表 | 药材知识（查询层） |
| GET | `/api/v1/herbs/meridians` | 归经统计 | 药材知识（查询层） |
| GET | `/api/v1/herbs/search` | 药材搜索 | 药材知识（查询层） |
| GET | `/api/v1/herbs/{herb_id}` | 药材详情 | 药材知识（查询层） |
| GET | `/api/v1/meta/cache` | 热点缓存命中率（6.2.1） | 元信息 |
| GET | `/api/v1/meta/config` | 运行期配置摘要（不含密钥） | 元信息 |
| GET | `/api/v1/meta/constitutions` | 九种体质说明 | 元信息 |
| GET | `/api/v1/meta/dataset` | 双层数据集概况 | 元信息 |
| GET | `/api/v1/meta/llm` | LLM provider 状态与用量 | 元信息 |
| GET | `/api/v1/meta/questionnaire` | 体质问卷结构 | 元信息 |
| GET | `/api/v1/rag/explain` | 两路召回对比（证明混合检索有效） | RAG 知识检索（P3） |
| GET | `/api/v1/rag/search` | 混合检索 | RAG 知识检索（P3） |
| GET | `/api/v1/rag/status` | 知识库索引状态 | RAG 知识检索（P3） |
| POST | `/api/v1/safety/probe-herbs` | 候选药材安全裁决 | 安全合规（BC7） |
| POST | `/api/v1/safety/probe-output` | 输出文本安全过滤 | 安全合规（BC7） |
| GET | `/api/v1/safety/rules` | 安全规则摘要 | 安全合规（BC7） |
| GET | `/api/v1/user/history` | 问诊历史 | 历史档案（BC6） |
| GET | `/api/v1/user/trend` | 体质变化趋势 | 历史档案（BC6） |
| GET | `/health` | 健康探针 |  |
