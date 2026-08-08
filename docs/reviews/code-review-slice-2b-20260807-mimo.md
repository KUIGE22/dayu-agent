# Slice 2B MiMo 独立审查报告

- **日期**: 2026-08-07
- **基线**: `ba8b83e` (`gateflow: accept write artifact callers slice 2a`)
- **审查者**: MiMo 第二路独立审查
- **范围**: Slice 2B Cohort B 9 个生产文件 + 4 个测试/索引文件 + 1 个实现记录
- **状态**: **PASS — 零 High/Medium findings**

---

## 1. 审查方法

独立运行以下验证，未依赖实现 artifact 中声明的结果：

1. 完整读取 AGENTS.md、plan v4.4 Slice 2B、实现 artifact
2. 完整读取 ba8b83e 后全部 tracked diff（6152 行）
3. 逐文件 adversarial 核对 eligible 删除 / defer 保留
4. pytest（237 passed, 1 skipped）、pyright（0 errors）、ruff（基线无新增规则码）
5. 结构审计：Cohort A 零 diff、类型逃逸零新增、git diff --check 通过

---

## 2. 逐文件 adversarial 核对

### 2.1 eligible 定义删除验证

| 文件 | 删除的 eligible | 保留的 defer | 判定 |
|---|---|---|---|
| `application.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc`, `_is_relative_to`, `_serialize`, `_decode_base64` (11) | `_validated_fingerprint` (族 C) | ✅ |
| `rollback_application.py` | 同 application (11) | `_validated_fingerprint` (族 B) | ✅ |
| `manual_recovery.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc`, `_serialize`, `_decode_base64` (10) | `_validated_fingerprint` (族 D) | ✅ |
| `manual_recovery_application.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_absolute_path`, `_is_relative_to`, `_serialize`, `_decode_base64`, `_format_utc` (10) | `_required_text` (族 2), `_validated_fingerprint` (族 B) | ✅ |
| `manual_recovery_clearance.py` | `_mapping`, `_required_text`, `_format_utc`, `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_serialize`, `_is_relative_to` (9) | `_validated_fingerprint` (族 B) | ✅ |
| `manual_recovery_verification.py` | `_canonical_json`, `_bytes_fingerprint`, `_mapping` (3) | `_required_text` (族 2), `_validated_fingerprint` (族 E) | ✅ |
| `manual_recovery_incident_dossier.py` | `_canonical_json`, `_fingerprint`, `_mapping`, `_required_text`, `_is_relative_to`, `_serialize` (6) | `_validated_fingerprint` (族 B) | ✅ |
| `dossier_revalidation.py` | `_canonical_json`, `_fingerprint`, `_bytes_fingerprint`, `_serialize`, `_mapping`, `_is_relative_to` (6) | `_required_text` (族 6), `_format_utc` (auto), `_validated_fingerprint` (族 B) | ✅ |
| `gate_revalidation.py` | `_canonical_json`, `_fingerprint`, `_bytes_fingerprint`, `_serialize`, `_mapping`, `_is_relative_to` (6) | `_required_text` (族 7), `_format_utc` (auto), `_validated_fingerprint` (族 F) | ✅ |

**判定**: 9 文件全部 eligible 删除完整，defer 保留完整，与 plan §1.6.6 Group C/D 一致。

### 2.2 bytes/str fingerprint 家族隔离

| 家族 | 使用文件 | shared helper | 判定 |
|---|---|---|---|
| bytes family (→ bytes) | application, rollback_application, manual_recovery, manual_recovery_application, clearance, verification | `fingerprint_bytes`, `bytes_fingerprint`, `canonical_json_bytes` | ✅ |
| str family (→ str) | incident_dossier, dossier_revalidation, gate_revalidation | `fingerprint_str`, `canonical_json_str` | ✅ |

两族未混用。dossier_revalidation/gate_revalidation 使用 `canonical_json_str` + `fingerprint_str`；其余 6 文件使用 `canonical_json_bytes` + `fingerprint_bytes`/`bytes_fingerprint`。

### 2.3 九个私有 `_validated_fingerprint` 隔离

9 个文件均保留私有 `_validated_fingerprint`，grep 确认 shared `validated_fingerprint` 调用为零。每个私有实现调用本地 defer 的 `_required_text`（或 shared `require_text`），不调用 shared `validated_fingerprint`。

### 2.4 时间族正确性

| 文件 | 时间精度 | helper | 判定 |
|---|---|---|---|
| application, rollback_application, manual_recovery | microseconds | `format_utc` | ✅ |
| manual_recovery_application, clearance | seconds | `format_utc_seconds` | ✅ |
| dossier_revalidation, gate_revalidation | auto (defer) | `_format_utc` (`.isoformat()` 无 timespec) | ✅ |

### 2.5 absolute_path / decode_base64 text 前置

各 caller 先经对应的 shared `require_text` 或 retained local `_required_text` 提取字符串，再传入 `absolute_path()` / `decode_base64()` / `decode_base64_strict()`。旧代码中 `_absolute_path` / `_decode_base64` 内部调用 `_required_text` 的两步链已拆为 caller 显式前置，shared `absolute_path` / `decode_base64` 仅接收已校验的 `str`。

逐文件 text 前置来源：

