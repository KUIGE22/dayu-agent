# Phase 1 Docker Integration Validation（真实容器证据）

- Plan: `docs/plans/2026-08-10-investment-platform-restoration.md`
- Scope: Phase 1（Slices 1.1–1.5）integration lanes
- Reviewer: DeepSeek-Flash（真实 Docker integration 验证 worker）
- Branch: `codex/investment-platform`
- Head: `b9e5b56`
- Mode: **只读验收，不修改 production/tests/README/plan/既有 review artifact，不启动 gateflow/phaseflow/controller，不 commit/push/PR**
- 目的：Spark（Codex）因沙箱无法访问 Colima socket 将 integration 标为环境阻塞（
  `docs/reviews/phase-1-integration-validation-20260811-codex-spark.md`）；本 worker 在本
  pane 补齐真实 Docker 证据，并独立判定是否可闭合。
- Result Status: **PASS（Spark 修复 + 本 worker post-fix Docker 验证后闭合，见文末 §9）**
- 原判定：**STOP/BLOCKED（发现 contract 缺陷，非环境问题）**，已由
  `docs/reviews/phase-1-integration-fix-20260811-codex-spark.md` 修复并在本 pane 复验。

## 1. 环境诊断（本 pane 可访问 docker/colima）

- `docker version`：Client 29.6.2 / Server 29.5.2，`Context: colima`
- `colima status`：running，arch `aarch64`，runtime docker，socket
  `unix:///Users/wsk/.colima/default/docker.sock`
- 与 Spark 的 `permission denied ... docker API` 不同：本 pane docker API 完全可访问，
  已实测 create/run/inspect/logs/stop/rm/network 全流程。

### 1.1 镜像（均为本地已存在 pinned digest，未触发任何 pull）

- PostgreSQL：
  - digest: `postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`
  - resolved: `sha256:64154d0bab...`（arm64 / linux，153082111 bytes）
- MinIO：
  - digest: `minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`
  - resolved: `sha256:14cea493d9a3...`（arm64 / linux，57548825 bytes）
- 两个 digest 均与测试文件硬编码值逐字一致（conftest.py:54 / test_fins_s3_blob_repository_minio.py:54-57）。

## 2. 执行命令与结果（全部在 `.venv` Python 3.11.15 / pytest 9.0.3）

| lane | 命令 | 结果 | 耗时 |
| --- | --- | --- | --- |
| PG16 migrations | `.venv/bin/pytest tests/integration/investment/test_platform_migrations_postgres.py -q` | **33 passed** | 13.98s |
| identity/source repos | `.venv/bin/pytest tests/integration/investment/test_identity_repositories_postgres.py -q` | **11 passed / 3 failed** | 8.02s |
| S3-MinIO blob | `.venv/bin/pytest tests/integration/investment/test_fins_s3_blob_repository_minio.py -q` | **11 passed** | 10.71s |
| workspace import | `.venv/bin/pytest tests/integration/investment/test_workspace_migration.py -q` | **14 passed** | 10.37s |

合计 **69 passed / 3 failed**。

## 3. passed 覆盖（真实依赖真值）

### 3.1 PG16 migrations lane（33/33）
- empty `upgrade -> downgrade -> upgrade` 循环、default organization 固定种子
- 13 表 schema exact（columns/type/null/default、named PK/FK/UQ/CK、**全部** physical
  indexes/predicate、RLS policy、PUBLIC/default ACL）
- PG16 `pg_auth_members` 的 `inherit_option/set_option/admin_option` 三字段独立断言
- RLS default-deny / same-tenant allow / cross-tenant reject / audit `SET ROLE` 受控
  bypass（operator NOBYPASSRLS、DML/DDL 拒绝）
- downgrade 三类 fail-closed（外部 member / active session / 外部 dependency）
- 0001 <-> 0002 循环、downgrade 外部 view 拒绝、app 对 marker/locator 无 UPDATE/DELETE
- bootstrap admission：非 superuser CREATEROLE 首个 DDL 前拒绝且零对象

### 3.2 identity/source repositories lane（11/11 passed）
- atomic company+security registration（second insert unique 冲突后 company 行不存在）
- stale `expected_version` CAS 不修改 row、optimistic conflict
- scope A 无法读写 scope B subscription、public reference 可投影、tenant setting 不泄漏
- company-target / security-target projection 不串位、nested config JSONB round-trip
- read-path schema fault（RENAME 表）稳定 `RepositoryError` 且无 DSN/SQL/候选泄漏并恢复
- subscription FK violation 映射、`_migrate_down_and_assert` 零残留

### 3.3 S3-MinIO lane（11/11）
- fresh bucket put/get/stat/list/delete、SHA 验证、seekable 流、overwrite 原子
- pagination 穷尽（1005 objects）/排序/staging 排除
- staging commit + rollback 保留旧 final、delete_entry swap 后远端删除
- SIGKILL 后 remote journal 重放两个 crash 窗口（staged / first-copy）收敛
- 双 writer lease 第二进程被拒、startup production S3 / development FS 选择
- FS/S3 同一 source bytes evidence 主文件逐字相同

