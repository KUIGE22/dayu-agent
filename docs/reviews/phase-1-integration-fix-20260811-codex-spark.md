# Phase 1 Integration Fix（Codex Spark）

- Controller: Codex Spark
- Branch / HEAD: `codex/investment-platform` / `b9e5b56`
- Artifact Status: **READY FOR DOCKER VALIDATION**
- Scope: `tests/integration/investment/test_identity_repositories_postgres.py`
- Timestamp: 2026-08-11

## 变更目标

修复 `TestProductionStartupBlackBox` 的 3 个失败测试：

- `test_production_provider_wires_real_identity_service`
- `test_production_provider_wrong_role_rejected`
- `test_production_provider_close_disposes_engine_once`

目标是让三测通过现有 PG 断言，并保持现有 platform provider / role admission / identity service / Engine 生命周期为真实路径，仅隔离 startup 外部依赖边界。

## 补丁内容

### 修改文件

- `tests/integration/investment/test_identity_repositories_postgres.py`

### 关键变更

1. 新增私有 helper（仅文件内）：
   - `_build_strict_s3_object_storage_payload()`：构造符合严格契约的 6-key JSON（`backend/endpoint_url/region/bucket/access_key_env/secret_key_env`）。
   - `_setup_production_startup_env()`：注入 `DAYU_PLATFORM_*` 启动环境及 dummy 凭证变量。
   - `_cleanup_production_startup_env()`：清理上述环境变量。
   - `_install_black_box_startup_stubs()`：统一安装 startup 外部边界替身：
     - `_build_s3_store_from_settings` -> `_bare(S3FileStore)`
     - `acquire_writer_lease` -> `_FakeWriterLease`
     - `build_fs_repository_set` -> `_bare(_FsRepositorySet)`
     - `resolve_startup_paths` / `resolve_host_config` / `DefaultFinsRuntime.create` / `recover_host_startup_state` / `Host` / `HostStore`

2. 三个失败测试改造：
   - 使用上面 helper 进行环境与 stub 设置。
   - 把 cleanup（`prepared`/`drop_temporary_login`/env/migration）放入 finally。
   - wrong-role 与 close 场景补齐 `_migrate_down_and_assert` 的最终清理。
   - 保持角色 admission 与 identity service/engine 生命周期实路径不被 stub。

## 静态证据

### 变更 diff（关键）

```bash
apply_patch
git diff -- tests/integration/investment/test_identity_repositories_postgres.py | sed -n '1,260p'
```

### 质量检查

```bash
ruff check tests/integration/investment/test_identity_repositories_postgres.py tests/application/test_service_startup_preparation.py
# All checks passed! 0 errors

pyright tests/integration/investment/test_identity_repositories_postgres.py
# Passed: no errors

git diff --check
# no whitespace errors
```

### 测试/collection（无需 Docker）

```bash
pytest --collect-only tests/integration/investment/test_identity_repositories_postgres.py -q
# Collected 14 items

pytest -q tests/integration/investment/test_identity_repositories_postgres.py \
  -k 'production_provider_wires_real_identity_service or production_provider_wrong_role_rejected or production_provider_close_disposes_engine_once'
# 3 selected, 11 deselected, but skipped by local cluster bootstrap
defect: PlatformIntegrationError: 本地缺少 pinned digest 镜像，请先手动 docker pull postgres@sha256:64154d0babcb
```

## 风险与结论

- 现阶段测试修改与静态校验已完成。
- 三个黑盒测试的运行受本地 pinned docker 镜像缺失限制（环境限制），需在可用 Docker 的验证环境执行。
- 生产逻辑无改动，仅增加测试级别的协议一致性桩，保持 `production startup` 真实 DB/角色路径。

## post-fix validation（DeepSeek-Flash，2026-08-11 追加，不改写上述事实）

### 追加修复（仅该测试文件内）

真机 Docker 验证中 `prepared.close()` 崩溃：`_build_s3_store_from_settings` 桩返回
`_bare(S3FileStore)`（`__new__` 未初始化），`S3FileStore.close()` 访问 `self._client`
抛 `AttributeError`（`dayu/fins/storage/s3_file_store.py:646`），且该崩溃发生在
`finally` 的 `_migrate_down_and_assert()` 之前，连锁造成 cluster 级 role 残留
（`role dayu_platform_app already exists`）污染后续测试。修复：

- 新增模块级 `_FakeObjectStore`（no-op `close()`），替换 `_build_s3_store_from_settings`
  桩的返回值为 `_FakeObjectStore()`；
- 移除不再使用的 `S3FileStore` 导入。

### 验证命令与结果（本 pane，colima docker 可用）

```bash
# 1) 三个目标测试
pytest tests/integration/investment/test_identity_repositories_postgres.py -q \
  -k 'TestProductionStartupBlackBox'                       # 4 passed（含 missing_dsn）
# 2) 完整文件
pytest tests/integration/investment/test_identity_repositories_postgres.py -q
                                                           # 14 passed
# 3) 四条 Phase1 integration 全量
pytest tests/integration/investment/test_platform_migrations_postgres.py \
  tests/integration/investment/test_identity_repositories_postgres.py \
  tests/integration/investment/test_fins_s3_blob_repository_minio.py \
  tests/integration/investment/test_workspace_migration.py -q
                                                           # 72 passed
# 4) 残留检查
docker ps -a --filter "label=dayu-slice11.owner"           # 0
docker network ls --filter "label=dayu-slice11.owner"      # 0
docker ps -a --filter "label=dayu.test.owner"              # 0
# 5) 静态
pyright tests/integration/investment/test_identity_repositories_postgres.py
                                                           # 0 errors
ruff check --select F,I tests/integration/investment/test_identity_repositories_postgres.py
                                                           # All checks passed!
git diff --check                                           # clean
```

### 结论

- **PASS**：修复后 72 passed（原 69 passed / 3 failed），三条 Phase 1 证据（真实
  investment_identity 装配 / wrong-role 拒绝 / close dispose 恰一次）在真实 PG16
  容器内闭合；owner 容器/网络/role 零残留。
- 生产代码、plan、README 均未改动。
