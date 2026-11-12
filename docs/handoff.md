# 交接：用 LangGraph 重写 ARag（日语版）

> **歴史的な資料（2026-11-08 着手時の計画）。** P0〜P5 の段階はすでに実装済み（`specs/001`〜）。今の決まりは `AGENTS.md`、運用は `docs/operations.md`、構成は `docs/architecture.html`。この文書は「なぜこう作ったか」（旧版との違い・ライセンスの原則・旧ソースの地図）を残すために置いている。

> 给新 session 的 Claude 读。旧项目（只读参考）：`/Users/ansen/Documents/Projects/playground/a-rag`
> 新项目就是本仓库：`/Users/ansen/Documents/Projects/playground/arag-lg`。不要改旧仓库。
> 旧仓库基准：`main@83b37005`（`c3ae45e` 之后只多了品牌标识更新：`BrandMark` 换成「小写 a + 上标引用方块」，PWA 图标与 favicon 同步更新）。
> 原则：**UI/UX 保持旧版观感；后端不必忠实旧实现，用当下最好的做法。** 版本号以官方 release notes 为准，开工时先查最新再锁定。

## 0. 目标与边界

- **目标**：用 LangChain 1.x / LangGraph 1.x 重写智能检索问答系统，**只做日语**。
- **本次不做**：能力包（`packages/cap-*`，成都瑞奇专用，中文）、工作日历、分享链接、PWA、多团队高级功能。
- **沟通**：与用户中文对话；新项目代码注释、提交信息用日语（Conventional Commits，例 `feat: 〜を追加`）。

## 1. 架构

```
Next.js 16（UI + 认证）            Python（FastAPI + LangChain/LangGraph）
  ├ Better Auth（会话/邮件验证/重置）   ├ Agent：create_agent + middleware
  ├ 页面、上传直传代理                 ├ 检索：Qdrant Query API（服务端融合）→ rerank
  └ 调 Python：OpenAPI 生成的 TS 客户端 ├ 入库：Docling → 结构感知分块 → 上下文增强 → 向量化
        │  SSE（LangGraph 原生流）      ├ 后台 run：与 HTTP 解耦，可续传/取消
        └──────────────────────────▶  └ 数据：threads/messages/citations/documents 全归 Python
Postgres（auth 表归 Next，其余归 Python）/ Qdrant / Redis（任务队列 + run 事件流；Valkey 可无缝替换）
推理：TEI 或 Infinity 容器（embedding / rerank），不再手写推理服务
追踪：Langfuse 自托管（OpenTelemetry）
```

### 与旧版相比的主要变化（及理由）

| 领域 | 旧版 | 新做法 | 理由 |
|---|---|---|---|
| Agent 编排 | TS 手写 `streamText` 循环 + StepBus | **`create_agent` + middleware**；只有确定性流程（入库管线等）才手写 StateGraph | LangChain 1.0 的标准做法，运行在 LangGraph 上，自带 checkpoint、HITL；CRAG 评分/改写重试、模型降级、长对话摘要都做成 middleware，可单独测试 |
| 融合 | Python 侧自己做 RRF | **Qdrant Query API**：dense + sparse 两个 prefetch，服务端 RRF（带权重、k 可调；需较新 Qdrant 版本）或 DBSF | 少一次数据往返，参数可调；先用自己的标注验证融合是否优于单路 |
| 精排 | cross-encoder reranker | 保留 reranker；**可选**评测 BGE-M3 multivector（late interaction）在 Qdrant 内重打分 | 后者更便宜，用 eval 决定 |
| 分块 | 解析块 + 检索后 ±1 相邻扩展 | **Docling HybridChunker**（按标题层级、按 token 上限）+ **父子块**：小块检索，返回所在章节 | 比相邻扩展更符合文档结构 |
| 上下文增强 | 无（rag 服务不能调 LLM） | 入库时用便宜模型给每块生成一句「この塊は〇〇文書の△△章で…」再向量化（Contextual Retrieval），利用 prompt caching 降成本 | 旧版的架构障碍消失了；对省略主语、指代多的日语文档尤其有效 |
| Agent 工具 | `retrieve`、`fetch_document` | `search`（带过滤：文档、类型、日期）+ **`keyword_search`**（型号、条款编号等精确匹配）+ **`list_documents` / `get_outline` / `read_section`** | 2026 年的 agentic search：让 agent 像人一样先看目录再读章节，而不只做向量检索 |
| 引用 | `[n]` 标记 + 编号注册表 | 保留 `[n]` 与注册表；生成后**校验每个 `[n]` 真实存在**、可选按句做忠实度检查（middleware） | 防止幻觉引用 |
| 数据归属 | web 管 users/threads/messages，rag 管 documents | **Next 只管认证表**；对话、引用、文档都归 Python（agent 本来就写这些） | 一处写对话，消除跨服务双写 |
| 前后端接口 | 手写 `rag-client.ts` | FastAPI 的 OpenAPI → `openapi-typescript` 生成客户端 | 类型自动同步 |
| 认证 | 手写 JWT + 十几个 auth 路由 | **Better Auth**（邮箱密码、邮件验证、重置、会话列表、限流）；Python 侧验证其签发的 JWT | 大幅减少自写安全代码 |
| 推理服务 | 自写 FastAPI 推理服务 | **TEI 或 Infinity** 容器 | 现成、带批处理；**开工前确认它们对 BGE-M3 sparse/ruri 的支持**，不支持的部分才自写 |
| 可观测性 | JSON 日志 + Prometheus | 保留日志与 request-id；LLM 调用走 **OpenTelemetry → Langfuse**，含 token 成本、用户 👍👎 关联到 trace | 线上问题能追到具体一次检索/生成 |

