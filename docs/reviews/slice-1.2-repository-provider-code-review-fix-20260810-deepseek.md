# Slice 1.2 code review fix artifact（TERRA-S12-001..005）

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：code review fix
- **Adjudication**：`docs/reviews/code-review-adjudication-20260810-slice-1.2-repository-provider-codex.md`
- **Branch**：`codex/investment-platform`
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**
- **Date**：2026-08-10

## TERRA-S12-001（高）— production provider 返回前 admission probe

**Finding**：`_build_production_identity_provider` 只 `create_engine` 不
连接/校验角色，unreachable/wrong-role DSN 被静默准入，Host/Fins 会在
数据库可用性确认前启动。

**Fix**（`dayu/services/startup_preparation.py`）：

- 新增 `_probe_production_engine(engine)`：`engine.connect()` +
  `SELECT 1` 验证可达；`pg_has_role(current_user, app_role, 'MEMBER')`
  校验 application role membership（接受 plan 的临时
  `LOGIN IN ROLE dayu_platform_app`，而非按用户名等于 group role）；
  同时拒绝 superuser（`rolsuper`）与 `BYPASSRLS`（`rolbypassrls`）。
- `_build_production_identity_provider` 将 engine 创建移入 try：任何
  连接/认证/角色失败统一 `engine.dispose()` + safe
  `PlatformCompositionError`（`from None`，不回显 DSN/候选值）。
- probe 在 session_factory 构造前执行，Host/Fins 副作用零；
  startup 失败路径不创建 atexit 注册（residue 零）。

**Tests**：

- `tests/application/test_service_startup_preparation.py`
  `TestProductionProviderAdmissionProbe`：
  - `test_unreachable_dsn_fails_safely`——不可达端口 DSN →
    `PlatformCompositionError`，Host/Fins 副作用零、`Engine.dispose`
    恰一次、atexit 注册零；
  - `test_malformed_dsn_fails_safely`——畸形 DSN →
    `PlatformCompositionError`，副作用零。
- `tests/integration/investment/test_identity_repositories_postgres.py`
  `TestProductionStartupBlackBox::test_production_provider_wrong_role_rejected`
  ——真实 PG16 上非 `dayu_platform_app` member 登录 →
  `PlatformCompositionError`，错误不回显 role/端口。

## TERRA-S12-002（中）— nil UUID / bool version strict boundary

**Finding**：nil UUID 与 bool 版本值被 `_validate_canonical_uuid` /
`_validate_positive_int` 接收（`isinstance(True, int)` 为 True）。

**Fix**：

- `dayu/investment/domain/source.py` `_validate_canonical_uuid`：
  `parsed.int == 0` 拒绝 nil UUID（复用现有消息）；
- `_validate_positive_int`：`type(value) is not int` 拒绝 bool 冒充
  （`True`/`False`），`TypeError` 消息明确“禁止 bool 冒充”；
- `dayu/investment/storage/postgres_identity.py`
  `_validate_positive_version`：`type(expected_version) is not int`
  拒绝 bool。

**Tests**（`tests/investment/test_identity_repositories.py`）：

- nil UUID 从 accept 参数集移入 reject；
- `test_company_projection_rejects_bool_version`（`version=True` →
  `TypeError`）；
- `test_subscription_id_rejects_nil_uuid`（nil UUID →
  `ValueError`）。

## TERRA-S12-003（中）— guard 绑定当前 class 直接 `__post_init__`

**Finding**：guard 用 `ast.walk` + 全局字段集，嵌套函数/嵌套类内调用
与跨类字段名可绕过。

**Fix**（`tests/investment/test_architecture_boundaries.py`）：

- `_collect_allowed_object_setattr_nodes` 改为沿 AST 真实父链判定：
  - `_build_parent_map` 构建节点 id -> 父节点映射；
  - `_direct_post_init_owner`：调用直接位于某 frozen+slots
    dataclass 的 `__post_init__(self)` 方法体内（方法定义直接挂在该
    class body、不经过任何嵌套函数/嵌套类）才返回该类；
  - `_collect_frozen_slots_fields_by_class`：字段集按 class id 隔离，
    只接受**本类** AnnAssign 字段名。
- 删除行号定位的 `_inside_post_init_of_frozen_slots`。

**Tests**（负例矩阵新增 4 项，全部 fail-closed）：

- nested function 内 `object.__setattr__`；
- nested class 方法内调用；
- 跨类字段名（字段声明在另一 frozen+slots class）；
- `__post_init__(self, other)` 多参数签名。

## TERRA-S12-004（中）— `PreparedHostRuntimeDependencies.close()` 与 registration 协调

**Finding**：registration 未交给 return object，manual `close()` 后
atexit callback 仍会调用 lifecycle。

**Fix**（`dayu/services/startup_preparation.py`）：

