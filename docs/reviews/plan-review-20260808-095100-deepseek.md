# Plan Review: v5.1 Slice 10 Dispatch Contract Conflict

- **日期**: 2026-08-08
- **审查目标**: accepted v5.1 master plan（`docs/plans/2026-08-07-cli-write-architecture-refactor.md`）Slice 10 — Protocol dispatch + argument type ownership（C4-01）
- **审查范围**: §4.2 行为不变量、S10-CTRL-01、S10-CTRL-02、C4-01、Slice 10 exact code block (line 1596–1603)、当前 HEAD `8eface5` 的 `research_template.py:97-184`、characterization tests
- **审查分支**: `codex/dual-model-research-mvp`
- **审查 HEAD**: `8eface5`
- **审查类型**: focused adversarial plan review — dispatch contract conflict
- **审查人**: DeepSeek (planreview skill)

---

## 1. 审查目标与范围

本 review 仅聚焦 Slice 10 的 `run_research_template_command` 入口函数重构契约冲突。不审查 Slice 10 的 arguments.py 类型定义、45 签名机械传播、parse_arguments 运行时契约等其他方面。

### 1.1 关键证据来源

| 证据 | 路径 | 关键行 |
|---|---|---|
| Master plan §4.2 行为不变量 | `docs/plans/2026-08-07-cli-write-architecture-refactor.md:599-609` | "退出码不变"、"错误消息文本不变" |
| Slice 10 exact 入口代码 | 同上 `:1596-1603` | `return 2`、`Log.error`、无 try/except |
| HEAD 当前入口实现 | `dayu/cli/commands/research_template.py:97-184` | try/except (FileNotFoundError, FileExistsError, ValueError) → `return 1`、fallthrough `return 1` |
| Characterization test (unknown action) | `tests/application/test_write_cli_dispatch.py:1375-1383` | `assert exit_code == 1` |
| Characterization test (runtime error) | `tests/cli/test_research_template_definitions.py:190-196` | `assert result == 1`、`"research-template error" in stderr` |
| AGENTS 硬约束 | `AGENTS.md:33-51` | 编码硬约束、禁止兼容性代码 |

### 1.2 Assumptions Tested

1. Plan §4.2 的 "退出码不变" 对 `run_research_template_command` 的未知 action 分支也成立
2. Plan §4.2 的 "错误消息文本不变" 覆盖 stderr 输出 "research-template error: ..." 模式
3. Slice 10 入口代码是 code-generation-ready — implementation agent 可直接按此生成
4. Slice 10 不改变 characterization tests 已锁定的行为契约
5. `ResearchTemplateDispatchArguments` Protocol 的 `research_template_action: str` 直接字段访问在所有合法调用路径上等价于当前的 `getattr(args, "research_template_action", "")`

---

## 2. Findings

### S10-R1-未修复-高-未知 action 退出码 2 与 §4.2 "退出码不变" 自相矛盾

- **位置**: Master plan §4.2 行为不变量表（行 603-604）vs Slice 10 exact 入口代码（行 1596–1603）
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**:

  Plan §4.2 声明：
  > | 退出码不变（0/2/4/6/130） | CLI 集成测试 |
  > | `run_research_template_command` 退出码不变 | CLI 集成测试 |

  Slice 10 exact 入口代码（行 1596–1603）：
  ```python
  def run_research_template_command(args: DayuCliArguments) -> int:
      setup_loglevel(args)
      action = _resolve_research_template_action(args)
      runner = _RESEARCH_TEMPLATE_ACTION_DISPATCH.get(action)
      if runner is None:
          Log.error(f"未知 research-template 子命令: {action!r}", module=MODULE)
          return 2   # <--- 与 HEAD return 1 冲突
      return runner(args)
  ```

  HEAD `8eface5` 实际行为（`research_template.py:101,184`）：
  ```python
  action = str(getattr(args, "research_template_action", "") or "").strip().lower()
  try:
      if action == "list": ...
      # ... 39 if-checks
  except (FileNotFoundError, FileExistsError, ValueError) as exc:
      print(f"research-template error: {exc}", file=sys.stderr)
      return 1
  return 1   # <--- 未知 action: 静默 return 1
  ```

