# Code Review

## Scope

- **Mode**: current changes (workspace diff vs HEAD `3363b6d`)
- **Branch**: `codex/dual-model-research-mvp`
- **Base**: `3363b6d gateflow: accept cli write architecture plan v4.9`
- **Output file**: `docs/reviews/code-review-20260808-060001-deepseek.md`
- **Included scope**:
  - `dayu/cli/commands/_write_config_application.py`（新建）
  - `dayu/cli/commands/_write_snapshot_builder.py`（新建）
  - `dayu/cli/commands/write.py`（修改）
  - `tests/application/test_write_model_configuration_preapplication.py`（修改）
  - `tests/engine/test_cli_running_config.py`（修改）
- **Excluded scope**: `docs/reviews/*`（实现记录与 plan review artifacts）
- **Reference documents**: AGENTS.md, accepted plan v4.9,
  `docs/reviews/slice-6-write-config-application-snapshot-implementation-20260808-codex.md`
- **Parallel review coverage**: 无，全量由主 reviewer 逐行走读

---

## Findings

### 1-未修复-低-run_label 默认值在三个函数签名中重复为魔法字符串

- **入口/函数**: `_build_fresh_application_routing_snapshot`（`_write_config_application.py:43`）、
  `_build_snapshot_for_args`（`_write_snapshot_builder.py:22`）、
  `build_snapshot_builder`（`_write_snapshot_builder.py:52`）
- **文件(行号)**: `_write_config_application.py:43`, `_write_snapshot_builder.py:22,52`
- **输入场景**: 调用方不显式传递 `run_label` 时，三层函数各自使用自己的默认值
- **实际分支**: 三个函数的 `run_label` 关键字参数均默认为字面量 `"configuration-application"`
- **预期行为**: AGENTS.md 明确要求“禁止魔法数字、魔法字符串”；该默认值应在单一定义点声明
  （例如 `_write_config_helpers.py` 中的模块级常量），三个函数签名统一引用同一常量
- **实际行为**: 字符串字面量 `"configuration-application"` 在三处独立重复，且测试文件
  `test_snapshot_builder_forwards_bound_arguments_and_mapping:406` 另有一处独立字面量
- **直接证据**: `rg -n '"configuration-application"'` 在 production 代码中命中 3 处默认参数
  （均以独立字符串字面量形式写入签名），测试中 1 处 `expected_label` 赋值
- **影响**: 若将来需要修改该默认标签，需同步修改 3 个 production 签名 + 1 个测试断言，
  任一遗漏会导致日志标签不一致或测试失败。本 Slice 的 v4.9 plan 明确依赖该默认值语义，
  当前三层默认值恰好一致，不存在行为 bug，但违反 AGENTS 编码硬约束
- **建议改法和验证点**: 在 `_write_config_helpers.py` 中新增 `_DEFAULT_APPLICATION_RUN_LABEL = "configuration-application"`，
  三个函数签名改为 `run_label: str = _DEFAULT_APPLICATION_RUN_LABEL`，
  测试 `expected_label` 引用同一常量。验证：pyright + 全量 write caller corpus
- **修复风险（低）**: 纯常量提取，不影响运行时行为；三个函数默认值当前已一致，
  提取为常量后语义完全相同
- **严重程度（低）**: 当前无行为 bug，但违反项目编码硬约束，且对后续维护构成轻微风险

### 2-未修复-低-`_build_snapshot_for_args` 是纯透传包装函数

- **入口/函数**: `_build_snapshot_for_args`（`_write_snapshot_builder.py:17-44`）
- **文件(行号)**: `_write_snapshot_builder.py:17-44`
- **输入场景**: `build_snapshot_builder` 通过 `functools.partial` 绑定参数后调用此函数
- **实际分支**: 函数体仅有一行 `return _build_fresh_application_routing_snapshot(...)`，
  将所有参数原样透传
- **预期行为**: 函数职责单一，仅作为 `functools.partial` 的位置参数适配层存在；
  plan v4.9 S6-W12-CYCLE-01 明确接受此设计
- **实际行为**: 与预期一致。函数签名中的 `args` 为位置参数（`*` 之前），其余为 keyword-only，
  使得 `functools.partial(_build_snapshot_for_args, args, ...)` 的语义清晰——`args`
  按位置绑定，其余按关键字绑定
