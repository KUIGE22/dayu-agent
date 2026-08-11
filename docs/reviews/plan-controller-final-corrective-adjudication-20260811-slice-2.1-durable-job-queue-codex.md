# Controller Final Corrective Adjudication：Slice 2.1 durable job queue

- **Gate**：final corrective plan re-review adjudication
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Valid independent reviews**：
  - `docs/reviews/plan-final-corrective-rereview-20260811-slice-2.1-contract-closure-mim.md`（PASS，open 0/0/0）
  - `docs/reviews/plan-final-corrective-rereview-20260811-slice-2.1-contract-closure-flash.md`（FAIL，open 2/1/2）
- **Conclusion**：`PLAN FIX REQUIRED / OPEN H/M/L = 3/2/2`
- **External actions**：未执行 commit、push、PR、deploy、live、paid、Docker 或 PostgreSQL action。

## 1. Review-integrity record

MiMo 的本轮输出无效：它先读了 MiM 的新 review，又把新结论写到历史 untracked
artifact 路径，导致历史内容不可恢复和独立性同时失效。该文件已由 MiMo 自身改为
`INVALIDATED / NOT A REVIEW PASS` 事故记录，不计入 gate。随后干净会话仍启动了指向错误
PLC 仓库的 Explore 子任务，因此被中断。AgentDS fallback 返回 402 余额不足，未重试、未计
review。DeepSeek Flash 未参与本计划编写或修复，本轮严格 reviewer-only，作为有效第二路
fallback。Codex Spark 的 mechanical audit 仅是 advisory inventory，不计独立 review；其中把
待实现代码不存在当过缺口，纠正后又把未定义的 receipt schema 误写成已存在，故不作为
finding closure 权威。

MiM 对 S21-CTRL-FINAL-001..004 的文字闭合判断成立，但其 PASS 没有追到 storage import
guard、Service correlation lookup 和 generic receipt construction。Controller 以直接源码、
计划调用链及有效 Flash review 证据裁决，而不是按 reviewer 投票。

## 2. Prior findings

`S21-CTRL-FINAL-001..004` 的原修复内容保持 **CLOSED-IN-PLAN**：15 DTO 字段表、
descriptor-only registry、Service-owned Host observation mapping、以及重复 reconciliation 的
`ALREADY_*`/event-dedupe 语义都已写明。下面是修复后暴露的新的 code-generation-readiness
缺口；它们不撤销原 finding 的事实闭合，但阻止计划进入 implementation。

## 3. Accepted findings

### S21-CTRL-FINAL2-001 — ACCEPTED — High — job contract owner 与 storage import guard 冲突

计划把全部 job DTO/Protocol 放在 `dayu.host`，同时要求
`dayu/investment/storage/postgres_jobs.py` 实现这些 Protocol、构造这些 DTO，且在 STOP 中禁止
storage import `dayu.host`。现有
`tests/investment/test_architecture_boundaries.py:80-97,193-195,214-243,838-866` 会对所有
`storage/**` AST import 拒绝 `dayu.host` 和 `dayu.contracts`，包含 `TYPE_CHECKING` import；该
测试也不在当前 allowlist。实现者没有合法 import path。

**Required fix**：Terra 必须选择一个唯一、分层正确的 contract/service/store owner，并同步
allowlist、DAG、architecture guard、constructor、imports、README 和 tests。不得以重复 DTO、
structural `object`、lazy import、compat wrapper 或 narrow test exemption 逃避。Host reserved-run
contract 继续留 Host；PG job application/storage contract 不得让 investment storage 反向依赖
Host。修订必须明确哪些类型属于 pure domain、repository Protocol 和 application Service，且
仍满足 master 的 Service → Host → Agent 边界。

### S21-CTRL-FINAL2-002 — ACCEPTED — High — terminal reconciliation 缺 correlation-by-id lookup

`JobService.reconcile_agent_run_terminal(scope, correlation_id)` 只有 correlation UUID，却必须先
取得 `correlation.reserved_host_run_id` 才能调用 Host reader。计划列出的 Store 方法没有按 ID
读取 correlation 的方法；Service 也不能由 correlation UUID 推导 attempt UUID 或 reserved ID，
更不能依赖进程内 cache，因为该入口专用于 restart recovery。

**Required fix**：在最终选定的 repository Protocol 中精确定义
`get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation`，给出 tenant-scoped
not-found/invariant 语义。固定 Service 顺序为 repository get → Host reader get → strict
observation mapping → repository terminal reconciliation；每次 restart/replay 都重新读取，storage
仍不接触 Host。补 direct/live/restart/missing/cross-tenant tests，并把方法加入 exact public
signature 表。