- **反例/失败场景**: 用户输入 `dayu-cli research-template nonexistent-subcommand`。HEAD 返回退出码 1（静默）。按 Slice 10 exact 代码实施后返回退出码 2 并打印 `Log.error`。任何依赖退出码 1 判断 "未知子命令" 的上层脚本（shell pipeline、CI、Makefile）全部断裂。
- **为什么有问题**: Plan 自身的 §4.2 不变量表明确要求退出码不变。Slice 10 代码直接违反该不变量，且无任何 erratum、controller ruling 或 changelog 条目记录此偏离。这不是主观偏好差异——plan 的两个部分给出了互相矛盾的指令，implementation agent 无法判断应以哪个为准。
- **直接证据**:
  1. Plan §4.2 表（行 603-604）：`退出码不变`、`run_research_template_command 退出码不变`
  2. HEAD `research_template.py:184`：`return 1`
  3. Plan Slice 10 代码（行 1602）：`return 2`
  4. Characterization test `test_unknown_action_returns_1`（`test_write_cli_dispatch.py:1375-1383`）：`assert exit_code == 1`
  5. 39 路 dispatch 的 ACTION_RUNNER_MAP（同文件 `:1283-1323`）：sentinel 值 101–139，无 sentinel=2
- **影响**: 实施 Agent 若按 exact 代码生成 → 退出码 2 不可逆地进入 CLI contract → characterization test 失败 → 必须回滚或追加 erratum commit。实施 Agent 若按 §4.2 保持 return 1 → 与 plan exact 代码不一致 → review 无法验收。无论哪种路径都产生返工。
- **建议改法和验证点**:

  最小修正——在 Slice 10 入口代码中将 `return 2` 改为 `return 1`，并删除 `Log.error(...)` 行（见下方 exact 文案）。修正后验证：
  - `pytest tests/application/test_write_cli_dispatch.py::TestResearchTemplateIfChain::test_unknown_action_returns_1` 通过
  - `rg 'return 2'` 在 `run_research_template_command` 函数体内命中为 0

- **修复风险**: 低 — 单行修改，不触及 mapping/selector/类型传播
- **严重程度**: **高** — plan 内 self-contradiction，阻止 code-generation-ready 验收

---

### S10-R2-未修复-高-try/except 异常处理被移除导致运行时错误契约断裂

- **位置**: Master plan Slice 10 exact 入口代码（行 1596–1603）vs HEAD `research_template.py:181-183`
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**:

  HEAD (`research_template.py:181-183`):
  ```python
  except (FileNotFoundError, FileExistsError, ValueError) as exc:
      print(f"research-template error: {exc}", file=sys.stderr)
      return 1
  ```

  Slice 10 exact 入口代码：**无 try/except 块**。`return runner(args)` 的任何异常都将直接向上传播。

- **反例/失败场景**: `dayu-cli research-template scorecard --name does-not-exist`。`load_research_template_definition("does-not-exist")` 抛出 `ValueError`。HEAD 行为：被 try/except 捕获 → stderr 输出 `research-template error: ...` → 返回退出码 1。Slice 10 实施后行为：`ValueError` 未被捕获 → 异常传播到 `main.py` → Python 打印原始 traceback 到 stderr → 退出码变为 1（未处理异常的系统默认）但 stderr 文本完全不同。
- **为什么有问题**:
  1. Plan §4.2 明确要求 "错误消息文本不变"——`research-template error:` 前缀被移除，stderr 输出从格式化单行变为原始 traceback
  2. Plan §4.2 要求 "退出码不变"——虽然未处理异常在 CPython 中默认 exit code 1，但这依赖于 `main.py` 不另行处理异常，且不是 plan 显式控制的契约
  3. Characterization test `test_run_scorecard_command_unknown_template_returns_error`（`test_research_template_definitions.py:190-196`）显式断言 `assert result == 1` 和 `assert "research-template error" in capsys.readouterr().err`——此测试在 Slice 10 实施后会失败
  4. 这不是 "runner 不应抛异常" 的理论假设——`_run_scorecard` → `load_research_template_definition` → `_load_yaml_definition` 对不存在的模板名抛 `ValueError`，这是当前生产路径

