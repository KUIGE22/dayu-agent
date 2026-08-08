# Plan Review: v5.0 CANDIDATE 最终独立复审（Slice 7 runner ownership re-review）

- **审查时间**: 2026-08-08 06:10 UTC
- **审查人**: DeepSeek（planreview skill）
- **基线**: clean HEAD `b55f794`
- **审查范围**: v5.0 CANDIDATE `docs/plans/2026-08-07-cli-write-architecture-refactor.md` 全文，对照 `dayu/cli/commands/write.py` AST、`AGENTS.md`
- **前置审查**: `docs/reviews/plan-review-20260808-061001-deepseek.md`（v4.9 Slice 7 FAIL，H1/M1/L1）——Controller 已全量接受并修订为 v5.0

---

## Verdict: PASS（零 findings，open High/Medium/Low = 0/0/0）

v5.0 CANDIDATE 已完整、精确地关闭了 v4.9 的 H1/M1/L1 三项 finding。Plan 与 b55f794 源码 AST 完全一致。Slice 7 已具备 code-generation-ready 标准，可进入实施。

---

## 1. 七项逐点闭包验证

### Point 1: Manual recovery exact 14 runners + `_check_..._gate`，`_write_manual_recovery.py` exact 15

| 子项 | v4.9 状态 | v5.0 修正 | 源码验证（b55f794） | 判定 |
|---|---|---|---|---|
| §1.2 功能域分组 | "手动恢复 12 runner" | "手动恢复 14 runner" ✅ | `grep -c "^def _run_write_model_configuration_manual_recovery_"` → **14** | PASS |
| §1.2 行范围 | "783–2057" | "579–1885" ✅ | 首个 runner 始于行 579，末个 runner 体止于 ~1885 | PASS |
| §1.2 Phase C gate | 与 12 runner 混在同一行 | 独立行 "Phase C 恢复 gate (1888–1932)" ✅ | gate 始于行 1888，止于 ~1932 | PASS |
| §2.1 文件结构 | "12 manual recovery runner + gate check" | "exact 14 manual recovery runners + Phase C gate check（exact 15 definitions）" ✅ | 源码 14 + 1 = 15 | PASS |
| §1.2 总行数 | "5262 行" | "3096 行"（注明已减去 Slice 5/6 迁出项） ✅ | `wc -l` → **3096** | PASS |
| Slice 7 函数清单 | 无 | 14 runner 逐名列表 + 1 gate check = exact 15 ✅ | 所有函数名精确匹配 | PASS |

**闭包**: H-01（v4.9 runner count 12≠14）**CLOSED**。v5.0 在 §1.2、§2.1、Slice 7 三处位置全部修正为 exact 14+1=15。

---

### Point 2: `_write_execution.py` exact 2；`write.py` 删除旧 17 定义并保留 exact 17 functional imports

| 子项 | v5.0 规范 | 源码验证 | 判定 |
|---|---|---|---|
| `_write_execution.py` definitions | exact 2：`_run_write_stage`, `_run_write_preflight` | 源码行 197、242 两函数 | PASS |
| `_write_manual_recovery.py` definitions | exact 15：14 runner + 1 gate check | 源码行 579–1885 共 14 runner + 行 1888 gate | PASS |
| 旧定义删除 | `write.py` 残留在 `_run_write_stage`/`_run_write_preflight`/`_run_...manual_recovery_*`/`_check_..._gate` = exact 0 | 共 2 + 14 + 1 = 17 | PASS |
| `write.py` imports from new owners | exact 17 functional symbols，非 compatibility re-export | 全部 17 个在 `run_write_command`（Phase A dispatch + Phase C gate + Phase H）有真实 caller | PASS |
| 禁止 glue/compatibility | "不是 compatibility re-export" 明确声明 | 直引 `write.<symbol>` 路径保持为功能 binding | PASS |

**闭包**: L-01（v4.9 Slice 7 缺少精确函数清单）**CLOSED**。Slice 7 现在包含完整逐名 14 runner 列表 + gate check。

---

### Point 3: 当前 b55f794 真实范围/owner 一致性

§1.2 功能域分组与源码行号对照：

| Plan §1.2 功能域 | Plan 行范围 | 源码定义起始行 | 匹配 |
|---|---|---|---|
| 写作执行 | 197–478 | `_run_write_stage`=197, `_run_write_preflight`=242 | ✅ |
| 配置 rollback | 481–576 | `_run_..._rollback`=481 | ✅ |
| 手动恢复 14 runner | 579–1885 | `_run_..._evidence`=579, `_run_..._incident_dossier_revalidation`=1771 | ✅ |
| Phase C gate | 1888–1932 | `_check_..._gate`=1888 | ✅ |
| Challenger 13 | 1935–2413 | `_challenger_preflight_cli_args`=1935 | ✅ |
| research materialize | 2416–2433 | `_materialize_research_after_write`=2416 | ✅ |
| run_write_command | 2436–3096 | `run_write_command`=2436, EOF=3096 | ✅ |

