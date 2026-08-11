# Slice 2.1 Durable Job Queue — Code Review Fix

- **Status**：`CLOSED / DUAL CORRECTIVE CODE RE-REVIEW PASS`
- **Implementation specialist**：DeepSeek Flash
- **Branch / baseline**：`codex/investment-platform` / `a457a7e`（Controller accepted-plan baseline）
- **Gate**：code review fix gate（Controller 裁决 `docs/reviews/slice-2.1-durable-job-queue-code-review-adjudication-20260812-codex.md`）
- **Review sources**：MiM `code-review-20260811-slice-2.1-durable-job-queue-mim.md`（open H/M/L=0/1/2 → 规范化 0/2/1）、MiMo `code-review-20260811-slice-2.1-durable-job-queue-mimo.md`（PASS/0）
- **Exact fix scope（Controller 裁决 §Exact fix scope）**：`dayu/investment/domain/jobs.py`、`tests/application/test_job_service.py`、`tests/integration/investment/test_postgres_jobs.py`、`docs/reviews/slice-2.1-durable-job-queue-implementation-20260811-deepseek-flash.md`、本 artifact。其余 production/tests/README/plan/source reviews 全部冻结。

## 1. F-001 — parse_generic_attempt_receipt 类型守卫（ACCEPTED / Medium）

### 修复

`dayu/investment/domain/jobs.py::parse_generic_attempt_receipt`：8 处 `assert` narrowing 全部改为显式 fail-closed 校验，非法值统一 `JobInputError`：

1. `assert isinstance(schema_name, str)` → `if not isinstance(schema_name, str): raise JobInputError("receipt schema_name 类型非法")`
2. `assert type(schema_version) is int` → `if type(schema_version) is not int: raise JobInputError("receipt schema_version 类型非法")`（拒绝 bool-as-int）
3. `assert isinstance(outcome_raw, str)` → `if not isinstance(...): raise ...`
4. `assert isinstance(reason_raw, str)` → 同上
5. `assert isinstance(result_raw, dict)` → `if not isinstance(result_raw, dict): raise JobInputError("receipt result 类型非法")`
6. `assert isinstance(ref_schema_name, str)` → 同上
7. `assert type(ref_schema_version) is int` → `if type(...) is not int: raise ...`（拒绝 bool-as-int）
8. `assert isinstance(ref_sha256, str)` → 同上

外层 `except (JobInputError, ValueError, TypeError, AssertionError, KeyError)` 移除 `AssertionError` → `(JobInputError, ValueError, TypeError, KeyError)`（函数内不再有 assert）。canonical 编码、精确 key 集合与组合矩阵合同未放宽；`_JsonValueValidator` 未改动。

### 证据

- 主进程：`parse_generic_attempt_receipt(schema_version=true 的 canonical 文本)` → `JobInputError`。
- `python -O` 子进程：同一文本，只有 `JobInputError` 才 exit 0（被接受 exit 1、其它异常 exit 2），子进程 returncode=0。
- 回归测试 `tests/application/test_job_service.py::TestGenericAttemptReceipt::test_generic_attempt_receipt_schema_version_true_rejected_under_optimized_interpreter`（使用 `sys.executable -O`，候选文本保持 canonical 编码：`json.dumps(tampered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`）。

## 2. F-002 — 同一 attempt 双 writer 结算竞态测试（ACCEPTED / Medium）

### 修复

`tests/integration/investment/test_postgres_jobs.py::TestConcurrentCompleteFail`（置于 TestCompleteAndFail 后）：

- `test_complete_vs_fail_exactly_one_settles`：`store` 与 `second_store` 两个独立 engine + `threading.Barrier(2)`；complete（带 result）vs fail（`retryable=False`）。
- `test_complete_vs_complete_exactly_one_settles`：两个独立 engine 各跑 complete。

### 断言

- 恰好一方 `:ok`、另一方 `:lease_lost`（`JobLeaseLostError`）。
- 唯一 immutable receipt（`_receipts_for` 长度 1）。
- lease 仅一行、`released_at` 非空、`version == 2`（versioned CAS 单次释放）。
- events 严格 `[job_created, job_claimed, <唯一 terminal>]` 且 `sequence_number == [1, 2, 3]`；complete 胜出 terminal=`job_completed`，fail 胜出 terminal=`job_failed`。
- job/attempt 终态与唯一 terminal 一致（SUCCEEDED/SUCCEEDED 或 FAILED/FAILED）。

未改变生产结算语义（仅新增测试）。

## 3. F-003 — JobService.cancel 公共路径测试（ACCEPTED / Low）

### 修复

两层：

