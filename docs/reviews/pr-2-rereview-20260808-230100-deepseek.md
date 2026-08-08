# PR-2 Re-Review

## Scope

- Mode: PR re-review（follow-up，非全量重审）
- Branch or PR: PR-2，https://github.com/KUIGE22/dayu-agent/pull/2；head `codex/dual-model-research-mvp-recovered`
- Base: `main`（本机无本地 `main`，使用 `origin/main`）
- Output file: `docs/reviews/pr-2-rereview-20260808-230100-deepseek.md`
- 输入真源:
  - 原始初审 `docs/reviews/pr-2-review-20260808-212900-deepseek.md`
  - Controller 裁决 `docs/reviews/pr-2-review-adjudication-20260808-codex.md`
  - Fix 记录 `docs/reviews/pr-2-fix-20260808-codex.md`
  - 当前 working tree `git diff`（12 files）
- Included scope: 仅复核 Controller accepted 四项（`PR2-ANTHROPIC-01`、`PR2-COVERAGE-01`、`PR2-SEC-01`、`PR2-DOC-01`）的修复实现，核验 rejected / deferred 裁决证据，检查修复是否引入新 blocker，并在 RR-01 修正落地后做纠正复测
- Excluded scope: 不重做全量 `main...HEAD` review；未修改任何 production / tests / README / plan
- Parallel review coverage: 无（本机 Agent 后端模型不可用，全部由主 reviewer 直接走读并实测）
- 复核轮次:
  - 轮次 1（初次 re-review）：复核 accepted 四项 + rejected/deferred 裁决，定向复测发现 `RR-01`
  - 轮次 2（纠正 re-review，本文件最终状态）：`RR-01` 修正已落到工作树，独立复测 ordinary phrase / 纯字母 / hex API key / 未配置 Git SHA / 两个 scanner

## Verdict

`PASS`

四项 accepted fix 全部闭环且证据可复现；rejected / deferred 裁决证据经独立复核成立。轮次 1 定向复测发现的 Low 级 fix-regression `RR-01` 已在工作树修正并经本 reviewer 独立复测通过，**RR-01 CLOSED**。未发现任何新 blocker。

- Open High: `0`
- Open Medium: `0`
- Open Low: `0`
- Deferred（明确 owner，**未修复，不计入 open**）: `2`（DeepSeek F4 剩余 exact488、MiMo F4）

## Accepted findings 复核

### PR2-ANTHROPIC-01 — 已修复 / 验证通过

- **裁决 fix contract**: 删除 `pause_turn -> stop` 成功终态映射；流式与非流式均 fail-loud 产出稳定 `anthropic_pause_turn_unsupported`，不产出成功 `DONE`；不得伪装成 `length`，不得发送额外 user continuation prompt。
- **实现核验**:
  - `dayu/engine/async_anthropic_runner.py:19-29`：`_STOP_REASON_MAP` 中的 `"pause_turn": "stop"` 已删除；新增 `_PAUSE_TURN_STOP_REASON` / `_PAUSE_TURN_ERROR_TYPE` / `_PAUSE_TURN_ERROR_MESSAGE` 三个具名常量，符合 AGENTS.md 禁止魔法字符串约束。
  - 流式路径 `:413-421`：`message_delta` 命中 `pause_turn` 时调用 `_record_protocol_error(...)` 并 `_merge_usage(...)` 后 `return`，不再进入 `_STOP_REASON_MAP` 查表，因此不会产出成功完成事件。
  - 非流式路径 `:553-565`：在 `_normalize_anthropic_response` **之前** fail-loud，复用父类 `dayu/engine/async_openai_runner.py:1688` 的 `_build_non_stream_error_event` 并 `return`，未新建兼容 wrapper。
- **契约符合性**: 未映射到 `length`（已 grep 确认 `_STOP_REASON_MAP` 无 `pause_turn` 条目），未新增 continuation prompt 发送逻辑。
- **测试**: `tests/engine/test_async_anthropic_runner.py:303 test_native_response_fails_loud_on_pause_turn_without_done`、`:434 test_native_stream_fails_loud_on_pause_turn_without_done`，两者均断言 `error_type == "anthropic_pause_turn_unsupported"` 且不产出成功 done。21 passed。
- **文档**: `dayu/engine/README.md:124` 已同步 fail-loud 契约，措辞为「当前怎么工作」而非未来设计，符合 AGENTS.md 文档写作约束。
- **状态**: `accepted 已修复`

