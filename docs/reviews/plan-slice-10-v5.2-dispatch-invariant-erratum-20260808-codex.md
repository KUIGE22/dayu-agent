# Slice 10 v5.2 Dispatch Invariant Erratum（Codex Controller）

- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **基线**: clean HEAD `8eface5`（`gateflow: accept research template module split slice 9`）
- **计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- **状态**: v5.2 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: 仅修正 Slice 10 research-template dispatch/selector 行为契约与验证边界；production、tests、README 及其他 slice 语义不变

## 审查输入

- DeepSeek: `docs/reviews/plan-review-20260808-095100-deepseek.md`
- MiMo: `docs/reviews/plan-review-20260808-095101-mimo.md`
- DeepSeek final re-review: `docs/reviews/plan-review-20260808-101000-deepseek.md`
- MiMo final re-review: `docs/reviews/plan-review-20260808-101001-mimo.md`
- HEAD 实现: `dayu/cli/commands/research_template.py` 的
  `run_research_template_command`
- 行为证据: `tests/application/test_write_cli_dispatch.py`、
  `tests/cli/test_research_template_definitions.py`

## Controller 裁决

### DeepSeek

| Finding | 裁决 | 计划修正 |
|---|---|---|
| S10-R1（未知 action `return 2`） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | S10-CTRL-03 锁定未知 action 无输出、返回 `1`；入口禁止 `return 2` |
| S10-R2（丢失 try/except） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | mapping lookup、runner-none 分支和 runner 调用均置于 `try`；精确保留三类异常、stderr 文本与返回 `1` |
| S10-R3（新增 `Log.error` 输出） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 删除计划中的新增输出；未知 action 保持静默，禁止 `Log` |
| S10-R4（未定义 `MODULE`） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 入口禁止 `MODULE`，不新增 research-template 日志常量或依赖 |
| S10-R5（selector fallback 漂移） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | selector 使用 HEAD 等价的 exact `str(getattr(..., "") or "").strip().lower()`；不是缺少 `str`/`or ""` 的弱化版本 |
| S10-R6（direct tests 范围不显式） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 列出 direct fixture owner 文件，并要求 implementation 以 AST/`rg` 穷尽 45 个目标函数的直接调用 |

### MiMo

| Finding | 裁决 | 计划修正 |
|---|---|---|
| H01（runner 异常处理丢失） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 同 S10-R2，保留 exact catch tuple、stderr 与返回码 |
| H02（未知 action 退出码/输出漂移） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 同 S10-R1/R3；在 MiMo 给出的两个选项中采用完全等价的静默方案 A |
| M01（`Log`/`MODULE` 未定义） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 同 S10-R4；禁止引入二者而不是扩张依赖面 |
| M02（selector 直接字段语义漂移） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 同 S10-R5；保留 missing/`None`/非字符串 defensive corpus |
| L01（39 mapping 一致） | **ACCEPTED EVIDENCE / CLOSED-NON-DEFECT** | 39 条 mapping 已逐项闭合，继续由参数化矩阵锁定，无修复项 |
| L02（runner 内部 `getattr` 边界不清） | **ACCEPT CLARIFICATION / CLOSED-BY-PLAN-TEXT** | 表外 runner/helper 内部存量 `getattr` 明确为 Slice 10 non-goal，不借类型传播顺手改行为 |
| L03（selector 未列 deliverable） | **ACCEPT CLARIFICATION / CLOSED-BY-PLAN-TEXT** | selector 明确列为 Slice 10 deliverable，但其 Protocol 参数不计入 `DayuCliArguments` 传播计数 |

## S10-CTRL-03：入口 dispatch/error exact contract

计划现锁定以下不可拆分顺序与行为：

1. `setup_loglevel(args)` 顺序不变。
2. 调用 selector 得到 action。
3. `try` 内执行 mapping lookup；runner 为 `None` 时无 stdout/stderr 且返回 `1`。
4. runner 存在时直接 `return runner(args)`。
5. 精确捕获 `(FileNotFoundError, FileExistsError, ValueError)`，执行
   `print(f"research-template error: {exc}", file=sys.stderr)` 后返回 `1`。
6. 禁止 `Log`、`MODULE`、新错误输出或 `return 2`。

该契约修复 v5.1 exact code 与 §4.2、HEAD characterization 的直接矛盾，不改变
mapping、runner、类型 owner 或其他 slice。

## S10-CTRL-04：selector 与计数边界

selector exact body 为：

```python
return str(getattr(args, "research_template_action", "") or "").strip().lower()
```

该唯一有界 `getattr` 只保留 HEAD 对缺字段、`None`、非字符串值的 runtime defensive
语义；`ResearchTemplateDispatchArguments` 继续承担正常调用路径的静态类型边界。
runner 内部表外存量 `getattr` 不迁移、不重写。

计数仍为 **45 args + 1 return**：research-template entry 1 + runners 39 + write
entry 1 + Slice 6 config-application 2 + snapshot-builder 2 = 45；
`parse_arguments` return = 1。selector 是额外 deliverable，其参数为 Protocol，故既不
遗漏也不增加 `DayuCliArguments` 机械传播计数。

## 验证契约

- 39-key mapping 参数化矩阵逐项验证 key、runner 与真实调用。
- 未知 action 断言返回 `1` 且 stdout/stderr 都为空。
- runner 分别抛 `FileNotFoundError`、`FileExistsError`、`ValueError`，逐项断言
  `research-template error: {exc}\n` 的精确 stderr 与返回 `1`。
- selector 对 missing、`None`、非字符串值与普通大小写/空白 corpus 的结果与 HEAD
  相同。
- direct fixture owner 至少覆盖计划列出的六个测试文件；以 AST/`rg` 对 45 个目标
  函数直接调用做穷尽审计，不 blanket 修改表外 Namespace fixture。
- pyright、Ruff、targeted signature/mapping/entry AST gates、逐文件 coverage 与
  `git diff --check` 保持 Slice 10 原门禁。
- stale audit：入口中 `Log`、`MODULE`、未知 action 新输出、`return 2` 均为 0；
  selector exact bounded fallback 为 1。

## 范围与残余风险

- 本 erratum 只改 master plan 和本 Controller artifact；未改 production、tests、
  README 或外部 review artifacts。
- v5.1 accepted 历史保留；v5.2 已通过双路 final plan re-review，Slice 10 可实施。
- 未知 action 的 silent behavior 与精确 stderr 依赖行为测试共同保护；剩余风险是实施
  时误把表外 runner `getattr` 纳入机械清理，已由 non-goal 与 targeted gate 限制。

## Final dual plan re-review closure

- DeepSeek `docs/reviews/plan-review-20260808-101000-deepseek.md`: **PASS**，
  095100 的 S10-R1..R6 为 6/6 CLOSED，open High/Medium/Low=0/0/0。
- MiMo `docs/reviews/plan-review-20260808-101001-mimo.md`: **PASS**，
  095101 的 H01/H02/M01/M02/L01..L03 为 7/7 CLOSED，open
  High/Medium/Low=0/0/0。
- 两路合计 13 observations 全部 CLOSED，无新增 finding；Controller 正式接受
  S10-CTRL-03/04。v5.2 达到 code-generation-ready，Slice 10 可按计划实施。
