# Code Re-review

## Scope

- Mode: 当前未提交改动的 corrective re-review
- Branch: `codex/investment-platform`
- Base: `3a70a16`
- Output file: `docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-terra.md`
- Included scope: Slice 1.3 的未提交 production/test/README 改动；已完整读取根 `AGENTS.md`、accepted Slice 1.3 plan/plan-fix/acceptance、Terra 与 MiM 初审、Controller adjudication、DeepSeek fix artifact。沿 `FinsService -> FinsRuntime -> repositories/FinsToolService` 复核 F-01、F-02、F-03 和 MiM primary-file 修复。
- Excluded scope: Slice 1.4、Slice 3.1、live/network/model/broker、commit/push/PR；审查中由其他工作流新增的 MiM re-review artifact 未改动。
- Parallel review coverage: 无（Terra 独立复审）。

## Findings

### F-01-未修复-中-direct DTO validator 未与 strict parser 等价，仍接受 bool-as-int payload
- **入口/函数**: `DefaultFinsRuntime.resolve_evidence_locator()` -> `validate_evidence_locator_request()` -> `_check_payload_pairing()`。
- **文件(行号)**: `dayu/fins/domain/evidence_locator.py:505-531, 740-790`；`dayu/fins/service_runtime.py:2441-2443, 590-607`。
- **输入场景**: 调用方绕过 JSON parser，直接构造 `PageLocatorPayload(page_no=True)`，并将其置入 otherwise-valid 的 processed `EvidenceLocatorRequest`；`True` 是 Python `int` 的子类，但不是 contract 要求的 positive-int JSON number。
- **实际分支**: `_check_payload_pairing()` 对 page 仅执行 `locator_payload.page_no <= 0`，`True <= 0` 为 false，因此 DTO validator 返回成功；Runtime 随后把 `True` 传给 `FinsToolService.get_page_content()`。该工具也仅以 `isinstance(page_no, int)` 判断，继续接受该值并形成 projection。
- **预期行为**: S13-CTRL-01/02、S13-CR-01 要求 direct DTO 与 strict parser 使用同一 invariant；`bool-as-int` 必须在 resolve/validate/read 进入任何 owner/tool I/O 前以 `EvidenceLocatorError` fail closed。
- **实际行为**: 已独立重放：`validate_evidence_locator_request()` 接受该 DTO；在已注入 page 数据的真实 Runtime 链路中，`resolve_evidence_locator()` 成功返回 `locator_payload={"page_no": true}` 的 projection。parser 路径的 `_require_int()` 明确拒绝 bool，两个入口语义不一致。
- **直接证据**: parser 的 `_require_int()` 在 `dayu/fins/domain/evidence_locator.py:1297-1318` 先执行 `isinstance(value, bool)` 拒绝；direct DTO 的 page 分支在 `740-757` 没有同等类型判断。`FinsToolService.get_page_content()` 的同类宽判断位于 `dayu/fins/tools/service.py:975-980`。此次修复虽在 Runtime 三个 public 入口调用 validator（`service_runtime.py:2441,2464,2483`），但 validator 自身遗漏该 invariant，故无法闭合绕过路径。
- **影响**: 公开 trust-boundary 可持久化不符合精确 schema 的 locator；同一逻辑规则在 parser 与 DTO validator 有两个实现，后续会继续产生 parser/direct-DTO 行为漂移。`TableCellLocatorPayload(row_index=True)` 同样受 `row_index < 0` 宽判断影响。
- **建议改法和验证点**: 将 page/row index 的“真实 int 且非 bool”校验抽为 domain validator 的唯一辅助函数，并让 parser 与 DTO validator共同调用；补 direct-DTO 的 page/row bool、非 int、负值反例，分别覆盖 resolve/validate/read，断言均为稳定 `EvidenceLocatorError` 且 processor 未创建。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### F-02-未修复-低-新增 domain owner 与测试桩引入显式禁止的 object 宽类型，且修复 artifact 的零新增声明不成立
- **入口/函数**: Evidence Locator domain/parser 与其新增 testkit 的类型边界。
- **文件(行号)**: `dayu/fins/domain/evidence_locator.py:106,132,158,188,220,315,380,511-516,678-720,838,913,979-1320`；`tests/fins/evidence_locator_testkit.py:56-1467`。
- **输入场景**: 维护者依赖新增 API 的静态类型契约、或修改 strict parser/DTO validator。
- **实际分支**: 新增模块以 `object` / `Mapping[str, object]` 表达 raw JSON、DTO enum 入参及 canonical bytes 入参；testkit 也将仓储 meta、handle 与 processor 行为广泛收窄为 `object`。
- **预期行为**: 根 `AGENTS.md` 的编码硬约束禁止新增 `object`、`Any` 和其他无法严格类型检查的签名；S13-CTRL-08 也将 forbidden type escapes 列为 validation gate。
- **实际行为**: 新增 production 模块本身已有多处 `object` 类型签名；fix artifact 第 3 节的“无新增 `Any` / `object` 字段”与当前 diff 不符。
- **直接证据**: `rg` 在上述新增文件定位到 `canonical_json_bytes(value: object)`、DTO validator 的 `source_kind/artifact_kind/locator_kind: object`、parser raw `object` 与 `Mapping[str, object]` 等；这些均由本 Slice 新增文件引入，而非既有 Runtime 的历史类型债务。
- **影响**: strict DTO/parser 的边界不能由类型系统表达，直接导致本报告 F-01 所示 parser 与 direct-DTO 校验漂移更难被静态发现；同时违反项目明确的可维护性与验收约束。
- **建议改法和验证点**: 定义递归 `JsonValue` / `JsonObject` 及狭窄的 raw-input 类型，enum validator 接受可判别的联合类型而非 `object`；将 test fake 的 handle/meta 依赖收窄到对应 protocol 所需类型。修改后运行 forbidden-type guard、affected-files Pyright，并确认不再新增 `object`/`Any`/`cast`/ignore。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 低。

