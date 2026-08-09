# 投资平台恢复计划 accepted closure

- **Plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **基线**：`d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **分支**：`codex/investment-platform`
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **切片**：37

## Review chain

1. Terra初审：`docs/reviews/plan-review-20260810-072034-terra.md`，FAIL，6H/2M。
2. MiM初审：`docs/reviews/plan-review-20260810-072130-mimo-native.md`，PASS-WITH-RISKS，13 observations。
3. Controller裁决/修复：`docs/reviews/plan-fix-20260810-072408-codex.md`。
4. Terra第一轮复审：`docs/reviews/plan-rereview-20260810-073659-terra.md`，FAIL，open 0/1/0。
5. MiM第一轮复审：`docs/reviews/plan-rereview-20260810-073659-mimo-native.md`，PASS，open 0/0/0。
6. Controller修复唯一DAG/composition观察。
7. Terra最终复审：`docs/reviews/plan-final-rereview-20260810-074150-terra.md`，PASS，open 0/0/0。
8. MiM最终复审：`docs/reviews/plan-final-rereview-20260810-074150-mimo-native.md`，PASS，open 0/0/0。

## Accepted contract

- 用户的11组原始功能全部是hard scope，并延伸为信息采集、证据、研究、组合优化、风险、审批、Paper执行、监控和归因闭环。
- 平台目标是提高风险调整后的决策质量和执行纪律，不承诺收益。
- UI只调用Service；Host负责通用持久任务；Agent/LLM只产候选；Fins保持材料唯一owner；确定性Service独占持久化、风险与交易执行。
- Tenant/RLS、Fins locator、Host/PG恢复、point-in-time backtest、订单幂等、kill switch、backup/deploy均已在具体slice中冻结。
- 37 slices有显式DAG、composition roots、integration lanes、stop conditions与逐slice review/accepted commit要求。
- Paper Broker属于deterministic scope；真实Broker/账户/credential/live/policy_auto必须在Slice 8.4获得独立plan review与用户外部授权。

## Gate result

所有plan findings与observations已CLOSED，Controller open H/M/L=0/0/0。计划可以从Slice 0.1开始implementation；不得跳过predecessor、review或外部授权gate。
