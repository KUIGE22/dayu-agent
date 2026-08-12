# Slice 2.3 Stream Ownership / Domain Split / Coverage — Controller Corrective Plan Acceptance

- **日期**：2026-08-12 CST
- **状态**：`ACCEPTED / ROUND-3 DEEPSEEK FLASH + MIMO PASS / OPEN H/M/L=0/0/0 / LOCAL ACCEPTED CORRECTIVE-PLAN COMMIT NEXT / IMPLEMENTATION FROZEN UNTIL COMMIT SUCCEEDS`
- **分支 / HEAD**：`codex/investment-platform` / `f0414facbef13081bb036e76d748e1f1cbf178b7`
- **目标计划**：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Master control**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **Corrective fix**：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md`
- **历史 accepted plan commit**：`f0414facbef13081bb036e76d748e1f1cbf178b7`；该 commit 是 superseded plan checkpoint，不是本次 corrective acceptance commit。
- **模型路由**：production/tests implementation 与 fix 只由 Codex internal models 完成；DeepSeek Flash 与 MiMo 只承担相互独立的 plan/code review。
- **性质**：corrective plan acceptance bookkeeping，不是 code acceptance；本 artifact 不授权或声称 stage、commit、push、PR、部署、provider、网络、模型、Broker、交易或资金动作已执行。

## 1. Controller 接受结论

Controller 接受 Slice 2.3 stream ownership、five-domain-owner split 与 coverage corrective plan。Round 3
DeepSeek Flash 和 MiMo 独立锁定同一 target/fix/WIP bytes，均为 `PASS / open H/M/L=0/0/0`；没有
blocking open question。

本次 acceptance 只在 target、master 与 fix 写入 status、review history、acceptance link、next gate 和
residual ownership metadata。Round-3 target 的 §1–§16 实施合同、43-path owner-test mapping、18 项
coverage-only zero-edit catalog、157 项命名测试、五个 concrete PG/migration lane、allowlist、STOP 条件与
residual 语义未改。下一步是 Controller 创建本地 accepted corrective-plan commit；该 commit 成功前，
implementation 与保留 WIP 继续冻结。

## 2. 冻结 review bytes 与 metadata closure bytes

| Artifact | Round-3 reviewer frozen SHA-256 / lines | Acceptance metadata closure SHA-256 / lines | 说明 |
| --- | --- | --- | --- |
| Target plan | `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` / 2884 | `a3e3c6b13d68d2d62d3492a0c6c41a1a732112a62a4ed88e39b2d2122d97c578` / 2910 | 只加 acceptance metadata；reviewed identity 保留 |
| Master control | `3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6` / 4238 | `44c78f6615cad61f04678d60f29070851662affe672d0b26d5d97b9cdb672d59` / 4272 | 只加当前 gate、review/acceptance link、changelog metadata |
| Corrective fix | `9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024` / 335 | `f61d146842f3a98978060c30ad082494fc09016956d35027cfaca75be7b062b2` / 363 | 只加 final closure/status、L1 closure、PONR residual 与 next gate |

本 acceptance artifact 不嵌入自身 SHA，避免自引用。创建本地 commit 前，Controller 必须复核上表 closure
SHA；任何 drift 都应停止并重新形成 closure evidence，不得把 metadata 后 SHA 反称为 reviewer 已锁定 SHA。

## 3. 六份 corrective review artifact 与状态历史

| Round | Reviewer | Artifact | Artifact SHA-256 | Reviewed target SHA-256 | Conclusion / open H/M/L | 最终状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | DeepSeek | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-deepseek.md` | `20dc65a18bd9fee5183dae01994b6224ee78b6a4c32fbac24a8bd3a1480f9db1` | `0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e` | `CLARIFY / 0/1/3` | historical；M1、L2–L4 accepted/fixed |
| 1 | MiMo | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-mimo.md` | `e3ba9cd6494ee1147d5a487eff268b73796502d3e356c57b25561c2e0e869e9d` | `0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e` | `PASS / 0/0/0` | historical；只证明 round-1 bytes |
| 2 | DeepSeek Flash | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-deepseek-flash.md` | `25bdcb28718a5840d3cac0a1dee41a282a5e5405bfeb7203da4d3be8211e6289` | `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2` | `CLARIFY / 0/0/1` | historical；L1 accepted/fixed by `S23-CORR-CONTRACT-09` |
| 2 | MiMo | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-mimo.md` | `163c409a993c1c323873f50888df7c13fc59a2ba21fc282b4b0ca960b66c687a` | `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2` | `PASS / 0/0/0` | historical；初始 decoder placement observation 最终证据失效 |
| 3 | DeepSeek Flash | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-deepseek-flash.md` | `78f8a2eaee1d505841c2d8ce141519701cdfa02d1d18110338af508759526a76` | `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` | `PASS / 0/0/0` | final independent PASS |
| 3 | MiMo | `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-mimo.md` | `7725b87136f1594a51535e0aaac30f6c2ef3b2ef3a50f474c0298f2aa73c1c91` | `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` | `PASS / 0/0/0` | final independent PASS |

