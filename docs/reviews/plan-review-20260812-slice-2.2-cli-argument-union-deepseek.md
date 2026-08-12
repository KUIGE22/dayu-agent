# Slice 2.2 CLI argument union DeepSeek plan review

- **Reviewer**: DeepSeek `deepseek-chat`（official API，temperature 0）
- **Scope**: S22-CTRL-010 与对应 Controller plan-fix，只读独立审核
- **结论**: **PASS**
- **Open H/M/L**: **0/0/0**

## 1. 根因分析

根因成立，直接证据链完整：

1. 目标计划 §3 的 implementation allowlist 原本只列出
   `tests/cli/test_platform_command.py` 与 `tests/cli/test_main.py` 作为 CLI tests，
   未包含 `tests/application/test_write_cli_dispatch.py`。
2. 目标计划 §8 已授权 `dayu/cli/arguments.py` 新增 `platform_action`、
   `tenant_id`、`worker_id`、`scheduler_id` 四个 typed field。
3. 失败测试 `test_protocol_and_dayu_fields_form_exact_union` 仍断言
   `dayu_fields == research_fields | write_fields` 且总数为 21，新增四字段必然失败。
4. 实施者在原合同下无法合法同步 AST 断言，因为该测试文件不在 allowlist 内。

根因是计划所有权缺口，不是平台 typed field 实现错误。删除平台字段、放宽 AST 断言
或修改 write/research 字段都会掩盖真实合同，均应拒绝。

## 2. 直接证据

| # | 证据 | 来源 |
| --- | --- | --- |
| 1 | 当前 `arguments.py` AST 计数为 Research=1、Write=20、Dayu=25 | `dayu/cli/arguments.py` |
| 2 | 四字段逐字为 `platform_action: str`、`tenant_id: str`、`worker_id: str \| None`、`scheduler_id: str \| None` | 目标计划与 Controller fix |
| 3 | 失败节点仍锁定 21 字段的两协议并集 | `tests/application/test_write_cli_dispatch.py` |
| 4 | 原 §3 未列出该 application test | 目标计划原 allowlist |
| 5 | Serper 失败与 CLI union 无数据流、import 或所有权联系 | 目标计划 residual |

## 3. 逐项合同矩阵

| 合同项 | 当前事实 | 可生成性与闭合性 |
| --- | --- | --- |
| `PlatformDispatchArguments` exact4 | 尚待实现 | 与既有 Protocol 模式一致，只依赖标准库；fix 精确锁定四字段 |
| Research exact1 | 已存在且精确一字段 | 保持不变，闭合 |
| Write exact20 | 已存在且精确二十字段 | 名字与类型保持不变，闭合 |
| Dayu exact25 | 当前已含 4+1+20 字段 | 三 Protocol 无重叠并集，可生成且闭合 |
| 单一 `argparse.Namespace` base | 当前唯一直接 base | fix 禁止 Protocol 继承，闭合 |
| 零 class default | 当前 annotation 均无 value | fix 明确保持，闭合 |
| 零 custom `__init__` | 当前不存在 | fix 明确禁止，闭合 |
| 测试 allowlist | 原计划遗漏一个既有测试文件 | 只新增该文件且只改目标节点/必要说明，范围最小 |
| Production scope | `arguments.py` 已在 allowlist | 不增加其它 production 路径，闭合 |
| Serper scope | 与本缺口无关 | 明确不授权修改，闭合 |

## 4. Findings

无。Open H/M/L = **0/0/0**。

## 5. 验证门禁

计划已经覆盖：

- focused exact-union 节点；
- write CLI + platform CLI + main 关联回归；
- `arguments.py` 与目标测试的 Pyright；
- Ruff default、F/I 与 format；
- 显式移除 `SERPER_API_KEY` 的 clean-env full non-integration；
- `git diff --check`。

raw inherited-env run不记为 PASS；若 clean-env 仍有 Serper 失败，必须重新取证。

## 6. STOP 覆盖

STOP 已覆盖新增 production/test 路径、任一 exact 合同无法并存、focused/static/full
回归失败，以及删除字段、宽松并集、Protocol 多继承、动态字段 bag、兼容 wrapper 或修改
Serper 等绕过方式。

## 7. 结论

本勘误根因成立、修复范围最小、合同精确闭合、验证与 STOP 充分；所有合同均可在修正后
allowlist 内实现。**PASS / open H/M/L = 0/0/0**。
