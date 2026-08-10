# Plan Review — Slice 1.2 Repository/Provider Erratum

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.2（lines 590-648）+ `docs/reviews/plan-fix-20260810-slice-1.2-repository-provider-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-review-20260810-slice-1.2-repository-provider-mimo-native.md`
- Focus：API/codegen completeness、tenant transaction/RLS、atomic/CAS、service/provider owner & import DAG、production/dev profile、secret、real PG16 lane、README/allowlist、future owner leakage

## Assumptions Tested

1. S12-CTRL-01 的 repository API 足够让 implementation agent 生成正确的 protocol + PostgreSQL implementation。
2. transaction-local tenant boundary（SET LOCAL + explicit predicate + RLS）在 PostgreSQL 16 中可实现且安全。
3. atomic registration 和 CAS update 的语义足够精确。
4. Service/provider owner 和 import DAG 不会引入反向依赖。
5. production default provider 和 dev fail-fast 行为足够明确。
6. 真实 PG16 integration lane 的测试契约足够证明所有关键行为。

## Verification

### API/Codegen Completeness (S12-CTRL-01)

**Source DTOs**：plan 要求 `dayu/investment/domain/source.py` 至少包含 company/security/source-definition/source-subscription 的 create/update request 与 read projection，以及 `SourceDefinitionId`/`SourceSubscriptionId` 强标识。"所有 UUID、ticker、MIC、currency、status、version 与 JSON config 在进入 storage 前严格校验；禁止 ORM row、SQLAlchemy 类型、`Any/object` 向 Service 泄漏。"

✅ DTO 类型有明确的校验约束和禁止泄漏规则。Implementation agent 可基于 13 表 schema 推导 exact fields。

**Repository protocols**：`IdentityRepositoryProtocol` 与 `SourceRepositoryProtocol`，"每个公开方法首参均显式为 `TenantScope`"。API 包括：
- identity：atomic company+security registration、按 id 读取、`(exchange_mic,ticker)` 查找
- source：source-definition registration/read、subscription create/read、`expected_version` CAS update

✅ API 面足够具体，implementation agent 可直接生成 protocol 签名。

**PostgreSQL implementation**：S12-CTRL-01 规定 "每个方法自己拥有一个 `Session.begin()` 事务，第一条数据库语句必须用 bind parameter 调用 `set_config('app.tenant_id', :tenant_id, true)`"。

✅ `set_config` 语法正确（PostgreSQL 9.5+ 支持 `is_local=true` 参数）。

### Tenant Transaction/RLS (S12-CTRL-01)

三层隔离机制：

| 层 | 机制 | 规格 |
|----|------|------|
| 1 | `SET LOCAL app.tenant_id` | 每个事务第一条语句用 bind parameter 设置，`is_local=true` 保证事务结束自动恢复 |
| 2 | 显式 tenant predicate | "所有私有 query 同时带显式 tenant predicate" |
| 3 | RLS | "RLS 是第二道边界"——`tenant_isolation` policy `FOR ALL TO dayu_platform_app` |

**验证**：
- `SET LOCAL` 是事务级，commit/rollback 后自动恢复——不会泄漏到下一个事务 ✅
- 显式 predicate + RLS 双层：即使 RLS 被意外绕过（例如 definer view），显式 predicate 仍保护 ✅
- plan 要求 "每次事务结束后 tenant setting 不泄漏"——由 `SET LOCAL` 的 `is_local=true` 保证 ✅

### Atomic/CAS (S12-CTRL-01)

**Atomic registration**："atomic registration 任一后续 insert 失败必须回滚前序 public-reference insert"。

✅ 语义明确：company（public）和 security（public）的联合注册必须原子——如果 security insert 失败，company insert 也必须回滚。

**CAS update**："'expected_version' CAS update"。

✅ 语义明确：UPDATE WHERE version = expected_version，如果 affected rows = 0 则抛 optimistic-conflict error。

### Service/Provider Owner & Import DAG (S12-CTRL-02)

**Import DAG**：

```text
domain/source.py (pure DTO)
    ↓
storage/protocols.py (pure protocol)
    ↓
storage/postgres_identity.py (SQL implementation)
    ↓
services/investment_identity.py (Service owner)
    ↓
services/protocols.py (re-export)
    ↓
startup_preparation.py (provider assembly)
    ↓
startup/platform.py (generic composition validator)
```

**Owner boundaries**：
- `PlatformIdentityServiceProtocol` 真源在纯层 `composition.py`，re-export 在 `services/protocols.py` ✅
- `InvestmentIdentityService` 具体 owner 在 `services/investment_identity.py` ✅
- Provider assembly 在 `startup_preparation.py` ✅
- `startup/platform.py` 保持通用，不 import future owner ✅

**反向依赖检查**：
- storage 不导入 service/startup ✅
- service 不导入 storage（通过 protocol）✅
- startup 不导入 service（通过 composition protocol）✅

### Production/Dev Profile (S12-CTRL-02)

**Production**："startup_preparation.py 在 platform enabled + production 且未显式注入 provider 时，只读取 `PlatformSettings.postgres_dsn_env` 指向的环境变量值，构造关闭 echo 的 engine/session factory、PostgreSQL repository、`InvestmentIdentityService` 与只含 `investment_identity` 的 provider"。

✅ 行为明确：production default = PostgreSQL repository + identity service。

