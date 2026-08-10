# Code Review

## Scope

- Mode: current changes
- Branch or PR: `codex/investment-platform`
- Base: `3a70a16`
- Output file: `docs/reviews/code-review-20260810-slice-1.3-evidence-locator-terra.md`
- Included scope: Slice 1.3 allowlist 中相对基线的 production、tests、`dayu/fins/README.md`，以及指定的计划、plan-fix、plan-acceptance、implementation artifact。
- Excluded scope: Slice 1.4、Slice 3.1、live/network/model/broker、提交/推送/PR；未审查本次审查期间由其他工作流新出现的非指定 review artifact。
- Parallel review coverage: 无（Terra 独立审查）。已沿 `FinsService -> FinsRuntime -> repositories/FinsToolService` 真实链路检查 strict parser/canonical bytes、source/processed identity、双 source-kind、request-scoped cache、pre/postflight、五类 projection、citation 输出、Protocol/delegate 与依赖边界。

## Findings

### F-01-未修复-高-公开 Runtime 入口绕过 repository/schema 与 DTO 严格校验
- **入口/函数**: `DefaultFinsRuntime.resolve_evidence_locator()`、`validate_evidence_locator()`、`read_citation_projection()`。
- **文件(行号)**: `dayu/fins/service_runtime.py:260-311, 575-590, 2418-2482`。
- **输入场景**: 调用方不经 `parse_evidence_locator_request()`，直接构造一个 otherwise-valid 的 `EvidenceLocatorRequest(schema_version="unknown", repository_id="untrusted.repo", ...)`；或将一个已生成 projection 的 `repository_id` 替换为 `untrusted.repo` 后传入 validate/read。
- **实际分支**: `_to_evidence_identity()` 与 `_locator_to_evidence_identity()` 丢弃 `schema_version`/`repository_id`，`_verify_evidence_identity()` 只校验其余 identity；resolve 在 `_build_current_projection()` 强制写回常量 repository，validate 成功，read 又把未经校验的 caller locator 原样放入 `CitationProjection`。
- **预期行为**: S13-CTRL-01/03/05 要求 unknown schema/repository fail closed，且 `validate/read` 必须验证 persisted projection 本身，不能以当前 owner 状态覆盖或忽略其字段。
- **实际行为**: 已直接复现：带 `schema_version="unknown"` 与 `repository_id="untrusted.repo"` 的 request 成功 resolve 为 `dayu.fins.public.v1`；将结果的 repository 改回 `untrusted.repo` 后，`validate` 成功且 `read_citation_projection(...).locator.repository_id` 仍为 `untrusted.repo`。此外，source+document 分支不读取或校验 payload 类型，直接构造 `locator_kind=document` 配合非 `DocumentLocatorPayload` 也可被接受并持久化为不一致 projection。
- **直接证据**: parser 虽在 `dayu/fins/domain/evidence_locator.py:473-484, 544-549` 拒绝 schema/repository，但 Service/Runtime public API 接受 DTO；`service_runtime.py:273-284, 300-311` 未携带这两个字段，`2418-2438` 未调用 domain 校验，`2404-2415` 覆盖 repository，`2454-2481` 再次忽略 repository 并返回 caller locator。`542-581` 对 source/document 仅判断 locator kind。
- **影响**: 信任边界被绕过，持久化或跨层传入的错误 repository/schema projection 会被当作有效证据，citation 中可出现未受支持的 repository identity；同时可出现 kind/payload 不一致的 locator。该行为直接违背 public locator 的 fail-closed contract。
- **建议改法和验证点**: 在 domain 唯一 owner 增加 DTO 级的完整 invariant validator（或在 DTO 初始化时验证），Runtime 三个 public 方法在任何 identity 投影前强制调用；必须覆盖 repository、schema、所有枚举、canonical ticker/document/hash、artifact-kind/locator-kind/payload 配对。补充 direct-DTO（不经 parser）的 request/projection 反例：unknown repository/schema、错误 payload 类型、source+document 错 payload，三个 Service delegate 路径均应抛 `EvidenceLocatorError`。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### F-02-未修复-高-逻辑删除的 counterpart 仍可被工具 fallback 读取，导致 source_kind 与 processed bytes 脱节
- **入口/函数**: processed locator 的 `_verify_evidence_identity()` -> request-scoped `FinsToolService`。
- **文件(行号)**: `dayu/fins/service_runtime.py:2033-2059, 2322-2376`；`dayu/fins/tools/service.py:1777-1788, 1805-1815`；`dayu/fins/storage/_fs_source_document_core.py:791-823, 556-580`。
- **输入场景**: 同一 `(ticker, document_id)` 有 active material（request 的 exact source）和逻辑删除但目录仍存在的 filing；processed meta 正确标记 `source_kind=material` 并与 material 的 version/fingerprint 闭合。两份 source 内容或处理结果不同。
- **实际分支**: counterpart filing 的 `is_deleted=true` 令 `_counterpart_source_active()` 返回 false，material preflight 通过。随后 fresh `FinsToolService` 不接收 `source_kind`，`_resolve_source_kind()` 只要 filing 的 `get_source_handle()` 未抛异常就优先返回 filing；该 handle 仅检查 meta 文件存在。postflight 只重读 material 与 counterpart 的 active 状态，因 filing 仍 deleted 而继续通过。
- **预期行为**: S13-CTRL-03/04/06 要求 fragment 从 exact source identity 的唯一无歧义 owner 读取；如果现有 tool API 无法选择 request 的 source_kind，任何能触发其 filing-first fallback 的 counterpart 都必须 fail closed，不能发布标记为 material 的 filing-derived processed citation。
- **实际行为**: logical delete 仅在 meta 写入 `is_deleted=true`，不移除 meta/目录；因此底层工具仍能优先构建 filing processor。返回 fragment 可来自 filing，而 projection/primary SHA/processed closure 全部绑定 material，形成 source-kind 与 evidence bytes 的错误 identity 闭包。
- **直接证据**: `service_runtime.py:2054-2059` 将 deleted counterpart 视为不存在；`tools/service.py:1805-1813` 未读 `is_deleted`、固定 filing 优先；FS `get_source_handle()` 的唯一存在性条件是 meta path 存在（`_fs_source_document_core.py:571-580`），而 logical delete 只改同一 meta 的字段（`791-823`）。runtime 的 request-scoped 构造（`2349`）并未改变该 fallback 语义。
- **影响**: 对同 ID 的 filing/material 重用场景，citation 可静默引用错误源文档；hash 和 pre/postflight 仍能全部通过，审计会把错误 processed bytes 归属到请求 source_kind。这是财报证据定位的 correctness/trust-boundary 错误。
- **建议改法和验证点**: 在不改 `FinsToolService` public API 的既定限制下，把 counterpart 的“会被 tool 发现”状态作为歧义：只要 counterpart handle/source meta 存在即拒绝（包括逻辑删除）；或在可演进的公共工具契约中显式传入 exact `source_kind`，并使缓存键包含它。新增 regression：deleted filing + active material、deleted material + active filing，分别覆盖 document/page/section/table/xbrl processed 路径，断言 resolve/validate/read 均为 `ambiguous_source_identity`，且 processor 未创建。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### F-03-未修复-中-非 document payload 未做精确字段集校验，未知字段被静默丢弃
- **入口/函数**: `parse_evidence_locator_request()` / `parse_evidence_locator_projection()` 的 `_parse_locator_payload()`。
- **文件(行号)**: `dayu/fins/domain/evidence_locator.py:790-840`。
- **输入场景**: 解析 `locator_kind="page", locator_payload={"page_no": 1, "uri": "s3://private/key"}`，或 table/xbrl/section payload 中含任意额外字段。
- **实际分支**: `_parse_locator_payload()` 仅读取各 kind 的必需键，未调用 `_require_exact_keys()`；返回的 slots dataclass 忽略未知键。
- **预期行为**: S13-CTRL-01/02 要求 nested locator payload 也 strict，拒绝 missing/unknown 字段和任何 arbitrary JSON extension，而不是静默进行 schema 降级。
- **实际行为**: 顶层 unknown 会拒绝，但 page/section/table_cell/xbrl_fact 的 nested unknown 被接受并丢弃；同一 raw payload 的语义与 canonical projection 不再一一对应。
- **直接证据**: `790-840` 没有针对四种 non-document payload 的 exact-key 调用；现有 tests 只断言顶层 extra（`tests/fins/test_evidence_locator_domain.py:218-223`）及 document payload 非空（`321-328`），没有任一 non-document nested-extra 反例。
- **影响**: 严格 parser contract 不成立，调用方以为已被接受的字段不会反映到 canonical bytes/projection；未来 schema 演进或不受信任 payload 会被无声降级，削弱审计确定性。
- **建议改法和验证点**: 每个 kind 在读取字段前以常量字段集调用 `_require_exact_keys()`；补 page、section、table_cell、xbrl_fact 四个 request/projection nested-extra 拒绝测试，并覆盖 missing-field 的 `invalid_fields`。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。

## Residual Risk

- 已通过：定向 91 项测试；`tests/fins`、`tests/services`、`tests/application/test_fins_service.py`、依赖边界测试共 2,041 项；全量 `pyright`；变更文件 `ruff check`；tracked 与新增文件的 whitespace diff check。
- 未独立复算 worker 报告中的逐生产模块 statement coverage；本审查发现的 direct-DTO、deleted-counterpart 与 nested-extra 反例均未被当前测试覆盖，因而现有绿测不能自证 S13-CTRL-01/03/04/06/07 的这些边界。
- 未运行 live/network/model/broker，也未进行 commit/push/PR。
