# Slice 1.3 Fins Evidence Locator corrective review fix artifact (round 2)

- **Work unit**：Investment Platform Restoration / Slice 1.3
- **Worker**：DeepSeek Flash
- **日期**：2026-08-10
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**（未 push / PR / Slice 1.4 / live/network）
- **基线**：`3a70a16`（clean accepted HEAD，branch `codex/investment-platform`）
- **Controller 裁决**：`docs/reviews/slice-1.3-fins-evidence-locator-review-adjudication-20260810-codex.md` —— Terra round1 F-01（bool-as-int）与 F-02（object 宽类型）裁决为 **S13-CR-05（MEDIUM）** / **S13-CR-06（LOW）**，全部 ACCEPTED；MiM round1 re-review PASS 仅作为其覆盖面证据，不关闭 Terra 新 finding。
- **来源 review**：`docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-terra.md`（F-01/F-02）

## 1. 修复范围

严格保持原 Slice 1.3 allowlist。本修复仅修改：

- `dayu/fins/domain/evidence_locator.py`（`JsonValue`/`JsonObject` 类型别名、`_require_real_int`
  单一 helper、parser 与 DTO validator 共同复用、移除 `object` 宽类型）
- `dayu/fins/service_runtime.py`（新增行 `object` → `JsonValue`/`Mapping[str, JsonValue]`）
- `tests/fins/evidence_locator_testkit.py`（`object` → `JsonValue`/`SourceHandle|ProcessedHandle`/
  精确 `on_fallback` Callable）
- `tests/fins/test_evidence_locator_domain.py`、`tests/fins/test_evidence_locator_runtime.py`、
  `tests/services/test_fins_evidence_locator_service.py`（bool-as-int adversarial regression；
  `object` 宽类型清除）
- 本 artifact 与 implementation/round-1 fix artifact 状态更新

未修改 `dayu/fins/tools/service.py` / `cache.py`、storage implementation、processor、
investment、migration、startup、根 `README.md`、plan、Controller adjudication 文件。

## 2. Finding 修复与证据

### S13-CR-05（MEDIUM）：direct DTO validator 未与 strict parser 等价，仍接受 bool-as-int — FIXED

**修复**：domain 建立真实 int 非 bool 的单一 invariant helper `_require_real_int()`：

```python
def _require_real_int(value: JsonScalar, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvidenceLocatorError("invalid_type", f"{key} 必须是整数，不能是布尔值")
    return value
```

- parser 的 `_require_int()` 先做 `isinstance(value, int)` 收窄后委托 `_require_real_int()`
  （拒绝 bool）；
- DTO validator 的 `_check_payload_pairing()` 对 page 分支调用
  `_require_real_int(locator_payload.page_no, "page_no")` 后做 `<= 0` 范围检查，对
  table_cell 分支调用 `_require_real_int(locator_payload.row_index, "row_index")` 后做
  `< 0` 范围检查。

parser 与 DTO validator 共用同一 helper，消除双真源：`True`/`False`、`"1"`、`1.5`、
`None`、`0`、负值均 fail closed。Runtime 三个 public 入口在任何 owner/tool I/O 之前
调用 validator，因此 bool-as-int 无法进入 `get_page_content` 等工具。

**证据（文件/行）**：
- `dayu/fins/domain/evidence_locator.py` — `_require_real_int`（新增）、`_require_int`
  （委托）、`_check_payload_pairing`（page/table_cell 分支调用并范围检查）。
- 测试：
  - `tests/fins/test_evidence_locator_domain.py` —
    `test_require_real_int_rejects_non_int_and_bool`（helper 直测 bool/str/float/None/int）、
    `test_validate_request_rejects_bool_page_no`、`test_validate_request_rejects_bool_row_index`、
    `test_validate_request_rejects_non_positive_page_no`（0/-1）、
    `test_validate_request_rejects_negative_row_index`。
  - `tests/fins/test_evidence_locator_runtime.py` —
    `test_resolve_rejects_bad_page_no`（True/0/-1，resolve + `create_call_count == 0`）、
    `test_resolve_rejects_bad_row_index`（True/-1，resolve + `create_call_count == 0`）、
    `test_validate_and_read_reject_bool_page_no`（validate/read + `create_call_count == 0`）。

**验证点**：page/row 的 bool、非 int（str/float，经 helper 单测）、0/负值在
resolve/validate/read 三个入口均抛稳定 `EvidenceLocatorError`（`invalid_type`/
`invalid_format`），且 processor 未创建。

### S13-CR-06（LOW）：新增 domain owner 与测试桩引入 object 宽类型 — FIXED

**修复**：按仓库既有严格模式定义递归 JSON 类型别名，使用协变容器避免 invariance：

```python
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]
```

替换本 Slice 所有新增行中的 `object`：

