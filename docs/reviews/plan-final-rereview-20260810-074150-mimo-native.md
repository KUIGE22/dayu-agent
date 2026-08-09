# 投资平台恢复计划最终复审（MiMo Native — Final Closure）

- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md`（最终修订）
- **审查基线**：`d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **审查分支**：`codex/investment-platform`
- **审查 gate**：最终 closure re-review（第三轮）
- **前置材料**：根 `AGENTS.md`、Controller 修复 `docs/reviews/plan-fix-20260810-072408-codex.md`、Terra 第一轮复审 `docs/reviews/plan-rereview-20260810-073659-terra.md`（FAIL, M=1）、MiM 第一轮复审 `docs/reviews/plan-rereview-20260810-073659-mimo-native.md`（PASS, M=0）
- **本地审查时间**：2026-08-10T07:41:50+08:00
- **范围**：仅判断最终修订计划是否可安全交给 code-generation agent；重点验证 Terra 唯一 open M（DAG/组合根）修复闭合；逐项确认 37 slices 与全部初审 findings 无回归。未修改目标计划、生产代码、测试、README，也未执行 commit/push/PR。

## 审查结论

**PASS**。Open H/M/L = 0。

Controller 已关闭 Terra 第一轮复审唯一 open finding（M-01，DAG/组合根）：0.2 收窄为纯 settings/composition contract，1.2 首次 PG 装配，2.1 job 装配，2.3 显式依赖 1.2/1.3/1.4/2.2。37 slices 计数一致；Terra T-01 至 T-08 与 MiM M-001 至 M-013 全部闭合且无回归。计划现在是 code-generation-ready。

## 1. 唯一 open M 的 DAG/组合根修复验证

### 1.1 问题回顾

Terra 第一轮复审 Finding 1（M）：0.2 在 PG repositories 存在前承担真实 repository/Service bundle 装配；2.3 在 job/worker 前承担 handler/receipt 注册。这与"每个 slice 只能修改 allowlist、发现 gap 必须停报"的执行规则冲突。

### 1.2 Controller 修复

Controller 在 revision changelog（第 15 行）和 fix document（第 56–62 行）中明确：
- 0.2 收窄为 strict settings + composition provider contract
- 1.2 负责首次 PG repository/service 实际装配
- 2.1 负责 job store/service 装配
- 2.3 显式依赖 1.2/1.3/1.4/2.2，只有在全部 accepted 后才注册 source sync handler
- 相关 composition roots 和 black-box tests 随 owner slice 移动

### 1.3 计划文本逐项验证

| Slice | DAG 边 | 计划文本 evidence（行号） | 修复闭合 |
|---|---|---|---|
| 0.2 | `0.1 -> 0.2` | 第 335 行 Allowed：`dayu/investment/config.py`、`dayu/investment/composition.py`、`dayu/services/protocols.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`；第 341 行 Completion："只建立 strict settings、`PlatformCompositionProviderProtocol`、空/禁用状态和 startup 注入点；本 slice 不导入或构造尚不存在的 PG/Fins/job repository" | **CLOSED** |
| 1.2 | `0.2 -> 1.1 -> 1.2` | 第 357 行 Allowed：`dayu/investment/storage/protocols.py`、`dayu/investment/storage/postgres_identity.py`；第 357 行 Completion："首次 production provider 只装配本 slice 已经存在的 identity/source repositories 与窄 Service Protocol；不得预注册 jobs/evidence/portfolio 等 future-slice owner" | **CLOSED** |
| 2.1 | `0.2 + 1.1 -> 2.1` | 第 388 行 Completion："把 PG job store 与 job service 加入既有 platform provider；不启动 scheduler/worker，也不注册业务 handler" | **CLOSED** |
| 2.2 | `2.1 -> 2.2` | 第 392 行 Allowed：`dayu/host/scheduler.py`、`dayu/host/worker.py`、`dayu/cli/commands/platform.py` | **CLOSED** |
| 2.3 | `1.2 + 1.3 + 1.4 + 2.2 -> 2.3` | 第 397 行 Dependencies：依赖 1.2（identity/source repo）、1.3（Fins locator）、1.4（S3 blob）、2.2（scheduler/worker）；第 403 行 Completion："source health transition 和 deduped alert event 持久化；handler 在 production composition registry 注册，source sync receipt 绑定 Fins locator 与 PG job attempt" | **CLOSED** |

