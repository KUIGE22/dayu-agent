# 投资 Agent：AAPL 实战验收实施计划

- **日期**：2026-08-09
- **分支**：`feat/investment-agent-acceptance`
- **基线**：`7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`
- **Work unit**：`investment-agent-aapl-acceptance`
- **目标证券**：`AAPL`（Apple Inc.）
- **当前 gate**：`plan accepted / deterministic Slices 0–4 handoff-ready`
- **计划状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**

> DeepSeek + MiMo final corrective dual plan re-review 均已通过，Controller 已关闭全部 findings；deterministic Slices 0–4 已 handoff-ready，只实现和验证 deterministic contract、评分器、preflight/runner 安全边界与文档，不调用 SEC、Web、DeepSeek、MiMo，也不需要真实运行预算或凭据。Slice 5 仍是独立 **LIVE AUTHORIZATION REQUIRED** gate；只有 Controller 再次取得用户对精确价格快照、费用、Token、请求数、wall-clock 和外部调用的明确授权后才可执行。当前 plan acceptance 不授权任何 live 或付费调用。

### Revision changelog

- 2026-08-09 plan-fix：显式加入三组 SEC download、price snapshot material import 与 `process`，统一 package config/template 真源，收窄 processed 指纹、类型边界、evidence 两层契约、timeout 协议与人工质量三态。状态仅为等待双路 plan re-review，不代表 plan accepted。
- 2026-08-09 corrective plan-fix：将 package research asset 指纹扩展为 `research_templates/` canonical tree + 根级 `定性分析模板.md` 的 materialization 输入闭包，并明确 fixture/live `verify` 模式互斥。状态仅为等待 corrective dual plan re-review，不代表 plan accepted。
- 2026-08-09 final corrective plan-fix：PRR-001 保持关闭；按 PRR-002 将绝对 home 路径禁令精确限于 acceptance harness-owned outputs，对生产 validator artifacts 只记录 package-relative locator + SHA-256、不摘录/改写内容。状态仅为等待 final corrective dual plan re-review，不代表 plan accepted。
- 2026-08-09 plan closure：DeepSeek + MiMo final corrective re-review 均 pass，Controller 关闭 PR-001..004、P1..P8、PF-EXTRA-001、PRR-001、PRR-002，open High/Medium/Low 均为 0。deterministic Slices 0–4 handoff-ready；Slice 5 仍未获 live 授权。

## 1. 动机与第一性原理判断

现有仓库已经分别实现并测试了财报下载、双模型写作、研究模板选择、研究工件物化、工作簿、进度报告、source-map、dry-run monitoring plan、成本台账和回滚。真实问题不是“再造一条投资 Agent 管线”，而是缺少一个可复核的验收层，证明这些已有边界在同一个 AAPL 运行中真正闭合，并把以下事实绑定成一个不可含糊的 receipt：

1. 用了哪些截至某一时点的源文档；
2. DeepSeek 与 MiMo 分别承担了什么角色；
3. 写作、审计和预算门禁是否全部通过；
4. 最终报告是否覆盖投资主线、bear case、估值、催化剂与风险；
5. 重要判断是否能够追溯到来源，而不是只有“命令退出 0”；
6. research bundle、workbook、progress report、source-map 与 monitoring plan 是否健康；
7. 失败是否可恢复、输入是否可复现、模型请求、Token、成本和耗时是否可审计；
8. 本次结果是否沉淀为不依赖联网与付费模型的固定回归基线。

因此最佳路径是：**复用现有生产 CLI 和产物契约，只新增位于 `utils/` 的验收编排/评分器、固定 AAPL 验收语料和操作文档**。不得为了验收改写核心写作管线，也不得把一次性验收逻辑提升为自动交易或通用多标的产品能力。

## 2. Non-goals

- 不做下单、持仓、组合再平衡、自动交易或投资建议分发。
- 不做实时价格推送、live alerts、常驻 scheduler 或自动启用 monitoring job。
- 不接入新的付费数据商，不实现广泛的多 ticker/portfolio 验收框架。
- 不重写 `write`、research-template、Fins storage 或 Host 生命周期。
- 不让验收器直接读取 `workspace/portfolio/...` 私有目录；源文档盘点必须通过 `dayu.fins.storage` 仓储协议。
- 不要求模型输出逐字节可重复；可复现目标是输入、代码、配置、源文档清单、预算、命令、产物指纹和评分算法可重放。
- 不把 research workbook 的 37 个问题自动伪装成已回答。当前 workbook 是 `manual_review` 跟踪工件；报告质量与 workbook 进度必须分别陈述。
- 不把默认 unbound 的 source-map 手工翻成 `bound`，也不为了“全绿”伪造 monitoring readiness。
- 不在 CI、pytest 或普通 gate 中运行 SEC、Web、DeepSeek、MiMo 等真实外部调用。

## 3. 直接仓库证据与当前缺口

### 3.1 已有能力

| 证据 | 当前契约 | 对本计划的结论 |
|---|---|---|
| `README.md` 的 `download` 章节 | AAPL 可通过 SEC 下载；年报/季报与事件表单的默认窗口不完全相同；支持显式 forms/start/end | live lane 不依赖未验证默认，按 as-of 构建 10-K/10-Q/8-K+DEF14A 三组显式窗口 argv |
| `README.md` 的 `upload_material` / `process` 章节、`dayu/fins/pipelines/docling_upload_service.py` | `upload_material` 支持 `.md` 且 `MATERIAL_OTHER`；`process` 会同时处理 filing/material；Fins tools 可列出并引用 material | `prepare` 把已校验 JSON 确定性渲染为 Markdown material，在任何付费 write 前先 import，再一次 `process` |
| `README.md` 的 `write` 章节 | 支持 DeepSeek 主写、MiMo 审计、preflight、请求/Token/成本预算、`--research-template technology --materialize-research` | 真实写作复用一个受预算约束的正式 `write` 命令 |
| `dayu/config/prompts/manifests/write.json`、`audit.json` | 默认主写为 `deepseek-v4-pro`，默认审计为 `mimo-v2.5-pro-thinking` | 模型策略无需新增路由抽象 |
| `dayu/config/llm_models.json` | 两个模型均声明 usage 支持和 CNY 价格；凭据通过环境变量占位符引用 | receipt 只记录模型名、目录指纹、环境变量名称/是否存在，绝不记录值 |
| `dayu/assets/research_templates/common.md`、`technology.md` | 已包含反证、估值、催化剂、治理和组合决策；technology 包含科技经营、FCF、产品周期等问题 | AAPL 固定使用 `technology`，不新增 AAPL 专属模板 |
| `dayu/cli/commands/_research_template_materialize.py` | 完整 workspace 物化位于 13 个受保护路径的回滚边界内 | 验收只校验已有 13 个产物，不另造平行 research bundle |
| `dayu/cli/commands/research_workbook.py` | technology workbook 为 10 类、37 项，answered 项必须有 response 与 evidence；报告有语义指纹和 body 指纹 | workbook 健康与内容完成度分开计分；不把空 workbook 当完成研究 |
| `dayu/cli/commands/_research_template_monitoring.py` | monitoring plan 强制 `execution_mode=dry_run`、`automated_execution_allowed=false`；unbound plan 仍可结构有效 | 本 work unit 的 monitoring 验收是“安全且可解释的计划”，不是执行告警 |
| `dayu/cli/commands/_research_template_helpers.py` | technology sources 包括 financial statements、operating metrics、product release notes、market data；后二者和 market data 不是已实现的 `dayu_fins_tool` provider | 未绑定项必须显示为 residual/blocker，不允许虚假 ready |
| `dayu/services/internal/write_pipeline/execution_summary_builder.py` | `write_run_summary_v3` 含 gate、章节审计、model usage、routing 与 budget | Token/成本/请求量以该 receipt 为真源，不从日志猜测 |
| `dayu/services/internal/write_pipeline/source_list_builder.py` | 生产 builder 会收录 bullet evidence，在非 bullet 兜底路径才要求四段；来源清单通常按前三段去重并保留定位 | 结构层保持与生产语义同源；验收器另加四段非空+可复核定位的更严质量 hard gate |
| `dayu/startup/config_file_resolver.py` | `resolve_package_config_path()` 返回当前包内 `dayu/config`；CLI 的显式 `--config` 可直接指向该目录 | `prepare` 仅通过 resolver 获得默认配置真源，所有 `dayu.cli` argv 强制使用同一 resolved config dir，不读 workspace override |
| `dayu/startup/config_file_resolver.py`、`research_template_assets.py`、`research_template_definitions.py` 与 package-manifest builder | `resolve_package_assets_path()/research_templates/` 同时包含全部 packaged `.md` 和 `.definition.json`；package manifest 通过 `list_research_templates()` 枚举目录中除 README 外的全部 `.md` 并消费其 monitoring 定义；composed technology 还读取根级 `定性分析模板.md`，checklist/bundle 读取 `technology.definition.json` | receipt 指纹必须覆盖整个 research-template canonical tree + 根级 base template；`--research-base` 只控制派生产物落点，用户 workspace 自定义模板不参与 |
| `tests/cli/test_research_template_command.py` | 已覆盖物化、指纹漂移、回滚、stale report、monitoring 安全开关、AAPL/technology 路径 | 新验收测试应复用这些 owner，不复制测试内 helper 到生产代码 |

