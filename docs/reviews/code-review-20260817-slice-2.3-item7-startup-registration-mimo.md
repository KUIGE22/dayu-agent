# Code Review

## Scope

- Mode: current changes (strict deepreview)
- Branch: `codex/investment-platform`
- Base: `ee75d17955a4a8f30a56a02cae56fac34df79be5`
- Output file: `docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-mimo.md`
- Actual model: `xiaomi/mimo-v2.5`
- Included scope: exact-seven candidate files — `dayu/services/startup_preparation.py`, `tests/application/test_service_startup_preparation.py`, `tests/integration/investment/test_identity_repositories_postgres.py`, `README.md`, `tests/README.md`, `dayu/README.md`, `dayu/investment/README.md`
- Excluded scope: implementation artifact, accepted plan/fix/acceptance, tests/pyright/PG/Docker/network, any DeepSeek review
- Parallel review coverage: 无，主 reviewer 逐文件走读

## START/identity drift gate

| item | expected | actual | pass |
|---|---|---|---|
| branch | `codex/investment-platform` | `codex/investment-platform` | ✓ |
| HEAD | `ee75d17955a4a8f30a56a02cae56fac34df79be5` | `ee75d17955a4a8f30a56a02cae56fac34df79be5` | ✓ |
| index | empty | empty | ✓ |
| candidate diff SHA-256 | `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9` | `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9` | ✓ |
| implementation artifact | `4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f /219/14375` | match | ✓ |
| source WIP before/after identity | `73309aba…` (same before/after) | match | ✓ |
| exact-seven file identities | all 7 match §3 after SHAs | match | ✓ |
| review artifact absent | not exist | not exist | ✓ |

## Findings

未发现实质性问题。

## Detailed evidence

### 1. Change intent alignment

Item 7 的目标是在 production auto-provider 的 startup composition 中注册 exactly-one Source Sync handler 并发布四项 Service mapping（从三项扩展为四项）。实现完全在 `_build_production_services_provider()` 中完成，不修改任何其它生产入口。

### 2. Implementation path review

**真实入口**：`_prepare_host_runtime_after_queue_admission()` → `_build_production_services_provider()` → `_ProductionServicesProvider.provide_services()` → `build_platform_composition()`。

**阶段 1**（`_prepare_production_platform_dependencies`）：读取 DSN → 创建 engine → probe → 创建 session factory → 创建 `PostgresIdentityRepository` → 创建 `InvestmentIdentityService`。失败路径：engine dispose exactly-once。

**阶段 2**（`_build_production_services_provider`）：构造 `PostgresJobStore`/`PostgresScheduleStore`（共享 session factory）→ 构造 `JobHandlerRegistry`/`JobExecutionRegistry` → 构造 `JobService`/`ScheduleService` → 构造 `FinsService` → `FinsSourceConnector` → `PostgresSourceSyncRepository` → `SourceConnectorRegistry` → `InvestmentSourcesService` → `SourceSyncExecutionService` → `SourceSyncExecutionHandler` → 注册 descriptor/handler → seal → 6 项 assertion → 构造 `_ProductionServicesProvider`。

**Atomic publish**：`_ProductionServicesProvider.provide_services()` 返回精确四项 mapping → `build_platform_composition()` 构造 `PlatformComposition`。

**Seal/assert 穷举**：`is_sealed`（descriptor/execution）× `count`（descriptor/handler）× `lookup`（descriptor/handler）× identity（descriptor/handler），6 项全部在 composition 前完成。

### 3. Branch ordering

- `_build_production_services_provider` 中 descriptor/handler 注册在 seal 之前，seal 在 assertion 之前，assertion 在 provider 构造之前。没有分支重叠或抢先命中风险。
- `_PreparedQueueAdmission.__post_init__` 的 closed shape 分支：NOT_REQUIRED/POSTGRES_ONLY/REDIS 三路互斥，每路有明确的 early return，不存在宽条件抢先。

### 4. Protocol / architecture boundary

