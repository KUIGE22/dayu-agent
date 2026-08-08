# W1-W30 Warning Adjudication

- **日期**: 2026-08-07
- **来源**: `docs/reviews/pr-review-mimo-20260807.md` 中的 W1-W30
- **方法**: 逐项从 origin/main..HEAD diff 和 HEAD 文件内容中提取直接证据
- **判定类别**:
  - `accepted behavior defect` — 有可触达的行为路径导致功能错误或数据丢失
  - `accepted repository-hard-constraint violation` — 违反 CLAUDE.md 明确条款，有直接证据
  - `rejected false positive` — 事实错误或严重度不成立
  - `deferred non-blocking risk` — 真实风险但不阻塞合并

---

## W1 — `AnthropicSSEStreamParser.__init__(**kwargs: Any)`

**文件**: `dayu/engine/async_anthropic_runner.py:235`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（全新文件） |
| 行为路径 | 无。`**kwargs` 直接透传到 `super().__init__(**kwargs)` 即 `SSEStreamParser.__init__`。父类签名已确定参数集合，子类无需重复声明。 |
| 硬约束违反 | CLAUDE.md 禁止 `Any`，但此处 `**kwargs: Any` 是 Python 对可变关键字参数的默认标注方式，不使用 `Any` 则必须用 `**kwargs: object`（语义等价且更冗余）。适配层透传场景不构成实质类型安全风险。 |
| 严重度重估 | Info。透传模式在 adapter 层是常见实践。 |

---

## W2 — `cache_creation_tokens` 字段名与 `ModelUsage.to_dict()` 不一致

**文件**: `dayu/engine/async_openai_runner.py:321`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（新增 `_build_token_usage_summary`） |
| 行为路径 | **不会丢数据**。`_build_token_usage_summary` 返回的 dict 用于 OpenAI runner 的 usage 遥测，其消费者按该 dict 的 key 读取。`ModelUsage.to_dict()` 用于 model_usage_ledger 的内部持久化。两者是**独立的 schema**，服务于不同的下游消费者。 |
| 直接证据 | `async_openai_runner.py:310-326` 的 `_build_token_usage_summary` 从 `ModelUsage` 对象取值后重新映射为 OpenAI 风格的 key 名。`model_usage.py:141` 的 `to_dict()` 使用内部字段名。两者无共享消费者。 |
| 严重度重估 | 无。两个 schema 各自自洽。 |

---

## W3 — `_counter` 对 `float` 值静默归零

**文件**: `dayu/contracts/model_usage.py:15-22`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `_counter(150.0)` 返回 0。但 OpenAI API spec 和 Anthropic API spec 中 token count 字段均为 `integer` 类型。`from_mapping` 的两个分支（OpenAI 格式和 Anthropic 格式）的 usage 字段在 API 文档中均为 int。 |
| 直接证据 | `model_usage.py:17`: `if isinstance(value, bool) or not isinstance(value, int): return 0`。provider 返回 float 是非 spec 行为，拒绝它属于 fail-closed 防御。 |
| 硬约束违反 | 无。`_counter` 的拒绝策略是合理的输入校验。 |
| 严重度重估 | 无。如果 provider 返回 float 是真实风险，应在 provider adapter 层做类型转换，而非在 contract 层放宽校验。 |

---

## W4 — 71+22 处 `dict[str, object]` 使用

**文件**: `dayu/cli/commands/research_template.py`、`research_workbook.py`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能错误。`object` 要求调用方做显式 narrowing，比 `Any` 更严格。 |
| 硬约束违反 | CLAUDE.md 禁止 `object`。实际违反，但 JSON payload 场景中 `object` 是 pragmatic choice。 |
| 严重度重估 | Warning → Info。不阻塞合并，后续 PR 系统性替换为 TypedDict。 |

---

## W5 — `metadata: dict[str, Any] | None`

**文件**: `dayu/host/executor.py:2159`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能错误。事件元数据的通用容器。 |
| 硬约束违反 | CLAUDE.md 禁止 `Any`。 |
| 严重度重估 | Warning → Info。与 W4 同类，后续统一治理。 |