- **直接证据**:
  1. HEAD `research_template.py:181-183`：`except (FileNotFoundError, FileExistsError, ValueError) as exc:`
  2. Plan Slice 10 代码（行 1596–1603）：无 except 块
  3. `test_research_template_definitions.py:190-196`：断言 `research-template error` 在 stderr 中
  4. 39 个 runner 中至少 `_run_scorecard`（行 206）、`_run_evidence`（行 220）、`_run_schema`（行 235）、`_run_checklist`（行 259）、`_run_copy`（行 285）、`_run_materialize_checklist`（行 268）、`_run_compose`（行 315）等通过 `load_research_template_definition(str(getattr(args, "name")))` 调用，对无效模板名抛 `ValueError`

- **影响**: 实施 Agent 按 exact 代码生成 → characterization test 失败 → stderr 格式不可逆改变 → 上层脚本/日志解析断裂 → 必须回滚或追加 erratum commit

- **建议改法和验证点**:

  将 mapping lookup 和 runner call 放回现有的 try/except 块内。runner 为 None 时保持当前行为（静默 `return 1`，见 S10-R1）。修正后验证：
  - `pytest tests/cli/test_research_template_definitions.py::test_run_scorecard_command_unknown_template_returns_error` 通过
  - `pytest tests/application/test_write_cli_dispatch.py::TestResearchTemplateIfChain::test_unknown_action_returns_1` 通过
  - 所有 39 路 `test_action_dispatches_to_correct_runner` 仍通过

- **修复风险**: 低 — try/except 结构已存在于 HEAD，只需将新 dispatch 逻辑放入其中
- **严重程度**: **高** — 丢失现有错误处理契约，破坏 characterization test

---

### S10-R3-未修复-中-未知 action 新增 Log.error 输出违反 "错误消息文本不变"

- **位置**: Master plan Slice 10 exact 入口代码（行 1601）
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**:

  Slice 10 exact 代码（行 1601）:
  ```python
  if runner is None:
      Log.error(f"未知 research-template 子命令: {action!r}", module=MODULE)
      return 2
  ```

  HEAD 行为：未知 action 静默 `return 1`——**无任何 stderr 输出**。当前 if-chain 的 39 个分支都不匹配时直接 fall through 到 `return 1`，不打印任何消息。

- **反例/失败场景**: 用户输入 `dayu-cli research-template nonexistent-subcommand`。HEAD 行为：退出码 1，stderr 无输出。Slice 10 实施后行为：stderr 新增 `[APP.RESEARCH_TEMPLATE] [ERROR] 未知 research-template 子命令: 'nonexistent-subcommand'`（或类似格式），退出码变为 2（见 S10-R1）。
- **为什么有问题**: Plan §4.2 "错误消息文本不变" 意味着不应新增或修改 stderr/stdout 输出。当前无输出的行为被 Log.error 替换——这是新增行为，任何解析 stderr 的上层工具都会看到差异。
- **直接证据**:
  1. HEAD `research_template.py:101,184`：无 Log import，无 Log.error 调用，fallthrough `return 1` 无任何 print
  2. Plan Slice 10 代码（行 1601）：`Log.error(f"未知 research-template 子命令: {action!r}", module=MODULE)`
  3. `research_template.py` 当前无 `MODULE` 常量定义（grep 确认），且无 `from dayu.log import Log` import
  4. `test_unknown_action_returns_1` 不检查 stderr 内容——当前 stderr 确实为空

- **影响**: 新增 stderr 输出改变 CLI contract；新增 `Log` import 和 `MODULE` 定义增加模块依赖
- **建议改法和验证点**:

  删除 `Log.error(...)` 行。未知 action 静默 `return 1`（与 HEAD 一致）。如果确实需要可观测性，应在独立 slice 中统一所有 CLI 入口的未知子命令处理，不在 Slice 10 的 dispatch contract 重构中附带此行为变更。

- **修复风险**: 低 — 单行删除
- **严重程度**: **中** — 功能上不影响 runner 调度，但引入行为变更且与 §4.2 冲突

---

### S10-R4-未修复-中-MODULE 常量未定义导致 Slice 10 代码不可编译

