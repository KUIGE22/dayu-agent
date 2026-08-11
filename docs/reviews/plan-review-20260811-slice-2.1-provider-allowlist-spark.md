# Slice 2.1 Provider Allowlist Erratum（独立）Plan Re-review（Codex Spark）

## 结论

- **STATUS：FAIL**
- **open H/M/L：1 / 0 / 0**
- 判定：当前 plan 目标语义（exact two-service mapping）与 WIP 代码/现有黑盒测试组合存在可执行性缺口，未满足“仅 rename/断言”即能闭合的要求。

## 审核范围

- `AGENTS.md`
- `docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- `docs/plans/2026-08-10-investment-platform-restoration.md`
- `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-allowlist-codex.md`
- `tests/integration/investment/test_identity_repositories_postgres.py`
- 当前 startup provider WIP：`dayu/services/startup_preparation.py`

## 关键检查项

### 1) minimal allowlist：`test_production_provider_wires_real_identity_service` 的唯一改名/断言是否足够

- `tests/integration/investment/test_identity_repositories_postgres.py:1340` 当前测试名为 `test_production_provider_wires_real_identity_service`，断言仅：
  `assert set(services) == {"investment_identity"}`（第 `1387` 行附近），与目标 plan 中 `{"investment_identity", "durable_jobs"}` 存在差距。
- `dayu/services/startup_preparation.py` 的 WIP 侧已从 `investment_identity` 扩展到两服务映射：
  - `_build_production_services_provider` 返回 `{"investment_identity": identity_service, DURABLE_JOBS_SERVICE_NAME: job_service}`（约 `381` / `433` 行附近）。
  - `DURABLE_JOBS_SERVICE_NAME` 为 `durable_jobs`（`dayu/services/job_service.py`）。
- 该项本身支持“改名+断言”收紧为正确目标；但这还不足以保证整个 PG16 黑盒 lane 可稳定运行（见下一项）。

### 2) 是否误授权（或误伤）其它测试与现有黑盒 helper

- 在同一测试文件中，`test_production_provider_s3_placeholder_still_rejected` 仍进行：
  - `original_build_provider = sp._build_production_identity_provider`
  - `monkeypatch.setattr(sp, "_build_production_identity_provider", ...)`（约 `1440` 行）。
- WIP 文件 `dayu/services/startup_preparation.py` 已不再存在 `_build_production_identity_provider`，仅有 `_build_production_services_provider`（约 `381` 行）。
- 结果是该黑盒测试在执行 monkeypatch 时直接触发属性缺失失败（与目标映射无关），导致完整 PG16 integration 入口不可执行。
- 这是高优先级阻断，因为它把一条非目标测试从“应该保留并跑通”的 PG16 入口变成必失败，违反“allowlist 精简 + minimal change”意图中的执行闭环边界。

### 3) two-service mapping / JobService / PostgresJobStore / Host 注入 / shared-engine 生命周期

- `exact two-service`：WIP 已达到，见 `_build_production_services_provider` 映射。
- `JobService` 类型与 `platform_service_name`：
  - 注入 `job_service = JobService(...)`（约 `408` 行）。
  - `platform_service_name` 为常量 `durable_jobs`，与 mapping 约束一致。
- `PostgresJobStore session_factory-only`：`PostgresJobStore(preparation.session_factory)`（`job_store` 仅接收 `session_factory`，第 `408` 行附近）。
- Host 注入在 Host 构造后：在 `prepare_host_runtime_dependencies` 中 Host 创建后才调用 `_build_production_services_provider(..., host_run_reader=host)`（约 `887` 行）。
- shared-engine 生命周期：`_prepare_production_platform_dependencies` 中 `InvestmentIdentityService(..., owned_engine=engine)`（约 `356` 行），且该 identity service 被作为 auto-created 生命周期 owner 回传与 close 一次性释放（约 `470` 行 + 相关 lifecycle wrapper）。

### 4) 完整 PG16 lane 与 stop 条件可执行性

- `plan-fix` 要求完整 lane（含 `test_identity_repositories_postgres.py`）继续可复用，并保持原有 close/placeholder 等测试不改。
- 当前 WIP 与现有测试耦合使该要求无法满足：缺失的 `_build_production_identity_provider` 会先于业务断言触发失败，不是可通过“仅重命名 black-box 映射测试”覆盖的路径。
- 因此 stop 条件“只改名断言不扩 allowlist 及不改其它测试”的前提下，当前状态不可安全放行到 implementation。

## 裁决

- **FAIL（阻断）**：必须先处理测试耦合兼容点（至少保证 `test_production_provider_s3_placeholder_still_rejected` 中的 helper patch 点可稳定运行）后，再重新提交两路 plan re-review。
