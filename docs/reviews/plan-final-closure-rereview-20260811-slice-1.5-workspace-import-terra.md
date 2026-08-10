# Slice 1.5 old-workspace import 最终 closure-only 对抗性复审

## Scope

- **模式**：closure-only plan re-review（只读）
- **审查时间**：2026-08-11 07:32:14 CST（本机系统时钟）
- **分支 / 基线**：`codex/investment-platform` / `58b7dd28db6183f29caaac337b09dffc3db80a76`；当前 `HEAD` 与基线一致。
- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.5 / `S15-CTRL-01..14`，以及 Controller fix 和此前 Terra、MiM Native 的 initial/final reviews。
- **本次唯一 closure 问题**：`TERRA-S15-FINAL-001` 是否真正闭合；并回归 TERRA-S15-001..004、MiM M01..M13，以及 schema/RLS/grant/downgrade、typed owner closure、no-create repository、advisory xact lock、单事务/no-op/race、locator、CLI 隔离、PG16、allowlist、stop conditions。
- **排除项**：未运行 live/network/model/broker、实现测试或 PostgreSQL；未修改 plan/code/tests/README；未 commit/push。
- **并行审查覆盖**：无。

## Findings

未发现实质性问题。

## Closure verification

### TERRA-S15-FINAL-001：已闭合

此前 finding 的直接根因成立：现有 bundle descriptor 的 `research_target` 只含 `ticker` 与 `company`，且 `_normalize_research_target()` 将 `company` 定义为经空白处理的公司名称；当前测试也以 `{"ticker": "0700.HK", "company": "Tencent Holdings"}` 断言该语义。它不含 legacy company ID。直接代码证据为：

- `dayu/cli/commands/_research_template_bundle.py:79-85` 构建的 descriptor 仅传入 `ticker`、`company`；`243-249` 只校验这两个 key；`386-424` 的当前 inspection 也只返回原 descriptor target。
- `dayu/cli/commands/_research_template_helpers.py:524-539` 明确将 `company` 规范化为名称字符串；`tests/cli/test_research_template_command.py:1770-1793` 证明实际 descriptor 使用名称而非 ID。

最新计划没有重犯“一字段承担两个事实”的错误。`S15-CTRL-07` 将新增 typed inspection 的字段固定为 `target_ticker`、`target_company_name`，staging 只将后者与 `CompanyMeta.company_name` exact；同一段明确 closure/descriptor 不拥有、不得伪造 legacy company ID。`S15-CTRL-05` 与 `S15-CTRL-07` step 2 则把 `legacy_company_id` 的唯一证明链固定为 strict manifest ↔ Fins inventory `CompanyMeta.company_id` raw byte-exact。`S15-CTRL-12` 要求覆盖 bundle ticker/company-name mismatch，且断言 closure 不含/不要求 legacy company ID。

因此，正常的 `company_id="AAPL_US"` 与 `company_name="Apple Inc."` 不会再被要求与同一个 closure 字段同时相等；adapter 也仍被禁止重读 descriptor 或另造 ID 证据。`TERRA-S15-FINAL-001` 的触发链已被切断。

### 初审及 schema/状态机回归：均已闭合