### 3.4 workspace import lane（14/14）
- publish_import 单事务发布 rows exact、exact rerun no_op 且时间/版本不变
- fingerprint / row drift 稳定抛 `WorkspaceImportDriftError`
- business-key conflict fail closed、public existing exact reuse
- advisory xact lock 算法 exact、两线程 race 恰一 committed 一 no_op、外部持锁阻塞
- trigger fault injection 各阶段整次 rollback 零行、winner 终止后 loser 完整发布
- RLS unset/cross-tenant 不可见不可写、locator 无冗余 company_id
- **vertical CLI**：真实 `dayu-cli init --import-existing-workspace` 注入 PG16 fixture，
  audit/read 模型解析回原 bundle 且 legacy bytes 未改（`_tree_snapshot` 前后一致）

## 4. failures（3，同一根因族，contract 缺陷）

全部位于 `test_identity_repositories_postgres.py::TestProductionStartupBlackBox`：

- `test_production_provider_wires_real_identity_service`
- `test_production_provider_wrong_role_rejected`
- `test_production_provider_close_disposes_engine_once`

### 4.1 直接证据

单测（隔离运行）根因一致：

```
dayu.services.startup_preparation.py:721: in prepare_host_runtime_dependencies
    s3_store = _build_s3_store_from_settings(os.environ, platform_settings)
dayu/services/startup_preparation.py:658: in _build_s3_store_from_settings
    parsed = parse_object_storage_settings(env, object_storage_env)
dayu/fins/storage/s3_settings.py:179: in _parse_json_object
    raise S3SettingsError(f"环境变量 {env_name} 必须是合法 JSON") from exc
E dayu.fins.storage.s3_settings.S3SettingsError: 环境变量 DAYU_PLATFORM_OBJECT_STORAGE 必须是合法 JSON
```

- 三个测试仍在 `monkeypatch.setenv("DAYU_PLATFORM_OBJECT_STORAGE", "s3://placeholder")`
  （test_identity_repositories_postgres.py:1074/1195/1260 等）。这是 slice 1.2（commit
  `b45e0ee`）时代的占位值；当时 `startup_preparation.py` **零 S3 逻辑**（`git show
  b45e0ee:dayu/services/startup_preparation.py | grep -c "s3|S3"` = 0），该值合法。
- slice 1.4（commit `58b7dd2`，S14-CTRL-02/05）后，production+enabled 时
  `prepare_host_runtime_dependencies` 固定顺序为：load settings -> resolve paths ->
  **strict JSON 解析 S3 settings + head_bucket** -> lease -> repository_set -> provider
  -> composition。`s3://placeholder` 不是合法 JSON，`S3SettingsError` 在 provider 装配
  之前抛出，三个 black-box 测试永远到不了「真实 identity service 装配 / wrong-role
  拒绝 / close dispose 恰一次」的断言点。
- 计划文档自身确认 `s3://placeholder` 只是占位（
  `docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md:46`：”
  当前测试中的 minio://localhost:9000 与 s3://placeholder 只是未被 owner 解析的占位，
  不能升级为正式 contract“）。

### 4.2 连锁失败（role 残留）

全文件/全类运行时，第一个失败（wires）在 `prepare_host_runtime_dependencies` 抛异常，
而测试体内的 `_migrate_down_and_assert()` 位于 `finally` 块**之后**（
test_identity_repositories_postgres.py:1151），异常路径不执行 downgrade，导致
`dayu_platform_app` / `dayu_platform_audit` group role 残留在 session cluster；后续
测试在 `_migrate` 时因同名 role fail-closed：

```
E sqlalchemy.exc.ProgrammingError: (psycopg.errors.RaiseException) role dayu_platform_app already exists
```

（隔离单跑时每个失败点都是 S3SettingsError；role already exists 是 class 内执行的
二次效应，非独立根因。）

### 4.3 判定

这是 **slice 1.2 测试未随 slice 1.4 实现边界迁移的 contract 缺陷**（生产代码行为符合
S14-CTRL-05 固定 startup 顺序；测试仍在用 slice 1.2 时代的非 JSON 占位值，且异常路径
不清理 role）。unit lane（`tests/application/test_service_startup_preparation.py:348`）
对 `_build_s3_store_from_settings` 有 stub，integration black-box 无对应适配。
按交接约束「若发现代码/contract 缺陷立即停报，不修复」，本 worker 停报，不做任何修复。

## 5. 未覆盖 / residual

- 3 个 black-box 测试因上述 contract 漂移无法在真实环境验证，Phase 1 的
  `production startup 装配真实 investment_identity / wrong-role 拒绝 / close() dispose
  恰一次` 三条证据仍缺（部分由 unit lane 覆盖）。
