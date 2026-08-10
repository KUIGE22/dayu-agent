# Plan Final Re-review — Slice 1.2 Repository/Provider

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.2 revised（S12-CTRL-01..06）+ 四份 reference 文档
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-final-rereview-20260810-slice-1.2-repository-provider-mimo-native.md`
- Source chain：Terra initial FAIL（H0/M2/L0）→ MiM initial PASS-WITH-RISKS（L2）→ Controller corrective fix → MiM corrective PASS（L2）→ Terra corrective FAIL（M2）→ Controller API/startup corrective fix（S12-CTRL-05/06）→ **本 final closure**
- Focus：S12-CTRL-05/06 是否闭合 Terra-S12-001/002 + MiM-001/002

## Prior Findings Closure Verification

### TERRA-S12-001 (Medium) — UUID Tenant Admission + DTO/API → CLOSED ✅

**S12-CTRL-05 修订内容**（plan lines 653-740）：

1. **Canonical UUID boundary**：小写、带连字符 `8-4-4-4-12`，`str(UUID(value)) == value`；不接受大写/无连字符/nil/空白；`TenantId`/`CompanyId`/`SecurityId` 保持通用 pure identifier 不改 `identifiers.py`；repository 入口二次校验 `scope.tenant_id` 与所有 ID；非法值抛 `RepositoryInputError`，不得执行 SQL。✅

2. **Exact DTO fields**：冻结 `CompanyCreateRequest`/`SecurityCreateRequest`/`CompanySecurityRegistration`/`CompanyProjection`/`SecurityProjection`/`RegisteredCompanySecurity`/`SourceDefinitionCreateRequest`/`SourceDefinitionProjection`/`SourceSubscriptionCreateRequest`/`SourceSubscriptionUpdateRequest`/`SourceSubscriptionProjection`——每个字段的 Python type、nullable、enum、JSON 约束全部明确。✅

3. **Exact error hierarchy**：`RepositoryError(RuntimeError)` → `RepositoryInputError` / `RepositoryNotFoundError` / `RepositoryConflictError` → `RepositoryOptimisticConflictError`；消息为固定 safe code，不含 DSN/SQL/候选值。✅

4. **Protocol exact methods**：`IdentityRepositoryProtocol`（4 methods）+ `SourceRepositoryProtocol`（6 methods）——每个方法签名、参数类型、返回类型、异常类型全部冻结。✅

5. **Atomic registration**：单 DB transaction，禁止 application delete/补偿/第二 transaction/partial commit。✅

### TERRA-S12-002 (Medium) — Production Default Provider Black-box → CLOSED ✅

**S12-CTRL-06 修订内容**（plan lines 741-766）：

1. **Public entry**：`prepare_host_runtime_dependencies(..., platform_provider=None)` 作为唯一 black-box 入口。✅

2. **Production default path**：enabled+production 且 provider=None → 读取 `settings.postgres_dsn_env` 指向的 env 值 → 构造默认 provider。显式 provider 非空时优先，不读取/构造 default。✅

3. **DSN safe failure**：missing/blank DSN → `PlatformSettingsError`（engine 创建前）；nonblank but malformed/unreachable/wrong-role → `PlatformCompositionError("production PostgreSQL identity provider 初始化失败")`，不带 cause value；`str/repr`/logs 不含 raw DSN/password/URL-encoded password/env value。✅

4. **Engine ownership/cleanup**：auto-created provider 在任何后续 failure 时必须 dispose engine；显式 provider 由 caller own；成功时 engine lifetime 由 `InvestmentIdentityService.close()` 持有；black-box finally 必须调用 `close()`。✅

5. **PG16 black-box**：迁移随机数据库 → 创建临时 `LOGIN NOBYPASSRLS IN ROLE dayu_platform_app` application DSN → 仅设置 production profile + 四项 env presence → 从 public `prepare_host_runtime_dependencies(..., platform_provider=None)` 进入 → 断言精确一个 `investment_identity` service → 通过该 service 完成 company/security registration + private subscription read → `close()`。✅

6. **Future owner exclusion**：导入审计证明 jobs/evidence/portfolio future module 未加载。✅

### MiM-001 (Low) — Error Class Naming → CLOSED ✅

S12-CTRL-05 冻结五类 stable error hierarchy：`RepositoryError` → `RepositoryInputError` / `RepositoryNotFoundError` / `RepositoryConflictError` → `RepositoryOptimisticConflictError`。✅

### MiM-002 (Low) — Atomic Rollback DB Transaction → CLOSED ✅

S12-CTRL-05 明确 "只允许一个数据库事务"，禁止 application delete/补偿 cleanup、第二 transaction 或部分 commit。✅

## S12-CTRL-05/06 Detailed Verification

### Canonical UUID Boundary

- `TenantId`/`CompanyId`/`SecurityId` 保持通用 pure identifier，不改 `identifiers.py` ✅
- `source.py` 构造期校验 embedded ID；repository 入口二次校验 ✅
- 非法值 → `RepositoryInputError`，不得执行 SQL ✅
- 不得传播 psycopg/SQLAlchemy UUID cast error ✅

### Production Startup Path

- `prepare_host_runtime_dependencies(..., platform_provider=None)` 是 public entry ✅
- `platform_provider` 非空时优先，不读取/构造 default ✅
- enabled+production+None → 读取 env → 构造 default provider ✅
- enabled+development+None → stable fail-fast ✅
-不得用 PG 冒充 in-memory ✅

### DSN Secret Safe

- missing/blank → `PlatformSettingsError` ✅
- malformed/unreachable/wrong-role → `PlatformCompositionError` 不带 cause ✅
- `str/repr`/logs 不含 raw DSN/password/URL-encoded password/env value ✅

### Engine Ownership

- auto-created engine 在 failure 时 dispose ✅
- explicit provider 由 caller own ✅
- success 时 engine lifetime 由 `InvestmentIdentityService.close()` 持有 ✅
- black-box finally 必须调用 `close()` ✅
- 不得把 engine/session/provider 暴露到 UI 或通用 composition API ✅

### PG16 Integration

- 复用 Slice 1.1 owner-labeled fixture ✅
- 禁止 SQLite/fake ✅
- black-box 测试场景：default provider → registration → subscription read → close() ✅
- DSN failure 测试：missing/blank/malformed/unreachable → safe error + zero side-effect + engine disposed ✅
- 导入审计：jobs/evidence/portfolio 未加载 ✅

### Allowlist/DAG/No Future Owner

- Allowlist 包含 domain/source.py、storage/protocol、具体 Service、startup、integration/doc ✅
- Import DAG 单向：domain ← storage ← service ← startup ✅
- "不得预注册 jobs/evidence/portfolio 等 future-slice owner" ✅
- `startup/platform.py` 不 import future owner ✅

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- S12-CTRL-05 的 frozen DTO/API 是 "at minimum" 语义——implementation agent 可以添加额外字段或方法，但必须在同 slice 内且不改变已有签名。风险低。
- S12-CTRL-06 的 black-box 测试需要定义最小 production config fixture；应只放在 PG16 integration lane。风险低。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra-S12-001（UUID tenant admission + DTO/API）和 Terra-S12-002（production default provider black-box）均已通过 S12-CTRL-05/06 闭合。MiM-001（error class naming）和 MiM-002（atomic rollback DB transaction）均已闭合。S12-CTRL-01..06 全部闭合：canonical UUID boundary、exact DTO/API/errors、单 DB transaction rollback/CAS、public `prepare_host_runtime_dependencies(..., platform_provider=None)` production path、DSN secret-safe failure、engine ownership/cleanup、PG16 integration、allowlist/DAG/no future owner。允许进入 accepted plan commit。
