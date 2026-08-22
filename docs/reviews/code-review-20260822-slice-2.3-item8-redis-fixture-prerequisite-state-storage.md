# Slice 2.3 Item 8 Redis fixture prerequisite — independent code review

## Findings

未发现实质性问题。

## Scope

- **Mode**：Controller-frozen bounded current-changes review；覆盖范围优先于 `deepreview` 的 generic current-changes scope。
- **Repository / branch / HEAD**：`/Users/wsk/workspace/dayu-agent`；`codex/investment-platform`；`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Accepted plan commit**：`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Included candidate**：仅 `tests/integration/investment/test_redis_queue_wakeup.py` 相对 HEAD baseline 的 diff。
- **Candidate diff SHA-256**：`e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`。
- **Candidate baseline**：`a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`。
- **Candidate END**：`f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`。
- **Implementation artifact**：`docs/reviews/implementation-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- **Accepted plan**：`docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Excluded scope**：Item 8 exact-four preserved WIP、其它 current changes、production、migration 和 shared fixture mutation；exact-four 仅核身份，不作为 finding。
- **Project instructions**：完整读取并应用仓库根 `AGENTS.md`；本变更保持完整中文 docstring、严格类型、模块级私有 helper、测试 ownership 与 README 职责边界。
- **Parallel review coverage**：无；该 candidate 是单文件 40-line bounded diff，主 reviewer 逐行完成 diff、真实 fixture 链、migration/FK 与 validation evidence 复核。

## Intent and implementation-path review

### 1. Root cause 与真实入口

- 第二个 Redis test 经 `JobService.enqueue()` 与 `claim()` 创建 `job_runs`、`job_attempts`、`job_leases` 和 `job_events`；真实 Postgres store 在 commit 或异常路径均关闭 session。
- baseline `migrated_jobs_database` 在 yield 后直接 downgrade；真实 `0006_job_request_identity.downgrade()` 在锁和 catalog/dependency 检查后读取 `job_runs` count，非空即 fail closed。
- candidate 在同一 owning fixture 的 finalizer 中先调用 `_clear_migrated_jobs_database()`，成功提交后才调用正式 `run_alembic_downgrade()`；没有修改 migration 或 production contract。

### 2. Dynamic SQL closedness

- `_SCHEMA` 是 module-private literal `dayu_platform`。
- `_MIGRATED_DATABASE_CLEANUP_TABLES` 是 module-private literal tuple；循环变量没有来自 fixture、test input、DSN、环境变量、反射或 catalog discovery。
- SQL 仅拼接上述 closed identifiers；没有值参数、外部 identifier、`CASCADE`、trigger/FK/RLS disable 或 fallback 路径。按当前隔离测试入口不存在 identifier injection 或 broad cleanup target 漂移。

### 3. 真实 FK set 与 child-first 顺序

- `source_health_alert_outbox` 引用 `source_health_snapshots` 与 `source_sync_runs`，因此最先删除。
- `source_health_states`、`source_sync_operations` 和 `source_health_snapshots` 均可引用 `source_sync_runs`；operation/run 还可绑定 job attempt/run。candidate 在这些 parent 前删除全部 source children。
- `job_schedule_occurrences` 可经 nullable `job_run_id` 引用 `job_runs`，因此保留在 tuple 并位于 job parent 前。
- `agent_run_correlations`、`job_attempt_receipts`、`job_leases` 引用 attempts/runs；`job_events` 引用 run；candidate 均在 `job_attempts -> job_runs` 前删除。
- 不引用 job 的 parent `job_schedules` 正确排除。任何 schema-valid schedule parent row都会留给真实 `0004` 的 `job_schedules + job_schedule_occurrences` count fail closed，而不会被 Redis fixture 擦除。
- `job_definitions` 是 `job_runs` parent，不是 descendant；删除 `job_runs` 后可由 `0003` 正式 downgrade 删除，无需扩大 cleanup tuple。

### 4. Transaction、dispose 与错误路径

- helper只创建一个 bootstrap engine，并以单个 `cleanup_engine.begin()` 包住 exact-order DELETE；正常退出时事务提交，任一 SQL/连接异常时 context manager 回滚并原样传播。
- `cleanup_engine.dispose()` 位于 `finally` 且唯一调用一次。cleanup 或 dispose 失败都会阻止后继 downgrade，未被吞掉、转换为 warning、skip 或 xfail。
- downgrade只在 cleanup成功返回后执行；`0006`、`0005`、`0004` 的 catalog/data/role admission与后续 self-check仍为真实权威路径。