| 文件 | absolute_path / decode 前置 text 来源 | 判定 |
|---|---|---|
| `application.py` | shared `require_text`（family 1，已迁） | ✅ |
| `rollback_application.py` | shared `require_text`（family 1，已迁） | ✅ |
| `manual_recovery.py` | shared `require_text`（family 1，已迁） | ✅ |
| `manual_recovery_application.py` | retained local `_required_text`（族 2，defer；未迁 shared） | ✅ |

模式一致：`absolute_path(require_text(..., maximum_length=32_768), name=...)` 或 `absolute_path(_required_text(..., maximum_length=32_768), name=...)`，`decode_base64(require_text(..., maximum_length=1_000_000), name=...)` 或 `decode_base64(_required_text(..., maximum_length=1_000_000), name=...)`。其余 5 文件（clearance, verification, dossier, dossier_revalidation, gate_revalidation）不调用 `absolute_path`/`decode_base64`/`decode_base64_strict`，不涉及此模式。

### 2.6 copy mapping dict adapter

两个 copy mapping 文件（dossier_revalidation, gate_revalidation）在每个 call site 正确使用：
- `dict(require_mapping(...))` — 保持 copy 语义
- `fingerprint_str(dict(...))` / `canonical_json_str(dict(...))` — 适配 dict 输入

验证行号：dossier_revalidation 244, 270, 352, 406, 412, 539, 786, 792；gate_revalidation 194, 200, 244, 284, 290, 320, 328, 356, 362, 406, 517, 525, 647, 653。

### 2.7 类型传播

- 零新增 `Any` 导入
- 零新增 `cast()` 调用
- 零新增 `type: ignore` 注释
- 零新增裸 `object` 类型注解（所有新增参数使用 `ModelConfigJsonValue`）
- 零新增 `Callable[..., ...]`
- 零新增 `getattr`/`hasattr`

### 2.8 测试验证

- 测试不再导入已删除的私有符号（`application._fingerprint`, `application._canonical_json`, `application._format_utc`, `application._serialize`, `application._decode_base64`, `application._is_relative_to`, `recovery_application._format_utc`, `manual_recovery._decode_base64`, `gate_revalidation._canonical_json`, `gate_revalidation._fingerprint`, `dossier_revalidation._fingerprint` 等）
- 测试改为直接断言 shared helper 输出（固定 corpus），不再通过已删除的私有 seam
- 新增 malformed corpus：gate_revalidation 测试新增 8 个畸形顶层字段验证；preapplication 测试新增 dossier revalidation 8 个畸形字段 + evidence 12 个畸形分支
- `tests/README.md` 更新为迁移后语义

### 2.9 Cohort A / shared / plan 零 diff

`git diff ba8b83e -- <10 Cohort A files>` 输出为空。shared helper `_write_artifact_utils.py`、plan 文件均未修改。

---

## 3. 独立验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests/application/test_write_artifact_utils.py -q` | **23 passed** |
| `pytest tests/application/test_write_model_configuration_manual_recovery_gate_revalidation.py -q` | **5 passed** |
| `pytest tests/application -k write_model -q` (排除 4 个 Streamlit 模块) | **237 passed, 1 skipped, 1082 deselected** |
| `pyright <13 files>` | **0 errors, 0 warnings, 0 informations** |
| `ruff check <13 files>` | All checks passed（规则码与 HEAD 基线一致） |
| `git diff --check` | 通过 |
| eligible 定义 grep | 9 文件零残留 |
| deferred `_validated_fingerprint` grep | 9 文件全部保留，shared 调用零 |
| Cohort A diff | 零 |
| 类型逃逸 grep | 零 |

---

## 4. Findings

### High

无。

### Medium

无。

### Low

| # | 文件 | 说明 | 严重度 |
|---|---|---|---|
| L1 | 全部 9 文件 | ruff 基线规则码（FURB162, TRY004, BLE001, UP012, RUF022）在 HEAD 已存在，本次 diff 未新增任何规则码。部分文件的 TRY004 计数因删除 eligible 定义而减少，属于正向改进。 | Low / Info |
| L2 | `manual_recovery_application.py` | 保留的 `_required_text`（族 2）仍使用 `object` 参数类型，与 shared `require_text` 的 `ModelConfigJsonValue` 不同。这是 accepted plan 明示 defer，后续 Slice 统一。 | Low / Accepted |
| L3 | `dossier_revalidation.py`, `gate_revalidation.py` | 保留的 `_format_utc`（auto precision）使用 `.isoformat()` 无 timespec，与 microseconds/seconds 两族不同。这是 accepted plan 明示 defer。 | Low / Accepted |

---

## 5. Verdict

**PASS** — Slice 2B Cohort B 实现完整、边界正确、测试充分。

- 9 文件 eligible 定义全部删除，defer 全部保留
- bytes/str fingerprint 家族零混用
- 9 个私有 `_validated_fingerprint` 零调用 shared
- 时间族三路分布正确
- absolute_path / decode_base64 全部有 require_text 前置
- copy mapping 全部 call site 有 dict() adapter
- 类型传播零逃逸
- 测试 237 passed, pyright 0 errors, ruff 基线无新增
- Cohort A / shared / plan 零 diff

---

## 6. Open Counts

| 类别 | 数量 |
|---|---|
| High findings | 0 |
| Medium findings | 0 |
| Low findings | 3 (均为 Info / Accepted) |
| 总计 | 3 |
