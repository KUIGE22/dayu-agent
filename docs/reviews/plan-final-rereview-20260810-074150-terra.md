# 投资平台恢复计划最终 closure-only 复审（Terra）

- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **审查性质**：只读、closure-only；仅验证上一轮 Terra 唯一 Open M 是否被完整关闭，并确认原 findings 没有回归。
- **本地审查时间**：2026-08-10T07:42:12+08:00
- **已完整读取的材料**：根 `AGENTS.md`、Controller 修复 `docs/reviews/plan-fix-20260810-072408-codex.md`、上一轮 Terra FAIL `docs/reviews/plan-rereview-20260810-073659-terra.md`、MiMo PASS `docs/reviews/plan-rereview-20260810-073659-mimo-native.md`、目标计划及初审 findings。
- **未执行的动作**：未修改目标计划、代码、测试、既有 artifact；未执行测试、提交、推送或外部动作。

## 结论

**PASS**。唯一 Open M 已按其根因完整关闭，且未发现 Terra T-01--T-08 或 MiMo M-001--M-013 的 material regression。

**Open 汇总：H=0，M=0，L=0。**

## 已验证的关键假设

1. **0.2 仅是 settings/composition contract**：计划 Slice 0.2 的完成条件明确限定为 strict settings、`PlatformCompositionProviderProtocol`、空/禁用状态和 startup 注入点；并明确禁止导入或构造尚不存在的 PG、Fins、job repository（计划:337-341）。因此它不再承担任何真实 repository/Service 装配，也不需要 future-slice import 或占位 adapter。
2. **1.2 是 PG 后首次实际装配**：DAG 固定 `0.1 -> 0.2 -> 1.1 -> 1.2`（计划:301-306）；Slice 1.1 先交付 engine/session、identity/source schema、RLS 与 migration（计划:345-351），而 Slice 1.2 才首次把本 slice 的 identity/source PostgreSQL repositories 和窄 Service Protocol 装入 production provider，并以 black-box test 排除 placeholder/future import（计划:353-358）。
3. **2.1 独立装配 job store**：DAG 为 `0.2 + 1.1 -> 2.1 -> 2.2`（计划:305），Slice 2.1 明确将 PG job store 与 job service 加入既有 provider，同时禁止启动 worker/scheduler 或注册业务 handler（计划:383-389）。其所需的组合契约由 0.2 提供、PG engine/schema/migration 能力由 1.1 提供；不依赖尚未存在的 identity repository 实现。
4. **2.2 才提供 worker/scheduler**：Slice 2.2 位于 2.1 后，专门负责 scheduler、worker process 与 Redis wake-up，并将 worker claim 和 handler receipt 定义为调用路径（计划:391-396）。这使 2.3 不再需要自行发明 registry 或 worker 生命周期。
5. **2.3 前置条件完整且无 future placeholder**：DAG 显式为 `1.2 + 1.3 + 1.4 + 2.2 -> 2.3`（计划:306），完全覆盖上一轮指出的 repository/service、Fins locator/S3 composition、job contract/worker registry 前置产物。其完成条件中的 production handler registration 与 receipt 绑定 Fins locator、PG job attempt（计划:398-403）均已分别由该四个 predecessor 交付；不需要新增 future placeholder。
6. **37 项机械计数一致**：计划声明 37 个 slices（计划:297）；对 `^#### Slice ` 的机械计数为 37，且 0.1--8.4 各编号恰好一次。分 Phase 计数为 `2 + 5 + 3 + 3 + 5 + 5 + 4 + 6 + 4 = 37`。
7. **原 findings 无回归**：计划继续保留并可定位初审关闭所需的 workspace migration（1.5）、真实组合根（1.4/2.2/7.x/8.2）、tenant/RLS（0.1/1.1/§6.2）、Fins-owned EvidenceLocator（1.3/§6.3）、Host/PG owner 与 recovery（§6.1/2.1）、point-in-time（§6.5/5.3--5.4）、执行幂等与 kill switch（§6.4/5.5/6.1--6.2）、integration lane（§8.0/§9）及 live admission gate（8.4）。此次职责移动只收缩 0.2、明确 1.2/2.1/2.2/2.3，未删除或削弱这些约束。

## Findings

无。上一轮的唯一 finding 已闭合：切片 DAG 现在与各自 completion condition 的实际依赖一致，实施 Agent 按 accepted predecessor 执行时不必越过 allowlist 或引入临时 seam。

## Open Questions

无。真实 Broker 的 vendor、账户和市场仍由 Slice 8.4 的外部授权 gate 决定，不属于 deterministic plan closure 的未收敛项。

## Residual Risks 与建议跟踪去向

| 风险 | 状态 | 建议 destination |
| --- | --- | --- |
| 供应商变化、对象存储/Redis 故障、模型偏差与 Broker 乱序 | 非 plan closure 缺口 | 计划 §12 与对应 slice 的 integration/acceptance |
| 真实券商接入和凭据 | 明确外部授权 gate | Slice 8.4 独立 plan review 与用户授权 |

## 最终复审结论

**pass**。Open **H=0 / M=0 / L=0**；计划可进入 implementation gate。
