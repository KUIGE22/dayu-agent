# Plan C5 逐函数源码审计报告

- **日期**: 2026-08-07
- **审计者**: AgentDS (DeepSeek)
- **审计范围**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.0 §1.6 C5 全部 20 个 helper 及未点名项
- **审计方法**: 逐函数源码全文搜索，每文件读取完整函数体
- **基线 HEAD**: 5821014

---

## 0. 总体结论

**计划 v4.0 在 C5 helper 函数清单、行为 spec、family 划分上存在 7 处实质性缺陷，需修正为 v4.1。**

核心问题：
1. 函数数量被低估（实际重复定义远多于 20 个可共享签名）
2. 多个函数的 proposed signature 与现有行为不等价
3. 将语义异构的函数强行归入统一 helper
4. 遗漏了关键的 sub-family 差异（错误文本、验证策略、原子语义）

---

## 1. format_utc —— 三族，非一族

### 源码证据

| 族 | timespec | astimezone | 文件数 | 示例文件 |
|---|---|---|---|---|
| **A: microseconds** | `isoformat(timespec="microseconds")` | `value.astimezone(UTC)` | 4 (含 public) | `_write_artifact_utils.py:333`, `write_model_configuration_application.py:255`, `write_model_configuration_rollback_application.py:380`, `write_model_configuration_manual_recovery.py:342` |
| **B: auto** | `isoformat()` 无 timespec 参数 | `value.astimezone(UTC)` | 6 | `write_model_configuration_change.py:298`, `write_model_configuration_rollback.py:355`, `write_model_challenger_run_approval.py:255`, `write_model_challenger_preflight_approval.py:165`, `write_model_configuration_manual_recovery_gate_revalidation.py:146`, `write_model_configuration_manual_recovery_incident_dossier_revalidation.py:198` |
| **C: seconds** | `isoformat(timespec="seconds")` | `_normalize_now(value)` 内部 astimezone | 2 | `write_model_configuration_manual_recovery_application.py:309`, `write_model_configuration_manual_recovery_clearance.py:461` |

### 计划缺陷

计划 §1.6.4 仅列出一个 `format_utc(value: datetime) -> str` 签名，spec 写 `value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`。实际 HEAD 源码**无一使用 `strftime`**，全部使用 `isoformat(timespec=...) + .replace("+00:00", "Z")`，且 timespec 分三族。

### 纠偏决策

- **不可统一**。三族 timespec 语义不等价：`auto` 省略尾零（`2026-08-07T12:30:45Z` vs `microseconds` 的 `2026-08-07T12:30:45.000000Z`），`seconds` 截断微秒。
- 拆为三个精确函数：
  - `format_utc(value: datetime) -> str` — microseconds 族（4 文件），作为默认
  - `format_utc_seconds(value: datetime) -> str` — seconds 族（2 文件）
  - **不抽取 auto 族**：6 文件使用的 `isoformat()` auto timespec 行为依赖 Python 版本语义，抽取风险高，保留原位
- **更新计划**: §1.6.4 行 210 `format_utc` → 拆为 `format_utc` (microseconds, 4 files) + `format_utc_seconds` (seconds, 2 files)；auto 族 6 文件 defer

---

## 2. is_relative_to —— 两族，resolve vs try/except

### 源码证据

| 族 | 实现 | 解析符号链接 | 文件数 |
|---|---|---|---|
| **A: resolve** | `path.resolve().is_relative_to(root.resolve())` | 是 | 1 (public) + 1 内联 (`write.py:2290`) |
| **B: try/except** | `try: path.relative_to(root) except ValueError: return False; return True` | **否** — 不 resolve | 8 |

族 B 的 8 个文件（全部 `write_model_configuration_*.py`）使用 `path.relative_to(root)` 的 try/except 模式，**不解析符号链接**。这与族 A 行为不等价。

### 计划缺陷

计划 §1.6.4 行 211 签名为 `path.resolve().is_relative_to(root.resolve())`，只描述族 A。8 个族 B 实现被错误归类为等价。

