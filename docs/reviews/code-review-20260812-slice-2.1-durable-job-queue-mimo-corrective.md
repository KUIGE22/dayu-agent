# Slice 2.1 Durable Job Queue — MiMo Corrective Code Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (corrective)
- **Branch**: codex/investment-platform / HEAD a457a7e
- **Scope**: F-001 / F-002 / F-003 fix re-review only（Controller 裁决 0/2/1 → fix → re-review）
- **Method**: 读取原 review + Controller 裁决 + fix artifact + 当前代码 diff；独立复跑 python -O 与 targeted non-PG 测试

## 0. Verdict

**PASS.** 三项 finding 修复均已正确应用，无新增回归。原 MiMo closed assert observation 被 Controller 覆盖为 F-001 Medium，修复后该 defect 已消除。

## 1. F-001 — parse_generic_attempt_receipt assert→显式类型守卫（Medium）

- **修复确认**: `jobs.py:768-801` 全部 8 处 `assert` 改为 `if not isinstance(...)` / `if type(...) is not int` → `raise JobInputError`。外层 except 移除 `AssertionError`（`jobs.py:817`）。
- **关键反例**: `schema_version: true`（JSON bool）。Python 中 `True == 1` 但 `type(True) is bool`，`type(True) is not int` 为 True → `JobInputError`。旧实现 `assert type(x) is int` 在 `-O` 下被移除，`True == 1` 使非法值被接受。
- **独立复证**: 主进程 `parse_generic_attempt_receipt(tampered)` → `JobInputError`。`python -O` 子进程同一文本 → `JobInputError`（exit 0）。两路均 PASS。
- **回归测试**: `test_generic_attempt_receipt_schema_version_true_rejected_under_optimized_interpreter` 使用 `subprocess.run([sys.executable, "-O", "-c", script])`，独立 pytest 复跑 2 passed exit 0。
- **原 closed observation 修正**: 我原将 assert 关闭为 non-blocking（"在 except AssertionError 块内"），Controller 以 `python -O` 反例证明是 correctness defect。修复后 observation 不再适用——函数内已无 assert。

## 2. F-002 — 同一 attempt 双 writer 结算竞态（Medium）

- **fixture 确认**: `second_store` fixture（`test_postgres_jobs.py:271-292`）创建独立 `create_platform_engine(login.dsn)` + `create_platform_session_factory(engine)` + `PostgresJobStore(session_factory)`，独立 engine.dispose()。与 `store` fixture 完全独立的 engine/session factory。
- **test_complete_vs_fail**（:1081-1164）: `threading.Barrier(2)` + 两线程各用 `store.complete` / `second_store.fail`。断言：恰好一方 `:ok` 另一方 `:lease_lost`；`_receipts_for` 长度 1；lease 1 行 `released_at` 非空 `version==2`；events `[job_created, job_claimed, <唯一 terminal>]` sequence `[1,2,3]`；job/attempt 终态一致。
- **test_complete_vs_complete**（:1167-1219）: 同样 Barrier + 两 engine 各 complete。断言：唯一 winner、唯一 receipt、`job_completed` event、lease 单次释放 `version==2`。
- **PG 证据**: fix artifact 记录 `TestConcurrentCompleteFail` 3 passed exit 0（MiM 独立 PG lane 已跑）。我读取测试实现确认断言完整覆盖 winner/receipt/terminal/lease/event 不变量。

## 3. F-003 — JobService.cancel 公共路径（Low）

- **application 层**: `_CapturingCancelStore` 记录 `(scope, request)` 引用同一性（`test_job_service.py:880-903`）。`reader.read_calls == []` 确认 Host 零读取。独立 pytest 复跑 PASS。
- **PG 层**: `TestJobServicePublicCancel.test_job_service_public_cancel_ready_path`（:2725-2755）用真实 `PostgresJobStore` + `JobHandlerRegistry` + `SQLiteRunRegistry` 装配 `JobService`。断言：`job_state=CANCELLED`、`attempt_id is None`、`receipt is None`、`_attempt_rows==[]`、`_receipts_for==[]`、events `[job_created, job_cancelled]`、后续 claim None。
- **证据**: fix artifact 记录 3 passed exit 0。我独立复跑 application 层 2 passed。

## 4. 回归风险

- F-001 修复只改 `parse_generic_attempt_receipt` 内部类型校验，不影响 canonical 编码/key 集合/组合矩阵。`_JsonValueValidator` 未改动。
- F-002/F-003 纯新增测试，未改生产语义。
- Fix artifact 完整门禁：156 unit passed + 三条 PG16 lane 36+16+71 passed + 全仓 8186 passed + pyright 0 + Ruff delta=0 + coverage ≥80%。

## 5. Final Verdict

**PASS / open H/M/L=0/0/0.** F-001/F-002/F-003 修复正确，无回归。可进入 accepted slice commit.
