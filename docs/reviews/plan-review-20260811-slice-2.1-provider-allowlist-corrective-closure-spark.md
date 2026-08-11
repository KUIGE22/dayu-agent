# Slice 2.1 Provider Allowlist Erratum（Spark corrective closure re-review）

- **Reviewer**: Codex Spark（closure-only）
- **Timestamp**: 2026-08-11
- **Scope**: AGENTS + target plan + master control plan + corrective plan + 首轮 plan re-reviews + startup WIP + startup black-box test WIP（仅为可执行性核验，未修改）
- **Outcome**: **PASS**（closure-only）
- **Open H/M/L**: **0 / 0 / 0**

## 1. 复审边界与结论

本次复审严格按你明确的 **plan gate** 执行：不修改任何 plan/code/tests；只判断 `plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md` 的四类授权是否足以闭合 `H-001`，并且 plan 叙述是否 code-generation-ready。

结论是：**PASS / open 0/0/0**。

## 2. H-001 closure 复核结果（基于四类授权）

1. 映射测试最小修改
- 已授权：重命名 `test_production_provider_wires_real_identity_service` 为 `test_production_provider_wires_exact_two_service_mapping`，并改写断言为 exact key set 与 `durable_jobs` 实例断言。
- 对应依据：
  - target plan §7E 与 §5 `Allowlist` 已将该测试列为唯一 mapping 变更点。
  - WIP `startup_preparation` 当前确实返回 `investment_identity + durable_jobs`（`DURABLE_JOBS_SERVICE_NAME`）。
- 结论：该授权直接对齐阻断点，不扩大改动边界。

2. Placeholder test helper 删除
- 已授权：仅在 `test_production_provider_s3_placeholder_still_rejected` 内删除旧 helper probe（`_build_production_identity_provider` 的 lookup/counter/monkeypatch/assert）。
- 对应依据：
  - WIP 仅保留 `_build_production_services_provider`；旧 helper 已无实现（Spark 初审测得）。
  - correction 文档明确要求保留 DSN/provider/PG zero side-effect 的 fail-closed 断言链。
- 结论：该授权足以修复该 test 与 full PG16 lane 的“不可执行”耦合点，且不触及 production code。

3. 模块说明更新
- 已授权：仅同步模块 docstring 为 two-service exact contract。
- 对应依据：target 和 corrective 文档均把“仅一个 identity service”记述视为陈旧技术债。
- 结论：该更新是文档一致性闭合项，属于 code-generation-ready。

4. unused import 清理
- 已授权：仅删除 `PlatformOwnedLifecycleProtocol` 单点 unused import。
- 对应依据：该 import 在第二项清理后失效，且清理路径与原有文件 freeze 一致。
- 结论：边界足够窄，避免无意义兼容代码。

## 3. 其它三审项核对（保持四类授权闭合范围）

- **unused import/docstring/compat**：已显式约束，且 plan 文本未引入 compatibility helper/adapter。
- **exact mapping 与 provider 生命周期**：
  - WIP `startup_preparation` 仍保持 `PostgresJobStore(session_factory=...)`。
  - `Host` 在构造后注入为 `host_run_reader`，并保持 `shared engine` 的 identity lifecycle。
  - 这一语义已在 target §3.2/§8 与 corrective §3 内同步，不与四类授权冲突。
- **integration lane**：
  - target §8 仍将 PG16 black-box 命令包含 `test_identity_repositories_postgres.py`。
  - 纠偏授权与该 lane 一致（仅修该文件内必要点），符合“不能改其它测试/production”的约束。

## 4. Code-generation-ready 评价

- `plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md` 的 4 类授权是操作位点完全确定、按方法粒度定位、并与 plan §2.2/§7E/§8 的 named-test 与 stop condition 一一对齐。
- 该 plan 可由实施者直接执行，且不会引入新边界。
- 本轮不存在 plan-level 的新增 Medium/Low 风险。

## 5. 最终判定

- **PASS，open H/M/L = 0/0/0**。
- `H-001` 在四类授权内可闭合，不需额外 plan 改动；当前 previous Spark artifact 为历史测评/gate-error 记录可保留。
