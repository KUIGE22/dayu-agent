# Slice 0.2 corrective re-review fix round3 artifact

- Work unit：`investment-platform-restoration`
- Gate：final corrective re-review fix（round3）
- Source reviews：
  - Terra final：`docs/reviews/code-rereview-20260810-102450-slice-0.2-terra-final.md`
  - MiM Native final：`docs/reviews/code-rereview-20260810-102450-slice-0.2-mimo-native-final.md`
- Adjudication：`docs/reviews/slice-0.2-corrective-rereview-adjudication-20260810-102200-codex.md`
  （§Round 3 final-review disposition）
- Base / predecessor accepted commit：`d5f024d`
- Branch：`codex/investment-platform`
- Fixer：DeepSeek Flash corrective fix worker
- Status：**CLOSED / DUAL RE-REVIEW PASS**
- Artifact path：`docs/reviews/slice-0.2-corrective-rereview-fix-round3-20260810-codex.md`

## Scope

只修 adjudication round3 disposition 的唯一 accepted finding（open H/M/L =
**0/1/0**）；只改 `dayu/investment/config.py`、
`tests/investment/test_platform_config.py` 与既有 implementation / fix /
round2 artifacts，并新增本 round3 artifact。不改 plan / source reviews /
README / 其他 production 或 tests。不得 commit / push / PR / live，不进入
Slice 1.1。

## Per-finding fix status

| Finding | Disposition | Fix status | Closure |
| --- | --- | --- | --- |
| Terra 001（round3）未知 profile 异常因果链在 traceback 回显候选 secret | ACCEPTED / MEDIUM | 已修复 | `load_platform_settings()` 未知 profile 分支改为 `raise PlatformSettingsError(稳定消息) from None`，不再保留不可信 `ValueError` 为 `__cause__`，`traceback.format_exception()` 不再输出含候选值的 cause；已有 3 个 profile secret-shape 测试（DSN / auth-token / provider-key）扩展为同时断言 `str(error)` 无候选、`error.__cause__ is None`、完整 `traceback.format_exception` 文本无候选，稳定消息不变（仍只含 `DAYU_PLATFORM_PROFILE` 与 development / production）。 |

## Changed files

1. `dayu/investment/config.py`（改）— 未知 profile 异常 `from error` → `from None`。
2. `tests/investment/test_platform_config.py`（改）— `import traceback`；
   `TestProfileSettingsRedaction` 三例断言扩展 `__cause__ is None` 与
   traceback 级 redaction。
3. `docs/reviews/slice-0.2-corrective-rereview-fix-round3-20260810-codex.md`
   （新）— 本 artifact。
4. `docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md`
   （改）— 状态更新为 REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW，
   追加 §13 round3 记录。
5. `docs/reviews/slice-0.2-corrective-rereview-fix-round2-20260810-codex.md`
   （改）— 追加 round3 记录。
6. `docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`（改）— 追加
   round3 记录。

## Validation（`.venv` 激活后）

- 聚焦：`tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py`
  → 77 passed。
- owner：`tests/investment` → 173 passed。
- 直接复现 Terra final 反例：`load_platform_settings({DAYU_PLATFORM_PROFILE_ENV:
  "sk-provider-review-secret"})` 的 `str(error)`、`error.__cause__` 与
  `"".join(traceback.format_exception(error))` 均不含候选值。
- pyright：变更 production + test 文件 0 errors；全仓 17 errors 与基线一致，
  无新增无扩散。
- Ruff：`--select E4,E7,E9,F,I` 与默认全规则通过。
- 冷导入：fresh interpreter 变更模块导入成功；`git diff --check` 无
  whitespace 错误。

## Plan gaps

无。round3 是 round2 同一 finding 的因果链闭合，仍在已接受 scope 内。

## Residual Risks（分类）

| 风险 | 分类 / destination |
| --- | --- |
| 若未来重新启用 profile 异常 cause 链（例如为调试引入），需重新评估 redaction | 已固定；无 owner 变更 |
| 根 README 未记录平台 env 开关 | 1.2 首次真实装配时随 operator workflow 补充（assigned to later slice） |

## 未执行的外部动作

- 未 commit / push / PR；未启动最终双路 re-review；未进入 0.3 / 1.1。
- 未修改 plan、source reviews、README、allowlist 外文件。
- 未运行 network / live / model / broker。

## Final dual re-review closure（20260810）

- Terra：`docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
  → PASS，open H/M/L = 0/0/0。
- MiM Native：
  `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`
  → PASS，open H/M/L = 0/0/0。

Round3 唯一 finding 与全部前序 findings 均 CLOSED；本 artifact 状态为
**CLOSED / DUAL RE-REVIEW PASS**。
