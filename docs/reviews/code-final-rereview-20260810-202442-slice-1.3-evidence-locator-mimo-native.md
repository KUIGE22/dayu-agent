# Code Final Re-Review

## Scope

- Mode: corrective final re-review
- Branch: `codex/investment-platform`
- Base: `3a70a16`
- Output file: `docs/reviews/code-final-rereview-20260810-202442-slice-1.3-evidence-locator-mimo-native.md`
- Included scope: Slice 1.3 allowlist 内全部 production/test/README 文件
- Excluded scope: Slice 1.4、Slice 3.1、live/network/model/broker、commit/push/PR
- Parallel review coverage: 无；主 reviewer 独立完成全量代码走读与证据复核

## S13-CR-01..06 Closure Verification

### S13-CR-01 — DTO 全 invariant — CLOSED

- `_validate_dto()` 覆盖：`_check_schema_version`（request only）、`_check_repository_id`、`_check_canonical_ticker`、`_check_canonical_document_id`、`_check_text`（document_version）、`_check_lower_hex64`（source_fingerprint / primary_content_sha256 / locator_content_sha256）、`_check_source_kind` / `_check_artifact_kind` / `_check_locator_kind`（isinstance 收窄拒绝字符串冒充枚举）、`_check_payload_pairing`（kind/payload 一致性）、`_check_artifact_combo`（source 只允许 document + DocumentLocatorPayload）。
- `validate_evidence_locator_request()` 和 `validate_evidence_locator_projection()` 均委托单一 `_validate_dto()`，无递归、无双真源。
- `DefaultFinsRuntime` 三个 public 方法在任何 identity 投影前强制调用对应 validator（`service_runtime.py`）。
- parser 构造 DTO 后也调用同一 validator，单一真源。
- 测试覆盖 direct-DTO 的 unknown schema/repository、错误 payload 类型、source+非 document payload、字符串冒充枚举、非 canonical 标识/illegal hash，三个入口均抛稳定 `EvidenceLocatorError`。
- **VERIFIED CLOSED。**

### S13-CR-02 — deleted counterpart — CLOSED

- `_counterpart_source_visible()` 使用 `get_source_handle()`（与 `FinsToolService._resolve_source_kind()` 同一存在性判定），含 `is_deleted=true` 的 meta 文件仍存在即返回 `True`。
- `_preflight_source_identity()` 在 `counterpart_visible` 为 `True` 时抛 `ambiguous_source_identity`；postflight 重读 counterpart 可见性，漂移同样拒绝。
- `_SourceIdentityState.counterpart_active` 已改名为 `counterpart_visible`，语义对齐。
- 测试覆盖 active material + deleted filing（5 种 processed payload）、active filing + deleted material（5 种 processed payload）、resolve 与 read 双向，均 `create_call_count == 0`。
- **VERIFIED CLOSED。**

### S13-CR-03 — nested exact keys — CLOSED

- `_parse_locator_payload()` 四种 non-document payload 分支均在读取字段前调用 `_require_exact_keys()`：page `{"page_no"}`、section `{"section_ref"}`、table_cell `{"table_ref", "row_index", "column"}`、xbrl_fact `{"concept", "fact_sha256"}`。
- request 与 projection parser 共用 `_parse_locator_payload()`，二者均覆盖。
- 测试覆盖四种 kind 各含 nested-extra、四种 kind 各缺键，request 与 projection 均拒绝。
- **VERIFIED CLOSED。**

### S13-CR-04 — primary read wrapping — CLOSED

- `_read_primary_source()` 将 `get_primary_source()`、`source.open().read()` 与 `get_primary_file()` 纳入同一 `try/except OSError` 块（`FileNotFoundError` 为 `OSError` 子类），统一包装为 `EvidenceLocatorError("primary_read_failed")`。
- testkit `primary_file_missing` 分支抛 `FileNotFoundError`，测试断言 `EvidenceLocatorError.code == "primary_read_failed"`。
- **VERIFIED CLOSED。**

### S13-CR-05 — bool-as-int single invariant — CLOSED

