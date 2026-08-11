# Slice2.1 Architecture Evidence Inventory（2026-08-11）

## 1. 输入依据
- `AGENTS.md`（项目约束与交付规则）
- `docs/plans/2026-08-10-investment-platform-restoration.md`（Slice2.1 纲要）
- `docs/reviews/phase-1-integration-acceptance-20260811-codex.md`
- `docs/reviews/plan-acceptance-20260810-074424-codex.md`
- 当前源码与测试（仅读）

## 2. dayu.host run/session/pending/outbox/lane/protocols/recovery 现状

### 2.1 Run
- 模块：
  - `dayu/host/run_registry.py`
  - `dayu/host/host.py`
  - `dayu/host/host_store.py`
- 关键符号：
  - `RunState`（`RUNNING/SUCCEEDED/FAILED/CANCELLED/UNSETTLED`）
  - `RunRecord` / `RunStateTransition`
  - `RunRegistry.*`（如 `upsert_run`,`complete_run`,`fail_run`,`cancel_run`,`cleanup_orphan_runs`）
- 状态机：
  - 活动态：`RUNNING`
  - terminal：`SUCCEEDED/FAILED/CANCELLED`
  - 回退态：`UNSETTLED`（用于异常收敛）
- recovery 关联：
  - 孤儿/陈旧 run 回收在 `RunRegistry.cleanup_orphan_runs()`。
  - 回收依据为 `host owner` 存活检测与运行时间阈值，结合数据库内状态。

### 2.2 Session
- 模块：
  - `dayu/host/session_registry.py`
  - `dayu/host/host.py`
  - `dayu/host/host_store.py`
- 关键符号：
  - `SessionState`（`ACTIVE/CLEARING/CLEARING_FAILED/CLOSED`）
  - `create_or_update_session`,`ensure_session_active`,`close_session`,`is_session_closed` 等
- 状态机：
  - `ACTIVE` 可接收新消息
  - `CLEARING` 作为关闭前屏障
  - `CLOSED` 终止该会话
  - `CLEARING_FAILED` 回退态，允许显式复位与重试路径

### 2.3 Pending Turn
- 模块：
  - `dayu/host/pending_turn_store.py`
  - `dayu/host/executor.py`
  - `dayu/host/host.py`
- 关键符号：
  - `PendingConversationTurnState`
    - `ACCEPTED_BY_HOST`
    - `PREPARED_BY_HOST`
    - `SENT_TO_LLM`
    - `RESUMING`
  - `resume_lease_id`、`pre_resume_state`
  - `record_resume_attempt`、`release_resume_lease`、`acquire_resume_lease`
- 可复用边界：
  - 同一 turn 的 resume lease 可被单 owner 持续持有并在恢复期间可重入
  - 与 run 状态无关但由 run owner + db CAS 约束同步
- 不可复用边界：
  - `pre_resume_state` 变更需 CAS（乐观并发）保护；陈旧持有不允许越权更新

### 2.4 Reply Outbox
- 模块：
  - `dayu/host/reply_outbox_store.py`
  - `dayu/host/host.py`
- 关键符号：
  - `ReplyOutboxState`
    - `PENDING_DELIVERY`
    - `DELIVERY_IN_PROGRESS`
    - `DELIVERED`
    - `FAILED_RETRYABLE`
    - `FAILED_TERMINAL`
  - `claim_reply_for_delivery`,`mark_delivered`,`mark_failed`,`cleanup_stale_deliveries`
- 可复用边界：
  - 一条 delivery 可以在 `PENDING_DELIVERY` 阶段被多执行者争抢，`claim` 成功后独占处理
- 不可复用边界：
  - `DELIVERY_IN_PROGRESS` 仅在有效 lease 下可更新状态，避免重复侧写

### 2.5 Lane（并发槽/permit）
- 模块：
  - `dayu/host/concurrency.py`
  - `dayu/host/host.py`
- 关键符号：
  - `Lane`（可执行槽名称语义）
  - `SQLiteConcurrencyGovernor`
  - `acquire_many`
  - `cleanup_stale_permits`
- 特性：
  - 单事务内获取多个 permit，基于 SQLite transaction 实现原子性
  - 通过 `owner_pid/owner_process_start_time/owner_boot_id` 做所有权核验

### 2.6 Protocols（服务边界）
- 模块：
  - `dayu/host/protocols.py`
- 核心协议：
  - `SessionOperations`
  - `RunAdministration`
  - `HostGovernance`
  - `PendingTurn`
  - `ReplyOutbox`
  - `HostAdminOperations`
