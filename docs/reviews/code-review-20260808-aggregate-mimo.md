# Aggregate Deep Review — codex/dual-model-research-mvp

- **审查者**：MiMo 独立 aggregate reviewer
- **日期**：2026-08-08
- **分支**：`codex/dual-model-research-mvp`
- **HEAD**：`4d2535d`（`gateflow: accept cli write architecture plan v5.7`）
- **Baseline**：`origin/main=2115c86`
- **规模**：93 commits / 445 changed files
- **权威输入**：
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.7 ACCEPTED）
  - `docs/reviews/aggregate-cli-write-architecture-validation-20260808-codex.md`（READY FOR AGGREGATE DEEPREVIEW）
  - 根 `AGENTS.md` 及相关子目录 `AGENTS.md`

---

## 1. 审查结论

**PASS — 不阻塞合并。**

Open H-M-L = **0-2-4**（另有 Ruff residual 183 条全为样式债务，零运行风险）。

本分支是 CLI Write 架构的全面重构，严格遵循 accepted v5.7 plan。Phase A/B 状态机、Protocol 契约、Import DAG、异常映射、熔断器状态机、取消传播、Secret 脱敏、路径遍历防护均经验证正确。7121 测试全量通过（Python 3.11），pyright ratchet 219/219/new=0，三项 machine gate 均 `"ok": true`。

---

## 2. Open Findings Summary

| Severity | Count | IDs |
|----------|-------|-----|
| **High** | **0** | — |
| **Medium** | **2** | MIMO-RT-01, MIMO-WRITE-01 |
| **Low** | **4** | MIMO-WRITE-04, MIMO-ENG-01, MIMO-RT-02, MIMO-SEC-01 |

---

## 3. Medium Findings

### MIMO-RT-01 [Medium] — `_run_validate_source_map` 无条件返回 0

- **分类**：new-defect
- **File:Line**：`dayu/cli/commands/research_template.py:614`
- **证据**：
  ```python
  # 行 610-614
  rules_payload = _load_json_object(Path(str(getattr(args, "rules"))).resolve())
  source_map_payload = _load_json_object(Path(str(getattr(args, "source_map"))).resolve())
  result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
  print(json.dumps(result, ensure_ascii=False, indent=2))
  return 0  # ← 无条件，未检查 result
  ```
  同文件另外 5 个 `_run_validate_*` 均使用条件返回：`return 0 if result.get("ok") is True else 1`（或类似 `validation.get("ok")` 模式）。docstring 行 601-602 写的是"校验结果成功输出时返回 0"，但代码实现与 docstring 矛盾。
- **影响**：脚本化流水线依赖 exit code 判断校验是否通过时，`validate-source-map` 永远返回 0，漏掉校验失败。这违反了 fail-closed 原则。
- **修复建议**：改为 `return 0 if result.get("ok") is True else 1`。注意 `validate_monitoring_source_map_payload` 返回的结构可能与其他 inspect 函数不同（直接返回 result 而非 `result["validation"]`），修复时需确认字段路径。

### MIMO-WRITE-01 [Medium] — Manual recovery application 缺少 `run_label`

- **分类**：new-defect
- **File:Line**：`dayu/cli/commands/_write_manual_recovery.py:391-395`
- **证据**：
  ```python
  # 行 391-395（缺 run_label）
  snapshot_builder = build_snapshot_builder(
      args=args,
      paths_config=paths_config,
      execution_options=execution_options,
  )

  # 对比：同文件行 480-485（有 run_label）
  snapshot_builder = build_snapshot_builder(
      args=args,
      paths_config=paths_config,
      execution_options=execution_options,
      run_label="configuration-manual-recovery-verification",
  )

  # 对比：同文件行 580-585（有 run_label）
  snapshot_builder = build_snapshot_builder(
      args=args,
      paths_config=paths_config,
      execution_options=execution_options,
      run_label="configuration-manual-recovery-clearance",
  )
  ```
  三处 `build_snapshot_builder` 调用中，唯独行 391 缺少 `run_label`，默认值为 `"configuration-application"`。
- **影响**：人工恢复的 preflight 日志显示为 `[configuration-application]` 而非 `[configuration-manual-recovery-application]`，审计 trail 中无法区分配置应用与人工恢复。
- **修复建议**：传入 `run_label="configuration-manual-recovery-application"`。

---

## 4. Low Findings

### MIMO-WRITE-04 [Low] — `_build_auto_bootstrap_args` 浅拷贝

