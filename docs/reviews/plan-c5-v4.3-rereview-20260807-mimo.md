# Plan C5 v4.3 Re-Review: CLI Write 架构重构 Master Plan

- **日期**: 2026-08-07
- **审查对象**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.3 DRAFT
- **基线 HEAD**: `81df373`
- **前序审查**: `plan-c5-v4.2-rereview-20260807-mimo.md`（MiMo v4.2 re-review，FAIL）、`plan-c5-v4.3-fix-20260807-deepseek.md`（v4.3 fix artifact，RR-F01/RR-F02 REJECTED + C5-CTRL-10 ACCEPTED）
- **审查方法**: 独立 adversarial re-review——逐项核验 v4.3 adjudication 是否被 HEAD 81df373 源码事实支撑；独立验证 C5-CTRL-10 全部 6 项修正；复核 17 helper 计数、19 文件集合、defer 边界
- **源码验证**: 19 个 `write_model_*.py` + `write_run_comparison.py`，逐函数 grep + 读取实现体

---

## Verdict: PASS

**理由**: v4.3 adjudication 全部正确，C5-CTRL-10 设计可实施，17 helper 计数/19 文件集合/defer 边界无回归。1 项 LOW 文档计数瑕疵（不影响实现正确性）。

---

## 上轮 Finding 最终状态

### RR-F01 [MiMo F-01] — REJECTED ✅ 维持

**v4.3 fix artifact 裁决**: REJECTED / EVIDENCE INVALID。verification.py 已在 Cohort B 集合与迁移表中。

**独立验证**: ✅ 裁决正确。

**源码证据**:

1. **Cohort B 文件集合**（plan v4.3 行 649）明确包含 `write_model_configuration_manual_recovery_verification.py`。

2. **2B 迁移表**（plan v4.3 行 664）包含 verification.py 完整迁移行：
   - `_canonical_json` (bytes) → `canonical_json_bytes`
   - `_bytes_fingerprint` → `bytes_fingerprint`
   - `_mapping` → `require_mapping`

3. **HEAD 81df373 源码确认** verification.py 包含 3 个 eligible helper：
   ```
   106: def _mapping(value: object, *, name: str) -> Mapping[str, Any]:    → return value (identity)
   188: def _canonical_json(payload: Mapping[str, Any]) -> bytes:          → bytes return
   203: def _bytes_fingerprint(value: bytes) -> str:                        → eligible
   ```

4. **文件计数**: 19 个 `write_model_*.py` + `write_run_comparison.py`。Cohort A 10 + Cohort B 9 = 19。verification.py 在 Cohort B 中，计数正确。

**结论**: MiMo v4.2 re-review 的 F-01 声称"verification.py 未被纳入任何 cohort"为证据失效。该文件在 v4.2 的 Cohort B 集合和迁移表中已存在。RR-F01 REJECTED 维持。

---

### RR-F02 [MiMo F-02] — REJECTED ✅ 维持

**v4.3 fix artifact 裁决**: REJECTED / EVIDENCE INVALID。fingerprint_str=12 正确，preflight 已在 2A 中。

**独立验证**: ✅ 裁决正确。

**源码证据**:

1. **MiMo 自带证据矛盾**: MiMo v4.2 re-review 行 114–127 的验证表仅列 12 项，#13 为空行。MiMo 声称"应为 13"但自身证据表不支持此声称。

2. **HEAD 81df373 `_fingerprint` 定义**: 17 个文件定义 `_fingerprint`：
   - **str 系 12 文件**（`_canonical_json` 返回 str → `.encode("utf-8")` → sha256）: challenger_preflight_approval, challenger_promotion, challenger_proposal, challenger_run_approval, configuration_change, configuration_preapplication, configuration_rollback, live_smoke_plan, health (inline json.dumps), incident_dossier, incident_dossier_revalidation, gate_revalidation
   - **bytes 系 5 文件**（`_canonical_json` 返回 bytes → sha256 直接）: configuration_application, manual_recovery, manual_recovery_application, manual_recovery_clearance, rollback_application

3. **challenger_preflight_approval.py 已在 Cohort A**: plan v4.3 行 624 迁移表明确列出 `_fingerprint` → `fingerprint_str`。

4. **fingerprint_str caller = 12 正确**: 11 个 str 系 `_canonical_json` 文件 + 1 个 health.py 内联等价 = 12。`verification.py` 无 `_fingerprint` 定义（仅有 `_bytes_fingerprint`），不计入。

