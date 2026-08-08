# Plan C5 v4.3 Fix Artifact: CLI Write 架构重构

- **日期**: 2026-08-07
- **修复者**: AgentDS (DeepSeek)
- **输入源**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.2、`docs/reviews/plan-c5-v4.2-rereview-20260807-mimo.md`（MiMo v4.2 re-review）
- **基线 HEAD**: `81df373`
- **分支**: `codex/dual-model-research-mvp`
- **状态**: **STOP** — plan v4.3 DRAFT / PENDING MIMO RE-REVIEW 已产出，不实施代码

---

## 0. Controller Adjudication

### RR-F01 [MiMo F-01] — REJECTED / EVIDENCE INVALID

**MiMo 声称**: `write_model_configuration_manual_recovery_verification.py` 未被纳入 2A/2B 任何 cohort。

**源码事实**: Plan 第 647 行 Cohort B 文件集合明确列出 `write_model_configuration_manual_recovery_verification.py`；第 662 行 2B 迁移表包含该文件的完整迁移行（`_canonical_json` bytes → `canonical_json_bytes`、`_bytes_fingerprint` → `bytes_fingerprint`、`_mapping` → `require_mapping`）。仓库共有 19 个 `write_model_*.py`，18 个相关文件 + `write_run_comparison.py` = 19。

**裁决**: REJECTED。不做任何计数或文件列表修改。

### RR-F02 [MiMo F-02] — REJECTED / EVIDENCE INVALID

**MiMo 声称**: `fingerprint_str` caller 应为 13（含 `challenger_preflight_approval.py`），plan 当前 12 遗漏了 preflight。

**源码事实**: MiMo 自带的表（review 行 114–127）仅列 12 项且 #13 为空行。17 个 `_fingerprint` 定义 = 12 str 系（含 preflight、health inline、live_smoke）+ 5 bytes 系。`challenger_preflight_approval.py` 已在 2A 表的 `fingerprint_str` 迁移列中（plan 行 618 附近），其 `_fingerprint` 属 str 系且已计入 12。

**裁决**: REJECTED。`fingerprint_str`=12 保持不变。

### C5-CTRL-10 [MEDIUM] — ACCEPTED: require_mapping identity-return 与 canonical/fingerprint adapter

**MiMo V1/V2 PASS 理由不完整**: MiMo 认为 `require_mapping` 返回 `dict(value)` 可以替代 identity-return 的 12 个文件（安全），并认为 `json.dumps(value)` 对任意 Mapping 与 `json.dumps(dict(value))` 字节级等价。这两个结论在本 task scope 内缺乏充分验证——`dict(value)` 改变了对象同一性，而 `json.dumps(Mapping)` 的等价性依赖 Mapping 子类的 `keys()`/`__getitem__` 语义。

**Controller 裁决**: 接受这一底层风险为 C5-CTRL-10 MEDIUM。Shared 17 函数及现有 caller 计数**保持不变**；但必须精确区分并显式处理 identity 族与 copy 族。

---

## 1. v4.3 修改清单（C5-CTRL-10）

| # | 修改项 | 位置 |
|---|---|---|
| 1 | `require_mapping` 明确保留 identity-return（`return value`），不返回 `dict(value)`。12 个 identity-return 文件直接迁移 | §1.6.7 备注、§5 Slice 2B 迁移规则 |
| 2 | Copy 族 2 文件（`incident_dossier_revalidation`、`gate_revalidation`）的 `_mapping` 替换为 call-site adapter `dict(require_mapping(value, name=...))` | §5 Slice 2B 表 |
| 3 | `gate_revalidation` 的 `_canonical_json`（str+dict 子变体）替换为 `canonical_json_str(dict(value))`；`_fingerprint` 替换为 `fingerprint_str(dict(value))` | §5 Slice 2B 表 |
| 4 | `incident_dossier_revalidation` 的 `_fingerprint`（调 `_canonical_json(dict(value))`）替换为 `fingerprint_str(dict(value))`；其 `_canonical_json` 直接迁移为 `canonical_json_str`（无 dict 适配器——caller 已传普通值） | §5 Slice 2B 表 |
| 5 | Slice 1 差分 corpus 新增：无 `Any`/`object`/`cast`/`type: ignore` 的 `dict` 子类，验证 identity 族 `require_mapping(value) is value`、copy 族 adapter `dict(require_mapping(value)) is not value` 且值相等；验证 gate_revalidation/incident_dossier_revalidation 的 `dict()` canonical/fingerprint adapter 输出与旧实现完全一致 | §5 Slice 1 |
| 6 | Plan metadata/changelog → v4.3 DRAFT / PENDING MIMO RE-REVIEW，引用 v4.2 re-review 与本 fix artifact | 头部 |

