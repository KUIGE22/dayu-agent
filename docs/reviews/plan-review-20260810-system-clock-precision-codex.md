# SystemClock 秒精度 erratum — Codex 独立 plan review

- 评审时间：`2026-08-10T06:14:39+08:00`（本机系统时钟）
- 角色：第二路独立 plan reviewer（非 Controller）
- 分支：`feat/investment-agent-acceptance`
- Accepted baseline：`d9f26713f651b459bac7915389b4fedc32707b0d`
- Reviewed target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 的 2026-08-10 SystemClock precision erratum
- Reviewed handoff：`docs/reviews/plan-fix-20260810-system-clock-precision-codex.md`
- Review scope：只评审 plan 的根因、两文件边界、真实 CLI 组合回归、时钟注入 fail-closed、staging/canonical receipt、验证与 docs decision
- Out of scope：implementation、code review、commit、push、PR、离线 `prepare` 重试和任何 live/网络/付费执行

## 结论

**PASS**。该 erratum 已达到 code-generation-ready：根因与当前代码数据流同源，`SystemClock` 系统采样边界截断是最小正确修复；两文件 allowlist 足以实现并证明真实 CLI 回归；没有发现会使 implementation agent 重新设计、放宽 strict contract、掩盖注入时钟错误或越过 live authorization gate 的 material finding。

- Open High / Medium / Low：`0 / 0 / 0`
- Final plan review conclusion：`pass`
- Implementation handoff：可进入双路 review 之后的 Controller adjudication；本结论本身不授权实施以外动作，也不授权重新 `prepare` 或执行 live `run`

## Goal、non-goals 与 success signal

