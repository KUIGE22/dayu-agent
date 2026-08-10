# Slice 1.3 Fins Evidence Locator implementation artifact

- **Work unit**：Investment Platform Restoration / Slice 1.3
- **Worker**：DeepSeek Flash
- **日期**：2026-08-10
- **状态**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**（corrective round 2 双路复审通过；未 push / PR / Slice 1.4 / live/network）
- **基线**：`3a70a16`（clean accepted HEAD，branch `codex/investment-platform`）
- **目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md` §6.2/§6.3、Slice 1.3 S13-CTRL-01..08、Slice 3.1 边界
- **Controller fix / acceptance**：`docs/reviews/plan-fix-20260810-slice-1.3-evidence-locator-codex.md`、`docs/reviews/plan-acceptance-20260810-slice-1.3-evidence-locator-codex.md`
- **Code review**：`docs/reviews/code-review-20260810-slice-1.3-evidence-locator-terra.md`（F-01/F-02/F-03，全部 ACCEPTED）、`docs/reviews/code-review-20260810-slice-1.3-evidence-locator-mimo-native.md`（Finding 1，ACCEPTED）
- **Code re-review round 1**：`docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-terra.md`（F-01 bool-as-int / F-02 object 宽类型，Controller 裁决为 S13-CR-05/06 并 ACCEPTED）、`docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-mimo-native.md`（PASS，仅作覆盖面证据）
- **Review fix（round 1）**：`docs/reviews/slice-1.3-fins-evidence-locator-review-fix-20260810-deepseek.md`
- **Corrective review fix（round 2）**：`docs/reviews/slice-1.3-fins-evidence-locator-corrective-review-fix-20260810-deepseek.md`

## 1. Scope

本 artifact 只修改 Slice 1.3 allowlist 内的文件：

- `dayu/fins/domain/evidence_locator.py`（新增：DTO / strict parser / canonical bytes owner）
- `dayu/fins/domain/__init__.py`（导出）
- `dayu/fins/service_runtime.py`（`FinsRuntimeProtocol` + `DefaultFinsRuntime` 三个 exact 方法）
- `dayu/services/protocols.py`（`FinsServiceProtocol` 三个 exact 方法）
- `dayu/services/fins_service.py`（`FinsService` 三个 delegate 方法）
- 相关 Fins domain/runtime/service tests：
  - `tests/fins/evidence_locator_testkit.py`（新增 testkit）
  - `tests/fins/test_evidence_locator_domain.py`（新增）
  - `tests/fins/test_evidence_locator_runtime.py`（新增）
  - `tests/services/test_fins_evidence_locator_service.py`（新增）
- `dayu/fins/README.md`（owner/API/错误与 citation 使用方式同步）
- `docs/reviews/slice-1.3-fins-evidence-locator-implementation-20260810-deepseek.md`（本 artifact）

未修改：`dayu/fins/tools/service.py` / `tools/cache.py`、storage implementation、
engine processor、investment、migration、startup、根 `README.md`。

## 2. Pre-edit accepted-contract audit

实施前只读审计确认以下安全点（与 accepted contract 一致，无新 plan gap）：

1. 现有 Fins 无 repository identity 真源；按 plan 固定 `REPOSITORY_ID = "dayu.fins.public.v1"`，
   与 backend/path/tenant 无关，unknown id 在 parser 层 fail closed。
2. 现有 `FinsToolService` public API（`get_document_sections` / `read_section` /
   `get_page_content` / `get_table` / `query_xbrl_facts`）均不接收 `source_kind`，
   且 `_resolve_source_kind()` 固定 filing→material fallback、processor cache key 仅
   `(ticker, document_id)`；因此 exact/counterpart preflight 保证唯一无歧义 owner，
   且每次读取用 request-scoped 空 cache 实例，无需改 `tools/service.py` / `cache.py`。
3. processed meta 真实字段为 `source_kind` / `source_document_version` /
   `source_fingerprint` / `reprocess_required`；source meta 真实字段为 `document_version` /
   `source_fingerprint` / `ingest_complete` / `is_deleted`。processed closure 直接闭合。
4. primary bytes 唯一来源 `get_primary_source(...).open()`；可选
   `get_primary_file(...).sha256` 存在时必须相等（lower 归一比较），不存在不跳过实算。
5. XBRL canonical row 13 字段对应 `_normalize_single_fact` 输出的 13 字段（排除派生
   `scale`）；table records/markdown 由 `_build_table_data_payload` 的 `data["kind"]` 区分。
6. `FinsService` 是真实实现且已在 allowlist；三个新方法只 delegate 到注入 runtime。
7. tenant isolation 归 Slice 3.1；Fins locator 无 tenant 字段，本 slice 只拒绝 wrong
   repository/ticker/document/source kind 与 content identity。

## 3. Implementation

### 3.1 domain/evidence_locator.py

- closed enum：`ArtifactKind`（source/processed）、`LocatorKind`
  （document/page/section/table_cell/xbrl_fact）；source kind 复用 `SourceKind`。
- 五类 strict payload（`frozen=True, slots=True`）：`DocumentLocatorPayload`（空）、
  `PageLocatorPayload(page_no>`0)`、`SectionLocatorPayload(section_ref 非空)`、
  `TableCellLocatorPayload(table_ref, row_index>=0, column)`、
  `XbrlFactLocatorPayload(concept, fact_sha256 lower-64-hex)`。
- `EvidenceLocatorRequest`（含 schema_version）与 `EvidenceLocatorProjection`
  （精确字段集，`to_json()` 产 canonical JSON bytes）均为 frozen+slots；
  `CitationProjection`（locator/content_type/content_bytes）frozen+slots。
- `parse_evidence_locator_request` / `parse_evidence_locator_projection` 严格双向拒绝：
  missing/unknown 字段、bool-as-int、空字符串、非 canonical ticker/document id
  （`[A-Za-z0-9][A-Za-z0-9.\-]*` / `[A-Za-z0-9][A-Za-z0-9_\-]*`）、非小写 64-hex SHA、
  未知 schema version / repository id / enum 值；document payload 必须为空。
- `canonical_json_bytes`（UTF-8、sort_keys、compact、allow_nan=False）与 `sha256_hex`、
  `is_lower_hex_sha256` 公共 helper。
- `EvidenceLocatorError(code, message)` 统一 fail-closed 异常。

### 3.2 service_runtime.py

`FinsRuntimeProtocol` 新增三个 exact 方法：
`resolve_evidence_locator(request) -> EvidenceLocatorProjection`、
`validate_evidence_locator(locator) -> None`、
`read_citation_projection(locator) -> CitationProjection`。

`DefaultFinsRuntime` 实现（resolve/validate/read 复用同一验证核心
`_verify_evidence_identity`）：

- `_preflight_source_identity`：exact `ticker+document_id+source_kind` 读 source meta；
  不存在/逻辑删除/未完成摄入/非法 version/fingerprint 拒绝；counterpart source kind
  探测，active 双 kind 抛 `ambiguous_source_identity`；processed 额外闭合
  exists/not-deleted/reprocess_required=false/`source_kind` 逐字相等/
  `source_document_version`/`source_fingerprint` 与 source exact 相等。
- `_read_primary_source`：`get_primary_source().open()` 读 exact bytes 实算 SHA；
  可选 `get_primary_file().sha256` 存在时 lower 归一相等校验（不等抛
  `primary_sha_mismatch`）；media_type 默认 `application/octet-stream`。
- `_build_request_scoped_tool_service`：每次用同一 repositories/registry 新建
  `FinsToolService`（空 cache），绝不调用 `get_tool_service()` 共享实例。
- `_resolve_fragment_bytes`（模块级）：source artifact 仅允许 document 并返回
  primary bytes；processed 按 kind 从 tool public API 提取计划规定的 exact 字段集，
  剥离 wrapper/citation；page `supported=false` 拒绝；table 必须 records，
  row 越界/缺列拒绝；XBRL 逐 canonical 13 字段 row 求 SHA，恰好一条匹配
  （0/重复拒绝）。
- `_verify_evidence_identity`：preflight -> identity 字段逐项比较 -> primary 实算
  -> fragment 读取（tool 异常包装为 `evidence_read_failed`）-> locator SHA 比较
  -> `_postflight_identity` double-read（重读 exact/counterpart source meta、
  processed meta、primary bytes 并与 preflight 快照逐字段比较，任何漂移拒绝）。
- 三个 public 方法：resolve 返回 current projection；validate 只验证不覆盖 caller
  projection；read 返回 `CitationProjection`（source artifact content_type 用
  primary media_type，processed 用 `application/json`），
  `sha256(content_bytes) == locator.locator_content_sha256`。

### 3.3 services/protocols.py + services/fins_service.py

`FinsServiceProtocol` 新增同名三方法；`FinsService` 三方法只 delegate
`self.fins_runtime`，不接触任何 storage handle。

### 3.4 tests

- `tests/fins/evidence_locator_testkit.py`：`MemorySource`、`EvidenceSourceRepository` /
  `EvidenceProcessedRepository` / `EvidenceCompanyRepository`（完整实现协议）、
  `FakeEvidenceProcessor`（完整 `DocumentProcessor` + page/xbrl 能力）、
  `EvidenceProcessorRegistry`（继承 `ProcessorRegistry`，可注入 per-document 数据与
  `create_hook` 模拟 race）、`StubBlobRepository` / `StubFilingMaintenanceRepository`。
- `tests/fins/test_evidence_locator_domain.py`（27 tests）：frozen+slots、canonical
  JSON sorted/compact/NaN 拒绝、SHA helper、五 payload 解析、missing/unknown/bool-int/
  空串/非 canonical ticker/document id/非 hex/未知 schema/repository/enum、document
  payload 必须为空、projection round-trip、递归泄漏扫描。
- `tests/fins/test_evidence_locator_runtime.py`（37 tests）：document+source/processed、
  page happy + unsupported、section、table_cell records happy + markdown/row 越界/缺列、
  XBRL 0/1/duplicate、validate/read happy + citation SHA 闭合、version/fingerprint/
  primary/locator drift、meta SHA optional/mismatch、source deleted/未摄入/非法指纹/
  缺 version、wrong identity、dual-kind collision、shared-cache stale processor 不复用、
  pre/post race（meta 与 primary bytes）、processed missing/deleted/reprocess/version/
  fingerprint/source_kind mismatch/缺失、payload 类型不匹配、tool 读取失败包装、
  输出递归泄漏扫描。
- `tests/services/test_fins_evidence_locator_service.py`（7 tests）：`FinsService`
  满足 `FinsServiceProtocol`、三个方法真实 delegate 到 runtime、错误透传、
  不触碰 host、citation SHA 闭合。

### 3.5 README

`dayu/fins/README.md` 新增 §3.3 "Evidence Locator 与 citation projection"（DTO/parser/
canonical bytes owner、三个对外方法、调用路径与 fail-closed 语义），并在 §3.1 对外暴露
列表补入三个方法；未触碰根 README。

## 4. Verification

- 相关测试全绿：
  - `tests/fins/` 全量：1964 passed
  - `tests/services/` + `tests/application/`：1483 passed
  - 架构护栏 `tests/architecture/test_dependency_boundaries.py`：passed
  - 本 slice 新增 71 tests 全通过
- coverage（新增 production statement，`git diff` 新增行 × coverage missing 交叉）：
  - `dayu/fins/domain/evidence_locator.py`：93%
  - `dayu/fins/service_runtime.py` 新增语句：99.1%（未覆盖 10 行均为防御/不可达分支）
  - `dayu/services/fins_service.py` 新增三方法：全部覆盖
  - `dayu/services/protocols.py`：100%
- pyright：修改的 production/tests 全部 0 errors / 0 warnings。
- Ruff（F + I + default）：修改文件全部通过；顺带修复 `service_runtime.py` 中 6 处
  pre-existing E501 超长行，未引入新 violation。
- `git diff --check`：通过（见 §6）。
- 无新增 `Any` / `object` 字段 / `cast` / `type: ignore` / `hasattr` / `getattr` /
  coverage pragma / seam；所有新增/修改函数具备完整中文 Args/Returns/Raises docstring。

## 5. 未覆盖项与风险

- runtime 内少量防御性分支未覆盖：XBRL `facts` 非 list / 非 dict（service 层保证
  list[dict]，runtime 不可达）、`unsupported_locator_kind` 兜底（closed enum 不可达）、
  postflight 中 source 被删除/processed 变更分支。均为 fail-closed 防御路径。
- 未运行 live/network/model/broker；未启动 code review / commit / push / PR；未进入
  Slice 1.4（MinIO/S3）或 Slice 3.1（tenant composite FK/RLS）。
- Slice 1.4 需验证 FS/S3 对同 owner bytes 产生相同 canonical projection；
  Slice 3.1 需以真实 PostgreSQL integration 验证 tenant 隔离，本 slice 不承担。

## 6. Diff check

```
git diff --check
```

（结果：无空白错误；见最终 worker 报告。）

## 7. Final dual re-review closure

- Terra：`docs/reviews/code-final-rereview-20260810-slice-1.3-evidence-locator-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- MiM Native：
  `docs/reviews/code-final-rereview-20260810-202442-slice-1.3-evidence-locator-mimo-native.md`，
  PASS，open H/M/L=`0/0/0`。
- S13-CR-01..06 全部 CLOSED；无新 finding，无待修 production/test 项。
