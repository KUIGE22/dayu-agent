# Plan C5 v4.1 Review: CLI Write 架构重构 Master Plan

- **日期**: 2026-08-07T19:10:00
- **审查对象**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.1 DRAFT
- **前序审查**: `plan-c5-source-audit-20260807-deepseek.md`（AgentDS 逐函数源码审计，SA-01..SA-12）
- **审查方法**: 逐项核验 v4.1 声称是否被源码事实支撑；交叉比对 HEAD 5821014 源码与已存在的 `_write_artifact_utils.py` 实现；检查 v4.1 新回归
- **源码验证**: `dayu/services/_write_artifact_utils.py`（623 行，20 函数）、19 个 `write_model_*.py`、`write_service.py`

---

## Verdict: FAIL

**理由**: 1 项 blocker（HIGH），3 项 MEDIUM，4 项 LOW。

**HIGH blocker**: `_write_artifact_utils.py` 已存在于 HEAD，含 20 个函数，但 v4.1 plan §5 Slice 1 仍标注"新建"。当前实现与 v4.1 spec 存在 **6 处实质性行为不等价**（`is_relative_to` 使用 resolve 而非 try/except、`decode_base64` 默认 urlsafe=True 而非标准 b64decode、`persist_immutable_atomic` 使用 os.replace 而非 os.link、`transaction_id` 语义完全不同、`snapshot_fingerprint` 缺少业务 validator、`require_exact_fields` 仅覆盖 1/8 family），必须在 v4.2 中明确迁移策略——是删除后重建还是就地重构。

---

## Findings

### SA-REVIEW-01 [HIGH] `_write_artifact_utils.py` 已存在且行为与 v4.1 spec 不等价

**位置**: §5 Slice 1（行 511）、§1.6.7（行 293）

**计划声称**:
> Slice 1: **新建**: `dayu/services/_write_artifact_utils.py`
> §1.6.7: 17 个 shared 函数清单

**源码事实**: `_write_artifact_utils.py` 已存在于 HEAD（623 行，20 个函数 + `__all__`）。当前实现基于 v4.0 spec，与 v4.1 存在以下 **6 处实质性行为不等价**：

| # | 当前函数 | 当前行为 | v4.1 spec | 等价性 |
|---|---|---|---|---|
| 1 | `is_relative_to` | `path.resolve().is_relative_to(root.resolve())`（解析符号链接） | `is_subpath`: `try: path.relative_to(root) except ValueError: return False; return True`（不解析） | **不等价** |
| 2 | `decode_base64` | `urlsafe: bool = True`（默认 urlsafe_b64decode） | 默认标准 `b64decode(validate=True)`，无 urlsafe 模式（零 caller） | **不等价** |
| 3 | `persist_immutable_atomic` | `os.replace`（原子 rename，可覆盖） | 大部分 caller 使用 `os.link`（硬链接，天然 no-clobber） | **不等价** |
| 4 | `transaction_id` | 生成 `{prefix}-{now:%Y%m%dT%H%M%S}-{fp[:12]}` | 4 个私有 `_transaction_id` 输出纯 SHA-256 hex（无 prefix/timestamp），1 个是输入校验函数。**完全 defer** | **语义不同** |
| 5 | `snapshot_fingerprint` | 直接提取 `snapshot["snapshot_fingerprint"]`，不含业务 validator | 5 个源码实现全部先调用 `validate_write_scene_model_routing_snapshot(snapshot)`。**完全 defer** | **行为缺失** |
| 6 | `require_exact_fields` | 仅 `missing/extra` + `sorted()` 格式 | 8 个 exact family（3 命名+4 错误格式）。**完全 defer** | **仅覆盖 1/8** |

