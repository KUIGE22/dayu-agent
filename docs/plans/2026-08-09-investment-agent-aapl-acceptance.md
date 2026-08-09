# 投资 Agent：AAPL 实战验收实施计划

- **日期**：2026-08-09
- **分支**：`feat/investment-agent-acceptance`
- **基线**：`504d74730d9ffc099c07d7732804d51152972875`（Slice 3 accepted implementation baseline）
- **Work unit**：`investment-agent-aapl-acceptance`
- **目标证券**：`AAPL`（Apple Inc.）
- **当前 gate**：`manual-review handoff accepted plan closure / code correction next`
- **计划状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**

> Slice 0–3 的 accepted plan/code 历史保持不变。用户明确授权的 Codex Controller review 为 PASS-WITH-RISKS/open 0，独立 Terra review 为 PASS/open 0；Controller 接受本 manual-review handoff plan。MiM provider 401 未参与本 gate，不得记为 MiM PASS。下一步只可实施第 9 节两文件 production correction；Slice 4 文档仍等待该 code correction accepted，Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。

### Revision changelog

- 2026-08-09 plan-fix：显式加入三组 SEC download、price snapshot material import 与 `process`，统一 package config/template 真源，收窄 processed 指纹、类型边界、evidence 两层契约、timeout 协议与人工质量三态。状态仅为等待双路 plan re-review，不代表 plan accepted。
- 2026-08-09 corrective plan-fix：将 package research asset 指纹扩展为 `research_templates/` canonical tree + 根级 `定性分析模板.md` 的 materialization 输入闭包，并明确 fixture/live `verify` 模式互斥。状态仅为等待 corrective dual plan re-review，不代表 plan accepted。
- 2026-08-09 final corrective plan-fix：PRR-001 保持关闭；按 PRR-002 将绝对 home 路径禁令精确限于 acceptance harness-owned outputs，对生产 validator artifacts 只记录 package-relative locator + SHA-256、不摘录/改写内容。状态仅为等待 final corrective dual plan re-review，不代表 plan accepted。
- 2026-08-09 plan closure：DeepSeek + MiMo final corrective re-review 均 pass，Controller 关闭 PR-001..004、P1..P8、PF-EXTRA-001、PRR-001、PRR-002，open High/Medium/Low 均为 0。deterministic Slices 0–4 handoff-ready；Slice 5 仍未获 live 授权。
- 2026-08-09 Slice 2 pre-edit plan-fix：现有 `AcceptancePlan` 严格 schema 不含 run root、ordered allowlisted commands、模型绑定和 required environment presence，却要求这些事实进入唯一 plan fingerprint。选择扩展现有 contract 的单一真源方案；拒绝新增 execution-plan envelope 或双 fingerprint。状态仅为等待双路 plan re-review，不代表 Slice 2 可恢复实施。
- 2026-08-09 Slice 2 corrective plan-fix：接受两路 review 的 verify fingerprint 自引用、PhaseReceipt raw absolute argv、run-root 规格、schema 内一致性、presence 二次校验、命令结构 allowlist、receipt 前缀闭包与 schema-version findings；verify 改为 plan-owned terminal action、PhaseReceipt 升 v2 并只持久化安全 token 与 digest。状态仅为等待 corrective dual plan re-review，不代表 Slice 2 可恢复实施。
- 2026-08-09 Slice 2 final corrective observation fix：corrective 双路均 PASS；补齐固定 `verify.json` 落点、PhaseReceipt v2 字段清单、`_PHASE_SCHEMA_VERSION` 常量与 §8.2 run root/ordered specs/env presence 漂移枚举。状态仅为等待 final 双路 plan re-review。
- 2026-08-09 Slice 2 plan-fix closure：DeepSeek `plan-review-20260809-103600-deepseek.md` 与 MiMo `plan-review-20260809-103601-mimo.md` 均 PASS/open 0；本 plan-fix 全部 findings/observations CLOSED，Slice 2 可恢复实施。
- 2026-08-09 Slice 2 code-review-triggered plan-fix：接受 discovery 自引用、PhaseReceipt 缺逐命令证据、价格 material SHA、source inventory、评分真源、timeout/异常/子进程/fixture lock 等 findings；保持唯一 `AcceptancePlan` v2，PhaseReceipt fresh 升 v3，并以严格 `--quiet` owner formatter ingress 闭合 download/import/process。状态为 **FIX REQUIRED / AWAITING DUAL PLAN RE-REVIEW**，不代表可恢复实施。
- 2026-08-09 Slice 2 corrective plan-fix：DeepSeek `plan-review-20260809-123000-deepseek.md` 与 MiMo `plan-review-20260809-123001-mimo.md` 均 FAIL。按 Controller 裁决改为唯一 formatter title anchor + 可信结构/opaque tail grammar、指纹化 subprocess env、material action 分支、六节 process 派生、canonical form/SEC accession、明确 terminal receipt writer、stdout 诊断和 0-record wall；另最小扩大 allowlist，让 download formatter 固定输出顶层 status。状态为 **REVIEW OBSERVATIONS FIXED / AWAITING CORRECTIVE DUAL PLAN RE-REVIEW**。
- 2026-08-09 Slice 2 final corrective plan-fix：DeepSeek `plan-review-20260809-130000-deepseek.md` 为 FAIL，MiMo `plan-review-20260809-130001-mimo.md` 为 pass-with-risks。按 Controller 裁决把 upload 的 action/status 正交建模、process 行内可信字段收窄到 document_id、quality 回归 processed repository 真源，并补空 form 分类拒绝与完整 upload sparse grammar。状态为 **REVIEW OBSERVATIONS FIXED / AWAITING FINAL CORRECTIVE DUAL PLAN RE-REVIEW**。
- 2026-08-09 Slice 2 accepted closure：DeepSeek `plan-review-20260809-133000-deepseek.md` 与 MiMo `plan-review-20260809-133001-mimo.md` 均 PASS/open H/M/L=0；全部 code-review-triggered plan findings CLOSED，Slice 2 计划 handoff-ready。Slice 5 仍为 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED**。
- 2026-08-09 Slice 3 resume-marker plan erratum：保留 Slice 2 accepted 历史；依据当前 runner 两条 write argv 固定 `--no-resume`、run 拒绝已有执行 receipt 的事实，删除“本 Slice 用同一 plan + operator marker 测试 resume”的歧义。Slice 3 只验证 partial/non-passed receipt 永不 PASS且无自动/隐式 resume；未来 resume 必须另立 plan/schema/action（或 marker）并绑定原 plan fingerprint + 新 operator authorization。状态为 **CANDIDATE / AWAITING DUAL PLAN RE-REVIEW**。
- 2026-08-09 Slice 3 corrective plan-fix：Codex S3R-001/S3R-002 与 duplicate Terra M-001 已接受；untrusted receipt lifecycle 的唯一入口改为 public live verify/strict loader，raw evaluator 只消费已收窄 trusted inputs。§8.1 全阶段统一 no-rerun/no-resume，当前唯一恢复是人工选择全新 run root 重新开始；任何同-plan recovery 另立 work unit并定义 authorization/fingerprint/receipt/idempotency。状态为 **REVIEW OBSERVATIONS FIXED / AWAITING CORRECTIVE DUAL PLAN RE-REVIEW**。
- 2026-08-09 Slice 3 final textual plan-fix：Codex corrective review PASS；Terra corrective review FAIL/C-001。按 Controller 裁决删除 §5.1“恢复必须使用同一 run-id 和已存在 manifest”的旧合同，统一为 preserve+stop、全新 run root/new plan fingerprint；same-run-id/manifest/same-plan recovery 继续留给需新 operator authorization 与明确策略的未来独立 work unit。状态为 **REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**。
- 2026-08-09 Slice 3 accepted closure：Codex 与 Terra final dual plan re-reviews 均 PASS/open H/M/L=0；S3R-001、duplicate Terra M-001、S3R-002、Terra C-001 全部 CLOSED。Slice 3 tests-only handoff-ready；Slice 5 仍为 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。
- 2026-08-09 manual-review handoff plan-fix：真实 runner 当前会在 planned phases 后无条件启动 terminal verify，使 evaluator 的 exit 3 被持久化为 non-passed terminal receipt并阻断人工复核后的独立 verify。修订为 exact pending skeleton 的显式 handoff：`run` 返回 canonical `PENDING_MANUAL_REVIEW`/exit 3，不启动或写 terminal，不写 acceptance outputs；人工填写后只运行独立 verify。状态为 **CANDIDATE / AWAITING DUAL PLAN RE-REVIEW**，不代表修正已接受或 Slice 4 可实施。
- 2026-08-09 manual-review handoff accepted closure：Codex Controller `plan-review-20260809-173027.md` 为 PASS-WITH-RISKS/open H/M/L=0，独立 Terra `plan-review-20260809-manual-review-handoff-terra.md` 为 PASS/open H/M/L=0；Controller关闭plan gate。MiM provider 401 未参与且不计为通过。状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**；仅两文件 code correction handoff-ready，Slice 4 docs继续等待code acceptance，Slice 5仍未授权。

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
- CLI fixture verify 为保持 production artifact 字节稳定，只能使用 repository-private、`.gitignore` 已覆盖的固定 runtime root（例如 `workspace/tmp/investment-agent-aapl-fixture-verify/`），不得使用共享 `/tmp`。并发锁用原子目录创建，锁内 canonical `owner.json` 只记录 PID、UTC started_at 与非 PII run label；存在锁时 fail closed 并给出 owner/stale 诊断，不自动破锁。cleanup 失败不得掩盖主异常：有主异常时保留其为 primary 并附静态脱敏 cleanup note；无主异常时 cleanup failure 必须抛出，不得盲目 suppress。

**Live lane（opt-in、绝不进 CI）**

- 只有在 Controller 取得本次模型/外部数据/费用授权，并把 Slice 5 的 live gate 显式标记为已授权后才可执行；Slices 0–4 未来即使通过 re-review 并进入 handoff-ready，也不能替代该授权。
- 先生成不调用外部服务的 preflight plan；`prepare` 要求精确 run root 不存在，在同一父目录 staging 中构造 `data-workspace/`、canonical price snapshot/Markdown material、quality-review 骨架和 plan，再用同文件系统原子 rename 到精确 run root；任一步失败不得留下可运行的正式 run root。plan 固定 as-of、代码 SHA、模型名、预算、wall-clock、package config/template 真源、run root 和全部 argv，并给出 SHA-256。
- `run` 必须要求显式传入该 plan 指纹；只允许执行计划中列出的 `python -m dayu.cli` argv，不用 shell、不接受任意命令字符串。
- allowlist 顺序固定为三组 download → 本地 price snapshot material import → 一次 process → write preflight → 付费 write+materialize → validators。每个 planned 阶段写独立 phase receipt；任何非零退出立即停止，不自动进入后续付费阶段。plan-owned terminal action 仍为 `verify`，但只有 quality review 在 planned phases 后不再是 exact pending skeleton 且通过 strict ingress 时，当前 `run` 才可派生 terminal subprocess。
- 从 `run` 进入第一阶段开始的整条自动化 planned 链（包括三组 download、material import、process、preflight、write 与 validators）共享一个 `max_wall_seconds`；任何阶段不得重置计时。planned phases 全部 passed 而 quality review 仍是 exact pending skeleton 时，自动化链以人工 handoff 结束，后续人工填写及独立 verify 不计入该 subprocess wall-clock，但必须另记录 review 时间。
- live 产物只写入 `.gitignore` 已覆盖的 `workspace/acceptance/investment-agent-aapl/<run-id>/`；固定回归 baseline 只在验收通过并脱敏后选择性提交。

