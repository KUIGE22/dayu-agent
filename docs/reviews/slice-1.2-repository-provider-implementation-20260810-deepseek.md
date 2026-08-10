# Slice 1.2 repository/provider implementation artifact

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：implementation
- **Approved plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`
  （Slice 1.2，S12-CTRL-01..08，行 611-808）
- **Predecessor accepted commits**：`acd64d8`（contract）、`bf6761b`（provider）、
  `1968b13`（frozen slots guard）
- **Branch**：`codex/investment-platform`
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- **Open H/M/L**：`0/0/0`

## Scope / Non-goals

只实现 accepted plan 的 Slice 1.2 allowlist；不启动 review/commit/push/PR，
不进入 Slice 1.3/live/model/broker。

- **Allowed files 实际改动**：
  - `dayu/investment/domain/source.py`（新，frozen DTO/closed enum/canonical UUID/递归深冻结 JSON）
  - `dayu/investment/storage/protocols.py`（新，两协议 + 五类稳定错误）
  - `dayu/investment/storage/postgres_identity.py`（新，transaction-scoped repository）
  - `dayu/investment/composition.py`（窄 `PlatformIdentityServiceProtocol` + `PlatformOwnedLifecycleProtocol`）
  - `dayu/services/protocols.py`（re-export 两协议）
  - `dayu/services/investment_identity.py`（新，`InvestmentIdentityService`）
  - `dayu/services/startup_preparation.py`（production provider + close/atexit/exact-once lifecycle）
  - `tests/investment/test_identity_repositories.py`（新，unit）
  - `tests/investment/test_architecture_boundaries.py`（frozen+slots `object.__setattr__` 豁免 + 正/负例）
  - `tests/application/test_service_startup_preparation.py`（新契约：production DSN 缺失/development fail-fast）
  - `tests/integration/investment/test_identity_repositories_postgres.py`（新，真实 PG16）
  - `dayu/investment/README.md`、`tests/README.md`（模块 owner 与 lane 登记）
  - 本文档

## Implemented plan items

### S12-CTRL-01/05 — Domain DTO 与 repository 契约

- `domain/source.py`：`SecurityType`/`SourceKind`/`SubscriptionStatus` closed
  enums；`SourceDefinitionId`/`SourceSubscriptionId` canonical UUID 强标识
  （`str(UUID(value))==value` 双重校验）；全部 create/update request 与 read
  projection frozen slots DTO；`JsonValue` 递归类型允许 tuple/Mapping，构造期
  `_deep_freeze` 递归冻结为嵌套 `MappingProxyType`，拒绝 NaN/Infinity/cycle/
  list/非字符串 key；文本字段复用 Slice 1.1 check 语义。
- `storage/protocols.py`：`IdentityRepositoryProtocol`（4 方法）与
  `SourceRepositoryProtocol`（6 方法），每方法首参 `TenantScope`；五类稳定错误
  `RepositoryError` 层级。

### S12-CTRL-01 — postgres_identity repository

- `PostgresIdentityRepository` 同时实现两协议；每方法自持 `Session.begin()`
  事务，首条语句 `set_config('app.tenant_id', :tenant_id, true)`（SET LOCAL
  等价）并读回确认；私有 query 显式 tenant predicate（RLS 第二道）；
  atomic company+security 单事务（第二 insert 冲突回滚前序）；CAS update 用
  `tenant_id+id+version` + `RETURNING` 区分 not-found/optimistic-conflict。
- 修复三处实施中发现的问题：psycopg3 `:x::jsonb` 需 `CAST(:x AS jsonb)`；
  UUID 列返回对象需 `_row_text` 转 str；`_SUBSCRIPTION_COLS` 列序在
  `_row_subscription_full` 错位（company=3/security=4/status=5）——已修复并加
  company-target/security-target projection 测试证明不串位。

### S12-CTRL-02/07 — 窄 Service 与 lifecycle

- `composition.py`：`PlatformIdentityServiceProtocol`（注册名精确
  `investment_identity`，只暴露 DTO 操作）+ `PlatformOwnedLifecycleProtocol`
  （`close()`）；`services/protocols.py` 稳定 re-export。
- `services/investment_identity.py`：`InvestmentIdentityService` 只编排两
  repository、原样要求 `TenantScope`、不 import ORM/engine；`close()` 线程安全
  幂等，只释放 owned engine。

### S12-CTRL-06 — production startup/provider

- `startup_preparation.py`：`_default_provider_or_fail`——显式 provider 优先；
  production 缺 provider 时读 `postgres_dsn_env` 构造默认 provider
  （engine/session factory/`PostgresIdentityRepository`/`InvestmentIdentityService`）；
  development 缺 provider fail-fast（禁 PG 冒充 in-memory）；missing/blank DSN
  由 `PlatformSettingsError` 拒绝，malformed/unreachable 统一转
  `PlatformCompositionError`（不回显 DSN）。
- `_probe_production_engine`（TERRA-S12-001 fix）：默认 provider 返回前执行
  无业务写入 admission probe——`engine.connect()` + `SELECT 1` 验证可达，
  `pg_has_role(current_user, app_role, 'MEMBER')` 校验 application role
  membership（接受临时 `LOGIN IN ROLE dayu_platform_app`），同时拒绝
  superuser 与 `BYPASSRLS`；engine 创建纳入 try，任何失败统一
  `dispose()` + safe `PlatformCompositionError`，Host/Fins 副作用零、无
  atexit residue。
- `PreparedHostRuntimeDependencies` 唯一私有 `_owned_platform_lifecycle`
  （`_OwnedLifecycleRegistration` wrapper）+ 公开幂等 `close()`；
  `_OwnedLifecycleRegistration` 延迟注册：初始化仅持有底层，完整构造
  Prepared 后显式 `register()`（exact-once），manual `close()` 后
  callback 真正 no-op（TERRA-S12-004 fix）；启动任一点失败同步 dispose 且
  不留 callback。

### S12-CTRL-08 — guard 豁免

- `test_architecture_boundaries.py`：对 frozen=True+slots=True dataclass
  `__post_init__(self)` 内精确 `object.__setattr__(self, declared_field, value)`
  （三位置参数零 keyword、字段为声明名字面量）豁免 `object` Name；12+4 负例
  （裸 object/注解/`__new__`/other receiver/未知字段/方法外/非 dataclass/
  non-frozen/存储引用/keyword-extra/参数个数/字段非字面量/嵌套函数/嵌套类/
  跨类字段/多参数 `__post_init__`）+ 1 正例，全部 fail-closed 验证。
- TERRA-S12-003 fix：豁免判定沿 AST 真实父链绑定——调用必须直接位于当前
  frozen+slots class 的 `__post_init__(self)` 方法体内（不经任何嵌套函数/
  嵌套类），字段必须为该类本体的 AnnAssign 字段（`_collect_frozen_slots_fields_by_class`
  按类 id 隔离），删除行号定位逻辑。

### Storage JSONB codec（pre-review correction）

- `domain/source.py` 的 `JsonValue` 允许嵌套 Mapping/tuple 且 DTO deep-freeze
  为 `MappingProxyType`/tuple；`postgres_identity.py` 新增唯一递归 storage
  codec：
  - `_json_outbound`：Mapping -> plain dict、tuple -> list、标量不变，
    拒非字符串 key/非法值 -> `RepositoryInputError`；
  - `_json_inbound`：dict -> dict（递归）、list -> tuple（递归）、标量不变，
    拒非字符串 key/非法值 -> `RepositoryError`；
  - 使用 JSONB wire 递归别名 `WireJsonValue`（plain list/dict/scalar），
    无 `object`/`Any`/`cast`/`ignore`；float 有限性由 DTO 构造与 DB
    ingress 双向 fail-closed。
- 修复 `_row_subscription_full` 列序错位（company=3/security=4/status=5）与
  config 经 `_json_inbound` 收窄。

### Lifecycle exact-once（pre-review correction + TERRA-S12-004）

- `_OwnedLifecycleRegistration` 延迟注册协调器（TERRA-S12-004 重构）：
  `__init__` 仅持有底层 lifecycle；显式 `register()` exact-once（已注册或
  已 close 后拒绝再注册）；`close()`（manual）无条件幂等释放并解除注册
  意图；`_close_at_exit()`（callback）仅当已注册且未被手动 close 时执行
  一次——先到者赢得 close 权，底层 `close()` 恰好一次。`PreparedHostRuntimeDependencies.close()`
  委托 wrapper.close()。测试：manual close 后 callback no-op、callback 两次
  只 close 一次、register 前 callback 无动作、register exact-once、close 后
  register no-op。

## Validation

```bash
pytest tests/investment tests/application/test_service_startup_preparation.py \
  tests/integration/investment -q                     # 1744 passed
