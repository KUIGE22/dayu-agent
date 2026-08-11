# Phase 1 Integration Corrective Fix（Codex Spark）

- Date: 2026-08-11
- Scope: `tests/integration/investment/test_identity_repositories_postgres.py`
- Frozen artifacts: `README` 与 `production/plan` 未变更（按约束冻结）
- Status: `AWAITING FINAL TERRA RE-REVIEW`

## 已执行修订

1. `test_identity_repositories_postgres.py`
   - 移除 `_FsRepositorySet` 与 `_bare/TypeVar` 依赖，改用显式 `_FakeRepositorySet`。
   - 删除 `_build_s3_store_from_settings` 替身；`S3FileStore.head_bucket` 改为带签名 noop，以保留六键 JSON 解析、凭证读取与 `S3FileStore` 构造真实路径。
   - 新增 production startup 黑盒私有清理 helper：
     `_cleanup_production_startup_resources(...)` + `_report_cleanup_errors(...)`。
     采用收集异常并行清理策略，主异常始终不被清理异常吞没。
   - 新增 black-box 负例：`test_production_provider_s3_placeholder_still_rejected`，
     覆盖旧 `s3://placeholder`，并通过哨兵断言 `platform_provider` 与
     `production identity provider` 均未触发。
   - `wrong-role` 场景改为先迁移再创建临时 login，且 login 从创建时即受
     cleanup 范围管理。
   - 新增 `prepared.close()` 抛错路径测试：`test_production_provider_close_propagates_failure_and_still_cleans`，
     验证关闭失败后仍完成 schema/group/login 清理语义。
   - 保留并未移除 `prepared.close()` 多次幂等断言测试。

2. `missing_dsn` 用例保持原行为未改。

## Docker 验证段（2026-08-11，真实容器证据）

在真实 Docker（colima，PostgreSQL 16.14 pinned digest，本地已存在）下按
`phase-1-docker-integration-validation-20260811-deepseek-flash.md` §9 命令集复跑
本 corrective patch：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 1 目标类 | `pytest test_identity_repositories_postgres.py -k TestProductionStartupBlackBox -q` | **6 passed** |
| 2 完整文件 | `pytest test_identity_repositories_postgres.py -q` | **16 passed** |
| 3 四条 Phase1 | migrations + identity + fins_s3_minio + workspace_import | **74 passed** |
| 4 残留 | `docker ps -a/network ls --filter label=dayu-slice11.owner` | **0 / 0**；`dayu.test.owner` 0 |
| 5 静态 | `pyright` 与基线一致 17 errors（docling_core/HTTPError 既有项，未新增未扩散）；`ruff --select F,I` pass；`ruff default` pass；`git diff --check` clean | 全绿 |

### Docker 复跑中发现并修复的测试桩缺陷（仅限本测试文件）

1. `test_production_provider_close_propagates_failure_and_still_cleans`：
   - 原断言 `close_calls != 1` 与真实语义不符：`prepared.close()` 首次 S3 close 故意
     抛错验证错误传播后，cleanup helper 必然第二次重试 close 以完成收口，
     因此预期为 **2**。修复：断言改为 `close_calls != 2`，并保留
     `close_error` 捕获证据（首次 close 确实抛出目标 `RuntimeError`）。
   - 移除 `Engine.dispose` monkeypatch/counter/assert：dispose 计数会被
     alembic downgrade 与 admin SQL 的 bootstrap engine 污染，不适合作
     failure-cleanup 断言；provider `dispose` 恰一次已由同文件
     `test_production_provider_close_disposes_engine_once` 锁定。本测试只锁
     错误传播 + 重试收口 + `_migrate_down_and_assert` 证明
     schema/group roles/login 归零。
   - 同步删除该测试内不再使用的 `from sqlalchemy.engine import Engine` 局部导入。

### 专项观察点确认

- **invalid s3 负例走 strict parser**：`test_production_provider_s3_placeholder_still_rejected`
  通过，哨兵断言 `_read_postgres_dsn` / provider / production provider 均未触发，
  错误消息不回显 `s3://placeholder`；`S3SettingsError` 在 provider 装配前由严格
  JSON 解析抛出，顺序符合 S14-CTRL-05。
- **close 抛错 test 仍清理 schema/group roles/login**：`_failing_s3_close` 首次抛错
  后，cleanup 第二次 close 走原实现完成 platform lifecycle 收口；尾部
  `_migrate_down_and_assert` 断言 `dayu_platform` schema 消失、group roles 归零，
  `drop_temporary_login` 已执行，测试通过。
- **wrong-role 顺序**：`test_production_provider_wrong_role_rejected` 通过——先迁移
  再创建临时 login，login 从创建起即受 cleanup 范围管理，probe 拒绝且不回显
  role/端口。

### 结论

- 16 项 identity 文件与 74 项四条 Phase1 全部在真实 PG16 容器内通过；
  原 docker artifact（deepseek-flash）最终数字同步更新为 **74 passed**。
- production / plan / README 未改动；仅本测试文件有两处 corrective 修复；
  未 commit/push/PR。
- 状态：`READY FOR CORRECTIVE DUAL RE-REVIEW`。

## 风险/未完成

- 已完成 Docker 环境验证（见上段）；等待 corrective dual re-review。

## Round 2（Terra corrective review 唯一 M，2026-08-11）

Terra 指出 close-failure 测试在 `close_error` 分支对 `cleanup_errors` 只加 note
不失败，违反「任何 cleanup failure 必须 fail」。本 round 仅改该测试：

1. `test_production_provider_close_propagates_failure_and_still_cleans`：
   在 `close_error` 分支显式断言 cleanup 零失败——
   `if cleanup_errors: raise ExceptionGroup("close failure path cleanup must not fail", cleanup_errors)`，
   保留 `close_calls == 2` 断言与 `close_error` 捕获证据。
2. Docker artifact（deepseek-flash）§9.3 残留数字 `72/72` 同步为 `74/74`。

### Round 2 验证结果（真实 Docker，colima + PG16 pinned digest）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 1 目标单测 | `pytest test_identity_repositories_postgres.py -k test_production_provider_close_propagates_failure_and_still_cleans -q` | **1 passed** |
| 2 完整文件 | `pytest test_identity_repositories_postgres.py -q` | **16 passed** |
| 3 四条 Phase1 | migrations + identity + fins_s3_minio + workspace_import | **74 passed** |
| 4 残留 | `docker ps -a/network ls --filter label=dayu-slice11.owner` | **0 / 0**；`dayu.test.owner` 0 |
| 5 静态 | scoped pyright 0 errors；`ruff --select F,I` pass；`ruff default` pass；`git diff --check` clean | 全绿 |

- 状态：`AWAITING FINAL TERRA RE-REVIEW`。
- production / plan / README 未改动；仅该测试文件一处 corrective 修改；
  未 commit/push/PR。
