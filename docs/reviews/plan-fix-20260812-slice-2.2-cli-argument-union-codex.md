# Slice 2.2 CLI typed-field exact union 计划修复

- **状态**：`CLOSED / DEEPSEEK + MIMO DUAL PLAN REVIEW PASS / IMPLEMENTATION MAY RESUME`
- **Gate**：Gateflow plan-fix；尚未进入plan re-review或implementation恢复。
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **触发点**：clean non-integration的既有CLI AST合同失败，命中目标计划§12 allowlist STOP。
- **本次写入范围**：目标计划与本artifact；未修改production、tests、dependency、CI或README。

## 1. 结论

失败动机成立，但根因是计划所有权缺口，不是平台typed field实现错误。目标计划已授权`dayu/cli/arguments.py`新增四个platform字段，却没有把拥有`DayuCliArguments`跨命令exact-union合同的`tests/application/test_write_cli_dispatch.py`列入implementation allowlist。删除平台字段、放宽AST检查或改动write/research字段都会掩盖真实合同，均被拒绝。

最小修复是：production allowlist保持不变，只把上述一个既有测试文件加入allowlist；在已允许的`arguments.py`中按既有command-specific Protocol模式定义精确四字段的`PlatformDispatchArguments`，然后让AST测试锁定三Protocol并集。

## 2. 直接证据

1. 当前`dayu/cli/arguments.py`的AST计数为：`ResearchTemplateDispatchArguments=1`、`WriteDispatchArguments=20`、`DayuCliArguments=25`。
2. 四个新增字段逐字为`platform_action: str`、`tenant_id: str`、`worker_id: str | None`、`scheduler_id: str | None`，与目标计划§8已批准CLI参数一致。
3. 失败节点`tests/application/test_write_cli_dispatch.py::TestWritePhaseTableStructure::test_protocol_and_dayu_fields_form_exact_union`仍断言`dayu_fields == research_fields | write_fields`和`len(dayu_fields) == 21`，因此新增四字段必然触发失败。
4. 目标计划原§3只允许`tests/cli/test_platform_command.py`与`tests/cli/test_main.py`作为CLI tests；失败节点所在文件未列出，实施者不能在原合同下合法同步AST断言。
5. 同一次raw full non-integration中的`tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key`因继承`SERPER_API_KEY`进入live request并遭本机proxy拒绝；它与CLI字段并集无数据流、import或所有权联系。

## 3. 已写回的 closed contract

### 3.1 字段与类型

`PlatformDispatchArguments(Protocol)`精确拥有：

```text
platform_action: str
tenant_id: str
worker_id: str | None
scheduler_id: str | None
```

`ResearchTemplateDispatchArguments`保持exact1，`WriteDispatchArguments`保持exact20且名字/类型不变，`PlatformDispatchArguments`为exact4。`DayuCliArguments`的class-level annotations必须是三个Protocol字段的无重叠exact union，总数25。

`DayuCliArguments`仍只继承`argparse.Namespace`，不继承Protocol、不定义`__init__`；全部annotation的class value保持`None`，parser runtime defaults不得变化。新增Protocol不吞入`base`、`config`等global字段，也不要求改动`dayu/cli/commands/platform.py`的private invocation Protocol。

### 3.2 精确所有权

- 既有production范围不扩大：只允许原计划已列出的`dayu/cli/arguments.py`承载上述Protocol/typed field合同。
- 测试allowlist只新增`tests/application/test_write_cli_dispatch.py`。
- 该测试文件只允许修改`test_protocol_and_dayu_fields_form_exact_union`及模块说明中与exact protocol/field计数直接冲突的文字。
- 其它phase table、selector、mapping、fixture与行为断言保持字节不变；不新增测试文件，不修改Serper路径。

## 4. 实施恢复后的精确验证

必须按顺序运行且如实记录：

```text
uv run pytest tests/application/test_write_cli_dispatch.py::TestWritePhaseTableStructure::test_protocol_and_dayu_fields_form_exact_union -q
uv run pytest tests/application/test_write_cli_dispatch.py tests/cli/test_platform_command.py tests/cli/test_main.py -q -m "not integration and not slow and not e2e"
uv run pyright dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
uv run ruff check dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
uv run ruff check --select F,I dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
uv run ruff format --check dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
env -u SERPER_API_KEY uv run pytest -q -m "not integration and not slow and not e2e"
git diff --check
```

raw inherited-env run不记为PASS；Serper proxy失败分类为clean-environment residual。若显式移除`SERPER_API_KEY`后仍失败，必须重新取证，不能沿用本次分类。

## 5. STOP 与非目标

以下任一发生立即回Controller：

- 需要新增production路径，或修改`arguments.py`之外的production文件；
- 需要修改新增allowlist以外的测试文件；
- Research exact1、Write exact20、Platform exact4、Dayu exact25、字段类型、单一base、零class default或零custom init任一合同无法同时满足；
- focused/static失败，或clean-env full non-integration出现CLI/write/research回归；
- 试图通过删除platform字段、宽松并集、Protocol多继承、动态字段bag、兼容wrapper或修改Serper代码/测试绕过。

本勘误不改变parser行为、runtime dispatch、signal、startup、Redis、PG、schedule/job合同、dependency、CI或README，也不授权live provider/model/broker、交易、push、PR或commit。

## 6. 双审闭合

审核快照为 target SHA-256
`a95194bcfe0a83cce859279f47ee4d5f4cdf7b0d6a70d933171d13b377a4a488` 与本 fix
SHA-256 `dd8776da05f44d4ba7dbba519e2d785b61f0f5e2da3430e5dc7d7403feec317f`。
DeepSeek 与 MiMo 两路独立 plan review 均给出 `PASS / open H/M/L=0/0/0`；Controller
接受该最小勘误并恢复 implementation。闭合只授权 `S22-CTRL-010` 的精确 production/test
范围，不改变其余 STOP 或最终 code-review gate。
