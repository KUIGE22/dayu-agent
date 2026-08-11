# Code Review

## Scope

- Mode: current changes（只读 Phase 1 integration fix review）
- Branch or PR: `codex/investment-platform`（workspace HEAD `b9e5b56`）
- Base: `b9e5b56`
- Review time: 2026-08-11 12:53:55 CST
- Output file: `docs/reviews/phase-1-integration-fix-review-20260811-terra.md`
- Included scope:
  - `AGENTS.md`；
  - `docs/reviews/phase-1-integration-validation-adjudication-20260811-codex.md`；
  - `docs/reviews/phase-1-integration-fix-20260811-codex-spark.md`；
  - `docs/reviews/phase-1-docker-integration-validation-20260811-deepseek-flash.md`；
  - 相对 `b9e5b56` 的 `tests/integration/investment/test_identity_repositories_postgres.py` 全部未提交 diff；
  - 真实调用链：`dayu/services/startup_preparation.py`、`dayu/investment/config.py`、S3 settings、PG integration fixture。
- Excluded scope: 未变更生产代码、其它 Phase 代码、live/model/broker；未改动 production/tests/plan/既有 artifact。
- Parallel review coverage: 无。

## Findings

### 1-未修复-中-S3 严格 admission 被替身置于其上层而没有进入真实解析分支

- **入口/函数**: `TestProductionStartupBlackBox` 三个目标测试经 `prepare_host_runtime_dependencies()` 的 production S3 startup 分支。
- **文件(行号)**: `tests/integration/investment/test_identity_repositories_postgres.py:414-418, 1280-1289, 1346-1356, 1483-1492`；`dayu/services/startup_preparation.py:639-668, 705-724`；`dayu/investment/config.py:271-304`。
- **输入场景**: `DAYU_PLATFORM_OBJECT_STORAGE` 被回退为旧的 `s3://placeholder`、JSON 缺 key/多 key、凭证变量缺失，或严格 S3 解析链发生回归。
- **实际分支**: `load_platform_settings()` 仅把非空值记录为 `object_storage_env` 名称；测试随后将 `_build_s3_store_from_settings()` 整体替换为 `_FakeObjectStore()`，所以执行路径从 `prepare_host_runtime_dependencies():721` 直接跳过 `parse_object_storage_settings()`、`read_credentials()`、`S3FileStore(...)` 与 `head_bucket()`。
- **预期行为**: 本次修复的三个 black-box 测试应以严格有效的 S3 配置越过真实的 strict-admission 逻辑，只在实际网络 I/O 边界替身，从而证明它们没有再次依赖失效的 `s3://placeholder` 契约。
- **实际行为**: `_build_strict_s3_object_storage_payload()` 虽生成了正确的六键 JSON，但该值在这三测中从不被 JSON parser 消费。将值改回 `s3://placeholder` 后，当前测试仍会通过这一 startup 段；原 P1-INT-02 所修复的契约漂移因此没有由目标黑盒测试防回归。
- **直接证据**: `load_platform_settings()` 在 `config.py:300-303` 只调用 `_read_optional_env_name()`，该函数只判断值是否非空；真实严格解析只在 `_build_s3_store_from_settings():658-667`。而测试的 `monkeypatch.setattr(sp, "_build_s3_store_from_settings", ...)`（测试文件 `414-418`）替换了含解析、凭证读取和 network probe 的整个函数。
- **影响**: 三个测试仍能证明真实 PG provider/role/service/Engine 分支（未替换 `_default_provider_or_fail`、`_build_production_identity_provider` 或 `Engine.dispose`），但不能证明 strict S3 env 已被接受。72 Docker PASS 是支持性执行证据，不能弥补该测试对未来 strict-admission 回归的盲区；不满足裁决 artifact 的“严格合法配置 + 在真实网络 I/O 边界使用替身”解除条件。
- **建议改法和验证点**: 保留真实 `_build_s3_store_from_settings()`；只替换 `S3FileStore.head_bucket()` 为有签名的 no-op 测试替身（必要时以真实构造出的 `S3FileStore.close()` 释放 client）。这样仍执行 strict JSON、六个精确 key、凭证变量读取和 `S3FileStore` 构造，而不访问网络。增加一个与三测同链路的负例，确认 `s3://placeholder` 在 provider/role 之前稳定失败；再重跑三测、完整 identity 文件及四 lane。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-中-成功启动后的 close 异常会再次短路环境、login 与 migration 清理

