# PR Deep Review: origin/main..HEAD

- **日期**: 2026-08-07
- **范围**: origin/main..HEAD（214 个文件，~110k 行新增）
- **审查维度**: Engine 层、Services 层、CLI + Write Pipeline、Tests + 安全工具、Docs + Config
- **审查方式**: 5 个独立 agent 并行审查，结果合并去重

---

## 概览

| 维度 | 🔴 Critical | 🟡 Warning | 🔵 Info |
|------|-------------|------------|---------|
| Engine 层 | 3 | 12 | 5 |
| Services 层 | 5 | 8 | 5 |
| CLI + Write Pipeline | 5 | 8 | 7 |
| Tests + 安全工具 | 3 | 6 | 6 |
| Docs + Config | 3 | 6 | 6 |
| **合计（去重后）** | **14** | **30** | **22** |

---

## 🔴 Critical（14 项）

### C1. God file: `dayu/cli/commands/write.py`（5262 行）

- **文件**: `dayu/cli/commands/write.py` 全文
- **问题**: 单文件 5262 行，60+ 个函数，承载写作 CLI 的所有子命令分发逻辑。违反"禁止 God function / God class"约束。
- **修复建议**: 按功能域拆分为 `write_challenger.py`、`write_configuration.py`、`write_manual_recovery.py`、`write_research.py`。`run_write_command` 的 30+ 个 if/elif 分支改为 dispatch table。

### C2. God file: `dayu/cli/commands/research_template.py`（4145 行）

- **文件**: `dayu/cli/commands/research_template.py` 全文
- **问题**: 单文件 4145 行，100+ 个函数，涵盖模板列表/展示/复制/组合、monitoring rules/source map/execution plan/scheduler manifest、bundle descriptor/rebind/rollback、workbook/status/report、portfolio materialization 等完全不同的功能域。
- **修复建议**: 按子命令簇拆分为 `research_template_monitoring.py`、`research_template_bundle.py`、`research_template_portfolio.py` 等。

### C3. God function: `run_write_command`（~350 行 / 30+ 分支）

- **文件**: `dayu/cli/commands/write.py`，第 4602-4950+ 行
- **问题**: 30+ 个 `if bool(getattr(args, "xxx", False))` 分支组成的 God function，新增子命令必须在巨型函数中插入新分支，极易出错。
- **修复建议**: 抽取为 `_WRITE_SUBCOMMAND_DISPATCH: dict[str, Callable]` 映射表。

### C4. God function: `print_report`（~670 行 / 13 个参数）

- **文件**: `dayu/services/write_service.py`，第 440-1102 行
- **问题**: `WriteService.print_report` 方法体约 670 行，承担 7 个独立业务子流程。
- **修复建议**: 拆分为 `_print_run_comparison`、`_handle_promotion_proposal`、`_handle_config_change_request` 等独立函数。

### C5. 20 个文件重复相同的工具函数

- **文件**: `dayu/services/write_model_*.py`（20 个新增文件）
- **问题**: `_canonical_json`（20 次）、`_fingerprint`（20 次）、`_validated_fingerprint`（17 次）、`_mapping`（18 次）、`_required_text`（15 次）、`_exact_fields`（16 次）逐字复制。保守估计 2,000+ 行重复代码。违反"重复逻辑必须抽取"约束。
- **修复建议**: 抽取到 `dayu/services/_write_artifact_utils.py` 共享模块。

### C6. `async_anthropic_runner.py` 大量使用 `Any`

- **文件**: `dayu/engine/async_anthropic_runner.py`
- **问题**: `from typing import Any` 贯穿整个模块，`dict[str, Any]` 出现在 15+ 处函数签名中。违反"禁止使用 `Any`"硬约束。
- **修复建议**: 定义 `AnthropicNativeMessage`、`AnthropicContentBlock` 等 TypedDict 替代。

### C7. `_normalize_tool_choice` 参数和返回值均为 `object`

- **文件**: `dayu/engine/async_anthropic_runner.py`，第 150-164 行
- **问题**: `def _normalize_tool_choice(value: object) -> object` 输入输出均为 `object`，等同于 `Any`。
- **修复建议**: 使用 `Union[str, dict[str, str | dict[str, str]]]` 或定义 `ToolChoiceValue` 联合类型。

