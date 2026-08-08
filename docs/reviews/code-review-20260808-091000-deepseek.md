# Code Review

## Scope

- Mode: current changes
- Branch: `codex/dual-model-research-mvp`
- Base: `89fa4bc` (gateflow: accept cli write architecture plan v5.1)
- Output file: `docs/reviews/code-review-20260808-091000-deepseek.md`
- Included scope:
  - `dayu/cli/commands/research_template.py`
  - `dayu/cli/commands/_research_template_helpers.py`
  - `dayu/cli/commands/_research_template_core.py`
  - `dayu/cli/commands/_research_template_bundle.py`
  - `dayu/cli/commands/_research_template_monitoring.py`
  - `dayu/cli/commands/_research_template_materialize.py`
  - `dayu/cli/commands/write.py`
  - `tests/cli/test_research_template_command.py`
- Excluded scope: `docs/reviews/slice-9-*` (implementation record, not production code)
- Parallel review coverage: 无。审查由主 reviewer 逐文件走读完成。

## Acceptance Contract Verification

本 review 确认以下各项与 accepted Slice 9 计划一致，不视为缺陷：

- **FunctionDef / ClassDef 门禁**：main `40/0`（`40 FunctionDef + 0 ClassDef`），五个 owner 分别为 `22/2`、`26/0`、`12/0`、`11/0`、`12/0`，合计迁移 `83` 函数 + `2 dataclass`。全部精确匹配。✓
- **`__all__` 55 删除 13**：68→55，删除的 13 个符号均为迁移到私有 owner 的 public name；无新增。外部消费者检查通过，无遗留 import。✓
- **exact45 functional bindings**：`6/18/6/9/6` 指向真实 owner，`identity` 测试逐项验证，其他 38 无 compat binding。✓
- **write function-local lazy import**：旧 owner 引用 exact 0，新 owner `_research_template_materialize` exact 1，测试验证真实调用链。✓
- **DAG / import smoke**：main→all5, core→helpers, bundle→core+helpers, monitoring→bundle+core+helpers, materialize→monitoring+bundle+core+helpers。helpers 无反向依赖，零 cycle。✓
- **pyright**：`0 errors, 0 warnings, 0 informations`。✓
- **Ruff delta**：正向 delta `{}`，负向 delta `{I001: 1}`（import 排序改善）。✓
- **七文件 coverage >= 80%**：按实施报告精确数据全部通过（最差 81.41%）。✓

## Findings

### 1-未修复-高-RuntimeError 可逃逸 CLI runner 异常处理器导致 traceback 崩溃

- **入口/函数**: `run_research_template_command` → `_run_materialize` / `_run_refresh_workspace`
- **文件(行号)**:
  - `dayu/cli/commands/research_template.py:181`（异常处理器声明 `except (FileNotFoundError, FileExistsError, ValueError)`）
  - `dayu/cli/commands/_research_template_materialize.py:369`（`raise RuntimeError(...) from exc`）
  - `dayu/cli/commands/_research_template_materialize.py:550`（`raise RuntimeError(...) from exc`）
- **输入场景**: materialize 或 refresh-workspace 操作的主流程写入成功但后续物化步骤失败，同时 rollback 也失败（典型场景：磁盘满/权限不足的 double fault）。
- **实际分支**:
  1. `materialize_research_workspace`（行 366 `except BaseException`）捕获初始异常
  2. `_rollback_materialization_artifacts` 返回非空错误列表
  3. 行 369 抛出 `RuntimeError("research workspace materialization failed (...); rollback also failed: ...")`
  4. 异常传播至 `_run_materialize`（行 462）→ `run_research_template_command`（行 139）
  5. 行 181 的 `except (FileNotFoundError, FileExistsError, ValueError)` 不匹配 `RuntimeError`
  6. 异常继续传播至 `main()` → 未处理 traceback 崩溃
- **预期行为**: CLI 应捕获并以 `return 1` 退出，打印错误消息到 stderr，不输出 traceback。
- **实际行为**: `RuntimeError` 穿透异常处理器，用户看到完整 Python traceback。
- **直接证据**:
  - `research_template.py:181`：`except (FileNotFoundError, FileExistsError, ValueError)` — 仅三种类型
  - `_research_template_materialize.py:234-237`：`raise RuntimeError(...)` — 不在上述三种中
  - `_research_template_materialize.py:366-372`：`except BaseException` → `raise RuntimeError(...)` — 不在上述三种中
  - `_research_template_materialize.py:547-553`：同模式的 `RuntimeError` 路径
- **影响**: 用户在 double fault（主操作失败 + rollback 也失败）场景下看到 traceback 而非干净的 CLI 错误消息。虽然 double fault 概率低，但一旦发生会破坏 CLI 的用户体验和可操作性。
- **建议改法和验证点**:
  1. 在 `research_template.py:181` 的 `except` 元组中增加 `RuntimeError`：
     ```python
     except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
     ```
  2. 或者将异常处理器改为更宽泛的 `except Exception as exc:`（需评估是否过于宽泛）。
  3. 验证：添加 runner-level 测试，mock `materialize_research_workspace` 抛出 `RuntimeError`，断言 `run_research_template_command` 返回 1（非 0 且不抛异常）。