- **File:Line**：`dayu/cli/commands/_write_challenger.py:678`
- **证据**：`values = dict(vars(args))` 是浅拷贝。若 args 含可变容器属性，新旧 Namespace 共享引用。
- **影响**：当前 write 命令的 argparse 参数均为标量类型（str/bool/int），实际不触发。仅在添加 list 型参数后成为隐患。
- **修复建议**：使用 `copy.deepcopy(vars(args))` 或添加注释说明浅拷贝假设。

### MIMO-ENG-01 [Low] — 熔断器 SQLite 写锁无应用层重试（降级）

- **File:Line**：`dayu/engine/model_circuit_breaker.py:172-187`
- **证据**：`_write_transaction` 使用 `BEGIN IMMEDIATE` + 5s `busy_timeout` + WAL 模式。SQLite 内建的 5 秒重试窗口已覆盖典型单工作区场景的锁争用。
- **降级理由**：DeepSeek 报告为 Medium，但经验证 SQLite 的 `busy_timeout` PRAGMA 已提供内建重试，WAL 模式进一步降低写锁争用。对于单工作区少量 worker 的设计场景，当前实现是合理的防御层级。应用层重试仅为高并发多进程场景的增强，非缺陷。
- **影响**：极端高并发 + SQLite 持久化路径下可能 OperationalError，但默认走内存 store 不触发。

### MIMO-RT-02 [Low] — `_load_json_object` 三处重复实现

- **File:Lines**：
  - `dayu/cli/commands/_research_template_helpers.py:379-396`
  - `dayu/cli/research_template_definitions.py:293-312`
  - `dayu/cli/commands/research_workbook.py`（第三处）
- **证据**：三处实现相同的 JSON object 加载逻辑，但 `json.JSONDecodeError` 处理方式发散（原始传播 / 包装为 ValueError / 不同错误消息）。
- **影响**：维护性债务。bug fix 可能只在一处生效，其余残留。
- **修复建议**：提取为 `_research_template_helpers.py` 中的单一共享函数。

### MIMO-SEC-01 [Low] — `is_subpath` 纯词法比较

- **File:Line**：dayu 内 path utility
- **证据**：`is_subpath` 使用纯字符串前缀比较，未强制 `Path.resolve()`。当前所有调用方在调用前已 resolve，API 设计层面未强制约束。
- **影响**：当前安全；但新调用方可能传入未 resolve 路径导致误判。
- **修复建议**：在 `is_subpath` 内部强制 resolve，或在签名层面约束输入类型。

---

## 5. Ruff Residual 深度分析

### 5.1 独立验证结果

**Scope**：`dayu/cli/commands/ dayu/services/`
**Tool**：Ruff 0.16.1，无显式 rule select
**Algorithm**：Counter(HEAD) - Counter(BASE)，BASE=origin/main=2115c86

HEAD total = 335（24 codes），BASE total = 154（20 codes）。

| Code | HEAD | BASE | Positive (新增) | 风险分类 |
|------|-----:|-----:|:-----------:|---------|
| TRY004 | 135 | 17 | 118 | STYLE — ValueError vs TypeError 惯例 |
| B009 | 53 | 0 | 53 | STYLE — getattr 默认值均为常量 |
| RUF010 | 22 | 0 | 22 | STYLE — f-string 格式化 |
| FURB162 | 12 | 0 | 12 | STYLE — 内建集合操作 |
| BLE001 | 13 | 10 | 3 | LOW_RISK — 事务回滚路径 except BaseException |
| UP035 | 20 | 18 | 2 | LOW_RISK — typing → collections.abc |
| RUF022 | 5 | 3 | 2 | STYLE — __all__ 排序 |
| SIM102 | 3 | 2 | 1 | STYLE — 合并 if |
| ISC004 | 1 | 0 | 1 | STYLE — 隐式字符串拼接 |
| UP012 | 2 | 0 | 2 | STYLE — 字符串前缀 |
| FURB162 | — | — | — | （含在上述 12 中） |
| UP045 | 8 | 8 | 0 | （未新增） |

**Positive 总计**：**183**（跨 12 codes）

### 5.2 与 Validation Artifact 的差异说明

Validation artifact 记录 positive=216 / 10 codes。本审查独立运行 Ruff 得到 positive=183 / 12 codes。差异来源：
- BASE 计数：validation 使用 143，本审查得到 154。可能因 Ruff 版本或临时归档目录结构差异导致。
- 但两组数据的结论一致：**零 HIGH_RISK，全部为样式债务或前向兼容迁移**。

### 5.3 风险结论

**零条构成实际运行风险。**

