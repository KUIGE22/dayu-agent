# Code Re-Review

## Scope

- Mode: current changes (independent re-review)
- Branch: `codex/investment-platform`
- Base: `ee75d17955a4a8f30a56a02cae56fac34df79be5`
- Output file: `docs/reviews/code-rereview-20260817-slice-2.3-item7-startup-registration-mimo.md`
- Actual model: `xiaomi/mimo-v2.5`
- Included scope: post-fix exact-seven candidate — `dayu/services/startup_preparation.py`, `tests/application/test_service_startup_preparation.py`, `tests/integration/investment/test_identity_repositories_postgres.py`, `README.md`, `tests/README.md`, `dayu/README.md`, `dayu/investment/README.md`
- Excluded scope: implementation/fix/review artifacts, tests/pyright/PG/Docker/network, any DeepSeek review output, Git writes, cache
- Parallel review coverage: 无，主 reviewer 逐文件走读
- First review artifact: `561d594b76313ff2bfe6ae01b791bfbc415c008f19a5ec4207bd63dc9683ce64 / 156 / 12708`
- Fix artifact: `8b3599bb3c5e5f865132ad6a64f82d0f065d956b2a4a74c0c58736780677be15 / 162 / 8827`

## START identity drift gate

| item | required | actual | pass |
|---|---|---|---|
| branch | `codex/investment-platform` | `codex/investment-platform` | ✓ |
| HEAD | `ee75d17955a4a8f30a56a02cae56fac34df79be5` | `ee75d17955a4a8f30a56a02cae56fac34df79be5` | ✓ |
| index | empty | empty | ✓ |
| candidate diff SHA-256 | `cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9` | `cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9` | ✓ |
| implementation artifact | `4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f / 219 / 14375` | match | ✓ |
| first review artifact | `561d594b76313ff2bfe6ae01b791bfbc415c008f19a5ec4207bd63dc9683ce64 / 156 / 12708` | match | ✓ |
| fix artifact | `8b3599bb3c5e5f865132ad6a64f82d0f065d956b2a4a74c0c58736780677be15 / 162 / 8827` | match | ✓ |
| output path absent | not exist | not exist | ✓ |

### F-01 closure verification

首审 F-01（Low）：PG module docstring "exact-three" stale truth 与 exact-four black-box 矛盾。

Fix artifact 实施的修改：
1. Module docstring line 12：`三个真实 Service` → `四个真实 Service`
2. Module docstring line 13-14：补入 `investment_sources`（`InvestmentSourcesService`）
3. Test renamed：`test_production_provider_wires_exact_three_service_mapping` → `test_production_provider_wires_exact_four_service_mapping`
4. Test docstring：`exact three-service mapping` → `exact four-service mapping`，补入 exact-four key set 描述

Re-review 独立验证：
- `grep "exact.three|精确承载三个|三个真实" tests/integration/investment/` → 0 hits
- `grep "exact.three|精确承载三个|三个真实" dayu/services/startup_preparation.py` → 0 hits
- Module docstring 当前状态（line 12-17）：`四个真实 Service` + 四项 service 名 + correct types
- Test name 当前状态：`test_production_provider_wires_exact_four_service_mapping`
- Test body 当前状态：exact-four key set + 4 个 isinstance 断言 + shared session_factory identity

**F-01 status: CLOSED — stale text fully purged, no regression.**

## Findings

未发现实质性问题。

## Detailed evidence (fresh five-perspective review)

### 1. Correctness

**真实入口**：`_prepare_host_runtime_after_queue_admission()` → `_build_production_services_provider()` → `_ProductionServicesProvider.provide_services()` → `build_platform_composition()`。

**阶段 2 assembly 顺序**：JobStore/ScheduleStore → registries → JobService/ScheduleService → FinsService → FinsSourceConnector → PostgresSourceSyncRepository → SourceConnectorRegistry → InvestmentSourcesService → SourceSyncExecutionService → SourceSyncExecutionHandler → register descriptor/handler → seal → 6 项 assertion → _ProductionServicesProvider。每步依赖前步产物，无环依赖。

