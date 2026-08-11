# Slice 2.1 Provider Mapping Allowlist Erratum — Controller Acceptance

- **Status**：`ACCEPTED / CORRECTIVE DUAL PLAN RE-REVIEW PASS`
- **Branch**：`codex/investment-platform`
- **Historical accepted plan commit**：`869e5c653ce9c64730ac8346a857a70b61d5a677`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Master**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **Controller artifacts**：
  - `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-allowlist-codex.md`
  - `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md`

## 1. Review chain

1. MiM initial：`docs/reviews/plan-review-20260811-192410-slice-2.1-provider-allowlist-mim.md`，PASS/open0，但漏检旧 private helper 测试耦合。
2. Spark initial：`docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-spark.md`，FAIL/open H=1；H-001 被 Controller 接受。
3. Controller corrective：把授权精确扩到同一 PG16 文件的第二个既有测试、模块 docstring 与单个 unused import；禁止 production compatibility helper。
4. Spark early corrective：`docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-spark.md`，因把 plan gate 误当 implementation gate而 FAIL；该 gate error 被拒绝，保留历史。
5. Final corrective reviews：
   - `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-mim.md`：PASS/open H/M/L=`0/0/0`；
   - `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-closure-spark.md`：PASS/open H/M/L=`0/0/0`。

## 2. Accepted contract

Implementation 只可在原 Slice 2.1 allowlist 基础上，对 `tests/integration/investment/test_identity_repositories_postgres.py` 做以下四类变更：

1. mapping 测试改名并锁定 exact two-service mapping、真实 `JobService` 与 `platform_service_name`；
2. placeholder 测试删除已不存在旧 helper 的 lookup/counter/monkeypatch/assert，同时保留 DSN、显式 provider、PG 零 side-effect 证明；
3. 模块 docstring 同步为 two-service contract；
4. 删除由第 2 项产生的单个 unused `PlatformOwnedLifecycleProtocol` import。

不得改其它测试/fixture/helper/import，禁止 production compatibility helper。Provider mapping、session-factory-only、Host reader 注入时机、identity shared-engine lifecycle、Host/PG owner DAG 与完整 PG16 lane全部保持。

## 3. Freeze and scope evidence

- 原 plan-fix 的 20 个 production/test WIP SHA-256 在 initial/corrective plan-fix 前后为 `20/20` 完全一致。
- Plan-fix 阶段未修改 production/tests/README，未运行 live/network/paid action。
- `git diff --check`、新文档 whitespace/final LF 与路径审计通过。

## 4. Controller decision

所有 material plan findings 已关闭，Controller open H/M/L=`0/0/0`。Slice 2.1 implementation WIP freeze 解除，允许 Flash 仅按 accepted exact allowlist 恢复实现与验证。

本 acceptance 只授权本地 implementation gate；不授权 push、PR、deploy、live、network 或 paid action。
