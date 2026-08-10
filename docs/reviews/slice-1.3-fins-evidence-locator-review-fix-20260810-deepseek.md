# Slice 1.3 Fins Evidence Locator code review fix artifact

- **Work unit**：Investment Platform Restoration / Slice 1.3
- **Worker**：DeepSeek Flash
- **日期**：2026-08-10
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**（round 1 与 corrective round 2 finding 全部关闭；未 push / PR / Slice 1.4 / live/network）
- **基线**：`3a70a16`（clean accepted HEAD，branch `codex/investment-platform`）
- **Controller 裁决**：`docs/reviews/code-review-20260810-slice-1.3-evidence-locator-terra.md`（F-01/F-02/F-03）与 `docs/reviews/code-review-20260810-slice-1.3-evidence-locator-mimo-native.md`（Finding 1）全部 ACCEPTED，无 rejected finding。

## 1. 修复范围

严格保持原 Slice 1.3 allowlist。本修复仅修改：

- `dayu/fins/domain/evidence_locator.py`（public DTO validators、nested exact-key、parser 复用 validator）
- `dayu/fins/domain/__init__.py`（导出）
- `dayu/fins/service_runtime.py`（public 入口强制校验、counterpart 可见性、primary 包装）
- `tests/fins/evidence_locator_testkit.py`（`primary_file_missing` 模拟）
- `tests/fins/test_evidence_locator_domain.py`、`tests/fins/test_evidence_locator_runtime.py`、
  `tests/services/test_fins_evidence_locator_service.py`（adversarial regression）
- 本 artifact 与 implementation artifact 状态更新

未修改 `dayu/fins/tools/service.py` / `cache.py`、storage implementation、processor、
investment、migration、startup、根 `README.md`、plan。

## 2. Finding 修复与证据

### Terra F-01（高）：公开 Runtime 入口绕过 repository/schema 与 DTO 严格校验 — FIXED

**修复**：domain 唯一 owner 新增 public DTO invariant validators
`validate_evidence_locator_request()` / `validate_evidence_locator_projection()`，
内部收敛到公共 `_validate_dto()`，覆盖：schema version（仅 request）、repository id、
canonical ticker/document id、小写 64-hex SHA、真实枚举类型（`_check_source_kind` /
`_check_artifact_kind` / `_check_locator_kind` 以 `isinstance` 收窄）、locator
kind/payload 配对（`_check_payload_pairing`）与 source artifact 组合
（`_check_artifact_combo`：source 只允许 document+`DocumentLocatorPayload`）。
`DefaultFinsRuntime` 三个 public 方法在任何 identity 投影前强制调用对应 validator；
parser 构造 DTO 后也调用同一 validator（单一真源，不经 parser 的 direct-DTO 与
parser 路径行为一致）。

**证据（文件/行）**：
- `dayu/fins/domain/evidence_locator.py` — `validate_evidence_locator_request` /
  `validate_evidence_locator_projection` / `_validate_dto` / `_check_*`（新增公共区）；
  `parse_evidence_locator_request` / `parse_evidence_locator_projection` 在返回前调用
  validator。
- `dayu/fins/service_runtime.py` — `resolve_evidence_locator` / `validate_evidence_locator` /
  `read_citation_projection` 在 `_to_evidence_identity` / `_locator_to_evidence_identity`
  之前调用 validator。
- 测试：`tests/fins/test_evidence_locator_domain.py` 的 `test_validate_request_rejects_unknown_schema_and_repository` /
  `test_validate_request_rejects_wrong_payload_type` / `test_validate_request_rejects_source_wrong_payload` /
  `test_validate_request_rejects_bad_canonical_or_hash` / `test_validate_dto_rejects_raw_string_enum` /
  `test_validate_projection_rejects_unknown_repository`；
  `tests/fins/test_evidence_locator_runtime.py` 的 `test_resolve_rejects_direct_dto_unknown_schema_and_repository` /
  `test_validate_and_read_reject_direct_dto_unknown_repository` /
  `test_resolve_rejects_direct_dto_wrong_payload_type`；
  `tests/services/test_fins_evidence_locator_service.py` 的
  `test_service_rejects_direct_dto_unknown_schema_and_repository`（三个 delegate 路径）。

**验证点**：direct-DTO（不经 parser）的 unknown schema/repository、错误 payload 类型、
source+非 document payload、字符串冒充枚举、非 canonical 标识/非法 hash 均在
resolve/validate/read 三个入口抛 `EvidenceLocatorError` 且错误码稳定。

### Terra F-02（高）：逻辑删除的 counterpart 仍可被工具 fallback 读取 — FIXED

**修复**：counterpart 判定从"active 状态"改为"可被工具发现"：
`_counterpart_source_active()` 重写为 `_counterpart_source_visible()`，改用
`get_source_handle()`（与 `FinsToolService._resolve_source_kind()` 的 filing-first
探测同一存在性判定），只要 counterpart 的 handle/meta 对工具仍可发现（含
`is_deleted=true`）即视为歧义并抛 `ambiguous_source_identity`。preflight 与
postflight 均使用同一判定；`_SourceIdentityState.counterpart_active` 字段相应改为
`counterpart_visible`。