### C8. 多处 `execution_options: Any` 参数类型

- **文件**: `dayu/cli/commands/write.py`，第 561、614、700、999、1093、1166 行
- **问题**: 多个函数签名使用 `execution_options: Any`，内部通过 `getattr` 反复访问属性，完全丧失类型检查。
- **修复建议**: 改为 `ExecutionOptions` 类型。

### C9. `protocols.py` / `write_service.py` 使用 `Mapping[str, object]`

- **文件**: `dayu/services/protocols.py` 第 154 行, `dayu/services/write_service.py` 第 445、861 行
- **问题**: `model_catalog: Mapping[str, Mapping[str, object]]` 中 `object` 等价于 `Any`。
- **修复建议**: 定义 `ModelCatalogEntry` TypedDict 替代。

### C10. `print_report` 中使用 `assert` 做运行时守卫

- **文件**: `dayu/services/write_service.py`，第 667、747、751、878、897、928、929 行
- **问题**: `assert` 在 Python `-O` 模式下被跳过，生产环境不生效。
- **修复建议**: 用 `if ... is None: raise ...` 替代。

### C11. `typing.Mapping` / `typing.Sequence` 废弃导入

- **文件**: `dayu/services/write_model_challenger_proposal.py` 第 12 行, `dayu/services/write_model_health.py` 第 12 行
- **问题**: 使用已废弃的 `typing.Mapping` 和 `typing.Sequence`，同批其他文件已正确使用 `collections.abc`。
- **修复建议**: 改为 `from collections.abc import Mapping, Sequence`。

### C12. `_DeniedTextReader` monkeypatch `Path.read_text` 破坏全局隔离

- **文件**: `tests/test_codex_review_gate.py:155`, `tests/test_validate_handoff_docs.py:22`, `tests/test_dual_model_pipeline_check.py:202`
- **问题**: 通过 `monkeypatch.setattr(Path, "read_text", ...)` 替换全局 `Path.read_text`，且 `_DeniedTextReader` 跨模块 import 形成测试文件间硬耦合。
- **修复建议**: 移到 `tests/conftest.py` 作为共享 fixture，改用实例级 patch。

### C13. `BLOCKED_TERMS` 字符串拼接规避模式脆弱

- **文件**: `utils/codex_review_gate.py`，第 14-23 行
- **问题**: `"TO" + "DO"`、`"pa" + "ss"` 等拼接为避免扫描器自身被误判，但维护者可能不理解意图而"修复"。
- **修复建议**: 用配置文件存储或 base64 编码，并在模块顶部注释说明原因。

### C14. README.md 大量混入英文段落

- **文件**: `README.md`，约第 860-1080 行
- **问题**: 手动恢复配置（manual recovery）流程约 50+ 行纯英文混入中文用户手册。
- **修复建议**: 翻译为中文，与 README 其余部分保持一致。

---

## 🟡 Warning（30 项，按主题分组）

### 类型安全（W1-W5）

| ID | 文件 | 问题 |
|----|------|------|
| W1 | `async_anthropic_runner.py:235` | `__init__(**kwargs: Any)` 应显式列出参数 |
| W2 | `async_openai_runner.py` 新增 `_build_token_usage_summary` | `cache_creation_tokens` 字段名与 `ModelUsage.to_dict()` 的 `cache_creation_input_tokens` 不一致 |
| W3 | `model_usage.py:15-22` | `_counter` 对 `float` 值静默归零（如 `150.0` → `0`），Anthropic 可能返回 float |
| W4 | `research_template.py`、`research_workbook.py` | 71+22 处 `dict[str, object]` 中 `object` 等价于 `Any` |
| W5 | `executor.py:2159` | `metadata: dict[str, Any] \| None` 应定义 `ErrorEventMetadata` TypedDict |

### 错误处理（W6-W10）

| ID | 文件 | 问题 |
|----|------|------|
| W6 | `web_search_providers.py:351-365` | `getattr` 遍历异常链无限制，应改用显式类型判断 |
| W7 | `async_anthropic_runner.py:219-221` | 未知 `stop_reason` 静默透传，应记录 warning |
| W8 | `pipeline.py:932-948` | `_persist_budget_block_summary_if_needed` 捕获所有 `Exception` 静默吞掉，磁盘满等严重问题被掩盖 |
| W9 | `write_model_challenger_proposal.py:49` 等 | `_mapping` 静默版本（非 Mapping 返回 `{}`）与严格版本（抛 ValueError）混用，语义不一致 |
| W10 | `write_service.py` | 退出码（2/4/130）语义未文档化，同类错误返回不同码 |

