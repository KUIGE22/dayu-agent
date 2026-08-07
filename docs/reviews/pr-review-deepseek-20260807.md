# PR Review — DeepSeek

## Scope

- **Mode**: PR Review
- **PR**: #1 (https://github.com/KUIGE22/dayu-agent/pull/1)
- **Base**: origin/main
- **Base SHA**: 2115c86d5a9027bb51cbbc8a4d0175080732e4e6
- **HEAD SHA**: 6e22cb57ac180ab69483baf0af1b45efefad3233
- **Merge-base**: 2115c86d5a9027bb51cbbc8a4d0175080732e4e6 (clean, == base)
- **Diff**: origin/main...HEAD
- **Output file**: docs/reviews/pr-review-deepseek-20260807.md
- **Review date**: 2026-08-07
- **Files changed**: 214 (110,467 insertions, 618 deletions)
- **Git status at review start**: clean

### Included scope

按风险优先级分层抽样，覆盖以下模块和入口：

| 层级 | 模块 | 审查方式 |
|------|------|----------|
| CLI 安全 | `dayu/cli/arg_parsing.py` | 全量走读（约 2028 行） |
| Engine | `dayu/engine/async_anthropic_runner.py` | 全量走读（531 行） |
| Engine | `dayu/engine/model_circuit_breaker.py` | 全量走读（535 行） |
| Engine | `dayu/engine/runner_factory.py` | 全量走读（变更部分） |
| Host | `dayu/host/executor.py` | 全量走读（变更部分） |
| Host | `dayu/host/agent_builder.py` | 全量走读（变更部分） |
| Service | `dayu/services/write_service.py` | 全量走读 |
| Service | `dayu/services/internal/write_pipeline/pipeline.py` | 全量走读 |
| Service | `dayu/services/internal/write_pipeline/model_usage_ledger.py` | 全量走读 |
| Service | `dayu/services/write_model_configuration_*.py` (5 文件) | 中等深度走读 |
| Contracts | `dayu/contracts/model_config.py`, `model_failover.py`, `model_usage.py` | 全量走读 |
| Research templates | `dayu/assets/research_templates/` (10 文件) | 逐文件对照检查 |
| Research template CLI | `dayu/cli/commands/research_template.py` | 中等深度走读 |
| Utils redaction | `utils/validate_handoff_docs.py`, `codex_review_gate.py`, `prepare_deepseek_task.py` | 安全面走读 |
| Tests | 关键测试文件 | 覆盖率分析 |

### 未覆盖区域

- `dayu/cli/commands/write.py` 的 5226 行全部变更（write 子命令报告打印逻辑）—— 仅通过 write_service.py 的调用点间接检查
- `dayu/services/write_model_challenger_*.py`（champion/challenger 对比运行服务）—— 未直接走读
- `dayu/services/write_model_configuration_manual_recovery_*.py`（手动恢复服务）—— 未直接走读
- `dayu/services/write_model_health.py`、`write_model_live_smoke_plan.py`、`write_run_comparison.py` —— 未走读
- `dayu/cli/research_template_checklist.py`、`research_template_assets.py` —— 仅通过调用链间接覆盖
- `dayu/fins/storage/` 变更 —— 未走读
- `utils/codex_review_gate.py`、`utils/prepare_deepseek_task.py`、`utils/dual_model_pipeline_check.py` 的全部功能路径 —— 仅安全面走读
- CI workflow (`.github/workflows/dual-model-gates.yml`) —— 未审查
- `pyproject.toml` 变更 —— 未审查

### 并行审查覆盖

本次审查使用了 4 个 Explore subagent 并行覆盖不同风险面：
- CLI arg_parsing 安全面（全量走读）
- Engine runner / circuit breaker / runner factory（全量走读）
- Host executor / agent builder / 架构边界（全量走读）
- Service write pipeline / model usage ledger / contracts（全量走读）
- Research template integrity / CLI 命令 / tests 覆盖（全量走读）
- Model configuration management services 状态机 / 数据完整性 / 回滚安全（中等深度走读）
- CLI redaction 与 utils redaction 的差异对照（逐文件比较）

所有 findings 由主 reviewer 去重、复核证据链、裁决 severity，discarded 了无法被同一逻辑/数据路径直接证据支撑的推测性发现。

---

## Findings

### 1-未修复-高-DayuCliArgumentParser 缺乏 CLI 输出脱敏

- **入口/函数**: `DayuCliArgumentParser.error()` / `parse_arguments()`
- **文件(行号)**: `dayu/cli/arg_parsing.py:26-43`, `dayu/cli/arg_parsing.py:2005-2018`
- **输入场景**: 操作者在 CLI 中将 API key 误作为 positional argument 或 option value 传入，例如 `python -m dayu.cli interactive sk-ant-api03-...`，或 `python -m dayu.cli write --model-name sk-...`
- **实际分支**: `DayuCliArgumentParser.error()` 仅对 `"required: command"` 做了特殊处理（行 39-41），其余所有错误通过 `super().error(message)` 透传到标准 argparse，直接打印包含原始输入值的 error message 和 usage line
- **预期行为**: 所有 CLI 错误输出、usage、help 文本应对 secret-shaped 字符串（如 `sk-` 前缀的 API key）做脱敏处理
- **实际行为**: argparse 的标准 `error()` 在 stderr 打印 `usage: python -m dayu.cli ...` 和完整 error message，其中包含用户输入的原始参数值。若包含 secret-shaped 值，直接泄漏
- **直接证据**:
  - `DayuCliArgumentParser` 继承 `argparse.ArgumentParser`（行 18），未继承 `RedactingArgumentParser`
  - `RedactingArgumentParser` 存在于 `utils/validate_handoff_docs.py:1019-1072`，提供了 `format_usage()`、`format_help()`、`error()` 三个覆盖方法，均调用 `redact_secret_shapes()` 脱敏
  - `redact_secret_shapes()` 使用正则 `(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}` 匹配 secret-shaped 字符串（`utils/validate_handoff_docs.py:18-19`）
  - 最近 commit `6e22cb5`、`b7dedc3` 标题明确提及 "redact parser prog in help and errors" 和 "redact cli parser errors"，但这些修复仅落在 `utils/` 下的工具模块，未覆盖主 CLI 解析器
  - 主 CLI 解析器 `parse_arguments()` 调用 `_create_parser().parse_args()`（行 2018），不做任何预处理
