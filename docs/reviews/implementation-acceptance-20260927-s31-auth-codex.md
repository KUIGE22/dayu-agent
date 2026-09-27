# Slice 3.1 S31-Auth Controller 接受记录

- 基线：`codex/investment-platform`，HEAD `91a42d22d955e44a117e848efe0153708c730724`。接受的 V9 计划 SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`；日志修复增补 SHA-256 `dbf930b922ee80c1461c1f7466a6fa47728b775bfb5a4ac0e27d5583d30b4117`，均未改写。
- S31-Auth 初审 `code-review-20260927-200816.md` 的 `FAIL H/M/L=0/1/0` 发现 SQLAlchemy INFO 日志可能记录 token hash。增补计划经独立 planreview `PASS 0/0/0` 后先行提交；受控 Engine `hide_parameters=True`，helper 对外部非隐藏 Session 在 hash-bound SQL 前固定拒绝。
- 对最终实施磁盘的非作者复审 `docs/reviews/code-review-20260927-202841.md`，SHA-256 `9d2aa8706a9baa139b67fce4ca4044d3da1b8e28a7b3525f8826db2d571f076c`，结论 **PASS，fresh open H/M/L=0/0/0**，旧 CR01 在 S31-Auth 范围内关闭。复审绑定了 `db.py`、私有 helper、两份测试、两份 README 及两份实施交接的最终 SHA；本记录不改变这些实施字节。
- 作者验证为受影响 unit/架构/迁移 `220 passed`、真实 PG16 auth `1 passed`、触及 Python 定向 pyright/ruff 与 diff check 通过；非作者独立复跑分别为 unit `5 passed`、PG16 `1 passed`、架构/迁移 `215 passed`、定向 pyright `0 errors`、ruff/diff check 通过。全仓 pyright 的 84 个旧诊断仍开放，不能据局部结果称全仓通过。
- Controller 决定：接受 **S31-Auth 实施片**，允许将审查绑定的 8 个路径、新独立复审及本记录作为一个切片提交；提交成功后可进入 S31-A。此接受只涵盖现有 0006 上的私有认证 helper；0007、六张 evidence 表、S31-B 仓库、Fins 3.2、十种 shape 完整递归闭包、S5/Gate 与总 shadow-only 决策闭环继续按各自门推进。