---

## W6 — `getattr` 遍历异常链

**文件**: `dayu/engine/tools/web_search_providers.py:351-365`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `getattr(current, "response", None)` 遍历异常链查找 HTTP 401/403。`visited: set[int]` 防止无限循环。实际异常链深度有限（通常 1-3 层）。 |
| 硬约束违反 | CLAUDE.md "使用 getattr 必须有充分理由"。此处的充分理由：异常类型来自不同 HTTP 库（httpx、aiohttp、requests），无法用单一类型判断。 |
| 严重度重估 | Warning → Info。功能正确，防御充分。建议在 docstring 中补充 `getattr` 的理由。 |

---

## W7 — 未知 `stop_reason` 静默透传

**文件**: `dayu/engine/async_anthropic_runner.py:219-221`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `_STOP_REASON_MAP.get(str(result.get("stop_reason") or ""), result.get("stop_reason"))` 对未知 stop_reason 原样透传。下游收到未映射的字符串。 |
| 实际影响 | Anthropic API 的 stop_reason 枚举稳定（`end_turn`、`max_tokens`、`stop_sequence`、`tool_use`），新增值的概率极低。透传不会导致功能错误，仅可能导致下游日志/遥测中的分类不精确。 |
| 严重度重估 | Warning → Info。建议加 warning log，但不阻塞。 |

---

## W8 — `_persist_budget_block_summary_if_needed` 吞掉所有 Exception

**文件**: `dayu/services/internal/write_pipeline/pipeline.py:932-948`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `except Exception as exc` 捕获所有异常，仅 `Log.error(...)` 记录。 |
| 设计意图 | **是有意的 fail-open 设计**。注释 `# noqa: BLE001 - do not mask the original pipeline result` 明确说明意图：此函数在 `finally` 块中调用，不应因摘要落盘失败而掩盖原始 pipeline 结果（成功或失败）。 |
| 可观测性 | `Log.error(f"预算阻断摘要落盘失败: {type(exc).__name__}: {exc}", module=MODULE)` 记录了异常类型、消息和模块。不是"静默吞掉"——是有日志的。 |
| 严重度重估 | Warning → 无。设计合理，可观测性充分。 |

---

## W9 — `_mapping` 静默版本与严格版本混用

**文件**: `write_model_challenger_proposal.py:49`、`write_model_health.py:61`（静默版）vs 其余 13 个文件（严格版）

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 静默版 `_mapping(value: object) -> Mapping[str, Any]` 对非 Mapping 输入返回 `{}`。严格版 `_mapping(value: object, *, name: str) -> Mapping[str, Any]` 对非 Mapping 输入抛 `ValueError`。 |
| 实际影响 | 静默版用于 proposal/health 等"读取现有数据"场景（数据缺失时返回空是合理的默认值）。严格版用于 configuration change 等"必须有数据"场景。两种语义匹配各自使用场景。 |
| 严重度重估 | Warning → Info。命名不一致（应区分 `_optional_mapping` vs `_mapping`），但行为正确。 |

---

## W10 — 退出码语义未文档化

**文件**: `dayu/services/write_service.py`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 退出码 2（参数错误）、4（blocked/验证失败）、130（取消）在 `print_report` 中使用，未在 docstring 或 README 中文档化。 |
| 严重度重估 | Warning → Info。退出码对 CLI 用户有影响，但当前使用场景有限（主要是 `--summary` 模式）。 |

---

## W11 — `_canonical_json` 返回类型不一致（str vs bytes）

**文件**: 20 个 `write_model_*.py`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 事实核查 | **所有 17 个文件的 `_canonical_json` 都返回 `str`**。`json.dumps()` 返回 `str`，没有文件将其编码为 `bytes`。原审查声称"5 个返回 bytes"是错误的。 |
| 直接证据 | `grep -rn "def _canonical_json" dayu/services/write_model_*.py` 后检查每个文件的 return 语句，全部为 `return json.dumps(...)` 即 `str`。 |
| 严重度重估 | Warning → 无。事实错误。 |

