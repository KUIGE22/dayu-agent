# Slice 1.1 package/test README owner erratum

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Controller**：Codex
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED**
- **Implementation state**：production/tests/migration READY，但 code review 未启动
- **External actions**：无

## Stop evidence

DeepSeek Flash 完成 Slice 1.1 后严格回滚了白名单外 `dayu/README.md` 修改并报告
plan gap。直接证据：

1. `dayu/README.md` §3.9 仍写 `dayu.investment` “三个模块均不导入 ORM”，且 owner
   图只列 domain/config/composition；当前 accepted design 已新增 storage SQL infra。
2. `tests/README.md` 仍写 architecture guard 对全部 investment package 禁 ORM，
   且只登记骨架测试；当前 guard 已按 pure/storage 分组，并新增真实 PG16 migration
   integration lane。
3. master plan §9 明确要求 `dayu/README.md` 维护包级阅读顺序、`tests/README.md`
   维护 unit/integration lane，因此延后会让本 slice 在 code review 时违反文档 hard
   gate；两文件又不在原 Slice 1.1 allowlist，worker 不能自行修改。

## Controller decision

问题 **ACCEPTED / PLAN GAP**。最小修复只增加 S11-CTRL-08 与两份 README allowlist：

- `dayu/README.md` 更新 pure/storage owner 与 Alembic/RLS 阅读顺序；
- `tests/README.md` 更新 path-based guard，并登记 unit 与真实 PG16 integration lane。

不修改 schema、migration、代码、测试、37-slice DAG、外部动作或 live gate。Terra 与
MiM Native 必须只读 plan re-review，任一路 open H/M/L 非零则 implementation 继续
冻结且不得启动 code review。

## Dual plan re-review closure

- Terra：`docs/reviews/plan-review-20260810-slice-1.1-doc-owner-terra.md`，
  **PASS**，open H/M/L=`0/0/0`。
- MiM Native：`docs/reviews/plan-review-20260810-slice-1.1-doc-owner-mimo-native.md`，
  **PASS**，open H/M/L=`0/0/0`。
- Controller：S11-CTRL-08 与两项 README allowlist 增量 accepted；本 plan gap
  CLOSED。只解冻 README 同步、最终验证与 Slice 1.1 code-review gate，未授权 live、
  push、PR 或后续 slice 行为。