- **位置**: Master plan Slice 10 exact 入口代码（行 1601）
- **问题类型**: 不可直接实施
- **当前写法**:

  Slice 10 exact 代码引用 `module=MODULE`:
  ```python
  Log.error(f"未知 research-template 子命令: {action!r}", module=MODULE)
  ```

  `research_template.py` 当前无 `MODULE` 常量。grep 确认：`MODULE` 在 `research_template.py` 中命中为 0。

- **反例/失败场景**: Implementation agent 按 exact 代码复制到 `research_template.py` → Python `NameError: name 'MODULE' is not defined` → 模块 import 失败 → 所有 research-template 命令不可用。
- **为什么有问题**: Plan exact 代码引用了一个不存在的符号。这不是 "实现时自然会处理" 的细节——plan 未指定 MODULE 应定义在哪里（`research_template.py` 顶层？helpers？core？）、应取什么值（`"APP.RESEARCH_TEMPLATE"`？）、以及是否与 write 模块的 `MODULE = "APP.WRITE"`（`_write_config_helpers.py`）有命名约定关系。如果随 S10-R3 一并删除 Log.error 行，此问题自然消失。
- **直接证据**:
  1. `grep MODULE dayu/cli/commands/research_template.py` → 0 hits
  2. `grep MODULE dayu/cli/commands/_research_template_helpers.py` → 0 hits
  3. Plan Slice 10 代码（行 1601）：`module=MODULE`
  4. Plan 未在任何位置说明 research-template 模块的 MODULE 定义位置和值

- **影响**: 按 exact 代码生成的模块无法 import → 全部 research-template 命令不可用
- **建议改法和验证点**:

  随 S10-R3 一并删除 Log.error 行 → MODULE 问题自然消失。如果坚持保留 Log.error，则 plan 必须补充：
  - MODULE 常量定义位置（建议 `research_template.py` 顶层，值 `"APP.RESEARCH_TEMPLATE"`）
  - `from dayu.log import Log` 导入行
  - `from dayu.cli.commands._research_template_helpers import MODULE` 或类似声明显式指定

- **修复风险**: 低
- **严重程度**: **中** — 使 exact 代码不可编译；但可与 S10-R3 一并消除

---

### S10-R5-未修复-低-Protocol 直接字段访问语义与当前 getattr fallback 不完全等价

- **位置**: Master plan Slice 10 selector helper（行 1523–1524）vs HEAD `research_template.py:101`
- **问题类型**: 架构边界
- **当前写法**:

  HEAD（`research_template.py:101`）:
  ```python
  action = str(getattr(args, "research_template_action", "") or "").strip().lower()
  ```
  三重防护：`getattr(..., "")` 缺字段时返回空字符串；`or ""` 处理 None；`str()` 处理非字符串类型。

  Plan Slice 10 selector（行 1523–1524）:
  ```python
  def _resolve_research_template_action(args: ResearchTemplateDispatchArguments) -> str:
      return args.research_template_action.strip().lower()
  ```
  直接属性访问，无 fallback。

- **反例/失败场景**: `DayuCliArguments` 在正常 argparse 路径下始终有 `research_template_action` 属性（argparse subparser `dest=` 保证）。但如果 args 由测试代码、脚本或异常路径构造时遗漏该字段，当前代码退化为 `action = ""` → 不匹配任何 if 分支 → `return 1`。新代码：`AttributeError` 在 `_resolve_research_template_action` 中抛出。
- **为什么有问题**: 如果 `_resolve_research_template_action` 的调用在 try/except 块外（当前 plan exact 代码中 setup_loglevel 和 selector 均在 try 外），`AttributeError` 不被捕获（当前 except 只捕获 `FileNotFoundError, FileExistsError, ValueError`）。异常向上传播 → traceback 输出到 stderr → 与当前静默 return 1 行为不同。
- **直接证据**:
  1. HEAD `research_template.py:101`：`getattr(args, "research_template_action", "")` — 有 fallback
  2. Plan Slice 10 selector（行 1523–1524）：`args.research_template_action` — 无 fallback
  3. Plan Slice 10 入口（行 1596–1603）：selector 调用（行 1598）在 try 块外
  4. HEAD except 元组（行 181）：`(FileNotFoundError, FileExistsError, ValueError)` — 不含 `AttributeError`
  5. §0 Spike 2 验证了 `ResearchTemplateDispatchArguments` Protocol 对声明字段零错误、错字产生 pyright error。但 pyright 静态检查不保证运行时 args 一定有该属性（`DayuCliArguments(argparse.Namespace)` 子类无 `__init__` 保证所有 Protocol 字段已设置）