pyright dayu/investment dayu/services/investment_identity.py \
  dayu/services/startup_preparation.py tests/investment \
  tests/application/test_service_startup_preparation.py tests/integration/investment
#   0 errors
ruff check dayu/investment dayu/services/investment_identity.py \
  dayu/services/startup_preparation.py tests/investment tests/integration/investment
#   All checks passed
git diff --check                                       # clean
```

真实 PG16 integration lane（42 tests 含迁移 + identity + startup black-box）：
unique/CAS/atomic rollback、cross-tenant、tenant setting 不泄漏、
company/security-target projection 不串位、nested Mapping/tuple-of-mapping
create/get/CAS round-trip（canonical 深冻结等价、输入修改不影响、更新后读回
一致）、read-path schema fault（RENAME）稳定 `RepositoryError` 且无
DSN/SQL/候选泄漏并恢复、production startup auto-provider 装配一个
`investment_identity`、DSN 缺失安全失败、wrong-role 连接被 probe 拒绝、
`close()` dispose 恰一次。测试后 Slice-owned container/network 为零，既有
PG17 stack 未触碰。

## Coverage note

每生产模块达到 §9 hard gate >=80%（本 fix 轮以 `COVERAGE_CORE=pytrace` +
独立 `COVERAGE_FILE`、真实 caller corpus 复证）：

| 文件 | corpus | coverage |
| --- | --- | --- |
| `dayu/services/startup_preparation.py` | application lane | 81% |
| `dayu/investment/domain/source.py` | investment + integration | 85% |
| `dayu/investment/storage/postgres_identity.py` | investment + integration | 81% |
| `dayu/investment/composition.py` | investment + integration | 100% |
| `dayu/services/investment_identity.py` | investment + integration | 83% |
| `dayu/services/protocols.py` | investment + integration | 100% |
| `dayu/investment/storage/protocols.py` | investment + integration | 100% |

剩余未覆盖均为类型系统/domain 校验保证不可达的防御分支：`_canonical_uuid`
非 str/UUID 解析错、`_row_*` 字段类型错、config 非 dict、`_json_dumps`
失败、注册后 row None、以及 `except RepositoryError: rollback; raise`（需
repository 内部抛 `RepositoryError`——仅 `_set_tenant_local` 确认失败可达，
而 scope 校验已拦）。这些分支是必要的安全网，真实 caller 无法触发，未用
ignore/pragma/private seam 绕过。

## Residual risks / owners

| 风险 | 分类 |
| --- | --- |
| `_downgrade_admission` RuntimeError 类型不统一 | deferred-with-owner（Slice 1.2 后续/2.1） |
| FK 名 63 字符上限 | deferred-with-owner（Slice 1.2 后续） |
| 输入校验分支类型系统不可达 | 合理防御（已在 artifact 说明） |

## Completion / stop status

- **Completed**：DTO/repository/service/provider/lifecycle/guard/codec 全部
  实现，TERRA-S12-001..005 + Round 2 RR-001/002 修复（MiM 001/002、
  RR-003 REJECT），322 tests 全绿，每生产文件 >=80%，pyright/Ruff/diff
  通过，README 同步，零容器残留、PG17 未动。
- **Not run**：无 live/model/broker；未 commit/push/PR。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Round 3（final re-review fix，TERRA-S12-FRR-001）

- **Final re-review 输入**：
  - Terra final re-review（
    `code-review-20260810-slice-1.2-repository-provider-final-rereview-terra.md`）
    **FAIL**，open H/M/L = **0/1/0**，TERRA-S12-FRR-001；
  - MiM final re-review（
    `code-review-20260810-slice-1.2-repository-provider-final-rereview-mimo-native.md`）
    **PASS**（RR-001/002 闭合、lifecycle/startup/RLS/codec 全部通过）。
- **Controller 裁决**：TERRA-S12-FRR-001 **ACCEPTED / Medium / FIX
  REQUIRED**；MiM PASS 保留，但当前树需再双审。
- **Round 3 fix**（仅
  `tests/investment/test_architecture_boundaries.py`，production 零改动）：
  - dataclass 识别收紧为模块级 `from dataclasses import dataclass`
    解析得到的、未被模块级重绑定的**直接** `ast.Name` decorator；
  - `frozen`/`slots` 必须出现在**同一个** decorator call 且值均为
    `ast.Constant(True)`，不得跨 decorator 聚合；重复关键字/模糊绑定
    fail closed；
  - attribute callee（`fake.dataclass`）、本地/模块同名伪 decorator、
    无标准导入一律拒绝；合法 direct standard decorator positive 保留；
  - Controller hardening：`import fake as dataclass` /
    `from fake import dataclass` 绑定计入模块重绑定；豁免仅限直接
    module-level ClassDef（nested class 由局部同名伪 decorator 遮蔽
    不再可能）。
- **Tests**：负例矩阵 +8（同名伪 decorator、attribute
  `fake.dataclass`、两个标准 dataclass call 分散 frozen/slots、标准
  import 后模块级重绑定、重复 frozen 关键字、import-as/from-import
  重绑定、nested-local-fake decorator），guard 文件 140→148 passed；
  Terra 复现场景从 `guard-violations []` 变为拒绝。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**（MiM
  prior PASS 保留、Terra prior FAIL 已按裁决修复，待双审）。

## Round 4（final closure fix，TERRA-S12-FC-001）

- **Final closure 输入**：
  - Terra final closure（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-terra.md`）
    **FAIL**，open H/M/L = **0/1/0**，TERRA-S12-FC-001；
  - MiM final closure（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-mimo-native.md`）
    **PASS**（保留）。
- **Controller 裁决**：TERRA-S12-FC-001 **ACCEPTED / Medium / FIX**；
  MiM PASS 保留，当前树需再双审。
- **Round 4 fix**（仅
  `tests/investment/test_architecture_boundaries.py`，production 零改动）：
  - 停止手工枚举 pattern AST，改用 **symtable** 作为模块绑定真源：
    `_collect_escape_violations_from_source(source)` 将 source 传给
    trust collector；`_collect_allowed_object_setattr_nodes(tree,
    source)` 单次 parse（tree 保证 node id 一致，symtable 仅用
    source），修复同 source 双 parse 导致的 11 个合法 `object` 误报；
  - `_collect_standard_dataclass_names(source)`：候选仍须是唯一模块级
    `from dataclasses import dataclass [as alias]` 且 AST 无其它同名
    import 模糊绑定，同时 `symtable.lookup(alias)` 必须 `is_imported`
    True 且 `is_assigned` False——assignment/for/with/except/walrus/
    match capture/del/function/class 统一 fail closed；
  - 删除手工枚举 helper `_module_scope_bound_names` /
    `_iter_assigned_names`；保留 top-level class / direct Name /
    unique same-call frozen=True slots=True 限制。
- **Tests**：负例矩阵 +2（Terra 精确 match/case capture runtime-shape、
  del binding 符号表边界），guard 文件 148→150 passed；match/case 与
  del 场景均从放行变为拒绝。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**（MiM
  prior PASS 保留、Terra prior FAIL 已按裁决修复，待双审）。

## Final closure（round4 dual re-review PASS）

- **Round 4 dual re-review**：
  - Terra final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`）
    **PASS**，open H/M/L = **0/0/0**；
  - MiM final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`）
    **PASS**，open H/M/L = **0/0/0**。
- **Findings closure**：TERRA-S12-FC-001、TERRA-S12-FRR-001、
  TERRA-S12-RR-001/002 与初审 findings（TERRA-S12-001..005）全部
  **CLOSED**；MiM 001/002（stale-source）与 RR-003
  （reviewer-environment / non-defect）的 REJECT 保持事实记录。
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。
  仅 Controller 可创建 accepted commit；本 worker 未 commit/push/PR，
  未进入 Slice 1.3；production/tests/README/plan/review source 冻结。
