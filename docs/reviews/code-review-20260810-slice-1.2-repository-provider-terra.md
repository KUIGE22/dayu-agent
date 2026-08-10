# Code Review — Slice 1.2 Repository/Provider Implementation

## Scope

- Mode: current changes
- Branch: `codex/investment-platform`
- Base: `main`（`7c97c1f`）及 accepted plan `Slice 1.2 / S12-CTRL-01..08`
- Review clock: 2026-08-10 15:15:43 CST
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-terra.md`
- Included scope: 当前 Slice 1.2 的 `source.py`、repository protocol/SQL implementation、identity service、composition/startup 改动、architecture guard、unit/PG16 integration tests 与两份 README；并交叉读取 Slice 1.1 schema/migration、AGENTS.md、implementation review artifact 与当前全部未提交 diff/new files。
- Excluded scope: Slice 1.3+、live data/model/broker、既有 PG17 stack；未修改 production/tests/README/plan 或既有 review artifact。
- Parallel review coverage: 无（独立单人复核）。

## Findings

### TERRA-S12-001-未修复-高-不可达或错误角色 DSN 被默认 provider 静默准入，Host/Fins 会在数据库可用性确认前启动

- **入口/函数**: `prepare_host_runtime_dependencies(..., platform_provider=None)` → `_default_provider_or_fail()` → `_build_production_identity_provider()`。
- **文件(行号)**: `dayu/services/startup_preparation.py:208-225, 428-477`；`dayu/investment/storage/db.py:80-94`。
- **输入场景**: enabled production，四个环境变量均存在，`DAYU_PLATFORM_POSTGRES_DSN` 是不可达地址、错误角色或无权限连接串。
- **实际分支**: `_build_production_identity_provider()` 在 `create_platform_engine(dsn)` 后仅构造 session factory/repository/service；`create_platform_engine()` 只执行 `create_engine()`，其 docstring 也明确连接错误在首次使用 engine 时才出现。函数返回 provider/lifecycle，随后 `prepare_host_runtime_dependencies()` 继续执行 `build_platform_composition()`、路径/配置、`HostStore.initialize_schema()`、Fins 与 Host 构造。
- **预期行为**: S12-CTRL-06 要求 nonblank 但 malformed/**unreachable/wrong-role** DSN 在 Host/Fins 副作用前统一转换为不含 cause 的 `PlatformCompositionError`，并完成 auto-created engine 清理。
- **实际行为**: 无网络连接的最小复现以 `postgresql+psycopg://review_user:review_secret@127.0.0.1:1/review_db` 调用 builder，输出 `unreachable_dsn_admitted= _ProductionIdentityProvider`；错误会推迟到首个 repository 调用，启动已被准入。
- **直接证据**: 当前 production builder 没有 `engine.connect()`、`SELECT 1` 或角色 admission；正常的构造链在 `startup_preparation.py:208-245` 完成后才进入主 startup 路径 `435-507`。现有 PG16 test 仅覆盖 missing DSN（`test_production_provider_missing_dsn_safe_failure`），未覆盖 malformed/unreachable/wrong-role。
- **影响**: 系统可带着不可用或不具 application 权限的数据库依赖启动，违反 fail-fast 与零副作用 admission；首个业务请求才以 repository 错误失败，运维上既不稳定也不符合 secret-safe startup contract。
- **建议改法和验证点**: 在返回 auto-created provider 前，以 engine 做最小、无业务写入的连接/admission probe；捕获所有连接/认证/角色失败并 `dispose()` 后抛固定 `PlatformCompositionError`（不链原始 cause/DSN）。补充 public startup tests，证明 malformed、unreachable、wrong-role 都在 Host/Fins sentinel 为零时失败，且 dispose/atexit residue 为零。
- **修复风险（低/中/高）**: 中（必须定义最小 probe 与 role admission SQL，但不应触及业务表）。
- **严重程度（低/中/高/严重）**: 高。

### TERRA-S12-002-未修复-中-UUID 及 version 的 strict boundary 不成立：nil UUID 与 bool 版本值被接收

