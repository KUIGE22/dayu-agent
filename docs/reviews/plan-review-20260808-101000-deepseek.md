# Plan Review: v5.2 Slice 10 Dispatch Invariant Erratum — Targeted Re-Review

- **日期**: 2026-08-08
- **审查类型**: v5.2 targeted re-review（基于 095100 初审 S10-R1..R6 逐项核验）
- **初审 artifact**: `docs/reviews/plan-review-20260808-095100-deepseek.md`（FAIL, 6 findings）
- **Controller erratum**: `docs/reviews/plan-slice-10-v5.2-dispatch-invariant-erratum-20260808-codex.md`
- **审查计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.2 CANDIDATE）
- **审查分支**: `codex/dual-model-research-mvp`
- **审查 HEAD**: `8eface5`
- **审查人**: DeepSeek (planreview skill, re-review pass)

---

## 1. Re-Review 范围

仅核验 095100 初审的 6 项 findings（S10-R1..R6）是否被 v5.2 erratum 完全修正。根据 Controller 要求逐项确认：

1. selector exact 保持 `getattr`/`str`/`or ""`/`strip`/`lower`
2. entry `setup_loglevel` 顺序不变、try 内 mapping+runner、未知 action 静默 `return 1`
3. 三异常精确 stderr `research-template error: {exc}` + `return 1`
4. Slice 10 fenced code 零 `Log`/`MODULE`/`return 2`
5. 39 mapping 完整、45 args + 1 return 计数、fixture/test owner 清单、表外 getattr non-goal 明确
6. 其他 slice 零语义变化

---

## 2. 逐项核验

### S10-R1（高）— 未知 action return 2 vs return 1

| 证据来源 | 位置 | 内容 |
|---|---|---|
| v5.2 入口代码 | plan `:1648-1649` | `if runner is None: return 1` |
| v5.2 §4.2 不变量 | plan `:606` | `run_research_template_command` 退出码不变（含未知 action 与 caught exception 返回 1） |
| S10-CTRL-03 | plan `:613-614` | 未知 action 不产生 stdout/stderr 并返回 `1` |
| 禁止 return 2 | plan `:1658` | 禁止 `return 2` |
| stale audit gate | plan `:1701-1702` | `return 2` 命中为 0 |

**裁决: CLOSED** — v5.2 exact 代码中 `return 2` 已删除，替换为 `return 1`。§4.2 不变量表已显式补充 "含未知 action 与 caught exception 返回 1"。S10-CTRL-03 锁定禁止 `return 2`。

---

### S10-R2（高）— try/except 异常处理被移除

| 证据来源 | 位置 | 内容 |
|---|---|---|
| v5.2 入口代码 | plan `:1646-1653` | `try:` 覆盖 `runner = mapping.get(action)`、`return 1`（None 分支）、`return runner(args)` |
| except 元组 | plan `:1651` | `except (FileNotFoundError, FileExistsError, ValueError) as exc:` — 与 HEAD `:181` 精确一致 |
| stderr 文本 | plan `:1652` | `print(f"research-template error: {exc}", file=sys.stderr)` — 与 HEAD `:182` 精确一致 |
| 返回码 | plan `:1653` | `return 1` — 与 HEAD `:183` 精确一致 |
| try 覆盖范围约束 | plan `:1656` | try 必须覆盖 mapping lookup、未知 action 分支与 runner 调用 |
| 顺序约束 | plan `:1656-1657` | `setup_loglevel(args)` 和 selector 调用顺序不得移动 |

**裁决: CLOSED** — try/except 完整保留，catch tuple、stderr 文本、返回码与 HEAD 逐字符一致。try 覆盖范围（mapping lookup + None 分支 + runner 调用）与 HEAD 语义等价（HEAD 的 39 个 `if action ==` 分支 + `return runner()` 也在 try 内）。

---

### S10-R3（中）— 未知 action 新增 Log.error 输出

| 证据来源 | 位置 | 内容 |
|---|---|---|
| v5.2 入口代码 | plan `:1648-1649` | `if runner is None: return 1` — 无任何 print/Log |
| 禁止 Log | plan `:1657-1658` | 入口禁止 import/引用 `Log` |
| 禁止新增输出 | plan `:1658` | 禁止新增未知 action 输出 |
| stale audit gate | plan `:1701-1702` | `Log`/未知 action 新输出 为 0 |

**裁决: CLOSED** — `Log.error` 行已删除。未知 action 静默 `return 1`，与 HEAD 行为一致。入口显式禁止 import `Log`。

---

### S10-R4（中）— MODULE 常量未定义

| 证据来源 | 位置 | 内容 |
|---|---|---|
| 禁止 MODULE | plan `:1657-1658` | 入口禁止 import/引用 `MODULE` |
| 代码中无 MODULE | plan `:1632-1653` | 入口函数全文零 `MODULE` 引用 |
| stale audit gate | plan `:1701-1702` | `MODULE` 命中为 0 |

**裁决: CLOSED** — `MODULE` 引用已随 `Log.error` 一并删除。入口函数不引用任何未定义常量。

---

### S10-R5（低）— Protocol 直接字段访问 vs getattr fallback

