# Code Re-review

## Scope

- Mode: Gateflow code re-review，仅复核 accepted `CR-DOM-001` 与 post-fix 新 blocker。
- Review time: `20260822-095837+0800`，来自本机系统时钟。
- Reviewer: 原 domain/ownership 独立 reviewer；不是 Controller、fix writer 或 implementation writer。运行时未暴露更细 model identifier。
- Repository / branch / base: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform` / accepted-plan commit `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Reviewed post-fix candidate: binary diff `6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`；Redis file `28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`。
- Fix artifact: `docs/reviews/code-review-fix-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`。
- Implementation artifact: `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`，保持冻结。
- Included evidence: post-fix SQL path、`_JOB_TYPE`/`_TENANT_UUID` sources、四类正常 child、0003-0005 FK DAG、0006 empty-job admission、one-transaction rollback/failure propagation、fix artifact plan-gap/validation statements。
- Excluded scope: 另一 review lane 结论、Item 8 exact-four 内容与 aggregate、D0、production 变更及其它 work unit。exact-four 仅作冻结身份复核。
- Parallel review coverage: 无。
- Execution boundary: 未运行 integration、pytest、PostgreSQL、Docker 或网络；未修改 implementation/fix/plan/README/workflow/index/Git state。仅用 `apply_patch` 回写 source finding 标题状态并创建本 artifact。

## Findings

### CR-DOM-001-已修复（Round2 final；历史反例 body 保留）-中-owner predicate 已绑定 tenant + job type

- **入口/函数**: `_clear_migrated_jobs_database()` 的四类 child DELETE 与最终 `job_runs` DELETE。
- **文件(行号)**: `tests/integration/investment/test_redis_queue_wakeup.py:65-74,414-459,491-507,510-531`；tenant-scoped definition identity 位于 `dayu/investment/storage/migrations/versions/0003_durable_jobs.py:119-139`；0006 readback 位于 `dayu/investment/storage/migrations/versions/0006_job_request_identity.py:1572-1579`。
- **输入场景**: 在同一个合法 schema 中创建 tenant B organization，并在 tenant B 下创建 `job_type='test.redis.integration'` 的 definition/job root及四类合法 descendants；tenant A 是本 fixture 固定 `_TENANT_UUID`。`uq_job_definitions_tenant_id_job_type` 只约束 `(tenant_id,job_type)`，因此 A/B 同名 job type 是 schema-valid，B root 不属于本 fixture scope。
- **实际分支**: 每条 SQL 虽以 child/run/definition 的 tenant 列彼此相等来保持 FK lineage，却只用 `definition.job_type = :job_type` 选择 owner；没有 `definition.tenant_id = :tenant_id` 或 `_TENANT_UUID` bind。tenant B 的同名 definition 因而同样命中，四类 child 和 root 都被删除。若库中只剩 A/B 同名 jobs，0006 随后看到 empty `job_runs` 并继续 downgrade。
- **预期行为**: Redis-owned root 应由当前 fixture 的 exact `(tenant_id=_TENANT_UUID, job_type=_JOB_TYPE)` 共同界定。其它 tenant 即使复用同一 test job type，也必须保留给 0006 fail-closed admission。
- **实际行为**: post-fix 修复了“不同 job type” foreign root，却仍会静默抹除“不同 tenant、同 job type” foreign evidence，因此原 finding 的 ownership closure 尚未完成。
- **直接证据**: `_JOB_TYPE` 在 `:66` 并由 descriptor `:524` 复用，满足 job-type 单真源；fixture scope 的独立 `_TENANT_UUID` 在 `:74`、`:505` 已存在，但 cleanup `:434-456` 从未消费它。0003 `:137-139` 明确允许每个 tenant 各有一个同名 job type。0006 `:1578-1579` 只检查 cleanup 后全表 count，无法恢复被删 tenant B evidence。
- **影响**: test-only foreign evidence 丢失，tenant 隔离维度上的 contamination 被隐藏，migration admission false-green；这与 accepted CR-DOM-001 的“foreign roots 保留”目标直接冲突。
- **建议改法和验证点**: 在四类 child 与 root SQL 中同时增加 `definition.tenant_id = :tenant_id`，并从既有 `_TENANT_UUID` 绑定同一 tenant 值；保持 job type 与 tenant 两个模块级真源分别由 descriptor/scope和 cleanup消费。机械验证两组 DELETE 都含相同 tenant+job-type bind，且不存在其它 owner literal。exact-three catalog 可继续冻结：本缺陷与下一修复均可由 closed SQL predicate、tenant-scoped UQ/FK 与独立静态 re-review证明，不要求新增第四个业务测试。
- **修复风险（低/中/高）**: 低。只收窄现有 owner predicate，不改变表集合、顺序、transaction、fixture lifecycle 或 test catalog。
- **严重程度（低/中/高/严重）**: 中。

## Accepted finding re-review

- `_JOB_TYPE` 已成为 descriptor/cleanup 单一 job-type 真源；通过。
- 正常 enqueue/claim cleanup 已收敛为 `job_events -> job_attempt_receipts -> job_leases -> job_attempts -> job_runs`，四类 child 均以真实 `(tenant_id,job_run_id)` root join 删除；通过。
- `source_*`、`job_schedule_occurrences`、`agent_run_correlations` 与 blanket/CASCADE 均不再删除。它们引用 owned attempt/run 时，当前 FK 均为 `ON DELETE RESTRICT`；child/root DELETE 失败会使同一 `engine.begin()` transaction 回滚，异常未捕获，后继 downgrade 不运行；通过。
- foreign **job type** roots会保留，但 foreign **tenant + same job type** roots不会保留；因此 CR-DOM-001 未闭合。
- fix artifact明确记录 accepted plan blanket tuple 是 plan gap，并保留 exact-three 决策与旧失败历史；记录如实。其“foreign job root 保留”表述缺少 tenant 限定，正由本 finding纠正。

## Open Questions

- 无。

## Residual Risk

- Fresh verdict: `FAIL`；open `H/M/L = 0/1/0`。
- 除 tenant owner bind 外未发现 post-fix 新 blocker。SQL identifier 仍只来自 closed tuple；参数值 bind；one transaction、rollback、dispose、异常传播、migration真源、AGENTS docstring/type 与 exact-three boundary均合理。
- Reviewer未复跑 fix artifact声称的 `3 passed`、Pyright、Ruff、architecture 或 owner-label evidence；本轮边界只允许静态 re-review。它们支持正常路径，但不能反证上述跨 tenant schema-valid counterexample。
- 本 verdict不授权 fix、stage、commit、push、PR、Gateflow advance或 Item 8 aggregate恢复。

## Frozen END

- Candidate diff: `6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`。
- Redis file: `28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`。
- Fix artifact: `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`。
- Implementation artifact: `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- Item 8 exact-four: excluded、preserved、未修改。