### 3.2 缺口

1. 仓库没有“一次 AAPL 运行”的统一 acceptance plan/receipt，也没有把 git SHA、as-of、配置指纹、源文档清单、各阶段耗时和所有产物指纹绑定起来。
2. 现有测试是组件级/离线测试；没有同时贯通 download → price snapshot material import → process → write → materialize → workbook/report → monitoring/source-map validation 的 opt-in live lane。
3. `run_summary.json` 有完成时间、usage 和成本，但没有整条验收链的开始时间、download/materialize/validation 分段耗时和 wall-clock ceiling。
4. 现有 source list 能校验证据行格式与去重，不能单独证明“每个重大判断均有支持”；需要确定性硬门禁加结构化人工 rubric。
5. materialize 后 workbook 合法但初始 37 项全部 open；它不能替代最终报告内容质量，也不能被错误计为 completed。
6. technology monitoring 默认 unbound，外部 market data 仍是 placeholder；这应在验收结果中显式暴露，而不是掩盖。
7. 没有固定 AAPL 质量语料和阈值，无法在以后不联网、不付费的情况下检测验收器或报告合同回归。

## 4. 总体设计与边界

### 4.1 两条 lane

**Deterministic lane（默认、CI 可运行）**

- 只读取仓库 fixture 和临时目录；不联网、不调用模型、不读取用户密钥。
- 用固定 AAPL 验收 contract、源清单、报告、write manifest 和 run summary 验证评分、失败分类、脱敏和稳定序列化。
- 在 `tmp_path` 中调用现有 research materializer 构建真实 13 产物，避免把整套派生产物复制进 fixture。
- 同一输入与显式时间注入必须生成字节一致的 normalized receipt。

**Live lane（opt-in、绝不进 CI）**

- 只有在 Controller 取得本次模型/外部数据/费用授权，并把 Slice 5 的 live gate 显式标记为已授权后才可执行；Slices 0–4 未来即使通过 re-review 并进入 handoff-ready，也不能替代该授权。
- 先生成不调用外部服务的 preflight plan；`prepare` 要求精确 run root 不存在，在同一父目录 staging 中构造 `data-workspace/`、canonical price snapshot/Markdown material、quality-review 骨架和 plan，再用同文件系统原子 rename 到精确 run root；任一步失败不得留下可运行的正式 run root。plan 固定 as-of、代码 SHA、模型名、预算、wall-clock、package config/template 真源、run root 和全部 argv，并给出 SHA-256。
- `run` 必须要求显式传入该 plan 指纹；只允许执行计划中列出的 `python -m dayu.cli` argv，不用 shell、不接受任意命令字符串。
- allowlist 顺序固定为三组 download → 本地 price snapshot material import → 一次 process → write preflight → 付费 write+materialize → validators → verify。每个阶段写独立 phase receipt；任何非零退出立即停止，不自动进入后续付费阶段。
- 从 `run` 进入第一阶段开始的整条自动化链（包括三组 download、material import、process、preflight、write、validators 和首次 verify）共享一个 `max_wall_seconds`；任何阶段不得重置计时。后续人工质量填写不在该 subprocess wall-clock 内，但必须另记录 review 时间。
- live 产物只写入 `.gitignore` 已覆盖的 `workspace/acceptance/investment-agent-aapl/<run-id>/`；固定回归 baseline 只在验收通过并脱敏后选择性提交。

### 4.2 模块职责

- `utils/investment_agent_acceptance_contracts.py`：严格 TypedDict/dataclass/schema 解析、canonical JSON 和指纹。三个新验收模块自身导出签名与内部传播不得使用 `Any`、`object` 或无类型签名；既有 owner 返回的 `DocumentMeta = dict[str, Any]` / `dict[str, object]` 只允许在一个明确 ingress 边界立即严格解析为 frozen dataclass/TypedDict，类型或未知字段不符即 fail closed，宽类型不得继续传播。
- `utils/investment_agent_acceptance_evaluator.py`：只读解析和确定性硬门禁/评分；不得执行 subprocess 或外部调用。
- `utils/investment_agent_acceptance.py`：薄 CLI、preflight plan 生成、allowlisted phase 编排和 receipt 输出；不得承载评分规则真源。
- 源文档盘点使用 `SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol` 与 `DocumentBlobRepositoryProtocol`；文件系统研究工件仍按其现有公开路径契约读取。
- 配置仅通过 `resolve_package_config_path()` 解析当前包内默认真源，其 canonical tree 覆盖 scene manifests 与其它被 config loader 消费的文件；个别关键文件指纹只是诊断分解，不是替代 tree 的不完全 allowlist。研究资产仅通过 `resolve_package_assets_path()` 解析；不硬编码用户 home、仓库绝对路径或 `workspace/config`。
- 禁止反向修改 `dayu/` 生产代码来迁就验收器；不得为宽类型 ingress 修改 owner，不得使用 `cast`、ignore 或 compatibility wrapper/facade 规避解析。若实施时证明当前 CLI 不能接受 resolver 返回的 package config dir，或审计发现其它真正的生产 gap，必须 STOP 并报告 plan gap，不得自行改用 workspace override、新 scene 或新生产 flag。

## 5. 精确验收 contract

### 5.1 身份与输入硬门禁

