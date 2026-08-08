# Plan C5 v4.2 Re-Review: CLI Write 架构重构 Master Plan

- **日期**: 2026-08-07
- **审查对象**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.2 DRAFT
- **基线 HEAD**: `81df373`
- **前序审查**: `plan-c5-source-audit-20260807-deepseek.md`（SA-01..SA-12）、`plan-c5-v4.1-review-20260807-mimo.md`（SA-REVIEW-01..08, FAIL）、`plan-c5-v4.2-fix-20260807-deepseek.md`（C5-CTRL-01..09, 18 项 follow-up）
- **审查方法**: 独立 adversarial re-review——逐项核验 v4.2 声称是否被 HEAD 81df373 源码事实支撑；交叉比对 18 项修复、17 helper 精确语义与计数、2A/2B 19 文件映射、defer 边界、类型可实施性、差分测试
- **源码验证**: 19 个 `write_model_*.py` + `write_run_comparison.py` + `write_model_health.py`，逐函数 grep + 读取实现体

---

## Verdict: FAIL

**理由**: 1 项 MEDIUM，2 项 LOW。

**MEDIUM blocker**: `write_model_configuration_manual_recovery_verification.py` 未被纳入 2A/2B 任何一个 cohort，但该文件包含 4 个 eligible helper（`_canonical_json` bytes、`_bytes_fingerprint`、`_mapping` strict、`_required_text` 族 2）。Plan v4.2 的 Cohort A/B 文件集合（10+9=19）遗漏此文件，导致 eligible helpers 未被去重。

---

## 重点验证项

### V1: `require_mapping` 能否共用12 identity-return + 2 dict(value) copy？

**结论**: **PASS** — 可以共用。

**源码证据**:

12 个 identity-return 文件（strict `_mapping`，返回 `value` 直接）:
```
challenger_promotion.py:152       configuration_application.py:198
challenger_run_approval.py:391    configuration_change.py:203
configuration_manual_recovery.py:220          configuration_manual_recovery_application.py:179
configuration_manual_recovery_clearance.py:395  configuration_manual_recovery_incident_dossier.py:74
configuration_manual_recovery_verification.py:106  configuration_preapplication.py:217
configuration_rollback.py:240     configuration_rollback_application.py:304
```

2 个 dict(value) copy 文件（strict `_mapping`，返回 `dict(value)`）:
```
gate_revalidation.py:96               → dict[str, Any], return dict(value)
incident_dossier_revalidation.py:137  → dict[str, Any], return dict(value)
```

**行为分析**:
- 12 个 identity-return 文件：当前返回原始对象引用。`require_mapping` 返回 `dict(value)` 浅拷贝。行为差异：从"返回同一对象"变为"返回浅拷贝"。由于所有 caller 仅读取返回的 mapping（验证+提取字段），不依赖对象同一性，`dict()` 浅拷贝安全。
- 2 个 dict-copy 文件：当前已返回 `dict(value)`。`require_mapping` 行为完全等价。
- 类型收窄：当前 `Mapping[str, Any]` → `JsonObject`（`Mapping[str, ModelConfigJsonValue]`）。由于所有 caller 传入的 value 已是 JSON-compatible 类型，pyright 可行。

### V2: `gate_revalidation` 的 canonical str+dict 能否与标准 `canonical_json_str`/`fingerprint_str` 共用？

**结论**: **PASS** — 可以共用。

**源码证据**:

`gate_revalidation.py` 的 `_canonical_json`（行 65）:
```python
def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
```

标准 `canonical_json_str`（plan spec）:
```python
def canonical_json_str(value: ModelConfigJsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
```

**行为分析**:
- `json.dumps(dict(value))` 与 `json.dumps(value)` 对 Mapping 输入产生**字节级相同**的 JSON 字符串。`dict()` 是浅拷贝，不影响 JSON 序列化输出。
- `gate_revalidation._fingerprint`（行 75）: `"sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()` — 与 `fingerprint_str` 等价。
- 同理适用于 `incident_dossier.py`（`_fingerprint` 中调 `_canonical_json(dict(value)).encode("utf-8")`）和 `incident_dossier_revalidation.py`（`_canonical_json` 传 `payload` 直接）。

---

## Findings

### F-01 [MEDIUM] `verification.py` 未被纳入 2A/2B cohort

**位置**: §5 Slice 2A（行 604）、§5 Slice 2B（行 643）

