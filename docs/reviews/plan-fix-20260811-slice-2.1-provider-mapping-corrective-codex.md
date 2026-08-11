# Controller Corrective Plan Fix：Slice 2.1 provider helper 测试耦合

- **Gate**：implementation-blocking plan erratum 首轮复审裁决。
- **状态**：`ACCEPTED / CORRECTIVE DUAL PLAN RE-REVIEW PASS / CLOSED`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Master**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **首轮 reviews**：
  - `docs/reviews/plan-review-20260811-192410-slice-2.1-provider-allowlist-mim.md`：`PASS / open H/M/L=0/0/0`；
  - `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-spark.md`：`FAIL / open H/M/L=1/0/0`。
- **冻结边界**：本轮只改 target、master、原 Controller artifact 与本文；production、tests、README 和 Flash WIP 字节冻结。

## 1. Finding 裁决

### Spark H-001：ACCEPTED / FIXED-IN-PLAN

直接证据：

1. 当前 production WIP 的唯一阶段二 helper 是 `_build_production_services_provider(preparation, *, host_run_reader)`；旧 `_build_production_identity_provider` 已不存在。
2. `tests/integration/investment/test_identity_repositories_postgres.py::TestProductionStartupBlackBox::test_production_provider_s3_placeholder_still_rejected` 仍在进入 `try` 前读取旧属性，并随后 monkeypatch 它；因此完整 PG16 lane 会在 S3 placeholder 断言前确定性失败。
3. 旧 helper probe 删除后，`PlatformOwnedLifecycleProtocol` 在该文件成为 unused import；模块 docstring 同时仍错误声称 production composition 只有一个 identity service 且不含 jobs。
4. MiM 首审断言“同文件其它测试无影响”遗漏上述直接引用，所以其 PASS 保留为历史 review，不能覆盖 Spark finding 或单独解除冻结。

Controller 采纳 Spark finding，并拒绝用 production compatibility helper 修补测试。根因是测试对已删除 private helper 的耦合及 plan allowlist 不完整，不是 two-service composition 设计错误。

## 2. 最小实现授权

corrective target 只允许同一 PG16 测试文件的四类机械变更：

1. 将 mapping 黑盒测试改名并断言 exact key set `{"investment_identity", "durable_jobs"}`、真实 `JobService` 与 `platform_service_name == "durable_jobs"`，保留 identity register 与重复 close。
2. 在 placeholder 测试方法内删除旧 helper 的 lookup、counter wrapper、monkeypatch 与计数断言；保留 `_read_postgres_dsn` 零调用、显式 provider sentinel 零调用和 safe S3 error 断言，从而继续证明失败发生在 DSN/provider/PG side effect 前。
3. 只同步模块 docstring 为 exact two-service contract。
4. 只删除因第 2 项变成 unused 的 `PlatformOwnedLifecycleProtocol` import。

禁止修改同文件任何其它 import、fixture、helper、测试或模块内容；禁止新增 compatibility helper、reflection、adapter、第二 lifecycle owner；禁止修改 production 或其它测试来迁就 lane。

## 3. 契约与验证闭合

- provider closed mapping 仍精确为 `investment_identity + durable_jobs`，不增加第三项。
- `PostgresJobStore` 仍只接收 session factory；真实 Host 仍在构造后、startup recovery 前注入 `JobService` reader。
- `InvestmentIdentityService` 仍是 shared engine 唯一 lifecycle/close owner。
- 完整相关 PG16 lane仍为：
  `pytest tests/integration/investment/test_identity_repositories_postgres.py tests/integration/investment/test_postgres_jobs.py tests/integration/investment/test_platform_migrations_postgres.py -q`。
- 若上述四类机械变更后完整 lane 暴露其它失败，实施者必须 STOP；不得自行扩 allowlist。

## 4. WIP freeze 与下一 gate

原 artifact 记录的 20 个 production/test WIP SHA-256 继续是 freeze manifest；本 corrective plan-fix 不改变其中任一字节。corrective 双路 plan re-review 必须同时验证：

1. H-001 已闭合且没有 compatibility fallback；
2. 四类授权足以使 test file lint/type 与完整 PG16 lane 可执行；
3. exact mapping、Host reader、session-factory-only 与 shared-engine lifecycle 无回归；
4. open H/M/L=`0/0/0`。

## 5. Corrective dual review closure

- `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-mim.md`：`PASS / open H/M/L=0/0/0`。
- `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-closure-spark.md`：`PASS / open H/M/L=0/0/0`。
- Spark 的早期 `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-spark.md` 把 plan gate 误当 implementation gate，以“冻结代码尚未修改”为 finding；Controller 拒绝该 gate error，要求 closure-only 复审，最终 Spark PASS/open0。
- MiM artifact §5 把应删除的 production-provider counter 误称为“第四条保留断言”，但其 §2、§7 与最终结论正确引用 exact corrective contract；Controller 将该句裁决为 reviewer wording error，不改变 plan 或 open finding 计数。

Controller acceptance：`docs/reviews/plan-acceptance-20260811-slice-2.1-provider-mapping-corrective-codex.md`。两路均 PASS，open H/M/L=`0/0/0`，implementation freeze 已解除；本 closure 不授权 push/PR。