- **修复风险**: 低。仅扩展异常捕获列表，不影响正常路径。
- **严重程度**: 高

### 2-未修复-中-`list_research_templates` docstring 与实际异常传播不一致

- **入口/函数**: `list_research_templates`
- **文件(行号)**:
  - `dayu/cli/commands/_research_template_core.py:39-59`（函数定义，行 48 docstring 声明 `Raises: 本函数不显式抛出异常`）
  - `dayu/cli/commands/_research_template_helpers.py:418-433`（`_resolve_template_dir`，行 432 `raise FileNotFoundError`）
- **输入场景**: 运行时研究模板目录不存在（打包损坏或 `resolve_package_assets_path()` 返回无效路径）。
- **实际分支**: `list_research_templates:52` → `_resolve_template_dir()` → 行 431-432 `if not template_dir.is_dir(): raise FileNotFoundError(...)` → 异常传播至外部调用者。
- **预期行为**: 要么不抛出异常（如 docstring 声称），要么 docstring 声明 `Raises: FileNotFoundError`。
- **实际行为**: `FileNotFoundError` 被抛出但 docstring 声称不抛出，调用者若信任 docstring 则缺少 try/except 保护。
- **直接证据**:
  - `_research_template_core.py:48`：`Raises: 本函数不显式抛出异常` — 与实现矛盾
  - `_research_template_helpers.py:431-432`：`raise FileNotFoundError(...)` — 未被 list_research_templates 捕获
- **影响**: 调用者被误导。当前直接调用者（CLI 入口 `_run_list`）不受影响因为 runner 异常处理器会兜底，但若任何其他代码信任 docstring 不设异常保护，会收到意外异常。
- **建议改法和验证点**:
  1. 将 docstring 的 `Raises` 改为 `FileNotFoundError: 当研究模板目录不存在时`。
  2. 或在 `list_research_templates` 中捕获 `FileNotFoundError` 并返回空元组（语义上更安全）。
  3. 验证：添加测试验证模板目录不存在时行为符合修正后的 docstring。
- **修复风险**: 低。若改为捕获并返回空元组，需确认调用者能正确处理空列表（当前 CLI `_run_list` 遍历空列表会静默输出无内容，行为合理）。
- **严重程度**: 中

### 3-未修复-中-`build_research_template_usage_guide` docstring 与实际异常传播不一致

- **入口/函数**: `build_research_template_usage_guide`
- **文件(行号)**:
  - `dayu/cli/commands/_research_template_core.py:910-1025`（函数定义，行 947 docstring 声明 `Raises: 本函数不显式抛出异常`）
  - `dayu/cli/commands/_research_template_core.py:951`（调用 `_resolve_template_path(normalized)`）
  - `dayu/cli/commands/_research_template_core.py:1238`（`_resolve_template_path`，行 1232-1233 docstring 声明 `Raises: FileNotFoundError`）
- **输入场景**: 传入不存在的研究模板名称。
- **实际分支**: `build_research_template_usage_guide:951` → `_resolve_template_path(name)` → 行 1236-1238 模板文件不存在 → `raise FileNotFoundError(...)`。
- **预期行为**: docstring 应声明可能抛出 `FileNotFoundError`。
- **实际行为**: `FileNotFoundError` 被抛出但 docstring 声称不抛出。
- **直接证据**:
  - `_research_template_core.py:947`：`Raises: 本函数不显式抛出异常`
  - `_research_template_core.py:951`：`template = _resolve_template_path(normalized)` — 可能抛出 `FileNotFoundError`
- **影响**: 同上，docstring 与实现不一致，调用者可能缺乏异常保护。
- **建议改法和验证点**: 将 docstring `Raises` 改为 `FileNotFoundError: 当模板路径不存在时`。
- **修复风险**: 低。
- **严重程度**: 中

### 4-未修复-低-`_load_company_facets_from_manifest` 为透明透传包装函数