- `ticker == "AAPL"`，公司规范名非空且接受 `Apple`/`Apple Inc.` 的仓储真源值。
- write manifest 中 requested/resolved/selection 必须闭合为 `technology`；`auto` 仅在 resolved 为 `technology` 且 provenance 完整时允许。
- `prepare` 仅通过 `resolve_package_config_path()` 取得当前包内默认配置目录；指纹覆盖该 resolved 目录的全部 regular-file canonical tree，因此 `prompts/manifests/write.json`、`audit.json` 等 scene manifests 与 `llm_models.json` 均在同一闭包内。receipt 可单列这些关键文件供定位，但 tree fingerprint 才是完整性真源。不要求用户先 `init`，不读取 `workspace/config` override；所有 `python -m dayu.cli` argv 都显式传入同一 resolved `--config` 绝对路径。
- package research asset 指纹是真实 materialization 输入闭包：(1) `resolve_package_assets_path()/research_templates/` canonical tree，按包相对 POSIX 路径排序并对每个 regular `.md` / `.definition.json` 文件记录路径+字节 SHA-256，明确覆盖 `common.md`、`technology.md`、`common.definition.json`、`technology.definition.json`、其它 package-manifest 会枚举/消费的 research template 资产与目录中其它 `.md`/`.definition.json`；(2) `resolve_package_assets_path()/定性分析模板.md` 的独立 SHA-256。遇到 symlink、非 regular file 或重复 canonical locator 即 fail closed。`--research-base` 只隔离派生研究产物，不是模板真源；用户 workspace 自定义模板不参与，必须写入 residuals。
- receipt 绑定：git commit SHA、dirty flag、Python 版本、平台、package config canonical tree SHA-256 及诊断用关键文件 SHA-256、package research-template canonical tree SHA-256、根级 `定性分析模板.md` SHA-256、CLI argv、UTC start/end、IANA timezone、as-of。receipt 中 config/assets 路径用包相对 locator，不泄漏 home 绝对路径；实际 subprocess argv 保留 resolved config 绝对路径以消除 CLI fallback 歧义，但对外 receipt 必须脱敏为 locator + fingerprint。
- 绝对 home 路径泄漏 hard gate 仅约束 acceptance harness-owned outputs：`phase-receipts/*.json`、`acceptance-receipt.json`、脱敏后的可提交 baseline 与 completion report。现有生产 validator artifacts（例如 `research-template.manifest.json`、`technology.monitoring-rules.json`）可保留 owner 写入的 package 绝对路径；verifier 不改写这些文件，不因其内嵌 package 绝对路径单独判 FAIL，也不将内容片段复制到 acceptance-owned outputs。acceptance-owned outputs 引用它们时只记录 package-relative artifact locator（例如 `research/assets/research_templates/research-template.manifest.json`）+ 文件 SHA-256，不记录生产 artifact 内嵌路径或其它原文。
- `prepare` 调用前精确 run root 必须不存在，父目录必须已解析且非 symlink。`prepare` 在同文件系统 staging 中一次性创建 run root 全部骨架与精确 `data-workspace/`，成功后原子 rename；正式 run root 不允许 `exist_ok`、merge 或 `--overwrite-research`。恢复必须使用同一 run-id 和已存在的 manifest。
- 除用户显式传入且仅供 `prepare` 只读的 price snapshot JSON 外，所有 subprocess 输入与输出真实路径必须位于精确 run root。`prepare` 对该外部 JSON 严格解析后只把 canonical JSON、确定性 Markdown 派生物和 SHA-256 写入 `inputs/`，receipt 不记录原绝对路径。拒绝 symlink 越界、`..` 与非普通文件。

### 5.2 数据 freshness / as-of policy

- `as_of` 为 preflight 时捕获的带时区 UTC 时间；同一 run 不随时钟漂移。
- 不依赖任何未验证的默认窗口。`prepare` 以同一 `as_of-date` 构建三组 download argv：`10K` 使用 `start = as-of 减 5 个日历年`；`10Q` 使用 `start = as-of 减 2 个日历年`；`8K DEF14A` 使用 `start = as-of 减 2 个日历年`；三组都显式传同一 `--end <as-of-date>` 与 resolved package `--config`。闰日减年时 clamp 到目标年最后合法日，所有日期写入 plan fingerprint。
- `download.json` 在一个 phase receipt 内按执行顺序记录三个完整 argv、分段 exit/duration/discovery 摘要与聚合 verdict。任一命令非零或 preliminary inventory 已可证明必需 form 缺失时，不进入 material import/process/write。
- 三组 download 成功后，在任何 write 前执行唯一 price import：`prepare` 已把六字段 JSON 确定性渲染为 `inputs/price-snapshot.material.md`，runner 用现有 `upload_material --forms MATERIAL_OTHER --material-name aapl-price-snapshot --report-date <market-date>` 导入本 run 的 Fins material 仓储。直接 `.json` 不在现有 upload suffix allowlist 内，不得尝试上传原 JSON；Markdown 必须包含 canonical JSON SHA-256 和全部六字段的无损文本表示。import receipt 记录 argv、返回的 material document_id、source fingerprint 与 JSON/Markdown 指纹闭合。
- material import 成功后显式执行一次 `dayu.cli process --ticker AAPL`，同时处理三组 SEC filing 与 price material。`process.json` 记录唯一 argv、filing/material summary、exit/duration 和返回的 document status；它的全部耗时计入整个 `max_wall_seconds`。任一必需文档缺 processed、处理失败或 `reprocess_required=true` 均在任何付费 write 前 hard fail。
- 源清单逐文档记录：document_id、source_kind、form、filing/report date、fiscal_year/period、source URI 的安全标识、primary file SHA-256，以及仓储协议可得的 processed 存在性、`source_fingerprint`、`schema_version`、`parser_version`、`quality`、`reprocess_required` 状态指纹。processed 侧不存在内容 SHA-256 真源，本 work unit 明确不要求、不扫描私有目录重算它。不得记录下载响应中的 cookie、header 或凭据。
- 所有 filing_date 必须 `<= as_of-date`；发现未来日期、缺 filing_date、缺 primary、必需文档缺 processed、`ingest_complete != true` 或 `reprocess_required=true` 均为硬失败。
- 在显式窗口内至少存在一份 10-K、一份 10-Q 和一份 DEF 14A；8-K 若不存在可记录 warning，不得伪造。最新 10-K/10-Q 必须与本次各自 SEC discovery 结果中的最新可用 accession 对齐。
- deterministic fixture 的 pinned accessions 只用于回归，不用于声明“今天最新”；live freshness 只能由本次 discovery receipt 证明。
- 市场价格/市值只接受显式 price snapshot 输入：`price`、`currency`、`market_date`、`source_url`、`captured_at`、`max_age_days` 六项均必填，并进入 plan fingerprint。验收器不得新增联网或 live web 抓价能力；真实 snapshot 内容延后到 Slice 5 live authorization gate。write scene 保留既有 `web` 工具且不修改生产 scene，但 price material 是估值的唯一获准基准，报告与 snapshot 不一致必须 fail closed。

### 5.3 来源与 citation policy

- 契约分两层，不得混为“生产 validator 损坏”：**生产结构层**按现有 `source_list_builder` 同源语义识别 bullet/兜底 evidence 并构建 source list；**验收质量层**另要求每个非 overview 的实质章节包含 `### 证据与出处`，且至少一条 `来源 | 类型/标识 | 日期 | 定位` 四段非空 evidence；overview 的证据由其依赖章节与最终来源清单承接。
- 生产结构层通过但四段不全或定位只写“见财报/官网”等模板化文本时，归类为 `acceptance_quality` hard finding，不归类为 production artifact corruption。日期不得晚于 as-of。
- 报告中的每个 evidence 文档键必须出现在最终 `来源清单`，并能与源清单 document_id/accession 或允许的外部 URL 记录闭合。
- 重大数字主张必须在同章 evidence 中至少有一个可定位来源；估值中的价格、股数、净现金、multiple/discount rate 和情景假设必须标明 as-of 与单位。
- 估值章必须有唯一、可机械解析的 `valuation_reference_price` 记录，其 Decimal 价格、币种与 market date 必须精确等于已指纹 price snapshot，且 evidence 闭合到已 import 的 Fins material document_id。历史价格可在明确标注其他日期/来源后作为背景，但不得成为估值基准；报告价格/币种/日期与 snapshot 不符即确定性 FAIL。
- 管理层表述必须与事实陈述区分；推断、情景和观点必须使用显式措辞，不能伪装成已披露事实。
- 允许明确写“缺少证据/待验证”并降低置信度；禁止用占位符、虚构来源或删除 bear case 来获得高分。
- 确定性检查负责格式、闭合、日期、产物一致性与 audit receipt；“主张是否真的被证据支持”由第 6 节人工 rubric 复核。两者都通过才可接受。

### 5.4 产物 inventory

live run root 固定为：

```text
workspace/acceptance/investment-agent-aapl/<run-id>/
├── acceptance-plan.json
├── inputs/
│   ├── price-snapshot.json          # 严格解析后的 canonical 副本
│   └── price-snapshot.material.md   # 供现有 upload_material 导入的无损派生物
├── phase-receipts/
│   ├── prepare.json
│   ├── download.json
│   ├── price-snapshot-import.json
│   ├── process.json
│   ├── write-preflight.json
│   ├── write.json
│   └── validations.json
├── data-workspace/                 # Fins storage，仅通过仓储协议审计
├── write/
│   ├── manifest.json
│   ├── run_summary.json
│   └── AAPL_qual_report.md
├── research/assets/research_templates/
│   ├── common-plus-technology.md
│   ├── technology.research-workbook.json
│   ├── technology.research-progress.md
│   ├── technology.monitoring-rules.json
│   ├── technology.source-map.json
│   ├── research-template.manifest.json
│   ├── technology.research-guide.md
│   ├── technology.checklist.md
│   ├── technology.bundle.json
│   ├── technology.monitoring-plan.json
│   ├── monitoring-status.json
│   ├── research-workbook-status.json
│   └── research-workbook-report-status.json
├── source-inventory.json
├── quality-review.json
└── acceptance-receipt.json
```

