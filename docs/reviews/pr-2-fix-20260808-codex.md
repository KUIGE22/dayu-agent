# PR-2 accepted findings 修复记录

## 状态

**DUAL PR RE-REVIEW PASS / READY FOR ACCEPTED PR REVIEW COMMIT**

- Gate：PR-2 review fix
- 裁决真源：`docs/reviews/pr-2-review-adjudication-20260808-codex.md`
- 修复范围：仅 `PR2-SEC-01`、`PR2-ANTHROPIC-01`、`PR2-COVERAGE-01`、
  `PR2-DOC-01`
- 未执行：gateflow、代码 review、commit、push、PR 操作

## 修复结果

### PR2-SEC-01

- 共享静态形状增加带可靠 `AIza` 前缀的 Google/Gemini legacy key；未增加裸长十六进制
  匹配器。
- 每次调用都重新读取名称符合 `*_API_KEY`、`*_AUTH_TOKEN`、
  `*_ACCESS_TOKEN`、`HF_TOKEN` 的当前环境变量值。候选必须至少 16 位、不含空白，并满足
  混合字符 token 形态；至少 32 位的纯十六进制值在环境候选阶段单独放行。通过资格判断后
  仍按未经裁剪的精确值检测和脱敏，因而同进程轮换立即生效。
- 十六进制资格判断只检查已由环境变量名筛出的候选值，不对任意待扫描文本增加裸长
  十六进制模式；`TEST_API_KEY=x`、`DEMO_API_KEY="the quick brown fox"` 与纯字母普通词
  不会污染普通文本。
- Codex review gate 与 dual-model pipeline 的 secret scan 均通过
  显式 `include_environment_secrets=True` 开关调用 `has_secret_shapes` 判断动态值；
  `redact` 仅决定预览输出策略，不再隐式选择 matcher。
- 回归测试覆盖 argparse stderr、共享检测/替换原语、两个 scanner、同进程轮换、精确值
  语义、短环境值/空白短语/纯字母词负例、15/16 与 31/32 位边界、matcher/输出策略解耦，
  以及未配置的 40/64 位 Git SHA 不误报。

### PR2-ANTHROPIC-01

- 删除 `pause_turn -> stop` 的成功终态映射。
- 流式 `message_delta` 收到 `pause_turn` 时记录稳定协议错误
  `anthropic_pause_turn_unsupported`；共享 Runner 随后以
  `CONTENT_COMPLETE -> ERROR` 收口，不产出成功 `DONE`。
- 非流式响应在归一化前 fail-loud，仅产出相同稳定 `ERROR`，不产出成功 `DONE`。
- 未伪装成 `length`，未发送额外 user continuation prompt；完整同回合续传仍属于独立
  Engine 消息契约 work unit。

### PR2-COVERAGE-01

- 仅移除 `search_public_web` 已被测试执行的 provider 异常分支上的旧
  `pragma: no cover`；auth suppression 的 fingerprint、auto-only 语义、日志与生命周期均未改。

### PR2-DOC-01

- 仅为两个 state store 的 4 个 `locked_entry` / `reset` 方法，以及 usage ledger 的
  `record` / `build_summary` 方法补充准确的中文概览、参数、返回值和异常说明。
- 对两个模块执行去 docstring AST 比对，均与 `HEAD` 的可执行 AST 完全一致。

## 文件范围

- `dayu/redaction.py`
- `utils/codex_review_gate.py`
- `utils/dual_model_pipeline_check.py`
- `tests/cli/test_arg_parsing_redaction.py`
- `tests/test_codex_review_gate.py`
- `tests/test_dual_model_pipeline_check.py`
- `dayu/engine/async_anthropic_runner.py`
- `tests/engine/test_async_anthropic_runner.py`
- `dayu/engine/tools/web_search_providers.py`
- `dayu/engine/model_circuit_breaker.py`
- `dayu/services/internal/write_pipeline/model_usage_ledger.py`
- `dayu/engine/README.md`
- `docs/reviews/pr-2-fix-20260808-codex.md`

