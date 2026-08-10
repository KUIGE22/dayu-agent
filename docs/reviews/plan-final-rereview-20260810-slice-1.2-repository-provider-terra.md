# Slice 1.2 repository/provider corrective final plan re-review — Terra

- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2，重点 S12-CTRL-05/06。
- **完整输入**：前次 Terra、MiM Native、Controller plan-gap fix、API/startup corrective fix 四份 review/fix artifact，以及当前 plan、`dayu/investment/config.py`、composition、public startup、Slice 1.1 migration/RLS/role grants 与现有 startup tests。
- **方式**：只读对抗审查；未启动 Docker/PG16、未连接 live/broker，未修改 plan、代码、测试或 README。
- **结论**：**FAIL**；open **H0 / M1 / L0**。S12 implementation 继续冻结。

## 逐项 closure 复证

| 事项 | 结论 | 直接证据 |
| --- | --- | --- |
| TERRA-S12-001：canonical UUID、exact DTO/API/errors | 已闭合 | S12-CTRL-05 固定小写 hyphenated UUID、逐 DTO/projection 字段、closed enum、JSON admissibility、五层 stable error、invalid scope/ID no-SQL negative；保留纯 `TenantId` 通用契约而在 DTO/repository physical boundary 收窄，与 `identifiers.py` 现状和 UUID/RLS schema 相容。 |
| MiM-001：error hierarchy | 已闭合 | `RepositoryError`、Input、NotFound、Conflict、OptimisticConflict 的继承与 fixed-safe message 已明确。 |
| MiM-002：atomic rollback | 已闭合 | S12-CTRL-05 明确仅一个 `Session.begin()` DB transaction，第二 insert failure 由 rollback 回收，禁止补偿 delete、第二 transaction、partial commit，并要求 PG16 fresh-transaction 断言。 |
| TERRA-S12-002：production no-provider path / secret error | 已闭合 | S12-CTRL-06 指定从实际 `prepare_host_runtime_dependencies(..., platform_provider=None)` 进入；与当前该函数的 public signature、`load_platform_settings()` 的 `postgres_dsn_env` name-only contract 相符。missing/blank 在建 engine 前由 `PlatformSettingsError` 拒绝，nonblank failure 统一为固定 `PlatformCompositionError`，并要求 `str/repr`/pytest logs 脱敏。 |
| RLS、CAS 与 PG16 lane | 已闭合 | protocol 将 subscription update 固定为 `tenant_id + id + version`；不存在/跨 tenant 与 stale version 有不同的安全错误语义。测试要求随机 migrated PG16 database、`LOGIN NOBYPASSRLS IN ROLE dayu_platform_app` DSN、public startup black-box、无 SQLite/fake 与 owner-label cleanup，符合 Slice 1.1 grants/RLS。 |
| allowlist / DAG / future owner | 已闭合 | 允许路径恰好覆盖 DTO、protocol、Postgres implementation、composition/startup、Service、unit/PG16/docs；不含 schema/migration/future jobs/evidence/portfolio，且计划要求导入审计。 |

## Finding

### TERRA-S12-FINAL-001-未修复-中-成功态 auto-created engine 没有公开且类型安全的生命周期 owner

