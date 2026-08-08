# Code Review

## Scope

- **Mode**: current changes
- **Branch**: `codex/dual-model-research-mvp`
- **Base**: HEAD `fcf4602 gateflow: accept cli write execution manual recovery slice 7`
- **Output file**: `docs/reviews/code-review-20260808-073322-deepseek.md`
- **Included scope**:
  - `dayu/cli/commands/write.py`（修改）
  - `dayu/cli/commands/_write_challenger.py`（新建）
  - `dayu/cli/commands/_write_config_rollback.py`（新建）
  - `tests/application/test_write_challenger.py`（修改）
  - `tests/application/test_write_cli_dispatch.py`（修改）
  - `tests/application/test_write_model_configuration_preapplication.py`（修改）
  - `tests/engine/test_cli_running_config.py`（修改）
- **Excluded scope**: 无
- **Parallel review coverage**: 无（单人全量走读）

---

## 前置结构验证（全部 PASS）

以下验证所有通过，不作为 Finding 列出，仅记录证据：

| 验证项 | 结果 | 证据 |
|---|---|---|
| `_write_challenger.py` 顶级函数数 | 13（exact） | AST 解析确认13个 `FunctionDef` |
| `_write_config_rollback.py` 顶级函数数 | 1（exact） | AST 解析确认1个 `FunctionDef` |
| `write.py` 本地定义数 | 2（`_materialize_research_after_write`、`run_write_command`） | AST 解析确认 |
| `write.py` 旧14定义残留 | 0 | AST 解析确认 |
| `write.py` 从 `_write_challenger` import 数 | 10（exact） | AST 解析确认 |
| `write.py` 从 `_write_config_rollback` import 数 | 1（exact） | AST 解析确认 |
| `run_write_command` 使用的 Challenger 符号 | 10（exact） | AST 解析确认 |
| `run_write_command` 使用的 rollback 符号 | 1（exact） | AST 解析确认 |
| 内部 helper（`_challenger_preflight_cli_args`、`_load_current_challenger_proposal`、`_manifest_has_usable_company_facets`）在 `write.py` 中的兼容绑定 | 0 | AST 解析确认 |
| 14 迁移函数去 docstring 后 AST 等价 | 14/14 PASS | AST dump 逐函数对比 |
| 反向 import（新 owner → `write.py`） | 0 | AST 解析确认 |
| `MODULE` 本地定义 | 0（均从 `_write_config_helpers` 单一真源 import） | AST 解析确认 |
| `Any` semantic uses | `_write_challenger.py`: 6、`write.py`: 1、合计 7（HEAD 7→当前 7） | AST 解析确认 |
| 既有 function-local domain import（`_manifest_has_usable_company_facets` 中 `from dayu.cli.research_template_routing import load_company_facets_from_manifest`） | 按 exact AST 保留 | 代码逐行确认 |
| owner/compat lazy 新增 import | 0 | 代码审查确认 |
| `git diff --check` | PASS | 实现文档确认 |
| Ruff full-rule finding-code multiset | HEAD 与当前无正增量 | 实现文档确认 |
| Pyright（目标文件） | `0 errors, 0 warnings, 0 informations` | 实现文档确认 |
| 测试通过 | 812 passed | 实现文档确认 |
| 覆盖率 | `_write_challenger.py`: 83.000000%、`_write_config_rollback.py`: 91.176471%、`write.py`: 83.068783%（均 ≥80%） | 实现文档确认 |

---

## Findings

### 01-未修复-中-`_build_auto_bootstrap_args` 缺乏直接单元测试覆盖

- **入口/函数**: `_build_auto_bootstrap_args` → `run_write_command`（auto 研究引导路径）
- **文件（行号）**: `dayu/cli/commands/_write_challenger.py:665-680`；被 `dayu/cli/commands/write.py:649` 调用
- **输入场景**: 用户使用 `--research-template auto`，且既有 manifest 不含可用公司画像时，`run_write_command` 调用 `_build_auto_bootstrap_args(args)` 构造引导参数，再通过 `setup_write_config` 构建引导配置并执行 `_run_write_stage`
- **实际分支**: 该 helper 的行为是：复制原始 `args` → 将 `template`、`research_template` 置为 `None` → 将 `infer` 置为 `True`。引导阶段依赖此修改后的参数正确关闭模板物化并开启画像推断
- **预期行为**: 任一参数修改错误（如未清除 `research_template`）将导致引导阶段行为异常——可能再次触发 auto 模板解析而非执行画像推断，形成逻辑循环或错误输出
- **实际行为**: 当前行为和 HEAD 一致，但无测试直接断言此 helper 的输出
- **直接证据**:
  - `_write_challenger.py:678-679`: `values.update({"template": None, "research_template": None, "infer": True})`
  - 测试 corpus 中无 `test_build_auto_bootstrap_args` 或等效断言
  - `_needs_auto_research_bootstrap` 有间接覆盖（`test_write_command_auto_bootstrap_when_manifest_missing_facets` 通过 `run_write_command` 端到端覆盖），但 `_build_auto_bootstrap_args` 在集成测试中被 mock 绕过
- **影响**: 若未来修改此 helper（如增减参数清除项），回归可能无法被单元测试捕获；端到端测试可能因 mock 路径而未能覆盖真实行为
- **建议改法和验证点**: 新增 1-2 个单元测试：a) 验证 `template` 和 `research_template` 被置为 `None`；b) 验证 `infer` 被置为 `True`；c) 验证原始 `args` 对象未被修改（`dict(vars(args))` 创建了新副本）
- **修复风险（低）**: 纯测试补充，不改变生产代码
- **严重程度（中）**: 函数承载关键的参数转换语义，但当前通过集成路径间接覆盖；未来重构时缺乏直接回归屏障