## Required Closure Replay

- F-01 的 schema/repository/raw-enum/canonical ticker-document/hash、kind/payload 类型配对及 source+non-document 组合，Runtime 三个入口均在 identity 投影前调用 domain validator，相关已有回归通过；但上述 bool-as-int direct DTO 反例说明“parser 等价、所有 direct DTO 非法组合全拒”未闭合。
- F-02 已关闭：`_counterpart_source_visible()` 使用与 `FinsToolService._resolve_source_kind()` 相同的 `get_source_handle()` 可见性事实。preflight 在创建 request-scoped processor 前拒绝 deleted filing/material counterpart；五种 processed kind 的双向 validate/read，以及 resolve/read 反例均通过且 `create_call_count == 0`。
- F-03 已关闭：page/section/table_cell/xbrl_fact 均在共享 `_parse_locator_payload()` 中先做 exact-key 校验；request 与 projection 的 extra/missing 情形沿同一 helper fail closed，未见递归调用。
- MiM primary-file 修复已关闭：`get_primary_file()` 位于 `_read_primary_source()` 的 `try/except OSError` 内，`FileNotFoundError` 重放为 `EvidenceLocatorError(code="primary_read_failed")`。
- Domain validator 未发现递归；但 F-01 的 parser `_require_int()` 与 DTO validator 的数值规则重复且不一致，故不存在可接受的单一 invariant 真源。

## Verification

- `source .venv/bin/activate && pytest -q tests/fins/test_evidence_locator_domain.py tests/fins/test_evidence_locator_runtime.py tests/services/test_fins_evidence_locator_service.py tests/application/test_fins_service.py`：125 passed。
- 受影响文件 Pyright：0 errors。
- 受影响文件 Ruff：通过。
- `git diff --check` 及 untracked `evidence_locator.py` 的 no-index diff check：通过。
- 全仓 Pyright：17 个既有错误，位于 `dayu/engine/processors/docling_processor.py` 与 `tests/engine/test_docling_processor_helpers.py`、`tests/engine/test_web_tools.py`；不在本 Slice 改动路径，受影响文件检查为 0 errors。

## Open Questions

- 无。

## Residual Risk

- 未运行 live/network/model/broker，未执行 commit/push/PR。
- 本次只允许新增本 artifact；未修改生产代码、测试、README 或既有 review 文件。

## Conclusion

**FAIL（Open H=0 / M=1 / L=1）**。F-02、F-03 与 MiM primary-file 修复可关闭；F-01 的 direct-DTO strict-invariant 闭环仍有可复现绕过，且新增宽类型违反项目验收约束。仅在 Open H/M/L 全为 0 后才可判定 PASS。
