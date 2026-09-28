# Controller 限定接受 — S31-B Fact series 澄清 V2

## 冻结身份

- 仓库 `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，接受时 HEAD `346bf13272f352379edea68439293c53c805d428`。
- 原已接受 Slice 3.1 V9 计划：`docs/plans/2026-09-27-slice-3.1-strict-evidence.md`，SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`，原文件不变。
- 本次接受的窄范围澄清：`docs/plans/2026-09-27-slice-3.1-s31-b-fact-series-clarification-v2.md`，SHA-256 `61785cdcc9a2642e6083322094eed68ceafb3f213a4f112dc7048a51bf0c6f91`。
- 前件 V1 SHA-256 `90dc02f733d9878f964cca5394b09d835198a710927d6f44cfeafe73d4a0d840`；V1 非作者 plan review `docs/reviews/plan-review-20260927-232946.md` SHA-256 `579560512258054e7a43899cf564d75e1248711fc95eac510bc2298502c28566`，FAIL/fresh H/M/L `0/0/1`。两者保留原样。
- V2 非作者 plan review `docs/reviews/plan-review-20260927-233855.md` SHA-256 `38e9432a263b3ad95c17d87bb8a3a8107d2db2b312315047cb2cc6931f478847`，PASS/fresh open H/M/L `0/0/0`；V1 唯一 L 的 staged diff 门序已在 V2 关闭。
- 触发的 S31-B 代码审查 `docs/reviews/code-review-20260927-232544.md` SHA-256 `585960fb6331adf73f9a8d7d44f312de02baf50c5cc9d61dc703fc1ef182461b`，FAIL/fresh H/M/L `0/2/0`。该代码结论没有因计划接受而改变。

## 限定决定

接受 V2 作为 S31-B 的实施补充：Fact series 列表以必填 `(tenant_id, company_id, fact_series_id)` 定位；协议、实现、静态契约及真 PostgreSQL 跨公司用例同步；补证 copy retry 在 head 前进后、reviewer terminal 转换与 bearer 重开、普通 append 状态门。沿用 V9 的既有数据库身份和 0007，不加迁移、不改 Fins/认证/状态矩阵。

实现者仅在 V2 的代码与测试 allowlist 内修改，冻结文件身份与测试结果后由非作者重审 M1/M2。Controller 对实现的接受、准确的 index 路径及 SHA、非空 staged diff 和 commit 都在后续门完成；本记录只接受计划，不接受现有代码或运行证据。任何来源、allowlist 或验收门漂移先停止并重审。

V8/H2、十种 shape 的实际递归值与合法历史、S5/D0/Gate、3.2 Fins 最终就绪及总 shadow-only 决策闭环继续独立 OPEN。