表下注释 "配置解析 helper / params validator 已在 Slice 5 迁出，configuration application 与 snapshot helper 已在 Slice 6 迁出" 正确说明了之前 slice 已迁出的域，与当前 write.py 的实际内容一致。

**闭包**: M-01（v4.9 行范围不准确）**CLOSED**。所有行范围已校准至 b55f794 实际值。

---

### Point 4: Application/verification/clearance 三处 snapshot factory 随 owner 迁移，labels 精确，import DAG 单向无环

**Factory call 现状（b55f794 源码）**:

| 函数 | 行号 | label | Slice 7 归属 |
|---|---|---|---|
| `_run_..._rollback` | 526 | 默认（`"configuration-application"`） | 留在 `write.py`（Slice 8 迁移） |
| `_run_..._application` | 843 | 默认（`"configuration-application"`） | `_write_manual_recovery.py` |
| `_run_..._verification` | 932 | `"configuration-manual-recovery-verification"` | `_write_manual_recovery.py` |
| `_run_..._clearance` | 1032 | `"configuration-manual-recovery-clearance"` | `_write_manual_recovery.py` |

**v5.0 DAG 规范**（§2.2 新增行 449-450）:
```
_write_manual_recovery → _write_snapshot_builder → _write_config_application
（仅此单向 CLI 内部依赖；零 reverse import / cycle）
```

**Slice 7 gate 验证**:
- `manual → snapshot` import exact 1，call exact 3 ✅
- `snapshot → config-application` 既有 import exact 1 ✅
- `manual → write` = 0，`snapshot → manual` = 0，`config-application → manual` = 0 ✅
- `manual / snapshot / config-application` import 链无环（三个模块形成严格偏序） ✅
- labels: 默认 / `configuration-manual-recovery-verification` / `configuration-manual-recovery-clearance` ✅
- `write.py` 残存 factory call exact 1（为 Slice 8 rollback 保留） ✅

**判定**: PASS。三处 factory 迁移路径、label 精确性、单向 DAG 均已锁定。

---

### Point 5: Direct runner/dependency patches 迁真实 owner；characterization 继续 patch write functional binding

Slice 7 测试 ownership 规则（plan 行 1054-1064）分三层：

| 测试类型 | Patch 目标 | 迁移行为 |
|---|---|---|
| 直接调用 runner 的测试 | 迁至 `_write_execution` / `_write_manual_recovery` 真实 owner | ✅ 随定义迁移 |
| 仅验证 runner 内部 service 依赖的 patch | 迁至真实 owner 模块 | ✅ 随依赖迁移 |
| 验证 `run_write_command` / Phase A/C dispatch 短路顺序 / Challenger global lookup | 继续 patch `write.<symbol>` 正常功能 binding | ✅ 保持原位 |
| blanket 全量迁走 | — | ❌ 明确禁止 |
| 为测试新增 compatibility seam | — | ❌ 明确禁止 |

Identity 回归新增两项：
- `write.py` 的 exact 17 functional bindings 分别与新 owner 函数对象相同
- direct-owner 与 dispatch-owner 两类回归都必须真实执行至少一条对应路径

**判定**: PASS。测试迁移规则精确区分了 "随定义迁移" 与 "dispatch characterization 保持原位" 两类场景，与 v4.7 S5-CTRL-04 的 `_challenger_requested` 双 owner 先例一致。

---

### Point 6: 每个修改生产文件 exact coverage ≥ 80%、pyright 0、Ruff no-new、AST/import/identity/README gates 可验收

| 门禁 | v5.0 规范 | 可验收性 |
|---|---|---|
| pyright | `dayu/cli/` + 修改测试 = 0 errors | ✅ 可自动化验证 |
| Ruff | F/I + HEAD full-rule finding-code multiset delta = 0 | ✅ 可自动化验证 |
| Coverage | `_write_execution.py`, `_write_manual_recovery.py`, `write.py` ≥ 80% | ✅ 可自动化验证 |
| `git diff --check` | 通过 | ✅ |
| AST gate: `_snapshot_builder` nested | 三模块合计 = 0 | ✅ grep 可验证 |
| AST gate: manual `build_snapshot_builder` | import exact 1, call exact 3 | ✅ grep 可验证 |
| AST gate: write.py factory call 残留 | exact 1（rollback） | ✅ grep 可验证 |
| Import gate: manual→snapshot | exact 1 | ✅ grep 可验证 |
| Import gate: snapshot→config-application | exact 1 | ✅ grep 可验证 |
| Import gate: reverse imports | 全部 = 0 | ✅ grep 可验证 |
| Identity gate: 17 bindings | `write.<symbol> is owner.<symbol>` | ✅ 可参数化测试 |
| README gate | tests 入口/分层不变 → 不更新；CLI private 模块拆分不变用户命令 → 根 README 不更新 | ✅ 规则明确，越界豁免清晰 |