**失败路径**: 若 Slice 2 按当前 `_write_artifact_utils.py` 实施迁移，将改变 19 个 `write_model_*.py` 的行为：
- 8 个使用 try/except `_is_relative_to` 的文件将改为 resolve 模式（符号链接语义变更）
- 6 个使用标准 `b64decode` 的文件将改为 urlsafe 模式
- 13 个使用 `os.link` 的文件将改为 `os.replace`（丧失天然 no-clobber 保证）
- 4 个 SHA-256 hex `_transaction_id` 将被替换为带时间戳的前缀格式
- 5 个含业务 validator 的 `_snapshot_fingerprint` 将丢失校验

**v4.2 修改要求**:
1. Slice 1 描述从"新建"改为"重构"，明确列出需删除的 6 个函数（`is_relative_to`→`is_subpath`、`decode_base64` 默认值修正、`persist_immutable_atomic`→defer、`transaction_id`→defer、`snapshot_fingerprint`→defer、`require_exact_fields`→defer）和需新增的 2 个函数（`format_utc_seconds`、`decode_base64_strict`）
2. 新增 `is_subpath` 函数（try/except 非 resolve），保留 `is_relative_to` 作为 resolve 版（但无 eligible private caller，需评估是否删除）
3. `decode_base64` 默认值从 `urlsafe=True` 改为 `urlsafe=False`
4. 在 Slice 1 commit message 中明确说明行为变更及影响

---

### SA-REVIEW-02 [MEDIUM] `is_relative_to` resolve 版零 eligible caller

**位置**: §1.6.4（行 248）、§1.6.7（行 311）

**计划声称**:
> SA-02: is_relative_to 8 个实现全部为 `try: path.relative_to(root)` 非 resolve 模式，统一为 `is_subpath`，删除无 caller 的 resolve 版

**源码验证**:
```bash
grep -A5 "def _is_relative_to" dayu/services/write_model_*.py
```
**全部 8 个私有实现**均使用 `try: path.relative_to(root) except ValueError: return False; return True`，无一使用 resolve。

当前 `_write_artifact_utils.py` 的 `is_relative_to` 使用 `path.resolve().is_relative_to(root.resolve())`，**与全部 8 个 caller 行为不等价**。

**§1.6.7 清单核验**: 表格行 13 写 `is_subpath`，但当前实现函数名为 `is_relative_to`。§1.6.4 行 248 写"删除无 caller 的 resolve 版 `is_relative_to`"——但当前实现**就是** resolve 版。

**v4.2 修改要求**:
1. 明确 Slice 1 需将当前 `is_relative_to`（resolve 版）重命名为 `is_subpath` 并**改变实现**为 try/except 非 resolve 模式
2. 或保留两个函数：`is_relative_to`（resolve，当前实现）+ `is_subpath`（try/except，新增），§1.6.7 明确各函数的 eligible caller

---

### SA-REVIEW-03 [MEDIUM] `decode_base64` 默认 urlsafe=True 与 v4.1 spec 矛盾

**位置**: §1.6.4（行 252）、§1.6.7（行 314）

**计划声称**:
> SA-06: decode_base64 全部现有实现为标准 b64decode(validate=True)，删除无 caller 的 urlsafe 模式

**源码验证**:
```bash
grep -B2 -A8 "def _decode_base64" dayu/services/write_model_configuration_application.py
```
全部 5 个 `_decode_base64` 实现均使用 `base64.b64decode(text, validate=True)`，无 urlsafe 用例。`manual_recovery.py` 的错误文本为 `"must be valid base64"`，缺 `TypeError` 捕获。

当前 `_write_artifact_utils.py` 的 `decode_base64` 默认 `urlsafe: bool = True`，使用 `base64.urlsafe_b64decode`——**与全部 5 个 caller 行为不等价**。

**v4.2 修改要求**:
1. `decode_base64` 默认值从 `urlsafe=True` 改为 `urlsafe=False`，或完全删除 `urlsafe` 参数（零 caller）
2. 新增 `decode_base64_strict` 函数（错误文本 `"must be valid base64"`，捕获 `(binascii.Error, ValueError)`，不补 TypeError）

---