- `startup_preparation.py` 导入 `FinsSourceConnector`、`SourceConnectorRegistry`、`SourceSyncExecutionHandler`、`SourceSyncExecutionService`、`InvestmentSourcesService`、`FinsService` — 全部是 composition root 自身需要装配的具体类型，不构成跨层穿透。
- `SourceSyncExecutionService` 依赖 `SourceSyncExecutionServiceProtocol`（Protocol），`InvestmentsSourcesService` 依赖 `PlatformSourceSyncServiceProtocol`（Protocol）— 公共契约边界清晰。
- `FinsService` 在阶段 2 构造，`FinsSourceConnector` 持有 `FinsService` 作为 `fins_gateway`，`SourceConnectorRegistry` 持有 `FinsSourceConnector` — 构造方向单向，无循环依赖。
- `_ProductionServicesProvider` 对外只暴露 `provide_services()` → `Mapping[str, PlatformServiceProtocol]`，不泄漏内部 repository/registry/engine。

### 5. Resource lifecycle / close order

成功路径 `PreparedHostRuntimeDependencies.close()` 释放顺序：queue_admission → writer_lease → s3_store → platform_lifecycle。这是逆依赖序（Redis client 先于 lease，lease 先于 S3，S3 先于 PG engine lifecycle）。

失败路径（19-stage failure matrix）释放顺序（通过 `close_order` 共享列表验证）：`["pg", "lease", "s3", "redis"]`。`_prepare_host_runtime_after_queue_admission` 的 `except` 块依次关闭 lifecycle → lease → s3 → queue_admission。

`_OwnedLifecycleRegistration` 的 `register()` 为 exact-once（`_registered`/`_closed` 双标记）；`close()` 为幂等（`_closed` 单标记）；atexit callback 与 manual close 互斥（先到者赢 close 权）。

### 6. Double dispose / shared engine

`PostgresIdentityService` 持有 `owned_engine`，engine 在 `InvestmentIdentityService.close()` 中 dispose。`PreparedHostRuntimeDependencies` 通过 `_OwnedLifecycleRegistration` close 一次 identity service。`PreparedPlatformQueueRuntime` close 时委托 `existing_runtime.close()`，不重复 dispose engine。测试 `test_production_provider_close_disposes_engine_once` 在真实 PG 上验证三次 `prepared.close()` 后 `dispose_calls == 1`。

### 7. Explicit provider zero side-effect

`test_explicit_production_provider_keeps_identity_and_baseline_default_fins_runtime_eager_component_but_skips_all_source_specific_cross_platform_assembly` 验证：
- 调用方 owned descriptor/execution registry 不被 seal 或修改
- `_prepare_production_platform_dependencies` 不被调用（0 hits）
- `_build_production_services_provider` 不被调用（0 hits）
- 全部 7 个 source-specific constructor seam 不被调用（0 hits）
- composition 只包含调方提供的 `{"platform": platform_service}`

### 8. Application test coverage

- `test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four`：exact-four key set、concrete type、shared session_factory identity、sealed registry、count=1、handler lookup identity、source connector → fins service → host identity。
- `test_production_composition_constructs_job_schedule_public_source_and_execution_services_then_handler_before_atomic_publish`：15-stage assembly order recorder，exact 顺序断言。
- `test_production_provider_failure_disposes_one_engine_once`：parametrize × 19 failure stages，每个 stage 精确命中 1 次，close_order 精确 `["pg", "lease", "s3", "redis"]`，recovery 不触发。
- `test_queue_admission_rejects_each_invalid_closed_shape`：6 分支逐路径覆盖。
- `_OwnedLifecycleRegistration` 5 个子测试：manual→callback no-op、callback→once、prepared→no-op、pre-register→noop、register→exact-once、register-after-close→noop。

### 9. PG black-box test

`test_production_provider_wires_exact_four_service_mapping`：
- 真实 PG16 integration lane
- exact-four key set `{"investment_identity", "investment_sources", "durable_jobs", "durable_schedules"}`
- `isinstance` 断言：`PlatformIdentityServiceProtocol`、`PlatformSourceSyncServiceProtocol`、`InvestmentSourcesService`、`JobService`、`ScheduleService`、`PostgresSourceSyncRepository`、`PostgresJobStore`、`PostgresScheduleStore`
- shared session_factory identity：`job_store._session_factory is source_repository._session_factory`
- double-close proof：三次 `prepared.close()` 无异常
- teardown：login/roles/schema 全部归零

### 10. Documentation

