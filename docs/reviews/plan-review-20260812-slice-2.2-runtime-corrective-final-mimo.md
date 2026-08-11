# Slice 2.2 Scheduler/Worker/Redis Runtime Contract Final Closure-Only Corrective Re-review

- **状态**: `FINAL CLOSURE-ONLY CORRECTIVE RE-REVIEW`
- **目标计划**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` (SHA-256: `ead24a7e264ee5f77b3070e8a531d1c0be3ad5c7716619d4563baf5439d12a63`)
- **修复文档**: `docs/reviews/plan-fix-20260812-slice-2.2-runtime-contract-codex.md` (SHA-256: `61b41b4e18bb0fe01dcaf92ab0251cfc18f1dd64b4d5ebe04455a085be388603`)
- **复核范围**: 首轮 DeepSeek L1/L2/L3、Controller M1/M2/M3/L1、MiMo 首轮可生成性质疑的裁决闭合验证；whole-plan blocking regression scan。
- **关键约束**: 本轮是实现冻结前的 plan review；当前代码和命名测试尚未实现是预期交付工作，不得仅以“代码不存在/测试未落盘”报 finding；只报告计划自身不充分、矛盾或无法生成。

## 1. Assumptions Tested

1. 计划已充分整合 fix document 中所有修复，覆盖首轮全部质疑点。
2. 计划自身没有内部矛盾、不充分或无法生成的描述。
3. 计划足够具体，可安全交给 implementation agent 执行。
4. 所有 open findings 已在计划或 fix document 中闭合。

## 2. Finding 映射与闭合验证

### 2.1 首轮质疑点闭合检查

| 质疑领域 | 首轮来源 | 修复状态 | 验证证据 |
| --- | --- | --- | --- |
| **allowlist/DAG与exact touchpoints** | Controller M-1 | CLOSED | §3 精确允许文件列表与依赖 DAG；§2.1 S22-CTRL-009 详细定义 allowlist 与修改点；§10 测试覆盖 `test_layers_do_not_import_forbidden_modules`。 |
| **ScheduleReservationBatch exact error** | Controller M-2 | CLOSED | §2.1 S22-CTRL-009 明确 `__post_init__` 抛出 `ScheduleInvariantError("schedule_batch_duplicate_scheduled_for")`；§10 测试 `test_schedule_reservation_batch_rejects_duplicate_scheduled_for_before_postgres`。 |
| **cron registration + activation no-set-state + due no-reserve + scheduler exit1 + real Store preparation** | Controller M-3 | CLOSED | §2.1 S22-CTRL-009 详细描述 registration fixed seed probe、activation/due exhaustion 处理、scheduler exit1；§6 提到 real Store preparation；§10 四个对应测试名称。 |
| **governance集中构造/cardinality/order/duplicate/action matrix/global invariant/repository-vs-unclassified exception** | DeepSeek L1/L2/L3, Controller M-2 | CLOSED | §2.1 S22-CTRL-009 详细 governance result identity 与验证逻辑；§10 七个 governance 测试覆盖 identity、cardinality、order、duplicate、action matrix、global invariant、repository failure、unclassified exception；§12 STOP conditions 包含 governance 相关。 |
| **Redis Worker-owned pure types/settings-before-import/query/fragment/surrogate/runtime TypeError/ValueError** | DeepSeek L-3, Controller L-1 | CLOSED | §2.1 S22-CTRL-009 详细 Redis pure protocol 导入边界、URL/query/fragment 处理、surrogate/TypeError/ValueError 处理；§10 七个 Redis 相关测试；§12 STOP conditions 包含 Redis 相关。 |

### 2.2 无新增 finding

经过对 target plan 和 fix document 的逐节审查，未发现计划自身存在不充分、矛盾或无法生成的描述。所有首轮质疑点均已闭合，且有明确的测试覆盖和 STOP 条件。

## 3. Open Questions

无。

## 4. Residual Risks (from §13)

计划已明确列出 residual risks，包括：
- Redis hint 天然可丢、重复、乱序。
- Host cancel 取决于 provider/Agent cooperative boundary。
- START_REQUIRED→Host reserved ensure 的跨库 TOCTOU。
- cooperative grace 后仍运行的非协作 handler。
- heartbeat 不加 jitter 导致的同相多 worker PG 瞬时峰值。
- 滚动部署期间不同 scheduler 进程的 execution capability 短暂不一致。
- 一进程一 tenant 是当前 selector 安全收缩，不是认证。
- production source schedule/handler、source health 与 subscription 映射属于 Slice2.3。

这些 residual risks 已在计划中明确记录，且不阻塞 plan review PASS。

## 5. Final Plan Review Conclusion

**PASS / open H/M/L = 0/0/0**

计划已充分整合所有修复，覆盖首轮全部质疑点，无内部矛盾或不充分描述，足够具体可交付 implementation agent。所有 open findings 已闭合。

**Reviewed target SHA-256**: `ead24a7e264ee5f77b3070e8a531d1c0be3ad5c7716619d4563baf5439d12a63`
**Fix document SHA-256**: `61b41b4e18bb0fe01dcaf92ab0251cfc18f1dd64b4d5ebe04455a085be388603`
