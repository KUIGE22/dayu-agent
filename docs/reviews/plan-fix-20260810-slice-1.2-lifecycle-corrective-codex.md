# Slice 1.2 lifecycle corrective plan fix

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Controller**：Codex
- **状态**：**CLOSED / DUAL PLAN RE-REVIEW PASS**
- **Source review**：
  `docs/reviews/plan-final-rereview-20260810-slice-1.2-repository-provider-terra.md`
- **Implementation state**：frozen，零 code/test/README 编辑

## Accepted finding

**TERRA-S12-FINAL-001 / Medium — ACCEPTED / FIXED IN PLAN**。
S12-CTRL-06 原来只让 concrete `InvestmentIdentityService` 持有 engine，却把成功启动结果
暴露为 `PlatformComposition[PlatformServiceProtocol]`，public caller 没有类型安全的关闭
入口。测试可以 downcast，但真实 CLI/WeChat/Web 生命周期无法可靠回收连接池。

## Controller decision

新增 S12-CTRL-07，并选择唯一实现方案：

1. 纯层新增最小 `PlatformOwnedLifecycleProtocol.close()`，不扩所有
   `PlatformServiceProtocol` 的义务；
2. `PreparedHostRuntimeDependencies` 私有持有 auto-created lifecycle 并公开幂等
   `close()`，禁止 registry downcast、`cast/getattr` 或 engine/session 泄漏；
3. 成功构造后注册一次 `atexit` 兜底，手工关闭后 callback no-op；失败同步 cleanup 且不
   注册；explicit provider 永远由 caller own；
4. PG16 public-path 证明 public typed close、dispose at-most-once、业务数据不变，unit 证明
   callback/explicit-provider/failure ownership。

该修复只使用 Slice 1.2 已允许的 `composition.py`、`services/protocols.py`、
`startup_preparation.py`、Service 与现有 unit/PG16 integration 测试路径；不需要扩大到
CLI/WeChat/Web 文件，不改变 schema/migration、37-slice DAG 或 future owner。

## Gate

Terra 与 MiM Native final corrective plan re-review 任一路非 PASS 或 open H/M/L 非零，
Slice 1.2 implementation 继续冻结。未运行 live/data/model/broker 外部动作。

## Final closure

- Terra：`plan-final-closure-20260810-slice-1.2-repository-provider-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- MiM Native：`plan-final-closure-20260810-slice-1.2-repository-provider-mimo-native.md`，
  PASS，open H/M/L=`0/0/0`。

TERRA-S12-FINAL-001 已 CLOSED，Slice 1.2 implementation 解冻。