**证据（文件/行）**：
- `dayu/fins/service_runtime.py` — `_counterpart_source_visible`（get_source_handle 判定）、
  `_preflight_source_identity` 与 `_postflight_identity` 引用更新、`_SourceIdentityState`
  字段改名。
- 测试：`tests/fins/test_evidence_locator_runtime.py` 的
  `test_deleted_filing_counterpart_ambiguous_all_kinds`（active material + deleted filing，
  五种 processed payload 的 validate 均 `ambiguous_source_identity` 且
  `create_call_count == 0`）、`test_deleted_material_counterpart_ambiguous_all_kinds`
  （active filing + deleted material，read 路径）、
  `test_deleted_counterpart_ambiguous_on_resolve_and_read`（resolve 与 read 双向）。

**验证点**：deleted counterpart 下五种 processed locator kind 的真实投影路径（validate
/read/resolve）全部在同一 preflight gate 拒绝，且 processor 未创建。

### Terra F-03（中）：非 document payload 未做精确字段集校验 — FIXED

**修复**：`_parse_locator_payload()` 对 page / section / table_cell / xbrl_fact 四种
non-document payload 在读取字段前调用 `_require_exact_keys()`（各自精确字段集），
nested missing/unknown 一律拒绝；document 分支保持空 payload 约束。request 与
projection parser 共用该函数，二者均覆盖。

**证据（文件/行）**：
- `dayu/fins/domain/evidence_locator.py` — `_parse_locator_payload` 各分支调用
  `_require_exact_keys`。
- 测试：`tests/fins/test_evidence_locator_domain.py` 的
  `test_parse_request_rejects_nested_payload_extra` /
  `test_parse_projection_rejects_nested_payload_extra`（四种 kind 各含 nested-extra）/
  `test_parse_request_rejects_nested_payload_missing`（四种 kind 各缺键）。

**验证点**：page/section/table_cell/xbrl_fact 的 nested-extra 与 missing 均在 request
与 projection parser 拒绝，错误码 `invalid_fields`。

### MiM Finding 1（中）：primary file meta 异常未包装为 primary_read_failed — FIXED

**修复**：`_read_primary_source()` 将 `get_primary_source()`、`source.open().read()` 与
`get_primary_file()` 纳入同一 `try/except OSError` 块（`FileNotFoundError` 为 `OSError`
子类），任何 source 主文件读取失败统一包装为
`EvidenceLocatorError("primary_read_failed", ...)`，不泄漏仓储异常类型。

**证据（文件/行）**：
- `dayu/fins/service_runtime.py` — `_read_primary_source` 的 try 块扩大覆盖
  `get_primary_file`。
- testkit：`tests/fins/evidence_locator_testkit.py` 的 `SeededSource.primary_file_missing`
  与 `EvidenceSourceRepository.get_primary_file` 抛 `FileNotFoundError` 分支。
- 测试：`tests/fins/test_evidence_locator_runtime.py` 的
  `test_primary_read_failed_when_primary_file_missing`。

**验证点**：`get_primary_source` 成功但 `get_primary_file` 抛 `FileNotFoundError` 时，
resolve 抛 `EvidenceLocatorError.code == "primary_read_failed"`。

## 3. 验证

- focused：`tests/fins/test_evidence_locator_domain.py`（45）、
  `tests/fins/test_evidence_locator_runtime.py`（52）、
  `tests/services/test_fins_evidence_locator_service.py`（8）全部通过。
- 相关 suite：`tests/fins/` 全量 1997 passed；`tests/services/` + `tests/application/`
  1484 passed；`tests/architecture/` 29 passed；`tests/fins/test_fins_runtime_tool_service.py`
  与 `tests/application/test_fins_service.py` 通过。
- pyright：修改的 production/tests 0 errors；全仓仅剩 2 个 pre-existing
  docling `reportPrivateImportUsage` 错误（HEAD 即存在、与本次无关、未扩散）。
- Ruff（F + I + default）：修改文件全部通过。
- coverage（新增 production 语句）：`evidence_locator.py` 91%（整文件新增）、
  `service_runtime.py` 新增语句 97.9%、`fins_service.py` 新增语句 98.3%、
  `protocols.py` 100%。未覆盖行均为不可达防御分支或既有逻辑行号偏移。
- `git diff --check`：通过。
- 无新增 `Any` / `object` 字段 / `cast` / `type: ignore` / `hasattr` / `getattr` /
  coverage pragma / seam；新增/修改函数具备完整中文 Args/Returns/Raises docstring。

## 4. 未覆盖项与风险

- runtime 防御分支（XBRL facts 非 list/非 dict、`unsupported_locator_kind` 兜底、
  postflight 中 source 被删除/processed 变更）不可达，未动态覆盖。
- 未运行 live/network/model/broker；未启动 re-review / commit / push / PR；未进入
  Slice 1.4（MinIO/S3）或 Slice 3.1（tenant composite FK/RLS）。

## 5. 结论

Terra F-01/F-02/F-03 与 MiM Finding 1 四项 ACCEPTED findings 已全部修复并有针对性
regression 测试与逐 finding 证据。**状态：READY FOR DUAL RE-REVIEW**。

最终闭环：Terra 与 MiM Native 最终复审均 PASS、open H/M/L=`0/0/0`；本 artifact
及其后续 corrective fix 所覆盖的 S13-CR-01..06 全部 CLOSED。
