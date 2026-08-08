# Plan Review: v5.1 Slice 9 DeepSeek Corrective Re-Review

- **审查时间**: 2026-08-08 08:35 UTC
- **审查人**: DeepSeek（planreview skill, corrective pass）
- **基线**: clean HEAD `1d0f9e6`（Slice 8 accepted）
- **审查范围**: Slice 9 v5.1 CANDIDATE 全文 + Controller erratum + 082000 L-01/L-02 纠正
- **此前审查**:
  - `docs/reviews/plan-review-20260808-075500-deepseek.md`（初审，FAIL, 3H/3M/3L）
  - `docs/reviews/plan-review-20260808-082000-deepseek.md`（复审，PASS, 0H/0M/2L）
  - `docs/reviews/plan-review-20260808-082001-mimo.md`（MiMo 复审，PASS, 0H/0M/0L）
- **Controller 裁决**: `docs/reviews/plan-slice-9-v5.1-ownership-dag-erratum-20260808-codex.md`（L-01 REJECTED-WITH-REASON / CLOSED, L-02 REJECTED-WITH-REASON / CLOSED, Controller open H/M/L=0/0/0）
- **审查模式**: 只读。纠正两项 LOW 的事实前提，独立复核 Controller 裁决与完整 v5.1。禁止修改任何 artifact。

---

## Verdict: PASS（open High/Medium/Low = 0/0/0）

**根因**: 082000 的 L-01 基于事实错误（声称 Slice 8 尚未实施）；L-02 自承非 bug。经独立复核 Controller 裁决，两项均已 CLOSED。v5.1 全部 claims 在独立 AST/callgraph 核验下闭合，无残余 findings。Slice 9 达到 code-generation-ready，可实施。

---

## 0. L-01/L-02 纠正与独立复核

### 0.1 L-01（行号漂移）—— 事实错误，已 CLOSED

**082000 原文**: "Slice 8（`_write_challenger + _write_config_rollback`）在 Slice 9 之前实施，可能改变 `write.py` 行号。若 Slice 8 在 `_materialize_research_after_write` 函数之前插入/删除代码，line 81 会漂移。"

**事实纠正**: 此前提错误。HEAD `1d0f9e6` **已是 Slice 8 accepted 后的基线**：

```bash
$ git log --oneline -1
1d0f9e6 gateflow: accept cli write challenger rollback slice 8
```

`write.py` 在 HEAD `1d0f9e6` 的精确定义已稳定——仅 2 个顶层函数（`run_write_command` + `_materialize_research_after_write`），741 行。line 81 的 function-local import 是**当前实测值**，不是历史遗留行号：

```bash
$ python3 -c "
import ast
tree = ast.parse(open('dayu/cli/commands/write.py').read())
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_materialize_research_after_write':
        for child in ast.walk(node):
            if isinstance(child, ast.ImportFrom):
                if child.module == 'dayu.cli.commands.research_template':
                    print(f'line {child.lineno}: from {child.module} import ...')
"
# → line 81: from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest
```

**Plan 语义锚点**: §9e 不仅引用 line 81，更以三重语义锚定锁定此 import：
1. **函数锚点**: `_materialize_research_after_write` 内的 function-local import
2. **旧 owner 门禁**: `write.py` 旧 lazy owner 路径 exact 0（grep 可审计）
3. **新 owner 门禁**: 新 materialize owner 路径 exact 1（grep 可审计）

这三重锚定不依赖任何行号。即使未来有人在 `_materialize_research_after_write` 之前插入代码改变行号，grep 门禁仍然有效。

**Controller 裁决**: REJECTED-WITH-REASON / CLOSED。裁决正确。L-01 的前提不成立，plan 的锚定语义超越了行号。

**本审查确认**: CLOSED。不再构成 finding。

### 0.2 L-02（star-import 语义差）—— 自承非 bug，已 CLOSED

**082000 原文**: "不是 bug，而是需在实施时确认所有已知 consumer 均已更新 import 路径。Plan §9d 已明确覆盖 tests，§9e 已覆盖 write.py，main.py 仅 import `run_research_template_command`（保留项）。已知 consumer 均已处理。"