### 代码重复与结构（W11-W16）

| ID | 文件 | 问题 |
|----|------|------|
| W11 | 20 个 `write_model_*.py` | `_canonical_json` 返回类型不一致：10 个返回 `str`，5 个返回 `bytes` |
| W12 | `write.py:643,729,1035,1113,1202` | `_snapshot_builder` 嵌套函数重复 5 次，结构完全相同 |
| W13 | `write_model_challenger_promotion.py:845-882` | 使用 `os.link` 而非 `os.replace`，与其他模块不一致且跨分区会失败 |
| W14 | `write.py` | `WriteCliConfig` 已有 20+ 字段，接近 God dataclass 边界 |
| W15 | `write_model_challenger_proposal.py:587` | `build_write_model_challenger_proposal` 内嵌套函数 `finish()` |
| W16 | `research_workbook.py:49` | `build_research_workbook_payload` 内嵌套函数 `append_current_section` |

### 并发与状态（W17-W20）

| ID | 文件 | 问题 |
|----|------|------|
| W17 | `model_circuit_breaker.py:90-118` | `_InMemoryCircuitStateStore._entries` 无大小限制，长期运行有内存泄漏风险 |
| W18 | `model_circuit_breaker.py:283-296` | InMemory 用 `time.monotonic`、SQLite 用 `time.time`，时钟基准不同 |
| W19 | `model_usage_ledger.py:636-671` | `build_summary()` 在锁内拷贝后锁外遍历，非完全一致快照 |
| W20 | `model_circuit_breaker.py:189-206` | `locked_entry` 的 context manager 未声明"entry 仅在 with 块内有效"契约 |

### 文档与配置（W21-W26）

| ID | 文件 | 问题 |
|----|------|------|
| W21 | `progress.md`（新增 4946 行） | 严重过度文档化，逐条变更日志不应放在仓库根目录 |
| W22 | 根目录 8 个新增交接文件 | `architecture.md`、`decisions.md`、`spec.md`、`task.md` 等应移入 `docs/handoff/` |
| W23 | `write_service.py` | `print_report` 混用中英文警告信息（`[警告]` vs `[warning]`） |
| W24 | `llm_models.json` | `claude-sonnet-4-6-thinking` 禁用工具调用（`supports_tool_calling: false`），功能退化 |
| W25 | `llm_models.json` | DeepSeek 写作温度从 1.3 降至 0.8，变更理由仅基于 live smoke 观察 |
| W26 | `.github/workflows/dual-model-gates.yml` | CI 缺少 pyright 检查，违反"必须通过 pyright"约束 |

### 测试（W27-W30）

| ID | 文件 | 问题 |
|----|------|------|
| W27 | `test_validate_handoff_docs.py`（6530 行）等 | 测试文件过大，单文件超 3000 行，应按职责拆分 |
| W28 | 3 个 test 文件 | `_FakeClock` 完全相同实现在 3 个文件中重复定义 |
| W29 | `test_storage_cross_process_recovery.py:37` | 跨进程测试超时硬编码 15s/30s，慢速 CI 可能假阳性 |
| W30 | `test_model_usage.py:65` | 测试语义不清——`True` 被接受还是被忽略？测试名说"ignores invalid"但行为不符 |

---

## 🔵 Info（22 项，精选）

### 优秀设计

| ID | 模块 | 亮点 |
|----|------|------|
| I1 | `model_usage_ledger.py`（978 行） | `Decimal` 精确成本计算、`Lock` 并发保护、admission + settlement 双阶段预算门禁。类型标注完整（无 Any），是本次变更设计质量最高的模块 |
| I2 | 安全脱敏架构 | `RedactingArgumentParser` 重写三个扩展点，JSON/plain text/argparse error 三条路径全覆盖 |
| I3 | Path traversal 防御 | `normalize_repository_path` → `is_unsafe_repository_path` → `is_path_within_repository_root` 三层校验 |
| I4 | Circuit breaker 状态机 | CLOSED → OPEN → HALF_OPEN → CLOSED 完整生命周期，generation 隔离、probe 竞争、half-open 超时 |
| I5 | 跨进程 crash recovery 测试 | `os._exit(7)` 模拟真实进程崩溃，验证 orphan batch 恢复、ticker 锁释放 |
| I6 | Challenger 审批链测试 | proposal → preflight approval → run approval → promotion → verification 全流程，含过期/指纹不匹配/重复审批边界 |