### 纠偏决策

- 拆为两个函数：
  - `is_relative_to(path: Path, root: Path) -> bool` — resolve 族（public existing）
  - `is_subpath(path: Path, root: Path) -> bool` — 不 resolve 的 try/except 族（8 文件）
- **更新计划**: §1.6.4 新增 `is_subpath` 条目

---

## 3. absolute_path —— 依赖两族 _required_text，非一族

### 源码证据

`_absolute_path` 的核心逻辑是 `_required_text(...) → Path(text).expanduser() → is_absolute() → resolve()`。但依赖的 `_required_text` 分属两个不同家族：

| 族 | _required_text 特征 | max_length | 文件数 | 示例文件 |
|---|---|---|---|---|
| **A: NFKC + ord<32** | NFKC 归一化 + ord<32 控制字符检查 + 静默 strip | 32_768 | 5 | `write_model_configuration_application.py`, `write_model_configuration_rollback.py`, `write_model_configuration_rollback_application.py`, `write_model_configuration_manual_recovery.py`, `write_model_configuration_manual_recovery_application.py`（后者缺控制字符检查） |
| **B: NO NFKC + cat C** | 无 NFKC + Unicode category "C" 控制字符 + 拒绝首尾空格 | 4_096 | 2 | `write_model_configuration_change.py`, `write_model_configuration_preapplication.py` |

外加：
- `write_model_challenger_run_approval.py` 的 `_validated_absolute_path` — **不调 expanduser**，错误文本不同（"must be an absolute path" vs "must be absolute"）
- public `absolute_path` — 内联校验，无 max_length、无控制字符检查、无 NFKC

### 计划缺陷

计划 §1.6.4 行 212 将 `absolute_path` 描述为单一签名，spec 写"非目录校验 `ValueError`"。实际：
1. 校验是 `is_absolute()` 非 `is_dir()`
2. 依赖两族不同 `_required_text`，行为不等价
3. `_validated_absolute_path` 不调 `expanduser()`

### 纠偏决策

- `absolute_path` 保留为 public 函数，但**内部 _required_text 检查不可统一**——两族调用者各自使用自己的 `_required_text` 变体
- `absolute_path` 本身的 `Path(text).expanduser() → is_absolute() → resolve()` 逻辑统一
- `_validated_absolute_path` 单独处理（不 expanduser，不同错误文本），不纳入统一 helper
- **更新计划**: 明确 `absolute_path` 调用者需各自处理 text validation，仅共享 Path 构造+校验逻辑

---

## 4. snapshot_fingerprint —— 含业务 validator，零依赖签名无法等价替代

### 源码证据

5 个私有 `_snapshot_fingerprint` 实现**完全相同的结构**：

```python
def _snapshot_fingerprint(snapshot: Mapping[str, Any], *, name: str) -> str:
    validate_write_scene_model_routing_snapshot(snapshot)  # ← 业务 validator
    return _validated_fingerprint(
        snapshot.get("snapshot_fingerprint"),
        name=f"{name}.snapshot_fingerprint",
    )
```

文件：`write_model_configuration_application.py:450`, `write_model_configuration_rollback.py:427`, `write_model_configuration_manual_recovery_application.py:494`, `write_model_configuration_manual_recovery_verification.py:868`, `write_model_configuration_rollback_application.py:752`

Public `snapshot_fingerprint` (`_write_artifact_utils.py:160`) **不含**业务 validator。

### 计划缺陷

计划 §1.6.4 行 213 列出的 `snapshot_fingerprint(snapshot: JsonObject, *, name: str) -> str` 签名不含 validator 参数，无法等价替代含 validator 的 5 个私有实现。

### 纠偏决策

- 该函数迁移时需传入 validator callable：`snapshot_fingerprint(snapshot: JsonObject, *, name: str, validate: Callable[[JsonObject], None] | None = None) -> str`
- 或拆为两个：`snapshot_fingerprint`（无 validator）和 `validated_snapshot_fingerprint`（含 validator）
- **更新计划**: §1.6.4 `snapshot_fingerprint` 签名追加 `validate` 参数

