# CLI Write 架构重构 Aggregate Deep Code Review

- **日期**：2026-08-08
- **分支**：`codex/dual-model-research-mvp`
- **当前 HEAD**：`4d2535d`
- **Baseline**：`origin/main=2115c86`
- **规模**：93 commits / 445 changed files / +168,836 −697 lines
- **审查来源**：
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.7 ACCEPTED）
  - `docs/reviews/aggregate-cli-write-architecture-validation-20260808-codex.md`（READY FOR AGGREGATE DEEPREVIEW）
  - 根 `AGENTS.md` 及相关子目录 `AGENTS.md`
- **审查者**：DeepSeek 独立 aggregate reviewer
- **审查方式**：五路并行深度审查（Write CLI / Engine-Async-Failover / Security-Redaction-Storage / Dual-Model-Gates-CI-Utils / Research-Template + Ruff Residual216），每路 adversarial pass

---

## 1. Executive Summary

**Verdict**: PASS — 零 HIGH severity findings，5 Medium，11 Low。

本分支是 CLI Write 架构的大规模重构，严格遵循 accepted v5.7 plan。架构决策（Protocol dispatch、Phase A/B 分治、单向模块 DAG、ownership migration、Config application/rollback snapshot 模式）实现正确。Ruff positive216 全为样式债务，零运行风险。安全维度净正向提升（CLI 脱敏、路径遍历加固、跨进程崩溃恢复）。

**Open Findings**:

| Severity | Count | IDs |
|----------|-------|-----|
| High | 0 | — |
| Medium | 5 | WRITE-01, WRITE-04, ENG-01, RT-01, RT-02 |
| Low | 11 | WRITE-02, WRITE-05, ENG-02~ENG-10, SEC-01, SEC-02, SEC-05, RT-03~RT-06, GATE-01~GATE-11 |

Medium findings 均不阻塞合并：WRITE-01/RT-01 是功能行为偏差（label/exit code），WRITE-04 是防御性债务（shallow copy），ENG-01 仅在极端并发碰撞触发，RT-02 是代码重复产生的维护风险。

---

## 2. Finding Summary

| ID | Severity | Classification | Area | Summary |
|----|----------|---------------|------|---------|
| WRITE-01 | **Medium** | new-defect | Write CLI | Manual recovery application 的 `run_label` 默认为 `"configuration-application"`，审计日志无法区分配置应用与人工恢复 |
| WRITE-02 | Low | pre-existing | Write CLI | `assert rollback_approval_output is not None` 在 `-O` 下被剥离，下游收到 None 无清晰错误 |
| WRITE-04 | **Medium** | new-defect | Write CLI | `_build_auto_bootstrap_args` 使用浅拷贝 `dict(vars(args))`，与原始 args 共享可变引用 |
| WRITE-05 | Low | pre-existing | Write CLI | Rollback snapshot builder 未传 `run_label`，日志标签错误 |
| ENG-01 | **Medium** | new-defect | Engine | 熔断器 SQLite 写锁超时（5s busy_timeout）后 open 异常未捕获，高并发下可导致 Runner crash |
| ENG-02 | Low | intentional | Engine | HALF_OPEN probe abandoned 等价 failure，频繁 Ctrl+C 可能导致 Provider 被长期熔断 |
| ENG-03 | Low | new-defect | Engine | aiohttp ClientSession 无强制关闭保证，长期运行进程可能连接泄漏 |
| ENG-04 | Low | pre-existing | Engine | `_finish_run_async` 中 `release_task.exception()` 在 event loop 被 `stop()` 时可能抛出 CancelledError |
| ENG-05 | Low | new-defect | Engine | `_anthropic_tool_initial_inputs` dict 无界增长（畸形 SSE 流风险） |
| ENG-06 | Low | new-defect | Engine | `_AUTH_FAILED_PROVIDER_KEY_FINGERPRINTS` 全局 set 永不驱逐 |
| ENG-08 | Low | new-defect | Engine | `_call_without_circuit_breaker` retry 循环中 session 替换存在理论竞态 |
| ENG-09 | Low | pre-existing | Engine | 连续同 role message 合并可能产生超大 content block |
| ENG-10 | Low | new-defect | Engine | `model_usage._counter` 对负数静默归零 |
| SEC-01 | Low | pre-existing | Security | `_normalize_entry_name` 未拒绝 null byte 字符 |
| SEC-02 | Low | new-defect | Security | `is_subpath` 纯词法比较，未强制 resolve，API 设计未在签名层面约束 |
| SEC-05 | Low | pre-existing | Security | `_persist_sources_json` 和最终报告未使用原子写入 |
| RT-01 | **Medium** | new-defect | Research Template | `_run_validate_source_map` 无条件返回 0，与其他 validate runner 行为不一致 |
| RT-02 | **Medium** | new-defect | Research Template | `_load_json_object` 三处重复实现，错误处理发散 |
| RT-03 | Low | new-defect | Research Template | `_TEMPLATE_DIR_NAME` / `_TEMPLATE_SUFFIX` 常量在两模块中重复定义 |
| RT-04 | Low | new-defect | Research Template | `materialize_research_bundle_from_write_manifest` 公开函数未在 `__all__` |
| RT-05 | Low | new-defect | Research Template | 4 处 `assert isinstance(...)` 用于类型收窄，`-O` 下被剥离 |
| RT-06 | Low | new-defect | Research Template | `_normalize_template_name` 两处近似实现，校验规则可能漂移 |
| GATE-01 | Low | new-defect | Gates | `validate_spec` 未校验 worktree baseline overlap，给调用方假阴性 |
| GATE-02 | Low | new-defect | Gates | `os.chdir` 在 finally 中可能以混淆的表面错误失败 |
| GATE-04 | Low | new-defect | Gates | pyright stderr 输出未脱敏打印到 CI 日志 |
| GATE-08 | Low | new-defect | Gates | handoff docs 和 codex review gate 的 scope check 重复实现且标准化不同 |
| GATE-09 | Low | new-defect | Gates | `_write_handoff_text` 中 `_resolve_handoff_write_path` 双重调用间存在 TOCTOU 窗口 |