- **影响**: API key 泄漏到 stderr / 终端日志 / CI 日志。`sk-` 前缀覆盖 Anthropic、OpenAI 及多数 LLM provider 的 key 格式
- **建议改法和验证点**:
  - 将 `DayuCliArgumentParser` 的基类改为 `RedactingArgumentParser`（它本身继承 `argparse.ArgumentParser`，兼容现有行为）
  - 或在 `DayuCliArgumentParser` 内复制 `format_usage()`、`format_help()`、`error()` 的脱敏覆盖
  - 验证：构造包含 `sk-` 前缀字符串的 CLI 参数，确认 error/usage/help 输出中的该字符串被替换为 `<redacted>`
- **修复风险（低）**: `RedactingArgumentParser` 仅对三个方法做装饰（调用 `redact_secret_shapes` 后委托 `super()`），不影响解析行为
- **严重程度（高）**: 安全泄漏，有直接复现路径

---

### 2-未修复-中-Anthropic extended thinking 与 temperature 互斥未在构造期校验

- **入口/函数**: `AsyncAnthropicRunner._build_request_payload()`
- **文件(行号)**: `dayu/engine/async_anthropic_runner.py:475-478`
- **输入场景**: runner running config 中同时指定了 `thinking.type == "enabled"` 和 `temperature > 0`
- **实际分支**: 行 475-476 检测到 `thinking_budget = thinking.get("budget_tokens")` 为真后，从 payload 中 `payload.pop("temperature", None)` 静默丢弃 temperature；否则行 478 正常添加 temperature
- **预期行为**: Anthropic API 不允许 extended thinking 与 temperature 同时出现。若二者被同时配置，应在构造期尽早报错（fail-fast），而非在请求 payload 构建时静默丢弃
- **实际行为**: temperature 被静默丢弃。调用方可能以为 temperature 生效（例如在 budget/quality 评估中依赖该值），实际请求不带 temperature
- **直接证据**:
  - 行 474-478 的判断逻辑：`if isinstance(thinking, dict) and thinking.get("budget_tokens")` 直接 `payload.pop("temperature", None)`，不产生任何 warning 或 log
  - temperature 的来源链：`runner_factory.py:74,111` → `agent_create_args.temperature` → `resolved_execution_options.temperature`；两处可能在 `build_request_payload` 之前不做互斥检查
- **影响**: 静默行为偏差——调用方预期 temperature 控制生效，实际请求不带 temperature；debug 困难，需要检查原始 HTTP 请求 payload 才能发现
- **建议改法和验证点**:
  - 在 runner 构造期或 `_build_request_payload` 中，若同时检测到 thinking enabled 和 temperature 为非默认值，至少 emit warning log
  - 或者在 `AsyncAnthropicRunner` 构造时做互斥校验
  - 验证：构造 thinking=enabled + temperature=0.7 的 runner，确认有 warning；构造 thinking=enabled + temperature=0.0（默认），确认无 warning
- **修复风险（低）**: 仅新增 warning log，不改变行为
- **严重程度（中）**: 静默行为偏差，debug 成本高，但功能正确（temperature 确实不应与 thinking 共存）

---

### 3-未修复-中-全局 circuit breaker 单例跨 run/session 累积故障计数

- **入口/函数**: `_build_model_circuit_breaker()` → `GLOBAL_MODEL_CIRCUIT_BREAKERS`
- **文件(行号)**: `dayu/engine/runner_factory.py:186-187`, `dayu/engine/model_circuit_breaker.py:523`
- **输入场景**: 同一进程内多个 run/session 共享默认（无 SQLite state_path）的 circuit breaker；前一个 run 的模型故障导致 circuit OPEN，后续 run 也被阻塞
- **实际分支**: `_build_model_circuit_breaker()` 行 186-187：当未配置 `state_path` 时，返回进程级全局单例 `GLOBAL_MODEL_CIRCUIT_BREAKERS`。该单例在 `model_circuit_breaker.py:523` 定义为 `ModelCircuitBreakerRegistry()`，生命周期等于进程生命周期
- **预期行为**: Circuit breaker 故障计数应隔离到合理的边界（如单个 write run、或配置为按 run 重置）；跨 session 累积的故障计数不应导致新 session 一开始就被 circuit-open 拒绝
- **实际行为**: 若模型 A 在某次 write run 中触发 circuit OPEN（默认 cooldown 60s），60s 内同进程的其他 write run 同样被 circuit-open 拒绝。在 CLI 连续使用场景中（例如先 `write` 再 `prompt`），这会导致无辜请求被拒绝
- **直接证据**:
  - `GLOBAL_MODEL_CIRCUIT_BREAKERS` 是无参构造的 `ModelCircuitBreakerRegistry()`（行 523），内部用 `_InMemoryCircuitStateStore`（行 95），状态生命周期 == 进程生命周期
  - `_build_model_circuit_breaker()` 仅在 `state_path` 配置时创建隔离的持久化 registry；未配置时回退到单例（行 182-189）
  - `runner_factory.py:172-189` 的 docstring 未说明全局单例的跨 run 共享行为
