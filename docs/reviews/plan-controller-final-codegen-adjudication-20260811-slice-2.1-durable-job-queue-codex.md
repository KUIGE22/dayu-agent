# Controller Final Codegen Adjudication：Slice 2.1 durable job queue

- **Gate**：final codegen plan re-review adjudication
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Independent reviews**：
  - `docs/reviews/plan-final-codegen-rereview-20260811-slice-2.1-mim.md`
    （PASS，open 0/0/0）
  - `docs/reviews/plan-final-codegen-rereview-20260811-slice-2.1-flash.md`
    （FAIL，open 0/1/3）
- **Conclusion**：`PLAN FIX REQUIRED / OPEN H/M/L = 1/1/3`
- **External actions**：未执行 implementation、tests、Docker、PostgreSQL、commit、push、PR、deploy、live 或 paid action。

## 1. Review-integrity 与 prior closure

两路 reviewer 均只写各自 artifact，未互读本 gate 的新 review。MiM 对
`S21-CTRL-FINAL2-001..007` 的逐项 CLOSED 判断有效，但其最终“与 master 无冲突”结论被
master `:3752-3758` 与 target 的直接文本差异否定，故不能单独通过 gate。Flash 同样确认旧七项
全部 CLOSED，并以源码/计划调用链发现新的 recover 缺口。

`S21-CTRL-FINAL2-001..007` 与后续 Host protocol allowlist、两个 reserved error constructor、
services-owned descriptor registry、Service-before-store enqueue finding 均保持
**CLOSED-IN-PLAN**；下面只裁决修复后仍开放的新问题。

## 2. Accepted findings

### S21-CTRL-FINAL3-001 — ACCEPTED — Medium — broad recover 不能表达 correlation-safe recovery

Flash M1 成立，而且是当前 API 自身的 code-generation gap，不只是未来 worker 的纪律问题：

- `JobStoreProtocol.recover(scope)` 是 tenant-wide bulk API；target §4.2.7 要它恢复所有过期
  leased/cancel-requested attempt，没有 correlation 排除条件。
- target §4.3 又要求 future caller 只恢复 `NO_HOST_RUN` 对应 attempt 与无 correlation attempt，
  但该 caller 无法把具体 attempt/correlation 传给 bulk API。一次调用就可能同时 abandon 另一条
  已观测为 `host_created`/`host_running` 的 attempt。
- `test_active_host_returns_wait_never_recovers_or_creates_new_attempt` 与 broad recover 当前语义无法
  同时成立；`recover-first` race test 又要求确实存在一个可精确赢得竞态的 recover 分支。

**Required fix**：保留 public `JobService.recover(scope)`，但不得继续把它写成 bulk store delegate。
Terra 必须把唯一安全算法写成：

1. `PostgresJobStore.recover(scope)` 只恢复以 SQL `NOT EXISTS agent_run_correlations` 证明**从未提交
   correlation** 的 expired attempt；它不得触碰任何 correlation-attached attempt。
2. 在 `JobStoreProtocol` 增加 exact targeted method
   `recover_agent_run_after_no_host(scope, correlation_id, observation_sha256)
   -> JobRecoveryResult | None`。它在同一 PG transaction 锁 job/attempt/correlation，只有 correlation
   仍为 current attempt、state=`reserved`、persisted missing observation fingerprint 与参数完全相等、
   lease 已过期、没有 later fence/attempt 时才恢复这一条；任一前提已变化返回 `None`，零 mutation、
   receipt、event。
3. `JobService.recover` 的固定顺序为：列出 expired committed correlations → 对每条执行既有
   repository-get → Host-read → strict-map → reconcile；仅对 `NO_HOST_RUN` decision 调 targeted
   recovery；`HOST_ACTIVE_WAIT`/terminal/stale/invariant 均不得进入 generic recovery；最后调用一次
   store `recover(scope)` 收敛无 correlation attempts。返回 tuple 只含本调用实际产生的
   `JobRecoveryResult`，顺序必须固定。
4. 补 PG two-engine barrier，证明 active correlation 与一个 no-correlation/NO_HOST_RUN attempt 同时存在
   时只恢复允许的 attempt；observation fingerprint/state/fence 任一在 targeted transaction 前变化均
   no-op；禁止新 attempt/第二模型入口。
5. 记录不可消除的跨 store residual：已经取得 start authorization、但在 Host ensure 前被长时间暂停并
   跨过 lease expiry 的 caller，仍可能与后续 recovery 形成 read-to-entry TOCTOU。Slice 2.2 必须以
   immediate Host entry、heartbeat/governance、re-observe/cancel owner 收敛；本 slice 只保证同一
   correlation 的 Host ensure at-most-once，不得宣称 distributed exactly-once。

