# Controller Plan Fix：Slice 2.1 PG16 lane process isolation

- **Status**：`ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Master**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **Accepted provider erratum commit**：`e0ac679`
- **Scope**：只修改 target、master 与本文；production/tests/README 及当前 Flash WIP 冻结。

## 1. Direct evidence and adjudication

Provider-allowlist implementation 按 accepted target 把三个 PG16 文件放入同一 pytest invocation，真实退出为 `63 passed / 35 failed`。失败集中在后运行的 `test_platform_migrations_postgres.py`；traceback 为 migration `0001_platform_foundation` 正确拒绝 cluster-global `dayu_platform_app` 已存在。

根因不是 production migration 或 durable job state machine：

1. `platform_cluster` 是 pytest session-scoped；同一 invocation 的三个文件共享一个 PG16 cluster。
2. identity/jobs 文件先运行 migration 并在 cluster 级创建 `dayu_platform_app` / `dayu_platform_audit` group roles；database cleanup 不等于 cluster-global role cleanup。
3. migration 文件故意要求独立 bootstrap admission，并正确 fail closed on role pre-existence；把它排在已迁移文件后会污染该测试前提。
4. `tests/README.md` 与 Phase 1 validation artifacts 均按文件分别启动 pytest 进程。该既有 lane 不是单进程 aggregate contract。

Controller 裁决：validation orchestration gap，接受最小 plan fix。禁止通过放宽 migration admission、修改 fixture/global role cleanup、改变测试顺序、`-k`、skip 或 masked pipeline exit 绕过。

同次审计还发现 provider corrective 第 4 项只列 `PlatformOwnedLifecycleProtocol`，但旧 `_counted_build_production_identity_provider` wrapper 同时是 `PlatformCompositionProviderProtocol` 的唯一引用；删除 wrapper 后两者都 unused。Target 现精确授权删除这两个既有 composition imports，不允许其它 import drift。

## 2. Exact plan correction

PG16 completion gate 改为三个独立进程，且三条都必须以真实退出码 PASS：

1. `.venv/bin/pytest tests/integration/investment/test_platform_migrations_postgres.py -q`
2. `.venv/bin/pytest tests/integration/investment/test_identity_repositories_postgres.py -q`
3. `.venv/bin/pytest tests/integration/investment/test_postgres_jobs.py -q`

顺序不赋予语义；进程隔离才是契约。不得把三文件合并为一个 invocation。`test_platform_migrations_postgres.py` 中仍未完成的 0003 exact table/constraint/index/grant 期望更新属于原 accepted PG/CLI test owner，Flash 恢复后必须在既有 allowlist 内完成；本 plan fix 不把该实现工作误判为新的 plan finding。

## 3. Frozen implementation snapshot

Plan-fix 开始时 21 个 production/test WIP SHA-256 如下；双审/acceptance 前后必须完全一致：

| Path | SHA-256 |
| --- | --- |
| `dayu/cli/workspace_migrations/runner.py` | `f171638ad9217c07d4d834328e1ac7957f331c3be5ae9368c011a67cbf6663a7` |
| `dayu/host/executor.py` | `d8de5420693a3ab3697b3d0338cac516e35a8c16cfd2d0dd1f1d8fb51a171106` |
| `dayu/host/host.py` | `527f75ebb9bef85373cbe4465be01118aa2ea460a26b939d9770a2fb93ea32d0` |
| `dayu/host/host_execution.py` | `bb64c81d978ae818543bc5b58677372a2b0090e3e8f4fedcd36c766dcfc8706b` |
| `dayu/host/protocols.py` | `76aa99774f3580de5df4e3fa6533feead2b7839b82624054580d8d571ab05249` |
| `dayu/host/run_registry.py` | `1b6e7de83151ed77cf5988ef0d4904dc45cb324f6cce3f7115c26371643d9f9e` |
| `dayu/investment/storage/protocols.py` | `0dd627c8584da5164825cd544d4d959829f414ecf625f5d5c465d52b1c00c079` |
| `dayu/services/startup_preparation.py` | `bc8bc1014d9bbe9da8fbde32790d704fcbf93473f0f2b24d34f00d344a599c5e` |
| `tests/application/test_run_registry.py` | `8e5897674a715c3fba52290f0721b20e7c0102fb1462640c0f67ac279f30d3c8` |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `5afb872ff99824e508381228be742aa4d055dd98bc60729b23d630fe98ee9034` |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `0823b6379b4cadb6b65c3b5f58a30c043ce624d96d6265db3873decfda43cedd` |
| `tests/investment/test_platform_migrations.py` | `1ad22fe8dec5b5c993d01c334c8d49ea50d06df8b3dba5e49c2d03339a614f8e` |
| `dayu/cli/workspace_migrations/platform_jobs.py` | `a6162883afca8f51de0dfa7c044195e70d75e36adcac79169c5263f1192bd9d3` |
| `dayu/investment/domain/jobs.py` | `db7b406f00ca2c647e35b73f43c3ab24b7030c69e1a50cf5ba91bc974f103ef4` |
| `dayu/investment/storage/migrations/versions/0003_durable_jobs.py` | `7586210a72e0d7c0c4e490ba9cf15e7c87f64130c133bf920da92ee8b3a90770` |
| `dayu/investment/storage/postgres_jobs.py` | `dadb78f8175e86370fb0939e9b49985334bf72afdb088f50e985078ac4dd932d` |
| `dayu/services/job_service.py` | `4fba330010dc04b1b668dbd94fdb59db7740e047dddc608b0d4f16825f11835d` |
| `tests/application/test_job_service.py` | `47150d6a221459262bb06d956a7e8080cb5147a89efecd25ef894f3319a63207` |
| `tests/application/test_reserved_agent_run.py` | `784d1b71d2eef327ab4340d95038528a8213d8797fbb845561bd3ef052e102db` |
| `tests/cli/workspace_migrations/test_platform_jobs.py` | `da3f397503617a394ab5c4dfb9f5aa3cc430f4cb682b79c1f4e1501894d04a3d` |
| `tests/integration/investment/test_postgres_jobs.py` | `59543456dbbea97c97d9082a3f3c48846b7aa5a30815b8c2fcfbe3218849aa9a` |

## 4. Stop and review gate

- 任一 reviewer 要求放宽 production role admission、修改 shared fixture/cleanup 或以同进程顺序规避，STOP。
- 任一 frozen WIP hash 漂移，STOP。
- 三个独立 PG16 进程中任何失败必须按其真实 owner 判断；不得把 0003 stale expected catalog 当成 process-isolation failure，也不得掩盖它。
- 双路 plan review 均 PASS、Controller open H/M/L=`0/0/0` 前 implementation 保持冻结。

## 5. Dual review closure

- `docs/reviews/plan-review-20260811-195259-slice-2.1-pg16-lane-isolation-mim.md`：PASS/open H/M/L=`0/0/0`。
- `docs/reviews/plan-review-20260811-slice-2.1-pg16-lane-isolation-spark.md`：PASS/open H/M/L=`0/0/0`。
- Controller acceptance：`docs/reviews/plan-acceptance-20260811-slice-2.1-pg16-lane-isolation-codex.md`。

21/21 WIP hashes 复核一致；implementation freeze 已解除。本 closure 不授权 push/PR。