### PR2-COVERAGE-01 — 已修复 / 验证通过

- **裁决 fix contract**: 只移除失真的 coverage 豁免；不改变 auth suppression 行为、生命周期或日志契约。
- **实现核验**: `dayu/engine/tools/web_search_providers.py:190`，diff 为单行 —— `except Exception as exc:  # pragma: no cover - ...` → `except Exception as exc:`。块内 `:191-195` 的认证判定、fingerprint 记录与日志调用逐字未变。
- **副作用检查**: 该文件本次 diff 仅此 1 行（`git diff --stat` 显示 `1 +-`），确认无行为漂移。
- **覆盖率**: clean-env 复跑 `dayu/engine/tools/web_search_providers.py` = `96%`，≥80% 目标。
- **状态**: `accepted 已修复`

### PR2-SEC-01 — 已修复 / 验证通过

- **裁决 fix contract**: (1) 静态形状增加可靠前缀 provider key；(2) 对 `*_API_KEY` / `*_AUTH_TOKEN` / `*_ACCESS_TOKEN` / `HF_TOKEN` 环境变量做动态精确值脱敏并支持同进程轮换；(3) 两个 scanner 统一走 `has_secret_shapes`；(4) 覆盖四个消费面且保留 Git SHA 负例；明确**不接受**裸 `{32,}` 十六进制模式。
- **实现核验**:
  - `dayu/redaction.py:28-33`：`SECRET_KEY_PATTERN` 增加 `AIza[0-9A-Za-z_-]{35}` 分支并补上 `(?![A-Za-z0-9_-])` 右边界；**未**引入裸十六进制匹配器，范围纠正被严格遵守。
  - `:41-45`：`_SECRET_ENV_NAME_PATTERN` 使用 `fullmatch` 而非 `search`，避免环境变量名部分匹配导致过宽收集。
  - `:47-57`：`_MIN_DYNAMIC_SECRET_LENGTH = 16`、`_MIN_DYNAMIC_HEX_SECRET_LENGTH = 32`、`_DYNAMIC_HEX_SECRET_CHARACTERS` 均为具名常量，非魔法数字。
  - `:60-93 _is_secret_like_environment_value`：值形态资格判断（RR-01 修正，见「RR-01 纠正复测」节）。该函数只作用于**名称已匹配**的环境变量值，不对任意待扫描文本做裸十六进制搜索，因此不违反 Controller 的范围纠正。
  - `:96-120 _known_environment_secret_values`：每次调用重新读取 `os.environ`，无缓存，因此同进程轮换立即生效——与 fix contract 第 2 条一致。返回值按长度降序排序，保证长值先于其子串被替换，避免部分脱敏残留。
  - `has_secret_shapes` / `redact_secret_shapes`：均在静态 regex 之后追加精确值检测/替换。
  - `utils/codex_review_gate.py:133`、`utils/dual_model_pipeline_check.py:82`：两个 scanner 均通过**显式** `include_environment_secrets=True` 开关调用；`utils/codex_review_gate.py:638-641` 与 `utils/dual_model_pipeline_check.py:245-248` 的判定逻辑一致，matcher 选择不再隐式绑定 `redact` 输出策略——满足 fix contract 第 3 条。
- **测试**: `tests/cli/test_arg_parsing_redaction.py` + `tests/test_codex_review_gate.py` + `tests/test_dual_model_pipeline_check.py` = **261 passed**（轮次 2 实跑）。
- **覆盖率**: `dayu/redaction.py` = `100%`（`29 passed`，轮次 2 实跑）。
- **三个 machine-readable gates 实跑**（在本机确有 5 个真实凭据环境变量的条件下）：
  ```
  ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / DEEPSEEK_API_KEY / FMP_API_KEY / SERPER_API_KEY

  python -m utils.codex_review_gate --allow-waiting --json   => ok=True
  python -m utils.dual_model_pipeline_check --json           => ok=True
  python -m utils.validate_handoff_docs --json               => ok=True
  ```
  即在真实凭据存在的宿主上，新增的动态扫描未对仓库既有文本产生误报。
- **状态**: `accepted 已修复`（fix contract 四条全部满足；轮次 1 发现的 `RR-01` 已在轮次 2 复测确认 **CLOSED**）

### PR2-DOC-01 — 已修复 / 验证通过