- **影响**: 在非正常 argparse 路径（如直接构造 args 的测试、脚本）中可能触发未捕获的 AttributeError。实际风险低——当前所有已知调用路径均由 argparse 构造 args。
- **建议改法和验证点**:

  方案 A（推荐）：selector 保留在 try 块外（因其不抛 FileNotFoundError/FileExistsError/ValueError），但为确保语义等价，selector 内增加防御：`return getattr(args, "research_template_action", "").strip().lower()` ——这与 HEAD 的 action 解析完全等价且不改变异常类型。

  方案 B：将整个 selector 调用移至 try 块内，并在 except 元组追加 `AttributeError`。但 AttributeError 是宽泛异常，可能意外吞掉 runner 内部的属性访问错误。

  方案 C（不推荐）：保持 Protocol 直接访问，依赖 argparse 保证字段存在。风险低但非零。

- **修复风险**: 低 — 方案 A 一行修改，完全等价于 HEAD 语义
- **严重程度**: **低** — 在正常 argparse 路径下不会触发；边缘情况

---

### S10-R6-未修复-低-45 签名传播表中未覆盖 tests/cli 下直接调用 run_research_template_command 的测试

- **位置**: Master plan Slice 10 签名传播表（行 1529–1536）
- **问题类型**: 测试缺口
- **当前写法**:

  Plan 的签名传播表列出 6 个模块的精确目标（arg_parsing、research_template 入口/39 runners、write 入口、config_application 2 函数、snapshot_builder 2 函数），合计 45 个 `argparse.Namespace` → `DayuCliArguments` 签名变更。

  Plan 行 1606–1616 要求 "对 39 runners、write entry 和 Slice 6 四函数的既有 direct tests 同步改用真实 `DayuCliArguments`"。

  但 `tests/cli/test_research_template_definitions.py` 直接构造 `argparse.Namespace(research_template_action=..., name=..., json=...)` 并调用 `run_research_template_command(args)`（行 178, 190, 202, 213 等）。这些测试不在 plan 的 "direct tests" 覆盖描述中（plan 只明确提及 write entry 和 Slice 6 四函数）。

- **反例/失败场景**: Slice 10 实施后，`run_research_template_command` 签名变为 `(args: DayuCliArguments) -> int`。`test_research_template_definitions.py` 构造普通 `argparse.Namespace` 传入 → pyright 类型检查报错（`argparse.Namespace` 不能赋值给 `DayuCliArguments`） → 测试文件需同步修改但 plan 未明确列出。
- **为什么有问题**: Plan 的 45 签名传播清单完整覆盖了生产代码，但测试代码的同步修改范围描述不够精确。这不是 blocker（implementation agent 会在 pyright 报错时自然发现），但 plan 声称 "code-generation-ready" 时应包含此信息。
- **直接证据**:
  1. Plan 行 1529–1536：45 签名传播表，不含测试文件
  2. `tests/cli/test_research_template_definitions.py:178,190,202,213`：直接构造 `argparse.Namespace` 并传给 `run_research_template_command`
  3. `tests/application/test_write_cli_dispatch.py:333`：`_make_rt_args` 返回 `argparse.Namespace`
  4. Plan 行 1615–1616："对 39 runners、write entry 和 Slice 6 四函数的既有 direct tests"——未列出 tests/cli 路径

- **影响**: 实施 Agent 发现 pyright 报错后补充修改 → 轻微返工
- **建议改法和验证点**:

  在 Slice 10 的 "同步新增/迁移测试" 段落（行 1606 起）中补充：
  > `tests/cli/test_research_template_definitions.py` 与 `tests/application/test_write_cli_dispatch.py` 中直接构造 `argparse.Namespace` 并传入 `run_research_template_command` 的调用点，同步改用 `DayuCliArguments` 构造。

- **修复风险**: 低 — 纯文档补充
- **严重程度**: **低** — 不阻止实施，pyright 会在实施时捕获

---

## 3. Recommended Erratum 评估

