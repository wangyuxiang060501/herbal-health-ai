# 参考文献 PDF 核验报告

> ## ⚠️ 本报告为**历史记录**（核验时点：2026-10-08 16:35 前后）
> 本报告描述的是**文献库重建之前**的状态：当时目录内有 14 个 PDF，其中 **7 篇张冠李戴**。
>
> **该问题已修复。** 修复后的文献库见 [参考文献/参考文献清单.md](参考文献/参考文献清单.md)：
> 7 篇错误文件已删除，改为 **19 篇逐篇核验过的文献**（16 篇 2025—2026 年 + 3 篇经典），
> 文件名内嵌 arXiv 编号，并已通过自动化验收（每个 PDF ↔ 清单条目一一对应，编号/标题吻合，无重复）。
>
> 本报告保留作为**问题发现过程的证据**，不再反映当前目录内容。

- 核验对象：`D:\herbal\参考文献\` 下 14 个 PDF（只读核验，未修改任何文件）
- 核验方法：PyMuPDF 1.24.11 逐页 `get_text` + 页级图像计数 + 文件 SHA-256 / 全文规范化 SHA-256 去重；首页文本与 arXiv 官方元数据双向比对（arXiv API `export.arxiv.org/api/query` 与 `arxiv.org/abs/<id>` 页面 `citation_title`）
- 核验时间：2026-10-08

## 一、逐文件核验表

| 文件名 | 真实标题（首页实测） | 真实 arXiv 号 | 页数 | 是否可提取文本 | 与清单是否一致 |
|---|---|---|---|---|---|
| 01_LLM_Survey_2025.pdf | A Survey of Large Language Models | 2303.18223v19 | 144 | 是（860,641 字符，0 空白页） | **一致**（版本标注为 v18/v19，非仅"2025 更新版"） |
| 02_Multi_Agent_LLM_2025.pdf | Large Language Model based Multi-Agents: A Survey of Progress and Challenges | 2402.01680v2 | 15 | 是（79,035 字符） | **部分一致**（主题一致；标题措辞不同，非清单所写标题） |
| 03_Agentic_RAG_2025.pdf | ReDeEP: Detecting Hallucination in Retrieval-Augmented Generation via Mechanistic Interpretability | 2410.11414v2 | 23 | 是（80,267 字符） | **不一致**（同 ID，但主题完全不同：幻觉检测，非 Agentic RAG 综述） |
| 04_GraphRAG_Microsoft_2025.pdf | From Local to Global: A GraphRAG Approach to Query-Focused Summarization | 2404.16130v2 | 26 | 是（89,607 字符） | **部分一致**（同一篇微软 GraphRAG 论文；标题为论文标题，清单写的是微软博客标题） |
| 05_SelfRAG_2025.pdf | Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection | 2310.11511v1 | 30 | 是（105,748 字符） | **一致** |
| 06_LLM_Reasoning_2025.pdf | A nonsmooth path-connectedness relation in the real plane | 2501.07916v2 | 5 | 是（12,197 字符） | **不一致**（数学论文 math.LO，与 LLM 推理综述完全无关） |
| 07_DeepSeek_R1_2025.pdf | DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning | 2501.12948v2 | 86 | 是（229,507 字符） | **一致** |
| 08_RAPTOR_2025.pdf | RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval | 2401.18059v1 | 23 | 是（77,199 字符） | **一致** |
| 09_LangGraph_2025.pdf | DB-PAISA: Discovery-Based Privacy-Agile IoT Sensing+Actuation | 2412.11572v1 | 16 | 是（95,306 字符） | **不一致**（物联网隐私安全论文 cs.CR，与 LangGraph 无关） |
| 10_Medical_LLM_2025.pdf | Time-Dependent Network Topology Optimization for LEO Satellite Constellations | 2501.13280v1 | 10 | 是（56,024 字符） | **不一致**（低轨卫星组网论文 cs.NI，与医学 LLM 综述无关） |
| 11_TCM_AI_2025.pdf | HingePlace: Harnessing the neural thresholding behavior to optimize Transcranial Electrical Stimulation | 2502.01382v1 | 85 | 是（150,928 字符） | **不一致**（脑电刺激优化论文 eess.SY，与中医药 AI 无关） |
| 12_Agent_Framework_2025.pdf | MMAU: A Holistic Benchmark of Agent Capabilities Across Diverse Domains | 2407.18961v3 | 33 | 是（83,483 字符；1 页仅 31 字符，纯图页） | **不一致**（Apple 的 Agent 评测基准，非"Agent 框架综述"） |
| 13_RAG_Survey_2025.pdf | Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG | 2501.09136v4 | 42 | 是（115,224 字符） | **不一致**（真实为 Agentic RAG 综述；清单把它写成"RAG for LLMs 综述"，且与 03 的题名重复） |
| 14_Healthcare_AI_Agent_2025.pdf | Cutting a unit square and permuting blocks | 2501.13844v2 | 23 | 是（49,868 字符） | **不一致**（组合数学论文 math.CO，与医疗 AI Agent 无关） |

文件大小（字节）：01 5,853,703；02 1,243,493；03 1,131,094；04 6,893,854；05 1,405,127；06 120,689；07 5,034,998；08 2,547,113；09 7,447,927；10 4,633,289；11 13,104,675；12 5,813,409；13 14,269,078；14 590,462。

## 二、严重问题（附提取原文证据）

**S1. 7 个文件的题目为"张冠李戴"——文件不是清单声称的那篇论文。**

| 文件 | 清单声称 | 首页实测证据（原文片段） | arXiv 官方标题（arxiv.org/abs 实测） |
|---|---|---|---|
| 06 | A Survey on LLM Reasoning (2501.07916) | "…path-connectedness equivalence rela-tion of the Knaster continuum…" | A nonsmooth path-connectedness relation in the real plane |
| 09 | LangGraph: Multi-Agent Orchestration Framework (2412.11572) | "…IoT devices are becoming increasingly com-monplace…" | DB-PAISA: Discovery-Based Privacy-Agile IoT Sensing+Actuation |
| 10 | A Survey on LLMs in Medicine (2501.13280) | "…LEO satellite networks, exemplified by SpaceX's Starlink…" | Time-Dependent Network Topology Optimization for LEO Satellite Constellations |
| 11 | Traditional Chinese Medicine and AI (2502.01382) | "…Transcranial Electrical Stimulation (tES) is a neuromodula-tion technique…" | HingePlace: Harnessing the neural thresholding behavior to optimize Transcranial Electrical Stimulation |
| 12 | Agent Frameworks: A Comprehensive Survey (2407.18961) | "…we introduce the Massive Multitask Agent Understanding (MMAU) benchmark…" | MMAU: A Holistic Benchmark of Agent Capabilities Across Diverse Domains |
| 14 | Healthcare AI Agents: A Survey (2501.13844) | "…Consider a random permutation of kn objects that permutes n disjoint blocks…" | Cutting a unit square and permuting blocks |
| 03 | Agentic Retrieval-Augmented Generation (2410.11414) | "…Retrieval-Augmented Generation (RAG) models are designed to incorporate ex-ternal knowledge…"（首页标题实为 ReDeEP 幻觉检测） | ReDeEP: Detecting Hallucination in Retrieval-Augmented Generation via Mechanistic Interpretability |

即：14 篇中 7 篇的 PDF 与清单描述的论文不是同一篇，其中 6 篇（06/09/10/11/12/14）主题领域完全不同（数学、物联网安全、卫星网络、脑电刺激、Agent 基准、组合数学），属"引用了根本没有的文献"级别的问题。清单中的 arXiv 编号本身也未指向所声称的论文。

**S2. 清单声称的多篇论文在 arXiv 上不存在（或编号根本对不上）。** 按标题检索 arXiv API 的结果：
- "Traditional Chinese Medicine and Artificial Intelligence" → 无任何结果；"Healthcare AI Agents" → 仅命中 AGENT-O (2608.28345)，非清单所称 2501.13844。
- 清单所写的 "LangGraph: Multi-Agent Orchestration Framework"、"Agent Frameworks: A Comprehensive Survey" 均非真实论文标题；arXiv 上无标题为 "A Survey on Large Language Model Reasoning" 的论文。
- 清单所写的 "A Survey on Retrieval-Augmented Generation for Large Language Models"（2501.09136）实际对应 2312.10997 "Retrieval-Augmented Generation for Large Language Models: A Survey"，而 2501.09136 实为 "Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG"——即清单把 03 与 13 两篇的题名/编号对应关系搞混了。

**S3. 题名与编号被重复使用。** 清单中 "Agentic Retrieval-Augmented Generation" 之名被同时挂在 03 与（近似地）13 上，而 03 的实际内容与 Agentic RAG 无关。

## 三、小问题

1. **版本/年份标注失实**：清单声称 14 篇"全部为 2025-2026 年发表/更新"，但首页实测版本为 2303.18223v19、2402.01680v2、2310.11511v1、2401.18059v1、2407.18961v3、2412.11572v1；PDF 元数据 CreationDate 分别为 D:20240422001222Z、D:20231019002818Z、D:20240201014546Z、D:20240819000724Z、D:20241217022317Z，均为 2023-2024 年投递稿。
2. **PDF 元数据缺失**：除 01、07、09、11、13、14 外，其余文件的 `/Title`、`/Author` 为空（`meta.title = ''`）；01、07、13、14 为 arXiv GenPDF 重制版，`CreationDate/ModDate` 为空字符串。故不能靠 PDF 元数据识别文献，只能依据首页正文。
3. **03 的内部证据自相矛盾（印厂层面）**：首页页眉为 "Published as a conference paper at ICLR 2025"，但该文实际收录于 ICLR 2025 的 ReDeEP，与文件名所指主题无关，属"文件名-注册信息-内容"三方不一致。
4. **07 的正文分布不均**：单页最少 296 字符（多为图表/附录页）；12 有一页仅 31 字符，为纯图页——均属正常排版，不影响可读性。
5. **04 的标题错配来源可解释**：清单用的是微软官方博客文章名 "GraphRAG: Unlocking LLM Potential through Knowledge Graphs"，而 PDF 是论文正式标题；引用时应改用论文标题。
6. **文件名 2025 后缀易误导**：如 06_LLM_Reasoning_2025.pdf、10_Medical_LLM_2025.pdf 等后缀年份与内容无关，建议重命名。

## 四、重复文件检查（任务第 5 项）

**未发现任何重复。** 证据：14 个文件的 SHA-256 两两互不相同；全文规范化文本 SHA-256 也无任何两组相同；页面数组合（144/15/23/26/30/5/86/23/16/10/85/33/42/23）与字符数组合两两互异。即不存在"同一篇论文被下载到两个文件名"的情况（03 与 13 虽同名相近，但内容确为两篇不同论文）。

## 五、总体结论

14 个文件本身都是**真实、完整、可提取文本的正规论文 PDF**（非扫描件、非占位文件、非损坏、非网页打印件），无重复下载；但**清单描述与文件内容严重不符：仅 4 篇完全一致、2 篇部分一致，另有 7 篇（03、06、09、10、11、12、14）为张冠李戴的错误文献，且这些错误 arXiv 编号在清单中同样错误，另有多篇清单标题在 arXiv 上根本不存在——该参考文献清单在修正前不可直接用于论文引用。**
