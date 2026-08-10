# Slice 1.3 Evidence Locator pre-edit adversarial plan review

- **审查日期**：2026-08-10 18:10:45 CST（本机时钟）
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 §6.2、§6.3、Slice 1.3、Slice 1.4、Slice 3.1、validation 与 stop；以及 `docs/reviews/plan-fix-20260810-slice-1.3-evidence-locator-codex.md`
- **基线**：`b45e0ee40467fee31f524a348a8fd8198087800d`，branch `codex/investment-platform`
- **方式与边界**：独立只读审查；未运行 live/network/model/broker，未修改计划、production、tests、README，未 commit/push/PR。本 artifact 是本次唯一写入。

## 审查结论

**FAIL**。Open：**H=2 / M=0 / L=0**。

勘误已经有效收敛了 repository namespace、五类严格 payload、canonical JSON、primary exact bytes、source/processed version-fingerprint-reprocess closure、真实 `FinsService` delegate、路径泄漏扫描和 Slice 3.1 的归属方向；这些不是本次 findings。可是现有公共读取 API 无法保留 `source_kind`，而 tenant 关联的语义又把公共 reference 与私有范围混为一谈。两者都会让实施者在允许范围外自行设计安全语义，故尚不能进入 Slice 1.3 实现。

## 已检验的关键假设

