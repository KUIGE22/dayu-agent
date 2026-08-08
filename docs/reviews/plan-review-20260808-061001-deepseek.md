# Plan Review: v4.9 Slice 7 runner-count ownership gap

- **审查时间**: 2026-08-08 06:10 UTC
- **审查人**: DeepSeek（planreview skill）
- **基线**: clean HEAD `b55f794`（v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS）
- **审查范围**: Slice 7 runner count 与 master plan / 源码 AST 的一致性
- **对照文件**:
  - `AGENTS.md`（项目约束）
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（master plan，1953 行）
  - `dayu/cli/commands/write.py`（源码 AST，提交时 3097 行）

---

## Verdict: FAIL（HIGH finding，不可直接实施 Slice 7）

**根因**: master plan 的 Slice 7 描述和 §1.2/§2.1 的功能域分组称 `_write_manual_recovery.py` 含 **"12 个 manual recovery runner + gate check"**，但源码 AST 实有 **14 个 `_run_write_model_configuration_manual_recovery_*` 函数** + 1 个 `_check_write_model_configuration_manual_recovery_gate` = **15 个函数**。plan 自身的 Phase A adapter 表（§11c/§11e）已正确列出全部 14 条目——plan 内部自矛盾。

---

## 1. 证据矩阵

### 1.1 源码证据：14 个 runner 函数（write.py 精确行号，b55f794 HEAD）

```
行 579:  _run_write_model_configuration_manual_recovery_evidence
行 644:  _run_write_model_configuration_manual_recovery_plan
行 718:  _run_write_model_configuration_manual_recovery_approval
行 791:  _run_write_model_configuration_manual_recovery_application      ← execution_options
行 896:  _run_write_model_configuration_manual_recovery_verification     ← execution_options
行 980:  _run_write_model_configuration_manual_recovery_clearance        ← execution_options
行 1085: _run_write_model_configuration_manual_recovery_clearance_revocation
行 1176: _run_write_model_configuration_manual_recovery_restart
行 1260: _run_write_model_configuration_manual_recovery_gate_check
行 1336: _run_write_model_configuration_manual_recovery_gate_verification
行 1440: _run_write_model_configuration_manual_recovery_gate_revalidation
行 1553: _run_write_model_configuration_manual_recovery_audit_timeline
行 1646: _run_write_model_configuration_manual_recovery_incident_dossier
行 1771: _run_write_model_configuration_manual_recovery_incident_dossier_revalidation
```

此外，独立 Phase C gate 函数：
```
行 1888: _check_write_model_configuration_manual_recovery_gate
```

**合计**: 14 runner + 1 gate check = 15 函数。

### 1.2 Plan 内部矛盾位置

| Plan 位置 | 声称数量 | 是否正确 |
|---|---|---|
| §1.2 功能域分组，行 118 | "手动恢复 12 runner" | **❌ 应为 14** |
| §2.1 目标文件结构，行 410 | "12 manual recovery runner + gate check" | **❌ 应为 14** |
| Slice 7 描述，行 982 | "12 个 manual recovery runner + `_check_..._gate`" | **❌ 应为 14** |
| §1.3 Phase 边界，行 138 | "Phase A 共 **14 条目**" | ✅ 正确 |
| §11c Action Inventory 表，行 1285-1302 | 14 行 Phase A 条目 | ✅ 正确 |
| §11e Adapter 列表，行 1388-1452 | 14 个 Phase A adapter | ✅ 正确 |
| §11d Phase 常量表，行 1314-1371 | 14 个 `_EarlyWriteSubcommandEntry` | ✅ 正确 |
| Slice 0 I-a Group 1，行 569-570 | "Phase A boolean selectors（11 个）" + Group 2 "3 个 path" | ✅ 合计 14 |
| §1.2 手动恢复区域行范围，行 118 | "783–2057 ~1275 行" | **❌** 实际从行 579 开始（evidence），结束于行 1886（incident_dossier_revalidation），范围 579–1886 |