**Controller 裁决**: REJECTED-WITH-REASON / CLOSED。理由：
- 五个私有模块 `__all__` exact 0 是**正确设计**——私有模块不应扩大 star-import surface
- `research_template.py.__all__` 68→55 精确删除 13 项，已逐一枚举
- 所有已知 consumer 已覆盖：main.py（retained entry）、write.py（lazy import 迁 owner）、tests（direct-owner/dispatch-owner 迁移）
- 无本仓库证据的未知 star consumer 不构成 defect
- 为私有模块新增 `__all__` 反而**扩大 surface**，违反封装原则

**本审查确认**: 082000 自身已承认这不是 bug。Controller 的设计决策正确——私有模块的 `__all__` exact 0 是封装最佳实践。CLOSED。

---

## 1. 完整 v5.1 独立复验

以下复验在 HEAD `1d0f9e6` 上独立运行，不使用 082000 的中间结果。

### 1.1 顶层 Inventory

| 度量 | 独立核验 | v5.1 Plan | 一致 |
|---|---|---|---|
| FunctionDef | **123** | 123 | ✅ |
| `_run_*` runner | **39** | 39 | ✅ |
| Entry | **1** | 1 | ✅ |
| Retained | **40** | 40 | ✅ |
| To migrate | **83** | 83 | ✅ |
| ClassDef | **2** | 2 | ✅ |

### 1.2 83 函数 Exact Ownership

| Owner | v5.1 | 独立核验 | missing | extra | overlap |
|---|---|---|---|---|---|
| helpers | 22 | 22 | 0 | 0 | 0 |
| core | 26 | 26 | 0 | 0 | 0 |
| bundle | 12 | 12 | 0 | 0 | 0 |
| monitoring | 11 | 11 | 0 | 0 | 0 |
| materialize | 12 | 12 | 0 | 0 | 0 |
| **合计** | **83** | **83** | **0** | **0** | **0** |

### 1.3 跨 Owner DAG

独立 call graph 验证（AST free-global 分析）：

```
main → helpers          ✓   main → core            ✓   main → bundle         ✓
main → monitoring       ✓   main → materialize     ✓
core → helpers          ✓
bundle → core           ✓   bundle → helpers       ✓
monitoring → bundle     ✓   monitoring → core      ✓   monitoring → helpers  ✓
materialize → monitoring ✓  materialize → bundle   ✓
materialize → core      ✓   materialize → helpers  ✓
```

- **Total edges**: 15（5 main→owner + 10 intra-owner）
- **Forbidden edges**: 0
- **Cycles**: 0
- **helpers internal domain deps**: 0（true leaf）

### 1.4 Main Functional Bindings（exact 45）

| Owner | v5.1 | 独立核验 | FP | FN |
|---|---|---|---|---|
| helpers | 6 | 6 | 0 | 0 |
| core | 18 | 18 | 0 | 0 |
| bundle | 6 | 6 | 0 | 0 |
| monitoring | 9 | 9 | 0 | 0 |
| materialize | 6 | 6 | 0 | 0 |
| **合计** | **45** | **45** | **0** | **0** |

Non-bound: **38**（=83−45），compat binding exact 0。

### 1.5 `__all__` 终态

| 度量 | v5.1 | 独立核验 |
|---|---|---|
| 当前条目 | 68 | 68 |
| 删除项 | 13 | 13（全部在 `__all__` 中存在） |
| 终态条目 | 55 | 55 |
| 私有 owner `__all__` | exact 0 | exact 0（设计正确） |

### 1.6 Dataclass & Constants

| 度量 | v5.1 | 独立核验 |
|---|---|---|
| Dataclass 归属 | helpers | ✅（仅被 migrated 函数使用，retained 调用 0） |
| Constants 归属 | helpers | ✅（5 Assign + 2 AnnAssign = 7） |
| `object` occurrence | 1→1（`_DATA_SOURCE_BINDING_CANDIDATES`） | ✅（line 99，存量模块常量类型） |

### 1.7 write.py Lazy Import

| 度量 | v5.1 | 独立核验 |
|---|---|---|
| 当前位置 | line 81, `_materialize_research_after_write` 内 | ✅（AST 确认） |
| 旧 owner 路径 | `dayu.cli.commands.research_template` | ✅ |
| 新 owner 路径 | `dayu.cli.commands._research_template_materialize` | ✅ |
| 门禁: 旧路径 exact 0 | grep 审计 | ✅ |
| 门禁: 新路径 exact 1 | grep 审计 | ✅ |

