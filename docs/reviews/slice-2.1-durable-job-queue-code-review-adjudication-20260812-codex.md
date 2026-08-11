# Slice 2.1 Durable Job Queue — Code Review Adjudication

- **Status**: CLOSED / DUAL CORRECTIVE CODE RE-REVIEW PASS / OPEN H/M/L=0/0/0
- **Controller**: Codex
- **Date**: 2026-08-12
- **Branch**: `codex/investment-platform`
- **Accepted plan baseline**: `a457a7e`

## Review sources

- MiM: `docs/reviews/code-review-20260811-slice-2.1-durable-job-queue-mim.md`
- MiMo: `docs/reviews/code-review-20260811-slice-2.1-durable-job-queue-mimo.md`

MiM 标题中的 `open H/M/L=0/1/2` 与正文不一致；正文实际包含两个 Medium（M-001、M-002）和一个 Low（L-001）。Controller 以逐项 finding 为准，将修复前 open 计数规范化为 `0/2/1`。

## Controller adjudication

### F-001 — ACCEPTED / Medium / fix required

来源：MiM M-001。

`parse_generic_attempt_receipt()` 使用八个 `assert` 作为不可信 JSON 的运行时类型边界；MiM 原 finding 少计一处。Controller 以 `python -O` 独立复现：把合法 canonical generic receipt 顶层 `schema_version` 改为 JSON `true` 后，当前实现输出 `ACCEPTED True bool`。优化模式移除 `assert type(schema_version) is int`，而 Python 中 `True == 1`，导致非法 schema version 被接受。

MiMo 将该 observation 关闭为 non-blocking，但这一具体反例证明 finding 是 correctness defect，Controller 覆盖该裁决。

修复合同：

1. 仅在 `dayu/investment/domain/jobs.py` 将八个 assert narrowing 改为显式、fail-closed 类型校验；两个整数边界必须使用精确 `type(value) is int`，非法值统一为 `JobInputError`。
2. 不放宽 canonical JSON、精确 key 集合或 receipt 组合不变量。
3. 在 `tests/application/test_job_service.py` 加入使用 `sys.executable -O` 的永久回归，精确证明 `schema_version: true` 被拒绝为 `JobInputError`。

### F-002 — ACCEPTED / Medium / test fix required

来源：MiM M-002。

当前真实 PG16 测试覆盖 claim race、event sequence race、terminal-versus-recover，但没有同一 attempt 的双 writer settlement race。锁与 fence 实现看起来正确，仍需把关键不变量变成持久门禁。

修复合同：

1. 在 `tests/integration/investment/test_postgres_jobs.py` 使用两个独立 `PostgresJobStore`/engine 与 `threading.Barrier(2)`。
2. `complete` versus `fail`：恰好一方成功，另一方为 `JobLeaseLostError`；最终只有一个 immutable receipt、一个终态 attempt/job、lease 仅释放一次、事件序列闭合。
3. `complete` versus `complete`：同样恰好一方成功，另一方为 `JobLeaseLostError`，且不得产生第二个 receipt 或重复 terminal event。
4. 不为测试改变生产结算语义。

### F-003 — ACCEPTED / Low / test fix required

来源：MiM L-001。

Store 的 cancel 状态机已有充分覆盖，但 `JobService.cancel()` 公共代理没有测试。最小修复是在已有 fake/真实 PG 装配中经 `JobService.cancel()` 验证参数逐字传递与 ready cancel 的真实 Service→Store 路径；不增加新的 service 行为。

## Rejected or closed observations

- MiMo 未提出额外 H/M/L finding。
- MiM 关于 `_persist_receipt()` 潜在锁序/`ON CONFLICT` 的 open question 当前没有可复现缺陷，且现实现已使用冲突收敛；作为 residual 记录，不扩大本次修复。
- 既有完整 lease identity（tenant/job/attempt/fence/token/current-attempt）修复与真实 PG 参数矩阵已在 implementation WIP 中闭合，不在本轮重复改造。

## Exact fix scope

允许修改：

- `dayu/investment/domain/jobs.py`
- `tests/application/test_job_service.py`
- `tests/integration/investment/test_postgres_jobs.py`
- `docs/reviews/slice-2.1-durable-job-queue-implementation-20260811-deepseek-flash.md`
- 本裁决 artifact
- 新建 `docs/reviews/slice-2.1-durable-job-queue-review-fix-20260812-deepseek-flash.md`

其余 production、tests、README、plan 与 source review 全部冻结。不得 commit、push、建 PR、stash，也不得启动 Slice 2.2/2.3。

## Required validation

1. F-001 定向测试，包含真实 `python -O` 子进程。
2. application/CLI focused suite。
3. 三条互相独立的 PG16 lanes；不得并行共享数据库。
4. 修改生产文件逐文件 coverage 仍不低于 80%。
5. exact Pyright 0、Ruff F/I 与 HEAD/full-rule delta gate、中文 docstring gate、`git diff --check`。
6. clean-env full lane；随后由原 MiM 与 MiMo reviewer 进行 corrective dual re-review，必须 open H/M/L=`0/0/0`。

## Closure

- Fix artifact：`docs/reviews/slice-2.1-durable-job-queue-review-fix-20260812-deepseek-flash.md`
- MiM corrective review：`docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mim-corrective.md` — PASS / open H/M/L=`0/0/0`
- MiMo corrective review：`docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mimo-corrective.md` — PASS / open H/M/L=`0/0/0`

F-001、F-002、F-003 均已 FIXED/CLOSED。MiM 独立复跑优化模式与真实 PG 定向测试；MiMo 独立复证 `python -O` 反例已被 `JobInputError` 拒绝，并复核 PG 并发测试结构和 Service cancel 公共路径。当前 Slice 2.1 code review open H/M/L=`0/0/0`，可进入本地 accepted commit gate。