- **入口/函数**: `SourceDefinitionId` / `SourceSubscriptionId` 构造，projection version 校验，以及 CAS `expected_version` 校验。
- **文件(行号)**: `dayu/investment/domain/source.py:54-77, 138-157`；`dayu/investment/storage/postgres_identity.py:218-228`。
- **输入场景**: 传入 nil UUID `00000000-0000-0000-0000-000000000000`；或传入 `True` 作为 projection `version` / repository CAS `expected_version`。
- **实际分支**: `_validate_canonical_uuid()` 只验证 canonical 形态和 `str(UUID(value))`，没有 nil 拒绝；`_validate_positive_int()` 与 `_validate_positive_version()` 均用 `isinstance(value, int)`，而 Python 的 `bool` 是 `int` 子类。
- **预期行为**: S12-CTRL-05 明定 physical UUID 不接受 nil，`bool` 不得冒充 `int`；S12-CTRL-05 还要求 `expected_version` 为 positive **exact int**。
- **实际行为**: 独立复现中两个 source UUID value object 均成功接受 nil；`CompanyProjection(..., version=True)` 成功构造，`_validate_positive_version(True)` 也成功返回。
- **直接证据**: `tests/investment/test_identity_repositories.py:258-274` 甚至把 nil UUID 放入成功参数集；没有 bool-version 或 `expected_version=True` negative test。
- **影响**: 非法 sentinel ID 可进入 DTO/SQL path，且 bool 会被当作版本 1 参与 CAS，破坏 DTO 与 API 的 exact type/canonical-ID contract。
- **建议改法和验证点**: 在两处 UUID validator 显式拒绝 `UUID(value).int == 0`；在两个 version validator 使用 `type(value) is int`（或等价 exact-type 检查）。增加 direct-constructor、repository pre-SQL 与 CAS 的 nil/bool negatives。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### TERRA-S12-003-未修复-中-frozen-slots escape guard 未绑定当前 class 与直接 `__post_init__`，可由嵌套函数或跨类字段绕过

- **入口/函数**: `_collect_escape_violations_from_source()` → `_collect_allowed_object_setattr_nodes()` → `_inside_post_init_of_frozen_slots()`。
- **文件(行号)**: `tests/investment/test_architecture_boundaries.py:316-338, 396-438, 478-507`。
- **输入场景**: (1) frozen+slots dataclass 的普通 helper 内嵌套名为 `__post_init__` 的函数，再调用 `object.__setattr__(self, "value", "x")`；(2) 类 A 声明 `shared`，类 B 声明 `own`，B 的 `__post_init__` 写入 `shared`。
- **实际分支**: field collector 返回所有 frozen+slots 类字段的全局 `set[str]`；上下文判断对每个 class 使用 `ast.walk(node)` 查找任意嵌套的同名 `FunctionDef`，只比对行号与参数数量，未验证 call 的直接所属 class、方法直接成员、该方法参数名或当前 class 的字段。
- **预期行为**: S12-CTRL-08 要求 field 必须属于**当前 class**，call 必须处于该 class 的直接 `def __post_init__(self)`，仅允许精确 `object.__setattr__(self, declared_field, value)`。
- **实际行为**: 两个独立 AST 反例调用 `_collect_escape_violations_from_source()` 均返回 `[]`，即 guard 未报告 `object`。
- **直接证据**: `field_arg.value not in frozen_slots_fields`（line 428）针对全局集合；`ast.walk(node)`（line 500）会进入嵌套 function/class，line 503 未检查参数名；现有 negative matrix 未覆盖 nested direct-method context 或 other-class declared field。
- **影响**: 该 guard 不再只豁免计划允许的 frozen DTO defensive copy；新增 production code 可用被误放行的 `object.__setattr__` 绕开统一 strict-type/immutability discipline。
- **建议改法和验证点**: 建立 AST parent/owner 栈，逐个 frozen+slots class 的直接 body 查找唯一直接 `__post_init__(self)`，只从其直接 subtree 接受 call，并用该 class 的 `AnnAssign` 字段集合验证。增加 nested function、nested class、other-class field、非 `self` 参数名等 negatives。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### TERRA-S12-004-未修复-中-公开 `close()` 无法取消对应 atexit 注册，违反 manual-close 后 callback exact no-op