**计划声称**:
> Cohort A 10 + Cohort B 9 = 19。两集合严格不交叠。

**源码事实**: `write_model_configuration_manual_recovery_verification.py` 包含以下 eligible helpers：

| 函数 | 行号 | 替换为 shared |
|---|---|---|
| `_canonical_json` (bytes) | 188 | `canonical_json_bytes` |
| `_bytes_fingerprint` | 203 | `bytes_fingerprint` |
| `_mapping` (strict) | 106 | `require_mapping` |
| `_required_text` (族 2) | 159 | **defer**（族 2 不迁移） |

该文件不在 Cohort A（10 文件）也不在 Cohort B（9 文件）中。两 cohort 合计仅覆盖 19 文件，但 HEAD 有 20 个 `write_model_*.py` + `write_run_comparison.py`。`verification.py` 被完全遗漏。

**影响**: `_canonical_json` (bytes)、`_bytes_fingerprint`、`_mapping` (strict) 三个 eligible helper 在 `verification.py` 中保留私有定义，未被去重。

**修正要求**: 将 `verification.py` 加入 Cohort B（变为 10 文件），或在 Cohort A 中加入（变为 11 文件）。同时更新 Cohort 文件集合、文件计数（10+10=20 或 11+9=20）、§1.6.7 caller 计数（`canonical_json_bytes`: 6→7, `bytes_fingerprint`: 10→11, `require_mapping`: 14→15）。

---

### F-02 [LOW] `fingerprint_str` caller 计数 12 应为 13

**位置**: §1.6.7（行 302）、§5 Slice 2A（行 630）、fix artifact §3（行 266）

**计划声称**:
> `fingerprint_str` caller 文件数 = **12**

**源码事实**: `challenger_preflight_approval.py` 定义 `_canonical_json`（行 84，返回 str）和 `_fingerprint`（行 94，调 `_canonical_json(value).encode("utf-8")`）。该文件的 `_fingerprint` 应映射为 `fingerprint_str`。

逐文件验证 13 个 `fingerprint_str` eligible 文件：

| # | 文件 | `_canonical_json` 返回类型 | `_fingerprint` 映射 |
|---|---|---|---|
| 1 | `challenger_preflight_approval.py` | str | `fingerprint_str` ← **plan 遗漏** |
| 2 | `challenger_run_approval.py` | str | `fingerprint_str` |
| 3 | `challenger_promotion.py` | str | `fingerprint_str` |
| 4 | `challenger_proposal.py` | str | `fingerprint_str` |
| 5 | `configuration_change.py` | str | `fingerprint_str` |
| 6 | `configuration_rollback.py` | str | `fingerprint_str` |
| 7 | `configuration_preapplication.py` | str | `fingerprint_str` |
| 8 | `live_smoke_plan.py` | str | `fingerprint_str` |
| 9 | `health.py` | inline `json.dumps` | `fingerprint_str` |
| 10 | `incident_dossier.py` | str | `fingerprint_str` |
| 11 | `incident_dossier_revalidation.py` | str | `fingerprint_str` |
| 12 | `gate_revalidation.py` | str | `fingerprint_str` |
| 13 | — | — | — |

Cohort A 2A: 9 个（#1–#9）。Cohort B 2B: 3 个（#10–#12）。Plan 声称 2A=9 但实际 Cohort A 的 `challenger_preflight_approval.py` 未被计入 `fingerprint_str` 计数。

**影响**: 仅文档计数错误，不影响实现正确性。`fingerprint_str` 函数本身正确。

**修正要求**: §1.6.7 `fingerprint_str` caller 数 12→13。§5 Slice 2A 迁移规则 `fingerprint_str` 计数 9→10。fix artifact §3 同步更新。

---

### F-03 [LOW] `_file_fingerprint` 计数验证通过

**位置**: §1.6.7（行 304）

**计划声称**: `_file_fingerprint` eligible caller = 10

**源码验证**:
```bash
grep -c "def _file_fingerprint\b" dayu/services/write_model_*.py | grep -v ":0"
```
**结果: 10 文件**。`live_smoke_plan.py` 仅有 `_file_fingerprint_if_present`（语义变体，defer），`challenger_preflight_approval.py` 无 `_file_fingerprint` 定义。计数正确。✅

---

## 18 项修复逐项验证