| 证据来源 | 位置 | 内容 |
|---|---|---|
| v5.2 selector exact body | plan `:1552` | `return str(getattr(args, "research_template_action", "") or "").strip().lower()` |
| HEAD 等价性 | `research_template.py:101` | `str(getattr(args, "research_template_action", "") or "").strip().lower()` — 逐字符一致 |
| §4.3 有界例外 | plan `:623-627` | selector 唯一有界 `getattr` 例外，保留 defensive 语义；Protocol 仍为静态类型边界 |
| S10-CTRL-04 | Controller `:61-68` | selector exact body 锁定；唯一有界 getattr；runner 内部表外 getattr 不迁移 |
| 定性说明 | plan `:1555-1557` | "唯一、精确、有界的 selector 例外...不能扩展成一般反射式参数访问" |

**裁决: CLOSED** — selector body 与 HEAD 逐字符一致，完整保留缺字段/None/非字符串值的 defensive 语义。Protocol 参数注解保留静态类型校验能力。有界例外在 §4.3 和 S10-CTRL-04 中均有明确约束。

---

### S10-R6（低）— 45 签名传播表未覆盖 tests/cli 测试文件

| 证据来源 | 位置 | 内容 |
|---|---|---|
| direct fixture owner 清单 | plan `:1671-1678` | 列出 6 个测试文件：`test_research_template_command.py`、`test_research_template_definitions.py`、`test_write_cli_dispatch.py`、`test_write_challenger.py`、`test_cli_running_config.py`、`test_write_model_configuration_preapplication.py` |
| AST/rg 穷尽审计 | plan `:1677-1678` | 实施时以 AST/`rg` 对 45 个目标函数的全部直接调用复核，不得 blanket 改动表外 Namespace fixture |
| 45 args + 1 return 计数 | plan `:1572-1577` | 明确 45 args（1+39+1+2+2）+ 1 parse return；selector 不计入 |
| S10-CTRL-04 计数 | Controller `:71-74` | selector 是额外 deliverable，参数为 Protocol，不遗漏也不增加 DayuCliArguments 机械传播计数 |

**裁决: CLOSED** — 测试文件修改范围已完整列出（6 个文件），覆盖了 095100 初审指出的 `tests/cli/test_research_template_definitions.py` 和 `tests/application/test_write_cli_dispatch.py`。45 计数澄清（之前 v5.1 写 "45" 但实际为 46 含 entry 自身，现在澄清为 45 args + 1 return = parse_arguments 返回另计）。

---

## 3. 其他契约核验

### 3.1 setup 顺序

plan `:1644-1645`：`setup_loglevel(args)` → `action = _resolve_research_template_action(args)` → `try:`。与 HEAD `:100-102` 顺序一致（`setup_loglevel(args)` → `action = ...` → `try:`）。**通过**。

### 3.2 39 mapping 完整性

plan `:1587-1627`：39 条目。对照 HEAD 39 个 `if action == "..."` 分支和 §1.5 的 39 action key 列表，一一对应。**通过**。

### 3.3 表外 getattr non-goal

plan `:1577`："39 runners 内部表外 helper/`getattr` 保持原样"；plan `:1699-1700`："runner 内部存量 `getattr` 也不属于本 Slice"。S10-CTRL-04 `:68`："runner 内部表外存量 `getattr` 不迁移、不重写"。**通过**。

### 3.4 其他 slice 零语义变化

v5.1→v5.2 changelog（plan `:28`）："其余 slice 零语义变化"。v5.2 仅修改 Slice 10 入口行为契约和 selector 定义，不触及 Slice 0–9 和 11–13。**通过**。

### 3.5 新增入口行为矩阵

plan `:1679-1682` 新增三项显式测试门禁：
- 未知 action：stdout/stderr 均为空 + 返回 `1`
- 三类异常：逐项断言 `research-template error: {exc}\n` + 返回 `1`
- selector defensive corpus：缺字段/None/非字符串值 vs HEAD

这些门禁直接保护了 S10-R1/R2/R3/R5 的不变量，防止未来回归。**充分**。

### 3.6 stale audit gates

plan `:1701-1702`：`Log`/`MODULE`/未知 action 新输出/`return 2` 为 0。这四个 targeted gate 以自动化 grep/AST 方式锁定了 v5.1 引入的全部四个缺陷。**充分**。

---

## 4. Verdict

**PASS** — 6/6 初审 findings 全部 CLOSED。

| Finding | 095100 Severity | v5.2 Status | Evidence |
|---|---|---|---|
| S10-R1 (return 2→1) | HIGH | **CLOSED** | entry `:1648-1649`, §4.2 `:606`, S10-CTRL-03 `:613-614` |
| S10-R2 (try/except 丢失) | HIGH | **CLOSED** | entry `:1646-1653`, try 覆盖范围 `:1656` |
| S10-R3 (Log.error 新增) | MEDIUM | **CLOSED** | entry `:1648-1649` 静默, 禁止 Log `:1657` |
| S10-R4 (MODULE 未定义) | MEDIUM | **CLOSED** | 禁止 MODULE `:1657-1658`, stale audit `:1701-1702` |
| S10-R5 (getattr fallback) | LOW | **CLOSED** | selector `:1552` exact, §4.3 `:623-627`, S10-CTRL-04 |
| S10-R6 (test owner 不全) | LOW | **CLOSED** | fixture owner 6文件 `:1671-1678`, 45计数澄清 `:1572-1577` |

open High/Medium/Low = **0/0/0**。

v5.2 Slice 10 入口 dispatch contract 已达到 code-generation-ready。Controller erratum S10-CTRL-03/04 正确修正了 v5.1 的所有契约冲突，行为不变量、错误处理、selector 语义与验证边界均已自洽。