### 4.2 模块职责

- `utils/investment_agent_acceptance_contracts.py`：严格 TypedDict/dataclass/schema 解析、canonical JSON 和指纹。三个新验收模块自身导出签名与内部传播不得使用 `Any`、`object` 或无类型签名；既有 owner 返回的 `DocumentMeta = dict[str, Any]` / `dict[str, object]` 只允许在一个明确 ingress 边界立即严格解析为 frozen dataclass/TypedDict，类型或未知字段不符即 fail closed，宽类型不得继续传播。
- `utils/investment_agent_acceptance_evaluator.py`：只读确定性硬门禁/评分；同时是 live acceptance contract、null quality-review skeleton、rubric 维度/子项分值、hard-gate 列表、总分/分项阈值与 required topic/evidence parts 的唯一规则真源。它是 **trusted post-ingress pure evaluator**：只消费已由 fixture parser 或 public live verify 的 strict receipt loader/repository closure 收窄出的 frozen `AcceptanceInputs`/`RuntimeEvidence`，不是不可信 persisted receipt、schema 或 lifecycle 的 ingress。不得直接向它注入任意伪造 receipt 来要求通用 lifecycle FAIL，也不得为此复制 loader gate；它只暴露 pure builders，不执行 subprocess 或外部调用。
- `utils/investment_agent_acceptance.py`：薄 CLI、preflight plan 生成、allowlisted phase 编排和 receipt 输出；不得承载评分规则真源。
- manual-review handoff 判定只复用 evaluator `build_pending_quality_review(f"live-{plan.fingerprint[:16]}")`，并要求磁盘 `quality-review.json` 已由 strict parser round-trip 后与该 canonical builder bytes 精确相等；CLI 不复制 rubric 字段/阈值，也不新建 schema、flag、action 或 evaluator gate。
- `AcceptancePlan` 是唯一的 preflight/运行身份 contract，保持 schema v2 与唯一 fingerprint；不得在 CLI 模块另造 execution-plan envelope、第二份 plan schema 或第二个 fingerprint。ordered specs 使用独立 frozen 子类型组成 tuple，禁止把 argv 平铺成 God dataclass。Slice 2 对 evaluator 的最小修改只迁移 pure scoring/contract builders，并让它消费 receipt-derived discovery；不得把 subprocess、owner formatter 解析或编排职责移入 evaluator。
- 当前 `dayu.cli` 的 download/upload_material/process 没有 JSON 输出模式；不得发明通用 JSON serializer。三个命令仍各固定一个 `--quiet`，但不得宣称它能产生纯净 stdout：acceptance runner 以各 formatter 固定标题 `下载结果` / `上传材料结果` / `全量处理结果` 作为唯一 anchor，锚前第三方前缀允许存在，0 个或多个 anchor 一律 fail closed。完整 raw stdout 只计算 SHA-256；锚前前缀或 reject 点只形成有界静态脱敏 `stdout_summary`，不复制 raw stdout。anchor 后只解析固定标题/字段/summary/section header 与可信结构前缀，reason/message/warning/files 均为 opaque tail，不进入 evidence；禁止宽 regex、inventory-derived fallback 或修改本计划未授权的 `dayu/` 行为。
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
- 唯一 `AcceptancePlan` v2 还必须严格绑定：(1) canonical run root；(2) 按执行顺序排列的 phase specs，每个 spec 只含 plan-owned phase name 与一个或多个 argv token tuple；(3) 复用 `ModelRoles` 的 primary=`deepseek-v4-pro`、audit=`mimo-v2.5-pro-thinking`；(4) required environment names `DEEPSEEK_API_KEY`、`MIMO_API_KEY`、`SEC_USER_AGENT` 及逐项 presence boolean，绝不包含值；(5) frozen `subprocess_env_policy`，精确为有序 tuple `(("TQDM_DISABLE","1"),("HF_HUB_DISABLE_PROGRESS_BARS","1"),("TRANSFORMERS_VERBOSITY","error"))`；(6) 由 owner `build_material_ids(form_type="MATERIAL_OTHER", material_name="aapl-price-snapshot", fiscal_year=None, fiscal_period=None)` 得到的稳定 `price_material_document_id`；(7) terminal action 精确等于 `verify`。这些字段全部进入 canonical JSON/fingerprint；ordered specs **不包含** terminal verify argv，避免 `--fingerprint <自身指纹>` 自引用；runner 只在 plan canonical SHA-256 已计算并核对后，由固定 terminal action 派生 `verify --plan <plan> --fingerprint <computed> --json`，不得接受用户覆盖。
- ordered specs 精确覆盖三组 download、price import、process、write preflight、付费 write+materialize 与五个 validators。phase name 与顺序是 fingerprint-sensitive，禁止排序规范化。strict parser 校验 token matrix 的结构，run preflight 通过同一纯构造器从 plan scalars、runtime resolver 与 `sys.executable` 重建完整 specs 并要求 canonical equality：argv[0] 必须等于本次解释器，argv[1:3] 必须等于 `-m dayu.cli`，subcommand/phase/flags 属固定 allowlist；run-root、config、model 与 budget tokens 必须与 plan 字段和本次 resolver 结果一致。不得接受 command string、shell fragment、未知 phase、额外 argv、空 token、任意 executable 或字段/argv 双写不一致。
- canonical run root 采用 `Path.resolve(strict=False)` 得到的绝对 POSIX 字符串；其父目录必须真实存在、resolved、非 symlink，且精确位于当前 repository root 的 `workspace/acceptance/investment-agent-aapl/` 下；末段 run-id 仅允许 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，目标本身必须不存在。run root 进入 fingerprint，因此 plan 有意绑定当前机器与 run-id，跨机或换目录必须重新 `prepare`，不得复用 fingerprint。
- `AcceptancePlan.to_json()`、`fingerprint` 与 `parse_acceptance_plan()` 继续共用封闭 schema v2；`_PLAN_SCHEMA_VERSION=2` 不因本次 fresh plan 结构扩充而升级，但旧 v2 bytes 因 missing 新字段严格拒绝，不建兼容分支。missing、unknown、重复 phase/command、顺序变化、首尾空白 token、空 token、程序替换、字段/argv 不一致、model/env-name/presence、静态 env policy、稳定 material ID 漂移均 fail closed；严格化只限 plan/phase token 与固定顺序边界，不做全局字符串 strip 行为重写。`run` 与 live-mode `verify` 先重算 plan 文件 canonical SHA-256；`run` 还重算 HEAD/package inputs/price/预算/运行身份与 exact phase specs，任一不一致都在创建 subprocess 前失败。
- environment presence 由显式 provider 提供：deterministic 测试注入 mapping，禁止读取宿主环境；获授权 live `prepare` 与 `run` 都读取 `os.environ` 的 key 是否存在，`run` 在首次 `Popen` 前要求结果与 plan 内三个 `true` 精确一致。Popen 不得使用隐式 `env=None`：runner 复制执行所需的当前 process environment 到新 mapping，再以 plan 中精确三项 non-secret policy 覆盖同名 key，并显式传 `env=`；credential 只继承本次进程中的值，plan/receipt 仍只记录名称与 presence。任何路径都不得读取后持久化、hash 或回显 secret 值。独立 `verify` 不需要凭据、不重读环境，只可原子写 harness-owned `source-inventory.json` 与 `acceptance-receipt.json`；`phase-receipts/verify.json` 由外层 `run` 在 terminal verify subprocess 返回后写入，独立 verify 不创建或更新 phase receipt。
- raw `acceptance-plan.json` 是 `.gitignore` 覆盖的本地 run artifact，允许保存执行消歧所需的绝对 run/config argv；它不得进入提交 baseline。`PhaseReceipt` fresh 升为 schema v3，`_PHASE_SCHEMA_VERSION=3`，strict parser 明确拒绝 v1/v2 且无兼容分支。v3 以 `command_records` 替换 phase-flat `safe_argv/argv_digests/exit_code/stop_reason/termination_action/partial_by_timeout`；每个 frozen strict `CommandRecord` 精确含：`command_index`、单条 `safe_argv` tuple、单条 raw argv canonical `argv_digest`、`status`、UTC start/end、`duration_seconds`、`exit_code`、`stop_reason`、`termination_action`、`partial_by_timeout`、`stdout_sha256`、`stderr_sha256`、有界静态脱敏 `stdout_summary`/`stderr_summary` 与 discriminated `evidence`。不得另建 stream sidecar；raw stdout/stderr、绝对路径、secret 值和 provider body 不落盘。
- `CommandRecord` 类型锁定为：`command_index: int`（从 0 连续）、`safe_argv: tuple[str, ...]`、`argv_digest: str`（小写 SHA-256）、`status: Literal["passed","failed","timeout","signal"]`、`started_at/ended_at: datetime`（UTC）、`duration_seconds: float`（有限非负）、`exit_code: int | None`、`stop_reason: str | None`、`termination_action: Literal["not_started","terminate","kill","termination_unconfirmed"] | None`、`partial_by_timeout: bool`、`stdout_sha256/stderr_sha256: str | None`、`stdout_summary/stderr_summary: str | None`、`evidence: DownloadCommandEvidence | MaterialImportCommandEvidence | ProcessCommandEvidence | None`。进程成功 start 后空流也记录空字节 SHA-256；只有 start 失败才能为 null。clean formatter success 且无 anchor 前缀时 `stdout_summary=null`；有前缀或 ingress reject 时，它记录 allowlisted category、触发行号和静态脱敏片段。两个 summary 各自 UTF-8 最多 `_STREAM_SUMMARY_MAX_BYTES=512`，禁止非法 UTF-8、home path、Authorization/cookie、secret shape 或 raw provider body。
- command evidence 是 frozen strict discriminated union，unknown/missing 字段全部拒绝：(1) `DownloadCommandEvidence` 记录 ticker、raw planned forms、经 `normalize_form` 得到的 canonical forms、start/end、`owner_status`、`total/downloaded/skipped/failed` summary，以及三节中每条可信结构 row 的 `document_id/accession/canonical_form/filing_date/section_status`；不记录 warning count；(2) `MaterialImportCommandEvidence` 记录 `owner_status: Literal["ok","skipped"]`、`material_action: Literal["create","update"]`、稳定 document_id、`source_fingerprint/report_date`（按 owner_status 条件可空）、plan price JSON/Markdown SHA-256 与仓储协议 primary file SHA-256；owner 返回 delete/其它 action 或其它 status 立即 fail closed；(3) `ProcessCommandEvidence` 记录 `owner_status`、filing/material summary 或 materials TODO 分支，以及逐文档 `document_id/source_kind/status`；stdout-derived quality 不进入 evidence。write/preflight/validators/terminal 的 evidence 必须为 null，由 exit 与最终 production artifacts validator 闭合。
- `evidence` union 是闭集；未来新增成员必须同步 bump `_PHASE_SCHEMA_VERSION`，不得静默扩展。通用 lifecycle/index/time/argv/exit closure 与 domain evidence semantic gates分组测试，但 v3 strict round-trip 仍必须构造并覆盖全部当前 evidence schema 的 missing/unknown/type/discriminator 分支，不得把 round-trip 写成 evidence-free。
- owner grammar 只信固定结构：每种 stdout 的 formatter title 必须全局唯一；anchor 后固定 scalar/summary/section header 必须唯一、顺序精确，`  - （无）` 是空节唯一合法占位。Download 固定 `ticker → status → 汇总 → optional opaque warnings → 成功下载/跳过/失败 filings`，三节 row 各带 `section_status` 且 document_id 跨节唯一；可用 discovery 只来自 downloaded+skipped，failed summary 大于 0 时整命令立即 semantic stop，failed rows 绝不参与 freshness。Process 固定 filings summary、materials summary/TODO 互斥行以及 `成功/跳过/失败 × filings/materials` 六节；六节必须全部出现且唯一有序，`source_kind/status` 只由 section 派生，行内可信字段**只到 document_id**，其后的行内 status/reason/form/quality 等一律 opaque，不进入 evidence。reason/message/warning/files 及其续行同样只计入 stdout digest/必要的有界 summary，不改变 discovery。
- Upload grammar 明确为：`上传材料结果 → - pipeline → - ticker → - status → - material_action` 五行必需、唯一、有序；随后 owner 固定顺序的可选行 `form_type, material_name, company_id, company_name, document_id, internal_document_id, primary_document, uploaded_files, document_version, source_fingerprint, filing_date, report_date, overwrite, skip_reason, message` 可按 owner 空值规则缺席，但出现时不得重复或重排；`files:` 必需、唯一且在所有可选行之后，其后的 file rows 全部 opaque。仅 status/action/stable document ID/source fingerprint/report date 等已列 evidence 字段被收窄，skip_reason/message/files 内容不进入 evidence。
- form 比较唯一复用 `dayu.fins.pipelines.sec_form_utils.normalize_form`：plan argv token、owner form 与 required forms 都经该函数得到 canonical 值，禁止复制 mapping、宽 regex 或自建第二 normalizer。download row 的 `form=` 为空时**不得**调用 `normalize_form`，而要直接产生 `structure_reject`，把类别与行号写入 `stdout_summary` 并按预期 fail closed，不得让 `ValueError` 逃逸到 unexpected exit 2。SEC accession 固定正字法为 `^[0-9]{10}-[0-9]{2}-[0-9]{6}$`；只有本 plan三组 download 产生且 document_id 精确为 `fil_<SEC-accession>` 的 filing 可参与 freshness。fresh run root 出现 `fil_sec_*`、`fil_cn_*`、其它来源或其它不合法 `fil_*` 必须 fail closed；唯一 `mat_<digest>` price material明确排除在 accession 比较外。
- evidence 子类型保持 immutable strict types：日期是 ISO `date`，counts 是非负 `int` 且 summary/section row 数量闭合，rows 是 owner 顺序 frozen tuple，`section_status: Literal["downloaded","skipped","failed"]`；download `owner_status: Literal["ok","downloaded","skipped","cancelled"]` 但只有 `ok` 可继续，process `owner_status: Literal["ok","cancelled"]` 但只有 `ok` 可继续；upload material 只有 `owner_status ∈ {ok,skipped}` 可继续。process `source_kind: Literal["filing","material"]`、`status: Literal["processed","skipped","failed"]`、`todo: bool`，所有摘要为小写 SHA-256。upload `owner_status=ok` 时 source_fingerprint/report_date 必填；`owner_status=skipped` 时两者可 null，但 stable document ID + repository meta/primary SHA 必须等于 plan material identity。其它 unknown/missing/type/value mismatch 一律拒绝。
- phase 聚合 `status/started_at/ended_at/duration_seconds/remaining_wall_seconds` 保留，但必须由 records 机械闭合：`prepare` 精确 0 record；planned passed phase 的 records 数量精确等于 plan command 数；失败 phase 只允许已实际执行的非空前缀，最后一条是失败/timeout/signal 且此前全部 passed；terminal verify 精确 1 record。每条 record 的 index/safe argv/digest 必须命中同 phase 同 index planned command，聚合 status 与最后 record 一致，phase start/end 包住 record 时间且 duration/remaining 单调。首个失败后不得存在后续 receipt；terminal 只允许在全部 planned records passed 后出现。
- safe argv 仅允许 `<PYTHON>`、`<RUN_ROOT>/...`、`<PACKAGE_CONFIG>/...`；绝对路径识别同时检查独立 token 和 `--flag=/abs` 的等号右侧，未知 placeholder/绝对路径 fail closed。raw argv 只存在于 local plan 与进程内存；phase/acceptance receipts、source inventory、completion report 与 baseline 不复制 raw owner text或绝对 argv。
- 绝对 home 路径泄漏 hard gate 仅约束 acceptance harness-owned outputs：`phase-receipts/*.json`、`acceptance-receipt.json`、脱敏后的可提交 baseline 与 completion report。现有生产 validator artifacts（例如 `research-template.manifest.json`、`technology.monitoring-rules.json`）可保留 owner 写入的 package 绝对路径；verifier 不改写这些文件，不因其内嵌 package 绝对路径单独判 FAIL，也不将内容片段复制到 acceptance-owned outputs。acceptance-owned outputs 引用它们时只记录 package-relative artifact locator（例如 `research/assets/research_templates/research-template.manifest.json`）+ 文件 SHA-256，不记录生产 artifact 内嵌路径或其它原文。
- `prepare` 调用前精确 run root 必须不存在，父目录必须已解析且非 symlink。`prepare` 在同文件系统 staging 中一次性创建 run root 全部骨架与精确 `data-workspace/`，成功后原子 rename；正式 run root 不允许 `exist_ok`、merge 或 `--overwrite-research`。正式 run root 一旦存在，其 manifest/receipts/partial artifacts 在任何失败后只保留用于只读诊断；当前重新执行必须选择全新 run-id/run root，重新 `prepare` 并生成新 plan/fingerprint。任何同-run-id、existing-manifest 或 same-plan phase recovery 都属于第 8.1 节的未来独立 recovery work unit，必须取得新的 operator authorization并先定义 receipt/幂等/replay/预算策略。
- 除用户显式传入且仅供 `prepare` 只读的 price snapshot JSON 外，所有 subprocess 输入与输出真实路径必须位于精确 run root。`prepare` 对该外部 JSON 严格解析后只把 canonical JSON、确定性 Markdown 派生物和 SHA-256 写入 `inputs/`，receipt 不记录原绝对路径。拒绝 symlink 越界、`..` 与非普通文件。