1. **application 层**（`tests/application/test_job_service.py`）：新建窄 `_CapturingCancelStore(_FakeJobStore)`——只覆盖 `cancel` 记录真实传入的 `(scope, request)` 并返回可配置 `cancel_result`；`_FakeJobStore.cancel` 的 `AssertionError` trap 保持不变（未削弱）。新增 `TestJobService.test_job_service_cancel_delegates_scope_and_request_to_store`：断言 `captured_scope is scope`、`captured_request is request`（同一性）、`reader.read_calls == []`（Host 零读取）、返回即 `store.cancel_result`。
2. **PG 层**（`tests/integration/investment/test_postgres_jobs.py::TestJobServicePublicCancel::test_job_service_public_cancel_ready_path`）：真实 `PostgresJobStore` + `JobHandlerRegistry` + `SQLiteRunRegistry`（结构满足 `HostRunReaderProtocol`）装配 `JobService`；经 `service.cancel(_SCOPE_A, request)` 取消 ready job：`job_state=CANCELLED`、`attempt_id is None`、`receipt is None`、`_attempt_rows == []`、`_receipts_for == []`、events 严格 `[job_created, job_cancelled]`、后续 `_claim == None`。

未新增任何 Service 行为（纯测试）。

## 4. Validation（每条精确命令与真实结果）

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `.venv/bin/pytest tests/application/test_job_service.py::TestGenericAttemptReceipt -q --timeout=60` | `3 passed`，exit `0`（含 `python -O` 子进程回归） |
| 2 | `.venv/bin/pytest tests/application/test_job_service.py -q --timeout=60` | `30 passed`，exit `0`（含 F-003 delegation） |
| 3 | `.venv/bin/pytest "tests/integration/investment/test_postgres_jobs.py::TestConcurrentCompleteFail" "tests/integration/investment/test_postgres_jobs.py::TestJobServicePublicCancel" -q --timeout=120` | `3 passed`，exit `0`（F-002 两竞态 + F-003 PG） |
| 4 | application/CLI focused：`pytest tests/application/test_job_service.py tests/application/test_run_registry.py tests/application/test_reserved_agent_run.py tests/application/test_service_startup_preparation.py tests/cli/workspace_migrations/test_platform_jobs.py tests/investment/test_platform_migrations.py -q --timeout=60` | `156 passed`，exit `0` |
| 5 | PG16 lane 1：`pytest tests/integration/investment/test_platform_migrations_postgres.py -q --timeout=120` | `36 passed`，exit `0` |
| 6 | PG16 lane 2：`pytest tests/integration/investment/test_identity_repositories_postgres.py -q --timeout=120` | `16 passed`，exit `0` |
| 7 | PG16 lane 3：`pytest tests/integration/investment/test_postgres_jobs.py -q --timeout=120` | `71 passed`，exit `0` |
| 8 | Coverage（unit + 3 lanes + full non-integration lane，fresh `COVERAGE_FILE`，`coverage run -m pytest` 无 `--source`）：`jobs.py 88%`、`postgres_jobs.py 83%`、`job_service.py 90%`、`executor.py 90%`、`host.py 84%`、其余 ≥88% | 全部修改生产文件 ≥80% |
| 9 | `pyright <全部 22 个改动 production/test 路径>` | `0 errors, 0 warnings` |
| 10 | Ruff：13 modified 文件 HEAD/current code multiset（`git show` stdin 只读） | 全部 `delta=0` |
| 11 | Ruff：新文件 `jobs.py` / `test_job_service.py` / `test_postgres_jobs.py` | `All checks passed` |
| 12 | 中文 docstring + escape guards（4 项） | 全 PASS |
| 13 | `git diff --check` | `OK` |
| 14 | `env -u SERPER_API_KEY .venv/bin/pytest -q --timeout=60 -m "not integration and not slow and not e2e"` | `8186 passed, 5 skipped, 157 deselected`，exit `0` |

## 5. 未变更 / residual

- 未 commit / push / PR / stash；未进入 Slice 2.2/2.3；未触碰 allowlist 外文件。
- MiM open question（`_persist_receipt` 锁序 / `ON CONFLICT`）由 Controller 裁决记录为 residual，不扩大修复。
- 既有完整 lease identity 修复（tenant/job/attempt/fence/token/current-attempt）与真实 PG 参数矩阵已闭合，本轮不重复。

## 6. 下一步

原 MiM 与 MiMo reviewer 已完成 corrective dual re-review：

- `docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mim-corrective.md` — PASS / open H/M/L=`0/0/0`
- `docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mimo-corrective.md` — PASS / open H/M/L=`0/0/0`

F-001/F-002/F-003 全部 CLOSED；无新 finding、无需第二轮 fix。当前状态可进入 accepted slice commit gate。
