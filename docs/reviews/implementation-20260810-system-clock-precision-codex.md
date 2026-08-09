# SystemClock 秒精度修复 — implementation artifact

- 日期：2026-08-10
- Gate：Gateflow-governed implementation
- 角色：implementation worker（非 Controller / reviewer）
- 分支：`feat/investment-agent-acceptance`
- Accepted baseline：`d9f26713f651b459bac7915389b4fedc32707b0d`
- Target plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 的 `Slice 5 pre-prepare erratum — SystemClock 秒精度系统边界`
- Live execution：**NOT AUTHORIZED / NOT RUN**
- 状态：**DUAL CODE REVIEW PASS / READY FOR ACCEPTED COMMIT**

## Scope and outcome

本 work unit 仅修复真实 `SystemClock` adapter 与既有 strict receipt 秒精度契约的边界错位。`SystemClock.utc_now()` 现在在系统采样边界返回 `datetime.now(tz=UTC).replace(microsecond=0)`；`_require_utc_datetime()`、receipt schema/parser/serializer、fixed/fake clock 与 staging 发布时序均未修改。

没有执行正式离线 `prepare`，没有执行 `run`、SEC download、Web、DeepSeek、MiMo、模型命令或任何网络/付费请求。

## Changed files

| File | Change |
|---|---|
| `utils/investment_agent_acceptance.py` | 将真实 UTC wall clock 规范到秒精度，并同步中文 docstring。 |
| `tests/test_investment_agent_acceptance.py` | 增加真实 CLI 组合回归、禁构造 subprocess sentinel、fixed-clock 正负严格语义，并加强 SystemClock adapter 断言。 |
| `docs/reviews/implementation-20260810-system-clock-precision-codex.md` | 记录 implementation scope、验证、文档决定与残余风险。 |

## Regression evidence

真实 CLI 回归调用 `main(("prepare", ...))`，只替换隔离 runtime identity、environment-presence 与 static Git state；未替换 `SystemClock`、`prepare_acceptance` 或 `_write_run_skeleton`。输入仅使用本地 fixture、package config/assets 与 `tmp_path`，并将 `SubprocessFactory` 替换为 fail-if-constructed sentinel。

回归锁定：

1. 真实 `SystemClock.utc_now()` 为 aware UTC、offset 0、`microsecond == 0`。
2. CLI exit 0，stdout 为 exact canonical prepared JSON，plan 与 prepare receipt 均为 canonical bytes。
3. 正式 run root 从不存在到完整发布，同父无 staging 残留。
4. prepare receipt 的 `started_at == ended_at`，序列化无小数秒，records 为空，duration 为 0，remaining wall 为完整预算。
5. 秒精度 `_FixedClock` 的精确注入值原样落入 receipt；非零微秒 `_FixedClock` 仍由 strict ingress 拒绝，且失败后无正式 root/staging 残留。

## Validation

全部命令在项目 `.venv` 中执行：

| Command | Result |
|---|---|
| 三条 focused SystemClock / real prepare CLI / fixed-clock tests | `3 passed` |
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | `227 passed` |
| `pyright utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | `0 errors, 0 warnings, 0 informations` |
| `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | PASS |
| `ruff check utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | PASS |
| `git diff --check` | PASS |

Coverage 未单独执行：项目 `AGENTS.md` 明确豁免 `utils/` 脚本的覆盖率要求，accepted plan 与双路 plan review 也确认本 erratum 无 coverage gate；完整 owner 测试文件已通过。

## Documentation decision

已按 `AGENTS.md` 检查 README 触发范围。此次变更只让内部系统时钟 adapter 遵守已公布的 strict receipt contract，不改变 CLI、参数、schema、operator workflow、分层或测试运行方式。因此按照 accepted plan：**不更新 README、tests README 或 operator runbook**。

## Dual code review closure

| Reviewer | Artifact | Conclusion | Open H/M/L | Validation |
|---|---|---|---|---|
| Codex independent reviewer | `docs/reviews/code-review-20260810-system-clock-precision-codex.md` | **PASS** | `0/0/0` | Focused `3 passed`；owner file `227 passed`；Pyright/Ruff/diff-check PASS。 |
| Terra independent reviewer | `docs/reviews/code-review-20260810-system-clock-precision-terra.md` | **PASS** | `0/0/0` | Focused `2 passed`；Pyright/Ruff/targeted diff-check PASS。 |

两路独立 code review 均未发现 material finding，最终 open High / Medium / Low 为 `0 / 0 / 0`，不需要 review fix。production、tests、target plan 与两份 code review source 自此冻结；本 artifact 只记录 closure，不改变实现或测试证据。

正式离线 `prepare`、live `run`、网络、SEC、Web 与模型执行仍未运行；双路 PASS 只关闭本修复的 code review gate，不扩张 live authorization。

## Residual risks

- 秒精度 wall clock 可能使同一秒内的短阶段显示相同 wall timestamp；这是既有 seconds-only receipt contract 的预期行为，duration/timeout 继续由未改动的 monotonic clock 治理。
- fail-if-constructed sentinel 精确证明 prepare 分支没有构造 planned subprocess factory；测试本身不等价于通用 socket sandbox。真实 prepare call graph 仅使用本地输入，本 work unit 未执行任何网络 owner。
- 本 artifact 与双路 review 已证明 implementation/code-review closure；仍需 Controller 形成 accepted commit。accepted commit 前不得重试正式离线 `prepare`；用户看到并确认 exact fingerprint 前不得执行 live `run`。

## Handoff

- Open implementation blocker：无
- Code review findings：无；两路 PASS，open H/M/L=`0/0/0`，无需 fix
- README/runbook change：无需
- Commit / push / PR：未执行
- Final implementation status：**DUAL CODE REVIEW PASS / READY FOR ACCEPTED COMMIT**
