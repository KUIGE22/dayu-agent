# Plan C5 v4.2 Fix Artifact: CLI Write 架构重构

- **日期**: 2026-08-07（含 follow-up 修正）
- **修复者**: AgentDS (DeepSeek)
- **输入源**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.1、`docs/reviews/plan-c5-source-audit-20260807-deepseek.md`、`docs/reviews/plan-c5-v4.1-review-20260807-mimo.md`、Controller 机械验收 follow-up（18 项）
- **基线 HEAD**: `81df373`
- **分支**: `codex/dual-model-research-mvp`
- **状态**: **STOP** — plan v4.2 与 fix artifact 已完成，停止，不进入 re-review

---

## 0. 修复范围

仅修改 `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（plan v4.2）并新建本 fix artifact `docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md`。

**受保护文件（只读，未修改）**:
- `docs/reviews/plan-c5-source-audit-20260807-deepseek.md`
- `docs/reviews/plan-c5-v4.1-review-20260807-mimo.md`
- `dayu/services/_write_artifact_utils.py`
- `tests/application/test_write_artifact_utils.py`
- `tests/README.md`
- 所有 `dayu/services/write_model_*.py`
- 所有其它源码与测试文件

---

## 1. Controller Rulings 汇总

### 1.1 MiMo SA-REVIEW Findings 裁决

| Finding | 严重度 | 裁决 | 理由 |
|---|---|---|---|
| SA-REVIEW-01 | HIGH→**MEDIUM** | **ACCEPTED** | `_write_artifact_utils.py` 不在 HEAD，是当前 worktree 的未跟踪旧草稿。Slice 1 必须明确替换该草稿（若不存在则创建），删除所有 v4.1 defer/零 caller 函数并新增目标函数，不保留兼容 wrapper |
| SA-REVIEW-02 | MEDIUM | **REJECTED** | v4.1 §1.6.4 已明确删除 resolve 版并实现不 resolve 的 `is_subpath`；在 SA-REVIEW-01 的 Slice 1 逐函数替换清单中再次写清 |
| SA-REVIEW-03 | MEDIUM | **REJECTED** | v4.1 已给出无 `urlsafe` 参数的精确签名和标准 `b64decode` 行为；旧草稿不是 plan 证据。但在 Slice 1 替换清单中明确删除 `urlsafe` 分支 |
| SA-REVIEW-04 | MEDIUM | **ACCEPTED**（部分） | 仅接受 `format_utc_seconds` 的完整规范缺口；`decode_base64_strict` 在 §1.6.4 已有完整错误文本与异常集合。`format_utc_seconds` 必须显式先检查 timezone-aware，naive 时抛 `ValueError("now must include a timezone")`，再 `astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")`；不依赖 Group D `_normalize_now` |
| SA-REVIEW-05 | LOW | **REJECTED** | 行为表和最终清单相邻且函数名可直接关联，无需增加脆弱行号交叉引用列 |
| SA-REVIEW-06 | LOW | **ACCEPTED** | 并扩展为所有 auto 族迁移表行 |
| SA-REVIEW-07 | LOW | **ACCEPTED** | 并扩展为所有 auto 族迁移表行 |
| SA-REVIEW-08 | LOW | **ACCEPTED** | 私有 eligible caller 实际为 6，不得把未跟踪 public helper 算作 caller；`rollback_application` 的 `_required_text` 行号改为 246 |

### 1.2 Controller 新增 Findings