### 5.2 数据 freshness / as-of policy

- `as_of` 为 preflight 时捕获的带时区 UTC 时间；同一 run 不随时钟漂移。
- 不依赖任何未验证的默认窗口。`prepare` 以同一 `as_of-date` 构建三组 download argv：`10K` 使用 `start = as-of 减 5 个日历年`；`10Q` 使用 `start = as-of 减 2 个日历年`；`8K DEF14A` 使用 `start = as-of 减 2 个日历年`；三组都显式传同一 `--end <as-of-date>` 与 resolved package `--config`。闰日减年时 clamp 到目标年最后合法日，所有日期写入 plan fingerprint。
- 三个 download planned argv 都固定且仅含一次 `--quiet`，但第三方 WARNING 仍可能出现在 stdout title anchor 前；`dayu.cli` 没有 `--json`，不得发明该 flag。为补齐现有 formatter 缺失的顶层 truth，Slice 2 唯一获准 production delta 是让 `_format_download_result` 在 `- ticker:` 后、`- 汇总:` 前固定输出唯一 `- status: <DownloadResultData.status>`，其它 formatter 行为不变。runner 必须解析该 exact 顺序；任一命令非零、owner status 非 `ok`（包括 `cancelled`）、summary `failed>0`、title/summary/section 缺失重复重排，或 10-K/10-Q/DEF 14A 任一必需 usable discovery 缺失时，不进入 material import/process/write；8-K 不存在仍只记录 warning。
- Download evidence 必须记录 downloaded/skipped/failed 三节的 `section_status`，document_id 跨节重复 fail closed；usable discovery 仅是 downloaded+skipped 两节并集，且这些 trusted structural rows 必须与 repository 独立闭合。failed 节只保留可收窄的可信结构前缀，永不参与 freshness；`summary.failed>0` 已足以立即 semantic stop，不要求把其中 reason/message tail 变成可用 discovery。plan token、owner form、required form 都经 production `normalize_form` 比较。
- 三组 download 成功后，在任何 write 前执行唯一 price import：`prepare` 已把六字段 JSON 确定性渲染为 `inputs/price-snapshot.material.md`，并用 owner `build_material_ids` 计算稳定 material ID 写入 plan；runner 用固定 `--quiet` 的现有 `upload_material --forms MATERIAL_OTHER --material-name aapl-price-snapshot --document-id <plan.price_material_document_id> --report-date <market-date>` 导入本 run 的 Fins material 仓储。直接 `.json` 不在现有 upload suffix allowlist 内，不得尝试上传原 JSON；Markdown 必须包含 canonical JSON SHA-256 和全部六字段的无损文本表示。`material_action` 只表示 owner create/update intent，不能表示 skip；delete/unknown action fail closed。`owner_status=ok` 时 document_id/source_fingerprint/report_date 全部存在；`owner_status=skipped` 时 source_fingerprint/report_date 可 null，但 document_id 必须等于 plan 稳定 ID，且 repository meta、primary SHA 与 `plan.price_material_sha256` 必须独立闭合。upload 其它 status 停止；两种允许状态的 primary SHA 都必须精确等于 plan material SHA。
- material import 成功后显式执行一次固定 `--quiet` 的 `dayu.cli process --ticker AAPL`，同时处理三组 SEC filing 与 price material。`process.json` 的单条 evidence 中 `source_kind/status` 由六个固定 section header 派生，行内只收窄 document_id；stdout quality 不可信且不得进入 evidence，质量唯一从 `ProcessedDocumentRepositoryProtocol` 的既有状态指纹读取并与 source inventory 闭合。filings summary 必须存在；materials 只允许互斥两态：完整 counts + `todo=false`，或固定 `- materials 处理: 未实现（TODO）` + counts null + `todo=true`。后者以及 process owner_status 非 `ok`、任一 summary failed、必需 filing/price material 未出现在结果中都在任何付费 write 前 semantic stop。process 全耗时计入 `max_wall_seconds`，并与仓储 processed 状态逐文档交叉闭合。
- 源清单逐文档记录：document_id、source_kind、form、filing/report date、fiscal_year/period、source URI 的安全标识、primary file SHA-256，以及仓储协议可得的 processed 存在性、`source_fingerprint`、`schema_version`、`parser_version`、`quality`、`reprocess_required` 状态指纹。processed 侧不存在内容 SHA-256 真源，本 work unit 明确不要求、不扫描私有目录重算它。不得记录下载响应中的 cookie、header 或凭据。
- 所有 filing_date 必须 `<= as_of-date`；发现未来日期、缺 filing_date、缺 primary、必需文档缺 processed、`ingest_complete != true` 或 `reprocess_required=true` 均为硬失败。
- 在显式窗口内至少存在一份 10-K、一份 10-Q 和一份 DEF 14A；8-K 若不存在可记录 warning，不得伪造。最新 10-K、10-Q、DEF 14A 必须分别与本次三个 download records 的 downloaded+skipped usable discovery 中最新可用 SEC accession 对齐，form 一律按 `normalize_form` canonical 值比较。
- deterministic fixture 的 pinned accessions 只用于回归，不用于声明“今天最新”；live freshness 只能由本次 download command evidence 证明。严禁从待校验 repository inventory 自身计算 `latest_discovery`，也严禁在 receipt 缺失/不可解析时 fallback。repository 比较集合只含本计划三次 download 产生且满足 SEC accession 正字法的 `fil_<accession>`；`mat_*` 不参与，`fil_sec_*`/`fil_cn_*`/其它来源 filing 在 fresh run root 直接 fail closed。receipt-derived discovery 与 repository 最新文档不一致必须产生 `source_price_closed` High finding并使 verdict 为 FAIL。
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
│   ├── validations.json
│   └── verify.json                 # 全部 planned specs 成功后才允许出现的 terminal receipt
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

