# S31-A Security ORM 增补 V1：Controller 判定

- 被审候选：`docs/plans/2026-09-27-slice-3.1-s31-a-security-orm-addendum-v1.md`，SHA-256 `4975e032cc7365948c53958905316c3301db1e111c0d5f36a9ecf40ea71aedf8`。
- 独立审查：`docs/reviews/plan-review-20260927-204632.md`，SHA-256 `c402ca097df263d15b429bdf2e5444da602fc2108a3691f2ce05dd64d61d681e`；`FAIL`，fresh H/M/L `0/1/0`。
- 接受的基准 V9：`docs/plans/2026-09-27-slice-3.1-strict-evidence.md`，SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`，§2 第 6 项第 28 行已经允许 `models_identity.py` 给公共 `securities` 增加 `(company_id,id,ticker)` UNIQUE；§2 第 8 项及测试 allowlist 已覆盖 0007/验证。

判定：**拒绝增补 V1，不作为实施或审查的规范门。** 候选中“V9 allowlist 缺席”及“增补接受前不得编辑”的断言错误，不能覆盖已接受 V9。保留候选和失败审查仅供审计，不把这个候选 finding 算作 V9 或 S31-A 代码的未关闭缺陷。S31-A 作者可直接依据 V9 完成最小 Security ORM 约束和 0007，对齐 metadata 与真实 PG16 复合 FK、双 MIC、负例、迁移往返；最终仍需独立代码审查 fresh open H/M/L `0/0/0`。

本记录不改 V9、0001–0006、运行中的 S31-A 代码或任何 Gate 状态。S31-A 与十种 shape 递归闭包依各自证据门继续开放。
