# Slice 2.1 Provider Allowlist Erratum（Spark corrective re-review，2026-08-11）

- **Reviewer**: Codex Spark（independent corrective re-review）
- **Status**: **FAIL**
- **Open H/M/L**: **1 / 0 / 0**
- **Scope**: `AGENTS.md`、`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`、`docs/plans/2026-08-10-investment-platform-restoration.md`、`docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-allowlist-codex.md`、`docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md`、`docs/reviews/plan-review-20260811-192410-slice-2.1-provider-allowlist-mim.md`、`docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-spark.md`、`dayu/services/startup_preparation.py`、`tests/integration/investment/test_identity_repositories_postgres.py`

## 1）结论先行

本次复审目标是验证 H-001 是否“最小闭合”。当前 snapshot 仍存在阻断性不一致，因此未达 0/0/0。

- H-001（旧 helper probe）在 `test_identity_repositories_postgres.py` 仍然可复现：
  - `PlatformOwnedLifecycleProtocol` 仍在 import 列表中且被 `original_build_provider: tuple[PlatformCompositionProviderProtocol, PlatformOwnedLifecycleProtocol]` 标注使用。
  - 第二测试 `test_production_provider_s3_placeholder_still_rejected` 仍直接 monkeypatch `sp._build_production_identity_provider`。
  - 当前 startup WIP 已无 `_build_production_identity_provider`，仅保留 `_build_production_services_provider`（`dayu/services/startup_preparation.py`）。
  - 该条 patch 在 runtime 会触发属性缺失异常，直接破坏完整 PG16 startup integration lane，无法算作“只改名 + 修改一个 black-box mapping 断言”即闭环。

- 该 finding 仍为 **Open High=1**，其余核查项在当前 snapshot 可执行，但不能掩盖该阻断。

## 2）核查项复核结果

1. **第二测试删除 old helper probe 的最小性**
   - `test_identity_repositories_postgres.py` 目前未按修正执行，仍保留旧 probe。
   - 结论：未闭合。

2. **DSN/provider/PG zero side-effect 语义**
   - 在修正后可维持：placeholder 测试本身仍走 `platform_provider=_PlatformProviderSentinel`，计划要求的 `_read_postgres_dsn`/provider/workspace/PG 调用计数断言可保留。
   - 结论：可实现，未在当前代码层面确认已闭合。

3. **unused import 与模块 docstring 同步**
   - 当前模块 docstring 仍写“production composition 只含一个 identity service”；与 WIP 中两 service 映射不一致。
   - `PlatformOwnedLifecycleProtocol` 当前在本文件内未有有效使用路径。
   - 结论：修正未完成。

4. **不得 compat**
   - 当前未见新增兼容 helper，未发现兼容性回退补丁。
   - 结论：达标。

5. **mapping 测试与 `JobService` 语义**
   - `startup_preparation.py` 现实现返回 `{"investment_identity": identity_service, DURABLE_JOBS_SERVICE_NAME: job_service}`。
   - `JobService.platform_service_name()` 返回 `durable_jobs`。
   - 结论：可闭合。

6. **`PostgresJobStore(session_factory=...)` 与 Host reader 注入**
   - 当前实现确认为 `PostgresJobStore(session_factory=preparation.session_factory)`，`JobService(..., host_run_reader=host)`。
   - 结论：已达成。

7. **Identity lifecycle 与 full PG16 lane 可实施性**
   - `InvestmentIdentityService` 在平台启动阶段仍为 shared-engine lifecycle owner。
   - integration lane（含 `test_identity_repositories_postgres.py` / `test_postgres_jobs.py` / `test_platform_migrations_postgres.py`）在当前状态因旧 helper probe 可复现失败。
   - 结论：在执行最小修复前不可稳定通行。

## 3）建议的 gate 处理

- 仍要求按 correction 4 项执行（只做：
  1) 映射断言测试改名与 exact two-service 断言；
  2) `test_production_provider_s3_placeholder_still_rejected` 中仅删除旧 helper probe 与相关计数；
  3) 模块 docstring 与 one-line 合约同步；
  4) 删除 `PlatformOwnedLifecycleProtocol` 单个 unused import。
）

执行完成后请提交新的 Spark re-review；无额外兼容实现。