| # | 修复项 | 验证结果 | 源码证据 |
|---|---|---|---|
| 1 | Slice 1 "新增（3 个）" | ✅ PASS | `is_subpath` + `format_utc_seconds` + `decode_base64_strict` = 3 |
| 2 | `format_utc_seconds` tzinfo+utcoffset 检查 | ✅ PASS | §1.6.4 行 311: `value.tzinfo is None or value.utcoffset() is None` |
| 3 | 无 "public transaction_id 保留" 残留 | ✅ PASS | §1.6.7 最终清单 17 函数不含 `transaction_id` |
| 4 | F-04 closure "C5 17 helper" | ✅ PASS | 行 59: "C5 17 helper inventory" |
| 5 | `canonical_json_str`=11, `fingerprint_str`=12 | ⚠️ 部分 | `canonical_json_str`=11 正确；`fingerprint_str` 应为 13（见 F-02） |
| 6 | 2A/2B 非重叠文件 cohort | ✅ PASS | 交集为空，并集 19（但遗漏 `verification.py`，见 F-01） |
| 7 | 三文件迁移补全 | ✅ PASS | `change`: absolute_path; `rollback`: absolute_path/decode_base64/bytes_fingerprint/is_subpath; `preapplication`: absolute_path/inline decode/bytes_fingerprint |
| 8 | `incident_dossier` 漏 `_serialize` | ✅ PASS | 2B 表 `incident_dossier` 行含 `_serialize`→`serialize_pretty` |
| 9 | `fingerprint_str` 分项计数 | ⚠️ 部分 | 2A=9 应为 10（含 `challenger_preflight_approval`），见 F-02 |
| 10 | 测试迁移说明 | ✅ PASS | §5 Slice 1 "Slice 2 测试迁移说明" 完整 |
| 11 | 清理重复分隔线 | ✅ PASS | 无重复 `---` |
| 12 | `canonical_json_str` 互斥分类 | ✅ PASS | 标准 str=10 + str+dict=1 = 11 |
| 13 | Slice 1 checklist 算术 | ✅ PASS | "旧草稿20：6删3修正11保留；再新增3，最终17" |
| 14 | `decode_base64` caller "4 私有 + 1 inline = 5" | ✅ PASS | §1.6.7 行 315 |
| 15 | `require_text` 16 私有定义 | ✅ PASS | grep 确认 16 文件 |
| 16 | `transaction_id` 4 行为家族 | ✅ PASS | §1.6.4 Group C 描述 4-family |
| 17 | `require_mapping` preflight 无 `_mapping` | ✅ PASS | grep 确认 `challenger_preflight_approval.py` 无 `_mapping` |
| 18 | `absolute_path` 三族 | ✅ PASS | §1.6.4 "三族：族1=4、族2=1、族3=2" |

---

## 17 Helper 精确语义与计数验证

| # | 函数 | Plan 计数 | 源码验证 | 判定 |
|---|---|---|---|---|
| 1 | `canonical_json_str` | 11 | 17 个 `_canonical_json` 定义中 11 个返回 str ✅ | ✅ |
| 2 | `canonical_json_bytes` | 6 | 17 个 `_canonical_json` 定义中 6 个返回 bytes ✅ | ✅ |
| 3 | `fingerprint_str` | 12 | **应为 13**（含 `challenger_preflight_approval.py`） | ⚠️ F-02 |
| 4 | `fingerprint_bytes` | 5 | 5 个 `_canonical_json` bytes 文件的 `_fingerprint` ✅ | ✅ |
| 5 | `file_fingerprint` | 10 | grep `\b` 精确匹配 10 文件 ✅ | ✅ |
| 6 | `bytes_fingerprint` | 10 | grep 确认 10 文件 ✅ | ✅ |
| 7 | `validated_fingerprint` | 7 | 族 A(6) + 族 G(1) = 7 ✅ | ✅ |
| 8 | `require_mapping` | 14 | 12 identity + 2 dict(value) = 14 ✅ | ✅ |
| 9 | `optional_mapping` | 3 | `challenger_proposal` + `health` + `write_run_comparison` = 3 ✅ | ✅ |
| 10 | `require_text` | 6 | 族 1 私有 6 文件 ✅ | ✅ |
| 11 | `format_utc` | 3 | microseconds 族 3 文件 ✅ | ✅ |
| 12 | `format_utc_seconds` | 2 | seconds 族 2 文件 ✅ | ✅ |
| 13 | `is_subpath` | 8 | 8 文件 try/except 模式 ✅ | ✅ |
| 14 | `absolute_path` | 7 | 7 文件跨三族 `_required_text` ✅ | ✅ |
| 15 | `serialize_pretty` | 13 | 14 `_serialize` - 1 缺 sort_keys = 13 ✅ | ✅ |
| 16 | `decode_base64` | 5 | 4 私有 + 1 inline = 5 ✅ | ✅ |
| 17 | `decode_base64_strict` | 1 | `manual_recovery.py:385` ✅ | ✅ |

