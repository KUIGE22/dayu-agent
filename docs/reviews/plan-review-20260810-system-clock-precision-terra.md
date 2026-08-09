# AAPL acceptance SystemClock 秒精度 erratum — 独立计划审查（Terra）

- 审查时间：2026-08-10T06:13:11+08:00（本机系统时钟）
- 分支：`feat/investment-agent-acceptance`
- 审查基线：`d9f26713f651b459bac7915389b4fedc32707b0d`
- 审查目标：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 的 2026-08-10 SystemClock precision erratum，以及 `docs/reviews/plan-fix-20260810-system-clock-precision-codex.md`
- 审查范围：仅最小两文件修复计划与其离线回归、授权/停止边界；未审查或实施代码改动。
- 执行边界：未执行 pytest、pyright、ruff、CLI、网络、SEC、模型或 live `run`；未改动 plan/code/tests/README，未 commit/push/PR。

## Goal and implementation boundary reviewed

计划要恢复标准 `prepare` 的既有 receipt 合同：`SystemClock.utc_now()` 在系统采样边界返回秒精度 UTC；`_require_utc_datetime()`、receipt schema/serializer 继续拒绝任意非秒精度的注入值。允许文件严格限于：

1. `utils/investment_agent_acceptance.py`
2. `tests/test_investment_agent_acceptance.py`

不改变 CLI、schema、contracts、evaluator、fixtures、README 或 operator runbook；不授予 `run`、SEC/Web、DeepSeek、MiMo、网络或付费调用权限。

## Assumptions tested and evidence

| Assumption / review lens | Evidence checked | Review result |
|---|---|---|
| 根因与动机成立 | `SystemClock.utc_now()` 当前直接返回 `datetime.now(tz=UTC)`；`_write_run_skeleton()` 将它传给 `_require_utc_datetime(..., "prepare receipt time")`；后者要求 UTC offset 0 且 `microsecond == 0`。 | 成立：真实系统适配器与 strict ingress 的边界错位可在原子 rename 前触发。 |
| 最佳修复边界 | `SystemClock` 是 live CLI 在 `main()` 中创建的系统 adapter；`_require_utc_datetime()` 还保护 prepare、run、verify 的注入时间。 | 选择 `datetime.now(tz=UTC).replace(microsecond=0)` 在 `SystemClock` 边界修复是最小且正确的路径；放宽 contract 或在 skeleton 截断会掩盖 fake/fixed clock 违约。 |
| Architecture / overcoupling | plan 明确禁止触及 contracts、evaluator、schema、flag/action 与 `dayu/`；代码事实显示故障仅在 adapter 到 receipt ingress 的单向连接。 | 无跨层扩散或新抽象需求；两文件 allowlist 与 ownership 相称。 |
| 真实 CLI 离线性 | `main()` 的 `PrepareCliCommand` 分支只构造 `PrepareServices` 并调用 `prepare_acceptance()`；`SubprocessFactory()` 只位于 `RunCliCommand` 分支。prepare 的本地工作为 price/config/assets、环境 presence、Git state、staging 与 rename。 | 计划的真实 `main(("prepare", ...))` 回归可以保持离线；fail-if-constructed `SubprocessFactory` sentinel 适合作为控制流回归，且不应把它表述为外部调用的唯一防线。 |
| Fixed-clock fail-closed | 现有 helper 使用秒精度 `_FixedClock`；`_write_run_skeleton()` 对 clock 值作 strict ingress；`prepare_acceptance()` 的异常路径仅清除本次 staging，正式 run root 在 `staging.replace(run_root)` 后才出现。 | 计划同时要求非零微秒 `_FixedClock` 被拒绝、无 run root/无同父 staging 残留，能防止把 normalization 错放到 ingress。 |
| Atomic cleanup / failure semantics | `prepare_acceptance()` 在同父目录 `mkdtemp`，成功后 `staging.replace(run_root)`；`except BaseException` 仅在 staging 存在时清理并重新抛出。 | 本修复不改变时序；计划要求成功发布和失败清理均回归验证，边界充分。 |
| Validation and handoff readiness | 新测试要求真实 SystemClock、未替换 prepare/skeleton 的 CLI path、严格 parse `prepare.json`、固定时钟正负路径，并保留 focused file、静态检查、diff check、双路 code review 与 Controller adjudication。 | 覆盖根因、成功、strict-negative、原子发布和无子进程的关键反例；实现 Agent 无需重新设计。 |
| README decision | 修复不改变 CLI 参数、schema、operator 流程、授权或可见行为，只令实际 adapter 遵从既有 canonical receipt 精度。 | 不更新 README/runbook 的决定成立。 |
| Stop conditions / authority | target plan 与 plan-fix 均规定修复接受前不得重试 prepare；接受后只可重新生成 plan 并展示 fingerprint；最终用户确认前 live `run` 仍未授权。 | fail-closed 和 handoff 条件明确，未把 repair authorization 扩张为 live execution authorization。 |

## Findings

没有 material findings。

## Open questions

无阻塞性 open question。实现时应按计划将 `SubprocessFactory` sentinel 的断言限定为“prepare 分支未构造 runner factory”；外部 side-effect 禁止仍由真实、未替换的 prepare 路径和本地 inputs 共同证明。

## Residual risks and tracking

- 把系统 wall-clock 截断到秒会使同一秒内的 run/verify wall timestamps 相同；该行为与既有 seconds-only receipt contract 一致，持续由 monotonic clock 负责 duration/timeout，非本 erratum 的新风险。
- 实施后的真实离线 `prepare` 仍须遵守已限定的授权和既定 price snapshot/环境 presence；任何 SEC、Web、模型或付费调用继续由 Slice 5 的独立 live authorization 管理。

建议将上述 residuals 继续留在既有 target plan 的 Slice 5/live authorization 跟踪中，不为本两文件修复新建恢复、schema 或 documentation work unit。

## Conclusion

**PASS** — 计划可交接最小实现；Open High / Medium / Low：**0 / 0 / 0**。

交接前提保持不变：仅在 two-file allowlist 内实现，完整跑计划列出的离线验证与双路 code review/Controller adjudication；在用户最终明确确认前不得执行 live `run`。
