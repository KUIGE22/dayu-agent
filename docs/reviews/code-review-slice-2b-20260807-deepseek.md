# Slice 2B Adversarial Code Review —— DeepSeek 独立审查路

- **日期**: 2026-08-07
- **基线**: `ba8b83e` (`gateflow: accept write artifact callers slice 2a`)
- **目标分支**: `codex/dual-model-research-mvp`
- **审查范围**: 9 个 Cohort B 生产文件 + 4 个测试文件 + tests/README.md
- **审查依据**: AGENTS.md、Master Plan v4.4 Slice 2B/C5-CTRL-01..10、Slice 2B implementation record
- **审查方法**: adversarial failure pass、结构审计、pytest/pyright/ruff、类型传播审计、过度耦合检查

## Verdict: PASS_WITH_OBSERVATIONS

**0 HIGH findings. 3 MEDIUM findings. 2 LOW findings.**

实现质量良好。全部 eligible 私有定义已正确删除，全部 deferred 私有定义已保留。bytes/str fingerprint 族、时间族、copy/identity mapping、dict adapter 均正确。测试、pyright、ruff 全绿。发现的 findings 均为 plan 文档精度和 diff 可读性问题，不影响运行时正确性。

---

## 审查范围

生产代码（9 文件）:
- `dayu/services/write_model_configuration_application.py`
- `dayu/services/write_model_configuration_rollback_application.py`
- `dayu/services/write_model_configuration_manual_recovery.py`
- `dayu/services/write_model_configuration_manual_recovery_application.py`
- `dayu/services/write_model_configuration_manual_recovery_clearance.py`
- `dayu/services/write_model_configuration_manual_recovery_verification.py`
- `dayu/services/write_model_configuration_manual_recovery_incident_dossier.py`
- `dayu/services/write_model_configuration_manual_recovery_incident_dossier_revalidation.py`
- `dayu/services/write_model_configuration_manual_recovery_gate_revalidation.py`

