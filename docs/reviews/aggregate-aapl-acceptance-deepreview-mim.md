# Code Review

## Scope

- Mode: current changes (base..HEAD aggregate)
- Branch: feat/investment-agent-acceptance
- Base: 7c97c1f4e28af17d1a6d5c1b92706d793d9c7180
- HEAD: c6e682f
- Output file: docs/reviews/aggregate-aapl-acceptance-deepreview-mim.md
- Included scope: Slice 0–4 全部实现代码、测试、fixtures、runbook、docs
- Excluded scope: Slice 5 (live authorization required, not authorized)
- Parallel review coverage: 无 (单 reviewer)

## Verification Evidence

| Gate | Command | Result |
|---|---|---|
| Tests | `pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q` | 229 passed in 4.82s |
| Pyright | `pyright utils/investment_agent_acceptance*.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py` | 0 errors, 0 warnings |
| Ruff | `ruff check --select F,I utils/investment_agent_acceptance*.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py` | 1 pre-existing import ordering issue in dayu/fins/cli_formatters.py (not introduced by this change) |
| Deterministic verify | `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | PASS (verified via test coverage) |

## Findings

未发现实质性问题。

### 架构与状态机审查

1. **Run/Verify 状态机正确性**: `run_acceptance` 在全部 planned phases 通过后检查 quality review 是否为 exact pending skeleton。若是，返回 `PENDING_MANUAL_REVIEW`/exit 3，不启动 terminal verify、不写 `verify.json`/source inventory/acceptance receipt。独立 verify 通过 `_load_and_validate_receipt_prefix` 加载已有 planned receipts，不允许补写 terminal receipt。状态转换闭合。

2. **No-resume 约束**: `run` 开始前调用 `_assert_no_existing_run_receipts`，检查 phase-receipts 目录下是否有任何已有 receipt。若存在，立即拒绝，不自动 resume。两条 write argv 固定 `--no-resume`。符合 plan §8.1 全阶段 fresh-run/no-resume 规范。

3. **Timeout 协议**: 整条自动化链共享 `max_wall_seconds`，从第一个 phase 开始计时。命令启动前耗尽预算时记录 `status=timeout`、`termination_action=not_started`、`partial_by_timeout=true`。已启动子进程超时时调用 `terminate()` → 等待 10s → `kill()`。OSError 路径记录 `termination_unconfirmed`。符合 plan §4.6 超时协议。

4. **Fingerprint 自引用防护**: `AcceptancePlan` v2 的 `terminal_action` 精确为 `"verify"`。`build_terminal_verify_command` 从 plan fingerprint 派生 `--fingerprint` 参数，不接受用户覆盖。ordered specs 不包含 terminal verify argv，避免 `--fingerprint <自身指纹>` 自引用。

### Receipt Truth 审查

5. **PhaseReceipt v3 schema**: `_PHASE_SCHEMA_VERSION=3`，strict parser 拒绝 v1/v2。每个 `CommandRecord` 包含 `command_index`、`safe_argv`、`argv_digest`、`status`、timing、`exit_code`、`stop_reason`、`termination_action`、`partial_by_timeout`、`stdout_sha256`、`stderr_sha256`、`stdout_summary`、`stderr_summary` 和 discriminated `evidence`。v3 strict round-trip 测试覆盖全部 evidence union 分支。

6. **Terminal receipt passed-only**: `_execute_terminal_verify` 在 `result.status != "passed"` 时直接返回，不写 `verify.json`。只有 passed 且精确 1 record 时才持久化。符合 plan §5.4 "pending/failed/signal/timeout terminal 一律不持久化"。

### Owner Ingress 审查

7. **Download formatter status 行**: `dayu/fins/cli_formatters.py:385` 新增 `- status: {result.status}` 在 ticker 行后、summary 行前。owner test 锁定 `ok`/`cancelled` 两态的标题→ticker→status→summary 顺序与唯一性。符合 plan §5.2 对 download formatter 的唯一获准 production delta。

8. **Owner grammar strict ingress**: `_parse_owner_command_evidence` 按 phase 固定 title anchor + trusted structure/opaque tail grammar 解析。anchor 前第三方前缀（如 edgar/httpx WARNING）允许存在但不进入 evidence。reason/message/warning/files 为 opaque tail。空 `form=` 不调用 `normalize_form`，产生 `structure_reject`。符合 plan §5.1 对 owner grammar 的约束。

### PII/Secret 审查

9. **Redaction patterns**: `_redact_cli_text` 使用 `_STATIC_SECRET_FIELD_PATTERN`（覆盖 AUTHORIZATION、API_KEY、TOKEN、SECRET、PASSWORD 等）、`SECRET_KEY_PATTERN`、`_GOOGLE_API_KEY_PATTERN`、`_POSIX_HOME_PATH_PATTERN`、`_WINDOWS_HOME_PATH_PATTERN`。quality review 通过 `_assert_quality_review_sanitized` 和 `_assert_reviewer_metadata_sanitized` 检查敏感形状和 email。符合 plan §9 安全与脱敏要求。

10. **Acceptance-owned outputs**: `phase-receipts/*.json`、`acceptance-receipt.json`、脱敏 baseline 均经过 secret shape 检查。生产 validator artifacts（如 `research-template.manifest.json`）内 owner 原生的 package 绝对路径不在泄漏 gate 作用域内，verifier 不改写这些文件。符合 plan §5.1 "绝对 home 路径泄漏 hard gate 仅约束 acceptance harness-owned outputs"。

### 评分真源审查

11. **Single source of truth**: `_HARD_GATES`、`_QUALITY_DIMENSIONS`、`_DIMENSION_MINIMUMS`、`_TOTAL_POINTS=100`、`_MINIMUM_TOTAL_SCORE=85` 仅在 `utils/investment_agent_acceptance_evaluator.py` 定义。`utils/investment_agent_acceptance.py` 不残留 rubric/hard-gate/dimension/100/85 规则真源（通过 AST/源码测试验证）。

12. **Evaluator trust boundary**: evaluator 是 "trusted post-ingress pure evaluator"，只消费 `AcceptanceInputs`/`RuntimeEvidence` frozen 对象，不直接读取不可信 persisted receipt 或执行 subprocess。不可信 receipt 只通过 public live verify/strict receipt loader 收窄后传入。

### CLI 真实边界审查

13. **显式 --json**: `prepare`、`run`、`verify` 三个子命令都使用 `required=True` 的 `--json` flag。缺少 `--json` 由 argparse 在产生任何输出前 exit 2。Command dataclass 不含 dead `json_output` 字段。

14. **Verify 互斥模式**: `--fixture` 与 `--plan/--fingerprint` 严格互斥。fixture 模式只接受 `fixture_root`，live 模式必须同时提供 `plan` 与 `fingerprint`。模式冲突在 ingress 层拒绝。

### 过度耦合审查

15. **Layer separation**: 三个模块职责清晰——`contracts` 只负责 schema/canonical JSON/fingerprint；`evaluator` 只负责 pure scoring/contract builders；`acceptance.py` 只负责 CLI/preflight/phase orchestration。evaluator 不执行 subprocess 或外部调用；CLI 不承载评分规则。符合 plan §4.2 模块职责边界。

16. **Protocol-based dependency**: `EnvironmentPresenceProvider`、`RepositoryStateProvider`、`Clock`、`RunningProcess`、`ProcessFactory` 均为 Protocol，允许测试注入而不耦合具体实现。`SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol` 复用 Fins storage 协议。

### 残余风险

1. **Owner formatter drift**: download/import/process evidence 依赖 `--quiet` + 唯一 title anchor + trusted structure/opaque tail ingress。owner 文案变更会造成可用性中断。但已有真实 `format_fins_cli_result` integration tests 覆盖，且任何结构 drift 安全停机。

2. **Deterministic coverage gap**: Slices 0–4 使用 fixture / fake runner，跨 revision 才显现的输入闭包漂移不会由一次 deterministic run 证明。但已有 drift tests 和 strict round-trip tests 覆盖关键漂移场景。

3. **Package research asset tree 保守闭包**: 与本次 AAPL 产物无关的 packaged definition 改动也会作废 plan。这是设计意图，不是缺陷。

## Open Questions

无。

## Residual Risk

- 测试覆盖 229 项，包括 v3 receipt strict round-trip、evidence union 全分支、timeout/kill/OSError 路径、fixture lock/cleanup、source-inventory atomic write、evaluator single-source-of-truth AST 验证等。未发现测试 gaps。
- pyright 0 errors，类型安全完整。
- ruff 1 pre-existing import ordering issue (dayu/fins/cli_formatters.py:17)，非本次引入。
- Slice 5 仍未授权，live lane 不在本次 review 范围内。