区分：`data-workspace/`、`write/`、`research/` 和 receipts 都是用户本次 live 输出，永不作为 test fixture 直接读取；`tests/fixtures/investment_agent/aapl_acceptance/` 是脱敏、固定、无外部依赖的回归语料。

`prepare.json` 是原子创建完成 receipt；`download.json` 内含三个有序 command records；`price-snapshot-import.json` 绑定 canonical JSON、Markdown、Fins material document_id 与 source fingerprint；`process.json` 覆盖 filing + material 的唯一 process 命令。所有 phase receipt 都使用同一 plan fingerprint 且统一记录 `status/started_at/ended_at/duration_seconds/remaining_wall_seconds/argv/exit_code/stop_reason`。

## 6. 质量 rubric（100 分 + hard gates）

### 6.1 Hard gates（任一失败则总结果 FAIL，不以分数抵消）

1. `run_summary.schema_version` 受支持，`gate_status=passed`、`publication_status=published`、budget 未 blocked、failed chapter 为 0。
2. audit 为 required；每个 required chapter 的 `audit_passed=true`、`gate_passed=true`，不存在 `passed_without_audit`。
3. model roles 闭合为 DeepSeek 主写与 MiMo 审计；usage 不为空，定价 coverage 完整，成本币种与批准预算一致。
4. 实际 requests、total tokens、estimated cost 和 wall-clock 均不超过批准上限；wall-clock 从第一个 download 阶段起一直覆盖 material import、process、write 与自动 validations，任一阶段不得重置。
5. 报告、manifest、run summary 以及 13 个 research 产物全部存在并通过各自当前 validator；bundle/write-manifest semantic fingerprint current。
6. workbook 必须结构有效；progress report 必须 current 且 untampered。允许 open items，但必须如实报告 `completion_status` 和 open count。
7. monitoring plan 必须 validator 通过、`dry_run`、`automated_execution_allowed=false`；unbound sources/blocked tasks 必须原样进入 residuals。
8. source inventory 满足显式窗口与 freshness，必需 filing 以及 price material 的 processed 存在且状态指纹完整、`reprocess_required=false`，所有报告 evidence 与 source list/源清单闭合。显式 price snapshot 六字段合法、未超 `max_age_days`、时间不晚于 as-of，JSON→Markdown→Fins material 指纹闭合，估值的 `valuation_reference_price` 价格/币种/日期与 snapshot 精确一致。
9. acceptance harness-owned `phase-receipts/*.json`、`acceptance-receipt.json`、脱敏可提交 baseline 与 completion report 中无 secret shape、凭据值、Authorization header、cookie 或任意绝对 home 路径。生产 validator artifacts 内 owner 原生写入的 package 绝对路径不在该泄漏 gate 作用域内；它们仅做存在性/validator/字节指纹校验，不改写且不因该路径单独 FAIL。
10. 人工质量复核必须是完整的 `PASS` 状态，没有未解决的 unsupported material claim，High/Medium finding 为 0；`PENDING_MANUAL_REVIEW` 不得被表述或冻结为验收 PASS。

### 6.2 评分项

| 维度 | 分值 | 通过标准 |
|---|---:|---|
| 来源可追溯 | 25 | 章节 evidence 覆盖 8；source-list/inventory 闭合 7；数字/日期/定位完整 6；来源层级与 as-of 清楚 4 |
| 投资研究完整性 | 30 | 投资主线 6；bear case/反证 6；估值三情景与关键假设 8；未来 6–18 月催化剂/失效条件 5；业务/治理/尾部风险 5 |
| 证据与推理质量 | 25 | 事实/观点/情景分离 5；财报与管理层/外部证据交叉验证 7；数字单位/期间一致 5；无 cherry-pick 与反例处理 4；结论可证伪 4 |
| 可复现与恢复 | 10 | 输入/配置/代码/产物指纹完整 4；重复 verify receipt 稳定 2；失败阶段可恢复且不覆盖已接受产物 4 |
| 运行治理 | 10 | 模型角色/usage/token/cost 完整 4；分段和总耗时完整 3；预算、stop reason 和 residuals 完整 3 |

- 总分阈值：`>= 85/100`。
- 来源可追溯、投资研究完整性、证据与推理质量各自不得低于该维度的 80%。
- `quality-review.json` 由 `prepare` 生成完整 schema 骨架：每个子项已有 `max_score`，`score=null`、`evidence_paths=[]`、`notes=null`，顶层 `reviewer_role=null`、`reviewer_id_label=null`。复核后必须记录每个子项 `score/max_score/evidence_paths/notes`，不得只给总分。
- deterministic scorer 只自动给可机械验证的项；需要判断语义的项必须由复核者明确给分并列出引用位置。不得让生成报告的模型单独自评后自动通过。
- 总 verdict 严格三态：任一 deterministic hard gate/完整人工 review 阈值失败为 `FAIL`；deterministic 全通过但任一子项、`reviewer_role`、evidence path 或 notes 未填完为 `PENDING_MANUAL_REVIEW`；只有全部字段完整、评分达标且 High/Medium=0 才为 `PASS`。骨架文件被删除/改 schema 是 tamper `FAIL`，不是 pending。
- reviewer 仅记录非 PII 角色/代号，例如 `investment-reviewer` 和 `reviewer-1`；不得写真实姓名、email、账号、home path 或凭据形状。

## 7. 模型/provider、预算和安全策略

- primary writer：`deepseek-v4-pro`；audit/reasoning：`mimo-v2.5-pro-thinking`。这是当前 packaged scene 默认和 README 推荐角色，不新增 challenger/fallback。
- 本验收不启用 fallback：供应商失败应作为真实可观测失败，而不是把模型变量混入首个质量 baseline。
- deterministic Slices 0–4 不检查真实 shell 凭据。只有 live `prepare`/`run` 才输出 `DEEPSEEK_API_KEY`、`MIMO_API_KEY`、`SEC_USER_AGENT` 等所需环境变量名称和 presence boolean；不得读取、打印、hash 或持久化值。
- AAPL canonical ticker 不需要 FMP infer；live 命令不传 `--infer`，避免无关外部请求。
- `max_model_requests`、`max_total_tokens`、`max_estimated_cost`、`budget_currency` 与 `max_wall_seconds` 全部是 live `prepare` 的显式必填 runtime 参数；实现不得提供 60/1,500,000/12 CNY 或任何 wall-clock 默认值。Slices 0–4 只测试合法边界、缺参拒绝和超限停止。
- Slice 5 执行前由用户批准这些精确值；runner 把 `max_wall_seconds` 作为整个 run 的 hard timeout，三组 download、price material import、process、write preflight、write/materialize 与 validators 都消耗同一 remaining budget，不能拿单请求 3600 秒 timeout 代替整次上限。
- 跨平台 timeout 不依赖 POSIX process group/signal 语义：子进程超时时先调用 `terminate()`，等待固定并写入 plan fingerprint 的 `termination_grace_seconds=10`；仍 alive 则调用 `kill()` 并等待退出。无论 terminate/kill 路径如何，都必须原样保留 run root、写 `status=timeout`、`termination_action`、elapsed/remaining 与 `partial_by_timeout=true` receipt，且后续阶段一律不执行。若 `kill()` 后仍不能确认退出，记录 `termination_unconfirmed` 并 STOP，不自动 cleanup/resume。
- write scene 保留现有 `web` 工具，因此模型侧外部请求仍是 residual；验收不修改 scene，而是以已导入 Fins material 的 price snapshot 作为估值唯一授权基准，用确定性报告一致性门禁+人工 unsupported-claim review 兦底。
- 日志与 phase receipt 必须通过现有 `dayu.redaction` secret shape 规则再输出；stderr 只保存脱敏摘要和 SHA-256，不在 baseline 中复制完整 provider error body。

