# Slice 1.1 doc-owner erratum acceptance

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Controller**：Codex
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **Open H/M/L**：`0/0/0`
- **External actions**：无

## Accepted change

S11-CTRL-08 只把 `dayu/README.md` 与 `tests/README.md` 纳入 Slice 1.1 allowlist：

1. `dayu/README.md` 必须把 investment owner 图更新为 pure
   `domain/config/composition` 与 infrastructure `storage`，只对 pure 层禁止 ORM，
   并登记 Alembic、13 表与 RLS 的阅读顺序。
2. `tests/README.md` 必须把 architecture guard 更新为 pure/storage 相对路径规则，
   登记 unit migration lane 与真实 PostgreSQL 16 integration lane，并写明不得用
   SQLite/fake 代替、Docker fixture 必须按 owner 标签清理。

不得借此改写其它 package/test 历史，也不得把 future slice、live data、模型或 broker
能力标为已实现。

## Review evidence

- Terra：`docs/reviews/plan-review-20260810-slice-1.1-doc-owner-terra.md`，
  **PASS**，open H/M/L=`0/0/0`。
- MiM Native：`docs/reviews/plan-review-20260810-slice-1.1-doc-owner-mimo-native.md`，
  **PASS**，open H/M/L=`0/0/0`。

两路均确认 allowlist 增量必要、最小且充分，implementation WIP 在 acceptance 前保持
冻结；没有 finding 或 open question。

## Controller closure

本 erratum accepted。Slice 1.1 worker 可同步两份 README、更新 implementation
artifact 并重跑最终 deterministic gates；完成后必须进入 Terra + MiM Native 双路
code review。schema、migration、测试语义、37-slice DAG 及 live authorization 均未改变。
