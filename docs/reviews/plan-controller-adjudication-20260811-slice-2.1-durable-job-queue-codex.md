# Controller Adjudication：Slice 2.1 final plan re-review

- **Gate**：Slice 2.1 final corrective plan review adjudication
- **Baseline**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Source reviews**：
  - `docs/reviews/plan-final-rereview-20260811-slice-2.1-durable-job-queue-mim.md`
  - `docs/reviews/plan-final-rereview-20260811-slice-2.1-durable-job-queue-mimo.md`
- **Conclusion**：`PLAN FIX REQUIRED / OPEN H/M/L = 0/4/0`
- **External actions**：未授权且未执行 commit、push、PR、deploy、live、paid action。

## 1. Review evidence

MiM final review initially concluded `PASS / open 0` and retained that conclusion after
Controller follow-up. MiMo initially concluded `PASS / open 0`, then amended its artifact to
`CONDITIONAL PASS / open 0/1/0` after the Controller challenged four code-generation-readiness
boundaries. MiMo accepted the Host observation owner/injection gap but treated the other three
questions as inferable.

The Controller does not accept inference or repository convention as a substitute for a public
contract in an architecture-sensitive PostgreSQL state-machine plan. Gateflow requires the
implementation worker to avoid choosing DTO shape, handler lifecycle, cross-layer ownership or
idempotent return semantics.

## 2. Finding adjudication

### S21-CTRL-FINAL-001 — ACCEPTED — exact public DTO schemas are missing

The plan names fourteen public DTOs but gives exact fields for only the two decision DTOs. DDL
columns do not uniquely determine request/response DTO shape: for example, `JobClaim` may embed or
flatten `JobLeaseHandle`; `JobEnqueueRequest`, `JobEnqueueReceipt`, `JobCompletion`, `JobFailure`,
`JobRecoveryResult` and `AgentRunCorrelationObservation` are not table rows. Their optionality,
nested ownership and invariant-bearing constructors affect every Service/store/test signature.

**Required fix**：add an exact per-DTO field/type/default/invariant table or code blocks, including
which DTOs embed which other DTOs. Keep all fields explicit; no metadata/dict escape.

### S21-CTRL-FINAL-002 — ACCEPTED — JobHandlerProtocol is a public placeholder

The plan says `JobHandlerProtocol` is a stable API but does not define its method name, sync/async
kind, arguments or return type. The reviewer statement that Flash may choose a reasonable
signature is direct evidence of implementation-time invention. An unused public placeholder also
conflicts with the slice rule that future scheduler/worker behavior must not be smuggled into this
slice.

**Required fix**：either define the exact minimal stable protocol now, with descriptor property and
one fully typed invocation signature that Slice 2.2 can consume unchanged, or remove the invocation
method from Slice 2.1 and expose only an exact descriptor registry contract. The plan must select
one option and update tests/non-goals consistently.

### S21-CTRL-FINAL-003 — ACCEPTED, reviewer remedy corrected — Host observation owner is missing

The plan requires terminal reconciliation to read Host `get_run`, but does not define the narrow
reader protocol, injection owner or observation-to-store boundary. MiMo correctly identified the
gap, but its proposed `PostgresJobStore(..., host_run_reader=...)` remedy is rejected: the storage
implementation layer must not import or own Host access. This would violate the master dependency
rule and the current `dayu.investment.storage` package contract.

**Required fix**：keep Host observation in `JobService` or another Host/Application owner. Define a
neutral lower-level reader contract in the existing contracts layer if needed; inject it into the
Service, not the PostgreSQL store. The Service must map `RunRecord | None` into the exact strict
`AgentRunCorrelationObservation` DTO. `JobStoreProtocol`/`PostgresJobStore` must consume that DTO in
their terminal reconciliation transaction and remain free of Host imports/readers. The plan must
give exact constructors/signatures/composition wiring and add the real contracts file to the
allowlist.

### S21-CTRL-FINAL-004 — ACCEPTED — repeated reconciliation semantics are not defined

Job-row locking, terminal absorption and the receipt unique constraint prevent some corruption,
but they do not specify the second call's public action, whether it returns the already committed
receipt/result, or how repeated stale observations avoid duplicate `correlation_stale_attempt`
events. A uniqueness violation is not an idempotency contract, and `job_events` deliberately
allows multiple sequence numbers.

**Required fix**：define exact repeated-call behavior for every terminalized, stale and active
outcome. The second call must be deterministic, must not rewrite/duplicate receipts, must not append
duplicate transition events for an unchanged observation, and must return a specified decision.
Add named PG16 two-worker/replay tests for terminal-first, recover-first stale, active repeat and
Host transition between observations.

## 3. Controller decision and next gate

All four findings are `accepted`. They directly protect the master design goals: strict
`UI -> Service -> Host -> Agent` layering, PostgreSQL as the sole durable job truth, Host as the sole
Agent lifecycle truth, no cross-store transaction, and no implementation-time contract invention.

Terra owns the bounded plan fix. Production, tests and README remain frozen. After the fix, MiM and
MiMo must perform a new corrective plan re-review; Slice 2.1 may enter implementation only when both
reviews have durable artifacts and Controller-adjudicated open H/M/L equal `0/0/0`.
