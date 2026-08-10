# Slice 1.5 old-workspace import：Closure-only adversarial re-review

- **审查时间**：2026-08-11 07:32:57 CST（本机系统时钟）
- **Work unit / gate**：Investment Platform Restoration / Slice 1.5 workspace import closure-only adversarial re-review
- **分支 / 基线**：`codex/investment-platform` / `58b7dd28db6183f29caaac337b09dffc3db80a76`（当前 `HEAD` 一致）
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的顶部状态、revision changelog、§8.0 DAG 与 Slice 1.5 `S15-CTRL-01..14`；Controller 修订 `docs/reviews/plan-fix-20260811-slice-1.5-workspace-import-codex.md`；Terra 与 MiM 初审和 final re-review 全部 artifact。
- **边界**：只读核验计划及当前源码；未运行 live/network/model/broker、测试、commit、push 或 PR；未修改 plan/code/tests/README。唯一允许新增本 artifact。
- **审查类型**：closure-only。不引入新 finding，只逐项验证此前所有 initial/final finding 是否真实闭合。

## 审查范围与动机

本次 closure review 独立验证以下文档中所有 finding 的闭合状态：

1. **Terra initial**（`plan-review-20260811-slice-1.5-workspace-import-terra.md`）：TERRA-S15-001..004（3H/1M）
2. **MiM initial**（`plan-review-20260811-071328-slice-1.5-workspace-import-mim-native.md`）：M01..M13（2H/6M/5L）
3. **Terra final re-review**（`plan-final-rereview-20260811-slice-1.5-workspace-import-terra.md`）：TERRA-S15-FINAL-001（1H）
4. **MiM final re-review**（`plan-final-rereview-20260811-slice-1.5-workspace-import-mim-native.md`）：PASS/open0

重点独立验证 TERRA-S15-FINAL-001 是否真实闭合。

## 代码证据基础

关键代码事实已直接核对：

| 事实 | 证据 |
|------|------|
| `research_target.company` 是公司名称字符串 | `_normalize_research_target()` 只做 `company.strip()`（`_research_template_helpers.py:524-540`）；测试断言 `{"ticker": "0700.HK", "company": "Tencent Holdings"}`（`test_research_template_command.py:1778`） |
| `CompanyMeta` 同时有 `company_id`（如 `"AAPL_US"`）和 `company_name`（如 `"Apple Inc."`） | `document_models.py:148-202` frozen dataclass |
| `inspect_research_template_bundle()` 返回值不含 closure/hash | `_research_template_bundle.py:386-426`（Terra initial evidence） |
| 当前无 `ResearchBundleClosureInspection`/`ResearchBundleClosureFile`/`inspect_research_template_bundle_closure` | grep 确认全仓库 0 match |
| `FsCompanyMetaRepository.__init__` 当前无 `create_directories` 参数 | `fs_company_meta_repository.py:17-43`（Controller fix evidence） |
| `FsSourceDocumentRepository` 已有 `create_directories` 参数 | `fs_source_document_repository.py:268-298` |

## TERRA-S15-FINAL-001 闭合验证

### 问题

**原始问题**：typed bundle closure 的 `target_company` 只有名称语义，却被要求同时精确匹配 legacy company ID 和名称。一个字段不能同时等于两个不同值。

### Controller 修复

Controller ACCEPTED/FIXED：当前 owner descriptor 的 `research_target.company` 语义是公司名称，不是 legacy company id。修订后的 typed closure 字段精确命名为 `target_company_name`，只与 `CompanyMeta.company_name` exact；legacy company id 继续由 manifest 与 Fins inventory 的 raw byte-exact gate 唯一证明。

### 闭合验证

**S15-CTRL-07 第 4 项**（plan:3380-3400）现在的定义是：

> `ResearchBundleClosureFile`（`role`、POSIX `relative_locator`、`size_bytes`、`sha256`）与 `ResearchBundleClosureInspection`（`template`、`target_ticker`、**`target_company_name`**、`descriptor_sha256`、sorted files tuple、`artifact_manifest_sha256`）

**关键文本**（plan:3393-3396）：

> staging 只消费该 typed result 并 cross-check：manifest `template_name`、canonical ticker、**`CompanyMeta.company_name`** 必须与 owner result exact；**closure/descriptor 不拥有也不得伪造 legacy company id**，该 ID 已由 step 2 的 manifest↔inventory raw-exact gate 唯一证明。

**代码证据交叉验证**：

1. `research_target.company` 确实只是公司名称（"Tencent Holdings"），不是 company_id（"0700_HK"）
2. typed closure 字段已改为 `target_company_name`，只与 `CompanyMeta.company_name` exact
3. `legacy_company_id` 的证明路径已明确限定为 step 2 的 manifest↔Fins inventory raw-exact gate
4. plan 明确禁止 closure/descriptor 拥有或伪造 legacy company id