- **裁决 fix contract**: exact 6 个方法补中文概览 + 参数 + 返回值 + 异常；不得改可执行行为、类型或数据契约。
- **实现核验**（逐个确认，6/6 齐全且四段完整）:
  - `dayu/engine/model_circuit_breaker.py:106 _InMemoryCircuitStateStore.locked_entry`
  - `dayu/engine/model_circuit_breaker.py:126 _InMemoryCircuitStateStore.reset`
  - `dayu/engine/model_circuit_breaker.py:221 _SQLiteCircuitStateStore.locked_entry`（异常段正确标注 `sqlite3.Error`）
  - `dayu/engine/model_circuit_breaker.py:246 _SQLiteCircuitStateStore.reset`（异常段正确标注 `sqlite3.Error`）
  - `dayu/services/internal/write_pipeline/model_usage_ledger.py:531 WriteModelUsageLedger.record`（异常段正确标注 `WriteBudgetExceededError`）
  - `dayu/services/internal/write_pipeline/model_usage_ledger.py:583 WriteModelUsageLedger.build_summary`
- **行为不变性**: 两个文件的 diff 为纯新增行（`+50` / `+30`，无删除行），无可执行语句变更。Fix 记录声明的去 docstring AST 比对结论与该 diff 形态一致。
- **覆盖率**: `model_circuit_breaker.py` = `91%`（35 passed，含内存/SQLite/Runner/factory 四个测试文件）；`model_usage_ledger.py` = `84%`（12 passed）。均 ≥80%。
- **状态**: `accepted 已修复`

## Rejected 裁决证据复核

### DeepSeek F1 — 复核结论：Controller rejection 成立，原 finding 证据失效

这是本次 re-review 的重点项。用户明确要求走真实 `run_write_command` 外层校验链而非内层 helper，已照做。

- **原 finding 缺陷**: 我在初审中只直接调用了内层 `_validate_challenger_run_plan_args`，未经过 `dayu/cli/commands/write.py:563` 处更早执行的 `_validate_research_materialization_args`。这是证据链取样点错误，不是被审代码的缺陷。
- **外层链路实测**（`dayu.cli.arg_parsing._create_parser()` 真实 parser + `_validate_research_materialization_args` 外层校验，穷举三种短路形态 + 相邻边界）：

  ```
  BLOCKED          无 challenger-output + --summary
                   -> --routing-challenger-run-approval-input 需要至少一个 Challenger 模型覆盖参数
  BLOCKED          无 challenger-output + --infer
                   -> --routing-challenger-run-approval-input 需要至少一个 Challenger 模型覆盖参数
  BLOCKED          有 co 无 challenger-model + --summary
                   -> --challenger-output 需要同时提供至少一个 Challenger 模型覆盖参数
  BLOCKED          有 co 有 cm + --summary
                   -> Challenger 运行不能与 --summary 同时使用
  BLOCKED          有 co 有 cam + --infer
                   -> Challenger 运行暂不支持 infer-only 的 --infer
  BLOCKED          有 co 有 cm + --preflight-only
                   -> --routing-challenger-run-approval-input 不能与 --preflight-only 同时使用
  BLOCKED          有 co 有 cm + --reprice-costs
                   -> --reprice-costs 需要与 --summary 同时使用
  REACHES-CONSUME  有 co 有 cm 正常双跑(基线)
  ```

- **拦截点行号**（与 Controller 裁决所述一致）: `dayu/cli/commands/_write_params_validation.py:1545-1546`（Challenger + `--summary`）、`:1547-1548`（Challenger + `--infer`）、`:1852-1853`（run approval + `--preflight-only`）。三处均**早于** `write.py:632` 的凭据消费执行。
- **结论**: 「凭据先消费再短路」的路径在真实入口不可达。基线用例证明外层链路不会过度拦截合法双跑（唯一 `REACHES-CONSUME` 者正是正常双跑形态），因此拒绝理由不是靠过宽拦截换来的。
- **状态**: `rejected 证据失效`

### DeepSeek F2 — 复核结论：Controller rejection 成立

- 裁决依据 accepted plan v5.3/v5.4/v5.5 对 `DayuCliArguments` exact21 边界的显式锁定，以及「不把 Namespace 子类扩成 god bag」的架构取舍。
- F2 原本以 F1 为其唯一已实现实例；F1 既已证伪，F2 退化为无失败实例的类型学观察，不满足初审自身「无证据不报 finding」的门槛。
- 该 fail-open 语义特性本身仍客观存在，但不构成本 PR 的 material defect。
- **状态**: `rejected 按理由关闭`

### DeepSeek F5 — 复核结论：Controller rejection 成立

