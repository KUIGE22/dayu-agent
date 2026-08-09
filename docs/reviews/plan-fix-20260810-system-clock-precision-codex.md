# AAPL acceptance live prepare SystemClock precision — plan-fix artifact

- 日期：2026-08-10
- Gate：Gateflow-governed minimal plan erratum only
- 角色：planning worker（非 Controller）
- 分支：`feat/investment-agent-acceptance`
- Clean accepted baseline：`d9f26713f651b459bac7915389b4fedc32707b0d`
- Target plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED ERRATUM / DUAL PLAN REVIEW PASS**
- Live execution：**NOT AUTHORIZED / NOT RUN**

## Outcome

本次只修订 target plan，把已复现的秒精度组合错误收窄为两文件修正：真实 `SystemClock.utc_now()` 在系统采样边界规范到秒精度 UTC，strict receipt contract 保持不变，并补齐真实 SystemClock + 离线 prepare CLI 组合回归。没有发现 contract、test ownership 或文件 ownership blocker。

## Dual plan review closure

| Reviewer | Artifact | Conclusion | Open H/M/L |
|---|---|---|---|
| Codex independent plan reviewer | `docs/reviews/plan-review-20260810-system-clock-precision-codex.md` | **PASS** | `0/0/0` |
| Terra independent plan reviewer | `docs/reviews/plan-review-20260810-system-clock-precision-terra.md` | **PASS** | `0/0/0` |

Controller 接受两路 PASS 结论，最终 open High / Medium / Low 为 `0 / 0 / 0`。本 erratum plan gate 已关闭；只允许 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py` 的最小 implementation + regression handoff，不授权任何 live `run`。

## Direct evidence and root cause

| 边界 | 直接证据 | 结论 |
|---|---|---|
| 真实时钟 | `utils/investment_agent_acceptance.py:1068-1081` 的 `SystemClock.utc_now()` 返回 `datetime.now(tz=UTC)` | 常规返回值携带非零微秒 |
| prepare receipt | `_write_run_skeleton()` 对 `clock.utc_now()` 调用 `_require_utc_datetime(..., "prepare receipt time")` | 错误发生在 staging 原子发布前 |
| strict contract | `_require_utc_datetime()` 要求 aware UTC、offset 0、`microsecond == 0` | contract 正确，不应放宽 |
| 测试缺口 | SystemClock adapter test 只断言 offset/monotonic；prepare helper 只使用秒精度 `_FixedClock` | 现有测试未组合真实 SystemClock 与 prepare CLI |
| 已观测失败 | `prepare receipt time 必须是秒精度 UTC` | 与代码数据流同源，根因成立 |

失败后正式 run root 未发布，当次 staging 已清理；未启动 SEC、DeepSeek、MiMo 或其它 planned subprocess，未产生模型费用。

## First-principles decision

秒精度是 receipt 的已有 canonical contract，问题在于系统 adapter 没有满足该边界，不在 parser 过严。因此最小且正确的修复是：

```python
datetime.now(tz=UTC).replace(microsecond=0)
```

该 normalization 只属于 `SystemClock` 系统采样边界。不得在 `_require_utc_datetime()`、receipt parser/serializer 或 `_write_run_skeleton()` 中截断任意注入值；否则会隐藏 fixed/fake clock 违约并破坏 strict ingress。

## Exact implementation boundary

唯一允许文件：

1. `utils/investment_agent_acceptance.py`
2. `tests/test_investment_agent_acceptance.py`

禁止修改 contracts/evaluator、`dayu/`、fixture、README、operator runbook、schema、CLI flag/action 或其他模块。不执行 live `run`、SEC/Web/模型/付费请求。

## Required regression evidence

1. 真实 `SystemClock.utc_now()` 必须返回 aware UTC、offset 0、微秒 0；monotonic 断言不变。
2. 真实 CLI `main(("prepare", ...))` 组合测试仅注入隔离 runtime/presence/Git state，不替换 `SystemClock`、`prepare_acceptance` 或 `_write_run_skeleton`。
3. CLI 测试使用 `tmp_path` 和本地 price fixture；`SubprocessFactory` 为 fail-if-constructed sentinel，以证明无 download/write/model subprocess、无网络/付费侧效。
4. 成功路径必须 exit 0，canonical JSON 报告 prepared，run root 从不存在到完整发布，同父 staging 无残留。
5. strict parse `phase-receipts/prepare.json`：`started_at == ended_at`、秒精度 UTC、无 command records、duration 0、remaining wall 为 full budget。
6. 秒精度 `_FixedClock` 仍精确保留注入值；微秒非零 fixed clock 仍被 strict ingress 拒绝，且失败时无正式 run root/staging 残留。

## Implementation validation contract

```text
python -m pytest tests/test_investment_agent_acceptance.py -q
pyright utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py
ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py
ruff check utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py
git diff --check
```

先单独运行新 SystemClock/prepare CLI/fixed-clock tests，再运行完整 focused file。之后必须双路 code review + Controller adjudication；未接受前不得重试已授权的离线 prepare。

## README decision

**无需更新任何 README 或 `docs/acceptance/` runbook。** 本修复不改变 CLI、参数、schema、operator 流程、分层或测试使用方式；只恢复真实 SystemClock 对已公布 receipt contract 的遵守。

## Authorization and next gate

- 用户已授权本最小修复。
- 现有价格快照与离线 prepare 授权保留，但修复 accepted 前不得重试 prepare。
- 修复 accepted 后只可重新生成 plan，将 exact fingerprint/模型/窗口/价格指纹/预算/run root 展示给用户。
- 用户最终确认前，live `run` 保持 **NOT AUTHORIZED / NOT RUN**。

## Planning result

- Open High / Medium / Low：`0 / 0 / 0`
- Blocking contract gap：无
- Blocking test gap：无；已精确指定缺失回归
- Blocking ownership gap：无；修复与回归均在原 owner 两文件内
- Handoff：**TWO-FILE CODE CORRECTION HANDOFF-READY**

本 artifact 未修改 code/tests/README，未运行 pytest/pyright/Ruff，未 commit/push/PR，未启动 live `run` 或任何外部请求。