### 1.8 Slice 10 Impact

| 度量 | 独立核验 |
|---|---|
| Retained 函数数 | 40（1 entry + 39 runners），仍在 `research_template.py` |
| Slice 10 签名目标 | 全部 40 个 retained 函数 |
| Slice 9 迁移的函数 | 83 个，均不在 Slice 10 传播范围内 |
| 类型安全 | `DayuCliArguments` 是 `argparse.Namespace` 子类，协变安全 |
| Dataclass | 已在 helpers，Slice 10 不重复迁移 |

Slice 10 不受 Slice 9 影响。✅

### 1.9 门禁完备性

Plan §9e 定义了完整门禁：

| 门禁 | 类型 | 状态 |
|---|---|---|
| pytest（3 文件） | 行为 | ✅ 已定义 |
| pyright `dayu/cli/` | 类型 | ✅ 已定义 |
| Ruff F,I delta=0 | Lint | ✅ 已定义 |
| AST 83→22/26/12/11/12 | 结构 | ✅ 已定义 |
| Main FunctionDef exact40, ClassDef0 | 结构 | ✅ 已定义 |
| Functional bindings exact45, 分布 6/18/6/9/6 | 结构 | ✅ 已定义 |
| Compat binding exact0 | 结构 | ✅ 已定义 |
| Old lazy owner exact0, new exact1 | 结构 | ✅ 已定义 |
| DAG 零 forbidden/cycle | 结构 | ✅ 已定义 |
| Import smoke | 集成 | ✅ 已定义 |
| 逐文件 coverage ≥80%（7 文件） | 覆盖率 | ✅ 已定义 |
| `git diff --check` | 格式 | ✅ 已定义 |
| README 触发判断 | 文档 | ✅ 已定义 |

---

## 2. Findings

**无新 findings**。082000 的 L-01 已确认为事实错误（Slice 8 已在 HEAD `1d0f9e6`），L-02 自承非 bug 且 Controller 裁决正确。重新独立复验全部 v5.1 claims，无任何偏差。

---

## 3. Open Questions

无。初审 9 项 findings 全部 CLOSED，复审 2 项 LOW 经纠正后 CLOSED，Controller open H/M/L = 0/0/0。

---

## 4. Residual Risks

| # | 风险 | 严重度 | 处置 |
|---|---|---|---|
| R1 | Slice 9 在 Slice 8 之后唯一实施，`write.py` 已稳定（741 行，2 顶层函数），line 81 不会漂移 | — | 已确认不构成风险 |
| R2 | 五个新模块的 pyright fresh analysis 可能产生不同于单文件分析的 warning | LOW | 已在门禁中覆盖（pyright `dayu/cli/` 0 errors） |

---

## 5. 审查结论

**Verdict: PASS**（open High/Medium/Low = 0/0/0）

v5.1 的全部 claims 经独立 AST/callgraph 复验全部闭合：

- 83 函数逐名 exact 且唯一分配（22/26/12/11/12），missing/extra/overlap = 0
- DAG 15 边，零 forbidden edge、零 cycle
- helpers 是真正的零内部 project-domain dependency 叶子
- 45 functional bindings 精确 6/18/6/9/6，零 false positive/negative
- 38 非 bound 函数零 compat re-export
- `__all__` 68→55，精确 13 项删除
- Dataclass 迁至 helpers 消除 import cycle
- 存量 `object` 1→1
- write.py lazy import 以函数锚点 + 旧/new exact 门禁三重语义锁定
- Slice 10 独立且安全
- 全部门禁（结构/行为/类型/lint/覆盖率/文档/diff）完整定义

082000 的 L-01/L-02 经纠正后均已 CLOSED。Controller 裁决正确。**Slice 9 v5.1 达到 code-generation-ready，建议进入 implementation phase。**

**审查人**: DeepSeek（planreview skill, corrective pass）
**审查方式**: 独立 AST/callgraph 机器复验 + Controller 裁决复核，只读，零修改
