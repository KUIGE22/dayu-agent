# Controller Plan Fix：Slice 2.1 production provider exact-mapping implementation blocker

- **Gate**：implementation-time plan erratum；本轮不进入 Gateflow review。
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Master control plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **Accepted plan commit**：`869e5c653ce9c64730ac8346a857a70b61d5a677`
- **当前状态**：`ACCEPTED / CORRECTIVE DUAL PLAN RE-REVIEW PASS / CLOSED`
- **本次文档范围**：target、master 状态/必要指针与本 Controller artifact；不改 acceptance、production、tests、fixtures、README，不 commit/push。

## 1. 根因与 Controller 裁决

### 直接证据

1. target §6 已把 default production provider 定义为精确 mapping：`{"investment_identity": identity_service, "durable_jobs": job_service}`；其中 `JobService.platform_service_name == "durable_jobs"`，`PostgresJobStore` 只接收 session factory，真实 `Host` 在构造后、startup recovery 前作为 reader 注入 JobService。
2. 当前 Flash WIP 的 `dayu/services/startup_preparation.py` 已按上述 mapping 装配两个真实服务。
3. `tests/integration/investment/test_identity_repositories_postgres.py::TestProductionStartupBlackBox::test_production_provider_wires_real_identity_service` 仍断言 `set(services) == {"investment_identity"}`，因此会拒绝正确的 two-service production composition。
4. target §2 的 exact allowlist 未列该 integration test；target §8 的 integration 命令也未运行该文件。实施者既不能合法修正该阻塞断言，也无法以计划规定的 integration lane 发现它。

### 根因结论

这是与正确 production mapping 同源的 plan allowlist / named-test / validation-lane 缺口，不是 allowlist 内 implementation defect。若保留旧断言，正确实现必然使完整 PG16 production-startup integration lane 失败；若为使其通过而改未列测试，则又违反 accepted target 的 stop rule。因此 implementation 必须冻结并回到 plan re-review。

## 2. 唯一允许修正

本 erratum 只授权 target plan：

1. 将 `tests/integration/investment/test_identity_repositories_postgres.py` 加入 exact allowlist。
2. 允许将其中既有 `TestProductionStartupBlackBox.test_production_provider_wires_real_identity_service` 改名为 `test_production_provider_wires_exact_two_service_mapping`，并在该方法本体内把 black-box 断言改为精确 two-service mapping：
   - key set 仅为 `{"investment_identity", "durable_jobs"}`；
   - `investment_identity` 仍是实际 identity service，既有 company/security 注册断言保持；
   - `durable_jobs` 是实际 `JobService`，且 `platform_service_name == "durable_jobs"`；
   - 既有关闭行为不弱化。
3. 根据首轮 Spark H-001，只允许在同文件 `test_production_provider_s3_placeholder_still_rejected` 方法内移除已经不存在的 `_build_production_identity_provider` lookup/counter/monkeypatch/assert；必须保留 `_read_postgres_dsn` 零调用、显式 provider 零调用与 safe placeholder error 断言。不得向 production 添加 compatibility helper，也不得以反射或宽 monkeypatch 替代。
4. 同文件模块级只允许把“仅一个 identity / 无 jobs”的过时说明改成 exact two-service contract，并从既有 composition import 删除因第 3 项变成 unused 的 `PlatformOwnedLifecycleProtocol`；其它 import、fixture、helper、测试和模块内容冻结。
5. target §§3、6、7E、8 必须把 exact provider mapping、`PostgresJobStore(session_factory=...)`、Host 构造后注入 reader、identity 为 shared-engine 唯一 lifecycle/close owner，以及各 named test 的 owner/path/lane 闭合。完整 integration 命令必须包含该 identity-repositories PG16 文件以及既有 job/migration integration 文件。
6. master 只同步 Slice 2.1 的 pending 状态与本 artifact 指针；其它 slice 不变。

这不是 production/test implementation 授权。本轮只改计划文档；重新放行前不得改任何 Flash WIP。

## 3. WIP freeze evidence

以下是本 plan-fix 开始前的完整 production/test WIP manifest。后续 plan-fix 前后必须逐项以 SHA-256 完全一致；任一文件内容变化均视为越界。

