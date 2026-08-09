# 投资 Agent：AAPL 实战验收 operator runbook

- 用途：把下载、价格 material 导入、预处理、双模型写作、研究工件物化、monitoring 与 source-map 校验在同一个 AAPL 运行中闭合，并生成可复核的 acceptance receipt。
- 适用范围：AAPL（Apple Inc.）固定目标；研究模板固定为 `technology`；主写模型 `deepseek-v4-pro`、审计模型 `mimo-v2.5-pro-thinking`。
- 入口：`python -m utils.investment_agent_acceptance`，子命令只有 `prepare`、`run`、`verify`，三者都必须显式传 `--json`。
- 退出码：`0` 成功（含 verify 得到 `PASS`）；`1` run/verify 结果 `FAIL`；`2` 参数/契约/I/O 失败；`3` 等待人工复核（`PENDING_MANUAL_REVIEW`）。
- 本验收是研究质量验收，不构成投资建议。

## 1. 两条 lane

### 1.1 Deterministic lane（默认、CI 可运行）

- 只读取仓库 fixture 与仓库内临时目录：不联网、不调用模型、不读取任何 API key 值。
- 用固定 AAPL 验收语料验证评分、失败分类、脱敏和稳定序列化；同一输入与固定时钟必须产生字节一致的 receipt。
- 直接命令：

```bash
python -m utils.investment_agent_acceptance verify \
  --fixture tests/fixtures/investment_agent/aapl_acceptance \
  --json
```

- fixture 固定位于 `tests/fixtures/investment_agent/aapl_acceptance/`，是脱敏、无外部依赖的回归语料；其中的 accession 与价格只用于回归，不声明“今天最新”。
- deterministic verify 会调用真实 research materializer 在仓库内固定临时根 `workspace/tmp/investment-agent-aapl-fixture-verify/` 物化 13 个研究产物（该目录已被 `.gitignore` 覆盖）。并发由原子锁目录保护，锁内 `owner.json` 只记录 PID、UTC started_at 与非 PII run label；存在锁时 fail closed 并给出 owner/stale 诊断，不自动破锁。

### 1.2 Live lane（opt-in、绝不进 CI）

- 只有在取得本次模型/外部数据/费用授权后才可执行；授权是独立于代码 review 的 gate，代码通过不等于授权外部调用。
- 执行前必须由用户逐项确认：模型、as-of、三组 source forms/start/end、price snapshot 指纹与 material import argv、process argv、package config canonical tree、package `research_templates/` canonical tree、根级 `定性分析模板.md` 指纹、全部预算、wall-clock、run root 与 exact plan fingerprint。
- live 产物只写入 `.gitignore` 已覆盖的 `workspace/acceptance/investment-agent-aapl/<run-id>/`；固定回归 baseline 只在验收通过并脱敏后选择性提交。
- live `prepare` 与 `run` 只检查所需环境变量名称是否存在（`DEEPSEEK_API_KEY`、`MIMO_API_KEY`、`SEC_USER_AGENT`），绝不读取、回显、hash 或持久化它们的值。

## 2. 真源：package config 与 research templates

- package config 真源：`prepare` 通过 `dayu.startup.config_file_resolver.resolve_package_config_path()` 得到当前包内 `dayu/config`，其 canonical tree 指纹覆盖 scene manifests（`prompts/manifests/write.json`、`audit.json` 等）与 `llm_models.json`。所有生成的 `python -m dayu.cli` argv 都显式传同一 resolved `--config` 绝对路径，不读 `workspace/config` override、不要求先 `init`。
- package research asset 真源：`resolve_package_assets_path()/research_templates/` 的 canonical tree（全部 regular `.md`/`.definition.json`，按包相对 POSIX 路径排序并记录路径+SHA-256），加上根级 `dayu/assets/定性分析模板.md` 的独立 SHA-256。
- `--research-base` 只隔离派生研究产物，不是模板真源；用户 workspace 自定义模板不参与验收，会在 residuals 中明示。
- 上述任意真源指纹漂移都使 plan 失效：必须重新 `prepare` 生成新 plan/fingerprint，不得复用旧 plan。

## 3. prepare

`prepare` 完全离线：不联网、不调用模型，校验并落盘计划。

