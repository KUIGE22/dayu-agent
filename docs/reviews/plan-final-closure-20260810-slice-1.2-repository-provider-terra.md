# Slice 1.2 repository/provider final closure-only corrective plan re-review — Terra

- **审查目标**：Slice 1.2 的 S12-CTRL-05/06/07，closure-only 核验 `TERRA-S12-FINAL-001`。
- **已完整读取**：前次 Terra final rereview、MiM Native final review、repository/provider、API/startup、lifecycle 三份 Controller plan-fix artifact，以及当前 master plan。
- **核验方式**：只读；并对照当前 `PlatformComposition` / `PlatformServiceProtocol` 与 `PreparedHostRuntimeDependencies` 的公开类型边界。未启动 PG16/Docker、未触碰 live/broker。

## Assumptions tested

1. auto-created engine 有唯一、公开、类型安全而不泄漏 engine/session/provider 的 success-state owner。
2. 手工 close、`atexit` 和 startup failure 不能造成 double-dispose、遗漏 cleanup 或关闭 injected provider。
3. 真实 PG16 public startup 能证明 lifecycle，而非通过 registry downcast 或 GC 伪绿。
4. lifecycle fix 不扩张 future Service 义务、不新增反向依赖，也不需要未列入 Slice 1.2 的 owner/test 路径。

## Closure verification

| 验证项 | 结论 | 证据 |
| --- | --- | --- |
| 纯层 lifecycle 真源 | 通过 | S12-CTRL-07 将唯一 `close() -> None` 的 `PlatformOwnedLifecycleProtocol` 放在 `dayu.investment.composition`，Service 层仅稳定 re-export；不导入 ORM、startup 或 future owner。 |
| public typed owner | 通过 | `PreparedHostRuntimeDependencies.close()` 成为唯一 public owner，并以私有 `PlatformOwnedLifecycleProtocol | None` 持有 auto-created lifecycle；不再经 `PlatformComposition[PlatformServiceProtocol]` registry 的 concrete downcast 关闭。 |
| exact-once / failure cleanup | 通过 | 成功完整构造后才注册一次 `atexit`；manual close 后 callback no-op；任意 startup failure 在原异常传播前同步 dispose 且不残留 callback；具体 Service `close()` 线程安全、幂等，engine `dispose()` 至多一次。 |
| explicit-provider ownership | 通过 | injected provider、disabled、development 都传 `None`，runtime `close()` 为 no-op；任意启动/关闭路径不得触碰 caller-owned provider。 |
| PG16 证明 | 通过 | S12-CTRL-07 要求仅由声明类型调用 `prepared.close()` 两次，断言 dispose 一次并由新 application engine/session 验证既有 company/security/subscription 不变；另覆盖 callback exact-once/manual no-op、explicit close count=0 与 failure residue=0。禁止以进程退出、GC、SQLite/fake 或 direct provider construction 代替。 |
| allowlist / DAG / future owner | 通过 | 仅使用既有允许的 pure composition、Service protocol/repository、startup、Service、application unit 与 PG16 integration 路径；未扩 `PlatformServiceProtocol`，故不需修改所有 future Service 或其既有测试；无 schema/migration、CLI/WeChat/Web、jobs/evidence/portfolio owner 变更。 |

## Findings

无。`TERRA-S12-FINAL-001` 已由 S12-CTRL-07 完整闭合：此前 public return type 无法类型安全关闭 auto-created engine 的反例，现由 `PreparedHostRuntimeDependencies.close()` 与 private lifecycle protocol 消除；成功、异常、atexit、manual retry 和 injected-provider 分支均有明确 owner 与可验证行为。

## Open questions

无。

## Residual risk

实现阶段仍须严格按 S12-CTRL-05/06 的 UUID/RLS/transaction/DSN redaction 与随机 PG16 fixture 执行；任何把 lifecycle handle 暴露给 UI、通过 `cast`/`getattr` 下转 service、或把 cleanup 后移到 future owner 的实现均不符合已接受计划，应在 code review 拒绝。

## Final conclusion

**PASS，open H0 / M0 / L0。** Slice 1.2 的 lifecycle owner、exact-once cleanup、explicit-provider boundary、PG16 verification、allowlist 与 import DAG 均已形成可直接实施的闭环；无需进一步 plan correction。
