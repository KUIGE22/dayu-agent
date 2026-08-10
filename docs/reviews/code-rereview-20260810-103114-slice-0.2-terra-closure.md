# Code Re-Review — Slice 0.2 Platform Settings / Composition (Round3 Closure)

## Scope

- Mode: current changes（round3 closure-only re-review）
- Branch: `codex/investment-platform`
- Base / predecessor accepted commit: `d5f024d`
- Review clock: `2026-08-10 10:33:52 CST`（本机系统时钟）
- Output file: `docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
- Included scope:
  - 根 `AGENTS.md`、accepted master plan 的 Slice 0.2；Terra FAIL、MiM final review、Controller round3 disposition 与 round3 fix artifact。
  - 唯一待闭合链路：`load_platform_settings()` 的 unknown-profile 异常，覆盖 `str(error)`、`error.__cause__` 与完整 `traceback.format_exception(error)`。
  - 对此前已闭合的公开构造器严格类型、cold import、Service Protocol / composition mapping、startup admission 与 README 边界做非回归检查。
- Excluded scope: Slice 0.1 已接受 domain、future slices、网络 / model / broker / live 动作；未修改 production、tests、README、plan、既有 artifact、commit 或远端状态。
- Parallel review coverage: 无；主 reviewer 沿 `load_platform_settings()` → `PlatformSettings` → `build_platform_composition()` → `prepare_host_runtime_dependencies()` 独立走读并复跑验证。

## Findings

未发现实质性问题。

round3 唯一 accepted finding 已闭合：`dayu/investment/config.py:290-295` 对枚举转换失败使用 `raise PlatformSettingsError(...) from None`。在全新解释器中分别以 DSN、auth-token、provider-key 形状的 unknown profile 调用真实入口，三例均满足：稳定错误消息不含候选值、`error.__cause__ is None`、完整 `traceback.format_exception(error)` 文本不含候选值。回归测试 `tests/investment/test_platform_config.py:986-1023` 覆盖同一三层泄露面。

此前闭合面无回归：`PlatformSettings._validate_field_types()`（`dayu/investment/config.py:129-150`）仍在业务规则前拒绝 `enabled=1`、`use_in_memory_adapters="yes"`、字符串 profile 以及 `int` / `bool` / `bytes` env-name；cold import 7/7 通过；组合根仍只接收非空 `PlatformServiceProtocol`、防御性快照注册映射，且平台 admission 仍早于 Host schema / Fins / recovery 副作用。

## Open Questions

无。

## Residual Risk

- 本轮未运行 network、model、broker、live、持久化基础设施或完整 unit lane；均不属于 Slice 0.2 closure-only 授权范围。
- `git diff --check d5f024d` 与本 slice 新增 production/test 文件的 no-index whitespace 检查通过。workspace 全量未跟踪文件扫描仍发现两份既有 review artifact 末尾额外空行：`docs/reviews/slice-0.2-code-review-adjudication-20260810-094100-codex.md:59`、`docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md:204`；这是非实质文档 whitespace，不计入 H/M/L，且按本轮只新增指定 artifact 的约束未修改。

## Validation Summary

| 检查项 | 结果 |
| --- | --- |
| fresh-interpreter unknown-profile redaction（DSN / auth-token / provider-key） | PASS — 3/3 `str`、`__cause__`、完整 traceback 均满足脱敏契约 |
| 公开构造器严格类型反例 | PASS — 6/6 被 `PlatformSettingsError` 拒绝 |
| cold imports | PASS — 7/7 路径成功 |
| `pytest tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py -q` | PASS — 77 passed |
| `pytest tests/investment -q` | PASS — 173 passed |
| 指定 production/test 文件 `pyright` | PASS — 0 errors, 0 warnings, 0 informations |
| 指定 Python 文件 Ruff F/I 与默认规则 | PASS |
| `git diff --check d5f024d` 与本 slice 新增 production/test no-index check | PASS |

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。round3 唯一 traceback-level secret-redaction finding 已按 Controller required closure 完整验证关闭；此前 strict-types、cold-import、protocol/mapping/admission/README 边界无回归。