### 1.3 execution_options 分发矩阵（源码验证）

3 个 runner 接受 `execution_options: ExecutionOptions`：
- `application`（行 791）：Phase A entry #14，adapter 惰性 build
- `verification`（行 896）：Phase A entry #10，adapter 惰性 build
- `clearance`（行 980）：Phase A entry #9，adapter 惰性 build

11 个 runner 不接受 `execution_options`——签名仅含 `args: argparse.Namespace` + `paths_config: WorkspaceConfig`。

与 §11c 惰性 build 标注完全一致（entries 9, 10, 14）。

### 1.4 snapshot_builder factory handoff 矩阵

3 个 runner 使用 `build_snapshot_builder`：
- `application`（行 843）：默认 label `"configuration-application"`
- `verification`（行 932）：显式 label `"configuration-manual-recovery-verification"`
- `clearance`（行 1032）：显式 label `"configuration-manual-recovery-clearance"`

与 Slice 7 描述中 "application/verification/clearance 三个 runner 迁移时必须连同其既有 `build_snapshot_builder` factory call 一并迁移" 一致。

---

## 2. Findings

### H-01 (HIGH) — runner count 12≠14，Slice 7 scope 定义错误

**严重度**: HIGH。Slice 7 是实施 slice，若按 "12" 实施将遗漏 2 个 runner 函数，导致 `write.py` 残留旧定义、`_write_manual_recovery.py` 不完整、Phase A dispatch 断裂。

**证据**:
- 源码 AST: `grep -c "^def _run_write_model_configuration_manual_recovery_" write.py` → **14**
- Plan §1.2: "手动恢复 12 runner"；§2.1: "12 manual recovery runner"；Slice 7: "12 个 manual recovery runner"
- Plan §11c/§11e: 均正确列出全部 14 个（plan 自矛盾）

**遗漏的 2 个 runner（确切名称）**:
1. `_run_write_model_configuration_manual_recovery_incident_dossier`（行 1646）
2. `_run_write_model_configuration_manual_recovery_incident_dossier_revalidation`（行 1771）

**两者均为 Phase A dispatch 条目**（§11c entries #2 和 #1），均有对应 adapter（§11e: `_run_incident_dossier_adapter` 和 `_run_incident_dossier_revalidation_adapter`），均无 `execution_options` 参数、无 `snapshot_builder` 依赖。

**根因分析**: pre-v4.0 分析时将 `incident_dossier` / `incident_dossier_revalidation` 错误排除在 "手动恢复 runner" 之外。F-07（§1 行 69）已将 Phase A 统一为 14，§1.3 和 adapter 表均已更新，但 §1.2、§2.1、Slice 7 三个位置的 "12" 残留未清理。

**不存在替代 owner**: 这两个 runner 是标准的 Phase A manual recovery entry，语义上属于 `_write_manual_recovery.py`，与其他 12 个 runner 无异。不归 Slice 8 或其他模块所有。

### M-01 (MEDIUM) — §1.2 行范围 "783–2057" 与实际不符

**严重度**: MEDIUM。行范围标注用于辅助定位，不直接影响实施正确性，但会误导后续源码审计。

**证据**: 第一个 runner `evidence` 始于行 579，而非 783。最后一个 runner `incident_dossier_revalidation` 止于行 1886，而非 2057。行 783 实际位于 `evidence` runner 内部（约其 docstring 中部），行 2057 超出了所有 manual recovery 函数范围。

**修正**: 行范围应修正为 "579–1886"（14 runner）+ "1888–1933"（gate check）。

### L-01 (LOW) — Slice 7 描述未列出精确 14 函数名

**严重度**: LOW。其他 slice（Slice 2A/2B、Slice 8、Slice 11）均按函数名精确列举迁移目标。Slice 7 仅用模糊的 "12 manual recovery runner" 概括，增加了实施时的歧义风险。

---

## 3. 精确修正建议（可直接落盘）