---

## 3. 详细 Findings

### 3.1 Write CLI Architecture

#### WRITE-01 [Medium] — Manual Recovery Application 日志标签错误

- **File:Line**: `dayu/cli/commands/_write_manual_recovery.py:391-395`
- **Evidence**:
  ```python
  snapshot_builder = build_snapshot_builder(
      args=args,
      paths_config=paths_config,
      execution_options=execution_options,
  )
  ```
  `build_snapshot_builder` 未传 `run_label`，默认值为 `"configuration-application"`。此标签流入 `_build_fresh_application_routing_snapshot` → `_log_write_preflight_result`，导致人工恢复的 preflight 日志显示为 `[configuration-application]` 而非 `[configuration-manual-recovery-application]`。对比同文件 `_run_write_model_configuration_manual_recovery_verification`（line 484）和 `_run_write_model_configuration_manual_recovery_clearance`（line 555）均已传入正确的 `run_label`。
- **Impact**: 人工恢复审计 trail 中无法区分配置应用预检与人工恢复预检，降低事故追溯可读性。
- **Fix**: 传入 `run_label="configuration-manual-recovery-application"`。

#### WRITE-04 [Medium] — `_build_auto_bootstrap_args` 浅拷贝共享可变引用

- **File:Line**: `dayu/cli/commands/_write_challenger.py:678-680`
- **Evidence**:
  ```python
  values = dict(vars(args))
  values.update({"template": None, "research_template": None, "infer": True})
  return argparse.Namespace(**values)
  ```
  `dict(vars(args))` 是浅拷贝。若原始 `args` 包含任何可变容器属性（如 `nargs="*"` 产生的 list），新旧 namespace 共享引用，一侧变更会污染另一侧。
- **Impact**: 当前 write 命令的 argparse 参数均为标量类型（str/bool/int），实际不触发。但若未来添加 list 型参数，将成为隐蔽的跨路径状态污染源。
- **Fix**: 使用 `copy.deepcopy(vars(args))` 或显式构造全新 namespace。至少添加注释说明浅拷贝假设。

#### WRITE-02 [Low] — `assert` 用于类型收窄，`-O` 下失效

- **File:Line**: `dayu/cli/commands/_write_execution.py:301`
- **Evidence**: `assert rollback_approval_output is not None` 在 `-O` 优化模式下被剥离，导致 `None` 静默传入 `persist_write_model_configuration_operator_rollback_approval`，产生模糊的下游错误。
- **Fix**: 替换为 `if rollback_approval_output is None: raise ValueError(...)`。

#### WRITE-05 [Low] — Rollback 快照构建缺 `run_label`