- **入口/函数**: `prepare_host_runtime_dependencies()` 成功路径与 `PreparedHostRuntimeDependencies.close()`。
- **文件(行号)**: `dayu/services/startup_preparation.py:137-153, 281-358, 508-518`。
- **输入场景**: production default provider 成功启动后，调用方执行 `prepared.close()`，随后进程退出触发已注册 callback。
- **实际分支**: success path 创建 `_OwnedLifecycleRegistration(owned_lifecycle)`，但仅保存在局部变量 `lifecycle_registration`；返回的 `PreparedHostRuntimeDependencies` 只保存 lifecycle，不保存 registration。其 `close()` 直接调用 lifecycle 的 `close()`，无法执行 `registration.mark_manually_closed()`/`registration.close()`。
- **预期行为**: S12-CTRL-07 明定 `PreparedHostRuntimeDependencies` 是唯一 public lifecycle owner，显式 `close()` 后 atexit callback 必须 no-op；测试还必须证明 manual-close 后 callback no-op。
- **实际行为**: 独立计数 lifecycle 复现：模拟 public object 的 `close()` 后调用 registration callback，得到 `close_count_after_manual_then_atexit= 2`。目前真实 `InvestmentIdentityService.close()` 内部幂等会掩盖 engine 二次 dispose，但 callback 仍非 no-op，换成任何严格 lifecycle implementation 即违反协议。
- **直接证据**: `PreparedHostRuntimeDependencies.close()` 只在 line 152-153 调 lifecycle；registration 在 line 509 创建却未传入 return object。现有 unit test 只直接测试 `_OwnedLifecycleRegistration.close()`，没有测试 public `prepared.close()` 与其 callback 的联动。
- **影响**: public owner 与 atexit coordinator 形成两个未协调的关闭入口，exact-once contract 仅因当前 concrete service 的额外幂等性被偶然掩盖；后续 lifecycle 实现或计量/释放动作可重复执行。
- **建议改法和验证点**: 将注册协调器以私有 typed field 交给 `PreparedHostRuntimeDependencies`，其 `close()` 委托协调器（无自持资源仍 no-op）；只在完整对象已构造成功后注册。补 public-object manual-close→callback count=1、startup failure callback residue=0、explicit provider count=0 tests。
- **修复风险（低/中/高）**: 中（需保持 frozen dataclass/public API 和 failure cleanup 顺序）。
- **严重程度（低/中/高/严重）**: 中。

### TERRA-S12-005-未修复-低-新增 unit test 自身使用 `hasattr`，且未被该 guard 覆盖

- **入口/函数**: protocol method presence assertions。
- **文件(行号)**: `tests/investment/test_identity_repositories.py:666, 690`。
- **输入场景**: 执行 protocol shape unit tests。
- **实际分支**: 测试直接调用 `hasattr(IdentityRepositoryProtocol, method_name)` 与 `hasattr(SourceRepositoryProtocol, method_name)`；architecture guard 仅扫描 `dayu.investment` production 和 integration test directory，不扫描此 unit 文件。
- **预期行为**: AGENTS.md 禁止把 `hasattr` 当作类型/边界逃逸；此次审查范围也明确要求不得引入 `hasattr`。
- **实际行为**: 新增文件含该调用，且当前自身的 guard 不会失败。
- **直接证据**: 上述两行与 `_iter_integration_test_files()` 的扫描范围（`test_architecture_boundaries.py:131-146, 759-763`）。
- **影响**: 违反项目严格检查约束，并给后续 unit test 宽松反射用法留下未守护入口；不影响当前 repository 功能。
- **建议改法和验证点**: 以对协议属性的显式引用或严格 AST/签名断言替代，并把受约束的新增 unit 文件纳入一致 guard（若项目确定该约束适用于 tests）。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。上述五项均可由当前代码路径与本地最小复现确认。

## Residual Risk

- SQL 映射、public/private table 边界、`set_config(..., true)`、subscription 的显式 tenant predicate、单事务 rollback、CAS 和递归 JSONB codec 已走读；其真实 PostgreSQL 16 行为未能在本机重新证明：fixture 在创建任何容器前因缺少指定 pinned `postgres:16.14` digest 终止，13 个 integration cases 均为 setup error，未触碰 PG17。
- 聚焦 unit：`tests/investment/test_identity_repositories.py`、`tests/investment/test_architecture_boundaries.py`、`tests/application/test_service_startup_preparation.py` 为 **172 passed**。Pyright 为 **0 errors**，Ruff 通过，`git diff --check` 通过。
- 覆盖率命令在收集期被本地 pandas/numpy 导入错误（`numpy: cannot load module more than once per process`）阻断，故本次无法独立确认每个修改生产文件的 >=80% 覆盖率；不得把此前 artifact 的数字当作本次验证结果。
- 未发现新增 future owner（jobs/evidence/portfolio）import、raw DSN 日志输出、SQL `create_all`、或对既有 PG17 的操作路径；但 TERRA-S12-001 仍使 unreachable/wrong-role DSN 的 startup admission 未闭合。

## Conclusion

**FAIL**

Open H/M/L = **1 / 3 / 1**。
