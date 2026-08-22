# Code Review

## Scope

- Mode: current changes，Controller 冻结的单文件 prerequisite candidate。
- Review time: `20260822-094903+0800`，来自本机系统时钟。
- Reviewer: 独立 domain/ownership reviewer；不是 Controller、implementation writer 或 fix writer。运行时未暴露更细的 model identifier。
- Repository / branch: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform`。
- Base: accepted-plan commit `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Output file: `docs/reviews/code-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-domain.md`。
- Included scope: canonical candidate diff `e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`；`tests/integration/investment/test_redis_queue_wakeup.py` END `f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`；implementation artifact `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`；accepted plan/acceptance；真实 fixture lifecycle、JobService/PostgresJobStore enqueue/claim 路径及 migrations 0003-0006 的 FK/admission/downgrade 合同。
- Excluded scope: pre-existing Item 8 exact-four WIP、其它 production/implementation diff、Item 8 aggregate、D0、网络与外部系统。exact-four 已按冻结身份只读复核，未吸收进本 candidate。
- Parallel review coverage: 无。本 lane 独立覆盖 scope/ownership、FK DAG、fixture teardown/cleanup contamination、transaction/failure propagation、AGENTS docstring/type/dynamic SQL、migration safety truth 与 validation evidence。
- Execution boundary: 未运行 integration、pytest、PostgreSQL、Docker 或网络；未修改 implementation、migration、README、workflow、index 或 Git state。仅以 `apply_patch` 创建本 review artifact。

## Findings

### CR-DOM-001-已修复（Round2 final；历史 finding body 保留）-中-cleanup owner key 已闭合并保留 foreign job evidence

- **入口/函数**: `_clear_migrated_jobs_database()`，由 `migrated_jobs_database` fixture finalizer 调用。
- **文件(行号)**: `tests/integration/investment/test_redis_queue_wakeup.py:421-469`；owner identity 位于同文件 `504-511`。受影响的安全 readback 位于 `dayu/investment/storage/migrations/versions/0006_job_request_identity.py:1572-1579` 与 `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py:2416-2437`。
- **输入场景**: 在该 function-scoped 独占数据库内，除三个 Redis test 预期创建的 `job_type='test.redis.integration'` job 外，因回归、误装配或新增 helper 产生一条 schema-valid 的其它 job definition/job run；它可以带合法 attempt/lease/event/source/schedule-occurrence descendant。这个反例不需要并发或非法 SQL，且正是 teardown 应显式暴露的跨 owner contamination。
- **实际分支**: helper 使用 bootstrap engine 进入一个 transaction，循环 frozen table tuple，对每张表执行无 `WHERE`、无 owner/root predicate 的 `DELETE FROM dayu_platform.<table>`。Redis 的唯一 owner discriminator `test.redis.integration` 从未进入 cleanup 数据链。所有外来 job 及 descendant 与 Redis rows 一并被删除，随后 0006 的 `SELECT count(*) FROM job_runs` 及 0005 的 source business-row admissions看到零并继续 downgrade。
- **预期行为**: cleanup 只能删除从本 fixture Redis job root 可证明可达的 rows；任何 foreign/unrooted job 或 descendant 必须在第一次 DELETE 前 fail closed，或被保留给现有 migration admission 拒绝。独占且最终 FORCE-drop 的数据库说明资源生命周期，但不能把未被 Redis 入口创建的业务证据自动改判为 Redis-owned；accepted plan 同样通过保留 `job_schedules` 认可了这一 contamination/readback 边界。
- **实际行为**: foreign evidence 在一个原子 transaction 中静默消失，正式 downgrade 返回成功，完整 Redis 文件可以 false-green；实施 artifact 的 `3 passed` happy path 不会构造 foreign owner，因此无法检测这一分支。
- **直接证据**: 候选 `:434-438` 创建 bootstrap engine 后只按 table-name tuple 全表 DELETE；`:504-511` 固定了可用于 ownership proof 的 Redis job type，但 helper不读取它。0006 `:1578-1579` 只检查 cleanup 后的 `job_runs` count；0005 `:2419-2437` 同样依赖 cleanup 后的 source rows/durable columns。当前 FK DAG 顺序本身正确：source alert/state/operation/snapshot/run、schedule occurrence、job correlation/event/receipt/lease/attempt/run 都是 child-first；缺陷是删除集合没有与 Redis root 绑定，而不是顺序错误。
- **影响**: test-only 数据证据丢失、跨 domain/owner contamination 被隐藏、migration fail-closed 真源在该 fixture 中被前置全表删除架空，导致 teardown 与后继 setup 给出错误的成功结论。生产 migration 代码未被修改，但本 prerequisite 所声称的 safety validation 不充分。
- **建议改法和验证点**: 在同一个 bootstrap transaction 中先固定 Redis-owned job root（复用单一模块级 job-type constant），并仅删除可由这些 job IDs 证明可达的 descendants；foreign 或无 root row 保留，使 0006/0005/0004 admission fail closed。也可先对整个 cleanup universe 做 exact reachability proof，发现任一 foreign/unrooted row即在首个 DELETE 前抛错。不得恢复 blanket DELETE、`CASCADE` 或吞异常。补一个同文件 hostile lifecycle case：插入合法 foreign job（至少一条 descendant），断言 cleanup/downgrade非零、foreign rows未被部分删除、第三 setup 不被伪装成成功；同时保持现有完整文件 exact-three 正常路径 `3 passed`。
- **修复风险（低/中/高）**: 中。需要在保持 one-transaction、child-first DAG 与唯一文件 scope 的同时闭合多表 reachability；若无法在唯一测试文件内完成，应按 accepted plan STOP 并交回 Controller 修 plan。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。若 Controller 要把“整个随机数据库中的一切业务行”定义为 fixture-owned，需要先修订 accepted plan 的 Redis-root 最小 ownership 与 `job_schedules` contamination readback 语义；当前 plan/implementation 不能同时支持该解释。

## Residual Risk

- Fresh verdict: `FAIL`；open `H/M/L = 0/1/0`。
- 除 CR-DOM-001 外，未发现独立实质问题：candidate 仅修改授权测试文件；tuple 对当前 FK DAG 为 child-first 且包含 `job_schedule_occurrences`、排除 `job_schedules`；动态 SQL identifier 仅来自私有 frozen tuple；helper 使用单一 `engine.begin()` transaction，失败自动 rollback，异常未捕获且 downgrade 不继续，engine 在 `finally` 恰好 dispose；fixture teardown 保留 adapter -> app engine -> temporary login -> bootstrap cleanup -> downgrade 的所有者顺序；docstring、严格类型签名与 AGENTS 边界闭合；0006 production admission 未被代码修改。
- Reviewer 按边界没有复跑 implementation artifact 声称的 PG/Redis/pytest/Pyright/Ruff/architecture evidence。该 evidence 足以证明当前 happy path 和实际 downgrade lifecycle，但不足以证明 ownership failure branch；此缺口已并入 CR-DOM-001，而非另列弱 finding。
- 本 review 不裁决 Item 8 exact-four、remaining aggregate 或 D0，也不授权 fix、stage、commit、push、PR、Gateflow advance 或 merge。

## Frozen END

- Reviewed candidate diff: `e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`。
- Redis test: `f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`。
- Implementation artifact: `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- Accepted plan commit: `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- Item 8 exact-four: excluded、preserved、未修改。