### 1.4 DAG 完整性

§8.0 DAG（第 301–319 行）中 2.3 的四条入边在第 307 行完整列出：`1.2 + 1.3 + 1.4 + 2.2 -> 2.3`。0.2 的 completion 已收窄为 pure contract，不存在与 PG/Fins/job repository 的前置冲突。DAG 无循环依赖；每条边对应真实的 schema/协议/composition 依赖。

**验证结果：唯一 open M 已完全闭合。**

## 2. 37 Slices 回归检查

§8 第 296 行声明 "本计划共 **37 个 slices**"。

| Phase | Slices | Count |
|---|---|---|
| 0 | 0.1, 0.2 | 2 |
| 1 | 1.1, 1.2, 1.3, 1.4, 1.5 | 5 |
| 2 | 2.1, 2.2, 2.3 | 3 |
| 3 | 3.1, 3.2, 3.3 | 3 |
| 4 | 4.1, 4.2, 4.3, 4.4, 4.5 | 5 |
| 5 | 5.1, 5.2, 5.3, 5.4, 5.5 | 5 |
| 6 | 6.1, 6.2, 6.3, 6.4 | 4 |
| 7 | 7.1, 7.2, 7.3, 7.4, 7.5, 7.6 | 6 |
| 8 | 8.1, 8.2, 8.3, 8.4 | 4 |
| **合计** | | **37** |

逐 Phase 直接标题计数确认：37 slices，编号 0.1 至 8.4 连续完整。无回归。

## 3. 原 findings 无回归检查

### 3.1 Terra T-01 至 T-08

| ID | 状态 | 回归检查 |
|---|---|---|
| T-01 workspace migration | CLOSED | Slice 1.5（第 371–376 行）保留完整 |
| T-02 composition roots | CLOSED | Slice 1.4/2.2/7.1–7.5/8.2 allowlist 保留完整 |
| T-03 tenant/RBAC | CLOSED | §6.2（第 163–167 行）+ Slice 0.1/1.1/7.1 保留完整 |
| T-04 Fins locator | CLOSED | §6.3（第 202–215 行）+ Slice 1.3 保留完整 |
| T-05 execution recovery | CLOSED | §6.4（第 237–255 行）+ Slice 5.5/6.1/6.2 保留完整 |
| T-06 point-in-time | CLOSED | §6.5（第 264–274 行）+ Slice 5.3/5.4 保留完整 |
| T-07 Host/PG recovery | CLOSED | §6.1（第 144–151 行）+ Slice 2.1 保留完整 |
| T-08 slice count | CLOSED | 37 slices 计数一致 |

### 3.2 MiM M-001 至 M-013

| ID | 状态 | 回归检查 |
|---|---|---|
| M-001 greenfield | REJECTED/CLOSED | §4.2 第 100 行 greenfield 声明保留完整 |
| M-002 缺依赖 | REJECTED/CLOSED | Slice 1.1/1.4/2.2/3.3 依赖锁定保留完整 |
| M-003 Fins boundary | DUPLICATE T-04/CLOSED | 与 T-04 同步 |
| M-004 DAG | CLOSED | §8.0 DAG + 第 320 行约束保留完整 |
| M-005 Claim trust | CLOSED | §6.2 confidence/expiry/conflict 规则保留完整 |
| M-006 look-ahead | DUPLICATE T-06/CLOSED | 与 T-06 同步 |
| M-007 kill switch | CLOSED | §6.4 kill switch 四级 scope + PG 真源保留完整 |
| M-008 tenant | CLOSED | §6.2 tenant-ready 从第一张私有表保留完整 |
| M-009 Redis degradation | CLOSED | §6.1 降级参数保留完整 |
| M-010 live broker | CLOSED | Slice 8.4 五步 sequence 保留完整 |
| M-011 slices 过多 | REJECTED/CLOSED | §8 第 296–297 行 rationale 保留完整 |
| M-012 integration lane | CLOSED | §8.0/§9 integration 定义保留完整 |
| M-013 README 职责 | CLOSED | §9 第 613 行 README 固定职责保留完整 |