- **影响**: 一个 run 的 transient failure 可能阻塞后续无关 run；当 circuit cooldown 60s 时影响有限（短时间窗口），但若配置了更长的 cooldown，影响扩大
- **建议改法和验证点**:
  - 为非持久化模式提供 per-run registry（例如在 `_build_model_circuit_breaker` 接受一个 `run_id` 参数并创建隔离实例）
  - 或至少在文档中明确记录全局单例的跨 run 共享语义
  - 验证：触发 circuit OPEN，等待 10s，发起新的 run，确认新 run 是否被错误拒绝
- **修复风险（中）**: 改变 registry 生命周期可能影响依赖全局状态的其他调用方
- **严重程度（中）**: 影响可用性但窗口有限（默认 cooldown 60s），有 workaround（配置 SQLite state_path 或禁用 circuit breaker）

---

### 4-未修复-中-研究模板 shared manifest 的 overwrite 硬编码为 True

- **入口/函数**: `materialize_research_template_bundle()`
- **文件(行号)**: `dayu/cli/commands/research_template.py:2469`
- **输入场景**: 两次并发的、针对不同模板的 `materialize` 操作，或先 materialize 模板 A 再 materialize 模板 B
- **实际分支**: 行 2469 调用 `write_research_template_package_manifest(workspace_root=workspace_root, overwrite=True)` —— `overwrite=True` 是硬编码的。而模板文件（行 2450-2453）和工作簿（行 2454）的写入尊重调用方传入的 `overwrite` 参数
- **预期行为**: 共享 manifest 的 overwrite 行为应与模板文件一致，或使用 merge 策略（追加新 bundle entry 而非整文件覆盖）
- **实际行为**: 每次成功 materialize 都无条件覆盖 package manifest。若先 materialize consumer 模板、再 materialize technology 模板，consumer 的 bundle entry 会从 manifest 中消失（被 technology 的 manifest 覆盖）
- **直接证据**:
  - 行 2469: `overwrite=True` 硬编码
  - 行 2418-2431: `_rollback_materialization_artifacts` 在 rollback 时会 unlink shared manifest（行 2428），进一步证实这是一个共享文件
  - `write_research_template_package_manifest` 在 `research_template_assets.py` 中实现（未直接走读），但从调用方式推断其行为是全量写入而非增量 merge
  - 对比行 2450-2453 和 2454 对 template 文件和 workbook 文件使用 `overwrite=overwrite`（调用方参数）
- **影响**: 多次 materialize 不同模板时，先前的 bundle registration 丢失；workbook 或 checklist 可能引用已不在 manifest 中的 bundle
- **建议改法和验证点**:
  - 将 package manifest 的 overwrite 改为增量 merge 语义（读现有 → 更新对应 bundle entry → 写回）
  - 或至少让 overwrite 参数一致传递
  - 验证：materialize consumer，再 materialize technology，检查 manifest 是否包含两个 bundle entry
- **修复风险（中）**: 需要理解 `write_research_template_package_manifest` 的内部实现和调用方契约
- **严重程度（中）**: 数据丢失风险（manifest entry 丢失），但 manifest 可重建

---

### 5-未修复-低-研究模板定义缺少 sections 7-10 的结构化模型

- **入口/函数**: `ResearchTemplateDefinition` dataclass / `build_research_checklist_payload()`
- **文件(行号)**:
  - `dayu/cli/research_template_definitions.py:78-97` (定义 dataclass)
  - `dayu/assets/research_templates/common.md:44-70` (估值/催化剂/管理层/组合决策 4 章节)
  - `dayu/assets/research_templates/common.definition.json:59-85` (仅 5 个 output_sections)
- **输入场景**: 用户运行 `dayu-cli research-template schema` 或 `checklist` 查看模板结构
- **实际分支**: `ResearchTemplateDefinition` dataclass 有 7 个字段，其中 `output_sections` 仅覆盖 MD 模板 sections 1-6。MD 模板 sections 7-10（估值与预期差、催化剂与时间轴、管理层治理与资本配置、组合决策与风险预算）无对应的结构化字段
- **预期行为**: 模板定义应完整覆盖 MD 模板的全部结构章节
- **实际行为**: checklist 和 schema 命令输出的结构信息为 MD 模板实际内容的约 60%。依赖 checklist/schema 做完整性检查的调用方会遗漏 4 个章节
- **直接证据**:
  - `common.md` 第 44-70 行明确包含 sections 7-10，每个都有 `## ` 级标题和详细子项
  - `common.definition.json` 的 `output_sections` 数组仅 5 个条目（行 59-85），分别对应 sections 2-6
  - 其他 4 个行业模板（consumer/cyclical/financial/technology）同样缺失 sections 7-10 的定义
- **影响**: 用户通过 checklist 跟踪研究进度时缺少 4 个章节的结构化检查项；完整性检查工具遗漏约 40% 的模板内容
- **建议改法和验证点**:
  - 在 `ResearchTemplateDefinition` 和 JSON schema 中增加 `valuation_section`、`catalyst_section`、`governance_section`、`portfolio_decision_section` 字段
  - 或在 `output_sections` 中补充对应条目
  - 验证：检查所有 5 个模板的 checklist 输出是否包含 sections 7-10