- **直接证据**: `_write_snapshot_builder.py:39-44`，函数体仅有一行 return 语句；plan v4.9
  line 968 显式描述此函数为模块级包装
- **影响**: 纯架构选择，无行为影响。额外的一层调用栈在性能敏感路径上可忽略（快照构建本身
  包含 preflight I/O）。该包装函数的存在使 `build_snapshot_builder` factory 无需知道
  `_build_fresh_application_routing_snapshot` 的签名细节（positional vs keyword-only）
- **建议改法和验证点**: 不需要修改。此 finding 是架构可观测性记录，非缺陷
- **修复风险（低）**: 无需修复
- **严重程度（低）**: 无行为缺陷；作为架构透明度记录

---

## Adversarial Failure Pass

对以下攻击面逐项排查，均未发现可利用缺陷：

### 参数与类型安全
- `execution_options` 在所有六个相关函数签名中均为 `ExecutionOptions`（非 `Any`、非 `None`、
  非 `object`），pyright `0 errors, 0 warnings, 0 informations` 确认
- `args` 在所有迁移/新建函数中均为 `argparse.Namespace`，与 plan v4.8 S6-CTRL-01 一致
- `snapshot_builder` 回调类型为 `Callable[[], Mapping[str, ModelConfigJsonValue]]`，
  零 `Any`、零 `Callable[..., ...]`
- `functools.partial` 在 application 模块中不绑定 `run_label`（依赖 `_build_fresh_application_routing_snapshot`
  的默认值 `"configuration-application"`），与 plan v4.9 S6-W12-CYCLE-01 精确一致；
  builder factory 的四次调用按默认/默认/verification/clearance 顺序设置 label

### 退出码与语义等价
- `_run_write_model_configuration_application` 的 exit code 映射：0（applied）、4（blocked/busy/rolled_back）、
  6（receipt error）、2（file/type/value error），与原实现完全一致
- rollback runner 的 exit code：0（rolled_back）、4（rolled_forward/blocked/busy）、6（receipt error）、
  2（file/type/value error），与原实现完全一致
- manual recovery application/verification/clearance 三个 runner 的 exit code 映射均保持不变
- 异常类型捕获顺序：Blocked/Busy → 4，ReceiptError → 6，File/Type/Value Error → 2，
  与迁移前完全一致，无分支重排

### 依赖方向与循环
- `_write_snapshot_builder.py → _write_config_application.py`：单向，仅 import `_build_fresh_application_routing_snapshot`
- `_write_config_application.py` 零 import `_write_snapshot_builder.py`、零 import `write.py`
- `write.py → _write_config_application.py`：单向，仅 import `_run_write_model_configuration_application`
- `write.py → _write_snapshot_builder.py`：单向，仅 import `build_snapshot_builder`
- 无双向依赖、无循环、无 lazy import、无 compatibility re-export
- `MODULE` 真源在 `_write_config_helpers.py`；application 模块正常 import，未复制本地常量

### 并发与异常路径
- 所有 runner 函数为同步单线程，不共享可变状态；`functools.partial` 捕获的是不可变引用
  （`argparse.Namespace` 解析后不变、`WorkspaceConfig` 冻结语义、`ExecutionOptions` 为 frozen dataclass）
- `snapshot_builder` callback 在事务函数内部被调用（延迟求值），不在 runner 的 except 分支之前执行，
  避免了 partial failure 导致的状态不一致
- 所有 runner 均通过 `datetime.now(UTC)` 传入当前时间，不依赖全局时钟

### 空值/缺失参数
- application runner 的 `plan_path`/`approval_path`/`receipt_path` 均通过 `str(getattr(args, key, "") or "").strip()` 获取，
  空字符串会被透传至事务函数，由事务函数自行校验——与原实现一致
- manual recovery verification/clearance 的 `config_root` 为 None 时提前返回 2——与原实现一致

### 测试真实验证
- `test_snapshot_builder_forwards_bound_arguments_and_mapping` 参数化覆盖 `run_label=None`（默认 label）和
  `run_label="configuration-manual-recovery-verification"`（显式 label），monkeypatch 底层
  `_build_fresh_application_routing_snapshot`，验证 callback 返回同一 snapshot mapping 且参数透传正确