`prepare.json` 是原子创建完成 receipt；`download.json` 内含三个有序 command records 与独立 discovery evidence；`price-snapshot-import.json` 绑定 canonical JSON、Markdown、稳定 Fins material ID/action/fingerprint/primary SHA；`process.json` 覆盖 filing + material 的唯一 process command record 与 owner summary。`verify.json` 是可选且 **passed-only** 的 terminal receipt，只能由外层 `run` 在全部 planned records 成功、quality review 非 exact pending skeleton、terminal verify subprocess 返回 0 后写入且精确含 1 record；pending/failed/signal/timeout terminal 不得持久化，旧的 non-passed terminal 仍由 strict loader 拒绝且不提供兼容层。planned phases 全部 passed且 quality review 仍是 exact pending skeleton 时，`run` 不派生/启动 terminal subprocess、不创建 `verify.json`，也不写 `source-inventory.json` 或 `acceptance-receipt.json`。独立 `verify` 永不创建或更新 phase receipt，且 terminal 缺席在完整 passed planned prefix 后是合法 handoff 状态。所有 v3 phase receipts 都使用同一 plan fingerprint，phase 聚合字段与 `command_records` 必须机械闭合，不得持久化 raw argv/stdout/stderr。

live `verify` 在 receipt-derived discovery、price material、process evidence、三个 Fins repository protocols 与 strict quality-review ingress 全部闭合后，使用同一个 frozen inventory/quality 对象调用 evaluator。operator 将 exact pending skeleton 完整填写后，只能运行独立 `verify --plan --fingerprint --json`；它允许 terminal receipt 缺席，按 evaluator 得到 PASS 或 FAIL，再原子写 strict canonical `source-inventory.json` 与 normalized `acceptance-receipt.json`。malformed quality、secret/PII shape、plan/receipt/artifact drift 在发布 acceptance outputs 前 fail closed；完整但未达阈值的合法 review 产生 canonical FAIL receipt。独立重复 verify 的 planned phase receipts 必须字节不变，且永不补写 terminal receipt。若 `run` 开始前 quality 已不是 exact pending skeleton，则先经同一 strict owner ingress；合法值按当前 terminal 路径执行，malformed/secret/drift 不得借 handoff 分支绕过。

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
- 跨平台 timeout 不依赖 POSIX process group/signal 语义：command 启动前 whole-run budget 已耗尽时写 `status=timeout`、`termination_action=not_started`、`partial_by_timeout=true`；已启动子进程超时时先调用 `terminate()`，等待固定并写入 plan fingerprint 的 `termination_grace_seconds=10`，仍 alive 则调用 `kill()` 并等待退出。无论 `not_started`/terminate/kill 路径如何，都必须原样保留 run root，且后续阶段一律不执行。若 terminate/kill 抛 `OSError` 或 kill 后仍不能确认退出，记录 `termination_unconfirmed` 并 STOP，不自动 cleanup/resume。
- `Popen` 必须固定 `cwd=<resolved repository root>`、`stdin=DEVNULL`、`shell=False`，stdout/stderr 仅以 pipe 捕获，并显式传入按 §5.1 构造、带三项 fingerprinted non-secret override 的 `env`；不得使用 `env=None`、继承调用者 cwd 或交互 stdin。0-record phase（prepare 或 command 启动前 wall exhaustion）的 wall 取 phase-level started_at→ended_at 跨度；全 run `actual_wall_seconds` 从首个实际 phase/record started_at 到 terminal/最后 phase ended_at 的端到端跨度，不得按 command/phase duration 求和低估间隙。
- write scene 保留现有 `web` 工具，因此模型侧外部请求仍是 residual；验收不修改 scene，而是以已导入 Fins material 的 price snapshot 作为估值唯一授权基准，用确定性报告一致性门禁+人工 unsupported-claim review 兦底。
- 每个 command record 保存完整 raw stdout/stderr 的 SHA-256；clean success 的 `stdout_summary` 为 null，有 title 前缀或 ingress reject 时才保存类别/行号/静态脱敏片段，stderr 非空时保存同样有界的分类摘要。两者共用 512-byte UTF-8 安全上限，不枚举真实环境变量值、不保存 traceback、绝对路径或 provider body，也不另建 stream sidecar。`main()` 对 `ContractError/OSError` 与 unexpected `Exception` 都只输出静态脱敏摘要并返回 exit 2；unexpected exception 不裸露 traceback。
- `run` 的 CLI JSON/exit contract 增加人工 handoff 终态：planned phases 全部 passed 且磁盘 quality review 与 evaluator builder 生成并 strict round-trip 的 exact pending skeleton canonical bytes 相等时，stdout 只输出 canonical JSON，至少含 `status`/`verdict="PENDING_MANUAL_REVIEW"`、已完成 planned phases与空 terminal 字段，退出码为 3。它不是失败 receipt、不得使 `RunResult.succeeded=true` 或宣称 PASS；同时必须保证 terminal process factory/Popen 调用数为 0，`phase-receipts/verify.json`、`source-inventory.json`、`acceptance-receipt.json` 均不存在。

## 8. 失败恢复、复现与 cleanup

### 8.1 恢复

- `prepare` 失败：不生成正式 run root；仅可安全清理该次尚未 rename 的精确 staging 目录，不得扫描或删除其它 run。
- 当前 acceptance `run` 是全阶段 fresh-run/no-resume runner：`download`、price import、`process`、write preflight、write、materialize、validators 或 terminal verify 任一失败，都保留已有 output/manifest、command records、phase receipts、仓储 journal 与 partial 产物并立即停止；不得自动/隐式 resume，不得在已有 phase receipt 的 run root 上重跑任一 phase，也不得手工覆盖、删除、改名 receipt 后继续。
- `download` 三组任一失败：只允许用仓储 recovery/read-only inventory 诊断现状；不重新执行同一 plan/run root，不删 `data-workspace`，不重写 as-of/start/end。
- price material import 失败：保留 canonical JSON/Markdown、稳定 `price_material_document_id`、import receipt 与仓储状态，不进入 process/write；当前不得依赖 upload 幂等语义进行同-plan retry，不得 overwrite 或更换 snapshot。
- `process` 失败：保留仓储 journal、已生成 processed 与 `process.json`，不进入任何付费 write；可用仓储协议只读盘点 `source_fingerprint/schema_version/parser_version/reprocess_required`，但当前不得人工重跑 process 或继续后续 phase。
- write preflight 失败：不得创建 write run，不进入付费 write；保留 receipt 并停止。
- write 中断：保留 output/manifest 与 truthful partial/non-passed receipt；preflight 与 paid write argv 均固定 `--no-resume`，不得自动重试鉴权、额度、内容策略或预算错误。
- write budget blocked：立即 FAIL；不得通过扩大预算或 `--force` 自动继续。
- materialize 失败：依赖现有 13 文件 byte-exact rollback；验收器核对目标与失败前 snapshot、不自写第二套 rollback，随后保留 receipt/现场并停止，不重跑 write/materialize。
- workbook/source-map 手工更新如进入未来 work unit，必须走现有 immutable backup/rollback；本次 baseline 不做这类变更。
- validation/quality FAIL：保留产物用于审计，不把失败目录重命名成 passed、不改评分输入、不重新运行已有 receipt 的 phase。
- planned phases 全部 passed且 exact pending skeleton 触发人工 handoff：保留全部 passed planned receipts，`run` 以 `PENDING_MANUAL_REVIEW`/exit 3 正常交还 operator；这不是 phase failure，也不得写 non-passed terminal receipt。operator 只可完整填写现有 `quality-review.json` 后调用独立 `verify --plan --fingerprint --json`；不得再次调用同一 plan 的 `run`、手动创建/删除/覆盖 `verify.json`，也不得修改任何 planned receipt。独立 verify 的 PASS/FAIL 都不补 terminal receipt；invalid/malformed/secret/drift 在 acceptance outputs 发布前 fail closed。
- wall-clock timeout：按第 7 节 `terminate → 10s grace → kill` 协议收敛，当次 acceptance 立即 `FAIL`，后续阶段不执行；原样保留目录与仓储 journal，residuals 标记 `partial_by_timeout`，不自动 resume、删除、重命名或再次消费。
- 当前唯一可执行恢复是：operator 检查保留现场后，选择**全新 run root** 重新 `prepare` 并从头开始；新 run 生成自己的 plan/fingerprint，若涉及 SEC/模型/网络/付费调用必须重新经过 Slice 5 live authorization。不得把旧 run 的 receipt 或 partial artifacts 复制成新 run 的成功证据。
- 任何未来对原 plan/run 的同-plan retry/resume（无论 download、import、process、write 或 validator phase）都完全 out-of-scope，必须进入独立 recovery work unit：取得显式新的 operator authorization，定义 receipt 替换或追加策略、phase selection、幂等/重复副作用边界、预算与 wall-clock 续算、replay policy，并把 durable recovery action/marker 绑定原 acceptance plan fingerprint。当前 Slice 3 不设计/实现该协议，不创建 test-local marker，也不新增 production flag/action/gate。

### 8.2 复现

- `acceptance-plan.json` canonical JSON 指纹是运行身份；任何 as-of、三组窗口、price JSON/Markdown、预算、模型、代码、package config canonical tree/诊断用关键文件、package `research_templates/` canonical tree、根级 `定性分析模板.md`、canonical run root、ordered phase specs、required environment presence、timeout grace 或命令变化都生成新 run-id/plan。
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

- 修改 `utils/investment_agent_acceptance_contracts.py`
- 新建 `utils/investment_agent_acceptance.py`
- 修改 `utils/investment_agent_acceptance_evaluator.py`
- 修改 `tests/test_investment_agent_acceptance.py`
- 修改 `dayu/fins/cli_formatters.py`
- 修改 `tests/fins/test_cli_formatters_coverage.py`

**变更内容**