### 关键选型（做成可替换，用 eval 决定）

| 环节 | 默认 | 对比候选 |
|---|---|---|
| 解析 | Docling（表格结构、OCR、图片导出） | 其他宽松许可解析器（MinerU 若为 AGPL 则不用） |
| 图片 | 入库时 VLM 生成图片说明 → 作为 text 块入索引；图片本身只显示 | 视觉检索（ColPali 类）留作后续 |
| 向量 | BGE-M3（dense + sparse） | 日语特化 `cl-nagoya/ruri-v3-*` |
| 关键词 | Qdrant BM25（sparse + IDF modifier），日语用 **Sudachi** 分词 | BGE-M3 sparse |
| 重排 | bge-reranker-v2-m3 | ruri reranker、BGE-M3 multivector |
| LLM | `init_chat_model` 多供应商（OpenAI / Anthropic / DeepSeek），模型降级用 middleware | — |

### 授权原则（硬性要求：不受商业限制）

- **优先宽松开源许可（MIT / Apache 2.0 / BSD / PostgreSQL）**。不用 AGPL/GPL（网络服务传染）、需要授权密钥的组件，以及限制会落到我们自己业务上的许可。RSAL/SSPL/ELv2 这类「只禁止把该软件本身当托管服务卖」的许可，作为内部组件使用不影响商用，可以用（逐个确认限制条款）。
- **不依赖任何需联网验证许可证的服务**（客户内网部署也要能跑）。
- 托管 SaaS（LangSmith、Langfuse Cloud、Better Auth 付费服务等）只能是可选项，系统没有它们也完整可用。
- 新增依赖时在 `specs/000-overview/licenses.md` 记一行：组件、许可证、确认日期、来源链接。CI 里加许可证扫描（Python：`pip-licenses`；JS：`license-checker` 等），出现禁用许可即失败。