| 假设 | 直接证据 | 结论 |
| --- | --- | --- |
| `dayu.fins.public.v1` 能避免 FS/S3/backend/path/tenant 投影差异 | §6.3 明确把它定义为逻辑、公共且 backend/path/tenant-independent namespace（计划:322-325），并要求 Slice 1.4 FS/S3 对同 owner bytes 一致（计划:400-402、959-962）。 | 可实施；常量不能单独证明内容绑定，但 document/version/fingerprint/primary/locator hashes 已提供绑定。 |
| source exact bytes 与可选 meta SHA 可由 owner 获取 | `SourceDocumentRepositoryProtocol` 公开 `get_primary_file` 与 `get_primary_source`（`repository_protocols.py:175-184`）；`Source` 公开二进制 `open()`（`dayu/engine/processors/source.py:42-55）。 | 可实施；计划的“meta SHA 存在时必须相等、始终实算”是正确闭包。 |
| processed closure 有现有真实字段而非虚构字段 | processed meta 真实写入 `source_document_version`、`source_fingerprint`、`reprocess_required`（`_fs_processed_core.py:305-318`）；处理跳过规则也比较 version/fingerprint/parser/schema/reprocess（`processing_helpers.py:115-133`）。 | 可实施，但须解决下述 source-kind 归属。 |
| table/XBRL 的 fail-closed 规则可放在 DTO/resolver owner | `get_table` 的 records/markdown/raw_text 是公开结果，`query_xbrl_facts` 返回已归一化 fact 行；计划已规定 markdown、越界、重复、unsupported 均拒绝（计划:352-359、944-950）。 | 可实施；需要按计划覆盖 0/1/duplicate，而不是依赖现有 tool 的去重策略。 |
| Service 调用链与泄漏测试已被纳入范围 | Slice 1.3 allowlist 已含真实 `dayu/services/fins_service.py`（计划:934-937），且测试项含 Service delegate identity、递归 path/URI/bucket/handle scan（计划:944-953）。 | 已修复此前 allowlist 缺口。 |

## Findings

### F-01-未修复-[高]-现有 public FinsToolService 无法按 locator 的 exact source_kind 重放 processed citation
- **位置**: §6.3.2/§6.3.3/§6.3.4，尤其计划:355-389；Slice 1.3 call path 与 allowlist，计划:934-950。
- **问题类型**: 契约缺失 / 架构边界 / 不可直接实施。
- **当前写法**: locator 将 `source_kind` 列为 identity，要求 runtime 用 `ticker + document_id + exact source_kind` 读取并禁止 filing/material fallback；但 processed locator 的内容必须经现有 `FinsToolService` public API 读取，且禁止调用其 private 方法或改 storage implementation。
- **反例/失败场景**: 同一 ticker 下 filing 与 material 恰好使用相同 `document_id`。runtime 可先成功验证请求为 material；随后它只能调用现有 `FinsToolService.get_document_sections/read_section/get_table/get_page_content/query_xbrl_facts`，这些 API 均不接收 `source_kind`。内部 `_resolve_source_kind()` 固定先探测 filing 再 material（`dayu/fins/tools/service.py:1791-1815`），故 material locator 会从 filing primary bytes 建 processor 并产生 citation bytes。更糟的是 cache key 仅为 `(ticker, document_id)`（`tools/cache.py:20-30`，使用处 `tools/service.py:1742-1754`），一次 filing 读取会让后续 material 读取直接复用 filing processor。processed repository 的 `get_processed_meta()` 也只以 `(ticker, document_id)` 取值（`repository_protocols.py:203-208`；FS 路径读取见 `_fs_processed_core.py:133-164`），因而无法替 runtime 消除这一歧义。
- **为什么有问题**: 这直接违反计划的 exact-source-kind/fail-closed 要求，且可以生成“identity 属于 material、content/locator hash 实际来自 filing”的持久化 projection。仅测试 wrong source kind 或同 ID 不同 kind 无法修复接口缺失；实施者若绕过 public API、调用 private processor，或在 runtime 猜测 filing/material，都会违反 §6.3.4 和 allowlist。现有 processed meta 虽保存 `source_kind`（`_fs_processed_core.py:305-314`），计划却没有要求它与 request 的 source_kind exact compare，故 version/fingerprint 偶然相同也不能阻止错误接受。
- **直接证据**: 计划:326、363-365、386-389、940-950；`dayu/fins/tools/service.py:1727-1815`；`dayu/fins/tools/cache.py:20-30`；`dayu/fins/storage/repository_protocols.py:188-220`；`dayu/fins/storage/_fs_processed_core.py:305-328`。
- **影响**: persisted locator 不再唯一指向其声明的 source；validate/read 可错误重放另一来源的文本、表格或 XBRL fact，破坏 citation auditability，也使 FS/S3 canonical 测试只能覆盖未碰撞的 happy path。
- **建议改法和验证点**: 在 master plan 的 §6.3.4 与 Slice 1.3 allowlist 中显式加入 `dayu/fins/tools/service.py`、`dayu/fins/tools/cache.py` 及对应 tests；新增一个由 `FinsToolService` 公开拥有的、显式接受 `SourceKind` 的 evidence-read API（或将与 evidence 相关的公开读取方法都增设这个必填参数），内部 processor/meta/cache key 必须为 `(ticker, document_id, source_kind)`，禁止 fallback。resolver 对 processed 必须同时验证 `processed_meta["source_kind"] == locator.source_kind`，缺失或不等一律拒绝。若不愿本 slice 扩展该公共 API，则 stop：现有协议无法表达可验证的 processed source owner，不能用 runtime/private seam 代替。测试应建立同 ticker/同 document_id 的 filing+material，先后交错 resolve/validate/read 五类可用 locator，证明各自产生不同且稳定 bytes；还要覆盖 processed meta source_kind mismatch/missing、cache pollution、以及 collision 下的 fail-closed 分支。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### F-02-未修复-[高]-Slice 3.1 的跨租户 EvidenceLink 规则把公共 reference 与私有 tenant ownership 混淆，无法生成可验收的隔离约束
- **位置**: §6.2 identity/tenancy 与 §6.3.5，计划:279-286、391-398；Slice 3.1，计划:997-1002。
- **问题类型**: 契约缺失 / 状态与 owner 边界 / 测试缺口。
- **当前写法**: §6.2 明确 companies、securities 和原始 Fins document identity 是公共 reference，私有表才有 non-null `tenant_id`；§6.3.5 又要求 private Fact/Claim/EvidenceLink 的 `TenantScope` 与“其 company/security projection 同 tenant”，并称“same public locator 跨 tenant 私有 link”必须拒绝。Slice 3.1 本身只写 cross-company reject，tests 未列 tenant-scope、RLS 或 cross-tenant link 矩阵。
- **反例/失败场景**: tenant A 与 tenant B 均研究同一 public company/document/locator。这应当允许各自创建私有 Fact/Claim/EvidenceLink；若按“same public locator 跨 tenant 私有 link reject”字面实现，第二个租户会被错误拒绝。反之，若 EvidenceLink 可将 tenant A 的 ClaimVersion 与 tenant B 的 Fact 关联，而只检查公共 company/document/locator，则 RLS scope 之外的关联可被写入。由于 company/security 是公共 reference，本身没有 tenant 可以与 `TenantScope` 比较；这会逼实施者自创 tenant projection 或把 tenant 字段回填 Fins locator，均违背既定所有权。
- **为什么有问题**: 租户隔离是 §6.2 的硬安全语义，不是后续实现细节。当前文字既没有定义“跨租户 private link”的精确定义，也没有把其 owner、schema 约束、repository signatures 与测试放进 Slice 3.1；因此不能证明 Slice 1.3 的公共 locator 在两个租户中可安全复用，或拒绝真正的 A-to-B 私有关联。
- **直接证据**: 计划:279-286、391-398、997-1002；现有 `SourceSubscription` 已展示正确方向——私有 `tenant_id` 指向 organization，而 company/security 只是公共 FK（`dayu/investment/storage/models_identity.py:251-281`）。
- **影响**: 实施者可能做出过度拒绝（公共事实无法被多个租户独立使用）或隔离失效（不同 tenant 的 Fact/ClaimVersion 被同一 EvidenceLink 关联）；审查也无法通过一条“跨 tenant”测试判定正确行为。
- **建议改法和验证点**: 只在 Slice 3.1 收敛，不给 Fins locator 加 tenant。将规则改为：Fact、Claim、ClaimVersion、EvidenceLink 均为 tenant-private；EvidenceLink 的所有私有端点（至少 ClaimVersion 与 Fact，及任何 tenant-private company/security projection）必须与调用 `TenantScope` 相同；公共 company/security/document/locator 可被不同 tenant 的各自私有 records 重复引用。通过 domain validation 加 repository first-parameter `TenantScope`，并在 PostgreSQL schema 使用含 `tenant_id` 的 composite FK/unique key 或等效约束，防止跨 tenant ID 关联。Slice 3.1 tests 必须分开断言：(1) A/B 都可引用同一已验证 public locator；(2) A 不能读、写或把 B 的 Fact/ClaimVersion 连成 EvidenceLink；(3) cross-company 仍拒绝；(4) RLS 与 repository predicate 双层拒绝。同步在 Slice 3.1 Allowed/Invariant/Tests 写出这些要求，移除“same public locator 跨 tenant private link 拒绝”的歧义表述。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

## Open questions

无。两项均有当前计划与代码的直接证据，应先改 master plan，而不是留给实现阶段选择。

## Residual risks 与建议追踪归属

- 修复 F-01 后，Slice 1.3 仍应按 S13-CTRL-07/08 以真 FS fixture 覆盖 source bytes、可选 meta SHA、processed stale/reprocess、五类 payload、canonical bytes 与递归泄漏扫描；Slice 1.4 再以 MinIO 证明同 owner bytes 的跨 backend projection，不以 fake 代替。
- 修复 F-02 后，Slice 3.1 的 PostgreSQL migration/repository tests 应成为 tenant link 的真源；Slice 1.3 只验证公共 locator，不承担 tenant admission。
- 不建议扩大为重新设计 locator 或存储层：`repository_id` 固定值、source exact bytes、processed source-version/fingerprint/reprocess closure、table records-only、XBRL canonical-row hash 和真实 Service delegate 是当前最小且合理的方向。

## 最终判定

**FAIL（Open H=2 / M=0 / L=0）**。先修正上述两处计划与 allowlist/owner 描述，再进行双路 re-review；在 open 归零前，Slice 1.3 的 code/tests/README 应继续冻结。
