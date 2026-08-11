# Phase 1 Integration Validation Handoff (Read-only)

- Plan: `docs/plans/2026-08-10-investment-platform-restoration.md`
- Scope: Phase 1 (Slices 1.1–1.5)
- Reviewer: Codex (read-only validation)
- Branch: `codex/investment-platform`
- Head: `b9e5b56`
- Mode: **只读验收，不修改生产/测试代码，不启动 gateflow/phaseflow/controller**
- Result Status: **STOP/BLOCKED**

## 1. 预检查（提交与工作区状态）

- 预检命令：`git status --short`
  - 结果：干净工作区（无新增修改）
- 预检命令：`git branch --show-current`
  - 结果：`codex/investment-platform`
- 预检命令：`git rev-parse --short HEAD`
  - 结果：`b9e5b56`

## 2. 先导文档与实现/评审 artifacts 采样核对

- 已读取并用于对照：
  - `docs/plans/2026-08-10-investment-platform-restoration.md`
  - `tests/README.md`
  - `docs/reviews/plan-acceptance-20260810-slice-1.1-schema-environment-codex.md`
  - `docs/reviews/plan-acceptance-20260810-slice-1.1-doc-owner-codex.md`
  - `docs/reviews/plan-acceptance-20260810-slice-1.2-frozen-slots-guard-codex.md`
  - `docs/reviews/plan-acceptance-20260810-slice-1.2-repository-provider-codex.md`
  - `docs/reviews/plan-acceptance-20260810-slice-1.3-evidence-locator-codex.md`
  - `docs/reviews/plan-acceptance-20260811-slice-1.4-s3-blob-repository-deepseek.md`
  - `docs/reviews/plan-acceptance-20260811-slice-1.4-cn-runtime-factory-allowlist-codex.md`
  - `docs/reviews/plan-acceptance-20260811-slice-1.5-workspace-import-codex.md`
  - `docs/reviews/plan-acceptance-20260811-slice-1.5-secure-closure-reader-codex.md`
  - `docs/reviews/slice-1.5-workspace-import-code-acceptance-20260811-codex.md`
  - `docs/reviews/code-review-20260811-121322.md`
  - `docs/reviews/code-review-20260811-121507-slice-1.5-final.md`

## 3. 接口覆盖与测试入口核对（真实依赖）

本阶段实际 integration 入口（按 tests/README 与当前树核对）
- `tests/integration/investment/test_platform_migrations_postgres.py`
- `tests/integration/investment/test_identity_repositories_postgres.py`
- `tests/integration/investment/test_fins_s3_blob_repository_minio.py`
- `tests/integration/investment/test_workspace_migration.py`

## 4. 集成验收执行与结果（只读）

### 4.1 PostgreSQL 16 migration / RLS / grants lane

- 命令：
  - `pytest tests/integration/investment/test_platform_migrations_postgres.py -q`
- 结果：`33 failed`（全部为 fixture/setup 阶段失败）
- 关键失败：
  - `本地缺少 pinned digest 镜像`，具体为 `postgres@sha256:64154d0bab...`

### 4.2 identity/source repositories lane

- 命令：
  - `pytest tests/integration/investment/test_identity_repositories_postgres.py -q`
- 结果：`14 failed`
- 关键失败：
  - 启动失败原因同上：缺少 pinned Postgres digest 镜像

### 4.3 S3 blob(owner) lane

- 命令：
  - `pytest tests/integration/investment/test_fins_s3_blob_repository_minio.py -q`
- 结果：`11 failed`
- 关键失败：
  - `MinIO 测试镜像缺失`
  - 具体镜像：`minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea...`

### 4.4 workspace import/composition lane

- 命令：
  - `pytest tests/integration/investment/test_workspace_migration.py -q`
- 结果：`14 failed`
- 关键失败：
  - 同样为 `postgres pinned digest` 缺失，无法完成真实迁移链路验证

### 4.5 明确失败根因的环境复测

- 命令：`docker pull postgres@sha256:64154d0bab...`
  - 结果：`permission denied while trying to connect to docker API at unix:///Users/wsk/.colima/default/docker.sock`
- 命令：`docker version`
  - 结果：Client OK / API 访问异常（权限问题）

结论：以上四条 lane 全部被“环境阻塞”，未进入真实 DB/S3 依赖验证，因此无从确认 schema、RLS、grants、repository 端到端证据。

## 5. Phase1 相关非集成 evidence

### 5.1 import-smoke 与架构边界

- 命令：`source .venv/bin/activate && pytest tests/investment/test_architecture_boundaries.py -q`
  - 结果：`151 passed`
- 命令：`source .venv/bin/activate && pytest tests/investment/test_platform_migrations.py tests/investment/test_identity_repositories.py -q`
  - 结果：`60 passed`
- 命令：`source .venv/bin/activate && pytest tests/architecture/test_dependency_boundaries.py -q`
  - 结果：`29 passed`

### 5.2 静态检查

- `ruff check dayu/investment tests/investment tests/architecture tests/integration/investment`
  - 结果：All checks passed

- 全量 `pyright`：
  - `source .venv/bin/activate && pyright`
  - 结果：17 errors（与本次验收范围无关的既有问题；主要集中在 docling_core 与 `tests/engine/test_web_tools.py`）
- Phase1 scoped `pyright`：
  - `source .venv/bin/activate && pyright dayu/investment tests/investment tests/integration/investment`
  - 结果：`0 errors, 0 warnings, 0 infos`

## 6. 风险与闭环证据分类（按用户定义）

- **失败**：integration lane 无法起容器，未产出真值执行结果。
- **缺证据**：不能确认以下项在真实依赖下运行：
  - schema/migrations RLS/grants 的行为执行输出
  - identity/source repositories 的 DB 交互行为
  - Fins locator 的持久化解析链路（受 workspace test 依赖阻塞）
  - S3-MinIO blob owner 路径与权限链路
  - 明确 workspace import composition 的端到端迁移结果
- **环境阻塞**：Docker daemon 权限/镜像访问问题属于执行环境问题，不是代码实现问题。

## 7. 按 Slice 逐项审计

### Slice 1.1（Schema/environment）
- 状态：BLOCKED（依赖容器）
- 证据：PG integration 与 migration lane 未能起服务
- residual owner：本地运行时/容器基础设施（Docker daemon + 镜像拉取权限）

### Slice 1.2（Identity repositories / frozen slots）
- 状态：BLOCKED（依赖容器）
- 证据：identity repositories lane 全量失败于 PG 镜像不可用
- residual owner：本地运行时/容器基础设施

### Slice 1.3（Evidence locator）
- 状态：BLOCKED（依赖 workspace-import integration lane）
- 证据：workspace migration lane 未能执行到代码层；未出现真实 RLS+仓储交互
- residual owner：本地运行时/容器基础设施

### Slice 1.4（S3 blob / CN runtime）
- 状态：BLOCKED（依赖 MinIO 镜像可用）
- 证据：S3-minio integration 全量失败于镜像缺失
- residual owner：本地运行时/容器基础设施

### Slice 1.5（workspace import / composition）
- 状态：BLOCKED（依赖 PG 与可复现 workspace import 环境）
- 证据：workspace migration lane 未启动；未完成 composition/startup 真实运行
- residual owner：本地运行时/容器基础设施

## 8. 结论给 Controller

- 不能闭环判断 Phase 1 true-closure。
- 当前状态应为 **STOP/BLOCKED**，因为关键 integration 入口全部受“本地环境无法访问 Docker API/镜像 pin 不可用”阻塞。
- 建议解除阻塞后，按本文件命令集优先复测。
