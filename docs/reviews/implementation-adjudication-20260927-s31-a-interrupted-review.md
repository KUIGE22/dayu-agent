# S31-A 审查中断后的修复裁定

## 冻结对象与证据界限

- 仓库 `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，HEAD `b6444ae16aa524a717e396160bacc855faa2049f`；S31-A 的 13 个交付文件仍未提交。
- 已接受 V9 计划 `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`。
- 修复前目标：`models_evidence.py` `ecad230d3aab0e484eba9ecaa08122c8585c352c05e72dd17dc94fcfe43b80de`；`0007_strict_evidence.py` `229466f9b3e5703857a3199d569e25220e4aa61887a2571d230ffadf3ec44fd3`；`test_postgres_evidence.py` `588ee06eca49b1f05893d2ad90b1cacc6acf2c6b2846aa91f4c5bf919ea848a1`。
- 原总审查员两次遭遇传输错误，未形成总代码审查报告。其独立 PG/ORM 子审计已只读核对并回报下列 **至少** 3 个 M；另一位非作者只读复核也确认了三处。此记录是 Controller 的修复裁定，不能代替完整独立 code review；当前 S31-A 验收为 `FAIL / open H/M/L >= 0/3/0`，其余未核。

## 已确认的修复输入

1. 0007 downgrade admission 仅查 `pg_class.relacl` 且忽略 `PUBLIC`；外部列级 `pg_attribute.attacl` 和四个新函数 `pg_proc.proacl` 授权也会随对象删除。扩展准入，包含有效默认 ACL、`PUBLIC`、外部 grantee/grantor，并用空库真实 PG 授权、拒绝、撤销后回退覆盖。
2. ClaimVersion 的 ORM/0007 `ck_claim_versions_first_version` 放行 V2 `claim_create` 及无 reviewer witness 的 V1 `approved`，与领域 DTO 相悖。同步收紧为 V1 必为 `claim_create+replace_all+draft`，V2+ 禁 `claim_create`，以 raw PG 反例验证并保持 ORM/迁移 DDL 一致。
3. locator SQL 函数五处文本字段使用默认 `btrim`，不能拒绝 Python/Fins `str.strip()` 会拒绝的 tab 和 Unicode 首尾空白。以精确空白字符集合统一校验，并用 Fins parser、SQL 函数及 raw PG INSERT 反例验证。

## 流转

只修复 V9 S31-A allowlist 内的迁移、ORM 与测试；保留原计划和冻结来源。修复后重新冻结最终磁盘身份，跑必要 unit、架构、PG16、DDL 等价、pyright/ruff，再由非作者对完整 S31-A diff 进行新一轮独立 code review。fresh open H/M/L 明确归零前，不做 Controller acceptance 或 S31-B 代码流转。