- 裁决理由为 intentional behavior：抑制键为 `(provider, sha256(key))`，仅 auto 模式 401/403 生效，换 key 立即恢复，显式 provider 不受抑制。
- 复核确认现有测试 `tests/engine/test_web_tools.py:862 test_search_web_auto_suppresses_auth_failed_key_until_key_changes` 精确锁定该产品意图。
- 我在初审中确实未能提交「同一 key 从真实 auth failure 恢复后仍应自动重试」的产品契约或失败复现，Controller 关于举证不足的判断成立。TTL/registry 属独立可靠性设计。
- **状态**: `rejected 按理由关闭`

### DeepSeek F7 — 复核结论：Controller rejection 成立

- 复核确认 `utils/ci_pr_pyright.py:108` 声明、`:297` 赋值、`tests/test_ci_pr_pyright.py:156/168/482` 三处 characterization 断言均维持原状，本轮 fix 未触碰该文件。
- 该字段不改变 fail-closed 判定、CI exit code 或报告内容，non-material 定性成立。
- **状态**: `rejected 按理由关闭`

### MiMo F3 / F5 / F6 / F7 — 复核结论：不属本 reviewer 初审范围

- 这四项来自 MiMo 初审。本次 re-review 已阅读 Controller 对各项的 rejection 理由，未发现与当前代码状态冲突的事实（特别是 F7 所涉的 recovery commit tree 一致性，我在初审中已用 `git diff --stat 172de45 783b15a` 为空独立证实）。
- 逐项证据强度的最终裁定属 MiMo 通道 re-review 职责，本报告不代为判定。

## Deferred 裁决复核

### DeepSeek F4 — deferred-with-owner，**未修复**，不得称为 fixed

- **Controller 事实纠正核验**: 494 缺失计数可复现（我在初审中以 AST 统计得出同一数字）。Controller 的分类纠正（478 private / 9 dunder / 7 public-name）与 exact6 已修复的说明，与本次 diff 形态一致。
- **当前真实状态**: 本轮仅修复 exact6，**剩余 exact488 缺失 docstring 的生产函数仍然存在**，包括我在初审 F4 中点名的 `write_model_configuration_application.py` 原子事务链路全部函数（`_stage_content`、`_replace_staged_file`、`_verify_applied_snapshot`、`_restore_operations`、`_recover_interrupted_transaction` 等）。
- **严重度纠正**: Medium → Low maintainability debt。我接受该纠正——F4 无当前行为错误，且 494/494 在架构 work-unit 前置基线 `4586e04` 已缺失，本 PR 的模块迁移没有删除既有 docstring，因此不是本 PR 引入的回归。
- **Owner / destination**: 后续独立 `production-docstring-compliance` work unit，由仓库 maintainer / Controller 负责；输入为固定 AST inventory（exact488）。
- **状态**: `deferred 保持明确 owner（未修复）`

### MiMo F4 — deferred-with-owner，**未修复**

- Owner: Service owner / 仓库 maintainer；destination: 独立 `typed-write-payload-contracts` work unit。
- 本报告不代 MiMo 通道复核该项证据强度，仅确认其 deferred 属性与 owner 已明确记录，未被伪称为 fixed。
- **状态**: `deferred 保持明确 owner（未修复）`

## 新 blocker 检查

对本轮 12 个变更文件做定向对抗性检查，结论：**未发现 blocker**。轮次 1 发现的 Low 级 fix-regression `RR-01` 已在轮次 2 复测确认 CLOSED（见下节）。

轮次 2 已执行的检查与结果：

```text
pytest（clean env，移除宿主 SERPER_API_KEY / TAVILY_API_KEY）
  tests/cli/test_arg_parsing_redaction.py
  tests/test_codex_review_gate.py
  tests/test_dual_model_pipeline_check.py            => 261 passed
  tests/engine/test_async_anthropic_runner.py        =>  21 passed

coverage: dayu/redaction.py = 100%（29 passed）

pyright  => 0 errors, 0 warnings, 0 informations
ruff check dayu/redaction.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py
         => All checks passed!
git diff --check => clean

三个 machine-readable gates（宿主含 5 个真实凭据环境变量）:
  validate_handoff_docs --json              => ok=True, issues=0
  codex_review_gate --allow-waiting --json  => ok=True
  dual_model_pipeline_check --json          => ok=True
```

轮次 1 已执行且本轮未失效的检查（覆盖率与其余 focused 集合）：