- **File:Line**: `dayu/cli/commands/_write_config_rollback.py:70-74`
- **Evidence**: 同 WRITE-01 模式，rollback 路径的 snapshot_builder 未传 `run_label`。
- **Fix**: 传入 `run_label="configuration-operator-rollback"`。

#### 正面确认（Write CLI）

- **Phase A/B 状态机正确**：Phase A 14 条目 dispatch 表 + Phase B 2 条目 dispatch 表与 accepted plan exact 一致。Phase A adapter 惰性构造 execution_options，Phase B 复用预计算值。
- **Protocol 契约精确**：`DayuCliArguments` 的 21 个 `AnnAssign` = `WriteDispatchArguments` 20 + `ResearchTemplateDispatchArguments` 1，字段名和类型完全匹配。
- **Import DAG 单向无环**：`_write_manual_recovery → _write_snapshot_builder → _write_config_application`，零反向 import，零 compatibility re-export。
- **异常映射正确**：`(FileNotFoundError, FileExistsError, OSError, TypeError, ValueError)` → exit code 2，未知 action → exit 1。
- **Challenger 防御性复核**：run plan 在 Host 初始化前后各构建一次，差异即 abort（exit 2），fail-closed。

### 3.2 Engine / Async / Failover

#### ENG-01 [Medium] — 熔断器 SQLite 写锁竞争无重试

- **File:Line**: `dayu/engine/model_circuit_breaker.py:172-187`
- **Evidence**: `_SQLiteCircuitStateStore._write_transaction` 使用 `BEGIN IMMEDIATE` + 5s `busy_timeout`。若多 worker 争抢导致超过 5s，SQLite 抛出 `OperationalError: database is locked`，在正常流程中不被捕获。
- **Impact**: 高并发下 `before_call()` / `record_failure()` / `record_success()` 可能因数据库锁竞争抛未处理异常，直接导致 Runner crash。仅在配置了持久化 path 时触发（默认走内存 store）。
- **Fix**: 在 `locked_entry` 外层包装重试逻辑（如 `tenacity`），或改用 WAL 模式 + 更长 busy_timeout。也可考虑内存热缓存 + 异步 SQLite 持久化。

#### ENG-02 [Low] — HALF_OPEN probe abandoned 等价 failure

- **File:Line**: `dayu/engine/model_circuit_breaker.py:427-441`
- **Evidence**: `record_abandoned()` 对 HALF_OPEN probe 直接调用 `_open_locked()`。用户取消（Ctrl+C）或 SIGTERM 触发的 abandoned 不被区分，与 provider 真实 failure 同处理。
- **Impact**: 频繁取消场景下 Provider 被长期熔断，但这不是 provider 健康问题。
- **Fix**: 区分取消原因。若由 `asyncio.CancelledError` 触发，不计入 failure；或改为不修改状态让下一调用者重新探针。

#### ENG-03 [Low] — aiohttp ClientSession 无强制关闭

- **File:Line**: `dayu/engine/async_openai_runner.py:657-677`
- **Evidence**: `_ensure_session()` 惰性创建 session，`close()` 提供显式关闭。但无 `__aenter__`/`__aexit__` 或 `__del__`，GC 时 aiohttp 输出 warning 且可能泄漏连接。
- **Fix**: 实现 async context manager，确保 session 在 `__aexit__` 中关闭。

其余 ENG-04~ENG-10 均为 Low severity，详见各子代理原始报告。总体而言 Engine 层状态机实现正确，取消传播路径完整，熔断器对 401/403 不触发（正确），429 触发（正确）。

### 3.3 Security / Redaction / Storage

总体评价：**净正向提升**。未发现 P0 安全漏洞。

- SEC-01 [Low]: `_normalize_entry_name` 未拒绝 null byte（pre-existing）
- SEC-02 [Low]: `is_subpath` 纯词法比较，API 未强制 resolve（new-defect，当前调用方安全）
- SEC-05 [Low]: `_persist_sources_json` 和最终报告未原子写入（pre-existing）

