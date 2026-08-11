# Slice 2.2 activation / availability corrective plan acceptance

- **时间**：2026-08-12 05:17:53 CST
- **状态**：`ACCEPTED / DEEPSEEK + MIMO FINAL PLAN RE-REVIEW PASS`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **经独立复审核验的语义快照 SHA-256**：`cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`
- **状态、审核来源与模型路由闭环后的目标文件 SHA-256**：`c953083c3c6d5db41e349537a8ffb31947e48f46e26d618ae76c9e1fcca4d2c7`
- **经独立复审核验的Controller fix SHA-256**：`e5846a6d0c50abc949c6e581dbfea723155a86d65d87058acf8e5ffaeeba1a76`
- **closure与模型路由写回后的Controller fix SHA-256**：`a146d0feda489124c13f8cbb4bfec6cc6445a28dc0100197bb016c832d731eb2`
- **此前 accepted plan baseline**：`2dcba107b20730a6ab40483f9b8a04c9320f7602`
- **模型路由**：Codex内部模型实施；DeepSeek + MiMo独立双审；Terra只作架构补充；DeepSeek Flash不再写入。

## 1. 最终审核结论

| 审核方 | Artifact | 结论 | Open H/M/L |
| --- | --- | --- | --- |
| DeepSeek | `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-deepseek.md` | `PASS` | `0/0/0` |
| MiMo | `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-mimo.md` | `PASS` | `0/0/0` |
| Terra（补充架构复审） | `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-terra.md` | `PASS` | `0/0/0` |

DeepSeek 与 MiMo 均独立读取并核验同一语义快照 SHA-256；MiMo另读取DeepSeek结果但重新逐项验证，不把其结论当作证据替代。Terra首轮 `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md` 的结论为 `FAIL / 0/1/1`，对应两项finding已修复并由三路最终复审确认闭合。

## 2. Finding closure

以下九项均为 `CLOSED`：

1. `TERRA-S22-APC-001`：row-lock后同一conditional DML与同一`clock_timestamp()`完成future guard、CAS与observation。
2. `TERRA-S22-APC-002`：每次public activate/re-enable总计三次CAS，包含首次且不自动rebase。
3. `CTRL-S22-APC-003`：scan-limit batch显式携带expected/resulting cursor与resulting state。
4. `CTRL-S22-APC-004`：transition result携带before/after/request/candidate并执行closed action matrix。
5. `CTRL-S22-APC-005`：MATERIALIZING只走`enqueue_committed_schedule_occurrence`。
6. `CTRL-S22-APC-006`：negative availability只产生本地typed no-work且零mutation，不升级为全局skip/disable。
7. `CTRL-S22-APC-007`：MATERIALIZING优先，PENDING使用bounded replay page与独立keyset cursor。
8. `CTRL-S22-APC-008`：due scan使用独立bounded cursor/page/result并跨页保证fairness。
9. `CTRL-S22-APC-009`：两个typed cursor均在gateway返回后、首个后续await前同步赋值且不得混用。

当前corrective plan open H/M/L=`0/0/0`，没有遗留plan blocker。

## 3. Controller裁决与实施边界

Controller接受该corrective plan。流程固定为：

1. 先只提交本次plan/fix/review/acceptance文档；不得夹带任何冻结的implementation WIP。
2. accepted plan erratum本地提交成功后，由Codex内部模型从冻结点恢复实施；DeepSeek Flash窗口继续冻结且不得写入。
3. 恢复后先删除或修正WIP中的旧activation invariant、`if False`占位、disabled cursor旧语义与旧DTO/Protocol surface，再运行focused/static/真实PostgreSQL门禁。
4. 实施完成后必须由DeepSeek与MiMo进行两路独立code review；accepted finding修复后两路corrective re-review均open0才允许accepted implementation commit。Terra只作为补充架构审核，不替代最终双审。
5. 未授权live provider/model/broker、交易、push、PR或部署。

## 4. 本次accepted plan erratum提交路径

只允许以下七条路径：

- `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- `docs/reviews/plan-fix-20260812-slice-2.2-activation-pg-clock-codex.md`
- `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md`
- `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-terra.md`
- `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-deepseek.md`
- `docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-mimo.md`
- `docs/reviews/plan-acceptance-20260812-slice-2.2-activation-pg-clock-codex.md`

以下十三条implementation WIP必须保持unstaged并从本次提交排除：两份constraints、`pyproject.toml`、`config.py`、`domain/jobs.py`、`domain/schedules.py`、`storage/protocols.py`、`storage/postgres_jobs.py`、`storage/postgres_schedules.py`、migration `0004`，以及三份application/investment tests。

## 5. 结论

`ACCEPTED`。DeepSeek + MiMo final plan re-review均为`PASS / open H/M/L=0/0/0`；计划勘误可以形成独立本地accepted commit，随后恢复Slice 2.2实施。