---

## 5. transaction_id —— 语义/签名完全不同，非一族

### 源码证据

| # | 函数 | 语义 | 输入 | 输出格式 | 文件 |
|---|---|---|---|---|---|
| 1 | `transaction_id` (public) | 生成带前缀+时间戳+指纹的 ID | `prefix, payload, now` | `{prefix}-{now:%Y%m%dT%H%M%S}-{digest[:12]}` | `_write_artifact_utils.py:539` |
| 2-5 | `_transaction_id` (4 private) | 纯 SHA-256 哈希 | `approval_fingerprint, plan_fingerprint` | 64-char hex（无前缀，无时间戳） | `configuration_application.py:868`, `manual_recovery_application.py:943`, `manual_recovery_verification.py:479`, `rollback_application.py:1204` |
| 6 | `_transaction_id` (1 private) | 输入校验/消毒 | `value: object` | 校验后的原始字符串 | `manual_recovery_incident_dossier.py:113` |

族 2 内部又有差异：null-byte 分隔 vs 换行分隔 vs domain tag 前缀。

### 计划缺陷

计划 §1.6.4 行 214 将所有 5 个实现归入同一个 `transaction_id(*, prefix, payload, now)` 签名。4 个族 2 实现**不接受 prefix/payload/now**，语义完全不同。

### 纠偏决策

- **完全 defer**。`transaction_id` 的 5 个"实现"不是同一函数的变体，而是三个完全不同语义的函数。不能用一个统一 helper 替换。
- Public `transaction_id` 保留为共享工具，族 2 的 4 个 `_transaction_id` 保留原位不改。
- 族 3（校验函数）同样保留原位。
- **更新计划**: §1.6.6 将 `transaction_id` 从 Group A 移至 Group C（不可安全抽取），仅 public 版本保留在 `_write_artifact_utils.py`

---

## 6. decode_base64 —— 标准 b64decode(validate=True)，非 urlsafe，两错误文本族

### 源码证据

| 族 | 解码器 | validate | 错误文本 | 捕获异常 | 文件数 |
|---|---|---|---|---|---|
| **A: "is invalid"** | `base64.b64decode` | `True` | `"{name} is invalid"` | `binascii.Error, TypeError, ValueError` | 5 (含 public) |
| **B: "must be valid base64"** | `base64.b64decode` | `True` | `"{name} must be valid base64"` | `binascii.Error, ValueError`（缺 TypeError） | 1 |

全部 6 个私有实现（含 1 个内联）使用 **`base64.b64decode(text, validate=True)`**，无一使用 `urlsafe_b64decode`。

### 计划缺陷

计划 §1.6.4 行 215 签名写 `urlsafe: bool = True`（默认 url-safe），spec 写 `base64.urlsafe_b64decode`。实际 HEAD 源码**全部使用标准 `b64decode`**，无 urlsafe 用例。

### 纠偏决策

- Public `decode_base64` 签名改为 `urlsafe: bool = False`（默认标准 b64decode），匹配现有 6 个调用者行为
- 族 B（`manual_recovery.py`）的 `"must be valid base64"` 错误文本通过 `error_label` 参数支持
- 族 B 缺 `TypeError` 捕获——这是一个**行为缺陷**，在迁移时统一补上（安全变更）
- **更新计划**: §1.6.4 `decode_base64` 签名修正为默认 `urlsafe=False`

---

## 7. require_text —— **8 族异构，不可统一**

### 源码证据

17 个 `_required_text` 定义分属 8 个行为家族：

