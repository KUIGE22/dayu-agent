# Slice 2.2 CLI argument union 计划勘误接受记录

- **状态**：`ACCEPTED / DEEPSEEK + MIMO DUAL PLAN REVIEW PASS`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **Reviewed target SHA-256**：`a95194bcfe0a83cce859279f47ee4d5f4cdf7b0d6a70d933171d13b377a4a488`
- **Reviewed fix SHA-256**：`dd8776da05f44d4ba7dbba519e2d785b61f0f5e2da3430e5dc7d7403feec317f`

## 裁决

Controller 接受 `S22-CTRL-010`。根因是既有跨命令 AST 合同测试被原 implementation
allowlist 遗漏，而不是四个 platform typed field 错误。修复只允许：

1. 在已允许的 `dayu/cli/arguments.py` 增加 exact4
   `PlatformDispatchArguments(Protocol)`；
2. 让 `DayuCliArguments` 保持 Research exact1 + Write exact20 + Platform exact4
   的无重叠 exact25 annotation union；
3. allowlist 只增加 `tests/application/test_write_cli_dispatch.py`，且只同步目标 AST
   test 与必要模块说明；
4. 保持单一 `argparse.Namespace` base、零 class default、零 custom `__init__`；
5. clean full regression 显式移除继承的 `SERPER_API_KEY`，不修改无关 Serper 路径。

## 双路独立审核

- DeepSeek：`docs/reviews/plan-review-20260812-slice-2.2-cli-argument-union-deepseek.md`，
  `PASS / open H/M/L=0/0/0`，artifact SHA-256
  `6c2883d2acc74806127044f821fbc3c86da08496c7a28c5554a98d1b6e9eda23`。
- MiMo：`docs/reviews/plan-review-20260812-slice-2.2-cli-argument-union-mimo.md`，
  `PASS / open H/M/L=0/0/0`，artifact SHA-256
  `691aa788fbf0ed2d9a0ca7614f2b65cd84e5ab9d6e0c22df8210efd7b8c7612c`。

两路均未发现 open finding；未用 Codex 自审替代任一路审核。

## 恢复边界

implementation 可按修正后 exact allowlist 恢复。该接受不授权 push、PR、live
provider/model/broker、交易或真实投资动作；其余 Slice 2.2 验证、真实 Redis lane、最终
DeepSeek + MiMo code review 与 accepted local implementation commit gate 保持不变。