- 设计边界：
  - 仅定义 Host 对外可依赖接口；上层仅依赖协议，不依赖实现细节

### 2.7 Recovery（主流程）
- 模块：
  - `dayu/services/startup_recovery.py`
  - `dayu/services/startup_preparation.py`
  - `dayu/host/host.py`
  - `dayu/host/run_registry.py`
- recovery 动线：
  - `recover_host_startup_state()` 在启动时执行 orphan run / stale permit / stale pending / stale outbox 的清理
  - Host run 生命周期中在取消/失败场景会触发 pending turn 与 outbox 的清理/状态归位
- 事务边界：
  - 以 Host 侧 SQLite 为主，恢复逻辑在启动时可失败软降级（non-fatal），并发与超时清理以告警为主

## 3. transaction owner 与 ownership 边界
- 主要 owner 识别符：
  - `dayu/host/concurrency.py` / `dayu/host/host_store.py`
  - tuple：`owner_pid`, `owner_process_start_time`, `owner_boot_id`
- 可复用边界：
  - 同一 process 生命周期内可复用 owner token 执行 lease 检测、permit 重入与 resume/release
- 禁止复用边界（must-stop）：
  - 旧进程崩溃后不得沿用旧 owner token 重写 stale 项目（通过 owner 校验 + stale 清理）
  - 不可将 business key（run_id / session_id / tenant）放到协议 `extra payload`，必须通过显式字段

## 4. current investment PostgreSQL 约定

### 4.1 Composition/Provider
- 关键文件：
  - `dayu/investment/composition.py`
  - `dayu/investment/storage/db.py`
  - `dayu/investment/storage/protocols.py`
- 组成约束：
  - composition 仅构造 provider，不下沉底层仓储细节给上层
  - 数据仓储接口通过协议抽象隔离

### 4.2 Provider / Repository / Session Scope
- 关键文件：
  - `dayu/investment/storage/postgres_identity.py`
  - `dayu/investment/storage/postgres_workspace_import.py`
  - `dayu/investment/storage/db.py`
- 显式 tenant scope：
  - `TENANT_CONTEXT_SETTING` 与 session-level setter（`_with_identity_scope`）
- 约定：
  - 不使用 `create_all` 建表；采用 migration 管线初始化 schema
  - identity/source/workspace_import 的事务边界彼此独立、可替换

### 4.3 Migrations conventions
- 关键文件：
  - `dayu/investment/storage/migrations/*`
  - `tests/integration/investment/test_workspace_migration.py`
  - `tests/integration/investment/test_platform_migrations_postgres.py`
- 约束：
  - 每次 schema 变更应作为 migration 插件进入 init 链路（当前任务为只读盘点，未见 active dual-write 新增 schema）

## 5. startup composition / close lifecycle
- 关键文件：
  - `dayu/startup/platform.py`
  - `dayu/services/startup_preparation.py`
  - `dayu/services/startup_recovery.py`
- 启动序列（抽象）：
  1. 载入配置与路径（含外部依赖检查）
  2. 构建 Fins 运行时与 identity/provider
  3. 构建 host 依赖与 protocol 实例
  4. 执行 startup recovery（best effort）
  5. 返回 `PreparedHostRuntimeDependencies`（含 close hooks）
- 关闭序列（抽象）：
  - Host writer permit lease 归还
  - S3/外部存储关闭
  - platform 生命周期关闭
- 关键约束：
  - 关闭必须 one-shot，避免重复关闭抛硬异常

## 6. tests 证据（并发/lease/idempotency/claim/retry/cancel/recovery）

### 6.1 并发
- `tests/application/test_concurrency.py`
- `tests/application/test_host_executor_lane_stacking.py`
- `tests/application/test_host_store.py::TestConcurrentReadWrite`

### 6.2 Lease
- `tests/application/test_pending_turn_store.py`
- `tests/application/test_pending_turn_store_cross_process.py`
- `tests/application/test_reply_outbox_store.py`

### 6.3 Idempotency
- `tests/application/test_pending_turn_store.py`
- `tests/application/test_reply_outbox_store.py::test_sqlite_reply_outbox_concurrent_submit_same_key_is_idempotent`
- `tests/application/test_host_clear_session_history.py::test_clear_is_idempotent`
- `tests/application/test_host_cancel_run_and_settle.py::test_cancel_run_and_settle_is_idempotent_on_already_cancelled`