测试与索引（5 文件）:
- `tests/application/test_write_artifact_utils.py`
- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/application/test_write_model_configuration_manual_recovery_gate_revalidation.py`
- `tests/README.md`

---

## C5-CTRL 逐项 Adversarial 核对

### C5-CTRL-01（validated_fingerprint 族 A/G 迁移，族 B-F 禁止迁移）: PASS ✓

**断言**: 9 个 Cohort B 文件全部保留私有 `_validated_fingerprint`，零调用 shared `validated_fingerprint`。

**证据**:
```
rg 'validated_fingerprint(' <9 Cohort B files>
→ 全部调用为 _validated_fingerprint（前缀下划线），零 shared validated_fingerprint 调用
```
- 族 B: `rollback_application`, `manual_recovery_application`, `clearance`, `incident_dossier`, `incident_dossier_revalidation` — 保留 ✓
- 族 C: `configuration_application` — 保留 ✓
- 族 D: `manual_recovery` — 保留 ✓
- 族 E: `verification` — 保留 ✓
- 族 F: `gate_revalidation` — 保留 ✓

**结论**: 无 regression。9/9 族 B-F 私有定义完整保留且未误用 shared。

### C5-CTRL-02（absolute_path text: str 入参）: PASS ✓

**断言**: absolute_path 使用 `text: str`（非 `ModelConfigJsonValue`），text 校验由调用方各自的 `_required_text` 族处理。

**证据**:
- `configuration_application.py`: `require_text(...)` 已迁移 → text 通过 shared `require_text` 预处理 → 传入 `absolute_path(text, ...)` ✓
- `rollback_application.py`: 同 pattern，`require_text` 已迁移 ✓
- `manual_recovery.py`: 同 pattern ✓
- `manual_recovery_application.py`: 族 2 `_required_text` 保留私有 → text 经私有 `_required_text` 预处理 → 传入 `absolute_path(text, ...)` ✓

**结论**: 无 regression。所有 caller 遵循 `_required_text` → `text: str` → `absolute_path` 链路。

### C5-CTRL-03（decode_base64/decode_base64_strict text: str 入参）: PASS ✓

**断言**: decode_base64 族 A（标准错误文本）和 decode_base64_strict 族 B（严格错误文本）正确分发。

**证据**:
- `configuration_application.py`, `rollback_application.py`, `manual_recovery_application.py` → `decode_base64`（族 A）✓
- `manual_recovery.py` → `decode_base64_strict`（族 B）✓
- 各 caller 用各自 `_required_text` 族得到 text 后传入 shared codec ✓

**结论**: 无 regression。

### C5-CTRL-04（fingerprint_str vs fingerprint_bytes 分发正确）: PASS ✓

**断言**: 底层 `_canonical_json` 返回 str 的用 `fingerprint_str`，返回 bytes 的用 `fingerprint_bytes`。

**证据**:
- bytes canonical → `fingerprint_bytes`: `configuration_application`, `rollback_application`, `manual_recovery`, `manual_recovery_application`, `clearance`（5 文件）✓
- str canonical → `fingerprint_str`: `incident_dossier`, `incident_dossier_revalidation`, `gate_revalidation`（3 文件）✓
- `verification.py` 保持 `bytes_fingerprint` 用于 raw bytes，payload 级 fingerprint 自行 `hashlib.sha256(canonical_json_bytes(payload))` ✓

**结论**: 无混用。

### C5-CTRL-05/SA-REVIEW-04（format_utc vs format_utc_seconds 精度）: PASS ✓

**断言**: microseconds/seconds/auto 三族正确分发。

**证据**:
- `format_utc` (microseconds): `configuration_application`, `rollback_application`, `manual_recovery`（3 文件）✓
- `format_utc_seconds` (seconds): `manual_recovery_application`, `clearance`（2 文件）✓
- `_format_utc` (auto, defer): `incident_dossier_revalidation`, `gate_revalidation`（2 文件，保留私有）✓

**结论**: 三族分发正确。

### C5-CTRL-10-ERRATUM（require_mapping identity-return + copy adapter）: PASS ✓

**断言**: shared `require_mapping` identity-return；12 identity 文件直接迁移；2 copy 族文件使用 `dict(require_mapping(...))` adapter。

**证据**:
- **7 identity 文件**: `configuration_application`, `rollback_application`, `manual_recovery`, `manual_recovery_application`, `clearance`, `verification`, `incident_dossier` — 全部直接使用 `require_mapping(`，零 `dict(require_mapping(` wrapper ✓
- **2 copy 文件**: `incident_dossier_revalidation`（7 `dict(require_mapping(...))` 调用点）、`gate_revalidation`（13 `dict(require_mapping(...))` 调用点）✓
- **canonical/fingerprint dict adapter**: `gate_revalidation` 有 `fingerprint_str(dict(...))`、`canonical_json_str(dict(...))`；`incident_dossier_revalidation` 有 `fingerprint_str(dict(...))` ✓

注意: `dict(require_mapping(...))` 为多行格式（`dict(\n    require_mapping(`），单行 grep 无法匹配。

**结论**: copy 语义保持，identity 语义保持。

---

## 结构审计

### Eligible 私有定义零残留

```
rg '^def _canonical_json|_fingerprint[^s]|_bytes_fingerprint|_file_fingerprint|_mapping|_absolute_path|_is_relative_to|_serialize|_decode_base64' <9 files>
→ 全部返回 0 ✓
```

### Deferred 私有定义全部保留

| 文件 | deferred 计数 | 内 容 |
|---|---|---|
| `configuration_application.py` | 6 | `_validated_fingerprint` (族 C), `_snapshot_fingerprint`, `_transaction_id`, `_persist_immutable`, `_parse_utc`, `_validate_source` |
| `rollback_application.py` | 7 | `_validated_fingerprint` (族 B), `_snapshot_fingerprint`, `_transaction_id`, `_persist_immutable`, `_parse_utc`, `_target_path`, `_validate_source` |
| `manual_recovery.py` | 5 | `_validated_fingerprint` (族 D), `_persist_immutable`, `_parse_utc`, `_target_path`, `_validate_source` |
| `manual_recovery_application.py` | 8 | `_validated_fingerprint` (族 B), `_required_text` (族 2), `_snapshot_fingerprint`, `_transaction_id`, `_persist_immutable`, `_parse_utc`, `_format_utc_seconds`... |
| `clearance.py` | 4 | `_validated_fingerprint` (族 B), `_persist_immutable`, `_parse_utc`, `_validate_source` |
| `verification.py` | 6 | `_validated_fingerprint` (族 E), `_required_text` (族 2), `_snapshot_fingerprint`, `_transaction_id`, `_parse_utc`, `_validate_source` |
| `incident_dossier.py` | 3 | `_validated_fingerprint` (族 B), `_transaction_id`, `_persist_immutable` |
| `incident_dossier_revalidation.py` | 5 | `_validated_fingerprint` (族 B), `_required_text` (族 6), `_format_utc` (auto), `_persist_immutable`, ... |
| `gate_revalidation.py` | 5 | `_validated_fingerprint` (族 F), `_required_text` (族 7), `_format_utc` (auto), `_persist_immutable`, ... |

**Deferred `_required_text`**: 4 文件（`manual_recovery_application` 族 2, `verification` 族 2, `incident_dossier_revalidation` 族 6, `gate_revalidation` 族 7）✓
**Auto `_format_utc`**: 2 文件（`incident_dossier_revalidation`, `gate_revalidation`）✓

### 类型传播审计

```
git diff ba8b83e -U0 | rg '^\+.*(\bAny\b|\bobject\b|cast\(|type:\s*ignore)'
→ 零匹配 ✓
```

**Deferred 私有函数类型精化**（正向改进）:
- `_validate_source`: `value: object` → `value: ModelConfigJsonValue`（4 文件）
- `_parse_utc`: `value: object` → `value: ModelConfigJsonValue`（4 文件）
- `_target_path`: `value: object` → `value: ModelConfigJsonValue`（2 文件）
- `_validated_fingerprint`: `value: object` → `value: ModelConfigJsonValue`（5 文件，族 B/C/D deferred）

上述 deferred 私有函数改用 shared `require_mapping` / `require_text` 作为内部实现，同时保持各自业务语义不变。这是 correct-by-construction 的类型传播 —— 零 type: ignore、零 cast。

### Cohort A 隔离审计

```
git diff ba8b83e --name-only | rg 'dayu/services/write_model_configuration_(change|rollback\.py|preapplication|challenger)|write_run_comparison'
→ NONE — Cohort A 10 生产文件零 diff ✓
```

### Shared 模块隔离审计

```
git diff ba8b83e -- dayu/services/_write_artifact_utils.py
→ 零 diff ✓
```

### Plan 文件隔离审计

```
git diff ba8b83e -- docs/plans/
→ 零 diff ✓
```

---

## 测试与验证审计

### 测试运行结果

| 测试套件 | 结果 |
|---|---|
| `test_write_artifact_utils.py` | 23 passed ✓ |
| `test_write_cli_dispatch.py` | 89 passed ✓ |
| `test_write_model_configuration_preapplication.py` + `gate_revalidation.py` | 140 passed ✓ |
| full `write_model` 套件 (237 selected) | 237 passed, 1 skipped, 1082 deselected ✓ |

### 测试导入审计

测试文件仅从 `_write_artifact_utils` 导入 shared helper。对 deferred 私有族的 characterization 仍通过模块属性访问（如 `rollback_application._validated_fingerprint`、`application._validated_fingerprint`、`gate_revalidation._validated_fingerprint`）。零导入已删除 eligible 私有符号 ✓。

### Malformed Corpus 审计

- `test_write_model_configuration_preapplication.py`: malformed dossier revalidation（top-level fields 注入 corrupt values）、malformed evidence（field-level validates）、invalid fingerprint format、malformed write_ahead_intent sub-fields ✓
- `test_write_model_configuration_manual_recovery_gate_revalidation.py`: malformed gate revalidation top-level corpus ✓

### 覆盖率审计

实现记录中报告的 9 文件覆盖率（80.05%–84.96%）以 Python 3.13 cov timid 模式独立测量，corpus 覆盖真实 public caller 路径。本次审查未独立复现覆盖率测量，但 237 个 write_model 测试全绿提供充分的行为覆盖证据。

### README 同步

`tests/README.md` 行 115: "迁移前差分 corpus" → "迁移后固定 corpus"，正确反映 Slice 2B 完成后的测试语义变更 ✓。

---

## 自动化门禁

| 门禁 | 结果 |
|---|---|
| Pyright (`dayu/services/` + 4 changed test files) | 0 errors, 0 warnings, 0 informations ✓ |
| Ruff (`--select F,I001` on 9 production + 4 test files) | All checks passed ✓ |
| `git diff --check` | 通过 ✓ |

---

## Findings

### MEDIUM Findings

#### M1 — Plan Cohort B 迁移表未列出部分 deferred 私有定义（plan accuracy）

- **文件**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` 行 658–670
- **证据**: Plan 的 Cohort B 每文件迁移表的"保留原位/defer 项"列未列出 `_parse_utc`、`_target_path`、`_validate_source`。这些是 Group C/D deferred 项，在实现中被正确保留（私有一定义 + 类型精化 `value: object` → `value: ModelConfigJsonValue`），但 plan 表格未予记载。
- **影响**: Plan 作为实现真源的完整性与可审计性下降。实现行为正确。
- **文件/行**:
  - `_parse_utc`: `write_model_configuration_application.py:229`, `write_model_configuration_rollback_application.py:350`, `write_model_configuration_manual_recovery.py:307`, `write_model_configuration_manual_recovery_clearance.py:439`
  - `_target_path`: `write_model_configuration_rollback_application.py:328`, `write_model_configuration_manual_recovery.py:285`
  - `_validate_source`: `write_model_configuration_manual_recovery.py:339`, `write_model_configuration_manual_recovery_application.py:415`, `write_model_configuration_manual_recovery_clearance.py:684`, `write_model_configuration_manual_recovery_verification.py:218`
- **修复建议**: 在 plan §Slice 2B Cohort B 迁移表中补充上述 deferred 项的列出。不影响代码。

#### M2 — `_validate_source` 在 `clearance.py` 的类型签名与其他 3 文件的差异（consistency）

- **文件**: `write_model_configuration_manual_recovery_clearance.py:684-689`
- **证据**: `clearance.py` 的 `_validate_source` 签名为 `value: ModelConfigJsonValue | Mapping[str, ModelConfigJsonValue]`，而其他 3 个文件（`manual_recovery.py:339`, `manual_recovery_application.py:415`, `verification.py:218`）的签名仅为 `value: ModelConfigJsonValue`。
- **影响**: 低。`clearance.py` 接受更宽的类型，是 `JsonObject` 协变分支的合理使用（与 v4.4 `require_mapping` 类型扩宽一致）。但同一 deferred helper 在 4 个文件中签名不一致，未来若进一步治理 `_validate_source` 时可能产生混淆。
- **修复建议**: 在后续 `_validate_source` 治理 plan 中统一 4 文件的签名。当前运行时行为正确，不需立即修改。

#### M3 — 5 个 `_validated_fingerprint` deferred 定义的 diff 噪声（diff clarity）

- **文件**: `configuration_application.py`, `rollback_application.py`, `manual_recovery.py`, `incident_dossier.py`, `clearance.py`
- **证据**: 这 5 个文件的 `_validated_fingerprint` 在 diff 中表现为 `-def _validated_fingerprint(value: object, ...)` + `+def _validated_fingerprint(value: ModelConfigJsonValue, ...)`，各一行删除、一行新增。原因: 旧签名使用 `object`，新签名使用 `ModelConfigJsonValue`，仅类型注解变化，校验逻辑完全相同。
- **影响**: 使 diff 看起来比实际更大，review 时需逐项排除。但这是类型系统的正向改进（消除 `object`），并非行为回归。
- **修复建议**: 无需修复。可在实现记录中注明此类型精化操作及其 diff 效应。

### LOW Findings

#### L1 — 多行 `dict(require_mapping(...))` 格式使 grep 审计不可靠

- **文件**: `incident_dossier_revalidation.py`, `gate_revalidation.py`
- **证据**: `dict(require_mapping(...))` 在两文件中格式为:
  ```python
  dict(
      require_mapping(
          ...
  ```
  单行 `rg 'dict\(require_mapping'` 无法匹配，必须用 `rg -U 'dict\(\s*\n\s*require_mapping'`。
- **修复建议**: 在代码风格上接受此格式（符合项目现有风格）。在 plan 或 review doc 中标注多行格式以利后续审计。

#### L2 — tests/README.md 行 115 仅更新了 helper 测试入口说明

- **文件**: `tests/README.md:115`
- **证据**: `tests/README.md` 中的 `test_write_artifact_utils.py` 条目从"迁移前差分 corpus"更新为"迁移后固定 corpus"，语义正确。但 README 未列出新增的 `test_write_model_configuration_preapplication.py` 和 `test_write_model_configuration_manual_recovery_gate_revalidation.py` 中与本 slice 相关的 malformed corpus 测试。
- **修复建议**: 可选。在 README 中补充 malformed corpus 测试覆盖说明，或保留当前粒度（README 不列举单个测试的详细内容）。

---

## 过度耦合检查

| 检查项 | 结果 |
|---|---|
| Cohort B 文件是否反向 import Cohort A 文件？ | 否 —— 仅 import shared `_write_artifact_utils` ✓ |
| Cohort B 文件是否 import 其他 Cohort B 文件？ | 否 —— 无跨文件依赖 ✓ |
| Shared helper 是否被循环依赖？ | 否 —— `_write_artifact_utils` 为零入度叶子 ✓ |
| 测试是否跨模块导入已删除符号？ | 否 —— 仅导入 shared helper 或 deferred 私有符号 ✓ |
| 类型传播是否改变 public contract？ | 否 —— public 函数签名不变 ✓ |

---

## 未覆盖项与残余风险

1. **Snapshot/transaction/persist deferred 族**: 按 plan accepted defer，9 文件各自保留私有实现。业务差异未在本 slice 解决。
2. **Streamlit 依赖缺失**: 当前环境未安装可选 `streamlit`，4 个 Streamlit 测试模块在 collection 期被排除。237 个 write_model 测试覆盖了所有迁移后的 caller。
3. **`_validate_source` 8 文件闭合计数**: Plan §1.6.6 Group C 声称为 8 文件。当前剩余实现数为 4（Cohort B）+ Cohort A 中的数量（零 diff 意味着不变）。若总数不符合 8，需重新审计 plan 的 Group C 原始计数是否随重构变化（非本 slice scope）。
4. **族 B/C/D/E/F validated_fingerprint 和族 2/6/7 required_text**: 业务差异保留，后续需独立 plan 治理。

---

## Open Counts

- **HIGH**: 0
- **MEDIUM**: 3（M1 plan 表格不完整, M2 `_validate_source` 签名不一致, M3 diff 噪声）
- **LOW**: 2（L1 多行格式, L2 README 粒度）
- **代码修改需求**: 0（所有 findings 为 observational，不阻塞 merge）

---

## 审查结论

Slice 2B 实现质量达到 accepted plan 要求。全部 9 个 Cohort B 生产文件的 eligible 私有定义已正确迁移至 shared helper，全部 deferred 族正确保留。bytes/str fingerprint 家族、microseconds/seconds/auto 时间族、identity/copy mapping、dict adapter 均与 plan spec 一致。Pyright 零错误、ruff 零告警、237 个 write_model 测试全绿。类型传播无 `Any`/`object`/`cast`/`type:ignore` 逃逸。Cohort A 和 shared helper 零 diff。推荐 merge。
