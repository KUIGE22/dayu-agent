# Corrective Independent Plan Re-Review（MiM Formal Gate）

## 结论

- **STATUS：PASS**
- **open H/M/L：0 / 0 / 0**

## 审核范围

- `AGENTS.md`
- `docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`（target）
- `docs/plans/2026-08-10-investment-platform-restoration.md`（master）
- `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-allowlist-codex.md`（原 plan-fix）
- `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md`（corrective plan-fix）
- `docs/reviews/plan-review-20260811-192410-slice-2.1-provider-allowlist-mim.md`（MiM 首审）
- `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-spark.md`（Spark 首审）
- `tests/integration/investment/test_identity_repositories_postgres.py`（target test file）
- `dayu/services/startup_preparation.py`（startup WIP）

## 1. Spark H-001 闭合验证

### 直接证据

1. **旧 helper 不存在**：`dayu/services/startup_preparation.py:381` 定义 `_build_production_services_provider`，文件中不存在 `_build_production_identity_provider`（grep 零匹配 production code）。
2. **测试仍引用旧 helper**：`test_identity_repositories_postgres.py:1440` 仍执行 `original_build_provider = sp._build_production_identity_provider`，这在当前 WIP 会触发 `AttributeError`。
3. **corrective plan-fix 已授权删除**：corrective plan-fix §2 第 2 项明确授权"在 `test_production_provider_s3_placeholder_still_rejected` 方法内删除旧 helper 的 lookup、counter wrapper、monkeypatch 与计数断言"。
4. **无 compatibility fallback**：corrective plan-fix §3 禁止"新增 compatibility helper、reflection、adapter"。

**结论**：Spark H-001 已真闭合。旧 helper 测试耦合是 plan allowlist 不完整（不是 implementation defect），corrective 已以最小机械变更解决。

## 2. 四类授权充分性验证

corrective plan-fix §2 只允许四类机械变更：

| # | 授权范围 | 验证 |
|---|---------|------|
| 1 | 将 mapping 黑盒测试改名并断言 exact two-service mapping | 充分：`test_production_provider_wires_real_identity_service` 断言 `set(services) == {"investment_identity"}`，与正确 `{"investment_identity", "durable_jobs"}` 冲突。改名+断言修正解决唯一阻塞点。 |
| 2 | 在 placeholder 测试方法内删除旧 helper 的 lookup/counter/monkeypatch/assert | 充分：删除 `sp._build_production_identity_provider` 引用后，该方法不再依赖已删除 helper；保留 `_read_postgres_dsn` 零调用、显式 provider 零调用与 safe S3 error 断言继续证明 fail-closed。 |
| 3 | 同步模块 docstring | 必要：当前 docstring (line 12) 错误声称"只含一个真实 `investment_identity` Service"。 |
| 4 | 删除因第 2 项变成 unused 的 `PlatformOwnedLifecycleProtocol` import | 必要：`PlatformOwnedLifecycleProtocol` 在 line 35 import，仅在 line 1448（被删除的 `_counted_build_production_identity_provider` 返回类型注解）使用。删除第 2 项后该 import 确实 unused。 |

**禁止范围**：同文件任何其它 import/fixture/helper/test/模块内容；新增 compatibility helper/reflection/adapter/第二 lifecycle owner；修改 production 或其它测试。

**结论**：四类授权恰好覆盖阻塞缺口，无过宽。

## 3. PlatformOwnedLifecycleProtocol unused 验证

直接证据：
- **Line 35**：`from dayu.investment.composition import ... PlatformOwnedLifecycleProtocol ...`
- **Line 1448**：`def _counted_build_production_identity_provider(...) -> tuple[PlatformCompositionProviderProtocol, PlatformOwnedLifecycleProtocol]:`

删除第 2 项后，line 1446-1461 的整个 `_counted_build_production_identity_provider` 函数及其 monkeypatch 被移除，`PlatformOwnedLifecycleProtocol` 不再被引用，成为 unused import。

**结论**：corrective plan-fix §2 第 4 项授权删除该 import 是正确且必要的。

## 4. 模块 docstring 更新必要性

当前模块 docstring (lines 1-17)：
```
- production startup 组合只含一个真实 ``investment_identity`` Service，
  且导入图不含 jobs/evidence/portfolio future module；
```

当前 WIP 已是 two-service composition（`investment_identity` + `durable_jobs`），docstring 需更新为 exact two-service contract。

**结论**：docstring 更新必要且 corrective 已授权。

## 5. Placeholder fail-closed 验证

