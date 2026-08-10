# Slice 1.5 old-workspace import：最终独立对抗性复审

- **审查时间**：2026-08-11 07:24:57 CST（本机系统时钟）
- **Work unit / gate**：Investment Platform Restoration / Slice 1.5 workspace import final independent adversarial re-review
- **分支 / 基线**：`codex/investment-platform` / `58b7dd28db6183f29caaac337b09dffc3db80a76`（当前 `HEAD` 一致）
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的顶部状态、revision changelog、§8.0 DAG 与 Slice 1.5 `S15-CTRL-01..14`；Controller 修订 `docs/reviews/plan-fix-20260811-slice-1.5-workspace-import-codex.md`；Terra 与 MiM 初审。
- **边界**：只读核验计划及当前源码；未运行 live/network/model/broker、测试、commit、push 或 PR；未修改 plan/code/tests/README。

## 范围、动机与被检验假设

本复审确认该 slice 的动机成立：legacy `CompanyMeta` 不持有 MIC/currency/security-type，且既有 identity/source repository 不能组成跨公共 reference、locator 与 marker 的单事务发布。因此 strict manifest、stage-before-connect 和独立 transaction owner 不是过度设计。

重点以当前源码验证：typed bundle closure 的字段闭合、Fins no-create owner、advisory-lock 线性化及 rollback、locator 无冗余 company、workspace-import 的 direct ORM 特许、exact projection、downgrade 以及 CLI 隔离。结论不是对 Controller 修订的复述，而是检查其是否能在当前 owner 契约上直接实施。

## Controller 裁决复核

| 初审项 | 复核 | 直接证据 |
| --- | --- | --- |
| TERRA-S15-001 | closure membership/owner allowlist 已具体化；但其 target contract 被下列未闭合项否决。 | S15-CTRL-03/07/12 已限定 owner API、closure 成员、`lstat`、containment 与 fail-closed。 |
| TERRA-S15-002 | 已闭合。 | S15-CTRL-03 允许仅为 `FsCompanyMetaRepository` 对称暴露 `create_directories`；S15-CTRL-07 对 company/source 两个 constructor 均明确传 `False`，并要求完整 tree manifest 回归。当前 source repository 已有该参数（`dayu/fins/storage/fs_source_document_repository.py:268-298`），company repository 当前确实缺失而可在白名单内最小补齐（`fs_company_meta_repository.py:17-43`）。 |
| TERRA-S15-003 | 已闭合。 | S15-CTRL-09 定义了 public row 之前的 `pg_advisory_xact_lock`、精确 key 算法、碰撞语义、commit/rollback 自动释放与五 barrier race；不再依赖缺失 row 的 `FOR UPDATE`。 |
| TERRA-S15-004 | 已闭合。 | S15-CTRL-08 的 locator 仅保存 `security_id`，明确禁止 `company_id`，公司由 `securities.company_id` 唯一解析。 |
| M01 | 已闭合。 | S15-CTRL-04 枚举七个稳定类别，并将 MIC/ticker/market/currency/country 归入 `workspace_import_identity_inconsistent`。 |
| M02 | 已闭合。 | S15-CTRL-05/07 要求 manifest 与 owner ticker 分别已 canonical 后 exact，legacy company id raw byte-exact，不作 silent uppercase。 |
| M03 | **未闭合（见 finding）**。 | typed result 的 target 字段不能满足新增的双重 exact cross-check。 |
| M04 | 已闭合。 | S15-CTRL-06 明定 UUIDv5 的 `legacy_company_id` 使用已验证 inventory raw value。 |
| M05 | 已闭合。 | S15-CTRL-09 精确授予 `PostgresWorkspaceImportRepository` 在唯一 session 内直接操作 `Company`、`Security`、`SourceDefinition` ORM models，且明确不得复用各自另开事务的 protocol。 |
| M06 | 已闭合。 | S15-CTRL-09 为 company/security/source/locator/marker 逐列给出 request-owned exact projection，并排除唯一的 server-managed 字段。 |
| M07 | 已闭合。 | 当前 `Principal` 是公开 `(TenantId, user_id: str)` frozen dataclass，`to_scope()` 可直接派生 scope（`dayu/investment/domain/identifiers.py:206-251`）；S15-CTRL-10 也将其限定为 default-tenant bootstrap 而非认证。 |
| M08 | 已闭合。 | S15-CTRL-06 禁止 pure workspace-import domain import `dayu.fins.*`，收窄只在 CLI adapter；S15-CTRL-07 固定 adapter 位置与 Fins public-only imports。 |
| M09 | 已闭合（有意的 closed enum）。 | S15-CTRL-08/14 明定 `repository_key='legacy-workspace'`；新 repository 必须另做 migration，不存在未授权的未来兼容需求。 |
| M10 | 已闭合。 | S15-CTRL-04 与 S15-CTRL-12 同时要求 import branch 在 normal init 之前，且以 AST/call-graph/behavior 禁止 reset/copy/legacy runner/prompt/prewarm/network/model/Host/Fins runtime。当前普通 init 的确会直接 copy 并调用 `apply_all_workspace_migrations()`（`dayu/cli/commands/init.py:1710-1777`），所以该隔离要求必要且可验收。 |
| M11 | 已闭合。 | S15-CTRL-08 正确区分 owner table 内 rows 与外部 dependent object：先 catalog preflight，locator→marker drop，无 CASCADE；测试要求 internal rows 成功、外部 dependency 全回滚。 |
| M12 | 已闭合。 | S15-CTRL-07 只允许 `platform_import` 使用 public Fins repositories 和 typed bundle API，禁止 internal/write API。 |
| M13 | 已闭合。 | S15-CTRL-14 将 runtime root resolver、legacy bytes 移动和删除分配给独立 future migration work units，而非 Slice 2.3 或本 slice。 |