## 8. 失败恢复、复现与 cleanup

### 8.1 恢复

- `prepare` 失败：不生成正式 run root；仅可安全清理该次尚未 rename 的精确 staging 目录，不得扫描或删除其它 run。
- `download` 三组任一失败：保留已执行的 command records、phase receipt 和仓储 journal；重新执行同一 plan 前先用仓储 recovery/read-only inventory 判断可恢复状态，不直接删 `data-workspace`，不重写 as-of/start/end。
- price material import 失败：保留 canonical JSON/Markdown 和 import receipt；不进入 process/write。重试仅能用同一 plan 内的指纹化 Markdown 和现有 upload 自动 create/update/skip 语义，不得 overwrite 或更换 snapshot。
- `process` 失败：保留仓储 journal、已生成 processed 与 `process.json`，不进入任何付费 write。在同一 plan 下先用仓储协议盘点 `source_fingerprint/schema_version/parser_version/reprocess_required`；仅当恢复评估确认现有 process 幂等语义可用时才可人工重跑，不删 `data-workspace`。
- write preflight 失败：不得创建 write run，不进入付费 write。
- write 中断：保留同一 output/manifest；只有 Controller 再次确认剩余预算后，才允许使用现有 `--resume` 语义继续。不得自动重试鉴权、额度、内容策略或预算错误。
- write budget blocked：立即 FAIL；不得通过扩大预算或 `--force` 自动继续。
- materialize 失败：依赖现有 13 文件 byte-exact rollback；验收器核对目标与失败前 snapshot，不自写第二套 rollback。
- workbook/source-map 手工更新如进入未来 work unit，必须走现有 immutable backup/rollback；本次 baseline 不做这类变更。
- validation/quality FAIL：保留产物用于审计，不把失败目录重命名成 passed，也不改评分输入。
- wall-clock timeout：按第 7 节 `terminate → 10s grace → kill` 协议收敛，当次 acceptance 立即 `FAIL`，后续阶段不执行；原样保留目录与仓储 journal，residuals 标记 `partial_by_timeout`，不自动 resume、删除、重命名或再次消费。

### 8.2 复现

- `acceptance-plan.json` canonical JSON 指纹是运行身份；任何 as-of、三组窗口、price JSON/Markdown、预算、模型、代码、package config canonical tree/诊断用关键文件、package `research_templates/` canonical tree、根级 `定性分析模板.md`、路径、timeout grace 或命令变化都生成新 run-id/plan。
- source inventory 按 `(filing_date, form, document_id)` 排序；artifact inventory 按仓库相对路径排序；JSON 禁止 NaN。
- live 文本输出允许模型差异，但相同 live artifacts 的 `verify` 必须得到相同 normalized score/receipt（除显式 injected verification time 外）。
- baseline fixture 保存脱敏的事实结构和最小报告语料，不保存 API 响应、原始密钥、cookie 或整份 SEC 原文。

### 8.3 Cleanup

- runner 不自动删除失败或成功 run。
- cleanup 只允许接收一个已解析、位于 `workspace/acceptance/investment-agent-aapl/` 下的精确 run-id 目录；禁止 glob、环境变量展开、`~` 和递归 workspace 根目录目标。
- 默认做可恢复的归档/移动；若未来需要永久删除，必须是独立用户授权，不属于本 work unit。

## 9. Implementation slices

每个 slice 都必须形成独立本地 accepted commit；实现前先确认 worktree 仅含本 work unit 的变更。以下列表是该 slice 的**精确允许文件**，不得顺手修改其它生产模块。

### Slice 0 — Characterization 与固定 contract

**允许文件**