```text
pytest（clean env）覆盖 Anthropic / redaction / web tools / circuit breaker 等
  => 395 passed
pytest tests/engine/test_model_circuit_breaker*.py
     tests/engine/test_runner_factory_circuit_breaker.py
     tests/engine/test_sqlite_model_circuit_breaker.py   => 35 passed
pytest tests/engine/test_model_usage_ledger.py           => 12 passed

逐文件 coverage:
  dayu/redaction.py                                            100%
  dayu/engine/tools/web_search_providers.py                     96%
  dayu/engine/model_circuit_breaker.py                          91%
  dayu/services/internal/write_pipeline/model_usage_ledger.py    84%
  dayu/engine/async_anthropic_runner.py                          82%
（均 >= AGENTS.md 的 80% 目标）
```

修正范围核验：`git status --short dayu/cli/` 无输出，确认 RR-01 修正未触碰 CLI 校验链（F1 相关证据链未被本轮修改影响）。变更仍限于 `dayu/redaction.py`、两个 scanner 与三个对应测试文件。

## Fix-regression finding

### RR-01-已修复（CLOSED）-[低]-匹配名环境变量若为含空格的普通短语，动态脱敏会把正常文本判为凭据并使 gate 失败

> **最终状态（轮次 2 纠正复测）**：**CLOSED**。修正已落到工作树 `dayu/redaction.py:60-93 _is_secret_like_environment_value`，经本 reviewer 独立复测通过，不计入 open counts。原 finding 内容保留如下以存证。

- **入口/函数**: `dayu.redaction.has_secret_shapes` / `redact_secret_shapes` → `utils.codex_review_gate._scan_files` → `run_review_gate` → CLI `--json` 退出码；同链路亦存在于 `utils.dual_model_pipeline_check._scan_text_files`
- **文件(行号)**（修正前）:
  - `dayu/redaction.py:69-70`（收集条件仅有名称 `fullmatch` 与 `len >= 16`，**无值形状约束**）
  - `dayu/redaction.py:88`（`has_secret_shapes` 的 `any(value in text ...)` 精确子串判定）
  - `dayu/redaction.py:105-106`（`redact_secret_shapes` 的 `str.replace` 无边界替换）
  - `utils/codex_review_gate.py:639-641`（scanner 采纳该判定）
  - `utils/codex_review_gate.py:157` / `:719`（secret hit → `ok=false` / exit 1）
  - `utils/dual_model_pipeline_check.py:245-248`（同一模式）
- **输入场景**: 进程中存在名称匹配 `*_API_KEY` / `*_AUTH_TOKEN` / `*_ACCESS_TOKEN` / `HF_TOKEN` 的环境变量，其值为长度 ≥16 的普通短语（含空格的自然语言、占位符、未替换的模板文案），且仓库被扫描文本恰好包含该短语
- **实际分支**（修正前）: 收集条件对该值成立 → `value in text` 命中 → `utils/codex_review_gate.py:640` 置 `matched=True` → 产生 `ScanHit` → `:157` 使 `ok=false`、`:719` 返回退出码 1
- **预期行为**: 动态精确值脱敏的目标是保护**真实凭据**。含空格的自然语言短语不具备凭据形状，不应被当作凭据；正常文档文本不应被脱敏，更不应使 review gate 失败
- **实际行为**（修正前）: 正常语句被替换为 `<redacted>`，且 machine-readable gate 报 secret hit 并 fail
- **直接证据**（轮次 1 最小复现，已实测，宿主真实凭据变量全部 unset 以隔离变量）:

  ```text
  含空格自然短语   "the quick brown fox"          len= 19  -> hit=True    <-- 误报
  占位符短语       "please configure me"          len= 19  -> hit=True    <-- 误报
  常见占位符       "your-api-key-here!!"          len= 19  -> hit=True    <-- 误报
  <16 含空格       "set me later"                 len= 12  -> hit=False
  典型真实 key     "sk-abcdefghij0123456789abcd"  len= 27  -> hit=True    （正确命中）
  ```

  真实 scanner 层同样命中：`_scan_files(..., include_environment_secrets=True)` 产生 `ScanHit(preview='<redacted>')`，经 `utils/codex_review_gate.py:157` 与 `:719` 直接导致 `ok=false` 与退出码 1