- `test_fresh_application_routing_snapshot_builds_from_resolved_dependencies` 通过真实 helper 控制流
  （stub 底层依赖），覆盖 preflight、logging、ticker strip 和 snapshot mapping 返回路径
- `test_application_runner_invokes_direct_partial_snapshot_callback` 在 `_apply_plan` stub 内部
  真实调用 `snapshot_builder()`，断言 `now.tzinfo is not None` 和 mapping identity，
  验证 runner 的同模块 partial 被事务依赖真实消费
- `test_cli_configuration_runners_map_errors_to_stable_exit_codes` 的 `dependency_target` 改用
  完整 monkeypatch 路径字符串（`"dayu.cli.commands._write_config_application.<name>"`），
  patch 目标与 runner 的真实 globals 绑定一致

### 过度耦合检查
- 两个新模块的职责边界清晰：`_write_config_application.py` 拥有 snapshot 构建真源与应用事务 runner；
  `_write_snapshot_builder.py` 拥有延迟 callback factory
- builder → application 的耦合限于单一函数 import（`_build_fresh_application_routing_snapshot`），
  不依赖 application 模块的内部实现细节
- application 模块的 `functools.partial` 直接绑定同模块函数，不通过 builder 间接调用，
  因此 application 模块的 callback 构造与 builder 模块的 factory 完全独立
- `write.py` 的 4 处 `build_snapshot_builder` 调用按 runner 语义分别设置 label，
  不共享 builder 实例或状态
- 无跨层穿透：CLI 层通过 Service 层 contract 调用事务函数，不绕过 Service 直接操作存储；
  snapshot 构建通过 `dayu.services.write_model_configuration_preapplication` 的 public API 完成

---

## 审查结论

### Verdict: **PASS**

Slice 6 C1+W12 实现忠实地执行了 v4.9 accepted plan 的全部要求：

- 迁移语义完全等价，退出码映射不变
- application runner 的 `functools.partial` 不显式绑定 `run_label`，沿用默认值
- write.py 四处 factory 调用的 label 顺序为默认/默认/verification/clearance
- builder→application 单向依赖，无 cycle/glue/compat re-export
- 所有 `execution_options` 从 `Any`/`object` 收窄为 `ExecutionOptions`
- 真实 owner monkeypatch 已迁移至 `_write_config_application` 模块
- callback 测试真正执行了 partial 回调并断言参数与返回值
- 并发/异常路径无退化
- 全部函数提供完整中文 docstring（Args/Returns/Raises）
- 覆盖率：`_write_config_application.py` 95.92%、`_write_snapshot_builder.py` 100%、
  `write.py` 81.06%，均 ≥ 80%

### Findings Summary

| # | 严重度 | 简述 |
|---|--------|------|
| 1 | **低** | `run_label` 默认值 `"configuration-application"` 在三处签名中作为魔法字符串独立重复 |
| 2 | **低** | `_build_snapshot_for_args` 为纯透传包装函数（架构透明度记录，非缺陷） |

- **High**: 0
- **Medium**: 0
- **Low**: 2

### Open Questions

- **Open H/M/L**: 0/0/0

无。

### Residual Risk

1. `_write_config_application.py` 有 2 条 uncovered statement（覆盖率 95.92%），
   估算为 recript status 非 "applied" 也非 "rolled_back" 的兜底返回 6 分支。
   该分支对应异常配置回执场景，现有 error mapping 参数化测试覆盖了主要异常路径，
   但未覆盖该 status 分支。风险低——该分支仅在与事务函数 contract 不一致的退化场景触发。
2. 即时快照测试对外部 host/service 装配使用 dependency stub，完整 write caller corpus
   （809 tests）提供回归保护。
3. `write.py` 的 81.06% 覆盖率为 HEAD 既有水平，本 Slice 不扩大未覆盖面积。
4. 两个新模块的 factory callback 通过 `functools.partial` 构造；若未来 Python
   `functools.partial` 行为变更（极低概率），需同步更新。

---

*审查完成于 2026-08-08T06:00:01Z · 审查者 DeepSeek v4-pro*