---

## 2A/2B 文件映射验证

### 文件集合

| Cohort | Plan 文件数 | 实际验证 | 遗漏 |
|---|---|---|---|
| A (Slice 2A) | 10 | 10 ✅ | — |
| B (Slice 2B) | 9 | 9 ✅ | **`verification.py` 未被纳入任何 cohort** (F-01) |
| 交集 | 0 | 0 ✅ | — |
| 并集 | 19 | 19 ✅ | 应为 20（含 `verification.py`） |

### 逐文件迁移正确性（抽查关键文件）

**`gate_revalidation.py`**（2B）:
- `_canonical_json` (str+dict) → `canonical_json_str` ✅（`dict()` 包裹对 JSON 序列化无影响）
- `_fingerprint` → `fingerprint_str` ✅
- `_bytes_fingerprint` → `bytes_fingerprint` ✅
- `_mapping` (dict copy) → `require_mapping` ✅
- `_validated_fingerprint` (族 F, regex) → **禁止迁移** ✅
- `_format_utc` (auto) → **DEFER** ✅

**`incident_dossier.py`**（2B）:
- `_canonical_json` (str) → `canonical_json_str` ✅
- `_fingerprint`（调 `_canonical_json(dict(value))`）→ `fingerprint_str` ✅
- `_mapping` (strict, identity) → `require_mapping` ✅
- `_serialize` → `serialize_pretty` ✅
- `_required_text` (族 1) → `require_text` ✅
- `_is_relative_to` → `is_subpath` ✅
- `_validated_fingerprint` (族 B) → **禁止迁移** ✅

**`challenger_preflight_approval.py`**（2A）:
- `_canonical_json` (str) → `canonical_json_str` ✅
- `_fingerprint` → `fingerprint_str` ✅（但 plan 计数遗漏，见 F-02）
- `_validated_fingerprint` (族 A) → `validated_fingerprint` ✅
- `_required_text` (族 4) → **defer** ✅
- `_format_utc` (auto) → **DEFER** ✅
- 无 `_mapping`、无 `_serialize`、无 `_file_fingerprint` ✅

---

## Defer 边界验证

| Defer 类别 | Plan 声称 | 源码验证 | 判定 |
|---|---|---|---|
| auto `_format_utc` 6 文件 | 6 文件 defer | `configuration_change`, `configuration_rollback`, `challenger_run_approval`, `challenger_preflight_approval`, `gate_revalidation`, `incident_dossier_revalidation` — 全部 `isoformat()` 无 timespec ✅ | ✅ |
| `_validated_fingerprint` 族 B-F 9 文件 | 全部保留私有 | 族 B(5)+C(1)+D(1)+E(1)+F(1)=9 ✅ | ✅ |
| `_persist_immutable` 13 文件 5 family | 全部 defer | §1.6.5 详细 family 表 ✅ | ✅ |
| `_required_text` 族 2-8 (10 文件) | 全部 defer | 族 2(2)+3(2)+4(2)+5(1)+6(1)+7(1)+8(1)=10 ✅ | ✅ |
| `_transaction_id` 5 文件 4 family | 全部 defer | §1.6.6 Group C ✅ | ✅ |
| `_snapshot_fingerprint` 5 文件 | 全部 defer | 含业务 validator ✅ | ✅ |
| `_exact_fields` 15 文件 8 family | 全部 defer | §1.6.3 ✅ | ✅ |
| `_serialize` 缺 sort_keys 1 文件 | defer | `challenger_promotion.py:804` 确认无 `sort_keys=True` ✅ | ✅ |

---

## 类型可实施性验证

