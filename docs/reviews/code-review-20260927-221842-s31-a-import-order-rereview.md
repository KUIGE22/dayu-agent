# Code Review — S31-A Ruff I001 import 排序有界复审

## Findings

Fresh open H/M/L：**0/0/0，PASS（仅本次五文件 import 排序范围）**。当前磁盘未发现新的 correctness、stability 或维护性 finding；这不是整个 S31-A 的重新验收。

## Scope and final-disk identity

- 非作者、只读复审。Repository HEAD `b6444ae16aa524a717e396160bacc855faa2049f`，branch `codex/investment-platform`。Controller 说明使用 `ruff check --select I --fix` 精确处理五个本片文件；本报告独立核当前 import 区块、最终身份与后续定向行为。未修改源文件、stage 或 commit。
- 五个当前目标均以 LF 结尾：

| Path | Final SHA-256 | Bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/domain/evidence.py` | `6846e067678d25ea9ae8852a5e22f6b126008109ec3d9ef8dd6255bdf831a7d3` | 75956 | 2319 |
| `dayu/investment/storage/__init__.py` | `ab606c9fcff9cbed2e4eccbaec01ce6caf40780a363fde539ecb4e4cc5378106` | 2627 | 90 |
| `dayu/investment/storage/models_evidence.py` | `77f4250524951420b70ee2a4de54bedbabeb4ba15795be9c048eaf834669d6e5` | 27274 | 317 |
| `tests/integration/investment/test_postgres_evidence.py` | `ad4d862410796bcbee45b2f7eafd6f0c88c564d320143badd73c307a0202062a` | 29337 | 554 |
| `tests/investment/test_evidence_domain.py` | `9176ab86e751745c0ce6ba22a3df51986eaeebaa9267d0e0ffe2e5dd6fadb0e2` | 28813 | 812 |

## Review evidence

- `domain/evidence.py` 顶部只有 stdlib import；`models_evidence.py` 是 stdlib→SQLAlchemy→本地 db；两个测试模块是 stdlib→第三方→本地模块。`storage/__init__.py` 的 tracked Git diff 显示此次排序涉及 `TENANT_CONTEXT_SETTING` 在同一 `storage.db` import 列表中移位；其现有 `models_evidence` import 在 `models_identity` 之前，ORM metadata 与真实 PG 路径均由本轮测试实际导入执行。
- 四个新 S31-A 文件在 Git 中仍为 untracked；排序前只有先前审查报告所记 SHA，没有可读取的旧字节副本，故本报告**不声称已作旧/新完整字节 diff 或形式化语义等价证明**。Controller 的精确 Ruff I autofix 说明、当前源码 import 块、Ruff I 无剩余项及受影响测试通过，共同支持“未观察到语义漂移”的有界结论。未把 prior SHA 当作可重建的旧内容。
- 当前 `storage/__init__.py` 的导出仍含六张 evidence ORM；`test_evidence_storage_contract.py` 和 PG schema 测试经过导入链，未见排序引起的循环导入或 metadata 缺项。

## Verification actually run after sorting

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/investment/test_evidence_domain.py tests/investment/test_evidence_storage_contract.py -q` | 41 passed |
| `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120` | pinned PG16，2 passed (4.39 s) |
| `.venv/bin/pyright --pythonpath .venv/bin/python` 加上述五路径 | 0 errors, 0 warnings |
| `.venv/bin/ruff check --select I` 加上述五路径 | all checks passed |
| fallback Git `git diff --check` | pass |

Pytest 使用 fallback Git 目录置于 `PATH` 首位，绕过宿主 `/usr/bin/git` 的 Xcode license 阻断。Controller 提供的 261 unit/architecture 与 57 migration PG 是**排序前**结果，本报告不将其冒作本人排序后复跑。

## Open Questions and residual boundary

无当前有界 finding。若需严格证明所有未提交文件在修复前后只发生 import 排序，需提供排序前五文件可读快照再作 AST/token 对照；现有 prior SHA 不足以完成该证明。未复审 S31-B、Fins owner/freshness、十 shape 递归闭包或交易路径；不授 Gate 权限。