### S21-CTRL-FINAL3-002 — ACCEPTED — Low — complete 的 cancel/deadline 同时成立顺序未锁定

Flash L2 成立。heartbeat、fail、recover 与 terminal reconciliation 已统一 cancel-first，但 complete
只写“cancel intent 或 deadline 优先”。

**Required fix**：固定 complete 同时命中时 `cancel intent → deadline → success`，写 cancelled state/
receipt/event，不写 deadline/success receipt；补 exact test。

### S21-CTRL-FINAL3-003 — ACCEPTED — Low — reserved run ID 的 Host enforcement owner 未锁定

Flash L3 成立。target 给出格式，却没有明确 invalid ID 在 SQLite 写入前由谁拒绝。

**Required fix**：`RunRegistry.ensure_reserved_run` 是格式校验唯一 owner；必须在开启 write transaction/
写 SQLite 前拒绝非 `run_` + 32 位小写 hex，抛固定无敏感 `ValueError`，零 Host side effect。executor/
Host 委托不得另建第二 validator；PG DTO/DDL 仍独立执行同一格式不变量。补 invalid matrix 与 no-write test。

### S21-CTRL-FINAL3-004 — ACCEPTED — Low — ready deadline terminal state 的 safe observation 未固定

Flash L4 成立。claim 前收敛已过 deadline 的 ready job 时，target 未锁 `safe_failure_code` 与 event。

**Required fix**：固定为 job=`failed`、`safe_failure_code=deadline_exceeded`、单一
`job_deadline_exceeded` event、无 attempt/lease/receipt；同一 job 重放不追加 event。补 exact test。

### S21-CTRL-FINAL3-005 — ACCEPTED — High — master Slice 2.1 与 target 已发生显式 contract drift

Controller 以 control/design truth 直接复现，MiM 的“与 master 无冲突”结论不成立：

- master `docs/plans/2026-08-10-investment-platform-restoration.md:3754` 把 owner/allowlist 锁在
  `dayu/host/job_contracts.py`、`dayu/host/job_service.py`、`dayu/investment/composition.py`、
  `dayu/startup/platform.py` 等；target 改为 `investment.domain.jobs`、`storage.protocols`、
  `services.job_service`，并明确不改后两文件。
- master `:3755` 要求 `JobHandlerProtocol`；target 选择 descriptor-only registry，明确本 slice 不定义
  invocation protocol。
- master `:3758` 写“missing correlation 安全重建”；target 正确地禁止为 claim→reserve crash 的旧
  attempt 补建 correlation，只允许 lease-expiry recovery。

这些是文件 ownership、public API 与 crash-recovery 行为的实质变化，不能用“能力边界而非 package owner”
解释为 master 未变。

**Required fix**：本轮 Terra allowlist 扩为 target plan、当前 fix artifact、master plan 三个文档。
必须只修订 master Slice 2.1 `Allowed/API/Invariants/Completion/Tests` 五行，使其成为 target 的高层摘要：
investment pure domain + storage protocol/store + Service registry/reader + Host reserved identity；
descriptor-only registry，execution protocol/handler 注册归 Slice 2.2/2.3；correlation missing 不补建旧
attempt；public Service recovery 使用 correlation-safe orchestration；其余 Phase 2 目标与 Slice 2.2/2.3
边界不变。master 状态/Phase 1 accepted history不得改写。

## 3. Rejected or corrected observations

- MiM 的 `PASS / no master conflict`：**REJECTED-WITH-REASON**；它与 master `:3754-3758` 的直接文本
  不一致，不能覆盖 design/control truth。
- Flash M1 的“future 运维直连 store”表述不是 public product guarantee；真正 accepted root cause 是
  Service 无法用 tenant-wide bulk store API表达自己已经判定的 per-correlation eligibility。Required
  fix 因此收敛在 Service orchestration + 两个明确 store primitives，而不是开放任意 caller。
- Flash 对 TOCTOU 的描述被接受为 residual，不被伪称本 slice 可在两个数据库间实现 exactly-once。

## 4. Next gate

Terra 只修改 target plan、master Slice 2.1 五行与本轮 existing final-codegen fix artifact；production、
tests、README 和全部 source review artifact 冻结。修复必须逐项映射
`S21-CTRL-FINAL3-001..005`，并证明 `S21-CTRL-FINAL2-001..007` 无回归。之后仍由两名未参与修复的
capable reviewer 做 final corrective re-review；Controller open H/M/L 归零前不得进入 Flash
implementation或创建 accepted plan commit。
