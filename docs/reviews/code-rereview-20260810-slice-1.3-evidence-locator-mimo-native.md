# Code Re-Review

## Scope

- Mode: current changes
- Branch: `codex/investment-platform`
- Base: `3a70a16`
- Output file: `docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-mimo-native.md`
- Included scope: Slice 1.3 allowlist 内全部文件 — `dayu/fins/domain/evidence_locator.py`（新增）、`dayu/fins/domain/__init__.py`、`dayu/fins/service_runtime.py`、`dayu/services/fins_service.py`、`dayu/services/protocols.py`、`dayu/fins/README.md`、四份测试/testkit、`tests/application/test_fins_service.py`
- Excluded scope: `dayu/fins/tools/service.py`、storage implementation、engine processor、investment、migration、startup、根 `README.md`
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量代码走读。

## Corrective Re-Review Context

本次 corrective re-review 独立验证四项 accepted findings 的修复是否正确、完整且无副作用：

| ID | 来源 | 严重程度 | 修复状态 |
|---|---|---|---|
| Terra F-01 | Terra code-review | 高 | FIXED |
| Terra F-02 | Terra code-review | 高 | FIXED |
| Terra F-03 | Terra code-review | 中 | FIXED |
| MiM Finding 1 | MiM Native code-review | 中 | FIXED |

## Finding Verification

### Terra F-01（高）：公开 Runtime 入口绕过 repository/schema 与 DTO 严格校验 — VERIFIED FIXED

**验证方法**：独立走读 `evidence_locator.py` 新增的 `validate_evidence_locator_request()` / `validate_evidence_locator_projection()` / `_validate_dto()`，以及 `service_runtime.py` 三个 public 方法的调用点。

**代码证据**：
- `dayu/fins/domain/evidence_locator.py:438-557` — `_validate_dto()` 覆盖：`_check_schema_version`（request only）、`_check_repository_id`、`_check_canonical_ticker`、`_check_canonical_document_id`、`_check_text`（document_version）、`_check_lower_hex64`（source_fingerprint / primary_content_sha256 / locator_content_sha256）、`_check_source_kind` / `_check_artifact_kind` / `_check_locator_kind`（`isinstance` 收窄拒绝字符串冒充枚举）、`_check_payload_pairing`（kind/payload 一致性）、`_check_artifact_combo`（source 只允许 document + `DocumentLocatorPayload`）。
- `dayu/fins/domain/evidence_locator.py:909,975` — parser 构造 DTO 后也调用同一 validator，单一真源。
- `dayu/fins/service_runtime.py` — `resolve_evidence_locator`（行 ~2637）、`validate_evidence_locator`（行 ~2653）、`read_citation_projection`（行 ~2670）在任何 identity 投影前调用 `validate_evidence_locator_request` / `validate_evidence_locator_projection`。
- **测试覆盖**：`test_validate_request_rejects_unknown_schema_and_repository`、`test_validate_request_rejects_wrong_payload_type`、`test_validate_request_rejects_source_wrong_payload`、`test_validate_request_rejects_bad_canonical_or_hash`、`test_validate_dto_rejects_raw_string_enum`、`test_validate_projection_rejects_unknown_repository`（domain）；`test_resolve_rejects_direct_dto_unknown_schema_and_repository`、`test_validate_and_read_reject_direct_dto_unknown_repository`、`test_resolve_rejects_direct_dto_wrong_payload_type`（runtime）；`test_service_rejects_direct_dto_unknown_schema_and_repository`（service，三个 delegate 路径）。

**结论**：direct-DTO（不经 parser）的 unknown schema/repository、错误 payload 类型、source+非 document payload、字符串冒充枚举、非 canonical 标识/非法 hash 均在 resolve/validate/read 三个入口抛 `EvidenceLocatorError` 且错误码稳定。**FIXED，无残留问题。**

### Terra F-02（高）：逻辑删除的 counterpart 仍可被工具 fallback 读取 — VERIFIED FIXED

**验证方法**：独立走读 `_counterpart_source_visible()` 与 preflight/postflight 逻辑，以及双向五 kind 参数化测试。

**代码证据**：
- `dayu/fins/service_runtime.py:2036-2068` — `_counterpart_source_visible()` 使用 `get_source_handle()`（与 `FinsToolService._resolve_source_kind()` 的 filing-first 探测同一存在性判定），含 `is_deleted=true` 的 meta 文件仍存在即返回 `True`。
- `dayu/fins/service_runtime.py:2125-2134` — `_preflight_source_identity()` 在 `counterpart_visible` 为 True 时抛 `ambiguous_source_identity`。
- `dayu/fins/service_runtime.py:2238-2260`（postflight）— 重读 counterpart 可见性，漂移同样拒绝。
- `_SourceIdentityState.counterpart_active` 已改名为 `counterpart_visible`，语义对齐。
- **测试覆盖**：
  - `test_deleted_filing_counterpart_ambiguous_all_kinds`（active material + deleted filing，5 种 processed payload，validate 路径，`create_call_count == 0`）。
  - `test_deleted_material_counterpart_ambiguous_all_kinds`（active filing + deleted material，5 种 processed payload，read 路径，`create_call_count == 0`）。
  - `test_deleted_counterpart_ambiguous_on_resolve_and_read`（resolve 与 read 双向）。