```bash
python -m utils.investment_agent_acceptance prepare \
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

- `--as-of`、全部预算参数与 `--max-wall-seconds` 没有默认值，必须显式提供；`--run-root` 必须是尚不存在的 `workspace/acceptance/investment-agent-aapl/<run-id>/`，run-id 只允许 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，父目录必须已解析且非 symlink。
- `--price-snapshot` 是唯一外部输入，只读；JSON 必须精确含 `price`、`currency`、`market_date`、`source_url`、`captured_at`、`max_age_days` 六字段，且时间不未来、不超 `max_age_days`。
- prepare 在同一父目录 staging 中构造 `data-workspace/`、canonical `inputs/price-snapshot.json`、确定性 `inputs/price-snapshot.material.md`（无损文本 + canonical JSON SHA-256）、`quality-review.json` 空骨架与全部 argv，成功后才原子 rename 到精确 run root；任一步失败不得留下可运行的正式 run root。
- 稳定 price material document_id 由 production owner `build_material_ids(form_type="MATERIAL_OTHER", material_name="aapl-price-snapshot", fiscal_year=None, fiscal_period=None)` 计算并写入 plan。
- 环境变量缺失、预算非法、价格超龄或 run root 已存在都直接 exit 2。
- 成功后输出 canonical JSON：

```json
{"status": "prepared", "plan": "<run-root>/acceptance-plan.json", "fingerprint": "<sha256>"}
```

## 4. run：12 个 planned 命令与人工 handoff

`run` 只接受 `--plan` 与 exact `--fingerprint`，只执行计划内固定顺序的 12 条命令（下载 3 + 导入 1 + process 1 + write preflight 1 + 付费 write 1 + validators 5）。任一命令非零、语义失败、timeout、signal、receipt mismatch 都立即停止，不自动进入后续付费阶段，不自动 resume。

```bash
python -m utils.investment_agent_acceptance run \
  --plan <run-root>/acceptance-plan.json \
  --fingerprint <exact-fingerprint> \
  --json
```

### 4.1 三组 download 窗口

以下 argv 由 runner 生成，日期在 plan 生成后不重算；三组都显式传同一 `--end <as-of-date>` 与 resolved package `--config`，各固定一个 `--quiet`：

| 组 | forms | start |
|---|---|---|
| 10K | `10K` | as-of 减 5 个日历年 |
| 10Q | `10Q` | as-of 减 2 个日历年 |
| 8K+DEF14A | `8K DEF14A` | as-of 减 2 个日历年 |

等价形式（`<run-root>`、`<config>` 为 plan 绑定占位符）：

```bash
python -m dayu.cli download --ticker AAPL --forms 10K \
  --start <as-of-minus-5-years> --end <as-of-date> \
  --base <run-root>/data-workspace --config <resolved-package-config-dir> --quiet
python -m dayu.cli download --ticker AAPL --forms 10Q \
  --start <as-of-minus-2-years> --end <as-of-date> \
  --base <run-root>/data-workspace --config <resolved-package-config-dir> --quiet
python -m dayu.cli download --ticker AAPL --forms 8K DEF14A \
  --start <as-of-minus-2-years> --end <as-of-date> \
  --base <run-root>/data-workspace --config <resolved-package-config-dir> --quiet
```

- 不依赖未验证的默认窗口；窗口日期进入 plan fingerprint。
- 验收解析各命令固定标题锚（如 `下载结果`）后的可信结构：download 固定 `ticker → status → 汇总 → 成功下载/跳过/失败 filings`；`status` 非 `ok`（含 `cancelled`）、`summary.failed>0`、必需 10-K/10-Q/DEF 14A usable discovery 缺失都停止；8-K 不存在只记 warning。
- form 比较唯一复用 `dayu.fins.pipelines.sec_form_utils.normalize_form`。

### 4.2 price snapshot material import 与 process

价格快照先被确定性渲染为 `inputs/price-snapshot.material.md`，再在任意付费 write 前导入 Fins material 仓储：

```bash
python -m dayu.cli upload_material --ticker AAPL --forms MATERIAL_OTHER \
  --material-name aapl-price-snapshot \
  --document-id <plan-bound-stable-price-material-document-id> \
  --files <run-root>/inputs/price-snapshot.material.md \
  --report-date <price-market-date> \
  --base <run-root>/data-workspace --config <resolved-package-config-dir> --quiet
