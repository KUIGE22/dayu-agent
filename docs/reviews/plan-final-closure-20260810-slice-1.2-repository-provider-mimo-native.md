# Plan Final Closure — Slice 1.2 Repository/Provider

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.2 revised（S12-CTRL-01..07）
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-final-closure-20260810-slice-1.2-repository-provider-mimo-native.md`
- Source chain：Terra FAIL（H0/M2/L0）→ MiM PASS（L2）→ fix → Terra FAIL（M1）→ S12-CTRL-05/06 fix → MiM PASS（L0）→ Terra FAIL（M1）→ S12-CTRL-07 lifecycle fix → **本 final closure**
- Focus：TERRA-S12-FINAL-001 是否由 S12-CTRL-07 完整闭合

## TERRA-S12-FINAL-001 — Lifecycle Owner → CLOSED ✅

### 先前问题

Terra-S12-FINAL-001（Medium）指出：成功态 auto-created engine 没有公开且类型安全的 lifecycle owner。`PreparedHostRuntimeDependencies.platform_composition` 的类型是 `PlatformComposition[PlatformServiceProtocol]`，而 `PlatformServiceProtocol` 只有 `platform_service_name` property——没有 `close()`。CLI/WeChat/Web 无法可靠回收连接池。

### S12-CTRL-07 闭合验证

**1. `PlatformOwnedLifecycleProtocol`**（plan line 772-776）：
- 纯层 `composition.py` 定义，唯一方法 `close() -> None`
- 不扩 `PlatformServiceProtocol`，future service 不被迫拥有数据库生命周期
- `services/protocols.py` 只做 stable re-export

✅ 最小纯层 lifecycle 协议，不污染现有 service contract。

**2. `PreparedHostRuntimeDependencies.close()`**（plan line 777-783）：
- 私有持有 `_owned_platform_lifecycle: PlatformOwnedLifecycleProtocol | None`
- 公开幂等 `close() -> None`
- production default provider 成功时传入具体 `InvestmentIdentityService`
- 显式注入 / disabled / development 路径传 `None`，其 `close()` 为 no-op
- 禁止 `cast`、`getattr`、按 service name 从 composition registry 下转、或把 lifecycle handle 暴露给 UI

✅ Public typed shutdown entry，无类型逃逸。

**3. `atexit` exact-once**（plan line 784-788）：
- 成功构造后注册一次 `atexit` callback
- 显式 `close()` 后 callback 再次调用必须 no-op
- startup 任一点失败则同步 close/dispose，且不注册 callback
- explicit provider 任何路径都由 caller own

✅ Safety net for callers that don't explicitly close。

**4. Engine disposal idempotency**（plan line 789-795）：
- `InvestmentIdentityService.close()` 必须线程安全且幂等
- auto-created engine 的 `dispose()` 至多一次
- 关闭后不删除/修改业务数据

✅ 防止 double-dispose 和数据损坏。

**5. PG16 测试覆盖**（plan line 790-795）：
- public-path black-box：仅经声明类型调用 `prepared.close()` 两次 → 断言 dispose 恰一次
- 用新 application engine/session 验证先前写入仍存在
- 覆盖：callback registration exact-once、manual-close 后 callback no-op、explicit-provider close count=0、startup failure callback/engine residue=0
- unit 测试不得依赖进程退出或垃圾回收证明 cleanup

✅ 完整 lifecycle 行为验证。

## Lifecycle/Allowlist/DAG — No New Gaps

| 检查项 | 结果 | 证据 |
|--------|------|------|
| S12-CTRL-07 只修改已允许文件 | ✅ | `composition.py`（加 protocol）、`services/protocols.py`（re-export）、`startup_preparation.py`（lifecycle 管理）——均在 allowlist |
| 不需要新文件 | ✅ | `PlatformOwnedLifecycleProtocol` 加入现有 `composition.py` |
| 不改变 37-slice DAG | ✅ | lifecycle 是 Slice 1.2 内部实现，不改变 slice 依赖关系 |
| 不引入 future owner | ✅ | `InvestmentIdentityService` 是唯一 concrete lifecycle owner，不预注册 jobs/evidence/portfolio |
| 不修改 `PlatformServiceProtocol` | ✅ | lifecycle 协议独立于 service 协议，future service 不被迫拥有 DB 生命周期 |
| 不向 UI/composition 泄漏 engine | ✅ | 禁止 cast/getattr/registry downcast |

## All S12-CTRL Items — Final Status

| 控制项 | 状态 | 闭合证据 |
|--------|------|----------|
| S12-CTRL-01 Repository/domain contract | ✅ CLOSED | frozen DTO/API/errors/UUID boundary |
| S12-CTRL-02 Service/provider contract | ✅ CLOSED | pure-layer protocol + service owner + production/dev profile |
| S12-CTRL-03 PG16 integration | ✅ CLOSED | real PG16 black-box + owner-label cleanup |
| S12-CTRL-04 Docs completion | ✅ CLOSED | README sync |
| S12-CTRL-05 Frozen DTO/API/UUID contract | ✅ CLOSED | canonical UUID + exact fields + error hierarchy + protocol signatures |
| S12-CTRL-06 Production startup/public failure | ✅ CLOSED | public entry + DSN safe failure + engine ownership + PG16 black-box |
| S12-CTRL-07 Public lifecycle/shutdown | ✅ CLOSED | PlatformOwnedLifecycleProtocol + PreparedHostRuntimeDependencies.close + atexit + failure cleanup |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- S12-CTRL-07 的 lifecycle 协议是 "minimal"——future slice 可能需要更丰富的 shutdown 协调（例如 multi-service graceful shutdown），但那是后续 slice 的职责。当前最小协议足够 Slice 1.2 闭合。
- `atexit` callback 注册在 `PreparedHostRuntimeDependencies` 构造成功后——如果进程被 `kill -9` 终止，callback 不会执行。这是 `atexit` 的固有局限，不构成 plan 缺陷。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

TERRA-S12-FINAL-001 已通过 S12-CTRL-07 完整闭合：`PlatformOwnedLifecycleProtocol` 最小纯层协议 + `PreparedHostRuntimeDependencies.close()` public typed shutdown + `atexit` exact-once safety net + failure cleanup + explicit-provider caller ownership + PG16 tests（dispose at-most-once + data persistence）。S12-CTRL-01..07 全部闭合。无 lifecycle/allowlist/DAG 新缺口。允许进入 accepted plan commit。
