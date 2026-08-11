# Corrective Code Review — Slice 2.1 Durable Job Queue

## Scope

- **Mode**: corrective re-review（仅复核 F-001/F-002/F-003 及回归风险）
- **Branch**: `codex/investment-platform`
- **Base**: `a457a7e`（Controller accepted-plan baseline）
- **Output file**: `docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mim-corrective.md`
- **Review sources**: MiM original `code-review-20260811-slice-2.1-durable-job-queue-mim.md`、Controller adjudication `slice-2.1-durable-job-queue-code-review-adjudication-20260812-codex.md`、fix artifact `slice-2.1-durable-job-queue-review-fix-20260812-deepseek-flash.md`
- **Included scope**: `dayu/investment/domain/jobs.py`（F-001 生产修复）、`tests/application/test_job_service.py`（F-001 回归 + F-003 委托）、`tests/integration/investment/test_postgres_jobs.py`（F-002 竞态 + F-003 PG）
- **Excluded scope**: 其余 production/tests/README/plan/artifacts 全部冻结；不并行跑整个 PG lane

## Conclusion

**PASS / open H/M/L = 0/0/0**

三项 fix 均正确实现且通过定向验证，未发现回归或新 finding。

---

## F-001 复核 — parse_generic_attempt_receipt 显式 fail-closed

### 修复验证

`dayu/investment/domain/jobs.py:768-801`：8 处 `assert isinstance/assert type is` 全部替换为显式 `if/raise JobInputError`：

| # | 旧行为 | 新行为（行号） |
|---|---|---|
| 1 | `assert isinstance(schema_name, str)` | `if not isinstance(schema_name, str): raise JobInputError(...)` (L768-769) |
| 2 | `assert type(schema_version) is int` | `if type(schema_version) is not int: raise JobInputError(...)` (L770-771) |
| 3 | `assert isinstance(outcome_raw, str)` | `if not isinstance(outcome_raw, str): raise JobInputError(...)` (L780-781) |
| 4 | `assert isinstance(reason_raw, str)` | `if not isinstance(reason_raw, str): raise JobInputError(...)` (L782-783) |
| 5 | `assert isinstance(result_raw, dict)` | `if not isinstance(result_raw, dict): raise JobInputError(...)` (L789-790) |
| 6 | `assert isinstance(ref_schema_name, str)` | `if not isinstance(ref_schema_name, str): raise JobInputError(...)` (L796-797) |
| 7 | `assert type(ref_schema_version) is int` | `if type(ref_schema_version) is not int: raise JobInputError(...)` (L798-799) |
| 8 | `assert isinstance(ref_sha256, str)` | `if not isinstance(ref_sha256, str): raise JobInputError(...)` (L800-801) |

- 整数校验使用 `type(x) is not int`（拒绝 `bool` 冒充 `int`），与 Controller 合同一致
- 外层 except clause (L817) 已移除 `AssertionError`：`except (JobInputError, ValueError, TypeError, KeyError)`
- canonical 编码、精确 key 集合、组合矩阵不变量未放宽
- 函数体内零 assert 残留（`sed -n '727,820p' | grep assert` → 空）

### 回归测试验证

`tests/application/test_job_service.py:489-553`：`test_generic_attempt_receipt_schema_version_true_rejected_under_optimized_interpreter`

- 构造合法 canonical receipt → 篡改 `schema_version` 为 JSON `true` → 重新 canonical 编码
- 主进程直接断言 `pytest.raises(JobInputError)`
- `python -O` 子进程：spawn `subprocess.run([sys.executable, "-O", "-c", script])`，exit 0 = `JobInputError` 被抛出（修复正确），exit 1 = 被接受（修复失败），exit 2 = 其它异常
- 断言 `completed.returncode == 0`
- **直接证据**: 测试通过（3 passed, 1.43s）

### 回归风险

无。修复只收紧了类型校验路径，不改变合法输入的处理逻辑。

---

## F-002 复核 — 同一 attempt 双 writer 结算竞态测试

### 修复验证

`tests/integration/investment/test_postgres_jobs.py:1077-1219`：`TestConcurrentCompleteFail` 类

**test_complete_vs_fail_exactly_one_settles** (L1081-1164)：
- 两个独立 `PostgresJobStore`（各自独立 engine/session）+ `threading.Barrier(2)`
- completer 调 `store.complete(scope, lease, JobCompletion(result=_result()))`
- failer 调 `second_store.fail(scope, lease, JobFailure(safe_error_code=HANDLER_REJECTED, retryable=False))`
- 断言：
  - `sum(o.endswith(":ok")) == 1` 且 `sum(o.endswith(":lease_lost")) == 1`
  - `_receipts_for(attempt_id)` 长度 == 1
  - lease 唯一一行、`released_at` 非空、`version == 2`
  - events 严格 `[job_created, job_claimed, <terminal>]`，sequence `[1, 2, 3]`
  - terminal_type 动态匹配胜出方（`job_completed` 或 `job_failed`）
  - job/attempt 终态与胜出 terminal 一致

**test_complete_vs_complete_exactly_one_settles** (L1167-1219)：
- 两个独立 engine 各跑 `complete`（用相同 `claim.lease`）
- 同样断言恰好一方成功
- events 严格 `[job_created, job_claimed, job_completed]`
- lease 单次释放、version=2

- **直接证据**: 测试通过（3 passed, 7.50s，含 F-003 PG 测试）

### 回归风险

无。仅新增测试，未改变生产结算语义。

---

## F-003 复核 — JobService.cancel 公共路径

### 修复验证

**Application 层** (`tests/application/test_job_service.py:720-903`)：

- `_CapturingCancelStore` (L720-736)：继承 `_FakeJobStore`，仅覆盖 `cancel` 方法记录 `(scope, request)` 并返回可配置 `cancel_result`。`_FakeJobStore.cancel` 的 `AssertionError` trap 保持不变
- `test_job_service_cancel_delegates_scope_and_request_to_store` (L880-903)：
  - 构造 `_CapturingCancelStore` + `_FakeHostReader`
  - 调 `service.cancel(scope, request)`
  - 断言：`result is store.cancel_result`（同一性）、`captured_scope is scope`、`captured_request is request`、`reader.read_calls == []`（Host 零读取）
  - **直接证据**: 测试通过（1 passed, 1.06s）

**PG 层** (`tests/integration/investment/test_postgres_jobs.py:2721-2755`)：

- `TestJobServicePublicCancel` 类：真实 `PostgresJobStore` + `JobHandlerRegistry` + `SQLiteRunRegistry`（结构满足 `HostRunReaderProtocol`）装配 `JobService`
- `test_job_service_public_cancel_ready_path` (L2725-2755)：
  - enqueue ready job → `service.cancel(_SCOPE_A, request)`
  - 断言：`job_state=CANCELLED`、`attempt_id is None`、`receipt is None`、`_attempt_rows == []`、`_receipts_for == []`、events `[job_created, job_cancelled]`、后续 `_claim == None`
  - **直接证据**: 测试通过（与 F-002 同一批次 3 passed）

### 回归风险

无。仅新增测试，未改变 Service 行为。

---

## Open Questions

无。

## Residual Risk

无新增。原 MiM residual 中的 `time_module.sleep()` CI flaky 风险和 `_persist_receipt` 锁序 open question 保持不变，不在本轮修复范围内。
