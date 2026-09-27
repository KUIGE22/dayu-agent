# Slice 3.1 / S31-Auth 实施交接

## 身份与范围

- 接受计划：`docs/plans/2026-09-27-slice-3.1-strict-evidence.md`，SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`。
- 起点：branch `codex/investment-platform`，HEAD `7ae26fd1a343547600e4fdd7478a510780c14450`，tree `a6b4abc1900194f4ead1c7f54726cb33ee8b4824`。
- 仅实施 S31-Auth。新增私有辅助模块与 unit/PG16 auth 测试；同步包级和测试 README。未新增六张 evidence 表、0007、token issuer、API 或 S31-A/B 写入行为，未提交。

## 实施事实

- `_evidence_review_auth.py` 校验 canonical 43 字符、解码 32 字节 bearer，仅把 SHA-256 hex 作为参数化 SQL bind；租户范围仅作不可信 RLS lookup hint。调用者必须有 Session 事务；同事务 `SET LOCAL app.tenant_id` 并读回，只接受 READ COMMITTED。
- active actor 与 reviewer 分别执行一条授权 SELECT。前者核现有 token、user、organization active 且 token 未过期；后者在同一语句内再核 `investment.claim.review` 的完整 RBAC grant 链。见证的 actor/tenant/token、grant IDs 与授权时刻从命中行推导；多 grant 按 ID 排序。辅助模块不提交、不更新 token，也不创建 `Principal`。
- 授权线性化点是各自 SELECT 的 READ COMMITTED 语句快照。快照前已提交的撤销拒绝；快照后重叠的撤销不追溯已通过的见证，不能解释为提交时仍有权限。无跨租户全表锁。
- 参数形态与 SQL 故障返回固定脱敏错误。SQLAlchemy 异常在 `except` 之外转为固定错误，避免原 SQL/bind 参数沿 `__context__` 或 `__cause__` 出现在对外异常链。SQL 故障由调用者的事务管理器回滚。
- 使用合成 `secrets.token_urlsafe(32)` fixture；未读取真实凭据。既有 0001–0006 schema/RLS/ACL 原样使用。

## 验证证据

- 受影响 unit、架构与迁移 unit：`219 passed`。运行时把已存在的 CommandLineTools Git 目录放在 `PATH` 前，避免本机 `/usr/bin/git` 许可状态导致既有迁移单测的 subprocess 失败。
- 独立真实 PG16 auth integration：`1 passed`；在现有 0006 上覆盖无 grant、逐项缺 permission/user_role/role_permission、错误提示和 token、null/expired/revoked token、disabled/locked user、disabled org、RLS/ACL、READ COMMITTED 撤销顺序、REPEATABLE READ 拒绝与故障回滚。测试中的原 SQL 异常链、格式化 traceback 均不含 synthetic bearer/hash。
- unit + PG16 覆盖测量：`5 passed`；新辅助模块 `126 statements / 8 missed / 94%`。使用 `COVERAGE_CORE=pytrace` 与 filesystem source 目录 `--cov=dayu/investment/storage`。
- 三份新增 Python 文件的 pyright：`0 errors, 0 warnings`；同文件 `ruff check --select E4,E7,E9,F,I`：通过；`git diff --check`：通过。
- 全仓 pyright 在当前环境仍有 `84 errors, 0 warnings`，诊断均不在本片三份新增 Python 文件。此项是全仓基线限制，不计为 S31-Auth 局部 PASS，也不在本片 allowlist 内修改。

## 审查入口与残余

- 作者自检 fresh open H/M/L：`0/0/0`；尚未执行独立 code review，不能据此宣称 Gate 接受。
- 此辅助仅在可信 `dayu_platform_app` 进程内可用；Phase 7.1 仍负责 issuer/API/凭据隔离。S31-B repository 才负责在受控 begin/review/resolve 操作中消费见证并写入不可变证据；3.2 才负责 Fins owner/freshness。十种 shape 的完整递归闭包仍为独立 OPEN 轨道。
- 下一步：以本次最终磁盘快照作独立 code review；若发现缺陷，按 Gateflow 修复、重验、复审。本记录不构成提交或授权后片实施。