| 组件 | 许可证（开工时以官方再确认） | 备注 |
|---|---|---|
| LangChain / LangGraph 库 | MIT | **不用** LangGraph Agent Server（ELv2 + 付费密钥） |
| Next.js / React / Tailwind | MIT | |
| FastAPI / Pydantic / SQLAlchemy / Alembic | MIT | |
| Better Auth | MIT | 库本身免费无限制；官方付费仪表盘/基础设施服务不使用 |
| PostgreSQL | PostgreSQL License | |
| Qdrant | Apache 2.0 | 自托管；Qdrant Cloud 不使用 |
| Redis 8.x | RSALv2 / SSPLv1 / AGPLv3 三选一 | 选 RSALv2：作为应用内部组件可自由商用，唯一限制是不能把 Redis 本身当托管服务对外提供；不修改 Redis 源码。若客户要求 OSI 开源，换 Valkey（BSD-3，协议兼容，零代码改动） |
| Docling | MIT | 默认解析器 |
| MinerU | **AGPL-3.0（需确认最新）** | 若仍为 AGPL 则**不使用**，旧版的 MinerU 适配器不迁移 |
| TEI / Infinity | Apache 2.0 / MIT（需确认） | |
| BGE-M3 / bge-reranker-v2-m3 | MIT / Apache 2.0 | 模型权重许可也要记录 |
| ruri-v3 | Apache 2.0（需确认） | |
| Sudachi（SudachiPy + 词典） | Apache 2.0 | |
| Langfuse | MIT（核心）；`ee` 目录为商业许可 | 只用 MIT 部分；或改用纯 OpenTelemetry + 自建面板 |
| Aegra | Apache 2.0 | 可选 |
| LLM API（OpenAI / Anthropic / DeepSeek） | 各家服务条款 | 按量付费的外部服务，属于运行成本而非授权限制；需要完全离线时可接 vLLM/Ollama 跑开源权重模型 |

## 2. 流式传输与 UI 保持

1. **前端资产直接复制**：`src/components/**`（含 `*.stories.tsx`）、`src/app/globals.css`（`@theme inline` token）、`layout.tsx` 字体加载（日语只要 Inter + Noto Sans JP）。
2. **线上传输用 LangGraph 原生 stream mode，只开 `messages` + `custom`**（不开 `values`：每步发整个 state；不开 `events`/`debug`：太啰嗦）。
   - `messages`：回答 token、工具调用参数流（可提前显示「検索中: 〇〇」）、`usage_metadata`。
   - `custom`：节点/middleware 里用 `get_stream_writer()` 发应用事件——检索子阶段（改写/检索/重排/评分、耗时、命中数）、引用登记（编号→出处）、拒答原因。**payload 定义成有类型的契约**（JSON Schema → pydantic + zod），前端不依赖图的节点名。
3. **服务端形态**：LangGraph Agent Server 的自托管生产使用需要 LangSmith 授权（Elastic License 2.0，社区与论坛信息，开工时以官方为准），因此**默认自己用 FastAPI 承载**：
   - run 在后台任务里执行，与 HTTP 连接解耦；事件写入 Redis Stream，前端断线后按 last-event-id 续传；支持取消。旧版 `src/app/api/chat/runs/[runId]/{stream,cancel}` 可参考思路。
   - 若想直接用 `@langchain/langgraph-sdk/react` 的 `useStream`（自带重连、分叉重生成、interrupt），可评估 Apache 2.0 的兼容实现 **Aegra**；成熟度自行判断，不作为默认。
4. **前端数据层重写、组件不动**：写一个 hook 读流，再写 selector 把消息 + custom 事件映射成旧组件的 props（旧 `ToolCall`、`CitationMap`、`Source` 类型作为 view model 继续用）。`Messages`、`ToolSteps`/`AgentActivity`、`AnswerFooter`、`src/components/sources/**` 引用侧栏保持原样。
   - 旧协议 `src/lib/types.ts` 的 `AgentEvent` 作对照：新数据层要能还原同样的信息。
5. **可以顺手加的 UX**（原生能力带来的）：编辑问题后从该点重新生成、刷新后接着看生成中的回答、需要确认时暂停（interrupt）。
6. **i18n**：保留 `t()` 调用形式，只放 ja 字典（来自旧 `src/i18n/locales/ja/**`）。
7. **视觉回归**：新旧两版跑起来后，Playwright 对关键页面截图比对（登录、空状态、对话中、引用侧栏、知识库、文档预览、管理首页）；Storybook story 原样迁移。
8. **界面规格以 Design System 为准**：https://claude.ai/artifact/QaGvknVyaiM1TwBwAHuNrY （claude.ai 私有 artifact，需在其 Share 菜单分享后他人才能打开）。依据旧仓库 `main@c3ae45e` 整理：
   - token：浅/深两套颜色、字体与 13 个字号样式、4px 间距、9 级圆角、3 级阴影、断点 769 / 1181px；品牌说明（日语文案原则、单一强调色、「选中只改颜色不加粗」、动效与交互状态）。
   - 资产：74 个线性图标、品牌标识（深色 / 白色）、PWA 图标。
   - 13 个组件的规格说明 + 静态预览：Composer、CitationMarker、AnswerProse、UserBubble、AnswerFooter、ToolSteps、ModelPicker（兼 Scope/Skill 选择器）、SourcePanel、ThreadItem、Toast、ConfirmModal、LoginCard、Button。预览是手写还原，**实现仍以复制旧组件源码为主**，Design System 用于核对与新页面照用。
   - 未收录：知识库列表、文档预览（表格/Mermaid/公式）、管理后台、设置弹窗各页、上传队列——这些直接参照旧源码。