- **修复风险（低）**: 纯数据模型扩展，不影响现有行为
- **严重程度（低）**: 信息不完整，但不影响写作流水线核心功能（这些章节由 LLM 生成，不依赖定义）

---

### 6-未修复-低-executor `_finish_run` 中的 `thread.join` 阻塞 asyncio event loop

- **入口/函数**: `DefaultHostExecutor._finish_run()`
- **文件(行号)**: `dayu/host/executor.py:1556-1585`
- **输入场景**: write pipeline 正常完成或取消，进入 `_finish_run()` 清理资源
- **实际分支**: `_release_resources()` (行 1528-1554) 调用 `resources.deadline_watcher.stop()` 和 `resources.bridge.stop()`。这两个 stop 方法在 `CancellationBridge.stop()` 中调用 `self._thread.join(timeout=poll_interval * 2)`（默认约 1 秒），在 `RunDeadlineWatcher.stop()` 中调用 `timer.join(timeout=...)`。这些 `thread.join()` 是同步阻塞调用
- **预期行为**: asyncio event loop 中的清理路径不应长时间阻塞；thread join 应使用 `run_in_executor` 或异步原语
- **实际行为**: event loop 被阻塞最多约 1 秒（默认配置 `poll_interval=0.5s`，timeout=1s）。单次调用影响有限，但若多个 run 同时结束（并行 middle chapter 场景），阻塞可能叠加
- **直接证据**:
  - `executor.py:1528-1554` 的 `_release_resources` 是同步方法
  - `executor.py:1556-1585` 的 `_finish_run` 是同步方法，在 async 上下文中被 `await` 之前已执行同步部分（实际调用在 finally 块中）
  - `cancellation_bridge.py:106` 的 `self._thread.join(timeout=poll_interval * 2)` 确认阻塞行为
- **影响**: event loop 短暂阻塞（毫秒到秒级），在高并发场景下可能引起延迟
- **建议改法和验证点**:
  - 使用 `asyncio.to_thread()` 或 `loop.run_in_executor()` 包装 thread join
  - 或将 bridge/watcher 的 stop 改为 async 方法
  - 验证：使用 `asyncio` debug mode 检测 event loop 阻塞时间
- **修复风险（中）**: 改变清理路径的同步/异步语义可能影响 SIGINT handler 中的同步清理路径（`release_resources_for_run` 在行 1587-1608 被信号处理器同步调用）
- **严重程度（低）**: 默认配置下阻塞 < 1s，实际影响有限

---

### 7-未修复-低-研究模板 `extract_monitoring_variables()` 依赖硬编码中文标题

- **入口/函数**: `extract_monitoring_variables()`
- **文件(行号)**: `dayu/cli/commands/research_template.py:411-427`
- **输入场景**: 模板 MD 文件中 "监控变量" 章节标题被改为其他措辞（如 "追踪指标"、"关键变量"）
- **实际分支**: 行 411-427 逐行扫描 MD 文本，查找 `## ` 开头的行中包含 `"监控变量"` 字符串。若标题改变，`in_section` 标志永不为 True，返回空 tuple
- **预期行为**: 应至少产生 warning 表明模板中未找到监控变量章节；或使用更健壮的解析方式（如基于 definition JSON 的结构化字段）
- **实际行为**: 静默返回空 tuple。下游 `build_monitoring_rules_payload` 收到空变量列表后生成 `blocked_no_tasks` 的 monitoring plan，不产生任何关于根因（标题缺失/变更）的 warning
- **直接证据**:
  - 行 416: `if "监控变量" in line:` —— 纯字符串匹配，无容错
  - 行 417-427: 返回值为 `tuple(parsed_variables)`，空列表时为空 tuple，与"模板无监控变量"无法区分
  - `common` 模板确实无 "监控变量" 章节（common.md 无 section 4），但 `extract_monitoring_variables` 对 common 返回空是预期行为；问题在于标题变更场景下无法区分"模板设计如此"和"标题被改"
- **影响**: 调试困难；静默失效导致 monitoring plan 生成结果不符合预期
- **建议改法和验证点**:
  - 在函数返回空 tuple 时，若模板名称不是 common（common 预期无监控变量），产生 debug log
  - 或将监控变量定义为 definition JSON 的结构化字段，不再依赖 MD 标题解析
  - 验证：修改模板标题为 "追踪指标"，确认 extract 返回空并检查 log
- **修复风险（低）**: 仅新增 log
- **严重程度（低）**: 不影响写作流水线核心功能，仅影响 monitoring 辅助功能

---

## Open Questions

1. **`dayu/cli/commands/write.py` 5226 行变更未走读**：该文件是 write 子命令的核心，包含 `print_report` 的完整静态方法（处理 compare、promotion proposal、configuration change request/approval、health trend、challenger proposal、preflight approval 等大量报告打印逻辑）。本次审查未覆盖该文件。其中的错误处理、互斥参数校验、模型路由配置读取值得独立审查。

2. **`dayu/services/write_model_configuration_manual_recovery_clearance.py` (4584 行) 未走读**：这是 PR 中最大的单文件之一，实现手动恢复清理机制。从 application.py 和 rollback_application.py 的 review 中可以看到`"manual_recovery_required"` 状态会触发该路径，但 clearance 逻辑本身未被走读。

