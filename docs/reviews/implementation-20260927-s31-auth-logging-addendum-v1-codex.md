# S31-Auth 参数日志修复实施增补 V1

## 接受的输入与范围

- 起点 HEAD：`91a42d22d955e44a117e848efe0153708c730724`，`codex/investment-platform`。
- 接受计划增补：`docs/plans/2026-09-27-slice-3.1-s31-auth-logging-addendum-v1.md`；原 V9 计划及先前 S31-Auth 实施记录保持原件。本记录不替代 `implementation-20260927-s31-auth-codex.md`。
- 仅修复独立 code review `docs/reviews/code-review-20260927-200816.md` 所报 INFO 日志泄露 synthetic token hash 的 M finding；未实施 0007、六张 evidence 表、issuer/API 或 S31-A/B。

## 修复与证据

- `create_platform_engine` 保持原签名和 `echo=False`，新增 `hide_parameters=True`。SQLAlchemy Engine INFO 日志及 DB 异常文本不展示 bind 值。
- 认证 helper 在 caller Session 的既有事务中取得一次 `Connection`，先核 `connection.engine.hide_parameters is True`，随后在同一 Connection 上执行 `SET LOCAL`、readback、READ COMMITTED 核查及唯一动作授权 SELECT。外部非隐藏 Engine 在 hash-bound SQL 前收到固定 storage 错；原 SQLAlchemy 异常仍在 `except` 之外映射，避免异常链透出 bind。
- Unit INFO 日志对照：显式非隐藏合成 SQLite Engine 的参数化查询可记录 synthetic hash；平台工厂 Engine 的同一查询及 DB 故障日志/异常文本不含该 hash。此对照只验证 SQLAlchemy logging path。
- 真 PG16 INFO 日志：active actor、reviewer 均成功且日志含授权 SQL，不含 synthetic bearer/hash；外部非隐藏 app Session 对两种动作均在授权 SELECT 前拒绝，日志无 hash/授权 SQL，事务回滚后 Session 可重新查询。迁移 fixture 会关闭 Engine logger，测试显式启用 INFO/propagation 并在结束后恢复原状态。

## 本轮验证

- 受影响 unit、架构与迁移 unit：`220 passed`。
- 真 PG16 auth integration：`1 passed`；unit + 真 PG16 覆盖测量：`6 passed`，`_evidence_review_auth.py` 为 `133 statements / 8 missed / 94%`。
- 四份触及 Python 文件定向 pyright：`0 errors, 0 warnings`；ruff `E4,E7,E9,F,I`：通过；全仓 pyright 仍为本片文件之外 `84 errors, 0 warnings`，不宣称全仓 PASS。
- `git diff --check`、最终文件 SHA/bytes/LF 及 porcelain 在本轮报告核验；未提交。

## 复审门与限制

- 作者自检 fresh open H/M/L：`0/0/0`。旧 code review 的 `FAIL 0/1/0` 不因本次修复自行转为 PASS；须对本次最终磁盘重新独立 code review，零开放 finding 后由 Controller 决定 accepted slice commit。
- 可信进程内故意读取参数的 DBAPI/event hook 不在本片威胁模型；Phase 7.1 API/credential owner 前不能外露 app-role 凭据。S31-A/B、Fins 3.2、十种 shape 完整递归闭包和总 shadow-only 投资决策循环仍开放。
