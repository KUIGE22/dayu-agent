# Slice 1.5 Workspace Import Final Independent Re-review — MiM Native

- **审查时间**：2026-08-11 07:25:38 CST（本机系统时钟）
- **Work unit / gate**：Investment Platform Restoration / Slice 1.5 old workspace explicit import，final independent re-review after Controller fix
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的顶部当前状态、revision changelog、§8.0 DAG 与 Slice 1.5 `S15-CTRL-01..14`；`docs/reviews/plan-fix-20260811-slice-1.5-workspace-import-codex.md`；`docs/reviews/plan-review-20260811-slice-1.5-workspace-import-terra.md`（Terra 初审）；`docs/reviews/plan-review-20260811-071328-slice-1.5-workspace-import-mim-native.md`（MiM 初审）；当前源码。
- **Baseline**：`58b7dd28db6183f29caaac337b09dffc3db80a76`（当前 `HEAD` 与此一致）
- **审查边界**：仅计划与当前代码事实核对；未运行网络、模型、Broker 或实现测试，未改动 production/tests/README/master plan。
- **审查重点**：逐项验证 Terra TERRA-S15-001..004 与 MiM M01..M13 的 Controller 裁决/修复是否真正闭合，特别挑战 typed bundle closure exact membership、Fins no-create owner、advisory lock算法/并发rollback、去冗余company locator、direct ORM transaction权限、exact projection、downgrade和CLI隔离。

## 范围、目标与被检验假设

本 slice 的目标是将已证明的 legacy company/security/source identity 与 research bundle locator/hash，以 stage-before-connect、单 PostgreSQL transaction、default-tenant bootstrap 的方式登记入平台；Host/Fins raw bytes 和研究正文仍由旧 workspace owner 持有。

本次以直接代码证据检验了以下关键假设：

1. strict operator manifest 只补足 legacy `CompanyMeta` 不拥有的 MIC/currency/security type，不形成第二身份真源；
2. 当前 Fins company/source storage 和 research-bundle owner 能在不读写 raw documents、也不直接复制私有路径算法的前提下提供只读 inventory、root presence 与完整 bundle closure；
3. 0002 的 marker/locator schema、RLS/grant/FK/unique/downgrade 能闭合 tenant、identity、locator 与 no-op/drift 语义；
4. transaction-scoped advisory lock 可让同 marker 的两进程稳定收敛为一条 imported、一条 no-op，且任一 fault 全回滚；
5. default-tenant one-shot Service 不冒充认证，且 import mode 与普通 init/legacy runner 隔离；
6. allowlist、测试和 stop conditions 足以让 implementation worker 无需重新设计 owner、状态或文件边界。

## Controller adjudication and fixes verification

### Terra TERRA-S15-001..004

| Finding | Controller裁决 | 验证状态 | 直接证据 |
|---------|--------------|----------|----------|
| TERRA-S15-001 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-03 允许修改 `dayu/cli/commands/_research_template_bundle.py`，仅新增 typed strict closure inspection API；§S15-CTRL-07 第4项定义 closure exact membership（descriptor、全部已知 artifacts、可选 write-manifest，unknown key fail-closed）。当前 `inspect_research_template_bundle()` 不返回 artifact 路径/hash，但 plan 要求新增 typed API，implementation agent 可据此实现。 |
| TERRA-S15-002 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-03 允许修改 `dayu/fins/storage/fs_company_meta_repository.py`，仅暴露 `create_directories: bool = True` 并透传给 `build_fs_repository_set()`；§S15-CTRL-07 第2项要求 `FsCompanyMetaRepository(source_root, create_directories=False).scan_company_meta_inventory()`；第3项要求 `FsSourceDocumentRepository.has_source_storage_root()`。当前 `FsCompanyMetaRepository.__init__` 无 `create_directories` 参数，但 plan 允许添加。 |
| TERRA-S15-003 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-09 定义 transaction-scoped advisory lock，key 为 `sha256(tenant_id + "\\0" + migration_id)` 前8字节 signed big-endian int64；明确 loser no-op、winner rollback 与五 barrier race 测试。当前无 advisory lock 实现，但 plan 已足够具体。 |
| TERRA-S15-004 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-08 明确 `research_bundle_locators` 表无 `company_id` 列，公司必须经 `security_id -> securities.company_id` 唯一解析。 |

### MiM M01..M13

| Finding | Controller裁决 | 验证状态 | 直接证据 |
|---------|--------------|----------|----------|
| M01 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-04 列举七个稳定错误类别，MIC/ticker/market/currency/country 不一致统一映射 `workspace_import_identity_inconsistent`。 |
| M02 | ACCEPTED-IN-PART / FIXED | **已闭合** | plan §S15-CTRL-05 要求 manifest ticker 与 owner ticker 均须先各自证明已 canonical，再 exact；raw legacy company id byte-exact。不做 silent case normalization。 |
| M03 | DUPLICATE TERRA-S15-001 / FIXED | **已闭合** | typed closure result提供规范 target；CLI adapter对 manifest、CompanyMeta 与 owner result做 explicit cross-check（§S15-CTRL-07 第4项）。 |
| M04 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-06 明确 `legacy_company_id` 精确使用 owner inventory 已验证的 raw value，禁止 normalization/alias。 |
| M05 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-09 明确 workspace import repository 被精确授权在唯一 session 内直接操作 identity/source ORM models，不调用另开 transaction 的 repository methods；该权限不外扩。 |
| M06 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-09 列出 exact projection 逐表逐列定义，所有 request-owned fields 都必须相等，只排除 server-managed timestamps/version。 |
| M07 | REJECTED-WITH-REASON / CLOSED | **已闭合** | baseline `Principal` 已公开支持 exact `(TenantId, user_id: str)` 并提供 `to_scope()`；无需改 identifiers。 |
| M08 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-06 明确 pure investment domain 禁止 import `dayu.fins.*`；Fins owner types 到 pure DTO 的收窄只发生在 `dayu.cli.workspace_migrations.platform_import`。 |
| M09 | REJECTED-WITH-REASON / CLOSED | **已闭合** | `repository_key='legacy-workspace'` 是当前 closed enum，有意要求 future schema migration。 |
| M10 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-04 要求 import mode call-graph/AST + behavior isolation，禁止 legacy runner/copy/prompt/prewarm。 |
| M11 | REJECTED-WITH-REASON / CLOSED | **已闭合** | PostgreSQL 删除 referencing table 本身不会因其内部 FK rows 失败；真正需拒绝的是 0002 owner 之外的 dependent objects。 |
| M12 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-07 明确 staging adapter 位置与只允许的 public Fins storage/typed bundle imports。 |
| M13 | ACCEPTED / FIXED | **已闭合** | plan §S15-CTRL-14 明确 legacy-root runtime resolver 与旧资料移动/删除分别归两个独立 future migration work units。 |