| 族 | NFKC | 控制字符检查 | 空白处理 | max_length | 文件数 |
|---|---|---|---|---|---|
| 1 | 是 | ord<32 | 静默 strip | 必需参数 | 7 |
| 2 | 是 | **无** | 静默 strip | 必需参数 | 2 |
| 3 | 否 | cat("C") | **拒绝** | 默认 4096 | 2 |
| 4 | 否 | cat("C") | **拒绝** | 必需参数 | 2 |
| 5 | 否 | **无** | **拒绝** | 默认 4096 | 1 |
| 6 | 否 | ord<32 | 静默 strip | 必需参数 | 1 |
| 7 | 否 | **无** | 静默 strip | 必需参数 | 1 |
| 8 | 否 | **无** | 静默 strip | **无参数** | 1 |

错误文本也不统一：`"must not be empty"` vs `"is required"` vs `"is empty"`。

### 计划缺陷

计划 §1.6.4 行 243 列出的 `require_text` 单一签名无法等价替换 8 族异构实现。若强制统一，必改变现有行为或错误文本。

### 纠偏决策

- **不统一**。`require_text` 的各异构变体保留在原文件内，不作为 `_write_artifact_utils.py` 的共享函数
- `_write_artifact_utils.py` 的 `require_text` 仅代表族 1 行为（NFKC + ord<32 + 必需 max_length）
- 族 3/4 等使用不同校验策略的调用者**不迁移**
- **更新计划**: §1.6.6 将 `require_text` 异构体从 Group A 移至 Group D（异构变体，不统一），仅族 1 的 7 文件可迁移

---

## 8. persist_immutable —— os.link vs os.replace，两类原子语义

### 源码证据

| 族 | 原子方法 | 符号链接检查 | Path 解析 | 序列化时机 | 文件数 |
|---|---|---|---|---|---|
| **1: hard-link + symlink guard** | `os.link` | 是 (3x) | `resolve()` | 混合 | 4 |
| **2: hard-link, no guard** | `os.link` | 否 | `resolve()` | 预计算 | 5 |
| **3: hard-link, raw Path** | `os.link` | 否 | 调用者预解析 | 预计算 | 2 |
| **4: absolute + symlink guard** | `os.link` | 是 (3x) | `absolute()` | 内联 | 2 |
| **5: public atomic** | `os.replace` | 是 (1x) | `expanduser()`+symlink check+`resolve()` | 预计算(可配置) | 1 |

关键差异：
1. 族 1-4 使用 `os.link`（同一文件系统内的硬链接，天然 no-clobber——目标存在时 `FileExistsError`）
2. 族 5（public）使用 `os.replace`（原子 rename，可覆盖）
3. 族 1/4 内部在 FileExistsError catch 和 link 之后重检符号链接
4. 族 4 使用 `absolute()` 非 `resolve()`，并额外捕获 `UnicodeError`

### 计划缺陷

计划 §1.6.5 行 222 的 `persist_immutable_atomic` 使用 `os.replace` + `overwrite` 参数。此行为**与现有的 13 个 `_persist_immutable`（全部使用 `os.link`）不等价**：
- `os.link` 目标存在 → `FileExistsError`（内核保证，无 TOCTOU race）
- `os.replace` + 预检查 → 存在 TOCTOU race 窗口

### 纠偏决策

- **保守方案**：`_write_artifact_utils.py` 的 `persist_immutable_atomic` 使用 `os.link` 而非 `os.replace`，匹配现有 13 个实现的行为
- `overwrite` 参数保留，但 overwrite=True 时使用 `os.replace`（仅此路径非等价）
- 符号链接检查纳入函数内部，提供 `check_symlinks: bool = True` 参数
- **更新计划**: §1.6.5 `persist_immutable_atomic` 默认行为改为 `os.link`，`overwrite=True` 时使用 `os.replace`

---

## 9. serialize_pretty —— sort_keys=True 是主流，有一处遗漏

### 源码证据

- 13 个 `_serialize` 含 `sort_keys=True`（族 D）
- **1 个遗漏**: `write_model_challenger_promotion.py:804` 的 `_serialize` 缺 `sort_keys=True`
- Public `serialize_pretty` 含 `sort_keys=True`

### 纠偏决策