**结论**：**TERRA-S15-FINAL-001 已真实闭合。** 修复将一个不可能的双重 exact 约束分解为两个独立的、各自可证明的 identity gate：名称走 typed closure exact，company_id 走 manifest↔inventory raw-exact。没有发明新字段、没有削弱 identity gate、没有突破 owner 边界。

## 全量回归验证

### Terra TERRA-S15-001..004

| Finding | Controller 裁决 | 闭合证据 | 状态 |
|---------|----------------|---------|------|
| TERRA-S15-001（typed closure owner boundary） | ACCEPTED/FIXED | S15-CTRL-03 允许修改 `_research_template_bundle.py` 新增 typed API；S15-CTRL-07 第 4 项定义 exact membership（descriptor、全部 required artifacts、optional write-manifest，unknown key fail-closed）；S15-CTRL-12 要求 escape/symlink/unknown-key 测试 | CLOSED |
| TERRA-S15-002（Fins company repository no-create） | ACCEPTED/FIXED | S15-CTRL-03 允许对称暴露 `create_directories`；S15-CTRL-07 第 2 项要求 `FsCompanyMetaRepository(source_root, create_directories=False)`；第 3 项要求 `FsSourceDocumentRepository` 同样 no-create；S15-CTRL-12 要求完整 tree entry/type/size/mtime 前后对比 | CLOSED |
| TERRA-S15-003（advisory lock 替代 FOR UPDATE） | ACCEPTED/FIXED | S15-CTRL-09 定义 `pg_advisory_xact_lock(sha256(tenant_id+"\0"+migration_id) 前8字节 signed big-endian int64)`；明确 loser no-op、winner rollback、五 barrier race 测试 | CLOSED |
| TERRA-S15-004（locator 去冗余 company_id） | ACCEPTED/FIXED | S15-CTRL-08 locator 表无 `company_id` 列；公司由 `security_id -> securities.company_id` 唯一解析 | CLOSED |

### MiM M01..M13

| Finding | Controller 裁决 | 闭合证据 | 状态 |
|---------|----------------|---------|------|
| M01（错误类别枚举） | ACCEPTED/FIXED | S15-CTRL-04 枚举七个稳定错误类别，MIC/ticker/market/currency/country 不一致统一映射 `workspace_import_identity_inconsistent` | CLOSED |
| M02（canonical ticker exact） | ACCEPTED-IN-PART/FIXED | S15-CTRL-05/07 要求 manifest 与 owner ticker 各自先 canonical 后 exact；legacy company id raw byte-exact；不做 silent uppercase | CLOSED |
| M03（bundle locator cross-validation owner） | DUPLICATE TERRA-S15-001/FIXED | 闭合于 TERRA-S15-FINAL-001 修复：typed closure 返回 `target_company_name` 只与 `CompanyMeta.company_name` exact；staging adapter 做 cross-check | CLOSED |
| M04（UUIDv5 legacy_company_id canonical form） | ACCEPTED/FIXED | S15-CTRL-06 明确 `legacy_company_id` 精确使用 owner inventory 已验证的 raw value，禁止 normalization/alias | CLOSED |
| M05（workspace import direct ORM permission） | ACCEPTED/FIXED | S15-CTRL-09 精确授权 workspace import repository 在唯一 session 内直接操作 identity/source ORM models；不复用各自另开事务的 protocol methods；权限不外扩 | CLOSED |
| M06（no-op exact projection） | ACCEPTED/FIXED | S15-CTRL-09 为 company/security/source/locator/marker 逐列给出 request-owned exact projection，排除 server-managed timestamps/version | CLOSED |
| M07（Principal 构造签名） | REJECTED-WITH-REASON/CLOSED | baseline `Principal` 已公开支持 `(TenantId, user_id: str)` 并提供 `to_scope()`；S15-CTRL-10 确认不修改 identifiers | CLOSED |
| M08（investment domain import boundary） | ACCEPTED/FIXED | S15-CTRL-06 禁止 pure workspace-import domain import `dayu.fins.*`；Fins owner types 收窄只在 CLI adapter（S15-CTRL-07） | CLOSED |
| M09（repository_key closed enum） | REJECTED-WITH-REASON/CLOSED | `repository_key='legacy-workspace'` 是当前 closed enum，有意要求 future schema migration | CLOSED |
| M10（CLI mode isolation） | ACCEPTED/FIXED | S15-CTRL-04 要求 import mode call-graph/AST + behavior isolation；S15-CTRL-12 要求 AST 断言禁止 reset/copy/legacy runner/prompt/prewarm/network/model/Host/Fins runtime | CLOSED |
| M11（downgrade FK closure） | REJECTED-WITH-REASON/CLOSED | PostgreSQL 删除 referencing table 不会因内部 FK rows 失败；0002 owner 外 dependent objects 才需拒绝；S15-CTRL-08 catalog preflight + 有 internal rows 可 downgrade + 有 external dependency fail/rollback 测试 | CLOSED |
| M12（staging adapter Fins import boundary） | ACCEPTED/FIXED | S15-CTRL-07 明确 staging adapter 位置与只允许的 public Fins storage/typed bundle imports；禁止 internal/write API | CLOSED |
| M13（residual owner classification） | ACCEPTED/FIXED | S15-CTRL-14 明确 legacy-root runtime resolver 与旧资料移动/删除分别归两个独立 future migration work units | CLOSED |

