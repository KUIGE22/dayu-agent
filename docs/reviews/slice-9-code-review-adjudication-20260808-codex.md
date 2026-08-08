# Slice 9 Code Review Controller 裁决记录

- **日期**: 2026-08-08
- **基线**: `89fa4bc gateflow: accept cli write architecture plan v5.1`
- **分支**: `codex/dual-model-research-mvp`
- **Gate**: Slice 9 code review adjudication
- **状态**: CLOSED / DUAL RE-REVIEW PASS
- **Controller open H/M/L**: `0/0/0`

## 输入 artifact

- DeepSeek：`docs/reviews/code-review-20260808-091000-deepseek.md`，Verdict
  `PASS`。正文实际列出 1 High + 2 Medium + 2 Low，共 5 项 finding。
- MiMo：`docs/reviews/code-review-20260808-091001-mimo.md`，Verdict `PASS`，
  open High/Medium/Low=`0/0/1`。
- 实现记录：
  `docs/reviews/slice-9-research-template-modules-implementation-20260808-codex.md`。
- Accepted plan：`docs/plans/2026-08-07-cli-write-architecture-refactor.md`
  v5.1 ACCEPTED / DUAL PLAN RE-REVIEW PASS。

DeepSeek Verdict 段写成“1 High + 2 Medium + 3 Low”，但 Findings 正文只有
5 个编号项，即 1 High + 2 Medium + 2 Low。Controller 以可定位、可逐项验证的
5 项正文为裁决对象，不使用误写的汇总计数。

## Controller 总体结论

Slice 9 的 83 个函数、2 个 dataclass、主模块 entry + 39 runners 在去除
docstring 后均与 HEAD `89fa4bc` AST 精确等价。Controller 接受三项
DeepSeek docstring 精度问题与 MiMo L-01，并以一次统一的 docstring-only
fix 改正；不接受 RuntimeError 处理与私有 owner wrapper 两项语义扩张。
修复后没有可执行语句、签名、owner、控制流、I/O、异常语义或测试契约变化；
Controller open H/M/L=`0/0/0`。

## Finding 逐项裁决

### DS 1（High）— `RuntimeError` 逃逸 runner 异常处理

- **裁决**: `REJECTED / CLOSED (PRE-EXISTING / OUT-OF-SCOPE)`
- **理由**:
  1. HEAD `89fa4bc` 中 materialize / refresh double-fault 抛出 `RuntimeError`、
     runner 只捕获 `FileNotFoundError` / `FileExistsError` / `ValueError` 的控制流
     与当前 stripped-docstring AST 完全相同。
  2. Slice 9 是 accepted v5.1 的 exact owner migration，禁止改变存量异常捕获边界。
     把 `RuntimeError` 加入 runner 捕获列表即使只需一行，也是计划外的用户可见
     控制流变化。
  3. 该场景可作为后续独立错误处理 work unit，不归因为本 Slice
     引入的 defect。
- **处理**: 不改生产控制流或测试。

### DS 2（Medium）— `list_research_templates` 异常 docstring 失真

- **裁决**: `ACCEPTED / FIXED / CLOSED`
- **修复**: 明确记录 `_resolve_template_dir` 传播的
  `FileNotFoundError`，以及目录遍历、标题读取可传播的 `OSError`。
- **范围**: 仅改 docstring，未增加 catch 或改变空列表语义。

### DS 3（Medium）— `build_research_template_usage_guide` 异常 docstring 失真

- **裁决**: `ACCEPTED / FIXED / CLOSED`
- **修复**: 精确记录模板名无效的 `ValueError`、模板目录或文件缺失的
  `FileNotFoundError`，以及标题文件读取失败的 `OSError`。
- **范围**: 仅改 docstring，底层异常仍原样传播。

### DS 4（Low）— `_load_company_facets_from_manifest` 被视为透明 wrapper

- **裁决**: `REJECTED / CLOSED (PRE-EXISTING / ACCEPTED-PLAN OWNERSHIP / NON-COMPAT)`
- **理由**:
  1. 该私有函数是 accepted v5.1 S9-CTRL 逐名列入的 exact 83 个迁移 owner
     之一，不是为保留旧 import path 新增的 compatibility wrapper。
  2. 其 stripped-docstring AST 与 HEAD 同名函数精确等价；移除它会改变
     accepted owner inventory 及依赖边界。
  3. 全量 docstring 修复已把“通过 routing 真源加载公司特征”写清，
     但这是 MiMo L-01 下的准确性修订，不表示接受 wrapper defect。
- **处理**: 保留计划锁定的 owner 与函数体，不改 caller/import DAG。

### DS 5（Low）— `write._materialize_research_after_write` 异常 docstring 失真

- **裁决**: `ACCEPTED / FIXED / CLOSED`
- **修复**: 明确列出底层 materialize owner 原样传播的 `OSError`、
  `ValueError`、`FileNotFoundError`、`FileExistsError` 和 double-fault
  `RuntimeError`及各自触发条件。
- **范围**: 仅改 docstring，function-local import 时序和异常传播语义不变。

### MiMo L-01（Low）— 83 个迁移函数 docstring 系统性泛化

- **裁决**: `ACCEPTED / FIXED / CLOSED`
- **修复**:
  1. 逐函数重写五个 owner 内 exact 83 个 docstring，用函数真实的输入、
     输出、校验、副作用和异常传播代替模板化表述。
  2. 每个函数保留完整中文概览、Args、Returns、Raises；所有实参名均有
     对应说明，泛化短语审计结果为 0。
  3. MiMo 称 82 项泛化；Controller 为避免遗留单个边界项，对 exact 83
     全量迁移函数统一执行精度审计与修复。
- **行为保护**: 83 个函数去 docstring AST 差异为 0；签名与 owner 不变。

## 修后证据

- 83 个迁移函数 + 2 个 dataclass + retained entry/39 runners 去 docstring
  AST 差异：`0 / 0 / 0`。
- docstring 结构审计：83/83 均包含中文功能概述、Args、Returns、Raises；
  实参遗漏 0，已知泛化模板短语残留 0。
- 功能测试：323 research-template tests 与 812 write tests 均 PASS。
- `pyright dayu/cli/ tests/cli/test_research_template_command.py`：0 errors。
- Ruff F/I：PASS；full-rule finding-code multiset positive delta `{}`。
- 相对已验证的实现，本 fix 只改五个 owner 与 `write.py` 的 docstring，
  `research_template.py` 也没有新的可执行变化；七文件 statement 与 coverage
  corpus 不变，继承实现阶段七文件精确 coverage，均 `>=80%`。
- `git diff --check`：PASS。

## Gate 状态

- 接受并修复：DS 2 / 3 / 5，MiMo L-01。
- Rejected-with-reason：DS 1 / 4。
- Controller open High/Medium/Low=`0/0/0`。
- DeepSeek targeted re-review：
  `docs/reviews/code-review-20260808-093800-deepseek.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo targeted re-review：
  `docs/reviews/code-review-20260808-093801-mimo.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- 两路均确认初审 6 项 observations 全部 CLOSED，无新 finding，无需进一步
  code、tests、README 或 plan fix；本 adjudication gate 已 CLOSED。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
