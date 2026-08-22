# Slice 2.3 Item 8 Redis fixture prerequisite plan fix

## 1. Gate 与身份

- **Role**：Gateflow plan-fix worker；不是 Controller 或 reviewer。
- **Current gate**：`plan fix`。
- **Source review**：`docs/reviews/plan-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md`，`a229e11d44b54d8525fcfca59105ffe5f0adba9d47fa981f42cfaf9c8ad1fa8c / 72 / 10604`，verdict `FAIL / open H/M/L=0/1/0`。
- **Plan START**：`docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md`，`8bfe0b0b693be2c5ad013bc7e05e8ae4f36189490c8411a752c07b8aec39f49d / 341 / 24559`。
- **Plan END**：`987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Persistent write set**：上述 plan 与本 fix artifact，exact two。
- **Boundary**：未修改 source review、Item 8 WIP、代码、测试、README、workflow 或其它 path；未运行测试、PG、Docker、network；未 stage/commit/push/PR；未进入 re-review。

## 2. Controller accepted finding

### PR-SS-001-已修复-中-删除 `job_schedules` 会绕过 0004 的现成 fail-closed readback

- **Controller disposition**：accepted；本轮唯一 finding，无 rejected/deferred/needs-more-evidence finding。
- **问题**：Redis path只拥有 job rows。`job_schedule_occurrences` 可通过 `job_run_id` 引用 Redis-owned job，属于必须清除的真实 FK descendant；`job_schedules` 不引用 job，不属于 Redis cleanup ownership。删除 parent 会让 `0004` 无法发现跨域 schedule row。
- **修复**：从 §4.1 frozen tuple 删除 `job_schedules`；保留 `job_schedule_occurrences`；将 tuple 定义收窄为删除 Redis-owned jobs 所需的真实 FK descendants。
- **权威 readback**：不新增 helper count。`0004` 现有 `job_schedules + job_schedule_occurrences` admission继续检查未被Redis fixture删除的schedule parent；存在跨域 row时正式 downgrade必须fail closed。
- **同步位置**：plan header、§4.1 tuple/ownership、§4.4 teardown sequencing、§5.1 data ownership、S23-I8-RFP-01 exact changes、§8.3 independent review oracle。
- **未改变**：唯一test-file implementation scope、one-transaction/engine/login/database/container顺序、migration合同、exact-three full-file gate、Item 8 WIP boundary。
- **Fix self-status**：`已修复`；最终状态以fresh independent re-review为准。

## 3. Before / After

| Surface | Before | After |
|---|---|---|
| Cleanup tuple tail | `job_attempts, job_runs, job_schedules` | `job_attempts, job_runs` |
| Occurrence child | retained | retained，明确因optional `job_run_id` FK属于真实descendant |
| Schedule parent | Redis fixture主动删除 | 不删除；交给`0004`双表count权威检查 |
| Helper-side count | none | none |
| Implementation allowlist | exact-one Redis test | unchanged |
| Plan state | `PLAN DRAFT / AWAITING INDEPENDENT PLAN REVIEW` | `PLAN FIX APPLIED / AWAITING FRESH INDEPENDENT RE-REVIEW` |

## 4. Mechanical validation

- START identities、branch/HEAD、index empty与preserved WIP通过只读preflight。
- `job_schedules` 已从 §4.1 code tuple 删除；仅在说明“排除/不删除/由0004检查”的current-truth prose出现。
- `job_schedule_occurrences` 仍在tuple，且 §4.1、Slice、review oracle三处显式要求保留。
- Source review保持 `a229e11d44b54d8525fcfca59105ffe5f0adba9d47fa981f42cfaf9c8ad1fa8c / 72 / 10604`。
- Item 8 exact-four END identities：
  - `.github/workflows/ci-mainline.yml`：`697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`；
  - `.github/workflows/ci-pr-extended.yml`：`0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`；
  - `tests/README.md`：`798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`；
  - `tests/investment/test_platform_migrations.py`：`8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`。
- Validation仅为文档身份、occurrence/stale、UTF-8/LF/CR/NUL、write-set与status机械检查；按handoff未运行implementation/test/PG/Docker。

## 5. Remaining 与 handoff

- **Remaining**：fresh independent re-review只复核 `PR-SS-001`、plan END identity与是否引入新blocker。
- **Blocking questions**：none。
- **Residual risk**：沿用plan §10；本fix未新增或重分类风险。
- **Status**：`READY FOR RE-REVIEW`，不自评Gateflow PASS，不授权implementation或accepted commit。
