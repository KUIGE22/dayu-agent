# Code Re-review — Slice 0.2 Platform Settings / Composition

## Scope

- Mode: 当前未提交 Slice 0.2 corrective changes 的独立复审。
- Branch: `codex/investment-platform`。
- Base / predecessor accepted commit: `d5f024d`。
- Output file: `docs/reviews/code-rereview-20260810-101622-slice-0.2-terra.md`。
- Included scope: 根 `AGENTS.md`；accepted master plan 的 Slice 0.2 / §9；两份初审、Controller adjudication、plan fix / 双路 plan review / acceptance、code-fix 与 implementation artifact；以及当前所有 Slice 0.2 production、tests、README 和 artifacts 的未提交改动。
- Excluded scope: Slice 0.1 已接受的 domain 实现、future slices、网络 / model / broker / live 动作；未修改任何 production、tests、plan 或既有 artifact。
- Parallel review coverage: 无；由本 reviewer 走读 `load_platform_settings()` → `build_platform_composition()` → `prepare_host_runtime_dependencies()` 的实际链路，并逐项复现边界输入。

## Findings

### 001-未修复-中-未知部署环境异常仍回显 secret-shaped profile 值

- **入口/函数**: `load_platform_settings()`。
- **文件(行号)**: `dayu/investment/config.py:256-265`。
- **输入场景**: 进程环境误把 credential / DSN 一类值配置到 `DAYU_PLATFORM_PROFILE`，例如 `postgres://user:profile-secret@db/dayu`。
- **实际分支**: `PlatformDeploymentProfile(raw_profile)` 抛出 `ValueError`，`except` 分支把 `raw_profile!r` 拼入 `PlatformSettingsError`。
- **预期行为**: 设置加载的任何非法值都应 fail closed 且不回显候选值；`dayu/investment/README.md:86-87` 也明确声明未知 profile 的异常只报告字段和固定规则。
- **实际行为**: 在 fresh interpreter 复现 `load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: "postgres://user:profile-secret@db/dayu"})`，异常为 `未知平台部署环境 'postgres://user:profile-secret@db/dayu'`，完整 secret-shaped 输入进入日志 / 错误上报面。
- **直接证据**: `config.py:263-265` 的 f-string 格式化不可信 `raw_profile`；`tests/investment/test_platform_config.py:464-478` 只断言普通 `staging` 被拒绝，`891-982` 的 redaction 矩阵仅覆盖四个 infra env-name 字段，未覆盖 profile。
- **影响**: 已接受的 secret-shape 异常不回显目标没有在真实 settings loader 的全部异常路径闭合；配置接线错误可泄露 credential。
- **建议改法和验证点**: 将异常改为只包含 `DAYU_PLATFORM_PROFILE_ENV` 和固定允许规则（不格式化候选值）；新增含 DSN / auth-key 形状 profile 的 redaction 测试，并断言候选值不在 `str(error)`。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 002-未修复-中-公开 PlatformSettings 构造器未对 bool/enum 运行时收口，未知 profile 可绕过 strict settings 契约

- **入口/函数**: `PlatformSettings.__post_init__()` → `validate()`。
- **文件(行号)**: `dayu/investment/config.py:63-120`。
- **输入场景**: 任意程序化调用者直接构造公开的 `PlatformSettings`，传入 `profile="unsupported-profile"`、`enabled=1` 或 `use_in_memory_adapters="yes"`。
- **实际分支**: `validate()` 只以 truthiness 判断两个 bool，并仅比较 `self.profile is PlatformDeploymentProfile.PRODUCTION`；非 enum profile 自动落入 `_validate_development()`。
- **预期行为**: Slice 0.2 的 strict settings 公开构造器应拒绝非 bool 和未知 / 非 `PlatformDeploymentProfile` 值，不能把非法 profile 按 development 路径接受。静态注解不是 Python 运行时 admission。
- **实际行为**: 复现 `PlatformSettings(enabled=True, profile="unsupported-profile", use_in_memory_adapters=True)` 成功构造；`PlatformSettings(enabled=1, profile=PlatformDeploymentProfile.DEVELOPMENT, use_in_memory_adapters="yes")` 也成功构造，字段实际保留 `int` / `str`。前者直接违反 README 对未知 profile fail-closed 的说明，并能改变后续 `settings.enabled` / profile 分支语义。
- **直接证据**: `config.py:71-84` 在构造时只调用 `validate()`；`107-120` 未校验 `enabled`、`profile`、`use_in_memory_adapters` 的运行时类型，且 profile 的唯一分支判断在 `117`。现有 tests 只经 `load_platform_settings()` 解析未知 profile（`test_invalid_profile_rejected`），没有覆盖公开构造器的同一边界。
- **影响**: 公开配置契约不是严格 / fail-closed；未来 composition root、测试装配或非环境来源若直接使用该 dataclass，可在无效类型与未知 profile 下得到看似有效的 settings，导致错误的启动 admission 决策。
- **建议改法和验证点**: 在 `validate()` 开头显式校验 `enabled` 与 `use_in_memory_adapters` 为 `bool`、`profile` 为 `PlatformDeploymentProfile`，并对 infra env-name 的非 `str | None` 输入转换为稳定且不回显候选值的 `PlatformSettingsError`；补充上述直接构造的反例测试。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Accepted Finding Verification