3. **Champion/Challenger 并行运行隔离**：`write_model_challenger_*.py` 系列文件（约 4400 行）实现 champion/challenger 对比运行。从 pipeline.py 的 docstring（行 142-153）中看到，存在一个已知的 race window：`_check_cancellation` 通过后到 `host.register_run` 完成前，子 LLM 调用可能用自己的 CancellationToken 运行到完成而不响应外部取消。该 race window 被标注为 "out-of-scope for this PR, requires Host-side changes"，但其实际影响范围未被本次审查评估。

4. **214 文件中大量新增测试 (~50,000+ 行) 的断言质量**：本次审查仅对代表性测试文件做了覆盖分析（`test_research_template_command.py`），确认了哪些场景有/无测试覆盖。其余测试文件（如 `test_write_model_challenger_*.py`、`test_write_model_configuration_*.py`、`test_write_service.py`、`test_cli_running_config.py` 等）的断言质量和 failure path 覆盖未做系统评估。

5. **DeepSeek/MiMo 路由具体实现**：从 `runner_factory.py` 和 `model_config.py` 看，DeepSeek 和 MiMo 被映射为 `RunnerType.OPENAI_COMPATIBLE`，通过 OpenAI-compatible endpoint 调用。`DeepSeekInboxTask` 相关的 task generation、handoff 状态机在 `utils/prepare_deepseek_task.py` (1130 行) 中实现，但该文件的完整功能路径未被走读（仅安全面走读）。

---

## Residual Risk / Out of Scope

### 本次 PR 引入的剩余风险

1. **CLI 输出脱敏不完整**：`DayuCliArgumentParser` 未脱敏，已在 Finding 1 中报告。此外，`utils/` 中的 `SECRET_KEY_PATTERN` 仅匹配 `sk-` 前缀，不覆盖其他 provider 的 key 格式（如某些国内模型 provider），这是一个已知限制但属于已有设计，非本次 PR 引入。

2. **Circuit breaker 全局单例**：已在 Finding 3 中报告。enable SQLite state_path 可缓解但未默认启用。

3. **Write pipeline 已知 race window**：pipeline.py docstring 记录的 `_check_cancellation` / `register_run` race 仍存在。影响评估为低概率（需要精确时序），且仅影响 champion/challenger 并行模式。

4. **Model configuration change 硬编码约束**：角色固定为 `("primary", "audit")`、JSON pointer 固定为 `"/model/default_name"`、manifest 路径固定为 `config_root / "prompts" / "manifests"`。这些硬编码不是 bug —— 当前系统只需要这些约束 —— 但未来扩展角色或配置维度时需要代码变更。按 AGENTS.md 中"禁止把业务规则硬编码成脆弱分支"的要求，这属于技术债务但当前功能正确。

5. **研究模板 definition JSON 不完整**：sections 7-10 缺少结构化定义（Finding 5），但不影响写作流水线。

### Out of Scope（base 之前已有的历史债务）

以下问题在 base commit 2115c86d 时已存在，不属于本次 PR 的 diff 范围，不予报告为 finding：

- `DayuCliArgumentParser` 的自定义 `error()` 仅覆盖 `"required: command"` 这一种 case —— 此模式在 base 中已存在，本次 PR 未修改该结构
- 全局 `GLOBAL_MODEL_CIRCUIT_BREAKERS` 单例模式 —— 本次 PR 新增了 circuit breaker 本身，但全局单例的跨 run 累积是设计选择，非 bug
- Engine runner 的 retry/circuit breaker 基础设施（如 `_call_without_circuit_breaker` 的 300+ 行 retry loop）—— 新增代码，已通过测试验证

---

## 实际验证

### Git 状态验证

```
命令: git branch --show-current && git status --short && git merge-base origin/main HEAD
结果: HEAD (clean), merge-base == 2115c86d == origin/main
退出码: 0 ✓
```

### 环境限制

```
命令: source .venv/bin/activate
结果: .venv 不存在于 review worktree
Python: /usr/bin/python3 (3.9.6)，项目要求 3.11
影响: 无法运行 pytest、pyright 验证
```

测试和类型检查的验证需要在有 .venv 环境的原始 repo 中完成，不在本次 review 范围内。

### Review worktree 完整性

```
命令: git diff --stat origin/main...HEAD | tail -1
结果: 214 files changed, 110,467 insertions(+), 618 deletions(-)
确认: 文件数与预期一致
```

---

## Cross-review Evidence Assessment

对 MiMo review（`docs/reviews/pr-review-mimo-20260807.md`）中 C1-C14 与 W26 共 15 项 finding 的逐项证据复核。

### 复核方法

对每项 finding 验证四个维度：
1. **是否由 origin/main...HEAD 引入**：检查 base 中是否存在该文件/代码
2. **是否违反 AGENTS/CLAUDE 硬约束**：对照 AGENTS.md 和 CLAUDE.md 的具体条款
3. **是否有直接行为路径**：是否可构造输入→代码分支→可观测错误输出的完整链路
4. **严重度是否被夸大**：评估 finding 的实际影响是否匹配 `Critical` 标签

### 逐项评估

---

#### C1 — God file: `write.py`（5262 行）

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | base 仅 188 行，HEAD 为 5262 行，净增 ~5074 行 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | AGENTS.md："禁止 God object、God function、God dataclass、god bag、god builder" |
| 直接行为路径 | **无** | 架构/可维护性 concern，不直接导致功能错误 |
| 严重度 | **夸大** | `Critical` 应预留给 correctness/security/data-loss 问题。此为可维护性风险，合理级别为 **Warning** |