9. **重写时顺手修正的偏离点**（旧版照抄会继承）：
   - **没有共用 Button / 输入框组件**，各处直接写 Tailwind 类。新项目按 Design System 的 Button（primary / danger / secondary / icon / text link）和 LoginCard 的输入框规格抽成共用组件。
   - **圆角不在阶梯上**：确认对话框按钮 9px、登录卡与移动端底部弹层 18px → 统一为 `radius-8` / `radius-16`。
   - **硬编码颜色**：`#B83A1F`（错误/差评/危险按钮）硬编码在 24 个组件文件里，应改用 `danger-ink` token；登录错误框的 `#F0CFC4` / `#FDF0EC` 也应 token 化。
   - **对比度不达标**（WCAG AA）：`muted-2` 在浅色底不到 3:1，只能放可有可无的提示；`muted` 在浅色 `bg` 上 4.40:1，小字略低于 4.5:1；强调色上的白字 3.12:1（按钮文字 600 字重勉强可接受，建议主按钮底色加深或字号 ≥ 14px）；深色主题 `danger-ink` 2.89:1，深色下应换更亮的错误色。调整后同步更新 Design System。

## 3. 分阶段（每阶段可独立演示）

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| P0 骨架 | monorepo（`web/` Next.js + pnpm、`api/` FastAPI + uv）、compose（postgres/qdrant/redis/TEI 或 Infinity）、CI、`specs/`、OpenAPI 客户端生成 | `docker compose up` 健康检查通过，CI 绿 |
| P1 入库 | 上传 → Docling → HybridChunker 父子块 → 上下文增强 → 向量化 → Qdrant；内容哈希去重；回收站 | 示例 7 份 PDF 入库，chunk/父章节可查 |
| P2 检索 | Qdrant 服务端混合检索 + rerank；检索 eval 搬过来 | 示例集 recall@5 ≥ 旧版（0.944~1.0），并做 RRF/DBSF、ruri/BGE-M3 对比 |
| P3 Agent | `create_agent` + 工具 + middleware（评分改写重试、引用校验、降级）；后台 run + 续传 | 聊天 UI 流式正常、引用可点、断线可续 |
| P4 Web 闭环 | Better Auth、线程列表、知识库视图、文档预览 | 旧版主要用户流程走通，截图比对通过 |
| P5 管理 | 成员、LLM key、模型目录、审计、分析（按优先级挑） | 按 spec 验收 |

## 4. 开发方式：SDD + TDD

- 每个功能先写 `specs/<编号>-<名称>/`：
  - `requirements.md`：EARS 验收条件（「〜のとき、システムは〜する」）
  - `design.md`：接口、数据结构、工具/middleware 设计
  - `tasks.md`：可勾选小任务，每条对应测试
- 先写失败测试再实现。`CLAUDE.md` 写明：无 spec 不写代码；spec 与代码同一个 PR。
- 可选 GitHub spec-kit；不引入就用上面的目录约定。

## 5. 评测与 CI

| 层 | 何时 | 内容 |
|---|---|---|
| 单元/契约 | 每个 PR | pytest + vitest；custom 流事件契约测试；selector 单元测试；middleware/工具用假模型（`FakeListChatModel` 等）测分支 |
| 组件 | 每个 PR | Storybook test + a11y |
| 检索质量 | 每个 PR（CPU 小集）/ nightly（全集） | recall@k、MRR、nDCG、fact_coverage，阈值门禁 |
| 回答质量 | nightly / 手动 | 引用召回/精度、事实覆盖、忠实度（LLM 评委）、工具调用数、token/成本、p50/p95、拒答率 |
| 线上评测 | 持续 | Langfuse 上按比例抽样线上 trace 用评委打分；用户 👍👎 关联 trace，差评自动进候选题库 |
| E2E | 合并前 | Playwright 主流程 + 截图比对 |