- **影响**（修正前）: gate 假阳性。方向为 fail-closed，**不泄漏凭据**，但会把正常文档文本脱敏成 `<redacted>`，并使两个 gate 在特定宿主环境上无故 fail，且失败原因被自身脱敏机制掩盖，定位成本高
- **建议改法和验证点**（原建议）: 在收集条件上追加**值形状**约束而不仅是长度；验证点为 (a) 含空格短语环境值不触发 `has_secret_shapes`；(b) 真实形状凭据仍被精确检测与脱敏，防止修复过度收紧
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **状态**: **已修复 / CLOSED**（修正实现与独立复测证据见下节）

## RR-01 纠正复测（轮次 2）

### 修正实现核验

新增 `dayu/redaction.py:60-93 _is_secret_like_environment_value`，作为环境候选的**值形态资格判断**，判定顺序为：

1. `len(value) < _MIN_DYNAMIC_SECRET_LENGTH(16)` → 拒绝；
2. 值含任意空白字符 → 拒绝（直接封死 RR-01 的自然语言短语通道）；
3. `len(value) >= _MIN_DYNAMIC_HEX_SECRET_LENGTH(32)` 且全部字符 ∈ `_DYNAMIC_HEX_SECRET_CHARACTERS` → 接受；
4. 否则要求「字母 / 数字 / 非字母数字」三类字符中至少命中 2 类 → 混合 token 接受，纯字母普通词拒绝。

**范围合规性核验**：第 3 条的纯十六进制放行只在**环境候选资格判断**内生效，`has_secret_shapes` 对待扫描文本仍只跑 `SECRET_KEY_PATTERN`（`sk-` / `AIza`）+ 已配置精确值子串匹配，**没有**引入 Controller 明确拒绝的裸 `{32,}` 全局十六进制模式。因此未配置为凭据的 Git SHA 不会被匹配。该结论由下方 D 组用例实测锁定。

### 独立复测证据（clean env：`ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `DEEPSEEK_API_KEY` / `FMP_API_KEY` / `SERPER_API_KEY` / `TAVILY_API_KEY` 及一切 `*_API_KEY`、`*_AUTH_TOKEN`、`*_ACCESS_TOKEN`、`HF_TOKEN` 全部 unset）

#### A. 原语层 `has_secret_shapes` / `redact_secret_shapes`

| 用例 | `DEMO_API_KEY` 取值 | len | 期望 | 实测 |
|---|---|---|---|---|
| ordinary phrase（含空格） | `the quick brown fox` | 19 | 不命中 | `False` ✔ |
| ordinary phrase（占位符） | `please configure me` | 19 | 不命中 | `False` ✔ |
| 纯字母（无空格） | `abcdefghijklmnopqrst` | 20 | 不命中 | `False` ✔ |
| 纯非 hex 字母（32） | `z`×32 | 32 | 不命中 | `False` ✔ |
| hex API key（已配置） | `0123456789abcdef`×2 | 32 | 命中 | `True` ✔ |
| 混合 token（16 边界） | `abcd1234efgh5678` | 16 | 命中 | `True` ✔ |
| 混合 token（15 边界） | `abcd1234efgh567` | 15 | 不命中 | `False` ✔ |
| 混合 alpha+符号 | `abcdefgh-ijklmnop-qr` | 20 | 命中 | `True` ✔ |
| 短环境值 | `x` | 1 | 不命中 | `False` ✔ |
| 未配置 Git SHA-1 | （未配置） | 40 | 不命中 | `False` ✔ |
| 未配置 Git SHA-256 | （未配置） | 64 | 不命中 | `False` ✔ |
| 静态 `sk-` 前缀 | （未配置） | 27 | 命中 | `True` ✔ |
| 静态 `AIza` 前缀 | （未配置） | 39 | 命中 | `True` ✔ |

输出脱敏实测：

```text
DEMO_API_KEY="the quick brown fox"
  redact("note: the quick brown fox")        -> 'note: the quick brown fox'          （原样，不再误脱敏）
DEMO_API_KEY="abcdefghijklmnopqrst"
  redact("note: abcdefghijklmnopqrst")       -> 'note: abcdefghijklmnopqrst'         （原样）
DEMO_API_KEY="0123456789abcdef0123456789abcdef"
  redact("key=0123456789abcdef0123456789abcdef") -> 'key=<redacted>'                 （真阳性保持）
（未配置）
  redact("commit aaaa...0 merged")           -> 原样返回，40 位 SHA 未被改写
  redact("commit bbbb...1 merged")           -> 原样返回，64 位 SHA 未被改写
```

#### B. 十六进制资格判断阈值刻画（仅改 `DEMO_API_KEY` 取值）

