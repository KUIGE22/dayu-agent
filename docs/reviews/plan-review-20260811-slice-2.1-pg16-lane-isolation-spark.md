# Plan Review: Slice 2.1 PG16 lane isolation（Independent review）

## 范围
- AGENTS 指令：`/Users/wsk/workspace/dayu-agent/AGENTS.md`
- 目标基线/计划：`/Users/wsk/workspace/dayu-agent/docs/plans/2026-08-10-investment-platform-restoration.md`（对应用户口径 `target/master`）
- 本次复核文档：`/Users/wsk/workspace/dayu-agent/docs/reviews/plan-fix-20260811-slice-2.1-pg16-lane-isolation-codex.md`
- 约束核对文件：`tests/conftest.py`、`tests/integration/investment/conftest.py`、`tests/integration/investment/test_platform_migrations_postgres.py`、`tests/integration/investment/test_identity_repositories_postgres.py`、`tests/integration/investment/test_postgres_jobs.py`、`tests/inventory/test_platform_migrations.py`、`dayu/investment/storage/migrations/versions/0003_durable_jobs.py`、`tests/README.md`

## 总体结论
PASS（可执行性可评审通过）

- Open findings: High=0 / Medium=0 / Low=0
- 代码改动不被请求：未修改任何 plan/code/tests，仅新增 review artifact。

## 评审要点核验结果

### 1) 关键约束与架构边界（AGENTS）
- 已确认遵循“非 compatibility 重构式修复优先、分层边界、无兼容 wrapper、存储仓储路径约束”等主约束。
- 本次仅生成 review 文档，未触发“测试后必须更新 README”等写入约束，因此无文档同步动作需求。

### 2) conftest session cluster / cluster-global roles
- `tests/integration/investment/conftest.py` 中 `platform_cluster` 为 `scope="session"`（session 级共享 PG16 cluster），并在单会话生命周期内复用同一 cluster 与 network。
- `lifecycle_database` 以随机数据库名隔离“每次测试数据库实例”，并依赖同一 cluster，符合“同一 cluster + random db”的 lane 设计目标。
- 组角色授权链路通过 `create_temporary_login` 与 `session scoped login`，并带 `INHERIT`/`SET` 语义，体现 cluster-global role 的共享管理面，支持跨文件复用同一租户语义。
- `tests/conftest.py` 与集成 cleanup 逻辑也可见最终资源回收是按 owner 过滤在同一 cluster 范围，不存在跨 lane 泄漏清理。

### 3) migration fail-closed
- `test_platform_migrations_postgres.py` 显示 migration lane 关注点明确：升级/降级前后 schema 迁移结果、失败态对象回滚、schema 无残留规则；
- `_assert_no_platform_objects` / `_assert_schema_absent` / `_assert_schema_present` 与失败测试路径组合，已经形成“写入失败即不得残留平台对象”的明确检查闭环。
- `test_platform_migrations.py` 中对 `0003` 的 schema 契约测试存在，且复核了 table、constraint、index、grant 的精确项；当前 plan 文档将其标注为 PG/CLI owner 下原始 contract，不列为 Slice2.1 的新增阻塞项，符合“非本 plan 范围不打断当前 lane 目标”的原则。

### 4) 三条独立 pytest 的必要性与充分性
- 必要性：
  - `test_platform_migrations_postgres.py`：聚焦迁移可用性与迁移失败回滚（lane 隔离的最小稳定层）。
  - `test_identity_repositories_postgres.py`：聚焦 identity 与 durable_jobs 两 service 组合语义，验证身份与仓储 role/可达性边界。
  - `test_postgres_jobs.py`：聚焦 durable_jobs 并发、SKIP LOCKED 与 tenant 隔离。
  - 这三者职责互补，分别覆盖迁移、身份路由、作业执行层，不可由单条命令替代。
- 充分性：
  - 这三组命令能在独立进程里验证不同层面的 lane 冲突与隔离，且均使用真实 PG16 集成环境；与共享 session cluster 的设计一致。
  - 仍有“跨文件语义的一次性组合行为”不在单元级别显式建模，属于架构层“更高层集成”边界，不是当前 plan 强制覆盖点；因此不构成阻塞。

### 5) cross-file 问题风险
- 当前 lane 文档与测试引用统一指向同一共享 cluster 会话、同一 migration schema 入口与同一角色/租户约定；未见“测试之间互相绕过 fixture 入口”的显性路径。
- `tests/README.md` 对 integration lane 的说明与本次 plan 约束一致（PG16、session cluster、单数据库生命周期隔离思想），未发现文档与计划之间的冲突。
- 结论：未发现可作为阻塞的跨文件一致性问题。

### 6) 两个 unused imports 的证据
- plan 文档已明确：
  - `_counted_build_production_identity_provider` 仅作为 `PlatformOwnedLifecycleProtocol` / `PlatformCompositionProviderProtocol` 两处类型路径中的桥接引用；
  - wrapper 删除后，两个引用同时失效，不可保留 import；该行为是清晰、局部且“删而非兼容保留”的可维护处理。
- 该部分与本 review 范围不属于未处理缺陷；已有对应变更方向与清理闭环（仅移除 wrapper 与对应 import）符合“不引入 compatibility shim”的规则。

### 7) 0003 exact schema owner 处理边界
- `0003_durable_jobs` 与迁移测试已表明 owner/constraint/index/grant 细项是既定 owner 合约；
- Plan 将该项标记为“既存 owner 合同”而非 PG16 lane 隔离新增问题，且未要求在本切片内重写 owner 定义，符合职责边界。

### 8) 真实退出码 / STOP / hash
- plan 中给出三条独立命令，均是完整 `pytest ... -q` 形式，未要求 `-k` 子集或“短路式遮蔽”；
- 计划明确要求以真实退出码/真实执行失败停止，且冻结 WIP hash 作为 `STOP` 条件之一（hash 漂移即中断），方向正确并与可复现实验一致。
- 本次 review 不执行命令，因此不能在此确认实际通过/失败，但这属于执行层验收点，不影响 plan 可生成性判定。

## 结论（code-generation readiness）
- 该计划文本与约束链路在本次范围内满足 code-generation readiness：
  - scope 一致、执行 lane 明确、失败退出条件完整、跨模块接口约束可追踪。
  - 未发现阻塞性缺陷（H/M/L）。

## PASS/FAIL
- PASS: `0`
- FAIL: `0`

## Open findings
- High: `0`
- Medium: `0`
- Low: `0`