### S21-CTRL-FINAL2-003 — ACCEPTED — Medium — deadline 与 correlation-missing 分支未闭合

稳定 `JobDeadlineExceededError` 没有抛出点；heartbeat 在 lease 尚有效但 PG now 已到 deadline
时，不清楚是 clamp、terminalize 还是报错。`SafeJobErrorCode.correlation_missing` 同样没有任何
明确 decision/return point。

**Required fix**：逐分支锁定 `now < deadline` 的 heartbeat expiry clamp、`now >= deadline` 的
attempt/job/lease/receipt/event 和稳定异常/返回；禁止返回 expiry 已在过去的成功 `JobClaim`。
同时选择 `correlation_missing` 的唯一生产分支并补测试，或从 closed enum 删除它。不得保留
永远不可达的 public error/code。

### S21-CTRL-FINAL2-004 — ACCEPTED — Low — mutable lease schema 与总则冲突

`job_leases.released_at/release_reason` 可 UPDATE，但表没有总则要求的 `updated_at/version`，而
计划又写“未列字段不得发明”。

**Required fix**：明确把 lease 定义为 versioned mutable row并补字段、grant、CAS/check/tests，
或明确规定它是 append-plus-single-release 的例外并删除冲突总则。必须选择一个，不留给实现者。

### S21-CTRL-FINAL2-005 — ACCEPTED — Low — Host UNSETTLED 映射不唯一

计划没有锁定 UNSETTLED 最终写 `host_unsettled` 还是 `host_failed`，也没有锁定
`host_run_unsettled` 还是 `host_run_failed`。

**Required fix**：固定 observation → correlation state → receipt safe code → decision action 的唯一
映射并补 exact test。推荐保持信息不丢失：`UNSETTLED → host_unsettled /
host_run_unsettled / TERMINALIZED_FAILURE`。

### S21-CTRL-FINAL2-006 — ACCEPTED — High — generic attempt receipt canonical schema 缺失

计划要求 `JobAttemptReceipt.receipt` 永远存在并持久化 schema/version/bytes/hash，但只定义了
Host-origin terminal receipt 的 schema 和 key 集合。`complete` 只接收 result；`fail` 只接收
safe code/retryable；cancel/recover 也没有 receipt document 输入。因此 normal complete、handler
failure、deadline、lease expiry 和 cancellation 都要求实现者发明持久 canonical object，影响
bytes/hash、重放和未来兼容性。Spark audit 声称 `JobCompletion` 含 receipt schema，与计划 DTO
字段 `result`-only 的直接证据矛盾。

**Required fix**：为非 Host attempt receipt 定义唯一常量 schema name/version、精确 canonical
key 集合、每个 outcome 的 nullability和值来源；明确 result 只保存 schema/version/hash 引用还是
其它安全字段，禁止 raw error/token/payload duplication。固定 complete/fail/cancel/deadline/
lease-expired/retry-exhausted 的 receipt builder 与同 attempt replay bytes/hash。补参数化 golden
bytes、strict parse、DB roundtrip 和 duplicate-finalization tests。

### S21-CTRL-FINAL2-007 — ACCEPTED — Medium — recover 的 attempt state/receipt 互相矛盾

DTO 表规定 retry 时 `JobRecoveryResult.attempt_state=failed`，而 generic recover 明确把 lease
expired attempt 标为 `abandoned` 再按 retry policy 使 job ready；cancel-intent recover 也先写
abandoned 再让 job cancelled。结果 DTO、stored attempt state 和 receipt outcome 无法同时遵守。

**Required fix**：分别锁定 handler `fail`、lease-expiry recover、cancel-intent recover、deadline
和 retry-exhausted 的 attempt state、job state、receipt outcome/safe code、next_available_at。推荐
cancel intent 直接把 attempt 收敛为 `cancelled`；非取消 lease expiry 保持 `abandoned` 并写
failed/`lease_expired` receipt；retry job 可回 ready，但结果必须报告真实 stored attempt state。
同步状态机表、DTO invariants、DDL CHECK、算法和命名 tests。

## 4. Next gate

Terra 只修改 target plan并新增一份 bounded plan-fix artifact；production、tests、README、master
plan 和已有 review artifacts 冻结。修订后由 MiM 与一个未参与修复、可保持绝对路径和独立性的
capable reviewer 做 corrective re-review。所有 `S21-CTRL-FINAL2-001..007` 必须逐项 CLOSED，
Controller open H/M/L 必须归零，才能创建 accepted plan local commit并进入 Flash implementation。