## 4. 新 finding 检查

本次 closure 复审中未发现新 finding：

- **DAG 无循环依赖**：所有边方向一致，无环
- **Completion predicates 可满足**：每个 slice 的 completion 均可由其 predecessor 提供所需的 imports、schema、protocol、registry
- **Composition roots 显式列出**：0.2/1.4/2.2/7.2/7.4 的 allowlist 或 completion 中列出真实 composition root 文件
- **无 future-slice import**：0.2 明确不导入 PG/Fins/job repository；2.3 的 handler registration 由 1.2/1.3/1.4/2.2 提供
- **无占位 adapter 或兼容 facade**：所有 slice 要求真实实现或 production fail-fast

## 5. Assumptions Tested

1. **Terra M-01（唯一 open M）已闭合**：通过。0.2 收窄为 pure contract，1.2 首次 PG 装配，2.1 job 装配，2.3 四前置完整。直接证据在计划第 335–341、355–357、386–388、397–403 行。
2. **37 slices 无增减**：通过。逐 Phase 计数 2+5+3+3+5+5+4+6+4 = 37。
3. **Terra T-01 至 T-08 全部无回归**：通过。8 项 plan text 保留完整。
4. **MiM M-001 至 M-013 全部无回归**：通过。13 项 plan text 保留完整。
5. **无新 finding**：通过。DAG 无环、completion predicates 可满足、无 future-slice import。
6. **Open H/M/L = 0**：通过。

## 6. Residual Risks

| 风险 | 状态 | 建议 destination |
|---|---|---|
| 供应商/交易所格式变化 | 已列入 §12 | Source connector strict parser + adapter-specific review |
| pgvector 相似度误导 | 已列入 §12 | Evidence Service exact locator gate |
| 优化过拟合/数据偏差 | 已列入 §12 | Backtest walk-forward + Paper admission + operator review |
| 模型幻觉 | 已列入 §12 | Candidate staging + evidence closure + audit |
| Broker 事件乱序/重复 | 已列入 §12 | Execution reconciliation + idempotency |
| 自动策略失控 | 已列入 §12 | account/strategy authorization + kill switch |
| Redis/通知不可用 | 已列入 §12 | PostgreSQL truth + retry/outbox |
| 对象存储或 DB 灾难 | 已列入 §12 | checksummed backup/restore |
| 用户权限误配 | 已列入 §12 | permission matrix + audit + default deny |
| 实际收益未达预期 | 已列入 §12 | 不做收益承诺；风险调整指标 + 归因 |

所有 residual 在 §12 有 owner 和 destination。implementation 风险，不阻塞 PASS。

## 7. Open Questions

无。所有初审与复审 open questions 已在修订计划中收敛或合理推迟到 Slice 8.4（live broker 授权）。

## 8. Final Verdict

**PASS**。

修订计划通过最终 closure 复审。Controller 已关闭 Terra 第一轮复审唯一 open finding（DAG/组合根），修复在计划文本中有直接 evidence 且无回归。37 slices 计数一致；Terra T-01 至 T-08 与 MiM M-001 至 M-013 全部闭合。Open H/M/L = 0。计划现在是 code-generation-ready，可以推进到 accepted plan commit。