- 新建 `tests/fixtures/investment_agent/aapl_acceptance/contract-v1.json`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/source-inventory-v1.json`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/report-v1.md`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/price-snapshot-v1.json`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/quality-review-v1.json`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/write-manifest-v1.json`
- 新建 `tests/fixtures/investment_agent/aapl_acceptance/run-summary-v1.json`
- 新建 `tests/test_investment_agent_acceptance.py`

**变更内容**

- 固定 `AAPL + technology + 85/100 + hard gates` contract。
- fixture 是脱敏最小语料：覆盖 thesis、bear、valuation、catalyst、risk、四段式 citations、精确 `valuation_reference_price` 和完整人工 quality review；源清单使用稳定的示例 filing/material document IDs、primary SHA-256 与 processed 状态指纹，不宣称 live freshness。
- characterization 测试证明当前 technology workbook 为 10 类/37 项、当前 workspace materializer 保护 13 个产物、当前 monitoring plan 始终 dry-run/automation false、当前 run summary v3 包含 budget/usage/audit。

**预期断言**

- fixture schema 精确且 canonical serialization 稳定。
- baseline report 所需五类内容和 evidence/source list 闭合。
- 当前生产 owner 的既有契约未被验收代码改变。

### Slice 1 — 严格 contracts 与确定性 evaluator

**允许文件**

- 新建 `utils/investment_agent_acceptance_contracts.py`
- 新建 `utils/investment_agent_acceptance_evaluator.py`
- 修改 `tests/test_investment_agent_acceptance.py`

**变更内容**

- 用 frozen dataclass/TypedDict 表达 plan、phase、inventory、rubric、receipt；所有函数具备完整中文 docstring。`Any/object` 禁令精确限于新验收模块的导出签名与内部传播；既有 owner 宽载荷在单一 ingress 严格收窄，不修改 `dayu/`，不使用 cast/ignore/wrapper。
- 实现 strict schema、canonical JSON/SHA-256、as-of/date/显式窗口、artifact containment、secret shape、source/citation closure、primary SHA + processed 状态指纹、生产结构/验收质量两层 evidence、price report consistency、run-summary budget/audit、research validators 和 rubric 聚合。
- evaluator 返回结构化 findings，不直接写 stdout，不执行命令。

**预期断言**

- happy fixture `PASS` 且总分/子分精确；quality review 骨架未填/部分填为 `PENDING_MANUAL_REVIEW`，完整且达标才 `PASS`，完整但不达标为 `FAIL`。
- 缺 bear case、断 citation、future source、processed 缺失/需重处理、带 bullet 但只有三段的 evidence（归类为验收加严失败）、报告价格/币种/日期与 snapshot 不符、blocked budget、audit skipped、成本超限、wall-clock 超限、stale/tampered report、fake monitoring ready、secret shape、symlink 越界分别 fail closed。
- sanitizer 测试边界必须有界：只扫描 acceptance harness-owned JSON（phase receipts、acceptance receipt 与脱敏 baseline payload），任一 POSIX/Windows 绝对 home 路径都 fail；对包含 package 绝对路径的 `research-template.manifest.json` / `technology.monitoring-rules.json` 生产 fixture，验证 verifier 不改写原字节、不因该字段单独 FAIL，且 acceptance receipt/baseline 只产生 package-relative artifact locator + SHA-256，不摘录 `template_file`/`source_template_file` 或任何生产 artifact 内容。该测试不递归扫描或 sanitizer-rewrite 生产产物。
- 指纹测试证明 config canonical tree 来自 `resolve_package_config_path()` 并覆盖 scene manifests；package research asset 闭包来自 `resolve_package_assets_path()/research_templates/` 全部 regular `.md`/`.definition.json` canonical tree + 根级 `定性分析模板.md`。分别修改 base template、`technology.definition.json`、`common.md`、`technology.md` 或任一其它会被 package manifest 枚举/消费的 research asset（例如 `consumer.md`）都必须改变闭包指纹并在 subprocess 前触发 drift fail。inventory 构建只读仓储协议，不拼接/遍历 `workspace/portfolio`。
- 同一输入与固定 clock 两次 receipt 字节一致；未知字段/schema/NaN 拒绝。

### Slice 2 — 薄 CLI、preflight plan 与 allowlisted live runner

**允许文件**

- 新建 `utils/investment_agent_acceptance.py`
- 修改 `tests/test_investment_agent_acceptance.py`

**变更内容**

- 子命令仅为 `prepare`、`run`、`verify`。
- `prepare` 不联网、不调用模型，验证新 run root、resolver 返回的 package config/asset 真源与模型目录价格、环境变量名称 presence、显式预算/wall-clock/as-of 与本地 price snapshot 六字段/时效。它在同父目录 staging 生成 `data-workspace`、canonical JSON/Markdown material、quality-review null 骨架、全部 argv 与 plan fingerprint，然后原子 rename 到精确 run root。
- `run` 要求 `--plan` 和 exact fingerprint；只执行 10K download → 10Q download → 8K+DEF14A download → price snapshot `upload_material` → 一次 `process` → write preflight → 付费 write+materialize → validators → verify。每个 `dayu.cli` argv 显式使用同一 package `--config`；使用 argv list、`shell=False`、整次 run 剩余 wall-clock timeout、脱敏 phase receipt。
- `verify` 只读既有产物，允许重复运行；源 inventory 通过 Fins storage protocols 构建，禁止目录扫描。它有且仅有两种互斥模式：deterministic fixture 模式只接受 `--fixture <dir>`，live/run 模式必须同时接受 `--plan <file> --fingerprint <sha256>`；`--fixture` 与 `--plan`/`--fingerprint` 任何同传、或 live 模式缺 plan/fingerprint 都在读取产物前 fail closed。
- runner 在任何非零、timeout、signal、receipt mismatch 后停止；timeout 使用跨平台 `terminate → 10s grace → kill` 协议，写 timeout receipt 并标记 `partial_by_timeout`。不自动 resume、不扩大预算、不删除产物。

**预期断言**

- fake command runner 验证三组 download 窗口、snapshot import、process、preflight 和 write 的精确顺序/argv；process 严格在 download+import 之后且早于任何付费 write，付费 write 绝不早于成功 preflight。
- plan fingerprint/HEAD/package config canonical tree 或诊断用关键文件/package `research_templates/` canonical tree/根级 `定性分析模板.md`/price JSON 或 Markdown/as-of/窗口/预算任一漂移均在 subprocess 前失败。
- stdout/stderr/异常含 secret shape 时输出与 receipt 均脱敏。
- prepare、三组下载、import、process、preflight、write、materialize、verify 每个失败点都只执行允许的前缀阶段。fake process 锁定 timeout 后调用 terminate、等待固定 grace、仍 alive 才 kill，后续命令数为 0，timeout receipt 存在且产物目录未删除/重命名；不依赖 POSIX process group。
- CLI 参数测试覆盖 `verify --fixture` 与 `verify --plan --fingerprint` 两个 happy path，并对两模式同传、单独 `--plan`、单独 `--fingerprint` 分别 fail closed。

### Slice 3 — 现有 CLI 集成与恢复场景

**允许文件**

- 修改 `tests/test_investment_agent_acceptance.py`
- 修改 `tests/cli/test_research_template_command.py`

**变更内容**

- 用真实 parser/dispatch（外部边界 fake）锁定 AAPL 三组 forms/start/end/base、`upload_material MATERIAL_OTHER`、随后一次 process、每条 argv 共用 resolver 返回的 package config、明确 DeepSeek/MiMo、完整预算、technology/materialize、隔离 output/research-base 参数。
- 复用现有 materialization 注入故障，证明验收器看到 byte-exact rollback。
- 证明 write partial receipt 不会被 evaluator 当 PASS；resume 必须使用同一 plan 且需要新的 operator authorization marker。
- 证明 unbound technology plan 可“结构健康但运行 blocked”，最终 receipt 必须在 residuals 报告它。

**预期断言**

- 不增加新的 production CLI action/flag。
- existing research-template tests 保持通过；验收器不通过 compatibility wrapper 调用 owner。
- 代码事实若显示 CLI 无法直接接受 package config dir 或 Markdown material 无法被 upload/process/Fins tools 闭合，必须 STOP 并报告 plan gap，不得创建新 flag、scene 或 owner wrapper。

### Slice 4 — 操作文档与 README 同步

**允许文件**

- 新建 `docs/acceptance/investment-agent-aapl.md`
- 修改 `README.md`
- 修改 `tests/README.md`

**变更内容**

- 详细文档说明 deterministic/live lane、package config/template 真源、三组 download、price material import、process、人工质量三态、timeout、preflight 与显式费用授权、产物目录、评分、恢复和 cleanup。
- 根 README 只添加用户可运行的最短路径与文档导航，不复制完整 rubric。
- tests README 说明 fixture 不是 freshness 真源、live test 禁止进入 CI。
- 示例只使用真实当前参数；绝不写 API key 示例值或 future design。

### Slice 5 — 授权后的单次 live 验收与基线冻结

**前置**：第 15 节全部 runtime inputs 已由用户明确提供/授权；Slices 0–4 的 plan/code/deepreview gates 已通过；Controller 在执行 Slice 5 的同一 live authorization gate 中再次展示并确认 exact plan fingerprint。此前不得执行本 slice。

**允许提交文件**

- 新建 `tests/fixtures/investment_agent/aapl_acceptance/accepted-quality-baseline-v1.json`
- 新建 `docs/acceptance/2026-08-09-aapl-result.md`
- 修改 `tests/test_investment_agent_acceptance.py`

**非提交输出**

- `workspace/acceptance/investment-agent-aapl/<run-id>/**`

**变更内容**

- 先 `prepare`，人工核对 plan、价格来源、预算和 as-of，再执行一次 live lane。
- 验收通过后，从 receipt 生成脱敏 baseline：只保留 schema、as-of、代码/配置/源清单指纹、维度分数、阈值、usage 汇总、residual 分类和 production artifact 的 package-relative locator/SHA-256；不提交完整 provider 日志、秘密、生产 artifact 内容片段或其内嵌绝对路径。
- completion report 明确区分已验证事实、人工 rubric、未绑定 monitoring sources、workbook open count 和非投资建议声明。
- baseline 测试只验证 contract 回归，不把 2026-08-09 snapshot 当今天 freshness 真源。

## 10. Live lane 计划命令形状

以下命令仅定义实现后的 argv contract，**现在不得执行**；`<approved-*>` 和 `<price-snapshot>` 都是 Slice 5 的 deferred runtime inputs，必须由第 15 节的 live authorization gate 决定并进入 signed plan fingerprint。Slices 0–4 只用 fixture 参数测试命令构建，不调用外部服务。

```bash
.venv/bin/python -m utils.investment_agent_acceptance prepare \
  --ticker AAPL \
  --company "Apple Inc." \
  --template technology \
  --as-of <UTC-RFC3339> \
  --run-root workspace/acceptance/investment-agent-aapl/<run-id> \
  --max-model-requests <approved-requests> \
  --max-total-tokens <approved-tokens> \
  --max-estimated-cost <approved-cost> \
  --budget-currency CNY \
  --max-wall-seconds <approved-wall> \
  --price-snapshot <price-snapshot.json> \
  --json
```

`<resolved-package-config-dir>` 不是用户输入；它必须由 `resolve_package_config_path()` 在 `prepare` 中解析且指纹化。runner 生成的现有 CLI argv 必须与下列结构等价，日期值在 plan 生成后不得重算。

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 10K \
  --start <as-of-minus-5-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 10Q \
  --start <as-of-minus-2-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 8K DEF14A \
  --start <as-of-minus-2-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

`download.json` 在同一 phase receipt 中依次保存上述三个 argv 与各自结果。随后的价格 material import 必须使用 `prepare` 产生且已在 plan 中指纹化的 Markdown：

```bash
.venv/bin/python -m dayu.cli upload_material \
  --ticker AAPL \
  --forms MATERIAL_OTHER \
  --material-name aapl-price-snapshot \
  --files <run-root>/inputs/price-snapshot.material.md \
  --report-date <price-market-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

import 成功后、任何 write 前只执行一次：

```bash
.venv/bin/python -m dayu.cli process \
  --ticker AAPL \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

```bash
.venv/bin/python -m dayu.cli write \
  --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --research-template technology \
  --output <run-root>/write \
  --preflight-only \
  --no-resume \
  --write-max-model-requests <approved-requests> \
  --write-max-total-tokens <approved-tokens> \
  --write-max-estimated-cost <approved-cost> \
  --write-budget-currency CNY \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

`--preflight-only` 不得与 `--research-base`/materialization 参数同时传入；隔离的 research 落点只属于下一条真实 write argv。

```bash
.venv/bin/python -m dayu.cli write \
  --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --research-template technology \
  --materialize-research \
  --output <run-root>/write \
  --research-base <run-root>/research \
  --no-resume \
  --write-max-model-requests <approved-requests> \
  --write-max-total-tokens <approved-tokens> \
  --write-max-estimated-cost <approved-cost> \
  --write-budget-currency CNY \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir>
```

validation argv 必须覆盖 `research-template validate-research-workbook --workbook ...`、`validate-workbook-report --report ...`、`validate-source-map --rules ... --source-map ...`、`validate-bundle --bundle ...`、`validate-monitoring-plan --plan ...`；每条都显式传 `--base <run-root>/research --config <resolved-package-config-dir>`，路径只指向第 5.4 节固定的 13 个产物。最后用 `.venv/bin/python -m utils.investment_agent_acceptance verify --plan <run-root>/acceptance-plan.json --fingerprint <exact-fingerprint> --json`。不得把多个命令拼成 shell 字符串。

## 11. 开发验证命令

每个 Python slice：

```bash
source .venv/bin/activate
```

```bash
python -m pytest tests/test_investment_agent_acceptance.py -q
```

```bash
python -m pytest tests/cli/test_research_template_command.py -k "materialize or research_workbook or workbook_report or source_map or monitoring" -q
```

```bash
python -m pytest tests/engine/test_source_list_builder.py tests/engine/test_execution_summary_builder.py tests/application/test_write_service.py -q
```

```bash
pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py
```

```bash
ruff check --select F,I utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py
```

```bash
git diff --check -- utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py tests/fixtures/investment_agent/aapl_acceptance docs/acceptance README.md tests/README.md
```

聚合 gate：

```bash
source .venv/bin/activate
```

```bash
pyright
```

```bash
python -m pytest -q
```

```bash
python -m utils.validate_handoff_docs --json
```

```bash
python -m utils.codex_review_gate --allow-waiting --json
```

```bash
python -m utils.dual_model_pipeline_check --json
```

deterministic acceptance：

```bash
source .venv/bin/activate
```

```bash
python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json
```

所有验证记录命令、exit code、stdout/stderr 脱敏摘要和时间；不得只写“tests passed”。若全仓已有 baseline failure，必须给出基线同命令与差分证据，不能归零或跳过。

## 12. Plan / code / deepreview gates

1. **Plan gate（Slices 0–4）**：本 revision 处于 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**。DeepSeek 与 MiMo 已对 PRR-002 修复后的同一 revision 完成 final corrective adversarial plan re-review，结果均为 pass；Controller 已逐条 adjudicate 并关闭全部 findings，open High/Medium/Low 均为 0。deterministic Slices 0–4 已 handoff-ready；该状态不授权 Slice 5 或任何 live 外部调用。
2. **Code gate（逐 slice）**：implementer 只改该 slice 白名单；运行 focused tests、pyright、ruff、diff-check；Controller 审核并做本地 accepted commit。
3. **双路 code review**：每个实质 slice 至少由 DeepSeek 和 MiMo 独立只读审查 correctness、security、recovery、cost gate、secret handling 与 over-coupling；Controller adjudicate，不按多数票自动接受。
4. **Deepreview gate**：所有 slices 合并后对当前未合并 workspace changes 做一次严格 deepreview，包含 adversarial failure pass、架构约束、source storage 边界、外部调用隔离与 residual risk。
5. **Slice 5 live authorization gate**：代码通过不等于授权外部调用。live run 前必须再次展示 exact plan fingerprint、模型、as-of、显式 price snapshot 指纹、费用/Token/请求/wall-clock 上限和数据来源；用户逐项确认后才可执行。
6. **Draft PR gate**：本地 aggregate PASS 后只报告 ready-to-open-draft-PR；push/PR 仍需用户单独授权。

### Plan closure evidence

完整 review / fix / re-review 链：

1. DeepSeek initial review：`docs/reviews/plan-review-20260809-062832.md`
2. MiMo initial review：`docs/reviews/plan-review-20260809-063137.md`
3. Controller-adjudicated plan fix：`docs/reviews/plan-fix-20260809-064803-codex.md`
4. MiMo re-review（P1–P8 + PF-EXTRA-001 收口）：`docs/reviews/plan-review-20260809-070142.md`
5. DeepSeek re-review（PR-001..004 收口并提出 PRR-001）：`docs/reviews/plan-review-20260809-070538.md`
6. PRR-001 corrective fix：`docs/reviews/plan-fix-20260809-071307-codex.md`
7. PRR-001 corrective DeepSeek review：`docs/reviews/plan-review-20260809-071640.md`
8. PRR-001 corrective MiMo review（提出后续 PRR-002）：`docs/reviews/plan-review-20260809-071911.md`
9. PRR-002 final corrective fix：`docs/reviews/plan-fix-20260809-072322-codex.md`
10. PRR-002 final corrective DeepSeek review：`docs/reviews/plan-review-20260809-072516.md`
11. PRR-002 final corrective MiMo review：`docs/reviews/plan-review-20260809-072913.md`

Controller closure adjudication：

| Finding | Closure status |
|---|---|
| PR-001 | **CLOSED** |
| PR-002 | **CLOSED** |
| PR-003 | **CLOSED** |
| PR-004 | **CLOSED** |
| P1 | **CLOSED** |
| P2 | **CLOSED** |
| P3 | **CLOSED** |
| P4 | **CLOSED** |
| P5 | **CLOSED** |
| P6 | **CLOSED** |
| P7 | **CLOSED** |
| P8 | **CLOSED** |
| PF-EXTRA-001 | **CLOSED** |
| PRR-001 | **CLOSED** |
| PRR-002 | **CLOSED** |

最终统计：**Open High 0 / Open Medium 0 / Open Low 0**。此 closure 只放行 deterministic Slices 0–4 implementation handoff；Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED**。

## 13. Stop conditions

出现任一情况立即停止，不自动修复或扩大范围：

- plan 指纹、HEAD、package config canonical tree、package `research_templates/` canonical tree、根级 `定性分析模板.md`、run root 或 as-of 漂移；
- `resolve_package_config_path()`/`resolve_package_assets_path()` 无法返回可读真源，package research asset tree 包含 symlink/非 regular file/重复 locator，CLI 无法接受该 resolved config dir，或任一 `dayu.cli` argv 缺少/不一致 `--config`；不得自行切到 workspace override/init；
- live `prepare`/`run` 中 `MIMO_API_KEY`/`DEEPSEEK_API_KEY`/`SEC_USER_AGENT` 所需名称缺失，或 preflight 非零；该条件不适用于 deterministic tests；
- SEC User-Agent 未按批准方式配置，三组 download 任一非零/窗口漂移，或发现缺失/未来/未处理的必需 filing；
- price JSON 六字段、canonical JSON/Markdown 指纹、material import document_id/source fingerprint 不闭合，或既有 upload/process/Fins tools 无法将该 Markdown material 纳入可引用来源；
- process 阶段非零、有 failed document、必需 filing/price material 缺 processed，或状态指纹显示 `reprocess_required=true`；
- 模型目录价格缺失、币种不一致或 provider usage 不完整；
- 任一请求/Token/成本/wall-clock 达到上限，或 write receipt budget blocked；
- 子进程 timeout 后按 `terminate → 10s grace → kill` 无法确认退出；必须标记 `partial_by_timeout/termination_unconfirmed`并保留现场；
- write gate、audit、materialization、bundle/workbook/report/source-map/monitoring validator 失败；
- acceptance harness-owned phase receipt、`acceptance-receipt.json`、脱敏 baseline 或 completion report 命中 secret shape/敏感 header/cookie/绝对 home 路径；生产 validator artifact 内 owner 原生 package 绝对路径不单独触发该 stop，但禁止将其内容摘录到 acceptance-owned output；
- rubric 为 `PENDING_MANUAL_REVIEW`、总分/分项低于阈值，或存在未关闭 unsupported material claim；pending 只允许停在等待人工复核，不得冻结 baseline/宣称 PASS；
- 恢复需要新费用、覆盖已有接受产物、修改生产 schema 或扩展新 provider；
- worktree 出现 slice 白名单外改动，或发现用户已有变更与本任务冲突。

## 14. Docs decision、残余风险与完成报告

### Docs decision

- **需要**新建 `docs/acceptance/investment-agent-aapl.md`：详细 operator runbook 与 rubric 不应塞入根 README。
- **需要**小幅更新根 `README.md`：这是新的项目级验收使用方式，属于用户手册职责；只放最短命令与导航。
- **需要**更新 `tests/README.md`：说明 deterministic fixture/live lane 隔离和禁止 CI 外部调用。
- **不需要**修改 `dayu/README.md`、Engine/Host/Fins/config README：本计划不改变分层、公共契约、Fins 机制或配置格式。

### 已知残余风险与跟踪去向

| 残余风险 | 跟踪去向 |
|---|---|
| Slices 0–4 使用 fixture / fake runner，跨 revision 才显现的输入闭包漂移不会由一次 deterministic run 证明 | Slice 1/2 drift tests；Slice 5 live authorization gate 前逐项复核 package config、research asset 与 plan fingerprint |
| 模型输出非确定；fixed baseline 只能守 contract 和质量下限，不能证明未来每次 prose 一致 | Slice 1 evaluator contract baseline；Slice 5 completion report 的 usage、评分与 residuals |
| chapter-level evidence closure 不等同逐句事实验证 | Slice 5 人工 unsupported-claim review hard gate |
| technology source-map 的 operating metrics/product releases/market data 仍可能 unbound | Slice 3 验证“结构健康但运行 blocked”；completion report 明示 unbound sources，不升级 placeholder provider |
| package research asset tree 是保守闭包；与本次 AAPL 产物无关的 packaged definition 改动也会作废 plan | Slice 1/2 drift tests；漂移后重新 `prepare`，不复用旧 plan |
| `--research-base` 只隔离派生产物，用户 workspace 自定义模板不参与本次验收 | Slice 4 runbook 与 completion report residuals |
| `prepare` staging → atomic rename 依赖同一文件系统 | Slice 2 prepare 失败/跨文件系统 fake 用例；失败不得留下正式 run root |
| 现有 write scene 保留 `web` 工具，模型理论上仍可自取外部价格 | Slice 1 report-vs-snapshot 确定性 gate + Slice 5 人工 review；不修改生产 scene |
| price snapshot JSON 不在 upload suffix allowlist，依赖无损、指纹化 Markdown 派生后走 `upload_material + process` | Slice 2/3 JSON→Markdown→material 指纹闭合测试；Slice 5 receipt |
| timeout 后可能出现 `termination_unconfirmed` 与仓储 journal 中间态 | Slice 2 fake-process 协议；保留现场、禁止自动 resume，交 operator 检查 |
| workbook 默认 37 项 open，本次不证明全部研究问题已回答 | Slice 3 validator 与 Slice 5 completion report 分离 open/answered 计数 |
| production validator artifacts 可能保留 owner 写入的 package 绝对路径，异机人工外发仍有路径泄漏风险 | acceptance-owned 输出只记 package-relative locator + SHA-256；若未来治理，在生产 owner 侧单独立项，不由验收器改写 |
| SEC/模型供应商临时故障可能使 live run 失败 | Slice 5 作为有效失败结果保留 receipt/现场，不自动 fallback 污染首个 baseline |
| 同一价格来源在非交易时段或公司行动后可能产生估值差异 | Slice 5 live authorization 固定 as-of、market date、snapshot fingerprint 与 max-age |
| 精确费用、Token、请求、wall-clock、price snapshot 与 final plan fingerprint 尚未提供 | 第 15 节 deferred runtime inputs；全部满足并获用户明确授权前 Slice 5 保持 blocked |

### 完成报告必须包含

- plan fingerprint、git SHA、as-of、run-id、package config canonical tree/诊断用关键文件、package `research_templates/` canonical tree 与根级 `定性分析模板.md` 指纹、各阶段 exit/duration/remaining wall；
- 三组 download argv/discovery、price JSON→Markdown→material 闭合、process filing/material summary、source inventory/processed 状态指纹和 freshness 判定；
- write gate、audit、model routing、usage/token/cost/budget；
- 13 个 research artifacts 与 validator 状态；对生产 artifacts 仅报告 package-relative locator + SHA-256，不摘录其内嵌绝对路径/内容片段；
- workbook open/answered counts、report freshness/tamper 状态；
- monitoring readiness、unbound sources 和 automation=false；
- rubric 明细、非 PII reviewer role/id label、人工复核 findings、三态总 verdict；
- 恢复是否发生、固定 baseline 路径、所有 residuals；
- 明确“研究质量验收，不构成投资建议”。

## 15. Live Authorization Questions / Deferred Runtime Inputs

本节**不阻塞 Slices 0–4 的 plan/code/deepreview**，但全部项目都阻塞 Slice 5。当前没有任何 live 或付费调用授权：

1. **费用/Token/请求上限**：用户在 live gate 提供精确 `max_model_requests`、`max_total_tokens`、`max_estimated_cost` 与 `budget_currency`。实现无默认值；README 的 60/1,500,000/12 CNY 示例不得被静默采用。若人工语义复核另行调用付费模型，必须单列复核预算。
2. **Wall-clock 上限**：用户提供精确 `max_wall_seconds`。未提供时 live `prepare` fail closed；不得用 provider 单请求 timeout 替代。上限包含三组 download、price material import、process、preflight、write/materialize 和自动 validators，timeout grace 固定为 plan 中的 10 秒。
3. **凭据仅存在性**：在执行 Slice 5 的同一 agent 终端，live `prepare` 只确认 `DEEPSEEK_API_KEY`、`MIMO_API_KEY` 与 `SEC_USER_AGENT` 是否存在。不得读取、回显、hash 或写入它们的值；缺失则 stop。
4. **显式 price snapshot**：用户提供或另行授权外部协调取得一个本地 JSON 输入，精确含 `price`、`currency`、`market_date`、`source_url`、`captured_at`、`max_age_days`。验收器只校验/指纹化该文件，不自行联网抓价；`prepare` 将其渲染为指纹化 Markdown，run 在任何 write 前通过现有 `upload_material + process` 纳入 Fins 可引用 material。snapshot 超龄、未来时间、非正价格、缺 URL/币种时 stop。
5. **Package config/assets 真源**：无需用户先 `init`或选择 workspace override；Controller 展示由 resolver 得到的 package config canonical tree fingerprint（scene manifests 在 tree 内）、write/audit/llm_models 诊断用单文件指纹、package `research_templates/` canonical tree 指纹与根级 `定性分析模板.md` 指纹。任一漂移需重新 `prepare`。
6. **人工质量复核**：不需在首次 `run` 前预填分数，但首次 verify 将停在 `PENDING_MANUAL_REVIEW`。只允许用非 PII `reviewer_role/reviewer_id_label` 填完骨架；如果复核另行调用付费模型，必须在第 1 项单列预算并再授权。
7. **最终 live 确认**：Controller 展示模型、as-of、三组 source forms/start/end、price JSON/Markdown 指纹与 material import argv、process argv、package config canonical tree、package `research_templates/` canonical tree 与根级 `定性分析模板.md` 指纹、全部预算、wall-clock、run root 与 exact plan fingerprint，用户明确确认后才允许执行 `run`。

Slices 0–4 完成与 accepted commits 不得被表述为 AAPL 实战验收已通过；只有 Slice 5 live receipt、人工 rubric 和 completion report 全部通过后，work unit 才可 closeout。