六份 reviewer artifact 均为只读历史/最终证据；本次 bookkeeping 未修改任一 reviewer artifact。

## 4. Controller finding 与 residual 裁决

- `S23-CORR-STREAM-01`、`S23-CORR-DOMAIN-02`、`S23-CORR-CANONICAL-03`、
  `S23-CORR-RUNTIME-04`、`S23-CORR-COVERAGE-05`：`accepted / fixed`。
- Round-1 DeepSeek M1：`accepted / fixed` by `S23-CORR-COVERAGE-06`；冻结 exact 43-path mapping、
  coverage-only catalog 与五个 PG owner 的 instrumented/plain gate 复用。
- Round-1 DeepSeek L2–L4：`accepted / fixed` by `S23-CORR-CONTRACT-07`；冻结 symbol owner、connector/runtime
  派生公式与 private downloader protocol。
- Round-2 DeepSeek Flash L1：`accepted / fixed` by `S23-CORR-CONTRACT-09`；persistence direct import
  zero-diff mapping owner 的两个 helper，冻结 exact 12-field keyword-only signature、删除五个旧 dependency，
  typed inner `aclose()` exactly once，caller 只传 downloader dependency。
- Round-2 MiMo decoder placement observation：`证据失效`；file-level matrix 已执行 containing
  architecture test file，无 open finding。
- DeepSeek OQ1：`accepted as residual`。owned-thread/PONR cleanup 对 SQLAlchemy/psycopg/OS connect、pool、
  network 或 statement 永不返回没有 wall-clock 上界；NOWAIT 只覆盖 row-lock contention。本 Slice 不用
  `asyncio.wait_for` 遗弃运行中 thread，不扩大 global timeout；后续 platform reliability gate 负责 bounded
  pool/connect/statement/network timeout 配置和故障验证。
- DeepSeek OQ2：`rejected as plan gap`；既有 eager identity/explicit-provider tests 已闭合。
- DeepSeek OQ3：`rejected as edit ripple`；`test_cn_download_runtime.py` 仅为 coverage-only zero-edit owner test，
  legacy command-stream `AsyncIterator` 不在 download-only corrective scope。

所有 accepted corrective finding 均已在 round-3 frozen target/fix 中闭合；没有未分类 residual。

## 5. WIP 保护、实施与外部权限边界

1. `dayu/investment/domain/source_sync.py` 必须保持 SHA-256
   `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`、1839 行、未跟踪；它不得进入
   accepted corrective-plan commit，也不得在 commit 成功前编辑、删除、覆盖或 stage。
2. 本地 accepted corrective-plan commit 成功后，才可由 Codex-internal implementation agent 恢复；首步必须
   重新核对 WIP SHA，再按 target 机械拆成 five-domain owners，不得重写或扩 allowlist。
3. implementation 后仍须由 DeepSeek Flash 与 MiMo 对同一冻结 diff 做相互独立的 code review；两路
   PASS/open0 之前不得进入 accepted slice commit。
4. 本 acceptance 不授权真实 provider、网络、付费模型、Broker、交易、真实资金或部署，也不授权 push、PR、
   merge、approve、mark-ready、外部 comment 或 issue 动作。

## 6. Intended accepted corrective-plan stage set

Controller 创建本地 accepted corrective-plan commit 时，只应 stage 以下十条路径：

1. `docs/plans/2026-08-10-investment-platform-restoration.md`
2. `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
3. `docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md`
4. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-deepseek.md`
5. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-mimo.md`
6. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-deepseek-flash.md`
7. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-mimo.md`
8. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-deepseek-flash.md`
9. `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-mimo.md`
10. `docs/reviews/plan-acceptance-20260812-slice-2.3-stream-domain-coverage-codex.md`

必须明确排除 `dayu/investment/domain/source_sync.py` 和任何 production/test/README/dependency/migration/CI
implementation path。建议 commit message：
`gateflow: accept corrective plan for slice-2.3-source-connectors-health`。是否 stage/commit 由 Controller 在
重新核验 branch、HEAD、index、closure SHA 与 exact path set 后执行；本 acceptance 不声称 commit 已完成。

## 7. 结论

`ACCEPTED`。Round-3 DeepSeek Flash 与 MiMo 对同一 corrective target/fix/WIP bytes 均为
`PASS / open H/M/L=0/0/0`。当前 gate 是 `local accepted corrective-plan commit next`；implementation 只有在
该本地 commit 成功后才能恢复。
