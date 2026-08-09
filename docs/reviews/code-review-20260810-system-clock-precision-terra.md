# Code Review

## Scope

- Mode: current changes（按指定 baseline 的限域实现审查）
- Branch or PR: `feat/investment-agent-acceptance`
- Base: `d9f26713f651b459bac7915389b4fedc32707b0d`
- Output file: `docs/reviews/code-review-20260810-system-clock-precision-terra.md`
- Included scope: `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py` 中的 SystemClock 秒精度 erratum；只读核对 target plan 和 implementation artifact。
- Excluded scope: 其它 workspace 改动、plan/implementation artifact 的内容变更、正式 `prepare`、任何 live `run`、SEC/Web/模型/网络调用、提交与 PR 操作。
- Parallel review coverage: 无（独立 reviewer 完成生产 adapter、strict ingress、真实 CLI prepare call path、原子发布与新增回归的端到端走读）。

## Findings

未发现实质性问题。

经核对，微秒截断只发生在 `SystemClock.utc_now()` 的系统 adapter 边界（`utils/investment_agent_acceptance.py:1081`）。strict ingress `_require_utc_datetime()` 未变，仍拒绝非 UTC 与任意非零微秒（`utils/investment_agent_acceptance.py:4690-4709`）；`_write_run_skeleton()` 仍在 receipt 建立前调用该 helper（`utils/investment_agent_acceptance.py:3813`）。因此 fixed/fake clock 不会被隐式规范化。

真实 CLI regression 未替换 `SystemClock`、`prepare_acceptance` 或 `_write_run_skeleton`（`tests/test_investment_agent_acceptance.py:3567-3587`），并通过会在构造时失败的 `SubprocessFactory` sentinel 证明 prepare 分支未进入 runner factory。该 sentinel 的断言是有效且范围准确的：生产 `main()` 仅在 `RunCliCommand` 分支构造该 factory（`utils/investment_agent_acceptance.py:1868-1895`）。测试同时严格解析并 canonical round-trip plan/receipt、验证秒精度 receipt、完整 run root 和 staging 清理（`tests/test_investment_agent_acceptance.py:3615-3659`）。

fixed-clock 回归分别证明秒精度值原样写入，以及非零微秒值被拒绝后既不发布 run root 也不残留本次 staging（`tests/test_investment_agent_acceptance.py:3517-3544`）。这与 prepare 的同父 staging → `replace()` 发布，以及异常时只清理未发布 staging 的逻辑一致（`utils/investment_agent_acceptance.py:1636-1649`）。未发现 canonical receipt 或原子 publication 退化。

docstring 已同步声明秒精度；修复不改变公开 CLI、schema、README 所属的用户工作流或分层边界，README 不更新的决定符合已接受 erratum 的限定范围。未发现 `Any`/无类型签名、额外耦合或 allowlist 外的生产/测试修改。

## Open Questions

- 无。

## Residual Risk

- 本次只执行新增的两个本地隔离回归与静态检查；未复跑整份 227 项测试文件，也未执行正式 `prepare` 或任何外部执行。implementation artifact 报告了全文件回归通过，但该结果未由本 reviewer 重新执行。
- `SystemClock` 的直接断言采样真实系统时间；在极罕见的恰好整秒采样下，旧实现也可能满足单次 `microsecond == 0` 断言。真实 CLI regression 仍覆盖实际组合路径，且生产 diff 的唯一行为变更可直接验证为 `.replace(microsecond=0)`；此概率性测试弱点不足以构成 material finding，但后续若重构 clock adapter，可增加一个对受控非零微秒采样的纯 unit test。

## Validation

- `python -m pytest tests/test_investment_agent_acceptance.py -q -k 'prepare_fixed_clock_preserves_seconds_and_rejects_microseconds or real_prepare_cli_uses_second_precision_system_clock_without_subprocess'` — 2 passed。
- `pyright utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` — 0 errors, 0 warnings, 0 informations。
- `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` — PASS。
- `ruff check utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` — PASS。
- `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` — PASS。

## Conclusion

**PASS** — approved SystemClock erratum implementation is consistent with the strict receipt contract and approved two-file boundary. Open High / Medium / Low: **0 / 0 / 0**. No formal prepare, live run, network, SEC, Web, or model action was performed.
