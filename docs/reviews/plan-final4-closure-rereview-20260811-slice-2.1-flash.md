# Plan Final4 Closure Re-Review：Slice 2.1 durable job queue（DeepSeek Flash）

- **Gate**：final closure-only re-review（FINAL4 / 独立 reviewer）
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **基线**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`（branch `codex/investment-platform`）
- **裁决输入**：`S21-CTRL-FINAL4-001..002`（`docs/reviews/plan-controller-final3-rereview-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`）
- **修复输入**：`docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`
- **结论**：**PASS / OPEN H/M/L = 0/0/0**
- **本次写入**：仅本 artifact。未运行 pytest/pyright/Ruff/Docker/PG；未 commit/push/PR/live；未读本轮另一 reviewer（MiM）artifact；未读任何 production/test/README 之外的改动。

## 1. 方法与范围

closure-only re-review：只裁决 `S21-CTRL-FINAL4-001..002` 是否在 target plan 中精确闭合，并确认
bounded regression clear（FINAL2-001..007 / FINAL3-001..005 不回退）。不做任何范围扩展，不新增
审计维度，不审计 Slice 2.2/2.3、master 其它区域或另一 reviewer 产物。

## 2. 机械只读审计

| 检查项 | 结果 |
| --- | --- |
| `git diff --check` | 通过（exit 0），无 whitespace 错误 |
| 目标计划 / master / fix artifact 尾随空白 | 无（逐文件脚本核对） |
| 目标计划 / master / fix artifact final LF | 齐全（逐文件脚本核对） |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` 改动范围 | 严格限于 Slice 2.1 五行（Allowed/API/Invariants/Completion/Tests），未触碰 Slice 2.2/2.3 或其它区域 |
| Terra fix write set | 仅 target plan 与本 fix artifact，与 fix 文档声明一致 |

## 3. S21-CTRL-FINAL4-001..002 逐项裁决

| Finding | 状态 | 独立证据 |
| --- | --- | --- |
| 001（Medium，§7D recovery branch 与 §3.2 冲突） | **CLOSED** | §3.2（plan L292）与 §7D（plan L388）的 `JobService.recover` 算法文本**逐字一致**（脚本比对 True）：sorted expired committed correlations → 每条 correlation lookup → Host read → strict mapping → reconcile；仅 `NO_HOST_RUN` decision 以该 observation 的 `sha256` 进入 targeted `recover_agent_run_after_no_host`；`HOST_ACTIVE_WAIT`、任一 terminal、stale、invariant decision 均不得进入任一 recover primitive；枚举完成后最后且仅最后调用一次 generic `job_store.recover(scope)`。旧批次级条件（"仅 NO_HOST_RUN 后 generic / 不得 HOST_ACTIVE_WAIT 后 generic"）已无任何残留（全文搜索无匹配）。 |
| 002（Low，16 个 mandatory named tests 认领） | **CLOSED** | Controller 指定的 16 个测试名按 A/B/C/D = 1/5/3/7 全部补入 §7 对应 implementation slice 的 Tests 清单，16/16 逐一 FOUND：A（1）`test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write`（plan L385）；B（5）disabled definition、cross-tenant reads not found、RLS setting leak、grant matrix、upgrade/downgrade（plan L386）；C（3）claim empty、ready deadline、complete tiebreak（plan L387）；D（7）missing replay、host failed/unsettled、host cancelled、correlation invariant、recover stable order、targeted isolation、zero-mutation（plan L388）。无改名、无缺失、未改 §8 算法与 completion gate。 |

## 4. Bounded regression clear

- FINAL2-001..007（owner/DAG、correlation lookup、deadline/correlation_missing、versioned lease、
  UNSETTLED 映射、generic receipt、recovery result）与 FINAL3-001..005（correlation-safe targeted
  recover、complete tiebreak、reserved ID validator、ready deadline、master 五行）在 target plan 中
  均保持闭合，未见回退。
- 未引入 re-export、wrapper、第二 contract owner、Host storage import、业务 handler/worker。
- STOP 条件（plan §9）与残余风险归属（TOCTOU 归 Slice 2.2）未改变。

## 5. Open questions 与 residual

- **Blocking open questions**：无。
- **Residual**：`START_REQUIRED` 后跨 lease 的 read-to-entry TOCTOU 为 plan 明示接受，归属
  Slice 2.2；本 gate 未运行 pytest/pyright/PG16 integration，属后续 implementation gate 计划内验证。
- **下一 gate**：open H/M/L 已归零；可由 Controller 接受计划并进入 implementation gate。

## 6. 收尾审计

本 artifact 已通过 whitespace（无尾随空白）与 final LF 检查，`git diff --check` 通过；未修改
target、master、production、tests、README 或其它 review artifact。