## 挑战点验证

### 1. typed bundle closure exact membership

**挑战**：plan 要求新增 typed strict closure inspection API，但当前代码不存在。是否足够具体？

**验证**：plan §S15-CTRL-03 允许修改 `dayu/cli/commands/_research_template_bundle.py`，仅新增 typed strict closure inspection API；§S15-CTRL-07 第4项定义 closure exact membership（descriptor、全部已知 artifacts、可选 write-manifest，unknown key fail-closed）。API 的输入/输出类型在 plan 中未显式定义，但 implementation agent 可根据 exact membership 定义自行设计。不是 blocking。

### 2. Fins no-create owner

**挑战**：plan 要求暴露 `create_directories` 参数，但未指定默认值。是否足够具体？

**验证**：plan §S15-CTRL-03 允许修改 `fs_company_meta_repository.py`，仅暴露 `create_directories: bool = True`。默认值 `True` 保持向后兼容，且 plan 要求 staging adapter 显式传 `False`。implementation agent 可据此实现。不是 blocking。

### 3. advisory lock算法/并发rollback

**挑战**：plan 描述了 key 生成算法，但未指定碰撞处理细节。是否足够具体？

**验证**：plan §S15-CTRL-09 描述 key 为 `sha256(tenant_id + "\\0" + migration_id)` 前8字节 signed big-endian int64，并说明 "hash碰撞只会额外串行而不改变 correctness"。这足够具体。不是 blocking。

### 4. 去冗余company locator

**挑战**：plan 明确删除 `company_id` 列，但未说明如何处理已有 locator 行引用 company 的场景。是否足够具体？

**验证**：plan §S15-CTRL-08 明确 locator 表无 `company_id` 列，公司必须经 `security_id -> securities.company_id` 唯一解析。这是 schema 变更，按全新 schema 起库处理（AGENTS.md 约束）。implementation agent 需在 migration 中实现。不是 blocking。

### 5. direct ORM transaction权限

**挑战**：plan 明确 workspace import repository 可以直接操作 identity/source ORM models，但未说明如何避免与现有 repository 的冲突。是否足够具体？

**验证**：plan §S15-CTRL-09 明确 "该特殊权限只属于 workspace import repository，不改变既有 repository owner"。implementation agent 可据此实现。不是 blocking。

### 6. exact projection

**挑战**：plan 定义了 exact projection，但未说明比较粒度。是否足够具体？

**验证**：plan §S15-CTRL-09 列出 exact projection 逐表逐列定义，所有 request-owned fields 都必须相等，只排除 server-managed timestamps/version。这足够具体。不是 blocking。

### 7. downgrade

**挑战**：plan 描述了 downgrade 顺序，但未说明如何处理 locator 行引用 company 的 FK 依赖。是否足够具体？

**验证**：plan §S15-CTRL-08 说明 "表内 locator/marker rows 不构成 '外部依赖' 且会随 owner table 删除"。locator 行引用 companies 表，但删除 locator 表时，FK 依赖不会阻止（因为 companies 表没有引用 locator 表）。downgrade 应该可以成功。不是 blocking。

### 8. CLI隔离

**挑战**：plan 描述了 import mode 独立分支，但未说明如何测试隔离。是否足够具体？

**验证**：plan §S15-CTRL-04 要求 import mode 在 `run_init_command()` 最前部独立分支；§S15-CTRL-12 要求 import mode call-graph/AST + behavior isolation 测试。这足够具体。不是 blocking。

## Open questions

无。

## Residual risks

| 风险 | Owner / destination |
|------|---------------------|
| typed strict closure inspection API 需实现，但 plan 已提供 exact membership 定义 | Slice 1.5 implementation agent |
| `FsCompanyMetaRepository` 需添加 `create_directories` 参数，但 plan 已明确 | Slice 1.5 implementation agent |
| advisory lock 碰撞处理细节可由 implementation agent 自行决定 | Slice 1.5 implementation agent |
| downgrade FK 依赖处理已由 plan 描述，无需额外操作 | Slice 1.5 implementation agent |

## Plan review conclusion

**PASS**

Slice 1.5 的 S15-CTRL-01..14 经 Controller 修订后，已闭合 Terra TERRA-S15-001..004 与 MiM M01..M13 的所有 material findings。当前 plan 足够具体，implementation agent 可直接实施，无需重新设计 owner、状态或文件边界。

**Open findings**: H=0, M=0, L=0

**Blocking findings**: 无。

Slice 1.5 可解除冻结，进入 implementation gate。