- `serialize_pretty` 签名保持 `sort_keys=True`，匹配 13/14 的行为
- `write_model_challenger_promotion.py:804` 的遗漏在迁移时修正（属于 bug fix）
- **更新计划**: 注明此修正

---

## 10. validated_fingerprint —— 6 sub-family，error_label 可覆盖但结构性差异需注意

### 源码证据

16 个 `_validated_fingerprint` 定义分属 6 个 sub-family：

| 子族 | 输入预处理 | max_length | 错误文本 | lower() | 文件数 |
|---|---|---|---|---|---|
| A | `str(value or "").strip()` | 无 | `"must be a sha256 fingerprint"` | 是 | 6 |
| B | `_required_text(value, maximum_length=80)` | 80 | `"must be a sha256 fingerprint"` | 是 | 5 |
| C | `_required_text(value, maximum_length=80)` | 80 | `"must use sha256"` / `"is invalid"` | **否** | 1 |
| D | `_required_text(value, maximum_length=128)` | 128 | `"must be a SHA-256 fingerprint"` | 否 | 1 |
| E | `_required_text(value, maximum_length=80)` | 80 | `"is not a SHA-256 fingerprint"` | 是 | 1 |
| F | `_required_text` + regex | 71 | `"is not a SHA-256 fingerprint"` | 否 | 1 |
| G | `str(value or "")` | 无 | `"must be a sha256 fingerprint"` | 是 | 1 |

### 纠偏决策

- Public `validated_fingerprint` 的 `error_label` 参数（计划已有）可覆盖主要错误文本差异
- 但 `_required_text`-based 族（B-F）与 `str(value or "")` 族（A, G）的结构性差异（max_length 检查、NFKC、控制字符）**无法用一个参数统一**
- 建议：`validated_fingerprint` 提供两个入口——`validated_fingerprint`（简单 str 校验，替代族 A/G）和 `validated_fingerprint_text`（经 `_required_text` 预处理，替代族 B-F）
- 或保持 `error_label` 参数，调用者自行在外部做 `_required_text` 预处理
- **更新计划**: §1.6.4 `validated_fingerprint` 明确仅替代族 A/G（7 文件），族 B-F（9 文件）各自在调用前做 `_required_text` 预处理

---

## 11. canonical/fingerprint/mapping/exact_fields —— 未点名项的核实

### canonical_json

- 3 族（str→bytes 6 文件，str→str 10 文件，str→str+dict 1 文件）
- Public `canonical_json_str` + `canonical_json_bytes` 可覆盖全部 17 个定义
- **计划已有，无需修正**

### fingerprint_str / fingerprint_bytes

- `fingerprint_str` 可替代族 1A（9 文件），`fingerprint_bytes` 可替代族 1B（8 文件）
- **计划已有，无需修正**

### file_fingerprint

- 10 个 `_file_fingerprint` 分 3 种循环写法 + 1 个 `_if_present` 变体
- 语义全等（1MB 块读取 + SHA-256）
- Public `file_fingerprint` 可替代全部 10 个
- `_file_fingerprint_if_present` 是语义变体（文件不存在返回 None），单独保留
- **计划已有，无需修正**

### bytes_fingerprint

- 10 个 `_bytes_fingerprint` 定义完全等价
- Public `bytes_fingerprint` 可替代全部 10 个
- **计划已有，无需修正**

### mapping

- 族 5A（14 文件，严格版）→ `require_mapping`
- 族 5B（3 文件，静默版）→ `optional_mapping`
- **计划已有，无需修正**

### exact_fields

- 族 6A `_validate_exact_fields`（5 文件，逗号+unexpected）
- 族 6B `_exact_fields`（6 文件，分号+extra）
- 族 6B' `_exact_fields` 一行版（1 文件，冒号+extra）
- 族 6B'' `_exact_fields` 一行版（1 文件，分号+extra）
- 族 6C `_exact_fields` frozenset 版（2 文件，分号+unexpected）
- **合计 15 文件，3 命名 + 4 错误格式 = 8 个 exact family**
- **Controller ruling**: 禁止用 extra_label/sep 参数爆炸声称覆盖 8 个 family。**全部 defer**，不在本 plan 的 `_write_artifact_utils.py` 中提供 `require_exact_fields`
- **更新计划**: §1.6.3 逐族列出，§1.6.7 删除此函数