- 子命令仅为 `prepare`、`run`、`verify`，三者都把 `--json` 定义为显式必填固定输出契约；缺少 `--json` 在产生任何输出/读取产物前 exit 2。删除三个 command dataclass 的 dead `json_output` 字段，不保留 no-op flag 状态。`AcceptancePlan` 保持 v2 且只能落在 contracts owner；CLI 不定义 envelope 或第二 fingerprint。
- evaluator owner 暴露 pure `build_live_acceptance_contract(...)` 与 `build_pending_quality_review(...)`；rubric dimensions/items/max score、hard gates、required topics/evidence parts、总分/最低分/分项阈值只在 evaluator 定义。CLI 删除 `_QUALITY_DIMENSIONS`、`_HARD_GATES` 和内联 100/85/dimension minima，只传 plan/price/material identity 并调用 builders；fixture/tests 是被一致性测试守卫的快照，不是第二规则真源。
- `prepare` 不联网、不调用模型，验证新 run root、resolver 返回的 package config/asset 真源与模型目录价格、环境变量名称 presence、显式预算/wall-clock/as-of 与本地 price snapshot 六字段/时效。它用 owner `build_material_ids` 得到稳定 price material ID，绑定三项静态 subprocess env policy，在同父目录 staging 生成 `data-workspace`、canonical JSON/Markdown material、由 evaluator builder 产生的 quality-review null 骨架、全部 argv 与 plan fingerprint，然后原子 rename 到精确 run root。
- `dayu/fins/cli_formatters.py` 的唯一改动是 `_format_download_result` 在 ticker 行后、summary 行前输出一次 `- status: {result.status}`；不改其它 formatter 行、公共 serializer 或 JSON 模式。owner test 精确锁定 `ok`/`cancelled` 两态的标题→ticker→status→summary 顺序与唯一性。
- `run` 要求 `--plan` 和 exact fingerprint；只执行 10K download → 10Q download → 8K+DEF14A download → price snapshot `upload_material --document-id <stable-id>` → 一次 `process` → write preflight → 付费 write+materialize → validators → verify。download/import/process 每条 argv 固定一个 `--quiet`，通过唯一 title anchor + trusted structure/opaque tail grammar 收窄；全部 `dayu.cli` argv 显式使用同一 package `--config`。Popen 使用 argv list、repo cwd、DEVNULL stdin、`shell=False`、显式 fingerprinted env 与整次 run 剩余 wall-clock timeout。
- `_execute_command` 返回 stdout/stderr bytes/text与执行事实，`_execute_phase` 逐条构造 v3 `CommandRecord`，在开始下一条前完成 command-specific semantic validation。download/process 只有 owner_status=ok 可继续；upload_material 只有 ok/skipped 可继续且 skipped 走 repository closure；其它 status 或 delete/unknown material action 即使 exit 0 也停止。title 0/多次、可信结构 missing/duplicate/reorder 停止，但 anchor 前第三方前缀与 owner opaque tail 不作为 evidence grammar。
- `verify` 只读既有 production artifacts，允许重复运行；源 inventory 通过 Fins storage protocols 构建，禁止目录扫描。它有且仅有两种互斥模式：deterministic fixture 模式只接受 `--fixture <dir>`，live/run 模式必须同时接受 `--plan <file> --fingerprint <sha256>`；两种模式都显式要求 `--json`。live 模式只从 downloaded+skipped download evidence 构建 latest discovery，完成 import/process/repository 闭合后原子写 canonical `source-inventory.json` 与 normalized acceptance receipt，再调用 evaluator；独立 verify 不写 phase receipt，terminal `verify.json` 由 run 写。
- runner 在任何 semantic failure、非零、timeout、signal、receipt mismatch 后停止；timeout 使用 `not_started` 或跨平台 `terminate → 10s grace → kill` 协议，写 truthful v3 record。unexpected exception 静态脱敏 exit 2；不自动 resume、不扩大预算、不删除产物。
- 删除未使用的 form 常量/重复 form 字面量与重复 git-object-id regex，使窗口/正则各有一个真源；fixture budget/wall/evaluation offset 使用具名常量。保留 untracked-files dirty 严格判定、receipt 临时残留 fail-closed、composition-root 的私有 materializer/Fs concrete 构造与单一 pure God builder 判断，不扩大生产范围。

**预期断言**

- fake command runner 验证三组 download 窗口、stable-ID snapshot import、process、preflight 和 write 的精确顺序/argv；download/import/process 精确含一个 `--quiet`，upload 精确含 plan-bound `--document-id`，process 严格在 download+import 之后且早于任何付费 write，付费 write绝不早于成功 preflight。
- plan fingerprint/HEAD/package config canonical tree 或诊断用关键文件/package `research_templates/` canonical tree/根级 `定性分析模板.md`/price JSON 或 Markdown/as-of/窗口/预算/stable material ID/三项 subprocess env policy 任一漂移均在 subprocess 前失败；Popen 显式 env 精确覆盖三个固定 non-secret 值且 receipt 不含 secret 值。
- owner formatter test 用 `ok`/`cancelled` DownloadResultData 锁定唯一 status 行及标题→ticker→status→summary 顺序；acceptance test 用同一真实 formatter 两态，`cancelled` 即使 exit 0 也必须在 paid write 前停止。
- 用真实 `format_fins_cli_result` 构造 download/upload_material/process stdout：标题前注入 edgar/httpx WARNING 仍解析成功、evidence 与 clean stdout 相同，完整 stdout digest 不同且 `stdout_summary` 有界脱敏；0/多标题 fail closed。anchor 后固定 title/scalar/summary/section header 缺失、重复、重排 fail closed；reason/message/warning/files 含 `|`/换行只作为 opaque tail，不能污染 evidence；clean success summary 为 null。
- Download tests 覆盖 downloaded/skipped/failed 三节、唯一 `（无）` 占位、跨节 document_id duplicate、all-skipped usable discovery、failed summary semantic stop、downloaded/skipped repository closure；`normalize_form("DEF14A")` 与 owner `DEF 14A` 同源闭合，禁止复制 mapping。空 `form=` 不调用 normalizer，必须 categorized `structure_reject` + line 写入 stdout_summary，不能落 unexpected exit 2。合法 SEC accession 参与 freshness，`fil_sec_*`/`fil_cn_*`/malformed `fil_*` fail closed，`mat_*` 排除。
- Upload grammar tests 锁定 title→pipeline→ticker→status→material_action、固定可选字段顺序与必需 files header；可选行允许缺席但不得重排/重复，files rows opaque。Material tests 用真实 formatter覆盖 `status=ok/action=create|update` 三字段必填、`status=skipped/action=create|update` fingerprint/report-date null 仍由 stable document ID + repository meta/primary SHA 闭合，以及 delete/unknown action、其它 status、SHA mismatch fail closed。
- Process tests 覆盖六节唯一有序、source_kind/status 由 header 派生、materials counts 与 TODO 行互斥、TODO counts null 且 semantic stop；构造 `reason="... | quality=fake"` 必须不污染 evidence、不误判 drift，quality 只能从 fake `ProcessedDocumentRepositoryProtocol` 状态指纹闭合。
- exit 0 但 download/process owner_status `cancelled`、download `summary.failed>0`、缺 10-K/10-Q/DEF 14A usable discovery、process failed/todo/缺 price material 都必须在付费 write 前停止；upload `skipped` 仅在 stable ID/repository SHA 闭合时可继续。receipt discovery 与 repository 最新 accession 不一致必须产生 `source_price_closed` High finding + FAIL。
- 每条 command record 单独断言 index、start/end/duration、exit、safe argv/digest、stdout/stderr digest/summary、evidence；第二条 download 失败只允许两个 records。v3 strict round trip 必须带全部 evidence union，并覆盖 missing/unknown/type/discriminator；另组 domain semantic tests，不得让 lifecycle roundtrip 替代 evidence schema coverage；v1/v2 receipt 明确拒绝。
- stdout/stderr/expected 与 unexpected 异常含 secret shape 时输出与 receipt 均静态脱敏；stream summaries 有界且不得新建 sidecar。
- prepare、三组下载、import、process、preflight、write、materialize、verify 每个失败点都只执行允许的前缀阶段。fake clock 覆盖首命令前与 terminal 前 whole-wall exhaustion，均断言 `timeout/not_started/partial=true`；fake process 覆盖 terminate/kill 成功、等待超时及 terminate/kill 抛 `OSError` 的 `termination_unconfirmed`，后续命令数为 0且现场保留。
- Popen 测试锁定 repo cwd、DEVNULL stdin、shell false 与显式 env；0-record phase wall 使用 phase start/end，全 run actual wall 使用首个实际 phase/record到 terminal/last phase 的端到端跨度，并拒绝 remaining wall 递增。
- fixture runtime-root 测试覆盖 repo-private ignored 路径、atomic owner lock、真实并发 fail closed、stale owner 可诊断；cleanup 失败有主异常时保留主异常并附 note，无主异常时 raise cleanup error。
- CLI 参数测试要求 `prepare/run/verify` 都显式带 `--json`；覆盖 `verify --fixture --json` 与 `verify --plan --fingerprint --json` 两个 happy path，以及缺 `--json`、两模式同传、单独 `--plan`、单独 `--fingerprint` 的 exit 2。断言 command dataclass 不含 dead `json_output` 字段。
- contract 测试覆盖 run root、ordered phase/commands、model binding、required environment names/presence 的 strict round trip；逐项 missing/unknown/重复/reorder/空 token/错误类型 fail closed。fake runner 断言任一执行身份或文件指纹漂移都在首次 `Popen` 前失败，且 deterministic presence 由注入 mapping 决定、与宿主真实 env 无关。
- 测试证明 plan fingerprint 一次计算完成且 terminal verify 在其后派生；不存在 fingerprint 占位符、二次写回或自引用。给定真实 home 下的 absolute run/config argv，PhaseReceipt v3 command records 只含三个受控 placeholder 与 raw argv digest，`--flag=/abs` 同样拒绝，evaluator sanitizer 不产生 finding；v1 receipt、v2 receipt 与 v1 plan 均明确拒绝。
- 测试逐项注入 executable/subcommand/flag/model/run-root/config/budget 与 plan 字段不一致、未知 phase、record safe argv/digest mismatch、receipt skip/reorder/duplicate/计划外后缀，均在首次 subprocess 前或 verify 时 fail closed。live fake presence provider 在 prepare 后移除任一 required name，`run` 必须在首次 `Popen` 前停止。
- evaluator builder 与 deterministic fixture 的 hard gates、rubric shape、100/85/分项阈值、topics/evidence parts 一致性测试证明一个规则真源 + 一个守卫快照；AST/源码验证对象精确是 `utils/investment_agent_acceptance.py`，其中不得残留 rubric/hard-gate/dimension/100/85 规则真源，不误扫 `dayu/cli/`。
- live verify 原子写 `source-inventory.json`，canonical bytes/strict parser/同一 frozen object 闭合；symlink、非同字节 overwrite 或写入失败不得继续 evaluator。独立 verify 前后 `phase-receipts/` 字节不变；run terminal 路径写的 `verify.json` 精确 1 record。

### Slice 3 — 现有 CLI 集成与恢复场景

**允许文件**

- 修改 `tests/test_investment_agent_acceptance.py`
- 修改 `tests/cli/test_research_template_command.py`

**变更内容**

