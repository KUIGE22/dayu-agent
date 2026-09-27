# Code Review — S31-A 聚合 PG auth fixture 清理补丁

## Findings

Fresh open H/M/L：**0/0/1，FAIL（仅文档一致性）**。PG 清理的目标行为已实际通过；以下 finding 不表示 auth 或 0007 迁移功能失败。

### 1-未修复-低-auth PG 用例运行版本仍被 README 与测试名写成 0006

- **入口/文件**：`tests/integration/investment/test_postgres_evidence_auth.py:156-177,661`；`dayu/investment/README.md:324,340`；`tests/README.md:57`。
- **输入/实际分支**：fixture 调用 `run_alembic_upgrade(..., "head")`，当前仓库 head 是 `0007_strict_evidence`；补丁的模块说明已改为“当前 head”，并在 teardown 调用 `run_alembic_downgrade(..., "base")`。但两份 README 仍称本 PG 用例“在现有 0006”上运行，测试函数名仍是 `test_s31_auth_pg16_on_existing_0006`。
- **预期/影响**：测试说明应与真实迁移环境相同，以便读者正确理解聚合运行对 0007 与 cluster-level group role 的依赖。当前文字可能让后续维护者误认为此用例只接触 0006，进而遗漏清理要求；未见认证断言语义被改动。
- **建议修复与验证**：同步两份 README 与测试名为“当前 head”，保留“auth 测试不操作 evidence 表、仅验证 S31-Auth 语义”的边界。复核聚合命令仍为 3 passed。
- **修复风险**：低。**严重程度**：低。

## Scope and identity

- 独立非作者小范围复审，base `b6444ae16aa524a717e396160bacc855faa2049f`，branch `codex/investment-platform`。目标文件 `tests/integration/investment/test_postgres_evidence_auth.py` SHA-256 `69fa2830b32181d7a1003c5148987746d77ecb53f2a98ec12e33a6ca331165eb`，27371 bytes / 690 LF，终行 LF。冻结差异仅为模块/fixture 说明、`run_alembic_downgrade` import 与 teardown 调用；未修改认证断言主体。
- 文档比对身份：`dayu/investment/README.md` SHA-256 `1547146aedec38209bd2df037f39a90500d092ddc191b1085dcf611c4154206f`；`tests/README.md` SHA-256 `0ce26a0011e2a317638b0e27b641a848906a4b189ff8b5bba26a9076604390f4`。此前三 finding 的复审已独立落盘于 `docs/reviews/code-review-20260927-220323-s31-a-rereview.md` SHA-256 `60a3b4ae599a6918b12786e348640584c5ee454fba59b5d2a1675dbce142045a`，本报告不重复判定其代码。

## Targeted path review

- **正常/测试体失败后的 teardown**：fixture 已进入 `try: yield _seed(admin, app)` 后，`finally` 依次 `app.dispose()`、`admin.dispose()`、`drop_temporary_login()`、`run_alembic_downgrade(...base)`。`_seed` 或测试体抛错仍会进入该 `finally`。`lifecycle_database` 随后 FORCE 删除该 fixture 自建随机库，session 级 cluster 最终按 owner label 清理。
- **0001 admission**：`0001_platform_foundation._downgrade_admission` 在破坏性 DDL 前拒绝 app/audit group role 的外部 member、活跃 member session、外部 role dependency。先 dispose 引擎再删除临时 LOGIN，使正常 teardown 在回退到 0001 时不再触发自身 member/session 拒绝；若删除 login 失败，后续 downgrade 不会被误称为成功。这保持 0001 的 fail-closed 边界。
- **auth 语义**：补丁未改 `_seed`、`_grant`、撤销快照、RLS/ACL、INFO 日志脱敏、异常回滚或 bearer 检查。`upgrade head` 会创建 0007 schema，但 auth 测试并不插入 evidence 行，0007 空表 downgrade admission 得以通过。相同 pytest 进程 auth→evidence 的实际测试通过，证明正常清理后下一随机库可再创建 0001 group roles。

## Verification actually run

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence_auth.py tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120` | pinned PostgreSQL 16，同进程 3 passed (4.85 s) |
| `.venv/bin/pyright --pythonpath .venv/bin/python tests/integration/investment/test_postgres_evidence_auth.py` | 0 errors, 0 warnings |
| `.venv/bin/ruff check tests/integration/investment/test_postgres_evidence_auth.py` | all checks passed |
| fallback Git `git diff --check` | pass |

Pytest 使用 pinned fallback Git 目录置于 `PATH` 首位，因为宿主 `/usr/bin/git` 受 Xcode license 提示阻断。没有读取或输出真实凭据。

## Open Questions and residual risk

- setup 中 `run_alembic_upgrade`、`create_temporary_login` 和 Engine 构造发生于 fixture 的 `try` 之前；如果这些阶段中途失败，新增 teardown 不执行。这是此补丁未扩展的 setup-failure 范围，不影响已实测的正常/测试体失败后路径；未对该故障注入作通过声明。
- 未重跑 S31-Auth 全部 unit、完整迁移 suite 或全仓质量门。本报告只审这个 fixture 清理补丁；无 stage/commit、无 Gate grant、无 S31-B/Fins/交易权限判断。