| 值形态 | len | 命中 | 说明 |
|---|---|---|---|
| 纯数字 | 31 | `False` | 单一字符类且 <32，被规则 4 拒绝 |
| 纯数字 | 32 | `True` | 规则 3 放行（纯 hex ≥32） |
| 纯 hex 字母 `abcdef…` | 31 | `False` | <32 |
| 纯 hex 字母 `abcdef…` | 32 | `True` | 规则 3 放行 |
| 纯非 hex 字母 `z`×32 | 32 | `False` | 不在 hex 字符集，规则 4 单一字符类拒绝 |
| 混合 alnum | 15 | `False` | <16 长度下界 |
| 混合 alnum | 16 | `True` | 规则 4 双字符类放行 |
| 混合 alnum | 31 | `True` | 规则 4 放行（不受 32 位 hex 阈值约束） |

> **纠正说明**：本 reviewer 在轮次 2 首次跑表时把「31 位纯 hex 数字混合值 `0123456789abcdef0123456789abcde`」预期为不命中，实测为命中。复核后确认这是**本 reviewer 的期望值推导错误**，不是实现缺陷——该值同时含字母与数字，属规则 4 的合格混合 token，本就应命中；32 位阈值只约束**纯**十六进制这一条单独通道。已按上表重新刻画，不作为 finding。

#### C. 两个 scanner 端到端（真实 `_scan_files` / `_scan_text_files`，`include_environment_secrets` 开/关对照）

| 用例 | gate 关/开 | pipeline 关/开 | 期望（开） | 结果 |
|---|---|---|---|---|
| ordinary phrase（含空格） | `0/0` | `0/0` | `0` | ✔ |
| 纯字母（20） | `0/0` | `0/0` | `0` | ✔ |
| 纯非 hex 字母（32） | `0/0` | `0/0` | `0` | ✔ |
| hex API key（32，已配置） | `0/1` | `0/1` | `1` | ✔ preview 均为 `<redacted>` |
| 未配置 Git SHA-1（40） | `0/0` | `0/0` | `0` | ✔ |
| 未配置 Git SHA-256（64） | `0/0` | `0/0` | `0` | ✔ |
| SHA-1 + SHA-256 + 无关 env 短语同文件 | `0/0` | `0/0` | `0` | ✔ |
| 静态 `sk-` | `1/1` | `1/1` | `1` | ✔ |
| 静态 `AIza` | `1/1` | `1/1` | `1` | ✔ |

MISMATCH COUNT = `0`。两个 scanner 行为完全一致，未出现单侧漂移。

#### D. 回归测试锁定核验

修正同时补入了负例测试，非仅靠实现约束：

- `tests/cli/test_arg_parsing_redaction.py:376-409 test_non_secret_like_environment_value_is_ignored`，`parametrize` 五组：`"x"`、`"Api_Key-2026-XY"`（<16）、`"the quick brown fox"`（含空格短语）、`"documentationreference"`（纯字母）、`"A"*31`（单一字符类 31 位边界），断言 `not has_secret_shapes(text)` 且 `redact_secret_shapes(text) == text`。
- `tests/cli/test_arg_parsing_redaction.py:411 test_unconfigured_git_sha_is_not_treated_as_secret`，`parametrize` `"a"*40` / `"b"*64`，锁定 Controller 范围纠正的核心负例。
- `test_dynamic_environment_secret_value_is_matched_exactly` 保留精确值语义（`exact_value[:-1]` 不命中），`test_dynamic_environment_secret_rotation_is_observed` 保留同进程轮换语义。

即真阳性（`sk-` / `AIza` / hex key / 轮换 / 精确值）与新增假阴性防线（短语 / 纯字母 / 长度与字符类边界 / Git SHA）双向都有测试锁定，不存在「靠实现收紧但无回归保护」的缺口。

### 裁决

`RR-01` **CLOSED**。修正方向与轮次 1 建议一致（追加值形态约束而非放宽长度），未削弱 fix contract 第 2 条的精确值 + 同进程轮换语义，未引入 Controller 拒绝的全局裸十六进制模式，未触碰 CLI 校验链或其它 accepted fix 的实现。未发现由该修正引入的新问题。

## 逐项状态汇总