- **入口/函数**: `test_production_provider_wires_real_identity_service()` 与 `test_production_provider_close_disposes_engine_once()` 的 `finally`；wrong-role 测试使用同一线性 teardown 形态。
- **文件(行号)**: `tests/integration/investment/test_identity_repositories_postgres.py:1301-1306, 1359-1364, 1498-1504`；`dayu/services/startup_preparation.py:206-228`。
- **输入场景**: `prepared.close()` 里任一 owned resource 的 `release()`、S3 `close()` 或 platform lifecycle `close()` 抛异常；或 `drop_temporary_login()` 抛异常。
- **实际分支**: 三处 `finally` 均顺序执行 `prepared.close()`、env cleanup、`drop_temporary_login()`、`_migrate_down_and_assert()`，但没有嵌套 `finally`/独立 cleanup guard。首个抛出的异常会直接离开 finally，后续语句不执行。
- **预期行为**: 无论 startup、断言或 close 何处失败，测试都必须尽力释放已取得资源，至少继续执行临时 LOGIN 删除和 migration downgrade 的零残留断言，不能再次污染共享 cluster。
- **实际行为**: 当前 `_FakeObjectStore.close()` 为 no-op，仅消除了先前已知的一个 close 异常；teardown 的控制流本身仍不保证 cleanup 可达。例如 `PreparedHostRuntimeDependencies.close()` 的源码按顺序调用 lease、S3 store、platform lifecycle（`startup_preparation.py:223-228`），前一项异常即阻止后续资源关闭；测试 `finally` 中该异常又阻止 env、LOGIN、schema/group role 的清理。`drop_temporary_login()` 的异常同样会阻止 `_migrate_down_and_assert()`。
- **直接证据**: 三个 finally 没有任何围绕 `prepared.close()` 或 `drop_temporary_login()` 的 `try/finally`（上述测试行号）。此前 Flash artifact §9.1 已实际记录过 S3 close 异常导致 downgrade 不可达和 role 残留；当前改动替换具体触发器，但未改变该线性异常传播路径。
- **影响**: 共享 PG16 cluster 可遗留 `dayu_platform_app`/`dayu_platform_audit` 或临时 LOGIN，随后测试可能以 `role already exists` 连锁失败，且失败是否出现取决于前一测试的资源关闭错误。该风险正是 Phase 1 closure 明确要求消除的污染路径。
- **建议改法和验证点**: 用一个测试专用、状态显式的资源清理 helper 或嵌套 `finally` 表达依赖顺序：关闭 prepared 后无论是否异常都清环境；删除已创建 login 后无论是否异常都对已成功迁移的数据库 downgrade/assert。用布尔状态记录“已迁移/已创建 login”，并新增 close 抛异常的 failure-path 测试，随后查询 PG catalog 证明 schema、两 group roles 与临时 LOGIN 均为零。保留原始测试失败作为主异常，并将 cleanup 异常明确链式报告。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### 3-未修复-中-wrong-role 测试在 migration 之前创建 cluster-wide LOGIN，migration 失败时无清理路径

- **入口/函数**: `test_production_provider_wrong_role_rejected()` 的资源获取顺序。
- **文件(行号)**: `tests/integration/investment/test_identity_repositories_postgres.py:1337-1345`；`tests/integration/investment/conftest.py:573-587, 632-673`。
- **输入场景**: `create_temporary_login()` 已成功，而随后 `_migrate()` 因 migration admission、数据库状态或基础设施异常失败。
- **实际分支**: 测试先创建 wrong-role LOGIN（`1338-1342`），再在 `try` 块外调用 `_migrate()`（`1343`）；只有 migration 成功后才进入含 `drop_temporary_login()` 的 finally。
- **预期行为**: migration 应先建立它拥有的 app/audit group role；wrong-role LOGIN 应在 migration 成功后创建，并且从创建时起被 cleanup 范围覆盖。
- **实际行为**: migration 抛出时 finally 尚未建立。`lifecycle_database` 的 fixture teardown 只 `DROP DATABASE ... WITH (FORCE)`（conftest `670-673`）；临时 LOGIN 是 cluster-wide role，只有 `drop_temporary_login()`（`573-587`）会删除，因此会遗留在共享 cluster。
- **直接证据**: 资源创建和 `_migrate()` 的位置均早于 `try:1345`；fixture 不枚举或删除临时 role。migration 的职责是创建 group roles，故先 migrate 再创建 wrong-role login 也符合资源依赖顺序。
- **影响**: 迁移失败后的 cluster 污染与本次修复要防止的 role 残留同类；随机 role 名降低碰撞概率，但不改变零残留契约失效。
- **建议改法和验证点**: 先迁移，再创建 `wrong_login`，并把 migration/login acquisition 纳入第 2 项所述的状态化 finally；注入 migration 失败后查询 `pg_roles` 验证无以该测试创建的 LOGIN 和无 slice group role 残留。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 4-未修复-低-测试替身依赖私有未初始化 concrete 类型，扩大了与 Fins 内部的耦合

