# Slice 2.1 Durable Job Queue — Implementation Artifact

- **Status**：`DUAL CORRECTIVE CODE RE-REVIEW PASS / READY FOR ACCEPTED COMMIT`（F-001/F-002/F-003 已 FIXED/CLOSED，MiM + MiMo open H/M/L=`0/0/0`）
- **Implementation specialist**：DeepSeek Flash（AgentDSFlash pane 等价 fallback）
- **Branch / baseline**：`codex/investment-platform` / `489a910`（accepted-plan HEAD）
- **Gate**：Phase 2 Slice 2.1 durable job queue implementation（implementation gate，非 commit/PR gate）
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`（ACCEPTED，含两项 erratum acceptance）
- **Controller local accepted commit**：`a457a7e`（identity docstring guard 计划，MiM+MiMo PASS/open0，解除 implementation freeze）
- **Independent reviewers**：MiM + MiMo（initial review、Controller adjudication、corrective re-review 均已闭环）

## 0. Code review closure

- Initial MiM：`docs/reviews/code-review-20260811-slice-2.1-durable-job-queue-mim.md`
- Initial MiMo：`docs/reviews/code-review-20260811-slice-2.1-durable-job-queue-mimo.md`
- Controller adjudication：`docs/reviews/slice-2.1-durable-job-queue-code-review-adjudication-20260812-codex.md`
- Fix：`docs/reviews/slice-2.1-durable-job-queue-review-fix-20260812-deepseek-flash.md`
- MiM corrective：`docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mim-corrective.md` — PASS / open H/M/L=`0/0/0`
- MiMo corrective：`docs/reviews/code-review-20260812-slice-2.1-durable-job-queue-mimo-corrective.md` — PASS / open H/M/L=`0/0/0`

Controller 接受的 F-001/F-002/F-003 全部 FIXED/CLOSED；无新 finding、无需第二轮 fix。代码与测试在 reviewer 期间 SHA-256 冻结，当前 Slice 2.1 可进入本地 accepted commit gate。

## 1. Scope 合规声明

- 全部 22 个 WIP 路径在 plan §2 exact allowlist 内；审计后仅原地继续，未丢弃/重置任何既有改动。
- `dayu/host/protocols.py` diff 严格限于 plan §3.1 四项 reserved contract（`ReservedRunEnsureResult`、`ReservedRunIdentityConflictError`、`ReservedAgentRunExistsError`、`ensure_reserved_run`）与其 `__all__`；未顺手清理 baseline Ruff 债务（顶部 imports 与 HEAD 逐字一致）。
- `tests/integration/investment/test_identity_repositories_postgres.py` 改动严格限于 erratum 四项 + Controller 授权（`a457a7e`）的 `_counted_read_postgres_dsn` 固定 docstring；stripped-docstring AST 对 489a910 结构 diff 精确等于授权项。
- 未修改 `dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/contracts/protocols.py` 与架构守护；未触碰 Slice 2.2/2.3 owner。
- 未 commit / push / PR / merge / deploy / live / paid / model / broker 调用；未读取/输出 secret 或 DSN。
- 未使用 stash/checkout/reset 做 baseline 测量（Ruff HEAD 对比仅 `git show HEAD:path | ruff --stdin-filename` 纯只读）。

## 2. Changed files（22 WIP + 3 README）

### Production
| 文件 | 变更 |
| --- | --- |
| `dayu/investment/domain/jobs.py`（新） | 11 枚举 / 15 DTO / 8 稳定错误 / canonical document / generic + Host-origin receipt builder；签名去 `object`（plan §3） |
| `dayu/investment/storage/protocols.py`（改） | 新增 `JobStoreProtocol`（14 方法精确签名） |
| `dayu/investment/storage/postgres_jobs.py`（新） | `PostgresJobStore` 全量实现；修 5 处实现 bug + 1 处 SQL bug（见 §4） |
| `dayu/investment/storage/migrations/versions/0003_durable_jobs.py`（新） | 七表 DDL/RLS/列级 GRANT/immutable trigger/downgrade admission；移除 plan 外 `ALTER DEFAULT PRIVILEGES` |
| `dayu/services/job_service.py`（新） | `JobHandlerRegistry(Protocol)`、`HostRunReaderProtocol`、`JobService`（registry gate 先于 store；recover correlation-safe 编排） |
| `dayu/services/startup_preparation.py`（改） | 两阶段 production composition（阶段 1 PG admission → Host 构造 → 阶段 2 provider 装配）；`_ProductionServicesProvider` 模块级化 |
| `dayu/cli/workspace_migrations/platform_jobs.py`（新） | `dayu-cli init` 幂等 Alembic upgrade hook |
| `dayu/cli/workspace_migrations/runner.py`（改） | 挂接 `migrate_platform_jobs()` |
| `dayu/host/protocols.py`（改） | 仅四项 reserved identity contract |
| `dayu/host/run_registry.py`（改） | `ensure_reserved_run`（BEGIN IMMEDIATE 单事务 INSERT OR IGNORE → SELECT → compare） |
| `dayu/host/host_execution.py`（改） | `HostExecutorProtocol` 四 entry 增加 keyword-only `reserved_run_id` |
| `dayu/host/executor.py`（改） | `_ensure_reserved_run_record`（created=True 才构造 Agent） |
| `dayu/host/host.py`（改） | `Host` 同名委托入口 |

### Tests
| 文件 | 说明 |
| --- | --- |
| `tests/application/test_job_service.py`（新） | 15 DTO / receipt golden+parse / canonical / registry / Service orchestration / trap 型无 async-entry 断言 |
| `tests/application/test_reserved_agent_run.py`（新） | reserved entry at-most-once / 错误 payload / protocol 契约 |
| `tests/application/test_run_registry.py`（改） | concurrent ensure / invalid-ID / 双格式共存 / metadata 归一化 |
| `tests/application/test_service_startup_preparation.py`（改） | E 四测试模块级化（plan §7E `file::test_*` literal）；两阶段装配/close 幂等 |
| `tests/cli/workspace_migrations/test_platform_jobs.py`（新） | no-op/fail-closed/幂等 |
| `tests/investment/test_platform_migrations.py`（改） | 0003 source-text 契约 |
| `tests/integration/investment/test_platform_migrations_postgres.py`（改） | 0003 真实 catalog 并入（22 表 columns/constraints/indexes/policies/grants），`_assert_schema_present` 15→22 |
| `tests/integration/investment/test_identity_repositories_postgres.py`（改） | erratum 四项 + `a457a7e` docstring |
| `tests/integration/investment/test_postgres_jobs.py`（新） | PG16 fault matrix + crash-window + 覆盖补强（branch/tenant/splice/matrix） |

### Docs
`dayu/host/README.md`、`dayu/investment/README.md`、`tests/README.md`（§6 docs decision）

## 3. Validation（每条精确命令与真实结果）

所有命令从仓库根执行，`.venv` 为 Python 3.11.15；PG16 三条 lane 均独立 pytest 进程、真实退出码、无 `-k`/pipe 掩码。

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `.venv/bin/pytest tests/application/test_job_service.py tests/application/test_run_registry.py tests/application/test_reserved_agent_run.py tests/application/test_service_startup_preparation.py tests/cli/workspace_migrations/test_platform_jobs.py tests/investment/test_platform_migrations.py -q --timeout=60` | `154 passed`，exit `0` |
| 2 | `.venv/bin/pytest tests/integration/investment/test_platform_migrations_postgres.py -q --timeout=120` | `36 passed`，exit `0` |
| 3 | `.venv/bin/pytest tests/integration/investment/test_identity_repositories_postgres.py -q --timeout=120` | `16 passed`，exit `0` |
| 4 | `.venv/bin/pytest tests/integration/investment/test_postgres_jobs.py -q --timeout=120` | `68 passed`，exit `0` |
| 5 | `env -u SERPER_API_KEY .venv/bin/pytest -q --timeout=60 -m "not integration and not slow and not e2e"` | `8184 passed, 5 skipped, 154 deselected`，exit `0` |
| 6 | `pyright <全部 22 个改动 production/test 路径>` | `0 errors, 0 warnings` |
| 7 | Ruff：13 个 modified 文件 HEAD/current code multiset delta | 全部 `delta=0`（无新增 finding；HEAD 用 `git show` stdin 只读） |
| 8 | Ruff：9 个 new 文件 | `All checks passed`（含 F/I） |
| 9 | `git diff --check` | `OK`（无空白错误） |
| 10 | 中文 docstring guard + escape guard（`tests/investment/test_architecture_boundaries.py` 相关 4 项） | 全 PASS |

### Coverage（unit + 三条 PG16 lane + 全仓 non-integration lane，独立 fresh `COVERAGE_FILE`，`coverage run -m pytest` 无 `--source` + `coverage report --include`）

| 模块 | Stmts | Miss | Cover |
| --- | --- | --- | --- |
| `dayu/cli/workspace_migrations/platform_jobs.py` | 30 | 0 | 100% |
| `dayu/cli/workspace_migrations/runner.py` | 26 | 2 | 92% |
| `dayu/host/executor.py` | 714 | 73 | 90% |
| `dayu/host/host.py` | 527 | 82 | 84% |
| `dayu/host/host_execution.py` | 20 | 0 | 100% |
| `dayu/host/protocols.py` | 234 | 1 | 99% |
| `dayu/host/run_registry.py` | 206 | 8 | 96% |
| `dayu/investment/domain/jobs.py` | 530 | 56 | 89% |
| `dayu/investment/storage/migrations/versions/0003_durable_jobs.py` | 118 | 1 | 99% |
| `dayu/investment/storage/postgres_jobs.py` | 879 | 153 | 83% |
| `dayu/investment/storage/protocols.py` | 45 | 0 | 100% |
| `dayu/services/job_service.py` | 102 | 11 | 89% |
| `dayu/services/startup_preparation.py` | 285 | 17 | 94% |

全部新增/修改 production module ≥ 80%。未覆盖行主要为防御性不可达路径（terminal replay reconciliation 等，按 Controller 指示不凑覆盖）。

## 4. Implementation 过程中修复/发现的关键缺陷（均有直接证据）

1. **fail/cancel post-commit session 复用**（`_terminalize_deadline` 调用后、`_commit_and_close` 后仍用 session 读 receipt/attempt_state → 第二个无 `SET LOCAL` 事务被 RLS 隐藏行）：`_terminalize_deadline` 改为返回 receipt，fail 用返回值；cancel 提前读 attempt_state。
2. **enqueue definition check-then-insert 竞态**（并发首入队泄漏 raw IntegrityError）：`ON CONFLICT (tenant_id, job_type) DO NOTHING` + 统一 descriptor/disabled 校验；idempotency-reuse receipt 的 `state` 固定 `READY`（不再读 live state）。
3. **authorize `LEASE_LOST` 带 `safe_error_code=None`**（会令 `AgentRunStartAuthorizationDecision.__post_init__` 直接抛错）：统一 `LEASE_EXPIRED`。
4. **`_synthesize_correlation` 用本机时钟**：改为事务内 PG `clock_timestamp()`。
5. **`list_expired_agent_run_correlations` SQL 双重前缀**（`SELECT c.{_prefixed_columns('c', ...)}` → `c.c.id`，UndefinedTable）：由新增 coverage 测试触达并修复。
6. **lease handle 关联校验缺失（Controller High finding）**：heartbeat/complete/fail（共享 `_lock_job_attempt_lease`）与 `reserve_agent_run_correlation` 原未核对 attempt/lease 的 `job_run_id` 与 job current attempt——同 tenant 跨 job 拼接 handle 可操作错 job。已在 Store 单一真源补齐：SQL predicate `job_run_id` + current-attempt 校验五入口一致；authorize 增加 lease.job_run_id 校验并保持 closed decision。未在 Service 重复校验。wrong-tenant / 跨 job 拼接 / wrong attempt / wrong fence / wrong token 全部 fail closed 且零 mutation（新增参数化 + adversarial PG 测试）。
7. **0003 migration 含 plan 未授权 `ALTER DEFAULT PRIVILEGES ... REVOKE`**：移除（实测 `pg_default_acl` 保持空，与 Phase 1 ACL 断言一致）。
8. **0003 exact catalog 缺失**：以真实 PG16 catalog dump 补全 `_PRIVATE_TABLES`（15→22）与 `_EXPECTED_COLUMNS/_EXPECTED_CONSTRAINTS/_EXPECTED_INDEXES`；`_assert_schema_present` 15→22；downgrade-to-0001 排除集补 0003 表。修复后首测级联（role 未清理）消失。

## 5. Named tests 完整性

- §7A/B/C/D/E 与 §8 全部命名测试齐备（76/76，Controller 只读审计确认）；本会话补全 9 个缺失项（`test_reserved_identity_errors_carry_exact_record_and_safe_message`、`test_cancel_before_claim_is_terminal_without_attempt_receipt`、`test_platform_jobs_workspace_migration_is_idempotent`、`test_terminal_reconcile_applies_cancel_then_deadline_then_host_outcome`、`test_terminal_reconciliation_replay_returns_existing_receipt_without_event`、`test_crash_after_reserve_before_future_host_call_reuses_same_reserved_id`、`test_crash_after_host_reserved_insert_before_model_does_not_enter_model_twice`、`test_active_host_wait_never_enters_model_twice`）。
- `test_production_provider_exposes_real_durable_jobs_service_and_platform_service_name`（§7E 原文）已由 erratum §7E owner/path 列表取代（exact two-service mapping 归 PG16 black-box 节点），不构成缺失。
- 覆盖补强（非命名清单）：`TestSlice21BranchCoverage`、`TestWrongTenantLeaseHandle`、`TestCrossJobSplicedLeaseHandle`、`TestLeaseFieldMatrix`。

## 6. Docs decision

测试全绿后同步三份 README（AGENTS.md 触发规则）：

- `dayu/host/README.md`：§5 新增确定性 reserved run 身份契约（ensure_reserved_run / 两个稳定错误 / executor reserved entry / 12-hex 与 32-hex 永久共存）。
- `dayu/investment/README.md`：§2 owner 表 + §2.6 15→22 表 + 新增 §2.8 Durable job queue（owner 边界、Store 单事务/时钟/lease 全关联校验、0003 grants、downgrade fail-closed on external dependency——运维须先移除外部依赖再重试、禁止 CASCADE，plan §9 要求）。
- `tests/README.md`：三条 PG16 文件独立进程规则、durable jobs lane 与命名测试、22 表 catalog、coverage 环境注意事项。

## 7. Plan gaps / 环境事件（含直接证据）

1. **identity docstring guard baseline 违规**：`test_identity_repositories_postgres.py::_counted_read_postgres_dsn` 在 489a910 即无中文 docstring（HEAD 同文件另有 2 项，erratum 已删 1 项），属 baseline 债务且被 erratum 冻结文件限制；Controller 本地 accepted commit `a457a7e`（MiM+MiMo PASS/open0）授权插入固定 docstring 后 guard PASS。
2. **宿主 `SERPER_API_KEY` 污染**（前序 Slice 13 同现）：`test_search_with_serper_requires_api_key` 首次全仓 lane 失败（ProxyError，`google.serper.dev` 经本地代理不可达 + key 已配置使测试路径改变）；`env -u SERPER_API_KEY` 后 PASS。最终门禁统一 clean-env。
3. **coverage 工具链冲突**：pytest-cov / `coverage --source` 触发 numpy `_multiarray_umath` "cannot load module more than once per process"（本机复现，与代码无关）；workaround 为 `coverage run -m pytest`（无 `--source`）+ `coverage report --include` 过滤。`tests/README.md` 已记录既有 `COVERAGE_CORE=pytrace` 提示。
4. **`workspace/tmp/trim_check.py` 已清理**：Controller 复核其为本任务创建、无交付价值的只读 PG constraint 渲染诊断脚本后，按精确路径删除；未删除任何用户文件或宽目录。

## 8. Residual risks / owners

- `START_REQUIRED` 取得后、Host ensure 前跨 lease 的 PG/Host read-to-entry TOCTOU 无法在两套 store 间消除；本 slice 只保证同一 correlation 的 Host ensure at-most-once，不宣称 distributed exactly-once → **Slice 2.2**（immediate Host entry、heartbeat/governance、re-observe/cancel delivery）。
- 外部 provider/tool exactly-once → 未来 Agent handler/connector 独立 idempotency protocol。
- scheduler polling / Redis degradation、backoff jitter → **Slice 2.2**（本 slice 的 deterministic no-jitter backoff 是公共契约，有意不变）。
- 业务 payload schema、source health、notification → **Slice 2.3**。
- `postgres_jobs.py` 等未覆盖行多为防御性不可达分支（terminal replay reconciliation 等），coverage 已 ≥80%，不追加凑数。

## 9. Cleanup（F）

- 已精确清理：测试容器 `dayu-slice11-pg-97116-b5fd0a0d`；网络 `dayu-slice11-net-72891-ad5ec9a6`、`dayu-slice11-net-97116-b5fd0a0d`、`dayu-slice11-net-97991-8a49520d`；诊断文件 `workspace/tmp/0003_catalog_dump.txt`、`workspace/tmp/dump_0003_catalog.py`、`workspace/tmp/trim_check.py`。最后一项由 Controller 确认任务归属和无交付价值后按精确路径删除。
- 5 个 `investment-agent-platform-*` 运行容器/卷/用户数据未触碰；`/tmp` coverage 目录与日志已不存在。
- 未使用通配符删除。

## 10. Completion / stop status

- Gate：implementation 完成，验证全绿（含三条独立 PG16 lane 真实 exit、全模块 coverage ≥80%、pyright/Ruff/diff-check/full lane）。
- Stop conditions：无触发（未要求塞 metadata、未在 host/protocols 承载 PG DTO、未加 compat wrapper、未注册 handler、未跨 store 事务、未改 allowlist 外文件、未要求以 fake 替代 RLS）。
- 下一步（Controller 裁定）：独立双路 code review（MiM + MiMo）→ accepted findings 修复 → re-review open0 → 本地 accepted slice commit。