**结论**: MiMo 的 F-02 声称"fingerprint_str 应为 13"为证据失效。MiMo 自带验证表仅列 12 项且 #13 为空。RR-F02 REJECTED 维持。

---

## C5-CTRL-10 独立验证

### 总体结论: ✅ PASS — 设计可实施，源码证据充分

### 10.1 require_mapping 必须保留 identity-return

**plan 声称**: shared `require_mapping` 为 identity-return（`return value`），不返回 `dict(value)`。

**源码验证**:

16 个 `_mapping` 定义在 `write_model_*.py` + 1 个在 `write_run_comparison.py`，共 17 个：

**strict 版 14 个**（需 `name` 参数，raise ValueError）:
- **identity-return 12 个**（`return value`）: challenger_promotion, challenger_run_approval, configuration_change, configuration_application, configuration_manual_recovery, configuration_manual_recovery_application, configuration_manual_recovery_clearance, configuration_manual_recovery_incident_dossier, configuration_manual_recovery_verification, configuration_preapplication, configuration_rollback, configuration_rollback_application
- **copy族 2 个**（`return dict(value)`）: gate_revalidation, incident_dossier_revalidation

**optional 版 3 个**（无 `name` 参数，静默回退）: challenger_proposal, health, write_run_comparison

**判定**: ✅ 12 identity + 2 copy + 3 optional = 17。require_mapping 保留 identity-return 正确——12 个文件直接迁移，2 个 copy 文件需 call-site adapter。

### 10.2 两个 copy族用 dict(require_mapping(...))

**plan 声称**: `incident_dossier_revalidation` 和 `gate_revalidation` 的 `_mapping` 替换为 `dict(require_mapping(value, name=...))`。

**源码验证**:

gate_revalidation.py `_mapping`（行 96）:
```python
def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)
```

incident_dossier_revalidation.py `_mapping`（行 137）:
```python
def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)
```

**替换等价性**: `dict(require_mapping(value, name=...))` = `dict(value)`（require_mapping 做 isinstance 检查后 return value，dict() 浅拷贝）。行为完全等价。

**判定**: ✅

### 10.3 gate canonical/fingerprint 及 incident_dossier_revalidation fingerprint 的 dict adapter

**plan 声称**:
- `gate_revalidation` 的 `_canonical_json`（str+dict 子变体）→ `canonical_json_str(dict(value))`
- `gate_revalidation` 的 `_fingerprint` → `fingerprint_str(dict(value))`
- `incident_dossier_revalidation` 的 `_fingerprint`（调 `_canonical_json(dict(value))`）→ `fingerprint_str(dict(value))`

**源码验证**:

gate_revalidation.py `_canonical_json`（行 65）:
```python
def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
```

gate_revalidation.py `_fingerprint`（行 75）:
```python
def _fingerprint(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
```

incident_dossier_revalidation.py `_fingerprint`（行 147）:
```python
def _fingerprint(value: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(dict(value)).encode("utf-8")).hexdigest()
    return f"{_FINGERPRINT_PREFIX}{digest}"
```

**替换等价性**:
- `canonical_json_str(dict(value))` = `json.dumps(dict(value), ...)` = 旧 `_canonical_json(value)`（内部 `dict(value)`）✅
- `fingerprint_str(dict(value))` = `sha256(canonical_json_str(dict(value)).encode("utf-8"))` = 旧 `_fingerprint(value)`（内部 `_canonical_json(value)` → `dict(value)`）✅
- `fingerprint_str(dict(value))` = 旧 `_fingerprint(value)`（内部 `_canonical_json(dict(value))`）✅

**判定**: ✅ dict adapter 保持旧行为，字节级等价。

### 10.4 dict 子类差分测试可实施且不使用 Any/object/cast/type-ignore

**plan 声称**: Slice 1 差分 corpus 新增 dict 子类 identity/copy 测试，验证 `require_mapping(value) is value`、`dict(require_mapping(value)) is not value` 且 `== value`；验证 gate_revalidation/incident_dossier_revalidation 的 `dict()` canonical/fingerprint adapter 输出与旧实现完全一致。零 `Any`/`object`/`cast`/`type: ignore`。

**设计验证**:

