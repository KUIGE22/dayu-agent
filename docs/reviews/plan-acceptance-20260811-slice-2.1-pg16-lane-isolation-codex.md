# Slice 2.1 PG16 Lane Isolation — Controller Acceptance

- **Status**：`ACCEPTED / DUAL PLAN RE-REVIEW PASS`
- **Branch**：`codex/investment-platform`
- **Prior accepted erratum commit**：`e0ac679`
- **Plan fix**：`docs/reviews/plan-fix-20260811-slice-2.1-pg16-lane-isolation-codex.md`
- **Reviews**：
  - `docs/reviews/plan-review-20260811-195259-slice-2.1-pg16-lane-isolation-mim.md`：PASS/open H/M/L=`0/0/0`；
  - `docs/reviews/plan-review-20260811-slice-2.1-pg16-lane-isolation-spark.md`：PASS/open H/M/L=`0/0/0`。

## Accepted correction

Slice 2.1 的三份真实 PostgreSQL 16 integration 文件必须分别在三个 pytest 进程运行并逐条保留真实退出码：

1. `pytest tests/integration/investment/test_platform_migrations_postgres.py -q`
2. `pytest tests/integration/investment/test_identity_repositories_postgres.py -q`
3. `pytest tests/integration/investment/test_postgres_jobs.py -q`

不得合并 invocation、用顺序规避、`-k`/skip 缩小或 pipeline 掩盖退出码。该隔离匹配既有 session-scoped PG16 cluster 与 cluster-global group-role admission 设计，不削弱任何测试覆盖。

Provider test cleanup 同时精确允许删除旧 wrapper 唯一使用的 `PlatformCompositionProviderProtocol` 和 `PlatformOwnedLifecycleProtocol` 两个 imports；其它 import 冻结。`test_platform_migrations_postgres.py` 的 0003 exact schema/grant expected catalog 仍由原 accepted PG/CLI test owner完成，不属于新 scope。

## Scope and freeze

- Plan-fix 期间 21/21 production/test WIP SHA-256 保持一致。
- 只修改 target/master 与 plan artifacts；未修改 production/tests/README。
- `git diff --check`、artifact whitespace/final LF 与路径审计通过。

Controller open H/M/L=`0/0/0`。Implementation freeze 解除，允许 Flash 恢复 Slice 2.1 实现与三条 PG16 验证；不授权 push、PR、deploy、live 或 paid action。
