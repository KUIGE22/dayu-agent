# Slice 2.1 identity integration docstring guard 计划勘误

- **状态**：`ACCEPTED / DUAL PLAN RE-REVIEW PASS / IMPLEMENTATION MAY RESUME`
- **历史状态**：`CANDIDATE / IMPLEMENTATION FROZEN / AWAITING DUAL PLAN RE-REVIEW`
- **Controller**：Codex
- **基线 HEAD**：`489a910`
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **主计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **独立复审**：`docs/reviews/plan-review-20260811-slice-2.1-identity-docstring-guard-mim.md`、`docs/reviews/plan-review-20260811-slice-2.1-identity-docstring-guard-mimo.md`
- **验收**：`docs/reviews/plan-acceptance-20260811-slice-2.1-identity-docstring-guard-codex.md`
- **时间**：`2026-08-11 22:11:21 +0800`

## 1. 触发证据

Slice 2.1 implementation WIP 的受影响 unit lane 已通过，随后在当前 Python 3.11
环境显式移除宿主既有 `SERPER_API_KEY` 后运行完整非 integration/slow/e2e lane：

```text
8183 passed, 1 failed, 5 skipped, 138 deselected
```

唯一失败为：

```text
tests/investment/test_architecture_boundaries.py::
TestArchitectureBoundaries::test_integration_tests_carry_chinese_docstrings

test_identity_repositories_postgres.py:
FunctionDef _counted_read_postgres_dsn 缺少中文 docstring
```

`_counted_read_postgres_dsn` 在 `489a910` 已存在且没有 docstring；它位于
`TestProductionStartupBlackBox.test_production_provider_s3_placeholder_still_rejected`
内部。先前 provider allowlist 勘误只授权该方法移除已删除 production helper 的 probe，
并在 target §9 明确禁止修改其它 helper。因此“完整 Python 3.11 lane 必须 PASS”与“不得
给该 helper 补 docstring”无法同时满足。Implementation worker 已按 STOP 条件冻结，未自行
修改该 helper。

首次未清理宿主 `SERPER_API_KEY` 的 full lane 另有既有环境污染；同一测试在
`env -u SERPER_API_KEY` 下独立通过。该环境事实不是本勘误的 production/test finding。

## 2. Controller 裁决

接受一个且仅一个机械授权 `S21-CTRL-DOC-001`：

1. 只在既有嵌套 helper `_counted_read_postgres_dsn` 的函数体首句插入 target §7E 固定的
   完整中文 docstring，说明其计数并转发真实 reader 的 Args/Returns/Raises。
2. 不修改 helper signature、closure、counter、真实 reader 调用、返回值、异常传播或
   monkeypatch target。
3. 去除新增 docstring 后，该 helper AST 必须与 `489a910` 精确相同。
4. `tests/integration/investment/test_identity_repositories_postgres.py` 的其它允许变更仍只限
   target §2 已列的模块说明、两个 exact 方法和两个 obsolete imports；不得借此清理其它
   baseline docstring/import/style 债务。
5. 不修改 architecture guard，不新增 ignore/baseline allowlist，不以跳过 full lane 关闭失败。

本勘误不改变任何 production owner、schema、migration、PG16 lane、business behavior、
test fixture 或 Slice 2.2/2.3 边界。

## 3. 验证与恢复条件

双路 plan re-review 已确认 open H/M/L=`0/0/0`，`S21-CTRL-DOC-001` 已接受，implementation
可按精确 docstring-only 授权恢复。恢复后至少执行：

1. helper stripped-docstring AST 对 `489a910` exact-equivalence；
2. `pytest tests/investment/test_architecture_boundaries.py::TestArchitectureBoundaries::test_integration_tests_carry_chinese_docstrings -q`；
3. `pytest tests/integration/investment/test_identity_repositories_postgres.py -q`，作为三条独立
   PG16 lane 之一，保留真实退出码；
4. `env -u SERPER_API_KEY pytest -q --timeout=60 -m "not integration and not slow and not e2e"`；
5. exact allowlist、`pyright`、Ruff HEAD/current finding delta、`git diff --check`。

若必须修改 helper 可执行 AST、其它 identity integration helper、architecture guard、production
或额外测试才能通过，立即再次 STOP。

## 4. WIP freeze

勘误落盘前 implementation WIP 保持未提交、未暂存。冻结摘要：

- tracked `dayu/` + `tests/` binary diff SHA-256：
  `067a9413ac9b9fa3d987a44c9acb9c01d9dd1b267c4bfbf57dd77be7281e83ee`
- untracked `dayu/` + `tests/` sorted file-hash manifest SHA-256：
  `ab8697afb82a7c9cb42ad7ec5bc162898a1039fb8ab2fea4cec347e7aa5d3d1b`

Plan review 期间 production/tests/README 冻结；只允许修改目标计划、主计划和本 Controller
artifact。不得 commit、push、创建 PR、启动 scheduler/worker、访问 broker/live/model 或执行
付费外部动作。

Architecture guard 真源 `tests/investment/test_architecture_boundaries.py` 的冻结 SHA-256 为
`312992327218b3d0f28d9df5e74525592a97ea9276ceeaad1b76815906f796d6`；本勘误不得修改或豁免它。

## 5. 双审结论

- MiM：`PASS / open H/M/L=0/0/0`；无 findings。
- MiMo：`PASS / open H/M/L=0/0/0`。其标题误用 `H-001` 的观察在正文明确标记为
  `Low -> 已关闭`，并裁决为 non-blocking；Controller 将其作为 closed observation
  记录，不计入 open finding。
- Controller：接受 `S21-CTRL-DOC-001`。两路均确认其是关闭 hard gate 的最小充分授权，
  stripped-docstring AST、architecture guard、独立 PG16 identity lane 与 clean-env full lane
  组成充分的恢复后验证矩阵。

最终状态为 `ACCEPTED / DUAL PLAN RE-REVIEW PASS / IMPLEMENTATION MAY RESUME`；本状态只解除
该计划勘误造成的冻结，不扩大原 Slice 2.1 allowlist，不代表 code review 或 implementation
validation 已通过。

## 6. 历史双审问题

1. `S21-CTRL-DOC-001` 是否是关闭 hard gate 的最小充分授权？
2. stripped-docstring AST 与 full-lane 双门禁是否足以证明零行为变化？
3. 是否存在无需修改 architecture guard、production 或其它 test helper 的更窄方案？