### 正确变更

| ID | 文件 | 说明 |
|----|------|------|
| I7 | `engine/README.md`、`config/llm_models.json` | Anthropic 原生支持已正确落地（runner_type、endpoint、headers） |
| I8 | `config/run.json`、`config/README.md`、`engine/README.md` | 模型熔断机制文档与配置一致 |
| I9 | `config/llm_models.json`、`config/README.md` | pricing 配置格式合理，CNY 计价 |
| I10 | `pyproject.toml` | research_templates 打包路径正确 |
| I11 | `_fs_blob_core.py:135` | `_normalize_entry_name` 路径安全改进 |
| I12 | `agent_builder.py:176-205` | Anthropic runner 分支，必需字段显式 None 检查 |

### 值得关注

| ID | 文件 | 说明 |
|----|------|------|
| I13 | `runner_factory.py:54` | `_build_openai_runner_running_config` 命名误导（Anthropic 路径也调用） |
| I14 | `model_config.py` | `ModelPricingConfig` 新增但未被使用 |
| I15 | `events.py:87-88` | `AppResult` 新增 `usage` 和 `error_details` 字段但未被填充 |
| I16 | `async_anthropic_runner.py:26-40` | `resolve_anthropic_endpoint_url` 未做 URL scheme 校验 |

---

## 修复优先级建议

### P0：合并前必须修复

1. **C14**：README.md 英文段落翻译为中文
2. **C5**：抽取共享工具函数到 `_write_artifact_utils.py`（消除 2,000+ 行重复）
3. **C6/C7/C8/C9**：类型安全——消除 `Any`、`object` 参数（涉及 `async_anthropic_runner.py`、`write.py`、`protocols.py`）
4. **C10**：`print_report` 中 `assert` 改为显式检查
5. **C11**：废弃的 `typing.Mapping` 导入修复
6. **W26**：CI 增加 pyright 检查

### P1：合并后尽快修复

1. **C1/C2/C3/C4**：God file / God function 拆分（技术债，不拆会持续恶化）
2. **W1-W5**：类型安全改进
3. **W6-W10**：错误处理一致性
4. **W11-W13**：代码重复与结构一致性
5. **W21/W22**：文档整理（根目录交接文件移入 `docs/handoff/`）

### P2：后续迭代

1. **W17-W20**：并发与状态管理细节
2. **W24/W25**：模型配置调整的文档补充
3. **I13-I16**：命名、未使用字段、URL 校验

---

## 总体评价

本次 PR 是一个大型功能变更（~110k 行），核心包括：

1. **Anthropic Messages API 原生适配**（`AsyncAnthropicRunner`）
2. **模型熔断器**（`model_circuit_breaker.py`，SQLite 持久化 + InMemory 双模式）
3. **模型配置变更/回滚/手动恢复的完整审批链**（20 个新增服务模块）
4. **研究模板 CLI 子系统**（模板定义、组合、portfolio materialization）
5. **写作流水线预算门禁**（`model_usage_ledger.py`，admission + settlement 双阶段）
6. **双模型 handoff 工具链**（secret 脱敏、path traversal 防御、handoff 文档验证）

**架构分层**基本正确，没有发现 UI→Service→Host→Agent 的反向依赖。**安全设计**（secret 脱敏、path traversal 防御、fail-closed 模式）质量较高，测试覆盖充分。

**最大风险**是代码重复（20 个文件共享相同的工具函数却各自复制）和 God file 问题（`write.py` 5262 行、`research_template.py` 4145 行）。这些技术债会随每次功能迭代加速累积，建议在合并后优先治理。

**类型安全**是编码硬约束层面的主要违反点——`async_anthropic_runner.py`、`write.py`、`protocols.py` 中的 `Any`/`object` 使用需要系统性清理。

---

## Cross-review Evidence Assessment

**对 DeepSeek 审查 F1-F7 的逐项证据复核。**