`test_production_provider_s3_placeholder_still_rejected` 方法 (lines 1415-1492) 的核心断言：
- **Line 1472**：`assert placeholder_read_calls[0] == 0`（`_read_postgres_dsn` 零调用）
- **Line 1473**：`assert provider_calls[0] == 0`（显式 `_PlatformProviderSentinel` 零调用）
- **Line 1474**：`assert production_provider_calls[0] == 0`（production provider 零调用）
- **Line 1463**：`with pytest.raises(S3SettingsError)`（safe S3 error）

corrective plan-fix §2 第 2 项要求"保留 `_read_postgres_dsn` 零调用、显式 provider 零调用与 safe S3 error 断言"。删除旧 helper 后这四条断言保持不变，继续证明 placeholder 在 DSN/provider/PG side effect 前 fail closed。

**结论**：placeholder fail-closed 证明充分，无回归。

## 6. Mapping/Lifecycle/Session-Factory/Host-Reader 回归验证

| 检查项 | 证据 | 结论 |
|--------|------|------|
| exact two-service mapping | `startup_preparation.py:431-434` 返回 `{"investment_identity": identity_service, "durable_jobs": job_service}` | 无回归 |
| `JobService.platform_service_name == "durable_jobs"` | `job_service.py:55` 常量 `DURABLE_JOBS_SERVICE_NAME = "durable_jobs"` | 无回归 |
| `PostgresJobStore` session_factory-only | `startup_preparation.py:407` `PostgresJobStore(session_factory=preparation.session_factory)` | 无回归 |
| Host reader 注入时机 | `startup_preparation.py:889` 在 Host 构造后调用 `_build_production_services_provider(..., host_run_reader=host)` | 无回归 |
| shared-engine lifecycle | `InvestmentIdentityService` 仍是唯一 engine lifecycle owner | 无回归 |
| 完整 PG16 lane | target §8 命令包含 `test_identity_repositories_postgres.py` + `test_postgres_jobs.py` + `test_platform_migrations_postgres.py` | 无回归 |

**结论**：所有核心契约无回归。

## 7. Stop Conditions 与边界

corrective plan-fix §3 完整 PG16 lane：
```
pytest tests/integration/investment/test_identity_repositories_postgres.py tests/integration/investment/test_postgres_jobs.py tests/integration/investment/test_platform_migrations_postgres.py -q
```

若四类机械变更后完整 lane 暴露其它失败，实施者必须 STOP，不得自行扩 allowlist。

corrective plan-fix §4 WIP freeze：原 artifact 记录的 20 个 production/test WIP SHA-256 继续是 freeze manifest，corrective 不改变其中任一字节。

**结论**：Stop conditions 完整，边界清晰。

## 8. MiM 首审漏检项修正

MiM 首审 (plan-review-20260811-192410) 声称"同文件其它测试无影响"，但未发现：
- `test_production_provider_s3_placeholder_still_rejected` 仍引用已删除的 `_build_production_identity_provider`
- 该引用会导致完整 PG16 lane 必然失败

corrective plan-fix 已明确承认"MiM 首审因漏检旧 helper 引用不能单独构成放行证据"。本轮 corrective re-review 已逐项验证该遗漏已被修复。

**结论**：MiM 首审漏检项已由 corrective 闭合。

## 9. Open H/M/L

| Level | Count | Items |
|-------|-------|-------|
| H | 0 | — |
| M | 0 | — |
| L | 0 | — |

## 10. Residual Risks

1. **Read-to-entry TOCTOU**：已取得 `START_REQUIRED` 但在 Host ensure 前跨 lease 的窗口不能在两套 store 间消除。这是 target plan §4.3 已明确承认的 residual，归属 Slice 2.2 收敛，不阻碍本 erratum。
2. **Integration 环境依赖**：完整 PG16 integration lane 需要真实 PostgreSQL 16 容器。环境不可用时需跳过并报告。这是既有 residual，不因本 erratum 改变。

## 11. Final Plan Review Conclusion

**PASS**

corrective plan-fix 精确诊断了 Spark H-001（旧 helper 测试耦合），以四类最小机械变更授权解决；MiM 首审漏检项已由 corrective 闭合；§§3/6/7E/8 同步到位；architecture boundary 无穿透；placeholder fail-closed 证明充分；mapping/lifecycle/session-factory/Host-reader 无回归。可以解除 implementation WIP freeze。

本轮不运行 pytest、pyright、Ruff、Docker/PG16、network、commit 或 push。