### 3.1 修正 §1.2 功能域分组（plan 行 118）

**当前**:
```
| 手动恢复 12 runner | 783–2057 | ~1275 |
```
**修正为**:
```
| 手动恢复 14 runner | 579–1886 | ~1310 |
```
> 行数重估：14 个 runner 函数体跨度 579–1886（1308 行），加 gate check 1888–1933（46 行），合计 ~1354 行。

### 3.2 修正 §2.1 目标文件结构（plan 行 410）

**当前**:
```
|   ├── _write_manual_recovery.py         # 12 manual recovery runner + gate check
```
**修正为**:
```
|   ├── _write_manual_recovery.py         # 14 manual recovery runner + gate check
```

### 3.3 修正 Slice 7 描述（plan 行 980-983）

**当前**:
```
### Slice 7: C1 — _write_execution + _write_manual_recovery

**新建**: `_write_execution.py`（`_run_write_stage`, `_run_write_preflight`）+ `_write_manual_recovery.py`（12 个 manual recovery runner + `_check_write_model_configuration_manual_recovery_gate`）。
```

**修正为**:
```
### Slice 7: C1 — _write_execution + _write_manual_recovery

**新建**: `_write_execution.py`（`_run_write_stage`, `_run_write_preflight`）+ `_write_manual_recovery.py`（14 个 manual recovery runner + `_check_write_model_configuration_manual_recovery_gate`，合计 exact 15 个函数）。

14 个 runner 精确清单（按源码出现顺序）:
1. `_run_write_model_configuration_manual_recovery_evidence`
2. `_run_write_model_configuration_manual_recovery_plan`
3. `_run_write_model_configuration_manual_recovery_approval`
4. `_run_write_model_configuration_manual_recovery_application`
5. `_run_write_model_configuration_manual_recovery_verification`
6. `_run_write_model_configuration_manual_recovery_clearance`
7. `_run_write_model_configuration_manual_recovery_clearance_revocation`
8. `_run_write_model_configuration_manual_recovery_restart`
9. `_run_write_model_configuration_manual_recovery_gate_check`
10. `_run_write_model_configuration_manual_recovery_gate_verification`
11. `_run_write_model_configuration_manual_recovery_gate_revalidation`
12. `_run_write_model_configuration_manual_recovery_audit_timeline`
13. `_run_write_model_configuration_manual_recovery_incident_dossier`
14. `_run_write_model_configuration_manual_recovery_incident_dossier_revalidation`

其中 runner 4/5/6（application/verification/clearance）接受 `execution_options: ExecutionOptions` 参数且使用 `build_snapshot_builder` factory；其余 11 个 runner 仅接受 `args` + `paths_config`。
```

### 3.4 无需修改的位置（已正确）

以下位置均已正确列出 14 条目，无需修改：
- §1.3 Phase 边界 "Phase A 共 **14 条目**" ✅
- §11c Action Inventory 表（14 行）✅
- §11d Phase 常量表 `_WRITE_PHASE_EARLY_RECOVERY`（14 个 `_EarlyWriteSubcommandEntry`）✅
- §11e Adapter 列表（14 个 adapter 函数）✅
- §11f `run_write_command` 重构后结构（Phase A for-loop 遍历 14 条目）✅
- Slice 0 I-a Groups 1+2（11 bool + 3 path = 14）✅
- §11a `WriteDispatchArguments` Protocol（14 个 Phase A bool/path 字段）✅

### 3.5 下游同步检查清单

修正 "12→14" 后，以下项需逐项确认（无需修改文本，仅在实施 Slice 7 时作为门禁）：