**Development**："development in-memory profile 在本 slice 不得假造 production repository，缺显式 provider 时继续 fail-fast"。

✅ 行为明确：dev profile 不提供 default provider，必须显式注入。

**Secret**："错误不得回显 DSN"。

✅ DSN 从环境变量读取，不存储在 config 中，错误消息不含 DSN。

### Real PG16 Lane (S12-CTRL-03)

**测试契约**：
- 复用 Slice 1.1 owner-labeled PG16 fixture ✅
- 禁止 SQLite/fake 代替 ✅
- 测试场景：unique conflict（company 行也不存在）、stale expected_version、cross-tenant isolation、public reference 可投影但 private subscription 按 tenant、tenant setting 不泄漏、production startup 只含一个 `investment_identity` Service、导入图不含 future module、owner resource 为零 ✅

### README/Allowlist (S12-CTRL-04)

**Allowlist**（plan line 592）：
- `dayu/investment/storage/protocols.py`、`postgres_identity.py` ✅
- `dayu/investment/domain/source.py` ✅
- `dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py` ✅
- `dayu/services/protocols.py`、`dayu/services/investment_identity.py` ✅
- tests: `test_identity_repositories.py`、`test_service_startup_preparation.py`、`test_identity_repositories_postgres.py` ✅
- docs: `dayu/investment/README.md`、`tests/README.md` ✅

**README 更新**：S12-CTRL-04 要求同步 source DTO、repository protocol/PostgreSQL owner、Service/provider 与依赖方向。

✅ Allowlist 完整，README 更新范围精确。

### Future Owner Leakage

**显式排除**：
- "不得预注册 jobs/evidence/portfolio 等 future-slice owner" ✅
- "导入图不含 jobs/evidence/portfolio future module" ✅
- `startup/platform.py` "不 import future jobs/evidence/portfolio owner" ✅
- "不得把 future jobs/evidence/portfolio、live source、broker 或自动交易标为已实现" ✅

**验证**：plan 的 allowed files 列表中不包含任何 jobs/evidence/portfolio 相关文件。✅

## Findings

### 001-未修复-低-Repository error types 未指定类名，implementation agent 需自行设计

- **位置**: S12-CTRL-01
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: plan 声称 "稳定的 not-found/conflict/optimistic-conflict 错误"，但未指定 error class 名称或继承关系。
- **反例/失败场景**: Implementation agent 可能为每个 repository 方法设计不同的 error 类型，或复用通用 `ValueError`，导致 API 边界不一致。
- **为什么有问题**: Error types 是 protocol contract 的一部分。如果 implementation agent 自行设计，可能导致不同 repository 的 error 类型不一致，或 error 消息泄漏候选值。
- **直接证据**: plan line 604-605 只说 "稳定的 not-found/conflict/optimistic-conflict 错误"。
- **影响**: Implementation agent 可能生成不一致的 error 类型，增加后续 slice 的集成成本。风险低，因为 protocol 签名本身是明确的。
- **建议改法和验证点**: Plan 可补充 error class 命名约定（例如 `IdentityNotFoundError`、`IdentityConflictError`、`OptimisticConflictError`），或明确 "error types 由 implementation agent 在 `storage/protocols.py` 中定义，必须有 stable 类名且消息不含候选值"。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 002-未修复-低-Atomic registration 的回滚语义未指定是 DB transaction 还是 application-level cleanup

- **位置**: S12-CTRL-01
- **问题类型**: 契约缺失
- **当前写法**: "atomic registration 任一后续 insert 失败必须回滚前序 public-reference insert"。
- **反例/失败场景**: "回滚" 可以是 DB transaction rollback（隐式）或 application-level delete（显式）。两者语义不同：DB rollback 更安全但可能不适用于跨 schema 操作；application delete 需要额外的 cleanup 逻辑。
- **为什么有问题**: PostgreSQL 的 transaction 已经保证原子性，但 plan 没有明确说明是依赖 DB transaction 还是额外的 application cleanup。
- **直接证据**: plan line 615-616。
- **影响**: Implementation agent 可能选择不必要的 application-level cleanup，增加复杂度。但 PostgreSQL transaction 已经保证原子性，所以实际风险很低。
- **建议改法和验证点**: Plan 可明确 "atomic registration 由单个 DB transaction 保证原子性——如果 security insert 失败，整个 transaction rollback，company insert 也不持久化"。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

无。

## Residual Risk

- S12-CTRL-01 的 "至少" 语义意味着 implementation agent 可以添加额外的 DTO 字段或 repository 方法。这是合理的扩展空间，但可能在后续 slice 中导致意外的 API 变化。风险低。
- S12-CTRL-03 的 integration test 场景是 "至少" 列表，implementation agent 可能添加更多场景。这也是合理的。

## Conclusion

**PASS**。Open H/M/L = **0/2/0**。

S12-CTRL-01..04 的核心设计（source DTO/repository protocol/transaction-local tenant/atomic registration/CAS update/service provider owner/import DAG/production dev profile/real PG16 lane/README/allowlist/future owner exclusion）均可实施且设计合理。两项 L-level finding（error class naming 和 atomic rollback 语义明确化）不构成 blocker，implementation agent 可以在 plan 接受后自行设计。Allowlist 完整，scope 精确，未扩大到 Slice 1.2 之外。允许进入 implementation。