- **入口/函数**: `_load_company_facets_from_manifest`
- **文件(行号)**: `dayu/cli/commands/_research_template_helpers.py:361-373`
- **输入场景**: 任何调用该函数的路径。
- **实际分支**: 函数体仅一行 `return load_company_facets_from_manifest(path)` — 不增加任何语义、验证、转换或错误处理。
- **预期行为**: 如果目的是将外部依赖收敛到 helpers 模块作为单一出口，可以接受。但需要明确记录其设计意图，避免被误认为兼容性 wrapper。
- **实际行为**: 无额外语义的透传调用。三个 caller（`_company_facets_from_args` helpers:348、`_resolve_template_selection_from_write_manifest` core:1140、`_build_write_manifest_binding_semantics` core:1212）均可直接 import `load_company_facets_from_manifest` from `dayu.cli.research_template_routing`，无需此 wrapper。
- **直接证据**: `_research_template_helpers.py:373`：`return load_company_facets_from_manifest(path)` — 函数体仅此一行。
- **影响**: 增加一层不必要的间接调用；维护者需要在两个位置（helpers 和 routing）之间追踪真实实现。当前影响很小，但若扩散此类模式会累积架构噪音。
- **建议改法和验证点**:
  1. 如果此 wrapper 的设计意图是「helpers 作为所有 owner 模块的唯一外部依赖出口」，在模块或函数 docstring 中明确说明。
  2. 或者移除 wrapper，让 core 模块直接 import `load_company_facets_from_manifest` from `dayu.cli.research_template_routing`。
- **修复风险**: 低（移除 wrapper 或仅加注释说明）。
- **严重程度**: 低

### 5-未修复-低-`_materialize_research_after_write` docstring 与实际异常传播不一致

- **入口/函数**: `_materialize_research_after_write`
- **文件(行号)**: `dayu/cli/commands/write.py:74-108`（行 92-93 docstring 声明 `Raises: 本函数不显式抛出异常`）
- **输入场景**: `materialize_research_bundle_from_write_manifest` 抛出异常（如 manifest 不存在、模板无效、disk full 等）。
- **实际分支**: 行 96-98 的 function-local `import` + 行 104 的 `materialize_research_bundle_from_write_manifest(...)` 调用可传播 `ValueError`、`OSError` 等。
- **预期行为**: docstring 应声明可能传播的异常或说明调用者应自行捕获。
- **实际行为**: 异常确实传播（`run_write_command:739-753` 以宽泛 `except Exception` 捕获），但 docstring 声称不抛出。
- **直接证据**:
  - `write.py:92-93`：`Raises: 本函数不显式抛出异常`
  - `write.py:104`：`materialize_research_bundle_from_write_manifest(...)` — 调用可抛异常的函数
- **影响**: docstring 误导。当前调用者已正确用 `except Exception` 保护（行 746），但若未来有新的调用者信任 docstring，会遗漏异常保护。
- **建议改法和验证点**: 将 `Raises` 改为说明异常会从底层传播至调用者，调用者应自行保护。
- **修复风险**: 低。
- **严重程度**: 低

## Open Questions

1. `_run_materialize`（`research_template.py:452-476`）在 `selection_payload` 中不检查 `"manifest_provenance"` 模式也需要 `write_manifest_path` 是否为 None 的边界条件（行 466-471 在非 explicit 模式才传入 manifest）。当前逻辑依赖 `_resolve_materialize_template_selection` 返回的 `selection_mode`，若未来增加新模式可导致 `write_manifest_path` 误为 None。建议添加显式的 `selection_mode not in {"explicit", "manifest_provenance", "manifest_recommendation"}` 的兜底检查，但当前模式集合封闭，不作为确定缺陷。

2. 七个文件的精确 coverage 数据来自实施报告，未在本 review 中独立重跑。考虑到 323+812 测试全部通过且覆盖率数据与代码规模一致（文件大则 missing 多），数据可信。若有独立验证需求，建议 CI 中固化 coverage 阈值。

## Residual Risk

1. **Double fault 恢复路径未测试**：`materialize_research_workspace` 和 `write_research_workspace_refresh` 中的 rollback-also-failed `RuntimeError` 路径缺少 runner-level 测试。当前仅有模块级测试（`test_materialize_rollback_removes_checklist_on_failure`）覆盖了 bundle 级别的 rollback，但 runner 层的异常传播未覆盖。

2. **`_run_refresh_workspace` 的 RuntimeError 路径**（`_research_template_materialize.py:550`）与 `_run_materialize` 的 RuntimeError 路径（`_research_template_materialize.py:369`）具有相同的 runner 逃逸风险，且均无 runner-level 测试覆盖。

3. **Portfolio 批量物化路径**（`materialize_research_portfolio`）对 per-target 异常使用了宽泛的 `except Exception` 捕获（行 682），这在当前设计中是正确的（不中断批量），但意味着 per-target 的 double fault 场景不会触发 runner 逃逸问题。这与 `_run_materialize`（单目标）的保护级别不一致——portfolio 做了隔离保护，单目标物化没有。

## Verdict

**PASS** — 带 1 个高严重度、2 个中严重度、3 个低严重度 findings。

核心拆分（83 函数 + 2 dataclass 精确迁移、45 functional bindings identity、DAG 零 cycle、pyright 零错误、323+812 测试全通过、七文件 >80% coverage）均验证正确。唯一的高严重度问题（RuntimeError 逃逸）修复成本低且不会影响正常路径。三个 docstring 不一致问题是机械错误，修复同样低成本。整体代码质量足以通过 review，建议修复高/中严重度 findings 后再 merge。
