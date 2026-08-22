# Code Re-review Round2

## Scope

- Mode: Gateflow final code re-review Round2，仅复核 accepted `CR-DOM-001` 的完整 owner key closure 与 post-fix 新 blocker。
- Review time: `20260822-100902+0800`，来自本机系统时钟。
- Reviewer: 原 domain/ownership 独立 reviewer；不是 Controller、implementation writer 或 fix writer。运行时未暴露更细的 model identifier。
- Repository / branch / base: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform` / accepted-plan commit `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Reviewed Round2 candidate: binary diff `26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`；Redis file `f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`。
- Round2 fix artifact: `docs/reviews/code-review-fix-round2-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `f7a20c5dcd8e07f32c3f23c6c8019add3677a68117ec3354fa11a8d5bc436725 / 69 / 6453`。
- Prior frozen artifacts: Round1 fix `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`；implementation `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- Source review START: `f980b9a1851330d98fe23f1bde349857d9558776211498950fd854ef7950f0a1 / 49 / 7939`；first domain re-review START: `847adce515731f8e68e328164e15baa70ee94190eabee000be40d8c5cf6f599f / 58 / 7022`。本轮仅回写两处历史 finding 标题的最终状态，历史 body/verdict 保留作为旧 candidate 证据。
- Included evidence: `_clear_migrated_jobs_database()` 两处 DELETE 的 tenant/job-type bind、definition composite join、closed four-child FK DAG、跨域 `RESTRICT`、one-transaction rollback/failure propagation、fixture finalizer、AGENTS docstring/type/dynamic-SQL 边界及 Round2 fix artifact 的 validation 记录。
- Excluded scope: 另一 review lane 结论、Item 8 exact-four 内容与 aggregate、D0、production 变更及其它 work unit。exact-four 仅作冻结身份复核。
- Execution boundary: 未运行 integration、pytest、PostgreSQL、Docker 或网络；未修改 implementation、fix、plan、README、workflow、index 或 Git state。仅以 `apply_patch` 回写两份 domain 历史 finding 标题并创建本 artifact。

## Findings

无。Fresh open `H/M/L = 0/0/0`。

## Accepted finding final re-review

### CR-DOM-001-已修复-owner key、foreign preservation 与 rollback 闭合

- **完整 owner key**：`tests/integration/investment/test_redis_queue_wakeup.py:434-445` 的四类 child DELETE 与 `:450-458` 的 root DELETE 都要求 `owned_run.tenant_id = :tenant_id` 和 `definition.job_type = :job_type`，并都精确绑定 `{"tenant_id": _TENANT_UUID, "job_type": _JOB_TYPE}`。`_TENANT_UUID` 同时服务 `_scope()`，`_JOB_TYPE` 同时服务 `_descriptor()`；cleanup 未引入第二套 owner literal。
- **definition composite join**：两组 DELETE 都要求 `owned_run.tenant_id = definition.tenant_id` 及 `owned_run.definition_id = definition.id`。0003 的 `job_runs(tenant_id,definition_id) -> job_definitions(tenant_id,id)` 为 `ON DELETE RESTRICT`，且 definition 唯一身份为 `(tenant_id,job_type)`；不能用另一 tenant 的同 ID 或同 job type 拼接出 owner match。
- **hostile：foreign same-type / other-tenant**：tenant B 可合法持有 `job_type='test.redis.integration'`，但其 run 在两组 DELETE 都不满足 `owned_run.tenant_id = _TENANT_UUID`；root 与四类 child 均保留，随后由 0006 empty-table admission fail closed。Round1 的 schema-valid 反例不再成立。
- **hostile：same-tenant / other-type**：该 root 不满足 `definition.job_type = _JOB_TYPE`；root 与 descendants 保留。相同 tenant + 相同 job type 由 `uq_job_definitions_tenant_id_job_type` 收敛为同一 owner definition，属于本 fixture 的 Redis owner domain。
- **正常 descendant DAG**：closed tuple 保持 `job_events -> job_attempt_receipts -> job_leases -> job_attempts` 后再删 `job_runs`；每类 child 都通过 `(child.tenant_id,child.job_run_id)` 连接精确 owned root。动态 identifier 仅来自模块级 closed tuple，值全部参数 bind；没有 blanket `DELETE`、`TRUNCATE`、`CASCADE`、fallback 或异常吞噬。
- **hostile：跨域 descendant**：`source_sync_runs`、`source_sync_operations` 以复合 FK `ON DELETE RESTRICT` 引用 owned attempt；`agent_run_correlations` 引用 attempt/run；`job_schedule_occurrences` 引用 run。它们故意不在 cleanup tuple。若任一存在，attempt 或 root DELETE 抛错，`cleanup_engine.begin()` 回滚之前已执行的 child DELETE；helper 不捕获异常，fixture 不会调用后继 downgrade。因而跨域 evidence 不会被静默清除，也不会产生 partial cleanup false-green。
- **lifecycle / migration truth**：cleanup 仍位于 adapter、application engine、temporary login 释放之后和正式 downgrade 之前；production migration/admission 未改变。`finally: cleanup_engine.dispose()` 只回收 engine，不改变失败传播。
- **AGENTS 合规**：helper 保持模块级、严格类型签名和完整中文 docstring；无 `Any`/`object`、lazy import 或反向依赖。当前修改是测试 cleanup predicate 收窄，不触发 README 或 production schema 同步。

## Exact-three 与 validation evidence

- Controller 冻结 exact-three catalog；Round2 只在既有两组 SQL 中增加同一 tenant predicate/bind，不增加新的执行路径、fixture 或动态 identifier。完整 `(tenant_id,job_type)` closed predicate、tenant-scoped UQ/FK 与本轮独立 hostile 静态证明足以闭合原反例；不要求扩张为第四个 integration test。
- Round2 fix artifact 如实记录跨 tenant hostile branch 未动态新增，并记录 post-fix full Redis file `3 passed`、Pyright `0 errors`、Ruff、architecture `171 passed`、owner residue `0/0` 与 static oracle。Reviewer 按冻结边界未复跑这些命令；未把 writer 自述替代为独立运行证据。
- Candidate `git diff --check` 本轮只读复核为 clean；canonical binary diff SHA 重新计算仍为冻结值。

## Open Questions

无。

## Residual Risk

- Fresh verdict: `PASS`；open `H/M/L = 0/0/0`。
- 当前四类正常 Job descendant 由 closed tuple 明确维护；未来 migration 新增正常 descendant 时，migration/test owner 仍须同步 DAG。这是未来演进条件，不是当前 blocker。
- exact-three 未动态构造跨 tenant hostile row；该残余被 Controller 的 frozen catalog、两处 literal parameter bind、schema composite identity 与独立静态反例复核共同接受，不形成 open finding。
- 本 verdict 不授权 stage、commit、push、PR、Gateflow advance、Item 8 aggregate 恢复或 merge。

## Frozen END

- Candidate diff: `26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`，与 START 相同。
- Redis file: `f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`，与 START 相同。
- Round2 fix artifact: `f7a20c5dcd8e07f32c3f23c6c8019add3677a68117ec3354fa11a8d5bc436725 / 69 / 6453`，与 START 相同。
- Round1 fix artifact: `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`，与 START 相同。
- Implementation artifact: `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`，与 START 相同。
- Item 8 exact-four preserved：
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`；
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`；
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`；
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`。