- 未执行任何 live market / model / broker / Telegram / 用户 workspace 操作（全部禁止）。
- 未做 coverage / pyright / ruff（非本交接范围，Spark 已给静态证据：Phase1 scoped
  pyright 0 errors）。
- 未对计划文档、README、生产代码、测试代码做任何修改。

## 6. 环境诊断结论（对比 Spark）

- Spark 结论「环境阻塞，Docker daemon 权限/镜像不可用」在本 pane **不成立**：
  本 pane docker API 可用、两个 pinned digest 镜像本地已存在、四条 lane 实际起容器
  并跑完。Spark 的环境阻塞定性只适用于其沙箱，不适用于本机。
- 本 pane 实测**非环境阻塞**：主要失败是上述 contract 缺陷。

## 7. cleanup 证据（只读检查）

全部测试结束后（含失败路径）：

```
docker ps -a --filter "label=dayu-slice11.owner"   -> 空
docker network ls --filter "label=dayu-slice11.owner" -> 空
docker ps -a --filter "label=dayu.test.owner"      -> 空
git status --short -> 仅 docs/reviews/phase-1-integration-validation-20260811-codex-spark.md（untracked，既有 dirty，未改动）
```

测试容器/network/database 由 fixture owner-label 清理，零残留；未触碰任何既有容器。

## 8. 结论给 Controller

- **STOP/BLOCKED（contract 缺陷）**：Docker integration 真实证据已补齐（69 passed），
  但 `TestProductionStartupBlackBox` 3 个测试暴露 slice 1.2 测试与 slice 1.4 S3 准入
  契约的漂移（非环境问题），不能宣布 Phase 1 true-closure。
- 解除条件建议：将三个 black-box 测试迁移到 slice 1.4 契约——合法 S3 settings JSON
  （或对 `_build_s3_store_from_settings` 做 typed stub 如 unit lane），并把
  `_migrate_down_and_assert()` 纳入 `finally` 保证异常路径 role 清理；随后重跑本文件
  并复核 0 残留。
- 如需完整证据，可按 §2 命令集直接复跑；本 worker 未修改任何文件。

## 9. post-fix validation（2026-08-11，Spark 修复后复验）

Controller 指派 Spark（Codex）按 §8 解除条件修复（
`docs/reviews/phase-1-integration-fix-20260811-codex-spark.md`），本 worker 在真实
Docker 环境复验并追加一处测试桩缺陷修复（仅限该测试文件，未触碰生产代码）。

### 9.1 追加修复（测试桩）

初跑三个目标测试在 `prepared.close()` 处崩溃：
`S3FileStore.close()` 访问未初始化实例的 `self._client`（
`dayu/fins/storage/s3_file_store.py:646`，`_bare(S3FileStore)` 用 `__new__` 造出无
状态实例），崩溃点位于 `finally` 的 `_migrate_down_and_assert()` 之前，连锁造成
`dayu_platform_app` group role 残留污染后续测试。修复：新增 `_FakeObjectStore`
（no-op `close()`）替换 `_build_s3_store_from_settings` 桩返回值；删除不再使用的
`S3FileStore` 导入。属 §4 同一根因族（测试未随 slice 1.4 实现边界迁移）的收尾。

### 9.2 复验结果（colima docker，Python 3.11.15 / pytest 9.0.3）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 1 目标三测 | `pytest test_identity_repositories_postgres.py -k TestProductionStartupBlackBox` | **4 passed** |
| 2 完整文件 | `pytest test_identity_repositories_postgres.py -q` | **14 passed** |
| 3 四条 Phase1 | migrations + identity + fins_s3_minio + workspace_import | **72 passed**（原 69/3f） |
| 4 残留 | `docker ps -a/network ls --filter label=dayu-slice11.owner` | **0 / 0**；`dayu.test.owner` 0 |
| 5 静态 | `pyright` 0 errors；`ruff --select F,I` pass；`ruff default` pass；`git diff --check` clean | 全绿 |

> 注：Spark corrective patch（`phase-1-integration-corrective-fix-20260811-codex-spark.md`）
> 将 identity lane 扩为 16 项（新增 s3 placeholder 负例 + close 抛错清理两测），
> 并修复 close-propagates 测试桩（close_calls 预期 2、移除 Engine.dispose 计数）。
> 复跑后 identity 16/16、四条 Phase1 合计 **74 passed**；残留 0/0/0，pyright 与
> 基线一致（docling_core/HTTPError 既有 17 errors，未新增未扩散）。

### 9.3 结论

- 三条 black-box 证据（真实 `investment_identity` 装配 / wrong-role 拒绝 / `close()`
  dispose 恰一次）在真实 PG16 容器内闭合；Phase 1 四条 lane 74/74。
- role 残留由每个测试尾部 `_migrate_down_and_assert()` 的 downgrade 归零断言覆盖，
  容器 `--rm` 无 volume，owner 资源零残留。
- 生产代码、plan、README 均未改动；未 commit/push/PR。
- **最终状态：PASS。**
