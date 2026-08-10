# Plan Review — Slice 1.1 Doc-Owner Erratum

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` S11-CTRL-08 + `docs/reviews/plan-fix-20260810-slice-1.1-doc-owner-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-review-20260810-slice-1.1-doc-owner-mimo-native.md`
- Focus：allowlist/docs 职责是否不足或扩大范围；existing implementation WIP 冻结

## Assumptions Tested

1. `dayu/README.md` 和 `tests/README.md` 需要被加入 Slice 1.1 allowlist 才能更新。
2. S11-CTRL-08 的更新范围是精确的，不会扩大到 Slice 1.1 之外。
3. Implementation WIP 冻结语义正确——实现已完成但 code review 被阻塞。

## Verification

### Allowlist 必要性

Plan §9（line 734）明确要求："文档职责也是 hard gate：`dayu/README.md` 维护包级阅读顺序；`tests/README.md` 维护 unit/integration/nightly/acceptance lane。不得把实现契约只写在 plan/review artifact。"

当前 Slice 1.1 allowlist（lines 403-414）包含 `dayu/README.md` 和 `tests/README.md`。✅ 已在 allowlist 中。

`dayu/README.md` §3.9 当前文本（line 388）声称 "三个模块均不导入 ORM"——这在 Slice 1.1 新增 `storage/` 后已过时。`tests/README.md` line 45 声称 architecture guard "不得导入任何上层包或 ORM/Web 框架"——同样过时。两者都是 §9 hard gate 要求同步的文档。✅ allowlist 添加必要。

### Scope 精确性

S11-CTRL-08 指定的更新内容：

| 文件 | 更新范围 | 是否超出 Slice 1.1 |
|------|----------|-------------------|
| `dayu/README.md` §3.9 | owner 图更新为 pure `domain/config/composition` + infra `storage`；明确只有 pure 层禁 ORM；登记 Alembic/13表/RLS 阅读顺序 | 否——精确对应 S11-CTRL-02/03/04 的新增内容 |
| `tests/README.md` | architecture guard 更新为 pure/storage 相对路径规则；登记 unit lane 与真实 PG16 `integration` lane；禁止 SQLite/fake；Docker owner cleanup 命令 | 否——精确对应 S11-CTRL-02/06/07 的新增内容 |

明确排除："不得改写其它包/测试历史或把 live/data/model/broker 标为已实现。" ✅ Scope 精确，未扩大。

### Implementation WIP 冻结

Fix document 声明："Implementation state：production/tests/migration READY，但 code review 未启动" 与 "code/tests/migration 继续冻结，双路 plan re-review PASS/open0 前不启动 code review"。

Plan revision changelog（line 65-71）确认："implementation 已完成 production/unit/PG16 gates，但严格未越界修改 `dayu/README.md`...code/tests/migration 继续冻结"。

✅ 冻结语义正确：实现已完成但被文档 gap 阻塞，erratum 审批通过后才能启动 code review。

### Staleness Verification

| 文档位置 | 当前文本 | 是否过时 | S11-CTRL-08 修正 |
|----------|----------|----------|-----------------|
| `dayu/README.md` line 388 | "三个模块均不导入 ORM" | 是——Slice 1.1 新增 `storage/` 导入 SQLAlchemy | 更新为 pure/storage 分组 |
| `dayu/README.md` line 376-384 | Owner 图只列 domain/config/composition | 是——Slice 1.1 新增 storage | 新增 infra `storage` |
| `tests/README.md` line 45 | "不得导入任何上层包或 ORM/Web 框架" | 是——guard 已按 pure/storage 分组 | 更新为相对路径规则 |
| `tests/README.md` line 39-40 | integration 只写"端到端集成测试" | 是——新增 PG16 migration integration lane | 登记具体 integration 文件与 marker |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `dayu/investment/README.md` 已在 Slice 1.1 allowlist 中，需由 implementation worker 同步更新（S11-CTRL-08 未显式提及但 §9 hard gate 要求）。Plan 的 Slice 1.1 allowlist 已包含该文件，implementation worker 应能自行识别。
- 两份 README 更新后，需要在 code review 中验证文本与代码一致——这是 code review 阶段的职责，不在 plan erratum 范围内。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

S11-CTRL-08 精确闭合了 documentation hard gap：`dayu/README.md` 和 `tests/README.md` 的 stale 文本与 Slice 1.1 新增的 storage/RLS/integration 内容不一致。Allowlist 添加必要且范围精确，未扩大到 Slice 1.1 之外。Implementation WIP 冻结语义正确——实现已完成但 code review 被文档 gap 阻塞。明确排除了其它包/测试历史的修改。允许进入 erratum accepted。