| Finding | 严重度 | 裁决 |
|---|---|---|
| C5-CTRL-01 | **HIGH** | validated_fingerprint 族 B-F 不得经各自 `_required_text` 后再调用 shared。族 C/D/F 不 lower，族 C 有两种错误文本，族 D/F 校验算法也不同；shared 会强制 lower 且只有一个 error_label。仅族 A/G 7 个私有 caller 迁移，族 B-F 9 个全部保留私有 `_validated_fingerprint` 与 `_required_text`。更新 §1.6.2、最终清单、Slice 1 测试、Slice 2 每行映射、迁移规则和 checklist |
| C5-CTRL-02 | **HIGH** | `absolute_path` 既然必须保留调用方各族文本预处理，签名必须是 `absolute_path(text: str, *, name: str) -> Path`；先 `Path(text).expanduser()`，在 resolve 前检查 `is_absolute`，否则 raise，再 `return path.resolve()`。不得接受原始 `ModelConfigJsonValue` 后偷偷选某一 `require_text` 族 |
| C5-CTRL-03 | **HIGH** | `decode_base64` 与 `decode_base64_strict` 同理改为 `text: str` 入参；各 caller 先用原有或迁移后的精确 `require_text` 族得到 text，再调用 shared codec。shared 只负责标准 `b64decode(validate=True)` 和各自异常/错误文本。inline preapplication 路径也保持族 3 预处理 |
| C5-CTRL-04 | **HIGH** | 重新逐文件核对 canonical/fingerprint 映射。`incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation` 的 `_fingerprint` 都是 canonical str + UTF-8，应映射 `fingerprint_str`，不是 `fingerprint_bytes`；其独立 `_bytes_fingerprint` 才映射 `bytes_fingerprint`。对 19 行全部重新验证 |
| C5-CTRL-05 | **HIGH** | 私有 `_format_utc` 定义实际为 microseconds 3 个、seconds 2 个、auto 6 个。不要把未跟踪 public helper 计入 caller。6 个 auto 文件为 `configuration_change`、`challenger_run_approval`、`challenger_preflight_approval`、`configuration_rollback`、`manual_recovery_gate_revalidation`、`manual_recovery_incident_dossier_revalidation`，全部 defer |
| C5-CTRL-06 | **MEDIUM** | 删除自相矛盾的"仅 public transaction_id 保留"说法；HEAD 无该 public helper，最终 17 清单也不含它。旧草稿 `transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、`persist_immutable_atomic`、`serialize_compact`、resolve `is_relative_to` 全部删除 |
| C5-CTRL-07 | **MEDIUM** | Slice 1 不得只测试新 helper 自洽。加入对 eligible 私有实现的差分 characterization / 固定反例 corpus，覆盖大小写 fingerprint、错误文本、naive datetime、relative path、symlink 非 resolve、各 required_text 家族、standard vs urlsafe Base64；说明 Slice 2 删除私有函数后测试如何迁移为 public/module-level regression。零 `type:ignore` / `Any` / `object` / `cast` 逃逸 |
| C5-CTRL-08 | **MEDIUM** | 原 Slice 2 一次迁移 19 文件过粗。重构为至少 2A/2B 两个可独立实现、测试、review、accepted commit 的小 slice；每个写清 allowed files、helper families、前置依赖、禁止提前修改另一 slice、独立绿信号。后续 slice 编号保留 3 起，不让依赖图/总数/checklist 失配 |
| C5-CTRL-09 | **LOW** | 清理全文残留"C5 20 helper"、旧 HEAD 5821014 与 v4.1 accepted 语句；头部更新 HEAD 81df373、v4.2 DRAFT / PENDING MIMO RE-REVIEW、完整 changelog 与本轮 review 引用 |

---

## 2. 逐 Finding 修复状态

### 2.1 SA-REVIEW-01 [ACCEPTED] — `_write_artifact_utils.py` 草稿替换

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §5 Slice 1 标题从"新建"改为"重构/替换"，明确列出需从旧草稿删除的函数和需保留/新增的函数
- §5 Slice 1 逐函数删除清单：`is_relative_to`（resolve 版）、`decode_base64`（urlsafe 分支）、`persist_immutable_atomic`、`transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、`serialize_compact`
- §5 Slice 1 逐函数新增清单：`is_subpath`（try/except 非 resolve）、`decode_base64_strict`、`format_utc_seconds`
- §5 Slice 1 逐函数保留+修正清单：`decode_base64`（删除 urlsafe 参数、改为 `text: str` 入参）、`absolute_path`（改为 `text: str` 入参）、`format_utc`（microseconds 族，caller 数 3）
- 新增 §5 Slice 1 迁移前自检 checklist：确认旧草稿 20 函数中哪些删、哪些改、哪些保留

### 2.2 SA-REVIEW-04 [ACCEPTED 部分] — `format_utc_seconds` spec 补全

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §1.6.4 `format_utc_seconds` 行为 spec 完整化：
  - 先检查 `value.tzinfo is None or value.utcoffset() is None`，naive 则 `raise ValueError("now must include a timezone")`
  - `value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")`
  - 明确不调用 `_normalize_now`，不依赖 Group D
- §5 Slice 1 `format_utc_seconds` 实现 spec 同步更新

### 2.3 SA-REVIEW-06/07 [ACCEPTED 扩展] — auto 族迁移表行

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- Slice 2A/2B 迁移表中所有 auto 族 `_format_utc` 标注为"defer（auto 族）"，不迁移为 `format_utc`
- 受影响文件（6 个）全部标注 defer：`configuration_change`、`challenger_run_approval`、`challenger_preflight_approval`、`configuration_rollback`、`manual_recovery_gate_revalidation`、`manual_recovery_incident_dossier_revalidation`

### 2.4 SA-REVIEW-08 [ACCEPTED] — require_text caller 计数与行号

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §1.6.3 族 1：私有 eligible caller 数从 7 改为 6（不计算未跟踪 public helper）
- `rollback_application` 的 `_required_text` 行号修正为 246
- §1.6.7 `require_text` caller 文件数从 7 改为 6