| 已接受项 | 复核结果 | 直接证据 |
| --- | --- | --- |
| cold import 无 cycle | PASS | fresh interpreter 分别导入 `dayu.startup.platform`、`dayu.investment.composition/config`、`dayu.services.protocols`、`dayu.services.startup_preparation`、`dayu.services` 与 `dayu.web.streamlit_app` 均成功；`startup/platform.py:26-32` 只导入纯层。 |
| 非空 runtime Service protocol 拒绝任意值 | PASS | `composition.py:30-69, 180-200` 以非空 `platform_service_name` runtime Protocol 加键 / 名称 / 值校验；测试覆盖 str、dict、int、None。 |
| 注册键 / 名称空、仅空白、首尾空白、名称不匹配 fail closed | PASS | `composition.py:180-200` 的同一校验；`test_platform_config.py:620-698` 覆盖反例。 |
| Mapping 防御快照 | PASS | `composition.py:111, 119-121` 复制后封装为 `MappingProxyType`；实际复现外部 registry 变更不影响 composition，写入代理抛 `TypeError`。 |
| secret-shape 异常不回显 | FAIL | 四个 infra env-name 路径已修复，但 finding 001 证明 profile 的真实 loader 异常仍泄露候选值。 |
| platform admission 位于 Host/schema/recovery 副作用前 | PASS | `startup_preparation.py:167-171` 在路径解析、`HostStore.initialize_schema()`（209-210）、Host 构造（220）和 recovery（236-240）之前；三个 sentinel 反例测试通过。 |
| tests 无 `Any/object/cast/ignore/getattr/hasattr` 逃逸 | PASS | 两个本 slice 测试文件的 AST / source guard 通过；审查 AST 未发现上述符号作为代码逃逸，命中的仅为 guard 常量和 docstring 文本。 |
| README 与代码一致 | FAIL | `dayu/investment/README.md:86-87` 声称未知 profile 不格式化候选值，但 finding 001 的代码反例相反；其余 composition owner / import 边界描述与当前代码一致。 |
| 重复 validate 已移除 | PASS | `load_platform_settings()` 在 `config.py:266-275` 仅构造并返回，构造期唯一校验来自 `__post_init__()`。 |

## Validation

- `python -m pytest tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py -q` → **68 passed**。
- `python -m pytest tests/investment -q` → **164 passed**。
- `python -m pytest tests/application/test_wechat_main.py tests/application/test_entrypoints.py tests/engine/test_cli_running_config.py::test_prepare_cli_host_dependencies_runs_unified_startup_recovery -q` → **36 passed**。
- 变更路径 `pyright` → **0 errors, 0 warnings, 0 informations**。
- 全仓 `pyright` → **17 errors**，均位于既有 `docling_processor` / `test_docling_processor_helpers` / `test_web_tools`，与 fix artifact 记录的基线一致；本 slice 未新增或扩散。
- 变更路径 `ruff check --select E4,E7,E9,F,I` 与默认 `ruff check` → **均通过**。
- `git diff --check` → **通过**（artifact 写入前）；本 artifact 不含空白错误。

## Open Questions

- 无。两项 finding 均可由公开入口和当前代码路径直接复现。

## Residual Risk

- 通过的聚焦测试尚未覆盖 finding 001 的 profile secret-shape 输入或 finding 002 的公开构造器运行时类型边界，因此当前 68/68 不能作为 strict settings 全面闭合证据。
- 未运行 network、model、broker、live 或任何持久化基础设施动作；这些动作不属于本 slice / 本复审授权范围。

## Conclusion

**FAIL**。Open findings：高 **0** / 中 **2** / 低 **0**。在修复两项 settings 边界问题并补齐对应反例测试前，不应进入 Slice 0.2 accepted commit。