```

- 直接上传 `.json` 不在 upload suffix allowlist 内，不得上传原 JSON。
- `material_action` 只允许 `create`/`update`，`owner_status` 只允许 `ok`/`skipped`；`delete`/unknown action 或其他 status 立即 fail closed。两种允许状态的 primary SHA 都必须精确等于 plan 中 price material SHA。
- 导入成功后显式执行一次 `process`（同时处理三组 SEC filing 与 price material），再进入任何 write：

```bash
python -m dayu.cli process --ticker AAPL \
  --base <run-root>/data-workspace --config <resolved-package-config-dir> --quiet
```

- process 的 `filings` summary 必须存在；`materials` 只允许互斥两态：完整 counts + `todo=false`，或固定 `- materials 处理: 未实现（TODO）` + counts null + `todo=true`。后者会在任何付费 write 前 semantic stop。
- 源清单与 processed 状态指纹（`source_fingerprint`、`schema_version`、`parser_version`、`quality`、`reprocess_required`）通过 `SourceDocumentRepositoryProtocol` / `ProcessedDocumentRepositoryProtocol` / `DocumentBlobRepositoryProtocol` 构建，不直接扫描 `workspace/portfolio/...` 私有目录。

### 4.3 write preflight 与付费 write

```bash
python -m dayu.cli write --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --research-template technology \
  --output <run-root>/write \
  --preflight-only --no-resume \
  --write-max-model-requests <approved-requests> \
  --write-max-total-tokens <approved-tokens> \
  --write-max-estimated-cost <approved-cost> \
  --write-budget-currency CNY \
  --base <run-root>/data-workspace --config <resolved-package-config-dir>

python -m dayu.cli write --ticker AAPL \
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
  --base <run-root>/data-workspace --config <resolved-package-config-dir>
```

- `--preflight-only` 不得与 `--research-base`/materialization 参数同时传入。
- preflight 失败不创建 write run、不进入付费 write；预算 blocked 立即 FAIL，不通过扩大预算或 `--force` 自动继续。
- 两条 write argv 都固定 `--no-resume`；任何已有 planned/terminal receipt 都使新的 `run` fail closed，不存在自动/隐式 resume。

### 4.4 validators

五个 validator 全部指向 run root 内固定的 13 个研究产物，显式传 `--base <run-root>/research --config <resolved-package-config-dir>`：

```bash
python -m dayu.cli research-template validate-research-workbook \
  --workbook <run-root>/research/assets/research_templates/technology.research-workbook.json \
  --base <run-root>/research --config <resolved-package-config-dir>
python -m dayu.cli research-template validate-workbook-report \
  --report <run-root>/research/assets/research_templates/technology.research-progress.md \
  --workbook <run-root>/research/assets/research_templates/technology.research-workbook.json \
  --base <run-root>/research --config <resolved-package-config-dir>
python -m dayu.cli research-template validate-source-map \
  --rules <run-root>/research/assets/research_templates/technology.monitoring-rules.json \
  --source-map <run-root>/research/assets/research_templates/technology.source-map.json \
  --base <run-root>/research --config <resolved-package-config-dir>
python -m dayu.cli research-template validate-bundle \
  --bundle <run-root>/research/assets/research_templates/technology.bundle.json \
  --base <run-root>/research --config <resolved-package-config-dir>
python -m dayu.cli research-template validate-monitoring-plan \
  --plan <run-root>/research/assets/research_templates/technology.monitoring-plan.json \
  --base <run-root>/research --config <resolved-package-config-dir>
```

### 4.5 12 条 planned 命令全部 passed 后：人工 handoff

- 12 条 planned 命令全部 passed 且磁盘 `quality-review.json` 仍是 `prepare` 生成的 exact pending 骨架（与 evaluator builder canonical bytes 精确相等）时，`run` 不派生/启动 terminal verify，返回 canonical JSON 并以退出码 3 结束：

```json
{"status": "PENDING_MANUAL_REVIEW", "verdict": "PENDING_MANUAL_REVIEW",
 "completed_phases": ["download", "price-snapshot-import", "process",
                      "write-preflight", "write", "validations"],
 "terminal": null}
