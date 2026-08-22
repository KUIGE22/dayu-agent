# Code Re-review Round2 — Slice 2.3 Item 8 Redis fixture prerequisite（state/storage）

## Scope

- **Mode**: Gateflow-governed final independent current-changes re-review；仅复核 `CRR-SS-001` Round2 fix 与 post-fix storage regression，不推进 gate、不修实现。
- **Repository / branch / HEAD**: `/Users/wsk/workspace/dayu-agent`；`codex/investment-platform`；`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Selected base**: accepted-plan HEAD `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Included candidate**: `tests/integration/investment/test_redis_queue_wakeup.py` = `f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`；canonical diff = `26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`。
- **Round2 fix artifact**: `docs/reviews/code-review-fix-round2-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `f7a20c5dcd8e07f32c3f23c6c8019add3677a68117ec3354fa11a8d5bc436725 / 69 / 6453`。
- **Source finding artifact START**: `docs/reviews/code-rereview-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md` = `909efa5c3fca74dc7477e27f7ed71d9cae582972730a6de08e3430e5544050f8 / 88 / 10042`；本轮只把 `CRR-SS-001` 标题状态回写为“已修复”。
- **Accepted plan**: `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Output file**: `docs/reviews/code-rereview-round2-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md`。
- **Excluded preserved WIP**: Item 8 exact-four；仅核 identity，不审其内容、不作为 finding。
- **Parallel review coverage**: 无。
- **Execution boundary**: 未运行 integration、PostgreSQL、Docker、network；未执行 Git mutation。

## Findings

未发现实质性问题。

## Accepted finding closure

### CRR-SS-001 — CLOSED

- Redis test 的真实业务 scope 仍固定为 `_TENANT_UUID = UUID(DEFAULT_ORGANIZATION_ID)` 与 `_JOB_TYPE = "test.redis.integration"`（Redis 文件 `65-74`、`493-509`、`512-533`）。Round2 没有引入第二份 tenant/job-type 真源。
- 四类 child DELETE 先按 `child.(tenant_id, job_run_id)` 连接 `owned_run`，再要求 `owned_run.tenant_id = :tenant_id`，并按 `owned_run.(tenant_id, definition_id)` 连接 definition 后要求 `definition.job_type = :job_type`（`414-446`）。最终 root DELETE 使用相同 tenant/type owner（`447-459`）。
- 两次 execute 都绑定精确相同的 `{"tenant_id": _TENANT_UUID, "job_type": _JOB_TYPE}`。`tenant_id` 是标准库 `UUID`，目标 PostgreSQL 列也是 UUID；DSN 明确使用 `postgresql+psycopg`，没有字符串拼接、隐式 tenant context 或未消费参数。
- hostile 第二 tenant + 同 `_JOB_TYPE` 反例现被 `owned_run.tenant_id = :tenant_id` 排除；foreign children/root 均保留。0006 在 destructive DDL 前取得锁并对全表 `job_runs` 计数，foreign root 使其 fail closed，而不再出现 Round1 的 false-green。
- 同 tenant + 其它 job type 由 definition job-type predicate排除；`job_definitions` 的真实唯一身份是 `(tenant_id, job_type)`，`job_runs` 的真实 definition lineage 是 `(tenant_id, definition_id)`，当前 join 与 schema identity一致。

## Post-fix storage review evidence

### Dynamic SQL、FK 与 DELETE order

- `_SCHEMA` 与四个 table identifier 全是模块 literal；外部输入只进入 value bind。未发现 identifier injection、`CASCADE`、fallback 或第二 cleanup path。
- closed tuple 顺序是 `job_events -> job_attempt_receipts -> job_leases -> job_attempts`。真实 0003 DDL证明四表均含 `(tenant_id, job_run_id)` 并 RESTRICT 引用 `job_runs`；receipts/leases 另以 `(tenant_id, attempt_id)` RESTRICT 引用 attempts，所以在 attempts 前删除，顺序正确。
- `agent_run_correlations`、`job_schedule_occurrences`、source lineage 未纳入 cleanup。若它们引用本测试 owner run/attempt，attempt/root DELETE会被真实 FK 拒绝；整个 cleanup transaction 回滚且 downgrade 不运行，未削弱 cross-domain fail-closed。

