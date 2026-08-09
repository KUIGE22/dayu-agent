# Code Review

## Scope

- Mode: current changes（Gateflow-governed 第二路独立 code review）
- Review time: `2026-08-10 06:24:15 +0800`（本机系统时钟）
- Branch: `feat/investment-agent-acceptance`
- Base: `d9f26713f651b459bac7915389b4fedc32707b0d`
- Output file: `docs/reviews/code-review-20260810-system-clock-precision-codex.md`
- Included scope: `utils/investment_agent_acceptance.py` 的 `SystemClock.utc_now()` precision correction；`tests/test_investment_agent_acceptance.py` 的真实 CLI、fixed-clock strictness、staging cleanup 与 adapter regression；accepted plan 的 `Slice 5 pre-prepare erratum — SystemClock 秒精度系统边界`；`docs/reviews/implementation-20260810-system-clock-precision-codex.md`
- Excluded scope: baseline 已接受实现、其它未跟踪 review artifacts、正式 `prepare`、live `run`、网络/SEC/模型/付费执行；未修改 production/tests/plan/implementation artifact
- Parallel review coverage: 无；本 reviewer 独立沿 `main → prepare_acceptance → _write_run_skeleton → _require_utc_datetime` 真实路径及 `SystemClock` 的 run/verify consumers 走读

## Findings

未发现实质性问题。

结论：**PASS**。Open High / Medium / Low = **0 / 0 / 0**。

## Review Evidence

- `SystemClock.utc_now()` 使用 `datetime.now(tz=UTC).replace(microsecond=0)`：先采样真实 UTC，再清零微秒，因此结果不会晚于采样时刻，只可能向下取整不足一秒；未引入 future timestamp。
- normalization 只发生在真实 `SystemClock` adapter；`_require_utc_datetime()`、receipt parser/serializer、`_FixedClock` 与 `_AdvancingClock` 未修改。新增 fixed-clock 回归证明秒精度注入值原样持久化，非零微秒仍以 `ContractError` fail closed。
- `main(argv)` 的 prepare 分支实际构造生产 `SystemClock`，测试未替换 `SystemClock`、`prepare_acceptance` 或 `_write_run_skeleton`；仅替换隔离 runtime identity、environment presence 与本地 Git state。prepare call graph 只读取本地 fixture/package config/assets并写 `tmp_path`，未到达 planned process factory。
- fail-if-constructed sentinel 精确覆盖当前唯一 planned `SubprocessFactory` 入口；静态 call-chain 检查确认 prepare 路径不存在其它 planned-command factory/start 调用。生产 prepare 的本地 Git 查询与 planned SEC/model subprocess 属于不同边界，测试通过 static provider 隔离前者。
- 成功回归断言正式 run root 从不存在到完整 canonical skeleton 发布、同父 staging 无残留；非零微秒失败发生在 staging 内，断言正式 root 缺席且精确 staging 被清理。`prepare_acceptance()` 的 `try/except BaseException` 与同父 `Path.replace()` 时序未修改。
- 测试通过 `tmp_path` 与 pytest `monkeypatch` 隔离路径和全局 provider，未读取真实环境变量值；真实 wall clock 只用于 receipt 秒精度断言，不依赖固定秒边界，因此没有可见 clock race。
- `SystemClock` 的 run/verify consumers 同样获得 contract-compatible 秒精度 wall time；whole-run timeout 与 remaining budget 继续由未修改的 monotonic clock 管理。秒内阶段可能显示相同 wall timestamp，是既有 seconds-only receipt contract 的预期表现。
- 本次不改变 CLI、参数、schema、operator workflow、测试分层或架构边界；accepted plan 的 README 不更新决定成立。

## Validation

- Focused regression：`3 passed, 224 deselected`
- Owner test file：`227 passed`
- Pyright：`0 errors, 0 warnings, 0 informations`
- Ruff：`All checks passed!`
- `git diff --check`：PASS
- 未执行正式 `prepare`、live `run`、网络或模型调用

## Open Questions

- 无。

## Residual Risk

- fail-if-constructed sentinel 证明当前 prepare dispatch 不构造唯一 planned `SubprocessFactory`，并由静态 call-chain review 补足当前无旁路的证据；它不是通用 socket/subprocess sandbox。若未来 prepare 新增其它外部 I/O adapter，应在对应变更中增加该 adapter 的 fail-if-called 边界测试。
- 按本 gate 禁令未执行正式 `prepare` 或 live integration；本结论只接受本次两文件 correction 与本地离线 regression，不构成 Slice 5 live 验收通过。