- `evidence_locator.py`：`to_dict() -> dict[str, JsonValue]`；`canonical_json_bytes(value:
  JsonValue)`；parser `raw: JsonValue` 与 `_require_mapping(raw: JsonValue) -> JsonObject`；
  `_require_*`/`_parse_*` 系列 `payload: Mapping[str, JsonValue]`；
  `_validate_dto` 与 `_check_source_kind`/`_check_artifact_kind`/`_check_locator_kind`
  的 enum 入参收敛为可判别联合 `SourceKind | str` / `ArtifactKind | str` /
  `LocatorKind | str`（运行时 `isinstance` 拒绝字符串冒充枚举）。
- `service_runtime.py`：`_as_optional_text(value: JsonValue)`；
  `_require_meta_text`/`_require_meta_fingerprint(meta: Mapping[str, JsonValue], ...)`；
  `_canonical_xbrl_row(fact: Mapping[str, JsonValue]) -> dict[str, JsonValue]`；
  `matched_rows: list[dict[str, JsonValue]]`；fragment dict 显式注解
  `dict[str, JsonValue]`。
- `tests/fins/evidence_locator_testkit.py`：`StubBlobRepository` handle 用
  `SourceHandle | ProcessedHandle`（对齐 `DocumentBlobRepositoryProtocol`）；meta 字典
  用 `dict[str, JsonValue]`；`query_xbrl_facts`/`get_financial_statement` 返回
  `dict[str, JsonValue]`；`create_with_fallback` 的 `on_fallback` 用精确
  `Callable[[type[DocumentProcessor], Exception, int, int], None] | None`。
- 测试文件：`_build_request_dict`/`_build_projection_dict`/`_xbrl_fact` 等 dict 用
  `dict[str, JsonValue]`；`_assert_no_leak(value: JsonValue | bytes, path)`；
  service 测试 stub 的 `metadata`/`state` 用协议精确类型
  `ExecutionDeliveryContext | None` / `SessionState | None`。

未引入 `Any`（既有 `service_runtime.py` 的 `from typing import Any` 仅为既有代码的
符号导入，非新增使用）、`cast`、`type: ignore`、`getattr`/`hasattr`（测试中
`hasattr(CitationProjection, "__slots__")` 改为 `"__slots__" in CitationProjection.__dict__`）、
coverage pragma 或 seam。既有上游协议内部的 `Any`（如 `DocumentMeta`）未在本 Slice
新增显式使用。

**证据**：diff-added-line forbidden scan（脚本见 §3）对全部修改文件的新增行与新增
untracked 文件全行匹配 `Any|object|cast|type: ignore|#pragma|noqa|getattr|hasattr`，
结果 **0 violations**（纯 import 行排除）。

## 3. 验证

- diff-added-line forbidden scan：新增 `Any`/`object`/`cast`/`type: ignore`/
  `#pragma`/`noqa`/`getattr`/`hasattr` = **0**。
- focused：domain 50 + runtime 62 + service 8 + application 20 = 140 passed；
  `tests/fins/test_fins_runtime_tool_service.py` 与 `tests/architecture/` 通过
  （focused 合计 181 passed）。
- 相关 suite：`tests/fins/` 全量 2008 passed；`tests/services/` + `tests/application/`
  1484 passed。
- pyright：修改的 production/tests 0 errors；全仓仅剩 2 个 pre-existing
  docling `reportPrivateImportUsage` 错误（HEAD 即存在、与本次无关、未扩散）。
- Ruff（F + I + default）：修改文件全部通过。
- coverage（新增 production 语句）：`evidence_locator.py` 92%（整文件新增）、
  `service_runtime.py` 新增语句 97.9%、`fins_service.py` 新增语句 98.3%、
  `protocols.py` 100%。未覆盖行均为不可达防御分支或既有逻辑行号偏移。
- `git diff --check`：通过。
- 新增/修改函数具备完整中文 Args/Returns/Raises docstring。

## 4. 未覆盖项与风险

- runtime 防御分支（XBRL facts 非 list/非 dict、`unsupported_locator_kind` 兜底、
  postflight 中 source 被删除/processed 变更）不可达，未动态覆盖。
- str/float 的 direct-DTO 反例经单一 helper `_require_real_int` 直接单测覆盖
  （与 bool 同一代码路径），runtime 全链路以 bool/0/负值覆盖；未通过类型注入构造
  str/float payload，避免新增 `cast`/`object` 桥接。
- 未运行 live/network/model/broker；未启动 re-review / commit / push / PR；未进入
  Slice 1.4（MinIO/S3）或 Slice 3.1（tenant composite FK/RLS）。

## 5. 结论

S13-CR-05（bool-as-int，MEDIUM）与 S13-CR-06（object 宽类型，LOW）两项 ACCEPTED
findings 已全部修复，并有针对性 regression 测试、diff-added-line forbidden scan 与
逐 finding 证据。**状态：READY FOR FINAL DUAL RE-REVIEW**。

最终闭环：Terra 与 MiM Native 最终复审均 PASS、open H/M/L=`0/0/0`；S13-CR-05/06
与回归复查的 S13-CR-01..04 均 CLOSED，无新增 finding。