**Seal/assert 穷举**：`is_sealed`（descriptor/execution）× `count`（descriptor/handler）× `lookup`（descriptor/handler）× identity（descriptor/handler）= 6 项，全部在 composition 前完成。任何一个失败都抛 `PlatformCompositionError`，不会发布不完整 mapping。

**Auto-provider vs explicit provider 互斥**：`_default_provider_or_fail` 返回 `(explicit_provider, None, None)` 或 `(None, preparation.identity_service, preparation)`。两者在 `_prepare_host_runtime_after_queue_admission` 中通过 `resolved_provider is not None` vs `platform_preparation is not None` 分支互斥。

### 2. Resource lifecycle / close order

成功路径 `PreparedHostRuntimeDependencies.close()`：queue_admission → writer_lease → s3_store → platform_lifecycle。逆依赖序正确。

失败路径（19-stage matrix）：`except` 块中 `lifecycle_registration.close()` / `owned_lifecycle.close()` → `lease_registration.close()` → `s3_store.close()` → `queue_admission.close()`。每个资源恰好 dispose 一次。

`_OwnedLifecycleRegistration` 双标记（`_registered` + `_closed`）确保 atexit callback 与 manual close 互斥、register exact-once。

### 3. Idempotency

- `PreparedHostRuntimeDependencies.close()`：幂等（`_owned_platform_lifecycle.close()` 委托 `_OwnedLifecycleRegistration.close()`，`_closed` 标记）
- `_PreparedQueueAdmission.close()`：幂等（`_closed` 标记）
- `_OwnedLifecycleRegistration.close()`：幂等（`_closed` 标记）
- `_OwnedS3LeaseRegistration.close()`：幂等（`_closed` 标记）
- PG black-box test 验证三次 `prepared.close()` 后 `dispose_calls == 1`

### 4. Ordering / branch correctness

- descriptor registration 在 seal 之前（seal 后不可注册）
- seal 在 assertion 之前（assertion 依赖 sealed state）
- assertion 在 provider 构造之前（确保 mapping 完整）
- provider 构造在 composition 之前（composition 消费 provider mapping）
- `_PreparedQueueAdmission.__post_init__` closed shape 分支：NOT_REQUIRED/POSTGRES_ONLY/REDIS 三路互斥，每路有 early return

### 5. Parameter effectiveness

- `host` 传入 `_build_production_services_provider`，分别作为 `host_run_reader=host` 和 `host_run_canceller=host`：Host 同时满足 `HostRunReaderProtocol` 和 `HostRunCancellationProtocol`，参数链路清晰
- `fins_runtime` 传入后直接绑定到 `FinsService(host=host, fins_runtime=fins_runtime)`，无覆盖/丢失
- `queue_settings` 传入后直接绑定到 `ScheduleService(schedule_max_lookback_seconds=...)` 和 `ScheduleService(schedule_candidate_scan_limit=...)`

### 6. Type safety

- 所有公共 Service 满足对应 Protocol（`PlatformServiceProtocol` / `PlatformIdentityServiceProtocol` / `PlatformSourceSyncServiceProtocol`）
- 具体 narrowing（`isinstance(PostgresJobStore)` 等）仅出现在测试中，不泄漏到生产代码
- AST guard `test_startup_preparation_test_avoids_escape_patterns` 守护 `Any/object/cast/type:ignore/getattr/hasattr` 逃逸
- Pyright `0 errors, 0 warnings, 0 informations`

### 7. Architecture / overcoupling

- 单向依赖：`startup_preparation.py` → composition/domain/storage 协议层，无反向 import
- Protocol 边界清晰：`SourceSyncExecutionServiceProtocol`、`PlatformSourceSyncServiceProtocol`、`PlatformCompositionProviderProtocol`
- 具体类型仅在 composition root 内部使用，不暴露给上层
- 无跨层穿透、双向依赖、共享可变状态

### 8. Structural clarity

- `_build_production_services_provider` 职责收敛：构造 → 注册 → 封存 → 断言 → 返回。无 god function 风险
- `_ProductionServicesProvider` 是纯 wrapper，`provide_services()` 返回 frozen mapping
- `_PreparedQueueAdmission` 是 closed shape value object，`__post_init__` 做 exhaustive validation
- 无布尔标记驱动的隐式流程

