# Slice 1.5 old-workspace import pre-edit Controller plan fix

- **Work unit**：Investment Platform Restoration
- **Gate**：Slice 1.5 pre-edit plan gap / plan-only fix
- **Branch**：`codex/investment-platform`
- **Baseline**：`58b7dd28db6183f29caaac337b09dffc3db80a76`
- **Status**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED**
- **Target plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`

## 1. Stop evidence

DeepSeek Flash 在 Slice 1.5 pre-edit 审计阶段零编辑停报。现有计划只允许 CLI
workspace migration 路径，却同时要求跨 company/security/source/locator/marker 的
单事务发布；真实仓库没有相应 schema、DTO、repository、Service 或 startup owner：

1. `0001_platform_foundation` 只有 13 张表，没有 import marker 与 research bundle
   locator；
2. `IdentityRepositoryProtocol` / `SourceRepositoryProtocol` 的方法各自拥有 transaction，
   不能组合成一个原子 migration publish；
3. legacy `CompanyMeta` 只有 company id/name/ticker/market/resolver/update/aliases，没有
   exchange MIC、currency、security type、ISIN/country，不能安全猜测；
4. `TenantScope` 只能由 `Principal.to_scope()` 产生，而 Slice 7.1 auth 尚未实现，原计划
   没有定义 bootstrap tenant；
5. `dayu.cli.workspace_migrations` 当前只做 run.json/Host SQLite 的 in-place migration，
   普通 init 会无条件调用，不能承载需要显式 flag、PostgreSQL事务和零交互的 platform
   import。

因此原 Slice 1.5 不是 code-generation-ready；worker若继续只能发明 schema、第二
transaction真源或默认猜交易所，均违反 Gateflow stop condition。

## 2. Controller decision

选择保持完整目标的方案 A：本 slice 仍导入 company/security/source identity 与
research bundle locator/hash，不把 locator 延期，也不缩成 inspection-only。

计划新增 S15-CTRL-01..14，锁定：

- strict operator manifest 明示 legacy metadata缺失的 MIC/currency/security type；
- Fins company/source storage与research bundle owner只读验证，不直接扫其私有路径；
- `0002_workspace_import` 两张 tenant-scoped append-only 表；
- 单一 `PostgresWorkspaceImportRepository.publish_import()` transaction owner；
- default organization限定的bootstrap scope，明确不是认证；
- import mode在正常init前独立分支且零交互，不运行legacy migrations/model prewarm；
- stage-before-connect、UUIDv5、canonical fingerprint、row drift与idempotent no-op；
- PG16/RLS/concurrency/fault injection、raw-byte no-read/no-copy与完整docs/quality gates。

## 3. Rejected alternatives

- **把 bundle locator 延到 Slice 3/4**：拒绝。会削弱原旧 workspace migration目标，
  也让后续证据/公司 read model继续缺失 legacy research identity桥接。
- **复用多个 identity/source repository calls**：拒绝。它们各自开 transaction，无法
  满足“任何阶段失败零发布”。
- **从 market默认推导美股 MIC/currency/security type**：拒绝。US CompanyMeta不能
  区分 XNAS/XNYS，猜测会污染 authoritative identity。
- **把 migration自动挂进普通 init runner**：拒绝。会把显式、需要PG的迁移变成
  隐式副作用并触发 provider交互。
- **把 Host/Fins bytes复制到platform**：拒绝。违反单一 owner、放大数据与恢复风险。
- **让 CLI 直接持 session/SQL**：拒绝。破坏 UI/CLI → Service → repository方向。

## 4. Review request

Terra 与 MiM Native 必须独立确认：

1. manifest、owner验证与fingerprint是否有第二真源、路径逃逸或不可实施字段；
2. 两表 schema、RLS/grant/FK/unique/downgrade是否足以表达 marker/locator；
3. single transaction/no-op/drift/race/rollback状态机是否闭合；
4. default-tenant bootstrap是否被严格限制且未冒充auth；
5. import mode是否与普通init、Host/Fins owner和production composition正确隔离；
6. tests/coverage/docs/stop conditions是否能直接指导 implementation。

任一路有 open H/M/L finding 时保持 Slice 1.5 冻结；Controller逐项裁决并只修 plan，
直到双路 PASS/open0。当前未修改 production/tests/README，未运行 live/network/model/
broker，未 commit/push/PR。

## 5. Initial dual plan reviews

- Terra：`docs/reviews/plan-review-20260811-slice-1.5-workspace-import-terra.md`，
  FAIL，open H/M/L=`3/1/0`。
- MiM Native：
  `docs/reviews/plan-review-20260811-071328-slice-1.5-workspace-import-mim-native.md`，
  PASS-WITH-RISKS，但正文仍列 open H/M/L=`2/6/5`；Gateflow 按 open findings 处理，不能
  把 summary 的“blocking=0”当作通过。

## 6. Controller adjudication and fixes

### Terra

| Finding | 裁决 | 计划修复 |
| --- | --- | --- |
| TERRA-S15-001 | ACCEPTED / FIXED | bundle owner 新增 typed strict closure API，并把 owner/test 纳入 allowlist；closure membership、containment、non-symlink、hash 与 unknown-key fail-closed 全部写死，staging 禁止自行解析 descriptor。 |
| TERRA-S15-002 | ACCEPTED / FIXED | `FsCompanyMetaRepository` 对称暴露 `create_directories=False`，company/source 两仓储均以 no-create mode 构造；完整 tree entry/type/size/mtime 前后对比证明无目录/recovery/mtime 副作用。 |
| TERRA-S15-003 | ACCEPTED / FIXED | 删除不存在 row 的 `FOR UPDATE` 方案，改为 SHA-256 派生 key 的 transaction-scoped PostgreSQL advisory lock；明确 loser no-op、winner rollback与五 barrier race。 |
| TERRA-S15-004 | ACCEPTED / FIXED | locator 删除冗余 `company_id`，公司只能经 `security_id -> securities.company_id` 解析，数据库不再能表达错配 pair。 |

### MiM Native

| Finding | 裁决 | 计划修复 |
| --- | --- | --- |
| M01 | ACCEPTED / FIXED | 七个稳定错误类别已枚举，MIC/ticker/market/currency/country 不一致统一映射 identity-inconsistent。 |
| M02 | ACCEPTED-IN-PART / FIXED | 不做 silent uppercase；manifest 与 owner ticker 均须先各自证明已 canonical，再 exact。raw legacy company id byte-exact。 |
| M03 | DUPLICATE TERRA-S15-001 / FIXED | typed closure result提供规范 target；CLI adapter对 manifest、CompanyMeta 与 owner result做 explicit cross-check。 |
| M04 | ACCEPTED / FIXED | `legacy_company_id` UUIDv5 component精确使用已验证 inventory raw value，禁止 normalization/alias。 |
| M05 | ACCEPTED / FIXED | workspace import repository被精确授权在唯一 session内直接操作 identity/source ORM models；不复用另开 transaction 的 repository methods，该权限不外扩。 |
| M06 | ACCEPTED / FIXED | exact projection逐表逐列写死；与 reviewer 建议不同，所有 request-owned fields 都必须相等，只排除 server-managed timestamps/version，避免 display/identity drift 被吞掉。 |
| M07 | REJECTED-WITH-REASON / CLOSED | baseline `Principal` 已公开支持 exact `(TenantId, user_id: str)` 并提供 `to_scope()`；无需改 identifiers。计划补直接事实与 non-auth 边界。 |
| M08 | ACCEPTED / FIXED | pure investment domain 禁止 import Fins；Fins owner type收窄只在 CLI staging adapter。 |
| M09 | REJECTED-WITH-REASON / CLOSED | `repository_key='legacy-workspace'` 是当前 closed enum，有意要求 future schema migration，不能为了未授权 future backend 放宽。计划已显式记录。 |
| M10 | ACCEPTED / FIXED | 增加 import mode call-graph/AST + behavior isolation，锁 normal init call order并禁止 legacy runner/copy/prompt/prewarm。 |
| M11 | REJECTED-WITH-REASON / CLOSED | PostgreSQL 删除 referencing table本身不会因其内部 FK rows失败；真正需拒绝的是 0002 owner之外的 dependent objects。计划补 catalog preflight、internal rows成功 downgrade与external dependency rollback tests。 |
| M12 | ACCEPTED / FIXED | staging adapter位置与只允许的 public Fins storage/typed bundle imports已写死。 |
| M13 | ACCEPTED / FIXED | legacy-root runtime resolver与旧资料移动/删除分别归两个独立 future migration work units；不归 Slice 2.3。 |

## 7. Corrected contract summary

本轮没有削弱旧 workspace identity + source definition + bundle locator/hash 的完整目标。
实现现在拥有三个此前缺失的可执行前置条件：owner-owned strict closure、真正只读的 Fins
construction path、缺失 marker 时也能线性化的 transaction lock。schema取消 locator
冗余 company列，transaction exactness、downgrade、错误类别、domain dependency、CLI isolation
和 residual owners 也已逐项闭合。

当前 Controller plan-review open H/M/L=`0/0/0`，但 Slice 1.5 仍冻结；必须由 Terra 与
MiM Native 对修订后的完整 plan 做独立 re-review，并且两路均 PASS/open 0 才能 accepted
commit 与 implementation handoff。production/tests/README仍未修改，未运行 live/network/
model/broker，未 commit/push/PR。

## 8. Final re-review observation and correction

- Terra：
  `docs/reviews/plan-final-rereview-20260811-slice-1.5-workspace-import-terra.md`，
  FAIL，`TERRA-S15-FINAL-001` 1H。
- MiM Native：
  `docs/reviews/plan-final-rereview-20260811-slice-1.5-workspace-import-mim-native.md`，
  PASS，open H/M/L=`0/0/0`。

Controller **ACCEPTED / FIXED** `TERRA-S15-FINAL-001`。当前 owner descriptor 的
`research_target.company` 语义是公司名称，不是 legacy company id。修订后的 typed
closure 字段精确命名为 `target_company_name`，只与 `CompanyMeta.company_name` exact；
legacy company id继续由 manifest与Fins inventory的raw byte-exact gate唯一证明。
未新增 bundle descriptor字段、未让 CLI重读 descriptor、未削弱 identity gate。

该修复的 Controller open H/M/L=`0/0/0`，但前述 MiM PASS 发生在修复前，不能单独当作
最终 closure。Slice 1.5 继续冻结，等待 Terra与MiM Native对最新完整文本做双路 closure
re-review；production/tests/README仍未修改，未运行 live/network/model/broker，未
commit/push/PR。

## 9. Final dual closure

- Terra：
  `docs/reviews/plan-final-closure-rereview-20260811-slice-1.5-workspace-import-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- MiM Native：
  `docs/reviews/plan-final-closure-rereview-20260811-slice-1.5-workspace-import-mim-native.md`，
  PASS，open H/M/L=`0/0/0`。

两路均独立确认 `TERRA-S15-FINAL-001` 已真实闭合：typed closure 仅暴露
`target_company_name` 并与 `CompanyMeta.company_name` exact；legacy company ID 只由
strict manifest 与 Fins inventory raw-exact gate 证明。Terra TERRA-S15-001..004、MiM
M01..M13、schema/RLS/grants/downgrade、no-create repositories、advisory xact lock、single
transaction/no-op/race、locator无冗余company、CLI隔离、真实PG16验证与stop conditions均无
回归。Controller最终 open H/M/L=`0/0/0`，本 artifact CLOSED；Slice 1.5 可进入
implementation gate。production/tests/README仍未修改，未运行 live/network/model/broker，
未 push/PR。