### SA-REVIEW-04 [MEDIUM] `format_utc_seconds` 和 `decode_base64_strict` 缺实现 spec

**位置**: §1.6.4（行 246, 253）、§1.6.7（行 310, 315）

**计划声称**:
> §1.6.7 行 310: `format_utc_seconds(value: datetime) -> str`，2 文件
> §1.6.7 行 315: `decode_base64_strict(value: ModelConfigJsonValue, *, name: str) -> bytes`，1 文件

**问题**: §1.6.4 对 `format_utc_seconds` 的行为 spec 写 `_normalize_now(value).isoformat(timespec="seconds").replace("+00:00", "Z")`，但未提供 `_normalize_now` 的 spec。源码中 `_normalize_now` 有 3 个变体（§1.6.6 Group D），`format_utc_seconds` 的 2 个 caller（`manual_recovery_application.py:309`、`manual_recovery_clearance.py:461`）使用的 `_normalize_now` 变体是 `astimezone(UTC).replace(microsecond=0, tzinfo=None)`（去微秒+转 UTC）。

**v4.2 修改要求**:
1. §1.6.4 补充 `format_utc_seconds` 的完整行为 spec：`value.astimezone(UTC).replace(microsecond=0).isoformat(timespec="seconds").replace("+00:00", "Z")`，明确不调用 `_normalize_now`（避免引入 Group D 依赖）
2. §1.6.4 补充 `decode_base64_strict` 的完整行为 spec：错误文本 `"{name} must be valid base64"`，捕获 `(binascii.Error, ValueError)`（不含 TypeError）

---

### SA-REVIEW-05 [LOW] §1.6.7 函数清单与 §1.6.4 行为 spec 交叉引用不完整

**位置**: §1.6.7（行 293–317）

**问题**: §1.6.7 表格列出 17 个函数的签名和 caller 文件数，但未提供 §1.6.4 行为 spec 的交叉引用。读者需手动在 §1.6.4 中查找每个函数的详细 spec。

**v4.2 修改要求**: §1.6.7 表格增加"行为 spec 来源"列，指向 §1.6.4 的具体行号或函数名。

---

### SA-REVIEW-06 [LOW] Slice 2 迁移表 `write_model_configuration_change.py` 缺 `_format_utc` 迁移

**位置**: §5 Slice 2（行 565）

**计划声称**:
> `write_model_configuration_change.py`: ... `_format_utc` ...

**源码验证**:
```bash
grep -A2 "def _format_utc" dayu/services/write_model_configuration_change.py
```
`_format_utc` 使用 `value.astimezone(UTC).isoformat().replace("+00:00", "Z")`——**auto 族**（无 timespec），属于 §1.6.6 Group D defer。

**v4.2 修改要求**: Slice 2 迁移表中 `write_model_configuration_change.py` 的 `_format_utc` 应标注为"defer（auto 族）"而非迁移为 `format_utc`。

---

### SA-REVIEW-07 [LOW] Slice 2 迁移表 `write_model_challenger_run_approval.py` 缺 `_format_utc` 族标注

**位置**: §5 Slice 2（行 571）

**源码验证**:
```bash
grep -A2 "def _format_utc" dayu/services/write_model_challenger_run_approval.py
```
`_format_utc` 使用 `value.astimezone(UTC).isoformat().replace("+00:00", "Z")`——**auto 族**，应 defer。

**v4.2 修改要求**: 同 SA-REVIEW-06，标注为 defer。

---

### SA-REVIEW-08 [LOW] §1.6.7 `require_text` caller 文件数 7 与 §1.6.3 族 1 精确映射表不完全一致

**位置**: §1.6.3（行 216）、§1.6.7（行 308）

**计划声称**:
> §1.6.3: 族 1（7 文件，含 public `require_text`）
> §1.6.7 行 308: Slice 2 caller 文件数 = 7

