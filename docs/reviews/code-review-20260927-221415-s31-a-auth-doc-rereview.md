# Code Review — S31-A auth PG head 文档复审

## Findings

Fresh open H/M/L：**0/0/0，PASS（只限上一轮一项 L 文档漂移）**。未发现新的可执行 finding；不将本结论扩展至此前已关闭的三项代码 finding 或 S31-B。

## Scope and frozen identity

- 非作者、只读、有界复审。Repository HEAD `b6444ae16aa524a717e396160bacc855faa2049f`，branch `codex/investment-platform`。上一轮唯一 L 来源：`docs/reviews/code-review-20260927-221119-s31-a-auth-fixture-rereview.md` SHA-256 `332be9b78633b083a82f036286933181ca90a1b812cdbea8d35b3c2d420d8229`。
- 三个最终磁盘目标均以 LF 结尾：

| Path | SHA-256 | Bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/README.md` | `a26f7e318d4954c80193a57d837c321d1f5044ce9fb6ab530c2af69e3ab572b4` | 25845 | 365 |
| `tests/README.md` | `200d1330575d9e4feb9d6f020ab5089f8a5c188e4a6675376eee46b511da40c0` | 135574 | 635 |
| `tests/integration/investment/test_postgres_evidence_auth.py` | `66a5a9466b1a1d3a08b13165afe28f41da083387d4ddbc05cd30e8db662575cf` | 27365 | 690 |

## L finding resolution

- `dayu/investment/README.md:324,340` 两处都已说 auth PG 测试运行于当前 head（0007），只验证认证语义；`tests/README.md:57` 同步当前 head（0007）。这与 fixture `test_postgres_evidence_auth.py:167` 的 `run_alembic_upgrade(...head)`、`:177` 的回退到 base 一致。
- 测试名在 `test_postgres_evidence_auth.py:661` 改为 `test_s31_auth_pg16_on_current_head`，其 docstring 说明 0001 group role 是 cluster-global，fixture 删除临时 LOGIN 并回退到 base，使下一随机库可再执行 0001。测试体的 auth 断言调用顺序没有改变。
- 两份 README 仍将 0001–0006 的 27 表基线和 0006 migration owner 单独描述；这些历史说明有明确版本限定，不再把当前 auth fixture 误称为 0006。

## Verification actually run

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence_auth.py tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120` | pinned PG16，同进程 3 passed (4.89 s) |
| `.venv/bin/pyright --pythonpath .venv/bin/python tests/integration/investment/test_postgres_evidence_auth.py` | 0 errors, 0 warnings |
| `.venv/bin/ruff check tests/integration/investment/test_postgres_evidence_auth.py` | all checks passed |
| fallback Git `git diff --check` | pass |

Pytest 使用 fallback Git 目录置于 `PATH` 首位，绕过宿主 `/usr/bin/git` 的 Xcode license 阻断。未读取真实凭据。

## Open Questions and residual boundary

此文档复审无开放问题。没有重审 S31-A 全部代码、完整迁移 suite、S31-B repository 或 Fins owner/freshness；本报告不构成 Gate acceptance、提交或交易授权。只新增本报告，未修改送审文件、未 stage/commit。