```

- 该终态不写 `phase-receipts/verify.json`、`source-inventory.json`、`acceptance-receipt.json`；terminal subprocess 调用数为 0；`succeeded` 恒为 `false`，不宣称 PASS。
- 若 `quality-review.json` 是 strict-valid 但非 exact skeleton（人工预填/partial），`run` 不走 handoff shortcut，保持 terminal strict path（派生并启动 terminal verify；terminal 失败不持久化 `verify.json`）。

### 4.6 超时协议

- 从第一个 planned 阶段开始，整条自动化链共享 `max_wall_seconds`，任何阶段不得重置计时；超时后先 `terminate()`，等待 plan 固定的 `termination_grace_seconds=10`，仍存活则 `kill()`。命令启动前已耗尽预算时记录 `status=timeout`、`termination_action=not_started`、`partial_by_timeout=true`。
- terminate/kill 抛 `OSError` 或 kill 后无法确认退出时记录 `termination_unconfirmed` 并 STOP；现场与仓储 journal 原样保留，不自动 cleanup/resume。
- 子进程固定 repository 根为 cwd、`stdin=DEVNULL`、`shell=False`，显式传入带三项固定非秘密覆盖的 env：`TQDM_DISABLE=1`、`HF_HUB_DISABLE_PROGRESS_BARS=1`、`TRANSFORMERS_VERBOSITY=error`。

## 5. 人工质量复核与独立 verify

- 人工复核只允许完整填写既有 `quality-review.json` 骨架：每个子项记录 `score/max_score/evidence_paths/notes`，顶层记录 `reviewer_role`、`reviewer_id_label`（只用非 PII 角色/代号，如 `investment-reviewer` / `reviewer-1`，不得写真实姓名、email、账号、home path）。
- 填写完成后只运行独立 live verify（允许 terminal receipt 缺席，完整 passed planned prefix + terminal absent 是合法 handoff 状态）：

```bash
python -m utils.investment_agent_acceptance verify \
  --plan <run-root>/acceptance-plan.json \
  --fingerprint <exact-fingerprint> \
  --json