Controller 提出的 erratum 方向：

1. 保留 setup 顺序（`setup_loglevel` 先于 action 解析）
2. `action = _resolve_research_template_action(args)` — selector 使用 Protocol
3. mapping lookup 和 runner 调用仍在现有 try/except 内
4. `runner is None` → 与当前完全相同的行为（静默 `return 1`），不引入 `Log.error`/`return 2`
5. 不引入重复日志、异常传播或 `return 2`

**评估**: 此 erratum 正确识别了 S10-R1 至 S10-R4 四个 findings 的根因，并以最小 diff 修正。方向完全正确。

但 plan 的 exact 代码块（行 1596–1603）需要同步更新为修正后的版本。以下是 code-generation-ready 的建议 exact 文案。

---

## 4. Code-Generation-Ready Exact 文案建议

修正后的 Slice 10 入口函数（替换 plan 行 1596–1603）：

```python
def run_research_template_command(args: DayuCliArguments) -> int:
    """Dispatch ``research-template`` subcommands via mapping lookup.

    Args:
        args: 经 argparse 解析并注入 DayuCliArguments 的命令行参数。

    Returns:
        int: 退出码。0 表示成功；1 表示未知子命令或 runner 运行时错误。

    Raises:
        无——所有异常在内部捕获并转为退出码 1。
    """
    setup_loglevel(args)
    action = _resolve_research_template_action(args)
    try:
        runner = _RESEARCH_TEMPLATE_ACTION_DISPATCH.get(action)
        if runner is None:
            return 1
        return runner(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"research-template error: {exc}", file=sys.stderr)
        return 1
```

**关键设计决策**：

1. **`runner is None → return 1`（静默）**：与 HEAD `research_template.py:184` 行为完全一致。不引入 `Log.error`、不引入 `MODULE`、不引入 `return 2`。

2. **try/except 保留**：`return runner(args)` 在 try 块内，与 HEAD 行为一致——runner 内部抛出的 `FileNotFoundError`/`FileExistsError`/`ValueError` 被捕获，以 `"research-template error: ..."` 格式输出到 stderr 并返回 1。

3. **selector 在 try 块外**：`_resolve_research_template_action` 只做字符串操作（`.strip().lower()`），不抛 `FileNotFoundError`/`FileExistsError`/`ValueError`。若需防御 `AttributeError`，selector 内部可保留 `getattr` fallback（见 S10-R5 方案 A），但这不是必须的——在 `DayuCliArguments` 正常路径下 `research_template_action` 始终存在。

4. **完整中文 docstring**：满足 AGENTS 编码硬约束（"函数必须提供完整中文 docstring，至少包含参数、返回值、异常"）。

### 4.1 Selector 辅助函数建议

```python
def _resolve_research_template_action(args: ResearchTemplateDispatchArguments) -> str:
    """从 args 中解析并规范化 research-template action key。

    Args:
        args: 实现 ResearchTemplateDispatchArguments Protocol 的参数对象。

    Returns:
        str: 小写、去除首尾空白的 action key。
    """
    return args.research_template_action.strip().lower()
```

如需保留 `getattr` fallback 语义（S10-R5 方案 A），改为：

```python
def _resolve_research_template_action(args: object) -> str:
    """从 args 中解析并规范化 research-template action key。

    对非 DayuCliArguments 的调用方提供 getattr fallback 兼容。

    Args:
        args: 应包含 ``research_template_action`` 属性的参数对象。

    Returns:
        str: 小写、去除首尾空白的 action key。缺字段时返回空字符串。
    """
    return str(getattr(args, "research_template_action", "") or "").strip().lower()
```

但此变体会丢失 Protocol 静态类型检查优势（pyright 不再对 selector 调用方的字段名拼写错误报错）。建议保持 Protocol 版本并依赖 argparse 保证字段存在。

---

## 5. 其他审计项

### 5.1 DayuCliArguments runtime identity

Plan 行 1513–1514 的 `parse_args(namespace=DayuCliArguments())` 构造契约合理。`DayuCliArguments(argparse.Namespace)` 子类实例的 `isinstance` 检查可通过。argparse 的 `namespace=` 参数将解析结果写入传入对象，返回同一对象——字段写入不会漂移。无 gap。

