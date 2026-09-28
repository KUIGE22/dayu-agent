# S31-A domain author handoff（2026-09-27）

## 身份与范围

- Controller 指定 clean base HEAD `db5c79a493fbdba24203150098aa1c64d44666c6`、tree `737ef63e7b0206712dd932016c6f10dd2d7df762`；V9 plan `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`。
- 本 lane 仅新增 `dayu/investment/domain/evidence.py` 与 `tests/investment/test_evidence_domain.py`；未 stage、commit、改 schema/README/其它测试。当前 macOS `/usr/bin/git` 因 Xcode license 提示退出 69，故此 handoff 的 baseline 身份来自 Controller 派发，非本 lane 独立 Git 复核。

## 实施

- 纯投资域 Fins v1 十一键结构镜像，五种 payload，严格 JSON bytes 入口、canonical bytes 和 JSONB 读回结构重建；不导入 Fins、ORM 或存储。
- Fact tagged value、未舍入 Decimal 38/12、unit/currency、PIT UTC/日期/revision 投影；六类主要持久化 DTO 与 §5 写请求均为 frozen slots。
- Claim 普通 append、begin、review、conflict resolution 状态边与局部 eligibility 闭合；review/begin 请求不带自报认证主体。EvidenceLink 明确 Fact/direct arm、`security_id+完整 locator` 身份、copy UUID5、replace/copy 互斥和 immutable source 指纹 frame。Candidate 仅 proposed 输入、bounded finite canonical JSON。

## 最终磁盘文件

| 文件 | 字节 | SHA-256 | 换行 |
| --- | ---: | --- | --- |
| `dayu/investment/domain/evidence.py` | 75641 | `f80cf5b51411ac66cd130a16f897259a69717dc735da33e0e4439d917f5d058b` | LF 2315、CR 0、末尾 LF |
| `tests/investment/test_evidence_domain.py` | 28063 | `1a910baea29f7c7aaad01c92ee1b1d91c19554337ca0ad9ac0332b7f5c32c120` | LF 794、CR 0、末尾 LF |

## 验证

- `.venv/bin/python -m pytest tests/investment/test_evidence_domain.py -q --cov=dayu.investment.domain.evidence --cov-report=term`：38 passed，domain 单文件覆盖率 91%。测试包含五种 locator 与 Fins parser 同义、JSON 歧义输入、decimal/PIT 边界、状态矩阵、双证券 direct 身份与 copy/replace frame。
- `.venv/bin/pyright --pythonpath .venv/bin/python dayu/investment/domain/evidence.py tests/investment/test_evidence_domain.py`：0 errors、0 warnings。
- `.venv/bin/ruff check dayu/investment/domain/evidence.py tests/investment/test_evidence_domain.py`：All checks passed。
- 并行 schema lane 写入期间运行全架构 guard：170 passed、1 failed；唯一失败是当时 `models_evidence.py` 的禁词 `object`，已通知 Controller，schema lane 随后修正。该次运行不能充作最终全仓架构 PASS。

## 未闭合

- 本 handoff 是 author 自查，不是独立 code review、真实 PG 迁移/约束证据或 Gate acceptance。Controller 须在各 lane 完成后按最终磁盘状态聚合复核。
- Fins 当前片段存在性、owner/readback/freshness 属 3.2；本 domain 只保证结构镜像。DB tenant/company/security closure、认证和事务状态由 storage/repository lane 验证。
