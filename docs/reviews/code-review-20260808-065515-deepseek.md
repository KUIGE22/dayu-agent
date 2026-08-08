# Code Review

## Scope

- Mode: current changes
- Branch: `codex/dual-model-research-mvp`
- Base: `5d1c3f9 gateflow: accept cli write architecture plan v5.0`
- Output file: `docs/reviews/code-review-20260808-065515-deepseek.md`
- Included scope:
  - `dayu/cli/commands/_write_execution.py`（新建）
  - `dayu/cli/commands/_write_manual_recovery.py`（新建）
  - `dayu/cli/commands/write.py`（17 函数迁出，改为 exact 17 functional binding）
  - `tests/application/test_write_cli_dispatch.py`（新增 exact 17 identity 测试、owner patch 目标更新）
  - `tests/application/test_write_model_configuration_preapplication.py`（patch 目标迁至 direct owner、新增 preflight 依赖错误与门禁阻断回归）
  - `tests/engine/test_cli_running_config.py`（patch 目标迁至 direct owner、import 重排）
- Excluded scope: 未跟踪文件 `docs/reviews/slice-7-write-execution-manual-recovery-implementation-20260808-codex.md`（实现记录，非 review 目标）
- Parallel review coverage: 无（单 reviewer 全量覆盖）

## Findings

### H-1-未修复-高-_check_write_model_configuration_manual_recovery_gate docstring 记录了不存在的参数

- **入口/函数**: `_check_write_model_configuration_manual_recovery_gate`
- **文件(行号)**: `dayu/cli/commands/_write_manual_recovery.py:1457-1470`
- **输入场景**: 任何调用者阅读该函数的 docstring 以了解接口
- **实际分支**: 函数签名仅接受 `*, paths_config: WorkspaceConfig`，无 `args` 参数
- **预期行为**: docstring 的 Args 节应准确列出函数实际接受的参数
- **实际行为**: docstring 的 Args 节记录了 `args: 解析后的写作命令参数`，但该参数在函数签名中不存在
- **直接证据**:
  - 函数签名（行 1457-1460）：`def _check_write_model_configuration_manual_recovery_gate(*, paths_config: WorkspaceConfig) -> int:`
  - docstring Args 节（行 1463-1465）：`Args: args: 解析后的写作命令参数。 paths_config: 写作工作区与配置路径。`
  - 函数体仅使用 `paths_config`，未访问 `args`
- **影响**: 文档与实际接口不一致，调用者可能误以为需要传入 `args` 参数；违反 AGENTS.md 编码硬约束"函数必须提供完整中文 docstring，至少包含参数、返回值、异常"中对参数准确性的要求
- **建议改法和验证点**: 删除 docstring Args 节中的 `args: 解析后的写作命令参数。` 行。验证：确保 docstring 与 `inspect.signature` 一致
- **修复风险（低）**: 仅修改 docstring 文本，不影响运行时行为
- **严重程度（高）**: 文档与接口不一致属于 correctness 缺陷（文档真源错误）

### M-1-未修复-中-test_cli_running_config.py 大范围 import 重排出 Slice 7 迁移范围

- **入口/函数**: 模块级 import 区域
- **文件(行号)**: `tests/engine/test_cli_running_config.py:15-107`
- **输入场景**: 该测试文件被任何 CI/本地运行加载时
- **实际分支**: 多个与 Slice 7 迁移无关的 import 语句被重新排序
- **预期行为**: 仅修改 Slice 7 必要的 patch 目标（`write_command_module` → `write_manual_recovery_command_module`、`write_command_module` → `write_execution_command_module`），不在同一文件中做无关 import 重组
- **实际行为**: 以下 import 发生重排但不属于 Slice 7 范围：
  - `dayu.cli.conversation_label_locks.ConversationLabelLease` 和 `dayu.cli.conversation_labels.FileConversationLabelRegistry` 从顶部移至中部（行 32-33）
  - `dayu.cli.commands.fins._build_fins_command, run_fins_command` 从行 ~46 移至行 19
  - `dayu.cli.main.main` 从行 ~46 移至行 59
  - `dayu.services.contracts.*` / `dayu.services.scene_execution_acceptance.*` / `dayu.services.write_service.*` / `dayu.startup.workspace.*` / `dayu.host.protocols.*` / `dayu.host.Host` 从分散位置聚合重排
- **直接证据**: `git diff 5d1c3f9 -- tests/engine/test_cli_running_config.py` 头部 import diff 块
- **影响**: 增加 diff 审查噪音，增大 import 丢失或循环依赖被意外引入的回归风险；import 重排的语义中立性无法从 diff 直接确认
- **建议改法和验证点**: 将 import 重排回退到 HEAD 顺序，仅保留 Slice 7 必要的三处变更：(1) 新增 `_write_manual_recovery as write_manual_recovery_command_module` import，(2) patch 目标从 `write_command_module` 改为 `write_manual_recovery_command_module`，(3) `dayu.cli.commands.write.run_write_pipeline` 改为 `dayu.cli.commands._write_execution.run_write_pipeline`。验证：`git diff 5d1c3f9 -- tests/engine/test_cli_running_config.py | diffstat` 确认仅有语义变更行
- **修复风险（低）**: 回退 import 顺序不改变测试的运行时行为
- **严重程度（中）**: 不造成运行时错误，但违反最小变更原则，增加审查和维护负担

