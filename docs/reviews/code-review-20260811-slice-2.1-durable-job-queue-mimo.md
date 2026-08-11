# Slice 2.1 Durable Job Queue — MiMo Independent Code Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (independent)
- **Branch**: codex/investment-platform / HEAD a457a7e
- **Method**: 全量逐行审读 22 production/test 文件 + 独立复跑 imports / 154 unit / 36 migration integration

## 0. Verdict

**PASS.** 无 open H/M/L。实现与 plan 公共契约、状态机、事务原子性、RLS、grants、downgrade、secret safety、named-test owner/path 逐项对齐。

## 1. Core Evidence

- **RLS**: 七表 ENABLE+FORCE RLS，tenant_isolation policy 双向 USING/WITH CHECK (0003:811-826)。每方法 SET LOCAL app.tenant_id + 读回确认 (postgres_jobs.py:602-619)。
- **Fence Token**: claim 256-bit token 只存 SHA-256。_lock_job_attempt_lease 五入口一致校验 tenant+job+attempt+fence+token_hash+current_attempt (postgres_jobs.py:2730-2798)。authorize 核对 lease_row.job_run_id (postgres_jobs.py:2191)。
- **State Machine**: claim/heartbeat/complete/fail/cancel/recover/reconcile 全与 plan §4 对齐。NOT EXISTS correlation guard (postgres_jobs.py:1769)。
- **Crash Windows**: 三窗口均有 named test。claim后reserve前无副作用，reserve后Host前 NO_HOST_RUN，Host insert后模型前 created=False。
- **Reserved At-Most-Once**: _validate_reserved_run_id 前置校验 (run_registry.py:44)。BEGIN IMMEDIATE INSERT OR IGNORE→SELECT→compare (run_registry.py:237-287)。executor created=True 才构造 Agent (executor.py:786)。
- **DDL/Grants/Downgrade**: 列级 UPDATE 精确 5 表。Immutable guard triggers。Single-release CAS trigger。Downgrade pg_depend preflight→fail closed→drop reverse order no CASCADE。
- **Composition**: 阶段1 PG admission→Host构造→阶段2 PostgresJobStore(session_factory)+JobService(host as reader)。PostgresJobStore 构造器只有 session_factory。Provider exact {"investment_identity","durable_jobs"}。
- **Secrets**: Raw token 仅 claim 返回一次。错误只含 safe code。CanonicalJobDocument 递归拒绝敏感键。

## 2. Bug Fix Verification (8 items)

1. _terminalize_deadline 返回 receipt 不复用 post-commit session
2. ON CONFLICT DO NOTHING 消除竞态 (postgres_jobs.py:801)
3. LEASE_LOST 统一 LEASE_EXPIRED (postgres_jobs.py:2118)
4. _clock(session) 取 PG 时钟 (postgres_jobs.py:182)
5. _prefixed_columns 修复 SQL 双重前缀 (postgres_jobs.py:2062)
6. 五入口一致校验 job_run_id + current-attempt
7. 0003 无 ALTER DEFAULT PRIVILEGES
8. 22 表 exact catalog (assert_schema_present 15→22)

## 3. Closed Observations

1. postgres_jobs.py:2607 前缺空行（Ruff 未报）
2. parse_generic_attempt_receipt 内 assert 在 except AssertionError 块内，-O 仍安全

## 4. Independent Verification

- import 全部 production module → OK
- pytest application/cli/migrations → 154 passed exit 0
- pytest test_platform_migrations_postgres → 36 passed exit 0
- Implementation artifact 完整门禁：三条 PG16 lane 36+16+68 / 全仓 8184 / pyright 0 / Ruff delta=0 / coverage ≥80%

## 5. Residual Risks (Plan §9)

START_REQUIRED→Host ensure 前 TOCTOU → Slice 2.2。外部 provider exactly-once → 未来 handler。scheduler/backoff → Slice 2.2。业务 payload → Slice 2.3。

## 6. Final Verdict

**PASS / open H/M/L=0/0/0.** 可进入 accepted slice commit.
