# Code Re-Review — Slice 0.2 Platform Settings / Composition

## Scope

- Mode: current changes（corrective re-review，限定为 Slice 0.2 fix 后状态）
- Branch: `codex/investment-platform`（uncommitted workspace changes）
- Base: `d5f024d`（Slice 0.1 predecessor accepted commit）
- Output file: `docs/reviews/code-rereview-20260810-101856-slice-0.2-mimo-native.md`
- Included scope:
  - `dayu/investment/config.py`（改）
  - `dayu/investment/composition.py`（改）
  - `dayu/startup/platform.py`（改）
  - `dayu/services/protocols.py`（改）
  - `dayu/services/startup_preparation.py`（改）
  - `tests/investment/test_platform_config.py`（改）
  - `tests/application/test_service_startup_preparation.py`（改）
  - `dayu/investment/README.md`（改）
  - `dayu/README.md`（改：§3.9）
- Excluded scope: `dayu/investment/domain/*`（Slice 0.1，非本 slice 变更）
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量走读与逐项验证

## Accepted Findings Verification

逐项验证 adjudication（`slice-0.2-code-review-adjudication-20260810-094100-codex.md`）中全部 accepted findings：

### Terra 001 冷启动循环导入（高）— FIXED ✓

- **验证**: `python -c 'import dayu.startup.platform'` 在 fresh interpreter 成功。
- **代码证据**: `dayu/startup/platform.py:26-32` 只导入 `dayu.investment.composition` 和 `dayu.investment.config`，不导入 `dayu.services`；`dayu/services/protocols.py:18-21` 改为纯层契约 re-export。
- **回归测试**: `tests/application/test_service_startup_preparation.py` 中 cold-import regression test 覆盖 `dayu.startup.platform`、`dayu.investment.composition`、`dayu.investment.config`、`dayu.services.protocols`、`dayu.services.startup_preparation`、`dayu.services`、`dayu.web.streamlit_app` 七条导入路径。
- **结论**: 无 cycle，稳定 owner 不依赖 import order。

### Terra 002 非法 env-name 回显 secret（中）— FIXED ✓

- **验证**: `PlatformSettings(enabled=False, profile=PlatformDeploymentProfile.DEVELOPMENT, postgres_dsn_env="postgres://user:pass@host/db")` 抛出 `PlatformSettingsError`，错误消息为 `postgres_dsn_env 必须是合法环境变量名称（仅允许大写字母、数字与下划线，且以字母开头）`，不包含候选值。
- **代码证据**: `config.py:112-114` 异常消息只报告字段名与固定规则，不再格式化 `env_name!r`。
- **测试覆盖**: `test_platform_config.py:895-982` `TestPlatformSettingsRedaction` 包含 `test_invalid_env_name_error_does_not_echo_candidate` 与 `test_secret_shaped_env_name_error_is_redacted`（DSN/object storage/Redis/auth key 四类 secret-shape 输入）。
- **结论**: 所有非法 env-name 异常只报告字段与固定规则，不回显候选值。

### Terra 003 启动 admission 迟到（中）— FIXED ✓

- **验证**: `startup_preparation.py` 源码走读：`load_platform_settings(os.environ)` 在第 167 行，`build_platform_composition(...)` 在第 168-171 行；`HostStore.initialize_schema()` 在第 210 行，`Host(...)` 在第 220 行，`recover_host_startup_state(...)` 在第 236 行。平台 admission（lines 167-171）严格先于所有 Host/Fins 副作用（lines 210-236）。
- **测试覆盖**: `test_service_startup_preparation.py:713-808` `TestPlatformAdmissionBeforeHostSideEffects` 包含三个测试：`test_missing_production_config_fails_before_host_side_effects`（缺四配置）、`test_missing_provider_fails_before_host_side_effects`（缺 provider）、`test_provider_error_fails_before_host_side_effects`（provider 抛错），均断言 `sentinels.all_empty()` 为 True。
- **结论**: 三类失败场景均在任何 Host/Fins 副作用之前 fail-fast，副作用计数为零。

### Terra 004 + MiM 1/3 任意对象注入（高）— FIXED ✓

- **验证**:
  - `composition.py:30-43` 定义非空 `@runtime_checkable PlatformServiceProtocol`（只读 `platform_service_name` property）。
  - `composition.py:46-69` 定义 `@runtime_checkable PlatformCompositionProviderProtocol`。
  - `composition.py:93-121` `__post_init__` 校验 enabled 类型、services Mapping 类型、注册键/名称/值并做 `MappingProxyType(dict(...))` 防御性快照。
  - `composition.py:156-200` `_validate_registry_entry` 对每个条目执行 `isinstance(value, PlatformServiceProtocol)` 运行时检查；str/dict/int/None 一律 `PlatformCompositionContractError`。
  - `platform.py:63-66` `build_platform_composition` 对 provider 做非空运行时协议检查；`platform.py:70-73` 组合契约异常转稳定 `PlatformCompositionError` 且不泄密。
- **运行时验证**: `PlatformComposition(enabled=True, services={"svc": "not-a-service"})` 抛出 `PlatformCompositionContractError`；`isinstance("not-a-service", PlatformServiceProtocol)` 为 False。
- **测试覆盖**: `test_platform_config.py:586-617` `test_composition_rejects_non_protocol_values` 覆盖 str/dict/int/None；`test_composition_rejects_invalid_registry_keys` 覆盖空/仅空白/首尾空白键；`test_composition_rejects_invalid_service_names` 覆盖空/仅空白/首尾空白名称；`test_composition_rejects_mismatched_registry_name` 覆盖键名不一致；`test_composition_contract_error_does_not_echo_candidate_value` 覆盖异常不回显候选值；`test_composition_snapshot_isolates_external_mutation` + `test_composition_services_mapping_is_read_only` 覆盖防御性快照。
- **结论**: 非空 runtime-checkable 契约 + 构造期校验 + MappingProxyType 快照 + 运行时 isinstance 检查四层防线闭合。