### 5.2 39 mapping 条目完整性

Plan 行 1551–1591 的 `_RESEARCH_TEMPLATE_ACTION_DISPATCH` 列出 39 个条目。对照 HEAD 的 39 个 `if action == "..."` 分支（行 103-179）和 §1.5 的 39 action key 列表，一一对应。无缺失、无重复。

### 5.3 45 签名传播范围

Plan 行 1529–1536 的签名传播表覆盖：1 (`parse_arguments` 返回) + 1 (`run_research_template_command` 入口) + 39 (`_run_*` runners) + 1 (`run_write_command`) + 2 (`_write_config_application.py`) + 2 (`_write_snapshot_builder.py`) = **46**（非 45）。

实际计数：表中 6 行分别为 1 + (1+39) + 1 + 2 + 2 = 46。plan 行 1538 写 "45 个 args 签名（1+39+1+2+2）" 少计了 `run_research_template_command` 自身——但 `run_research_template_command` 的签名传播已明确在表中（行 1532）。建议 plan 将数字修正为 46，或澄清 `parse_arguments` 返回签名不计入 "args 签名" 计数（因其不在 `Callable[[DayuCliArguments], int]` 之列）。这是文档数字不一致（LOW），不影响实施正确性。

### 5.4 targeted gate 正则覆盖

Plan 行 1622–1625 的 targeted rg 命令：
```text
rg '^def (run_research_template_command|_run_[a-z0-9_]+)\(args: argparse\.Namespace\)'
```

当前 39 个 runner 全部匹配 `^def _run_[a-z0-9_]+` 模式（`_run_list`, `_run_show`, ..., `_run_source_binding_history`）。`run_research_template_command` 也匹配。正则覆盖完整，无 gap。

---

## 6. Open Questions

无。所有发现的问题均有直接证据和明确修正方向。

---

## 7. Residual Risks

| 风险 | 跟踪建议 |
|---|---|
| 移除 try/except 的诱惑：未来 slice 可能有人提议 "runner 不应抛异常，应各自内部处理"，从而再次尝试移除 try/except | 在 Slice 10 入口代码注释中显式记录 try/except 的保留理由 |
| Protocol selector 的 getattr fallback 被移除后，非 argparse 构造的 args（如测试 fixture）可能触发 AttributeError | 见 S10-R5 方案 A；若选择保留 Protocol 直接访问，需确保所有测试使用 `DayuCliArguments()` 而非 `argparse.Namespace()` 构造 args |

---

## 8. Verdict

**FAIL** — 存在 2 个 HIGH findings（S10-R1、S10-R2），plan 的 Slice 10 exact 入口代码与 §4.2 行为不变量直接冲突，且移除 try/except 会导致现有 characterization test 失败。

修正路径明确且低风险：将 plan 行 1596–1603 的 exact 代码替换为 §4 的建议文案，同步更新 plan 中引用 `return 2` 和 `Log.error` 的描述文字。修正后预期所有 findings 关闭，Slice 10 达到 code-generation-ready。

**修正后预期 verdict**: PASS。

---

## 9. Finding Summary

| ID | Severity | Summary | Suggested Fix |
|---|---|---|---|
| S10-R1 | **HIGH** | 未知 action `return 2` 与 §4.2 "退出码不变" 和 HEAD `return 1` 冲突 | `return 2` → `return 1`，删除 `Log.error` |
| S10-R2 | **HIGH** | try/except 移除导致 runner ValueError 不再被捕获，"research-template error:" stderr 契约断裂 | mapping lookup + runner call 放回 try/except 内 |
| S10-R3 | MEDIUM | 未知 action 新增 `Log.error` 输出，HEAD 为静默 | 随 S10-R1 一并删除 |
| S10-R4 | MEDIUM | `module=MODULE` 引用未定义常量 | 随 S10-R3 一并删除；或补充 MODULE 定义 |
| S10-R5 | LOW | Protocol 直接字段访问无 getattr fallback | 保持 Protocol 版本（argparse 保证字段存在）；或 selector 内增加 getattr fallback |
| S10-R6 | LOW | 45 签名传播表未覆盖 tests/cli 下的测试文件修改范围 | 文档补充测试文件同步修改说明 |
