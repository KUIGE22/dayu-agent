# Code Review — S31-A 0007 DDL 行尾空白修复

## Findings

Fresh open H/M/L：**0/0/0，PASS（仅 0007 行尾空白补丁）**。工作树中未见 DDL/约束语义漂移。暂存索引仍是修复前版本；提交前必须由 Controller 重新暂存新工作树版本并复跑 `git diff --cached --check`。

## Scope and identity

- 非作者、只读、有界复审。Repository HEAD `b6444ae16aa524a717e396160bacc855faa2049f`，branch `codex/investment-platform`。目标仅 `dayu/investment/storage/migrations/versions/0007_strict_evidence.py`；未改源文件、stage 或 commit。
- Git index 旧 blob：SHA-256 `640e4101c61004ee115b7f7ed66303168fe11fb78c704fc37f14994277f8bd52`，44345 bytes / 674 LF。工作树最终 blob：SHA-256 `1a4197b34b7d732b48bf6f30bb78ddfc2f52468f6e8e7cbedd1763b5c0a14ce6`，44136 bytes / 674 LF。两者均有终行 LF。

## Direct comparison

- 从 `git show :dayu/investment/storage/migrations/versions/0007_strict_evidence.py` 读取暂存旧字节，与当前工作树逐行对照。全文件满足 `old 每行 rstrip(b' \t') + LF == new`；209 个变动行各少 1 个行尾空格，最早第 63 行、最晚第 286 行，全部在 `_TABLE_DDL` 定义内。其余字节、行数、行序均相同。
- AST 提取旧/新 `_TABLE_DDL`，两者均为六条 `CREATE TABLE` SQL 字符串；每条旧 SQL 逐行去尾空白后与新 SQL 完全相同，六表为 `facts`、`claims`、`claim_versions`、`evidence_links`、`claim_conflicts`、`research_candidates`。没有 token、列、约束、FK、CHECK、索引或迁移控制流被更改。改变的 SQL 空格只在每个 DDL 行尾，定向真实 PG16 升降级再验证执行路径。

## Verification actually run

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/investment/test_evidence_storage_contract.py tests/investment/test_platform_migrations.py -q` | 47 passed |
| `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence.py::test_0007_empty_upgrade_downgrade_upgrade -q -m integration --timeout=120` | pinned PG16，1 passed (3.17 s) |
| `.venv/bin/pyright --pythonpath .venv/bin/python dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | 0 errors, 0 warnings |
| `.venv/bin/ruff check dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | all checks passed |
| fallback Git `git diff --check -- dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | pass for working-tree delta |

Pytest 使用 fallback Git 目录置于 `PATH` 首位，绕过宿主 `/usr/bin/git` 的 Xcode license 阻断。Controller 的最终完整 PG/质量门仍在运行；本报告不把未取得的结果写成通过。

## Open Questions and release boundary

当前 index 仍指向含 209 个行尾空格的旧 blob，工作树标记为 `AM`。本报告只审定工作树修复；Controller 需重新 `git add` 此路径后检查 staged blob SHA 等于 `1a4197b3...`，并复跑 `git diff --cached --check`，然后才能将 staged 检查视为通过。除此之外无本范围开放 finding。不重审 S31-B、Fins owner/freshness、十 shape 递归或交易路径；不授 Gate 权限。