- 用真实 parser/dispatch（外部边界 fake）锁定 AAPL 三组 forms/start/end/base、`upload_material MATERIAL_OTHER`、随后一次 process、每条 argv 共用 resolver 返回的 package config、明确 DeepSeek/MiMo、完整预算、technology/materialize、隔离 output/research-base 参数。
- 复用现有 materialization 注入故障，证明验收器看到 byte-exact rollback。
- 证明 failed/signal/timeout/incomplete/non-passed persisted receipt 只能通过 public live `verify_acceptance()`/strict receipt loader/composition boundary 进入，并在调用 trusted evaluator 前 fail closed；raw evaluator 不是不可信 receipt/schema/lifecycle ingress，不要求 direct evaluator 对任意伪造 `RuntimeEvidence` FAIL，也不为此新增 production gate。
- 当前 runner 的 preflight/paid write 始终携带 `--no-resume`，且任何已有 planned/terminal receipt 都使新的 `run` fail closed，因此任一 phase 都不存在自动、隐式或 receipt-deletion 驱动的 resume/rerun。
- 未来 resume 完全不属于 Slice 3：若另行立项，必须定义新的 plan/schema/action（或 durable authorization marker），绑定原 acceptance plan fingerprint 并取得新的 operator authorization，再经过独立 plan/code review。Slice 3 不得创建 test-local marker、调用 resume 路径或把 owner 的通用 resume 能力伪装成本验收已授权行为。
- 证明 unbound technology plan 可“结构健康但运行 blocked”，最终 receipt 必须在 residuals 报告它。

**预期断言**

- 不增加新的 production CLI action/flag。
- partial receipt 测试只能构造当前 v3 的 failed/signal/timeout/不完整/non-passed persisted prefix，并通过 public live verify/receipt loader 调用；断言 `ContractError`、trusted evaluator 调用计数为 0、`acceptance-receipt.json` sentinel 字节与 phase receipts 均不变、后续 command/phase 数为 0。不得 direct-call evaluator 后声称它负责拒绝任意伪造 lifecycle input，也不得新增 evaluator lifecycle gate。
- 同一 plan 再次调用 `run` 必须因任一已有 phase/terminal receipt 在任何 process factory/Popen 前拒绝；测试锁定两条 write argv 各精确一个 `--no-resume`，不得定义 authorization-marker fixture、resume command、receipt cleanup workaround 或绕过 `--no-resume`。
- existing research-template tests 保持通过；验收器不通过 compatibility wrapper 调用 owner。
- 代码事实若显示 CLI 无法直接接受 package config dir 或 Markdown material 无法被 upload/process/Fins tools 闭合，必须 STOP 并报告 plan gap，不得创建新 flag、scene 或 owner wrapper。

### Slice 4 — 操作文档与 README 同步

Slice 4 开始前必须先完成以下 **manual-review handoff production correction** 并通过独立双路 plan/code review；这是一项最小 pre-doc blocker，不撤销 Slice 2/3 accepted 历史，也不扩大 Slice 4 文档 allowlist。

**修正允许文件**

- 修改 `utils/investment_agent_acceptance.py`
- 修改 `tests/test_investment_agent_acceptance.py`

**禁止扩展**

- 不修改 `utils/investment_agent_acceptance_contracts.py` 或 `utils/investment_agent_acceptance_evaluator.py`；现有 evaluator builder、strict quality parser、`Verdict` 与 terminal-absent loader 已足够。
- 不新增 production action/flag/schema/receipt status，不创建人工 authorization marker，不改变 `AcceptancePlan` v2 或 `PhaseReceipt` v3；terminal persisted contract 仍为 passed-only。

**状态机与预期断言**

- `prepare` 继续写 evaluator `build_pending_quality_review(f"live-{fingerprint[:16]}")` 的 strict canonical exact skeleton，不新增第二模板真源。
- planned phases 全部成功后，runner 在派生 terminal argv、检查 terminal whole-wall 或调用 process factory 前，strict 读取 quality review并与同一 evaluator builder canonical bytes 比较。exact pending skeleton → canonical `PENDING_MANUAL_REVIEW` JSON、exit 3；planned receipts 全部 passed且字节稳定，terminal Popen=0，`verify.json`/source inventory/acceptance receipt 全部不存在。
- operator 完整填写合法 review 后，只运行独立 live verify；完整 passed planned prefix + terminal absent 必须合法。PASS review 生成 PASS inventory/receipt，完整但未达标的合法 review生成 FAIL receipt；两条路径前后 planned receipt bytes相同，且都不创建 terminal receipt。
- malformed quality、unknown/missing/type/schema、非 canonical/secret/PII、plan fingerprint、receipt prefix、repository/artifact drift 均在 acceptance outputs 发布前 fail closed。若 review 在 `run` 前已是其它 strict-valid非 exact skeleton，runner 不走 handoff shortcut，保持当前 terminal strict path；不得把 partial pending或人工预填伪装成初始 exact skeleton。
- 旧 failed/signal/timeout/incomplete/non-passed terminal receipt 仍在 evaluator 前拒绝，sentinel acceptance outputs与所有 phase receipt bytes不变；不增加兼容 parser或清理/覆盖路径。
- 同一 plan `run` 仍是 no-resume：人工 handoff 后已有 planned receipts使再次 `run` 在 process factory/Popen 前拒绝；人工步骤不能借机重跑任何 planned phase。

在该 correction 的 plan re-review 与 code review 均接受前，下面 Slice 4 保持冻结；Slice 5 仍未授权。

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

`prepare`、`run`、`verify` 三个 acceptance 子命令都只有显式 `--json` 输出契约；该 flag 必填而非存入 command object 的可选 boolean。缺少它时 exit 2，CLI 不提供隐式 JSON 或另一套人读输出。下列 Fins owner 命令没有 JSON mode；download/upload_material/process 仍固定 `--quiet`，但解析必须允许唯一 formatter title anchor 前的第三方 stdout 前缀，并按 plan-bound 静态 env policy 尽量降噪。

`<resolved-package-config-dir>` 不是用户输入；它必须由 `resolve_package_config_path()` 在 `prepare` 中解析且指纹化。runner 生成的现有 CLI argv 必须与下列结构等价，日期值在 plan 生成后不得重算。

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 10K \
  --start <as-of-minus-5-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir> \
  --quiet
```

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 10Q \
  --start <as-of-minus-2-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir> \
  --quiet
```

```bash
.venv/bin/python -m dayu.cli download \
  --ticker AAPL \
  --forms 8K DEF14A \
  --start <as-of-minus-2-calendar-years> \
  --end <as-of-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir> \
  --quiet
```

`download.json` 在同一 phase receipt 中依次保存上述三个 argv 与各自结果。随后的价格 material import 必须使用 `prepare` 产生且已在 plan 中指纹化的 Markdown：

```bash
.venv/bin/python -m dayu.cli upload_material \
  --ticker AAPL \
  --forms MATERIAL_OTHER \
  --material-name aapl-price-snapshot \
  --document-id <plan-bound-stable-price-material-document-id> \
  --files <run-root>/inputs/price-snapshot.material.md \
  --report-date <price-market-date> \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir> \
  --quiet
```

`<plan-bound-stable-price-material-document-id>` 必须由 `prepare` 调用 production owner `build_material_ids(form_type="MATERIAL_OTHER", material_name="aapl-price-snapshot", fiscal_year=None, fiscal_period=None)` 生成、写入 `AcceptancePlan` 并由 upload owner 校验，不得在验收器复制 SHA-1 seed 算法。

import 成功后、任何 write 前只执行一次：

```bash
.venv/bin/python -m dayu.cli process \
  --ticker AAPL \
  --base <run-root>/data-workspace \
  --config <resolved-package-config-dir> \
  --quiet
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

validation argv 必须覆盖 `research-template validate-research-workbook --workbook ...`、`validate-workbook-report --report ...`、`validate-source-map --rules ... --source-map ...`、`validate-bundle --bundle ...`、`validate-monitoring-plan --plan ...`；每条都显式传 `--base <run-root>/research --config <resolved-package-config-dir>`，路径只指向第 5.4 节固定的 13 个产物。若 planned phases 后仍是 exact pending skeleton，`run` 在此停止并以 canonical `PENDING_MANUAL_REVIEW`/exit 3 交还 operator，不派生 terminal 命令。operator 完整填写 review 后，才独立运行 `.venv/bin/python -m utils.investment_agent_acceptance verify --plan <run-root>/acceptance-plan.json --fingerprint <exact-fingerprint> --json`；该命令不写 terminal receipt或改 planned receipts。不得把多个命令拼成 shell 字符串。

## 11. 开发验证命令

每个 Python slice：

```bash
source .venv/bin/activate
```

```bash
python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q
```

```bash
python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q \
  --cov=utils.investment_agent_acceptance \
  --cov=utils.investment_agent_acceptance_contracts \
  --cov=utils.investment_agent_acceptance_evaluator \
  --cov=dayu.fins.cli_formatters \
  --cov-report=term-missing
```

coverage 报告必须显示本次新增 download formatter status 行、owner-formatter ingress、v3 records/evidence、whole-wall `not_started`、terminate/kill `OSError`、fixture lock/cleanup、unexpected exception 与 source-inventory atomic write 分支被执行；不得只报告总百分比掩盖这些安全分支。

```bash
python -m pytest tests/cli/test_research_template_command.py -k "materialize or research_workbook or workbook_report or source_map or monitoring" -q
```

```bash
python -m pytest tests/engine/test_source_list_builder.py tests/engine/test_execution_summary_builder.py tests/application/test_write_service.py -q
```

```bash
pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py
```

```bash
ruff check --select F,I utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py
```

```bash
git diff --check -- utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py tests/fixtures/investment_agent/aapl_acceptance docs/acceptance README.md tests/README.md
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

1. **Plan gate（Slices 0–4）**：Slice 0–3 的 accepted plan/code 历史保持不变。本 manual-review handoff erratum 已由用户明确授权的 Codex Controller review与独立 Terra review完成双路复核，Controller adjudicate open H/M/L=0；状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**。第 9 节两文件 production correction可进入 implementation/code-review gate；Slice 4 文档仍等待该 correction accepted。MiM provider 401 未参与本 gate且不计为通过。该状态不授权 Slice 5 或任何 live 外部调用。
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

上述最终统计是 pre-code-review 历史 closure，不代表当前 Slice 2 WIP 已通过。新 code-review-triggered 链如下：

