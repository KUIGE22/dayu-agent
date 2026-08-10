# Code Re-Review — Slice 0.2 Platform Settings / Composition (Round 3 Closure)

## Scope

- Mode: current changes（Slice 0.2 round3 final closure-only re-review）
- Branch: `codex/investment-platform`（uncommitted workspace changes）
- Base / predecessor accepted commit: `d5f024d`
- Review clock: `2026-08-10 10:31:14 CST`（本机系统时钟）
- Output file: `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`
- Included scope:
  - `dayu/investment/config.py`（新）
  - `dayu/investment/composition.py`（新）
  - `dayu/startup/platform.py`（新）
  - `dayu/services/protocols.py`（改）
  - `dayu/services/startup_preparation.py`（改）
  - `tests/investment/test_platform_config.py`（新）
  - `tests/application/test_service_startup_preparation.py`（改）
  - `dayu/investment/README.md`（改）
  - `dayu/README.md`（改：§3.9）
- Excluded scope: `dayu/investment/domain/*`（Slice 0.1）、future slices、网络 / model / broker / live 动作
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量走读、三层脱敏独立复现与逐项验证

## Adjudication Required Closure — Independent Three-Layer Verification

本轮核心任务：独立验证 Terra 001 round3 的 required closure——unknown profile 对 DSN / auth-token / provider-key 候选在 `str(error)`、`error.__cause__`、`traceback.format_exception(error)` 三层全脱敏。

### 代码路径确认

`config.py:290-295`：`PlatformDeploymentProfile(raw_profile)` 抛出 `ValueError`；`except ValueError:` 分支构造 `PlatformSettingsError(固定消息) from None`，不保留原始 `ValueError` 为 `__cause__`。

### 独立三层复现

在 fresh interpreter 中分别以三种 secret 形状调用 `load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: candidate})`：

| 候选形状 | 候选值 | `str(error)` 不含候选 | `error.__cause__ is None` | `traceback.format_exception(error)` 不含候选 | 消息内容 |
|---------|-------|----------------------|--------------------------|---------------------------------------------|---------|
| DSN | `postgres://user:secret@host/db` | ✅ | ✅ | ✅ | `DAYU_PLATFORM_PROFILE 必须是受支持的部署环境（development / production）` |
| auth-token | `auth-token-super-secret-abcdef` | ✅ | ✅ | ✅ | 同上 |
| provider-key | `sk-provider-super-secret-abcdef` | ✅ | ✅ | ✅ | 同上 |

- 三个 case 均抛出 `PlatformSettingsError`；
- 稳定消息只含 `DAYU_PLATFORM_PROFILE` 与固定允许值（development / production），不含任何候选值；
- `error.__cause__` 为 `None`，`from None` 生效；
- `"".join(traceback.format_exception(error))` 不含候选值，因果链已完全抑制。

### 测试覆盖确认

`test_platform_config.py:986-1023` `TestProfileSettingsRedaction`：
- parametrized 3 例（DSN / auth-token / provider-key）；
- 每例断言 `str(error)` 不含候选（line 1019）；
- 断言 `error.__cause__ is None`（line 1022）；
- 断言 `traceback.format_exception(error)` 不含候选（line 1023）；
- `import traceback` 在文件头（line 17）。

## Terra 002 — Direct Constructor Strict Types

`config.py:129-150` `_validate_field_types()` 在 `__post_init__` 中先于所有业务校验执行：

| 反例 | 预期 | 实际 | 消息 |
|------|------|------|------|
| `enabled=1` | `PlatformSettingsError` | ✅ | `enabled 必须是布尔值` |
| `enabled="yes"` | `PlatformSettingsError` | ✅ | `enabled 必须是布尔值` |
| `use_in_memory_adapters="yes"` | `PlatformSettingsError` | ✅ | `use_in_memory_adapters 必须是布尔值` |
| `profile="bad"` | `PlatformSettingsError` | ✅ | `profile 必须是 PlatformDeploymentProfile 枚举值` |
| `postgres_dsn_env=123` | `PlatformSettingsError` | ✅ | `postgres_dsn_env 必须是环境变量名称或 None` |
| `postgres_dsn_env=True` | `PlatformSettingsError` | ✅ | 同上 |
| `postgres_dsn_env=b"x"` | `PlatformSettingsError` | ✅ | 同上 |

所有消息均不包含候选值。测试覆盖：`test_platform_config.py:1026-1112` `TestPlatformSettingsStrictTypes`，4 个测试方法覆盖 `enabled=1`、`use_in_memory_adapters="yes"`、未知字符串 profile、非字符串 env-name（int / bool / bytes parametrized）。

## Previously Accepted Findings — Regression Check