`dayu/engine/README.md` 已同步当前 `pause_turn` fail-loud 契约。`tests/README.md` 的测试分层、
运行命令与维护规则未变化，因此按职责检查后不修改。两份初审与 Controller 裁决文档保持不改。

## 验证证据

### Focused pytest

```text
pytest -q tests/engine/test_async_anthropic_runner.py \
  tests/cli/test_arg_parsing_redaction.py \
  tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py \
  tests/engine/test_web_tools.py::test_search_web_auto_suppresses_auth_failed_key_until_key_changes
=> 275 passed
```

Controller correction 后的 redaction/utils focused 回归：

```text
pytest -q tests/cli/test_arg_parsing_redaction.py \
  tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py
=> 254 passed
```

PR re-review correction 增加环境候选 token 资格规则后的同一 focused 集合：

```text
pytest -q tests/cli/test_arg_parsing_redaction.py \
  tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py
=> 261 passed
```

### Pyright 与 Ruff

```text
pyright
=> 0 errors, 0 warnings, 0 informations

ruff check <全部 11 个变更 Python 文件>
=> All checks passed!
```

因此 Ruff 当前结果为零问题，不存在 positive delta。

### 逐生产文件 coverage

```text
dayu/redaction.py                                              100%
dayu/engine/async_anthropic_runner.py                           82%
dayu/engine/tools/web_search_providers.py                       96%
dayu/engine/model_circuit_breaker.py                            91%
dayu/services/internal/write_pipeline/model_usage_ledger.py     84%
```

Controller correction 后单独复跑 `dayu/redaction.py`：`24 passed`，覆盖率 `100.00%`。
PR re-review correction 后再次单独复跑：`29 passed`，覆盖率 `100.00%`。

- 其余四个文件的 clean coverage 命令：显式移除宿主已有的 `TAVILY_API_KEY` /
  `SERPER_API_KEY` 后运行 redaction、Anthropic、完整 web tools、usage ledger 测试，
  `157 passed`，总覆盖率 `87.29%`，每个文件均不低于 80%。
- circuit breaker 的内存、SQLite、Runner 与 factory 测试共 `35 passed`，目标文件 `91.09%`。
- 首次完整 web tools coverage 运行有 `175 passed, 1 failed`：宿主已配置
  `SERPER_API_KEY`，使“缺少 key”测试越过预期分支并尝试访问不可用的本地代理；显式移除该
  环境变量后的相同测试 clean 通过。没有为此环境污染修改生产代码或测试。

### AST、JSON gates 与 diff-check

```text
exact6 所在两个模块去 docstring AST 对比
=> executable AST unchanged（2/2）

python -m utils.validate_handoff_docs --json
=> {"ok": true, "issues": []}

python -m utils.codex_review_gate --allow-waiting --json
=> {"ok": true, ...}

python -m utils.dual_model_pipeline_check --json
=> {"ok": true, ...}

git diff --check
=> clean
```

## 残余风险与边界

- 当前修复有意不实现 Anthropic 官方的同回合 continuation；在消息契约能保留完整 assistant
  content blocks 前，`pause_turn` 会明确失败，避免把未完成响应静默标记成功。
- 验证期间仅观察到 requests 依赖版本与 pandas 重载 warning；它们未导致 focused、coverage、
  pyright、Ruff 或 JSON gate 失败，也不由本轮变更引入。
- accepted 四项均已闭环；没有需要扩大本轮范围处理的 blocking gap。

## 双路复审闭环

- DeepSeek: `docs/reviews/pr-2-rereview-20260808-230100-deepseek.md`，`PASS`，
  open High/Medium/Low = `0/0/0`。
- MiMo: `docs/reviews/pr-2-rereview-20260808-230101-mimo.md`，`PASS`，
  open High/Medium/Low = `0/0/0`。
- DeepSeek 首轮复审发现的 Low fix-regression `RR-01` 已按 Controller 裁决最小修正；
  两路 corrective re-review 均独立复测并确认 `CLOSED`。
- Deferred-with-owner 两项继续保留各自 owner 与独立 work unit，不计入本 PR open counts，
  未被伪称为 fixed。
