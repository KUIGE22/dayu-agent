# Code Re-Review — Slice 0.2 Platform Settings / Composition (Final)

## Scope

- Mode: current changes（round2 corrective re-review final，限定为 Slice 0.2 fix 后状态）
- Branch: `codex/investment-platform`（uncommitted workspace changes）
- Base: `d5f024d`（Slice 0.1 predecessor accepted commit）
- Output file: `docs/reviews/code-rereview-20260810-102450-slice-0.2-mimo-native-final.md`
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
  - Gateflow artifacts（改）
- Excluded scope: `dayu/investment/domain/*`（Slice 0.1）、future slices、网络 / model / broker / live 动作
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量走读与逐项验证

## Adjudication Required Closure Verification

逐项独立复现 adjudication（`slice-0.2-corrective-rereview-adjudication-20260810-102200-codex.md`）中两项 accepted findings 的 required closure：

### Terra 001 — DSN/auth/provider-key-shaped profile 异常不含候选值

- **验证方法**: fresh interpreter 分别以 DSN (`postgres://user:secret@host/db`)、auth-token (`auth-token-super-secret-abcdef`)、provider-key (`sk-provider-super-secret-abcdef`) 三种 secret 形状调用 `load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: value})`。
- **直接证据**:
  - 三个 case 均抛出 `PlatformSettingsError`；
  - 异常消息均为 `DAYU_PLATFORM_PROFILE 必须是受支持的部署环境（development / production）`；
  - 三个 secret 形状值均不在 `str(error)` 中；
  - 异常消息包含 `DAYU_PLATFORM_PROFILE_ENV` 环境变量名和固定允许值（development / production）。
- **代码路径**: `config.py:290-295` — `PlatformDeploymentProfile(raw_profile)` 抛出 `ValueError`，`except` 分支构造 `PlatformSettingsError(f"{DAYU_PLATFORM_PROFILE_ENV} 必须是受支持的部署环境（development / production）")`，不格式化 `raw_profile`。
- **测试覆盖**: `test_platform_config.py:985-1015` `TestProfileSettingsRedaction` — 3 例 parametrized 测试，断言 secret_profile 不在 message 且 `DAYU_PLATFORM_PROFILE_ENV` 和固定允许值在 message 中。
- **结论**: ✅ CLOSED — 三种 secret 形状 profile 值均被 redacted，异常消息稳定且不含候选值。

### Terra 002 — public PlatformSettings 直接构造器运行时类型边界

- **验证方法**: 对 `PlatformSettings` dataclass 使用 `dataclasses.replace()` 注入非 `bool`/非 `PlatformDeploymentProfile`/非 `str|None` 值，逐项复现。
- **直接证据**:
  - `enabled=1` → `PlatformSettingsError("enabled 必须是布尔值")` ✅
  - `use_in_memory_adapters="yes"` → `PlatformSettingsError("use_in_memory_adapters 必须是布尔值")` ✅
  - `profile="unsupported-profile"` → `PlatformSettingsError("profile 必须是 PlatformDeploymentProfile 枚举值")` ✅
  - `postgres_dsn_env=123` → `PlatformSettingsError("postgres_dsn_env 必须是环境变量名称或 None")` ✅
  - `postgres_dsn_env=True` → `PlatformSettingsError("postgres_dsn_env 必须是环境变量名称或 None")` ✅
  - `postgres_dsn_env=b"bytes"` → `PlatformSettingsError("postgres_dsn_env 必须是环境变量名称或 None")` ✅
- **代码路径**: `config.py:129-150` `_validate_field_types()` — 先于所有业务校验执行；`isinstance` 检查精确类型，非 bool / 非枚举 / 非 str|None 一律 raise。
- **测试覆盖**: `test_platform_config.py:1018-1104` `TestPlatformSettingsStrictTypes` — 4 个测试方法覆盖 `enabled=1`、`use_in_memory_adapters="yes"`、未知字符串 profile、非字符串 env-name（int / bool / bytes）。
- **结论**: ✅ CLOSED — 所有反例均稳定 `PlatformSettingsError` 且消息不回显候选值。

## Previously Accepted Findings — Regression Check

| 区域 | 验证方法 | 结果 |
|------|---------|------|
| Cold import 无 cycle | fresh interpreter 7 条路径：`dayu.startup.platform`、`dayu.investment.composition`、`dayu.investment.config`、`dayu.services.protocols`、`dayu.services.startup_preparation`、`dayu.services`、`dayu.web.streamlit_app` | ✅ 全部 PASS |
| Runtime Service protocol 拒绝任意值 | str/dict/int/None 构造 → `PlatformCompositionContractError`；`isinstance` 运行时检查 | ✅ 全部 FAIL closed |
| 注册键/名称空、仅空白、首尾空白、名称不匹配 | 构造验证 | ✅ 全部 FAIL closed |
| Mapping 防御快照 | 构造后原映射修改 → composition 不受影响 | ✅ 隔离有效 |
| secret 异常 redaction（infra env-name） | DSN/Auth key/Redis/Object storage 四类 secret-shape → `PlatformSettingsError` | ✅ 候选值不在 message |
| platform admission 位于 Host/schema/recovery 前 | `startup_preparation.py:167` (platform) < `:209` (HostStore) < `:220` (Host) < `:236` (recovery) | ✅ 顺序正确 |
| tests 无 Any/object/cast/ignore/getattr/hasattr 逃逸 | AST 扫描两个测试文件 | ✅ 0 逃逸 |
| README 与代码一致 | `dayu/investment/README.md` owner 表、§2.4/§2.5 与当前代码一致；`dayu/README.md` §3.9 同步 | ✅ 一致 |
| 重复 validate 已移除 | `load_platform_settings()` 仅构造并返回，无冗余 `validate()` 调用 | ✅ 单一构造期校验 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py` | **PASS** — 77 passed |
| `pytest tests/investment` (owner) | **PASS** — 173 passed |
| `pyright` 变更 production + test 文件 | **PASS** — 0 errors, 0 warnings |
| `pyright` 全仓 | **PASS** — 17 errors（基线 `docling_processor` / `test_web_tools`），无新增无扩散 |
| `ruff check --select E4,E7,E9,F,I` 变更文件 | **PASS** |
| `ruff check` 默认全规则变更文件 | **PASS** |
| Cold import fresh interpreter 7/7 路径 | **PASS** |
| Adversarial DSN/auth-token/provider-key profile redaction | **PASS** — 3/3 secret 形状值被 redacted |
| Adversarial PlatformSettings strict types | **PASS** — 6/6 反例稳定 PlatformSettingsError |
| Adversarial composition protocol guard | **PASS** — 5/5 场景 fail closed |
| Adversarial composition secret redaction | **PASS** — 候选值不在异常消息 |
| Admission ordering | **PASS** — platform (167) before host (209-236) |
| AST escape guard | **PASS** — 0 逃逸 |
| `git diff --check` | **PASS** — 无 whitespace 错误 |

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

**PASS**。Open H/M/L = **0/0/0**。两项 accepted findings（Terra 001 profile redaction + Terra 002 strict types）均已按 adjudication required closure 修复并经独立验证闭合。此前 cold import / protocol / mapping / admission / test escape / README closure 无回归。全部 14 项验证通过。允许进入 accepted local commit。