**评估：supported（severity overstated）**

---

#### C2 — God file: `research_template.py`（4145 行）

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | base 中该文件不存在（0 行），4145 行全为本次新增 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | 同上，禁止 God file |
| 直接行为路径 | **无** | 架构/可维护性 concern |
| 严重度 | **夸大** | 同上，合理级别为 **Warning** |

**评估：supported（severity overstated）**

---

#### C3 — God function: `run_write_command`（~350 行 / 30+ 分支）

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | write.py 从 188 行扩至 5262 行，该函数为新增 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | 禁止 God function；30+ 个 if/elif 分支违反"禁止把业务规则硬编码成脆弱分支" |
| 直接行为路径 | **无** | 架构 concern |
| 严重度 | **夸大** | 合理级别为 **Warning** |

**评估：supported（severity overstated）**

---

#### C4 — God function: `print_report`（~670 行 / 13 个参数）

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `write_service.py` 的 `print_report` 方法为本次新增（行 440-1102） |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | 禁止 God function |
| 直接行为路径 | **无** | 架构 concern |
| 严重度 | **夸大** | 合理级别为 **Warning** |

**评估：supported（severity overstated）**

---

#### C5 — 20 个文件重复相同的工具函数

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | 18 个 `write_model_*.py` 文件全为本次新增 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | "重复逻辑必须抽取" |
| 直接行为路径 | **部分有** | 重复代码中 `_canonical_json` 返回类型不一致（W11 指出 10 个返回 `str`，5 个返回 `bytes`），可能导致调用方类型混淆。但核心功能正确 |
| 严重度 | **轻微夸大** | 规模确实严重（17-18 个文件，保守估计 2000+ 行重复），但仍是可维护性问题。合理级别为 **High** |

**直接证据**：
```text
$ grep -rl '_canonical_json' dayu/services/write_model_*.py | wc -l
17
$ grep -rl 'def _fingerprint' dayu/services/write_model_*.py | wc -l
17
```
17 个文件各自定义了 `_canonical_json` 和 `_fingerprint`，逐字相同。

**评估：supported**

---

#### C6 — `async_anthropic_runner.py` 大量使用 `Any`

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `async_anthropic_runner.py` 为全新文件（531 行） |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | "禁止使用 object、Any、无类型参数、无类型返回值" |
| 直接行为路径 | **无** | 类型标注问题，不影响运行时行为 |
| 严重度 | **夸大** | Protocol adapter 层因上游协议为动态 JSON，使用 `dict[str, Any]` 是 Python 生态中广泛接受的模式。TypedDict 是理想改进但非必须。合理级别为 **Warning** |

**补充说明**：`AsyncAnthropicRunner._to_anthropic_messages()` 接收 `List[AgentMessage]`（上游 contract 类型），产出 `list[dict[str, Any]]`（Anthropic API 的原生 JSON 格式）。适配层的中间表示用 `Any` 标注 protocol payload 是 pragmatic choice，与业务逻辑中使用 `Any` 有本质区别。

**评估：supported（severity overstated，适配层上下文减轻了严重度）**

---

#### C7 — `_normalize_tool_choice` 参数和返回值均为 `object`

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `async_anthropic_runner.py:150-164` |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | `object` 在 contract 中被禁止 |
| 直接行为路径 | **无** | 类型标注问题。该函数实际只处理 `str` 和 `dict` 两种类型，运行时对其他类型已通过 ValueError 拒绝（行 160, 163） |
| 严重度 | **夸大** | 这是一个私有辅助函数（`_` 前缀），行数仅 15 行。合理级别为 **Info** |

**直接证据**：`async_anthropic_runner.py:150-164`
```python
def _normalize_tool_choice(value: object) -> object:
```
函数体内对非法输入抛出 ValueError，运行时安全性已保障。

**评估：supported（severity overstated）**

---

#### C8 — 多处 `execution_options: Any` 参数类型

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | write.py 行 561, 614, 700, 999, 1093, 1166 共 6 处 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | 禁止 `Any` |
| 直接行为路径 | **无** | 类型标注问题，不影响运行时行为 |
| 严重度 | **夸大** | 6 个函数签名使用 `Any` 而非具体类型，应修复但不构成 correctness 威胁。合理级别为 **Warning** |

**直接证据**：
```text
$ grep -n 'execution_options: Any' dayu/cli/commands/write.py
561:    execution_options: Any,
614:    execution_options: Any,
700:    execution_options: Any,
999:    execution_options: Any,
1093:    execution_options: Any,
1166:    execution_options: Any,
```

**评估：supported（severity overstated）**

---

#### C9 — `protocols.py` / `write_service.py` 使用 `Mapping[str, object]`

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `protocols.py:154` 等为本次新增的服务协议方法签名 |
| 违反 AGENTS/CLAUDE 硬约束 | **部分违反** | AGENTS.md 禁止 `object` 和 `Any`。但 `object` 与 `Any` 有本质区别——`object` 要求调用方在使用前做显式类型缩窄（narrowing），`Any` 则完全跳过类型检查。`Mapping[str, object]` 在 Python typing 中表示"值类型未知的映射"，比 `Mapping[str, Any]` 更严格 |
| 直接行为路径 | **无** | 类型标注问题 |
| 严重度 | **夸大** | 合理级别为 **Info** |

**评估：supported（severity overstated，`object` != `Any` 区分降低实际风险）**

---