### 回归检查：所有 Schema/RLS/Grants/Downgrade 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| 0002 两表 schema 精确列/约束 | S15-CTRL-08 逐列定义 marker+locator，含 FK/unique/RLS | CLOSED |
| RLS ENABLE/FORCE + tenant policy | S15-CTRL-08 "两表为 private tenant tables，必须 ENABLE/FORCE RLS" | CLOSED |
| App role grants 精确 | S15-CTRL-08 "app 仅 marker SELECT/INSERT、locator SELECT/INSERT" | CLOSED |
| Downgrade 顺序与无 CASCADE | S15-CTRL-08 "downgrade 先用 catalog 拒绝外部依赖，再按 locator→marker 顺序删除"；"禁止 CASCADE" | CLOSED |
| 0001 -> 0002 -> 0001 -> 0002 可重复 | S15-CTRL-08 要求 "fresh head 与重复 upgrade exact"；S15-CTRL-12 要求 "内部 rows 仍可 downgrade、外部 dependent object fail/rollback" | CLOSED |

### 回归检查：Typed Owner Closure 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| 新增 typed closure inspection API | S15-CTRL-03 允许修改 `_research_template_bundle.py`；S15-CTRL-07 第 4 项定义 `ResearchBundleClosureFile`/`ResearchBundleClosureInspection`/`inspect_research_template_bundle_closure` | CLOSED（plan 已足够具体） |
| Closure exact membership 定义 | S15-CTRL-07: descriptor + `_BUNDLE_ARTIFACT_KEYS` required + optional `research_progress_report` + optional `source_write_manifest.path`；unknown key fail-closed | CLOSED |
| No self-parse | S15-CTRL-07: "adapter 不得自行重读 descriptor 或复制 artifact/path schema" | CLOSED |
| Symlink/FIFO/device 检测 | S15-CTRL-07: "每个 path 必须以 `lstat` 证明 non-symlink，再 resolve 后 contained 于 source root" | CLOSED |

### 回归检查：No-Create Repos 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| `FsCompanyMetaRepository` 暴露 `create_directories` | S15-CTRL-03 允许修改 `fs_company_meta_repository.py`；S15-CTRL-07 要求 `create_directories=False` | CLOSED（最小补齐，source repo 已有该参数） |
| 完整 tree manifest 回归 | S15-CTRL-12: "对 empty/missing-meta/invalid/source-root-file 比较完整 source tree entry/type/size/mtime manifest" | CLOSED |

### 回归检查：Advisory xact Lock 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| Key 算法精确 | S15-CTRL-09: `sha256(tenant_id + "\0" + migration_id)` 前 8 字节 signed big-endian int64 | CLOSED |
| 碰撞语义 | S15-CTRL-09: "hash 碰撞只会额外串行而不改变 correctness" | CLOSED |
| Commit/rollback 自动释放 | S15-CTRL-09: "transaction commit/rollback 自动释放" | CLOSED |
| 五 barrier race 测试 | S15-CTRL-09: "测试 barrier 至少覆盖 lock 前、public row 前、locator 前、marker 前和 commit 前" | CLOSED |

### 回归检查：Single Transaction / No-Op / Race 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| 单 session 单 transaction | S15-CTRL-09: "每次调用只建一个 session" | CLOSED |
| No-op exact 定义 | S15-CTRL-09: "schema/root/payload/counts 全相同且 intended rows 仍 exact 时返回 no_op" | CLOSED |
| Exact projection 逐列 | S15-CTRL-09: company/security/source/locator/marker 各有精确列列表 | CLOSED |
| Drift error | S15-CTRL-09: "marker 任一字段不同，或 marker exact 但 row missing/drift，抛稳定 drift error" | CLOSED |
| 双进程 race 收敛 | S15-CTRL-09: "同 marker 双进程 race 的 loser 必须在 advisory lock 后读取 winner 已提交 marker 并走 exact no-op" | CLOSED |
| Rollback 零半发布 | S15-CTRL-09: "任一 insert/constraint/connection error rollback 全部" | CLOSED |