## Findings

### TERRA-S15-FINAL-001-未修复-高-typed bundle closure 的公司 target 只有名称语义，却被要求同时精确匹配 legacy company ID 和名称

- **位置**：S15-CTRL-07 第 4 项（`docs/plans/2026-08-10-investment-platform-restoration.md:3369-3384`）；MiM M03 的 Controller 裁决。
- **问题类型**：契约缺失 / 架构边界 / 不可直接实施。
- **当前写法**：`ResearchBundleClosureInspection` 只定义 `target_ticker`、`target_company`；staging 禁止自行读取 descriptor，并要求将 manifest template、ticker、`CompanyMeta.company_id` **和** company name 与 owner result exact cross-check。
- **反例/失败场景**：普通条目可为 `CompanyMeta(company_id="AAPL_US", company_name="Apple Inc.")`。bundle owner 的唯一 `target_company` 不能同时等于这两个不同字符串：若它保持当前 bundle schema 的公司名称语义，则 company-id 比较失败；若改为 company-id，则 company-name 比较失败。因 staging 被禁止自行重读 descriptor，也不能在 adapter 层补出第二个值。
- **为什么有问题**：Controller 声称 M03 由“typed closure result 提供规范 target”修复，但该 target 的信息量不足，反而把两个不同 identity facts 压缩成一个字段。它会让正常 legacy workspace fail closed，或迫使 implementation agent 擅自改变 bundle descriptor schema、删除其中一项 cross-check，或突破 owner 边界；三者都不符合计划。
- **直接证据**：当前 owner 构建 descriptor 时把 `research_target` 固定为 `ticker` 与 `company` 两键（`dayu/cli/commands/_research_template_bundle.py:72-91`），其中 `company` 来自 `_normalize_research_target()` 的普通公司名称字符串（`dayu/cli/commands/_research_template_helpers.py:524-539`）。现有测试也直接证明其语义为名称：`{"ticker": "0700.HK", "company": "Tencent Holdings"}`（`tests/cli/test_research_template_command.py:1774-1787`）。当前 descriptor 不含 company id；而 S15-CTRL-07 同时要求 `CompanyMeta.company_id/company name` 与 result exact（计划:3381-3384）。
- **影响**：实施 Agent 跑偏 / 正常导入被拒绝 / identity cross-check 被弱化 / review 不可验收。
- **建议改法和验证点**：在 Controller plan 中选择一个可表达且单一 owner 的契约：
  1. 若 bundle 的既有 target 就是名称，则 closure inspection 只返回并要求 `target_company_name`，并删除不存在的 company-id cross-check；company-id 仍由 manifest↔Fins inventory raw-exact gate 保证。
  2. 若确实必须把 bundle 绑定到 legacy company id，则必须将 owner descriptor 和 typed inspection 明确扩展为彼此独立的 `target_company_id` 与 `target_company_name`，定义旧 bundle 不含该字段时的本-slice fail-closed 行为，并测试 ID-only/name-only/mismatch/正常不同值四类。

  不能把 `target_company` 同时解释为两个值，也不能让 CLI 解析私有 descriptor 兜底。
- **修复风险（低/中/高）**：低。
- **严重程度（低/中/高/严重）**：高。

## Open questions

无。该问题由修订计划自身的 DTO 字段与当前 bundle owner/schema 的直接事实确定，不依赖外部系统。

## Residual risks

- 在修复 finding 后，operator manifest 仍只是 legacy 缺失市场字段的显式 assertion，不是交易所级认证事实；应按 S15-CTRL-14 留给 multi-listing/auth 后续 owner。
- locator/hash 不是运行时 legacy-root resolver；该能力继续由 S15-CTRL-14 指定的独立 future migration work unit 承担。
- downgrade 是有意的 administrative destruction；S15-CTRL-08 的 catalog preflight 与 Slice 8.1 backup/restore acceptance 应共同约束实际操作。

## 最终结论

**FAIL**。开放 finding 为 **高 1 / 中 0 / 低 0**，因此 Slice 1.5 必须保持冻结，不能进入 implementation handoff。除上述 typed bundle target closure 外，Terra `TERRA-S15-001..004` 与 MiM `M01..M13` 的 Controller 裁决均已有可直接实施、可验证的计划闭合。