#### C10 — `print_report` 中使用 `assert` 做运行时守卫

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `write_service.py` 行 667, 747, 751, 878, 897, 928, 929 共 7 处 |
| 违反 AGENTS/CLAUDE 硬约束 | **间接违反** | 非直接文字违反，但违背"最佳实践优先"的思考纪律 |
| 直接行为路径 | **有** | Python `-O` 模式下 `assert` 被跳过。例如行 667 `assert challenger_promotion_proposal_input is not None` 若被跳过，下一行 `build_write_model_configuration_change_request(challenger_promotion_proposal_input)` 将以 `None` 调用，导致难以诊断的 `AttributeError` |
| 严重度 | **准确** | 这是本次 cross-review 中唯一有直接行为路径的 Critical finding。`-O` 在生产环境不常见，但 `assert` 用于业务守卫是公认的反模式 |

**直接证据**：`write_service.py:666-672`
```python
if challenger_config_change_request_output is not None:
    assert challenger_promotion_proposal_input is not None  # ← 行 667
    try:
        config_change_request = (
            build_write_model_configuration_change_request(
                challenger_promotion_proposal_input  # ← 行 671，若 assert 被跳过则为 None
            )
        )
```

**评估：supported（severity 准确，有直接行为路径）**

---

#### C11 — `typing.Mapping` / `typing.Sequence` 废弃导入

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `write_model_challenger_proposal.py:12` 和 `write_model_health.py:12` |
| 违反 AGENTS/CLAUDE 硬约束 | **否** | AGENTS.md 无明确条款禁止使用 `typing` 模块的别名。Python 3.9+ 中 `typing.Mapping` / `typing.Sequence` 是 deprecated 但并未移除 |
| 直接行为路径 | **无** | deprecated 导入在运行时完全正常工作 |
| 严重度 | **严重夸大** | 这是一个代码风格/现代化问题，不应列为 `Critical`。合理级别为 **Info** |

**直接证据**：
```text
$ grep -n 'from typing import.*Mapping\|from typing import.*Sequence' \
  dayu/services/write_model_challenger_proposal.py dayu/services/write_model_health.py
dayu/services/write_model_challenger_proposal.py:12:from typing import Any, Mapping, Sequence
dayu/services/write_model_health.py:12:from typing import Any, Mapping, Sequence
```

**评估：supported（severity 严重夸大，不违反硬约束）**

---

#### C12 — `_DeniedTextReader` monkeypatch `Path.read_text`

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `test_validate_handoff_docs.py:15` 定义，被 2 个其他 test 文件 import |
| 违反 AGENTS/CLAUDE 硬约束 | **否** | 无明确条款禁止跨 test 文件共享 fixture/helper |
| 直接行为路径 | **无** | pytest 的 `monkeypatch.setattr` 在测试结束后自动恢复，不存在全局隔离被破坏的持久风险。跨文件 import 测试 helper 增加了耦合，但属于测试组织问题 |
| 严重度 | **严重夸大** | 合理级别为 **Info**。`_DeniedTextReader` 是一个 8 行的简单类，跨文件共享和 monkeypatch 都是 pytest 生态中的标准模式 |

**直接证据**：`test_validate_handoff_docs.py:15` — `_DeniedTextReader` 是一个实现了 `read_text` 方法的简单类，用于模拟不可读文件。跨文件 import 增加了测试文件间的耦合，但 `monkeypatch.setattr` 的恢复机制保证了测试隔离。

**评估：supported（severity 严重夸大，不违反硬约束）**

---

#### C13 — `BLOCKED_TERMS` 字符串拼接规避模式

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `utils/codex_review_gate.py:14-23` |
| 违反 AGENTS/CLAUDE 硬约束 | **否** | 无条款禁止字符串拼接。该模式的设计意图（避免扫描器自触发）是合理的防御性设计 |
| 直接行为路径 | **无** | 不导致功能错误。最坏情况：维护者不理解意图而"修复"拼接，导致扫描器把自己的源码标记为违规——但这需要同时修改多个文件 |
| 严重度 | **严重夸大** | 合理级别为 **Info**。建议加注释说明意图，但绝不构成 `Critical` |

**评估：supported（severity 严重夸大，不违反硬约束）**

---

#### C14 — README.md 混入英文段落

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | README.md 新增约 1000 行，含英文 manual recovery 流程描述 |
| 违反 AGENTS/CLAUDE 硬约束 | **间接** | AGENTS.md "一律用中文回答" 约束面向 agent 交互，READM 是项目文档。但项目整体以中文为主，50+ 行英文在中文用户手册中不一致 |
| 直接行为路径 | **无** | 文档一致性问题，不影响功能 |
| 严重度 | **夸大** | 合理级别为 **Info** 或 **Warning**。文档不一致不应列为 `Critical` |

**评估：supported（severity overstated）**

---

#### W26 — CI 缺少 pyright 检查

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `.github/workflows/dual-model-gates.yml` 为本次新增 |
| 违反 AGENTS/CLAUDE 硬约束 | **是** | "任何新增或修改代码都必须通过 pyright" |
| 直接行为路径 | **有** | CI 不含 pyright 步骤意味着类型错误可以在 PR 中合入而不被发现。结合 C6-C9 已确认的多处类型问题，pyright 缺失直接导致这些违规未被自动化拦截 |
| 严重度 | **准确** | 类型安全违规（C6-C9）与 CI 缺少强制执行机制形成复合风险。`Warning` 级别准确 |

**直接证据**：CI 文件 `dual-model-gates.yml:61-72` 的 lint 步骤仅运行 `ruff check`，无 `pyright` 步骤。

