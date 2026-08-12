# Slice 2.3 Item 6 Recovery Errors / Receipt Owner — MiMo Plan Re-Review

- 日期：2026-08-12 23:15:00 +0800（本机系统时钟）
- 状态：REVIEW COMPLETE / PASS
- Gate：Gateflow Item 6 corrective plan re-review；本 artifact 只宣 plan review 结论，不宣 code acceptance
- 分支：`codex/investment-platform`
- 当前 HEAD / accepted corrective-plan commit：`3f0de579e1c95b428b61e046bae2a0583a4e76d6`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Master control：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Fix artifact：`docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md`
- Target FINAL FROZEN candidate SHA-256：`e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c`
- Master FINAL FROZEN candidate SHA-256：`9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1`
- Fix artifact SHA-256：`56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2`
- 模型路由：MiMo 只承担独立 plan review，不参与实现

## 1. SHA-256 冻结验证

MiMo 已直接计算并核验以下 SHA-256：

| 文件 | 预期 SHA-256 | 实际 SHA-256 | 结论 |
|---|---|---|---|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c` | `e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c` | ✅ 匹配 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1` | `9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1` | ✅ 匹配 |
| `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md` | `56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2` | `56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2` | ✅ 匹配 |

三份 frozen 文件字节一致，review 基础有效。

## 2. Fix artifact 逐项审查

### 2.1 S23-I6-RECOVERY-ERROR-01：无 typed code 的 Job/Schedule repository error 不能稳定生成 persisted_invariant

**Fix 裁决**：`accepted`。

**审查**：

1. **直接证据成立**：`dayu/investment/domain/jobs.py:233-234` 的 `JobRepositoryFailureError` 确实只是无字段的 `RuntimeError` subclass，docstring 只承诺 closed repository failure，不携带 cause 细节或 typed `code`。`dayu/investment/domain/schedules.py:167-168` 的 `ScheduleRepositoryError` 同样如此。
2. **矛盾成立**：target pre-edit §9 authoritative table 已将 `JobRepositoryFailureError / ScheduleRepositoryError` 统一映射 `SourceServiceUnavailableError(unavailable)`，但 §3.4/§5 三处写 `persisted_invariant`，两套合同互相矛盾。
3. **Fix 方案合理**：统一精确映射 `SourceServiceUnavailableError(unavailable)` 是最小且 owner-correct 方案。禁止 message/cause/SQLSTATE/row shape 分支是正确的——没有 typed code 时，按 message 分支会制造未声明的 public contract。
4. **Source repository carve-out 正确**：`SourceSyncRepositoryFailure(code)` 由 Source 自己拥有 closed typed code，`persisted_invariant` 保持原语义，不因 Job/Schedule 异常收窄而删除或改名。
5. **可观测性裁决合理**：当前 public surface 诚实地丢失 infra/tamper 细分。若产品未来必须公开区分，另开 typed Job/Schedule repository-error contract plan；当前 Slice 不得猜。

**target §9 authoritative exception table 验证**：

| Downstream exception | Source public action | 与 fix 一致性 |
|---|---|---|
| `JobIdempotencyConflictError` | 原样传播 | ✅ |
| `ScheduleVersionConflictError` | 原样传播 | ✅ |
| `JobInputError` / `ScheduleInputError` | `SourceServiceInputError(invalid_input)` | ✅ |
| `JobRepositoryFailureError` / `ScheduleRepositoryError` | `SourceServiceUnavailableError(unavailable)` | ✅ 与 fix 一致 |
| `JobNotFoundError` / `JobStateConflictError` / `JobCorrelationInvariantError` / `JobGovernanceRequiredError` | `SourceServiceUnavailableError(persisted_invariant)` | ✅ source fixed descriptor lookup/enqueue 不应观察到这些 durable drift |
| `JobLeaseLostError` / `JobDeadlineExceededError` | 本调用集合不可达；若 callee 违约抛出，收窄为 `SourceServiceUnavailableError(persisted_invariant)` | ✅ |
| `ScheduleInvariantError` / `ScheduleExecutionUnavailableError` | `SourceServiceUnavailableError(persisted_invariant)` | ✅ |