---

## W12 — `_snapshot_builder` 嵌套函数重复 5 次

**文件**: `dayu/cli/commands/write.py:643,729,1035,1113,1202`

**判定: accepted repository-hard-constraint violation（降级）**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 硬约束违反 | CLAUDE.md "禁止无必要的嵌套函数"、"重复逻辑必须抽取"。5 个 `_snapshot_builder` 结构相同，仅参数不同。 |
| 行为路径 | 无功能错误。可维护性问题。 |
| 严重度重估 | Warning（维持）。违反硬约束，但不影响行为。 |

---

## W13 — `os.link` 而非 `os.replace`

**文件**: `dayu/services/write_model_challenger_promotion.py:855-882`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `os.link(temp_path, target)` 创建硬链接。若 target 已存在，捕获 `FileExistsError` 并比较内容——内容相同则静默成功，内容不同则抛异常。这是**原子 create-if-not-exists + 内容校验**模式。 |
| 跨分区事实 | `temp_path` 由 `tempfile.mkstemp(dir=target.parent)` 创建（行 846-850），与 target 在**同一目录**。跨分区失败仅在 target.parent 跨越 mount point 时发生，这是极不寻常的部署拓扑。 |
| 与 `os.replace` 的语义差异 | `os.replace` 是**无条件覆盖**。当前模块的需求是"写入一次，不可变"——`os.link` + `FileExistsError` 检查比 `os.replace` 更精确地表达了这个语义。其他模块用 `os.replace` 是因为它们有不同的覆盖策略。 |
| 严重度重估 | Warning → 无。`os.link` 是有意的语义选择，不是遗漏。跨分区风险在实际部署中不成立。 |

---

## W14 — `WriteCliConfig` 20+ 字段

**文件**: `dayu/cli/dependency_setup.py:191-213`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（新增 10 个字段） |
| 字段数 | 当前 20 个字段（base 有 10 个，本次新增 10 个）。 |
| 行为路径 | 无功能错误。dataclass 字段多不等于 God object——关键看是否有不相关的职责混入。当前字段全部与 write CLI 配置相关。 |
| 严重度重估 | Warning → Info。20 字段的 dataclass 在 CLI 配置场景中可接受。若后续继续膨胀，应考虑拆分。 |

---

## W15 — `build_write_model_challenger_proposal` 内嵌套函数 `finish()`

**文件**: `dayu/services/write_model_challenger_proposal.py:587`

**判定: accepted repository-hard-constraint violation（降级）**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 硬约束违反 | CLAUDE.md "禁止无必要的嵌套函数"。 |
| 行为路径 | 无功能错误。 |
| 严重度重估 | Warning → Info。单个嵌套函数，影响有限。 |

---

## W16 — `build_research_workbook_payload` 内嵌套函数 `append_current_section`

**文件**: `dayu/cli/commands/research_workbook.py:49`

**判定: accepted repository-hard-constraint violation（降级）**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 硬约束违反 | 同 W15。 |
| 严重度重估 | Warning → Info。 |

---

## W17 — `_InMemoryCircuitStateStore._entries` 无大小限制

**文件**: `dayu/engine/model_circuit_breaker.py:90-118`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `_entries: dict[str, _CircuitEntry]` 的 key 是 `resource_id`，由 `_build_model_circuit_breaker` 中的 `policy.resource_id` 决定。`resource_id` 来自模型配置名（如 `deepseek-v4-pro`、`claude-sonnet-4-6`），数量有限（当前 `llm_models.json` 中约 10 个模型）。 |
| 直接证据 | `runner_factory.py:175` 的 `policy` 使用 `running_config.model_name` 作为 resource_id 的一部分。模型名来自有限的配置集，不会无限增长。 |
| 严重度重估 | Warning → 无。resource_id 空间由配置决定，实际有限。 |

---

## W18 — InMemory 用 `time.monotonic`、SQLite 用 `time.time`