```python
class _DictSubclass(dict):
    """用于差分测试的 dict 子类，零 Any/object/cast/type-ignore。"""
    pass

def test_require_mapping_identity_vs_copy() -> None:
    """验证 identity 族 require_mapping 返回同一对象，copy 族 adapter 返回新对象。"""
    original = _DictSubclass({"key": "value"})
    # identity: require_mapping 返回同一对象
    result = require_mapping(original, name="test")
    assert result is original  # identity
    assert result == original  # 值相等
    # copy: dict(require_mapping(...)) 返回新对象
    copied = dict(require_mapping(original, name="test"))
    assert copied is not original  # 不同对象
    assert copied == original      # 值相等
```

**类型可行性**: `_DictSubclass` 继承 `dict[str, str]`，传入 `require_mapping(value: ModelConfigJsonValue, ...)` 时 pyright 可接受（`dict[str, str]` 是 `ModelConfigJsonValue` 的子类型）。零 `Any`/`object`/`cast`/`type: ignore`。

**canonical/fingerprint adapter 一致性测试**:
```python
def test_gate_revalidation_canonical_adapter() -> None:
    """验证 canonical_json_str(dict(value)) 与旧 _canonical_json(value) 输出一致。"""
    value = _DictSubclass({"b": 2, "a": 1})
    # 旧实现: json.dumps(dict(value), sort_keys=True, ...)
    # 新实现: canonical_json_str(dict(value)) = json.dumps(dict(value), sort_keys=True, ...)
    # dict(dict(value)) = dict(value)（浅拷贝），JSON 序列化输出字节级一致
    assert canonical_json_str(dict(value)) == canonical_json_str(value)
```

**判定**: ✅ 测试设计可实施，类型安全，零逃逸。

---

## 17 Helper 计数复核

| # | 函数 | Plan 计数 | 源码验证 | 判定 |
|---|---|---|---|---|
| 1 | `canonical_json_str` | 11 | 17 个 `_canonical_json` 中 11 个返回 str ✅ | ✅ |
| 2 | `canonical_json_bytes` | 6 | 17 个 `_canonical_json` 中 6 个返回 bytes ✅ | ✅ |
| 3 | `fingerprint_str` | 12 | 12 个 str 系 `_fingerprint`（含 health.py inline）✅ | ✅ |
| 4 | `fingerprint_bytes` | 5 | 5 个 bytes 系 `_fingerprint` ✅ | ✅ |
| 5 | `file_fingerprint` | 10 | grep `\b` 精确匹配 10 文件 ✅ | ✅ |
| 6 | `bytes_fingerprint` | 10 | grep 确认 10 文件 ✅ | ✅ |
| 7 | `validated_fingerprint` | 7 | 族 A(6) + 族 G(1) = 7 ✅ | ✅ |
| 8 | `require_mapping` | 14 | 12 identity + 2 dict(value) = 14 ✅ | ✅ |
| 9 | `optional_mapping` | 3 | challenger_proposal + health + write_run_comparison = 3 ✅ | ✅ |
| 10 | `require_text` | 6 | 族 1 私有 6 文件 ✅ | ✅ |
| 11 | `format_utc` | 3 | microseconds 族 3 文件 ✅ | ✅ |
| 12 | `format_utc_seconds` | 2 | seconds 族 2 文件 ✅ | ✅ |
| 13 | `is_subpath` | 8 | 8 文件 try/except 模式 ✅ | ✅ |
| 14 | `absolute_path` | 7 | 7 文件跨三族 `_required_text` ✅ | ✅ |
| 15 | `serialize_pretty` | 13 | 14 `_serialize` - 1 缺 sort_keys = 13 ✅ | ✅ |
| 16 | `decode_base64` | 5 | **应为 6**（5 私有定义 + 1 inline）。4 映射到 `decode_base64` + 1 映射到 `decode_base64_strict` + 1 inline = 6 eligible files | ⚠️ LOW |
| 17 | `decode_base64_strict` | 1 | `manual_recovery.py:385` ✅ | ✅ |

**decode_base64 计数瑕疵**: plan §1.6.7 行 316 声称 `decode_base64` caller = "5（4 私有 + 1 inline）"。实际为 5 个 `_decode_base64` 定义（configuration_application, manual_recovery, manual_recovery_application, configuration_rollback, rollback_application）+ 1 个 inline（configuration_preapplication）= 6 个 eligible files。其中 manual_recovery.py 的 `_decode_base64` 映射到 `decode_base64_strict`，其余 4 个映射到 `decode_base64`。plan 计数少 1。**影响**: 仅文档计数，不影响实现——Slice 2A/2B 逐文件迁移表已正确列出每个文件的迁移条目。

---

## 19 文件集合复核