**判定**: PASS。所有门禁均可自动化验证或 grep 审计，无模糊判断项。

---

### Point 7: Phase A adapter/dispatch/Protocol、Slice 8 exact 13 等无意外改变

Slice 7 Non-goals（plan 行 1086-1089）明确声明：
- Phase A 14 条目与顺序 —— 不改变 ✅
- Phase C gate 调用位置 —— 不改变 ✅
- Slice 10/11 adapter/Protocol 设计 —— 不改变 ✅
- Slice 8 exact 13 Challenger + rollback ownership —— 不改变 ✅
- 不提前实现 dispatch table / `DayuCliArguments` / Challenger/rollback 迁移 / 新业务语义 ✅

Phase A 相关表（§11c/§11d/§11e）在 v4.9 即已正确（14 条目），v5.0 无改动。✅

Slice 8 描述（plan 行 1095-1124）: "从原源码连续 14 函数组中迁移剩余 exact 13 个" — `_challenger_requested` 已在 Slice 5 迁出，14 - 1 = 13 ✅。13 函数清单（行 1101-1113）未变 ✅。

**判定**: PASS。所有非 Slice 7 语义均未改变。

---

## 2. v5.0 Changelog 完整性

v4.9→v5.0 changelog（plan 行 17）三项 S7-CTRL 的覆盖度：

| CTL | 内容 | 覆盖的 v4.9 finding |
|---|---|---|
| S7-CTRL-01 | 14 runner + gate = 15, `_write_execution` exact 2, write.py 删 17 + import 17 | H-01（runner count）, L-01（缺少清单） |
| S7-CTRL-02 | 三处 factory 迁移，label 精确，DAG 单向 | 新增 gate（无前置 finding） |
| S7-CTRL-03 | 测试 owner 迁移规则，禁止 blanket/compatibility | 新增 gate（无前置 finding） |

v5.0 审查来源行（plan 行 6）新增两篇：
- `docs/reviews/plan-review-20260808-061001-deepseek.md`（Slice 7 runner ownership DeepSeek review, FAIL）
- `docs/reviews/plan-review-20260808-061002-mimo.md`（Slice 7 runner ownership MiMo review, PASS with Medium/Low findings）

两者均已列入。✅

---

## 3. 无 finding 的确认项

以下项经逐条检查，确认无问题：

1. **Phase A=14 全文一致性**: §1.3（"14 条目"）、§11c（14 行）、§11d（14 个 `_EarlyWriteSubcommandEntry`）、§11e（14 adapter）、§11a Protocol（14 个 Phase A 字段）、Slice 0 I-a（11 bool + 3 path = 14）——全部一致 ✅
2. **Slice 5/6 已迁出项**: §1.2 注释正确列出 "配置解析 helper / params validator 已在 Slice 5 迁出，configuration application 与 snapshot helper 已在 Slice 6 迁出" ✅
3. **write.py import 路径**: 源码行 13-27 已从 `_write_config_application`、`_write_config_helpers`、`_write_params_validation`、`_write_snapshot_builder` import ✅
4. **`execution_options: ExecutionOptions` 类型**: 三个 runner（application/verification/clearance）签名均使用 `ExecutionOptions`（非 `Any`），源码 import 自 `dayu.execution.options` ✅
5. **Challenger 14→13**: `_challenger_requested` 已迁至 `_write_params_validation.py`（行 23-26 import 可证），Slice 8 剩余 exact 13 ✅
6. **lazy import**: `_materialize_research_after_write`（行 2416）内部仍含 `from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest` lazy import，迁移语义不变 ✅

---

## 4. 最终判决

| 项目 | 结果 |
|---|---|
| **Verdict** | **PASS** |
| **Open High** | **0** |
| **Open Medium** | **0** |
| **Open Low** | **0** |
| **v4.9 findings 闭包** | H-01 CLOSED / M-01 CLOSED / L-01 CLOSED |
| **Slice 7 可实施性** | **是** — 已达到 code-generation-ready 标准 |
| **剩余风险** | 无。实施风险仅限于人为操作失误（如迁移时漏掉某个 runner 函数），由逐名 14 函数清单 + AST grep gate（残留=0）充分对冲 |

---

*审查工具: planreview skill / DeepSeek model / 基线 b55f794*