- `_require_real_int()` 拒绝 bool：`if not isinstance(value, int) or isinstance(value, bool)`。
- parser 的 `_require_int()` 先做 `isinstance(value, int)` 收窄后委托 `_require_real_int()`（拒绝 bool）。
- DTO validator 的 `_check_payload_pairing()` 对 page 分支调用 `_require_real_int(locator_payload.page_no, "page_no")` 后做 `<= 0` 范围检查，对 table_cell 分支调用 `_require_real_int(locator_payload.row_index, "row_index")` 后做 `< 0` 范围检查。
- parser 与 DTO validator 共用同一 helper，消除双真源。
- 测试覆盖：`test_require_real_int_rejects_non_int_and_bool`（bool/str/float/None/int 单测）、`test_validate_request_rejects_bool_page_no`、`test_validate_request_rejects_bool_row_index`、`test_validate_request_rejects_non_positive_page_no`（0/-1）、`test_validate_request_rejects_negative_row_index`、`test_resolve_rejects_bad_page_no`（True/0/-1 + `create_call_count == 0`）、`test_resolve_rejects_bad_row_index`（True/-1 + `create_call_count == 0`）、`test_validate_and_read_reject_bool_page_no`（validate/read + `create_call_count == 0`）。
- Pyright 0 errors；diff-added-line forbidden scan 0 violations。
- **VERIFIED CLOSED。**

### S13-CR-06 — forbidden type escapes — CLOSED

- 本 Slice 新增 production 文件：`evidence_locator.py` 使用递归 `JsonValue`/`JsonObject`/`JsonScalar` 类型别名；`service_runtime.py` 新增行使用 `JsonValue`/`Mapping[str, JsonValue]`。
- 本 Slice 新增 testkit：`SourceHandle | ProcessedHandle`（对齐 `DocumentBlobRepositoryProtocol`）、`dict[str, JsonValue]`、精确 `Callable` 签名。
- `from typing import Any` 在 `service_runtime.py` 中存在，但该 import 行由本 Slice 重构时重排，`Any` 为 HEAD 既有的符号导入（HEAD 第 10 行已有），非本 Slice 新增语义用法。HEAD 中使用 `Any` 的函数（`_coerce_forms_input`、`_build_*` 系列）均非本 Slice 新增或修改。
- diff-added-line forbidden scan：全部修改文件的新增行匹配 `Any|object|cast|type: ignore|getattr|hasattr|#pragma|noqa` 结果 **0 violations**（import 行排除）。
- Pyright 0 errors（修改的 production/tests）；全仓仅剩 2 个 pre-existing docling 错误，与本 Slice 无关。
- **VERIFIED CLOSED。**

## Adversarial Pass

### S13-CR-01..06 闭合后独立 adversarial scan

- **无新 correctness finding**：S13-CR-01 的 domain validator 为单一 `_validate_dto()` 入口，无递归；S13-CR-05 的 `_require_real_int()` 为单一 int invariant 真源；S13-CR-02 的 counterpart visible 与真实 tool 探测一致；S13-CR-03 的 nested exact-key 由共享 `_parse_locator_payload()` 覆盖 request/projection 双向；S13-CR-04 的 primary read 异常路径统一包装；S13-CR-06 的类型替换完整。
- **无新 security finding**：trust boundary 的 schema/repository/payload 校验在 Runtime public 方法入口处拦截，不依赖 parser 调用路径。
- **无新 maintainability finding**：`_validate_dto()` 是单一内聚函数，无递归、无双真源；`_require_real_int()` 被 parser 与 DTO validator 共用，parser 的 `_require_int()` 委托到同一 helper。

## Verification Results

| 检查项 | 结果 |
|---|---|
| 136 focused tests（domain 50 + runtime 62 + service 8 + application 20） | PASS |
| pyright（修改的 production/tests） | 0 errors |
| diff-added-line forbidden scan（Any/object/cast/type:ignore/getattr/hasattr/pragma/noqa/seam） | 0 violations |
| ruff（F + I + default） | All checks passed |
| git diff --check | Clean |

## Open Questions

无。

## Residual Risk

- runtime 防御分支（XBRL facts 非 list/非 dict、`unsupported_locator_kind` 兜底、postflight 中 source 被删除/processed 变更）不可达，未动态覆盖；不影响 correctness 判断。
- 未运行 live/network/model/broker；未 commit/push/PR。

## Conclusion

S13-CR-01..06 六项 accepted findings 均已正确闭合，修复有充分测试覆盖，forbidden type scan 0 violations，无新增 H/M/L findings。pyright 0 errors，ruff clean，136 tests passed。

**结论：PASS，open H/M/L = 0/0/0。**