### 9. Adversarial failure pass

- **Phase-1 failure（PG 连接/DSN/probe）**：`_prepare_production_platform_dependencies` 中 engine dispose exactly-once，不泄漏。由独立 application test `test_unreachable_dsn_fails_safely`/`test_malformed_dsn_fails_safely` 和 PG black-box test `test_production_provider_wrong_role_rejected`/`test_production_provider_missing_dsn_safe_failure` 覆盖
- **Phase-2 failure（19 stages）**：每个 stage 精确命中 1 次，close_order 精确 `["pg", "lease", "s3", "redis"]`，recovery 不触发，composition 不包含任何半成品
- **Double publish**：auto-provider 和 explicit provider 路径互斥，不存在同一启动中两次 publish
- **Race condition**：startup composition 是单线程同步执行
- **Stale state after close**：close 后 registry state 不变（测试 `test_explicit_production_provider_keeps_identity_...` 的 close 后断言）
- **Observability**：失败抛出 `PlatformCompositionError`/`RuntimeError`，不静默吞错

### 10. Test coverage (fresh assessment)

**Application tests (64 tests)**：
- Assembly order recorder（15-stage）证明唯一依赖顺序
- 19-stage failure matrix parametrize 证明每个 failure 点精确 close 一次
- Closed-shape admission 6 分支逐路径覆盖
- Explicit provider zero side-effect（11 个 trap probe 全部 0 hits）
- 5 个 `_OwnedLifecycleRegistration` 子测试证明 atexit 协调语义
- AST guard 证明测试文件自身无逃逸

**PG black-box tests (17 tests)**：
- exact-four key set + 4 个 isinstance + shared session_factory identity
- double-close proof（三次 close 后 dispose_calls == 1）
- S3 placeholder rejected before PG/provider
- Wrong role rejected with DSN suppressed
- Missing DSN safe failure
- Close failure propagation + cleanup

**Residual test gap**：phase-1（`_prepare_production_platform_dependencies`）内部 PG 连接失败由 application test 的 DSN probe tests + PG black-box 的 wrong-role/missing-DSN tests 组合覆盖，无显著缺口。

### 11. Documentation (post-fix)

- PG module docstring：`四个真实 Service` + `investment_identity` + `investment_sources` + `durable_jobs` + `durable_schedules` — correct
- 根 `README.md`：`:134` byte-identical；`:385-388` replacement 正确
- `tests/README.md`：exact-four description 正确
- `dayu/README.md`：exact-one handler + 四项 Service 正确
- `dayu/investment/README.md`：exact-one handler 注册正确
- 四 README 均不声明 Item 8 完成

## Open Questions

无。

## Residual Risk

- 本 work unit 不包含 Item 8 final CI / nine-lane scope。
- 19-stage failure matrix 覆盖 phase-2 全部构造/注册/封存/断言/发布阶段；phase-1 由独立 tests 覆盖。
- S3 head_bucket 探活失败路径由 `_should_build_s3_store` + `_build_s3_store_from_settings` 异常传播覆盖，不在 Item 7 focused scope。

## Verdict

**PASS** — 0 High / 0 Medium / 0 Low

## END identities

| path | SHA-256 | lines | bytes |
|---|---|---|---|
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e` | 1689 | 63289 |
| `tests/application/test_service_startup_preparation.py` | `2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545` | 4123 | 130135 |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `1cefaee33dd0a2e93b236e36171efc2aced09dba4863872982eabe54b64c492e` | 2124 | 73611 |
| `README.md` | `d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94` | 2407 | 153621 |
| `tests/README.md` | `1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f` | 612 | 132898 |
| `dayu/README.md` | `8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5` | 1297 | 65205 |
| `dayu/investment/README.md` | `1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331` | 333 | 22921 |

## Boundary proof

- candidate diff SHA-256 与 post-fix canonical 一致
- 七文件 END identities 与 fix artifact §5 完全一致
- F-01 stale exact-three text fully purged（grep 0 hits）
- implementation / first-review / fix artifact identities 未被修改
- 无额外 untracked 文件（仅 inherited artifacts）
- re-review artifact 为唯一写入