### 5. Fixture、role、database 与 container lifecycle

- `job_runtime` 依赖 `migrated_jobs_database`，所以其 finalizer先关闭 publisher adapter、dispose app engine、drop temporary LOGIN/membership；随后 migrated database finalizer才用 bootstrap engine cleanup/downgrade。
- Postgres store的 enqueue/claim session在成功和异常分支均 commit/rollback并close；没有已知 checked-out app session穿越到 role drop或 migration locks。
- `lifecycle_database` 是 migrated fixture 的 dependency；其 FORCE database drop发生在 migrated finalizer之后。即使 cleanup/downgrade失败，错误仍可见，外围 owned database/container cleanup不会伪造 migration成功。
- Redis cluster与 migrated database是 sibling fixtures，但 dependent `job_runtime` 已先关闭跨资源 adapter；后续代码不依赖 sibling teardown相对顺序。PG/Redis container和network继续走既有exact owner-label cleanup。

### 6. 0004/0005/0006 fail-closed evidence

- `0006` 仍执行 identity lock、catalog、external dependency与 empty-`job_runs` admission；candidate只清理本fixture拥有的数据，没有test bypass。
- `0005` 仍以 ACCESS EXCLUSIVE NOWAIT lock后检查三张新表、durable source字段、snapshot版本、旧索引冲突、外部依赖和role membership。candidate不修改这些检查。
- `0004` 的two-table count仍能看到未由Redis fixture删除的`job_schedules`。occurrence必须先删以解除真实job FK；parent保留确保跨域污染仍失败关闭。

### 7. Test evidence 与第三个 setup 污染证明

- 文件只含三个module-scope tests；第二个test位于第三个之前，仓库pytest配置未启用随机/排序插件。
- 第三个test请求`job_runtime`，其依赖会先创建新database并执行`upgrade head`。若第二个test teardown未回到`0001`并删除cluster-global roles，第三个setup会在`0001`重建role时失败，正是历史复现路径。
- implementation artifact记录同一pytest process、完整文件、单次执行为`3 passed`。因此第三个test不仅被collect，其新database setup与`upgrade head`也实际成功；该证据足以证明当前复现的跨测试role污染已消失。
- 本 reviewer按handoff未复跑该integration证据；见Residual Risk。

### 8. Docs 与 AGENTS decision

- `tests/README.md` 已描述该文件的PG+pinned Redis 8.4目标、三项业务语义、独立process命令、pinned image和owner-label cleanup。
- candidate只改变fixture内部teardown，不改变命令、marker、test names、分层、owner label、镜像或用户runbook。`README = NO CHANGE`符合 `AGENTS.md` “先判断职责与当前代码是否不一致”的条件，也避免吸收excluded Item 8 WIP。
- 新helper和更新后的fixture均提供中文Args/Returns/Raises docstring；签名无`Any`/`object`，也未引入nested helper、shared glue seam或production coupling。

## Open Questions

- 无。

## Residual Risk

- 本review lane按Controller边界未运行integration、PostgreSQL、Docker或network；`3 passed`、Pyright/Ruff/architecture、image readback与owner `0/0`来自冻结implementation artifact，已做静态一致性复核但未由本reviewer复现。
- cleanup tuple与当前`0001`–`0006` migration DAG绑定。未来migration新增真实job FK descendant时，migration owner必须同步相关test lifecycle fixtures；这不影响当前冻结candidate正确性。
- `job_runtime`在yield前的既有partial-setup cleanup不属于本candidate diff；本变更未扩大该风险，当前validated入口也未触发它。

## Conclusion

- **Verdict**：`pass`。
- **Fresh open H/M/L**：`0/0/0`。
- 当前candidate可交回Controller裁定；本review不授权fix、implementation、stage、commit、push、PR或Gateflow advance。

## END identity

- **Candidate diff**：`e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`。
- **Candidate END**：`f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`。
- **Implementation artifact**：`003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- **Accepted plan**：`987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Branch / HEAD**：`codex/investment-platform / 9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Item 8 exact-four unchanged**：
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`；
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`；
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`；
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`。