- 根 `README.md`：`:134` byte-identical；`:385-388` replacement 精确描述 exact-one Source Sync handler、四项 Service、不含 research/Agent/Broker handler、区分 Compose deployment 与 platform composition。
- `tests/README.md`：更新 exact-four description、exact-one handler、shared session factory。
- `dayu/README.md`：同步 exact-one Source Sync handler + 四项 Service。
- `dayu/investment/README.md`：同步 descriptor/execution registry 注册 exact-one Source Sync handler。
- 四 README 均不声明 Item 8 完成。

### 11. AGENTS.md constraint compliance

- 架构硬约束 `UI -> Service -> Host -> Agent`：startup_preparation.py 是 Service 层 public surface，正确依赖下层 composition/domain/storage 协议，不反向依赖上层。
- 编码硬约束：无 `object`/`Any`/`cast`/`type:ignore`/`getattr`/`hasattr` 逃逸（AST guard `test_startup_preparation_test_avoids_escape_patterns` 守护）。
- 测试硬约束：pyright 0 errors、coverage ≥ 80%（80.48%）、全部通过。
- README 触发规则：命中 `dayu/services/` 修改 → 更新 `dayu/README.md`；`tests/` 修改 → 更新 `tests/README.md`；分层关系变化 → 更新根 `README.md` + `dayu/README.md`。

### 12. Adversarial failure pass

- **Resource leak on phase-2 failure**：`_prepare_host_runtime_after_queue_admission` 的 `except` 块处理了所有 `lifecycle_registration`/`lease_registration`/`s3_store`/`queue_admission` 的 close。如果 `platform_preparation` 非 None 但 `lifecycle_registration` 为 None（phase 2 失败），`owned_lifecycle.close()` 被正确调用。✓
- **Double publish**：composition 只在 `platform_composition` 变量中构建一次。显式 provider 路径在 Host 前构建；auto-provider 路径在 Host 后覆盖。两者互斥（`resolved_provider is not None` vs `platform_preparation is not None`）。✓
- **Race condition**：startup composition 是单线程同步执行，不存在并发写入风险。✓
- **Idempotency**：`PreparedHostRuntimeDependencies.close()` 是幂等的（`_owned_platform_lifecycle.close()` 委托 `_OwnedLifecycleRegistration.close()`，`_closed` 标记防重入）。✓
- **Stale state after close**：close 后 registry seal/lookup/state 不变（测试 `test_explicit_production_provider_keeps_identity_and_baseline_default_fins_runtime_eager_component_but_skips_all_source_specific_cross_platform_assembly` 的 close 后断言）。✓

## Open Questions

无。

## Residual Risk

- 本 work unit 不包含 Item 8 final CI / nine-lane scope，剩余未覆盖项在 accepted plan scope 内。
- 19-stage failure matrix 覆盖了全部构造/注册/封存/断言/发布阶段，但不覆盖 phase 1（`_prepare_production_platform_dependencies`）内部的 PG 连接失败 — 该阶段由独立的 application test `test_unreachable_dsn_fails_safely` / `test_malformed_dsn_fails_safely` 和 PG black-box test `test_production_provider_wrong_role_rejected` / `test_production_provider_missing_dsn_safe_failure` 覆盖。
- S3 store head_bucket 探活失败路径由 `_should_build_s3_store` + `_build_s3_store_from_settings` 的异常传播覆盖，不在 Item 7 focused scope 内。

## Verdict

**PASS** — 0 High / 0 Medium / 0 Low

## END identities

| item | SHA-256 | lines | bytes |
|---|---|---|---|
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e` | 1689 | 63289 |
| `tests/application/test_service_startup_preparation.py` | `2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545` | 4123 | 130135 |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `b0049d210864fd3246562c50e926b90793169b6fc694a60401b88d4478004d53` | 2123 | 73549 |
| `README.md` | `d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94` | 2407 | 153621 |
| `tests/README.md` | `1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f` | 612 | 132898 |
| `dayu/README.md` | `8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5` | 1297 | 65205 |
| `dayu/investment/README.md` | `1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331` | 333 | 22921 |

## Boundary proof

- candidate diff SHA-256 与 §6 canonical 一致
- 七文件 END identities 与 §3 after 完全一致
- implementation artifact SHA/lines/bytes 与 handoff 一致
- accepted master/fix/acceptance identity 未被修改
- 无额外 untracked 文件（仅 implementation artifact）
- review artifact 为唯一写入