### 回归检查：Locator 无冗余 company_id 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| Locator 无 company_id 列 | S15-CTRL-08: locator 表精确列定义无 company_id | CLOSED |
| 公司只经 security_id 解析 | S15-CTRL-08: "company 必须由 security_id -> securities.company_id 唯一解析" | CLOSED |
| Direct INSERT mismatch 测试 | S15-CTRL-12: "直接 app-role insert locator 必须只靠 security 解析 company，schema 中不存在冗余 company_id" | CLOSED |

### 回归检查：CLI/Normal-Init 隔离项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| Import mode 独立分支 | S15-CTRL-04: "import mode 在 run_init_command() 最前部独立分支" | CLOSED |
| 禁止普通 init 副作用 | S15-CTRL-04: "禁止执行正常 init 的 mkdir/reset/copy/legacy migrations/provider prompt/prewarm" | CLOSED |
| 普通 init 行为不变 | S15-CTRL-04: "普通 dayu-cli init 行为与既有 apply_all_workspace_migrations() 顺序字节/AST 不变" | CLOSED |
| AST/behavior 测试 | S15-CTRL-12: "import mode call-graph/AST 与 behavior 均证明不调用 reset/copy/apply_all_workspace_migrations/prompt/prewarm/network/model/Host/Fins runtime" | CLOSED |

### 回归检查：真实 PG16 测试项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| Fresh upgrade exact 15 tables | S15-CTRL-12: "fresh upgrade head exact 15 tables/RLS/grants/index/FK" | CLOSED |
| Upgrade/downgrade 循环 | S15-CTRL-12: "0001 -> 0002 -> 0001 -> 0002" | CLOSED |
| Fixture workspace 导入验证 | S15-CTRL-12: "fixture workspace 导入后 company/security/source/locator/marker exact" | CLOSED |
| RLS/cross-tenant 测试 | S15-CTRL-12: "unset/cross tenant RLS 不可见/不可写" | CLOSED |
| Advisory key exact | S15-CTRL-12: "advisory key 算法 exact" | CLOSED |
| Vertical CLI test | S15-CTRL-12: "真实 dayu-cli init --import-existing-workspace 通过 injected PostgreSQL fixture" | CLOSED |

### 回归检查：Allowlist / Stop Conditions 项

| 检查项 | 证据 | 状态 |
|--------|------|------|
| S15-CTRL-03 精确 allowlist | 逐文件列出新增/修改 production/test/doc 路径；"未列 production/test 路径禁止修改" | CLOSED |
| S15-CTRL-14 stop conditions | 7 项明确 stop criteria + 5 项 residual owner 分配 | CLOSED |
| 冻结 Fins 写入语义 | S15-CTRL-03: "不得修改 Fins repository 的写入语义、research materializer、Host store" | CLOSED |

## Open questions

无。

## Residual risks（在所有 finding 修复后仍应追踪）

| 风险 | Owner / destination |
|------|---------------------|
| strict manifest 的 MIC/currency/security type 是 operator assertion，不是交易所级认证事实 | Slice 7.1 / independent future migration |
| locator/hash 不提供 legacy root 的运行时解析能力 | S15-CTRL-14: future operator config |
| downgrade 是有意的 administrative destruction | S15-CTRL-08 + Slice 8.1 backup/restore |

## 最终结论

**PASS**。所有此前 finding 均已真实闭合：

- **TERRA-S15-FINAL-001**：**已真实闭合**。typed closure 字段已精确命名为 `target_company_name`，只与 `CompanyMeta.company_name` exact；legacy company id 由 manifest↔Fins inventory raw-exact gate 唯一证明；closure/descriptor 不拥有也不伪造 company id。修复无回归。
- **Terra TERRA-S15-001..004**：全部 CLOSED。
- **MiM M01..M13**：全部 CLOSED。
- **Schema/RLS/grants/downgrade**：全部闭合。
- **Typed owner closure**：已定义 exact membership、typed API、fail-closed 规则。
- **No-create repos**：两 repository 均以 no-create mode 构造。
- **Advisory xact lock**：key 算法、碰撞、五 barrier race 均已定义。
- **Single transaction/no-op/race**：exact projection、drift error、rollback 零半发布均已定义。
- **Locator 无冗余 company_id**：已删除，公司只经 security_id 解析。
- **CLI/normal-init 隔离**：import mode 独立分支 + AST/behavior 测试。
- **真实 PG16 测试**：fresh upgrade、downgrade 循环、RLS、advisory key、vertical CLI test。
- **Allowlist/stop conditions**：精确白名单 + 7 项 stop criteria + 5 项 residual owner。

**Open findings**: H=0, M=0, L=0

**Blocking findings**: 无。

Slice 1.5 可解除冻结，进入 implementation gate。
