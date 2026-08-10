# Slice 1.5 旧 workspace 显式导入：独立计划对抗审查

- **审查时间**：2026-08-11 07:13:28 CST（本机系统时钟）
- **Work unit / gate**：Investment Platform Restoration / Slice 1.5 old workspace explicit import，initial dual plan review
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的顶部当前状态、revision changelog、§8.0 DAG 与 Slice 1.5 `S15-CTRL-01..14`；`docs/reviews/plan-fix-20260811-slice-1.5-workspace-import-codex.md`
- **Baseline**：`58b7dd28db6183f29caaac337b09dffc3db80a76`（当前 `HEAD` 与此一致）
- **审查边界**：仅计划与当前代码事实核对；未运行网络、模型、Broker 或实现测试，未改动 production/tests/README/master plan。

## 范围、目标与被检验假设

本 slice 的目标是将已证明的 legacy company/security/source identity 与 research bundle locator/hash，以 stage-before-connect、单 PostgreSQL transaction、default-tenant bootstrap 的方式登记入平台；Host/Fins raw bytes 和研究正文仍由旧 workspace owner 持有。

本次以直接代码证据检验了以下关键假设：

1. strict operator manifest 只补足 legacy `CompanyMeta` 不拥有的 MIC/currency/security type，不形成第二身份真源；
2. 当前 Fins company/source storage 和 research-bundle owner 能在不读写 raw documents、也不直接复制私有路径算法的前提下提供只读 inventory、root presence 与完整 bundle closure；
3. 0002 的 marker/locator schema、RLS/grant/FK/unique/downgrade 能闭合 tenant、identity、locator 与 no-op/drift 语义；
4. `SELECT ... FOR UPDATE` 的 marker 协议可让同 marker 的两进程稳定收敛为一条 imported、一条 no-op，且任一 fault 全回滚；
5. default-tenant one-shot Service 不冒充认证，且 import mode 与普通 init/legacy runner 隔离；
6. allowlist、测试和 stop conditions 足以让 implementation worker 无需重新设计 owner、状态或文件边界。

manifest 对缺失市场身份字段采用 operator 显式映射、HK/CN consistency gate 且禁止猜 US MIC 的方向成立；default tenant 的 CLI → Service → repository 分层、普通 init 独立分支、PG16/RLS/fault-injection 验证目标也合理。以下发现使当前版本仍不可交给 implementation。

## Findings