| 区域 | 验证方法 | 结果 |
|------|---------|------|
| Cold import 无 cycle | fresh interpreter 7 条路径：`dayu.startup.platform`、`dayu.investment.composition`、`dayu.investment.config`、`dayu.services.protocols`、`dayu.services.startup_preparation`、`dayu.services`、`dayu.web.streamlit_app` | ✅ 全部 OK |
| Runtime Service protocol 拒绝任意值 | `isinstance("not-a-service", PlatformServiceProtocol)` → False；str/dict/int/None 构造 → `PlatformCompositionContractError` | ✅ 全部 fail closed |
| 注册键空/仅空白/首尾空白 | 构造验证 | ✅ 全部 fail closed |
| 名称不匹配 reject | 构造验证 | ✅ fail closed |
| Mapping 防御快照 | `MappingProxyType` 快照后原映射修改 → composition 不受影响；`c.services['new'] = 'x'` → `TypeError` | ✅ 隔离有效 |
| disabled + services reject | 构造验证 | ✅ fail closed |
| secret 异常 redaction（infra env-name） | DSN / Auth key / Redis / Object storage 四类 secret-shape → `PlatformSettingsError` | ✅ 候选值不在 message |
| platform admission 位于 Host/schema/recovery 前 | `startup_preparation.py:167` (platform) < `:209` (HostStore) < `:220` (Host) < `:236` (recovery) | ✅ 顺序正确 |
| tests 无 Any/object/cast/getattr/hasattr 逃逸 | AST 扫描两个测试文件 | ✅ 0 逃逸 |
| README 与代码一致 | `dayu/investment/README.md` owner 表、§2.4/§2.5 与当前代码一致 | ✅ 一致 |
| 重复 validate 已移除 | `load_platform_settings()` 仅构造并返回 | ✅ 单一构造期校验 |
| production + in-memory reject | `PlatformSettings(enabled=True, profile=PRODUCTION, use_in_memory_adapters=True, ...)` → `PlatformSettingsError` | ✅ fail closed |
| production missing env reject | 缺四个基础设施 env-name → `PlatformSettingsError` | ✅ fail closed |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py` | **PASS** — 77 passed |
| `pytest tests/investment`（owner） | **PASS** — 173 passed |
| `pyright` 变更 production + test 文件 | **PASS** — 0 errors, 0 warnings, 0 informations |
| `pyright` 全仓 | **PASS** — 17 errors（基线 `docling_processor` / `test_web_tools`），无新增无扩散 |
| `ruff check --select E4,E7,E9,F,I` 变更文件 | **PASS** |
| `ruff check` 默认全规则变更文件 | **PASS** |
| Cold import fresh interpreter 7/7 路径 | **PASS** |
| 三层脱敏独立复现（DSN / auth-token / provider-key） | **PASS** — 3/3 候选值在 str / cause / traceback 全部被 redacted |
| Adversarial PlatformSettings strict types（7 反例） | **PASS** — 全部稳定 `PlatformSettingsError`，消息不含候选值 |
| Adversarial composition protocol guard（str/dict/int/None + 空/空白键） | **PASS** — 9/9 场景 fail closed |
| Adversarial composition disabled + services | **PASS** — fail closed |
| Adversarial MappingProxyType read-only snapshot | **PASS** — `TypeError` on mutation |
| Admission ordering | **PASS** — platform (167-171) before host (209-236) |
| AST escape guard | **PASS** — 0 逃逸 |
| `git diff --check` | **PASS** — 无 whitespace 错误 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `BaseServiceProtocol`（`protocols.py:44-46`）仍为零成员 `@runtime_checkable` Protocol，任意值结构性通过；但本 slice 的平台组合契约已完全基于 `PlatformServiceProtocol`（携带 `platform_service_name`），`BaseServiceProtocol` 用于既有服务层协议体系（Chat/Prompt/Write/Fins/HostAdmin/ReplyDelivery），与平台组合无关。当前隔离正确。
- `dayu/services/startup_preparation.py` 的 `prepare_host_admin_dependencies`（行 251-302）和 `prepare_scene_execution_acceptance_preparer`（行 100-130）未被本轮测试覆盖，均为既有未覆盖区域，非本 slice 新增逻辑。
- 根 README 未记录平台 env 开关，用户可能不知晓该开关存在；由后续 slice（1.2 首次真实装配）随 operator workflow 补充。
- 全量 unit lane `pytest -q --timeout=60 -m "not integration and not slow and not e2e"` 未复跑（因 fix artifact 已报告 7543 passed，本轮聚焦 Slice 0.2 路径）；若有回归风险需在 accepted commit 前复跑。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。Terra 001 round3 的 required closure（`from None` 抑制异常因果链 + DSN / auth-token / provider-key 三层全脱敏断言）已独立复现确认闭合。Terra 002 strict types 无回归。此前 cold import / protocol / mapping / admission / test escape / README closure 无回归。全部 15 项验证通过。允许进入 accepted local commit。