### 6.4 Claim / Retry / Cancel / Recovery
- Claim：`test_pending_turn_store*`, `test_reply_outbox_store*`
- Retry：`tests/application/test_host_executor.py`, `tests/application/test_reply_outbox_store.py`
- Cancel：`tests/application/test_host_cancel_run_and_settle.py`
- Recovery：
  - `tests/application/test_run_registry.py::TestCleanupOrphanRuns`
  - `tests/application/test_host_admin_service.py::test_recover_host_startup_state_*`
  - `tests/application/test_service_startup_preparation.py::test_prepare_host_runtime_dependencies_runs_unified_startup_recovery`

## 7. Slice2.1 新增/修改清单（按源码边界）

### 7.1 计划新增（按现有纲要）
- `dayu/host/job_contracts.py`
  - 新增 durable job contracts（新增 API 面，需与 protocols 与 service 对齐）
- `dayu/host/job_service.py`
  - 新增 durable job 运行时 service（受 host orchestration 调度）
- `dayu/host/protocols.py`
  - 扩展新增 job contracts 对应 protocol（避免服务直接依赖实现）
- `dayu/investment/storage/postgres_jobs.py`
  - 新增 PG repository/provider（持久化 job 元信息）
- `dayu/investment/composition.py`
  - 注入 new postgres_jobs 的 provider 绑定
- `dayu/startup/platform.py`
  - compose path 接入 job 组件
- `dayu/services/startup_preparation.py`
  - 将 job 依赖注入 host runtime lifecycle
- `dayu/investment/storage/migrations/*`（migration 插件）
  - 新增 job schema 与租户约束
- 相关测试目录：
  - `tests/integration/investment/`（PG+tenant+迁移）
  - `tests/application/`（run/session/pending/outbox + job protocol）

### 7.2 真实 call-graph（目前可落地）DAG
```text
CLI/服务入口
  -> prepare_host_runtime_dependencies (tests: test_service_startup_preparation)
    -> build_platform_composition
    -> host runtime 组装（protocols/stores/governance）
    -> recover_host_startup_state (best effort)
    -> Host runtime 服务启动
      -> executor/pending_turn_store/reply_outbox_store/concurrency
      -> run_registry/session_registry
```

### 7.3 Slice2.1 对现有边界的直接改造方向
- 从现有 HostStore（session/run/pending/outbox）不触发 PG dual-write
- 新增 PG job 仅承载 durable job layer 的 recovery 查询与恢复前提证据
- Host 与 job 跨 Store 通过 `query-before-retry` 做补偿关联（不做同事务联动）

## 8. cross-store Host run correlation 不 dual-write 可实现边界与已知 gap
- 可实现边界（在现有约束下）：
  - 可在启动/恢复路径使用 `run_id`/`session_id` 作为 correlation key 做只读回查
  - Recovery 可基于 Host SQLite 状态触发 PG 侧重放
  - 跨进程恢复时仅在缺失 Host 主体时采用回退查询，不要求同步提交
- 已知 gap（未闭环）：
  - Host 与 PG 的统一全局 transaction owner ID 并无已实现强一致映射
  - 失败窗口期内，PG 侧已观察到 run event 与 Host state 可能短期不一致（属于 plan 预期的 query-before-retry 风险）
  - 现阶段无统一幂等语义桥接层将 host run event 与 PG job 事件完全原子化（与 Slice2.1 目标一致：故意不双写）

## 9. 必须停报项（Must Stop）
1. 不允许实现 Host run 与 PostgreSQL durable job 的 dual-write（与 phase1 acceptance、plan 条款冲突）
2. 不允许在协议层做兼容 wrapper/透传以掩盖新旧语义差异（违反 AGENTS 的兼容性禁令）
3. 不允许新增无 owner 校验的 lease 更新（会破坏 stale 回收与 recover 安全）
4. 不允许跨层直接依赖具体仓储实现（保持 `UI -> Service -> Host -> Agent` 和 protocols 边界）
5. 不允许在启动恢复中强制 fail-fast（当前 recovery 为 best-effort，异常应记录并继续）

## 10. 风险与下一步验证建议
- 风险：
  - Slice2.1 未实现文件尚未存在，当前仅为“新增实现的前置盘点”状态；必须在补齐后补齐并发/lease/重放/恢复的端到端测试
- 下一步（按顺序）：
  1. 落地 `postgres_jobs` 与 `job_*` 协议
  2. 注入 composition/startup
  3. 用最小变更测试 `query-before-retry` 的 recover 路径
  4. 严格保持 run 与 PG job 不 dual-write 的约定