### Transaction、rollback 与 teardown

- helper 的全部 child/root DELETE 位于单一 `cleanup_engine.begin()`；任一 SQL/FK 异常触发 rollback并传播。`finally` 无条件 dispose，且 `_clear_migrated_jobs_database()` 抛出时后继 `run_alembic_downgrade()` 不可达。
- pytest fixture依赖顺序未变：`job_runtime` 先 close adapter、dispose app engine、drop temporary login；随后 migrated database cleanup/downgrade；最后 lifecycle database FORCE drop，session PG cluster再按 owner label收敛。没有连接、role、database或container lifecycle回归。
- helper仍不删除 `job_definitions`。正常 owner `job_runs` 清空后，definition在0003回滚时随 Job tables 精确删除，不需要额外 cleanup 或 count/readback path。

### 0006 / 0005 / 0004 admissions

- 0006 仍执行 catalog/dependency检查、NOWAIT lock并要求 `job_runs` 全表为空；Round2只收窄前置 test teardown SQL，没有修改 migration。
- 0005 仍在线性化锁内拒绝三张新表业务行、source run durable字段、snapshot version、外部依赖及 role member；0004 仍同时计数 `job_schedules` 与 `job_schedule_occurrences`。tuple外 foreign evidence不会被 helper擦除。
- 复合 owner fix只移除 default tenant + Redis job type 的本测试根与正常 descendants；因此正常 exact-three teardown可通过，同时可构造 foreign evidence仍交给原 migration owners拒绝。

### Exact-three validation、AGENTS 与文档

- Round2 fix artifact记录完整 Redis 文件单进程 exact-three `3 passed in 7.72s`，并记录 pyright、Ruff、171 architecture tests、静态复合 owner oracle与零容器/network残留。三个测试名称/顺序/断言没有变，第三个 setup仍证明前一 migrated database teardown已成功完成。
- Controller冻结 exact-three，不新增第四个 hostile test。当前缺口可由两处相同 literal tenant/type predicate、真实 tenant-scoped UQ/FK以及0006全表count静态闭合；这不构成新的 blocker。
- 新代码仍是模块级私有 helper、严格类型签名与完整中文 docstring；没有生产边界、反向依赖或 public API变化。
- `tests/README.md` 已覆盖 Redis lane、真实依赖、运行命令与不隐式 pull；内部 owner predicate收窄不改变这些用户可见事实，`NO CHANGE` 合理。

## Open Questions

- 无。

## Residual Risk

- reviewer按冻结边界没有重跑 integration/PG/Docker；动态正常路径证据来自 Round2 fix artifact。本轮独立结论基于 candidate byte-level身份、真实 DDL/FK、fixture call chain 与 closed SQL predicate。
- exact-three没有动态构造第二 tenant同 type，但该分支已由显式 tenant bind封闭；未来若 Redis lane扩大 owner tenant或新增正常 descendant，test/migration owner需同步更新 closed owner tuple与FK顺序。
- receipts/leases的 attempt FK与job-run FK仍是分别约束；本 helper满足现有真实 FK delete order，本 prerequisite不声称验证二者的业务等价关系。

## Verdict

- **PASS**
- **Fresh open H/M/L**: `0 / 0 / 0`
- **CRR-SS-001 final status**: `CLOSED`

## END identity

- Candidate diff: `26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`。
- Redis file: `f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`。
- Round2 fix artifact: `f7a20c5dcd8e07f32c3f23c6c8019add3677a68117ec3354fa11a8d5bc436725 / 69 / 6453`。
- Accepted plan: `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- HEAD: `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Item 8 exact-four: START identities unchanged。