**target §15 STOP conditions 验证**：已新增"为区分 Job/Schedule repository infra failure 与 persisted tamper 而检查异常 message、SQL/row shape、cause 或自由字符串，或在现有无 typed-code 异常上伪造 `persisted_invariant`"作为 STOP 条件。✅

**target §16 residual 验证**：已新增 item 9："Job/Schedule 既有 repository failure surface 没有 typed code，因此 Source public facade 只能稳定暴露 `unavailable`，不能区分 infra failure 与 persisted drift。"✅

### 2.2 S23-I6-RECEIPT-OWNER-02：JobService lookup 与 Source facade receipt reconstruction 职责倒置

**Fix 裁决**：`accepted`。

**审查**：

1. **直接证据成立**：`dayu/services/job_service.py:519-545` 的 `JobService.enqueue` 拥有 registry gate、Store enqueue 与 post-commit wakeup publish；它不是 Source payload parser owner。`dayu/investment/domain/jobs.py:1057-1089` 的 `JobEnqueueReceipt` 构造要求 `state is JobState.READY`。
2. **矛盾成立**：target pre-edit §3.4/§5.1 写 `JobService` 重建 receipt，但 §9 authoritative table 已把 `JobRepositoryFailureError / ScheduleRepositoryError` 统一映射 `SourceServiceUnavailableError(unavailable)`，与 generic lookup owner 同时冲突。
3. **Fix 方案合理**：`JobStoreProtocol` 与 `JobService.get_by_idempotency_key` exact 返回 `JobIdempotencyRecord | None`；`JobService` 只 read-only delegate 一次并原样返回，不 parse Source payload、不比较 caller intent、不构造 receipt、不 publish、不 mutation。
4. **Receipt owner 正确**：`InvestmentSourcesService.enqueue_manual_sync` 在 lookup hit 后依次 strict parse persisted manual Source payload、比较 caller intent、验证 record/descriptor/tenant/key/payload/hash/time identity；全部通过后才唯一构造 `JobEnqueueReceipt(..., state=JobState.READY, idempotency_reused=True)`。

**target §3.4 JobIdempotencyRecord 验证**：

- 精确字段：`tenant_id: TenantId`、`definition_id: UUID`、`job_id: UUID`、`descriptor: JobHandlerDescriptor`、`idempotency_key: str`、`payload: CanonicalJobDocument`、`payload_sha256: str`、`request_fingerprint: str`、`available_at: datetime`、`deadline_at: datetime` ✅
- 构造期 typed parse/canonical re-encode 只验证 generic `CanonicalJobDocument` 与 outer payload SHA、aware time/identity ✅
- source payload schema 的 strict parse 与 caller-intent compare 仍只由 `InvestmentSourcesService` 拥有 ✅
- `JobService.get_by_idempotency_key` 只 read-only 委托 Store 一次并原样返回 `JobIdempotencyRecord | None` ✅

**target §5.1 Manual trigger 验证**：

- 步骤 1：strict request validation，按 §3.4 固定公式构造 manual key 与 caller-intent fingerprint；调用 `JobService.get_by_idempotency_key`，该 lookup 必须发生在任何 current binding/status/version 读取之前 ✅
- 步骤 2：lookup 命中时 strict parse persisted manual payload，验证 tenant、fixed job type/key、subscription、trigger、expected version、available/deadline、caller-intent fingerprint、payload canonical bytes/SHA 和 record identity。exact 则直接重建并返回同一个 `READY/idempotency_reused=True` 原 enqueue receipt ✅
- caller intent drift 抛 `JobIdempotencyConflictError`；Store/record persisted tamper 经 `JobRepositoryFailureError` 统一精确映射 `SourceServiceUnavailableError(unavailable)` ✅

**target §5.2 Crash-safe schedule draft 验证**：

