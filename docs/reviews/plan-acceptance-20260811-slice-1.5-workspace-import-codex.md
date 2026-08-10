# Slice 1.5 old-workspace import plan acceptance

- **Work unit**：Investment Platform Restoration
- **Gate**：Slice 1.5 plan closure
- **Branch**：`codex/investment-platform`
- **Baseline**：`58b7dd28db6183f29caaac337b09dffc3db80a76`
- **Status**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **Target plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`

## Decision

Slice 1.5 的旧 workspace 显式导入计划已 code-generation-ready。Controller 接受并修复
Terra initial TERRA-S15-001..004、MiM Native M01..M13 中所有 material observations，
并在 final review 中接受、修复 `TERRA-S15-FINAL-001`。最终契约保持旧 workspace
identity、source definitions 与 research bundle locator/hash 的完整导入目标，没有把
locator延期、复制 Host/Fins 原始字节、猜测市场字段或引入第二 transaction owner。

`TERRA-S15-FINAL-001` 的最终语义边界为：bundle descriptor
`research_target.company` 是公司名称；typed owner closure 只暴露
`target_company_name` 并与 `CompanyMeta.company_name` exact。legacy company ID 不进入
closure/descriptor，只由 strict operator manifest 与 Fins inventory 的 raw byte-exact
gate 唯一证明。

## Review chain

- Initial Terra：
  `docs/reviews/plan-review-20260811-slice-1.5-workspace-import-terra.md`，
  FAIL，TERRA-S15-001..004。
- Initial MiM Native：
  `docs/reviews/plan-review-20260811-071328-slice-1.5-workspace-import-mim-native.md`，
  PASS-WITH-RISKS，正文 M01..M13。
- Controller fix：
  `docs/reviews/plan-fix-20260811-slice-1.5-workspace-import-codex.md`。
- Final Terra：
  `docs/reviews/plan-final-rereview-20260811-slice-1.5-workspace-import-terra.md`，
  FAIL，`TERRA-S15-FINAL-001`。
- Final MiM Native：
  `docs/reviews/plan-final-rereview-20260811-slice-1.5-workspace-import-mim-native.md`，
  PASS，open H/M/L=`0/0/0`。
- Final closure Terra：
  `docs/reviews/plan-final-closure-rereview-20260811-slice-1.5-workspace-import-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- Final closure MiM Native：
  `docs/reviews/plan-final-closure-rereview-20260811-slice-1.5-workspace-import-mim-native.md`，
  PASS，open H/M/L=`0/0/0`。

## Accepted implementation boundary

Implementation 必须逐字遵守 plan 的 `S15-CTRL-01..14`：typed strict bundle closure、
company/source no-create repositories、strict operator manifest、default-tenant bootstrap、
`0002_workspace_import` 两表及 RLS/grants/downgrade、transaction-scoped advisory lock、
唯一 PostgreSQL transaction owner、exact no-op/drift/race/rollback、normal-init隔离以及真实
PostgreSQL 16 integration gates。未列入 allowlist 的 production/test 文件不得修改；任何
需要猜 MIC/currency/type、读取/复制 legacy raw bytes、放宽 tenant、使用 fake PG 代替真实
RLS/concurrency 或修改白名单外 owner 的情况必须立即停报。

## Closure

- Controller accepted findings：全部 FIXED/CLOSED。
- Controller open findings：H/M/L=`0/0/0`。
- Terra final closure：PASS，open `0/0/0`。
- MiM Native final closure：PASS，open `0/0/0`。
- Production/tests/README：本 plan gate 未修改。
- External actions：未运行 live/network/model/broker，未 push/PR。

Slice 1.5 解除计划冻结，获准进入 implementation gate。该授权不包含付费模型、网络、
真实 broker、生产部署或任何 live external action。
