# Code Re-review — Slice 2.3 Item 8 Redis fixture prerequisite（state/storage）

## Scope

- **Mode**: Gateflow-governed second independent current-changes re-review；仅复核 post-fix Redis prerequisite candidate，不推进 gate、不修代码。
- **Repository / branch / HEAD**: `/Users/wsk/workspace/dayu-agent`；`codex/investment-platform`；`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Selected base**: accepted-plan HEAD `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Included candidate**: `tests/integration/investment/test_redis_queue_wakeup.py` = `28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`；canonical diff = `6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`。
- **Fix artifact**: `docs/reviews/code-review-fix-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`。
- **Source state/storage review（只读、不回写）**: `docs/reviews/code-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md` = `c94902e2a21c4d600e741b67b5e53c27135f903e9ec26ae318bddc675c4f076b / 104 / 9601`。
- **Accepted plan**: `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Output file**: `docs/reviews/code-rereview-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md`。
- **Excluded preserved WIP**: Item 8 exact-four（仅核身份，不作为 finding）：`.github/workflows/ci-mainline.yml`、`.github/workflows/ci-pr-extended.yml`、`tests/README.md`、`tests/investment/test_platform_migrations.py`。
- **Parallel review coverage**: 无；本 lane 独立检查 storage/FK/dynamic SQL/transaction/definition identity/teardown/admission。
- **Execution boundary**: 未运行 integration、PostgreSQL、Docker、network；未执行 Git mutation。

## Findings

### CRR-SS-001-已修复-[中]-cleanup owner 未绑定固定 tenant，会删除另一租户同 job type 的合法行并让 downgrade 假绿

- **入口/函数**: fixture teardown `migrated_jobs_database()` 调用 `_clear_migrated_jobs_database()`。
- **文件(行号)**: `tests/integration/investment/test_redis_queue_wakeup.py:414-459`，尤其 owner predicate `437-456`；真实 definition 唯一约束位于 `dayu/investment/storage/migrations/versions/0003_durable_jobs.py:119-139`；本测试固定 tenant 位于 Redis 文件 `74`、`504-507`。
- **输入场景**: 在该 function-scoped 数据库中构造第二个 schema-valid organization；为它插入 `job_type='test.redis.integration'` 的 definition、job run，以及只落在当前 exact-four cleanup 表中的合法 descendants。该反例不违反任何约束：`organizations.id` 可取另一 UUID，而 `job_definitions` 只要求 `(tenant_id, job_type)` 唯一，并不要求 `job_type` 全局唯一。
- **实际分支**: helper 使用 bootstrap superuser engine；四个 child DELETE 与最终 `job_runs` DELETE 都只要求 definition 的 `job_type = :job_type`。predicate 没有 `definition.tenant_id = :tenant_id`，因此遍历并删除所有 tenant 下同名 definition 的 run/children。若该 foreign run 不带 source/schedule/correlation 等 tuple 外依赖，transaction 正常提交，随后 0006 看到空 `job_runs` 并继续 downgrade。
- **预期行为**: cleanup 只能删除本测试真实创建的 owner identity，即固定 `_TENANT_UUID` 与 `_JOB_TYPE` 的交集；另一 tenant 的同名 job type 必须保留，使 0006 empty-table admission fail closed。
- **实际行为**: `_JOB_TYPE` 被当作跨 tenant 的唯一 owner discriminator，扩大了删除集合；第二 tenant 的合法 root 和 exact-four descendants 被静默擦除，migration lifecycle 返回成功。
- **直接证据**:
  - Redis test 的真实 runtime scope 固定为 `_TENANT_UUID = UUID(DEFAULT_ORGANIZATION_ID)`，`_scope()` 始终用该 tenant（Redis 文件 `74`、`504-507`）。
  - 两处 DELETE 参数只有 `{"job_type": _JOB_TYPE}`，SQL 在 definition join 后仅检查 `definition.job_type = :job_type`（Redis 文件 `437-456`）。
  - `job_definitions` 的数据库 identity 是 `UNIQUE (tenant_id, job_type)`（0003 `137-139`）；`organizations` 允许多个不同 UUID 行（0001 `154-165`），所以反例确实 schema-valid。
  - `job_runs` 以 `(tenant_id, definition_id)` 指向 definition（0003 `180-210`）；因此同 job type 的第二 tenant root 会被当前 join 命中，而不是因 FK 被排除。
  - 0006 downgrade 的数据 admission 只检查 `SELECT count(*) FROM job_runs`（0006 `1572-1579`）。错误删除后没有剩余 root 能触发拒绝；0005 与 0004 分别只保护自身 source/schedule 数据，不能恢复已删除的 foreign job root。
- **影响**: ephemeral integration teardown 会掩盖跨 tenant 装配/fixture 污染，给 migration fail-closed gate 产生 false-green；不会直接删除生产库数据，但会降低该前置测试作为 schema/migration 证据的可信度。
- **建议改法和验证点**:
  1. 在 child 与 root 两处 owner predicate 同时增加 `definition.tenant_id = :tenant_id`（或等价的 `owned_run.tenant_id = :tenant_id`），并绑定模块现有 `_TENANT_UUID`；owner tuple 明确为 `(_TENANT_UUID, _JOB_TYPE)`。
  2. hostile oracle 在同一临时数据库插入第二 tenant、同 `_JOB_TYPE`、无 tuple 外依赖的合法 definition/run/children；调用 cleanup 后读回 foreign root/children仍存在，并确认 `run_alembic_downgrade()` 在 0006 拒绝。正常 default-tenant exact-three 路径仍应清零并通过。
- **修复风险（低/中/高）**: 低；仅收窄两个 SQL predicate 与 bind 参数，不改变 table tuple、DELETE 顺序或 migration 实现。
- **严重程度（低/中/高/严重）**: 中。

## Targeted re-review evidence

### Dynamic SQL 与 table set

- `_SCHEMA` 与 `_MIGRATED_DATABASE_CLEANUP_CHILD_TABLES` 均为模块内 literal；动态 identifier 不来自输入，`job_type` 使用 bind parameter，没有 identifier/value injection 面。
- exact-four child 是 `job_events -> job_attempt_receipts -> job_leases -> job_attempts`。真实 0003 DDL 证明四表都存在 `tenant_id`、`job_run_id`；receipts/leases 还以 `(tenant_id, attempt_id)` RESTRICT 引用 attempt，所以两者先于 attempts 删除，顺序成立。
- `agent_run_correlations`、`job_schedule_occurrences`、`source_sync_runs`/`source_sync_operations` 未进入 cleanup。它们引用 Redis-owned run/attempt 时会阻止 attempts 或 run DELETE，并使整个 transaction rollback，符合跨 domain fail-closed；本 finding 是 predicate 可区分却漏掉的跨 tenant 同 type 情形。

### Transaction、teardown 与资源释放

- 所有 DELETE 位于同一个 `cleanup_engine.begin()`；任一 FK/SQL 异常会回滚并传播，`finally` 始终 dispose，且异常会阻止后继 `run_alembic_downgrade()`。
- pytest dependency teardown 先执行 `job_runtime` finalizer：关闭 Redis adapter、dispose app engine、drop temporary login；随后才执行 `migrated_jobs_database` cleanup/downgrade；`lifecycle_database` 最后 FORCE drop database，session fixture 最后按 owner label 清 PG container/network。post-fix 未破坏该次序。
- helper 不删除 `job_definitions`；正常 owner run 清空后，0006/0005/0004 依次回滚，0003 最终精确删除 Job tables，definition 不构成残留 blocker。

### Migration admissions

- 0006 在 NOWAIT lock 与 catalog/dependency checks 后要求 `job_runs` 全表为空；0005 对三张新表、source run durable 字段、snapshot version、外部依赖和 role member fail closed；0004 同时计数 `job_schedules` 与 `job_schedule_occurrences`。candidate 没有修改或弱化这些 migration owners。
- 由于 cleanup 在 admission 前以 bootstrap 权限执行，admission 只能观察 cleanup 后状态；因此 owner predicate 的完整性是本 finding 的根因，不能由后继 migration 自愈。

### Validation、AGENTS 与文档

- fix artifact 记录单进程 exact-three `3 passed`、pyright、Ruff、architecture 与静态 oracle通过；这些证据覆盖正常 default tenant path，但三个测试所有 JobService 调用都使用 `_scope()` 的同一 `_TENANT_UUID`，没有覆盖第二 tenant 同 `_JOB_TYPE` 反例，不能关闭 CRR-SS-001。
- 新 helper、常量和 docstring 满足相关 AGENTS 类型/docstring/模块级 helper 约束；未发现反向依赖或 production boundary 变化。
- `tests/README.md` 已记录 Redis lane、真实 PG/Redis、手工命令与不隐式 pull。此次内部 teardown owner 收窄不改变用户命令、marker 或 catalog；README `NO CHANGE` 本身不是 finding。

## Open Questions

- 无。

## Residual Risk

- 本 reviewer 按冻结边界未重跑 integration/PG/Docker；正常路径运行证据来自 fix artifact，hostile verdict 来自真实 DDL/FK 与 SQL predicate 的静态可构造反例。
- receipts/leases 的 0003 attempt FK 与 job-run FK 是分别约束；当前 DELETE 顺序满足两类 FK。若后续需要把逻辑上的 attempt-to-run 一致性也作为 teardown gate，必须由 schema/test owner另行定义，不能假定现有两条 FK已经证明该事实。

## Verdict

- **FAIL**
- **Fresh open H/M/L**: `0 / 1 / 0`
- **Blocking finding**: `CRR-SS-001`

## END identity

- Candidate diff: `6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`。
- Redis file: `28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`。
- Fix artifact: `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`。
- Accepted plan: `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- Source state/storage review: `c94902e2a21c4d600e741b67b5e53c27135f903e9ec26ae318bddc675c4f076b / 104 / 9601`。
- HEAD: `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Item 8 exact-four: START identities unchanged。
