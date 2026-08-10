# Slice 0.2 corrective re-review fix round2 artifact

- Work unit：`investment-platform-restoration`
- Gate：corrective re-review fix（round2，pre-re-review bounded correction 之后）
- Source reviews：
  - Terra：`docs/reviews/code-rereview-20260810-101622-slice-0.2-terra.md`
  - MiM Native：`docs/reviews/code-rereview-20260810-101856-slice-0.2-mimo-native.md`
- Adjudication：`docs/reviews/slice-0.2-corrective-rereview-adjudication-20260810-102200-codex.md`
- Base / predecessor accepted commit：`d5f024d`
- Branch：`codex/investment-platform`
- Fixer：DeepSeek Flash corrective fix worker
- Status：**CLOSED / DUAL RE-REVIEW PASS**
- Artifact path：`docs/reviews/slice-0.2-corrective-rereview-fix-round2-20260810-codex.md`

## Scope

只修 adjudication 中 accepted open H/M/L = **0/2/0** 的两项 settings 边界
finding；只改 `dayu/investment/config.py`、
`tests/investment/test_platform_config.py` 与 Gateflow artifacts；不改
plan / source reviews / README / 其他 production 或 tests。不得 commit /
push / PR / live，不进入 Slice 1.1。

## Per-finding fix status

| Finding | Disposition | Fix status | Closure |
| --- | --- | --- | --- |
| Terra 001（round2）未知部署环境异常回显 secret-shaped profile | ACCEPTED / MEDIUM | 已修复 | `load_platform_settings()` 未知 profile 异常改为只写 `DAYU_PLATFORM_PROFILE` 与固定允许值（development / production），不再格式化候选值；新增 DSN / auth-token / provider-key 三类形状的 profile redaction 测试，断言候选值不在 `str(error)` 且消息含环境变量名与允许值。 |
| Terra 002（round2）公开构造器运行时边界不严格 | ACCEPTED / MEDIUM | 已修复 | `PlatformSettings.validate()` 单一边界新增 `_validate_field_types()`：`enabled` / `use_in_memory_adapters` 必须为精确 `bool`、`profile` 必须为 `PlatformDeploymentProfile` 枚举值、四个基础设施字段必须为 `str | None` 之后才做 regex；所有失败消息稳定且不回显候选值；新增直接构造反例：`enabled=1`、`use_in_memory_adapters="yes"`、未知字符串 profile、非字符串 env-name（int / bool / bytes）。 |
| MiM Native PASS | INSUFFICIENT TO CLOSE | 无需修复 | 保持 MiM 对已覆盖边界的 PASS；本 round 以 Terra 两项可复现 finding 为准。 |

## Changed files

1. `dayu/investment/config.py`（改）— `validate()` 前移 `_validate_field_types()`
   类型边界；未知 profile 异常只报告 `DAYU_PLATFORM_PROFILE` 与固定允许值。
2. `tests/investment/test_platform_config.py`（改）— 新增
   `TestProfileSettingsRedaction`（3 例）与 `TestPlatformSettingsStrictTypes`
   （enabled=1 / "yes" / 未知字符串 profile / 非字符串 env-name 4 例）。
3. `docs/reviews/slice-0.2-corrective-rereview-fix-round2-20260810-codex.md`
   （新）— 本 artifact。
4. `docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md`
   （改）— 状态更新为 REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW，
   追加 §12 round2 记录。
5. `docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`（改）— 追加
   round2 corrective fix 记录。

## Validation（`.venv` 激活后）

- 聚焦：`tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py`
  → 77 passed。
- owner：`tests/investment` → 复跑通过（见最终数字）。
- 直接复现 Terra 反例：secret-shaped profile 异常不含候选值；`enabled=1`、
  `use_in_memory_adapters="yes"`、未知字符串 profile 构造一律
  `PlatformSettingsError`，消息稳定。
- pyright：变更 production + test 文件 0 errors；全仓 17 errors 与基线一致，
  无新增无扩散。
- Ruff：`--select E4,E7,E9,F,I` 与默认全规则通过。
- 冷导入：fresh interpreter 变更模块导入成功；`git diff --check` 无
  whitespace 错误。

## Plan gaps

无。adjudication 明确 scope 只含 config / tests / artifacts，不引入
plan change、新依赖、future repository 或兼容适配器。

## Residual Risks（分类）

| 风险 | 分类 / destination |
| --- | --- |
| `PlatformSettings` 类型边界消息为固定文案，不携带具体字段值，调试时依赖字段名定位 | 已固定；无 owner 变更 |
| 根 README 未记录平台 env 开关 | 1.2 首次真实装配时随 operator workflow 补充（assigned to later slice） |

## 未执行的外部动作

- 未 commit / push / PR；未启动最终双路 re-review；未进入 0.3 / 1.1。
- 未修改 plan、source reviews、README、allowlist 外文件。
- 未运行 network / live / model / broker。

## Round3 corrective fix 记录（20260810）

- final corrective re-review（Terra
  `code-rereview-20260810-102450-slice-0.2-terra-final.md`）发现 round2 对
  Terra 001 的闭合不完整：未知 profile 异常仍 `raise ... from error`，完整
  traceback 会经 `ValueError` cause 回显候选 secret；Controller round3
  disposition accepted（open H/M/L = 0/1/0）。
- round3 fix 见 `docs/reviews/slice-0.2-corrective-rereview-fix-round3-20260810-codex.md`；
  本 artifact 状态随之推进为
  **REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW**。

## Final closure（20260810）

Round3 修复经 Terra 与 MiM Native 最终双路复审 PASS，open H/M/L =
**0/0/0**；本 round2 artifact 状态为 **CLOSED / DUAL RE-REVIEW PASS**。