### TERRA-S15-001-未修复-高-现有研究 bundle owner 不提供可验证的 strict closure，白名单下无法完成 locator/hash staging
- **位置**: S15-CTRL-03（禁止修改 research materializer/bundle owner，且禁止复制其 parser/路径算法）、S15-CTRL-07 第 4 项、S15-CTRL-12 vertical tests、S15-CTRL-14。
- **问题类型**: 契约缺失 / 架构边界 / 不可直接实施。
- **当前写法**: 计划要求 staging 仅通过 `inspect_research_template_bundle()` 的 owner validation，取得 bundle、自身 artifacts 和可选 source write-manifest 的“owner 已验证 closure”，逐个记录 relative locator、size、SHA-256，并拒绝 symlink/escape。
- **反例/失败场景**: 一个 bundle descriptor 的 `artifacts` 或 `source_write_manifest.path` 指向 source root 外、symlink，或 validator 将未知 artifact 仅作为 warning。implementation worker 只能调用现有 inspect API：它既拿不到 owner-owned closure，也无法判定哪些路径属于 closure。若自行重读 descriptor 并枚举 `artifacts`/manifest，便复制 bundle owner 的私有 schema/path/validation 语义；若只信 inspect 的 `ok`，便不能实现 contained/symlink closure 与 artifact-manifest hash。
- **为什么有问题**: 这不是测试缺失，而是计划要求的唯一证据来源不存在。继续实施只能违反 S15 的 owner 边界、no-private-layout 约束或写出不可证明的 hash/locator。
- **直接证据**: `dayu/cli/commands/_research_template_bundle.py:386-426` 的 `inspect_research_template_bundle()` 返回的仅是 `descriptor_file`、template、`research_target`、`automation_status` 和 validation summary；返回值没有 artifact 路径、source write-manifest 路径、相对化结果、文件类型或 digest。`validate_research_template_bundle_descriptor()`（同文件:214-380）只以 `Path(...).is_file()` 验证 artifacts，并把 unknown artifact entries 写为 warning；它没有 source-root containment、`lstat`/non-symlink、closure DTO 或 digest contract。其公开类型还是 `dict[str, object]`，不满足 S15-CTRL-06 所声称的 strict owner contract。计划同时在 S15-CTRL-03 禁止修改此 owner 或复制其 parser/path algorithm。
- **影响**: 实施 Agent 跑偏 / 生成错误代码 / review 不可验收 / 风险后移。尤其会产生“validation.ok”却无法证明 locator 可安全解析回旧 workspace 的记录，直接破坏 S15-CTRL-07/12 的 contained closure 与 vertical assertion。
- **建议改法和验证点**: Controller 应先只修计划与 slice 边界：要么把 bundle owner 的**最小、typed、只读 closure inspection API**（输入 descriptor + source root；输出已 canonical 的 relative files、regular/non-symlink 状态、size、SHA-256、target/template、validation result；不得泄漏 absolute paths/raw bytes）及其 owner tests 纳入本 slice allowlist；要么将该 API 作为一个已 accepted predecessor slice，并令 S1.5 仅消费它。然后明确 closure 的 exact membership（descriptor、全部已知 artifacts、可选 write-manifest，以及它是否递归展开）与 unknown key 的 fail-closed 规则。PG/CLI tests 必须以 escape、symlink、unknown artifact、stale manifest 证明 staging 在 DB connect 前失败，且不自行解析私有 descriptor layout。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### TERRA-S15-002-未修复-高-指定 Fins company repository 的构造会写 legacy workspace，违背 read-only staging 且无白名单内替代路径
- **位置**: S15-CTRL-01、S15-CTRL-03、S15-CTRL-07 第 2/3 项、S15-CTRL-11、S15-CTRL-12、S15-CTRL-14。
- **问题类型**: 架构边界 / 状态机漏洞 / 不可直接实施。
- **当前写法**: staging 必须“只通过 `FsCompanyMetaRepository.scan_company_meta_inventory()`”读取 inventory，source tree 在所有状态只读，且不得修改 Fins repository；S15 只允许新增 import adapter 与新 platform owner。
- **反例/失败场景**: 对没有 `portfolio/` 或 `.dayu/` 的合法 empty legacy source root 执行 import。创建 `FsCompanyMetaRepository(source_root)` 时，它会沿默认构造路径建立 `portfolio`、`.dayu/batches`、`.dayu/backups`、lock/remote-op 目录并进行 batch recovery，然后才可能扫描 inventory。即使随后 manifest 验证失败、DB connect count 为 0，source tree 已被写入；这违反 “empty import”“只读”“不得清理/修改 legacy tree” 三项硬约束。
- **为什么有问题**: 计划将现有写入型 repository construction 当作只读 adapter 使用，但没有为它指定或允许一个 public read-only construction path。直接使用 Fins private `_FsRepositorySet`/factory 的 `create_directories=False` 则违反 S15-CTRL-03 的 public owner / 禁止私有布局要求；当前 `FsCompanyMetaRepository.__init__` 又没有暴露该参数。因此 implementation worker 没有合规实现选择。
- **直接证据**: `dayu/fins/storage/fs_company_meta_repository.py:17-42` 的 constructor 只把 `workspace_root` 传给 `build_fs_repository_set()`，未暴露 `create_directories`。`dayu/fins/storage/_fs_repository_factory.py:24-55` 默认 `create_directories=True`，并在 true 时调用 `core.ensure_batch_recovery()`；`dayu/fins/storage/_fs_storage_infra.py:200-208,1265-1282` 在该模式创建 `portfolio`、`.dayu`、batch/backup/lock/remote-op 目录。相比之下，`FsSourceDocumentRepository` 虽有 `create_directories` 参数（`fs_source_document_repository.py:268-290`），S15-CTRL-07 也未要求显式传 `False`，会留下相同默认写入风险。
- **影响**: 数据/工作区被意外修改 / 实施 Agent 跑偏 / review 不可验收。该副作用发生在计划承诺的 stage-before-connect，因此无法用 DB rollback、marker 或 fault injection 恢复。
- **建议改法和验证点**: 将最小的 public read-only construction contract 纳入当前 slice（优先在两个 Fins repository constructor 明确 `create_directories: bool = True` 并由 S1.5 精确传 `False`，或加入一个 public readonly factory；不要让 investment/CLI import 私有 Fins factory）。计划必须写明此 owner API 与对应 Fins regression tests 属于 allowlist，并要求 company/source repository 均以 no-create mode 构造。增加 empty-root、missing-meta、invalid-manifest、source-root-is-file 的 staging tests，事前/事后比较整个 legacy tree entry manifest，证明没有新增目录、mtime 写入或 recovery 文件；这比“sentinel bytes identical”更能证明无写入。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### TERRA-S15-003-未修复-高-缺 marker 时的 FOR UPDATE 不会锁住竞争者，无法保证 race 收敛为 imported + no-op
- **位置**: S15-CTRL-09 前两项、S15-CTRL-11 状态机、S15-CTRL-12 两进程 race test。
- **问题类型**: 并发恢复风险 / 状态机漏洞 / 不可直接实施。
- **当前写法**: repository 先对 `(tenant_id, migration_id)` 执行 `SELECT ... FOR UPDATE`；无 marker 才发布；同 marker 并发测试要求恰一 imported、一条 no-op，marker/locators 在同一 transaction。
- **反例/失败场景**: T1 和 T2 都在 marker 不存在时运行 `SELECT ... FOR UPDATE`。不存在的 row 不会被 row lock 锁住，因此二者都会进入 public reconcile 和 locator/marker insert。T1 commit 后，T2 的最终 marker unique insert 要么在等待后抛 unique violation（其 transaction 已进入 abort，不能直接再读 marker），要么更早在 public `(exchange_mic,ticker)` / `source_key` unique 上失败；按当前文字它不会返回 no-op。这与计划指定的 race result 相矛盾，且有 public-write fault injection 时更难确定恢复分支。
- **为什么有问题**: 计划把“锁已有 marker”误作“为尚不存在 marker 取得互斥”。`UNIQUE(tenant_id,migration_id)` 只能发现冲突，不能自动把失败 transaction 变成 no-op；当前状态机也没有声明 savepoint/recheck 或 reservation 线性化点。
- **直接证据**: S15-CTRL-08 只定义 marker 的 `UNIQUE(tenant_id,migration_id)`（计划:3345），S15-CTRL-09 明确“先 `SELECT ... FOR UPDATE`；无 marker 才发布”（计划:3362），而 marker 插入在 public reconcile/locator inserts 之后才被描述为 completed marker（计划:3358-3370）。S15-CTRL-12 却要求 “two-process 同 marker race 恰一 imported 一 no-op”（计划:3423-3425）。PostgreSQL row lock 只能锁住已被选中的 row；缺行时不存在可锁记录。
- **影响**: 状态不一致 / 错误的 CLI failure / review 不可验收。实现者若为通过 race test 额外发明 advisory lock、pending row 或 unique-error retry，将自行扩展计划状态机；若不扩展，承诺的幂等并发行为无法实现。
- **建议改法和验证点**: 在 S15-CTRL-09/11 明确定义唯一线性化算法。例如同一 transaction 在任何 public reference 写前执行已知 marker payload 的 `INSERT ... ON CONFLICT DO NOTHING RETURNING id`：赢者持有未提交的 reservation 并继续发布，失败/kill 时 transaction rollback 后不留下 marker；输者等待冲突决议、重新读取 marker 与 intended rows，只有 exact 时返回 no-op，否则 drift。或者定义受 tenant/migration key 约束的 transaction-scoped advisory lock，但必须规定 key、碰撞、异常释放与 RLS 无关性。无论选项，必须写出 commit exception、unique conflict/savepoint、reservation rollback 的稳定错误映射，并把二进程 barrier 测试放在 marker reservation 前、public row 前、locator 前和 commit 前四个点。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### TERRA-S15-004-未修复-中-locator 冗余 company_id 与 security_id 没有数据库级同属关系，FK closure 不完整
- **位置**: S15-CTRL-08 的 `research_bundle_locators` schema、S15-CTRL-09 exact reuse/drift、S15-CTRL-12 的 FK tests。
- **问题类型**: 契约缺失 / schema 变更 / 测试缺口。
- **当前写法**: locator 同时保存 `company_id` 与 `security_id`，各自 FK 到公共 `companies`/`securities`，并要求 repository 对 security-company relation fail closed。
- **反例/失败场景**: app role 可直接 INSERT 一个 tenant 内 locator，令 `company_id=C1`、`security_id=S2`，其中 `S2.company_id=C2`；两个单列 FK 都通过，marker FK/RLS/unique 也都通过。之后 import 的 intended-row “exact”可把这个不一致记录为 drift，但 database 仍永久允许并保存无法代表任何真实 company-security bundle 的 locator；审计/后续 read model 也不能仅靠 FK 判断关联正确。
- **为什么有问题**: `companies`/`securities` 是公共 reference，且 0001 给 app `SELECT, INSERT, UPDATE`（`0001_platform_foundation.py:550-568`）。计划本身强调 FK/unique/RLS exactness，却把可由 schema 表达的跨行 identity invariant 只留给新 repository 的行为约定，削弱 append-only locator 的可验证性。
- **直接证据**: 计划列定义在 3346 仅包含 company→companies 和 security→securities 两个独立 FK；没有 `(security_id, company_id)` 复合 FK 或等价约束。`securities.company_id` 是既有 FK，且只有 `securities.id` primary key（`models_identity.py` 与 `0001_platform_foundation.py:190-219`）；没有可被 locator 引用的 `(id, company_id)` unique key。S15-CTRL-12 虽要求 index/FK exact，却没有 mismatch negative test（计划:3420-3427）。
- **影响**: 状态不一致 / 后续返工 / audit 证据不完整。尤其在 default tenant bootstrap 不是 authentication 的阶段，数据库本身应守住最小身份图不变量。
- **建议改法和验证点**: Controller 应选择一个单一表示：优先删除 locator 冗余 `company_id`，由 `security_id -> securities.company_id` 解析公司；若业务确实要求冗余列，则允许 0002 同时在 `securities(id, company_id)` 建 unique constraint/index 并使 locator 以 `(security_id, company_id)` 引用它，同时把 ORM metadata/allowlist一并补齐。新增 app-role direct INSERT mismatch negative test、repository exact-reuse test 和 downgrade 恢复该约束的测试。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## Open questions

无。上述四项均可由当前 plan 与代码直接证实，不需要等待外部系统、网络或未来 slice 决策。

## Residual risks（在以上 finding 修复后仍应追踪）

- strict manifest 的 MIC/currency/security type 是 operator assertion，不是交易所认证事实；本 slice 应只审计其 canonical content/hash，交易所级 authority 与 multi-listing 仍应由 Slice 7.1/独立 future migration work unit 承担。
- `repository_key + relative_locator + hashes` 不提供 legacy root 的运行时解析能力；S15-CTRL-14 已将 root mapping 留给 future operator config。该边界应保留在 Slice 1.5 README/operator workflow，不能被误报为可运行 evidence resolver。
- downgrade 将有意移除 import marker/locator；执行该 destructive administrative action 前仍需以备份和外部依赖 preflight 为 operator 责任，建议跟踪至 Slice 8.1 backup/restore acceptance。

## 结论

**FAIL**。当前计划不能进入 implementation：开放 finding 为 **高 3 / 中 1 / 低 0**。Controller 应先仅修 plan，关闭四项并完成 dual re-review 到 open 0 后，才解除 Slice 1.5 冻结。