---

## 12. 修正后的最终 shared/deferred 函数清单（v4.1 / Controller Rulings 已应用）

### Shared（纳入 `_write_artifact_utils.py`，17 函数，每函数有 Slice 2 caller）

| # | 函数 | 替代文件数 | 备注 |
|---|---|---|---|
| 1 | `canonical_json_str` | 10 | Category B + C |
| 2 | `canonical_json_bytes` | 6 | Category A |
| 3 | `fingerprint_str` | 9 | 子族 1A |
| 4 | `fingerprint_bytes` | 8 | 子族 1B |
| 5 | `file_fingerprint` | 10 | 3 种循环写法等价 |
| 6 | `bytes_fingerprint` | 10 | 完全等价 |
| 7 | `validated_fingerprint` | 7 | 族 A+G（`str(value or "").strip()` 策略），`error_label` 参数覆盖族 A/B 错误文本差异 |
| 8 | `require_mapping` | 14 | 族 5A 严格版 |
| 9 | `optional_mapping` | 3 | 族 5B 静默版（含 `write_run_comparison.py:19`） |
| 10 | `require_text` | 7 | 仅族 1（NFKC+ord<32+必需max_length）。精确族映射：`configuration_application.py:204`, `configuration_rollback.py:246`, `rollback_application.py:310`, `manual_recovery.py:283`, `manual_recovery_clearance.py:414`, `incident_dossier.py:95` + public |
| 11 | `format_utc` | 4 | microseconds 族：`configuration_application.py`, `rollback_application.py`, `manual_recovery.py` + public |
| 12 | `format_utc_seconds` | 2 | seconds 族：`manual_recovery_application.py:309`, `manual_recovery_clearance.py:461` |
| 13 | `is_subpath` | 8 | `try: path.relative_to(root) except ValueError: return False; return True`。不 resolve。Controller ruling: 8 个现有实现全为此模式，无 resolve caller |
| 14 | `absolute_path` | 7 | Path 构造+`is_absolute()` 共享。text 校验由调用方各自的 `_required_text` 处理 |
| 15 | `serialize_pretty` | 13 | `sort_keys=True, indent=2 + "\n"`。不含缺 sort_keys 的 1 文件（controller: 行为保持优先） |
| 16 | `decode_base64` | 5 + 1 内联 | 族 A：标准 `b64decode(validate=True)`，`"is invalid"`。无 urlsafe 模式（controller: 零 caller） |
| 17 | `decode_base64_strict` | 1 | 族 B：标准 `b64decode(validate=True)`，`"must be valid base64"`，缺 TypeError 捕获。行为保持——不补 TypeError、不改为族 A 错误文本 |

**合计: 17 个 shared 函数**（计划 v4.0 原列 20 个）

### Deferred（不迁移，保留原位）

