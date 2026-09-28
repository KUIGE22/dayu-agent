# S31-A 本地切片验收：严格证据领域与 0007 schema

## 裁定与边界

- 仓库 `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，验收前 HEAD `b6444ae16aa524a717e396160bacc855faa2049f`。计划真源 `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`；S31-Auth 已在 `db5c79a493fbdba24203150098aa1c64d44666c6` 接受，后续 docs-only HEAD 不改其语义。
- **Controller 裁定：S31-A 本地切片接受，当前代码审查开放 H/M/L = 0/0/0。** 范围是纯领域 DTO、五类 Fins locator 结构镜像、六张私有 ORM 表、0007 迁移与 schema/负例测试。S31-B repository 写入和运行时业务行为尚未实现；Fins owner/readback/freshness、十种 shape 完整递归闭包、H2/S5/D0/Gate、交易权限均未由此验收。
- 此裁定不声称全仓质量门通过：全仓 pyright 有 84 个既存、非本片目标路径的错误；指定目录的完整 Ruff 命令仍有 3 个非 allowlist 旧文件的 import 排序告警。两项均在 aggregate gate 前保持可见，不修改冻结计划或扩散 S31-A 文件范围。

## 最终交付身份

下表均为最终磁盘内容，末尾 LF、零 CR；本次只提交这些 13 个交付路径与下述审查记录。

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/domain/evidence.py` | `6846e067678d25ea9ae8852a5e22f6b126008109ec3d9ef8dd6255bdf831a7d3` | 75956 | 2319 |
| `dayu/investment/storage/models_evidence.py` | `77f4250524951420b70ee2a4de54bedbabeb4ba15795be9c048eaf834669d6e5` | 27274 | 317 |
| `dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | `1a4197b34b7d732b48bf6f30bb78ddfc2f52468f6e8e7cbedd1763b5c0a14ce6` | 44136 | 674 |
| `dayu/investment/storage/models_identity.py` | `5d266741efec51b7b83178de4228b86a0dc87785a16b3a9bb3a2fc283f090a78` | 38494 | 910 |
| `dayu/investment/storage/__init__.py` | `ab606c9fcff9cbed2e4eccbaec01ce6caf40780a363fde539ecb4e4cc5378106` | 2627 | 90 |
| `dayu/investment/README.md` | `a26f7e318d4954c80193a57d837c321d1f5044ce9fb6ab530c2af69e3ab572b4` | 25845 | 365 |
| `tests/investment/test_evidence_domain.py` | `9176ab86e751745c0ce6ba22a3df51986eaeebaa9267d0e0ffe2e5dd6fadb0e2` | 28813 | 812 |
| `tests/investment/test_evidence_storage_contract.py` | `eebcef575ad3c8d31e606c84803fd2d0428dc8a8f3be65567b161a64fd911eae` | 5365 | 140 |
| `tests/investment/test_platform_migrations.py` | `8cfab568a6b57d9d3a49c5bf458bc563edf5d4365f9d11f977e7e1b62272a51c` | 110408 | 3192 |
| `tests/integration/investment/test_postgres_evidence.py` | `ad4d862410796bcbee45b2f7eafd6f0c88c564d320143badd73c307a0202062a` | 29337 | 554 |
| `tests/integration/investment/test_postgres_evidence_auth.py` | `66a5a9466b1a1d3a08b13165afe28f41da083387d4ddbc05cd30e8db662575cf` | 27365 | 690 |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `aca0cbb5b6a55572f1f5387549f405514785842aa3858f82e5b2e3f11344e70b` | 312500 | 6923 |
| `tests/README.md` | `200d1330575d9e4feb9d6f020ab5089f8a5c188e4a6675376eee46b511da40c0` | 135574 | 635 |

## 非作者审查与修复链

- 作者交接 `implementation-20260927-s31-a-domain-handoff.md` SHA `baab9c21bfe2da3c2987106f8418a103c2236ded4e901251737fdf5925281436`。首次总审查传输中断；Controller 有界修复裁定 `implementation-adjudication-20260927-s31-a-interrupted-review.md` SHA `807a15ed9c43cb4f1b8202f92cb67e60e722eaf37017be2db058b618d318e5a6` 明列 ACL、首版约束、locator 空白三项。
- 完整独立 code review `code-review-20260927-215415-s31-a-final.md` SHA `5402722dc48cfb5434ec05525d202841067166770ad0529f5033bf0b8b594baa` 提出 H/M/L `0/2/1`：review witness 持久 ID、真实两连接 NOWAIT、PIT 单侧区间。修复后有界非作者复审 `code-review-20260927-220323-s31-a-rereview.md` SHA `60a3b4ae599a6918b12786e348640584c5ee454fba59b5d2a1675dbce142045a`，对这三项 fresh `0/0/0`。
- 聚合同进程 PG 测试暴露 auth fixture 遗留 cluster-global role。清理补丁的独立报告 `code-review-20260927-221119-s31-a-auth-fixture-rereview.md` SHA `332be9b78633b083a82f036286933181ca90a1b812cdbea8d35b3c2d420d8229` 仅余一项 L 文档漂移；文档/测试名复审 `code-review-20260927-221415-s31-a-auth-doc-rereview.md` SHA `45d5cce52bf9900624650cc705b37dd89a7265b1aa5dac128b6a46d0cc13fe87` fresh `0/0/0`。
- 最终五个本片文件 import 排序的有界非作者复审 `code-review-20260927-221842-s31-a-import-order-rereview.md` SHA `8b8958bc8c73fd199dc80bd418fad9a904f6bc70bbd9408a2329c3dff31cd071` fresh `0/0/0`。四个新文件缺排序前的独立字节快照，因此这份报告只审 import 范围；最终测试和质量检查另按下表记录。暂存检查发现静态迁移 DDL 209 行有行尾空格；仅逐行去尾空白后，六张表 DDL 与 ORM 编译结果逐行去尾空白相等。非作者有界复审 `code-review-20260927-222356-s31-a-0007-trailing-space-rereview.md` SHA `7518e75099121a74f905ab6beb81d09ae2d2eb2fdc8f46ab0ca08492b06e8f89` fresh `0/0/0`；其读取旧 index 时新文件尚未暂存，Controller 随后核 staged blob SHA 为最终 `1a4197b3...`、`git diff --cached --check` 通过。各报告均保留原始 FAIL 与修复后 PASS，不倒改既有审查结论。

## 最终验证

| 验证 | 结果 |
| --- | --- |
| V9 指定 5 文件 unit/architecture pytest | 261 passed，最终 import 排序后复跑 |
| auth→evidence 同进程真实 pinned PG16 pytest | 3 passed，最终 import 排序后复跑 |
| 0007 full-chain migration PG16 pytest | 57 passed，最终迁移格式整理后复跑 |
| 十个本片 Python 目标路径 pyright | 0 errors / 0 warnings，最终磁盘复跑 |
| 五个整理 import 的目标文件 Ruff `E4,E7,E9,F,I` | PASS |
| `git diff --check` 与 `git diff --cached --check` | PASS |
| V9 全仓 pyright | 84 errors，目标路径定向检查为 0；aggregate gate 待处理 |
| 指定目录完整 Ruff `E4,E7,E9,F,I` | 3 个既存非 allowlist 文件 I001：`tests/integration/investment/conftest.py`、`test_workspace_migration.py`、`tests/investment/test_identity_repositories.py` |

PG fixture 使用固定 PostgreSQL 16 镜像与随机库；未读真实凭据。认证 fixture 在当前 head 0007 上只测 S31-Auth 语义，teardown 删除临时 LOGIN 并回退 base，使后续随机库可重新建立 0001 group roles。0007 实测 33 physical / 24 mapped、六张私有表、FORCE RLS/ACL、原始 SQL 负例、双 MIC、五类 locator、空库迁移往返与有界 downgrade 拒绝。S31-B 仍需实现实际 repository CAS、幂等、审查/冲突/到期和 Fins 实时 owner 边界。