### 2.5 C5-CTRL-01 [HIGH] — validated_fingerprint B-F 不可迁移

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §1.6.2：删除"族 B-F 各自在调用前经私有 `_required_text` 预处理后传入 shared"的说法，改为"族 B-F 9 个文件全部保留私有 `_validated_fingerprint` 与 `_required_text`，不得调用 shared"
- §1.6.7 `validated_fingerprint` caller 数确认为 7（族 A:6 + 族 G:1）
- Slice 2A/2B 迁移表：B-F 文件的 `_validated_fingerprint` 从"替换为 shared"移至"保留原位/defer"列
- 迁移规则更新：仅族 A/G 可迁移，族 B-F 禁止迁移

**源码证据**（HEAD 81df373）:
- 族 A（6 文件，`str(value or "").strip().lower()`）: `configuration_change.py:187`, `configuration_rollback.py:310`, `configuration_preapplication.py:201`, `challenger_run_approval.py:167`, `challenger_preflight_approval.py:99`, `challenger_promotion.py:115`
- 族 G（1 文件，`str(value or "").strip().lower()`，`value: str`）: `challenger_proposal.py:68`
- 族 B（5 文件，`_required_text(max_len=80).lower()`）: `manual_recovery_application.py:339`, `manual_recovery_clearance.py:432`, `manual_recovery_incident_dossier.py:145`, `incident_dossier_revalidation.py:202`, `rollback_application.py:426`
- 族 C（1 文件，NO lower，两种错误文本）: `configuration_application.py:307`
- 族 D（1 文件，NO lower，`int(digest,16)` 校验）: `manual_recovery.py:372`
- 族 E（1 文件，lower，不同错误文本）: `manual_recovery_verification.py:207`
- 族 F（1 文件，NO lower，regex fullmatch）: `gate_revalidation.py:156`

### 2.6 C5-CTRL-02 [HIGH] — absolute_path 签名改为 text: str

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §1.6.4 `absolute_path` 签名从 `(value: ModelConfigJsonValue, *, name: str) -> Path` 改为 `(text: str, *, name: str) -> Path`
- 行为 spec：先 `Path(text).expanduser()`，在 resolve 前检查 `is_absolute()`，否则 raise，再 `return path.resolve()`
- 各 caller 先用各自 `_required_text` 族得到 text，再传入 shared
- §1.6.7 同步更新

### 2.7 C5-CTRL-03 [HIGH] — decode_base64 签名改为 text: str

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §1.6.4 `decode_base64` 签名从 `(value: ModelConfigJsonValue, *, name: str) -> bytes` 改为 `(text: str, *, name: str) -> bytes`，删除 `urlsafe` 参数
- `decode_base64_strict` 签名从 `(value: ModelConfigJsonValue, *, name: str) -> bytes` 改为 `(text: str, *, name: str) -> bytes`
- 各 caller 先用各自 `_required_text` 族得到 text，再调用 shared codec
- inline preapplication 路径也保持族 3 预处理
- §1.6.7 同步更新

### 2.8 C5-CTRL-04 [HIGH] — canonical/fingerprint 逐文件重映射

**状态**: ✅ 已修复

**源码证据**（HEAD 81df373，逐函数读出）:

**`_fingerprint` 调用侧的 `_canonical_json` 返回类型决定映射**:
- 若 `_canonical_json` 返回 `bytes` → `_fingerprint` 直接 sha256 → `fingerprint_bytes`
- 若 `_canonical_json` 返回 `str` → `_fingerprint` 调 `.encode("utf-8")` → `fingerprint_str`

**fingerprint_bytes（5 文件，`_canonical_json` 返回 bytes）**:
1. `configuration_application.py:288` — `_canonical_json(payload)` 返回 bytes → sha256 直接
2. `manual_recovery.py:356` — 同上
3. `manual_recovery_application.py:323` — 同上
4. `manual_recovery_clearance.py:475` — 同上
5. `rollback_application.py:409` — 同上

**fingerprint_str（12 文件，`_canonical_json` 返回 str → `.encode("utf-8")`）**:
1. `configuration_change.py:172`
2. `configuration_rollback.py:291`
3. `configuration_preapplication.py:182`
4. `challenger_run_approval.py:152`
5. `challenger_preflight_approval.py:94`
6. `challenger_promotion.py:100`
7. `challenger_proposal.py:63`
8. `live_smoke_plan.py:68`
9. `incident_dossier.py:138` ← **v4.1 错误标为 fingerprint_bytes**
10. `incident_dossier_revalidation.py:113` ← **v4.1 错误标为 fingerprint_bytes**
11. `gate_revalidation.py:75` ← **v4.1 错误标为 fingerprint_bytes**
12. `health.py:65`（内联 `json.dumps` str）

**verification.py**: 无 `_fingerprint`（仅有 `_bytes_fingerprint`），不参与 fingerprint_str/bytes 映射。