```

- 独立 verify 不创建/更新任何 phase receipt，也不补写 terminal receipt；`phase-receipts/` 前后字节不变。它只原子写 canonical `source-inventory.json` 与 normalized `acceptance-receipt.json`。
- 三态 verdict：任一 deterministic hard gate 或完整人工 review 阈值失败为 `FAIL`（exit 1）；deterministic 全通过但任一子项/`reviewer_role`/evidence path/notes 未填完为 `PENDING_MANUAL_REVIEW`（exit 3）；只有全部字段完整、评分达标且 High/Medium=0 才为 `PASS`（exit 0）。骨架被删除或 schema 被改是 tamper `FAIL`，不是 pending。
- malformed quality、secret/PII 形状、plan/receipt/artifact drift 在任何 acceptance outputs 发布前 fail closed。
- 独立重复 verify 的 planned phase receipts 必须字节不变。

## 6. 评分

- 总分 100，通过阈值 `>= 85`；来源可追溯（25）、投资研究完整性（30）、证据与推理质量（25）各自不得低于维度的 80%（20/24/20）；可复现与恢复（10）、运行治理（10）无分项最低分。
- 维度分值、子项分值、hard gates、required topics/evidence parts 与阈值只定义在 evaluator（`utils/investment_agent_acceptance_evaluator.py`）一个真源；fixture 与测试只是被一致性测试守卫的快照。
- deterministic scorer 只自动给可机械验证的项；需要判断语义的项必须由复核者明确给分并列出引用位置，不允许多模型自评后自动通过。
- hard gates 包括：run summary 通过、audit 完整、双模型角色闭合、预算未超限、13 个研究产物与 validators 通过、workbook 结构有效且进度如实、monitoring 安全（dry-run、automation=false、unbound sources 进 residuals）、source/price 闭合、acceptance outputs 脱敏、人工复核完整 PASS。
- 估值的 `valuation_reference_price` 价格/币种/日期必须与已指纹 price snapshot 精确一致，且 evidence 闭合到已导入的 Fins material document_id。

## 7. 产物目录与残留状态

live run root 固定结构：

```text
workspace/acceptance/investment-agent-aapl/<run-id>/
├── acceptance-plan.json
├── inputs/
│   ├── price-snapshot.json          # canonical 六字段价格
│   └── price-snapshot.material.md   # 无损派生物
├── phase-receipts/
│   ├── prepare.json
│   ├── download.json                # 三个有序 download command records
│   ├── price-snapshot-import.json
│   ├── process.json
│   ├── write-preflight.json
│   ├── write.json
│   ├── validations.json
│   └── verify.json                  # 可选，passed-only terminal receipt，仅由 run 写
├── data-workspace/                  # Fins storage，只经仓储协议审计
├── write/
│   ├── manifest.json
│   ├── run_summary.json
│   └── AAPL_qual_report.md
├── research/assets/research_templates/   # 13 个研究产物
├── source-inventory.json            # 独立 verify 原子写
├── quality-review.json              # prepare 生成空骨架，人工填写
└── acceptance-receipt.json          # 独立 verify 原子写
```

- 13 个研究产物固定为：`common-plus-technology.md`、`technology.research-workbook.json`、`technology.research-progress.md`、`technology.monitoring-rules.json`、`technology.source-map.json`、`research-template.manifest.json`、`technology.research-guide.md`、`technology.checklist.md`、`technology.bundle.json`、`technology.monitoring-plan.json`、`monitoring-status.json`、`research-workbook-status.json`、`research-workbook-report-status.json`。
- `prepare.json` 是原子创建完成 receipt，0 条 command records；`verify.json` 只允许在全部 planned records 成功、quality review 非 exact pending skeleton、terminal verify subprocess 返回 0 后出现且精确含 1 条 record；pending/failed/signal/timeout terminal 一律不持久化。
- 常见 residuals（如实报告，不得伪造 ready）：monitoring unbound sources（如 `financial_statements`/`operating_metrics`/`product_release_notes`/`market_data` 未绑定）、`monitoring_blocked_task_count`、`workbook_open_item_count=37`、`workbook_completion_status=not_started`、`optional_8k_absent`、`user_workspace_custom_templates_not_part_of_acceptance`。
- workbook 是 `manual_review` 跟踪工件，37 项 open 不被当作研究完成；monitoring 只验收“安全且可解释的计划”（dry-run + 禁止自动执行），不是执行告警。

## 8. 失败恢复与 cleanup

- runner 不自动删除失败或成功 run。
- 任一 planned phase 失败后：保留已有 output/manifest、command records、phase receipts、仓储 journal 与 partial 产物并立即停止；不得自动/隐式 resume，不得手工覆盖、删除、改名 receipt 后继续，不得在同一 run root 重跑任一 phase。
- 当前唯一可执行恢复：operator 检查保留现场后，选择**全新 run root** 重新 `prepare` 并从零开始；新 run 生成自己的 plan/fingerprint。若涉及 SEC/模型/网络/付费调用，必须重新经过 live authorization。
- 不得把旧 run 的 receipt 或 partial artifacts 复制成新 run 的成功证据。
- cleanup（如需要归档/移动失败现场）只接受一个已解析、精确位于 `workspace/acceptance/investment-agent-aapl/` 下的 run-id 目录；禁止 glob、环境变量展开、`~` 或递归 workspace 根目录目标。默认做可恢复的归档/移动；永久删除必须另立用户授权。

## 9. 安全与脱敏

- 环境变量只记录名称与存在性，绝不记录值；plan/receipt/source inventory/completion report 中不得出现 API key、Authorization header、cookie 或绝对 home 路径。
- acceptance-owned 输出（`phase-receipts/*.json`、`acceptance-receipt.json`、脱敏 baseline、completion report）若命中 secret shape 或绝对 home 路径即 fail closed。
- 生产 validator 产物（如 `research-template.manifest.json`、`technology.monitoring-rules.json`）内 owner 原生的 package 绝对路径不在该泄漏 gate 作用域内；verifier 不改写这些文件，引用时只记录包相对 locator + SHA-256，不摘录其内嵌路径或内容片段。
- `main()` 对契约错误、OSError 与 unexpected exception 都只输出静态脱敏摘要并返回 exit 2，不裸露 traceback。

## 10. 回归基线（Slice 5 之后）

- 只有 live 验收通过且脱敏后才选择性提交固定回归 baseline：保留 schema、as-of、代码/配置/源清单指纹、维度分数、阈值、usage 汇总、residual 分类与 production artifact 的包相对 locator/SHA-256；不提交完整 provider 日志、秘密、生产产物内容片段或其内嵌绝对路径。
- baseline 测试只验证 contract 回归，不把某个日期快照当“今天最新”的 freshness 真源。

## 11. 文档导航

- 本 runbook 对应的 implementation plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`。
- 根 README 只保留最短入口与导航：见 `README.md` 的投资 Agent 实战验收一节。