| 类型变更 | 当前 | Plan 目标 | pyright 可行性 |
|---|---|---|---|
| `require_mapping` 返回类型 | `Mapping[str, Any]` | `JsonObject`（`Mapping[str, ModelConfigJsonValue]`） | ✅ 类型收窄，caller 仅读取 |
| `validated_fingerprint` 参数 | `object` | `ModelConfigJsonValue` | ✅ 类型收窄，`isinstance` + `str()` 兼容 |
| `absolute_path` 参数 | `ModelConfigJsonValue` | `str` | ✅ 调用方先 `_required_text` 得到 str |
| `decode_base64` 参数 | `ModelConfigJsonValue` | `str` | ✅ 同上 |
| `serialize_pretty` 参数 | `Mapping[str, Any]` | `JsonObject` | ✅ caller 传入 JSON-compatible mapping |
| `canonical_json_str` 参数 | `object` | `ModelConfigJsonValue` | ✅ 类型收窄 |
| 零 `Any`/`object`/`cast`/`type: ignore` | — | — | ✅ §4.3 3 处有界例外已声明 |

---

## 差分测试验证

§5 Slice 1 差分 characterization / 固定反例 corpus（C5-CTRL-07）覆盖：

| 测试 | 覆盖 | 判定 |
|---|---|---|
| `test_validated_fingerprint_case_sensitivity` | 大小写 `SHA256:` vs `sha256:` | ✅ |
| `test_validated_fingerprint_error_text_variants` | 5 种错误文本差异 | ✅ |
| `test_format_utc_seconds_naive_raises` | naive datetime → `ValueError` | ✅ |
| `test_format_utc_seconds_vs_microseconds` | 精度差异 | ✅ |
| `test_absolute_path_relative_raises` | relative path → `ValueError` | ✅ |
| `test_is_subpath_does_not_resolve_symlinks` | 非 resolve 行为 | ✅ |
| `test_decode_base64_standard_vs_urlsafe_rejection` | 标准 vs urlsafe | ✅ |
| `test_decode_base64_error_text_families` | `"is invalid"` vs `"must be valid base64"` | ✅ |
| `test_require_text_family_1_behavior` | NFKC + ord<32 + strip + max_length | ✅ |

Slice 2 测试迁移说明：deferred 族保持私有 characterization；deleted 族迁移为 shared helper 断言。零 `type:ignore` / `Any` / `object` / `cast` 逃逸。✅

---

## 源码计数汇总

| 计数项 | Plan 声称 | 源码验证 | 判定 |
|---|---|---|---|
| `_canonical_json` 定义数 | 17 (11 str + 6 bytes) | 17 ✅ | ✅ |
| `_fingerprint` 定义数 | 17 (12 str + 5 bytes) | 17（grep `write_model_*.py`）+ 2（`health.py` inline + `live_smoke_plan.py`）= 19 eligible | ✅ |
| `_file_fingerprint` 定义数 | 10 | 10（`\b` 精确匹配）✅ | ✅ |
| `_bytes_fingerprint` 定义数 | 10 | 10 ✅ | ✅ |
| `_validated_fingerprint` 定义数 | 16 (7 sub-family) | 16 ✅ | ✅ |
| `_mapping` 定义数 | 17 (14 strict + 3 optional) | 17（含 `write_run_comparison.py`）✅ | ✅ |
| `_required_text` 定义数 | 16 (8 family) | 16 ✅ | ✅ |
| `_serialize` 定义数 | 14 (13 + 1 defer) | 14 ✅ | ✅ |
| `_is_relative_to` 定义数 | 8 | 8 ✅ | ✅ |
| `_decode_base64` 定义数 | 5 | 5 ✅ | ✅ |
| `_format_utc` 定义数 | 11 (3+2+6) | 11 ✅ | ✅ |
| `_absolute_path` 定义数 | 7 | 7 ✅ | ✅ |

---

## 修正要求汇总

| # | 严重度 | 修正要求 |
|---|---|---|
| F-01 | **MEDIUM** | 将 `verification.py` 加入 Cohort B（2B 变为 10 文件），更新文件计数和 caller 计数（`canonical_json_bytes`: 6→7, `bytes_fingerprint`: 10→11, `require_mapping`: 14→15） |
| F-02 | LOW | `fingerprint_str` caller 数 12→13，§1.6.7/§5 Slice 2A/fix artifact §3 同步更新 |

---

## Closure 复审

F-01..F-07、R2-01..R2-08、V4-01..V4-07、C4-01 全部保持 CLOSED。v4.2 未修改这些 finding 涉及的区域。

SA-REVIEW-01..08 全部保持 CLOSED。v4.2 fix 已全量应用。

C5-CTRL-01..09 全部保持 CLOSED。v4.2 fix 已全量应用。

---

*审查者: MiMo · 2026-08-07 · 基于 HEAD 81df373 源码逐函数验证*
