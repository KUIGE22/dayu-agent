# Phase 1 Integration Corrective Re-Review（MiM Native）

- Reviewer: MiM Native
- Branch / HEAD: `codex/investment-platform` / `b9e5b56`
- Scope: accepted P1-INT-FIX-01..04 + MiM 3 项裁决验证
- Mode: 只读验证，不修改代码
- Output: docs/reviews/phase-1-integration-corrective-review-20260811-mim.md
- Status: **PASS**

## 证据来源

- `docs/reviews/phase-1-integration-fix-review-20260811-terra.md`（初审 Terra M1/M2/M3/L1）
- `docs/reviews/phase-1-integration-fix-review-20260811-mim.md`（初审 MiM finding 1/2/3）
- `docs/reviews/phase-1-integration-validation-adjudication-20260811-codex.md`（Controller 裁决）
- `docs/reviews/phase-1-integration-corrective-fix-20260811-codex-spark.md`（corrective fix artifact）
- `docs/reviews/phase-1-docker-integration-validation-20260811-deepseek-flash.md`（Flash 74-pass Docker artifact）
- `tests/integration/investment/test_identity_repositories_postgres.py`（current test diff vs b9e5b56）

## P1-INT-FIX-01（Terra M1）: strict parser/credential/real S3 construct + head_bucket-only seam

### 裁决要求

Controller 接受 Terra M1，要求：保留 `_build_s3_store_from_settings()` 真实路径，network probe 只在 `S3FileStore.head_bucket()` 边界替换；加旧 `s3://placeholder` 负例。

### 验证

**PASS**

1. **head_bucket-only seam**：`_install_black_box_startup_stubs()` (diff line 332-345) 只替换 `sp.S3FileStore.head_bucket = _head_bucket_noop`，保留 `_build_s3_store_from_settings()` 真实路径。
2. **六键 JSON + 凭证变量**：`_build_strict_s3_object_storage_payload()` 生成包含 `backend/endpoint_url/region/bucket/access_key_env/secret_key_env` 的严格 JSON；`_setup_production_startup_env()` 同时注入 dummy 凭证变量 `DAYU_PLATFORM_S3_ACCESS_KEY` 和 `DAYU_PLATFORM_S3_SECRET_KEY`。
3. **invalid placeholder 负例**：新增 `test_production_provider_s3_placeholder_still_rejected` (diff line 477+)，验证旧 `s3://placeholder` 在 provider/PG service 动作前被 `S3SettingsError` 拒绝，哨兵断言 `_read_postgres_dsn` / `_build_production_identity_provider` / `PlatformProviderSentinel` 均未触发。

## P1-INT-FIX-02（Terra M2）: cleanup all-attempt/primary exception、close retry

### 裁决要求

Controller 接受 Terra M2，要求：改为状态化/嵌套 `try/finally`，保证 env、login、migration downgrade 都被尽力执行，且原始失败不被静默吞掉；增加 close-failure 清理证明。

### 验证

**PASS**

1. **状态化 cleanup helper**：新增 `_cleanup_production_startup_resources()` (diff line 350-400)，逐项执行 `prepared.close()` / `_cleanup_production_startup_env()` / `drop_temporary_login()` / `_migrate_down_and_assert()`，每个操作独立 try/except，收集异常到列表。
2. **primary exception 不被吞掉**：新增 `_report_cleanup_errors()` (diff line 402-430)，若 `primary_exception` 存在，通过 `add_note()` 附加 cleanup error 信息；若不存在则 raise `ExceptionGroup`。
3. **close-failure 测试**：新增 `test_production_provider_close_propagates_failure_and_still_cleans` (diff line 740+)，验证 `S3FileStore.close()` 首次抛错后，cleanup 重试 close 并完成 `schema/group roles/login` 清理。
4. **所有三目标测试 + 新增测试** 均使用 `_cleanup_production_startup_resources()` + `_report_cleanup_errors()` 模式。