| Git 状态 | 路径 | SHA-256 |
| --- | --- | --- |
| `M` | `dayu/cli/workspace_migrations/runner.py` | `f171638ad9217c07d4d834328e1ac7957f331c3be5ae9368c011a67cbf6663a7` |
| `M` | `dayu/host/executor.py` | `d8de5420693a3ab3697b3d0338cac516e35a8c16cfd2d0dd1f1d8fb51a171106` |
| `M` | `dayu/host/host.py` | `527f75ebb9bef85373cbe4465be01118aa2ea460a26b939d9770a2fb93ea32d0` |
| `M` | `dayu/host/host_execution.py` | `bb64c81d978ae818543bc5b58677372a2b0090e3e8f4fedcd36c766dcfc8706b` |
| `M` | `dayu/host/protocols.py` | `76aa99774f3580de5df4e3fa6533feead2b7839b82624054580d8d571ab05249` |
| `M` | `dayu/host/run_registry.py` | `1b6e7de83151ed77cf5988ef0d4904dc45cb324f6cce3f7115c26371643d9f9e` |
| `M` | `dayu/investment/storage/protocols.py` | `0dd627c8584da5164825cd544d4d959829f414ecf625f5d5c465d52b1c00c079` |
| `M` | `dayu/services/startup_preparation.py` | `bc8bc1014d9bbe9da8fbde32790d704fcbf93473f0f2b24d34f00d344a599c5e` |
| `??` | `dayu/cli/workspace_migrations/platform_jobs.py` | `a6162883afca8f51de0dfa7c044195e70d75e36adcac79169c5263f1192bd9d3` |
| `??` | `dayu/investment/domain/jobs.py` | `db7b406f00ca2c647e35b73f43c3ab24b7030c69e1a50cf5ba91bc974f103ef4` |
| `??` | `dayu/investment/storage/migrations/versions/0003_durable_jobs.py` | `7586210a72e0d7c0c4e490ba9cf15e7c87f64130c133bf920da92ee8b3a90770` |
| `??` | `dayu/investment/storage/postgres_jobs.py` | `dadb78f8175e86370fb0939e9b49985334bf72afdb088f50e985078ac4dd932d` |
| `??` | `dayu/services/job_service.py` | `4fba330010dc04b1b668dbd94fdb59db7740e047dddc608b0d4f16825f11835d` |
| `M` | `tests/application/test_run_registry.py` | `8e5897674a715c3fba52290f0721b20e7c0102fb1462640c0f67ac279f30d3c8` |
| `M` | `tests/integration/investment/test_platform_migrations_postgres.py` | `0823b6379b4cadb6b65c3b5f58a30c043ce624d96d6265db3873decfda43cedd` |
| `M` | `tests/investment/test_platform_migrations.py` | `1ad22fe8dec5b5c993d01c334c8d49ea50d06df8b3dba5e49c2d03339a614f8e` |
| `??` | `tests/application/test_job_service.py` | `47150d6a221459262bb06d956a7e8080cb5147a89efecd25ef894f3319a63207` |
| `??` | `tests/application/test_reserved_agent_run.py` | `784d1b71d2eef327ab4340d95038528a8213d8797fbb845561bd3ef052e102db` |
| `??` | `tests/cli/workspace_migrations/test_platform_jobs.py` | `da3f397503617a394ab5c4dfb9f5aa3cc430f4cb682b79c1f4e1501894d04a3d` |
| `??` | `tests/integration/investment/test_postgres_jobs.py` | `59543456dbbea97c97d9082a3f3c48846b7aa5a30815b8c2fcfbe3218849aa9a` |

## 4. Stop conditions

- 需要修改 `test_identity_repositories_postgres.py` 中上述两个方法、模块 docstring 与单个 unused import 之外的任一测试、fixture、helper、import 或模块级内容时，STOP 并交回 Controller。
- 需要修改 production、schema、public contract、owner、其它 Slice、acceptance 或 README 时，STOP；不得借 compatibility wrapper、adapter、反射或第二 lifecycle owner 绕过此缺口。
- 完整 integration lane 若暴露任何其它失败，不得顺带修复；记录直接证据并交回 Controller 取得新的明确授权。
- 任何上述冻结路径的 SHA-256 漂移，或任何非 target/master/artifact 的工作树改动，均 STOP。

## 5. Review gate 与下一入口

首轮独立 plan re-review 已完成：MiM `PASS / open H/M/L=0/0/0`，Spark `FAIL / open H/M/L=1/0/0`。Controller 接受 Spark H-001 并以 `docs/reviews/plan-fix-20260811-slice-2.1-provider-mapping-corrective-codex.md` 完成最小修正；MiM 首审因漏检旧 helper 引用不能单独构成放行证据。最终 `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-mim.md` 与 `docs/reviews/plan-review-20260811-slice-2.1-provider-allowlist-corrective-closure-spark.md` 均 `PASS / open H/M/L=0/0/0`；Controller acceptance 为 `docs/reviews/plan-acceptance-20260811-slice-2.1-provider-mapping-corrective-codex.md`。Implementation freeze 已解除，仅限 accepted exact allowlist；仍不授权 push 或 PR。

本轮完成后只做限定 diff、whitespace、LF 与 path 审计；不运行 pytest、pyright、Ruff、Docker/PG16、network、commit 或 push。