| 函数 | 文件数 | 原因 |
|---|---|---|
| `_format_utc` auto 族 | 6 | `isoformat()` 无 timespec，依赖 Python 版本 auto 语义，不等价 |
| `_transaction_id` 族 2（4 个）+ 族 3（1 个） | 5 | 语义/签名与 public `transaction_id` 完全不同，不可用一个签名替换 |
| `_snapshot_fingerprint` 含 validator | 5 | 依赖业务 validator `validate_write_scene_model_routing_snapshot`，注入 `Callable[[JsonObject], None]` 需精确类型+pyright 可行性验证（controller: 证据不足则 defer） |
| `_exact_fields` / `_validate_exact_fields` | 15 | 3 命名+4 错误格式=8 exact family，参数爆炸（controller: 禁止 extra_label/sep 参数爆炸声称覆盖） |
| `_persist_immutable` | 13 | 5 family（os.link/os.replace、symlink guard 有无、absolute vs resolve、UnicodeError 捕获），需 4+ flags——参数爆炸（controller: defer） |
| `_serialize` 缺 sort_keys | 1 | `write_model_challenger_promotion.py:804`。Controller: 行为保持优先，不顺手修复 |
| `serialize_compact` | 0 | 无现有等价 caller，net-new helper 不属 C5 scope（controller: 禁止为凑数新增未使用 helper） |
| `is_relative_to` resolve 版 | 0（仅 public 自身） | 无 eligible private caller——8 个现有实现全部是 try/except 非 resolve 模式（controller: 删除无 caller 项） |
| `_decode_base64` 族 B | — | Controller: 行为保持，拆为独立 `decode_base64_strict`，不合并到族 A |
| `_validated_absolute_path` | 1 | `challenger_run_approval.py:375`，不 expanduser，错误文本不同 |
| `_file_fingerprint_if_present` | 1 | 语义变体（文件不存在返回 None），不是单纯重复 |
| `_normalize_now` 三变体 | 11 | Group D，语义意图不同 |
| `_parse_utc` 两变体 | 8 | Group D，offset 处理不等价 |
| `_validate_source` | 8 | Group C，业务 schema 差异 |
| `_load_json_object` | 10 | Group C，异常消息与业务上下文强绑定 |
| `_source_reference` | 7 | Group C，与 `_validate_source` 耦合 |
| `_required_text` 族 2-8 | 10 | 7 种不同校验完整性（NFKC/控制字符/空白处理/max_length 各有差异），不可统一 |

---

## 13. 残余风险（v4.1 / Controller Rulings 已应用）

| 风险 | 严重度 | Controller Ruling | 说明 |
|---|---|---|---|
| `require_text` 8 族异构 | HIGH | 仅族 1 迁移（7 文件），族 2-8 defer | 17 个定义有 8 种不同行为。族 1 精确映射至 7 个文件（§12）。其余 10 文件保留私有 `_required_text` |
| `exact_fields` 8 exact family | HIGH | **全部 defer** | 15 文件，3 命名+4 错误格式。参数爆炸，后续独立 plan 治理 |
| `persist_immutable` 5 family 参数爆炸 | HIGH | **全部 defer** | 13 文件，os.link/os.replace、symlink guard、absolute/resolve、UnicodeError 差异。需 4+ flags |
| `snapshot_fingerprint` validator 注入 | MEDIUM | **全部 defer** | 5 文件含业务 validator。`Callable[[JsonObject], None]` 注入需精确类型+pyright 可行性验证，证据不足 |
| `transaction_id` 语义异构 | MEDIUM | 族 2/3 defer | 5 个实现分属三个完全不同语义的函数，部分已是正确形态（domain-tagged hash），不应统一 |
| `format_utc` auto 族 defer | LOW | 6 文件 defer | `isoformat()` 无 timespec，依赖 Python 版本语义 |
| `_serialize` 缺 sort_keys | LOW | 行为保持，不修复 | `write_model_challenger_promotion.py:804`，不迁移到 `serialize_pretty` |
| `decode_base64` 族 B 缺 TypeError | LOW | 行为保持，独立函数 | `manual_recovery.py:385`，拆为 `decode_base64_strict`，不改变异常捕获 |
| `absolute_path` 两族 _required_text | LOW | text 校验在调用方 | 族 A（NFKC+ord<32）和族 B（无NFKC+catC）的校验由各自 `_required_text` 处理 |
| `validated_fingerprint` 族 B-F 预处理 | LOW | 调用方先 `_required_text` 再传入 | 族 B-F（9 文件）需 `_required_text` 预处理，不可直接用 shared `validated_fingerprint` |

---

*审计者: AgentDS (DeepSeek) · 2026-08-07 · 基于 HEAD 5821014 源码逐函数全文审计*