### 02-未修复-低-`_challenger_preflight_cli_args` 切片语义未经直接测试验证

- **入口/函数**: `_challenger_preflight_cli_args`
- **文件（行号）**: `dayu/cli/commands/_write_challenger.py:49-75`
- **输入场景**: Challenger preflight CLI 参数构造，在 `_verify_challenger_preflight_approval_before_host`（行 123）和 `_build_challenger_run_plan_from_args`（行 203）中被调用。行 203 使用 `[1:]` 切片去掉 `--preflight-only`，仅将模型覆盖参数纳入双跑计划
- **实际分支**: 函数构造 `["--preflight-only", "--challenger-model-name", "xxx", ...]`。调用方使用 `[1:]` 时得到 `["--challenger-model-name", "xxx", ...]`
- **预期行为**: `[1:]` 切片假设列表第一个元素始终是 `--preflight-only`。若未来函数修改了参数顺序或允许空结果，切片语义将断裂
- **实际行为**: 当前行为正确（与 HEAD AST 一致），但切片假设未经过测试断言
- **直接证据**:
  - `_write_challenger.py:64`: `result = ["--preflight-only"]`
  - `_write_challenger.py:203`: `challenger_cli_args=(_challenger_preflight_cli_args(args)[1:])`
  - 无测试直接断言 `_challenger_preflight_cli_args` 的返回值结构
- **影响**: 若函数返回值结构变更，运行计划审批校验可能产生不匹配但不会直接报错——仅导致审批拒绝（exit 4），排查困难
- **建议改法和验证点**: 新增 1 个单元测试：验证 `_challenger_preflight_cli_args` 返回的列表以 `"--preflight-only"` 开头，且 `[1:]` 切片后仅含模型覆盖参数
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**: 函数逻辑简单（一个标志+两个可选参数），当前行为正确；无测试主要影响未来可维护性

### 03-未修复-低-`_assert_challenger_run_output_boundaries` 错误路径未经直接测试覆盖

- **入口/函数**: `_assert_challenger_run_output_boundaries`
- **文件（行号）**: `dayu/cli/commands/_write_challenger.py:215-244`
- **输入场景**: 输出映射无效（`outputs` 不是 `Mapping`）、输出位于工作区外、输出路径已存在
- **实际分支**: 三种错误分别抛出 `ValueError`（输出无效/位于工作区外）或 `FileExistsError`（已存在）
- **预期行为**: 错误被调用方 `_verify_and_consume_challenger_run_approval_before_host`（行 415-418）和 `run_write_command`（行 332-335）的 try-except 捕获，返回 exit code 2
- **实际行为**: 两处调用方均正确捕获这些异常，但无测试直接触发这些错误路径
- **直接证据**:
  - `_write_challenger.py:237-244`: 三个 `raise` 语句
  - `_write_challenger.py:459-470`（`_verify_and_consume_challenger_run_approval_before_host`）和 `write.py:336-347`（`run_write_command`）：异常捕获范围包含 `FileExistsError`、`ValueError`
  - 测试 corpus 中无测试通过无效 `plan["outputs"]` 或已存在路径触发这些分支
- **影响**: 若异常类型被意外修改或捕获范围变窄，错误处理可能断裂
- **建议改法和验证点**: 新增参数化测试覆盖：a) `outputs` 不是字典 → `ValueError` → exit 2；b) 输出在工作区外 → `ValueError` → exit 2；c) 输出已存在 → `FileExistsError` → exit 2
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**: 错误路径逻辑简单，且通过调用方的 try-except 间接保护；覆盖率已 ≥80%

---

## Open Questions

无。

---

## Residual Risk

1. **既有 sqlite `ResourceWarning`**: 全量测试 812 passed 附带既有 sqlite 资源未关闭警告（`ResourceWarning`）。本 Slice 不改变资源生命周期管理，此风险为 pre-existing。
2. **engine test 既有 `I001`**: Ruff `I001`（import 排序）出现在 `tests/engine/test_cli_running_config.py`，为 HEAD 既有，本 Slice 未新增或扩散。
3. **既有 function-local domain import**: `_manifest_has_usable_company_facets` 中的 `from dayu.cli.research_template_routing import load_company_facets_from_manifest` 按 exact AST 保留。它不是 lazy seam 或 compat wrapper，但若 `research_template_routing` 模块重构，此 import 需同步更新——这是 HEAD 既有的设计选择，不在本 Slice 范围内解决。
4. **Rollback `build_snapshot_builder` 默认 label**: `_run_write_model_configuration_rollback` 调用 `build_snapshot_builder` 时不传 `run_label`，依赖其默认值。若默认值语义变更，rollback 快照标记可能不准确。这是 HEAD 既有行为。

---

## Verdict: PASS

本 Slice 的代码迁移是结构正确、AST 等价、无新增缺陷的纯重构：

- 14 个迁移函数去 docstring 后与 HEAD AST 逐字节一致
- 10+1 真实 import/caller 对应关系精确，无兼容绑定或 wrapper
- 反向依赖为 0，MODULE 单一真源，import 无遗漏
- 退出码/异常分类/控制流与 HEAD 一致
- `Any` 使用无扩散（7→7），typings import 仅为新 owner 承载既有签名
- Pyright/Ruff/测试/覆盖率全部通过门禁
- 既有 function-local domain import 按 exact AST 保留

三个 L-M 级 finding 均为测试覆盖补充建议，无生产代码缺陷。建议在后续 Slice 中择机补充测试覆盖。