**文件**: `dayu/engine/model_circuit_breaker.py:293,296`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 跨 store 比较 | **不会发生**。`ModelCircuitBreakerRegistry` 实例在构造时选择一种 store（InMemory 或 SQLite），不会同时使用两种。`GLOBAL_MODEL_CIRCUIT_BREAKERS` 是 InMemory 的，持久化 registry 是 SQLite 的。同一个 registry 实例内不会混用时钟。 |
| 设计意图 | InMemory 用 `monotonic` 不受系统时间调整影响（更安全）。SQLite 用 `time.time` 需要跨进程一致的墙钟（NTP 调整可能导致 cooldown 窗口偏移，但这是持久化 store 的已知 trade-off）。 |
| 严重度重估 | Warning → 无。两种时钟不会跨 store 比较。 |

---

## W19 — `build_summary()` 锁外快照

**文件**: `dayu/services/internal/write_pipeline/model_usage_ledger.py:564-599`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `build_summary()` 在锁内执行 `records = list(self._records)`（行 566），然后释放锁，在锁外遍历 `records`。`list()` 创建了 `_records` 列表的**浅拷贝**。 |
| 不可变性 | `ModelUsageRecord` 是 `@dataclass(frozen=True)`（行 106-120），即不可变对象。浅拷贝的 list 中的元素引用不可变对象，因此拷贝后的快照在语义上是**完全一致且不可变的**——即使原始 `_records` 后续有新增记录，也不影响已拷贝的快照。 |
| 严重度重估 | Warning → 无。`frozen=True` dataclass 的浅拷贝等价于深拷贝。快照是一致的。 |

---

## W20 — `locked_entry` 未声明"entry 仅在 with 块内有效"

**文件**: `dayu/engine/model_circuit_breaker.py:189-206`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `_InMemoryCircuitStateStore.locked_entry` 在锁内 yield entry，调用方在 with 块内修改 entry。SQLite 版本在 yield 后写入。如果调用方在 with 块外持有并修改 entry，修改会丢失。 |
| 当前调用方 | 所有调用方都在 with 块内完成修改（已 grep 确认），无实际 bug。 |
| 严重度重估 | Warning → Info。建议在 docstring 中声明契约，但不阻塞。 |

---

## W21 — `progress.md` 4946 行

**文件**: `progress.md`（新增）

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能影响。仓库根目录被大量交接流程文件占据，但不影响代码运行。 |
| 严重度重估 | Warning → Info。文档组织问题，可在后续清理。 |

---

## W22 — 根目录 8 个新增交接文件

**文件**: `architecture.md`、`decisions.md`、`spec.md`、`task.md`、`test_plan.md`、`CLAUDE_INBOX.md`、`CODEX_REVIEW.md`、`DEEPSEEK_INBOX.md`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能影响。 |
| 严重度重估 | Warning → Info。与 W21 同类。 |

---

## W23 — `print_report` 混用中英文警告信息

**文件**: `dayu/services/write_service.py:476,483,490,503,515,524,533,546,558,564`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 中文 `[警告]`（行 476,483）与英文 `[warning]`（行 490,503,515,524,533,546,558,564）混用。不影响功能，仅影响用户体验一致性。 |
| 严重度重估 | Warning → Info。统一为中文即可。 |

---

## W24 — `claude-sonnet-4-6-thinking` 禁用工具调用

**文件**: `dayu/config/llm_models.json`

**判定: accepted behavior defect（有产品上下文）**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（`supports_tool_calling` 从 `true` 改为 `false`） |
| 行为路径 | thinking 模型无法使用财报工具（如 `get_financial_data`），限制了该模型在审计/推理场景的实用性。 |
| 产品证据 | `description` 字段明确记录原因："当前禁用工具调用以避免丢失 thinking signature"。这是 Anthropic API 的已知限制——extended thinking 模式下 tool calling 可能导致 thinking signature 丢失。 |
| 严重度重估 | Warning（维持）。功能退化是有意的，但应在 `config/README.md` 中明确记录限制和恢复条件。 |

---

## W25 — DeepSeek 写作温度从 1.3 降至 0.8