**结论**：deleted counterpart 下五种 processed locator kind 的 validate/read/resolve 全部在同一 preflight gate 拒绝，processor 未创建。修复与 `FinsToolService` 的真实工具探测行为一致。**FIXED，无残留问题。**

### Terra F-03（中）：非 document payload 未做精确字段集校验 — VERIFIED FIXED

**验证方法**：独立走读 `_parse_locator_payload()` 各分支，以及 domain 参数化测试。

**代码证据**：
- `dayu/fins/domain/evidence_locator.py:1224-1244` — 四种 non-document payload 分支均在读取字段前调用 `_require_exact_keys()`：
  - page: `{"page_no"}`
  - section: `{"section_ref"}`
  - table_cell: `{"table_ref", "row_index", "column"}`
  - xbrl_fact: `{"concept", "fact_sha256"}`
- request 与 projection parser 共用 `_parse_locator_payload()`，二者均覆盖。
- **测试覆盖**：
  - `test_parse_request_rejects_nested_payload_extra`（4 种 kind 各含 nested-extra）。
  - `test_parse_projection_rejects_nested_payload_extra`（4 种 kind 各含 nested-extra）。
  - `test_parse_request_rejects_nested_payload_missing`（4 种 kind 各缺键）。

**结论**：page/section/table_cell/xbrl_fact 的 nested-extra 与 missing 均在 request 与 projection parser 拒绝，错误码 `invalid_fields`。**FIXED，无残留问题。**

### MiM Finding 1（中）：primary file meta 异常未包装为 primary_read_failed — VERIFIED FIXED

**验证方法**：独立走读 `_read_primary_source()` try 块范围，以及 testkit `primary_file_missing` 模拟和测试。

**代码证据**：
- `dayu/fins/service_runtime.py` — `_read_primary_source()` 方法中 `get_primary_source()`、`source.open().read()` 与 `get_primary_file()` 纳入同一 `try/except OSError` 块（`FileNotFoundError` 为 `OSError` 子类），任何 source 主文件读取失败统一包装为 `EvidenceLocatorError("primary_read_failed", ...)`。
- testkit `EvidenceSourceRepository.get_primary_file` 的 `primary_file_missing` 分支抛 `FileNotFoundError`。
- **测试覆盖**：`test_primary_read_failed_when_primary_file_missing` 断言 `EvidenceLocatorError.code == "primary_read_failed"`。

**结论**：`get_primary_source` 成功但 `get_primary_file` 抛 `FileNotFoundError` 时统一包装为 `primary_read_failed`，不泄漏仓储异常类型。**FIXED，无残留问题。**

## Adversarial Pass

在四项 accepted findings 修复基础上，独立进行 adversarial failure pass：

### Correctness / Security / Maintainability H/M/L 检查

- **无新 correctness finding**：四项修复均在已有验证核心上增加前置 gate，不改变 happy path 语义；identity 投影、pre/postflight double-read、canonical bytes 生成、SHA 闭合链路保持完整。
- **无新 security finding**：`_validate_dto()` 在 Runtime public 方法入口处拦截，不依赖 parser 调用路径；`_counterpart_source_visible()` 使用与工具相同的 `get_source_handle()` 探测，与真实 tool 探测行为一致。
- **无新 maintainability finding**：`_validate_dto()` 是单一内聚函数，无递归、无双真源；`_counterpart_source_visible()` 语义清晰且与 `_SourceIdentityState.counterpart_visible` 字段名对齐。

### Domain validator 无递归/双真源

- `validate_evidence_locator_request()` 与 `validate_evidence_locator_projection()` 均委托单一 `_validate_dto()`，无递归调用。
- parser（`parse_evidence_locator_request` / `parse_evidence_locator_projection`）在构造 DTO 后也调用同一 `_validate_dto()`，单一真源，不经 parser 的 direct-DTO 与 parser 路径行为一致。
- `_validate_dto()` 不调用 parser，parser 不包含 invariant 校验逻辑，无双真源。

### Counterpart visible 与真实 tool 探测一致

- `_counterpart_source_visible()` 调用 `self.source_repository.get_source_handle(ticker, document_id, counterpart)`。
- `FinsToolService._resolve_source_kind()` 使用相同的 `get_source_handle()` 做 filing-first 探测（只检查 meta 文件存在性）。
- 修复后，只要 counterpart 的 handle/source meta 对工具仍可发现（含 `is_deleted=true`），preflight 即拒绝，与工具真实 fallback 行为对齐。

## Verification Results

| 检查项 | 结果 |
|---|---|
| 125 focused tests（domain 45 + runtime 52 + service 8 + application 20） | PASS |
| pyright（修改的 production/tests） | 0 errors |
| ruff（F + I + default） | All checks passed |
| git diff --check | Clean |

## Open Questions

无。

## Residual Risk

- runtime 防御分支（XBRL facts 非 list/非 dict、`unsupported_locator_kind` 兜底、postflight 中 source 被删除/processed 变更）不可达，未动态覆盖；不影响 correctness 判断。
- 未运行 live/network/model/broker；未 commit/push/PR。

## Conclusion

四项 accepted findings（Terra F-01/F-02/F-03 + MiM Finding 1）均已正确修复，修复有充分测试覆盖，无新增 H/M/L findings，domain validator 无递归/双真源，counterpart visible 与真实 tool 探测一致。pyright 0 errors，ruff clean，125 tests passed。

**结论：PASS，open H/M/L = 0/0/0。**