- `ScheduleService.get_by_key` 具有相同同步签名并只委托 tenant-scoped Store read ✅
- 命中时返回当前 definition projection 供 Source facade 核对 immutable creation intent ✅
- Store 命中 row 但 canonical payload/descriptor/time/immutable definition 无法构造时精确抛 `ScheduleRepositoryError`，ScheduleService 原样传播，Source facade 统一精确映射为 `SourceServiceUnavailableError(unavailable)` ✅

## 3. Named test 验证

- 命名测试总数：158 项（从 157 项增加 1 项）✅
- 新增测试：`test_job_service_idempotency_lookup_returns_record_without_receipt_reconstruction_or_publish` ✅
- 该测试必须证明 `JobService` 逐次只委托 Store 并原样返回 exact record 或 `None`，且不构造 receipt、不调用 wakeup publisher、不读取 current Job projection、不 mutation ✅
- manual lost-response named test 同步改名，显式锁定"strict persisted Source intent validation 完成后，只有 Source facade 构造 READY/reused receipt" ✅
- 既有 exhaustive Source exception mapping test 扩断言，不再新增重复 test：四个 Job/Schedule 调用 seam 分别注入 repository failure，统一 assert `SourceServiceUnavailableError(unavailable)` 且禁止 message/shape 分支 ✅

## 4. Architecture / best-practice / optimality / overengineering / overcoupling 审查

- **Architecture boundary**：generic JobService 只暴露 generic immutable record；Source schema 与 caller intent 仍由 InvestmentSourcesService 拥有，依赖方向不反转 ✅
- **Best practice**：stable public error 必须由 typed discriminator 驱动；没有 typed code 时选择单一 closed `unavailable` 比解析 internal message 更可靠、可测试 ✅
- **Optimal solution**：本 Slice 不需要扩 Job/Schedule error hierarchy；统一映射是满足当前用户可见语义的最小修复 ✅
- **Overengineering**：拒绝为两条 recovery 路径新增 wrapper、adapter、compat alias 或第二 receipt builder ✅
- **Overcoupling**：read-only lookup 不复用 enqueue/publish 路径，Source validation 不下沉到 jobs domain ✅

## 5. Scope 一致性审查

本 candidate 只写三份 docs：

1. `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` ✅
2. `docs/plans/2026-08-10-investment-platform-restoration.md` ✅
3. `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md` ✅

明确零修改：production、tests、README、CI、migration、现有 review/acceptance artifacts、Item 1 WIP ✅
不新增 public method/type/error code，不扩大 §11 production/test/docs allowlist 或 Item 6 exact write set ✅

## 6. Master control 一致性审查

master control `docs/plans/2026-08-10-investment-platform-restoration.md` 顶部状态已更新为：
"PHASE 2 SLICE 2.3 ITEM 6 CORRECTIVE CANDIDATE；IMPLEMENTATION FROZEN；AWAITING FRESH SAME-SHA DEEPSEEK FLASH + MIMO PLAN REVIEW；ACCEPTED CORRECTIVE-PLAN COMMIT `3f0de57` SUCCEEDED" ✅

Slice 2.3 evidence index、revision changelog 与 Slice 2.3 current gate 摘要已同步更新 ✅

## 7. Open question 审查

无 open question。fix artifact 的两个 Controller finding 均已 accepted 并完整集成到 target/master，无遗留 blocking question。

## 8. 结论

**PASS / open H/M/L=0/0/0**。

MiMo 独立确认：
1. 三份 frozen SHA-256 字节一致；
2. Item 6 fix 的两个 Controller finding（RECOVERY-ERROR-01、RECEIPT-OWNER-02）均 accepted，直接证据成立，矛盾真实存在，fix 方案合理且最小；
3. target §3.4/§5.1/§5.2/§9/§12/§13.1/§15/§16/§17 已正确集成 fix 内容，合同一致；
4. 命名测试从 157 项增至 158 项，新增测试精确锁定 JobService exact delegation owner；
5. architecture/best-practice/optimality/overengineering/overcoupling 审查无问题；
6. scope 一致，未超出 docs-only 修正范围；
7. 无 open question。

本文不宣称 code pass、accepted commit 或 ready-to-open-draft-PR。