12. DeepSeek Slice 2 code review：`docs/reviews/code-review-20260809-114000-deepseek.md`（FAIL）
13. MiMo Slice 2 code review：`docs/reviews/code-review-20260809-114001-mimo.md`（FAIL）
14. Controller-adjudicated plan fix：`docs/reviews/plan-fix-20260809-121500-codex.md`（首次 fix，随后双路 plan review FAIL）
15. DeepSeek plan review：`docs/reviews/plan-review-20260809-123000-deepseek.md`（FAIL；H3/M4/L1）
16. MiMo plan review：`docs/reviews/plan-review-20260809-123001-mimo.md`（FAIL；H2/M3/L2）
17. Corrective Controller-adjudicated plan fix：`docs/reviews/plan-fix-20260809-124500-codex.md`（首次 corrective fix）
18. DeepSeek corrective plan re-review：`docs/reviews/plan-review-20260809-130000-deepseek.md`（FAIL；G-001/G-002/G-003）
19. MiMo corrective plan re-review：`docs/reviews/plan-review-20260809-130001-mimo.md`（pass-with-risks；新增 Low 2）
20. Final corrective Controller-adjudicated plan fix：`docs/reviews/plan-fix-20260809-131500-codex.md`
21. DeepSeek final corrective plan re-review：`docs/reviews/plan-review-20260809-133000-deepseek.md`（PASS；open H/M/L=0）
22. MiMo final corrective plan re-review：`docs/reviews/plan-review-20260809-133001-mimo.md`（PASS；open H/M/L=0）
23. Controller durable acceptance closure：`docs/reviews/plan-acceptance-20260809-134500-codex.md`
24. Slice 3 resume-marker plan erratum：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`（candidate；等待 dual plan re-review）
25. Codex Slice 3 erratum plan review：`docs/reviews/plan-review-20260809-slice3-resume-codex.md`（FAIL；S3R-001/S3R-002）
26. Terra Slice 3 erratum plan review：`docs/reviews/plan-review-20260809-slice3-resume-terra.md`（FAIL；M-001，duplicate of S3R-001）
27. Controller corrective plan fix：`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`（等待 corrective dual plan re-review）
28. Codex corrective plan re-review：`docs/reviews/plan-review-20260809-slice3-resume-corrective-codex.md`（PASS；open H/M/L=0）
29. Terra corrective plan re-review：`docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md`（FAIL；C-001 Medium）
30. Controller final textual plan fix：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`（等待 final dual plan re-review）
31. Codex final plan re-review：`docs/reviews/plan-review-20260809-slice3-resume-final-codex.md`（PASS；open H/M/L=0）
32. Terra final plan re-review：`docs/reviews/plan-review-20260809-slice3-resume-final-terra.md`（PASS；open H/M/L=0）
33. Controller durable accepted closure：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
34. Manual-review handoff plan-fix：`docs/reviews/plan-fix-20260809-manual-review-handoff-codex.md`
35. 用户明确授权的 Codex Controller plan review：`docs/reviews/plan-review-20260809-173027.md`（PASS-WITH-RISKS；open H/M/L=0）
36. 独立 Terra plan review：`docs/reviews/plan-review-20260809-manual-review-handoff-terra.md`（PASS；open H/M/L=0）
37. Controller durable accepted closure：`docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md`

### Slice 3 resume erratum Controller adjudication

| Finding | Decision / status | Corrective destination |
|---|---|---|
| Codex S3R-001 | **CLOSED** | raw evaluator 明确为 trusted post-ingress pure evaluator；failed/signal/timeout/incomplete/non-passed persisted receipts 只经 public live verify/strict loader，并在 evaluator 调用前 fail closed；禁止 direct evaluator 伪造 lifecycle 断言或新增 production gate |
| Terra M-001 | **CLOSED AS DUPLICATE** | 与 S3R-001 相同 trust-boundary finding，合并到同一 public composition-boundary tests |
| Codex S3R-002 | **CLOSED** | §8.1 download/import/process/write/validation 全阶段统一 fresh-run/no-resume；当前只允许全新 run root 从头开始，所有同-plan recovery 进入独立 work unit并定义新授权、receipt policy、幂等与 fingerprint 绑定 |
| Terra C-001 | **CLOSED** | §5.1 删除同 run-id/existing manifest 当前恢复合同；正式 run root 失败后只读保留，当前重执行必须新 run-id/root + 新 plan/fingerprint，same-plan recovery 仍归未来独立 work unit |

### Slice 2 code-review-triggered Controller adjudication

| Source finding | Decision | Plan destination |
|---|---|---|
| DS H-1 | **ACCEPT** | download command evidence 是 live latest discovery 唯一真源；禁止 inventory-derived fallback |
| DS H-2 | **ACCEPT** | PhaseReceipt v3 frozen `CommandRecord` + discriminated owner evidence；逐命令前缀/时间/退出闭合 |
| DS M-1 | **DUPLICATE / ACCEPT IN PART** | 与 MiMo M-7 合并：repo-private runtime root、owner lock、可诊断 stale、保留主异常；不盲 suppress cleanup |
| DS M-2 | **ACCEPT** | whole-wall 启动前/terminal 前耗尽统一 `timeout/not_started/partial=true` |
| DS M-3 | **DUPLICATE / ACCEPT IN PART** | 与 MiMo M-4 合并：stderr digest + 有界静态脱敏分类摘要进入 record；拒绝独立 stderr 文件 |
| DS M-4 | **ACCEPT** | import document/source fingerprint/repository primary SHA 与 `plan.price_material_sha256` 闭合 |
| DS M-5 | **REJECT / CLOSED** | 保留 untracked dirty 严格性；未跟踪 Python 可改变实际 import/执行行为 |
| DS L-1 | **ACCEPT** | live verify 原子写 canonical `source-inventory.json` 并使用同一 frozen object |
| DS L-2 | **DUPLICATE** | 由 MiMo L-3 的 form/window 单一真源修复覆盖 |
| DS L-3 | **DUPLICATE** | 由 MiMo L-5 的具名 fixture budget/wall/time constants 修复覆盖 |
| DS L-4 | **REJECT / CLOSED** | receipt 临时残留继续 fail closed，交人工恢复；不静默忽略未知文件 |
| DS L-5 | **REJECT / CLOSED** | Fs concrete/private materializer 仅在 composition root 构造后交 Protocol，当前唯一 owner 不扩架构 |
| MiMo H-1 | **ACCEPT** | evaluator 成为 live contract/null rubric/rubric/hard-gate/阈值唯一规则真源；Slice 2 allowlist 加 evaluator |
| MiMo M-2 | **ACCEPT** | unexpected `Exception` 静态脱敏、无 traceback、exit 2 |
| MiMo M-3 | **ACCEPT** | Popen 固定 repository cwd、DEVNULL stdin、shell false |
| MiMo M-4 | **ACCEPT IN PART** | 接受 receipt 内 digest + 有界静态脱敏分类摘要；拒绝 sidecar stderr 文件双真源 |
| MiMo M-5 | **ACCEPT** | fake clock 覆盖首命令/terminal 前 whole-wall exhaustion 与 remaining 单调性 |
| MiMo M-6 | **ACCEPT** | terminate/kill `OSError` 与等待超时均锁定 `termination_unconfirmed` |
| MiMo M-7 | **ACCEPT IN PART** | repo-private atomic owner lock + stale 诊断；cleanup 有主异常附 note，无主异常 raise，不盲 suppress |
| MiMo L-1 | **ACCEPT** | safe argv 同时检查独立 token 与 `--flag=/abs` 右值 |
| MiMo L-2 | **ACCEPT IN PART** | 只在 plan/phase token/order 边界拒绝空白/重排；拒绝全局宽泛 strip 行为改动 |
| MiMo L-3 | **ACCEPT** | 删除 dead form literal 或统一到一个 window/form 真源 |
| MiMo L-4 | **ACCEPT** | 复用 contracts git object-id regex，删除重复 regex |
| MiMo L-5 | **ACCEPT** | fixture budget/wall/evaluation offset 全部具名；评分数字迁 evaluator 真源 |
| MiMo L-6 | **ACCEPT** | actual wall 使用首 record start 到末 record end 的端到端跨度 |
| MiMo L-7 | **ACCEPT** | `prepare/run/verify` 显式必需 `--json`；删除 dead `json_output` 字段 |

上述 code-review findings 裁决保持不变；首次 plan fix 的两份 plan reviews 都是 FAIL，新增 observations 的 Controller 裁决如下：

| Review finding | Decision | Corrective destination |
|---|---|---|
| DeepSeek F-001 | **ACCEPT / FIXED IN PLAN** | Process 六节唯一有序；source_kind/status 由 header 派生，行内只取可信结构字段 |
| DeepSeek F-002 | **ACCEPT / FIXED IN PLAN** | AcceptancePlan v2 指纹化三项静态 env policy；Popen 显式 env；唯一 title anchor + stdout summary |
| DeepSeek F-003 | **ACCEPT / FIXED IN PLAN** | 经 G-001/G-002 最终校正：action 仅 create/update；顶层 status=ok/skipped 判别字段闭合 |
| DeepSeek F-004 | **ACCEPT / FIXED IN PLAN** | title/summary/section/trusted-prefix grammar；reason/message/warning/files opaque；移除 warning count |
| DeepSeek F-005 | **ACCEPT / FIXED IN PLAN** | Materials summary 与固定 TODO 行是互斥文法；TODO counts null、semantic stop |
| DeepSeek F-006 | **ACCEPT / FIXED IN PLAN** | 唯一复用 production `normalize_form`，禁止复制 mapping/宽 regex |
| DeepSeek F-007 | **ACCEPT / FIXED IN PLAN** | SEC accession 固定正字法；仅三次 download filing 参与 freshness，异源 filing fail closed，material 排除 |
| DeepSeek F-008 | **ACCEPT / FIXED IN PLAN** | run 写 terminal `verify.json`；独立 verify 只写 source inventory/acceptance receipt，不改 phase receipts |
| MiMo H-1 | **ACCEPT / FIXED IN PLAN** | 与 DS F-002 合并：不宣称 quiet 纯净，唯一 anchor 前缀可诊断，静态 env 入 plan identity |
| MiMo H-2 | **ACCEPT / FIXED IN PLAN** | 与 DS F-004/F-006 合并：可信前缀 + opaque tail + production form normalizer |
| MiMo M-1 | **ACCEPT IN PART / FIXED IN PLAN** | 三节 section_status 全记录；usable 只 downloaded+skipped，failed>0 整命令停止，跨节 duplicate 拒绝 |
| MiMo M-2 | **ACCEPT AS CONSTRAINT / FIXED IN PLAN** | union 闭集，新增成员必须 bump receipt schema；lifecycle/domain 分组但 strict round-trip 仍覆盖 evidence schema |
| MiMo M-3 | **ACCEPT / FIXED IN PLAN** | 单一 `stdout_summary`：clean null，前缀/reject 记录类别+行号+脱敏片段；无 sidecar |
| MiMo L-1 | **ACCEPT / FIXED IN PLAN** | AST/源码检查精确针对 acceptance CLI，不误写或误扫 `dayu/cli/` |
| MiMo L-2 | **ACCEPT / FIXED IN PLAN** | 0-record phase 用 phase-level 跨度；全 run 用首个实际 phase/record 到 terminal/last phase跨度 |
| Controller gap C-001 | **ACCEPT / FIXED IN PLAN** | 最小扩大 formatter allowlist：download 在 ticker 后/summary 前输出唯一 status；owner test 锁 ok/cancelled |

上述首次 corrective findings 裁决保持不变；13:00 双路 re-review 的新增 observations 裁决如下：

| Review finding | Decision | Final corrective destination |
|---|---|---|
| DeepSeek G-001 | **ACCEPT / FIXED IN PLAN** | material_action 仅 create/update；owner_status ok/skipped 是字段条件判别；delete/unknown fail closed |
| DeepSeek G-002 | **ACCEPT / FIXED IN PLAN** | status gate 按命令拆分：download/process 仅 ok；upload 允许 ok/skipped 且 skipped 强制 repository closure |
| DeepSeek G-003 | **ACCEPT / FIXED IN PLAN** | process stdout 行内只信 document_id；quality 唯一来自 ProcessedDocumentRepositoryProtocol |
| MiMo new L-1 | **ACCEPT / FIXED IN PLAN** | 空 form 不调用 normalizer，categorized structure_reject + line 写 stdout_summary，不落 unexpected exit 2 |
| MiMo new L-2 | **ACCEPT / FIXED IN PLAN** | upload 必需五行、固定顺序稀疏可选行、必需 files header 与 opaque file rows |
| MiMo open question | **ACCEPT / FIXED IN PLAN** | owner material_action=delete/unknown 明确 fail closed |