- **入口/函数**: `_install_black_box_startup_stubs()`。
- **文件(行号)**: `tests/integration/investment/test_identity_repositories_postgres.py:22, 332-345, 424-432`。
- **输入场景**: `prepare_host_runtime_dependencies()` 在 `DefaultFinsRuntime.create()` 之前新增对 repository set 的属性访问，或私有 `_FsRepositorySet` 结构变动。
- **实际分支**: 测试直接导入私有 `_FsRepositorySet`，通过 `__new__` 构造未初始化对象；随后又将 `DefaultFinsRuntime.create()` 替换为返回 `None`，所以该对象没有被真实按其契约消费。
- **预期行为**: 黑盒测试应以最窄、显式协议替身隔离非目标 Fins 边界，且不依赖私有 concrete implementation。
- **实际行为**: `_bare()` 的 `TypeVar` 只保证返回传入的任意 class 实例，不表达 file/repository 协议；测试与 `dayu.fins.storage` 私有实现绑定，新增启动内部访问时可能以无关的 `AttributeError` 失败。
- **直接证据**: 私有导入在 `22`；无初始化构造在 `332-345`；`build_fs_repository_set` 返回该对象而 `DefaultFinsRuntime.create` 同时被 stub 为 `None`（`424-432`）。
- **影响**: 当前三条目标断言不依赖该对象，故不否定已有 PG provider、role admission、service registration 和 Engine lifecycle 证据；但测试维护性与边界隔离较弱。
- **建议改法和验证点**: 使 Fins startup 的 test seam 接受稳定的窄 protocol，或将 Fins/runtime 相关 stubs 收敛为一个具备显式最小契约的测试 helper，去除私有 `_FsRepositorySet` 和 `__new__`。验证三测仍只隔离 S3 network/Fins/Host 外部边界，不替换 platform provider。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无阻碍本结论的问题。当前本机没有固定 PostgreSQL 16 digest，三个目标测试在 cluster fixture 创建前报 `本地缺少 pinned digest 镜像`；因此未能独立复现 Flash artifact 的 Docker 72/72。未下载镜像，以避免超出只读 review 的必要范围。

## Residual Risk

- Flash Docker artifact §9 报告的 72/72、零 owner container/network 与静态检查，是当前补丁通过真实 PG16 目标分支的重要支持证据；本审查也静态确认测试未 stub PG provider 构建、role admission、`investment_identity` 注册/调用或 `Engine.dispose`，故这些证据不是同-builder self-test 或虚假 identity 黑盒。
- 但 Docker 成功仅说明当前 happy path；第 1–3 项异常和 strict-admission 回归面没有被该测试实现持续覆盖。因此 open H/M/L 为 **H=0、M=3、L=1**，结论为 **FAIL**，不支持 Phase 1 closure。
- 本机执行：`pyright tests/integration/investment/test_identity_repositories_postgres.py` 为 0 errors；`ruff check` 与 `git diff --check` 通过。目标 Docker 测试未执行到测试体，不将该环境限制记为产品或补丁失败。

## Conclusion

**FAIL** — open H/M/L：**0 / 3 / 1**。在第 1–3 项修复并以真实 Docker 复验三测、完整 identity 文件、四条 Phase 1 lanes 及 PG catalog 零残留前，不应将 Phase 1 标为 accepted。