---

## 2. 裁决汇总

| Finding | 来源 | 严重度 | 裁决 |
|---|---|---|---|
| RR-F01 | MiMo F-01 | MEDIUM | **REJECTED** — evidence invalid（verification.py 已在 2B） |
| RR-F02 | MiMo F-02 | LOW | **REJECTED** — evidence invalid（preflight 已在 2A fingerprint_str 9 中） |
| C5-CTRL-10 | Controller | MEDIUM | **ACCEPTED** — require_mapping identity-return；copy 族 call-site adapter；canonical/fingerprint dict adapter |

---

## 3. 最终 shared 函数清单不变（17 函数，caller 计数不变）

| # | 函数 | 签名 | Callers | 备注 |
|---|---|---|---|---|
| 1 | `canonical_json_str` | `(value: ModelConfigJsonValue) -> str` | 11 | identity 直接 |
| 2 | `canonical_json_bytes` | `(payload: JsonObject) -> bytes` | 6 | identity 直接 |
| 3 | `fingerprint_str` | `(value: ModelConfigJsonValue) -> str` | 12 | identity 直接；gate_revalidation/incident_dossier_revalidation 用 call-site `dict()` adapter |
| 4 | `fingerprint_bytes` | `(payload: JsonObject) -> str` | 5 | identity 直接 |
| 5 | `file_fingerprint` | `(path: Path) -> str` | 10 | — |
| 6 | `bytes_fingerprint` | `(value: bytes) -> str` | 10 | — |
| 7 | `validated_fingerprint` | `(value: ModelConfigJsonValue, *, name: str, error_label: str = ...) -> str` | 7 | 仅族 A/G |
| 8 | `require_mapping` | `(value: ModelConfigJsonValue, *, name: str) -> JsonObject` | 14 | **identity-return**：`return value`。copy 族 2 文件用 call-site `dict(require_mapping(...))` |
| 9 | `optional_mapping` | `(value: ModelConfigJsonValue) -> JsonObject` | 3 | — |
| 10 | `require_text` | `(value: ModelConfigJsonValue, *, name: str, maximum_length: int) -> str` | 6 | 族 1 |
| 11 | `format_utc` | `(value: datetime) -> str` | 3 | microseconds |
| 12 | `format_utc_seconds` | `(value: datetime) -> str` | 2 | seconds |
| 13 | `is_subpath` | `(path: Path, root: Path) -> bool` | 8 | — |
| 14 | `absolute_path` | `(text: str, *, name: str) -> Path` | 7 | — |
| 15 | `serialize_pretty` | `(payload: JsonObject) -> str` | 13 | — |
| 16 | `decode_base64` | `(text: str, *, name: str) -> bytes` | 5 | 4 私有 + 1 inline |
| 17 | `decode_base64_strict` | `(text: str, *, name: str) -> bytes` | 1 | — |

---

## 4. 验证

```bash
git diff --check  # PASS
```

**Changed files（本回合）**:
1. `docs/plans/2026-08-07-cli-write-architecture-refactor.md` — 更新至 v4.3 DRAFT
2. `docs/reviews/plan-c5-v4.3-fix-20260807-deepseek.md` — 本 fix artifact（新建）

**Unchanged**: MiMo artifacts、旧 fix artifact、源码、测试。

---

## 5. Stop Status

**STOP** — plan v4.3 DRAFT / PENDING MIMO RE-REVIEW。不实施代码。

---

*修复者: AgentDS (DeepSeek) · 2026-08-07 · 基于 MiMo v4.2 re-review + Controller Adjudication*