**plan v4.2 修改点**:
- §1.6.1: canonical/fingerprint 变体文件数更新为 fingerprint_str:12 + fingerprint_bytes:5 = 17
- §1.6.7: `fingerprint_str` caller 数 9→12，`fingerprint_bytes` caller 数 8→5
- Slice 2A/2B 迁移表：`incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation` 的 `_fingerprint` → `fingerprint_str`（非 `fingerprint_bytes`）
- 对全部 19 行 `_fingerprint` 映射重新逐行验证

### 2.9 C5-CTRL-05 [HIGH] — format_utc 族文件数修正

**状态**: ✅ 已修复

**源码证据**（HEAD 81df373，逐函数读出）:

**microseconds 族（3 文件）**: `isoformat(timespec="microseconds")`
1. `configuration_application.py:255`
2. `rollback_application.py:380`
3. `manual_recovery.py:342`

**seconds 族（2 文件）**: `_normalize_now(value).isoformat(timespec="seconds")`
1. `manual_recovery_application.py:309`
2. `manual_recovery_clearance.py:461`

**auto 族（6 文件）**: `isoformat()` 无 timespec，全部 defer
1. `configuration_change.py:298`
2. `configuration_rollback.py:355`
3. `challenger_run_approval.py:255`
4. `challenger_preflight_approval.py:165`
5. `gate_revalidation.py:146`
6. `incident_dossier_revalidation.py:198`

**plan v4.2 修改点**:
- §1.6.4 `format_utc` microseconds 族文件数 4→3
- §1.6.7 `format_utc` caller 数 4→3
- Slice 2A/2B 迁移表：`configuration_change`、`configuration_rollback`、`challenger_run_approval`、`challenger_preflight_approval` 的 `_format_utc` 标注 defer（auto 族，原错误标为迁移）