- `_OwnedLifecycleRegistration` 重构为延迟注册协调器：
  - `__init__` 仅持有底层 lifecycle（`_registered=False`、
    `_closed=False`），不注册 atexit；
  - 显式 `register()`：exact-once，已注册或已 close 后拒绝再注册；
  - `_close_at_exit()`（callback）：仅当已注册且未被手动 close 时
    执行一次；
  - `close()`（manual）：无条件幂等释放底层并解除注册意图。
- `PreparedHostRuntimeDependencies` 移除第二 field，唯一
  `_owned_platform_lifecycle` 直接持有 wrapper；`close()` 委托
  `wrapper.close()`。
- 装配流：先建 wrapper -> 作为唯一 field 构造 Prepared -> 完整构造
  成功后 `register()` -> return；失败路径 `wrapper.close()` /
  `owned_lifecycle.close()` 兜底。

**Tests**（`tests/application/test_service_startup_preparation.py`）：

- `test_prepared_close_then_callback_is_noop`（Prepared 构造后显式
  `register()` 挂载回调，public close 后已注册 callback 不再 close）；
- `test_register_before_callback_is_noop`（register 前 callback 无动作）；
- `test_register_is_exact_once`（重复 register 只挂一次）；
- `test_register_after_close_is_noop`（close 后 register 不挂回调）；
- `test_unreachable_dsn_fails_safely` 补 atexit 注册零断言。

## TERRA-S12-005（低）— unit test 移除 `hasattr`

**Finding**：`test_identity_repositories.py` 用
`hasattr(Protocol, method_name)` 做协议面验证，自身违反 guard。

**Fix**（`tests/investment/test_identity_repositories.py`）：改为显式
protocol 属性引用（`_ = (IdentityRepositoryProtocol.register_company_security, ...)`
元组赋值），移除全部 `hasattr`。

## MiM 001/002 — REJECT（stale-source，无改动）

详见 adjudication：source.py 705/738/794 已 `_deep_freeze`、guard
396+ 已实现豁免，MiM 自身 Verified 段落确认 codec/guard/lifecycle
通过，不按旧片段修复。

## Validation（本 fix 轮重跑）

```bash
pytest tests/investment tests/application/test_service_startup_preparation.py \
  tests/integration/investment -q        # 1744 passed（unit 266 + integration 全部）
pyright <slice 全部 11 文件>               # 0 errors
ruff check <slice 全部文件>                # All checks passed
git diff --check                          # clean
```

Coverage（每 modified production 文件 >=80%，`COVERAGE_CORE=pytrace` +
独立 `COVERAGE_FILE`，真实 caller corpus）：

| 文件 | corpus | coverage |
| --- | --- | --- |
| `dayu/services/startup_preparation.py` | application lane (22) | 81% |
| `dayu/investment/domain/source.py` | investment + integration (258) | 85% |
| `dayu/investment/storage/postgres_identity.py` | investment + integration (258) | 81% |
| `dayu/investment/composition.py` | investment + integration | 100% |
| `dayu/services/investment_identity.py` | investment + integration | 83% |
| `dayu/services/protocols.py` | investment + integration | 100% |
| `dayu/investment/storage/protocols.py` | investment + integration | 100% |

integration lane 真实 PG16：14 passed（identity repository 全链 +
startup black-box：wires/wrong-role/missing-DSN/close-dispose-once）。
测试后 Slice-owned container/network 为零，既有 PG17 stack 未触碰。

## Residual risks

| 风险 | 分类 |
| --- | --- |
| probe 连接等待依赖 DB 网络往返（本地 PG16 实测 <1s） | 可接受 |
| `pg_has_role` 查询需 `pg_roles` 可读（application role 已 GRANT） | 已由真实 PG16 wrong-role/正常路径证明 |
| 输入校验分支类型系统不可达（原有防御分支） | 合理防御（见 implementation artifact） |

## Completion / stop status

- **Completed**：TERRA-S12-001..005 全部修复并验证；MiM 001/002
  REJECT；1744 tests 全绿、pyright 0、ruff clean、每生产文件
  >=80%、diff clean、零容器残留、PG17 未动。
- **Not run**：未启动 review/commit/push/PR/live/Slice 1.3。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Artifact-only closure（round4 dual re-review PASS）

- **Round 4 dual re-review**：
  - Terra final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`）
    **PASS**，open H/M/L = **0/0/0**；
  - MiM final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`）
    **PASS**，open H/M/L = **0/0/0**。
- **Findings closure**：TERRA-S12-001..005、TERRA-S12-RR-001/002、
  TERRA-S12-FRR-001、TERRA-S12-FC-001 全部 **CLOSED**；MiM 001/002
  （stale-source）与 RR-003（reviewer-environment / non-defect）的
  REJECT 保持事实记录。
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**（历史 FAIL/PASS 与各轮
  裁决保持事实记录）。