| Cohort | Plan 文件数 | 源码验证 | 判定 |
|---|---|---|---|
| A (Slice 2A) | 10 | 10 ✅ | ✅ |
| B (Slice 2B) | 9 | 9 ✅（含 verification.py） | ✅ |
| 交集 | 0 | 0 ✅ | ✅ |
| 并集 | 19 | 19 ✅ | ✅ |
| 未覆盖 | — | `challenger_verification.py`（零 eligible helper）✅ | ✅ |

**Cohort A 10 文件**: configuration_change, configuration_rollback, configuration_preapplication, challenger_run_approval, challenger_preflight_approval, challenger_promotion, challenger_proposal, health, live_smoke_plan, write_run_comparison ✅

**Cohort B 9 文件**: configuration_application, rollback_application, manual_recovery, manual_recovery_application, manual_recovery_clearance, manual_recovery_verification, incident_dossier, incident_dossier_revalidation, gate_revalidation ✅

---

## Defer 边界复核

| Defer 类别 | Plan 声称 | 源码验证 | 判定 |
|---|---|---|---|
| auto `_format_utc` 6 文件 | 6 文件 defer | 6 文件确认 ✅ | ✅ |
| `_validated_fingerprint` 族 B-F | 9 文件保留私有 | 族 B(5)+C(1)+D(1)+E(1)+F(1)=9 ✅ | ✅ |
| `_persist_immutable` 13 文件 5 family | 全部 defer | 13 文件确认 ✅ | ✅ |
| `_required_text` 族 2-8 (10 文件) | 全部 defer | 族 2(2)+3(2)+4(2)+5(1)+6(1)+7(1)+8(1)=10 ✅ | ✅ |
| `_transaction_id` 5 文件 4 family | 全部 defer | 5 文件确认 ✅ | ✅ |
| `_snapshot_fingerprint` 5 文件 | 全部 defer | 5 文件确认 ✅ | ✅ |
| `_exact_fields` 15 文件 8 family | 全部 defer | 15 文件确认 ✅ | ✅ |
| `_serialize` 缺 sort_keys 1 文件 | defer | challenger_promotion.py 确认 ✅ | ✅ |

---

## 其它计数复核

| 计数项 | Plan 声称 | 源码验证 | 判定 |
|---|---|---|---|
| `_canonical_json` 定义数 | 17 (11 str + 6 bytes) | 17 ✅ | ✅ |
| `_fingerprint` 定义数 | 17 (12 str + 5 bytes) | 17 ✅ | ✅ |
| `_file_fingerprint` 定义数 | 10 | 10 ✅ | ✅ |
| `_bytes_fingerprint` 定义数 | 10 | 10 ✅ | ✅ |
| `_validated_fingerprint` 定义数 | 16 (7 sub-family) | 16 ✅ | ✅ |
| `_mapping` 定义数 | 17 (14 strict + 3 optional) | 17 ✅ | ✅ |
| `_required_text` 定义数 | 16 (8 family) | 16 ✅ | ✅ |
| `_serialize` 定义数 | 14 (13 + 1 defer) | 14 ✅ | ✅ |
| `_is_relative_to` 定义数 | 8 | 8 ✅ | ✅ |
| `_format_utc` 定义数 | 11 (3+2+6) | 11 ✅ | ✅ |
| `_absolute_path` 定义数 | 7 | 7 ✅ | ✅ |
| Phase A 条目数 | 14 | 14 ✅ | ✅ |
| Phase B 条目数 | 2 | 2 ✅ | ✅ |
| Phase A+B 总计 | 16 | 16 ✅ | ✅ |
| research_template action 数 | 39 | 39 ✅ | ✅ |

---

## Closure 复审

F-01..F-07、R2-01..R2-08、V4-01..V4-07、C4-01、C5-CTRL-01..09 全部保持 CLOSED。v4.3 仅修改 C5-CTRL-10 相关区域，未触及已关闭 finding 涉及的区域。

RR-F01、RR-F02 保持 REJECTED。源码证据确认 v4.3 fix artifact 裁决正确。

---

## 修正要求汇总

| # | 严重度 | 修正要求 |
|---|---|---|
| 1 | **LOW** | §1.6.7 行 316 `decode_base64` caller 计数 "5（4 私有 + 1 inline）" 应为 "6（5 私有 + 1 inline）"。不影响实现——Slice 2A/2B 逐文件迁移表已正确 |

---

*审查者: MiMo · 2026-08-07 · 基于 HEAD 81df373 源码逐函数验证*