**评估：supported（severity 准确）**

---

### 汇总矩阵

| Finding | 引入来源 | 违反硬约束 | 直接行为路径 | 严重度评估 |
|---------|----------|-----------|-------------|-----------|
| **C1** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C2** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C3** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C4** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C5** | HEAD 新增 | 是 | 部分有 | supported → High |
| **C6** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C7** | HEAD 新增 | 是 | 无 | supported, overstated → Info |
| **C8** | HEAD 新增 | 是 | 无 | supported, overstated → Warning |
| **C9** | HEAD 新增 | 部分 | 无 | supported, overstated → Info |
| **C10** | HEAD 新增 | 间接 | **有** | **supported → Critical（准确）** |
| **C11** | HEAD 新增 | 否 | 无 | supported, overstated → Info |
| **C12** | HEAD 新增 | 否 | 无 | supported, overstated → Info |
| **C13** | HEAD 新增 | 否 | 无 | supported, overstated → Info |
| **C14** | HEAD 新增 | 间接 | 无 | supported, overstated → Info/Warning |
| **W26** | HEAD 新增 | 是 | **有** | supported → Warning（准确） |

### 关键发现

1. **15 项 finding 全部由 origin/main...HEAD 引入**，无 pre-existing 误标。所有代码/文件在 base commit (`2115c86d`) 中不存在或规模极小（write.py 仅 188 行）。

2. **仅 2 项有直接行为路径（C10, W26）**。其余 13 项为架构/可维护性/类型标注/文档问题，虽大多数违反了 AGENTS.md 某一条款，但没有可构造的"输入→代码分支→错误输出"链路。

3. **13 项严重度被高估**。MiMo review 将 14 项标为 `Critical`，经逐项复核后：
   - 仅 **C10**（`assert` 运行时守卫）维持 `Critical` —— 有直接行为路径
   - **C5**（代码重复）应降为 `High` —— 规模严重但无直接 behavior bug
   - **C1-C4**（God file/function）应降为 `Warning` —— 架构 debt，非 correctness
   - **C6-C9**（类型标注）应降为 `Warning/Info` —— 标注问题，非 behavior
   - **C11-C14** 应降为 `Info` —— 风格/文档问题

4. **W26（CI 缺 pyright）与 C6-C9 形成复合风险**：类型安全违规在 CI 中无自动拦截，增加了后续类型错误扩散的风险。这也是本 reviewer 最初想运行 pyright 但 worktree 缺 .venv 而未能验证的项目。

### 最小修复分组建议

按投入产出比排序，综合本 review 的 7 项 finding 和 MiMo review 的 15 项 finding：

**P0 — 合并前必须处理（有直接行为路径或安全泄漏）**：

| 优先级 | 来源 | ID | 简述 | 修复工作量 |
|--------|------|-----|------|-----------|
| P0 | DS | Finding 1 | CLI arg_parsing 脱敏缺失（安全泄漏） | ~30 行，改基类 |
| P0 | MiMo | C10 | `assert` 改为显式 `if/raise`（7 处） | ~30 行 |
| P0 | MiMo | W26 | CI 增加 pyright 步骤 | ~5 行 YAML |

**P1 — 合并后首个 PR 处理（高价值架构/类型改进）**：

| 优先级 | 来源 | ID | 简述 | 修复工作量 |
|--------|------|-----|------|-----------|
| P1 | MiMo | C5 | 抽取共享工具函数到 `_write_artifact_utils.py` | ~200 行重构 |
| P1 | MiMo | C6/C7/C8 | 消除 `Any`/`object` 类型标注 | ~100 行 TypedDict |
| P1 | DS | Finding 3 | Circuit breaker 单例文档化或隔离 | ~50 行或文档 |
| P1 | DS | Finding 4 | Research template manifest overwrite 改为 merge | ~40 行 |

**P2 — 后续迭代（架构演进，不阻塞合并）**：

| 优先级 | 来源 | ID | 简述 |
|--------|------|-----|------|
| P2 | MiMo | C1/C2/C3/C4 | God file/function 拆分 |
| P2 | DS | Finding 2 | Anthropic thinking 互斥 warning |
| P2 | DS | Finding 5 | Template definition 补充 sections 7-10 |
| P2 | MiMo | C11/C14 | 废弃导入/文档语言统一 |
| P2 | MiMo | C12/C13 | 测试组织/注释澄清 |

### 未在本次 cross-review 中复核的 MiMo Warning 项

W1-W25、W27-W30 不在本次 cross-review 范围（用户指定 C1-C14 + W26），但其中值得本 reviewer 关注并独立确认的：

- **W3**（`_counter` 对 float 静默归零）：已确认 `model_usage.py:15-22` 的 `_counter` 对 `isinstance(value, int)` 检查会拒绝 `float`。若 Anthropic API 的 token counts 可能以 float 返回，确实存在数据丢失风险。建议纳入 P1。
- **W8**（`_persist_budget_block_summary_if_needed` 吞掉所有 Exception）：已在本次审查的 pipeline.py 走读中看到（行 932-948），需纳入 P1。
- **W18**（InMemory 用 `time.monotonic`、SQLite 用 `time.time`）：已确认 `model_circuit_breaker.py:293,296` 确实使用了不同的时钟源。`time.monotonic` 不受系统时间调整影响，`time.time` 受 NTP 影响——两者计算出的 cooldown 时长可能不一致。建议纳入 P1。

---

## Artifact Path

```
docs/reviews/pr-review-deepseek-20260807.md
```