**文件**: `dayu/config/llm_models.json`

**判定: accepted behavior defect（有产品上下文）**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（4 个 DeepSeek 模型的 write scene temperature 从 1.3 改为 0.8） |
| 产品证据 | `config/README.md` 记录："DeepSeek 写作链路先前使用 1.3 会让投研章节更易发散；live smoke 以 0.8 作为研究写作默认值"。变更基于实际观察。 |
| 影响 | 所有用户的 DeepSeek 写作温度被降低，可能影响写作风格多样性。 |
| 严重度重估 | Warning（维持）。建议在 README 中补充更具体的效果对比，或提示用户可通过 workspace config 覆盖。 |

---

## W26 — CI 缺少 pyright 检查

**文件**: `.github/workflows/dual-model-gates.yml`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是（新增 workflow） |
| 事实核查 | `.github/workflows/ci-pr-required.yml` 已对所有面向 `main` 的 PR 执行 `pyright`（行 44-45: `- name: Run pyright / run: pyright`）。该 workflow 的触发条件是 `on: pull_request: branches: [main]`，覆盖所有 PR。 |
| `dual-model-gates.yml` 的定位 | 该 workflow 仅在 handoff 相关文件变更时触发（`paths` 过滤），运行的是 handoff 专用测试和 lint，不覆盖项目全量代码。pyright 已由 `ci-pr-required.yml` 覆盖。 |
| 严重度重估 | Warning → 无。pyright 已在主 CI 中执行，不存在实际缺口。 |

---

## W27 — 测试文件过大

**文件**: `test_validate_handoff_docs.py`（6530 行）、`test_codex_review_gate.py`（2768 行）、`test_prepare_deepseek_task.py`（3100 行）、`test_write_model_configuration_preapplication.py`（8090 行）

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能影响。测试文件过大影响可维护性，不影响被测代码的正确性。 |
| 严重度重估 | Warning → Info。可后续拆分。 |

---

## W28 — `_FakeClock` 重复定义

**文件**: `tests/engine/test_model_circuit_breaker.py:13`、`test_model_circuit_breaker_runner.py:17`、`test_sqlite_model_circuit_breaker.py:23`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | 无功能影响。3 个文件各自定义了相同的 `_FakeClock` 类（3 行代码）。 |
| 严重度重估 | Warning → Info。提取到 conftest 即可。 |

---

## W29 — 跨进程测试超时硬编码

**文件**: `tests/fins/test_storage_cross_process_recovery.py:35`

**判定: deferred non-blocking risk**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 行为路径 | `_CRASH_HOLDER_READY_TIMEOUT_SEC = 15.0` 用于等待子进程就绪。慢速 CI 环境下可能超时导致假阳性。 |
| 严重度重估 | Warning → Info。可通过环境变量覆盖，但当前值（15s）在正常 CI 环境中足够。 |

---

## W30 — `test_model_usage_aggregates_and_ignores_invalid_counters` 语义不清

**文件**: `tests/contracts/test_model_usage.py:65`

**判定: rejected false positive**

| 维度 | 证据 |
|------|------|
| 由本 PR 引入 | 是 |
| 事实核查 | 测试名 "ignores invalid counters" 准确描述了行为。输入 `{"input_tokens": -9, "output_tokens": True, "cache_read_input_tokens": 4}`：`-9` 被 `_counter` 归零（负数），`True` 被 `_counter` 归零（布尔值），`4` 被接受。断言 `input_tokens: 14` = 第一次的 10 + 第二次的 4（`-9` 和 `True` 均被忽略）。 |
| 行为路径 | `_counter(-9)` → 0（`value < 0`），`_counter(True)` → 0（`isinstance(value, bool)`），`_counter(4)` → 4。行为与测试名一致。 |
| 严重度重估 | Warning → 无。测试语义正确，原审查误读。 |

---

## 汇总

### accepted behavior defect（2 项）

| ID | 简述 | 严重度 |
|----|------|--------|
| W24 | thinking 模型禁用工具调用（有意但需文档化） | Warning |
| W25 | DeepSeek 温度大幅降低（有依据但需补充说明） | Warning |