- Goal：让真实 `SystemClock.utc_now()` 返回 aware UTC、offset 0、秒精度值，使标准 `prepare` 能生成 canonical `prepare.json`。
- Non-goals：不修改 receipt schema/parser/serializer，不改变 command timing/evaluator/as-of/price 语义，不新增抽象、配置、flag/action，不执行外部调用。
- Success signal：真实 `main(("prepare", ...))` 在不替换 `SystemClock`、`prepare_acceptance`、`_write_run_skeleton` 的情况下 exit 0；run root 原子发布；prepare receipt strict parse 后秒精度、0 record、0 duration、full remaining wall；微秒 fixed clock 仍 fail closed 且无残留。
- Implementation boundary：只允许修改 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py`。

## Assumptions tested

| Assumption | Adversarial check and direct evidence | Result |
|---|---|---|
| 根因是 adapter/contract 组合错位，而不是 receipt parser 过严 | `SystemClock.utc_now()` 当前直接返回 `datetime.now(tz=UTC)`（production `:1055-1081`）；prepare 在 staging 内把该值交给 `_require_utc_datetime()`（`:3813-3825`）；strict helper 明确拒绝非零微秒（`:4690-4709`） | 成立；修 adapter，不放宽 ingress |
| 一处 SystemClock 边界修复覆盖真实 prepare、phase、terminal 与 evaluator | `main()` 每次命令只构造一个真实 `SystemClock`，并把同一实例注入 prepare/run/verify（`:1863-1894`）；phase 与 terminal 均从 `services.clock.utc_now()` 采样（`:2245-2361`、`:2519-2555`）；live evaluator 同样从注入 clock 采样（`:4632-4633`） | 成立；无需在各 consumer 重复截断 |
| 系统边界截断不会掩盖 fixed/fake clock 的错误 | prepare 与 evaluator 分别显式调用 `_require_utc_datetime()`；phase/terminal 虽先构造 receipt，但 `_write_phase_receipt()` 会做 `parse_phase_receipt(receipt.to_json()) == receipt` 的 strict round-trip（`:4285-4312`），微秒值在秒精度序列化后不等于原对象，因此 fail closed；`_FixedClock`/`_AdvancingClock` 直接返回注入值（tests `:294-370`），无需也不得 normalization | 成立；计划要求的微秒 fixed-clock prepare 失败回归足以锁住本次修复边界 |
| 真实 prepare CLI 回归可在两文件 allowlist 内完成且不触发 Popen/网络 | `main()` 的 prepare 分支只构造 `PrepareServices`；`SubprocessFactory()` 只在 run 分支构造（production `:1868-1894`）。测试可沿既有 monkeypatch seam 注入 runtime、environment presence、static Git state，并把 `SubprocessFactory` 替换为 fail-if-constructed sentinel；真实 prepare owner 与 SystemClock 保留。prepare call graph只读取本地 price、package config/assets，并生成 argv/本地 staging，没有 SEC/Web/model client 调用 | 成立；sentinel证明 planned process factory 未构造，代码路径证据证明没有网络 owner |
| 微秒 fixed-clock 失败会清理精确 staging | `prepare_acceptance()` 在同父 `mkdtemp` 后以 `try/except BaseException` 精确删除 staging，再 re-raise；现有 staging failure test 已证明通用 cleanup（tests `:3442-3477`），新回归把失败点换成真实 receipt precision ingress并同时断言正式 root/同父 staging 均缺席 | 成立；测试无需 patch skeleton |
| 成功 receipt 可证明 canonical，而不只证明文件存在 | 计划要求 strict parse、无小数秒文本、parse 后微秒 0、时间相等、0 records、duration 0、full remaining wall；真实 CLI output 还必须等于 canonical prepared JSON。现有 skeleton test仅覆盖结构（tests `:3428-3434`），新回归精确补上缺口 | 成立；验收信号不依赖弱字符串包含断言 |
| docs/type/lint/test gates 没有遗漏 | plan 要求 focused new tests、完整 `tests/test_investment_agent_acceptance.py`、targeted pyright、两层 Ruff 与 `git diff --check`；AGENTS 明确豁免 `utils/` 脚本的覆盖率要求。修复不改变用户命令、schema、operator workflow 或测试运行方式 | 成立；README/runbook 无需机械更新，coverage 不构成缺失 gate |

## Required special lenses

### Architecture boundary review

修复停留在 system adapter owner，consumer 的 strict ingress、receipt/evaluator contracts 与 `dayu/` 分层均不变。依赖方向没有新增反向依赖，也没有把时间 normalization 泄漏到 parser/serializer。结论：无 finding。

### Best-practice review

在采样边界规范化外部系统时间，同时保持注入值严格可观察，是该类可测试时钟 adapter 的最小实践。真实 CLI integration test与 fixed-clock negative test形成正反闭环，且 staging cleanup/canonical bytes均有断言。结论：无 finding。

### Optimal-solution review

替代方案——放宽 `_require_utc_datetime()`、在 serializer 静默截断、给每个 consumer 重复 `.replace()`、引入新 Clock wrapper/config——要么掩盖错误，要么扩大耦合和修改面。plan 的单行 adapter 修复最实际。结论：无 finding。

### Overengineering review

计划明确禁止新抽象、schema、flag/action、contracts/evaluator/dayu 变更；新增测试只覆盖已复现组合缺口。结论：无过度设计。

### Overcoupling review

`SystemClock` 继续通过既有 `Clock` protocol 注入；prepare/run/verify owners不互相新增依赖。两文件修改是实现与其 owner 测试的正常闭包，不要求跨层同步修改。结论：无过度耦合。

## Findings

无 material findings。

## Open questions

无。implementation agent 不需要自行选择截断位置、测试 seam、文件范围或 docs 策略。

## Residual risks and tracking

| Residual risk | Disposition / tracking destination |
|---|---|
| 秒精度会让同一秒内的短 phase/command wall duration显示为 0 | 这是既有 receipt 秒精度契约的预期表现；预算/timeout仍由 monotonic clock治理，不属于本 erratum。后续 code review确认 monotonic逻辑未改变 |
| `SubprocessFactory` sentinel 约束的是验收计划命令工厂，不是通用 socket sandbox | 当前 prepare call graph无网络 owner；implementation/code review仍须确认测试没有真实环境 provider、SEC/Web/model调用，且不得执行 live `run` |
| README 总规则要求代码变化后检查 docs | 已完成职责检查：内部 adapter精度修复不改变用户或测试手册可见行为；Controller closure记录“checked, no update”，无需产生白名单外改动 |

## Reviewer boundary statement

本评审只读取 plan、handoff、相关 production/tests/contract 证据并写入本 artifact；未修改 plan/code/tests/README，未运行 implementation tests，未 commit/push/PR，未执行 `prepare`、`run`、SEC/Web/模型或任何网络/付费动作。