正面确认：
- CLI 脱敏（`RedactingArgumentParser`）正确覆盖 usage/help/error 三个输出路径
- `store_file` 从简单 `strip` 升级为 `_normalize_entry_name`，拒绝 `.`/`..`/`/`/`\`
- path traversal 测试覆盖 6 类 attack，跨进程崩溃恢复测试覆盖 orphan batch 自动恢复
- 所有 secret scanning gate 均返回 `secret_key_hits=[]`

### 3.4 Research Template Architecture

#### RT-01 [Medium] — `_run_validate_source_map` 无条件返回 0

- **File:Line**: `dayu/cli/commands/research_template.py:595-614`
- **Evidence**:
  ```python
  result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
  print(json.dumps(result, ensure_ascii=False, indent=2))
  return 0  # ← 无条件，未检查 result.get("ok")
  ```
  其他 5 个 validate runner 均使用 `return 0 if result.get("ok") is True else 1`。
- **Impact**: 脚本化流水线依赖 exit code 判断校验是否通过时，`validate-source-map` 永远返回 0，漏掉校验失败。
- **Fix**: 改为 `return 0 if result.get("ok") is True else 1`。

#### RT-02 [Medium] — `_load_json_object` 三处重复，错误处理发散

- **File:Line**:
  - `dayu/cli/commands/_research_template_helpers.py:379-396`
  - `dayu/cli/research_template_definitions.py:293-312`
  - `dayu/cli/commands/research_workbook.py`（第三处）
- **Evidence**: 三处实现相同的 JSON object 加载逻辑，但 `json.JSONDecodeError` 处理不同——一处原始传播，一处包装为 `ValueError`，错误消息措辞不同。
- **Impact**: bug fix 可能只在一处生效，其余两处残留。错误消息不一致增加调试难度。
- **Fix**: 提取为 `_research_template_helpers.py` 中的单一共享函数，所有调用方统一导入。

RT-03~RT-06 为 Low severity（常量重复定义、公开函数未入 `__all__`、assert isinstance 用于类型收窄、模板名标准化函数重复）。

正面确认：
- 模块拆分精确匹配 accepted plan：exact41/22/26/12/11/12 = 83 互斥并集
- `__all__` exact55，零 compatibility re-export
- Import DAG 完全单向无环：main→all5 / core→helpers / bundle→core+helpers / monitoring→bundle+core+helpers / materialize→monitoring+bundle+core+helpers
- 39-key dispatch mapping 完整，未知 action → exit 1
- Selector `str(getattr(args, "research_template_action", "") or "").strip().lower()` exact match
- Exception mapping: (FileNotFoundError, FileExistsError, ValueError) → stderr + exit 1

### 3.5 Dual-Model Gates / CI / Utils

GATE findings 均为 Low severity。核心问题：
- GATE-01: `validate_spec` 未校验 worktree baseline overlap——给调用方假阴性
- GATE-02: `os.chdir` 在 finally 块中可能因 CWD 已卸载产生混淆错误
- GATE-04: pyright stderr 输出打印到 CI 日志前未脱敏
- GATE-08: handoff 和 codex review gate 的 scope check 逻辑重复且标准化不同

正面确认：
- 三个 JSON machine gate 全部返回 `"ok": true`
- 699 dual-model focused tests 通过
- CI workflows 正确使用 `concurrency` groups，fail-closed
- 所有 utils 脚本无硬编码凭证，正确使用 `dayu.redaction`

---

## 4. Ruff Residual216 深度分析

**Scope**: `dayu/cli/commands/ dayu/services/`
**Tool**: Ruff 0.16.1，无显式 rule select
**Algorithm**: Counter(HEAD) - Counter(BASE)，origin/main=2115c86

| 分类 | 数量 | Rule Codes |
|------|------|-----------|
| **HIGH_RISK** | **0** | — |
| **LOW_RISK** | **2** | BLE001 (3 处 `except BaseException` 在事务回滚路径), UP035 (20 处已弃用 `typing` 导入) |
| **STYLE_ONLY** | **8** | B009(53), FURB162(12), ISC004(1), RUF010(22), RUF022(5), SIM102(3), TRY004(135), UP012(2) |

**关键结论**: 266 条违规中，**零条构成实际运行风险**。全部为已知设计决策（BLE001 的事务回滚 partial-success、pipeline 降级继续）或纯样式债务（B009 getattr 默认值均为常量、TRY004 ValueError vs TypeError 惯例等）。

LOW_RISK 2 项：
- BLE001 3 处 `except BaseException`：用于事务性快照 apply→restore 路径，吞掉 KeyboardInterrupt 以保证状态恢复。建议评估是否在 restore 后 re-raise 信号异常。
- UP035 20 处 `typing.X` → `collections.abc.X`：Python 3.14+ 前向兼容迁移，不影响 3.11 运行。

---

## 5. 正面确认汇总

以下关键架构属性经逐文件、逐函数、逐 import 边验证通过：

| 维度 | 验证结果 |
|------|---------|
| Phase A/B 状态机 | 14+2 dispatch 表 exact match，execution_options 惰性/预计算分治正确 |
| Protocol 契约 | 21 = 20 + 1，字段集合精确相等，pyright structural subtyping 通过 |
| Import DAG | 完全单向无环（write + research 两域均验证），零 compatibility re-export |
| 异常安全 | 已知异常类型映射到 exit code 2/4/6，未知 → exit 1，research materialize 为 documented partial-success |
| 熔断器状态机 | CLOSED→OPEN→HALF_OPEN→CLOSED 正确，generation 防 stale permit，401/403 不触发，429 正确触发 |
| 取消传播 | CancelledError 正确处理，shield + while-not-done 保护资源释放 |
| Secret 安全 | CLI 脱敏覆盖三路径，CI no echo，redaction tests 覆盖 argparse 全参数 |
| 路径遍历 | store_file 三层防御（_normalize_entry_name + containment check + 6 类 attack test） |
| 跨进程恢复 | orphan batch 自动恢复，os._exit(7) crash test 通过 |
| Module split | exact41+83=123 FunctionDef, __all__ 55, functional bindings 45, exact match to v5.7 plan |
| 行为测试 | 379 focused + 699 dual-model + 7121 full suite (Python 3.11) 全部通过 |
| Pyright ratchet | HEAD=219 / BASE=219 / new=0 |
| Architecture Ruff | positive=0 / negative=29 (I001:11, TRY004:17, UP035:1) |
| Machine gates | 三项 exit 0, `"ok": true`, issues=[], secret_key_hits=[], blocked_term_hits=[] |

---

## 6. 风险评估

| 风险类别 | 等级 | 说明 |
|---------|------|------|
| Correctness | **Low** | RT-01 是唯一的功能行为偏差（validate-source-map exit code），其余 Medium 均为非核心路径的防御性/审计债务 |
| Stability | **Low** | ENG-01 仅在极端高并发 + SQLite 持久化路径触发，其余 Engine findings 均为极边缘场景 |
| Security | **Very Low** | 零 P0 发现，分支是安全净正向提升（脱敏、路径加固、crash recovery） |
| Data Integrity | **Low** | SEC-05 非原子写入仅影响非关键产物（sources_dedup.json + final report），pre-existing |
| Maintainability | **Medium** | RT-02 三处 `_load_json_object` 重复和 RT-03/RT-06 常量/函数重复是实质性维护债务 |
| Technical Debt | **Acceptable** | Ruff positive216 全为样式债务，zero 运行风险 |

---

## 7. 建议

### 合并前（建议但不阻塞）

1. **RT-01 修复**：`_run_validate_source_map` 对齐其他 validate runner 的 exit code 逻辑（1 行改动）
2. **WRITE-01 修复**：`_run_write_model_configuration_manual_recovery_application` 传入正确的 `run_label`（1 行改动）

### 后续 Debt Week/Backlog

3. RT-02：提取 `_load_json_object` 为单一共享函数，移除两处重复实现
4. RT-03/RT-06：统一模板相关常量和标准化函数的单一真源
5. WRITE-04：`_build_auto_bootstrap_args` 改用 `copy.deepcopy`
6. ENG-01：熔断器 SQLite 写锁加重试
7. Ruff UP035：20 处 `typing` → `collections.abc` 迁移

---

## 8. 审查范围与限制

- **已审查**：write CLI（13 文件）、research template（10 文件）、engine/async/failover（14 文件）、security/redaction/storage（16 文件）、gates/CI/utils（13 文件）、Ruff residual216（10 rule codes）。合计约 66 个关键文件 + 216 条 Ruff 违规深度分析。
- **未深入审查**：`dayu/config/prompts/` 下的 prompt manifest JSON（14 个文件均为存量迁移，未发现安全或正确性风险）、`dayu/assets/research_templates/` 下的模板 markdown（10 个文件均为内容资产）、`tests/engine/test_cli_running_config.py` 等超大测试文件（已有 7121 passed 行为验证）。
- **未审查（非变更文件）**：`dayu/engine/` 下未变更的核心文件、`dayu/fins/` 下未变更的存储实现。
- 本审查不修改任何 production/tests/README/plan/validation artifact，不 commit/push。

---

*审查完成时间: 2026-08-08 | DeepSeek Aggregate Reviewer*