## P1-INT-FIX-03（Terra M3）: wrong-role order

### 裁决要求

Controller 接受 Terra M3，要求：先迁移再创建 login，并从创建时起进入 cleanup scope。

### 验证

**PASS**

`test_production_provider_wrong_role_rejected` (diff line 557+)：

1. 先执行 `_migrate(platform_cluster, database)` (line 520)
2. 再创建 `wrong_login = create_temporary_login(platform_cluster, database, member_of="")` (line 523)
3. finally 中使用 `_cleanup_production_startup_resources(... login=wrong_login)` 确保 login 从创建起即受 cleanup 范围管理

## P1-INT-FIX-04（Terra L1）: private bare removal, TypeVar

### 裁决要求

Controller 接受 Terra L1，要求：去除私有 `_FsRepositorySet` 未初始化实例与 `_bare`/`TypeVar`；使用显式最小测试替身。

### 验证

**PASS**

1. **TypeVar 删除**：diff 中无 `ObjectStoreTestDouble`、`TypeVar`、`_bare` 残留（grep 确认为空）。
2. **私有 `_FsRepositorySet` 删除**：`_install_black_box_startup_stubs()` 使用显式 `_FakeRepositorySet()` 类 (diff line 283-290) 替代 `_bare(_FsRepositorySet)`。
3. **`_bare` 函数删除**：diff 中无 `_bare` 定义或调用。
4. **`build_fs_repository_set` stub**：返回 `_FakeRepositorySet()` (line 345)，具备 `core = None` 属性。

## MiM 裁决验证

### MiM Finding 1: 多次close仍为intentional idempotency

**裁决：non-defect，保留**

验证：`test_production_provider_wires_real_identity_service` (diff line 1385-1396) 保留了：
```python
prepared.close()
prepared.close()
```
且 `test_production_provider_close_disposes_engine_once` (line 1692-1696) 同样保留：
```python
prepared.close()
prepared.close()
assert len(dispose_calls) == 1
prepared.close()
assert len(dispose_calls) == 1
```
符合 Controller 裁决：目标测试有意多次调用 `prepared.close()` 来证明幂等性；finally 再调用是异常安全清理。

### MiM Finding 2: missing-dsn不扩

**裁决：non-defect/out-of-scope，保留**

验证：`test_production_provider_missing_dsn_safe_failure` (line 1566-1623) 仍使用 `"s3://placeholder"` (line 1598)，未更新为严格 JSON 配置。该测试目标是验证 DSN 缺失时的安全失败，在 object-store admission 之前返回（`PlatformSettingsError` 而非 `S3SettingsError`），不涉及 S3 功能。符合 Controller 裁决：missing-DSN 测试锁定最早的严格 platform settings failure，在 object-store admission 之前返回。

### MiM Finding 3: TypeVar已随bare删除

**裁决：原事实拒绝，TypeVar 已随 Terra L1 一并删除**

验证：diff 确认 `ObjectStoreTestDouble` TypeVar、`_bare` 函数均已删除，替换为显式 `_FakeRepositorySet` 类。符合 Controller 裁决。

## Docker 证据

Flash artifact §9.2 复验结果（74 passed）：

| 步骤 | 结果 |
| --- | --- |
| 1 目标类（含新增 s3 placeholder 负例 + close 抛错清理两测） | 6 passed |
| 2 完整 identity 文件 | 16 passed |
| 3 四条 Phase1 lanes | 74 passed |
| 4 残留 | 0/0/0 |
| 5 静态 | pyright 与基线一致（17 既有可能，未新增未扩散） |

## 结论

**PASS**

- P1-INT-FIX-01..04 全部验证通过，corrective fix artifact 描述与 current test diff 一致。
- MiM 3 项裁决验证通过：多次close保留、missing-dsn不扩、TypeVar随bare删除。
- Flash 74-pass Docker artifact 确认真实 PG16 容器内四条 lane 全绿、零残留。
- Open H/M/L = 0/0/0。