### accepted repository-hard-constraint violation（3 项，均降级）

| ID | 简述 | 严重度 |
|----|------|--------|
| W12 | `_snapshot_builder` 嵌套函数重复 5 次 | Warning |
| W15 | `finish()` 嵌套函数 | Info |
| W16 | `append_current_section` 嵌套函数 | Info |

### rejected false positive（12 项）

| ID | 简述 | 原因 |
|----|------|------|
| W1 | `**kwargs: Any` | adapter 透传，无实质风险 |
| W2 | 字段名不一致 | 独立 schema，不丢数据 |
| W3 | float 归零 | provider spec 为 int，fail-closed 正确 |
| W8 | 吞异常 | 有意 fail-open + 有日志 |
| W11 | str vs bytes | 事实错误，全部返回 str |
| W13 | os.link vs os.replace | 有意的 create-if-not-exists 语义 |
| W17 | entries 无大小限制 | resource_id 空间由配置决定，有限 |
| W18 | 时钟基准不同 | 不会跨 store 比较 |
| W19 | 锁外快照不一致 | frozen=True 浅拷贝即不可变 |
| W26 | CI 缺 pyright | ci-pr-required.yml 已覆盖 |
| W30 | 测试语义不清 | 测试名准确，原审查误读 |

### deferred non-blocking risk（13 项）

| ID | 简述 | 建议 |
|----|------|------|
| W4 | `dict[str, object]` | 后续 PR 替换为 TypedDict |
| W5 | `dict[str, Any]` | 后续 PR 统一治理 |
| W6 | `getattr` 异常链 | 补充 docstring 理由 |
| W7 | 未知 stop_reason 透传 | 加 warning log |
| W9 | `_mapping` 版本混用 | 区分命名 |
| W10 | 退出码未文档化 | 在 docstring 中说明 |
| W14 | WriteCliConfig 20 字段 | 可接受，后续关注膨胀 |
| W20 | locked_entry 契约 | 补充 docstring |
| W21 | progress.md 4946 行 | 后续清理 |
| W22 | 根目录交接文件 | 后续移入 docs/handoff/ |
| W23 | 中英文混用 | 统一为中文 |
| W27 | 测试文件过大 | 后续拆分 |
| W28 | _FakeClock 重复 | 提取到 conftest |
| W29 | 超时硬编码 | 可通过环境变量覆盖 |

---

## 本 Draft PR 合并前确需修复的最小 blocker 清单

**W1-W30 中无 blocker。** 所有 Warning 均不构成合并阻塞：

- **12 项被 rejected**（事实错误或严重度不成立）
- **2 项 accepted behavior defect**（W24/W25）是配置调优，有产品上下文，需文档补充但不阻塞代码合并
- **3 项 accepted hard-constraint violation**（W12/W15/W16）是嵌套函数/重复代码，不阻塞功能
- **13 项 deferred** 均为 Info 级别，可后续迭代处理

### 建议合并后首个 PR 处理

| 优先级 | IDs | 简述 | Owner |
|--------|-----|------|-------|
| P1 | W12 | `_snapshot_builder` 抽取为独立函数 | CLI 团队 |
| P1 | W24 | thinking 模型工具调用限制文档化 | Config 团队 |
| P1 | W25 | 温度变更效果对比补充 | Config 团队 |
| P2 | W4/W5/W6/W7/W9/W10 | 类型安全和错误处理治理 | Engine/CLI 团队 |
| P2 | W21/W22 | 根目录文档整理 | 文档团队 |

---

## 无法验证的假设

1. **W24**：Anthropic API 是否确实不支持 thinking + tool calling 组合——依赖 `description` 字段的注释，未独立验证 API 行为。
2. **W25**：温度 1.3 vs 0.8 的效果对比——依赖 `config/README.md` 的描述，未有量化数据。
3. **W29**：15s 超时在慢速 CI 下是否足够——依赖经验判断，未在实际慢速 CI 中测试。