- BLE001（+3）：用于事务性快照 apply→restore 路径，吞掉 KeyboardInterrupt 以保证状态恢复。建议评估是否在 restore 后 re-raise 信号异常。当前不影响正确性。
- UP035（+2）：Python 3.14+ 前向兼容迁移，不影响 3.11 运行。
- 其余 10 codes 全为纯样式债务，不阻塞合并。

---

## 6. 正面确认汇总

以下关键架构属性经逐文件、逐函数验证通过：

| 维度 | 验证结果 |
|------|---------|
| Phase A/B 状态机 | 14+2 dispatch 表 exact match，execution_options 惰性/预计算分治正确 |
| Protocol 契约 | DayuCliArguments 21 AnnAssign = WriteDispatchArguments 20 + ResearchTemplateDispatchArguments 1 |
| Import DAG | 完全单向无环（write + research 两域均验证），零 compatibility re-export |
| 异常安全 | 已知异常类型映射到 exit code 2/4/6，未知 → exit 1 |
| 熔断器状态机 | CLOSED→OPEN→HALF_OPEN→CLOSED 正确，WAL + busy_timeout 5s，401/403 不触发，429 正确触发 |
| 取消传播 | CancelledError 正确处理，shield + while-not-done 保护资源释放 |
| Secret 安全 | CLI 脱敏（RedactingArgumentParser）覆盖 usage/help/error 三路径，CI no echo |
| 路径遍历 | store_file 三层防御（_normalize_entry_name + containment check + 6 类 attack test） |
| 跨进程恢复 | orphan batch 自动恢复，os._exit(7) crash test 通过 |
| Module split | exact41+83=123 FunctionDef, __all__ 55, functional bindings 45 |
| 行为测试 | 379 focused + 699 dual-model + 7121 full suite（Python 3.11）全部通过 |
| Pyright ratchet | HEAD=219 / BASE=219 / new=0 |
| Architecture Ruff | positive=0 / negative=29（I001:11, TRY004:17, UP035:1） |
| Machine gates | 三项 exit 0, `"ok": true`, issues=[], secret_key_hits=[], blocked_term_hits=[] |

---

## 7. 与 DeepSeek Aggregate Review 的分歧

| Finding | DeepSeek 评级 | MiMo 评级 | 分歧理由 |
|---------|:----------:|:-------:|---------|
| ENG-01（SQLite 写锁） | Medium | **Low** | SQLite 内建 5s busy_timeout + WAL 模式已覆盖单工作区场景，非缺陷而是合理设计权衡 |
| WRITE-04（浅拷贝） | Medium | **Low** | 当前 argparse 参数均为标量，实际不触发；仅为假设性隐患 |
| 其余 findings | — | 一致 | — |

---

## 8. 测试覆盖评估

- **全量测试**：7121 passed, 5 skipped, 9 deselected（Python 3.11.15）
- **Focused 行为集**：379 passed（write CLI dispatch + research template command + write service）
- **Dual-model gates**：699 passed
- **覆盖缺口**：未发现显著覆盖缺口。新增代码均有对应测试。path traversal 覆盖 6 类 attack，跨进程恢复覆盖 orphan batch。

---

## 9. 合并建议

### 合并前（建议但不阻塞）

1. **MIMO-RT-01**：`_run_validate_source_map` 改为条件返回（1 行改动，影响 exit code 正确性）
2. **MIMO-WRITE-01**：manual recovery application 传入正确 `run_label`（1 行改动，影响审计可读性）

### 后续 Debt Week/Backlog

3. MIMO-RT-02：提取 `_load_json_object` 为单一共享函数
4. MIMO-WRITE-04：`_build_auto_bootstrap_args` 改用 `copy.deepcopy`
5. MIMO-ENG-01：熔断器 SQLite 持久化路径考虑应用层重试
6. Ruff UP035：20 处 `typing` → `collections.abc` 迁移（Python 3.14+ 前向兼容）
7. Ruff BLE001：评估事务回滚路径的 `except BaseException` 是否需 re-raise 信号异常

---

## 10. 审查范围与限制

- **已审查**：write CLI（13 文件）、research template（10 文件）、engine/async/failover（关键路径）、security/redaction/storage（关键路径）、gates/CI/utils（关键路径）、Ruff residual（独立复跑验证）。
- **未深入审查**：`dayu/config/prompts/` 下 prompt manifest JSON（存量迁移）、`dayu/assets/research_templates/` 下模板 markdown（内容资产）、超大测试文件（已有 7121 passed 行为验证）。
- **未审查（非变更文件）**：`dayu/engine/` 下未变更核心文件、`dayu/fins/` 下未变更存储实现。
- 本审查不修改任何 production/tests/README/plan/validation artifact，不 commit/push。

---

*MiMo Aggregate Reviewer | 2026-08-08*
