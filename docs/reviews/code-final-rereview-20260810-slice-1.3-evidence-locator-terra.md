# Code Final Re-review

## Scope

- Mode: current changes（最终 corrective re-review）
- Branch or PR: `codex/investment-platform` workspace
- Base: `3a70a16f0fcb55f79794f824ea30e3cb7e61f06d`
- Review time: `2026-08-10 20:06:09 CST`（本机系统时钟）
- Output file: `docs/reviews/code-final-rereview-20260810-slice-1.3-evidence-locator-terra.md`
- Included scope: Slice 1.3 allowlist 的全部 production、testkit、tests、README 变更；根 `AGENTS.md`、master plan 的 Slice 1.3 / S13-CTRL-08，以及用户指定的七份前序 review/adjudication/fix artifact。
- Excluded scope: Slice 1.4、Slice 3.1、live/network/model/broker；未执行 commit/push/PR，未改 code/tests/README/plan/既有 artifact。
- Parallel review coverage: 无。本次由 Terra 独立沿 `FinsService -> FinsRuntime -> domain validator -> identity preflight -> request-scoped FinsToolService -> postflight` 真实路径复证。

## Findings

未发现实质性问题。

### S13-CR-05 closure evidence

- `evidence_locator.py:756-779` 的 `_require_real_int()` 拒绝 bool、str、float、None；parser 的 `_require_int()`（`1340-1362`）与 direct-DTO validator 的 page/table-cell 分支（`803-832`）共同调用该 helper，数值类型 invariant 只有这一真源。
- `DefaultFinsRuntime.resolve_evidence_locator()`、`validate_evidence_locator()`、`read_citation_projection()` 分别在 `service_runtime.py:2441,2464,2483` 于 identity 投影、仓储读取和 processor 创建之前调用 request/projection validator。`FinsService` 三方法只作同名 runtime 委托（`fins_service.py:179-228`），未引入绕过路径。
- 独立执行 direct-DTO adversarial matrix：page/row 的 bool、str、float，以及 page 的 0/负数、row 的负数，覆盖 resolve/validate/read 共 27 个组合。全部以 `EvidenceLocatorError`（`invalid_type` 或 `invalid_format`）拒绝，且每例 `processor_registry.create_call_count == 0`。

### S13-CR-06 closure evidence

- 新增 `dayu/fins/domain/evidence_locator.py`、`tests/fins/evidence_locator_testkit.py`、新增 evidence tests 与本 Slice 改动行均未发现 `object`、新增 `Any` 使用、`cast`、`type: ignore`、`getattr`、`hasattr` 或 seam。`service_runtime.py` diff 中出现的 `from typing import Any` 是 HEAD 已有 import 的重排；基线 `3a70a16:dayu/fins/service_runtime.py:7` 已包含该符号，runtime HEAD 既有 `Any/object/getattr` 未被误判为本 Slice 新增债务。
- domain owner 以递归 `JsonScalar` / `JsonValue` / `JsonObject`（`evidence_locator.py:46-58`）约束 JSON 边界；runtime 的新 meta/fragment/XBRL 处理使用 `Mapping[str, JsonValue]` / `dict[str, JsonValue]`，testkit 的 source/blob/processor fake 使用 `DocumentMeta`、`SourceHandle | ProcessedHandle`、typed result aliases 与精确 callback 类型。受影响 production/tests 的 Pyright 为 0 errors。

### S13-CR-01..04 regression evidence

- CR-01：request/projection validator 在三个 Runtime public entry 的 identity 投影前执行；`_validate_dto()` 复用 schema/repository、canonical id/hash、real enum、payload pairing 与 artifact-combination invariant（`evidence_locator.py:453-571`）。
- CR-02：counterpart 可见性与工具的 handle 探测事实对齐（`service_runtime.py:2036-2068`）；deleted counterpart 在 preflight（`2125-2134`）及 postflight 复核中均 fail closed，先于 request-scoped processor 构造。
- CR-03：四种 non-document payload 在 parser 读取字段前调用 exact-key gate（`evidence_locator.py:1238-1286`）；request/projection 共用该 parser helper。
- CR-04：`get_primary_file()` 已包含在 `_read_primary_source()` 的 `OSError` 包装范围（`service_runtime.py:2204-2214`），metadata `FileNotFoundError` 收敛为 `primary_read_failed`。

## Open Questions

无。

## Residual Risk

- 已运行且通过：focused evidence 相关测试 136 项；`tests/fins tests/services tests/application` 回归集 3,494 项；受影响 production/tests Pyright 0 errors；Ruff 通过；`git diff --check` 通过。
- 未运行 live/network/model/broker，也未执行 commit/push/PR；这些项目按本次授权范围排除，且不构成当前 Slice 静态/离线 correctness finding。

## Conclusion

**PASS（open H/M/L = 0/0/0）。** S13-CR-05、S13-CR-06 以及 S13-CR-01..04 均以当前代码和独立 adversarial evidence 闭合。