### 2.10 C5-CTRL-06 [MEDIUM] — 删除旧草稿 residual 引用

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- 删除所有"仅 public transaction_id 保留"说法
- §1.6.7 最终清单不包含 `transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、`persist_immutable_atomic`、`serialize_compact`
- §1.6.6 Group C/D 明确列出这些全部 defer/删除
- §5 Slice 1 逐函数删除清单包含所有旧草稿函数

### 2.11 C5-CTRL-07 [MEDIUM] — Slice 1 差分 characterization 测试

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- §5 Slice 1 新增"差分 characterization / 固定反例 corpus"测试组：
  - `test_validated_fingerprint_case_sensitivity` — 大小写 fingerprint 反例，验证族 A/G 的 lower 行为
  - `test_validated_fingerprint_error_texts` — 验证各家族错误文本差异：`"must be a sha256 fingerprint"` vs `"must use sha256"` vs `"is invalid"` vs `"must be a SHA-256 fingerprint"` vs `"is not a SHA-256 fingerprint"`
  - `test_format_utc_seconds_naive_raises` — naive datetime（`tzinfo is None or utcoffset() is None`）必须抛 `ValueError("now must include a timezone")`
  - `test_format_utc_seconds_vs_microseconds` — 精度差异：`timespec="seconds"` 截断微秒 vs `timespec="microseconds"` 保留
  - `test_absolute_path_relative_raises` — relative path 抛 `ValueError`
  - `test_absolute_path_symlink_not_pre_resolved` — 验证 symlink 在 expanduser 后、resolve 前不做额外处理
  - `test_is_subpath_does_not_resolve_symlinks` — 非 resolve 行为
  - `test_decode_base64_standard_vs_urlsafe` — 标准 b64decode vs urlsafe 差异，锁定零 urlsafe 行为
  - `test_decode_base64_error_text_families` — `"is invalid"` vs `"must be valid base64"`
  - `test_require_text_family_1_behavior` — NFKC + ord<32 + strip + max_length
- 新增 §5 Slice 1 "Slice 2 测试迁移说明"：Slice 2 删除私有函数后，对应 characterization 测试迁移为 shared helper 的 module-level regression，通过直接 import `_write_artifact_utils` 完成，不留下任何导入已删除私有函数的脆弱测试引用
- 零 `type: ignore` / `Any` / `object` / `cast` 逃逸约束

### 2.12 C5-CTRL-08 [MEDIUM] — Slice 2 拆分为 2A/2B

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- 原 Slice 2 拆为 Slice 2A（canonical/fingerprint/file/bytes + require_mapping + optional_mapping + serialize_pretty，~10 文件）+ Slice 2B（path + validation + time + codec 族，~9 文件）
- Slice 2A 和 2B 各含 allowed files、helper families、前置依赖（均依赖 Slice 1）、独立绿信号
- Slice 2A 禁止修改 Slice 2B 的文件，反之亦然
- 总 slice 数从 14 变为 15（0..2A, 2B, 3..13），依赖图、总数、checklist 同步更新

### 2.13 C5-CTRL-09 [LOW] — 清理旧版本残留

**状态**: ✅ 已修复

**plan v4.2 修改点**:
- 头部：HEAD `5821014` → `81df373`，v4.1 DRAFT / PENDING MIMO REVIEW → v4.2 DRAFT / PENDING MIMO RE-REVIEW
- 审查来源新增：`docs/reviews/plan-c5-v4.1-review-20260807-mimo.md`、`docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md`
- 全文清理"C5 20 helper"→"C5 17 helper"（或更精确的当前数量）
- 删除 v4.1 "ACCEPTED" 声明
- 新增 v4.1→v4.2 changelog 条目

---

## 3. 修改后的 shared 函数最终清单（v4.2，17 函数）

每个 caller 计数基于 HEAD 81df373 私有 eligible callers，不计未跟踪 `_write_artifact_utils.py` 自身。

| # | 函数 | 精确签名 | HEAD 私有 eligible callers | 备注 |
|---|---|---|---|---|
| 1 | `canonical_json_str` | `(value: ModelConfigJsonValue) -> str` | **11** | str 系 `_canonical_json` 直接定义数（`health.py` 使用内联 `json.dumps`，不计入 `canonical_json_str` 直接 caller；仅计入 `fingerprint_str`） |
| 2 | `canonical_json_bytes` | `(payload: JsonObject) -> bytes` | 6 | bytes 系 `_canonical_json` 文件数 |
| 3 | `fingerprint_str` | `(value: ModelConfigJsonValue) -> str` | **12** | 11 个 `_canonical_json` 返回 str → `.encode("utf-8")` → sha256 的文件 + `health.py` 内联 `json.dumps` 等价 |
| 4 | `fingerprint_bytes` | `(payload: JsonObject) -> str` | **5** | 所有 `_canonical_json` 返回 bytes → sha256 直接的文件 |
| 5 | `file_fingerprint` | `(path: Path) -> str` | 10 | 3 种循环写法等价 |
| 6 | `bytes_fingerprint` | `(value: bytes) -> str` | 10 | 完全等价 |
| 7 | `validated_fingerprint` | `(value: ModelConfigJsonValue, *, name: str, error_label: str = "must be a sha256 fingerprint") -> str` | **7** | 仅族 A（6）+ 族 G（1）。族 B-F（9）全部保留私有，禁止经预处理后调用 shared |
| 8 | `require_mapping` | `(value: ModelConfigJsonValue, *, name: str) -> JsonObject` | 14 | 严格版 |
| 9 | `optional_mapping` | `(value: ModelConfigJsonValue) -> JsonObject` | 3 | 静默版 |
| 10 | `require_text` | `(value: ModelConfigJsonValue, *, name: str, maximum_length: int) -> str` | **6** | 仅族 1（NFKC+ord<32+必需max_length）私有 caller。不含未跟踪 public helper |
| 11 | `format_utc` | `(value: datetime) -> str` | **3** | microseconds 族：`configuration_application`、`rollback_application`、`manual_recovery` |
| 12 | `format_utc_seconds` | `(value: datetime) -> str` | 2 | seconds 族。先检查 `tzinfo is None or utcoffset() is None`，naive → ValueError("now must include a timezone")，再 astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z") |
| 13 | `is_subpath` | `(path: Path, root: Path) -> bool` | 8 | try/except path.relative_to(root)，不 resolve |
| 14 | `absolute_path` | `(text: str, *, name: str) -> Path` | 7 | text: str 入参（非 ModelConfigJsonValue）；Path(text).expanduser() → is_absolute() → resolve()。text 校验由调用方各自 _required_text 处理 |
| 15 | `serialize_pretty` | `(payload: JsonObject) -> str` | 13 | sort_keys=True, indent=2 + "\n" |
| 16 | `decode_base64` | `(text: str, *, name: str) -> bytes` | **5**（4 私有 + 1 inline） | text: str 入参（非 ModelConfigJsonValue）；标准 b64decode(validate=True)，"is invalid"。4 私有：configuration_application, rollback_application, manual_recovery_application, configuration_rollback；1 inline：configuration_preapplication |
| 17 | `decode_base64_strict` | `(text: str, *, name: str) -> bytes` | 1 | text: str 入参；标准 b64decode(validate=True)，"must be valid base64" |

**从旧草稿删除的函数（6 个，不进入 v4.2 最终清单）**:
- `is_relative_to`（resolve 版）→ 替换为 `is_subpath`
- `transaction_id` → defer（语义异构，§1.6.6 Group C）
- `snapshot_fingerprint` → defer（含业务 validator，§1.6.6 Group C）
- `require_exact_fields` → defer（8 exact family，参数爆炸，§1.6.6 Group C）
- `persist_immutable_atomic` → defer（5 family，参数爆炸，§1.6.6 Group D）
- `serialize_compact` → 删除（零 eligible caller）

---

## 4. Slice 2A/2B 拆分设计（Cohort 模式，非重叠文件集合）

### 设计原则（C5-CTRL-08 follow-up 修正）

**非重叠文件 cohort**，非 helper-family 分段。每个 cohort 的每个文件在一次 commit 中完成该文件**全部** eligible shared helper 迁移。不得留跨-slice 的半迁移状态（"→2B"）。auto 族/defer 仍保留原位。

### Cohort A（Slice 2A，10 文件）

`configuration_change`, `configuration_rollback`, `configuration_preapplication`, `challenger_run_approval`, `challenger_preflight_approval`, `challenger_promotion`, `challenger_proposal`, `health`, `live_smoke_plan`, `write_run_comparison`

每文件完成全部 eligible helper 迁移，含 `absolute_path`、`decode_base64`、`bytes_fingerprint`、`is_subpath` 等。auto `_format_utc` defer。族 3 `_required_text` 保留用于本地预处理。

### Cohort B（Slice 2B，9 文件）

`configuration_application`, `rollback_application`, `manual_recovery`, `manual_recovery_application`, `manual_recovery_clearance`, `manual_recovery_verification`, `incident_dossier`, `incident_dossier_revalidation`, `gate_revalidation`

每文件完成全部 eligible helper 迁移。`incident_dossier` 含 `_serialize`→`serialize_pretty`。族 B-F `_validated_fingerprint` 全部 "**禁止迁移**"。`fingerprint_str` 3 文件（incident_dossier/incident_dossier_revalidation/gate_revalidation）。

### 文件集合验证

- Cohort A: 10 files ✅
- Cohort B: 9 files ✅
- 交集: empty ✅
- 并集: 19 ✅

---

## 5. 机械一致性检查（Mechanical Consistency Check）

v4.2 plan 须通过以下自动/手动检查：

| # | 检查项 | 预期结果 |
|---|---|---|
| MC-01 | 全文无"C5 20 helper"字样 | 0 命中 |
| MC-02 | 全文无"5821014"（旧 HEAD） | 0 命中（除 changelog 历史记录外） |
| MC-03 | 全文无"v4.0→v4.1 变更"中"microseconds 族 4 文件" | 已改为 3 文件 |
| MC-04 | `fingerprint_bytes` 映射不包含 incident_dossier / incident_dossier_revalidation / gate_revalidation 的 `_fingerprint` | 上述三文件 `_fingerprint` → `fingerprint_str` |
| MC-05 | auto 族 `_format_utc` 不在任何迁移列中 | 6 文件全部标注 defer（auto 族） |
| MC-06 | `validated_fingerprint` 迁移仅限族 A/G 7 文件 | 族 B-F 9 文件全部在 defer 列 |
| MC-07 | `absolute_path` 签名为 `(text: str, *, name: str) -> Path` | 不接受 `ModelConfigJsonValue` |
| MC-08 | `decode_base64` / `decode_base64_strict` 签名为 `(text: str, *, name: str) -> bytes` | 不接受 `ModelConfigJsonValue`，无 `urlsafe` 参数 |
| MC-09 | 无 public `transaction_id` 在最终清单中 | 最终 17 清单不含 transaction_id |
| MC-10 | 无 `snapshot_fingerprint` 在最终清单中 | 最终 17 清单不含 snapshot_fingerprint |
| MC-11 | 无 `require_exact_fields` 在最终清单中 | 最终 17 清单不含 require_exact_fields |
| MC-12 | 无 `persist_immutable_atomic` 在最终清单中 | 最终 17 清单不含 persist_immutable_atomic |
| MC-13 | 无 `serialize_compact` 在最终清单中 | 最终 17 清单不含 serialize_compact |
| MC-14 | 无 resolve 版 `is_relative_to` 在最终清单中 | 已替换为 `is_subpath` |
| MC-15 | Slice 0..2B..13 总数一致 | 15 个 slice（0, 1, 2A, 2B, 3–13），依赖图、§5 序列、§6 排序理由、§11 完成定义全部同步 |
| MC-16 | `require_text` caller 数 = 6 | 不计算未跟踪 public helper |
| MC-17 | `format_utc` caller 数 = 3 | microseconds 族私有 3 文件 |
| MC-18 | `fingerprint_str` caller 数 = 12（11 defs + health inline） | 逐文件验证：2A=9 + 2B=3 |
| MC-19 | `fingerprint_bytes` caller 数 = 5 | 逐文件验证 |
| MC-20 | `validated_fingerprint` caller 数 = 7 | A(6) + G(1) |
| MC-21 | `canonical_json_str` caller 数 = 11（health 不计入） | 直接 `_canonical_json` 返回 str 的定义数 |
| MC-22 | `serialize_pretty` 迁移 13 + defer 1 = 14 all | 2A=5 migrate + 1 defer, 2B=8 migrate |
| MC-23 | Slice 1 算术：20 − 6 + 3 = 17 | 3 新增非 2 |

---

## 6. Plan v4.2 修改的 Section 清单

| Section | 修改类型 | 关键变更 |
|---|---|---|
| 头部（行 1–9） | 重写 | HEAD 81df373、v4.2 DRAFT / PENDING MIMO RE-REVIEW、新增 v4.1→v4.2 changelog、审查来源新增 MiMo + 本 fix |
| §1.6.1（行 185–190） | 数据修正 | canonical/fingerprint 变体文件数更新：fingerprint_str 12、fingerprint_bytes 5 |
| §1.6.2（行 192–206） | 策略修正 | 族 B-F 禁止经预处理后调用 shared，全部保留私有。仅族 A/G 7 文件迁移 |
| §1.6.3（行 208–237） | 数据修正 | 族 1 eligible caller 7→6，rollback_application 行号修正 |
| §1.6.4（行 239–254） | 多函数修正 | format_utc 3/2/6、format_utc_seconds spec 补全、absolute_path text:str、decode_base64 text:str 无 urlsafe、decode_base64_strict text:str |
| §1.6.6（行 276–291） | 扩充 | 新增旧草稿 6 函数 defer/删除条目 |
| §1.6.7（行 293–317） | 全面重写 | 17 函数精确签名、正确 caller 数、删除旧草稿函数 |
| §5 Slice 1（行 511–553） | 重写 | "重构/替换"模式、逐函数删除/新增/修正清单、差分 characterization 测试、Slice 2 测试迁移说明 |
| §5 Slice 2（行 557–589） | 拆分+重写 | 拆为 2A/2B，逐文件精确迁移表，correct fingerprint/validated_fingerprint/format_utc 映射 |
| §5 Slice 序列（行 457–474） | 更新 | 14→15 slice，依赖图更新 |
| §6 排序理由（行 1303–1314） | 更新 | 新增 2A→2B 依赖 |
| §8 约束合规（行 1324–1341） | 数据修正 | "17 共享函数（v4.2）" |
| §10 残余风险（行 1393–1401） | 更新 | 新增 Slice 2A/2B 拆分风险缓解 |
| §11 完成定义（行 1405–1422） | 更新 | 15 slice、v4.2 函数清单 |
| Closure Tables（行 49–83） | 不变 | F/R2/V4 closure 保持，新增 v4.2 adjudication |
| Slice 3..13 | 重新编号 | Slice 3 起编号不变，但依赖图更新反映 2A→2B→3 |

---

## 7. 验证

### 7.1 已执行验证（含 follow-up 机械验收）

```bash
# 确认未修改受保护文件
git diff --check  # PASS: clean
git diff --name-only
# 输出:
#   docs/plans/2026-08-07-cli-write-architecture-refactor.md
#   docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md (新建)
#   tests/README.md (pre-existing unstaged, not modified by this session)
```

**机械验证结果（18 项 follow-up 全量验证）**:

| # | 验证项 | 结果 |
|---|---|---|
| V1 | 2A 迁移表行数 = 10 | ✅ PASS（含 `write_run_comparison.py`） |
| V2 | 2B 迁移表行数 = 9 | ✅ PASS |
| V3 | 19 文件集合唯一且不交叠 | ✅ PASS（交集为空，并集 19） |
| V4 | serialize: 2A=5 migrate + 1 defer, 2B=8 migrate → 13 migrate + 1 defer = 14 all | ✅ PASS |
| V5 | canonical_json_str 迁移表行: 2A=8 实际迁移（health 行含解释性文本不计）+ 2B=3 = 11 direct defs | ✅ PASS |
| V6 | fingerprint_str 迁移表行: 2A=9（8 str-canonical + health inline）+ 2B=3 = 12 | ✅ PASS |
| V7 | validated_fingerprint B-F 全部在 defer 列（9 文件 "**禁止迁移**"） | ✅ PASS |
| V8 | auto 族 format_utc 全部标注 DEFER（6 文件） | ✅ PASS |
| V9 | 无 public transaction_id 残留 | ✅ PASS |
| V10 | 无 "C5 20 helper" 残留（仅 F-04 历史 closure） | ✅ PASS |
| V11 | Slice 1 算术：20 − 6 删除 + 3 新增 = 17 | ✅ PASS |
| V12 | format_utc_seconds: `tzinfo is None or utcoffset() is None` 检查 | ✅ PASS |
| V13 | 无重复 `---` 分隔线 | ✅ PASS |
| V14 | 迁移表中无 "→2B" 半迁移标记（cohort 设计下每行一次完成全量迁移） | ✅ PASS |
| V15 | incident_dossier _serialize→serialize_pretty 已在 2B 表 | ✅ PASS |

### 7.2 待 Slice 实现时验证

- `pytest tests/application/ -v` — Slice 0 characterization 绿
- `pyright dayu/services/_write_artifact_utils.py` — 0 errors
- `pyright dayu/services/write_model_*.py` — 迁移后 0 新增 errors

---

## 8. Follow-up 修正清单（Controller 机械验收）

以下为 controller 机械验收及后续源码对照发现的 18 项问题及修正状态：

| # | 问题 | 修正 |
|---|---|---|
| 1 | Slice 1 "新增（2 个）"应为 3 | ✅ "新增（3 个）"，checklist "旧草稿20：6删3修正11保留；再新增3，最终17" |
| 2 | format_utc_seconds 仅检查 tzinfo，遗漏 utcoffset | ✅ `value.tzinfo is None or value.utcoffset() is None` |
| 3 | §1.6.4 仍写 "public transaction_id 保留" | ✅ 改为全部 5 私有 defer，HEAD 无 public helper |
| 4 | F-04 closure "C5 20 helper" | ✅ 改为 "C5 17 helper inventory" |
| 5 | canonical_json_str=12 错，应为 11（health 不计） | ✅ §1.6.1/§1.6.7 修正：canonical_json_str=11 direct defs，fingerprint_str=12（11 defs+health inline） |
| 6 | 2A/2B 非重叠文件 cohort 设计 | ✅ 完全重写：cohort A 10 文件 + cohort B 9 文件，不交叠，无 "→2B" |
| 7 | 三文件迁移补全（change/rollback/preapplication） | ✅ change: absolute_path（无 codec）；rollback: absolute_path/decode_base64/bytes_fingerprint/is_subpath；preapplication: absolute_path/inline decode/bytes_fingerprint |
| 8 | incident_dossier 漏 _serialize | ✅ 加入 `_serialize`→`serialize_pretty` |
| 9 | fingerprint_str 直接文件数 2A=9/2B=3，canonical_json_str=11 | ✅ 分项计数，health 只计 fingerprint_str |
| 10 | 测试迁移说明笼统 | ✅ 重写：deferred 族保持私有 characterization；deleted 族迁移为 shared 断言 |
| 11 | 清理重复分隔线 + 运行验证 | ✅ 修复 + 15 项机械验证全部 PASS |
| 12 | §1.6.1 canonical 计数：标准 str=10 + str+dict=1 → 11（非标准 str=11） | ✅ 互斥分类，fingerprint_str 仍 12（10+1+health inline） |
| 13 | Slice 1 checklist "6删3新增3修正8保留" 逻辑错误（新增不属于旧草稿分解） | ✅ "旧草稿20：6删3修正11保留；再新增3，最终17" |
| 14 | **codec**: decode_base64 caller 应为 "4 私有 + 1 inline = 5"（非 5+1）；config_change 无 b64 | ✅ §1.6.4/§1.6.7 修正；2A 表 change 行删除 b64；迁移规则重写 |
| 15 | **require_text**: 16 私有定义（非 17） | ✅ changelog SA-08 + §1.6.3 17→16；family 表 6+2+2+2+1+1+1+1=16 |
| 16 | **transaction_id**: 4 行为家族（3 hash algos + 1 validator），非 3 语义 | ✅ §1.6.4 + Group C 改为 4-family 精确叙述；保留全部 DEFER |
| 17 | **require_mapping**: preflight 无 `_mapping` 定义，从 2A 表删除 | ✅ strict=5(2A)+9(2B)=14；optional=3(2A)；闭合 17 |
| 18 | **absolute_path**: 7 定义跨三族（非两族） | ✅ §1.6.4 "两族"→"三族"：族1=4、族2=1、族3=2 |

---

## 9. 残余风险（v4.2 follow-up 后更新）

| 风险 | 严重度 | 说明 |
|---|---|---|
| Slice 2A/2B cohort 文件集合不交叠 | — | 已验证：交集为空，并集 19 |
| serialize 13+1 分布正确 | — | 2A=5 migrate + 1 defer, 2B=8 migrate |
| canonical_json_str 11 direct + fingerprint_str 12 | — | 2A 8+9, 2B 3+3 |
| health.py 仅迁 fingerprint_str + optional_mapping | LOW | 内联 `json.dumps` 等价 canonical_json_str 但非直接定义，不计入 canonical 迁移 |

---

## 10. Stop Status

**STOP** — plan v4.2 DRAFT / PENDING MIMO RE-REVIEW 已完成（含 follow-up 修正）。不进入 re-review，不实施代码。

**Changed files**:
1. `docs/plans/2026-08-07-cli-write-architecture-refactor.md` — 更新至 v4.2 DRAFT（含 follow-up）
2. `docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md` — 本 fix artifact（含 follow-up）

**Unchanged (read-only) files**: 全部其他文件。

---

*修复者: AgentDS (DeepSeek) · 2026-08-07 · 基于 HEAD 81df373 源码 + MiMo SA-REVIEW + Controller Rulings + 机械验收 follow-up*