| 编号 | 来源 | 原严重度 | Controller 裁决 | 本次复核状态 |
|---|---|---|---|---|
| PR2-ANTHROPIC-01 | DeepSeek F3 | Medium | accepted | **accepted 已修复** |
| PR2-COVERAGE-01 | DeepSeek F6 | Low | accepted | **accepted 已修复** |
| PR2-SEC-01 | MiMo F1+F2 | High | accepted | **accepted 已修复**（RR-01 已 CLOSED） |
| PR2-DOC-01 | MiMo F8 | Low | accepted | **accepted 已修复** |
| RR-01 | 本次 re-review | Low | 已接受为 Low fix-regression | **已修复 / CLOSED**（轮次 2 独立复测通过，不计入 open） |
| DeepSeek F1 | DeepSeek | High | rejected-with-reason | **rejected 证据失效**（外层链路实测三形态全 BLOCKED） |
| DeepSeek F2 | DeepSeek | Medium | rejected-with-reason | **rejected 按理由关闭**（accepted design，失去唯一实例） |
| DeepSeek F5 | DeepSeek | Medium | rejected-with-reason | **rejected 按理由关闭**（intentional behavior，举证不足） |
| DeepSeek F7 | DeepSeek | Low | rejected-with-reason | **rejected 按理由关闭**（non-material） |
| DeepSeek F4 | DeepSeek | Medium→Low | deferred-with-owner | **deferred 保持明确 owner（未修复，exact488 仍在）** |
| MiMo F3/F5/F6/F7 | MiMo | — | rejected-with-reason | 不属本 reviewer 初审范围，未发现与当前代码冲突的事实 |
| MiMo F4 | MiMo | — | deferred-with-owner | **deferred 保持明确 owner（未修复）** |

## Open Questions

- PR-2 的 GitHub metadata 与 CI checks 实况仍**无法直接读取**：本机 `gh` CLI 未认证。Controller 裁决记录「三个 checks 均 success、mergeable state 为 clean、PR 当前 `draft=false`」，本次 re-review 无法独立复验该三条 PR facts，按 skill 约束不编造。若最终 gate 要求 Draft 状态，`draft=false` 是 Controller 已记录的未满足项，不属代码 finding。
- 本轮 fix 尚未 commit（`git status` 显示 12 个文件为工作区未暂存修改）。本报告的全部验证针对**当前工作区状态**，非某个 commit。

## Residual Risk

- **RR-01 已 CLOSED，不再是 open 项**。残余边界仅为：动态检测的资格判断是启发式的，若真实凭据恰好是「≥16 位纯字母且非十六进制」或「<16 位」的极端形态，将不进入动态精确值保护，只能依赖静态 `sk-` / `AIza` 形状。方向为 fail-open（少脱敏），但仅影响该极端形态凭据在错误消息与 handoff 扫描中的额外保护层，不影响凭据本身的存储与传输路径。当前 provider 凭据均不属该形态。
- **`pause_turn` 当前为 fail-loud 而非续传**：这是 Controller 有意选择的边界——在 `AgentMessage` 能无损保留 Anthropic server-tool 内容块之前，宁可显式失败也不静默标记成功。代价是若线上真实触发 `pause_turn`，用户会看到硬错误而非自动续写。完整续传属独立 Engine 消息契约 work unit，owner 需在该 work unit 中承接。
- **exact488 docstring 债务仍在**：包括配置应用原子事务、补偿回滚、人工恢复等高风险链路。这些路径的前置条件、副作用与异常契约至今未文档化，后续修改的回归风险未被本轮 fix 降低。owner 为 `production-docstring-compliance` work unit。
- **`_validate_challenger_run_plan_args` 的禁用清单仍零测试**：`grep -rn "Challenger 双跑授权" tests/` 命中 0 次。F1 虽已证伪（外层链路兜住），但内层门禁本身依然无测试锁定，且内层为 fail-open 语义。当前安全性完全依赖 `_validate_research_materialization_args` 的外层拦截；若未来重构调整两层校验的调用顺序或职责划分，将失去回归保护。这不是本 PR 的 open finding，但是真实的 test gap。
- **初审未覆盖区域仍未覆盖**：`write_model_configuration_manual_recovery_*.py` 系列 5 个新增模块的完整状态机路径、`write_model_health.py` 的健康趋势计算，两轮均未逐行走读（本机 Agent 后端不可用，无法并行深挖）。其 finding 状态应视为**未知**，而非「已确认无问题」。
- **环境依赖测试**：`tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key` 在宿主配置了 `SERPER_API_KEY` 时会假失败（pre-existing，非本 PR 引入，Controller 已知悉）。本次所有验证均显式移除该变量后运行。该测试自身缺少 `monkeypatch.delenv`，会持续干扰后续 gate 的验证信号可信度。