来源文件：`/Users/wsk/Documents/Codex/2026-08-06/tou/work/dayu-agent-pr-review-ds/docs/reviews/pr-review-deepseek-20260807.md`

复核方法：对每项 finding 核对四个维度：
1. 是否由 origin/main...HEAD 引入（vs pre-existing）
2. 实际代码路径能否复现问题
3. 设计是否有意为之
4. 严重度是否合理

---

### F1 — DayuCliArgumentParser 缺乏 CLI 输出脱敏

**DeepSeek 判定**：高，安全泄漏

**复核结论：✅ supported**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **部分** | `DayuCliArgumentParser.error()` 的 `"required: command"` 特殊处理和 `super().error(message)` 透传在 base 中已存在（`git show origin/main:dayu/cli/arg_parsing.py` 确认）。但 `RedactingArgumentParser`（`utils/validate_handoff_docs.py:1019-1072`）是本次 PR 新增的，且最近 commit `6e22cb5`、`b7dedc3` 明确修复了 parser 脱敏——但仅限 utils 层的 `RedactingArgumentParser`，未覆盖主 CLI 解析器。 |
| 实际代码路径可复现 | **是** | `DayuCliArgumentParser` 继承 `argparse.ArgumentParser`（非 `RedactingArgumentParser`）。当用户传入 `sk-ant-api03-...` 作为 positional arg 触发错误时，`super().error(message)` 将原始值打印到 stderr。`RedactingArgumentParser` 已有完整实现（`format_usage()`、`format_help()`、`error()` 三个覆盖方法均调用 `redact_secret_shapes()`），但主解析器未使用。 |
| 设计是否有意 | **否（遗漏）** | commit 标题 "redact cli parser errors" 暗示意图覆盖所有 parser，但实际只修了 utils 层。 |
| 严重度 | **合理** | 安全泄漏有直接复现路径。但需注意：base 中 `DayuCliArgumentParser.error()` 已有相同问题，本次 PR 只是未能利用新增的 `RedactingArgumentParser` 来修复它。严格说是 pre-existing 问题 + 本次 PR 的修复不完整。 |

**补充**：DeepSeek 指出的根因准确——`RedactingArgumentParser` 已存在但未被主解析器使用。修复方案（改基类）工作量极小（~1行），风险极低。

---

### F2 — Anthropic extended thinking 与 temperature 互斥未在构造期校验

**DeepSeek 判定**：中，静默行为偏差

**复核结论：✅ supported（但严重度偏高）**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `async_anthropic_runner.py` 为全新文件，`_build_request_payload` 中 `if thinking_enabled: payload.pop("temperature", None)` 在行 475-476 |
| 实际代码路径可复现 | **是** | 当 `thinking.budget_tokens` 为真时，temperature 被静默丢弃，无 warning/log |
| 设计是否有意 | **是** | Anthropic API 确实不允许 extended thinking + temperature 共存。静默 pop 是 pragmatic 防御——与其让 API 返回 400 错误，不如静默去掉 temperature。但缺少 warning 确实增加了 debug 成本。 |
| 严重度 | **偏高** | 功能正确（temperature 确实不应与 thinking 共存），仅 debug 体验差。合理级别为 **Low** 而非 Medium。建议加 warning log，但不阻塞合并。 |

---

### F3 — 全局 circuit breaker 单例跨 run/session 累积故障计数

**DeepSeek 判定**：中，跨 run 隔离不足

**复核结论：✅ supported（但设计是有意的）**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `GLOBAL_MODEL_CIRCUIT_BREAKERS = ModelCircuitBreakerRegistry()` 在 `model_circuit_breaker.py:523`，`_build_model_circuit_breaker` 在 `runner_factory.py:182-189` 未配置 state_path 时回退到单例 |
| 实际代码路径可复现 | **是** | 同进程内多个 run 共享同一 registry，前一个 run 的 circuit OPEN 会阻塞后续 run（默认 cooldown 60s） |
| 设计是否有意 | **是** | 全局单例是有意设计——CLI 场景下同一进程内的多个 run 共享模型健康状态是合理的（如果模型在 run A 失败，run B 也应该知道）。SQLite state_path 提供了持久化隔离选项。 |
| 严重度 | **合理** | 默认 cooldown 60s 窗口有限，且有 workaround（配置 state_path 或禁用 circuit breaker）。建议在文档中明确说明跨 run 共享语义。 |