### Terra 005 测试 object/cast 逃逸（低）— FIXED ✓

- **验证**: AST 扫描 `tests/investment/test_platform_config.py` 和 `tests/application/test_service_startup_preparation.py`，无 `object`/`cast`/`getattr`/`hasattr`/`Any` 使用。
- **代码证据**: `test_service_startup_preparation.py:57-76` 使用 `_bare(cls)` helper（`cls.__new__(cls)`）替代 `cast(..., object())`；`test_service_startup_preparation.py:912-942` `test_startup_preparation_test_avoids_escape_patterns` 执行文件内 AST escape guard 自扫描。
- **结论**: 全部逃逸已移除，AST guard 守护新增路径。

### Terra 006 + MiM 4 包 README 漂移（低 / PLAN GAP）— FIXED ✓

- **验证**: `dayu/investment/README.md` 模块 owner 表（lines 38-45）包含 `config.py` 和 `composition.py` 及其职责描述；§2.4 平台严格设置和 §2.5 平台组合契约完整描述当前实现。`dayu/README.md` §3.9（lines 374-402）同步协议契约真源（纯层定义 + re-export）与冷启动导入能力。
- **结论**: 包级文档与代码一致，不再声称仅有 Slice 0.1 domain 骨架。

### MiM 2 重复 validate()（低）— FIXED ✓

- **验证**: `config.py:241-275` `load_platform_settings()` 函数体中第 266 行构造 `PlatformSettings(...)`（触发 `__post_init__` 校验），函数体中不再有 `settings.validate()` 调用；构造后直接 `return settings`（第 275 行）。
- **结论**: 单一构造期校验真源，无冗余调用。

### MiM 5 合法依赖观察 — REJECTED / CLOSED（无变更需求）

- **结论**: 不处理。

## Adversarial Check — Additional Verification

除逐项验证 accepted findings 外，执行以下额外 adversarial 检查：

| 检查项 | 方法 | 结果 |
|--------|------|------|
| cold import 全路径 | fresh interpreter 7 条导入路径 | 全部成功 |
| Composition str/dict/int/None reject | 运行时构造验证 | 全部 fail closed |
| 空/仅空白/首尾空白键 reject | 运行时构造验证 | 全部 fail closed |
| 键名不匹配 reject | 运行时构造验证 | fail closed |
| secret 异常 redaction | DSN 直构异常验证 | 字段名+规则，无候选值 |
| MappingProxyType snapshot | 构造后原映射修改 | 隔离有效 |
| disabled + services reject | 运行时构造验证 | fail closed |
| provider 协议运行时检查 | `isinstance(str, PlatformCompositionProviderProtocol)` | False |
| admission 顺序 | AST 源码走读 | platform (167-171) before host (210-236) |
| 无 object/cast 逃逸 | AST 扫描两个测试文件 | 无逃逸 |
| pyright | 变更文件 0 errors | 通过 |
| ruff | 默认全规则 | 通过 |
| git diff --check | whitespace | 无错误 |
| 聚焦测试 | 68 passed | 全部通过 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py` | **PASS** — 68 passed |
| `pyright` 变更 production + test 文件 | **PASS** — 0 errors, 0 warnings |
| `ruff check` 默认全规则 | **PASS** — All checks passed |
| Cold import fresh interpreter | **PASS** — 7/7 路径成功 |
| Adversarial composition guard | **PASS** — 5/5 场景 fail closed |
| Adversarial secret redaction | **PASS** — DSN/Auth key/Redis/Object storage 均 redacted |
| Admission ordering | **PASS** — platform lines 167-171 before host lines 210-236 |
| AST escape guard | **PASS** — 0 逃逸 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `BaseServiceProtocol`（`protocols.py:44-46`）仍为零成员 `@runtime_checkable` Protocol，任意值结构性通过；但本 slice 的平台组合契约已完全基于 `PlatformServiceProtocol`（携带 `platform_service_name`），`BaseServiceProtocol` 用于既有服务层协议体系（Chat/Prompt/Write/Fins/HostAdmin/ReplyDelivery），与平台组合无关。修复不应改变既有服务层协议结构，当前隔离正确。
- `dayu/services/startup_preparation.py` 的 `prepare_host_admin_dependencies`（行 251-302）和 `prepare_scene_execution_acceptance_preparer`（行 100-130）未被本轮测试覆盖，均为既有未覆盖区域，非本 slice 新增逻辑。
- 根 README 未记录平台 env 开关，用户可能不知晓该开关存在；由后续 slice（1.2 首次真实装配）随 operator workflow 补充。
- 全量 unit lane `pytest -q --timeout=60 -m "not integration and not slow and not e2e"` 未复跑（因 fix artifact 已报告 7543 passed，本轮聚焦 Slice 0.2 路径）；若有回归风险需在 accepted commit 前复跑。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。全部 8 项 accepted findings（合并后 7 项有效）已按 adjudication required closure 完成修复并经双路验证。Adversarial 检查无新增问题。允许进入 accepted local commit。
