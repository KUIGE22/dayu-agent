# Code Review — Slice 9 Targeted Re-Review

## Scope

- Mode: current changes (targeted re-review of review fix)
- Branch: `codex/dual-model-research-mvp`
- Base: `89fa4bc` (gateflow: accept cli write architecture plan v5.1)
- Output file: `docs/reviews/code-review-20260808-093800-deepseek.md`
- Primary review artifact: `docs/reviews/code-review-20260808-091000-deepseek.md`
- Adjudication: `docs/reviews/slice-9-code-review-adjudication-20260808-codex.md`
- Fix record: `docs/reviews/slice-9-research-template-modules-fix-20260808-codex.md`
- Included scope: all seven production files + test file (same as original review)
- Parallel review coverage: 无

## Finding Status Summary

| Finding ID | Source | Severity | Description | Adjudication | Status |
|---|---|---|---|---|---|
| DS 1 | DeepSeek #1 | High | RuntimeError escapes runner handler | REJECTED / CLOSED (pre-existing 89fa4bc) | **CLOSED** |
| DS 2 | DeepSeek #2 | Medium | `list_research_templates` docstring | ACCEPTED / FIXED | **CLOSED** |
| DS 3 | DeepSeek #3 | Medium | `build_research_template_usage_guide` docstring | ACCEPTED / FIXED | **CLOSED** |
| DS 4 | DeepSeek #4 | Low | `_load_company_facets_from_manifest` wrapper | REJECTED / CLOSED (accepted-plan ownership) | **CLOSED** |
| DS 5 | DeepSeek #5 | Low | `_materialize_research_after_write` docstring | ACCEPTED / FIXED | **CLOSED** |
| MiMo L-01 | MiMo | Low | 83 function docstrings systematic generalization | ACCEPTED / FIXED | **CLOSED** |

## Per-Finding Verification

### DS 1 (High, REJECTED) — RuntimeError 逃逸

- **裁决**: REJECTED / CLOSED (PRE-EXISTING / OUT-OF-SCOPE)
- **Controller 理由**: HEAD `89fa4bc` 中 materialize/refresh double-fault 抛出 `RuntimeError` 且 runner 仅捕获 `(FileNotFoundError, FileExistsError, ValueError)` 的控制流与当前 stripped-docstring AST 完全相同。Slice 9 是 accepted v5.1 的 exact owner migration，禁止改变存量异常捕获边界。
- **Re-review 确认**: stripped-docstring AST 确认为 0 diff（包含异常处理与传播路径）。`_research_template_materialize.py:237/375/558` 的 `raise RuntimeError` 与 `research_template.py:181` 的 `except (FileNotFoundError, FileExistsError, ValueError)` 均为 HEAD 存量语义。本 re-review 独立确认裁决正确。
- **关闭**: CLOSED，不进入本 Slice 修复范围。

### DS 2 (Medium, FIXED) — `list_research_templates` docstring

- **裁决**: ACCEPTED / FIXED
- **原始问题**: docstring 声称 "本函数不显式抛出异常"，但实际通过 `_resolve_template_dir()` 传播 `FileNotFoundError`。
- **修复证据** (`_research_template_core.py:48-51`):
  ```
  Raises:
      FileNotFoundError: 当打包研究模板目录不存在时，由 ``_resolve_template_dir`` 传播。
      OSError: 当模板目录无法遍历或模板标题文件无法读取时。
  ```
- **验证**: docstring 精确记录了 `FileNotFoundError`（目录缺失）与 `OSError`（目录遍历/标题读取失败）两种异常及触发条件。未增加 catch 或改变空列表语义，符合 Controller 要求的 docstring-only 修复。
- **关闭**: CLOSED ✓

### DS 3 (Medium, FIXED) — `build_research_template_usage_guide` docstring

- **裁决**: ACCEPTED / FIXED
- **原始问题**: docstring 声称 "本函数不显式抛出异常"，但实际通过 `_resolve_template_path()` 传播异常。
- **修复证据** (`_research_template_core.py:977-980`):
  ```
  Raises:
      ValueError: 当模板名无效时。
      FileNotFoundError: 当模板目录或指定模板文件不存在时，由路径解析传播。
      OSError: 当模板标题文件无法读取时，由底层文件操作传播。
  ```
- **验证**: docstring 精确记录了 `ValueError`（名无效）、`FileNotFoundError`（模板/目录缺失）、`OSError`（标题读取失败）三种异常及触发条件。底层异常仍原样传播，符合 Controller 要求。
- **关闭**: CLOSED ✓

### DS 4 (Low, REJECTED) — `_load_company_facets_from_manifest` wrapper

- **裁决**: REJECTED / CLOSED (PRE-EXISTING / ACCEPTED-PLAN OWNERSHIP / NON-COMPAT)
- **Controller 理由**: 该私有函数是 accepted v5.1 S9-CTRL 逐名列入的 exact 83 个迁移 owner 之一，不是为保留旧 import path 新增的 compatibility wrapper。其 stripped-docstring AST 与 HEAD 同名函数精确等价。
- **Re-review 确认**:
  - `_load_company_facets_from_manifest` 的 stripped-docstring AST 0 diff ✓
  - 83/83 owner functions count 精确匹配（helpers 22, core 26, bundle 12, monitoring 11, materialize 12）✓
  - 该函数是 accepted plan 逐名锁定的 owner inventory 成员，不是 `__all__` compat re-export ✓
  - 全量 docstring 修复已将功能写清："通过 research-template routing 真源加载指定清单的公司特征"（`_research_template_helpers.py:363-376`）