- **题库要扩充**：旧 `rag/eval/suites/agentic_rag_demo` 只有 6 题（日语，含跨页表格、图、例外条款、拒答），作为种子；用 LLM 从文档合成候选题，再人工筛选到 50+ 题，覆盖：精确型号/条款查询、跨文档比较、多跳、拒答、版本冲突。
- **评委要校准**：先人工标 20~30 条，确认评委与人一致再用于门禁；评委输出用结构化输出（JSON schema），避免旧版出现的「不是合法 JSON」。
- 旧版基线（`tools/answer-eval/`）：引用召回 1.0、精度 0.92~1.0、事实覆盖 1.0、忠实度约 0.79、工具调用约 6 次、p50 约 64s。目标：质量不降、忠实度上升、更快。

## 6. 旧项目里值得保留的设计

- **内容寻址**：同一文件只解析一次（content_hash 实体与知识库条目分离）；删除先进回收站。见 `docs/design/document-lifecycle.md`。
- **图片只显示**，图中文字（说明、流程图）作为独立 text 块入索引。
- **引用编号统一管理**：多次检索不重号，`[n]` 与侧栏原文一一对应。
- **拒答原因**：用于分析页「知识缺口」统计。
- **大 PDF 按页窗口分批解析**，控制内存峰值。
- **日志**：结构化 JSON + `X-Request-Id` 贯穿；服务端不用 `console.*`/`print`。
- **安全**：检索到的文档内容当数据不当指令（提示词里明确隔离，防文档内提示注入）。

## 7. 旧项目源码地图（只读参考）

| 关注点 | 位置 |
|---|---|
| Agent 循环 / 提示词 / 配置 | `src/lib/agent/run.ts`、`prompts.ts`、`config.ts`、`tools.ts`、`grade.ts`、`verify.ts`、`citations.ts` |
| 流协议 / 后台 run | `src/lib/types.ts`（`AgentEvent`）、`src/lib/chat-stream.ts`、`src/lib/chat-run.ts`、`src/app/api/chat/**` |
| 聊天 UI | `src/components/chat/**`、`src/components/sources/**` |
| 知识库 / 文档预览 | `src/components/library/**`、`src/components/documents/**`、`src/app/api/documents/**` |
| 外壳 / 侧栏 / 设置 | `src/components/{shell,sidebar,workspace,modals,settings,onboarding}` |
| 管理后台 | `src/components/admin/**`、`src/app/admin/**` |
| 认证 | `src/lib/auth.ts`、`src/proxy.ts`、`src/app/api/auth/**` |
| 数据表 | `src/lib/db/schema.ts`、`rag/app/models.py` |
| 检索 / 入库 | `rag/app/retrieval/service.py`、`multihop.py`、`rag/app/worker.py`、`rag/app/parsing/` |
| 评测 | `rag/eval/`、`tools/answer-eval/` |
| 日语文案 | `src/i18n/locales/ja/**` |
| 视觉 token / 图标 | `src/app/globals.css`、`src/lib/constants.ts`（强调色）、`packages/capability-sdk/src/icons.tsx`；整理版见第 2 节的 Design System |

## 8. 新 session 的第一步

1. 查最新版本与授权（按第 1 节授权原则逐项确认）：LangChain/LangGraph、Qdrant（Query API 融合参数）、Docling、TEI/Infinity 对所选模型的支持、Better Auth、Next.js 16。结论写进 `specs/000-overview/decisions.md`。
2. 通读第 7 节文件，产出 `specs/000-overview/`：功能清单（MVP/后续）、页面清单、API 清单、数据模型。**先给用户确认范围**再动手。
3. 建 P0 骨架与 CI，提交；按 P1→P5 推进，每阶段跑对应 eval 并在 PR 里贴数字。