### L-1-未修复-低-_run_write_preflight 格式化差异与实现记录声称的"逐项相同"在字面上不一致

- **入口/函数**: `_run_write_preflight`
- **文件(行号)**: `dayu/cli/commands/_write_execution.py:213` vs HEAD `write.py:292`
- **输入场景**: 代码审查者对比新旧函数体
- **实际分支**: 无影响，AST 层面等价
- **预期行为**: 格式化完全不变（若遵循 exact 逐字迁移目标）
- **实际行为**: HEAD 中 `str(current_snapshot.get("snapshot_fingerprint") or "")` 跨两行，新文件中同行书写。实现记录声称"迁移函数与 HEAD 的 AST 在移除 docstring 后逐项相同: 17/17 PASS"——该声明在 AST 层面成立（经 `ast.dump` 验证一致），但字面文本不完全相同
- **直接证据**: AST dump 比较确认同构；文本 diff 显示换行差异
- **影响**: 仅影响字面审查体验，不影响行为正确性
- **建议改法和验证点**: 可忽略；若追求精确逐字迁移，将行 213 拆回两行以与 HEAD 完全一致
- **修复风险（低）**: 纯格式化变更
- **严重程度（低）**: AST 已验证等价，属于格式差异而非逻辑差异

### L-2-未修复-低-_write_execution.py 与 _write_manual_recovery.py 缺少模块级 `__all__`

- **入口/函数**: 模块顶层
- **文件(行号)**: `dayu/cli/commands/_write_execution.py:1`, `dayu/cli/commands/_write_manual_recovery.py:1`
- **输入场景**: 其他模块使用 `from dayu.cli.commands._write_execution import *` 或静态分析工具检查公共 API 边界
- **实际分支**: 两个新模块均为 CLI 私有实现（`_` 前缀），但未声明 `__all__`
- **预期行为**: 私有模块显式声明 `__all__` 以锁定对外暴露面
- **实际行为**: 无 `__all__` 声明，`import *` 将导出所有顶层公开符号
- **直接证据**: 两个模块文件均无 `__all__` 定义
- **影响**: 当前 `write.py` 通过显式 import 逐个导入所需符号，不受影响；但缺少 `__all__` 使模块公共契约边界模糊，未来可能被意外依赖
- **建议改法和验证点**: 在两模块开头分别添加 `__all__ = ["_run_write_stage", "_run_write_preflight"]` 和 `__all__ = ["_check_write_model_configuration_manual_recovery_gate", "_run_write_model_configuration_manual_recovery_application", ...]`（列出 15 个符号）
- **修复风险（低）**: 仅添加声明，不改变现有 import 行为
- **严重程度（低）**: 私有模块（`_` 前缀）的契约边界已由命名约定传达，`__all__` 是额外加固

## Verdict

**PASS** — 条件：H-1 修复后方可 merge。

17 函数迁移的 AST 等价性已验证；write.py exact 17 functional binding 均为真实 global lookup（同进程 `is` 一致性测试覆盖）；import 删除无漏依赖；manual 三 factory labels 正确且 DAG 单向无环；direct-owner vs dispatch-owner patch 目标正确；新模块未引入 `Any`/`object`/`cast`/`ignore`；新增 preflight 依赖错误回归测试真实捕获退出码 2 与 4；逐文件 statement coverage 均 ≥80%。H-1（docstring 记录不存在参数）是唯一阻止项，修复风险低。

## Open Questions

无。

## Residual Risk

1. `_run_write_preflight` 的 26 个未覆盖 statement 主要落在 artifact 输出分支（`routing_snapshot_output`、`live_smoke_plan_output` 等路径），这些路径依赖完整文件系统 mock，当前通过 dispatch 集成测试间接覆盖。若未来这些分支中的 print/format 调用签名变更，可能被静默遗漏。
2. `_write_manual_recovery.py` 的 73 个未覆盖 statement 分布在 15 个 runner 的异常处理与边界分支上，参数化测试覆盖了主要退出码路径但未穷举所有异常类型组合。
3. `test_cli_running_config.py` 的 import 重排（M-1）虽然功能等价，但若重排过程中引入静默 import 循环（两个模块互相导入），Python 可能以 `AttributeError` 形式在远晚于 import 时才暴露，建议回退无关重排。
4. 本 Slice 未涉及 README 更新（实现记录判断合理：命令、参数、退出码无变化），但若后续 Slice 8 迁移 Challenger/rollback 后对外接口发生变化，需按触发规则更新对应 README。