- **位置**：S12-CTRL-06（auto-created engine success lifetime/`InvestmentIdentityService.close()`）；当前 `dayu/services/startup_preparation.py` 第 77–96、133–247 行，`dayu/investment/composition.py` 第 35–69、80–110 行。
- **问题类型**：架构边界 / 资源所有权 / 不可直接实施。
- **当前写法**：计划规定成功时 engine 由返回组合中的 concrete `InvestmentIdentityService` 持有，Service 提供幂等 `close()`；integration finally 调用它，同时禁止把 engine/session/provider 暴露给 UI 或通用 composition API。
- **反例/失败场景**：production 调用公开 `prepare_host_runtime_dependencies(..., platform_provider=None)` 成功后，只得到 `PreparedHostRuntimeDependencies.platform_composition: PlatformComposition[PlatformServiceProtocol]`。`PlatformServiceProtocol` 当前仅有 `platform_service_name`，`PlatformComposition` 也没有 `close()`；`PreparedHostRuntimeDependencies` 同样没有关闭方法。正常 CLI/WeChat 生命周期没有一个声明的、类型安全的 owner 能调用 concrete service 的 `close()`。重复 startup/test worker 或长驻运行结束时，pool/connection 的回收只能依赖垃圾回收或未声明的 downcast，二者都不满足计划的 cleanup claim。
- **为什么有问题**：这不是测试 finally 可以掩盖的细节。计划同时要求成功态 engine ownership/cleanup、严格 protocol boundary，且禁止向通用 composition API 泄漏 engine；当前描述却把唯一 close handle 藏在以 `PlatformServiceProtocol` 类型暴露的 registry value 中。实现 agent 必须自行决定是下转具体类型、把 `close()` 加到 base protocol、让 `PreparedHostRuntimeDependencies` 承担关闭、还是另设 lifecycle owner；各方案对既有 `PlatformComposition`、其测试和 future services 的影响不同，无法由当前 allowlist 与验证条款唯一选择。
- **直接证据**：`prepare_host_runtime_dependencies()` 只返回五项既有 runtime dependency 加 `platform_composition`，函数末尾无 teardown owner；`PlatformCompositionProviderProtocol.provide_services()` 返回 `Mapping[str, PlatformServiceProtocol]`，而 `PlatformServiceProtocol` 只有名称 property。S12-CTRL-06 的 black-box 仅要求 test finally 调用 concrete `close()`，没有规定 production shutdown 从何处调用或怎样避免类型逃逸。
- **影响**：真实 production default-provider 路径可在测试中 green，却在应用运行结束、失败后的 retry 或多次启动时泄漏 SQLAlchemy engine/pool connections；或 implementation 以 `cast`/`getattr` 绕过严格类型和稳定依赖边界。
- **建议改法和验证点**：在 S12-CTRL-06 选择并冻结一个唯一 lifecycle contract，同时把其真源与受影响测试加入 allowlist。例如：由 `PreparedHostRuntimeDependencies` 在 Service 层提供幂等 `close()`，仅调用一个纯层定义的 minimal `PlatformLifecycleProtocol.close()`，而 `PlatformComposition` 持有不暴露 engine 的 lifecycle owner；或把 lifecycle 纳入 `PlatformServiceProtocol` 并明确所有 provider/service 的实现义务。无论选择哪种，都须：成功 public startup 后由声明类型可调用一次/两次 shutdown；断言 engine disposed、业务数据未变；explicit provider 仍由 caller own；startup 任一点失败仍零 owned engine；避免 `cast`、`getattr` 或暴露 repository/session。若变更既有 `composition.py` 的 stable base protocol，必须把其现有真源测试（如 `tests/investment/test_platform_config.py`）纳入最小 allowlist，不能仅改未覆盖的实现文件。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：中。

## Open questions

无。该 finding 可由当前公开返回类型与 S12-CTRL-06 文本直接复现，不依赖 future-slice 决策。

## Residual risk / tracking

上述 M 关闭后，S12 仍应只实现计划已冻结的 13 表 consumer，不得改 schema/migration/DAG、加载 future owner，或以 SQLite/fake、direct provider construction 替代 real PG16 public startup lane。引擎生命周期属于当前 Slice 1.2 startup owner，不能后移给 future jobs/evidence/portfolio slice。

## 最终裁决

**FAIL，open H0 / M1 / L0。** S12-CTRL-05 已闭合前次 UUID/API/error/transaction finding，S12-CTRL-06 也已闭合 default provider、secret failure 与 PG16 public-path 覆盖；但成功态 engine 的关闭 owner 尚未成为可实现且类型安全的公开契约。补齐该最小 lifecycle contract 后方可给 final PASS。
