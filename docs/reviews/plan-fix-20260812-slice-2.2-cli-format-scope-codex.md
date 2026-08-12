# Slice 2.2 CLI formatter 范围计划修复

- **状态**：`CLOSED / DEEPSEEK + MIMO DUAL PLAN REVIEW PASS / ACCEPTED`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **Controller finding**：`S22-CTRL-011`

## 1. 触发证据

`S22-CTRL-010`的typed-field实现完成后，精确AST节点、149项CLI focused、exact Pyright、Ruff default及F/I均通过。唯一失败为：

```text
uv run ruff format --check dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
Would reformat: tests/application/test_write_cli_dispatch.py
```

失败不是本次新增代码独有。accepted implementation baseline `37cac2f`中的原测试文件SHA-256为`e740de000928b915d04168b8bd26d0836423a5a619acb30062c80561777f2340`；用锁定Ruff `0.15.11`对该原文件独立执行format diff得到566行历史diff。原计划同时要求目标方法之外字节不变，因此全文件写回不是合法修复。

## 2. Controller 裁决

接受最小门禁修正：production `arguments.py`保持全文件format check；既有大测试文件只对获准变化的模块/import区间`1-40`与目标方法区间`1297-1372`执行range check，并以相对`37cac2f`的零上下文diff证明没有修改其它测试内容。

该裁决不改变Research exact1、Write exact20、Platform exact4、Dayu exact25、字段类型、structural conformance、单一`argparse.Namespace` base、零class default、零custom init，也不扩大implementation allowlist。

## 3. 必须复审的问题

DeepSeek与MiMo须独立确认：

1. range边界完整覆盖本次唯一获准的测试变化，且不遗漏目标方法；
2. baseline全文件format失败可复现，不能诚实要求全文件PASS；
3. 零上下文diff gate足以阻止借本勘误修改其它历史测试；
4. 不存在更小且同时满足“历史字节不变”和“新增代码格式化”的方案；
5. 无新增H/M/L finding后才可恢复implementation。

## 4. STOP 与残余

若range check仍失败、range必须越过目标方法、baseline证据不成立，或任何方案需要改Ruff配置/版本、全文件机械格式化、`fmt`跳过标记或新implementation路径，立即STOP。

保留残余：该历史测试文件整体仍不满足当前Ruff formatter；owner只能在独立、明确授权的机械格式化work unit处理中，本Slice不顺手修复。

## 5. Closure

DeepSeek `plan-review-20260812-slice-2.2-cli-format-scope-deepseek.md`与MiMo `plan-review-20260812-slice-2.2-cli-format-scope-mimo.md`均独立核验reviewed target SHA-256 `5bf2541dbb6db43b6a8a652800160ac6f6146a0c98490ead5ef24999c90eb824`及fix SHA-256 `f427a223a9e9c32f4e81eadc32fed716bd8ca7a3ae055aef50fa851fc3f6152f`，并均裁决`PASS / open H/M/L=0/0/0`。Controller接受`S22-CTRL-011`；implementation可在accepted plan commit后恢复，但最终实现仍须完成全部门禁及DeepSeek+MiMo独立code review。