---

### F4 — 研究模板 shared manifest 的 overwrite 硬编码为 True

**DeepSeek 判定**：中，数据丢失风险

**复核结论：✅ supported**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `research_template.py:2469` 的 `overwrite=True` 硬编码，而同函数内行 2450-2454 对 template/workbook 文件使用 `overwrite=overwrite`（调用方参数） |
| 实际代码路径可复现 | **是** | 先 `materialize consumer`、再 `materialize technology` 时，第二次写入会覆盖 manifest，consumer 的 bundle entry 丢失。`_rollback_materialization_artifacts` 在行 2428 会 unlink shared manifest，进一步证实这是共享文件。 |
| 设计是否有意 | **不确定** | 可能是遗漏（对比同函数内其他文件使用 `overwrite=overwrite`），也可能是有意为之（每次 materialize 重建完整 manifest）。需要查看 `write_research_template_package_manifest` 的实现确认是全量写入还是增量 merge。 |
| 严重度 | **合理** | 多次 materialize 不同模板确实会丢失先前的 bundle registration。manifest 可重建，但用户体验差。 |

---

### F5 — 研究模板定义缺少 sections 7-10 的结构化模型

**DeepSeek 判定**：低，信息不完整

**复核结论：✅ supported**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `common.definition.json` 和 `common.md` 均为本次新增。MD 模板有 sections 0-9（10 个 `## ` 级标题），但 `output_sections` 仅 5 个条目（对应 sections 2-6 的子集） |
| 实际代码路径可复现 | **是** | `common.definition.json` 的 `output_sections` 数组仅 5 个条目（核心结论、关键变量、证据链、反证条件、下一步监控），缺失估值、催化剂、管理层、组合决策 4 个章节。其他 4 个行业模板同样缺失。 |
| 设计是否有意 | **可能是有意** | sections 7-10 由 LLM 生成，不依赖 definition JSON 的结构化字段。`output_sections` 可能仅用于 checklist 跟踪，而非模板完整性约束。 |
| 严重度 | **合理** | 不影响写作流水线核心功能，仅影响 checklist/schema 命令的完整性展示。 |

---

### F6 — executor `_finish_run` 中的 `thread.join` 阻塞 asyncio event loop

**DeepSeek 判定**：低，event loop 短暂阻塞

**复核结论：⚠️ partially supported（事实描述有误）**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `_finish_run` 和 `_release_resources` 在本次 PR 新增 |
| 实际代码路径可复现 | **部分** | DeepSeek 声称 `resources.deadline_watcher.stop()` 和 `resources.bridge.stop()` 都调用 `thread.join()`。**经核对，仅 `bridge.stop()` 调用 `thread.join(timeout=1.0)`**（`cancellation_bridge.py:106`，默认 `poll_interval=0.5`）。`deadline_watcher.stop()` 仅调用 `timer.cancel()`（`executor.py:336`），不调用 `thread.join()`。`threading.Timer.cancel()` 只是设置标志位防止触发，不阻塞。 |
| 设计是否有意 | **是** | `_finish_run` 是同步方法，在 async `finally` 块中直接调用（非 `await`）。bridge 的 `thread.join(timeout=1.0)` 确实阻塞 event loop，但这是有意的同步清理路径——同方法 `release_resources_for_run` 被 SIGINT handler 同步调用，不能改为 async。 |
| 严重度 | **偏高** | 仅 `bridge.stop()` 有 `thread.join`，默认 timeout=1.0s。单次调用影响有限。DeepSeek 描述的"两个 stop 都调用 thread.join"不准确。合理级别维持 **Low**，但事实描述需修正。 |

**修正**：DeepSeek 原文说 `deadline_watcher.stop()` 也调用 `thread.join()`，实际只调用 `timer.cancel()`。阻塞来源仅为 `CancellationBridge.stop()`。

---

### F7 — 研究模板 `extract_monitoring_variables()` 依赖硬编码中文标题

**DeepSeek 判定**：低，调试困难

**复核结论：✅ supported（但实际影响极低）**