**源码验证**: §1.6.3 族 1 列出 6 个私有文件 + public = 7。但 §1.6.3 行 216 列出的文件为：`configuration_application.py:204`, `configuration_rollback.py:246`, `rollback_application.py:310`, `manual_recovery.py:283`, `manual_recovery_clearance.py:414`, `manual_recovery_incident_dossier.py:95`（+ public `require_text`）= 6 私有 + 1 public = 7。

**核验**: 逐文件检查 `_required_text` 实现，确认这 6 个文件的 `_required_text` 使用 NFKC + ord<32 + 必需 max_length 策略。

**判定**: 数字一致，但 §1.6.3 行 216 的文件列表中 `rollback_application.py:310` 的行号指向 `_absolute_path` 而非 `_required_text`。实际 `_required_text` 在 `rollback_application.py:246`。**行号笔误**。

**v4.2 修改要求**: §1.6.3 族 1 文件列表中 `rollback_application.py:310` 修正为 `rollback_application.py:246`。

---

## 源码验证汇总

| v4.1 声称 | 源码事实 | 判定 |
|---|---|---|
| 17 个 shared 函数 | 当前实现 20 个，6 个需删除/重构，2 个需新增 | **需重构** |
| `is_subpath` 8 文件 try/except | 全部 8 个 `_is_relative_to` 使用 try/except，当前 shared 用 resolve | **不等价** |
| `format_utc` microseconds 族 4 文件 | 4 文件确认使用 `timespec="microseconds"` | ✅ |
| `format_utc` auto 族 6 文件 defer | 6 文件确认使用 `isoformat()` 无 timespec | ✅ |
| `format_utc_seconds` 2 文件 | 2 文件确认使用 `timespec="seconds"` | ✅ |
| `decode_base64` 标准 b64decode 5 文件 | 5 文件确认使用 `b64decode(validate=True)`，当前 shared 默认 urlsafe | **不等价** |
| `decode_base64_strict` 1 文件 | `manual_recovery.py:385` 确认错误文本 `"must be valid base64"`，缺 TypeError | ✅ |
| `persist_immutable` 5 family 13 文件 | 13 文件确认，当前 shared 用 os.replace 而非 os.link | **不等价** |
| `transaction_id` 3 语义 5 实现 | 5 实现确认：public 带前缀+时间戳、4 私有纯 SHA-256 hex、1 校验函数 | **语义不同** |
| `snapshot_fingerprint` 5 文件含 validator | 5 文件确认全部调用 `validate_write_scene_model_routing_snapshot` | ✅ |
| `require_text` 8 族 17 定义 | 16 个 `_required_text` + public = 17，确认 8 族 | ✅ |
| `require_exact_fields` 8 family 15 文件 | 15 文件确认，当前 shared 仅覆盖 1 family | **仅 1/8** |
| `validated_fingerprint` 6 sub-family | 16 个定义确认 7 sub-family（含 G） | ✅ |
| 39 action key research_template | `grep -c 'if action ==' = 39` | ✅ |
| 16 dispatch entries write | `grep 'getattr' | awk '>=4637 && <=4822'` = 16 行 | ✅ |

---

## F-01..F-07 + V4-01..V4-07 + C4-01 Closure 复审

全部保持 CLOSED。v4.1 未修改这些 finding 涉及的区域。SA-01..SA-12 变更仅影响 §1.6（C5 函数清单）和 §5 Slice 1–2（C5 迁移计划）。

---

## 最终判定

**FAIL**。1 项 HIGH blocker（`_write_artifact_utils.py` 已存在且行为与 v4.1 spec 不等价），必须在 v4.2 中明确迁移策略后重新提交。3 项 MEDIUM（`is_relative_to`/`is_subpath` 实现差异、`decode_base64` 默认值差异、新函数 spec 不完整）需同步修正。

**建议**: v4.2 应将 Slice 1 从"新建"改为"重构"，提供逐函数 diff spec（当前实现 → v4.1 目标），并在 commit message 中明确行为变更清单。

---

*审查者: MiMo · 2026-08-07 · 基于 HEAD 5821014 源码逐函数验证*