最终 closure：初始 code-review findings（DS H-1/H-2/M-1..M-5/L-1..L-5；MiMo H-1/M-2..M-7/L-1..L-7）、首次 plan-review observations（DS F-001..F-008；MiMo H-1/H-2/M-1..M-3/L-1/L-2；Controller C-001）以及 final corrective observations（DS G-001..G-003；MiMo new L-1/L-2/open question）均为 **CLOSED**。两份 final corrective plan re-review 均 PASS，open High/Medium/Low = **0/0/0**；Slice 2 计划 handoff-ready。Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。

## 13. Stop conditions

出现任一情况立即停止，不自动修复或扩大范围：

- plan 指纹、HEAD、package config canonical tree、package `research_templates/` canonical tree、根级 `定性分析模板.md`、run root 或 as-of 漂移；
- `resolve_package_config_path()`/`resolve_package_assets_path()` 无法返回可读真源，package research asset tree 包含 symlink/非 regular file/重复 locator，CLI 无法接受该 resolved config dir，或任一 `dayu.cli` argv 缺少/不一致 `--config`；不得自行切到 workspace override/init；
- live `prepare`/`run` 中 `MIMO_API_KEY`/`DEEPSEEK_API_KEY`/`SEC_USER_AGENT` 所需名称缺失，或 preflight 非零；该条件不适用于 deterministic tests；
- SEC User-Agent 未按批准方式配置，三组 download 任一非零/窗口漂移，或发现缺失/未来/未处理的必需 filing；
- download/upload_material/process 任一计划 argv 缺少/重复 `--quiet`，或 Popen 未显式应用 plan 中精确三项 static env policy；不得 fallback 到 workspace init/profile；
- formatter title 为 0/多次，download 的 ticker→status→summary/三节 header、upload 的 pipeline→ticker→status→material_action/固定可选字段顺序/files header，或 process summary/TODO/六节 header 缺失、重复、重排；download form 为空必须 categorized structure reject，process 行内 quality 不得进入 evidence。可信结构无法收窄时安全停机，anchor 前第三方前缀与 opaque reason/message/warning/files 不得误当 evidence，也不得用宽 regex、inventory 自引用或未授权 `dayu/` 修改规避；
- v3 command records 与 plan command prefix/index/safe argv/digest/时间/退出/stream summary/evidence 不闭合，出现 v1/v2 receipt，download usable receipt-derived 10-K/10-Q/DEF 14A discovery 与 repository 最新 accession 不一致，或失败 record 后仍有后续 receipt；
- download owner status 非 `ok`（含 exit-0 `cancelled`）、summary failed>0、downloaded/skipped row 与 repository 不闭合、document ID 跨节重复，或 fresh run root 出现不符合本计划 SEC accession identity 的其它 filing；
- price JSON 六字段、canonical JSON/Markdown 指纹或稳定 material document ID 不闭合；upload material_action 不在 create/update、owner_status 不在 ok/skipped、ok 缺 source fingerprint/report date，或 skipped 未由 stable ID + repository meta/primary SHA 闭合；delete/unknown action 与其它 status 都停止；
- price material repository primary SHA 不等于 `plan.price_material_sha256`；process 阶段非零、owner_status 非 ok、六节/summary 不闭合、failed/TODO、有 failed document、必需 filing/price material 缺 result/processed，或 `ProcessedDocumentRepositoryProtocol` quality/状态指纹缺失、显示 `reprocess_required=true`；
- 模型目录价格缺失、币种不一致或 provider usage 不完整；
- 任一请求/Token/成本/wall-clock 达到上限，或 write receipt budget blocked；
- 子进程 timeout 后按 `terminate → 10s grace → kill` 无法确认退出；必须标记 `partial_by_timeout/termination_unconfirmed`并保留现场；
- 子进程 cwd 不是 resolved repository root、stdin 不是 DEVNULL、shell 非 false、env 未显式传入，whole-wall 启动前耗尽未记录 `timeout/not_started/partial=true`，0-record phase 未使用 phase-level 跨度，或全 run actual wall 不是首个实际 phase/record 到 terminal/last phase 的端到端跨度；
- write gate、audit、materialization、bundle/workbook/report/source-map/monitoring validator 失败；
- acceptance harness-owned phase receipt、`acceptance-receipt.json`、脱敏 baseline 或 completion report 命中 secret shape/敏感 header/cookie/绝对 home 路径；生产 validator artifact 内 owner 原生 package 绝对路径不单独触发该 stop，但禁止将其内容摘录到 acceptance-owned output；
- rubric 为 `PENDING_MANUAL_REVIEW`、总分/分项低于阈值，或存在未关闭 unsupported material claim；pending 只允许停在等待人工复核，不得冻结 baseline/宣称 PASS；
- exact pending skeleton handoff 仍启动/派生 terminal subprocess、写 `verify.json`/source inventory/acceptance receipt、返回 exit 0/1/2或把 planned receipt改成 non-passed；独立 verify 因 terminal 缺席拒绝完整 passed planned prefix、创建 terminal receipt或改写任一 planned receipt；
- `utils/investment_agent_acceptance.py` 仍持有 rubric/hard-gate/dimension/100/85/分项阈值规则真源，fixture/tests 快照未与 evaluator builder 一致，或 acceptance 子命令缺显式 `--json` 仍被接受；
- download formatter 未精确在 ticker 后/summary 前输出唯一 status、其它 formatter 行为被改变，独立 verify 改写 phase receipts，或非-pending `run` 的 terminal 成功未写精确一条 record 的 `verify.json`；
- repo-private fixture lock 已存在或 stale owner 无法诊断、cleanup failure 掩盖主异常，或 `source-inventory.json` 无法 canonical 原子写入/发现非同字节既有文件；
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
| AcceptancePlan v2 的 run root、命令、env presence、三项 static subprocess env policy 与 stable material ID 只由 Slice 2 contract/fake-runner tests 覆盖，不进入 fixture-only deterministic verify；且 fingerprint 有意绑定当前机器与 run-id | Slice 2 strict round-trip/drift/receipt-prefix tests；跨机或换 run-id 必须重新 prepare，Slice 5 gate 展示当前机器生成的 exact fingerprint |
| 当前 Fins CLI 没有 JSON mode，download/import/process evidence 依赖 `--quiet` + 唯一 title anchor + trusted structure/opaque tail ingress；owner 文案变更会造成可用性中断 | Slice 2 对真实 `format_fins_cli_result` 的 integration tests；任何结构 drift 安全停机并重新 plan，绝不宽 regex、fallback inventory 或扩大 `dayu/` 修改 |
| `--quiet` 仍允许 edgar/httpx WARNING 写入 title 前，三个静态环境变量也不能穷尽未来第三方直写 stdout 通道 | 完整 stdout digest + bounded `stdout_summary` 保留诊断；title 前噪声注入测试，0/多 anchor fail closed；未来新增通道重新 plan |
| owner reason/message/warning/files 是未转义自由文本，验收刻意不审计其内容 | 只把可信结构前缀用于 evidence，opaque tail 仅进 raw stdout digest；人工诊断依赖保留现场，不复制到 receipt |
| upload material owner_status 在 production 是开放字符串，未来可能新增合法状态；本验收只允许 ok/skipped | 新状态安全停机并重新 plan；不得把未知状态静默映射到 skip/ok，也不得扩大 material_action 的 create/update 闭集 |
| process optional parts 的位置/内容未版本化，quality 前存在自由 reason | stdout evidence 只收 document_id，source_kind/status 由六节派生，quality 从 ProcessedDocumentRepositoryProtocol 获取；reason 注入回归测试 |
| fresh `data-workspace/` 单一来源不变量依赖本计划命令 allowlist；未来其它 upload filing 会破坏 accession 集合 | Slice 2 对 `fil_sec_*`/`fil_cn_*`/malformed filing fail-closed tests；只允许三次 SEC download + 唯一 `mat_*` price material |
| PhaseReceipt v3 是 fresh schema，旧 WIP v2 receipts 与已 prepare 的本地 plan/run 无法恢复 | 将旧 run 标为不可恢复并由 operator 按 cleanup runbook 单独处理；parser 明确拒绝 v1/v2，不建兼容层、不自动删除 |
| repo-private fixed fixture root 可能因强制终止留下 stale owner lock；自动破锁可能误伤并发进程 | owner metadata 只提供诊断，仍 fail closed；operator 核实 PID/started_at 后按 runbook 人工处理，cleanup 错误不得掩盖主异常 |
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

- plan fingerprint、git SHA、as-of、run-id、package config canonical tree/诊断用关键文件、package `research_templates/` canonical tree、根级 `定性分析模板.md` 指纹、静态 subprocess env policy 名称/非秘密固定值、各阶段 exit/duration/remaining wall；
- 三组 download argv/status/sectioned usable discovery、price JSON→Markdown→stable material ID/action 闭合、process filing/material summary/TODO/六节证据、source inventory/processed 状态指纹和 freshness 判定；
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
6. **人工质量复核**：不需且不应在首次 `run` 前预填分数。planned phases 全部 passed且 quality review 仍为 prepare 生成的 exact pending skeleton 时，`run` 自身以 canonical `PENDING_MANUAL_REVIEW`/exit 3 完成人工 handoff，不启动 terminal verify、不写 terminal/source-inventory/acceptance receipt。只允许用非 PII `reviewer_role/reviewer_id_label` 完整填写既有骨架，随后只运行独立 verify；如果复核另行调用付费模型，必须在第 1 项单列预算并再授权。
7. **最终 live 确认**：Controller 展示模型、as-of、三组 source forms/start/end、price JSON/Markdown 指纹与 material import argv、process argv、package config canonical tree、package `research_templates/` canonical tree 与根级 `定性分析模板.md` 指纹、全部预算、wall-clock、run root 与 exact plan fingerprint，用户明确确认后才允许执行 `run`。

Slices 0–4 完成与 accepted commits 不得被表述为 AAPL 实战验收已通过；只有 Slice 5 live receipt、人工 rubric 和 completion report 全部通过后，work unit 才可 closeout。

### Current erratum gate / next entry point

- Plan status：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**。
- Accepted history：Slice 2 的 final evidence `docs/reviews/plan-review-20260809-133000-deepseek.md` 与 `docs/reviews/plan-review-20260809-133001-mimo.md` 均 PASS/open H/M/L=0，durable closure 为 `docs/reviews/plan-acceptance-20260809-134500-codex.md`；本 erratum 不撤销该历史。
- Slice 3：Codex + Terra final reviews 均 PASS/open H/M/L=0；S3R-001/S3R-002、duplicate Terra M-001 与 Terra C-001 全部 CLOSED，accepted implementation history保持不变。
- Manual-review handoff closure：用户明确授权的 Codex Controller review `docs/reviews/plan-review-20260809-173027.md` 为 PASS-WITH-RISKS/open H/M/L=0，独立 Terra review `docs/reviews/plan-review-20260809-manual-review-handoff-terra.md` 为 PASS/open H/M/L=0；durable closure 为 `docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md`。MiM provider 401 未参与本 gate，未被记为 MiM PASS。只允许下一步修正 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py`；不需要 contracts/evaluator 变更，不新增 production flag/action/schema/marker。Slice 4 docs仍等待该code correction accepted。
- Slice 5：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；本 closure 不授予 SEC、Web、模型、网络或付费执行权限。
- 第 14 节全部 residual risks 及其 destinations 原样保留，后续实施与 live gate 必须逐项承接。