| 维度 | 结论 | 证据 |
|------|------|------|
| 由 origin/main...HEAD 引入 | **是** | `research_template.py:411-427` 为本次新增 |
| 实际代码路径可复现 | **是** | `if "监控变量" in stripped:` 纯字符串匹配。若标题改为"追踪指标"，`in_section` 永不为 True，返回空 tuple。 |
| 设计是否有意 | **是** | 模板内容本身是中文的，"监控变量"是模板定义的标准章节标题。硬编码匹配是 pragmatic choice——模板内容由项目控制，不会被外部修改。 |
| 严重度 | **偏低** | 模板内容由项目维护，标题变更需要同时修改 MD 文件和代码，属于同步修改场景。`common` 模板本身无"监控变量"章节，返回空是预期行为。实际风险极低。 |

---

### 汇总矩阵

| Finding | 判定 | 由 HEAD 引入 | 可复现 | 设计有意 | 严重度评估 |
|---------|------|-------------|--------|---------|-----------|
| **F1** | ✅ supported | 部分（pre-existing + 修复不完整） | 是 | 否（遗漏） | High — 合理 |
| **F2** | ✅ supported | 是 | 是 | 是 | Low — DS 判 Medium 偏高 |
| **F3** | ✅ supported | 是 | 是 | 是 | Medium — 合理 |
| **F4** | ✅ supported | 是 | 是 | 不确定 | Medium — 合理 |
| **F5** | ✅ supported | 是 | 是 | 可能是 | Low — 合理 |
| **F6** | ⚠️ partially supported | 是 | 部分（仅 bridge.stop 阻塞） | 是 | Low — 合理，但事实描述有误 |
| **F7** | ✅ supported | 是 | 是 | 是 | Low — DS 判 Low 合理，实际影响极低 |

**关键发现**：
1. **F1-F7 全部由 origin/main...HEAD 引入**（或为 pre-existing 问题的修复不完整），无 pre-existing 误标。
2. **F6 事实描述有误**：DeepSeek 声称 `deadline_watcher.stop()` 和 `bridge.stop()` 都调用 `thread.join()`，实际仅 `bridge.stop()` 调用。`deadline_watcher.stop()` 只调用 `timer.cancel()`，不阻塞。
3. **F2 严重度偏高**：静默 pop temperature 是 pragmatic 防御（Anthropic API 本身会拒绝 thinking+temperature），debug 体验差但功能正确，Medium 应降为 Low。
4. **F1 是最有价值的 finding**：`RedactingArgumentParser` 已存在但未被主 CLI 解析器使用，修复仅需改基类（~1行），安全收益高。

---

### 最小修复分组建议（综合 MiMo + DeepSeek 两份审查）

#### P0 — 合并前必须处理

| 来源 | ID | 简述 | 修复工作量 |
|------|-----|------|-----------|
| DS F1 | CLI 脱敏缺失 | `DayuCliArgumentParser` 改继承 `RedactingArgumentParser` | ~1 行 |
| MiMo C10 | `assert` 运行时守卫 | 7 处 `assert` 改为 `if ... is None: raise` | ~30 行 |
| MiMo W26 | CI 缺 pyright | `dual-model-gates.yml` 增加 pyright 步骤 | ~5 行 YAML |

#### P1 — 合并后首个 PR

| 来源 | ID | 简述 | 修复工作量 |
|------|-----|------|-----------|
| MiMo C5 | 工具函数重复 | 抽取 `_write_artifact_utils.py` | ~200 行重构 |
| MiMo C6/C7/C8 | 类型安全 | 消除 `Any`/`object`，定义 TypedDict | ~100 行 |
| DS F3 | Circuit breaker 单例 | 文档化跨 run 共享语义或提供 per-run 选项 | ~50 行 |
| DS F4 | Manifest overwrite | 改为增量 merge 或传递 `overwrite` 参数 | ~40 行 |
| DS F2 | thinking/temperature | 添加 warning log | ~5 行 |

#### P2 — 后续迭代

| 来源 | ID | 简述 |
|------|-----|------|
| MiMo C1/C2/C3/C4 | God file/function 拆分 |
| DS F5 | Template definition 补充 sections 7-10 |
| DS F6 | bridge.stop() thread.join 改为 async（注意 SIGINT 路径） |
| DS F7 | extract_monitoring_variables 增加 debug log |
| MiMo C11-C14 | 废弃导入、文档语言、测试组织 |
