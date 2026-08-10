# Code Re-review

## Scope

- Mode: current changes（Slice 0.2 round2 final corrective re-review）
- Branch: `codex/investment-platform`
- Base / predecessor accepted commit: `d5f024d`
- Review clock: `2026-08-10 10:27:40 CST`（本机系统时钟）
- Output file: `docs/reviews/code-rereview-20260810-102450-slice-0.2-terra-final.md`
- Included scope: 根 `AGENTS.md`；accepted master plan 的 Slice 0.2；两份初审、前轮双路 re-review、Controller corrective adjudication、round2 fix 与 implementation artifacts；以及当前 Slice 0.2 production、tests、README、启动注入链路。
- Excluded scope: Slice 0.1 已接受的 domain 实现、future slices、网络 / model / broker / live 动作；未修改任何 production、test、README、plan 或既有 artifact。
- Parallel review coverage: 无。独立走读 `load_platform_settings()` → `PlatformSettings` → `build_platform_composition()` → `prepare_host_runtime_dependencies()`，并以 fresh interpreter 和公开构造器复现边界。

## Findings

### 001-未修复-中-未知 profile 的异常因果链仍在 traceback 回显候选 secret

- **入口/函数**: `load_platform_settings()`。
- **文件(行号)**: `dayu/investment/config.py:290-295`。
- **输入场景**: `DAYU_PLATFORM_PROFILE` 被误配为 DSN、auth token 或 provider key 形状的 secret，例如 `sk-provider-review-secret`。
- **实际分支**: `PlatformDeploymentProfile(raw_profile)` 抛出含候选值的 `ValueError`；`except ValueError as error` 通过 `raise PlatformSettingsError(...) from error` 保留它为 `PlatformSettingsError.__cause__`。
- **预期行为**: Controller 对 Terra 001 的 required closure 要求未知 profile 使用稳定消息且不含候选值；包 README 也承诺未知 profile 异常只报告字段与固定规则。该契约必须覆盖常规异常渲染与错误上报，而不仅是 `str(top_level_error)`。
- **实际行为**: 顶层 `str(PlatformSettingsError)` 已脱敏，但 `traceback.format_exception(error)` 会输出 cause：`ValueError: 'sk-provider-review-secret' is not a valid PlatformDeploymentProfile`。对 DSN、auth token、provider key 三类输入均可独立复现。
- **直接证据**: 当前代码第 290-295 行的显式 exception chaining；本复审在 fresh interpreter 运行 `load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: candidate})` 后，对 `"".join(traceback.format_exception(error))` 逐一断言，三例均为 `traceback_redacted=False`。现有 `tests/investment/test_platform_config.py:997-1015` 仅断言 `str(excinfo.value)` 不含候选，未检查 `__cause__` 或格式化 traceback，故 77 个 focused tests 均通过但不能覆盖该泄露面。
- **影响**: 启动失败若被标准 traceback、错误聚合器或日志框架记录，会把误配的 credential 写入日志 / telemetry；这直接违反本 slice 的 secret-redaction 约束，也使 round2 对 Terra 001 的闭合不成立。
- **建议改法和验证点**: 将该分支改为不保留原始 `ValueError`（例如 `raise PlatformSettingsError(stable_message) from None`），保持固定消息。新增 DSN、auth-token、provider-key 三个测试，分别断言 `str(error)`、`error.__cause__ is None` 与 `traceback.format_exception(error)` 均不含候选值。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。

## Residual Risk

- 已独立确认此前冷导入、非空 Service protocol、组合映射防御性快照、启动 admission 前置、测试 escape guard 与 README owner/边界描述没有回归；但 finding 001 修复前，任何记录 exception cause 的观测链路仍可能泄露 profile 候选。
- 验证结果：fresh-interpreter cold import 7 条路径通过；focused `tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py -q` 为 **77 passed**；owner `tests/investment -q` 为 **173 passed**；指定 production/test 文件 pyright 为 **0 errors, 0 warnings, 0 informations**；Ruff `--select E4,E7,E9,F,I` 与默认规则均通过；`git diff --check d5f024d` 和对未跟踪新 Python 文件的 `git diff --no-index --check` 均无 whitespace 错误。
- 未运行 network、model、broker、live 或持久化基础设施；它们不属于本 slice / 本复审授权范围。

## Conclusion

**FAIL**。Open H/M/L = **0/1/0**。在移除未知 profile `ValueError` 的异常因果链并补齐 traceback 级 redaction 回归测试前，不应进入 Slice 0.2 accepted commit。