| 审查面 | 闭合的直接计划证据 |
| --- | --- |
| TERRA-S15-001 / MiM M03：typed owner closure | `S15-CTRL-03` 仅允许 bundle owner 新增 typed strict closure API；`S15-CTRL-07` 精确规定 descriptor、required artifacts、可选 progress report、可选 `source_write_manifest.path` 的 membership、`lstat`/containment、unknown key fail-closed、typed DTO 边界与 adapter 禁止重解析。 |
| TERRA-S15-002：no-create Fins repository | `S15-CTRL-03` 允许 `FsCompanyMetaRepository` 仅对称暴露已有 source repository 的 `create_directories: bool = True`；`S15-CTRL-07` step 2/3 强制 company/source 两仓储传 `False`；`S15-CTRL-12` 要求全 tree entry/type/size/mtime 对比。当前源码佐证 source repository 已有该参数（`dayu/fins/storage/fs_source_document_repository.py:268-298`），company repository 当前缺该公开参数（`fs_company_meta_repository.py:18-43`），故白名单修补既必要又充分。 |
| TERRA-S15-003：缺失 marker 并发 | `S15-CTRL-09` 在任何 public row I/O 前指定 `sha256(tenant_id + "\\0" + migration_id)` 派生 signed int64，并调用 `pg_advisory_xact_lock`；规定 lock 后读 marker、碰撞仅额外串行、rollback 自动释放、winner rollback 后下一进程完整发布。`S15-CTRL-12` 要求五个 barrier 的真实两进程 PG16 验证，禁止 unique error 外泄。 |
| TERRA-S15-004：locator company 冗余 | `S15-CTRL-08` 的 locator 仅保存 `security_id`，明确禁止 `company_id`，公司只能经 `security_id -> securities.company_id` 解析；PG16 测试要求 schema 不存在冗余列，并以 app-role direct insert 验证该关系。 |
| MiM M01/M02/M04/M06 | `S15-CTRL-04` 枚举七个稳定错误类别并统一 identity-inconsistent；`S15-CTRL-05` 要求 canonical 后 exact ticker 和 raw-exact legacy ID；`S15-CTRL-06` 将 UUIDv5 的 company component 固定为已验证 raw value；`S15-CTRL-09` 列出 company/security/source/locator/marker 的逐字段 request-owned exact projection。 |
| MiM M05/M07/M08/M12 | `S15-CTRL-09` 将唯一 session 的直接 ORM 特许限制在 import repository，禁止复用各自另开事务的 protocol；`S15-CTRL-10` 使用当前公开 `Principal(TenantId, user_id).to_scope()` 仅生成 fixed-default bootstrap scope；`S15-CTRL-06/07` 禁止 pure domain import Fins，且仅 CLI adapter 可消费 public read-only Fins API。当前 `Principal` 的构造和 `to_scope()` 直接位于 `dayu/investment/domain/identifiers.py:206-251`。 |
| MiM M09/M11/M13 | `S15-CTRL-08/14` 有意将 `repository_key` 设为 `legacy-workspace` closed enum；downgrade 使用 catalog preflight，按 locator→marker 删除且禁止 `CASCADE`，内部 rows 可删除、外部依赖应整次 rollback；runtime root resolver 与 legacy byte 移动/删除均明确留给独立 future migration work unit。 |
| CLI / normal-init 隔离 | `S15-CTRL-04` 要求 import 在 `run_init_command()` 最前的独立分支，禁止 reset/copy/legacy runner/prompt/prewarm；`S15-CTRL-12` 进一步要求 AST、call-graph 和行为三层验证。该要求对应真实风险：当前 normal init 在 `dayu/cli/commands/init.py:1710-1785` 会 mkdir、copy config/assets，并调用 `apply_all_workspace_migrations()`。 |
| schema/RLS/grant/真实 PG16 | `S15-CTRL-08` 固定仅新增 marker/locator 两张表、RLS `ENABLE/FORCE`、现有 `app.tenant_id` policy、app `SELECT/INSERT`、audit `SELECT`、PUBLIC revoke、禁用 application UPDATE/DELETE；`S15-CTRL-12` 要求 fresh head 与 `0001 -> 0002 -> 0001 -> 0002`、RLS/grants/FK/index、fault rollback、race 和 vertical CLI 使用真实 PostgreSQL 16，禁止 SQLite/fake PG 代替。基线 0001 已采用同一 RLS 机制（`dayu/investment/storage/migrations/versions/0001_platform_foundation.py:585-603`），计划没有引入第二套租户策略。 |
| allowlist / stop conditions | `S15-CTRL-03` 给出精确路径白名单并禁止改既有 0001、Host/Fins 写语义及 materializer；`S15-CTRL-14` 对缺 public owner closure、需要猜市场字段、读/复制原始字节、无法单事务、放宽 default tenant、以 fake PG 替代真实并发/RLS 或需改白名单外 owner，均要求立即停报。 |

上述闭合均保留了 `UI/CLI -> Service -> repository` 方向：`S15-CTRL-10/11` 要求 CLI 仅 stage、构造 one-shot Service、`try/finally close()`，而 session/SQL 和状态发布只属于 repository。不存在为 closure 添加 compatibility adapter、第二真源、普通 init 隐式迁移或运行时 legacy-root resolver 的计划路径。

## Open Questions

无。

## Residual Risk

无。实现尚未开始，`S15-CTRL-12/13` 已将真实 PostgreSQL 16、RLS/grant、并发、rollback、typed closure 和 normal-init isolation 的验证列为 implementation acceptance gate；它们不是本次计划 closure 的开放 finding。

## Conclusion

**PASS**

开放 finding：**高 0 / 中 0 / 低 0**。`TERRA-S15-FINAL-001` 已真实闭合，且此前 initial/final findings 的修订无回归；Slice 1.5 可以解除本轮计划冻结并进入 implementation gate。