- **关闭**: CLOSED ✓

### DS 5 (Low, FIXED) — `write._materialize_research_after_write` docstring

- **裁决**: ACCEPTED / FIXED
- **原始问题**: docstring 声称 "本函数不显式抛出异常"，但底层物化流程传播多种异常。
- **修复证据** (`write.py:92-98`):
  ```
  Raises:
      OSError: 当 write manifest、模板资产或物化产物无法读写时由底层物化流程传播。
      ValueError: 当 manifest 未完成、模板选择无效或物化验证失败时由底层物化流程传播。
      FileNotFoundError: 当 manifest 或选中的模板资产不存在时由底层物化流程传播。
      FileExistsError: 当目标产物已存在且未启用覆盖时由底层物化流程传播。
      RuntimeError: 当物化失败且快照回滚也失败时由底层物化流程传播。
  ```
- **验证**: 五种异常类型（`OSError`、`ValueError`、`FileNotFoundError`、`FileExistsError`、`RuntimeError`）均有精确触发条件说明。function-local import 时序不变，异常传播语义不变。符合 Controller 要求。
- **关闭**: CLOSED ✓

### MiMo L-01 (Low, FIXED) — 83 迁移函数 docstring 系统性泛化

- **裁决**: ACCEPTED / FIXED
- **原始问题**: 83 个迁移函数的 docstring 使用模板化短语（"调用所需的 ``xxx`` 参数"、"函数处理结果"）代替真实行为描述。
- **修复范围**: 五个 owner 模块全部 83 个迁移函数逐函数重写 docstring。
- **修复证据**:
  - 83/83 函数均含完整的中文功能概述（不再使用"提供研究模板数据"等模板短语）
  - 83/83 函数的 Args 全部描述参数的真实业务含义（如 `_print_definition_header` 的 Args 从空的"调用所需的 ``definition`` 参数"改为"待打印表头的模板定义"）
  - 83/83 函数的 Returns 全部描述返回值的真实内容（如 `list_research_templates` 的 Returns 从"函数处理结果"改为"按文件名排序的稳定模板视图元组"）
  - 83/83 函数的 Raises 全部列出可传播异常类型及精确触发条件
  - 自动化检查：泛化模板短语（"调用所需的 ``"、"函数处理结果"、"待处理的研究模板数据"、"提供研究模板"）命中数 = 0
- **行为保护**: 83 函数 stripped-docstring AST 全部 0 diff；签名与 owner 不变 ✓
- **关闭**: CLOSED ✓

## Regression Verification

### Stripped-Docstring AST

```
83 迁移函数: AST 0 diff
2  dataclass: AST 0 diff
entry + 39 runners: AST 0 diff

FunctionDef/ClassDef: helpers=(22,2) core=(26,0) bundle=(12,0) monitoring=(11,0) materialize=(12,0) main=(40,0)
```

### 测试

```
323 passed in 2.08s (research-template corpus)
812 passed in 11.76s (write corpus)
```

### 静态门禁

```
pyright: 0 errors, 0 warnings, 0 informations
ruff F/I: All checks passed!
```

### DAG / Import Smoke

```
main → all 5 owners ✓
core → helpers ✓
bundle → core, helpers ✓
monitoring → bundle, core, helpers ✓
materialize → monitoring, bundle, core, helpers ✓
helpers → (none of the other owners) ✓
zero cycles ✓
zero reverse imports ✓
```

### Identity / Owner

```
45 functional bindings: 6/18/6/9/6 → all identity-verified ✓
write function-local lazy import: old 0 / new 1 → correct owner ✓
39 runner global lookups: unchanged ✓
```

### Coverage

继承实现阶段精确证据（docstring-only fix 不改变可执行 statement）：
- helpers `87.18%` ✓
- core `89.33%` ✓
- bundle `83.04%` ✓
- monitoring `81.41%` ✓
- materialize `89.96%` ✓
- main `82.81%` ✓
- write `83.07%` ✓
- 七文件均 `>=80%` ✓

## Open Questions

无。

## Residual Risk

1. DS 1 RuntimeError double-fault runner 捕获范围是 HEAD 存量语义，本 Slice 不改变。如要改变需独立语义 work unit 与 runner-level 回归测试。
2. 83 函数 docstring 批量改写已在 stripped-docstring AST 0 diff 门禁和 323+812 tests 下确认无行为漂移。

## Verdict

**PASS** — 全部 6 项 finding CLOSED，终态 open High/Medium/Low = `0/0/0`。

Controller 裁决全部确认正确：DS 2/3/5 与 MiMo L-01 的 docstring 修复全部 CLOSED 且有直接证据支撑；DS 1 的 RuntimeError 确认为 HEAD 89fa4bc 存量语义（stripped-docstring AST 0 diff）；DS 4 的私有 wrapper 确认为 accepted-plan 逐名 owner 迁移项而非 compat 代码。83+2+entry+39 stripped-docstring AST 全部 0 diff；323+812 tests PASS；pyright 0 errors；Ruff delta 0；DAG/identity/owner 无回归。