| # | 检查项 | 预期 |
|---|---|---|
| 1 | `_write_manual_recovery.py` 函数数 | exact 15（14 runner + 1 gate check） |
| 2 | 其中含 `execution_options` 参数的 runner | exact 3（application, verification, clearance） |
| 3 | 其中含 `build_snapshot_builder` import 和调用 | exact 3（同上） |
| 4 | 从 `_write_config_helpers` import `MODULE` | 15 个函数中所有使用日志的函数 |
| 5 | `write.py` 删除旧定义后残留 `_run_write_model_configuration_manual_recovery_*` 定义 | 0 |
| 6 | `write.py` 残留 `_check_..._gate` 定义 | 0 |
| 7 | `write.py` 对 `_write_manual_recovery` 的 import | 15 个函数均通过顶层 import 引用 |
| 8 | Slice 11 Phase A dispatch table 条数 | 14（不受影响，已正确） |
| 9 | `pyright dayu/cli/` | 0 errors |
| 10 | 逐文件 coverage | `_write_manual_recovery.py` ≥ 80% |
| 11 | Ruff F/I finding-code multiset delta vs HEAD | 0 |
| 12 | 无循环 import（`_write_manual_recovery.py` → `_write_snapshot_builder.py` → `_write_config_application.py` 单向） | ✅ 已验证 |

### 3.6 不是 erratum 的项（明确排除）

以下 **不需要修改**：
- **Slice 8 scope 不变**: Slice 8 迁移 exact 13 Challenger 函数 + rollback runner，与 manual recovery runner 数无关。两个遗漏的 runner（incident_dossier / incident_dossier_revalidation）**不归 Slice 8**。
- **Phase A/B 计数不变**: Phase A=14、Phase B=2、总计=16 已在 §1.3、§11c 正确，无需改动。
- **`_check_..._gate` 归属不变**: 该函数属于 Phase C（非 Phase A dispatch），但语义上属于 manual recovery 域，放在 `_write_manual_recovery.py` 合理。无需挪动。
- **snapshot_builder factory 描述不变**: 当前 Slice 7 对 application/verification/clearance 三个 runner 的 factory handoff 描述已精确，不因 runner 总数修正而改变。
- **Adapter 表/Protocol 字段不变**: §11c/§11e adapter 列表、§11d phase 常量、§11a Protocol 字段均已正确列出 14 条目。

---

## 4. 开放问题（Open Issues）

| ID | 严重度 | 描述 | 建议处置 |
|---|---|---|---|
| O-01 | Low | Slice 7 原稿未列出精确 14 函数清单，实施时可能误将某个 runner 留在 write.py | 按 §3.3 修正后的精确清单逐函数迁移，AST grep 验证 write.py 残留=0 |
| O-02 | Low | `incident_dossier`（行 1646）内部调用 `build_write_model_configuration_manual_recovery_audit_timeline` 和 `build_write_model_configuration_manual_recovery_incident_dossier`——这两个 import 来自 `dayu.services` 层，迁移到 `_write_manual_recovery.py` 后 import 路径不变，无循环风险 | 实施时自然验证 |
| O-03 | Info | §1.2 "手动恢复 12 runner" 的行范围 783–2057 跨度约 1275 行。修正为 14 runner 后，行数重估约 ~1308 行（runner 体）+ ~46 行（gate check）= ~1354 行。不影响 Slice 6 diff 预估 | 仅更新文档数字 |

---

## 5. 总结

**Verdict: FAIL** — 一个 HIGH finding（runner count 12≠14）阻止 Slice 7 直接实施。修正方案极小：三处文本 "12"→"14"，外加 Slice 7 补充精确 14 函数清单。Phase A adapter 表、dispatch 常量、Protocol 字段等核心设计均已正确（14 条目），无需变更。

**修正工作量**: 约 3 处文本替换 + Slice 7 补充函数清单，预计 < 10 行变更。修正后 Slice 7 即可实施，无架构重设计需求。

**实施后门禁**: 14 runner + 1 gate check = exact 15 函数进入 `_write_manual_recovery.py`；`write.py` 残留旧定义为 0；pyright 0 errors；coverage ≥ 80%；Ruff delta 0；循环 import 0。

---

*审查工具: planreview skill / DeepSeek model / 基线 b55f794*
