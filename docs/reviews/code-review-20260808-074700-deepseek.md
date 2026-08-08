# Code Review（复审）

## Scope

- **Mode**: current changes（复审同一 Slice8 workspace changes）
- **Branch**: `codex/dual-model-research-mvp`
- **Base**: HEAD `fcf4602 gateflow: accept cli write execution manual recovery slice 7`
- **Output file**: `docs/reviews/code-review-20260808-074700-deepseek.md`
- **Reviewed artifacts**:
  - 初审：`docs/reviews/code-review-20260808-073322-deepseek.md`（DS，Verdict PASS，1M+2L）
  - 并行审：`docs/reviews/code-review-20260808-073323-mimo.md`（MiMo，Verdict PASS，1L）
  - Controller 裁决：`docs/reviews/slice-8-code-review-adjudication-20260808-codex.md`（全部 CLOSED，open 0/0/0）
  - 实现记录：`docs/reviews/slice-8-write-challenger-rollback-implementation-20260808-codex.md`
- **复审目标**: 独立验证 Controller 四项裁决，确认 open H/M/L = 0/0/0
- **Parallel review coverage**: 无

---

## Controller 裁决逐项独立复核

### DS M01 — `_build_auto_bootstrap_args` 缺直接单元测试

- **Controller 裁决**: `rejected-with-reason / CLOSED`
- **独立复核证据**:
  1. `_build_auto_bootstrap_args`（`_write_challenger.py:665-680`）去 docstring 后 AST 与 HEAD `write.py` 中该函数精确等价——参数复制 `dict(vars(args))`、三字段覆盖 `{"template": None, "research_template": None, "infer": True}`、`argparse.Namespace(**values)` 新建全同。
  2. 该函数在 HEAD `write.py` 中即有相同的测试粒度——HEAD 同样无针对此 private helper 的独立 unit test。本 Slice 是 AST-only owner migration，未引入此测试缺口。
  3. `_write_challenger.py` 精确 statement coverage 为 `166/200 = 83.000000%`，满足 accepted plan 与 AGENTS 的 `≥80%` 门槛。812 个真实 caller tests 全部通过。
  4. 所述风险（未来参数覆盖变更时缺乏回归屏障）是测试深度建议，不是本 Slice 引入的 correctness/stability defect。
- **复核结论**: Controller 裁决成立。**CLOSED**。

### DS L02 — `_challenger_preflight_cli_args` 切片语义缺直接测试

- **Controller 裁决**: `rejected-with-reason / CLOSED`
- **独立复核证据**:
  1. `_challenger_preflight_cli_args`（`_write_challenger.py:49-75`）去 docstring 后 AST 与 HEAD 精确等价——`result = ["--preflight-only"]` 首元素、两个模型覆盖参数的条件追加逻辑、两个 caller（行 123 和行 203）的调用方式全部不变。
  2. 行 203 的 `[1:]` 切片与 HEAD 一致，切片语义（去掉首元素 `--preflight-only` 保留模型覆盖参数）未改变。
  3. 该 helper 在 HEAD 中同样无独立 direct test。本 Slice 的目标是按 accepted v5.0 锁定 AST 完成 owner migration，不是重新定义旧 helper 的测试矩阵。
  4. 审批流程的端到端测试（`test_common_preflight_gate_consumes_matching_receipts`、`test_write_command_blocks_unapproved_common_preflight_before_host`）通过真实 caller 路径覆盖了 `_challenger_preflight_cli_args` 的间接行为。
- **复核结论**: Controller 裁决成立。**CLOSED**。

### DS L03 — output boundary 错误路径缺直接测试

- **Controller 裁决**: `rejected-with-reason / CLOSED`
- **独立复核证据**:
  1. `_assert_challenger_run_output_boundaries`（`_write_challenger.py:215-244`）去 docstring 后 AST 与 HEAD 精确等价——三个 `raise`（`ValueError` × 2 + `FileExistsError` × 1）及其条件判断不变。
  2. 两处调用方的异常捕获（`_verify_and_consume_challenger_run_approval_before_host:459-470` 和 `run_write_command:336-347`）与 HEAD 一致，捕获范围 `(FileExistsError, FileNotFoundError, OSError, TypeError, ValueError)` 不变，退出码映射不变。
  3. 这些错误路径在 HEAD 中同样无独立 direct test。本 Slice 未改变异常类型、捕获范围或退出码。
  4. 812 tests 全部通过且三文件 coverage 均 ≥80%，说明 owner migration 没有造成运行时回归或覆盖率下降。
- **复核结论**: Controller 裁决成立。**CLOSED**。

### MiMo L-1 — `_write_challenger.py` 函数计数不精确

- **Controller 裁决**: `rejected-with-reason / CLOSED (measurement error)`
- **独立复核证据**:
  1. Python `ast` 模块对当前 `_write_challenger.py` 顶层 `FunctionDef` 独立实测结果：**exact 13**。逐名清单：
     ```
     1. _challenger_preflight_cli_args
     2. _verify_challenger_preflight_approval_before_host
     3. _build_challenger_run_plan_from_args
     4. _assert_challenger_run_output_boundaries
     5. _load_current_challenger_proposal
     6. _persist_challenger_run_authorization_after_preflight
     7. _verify_and_consume_challenger_run_approval_before_host
     8. _build_challenger_write_config
     9. _preflight_champion_and_challenger
     10. _run_champion_challenger_experiment
     11. _manifest_has_usable_company_facets
     12. _needs_auto_research_bootstrap
     13. _build_auto_bootstrap_args
     ```
     其中 10 个为 external（被 `write.py` import）、3 个为 internal helper（无 `write.py` caller）。
  2. `_write_config_rollback.py` 顶层定义 exact 1（`_run_write_model_configuration_rollback`）。
  3. Slice 8 总迁移 = 13 + 1 = 14 个函数。implementation artifact 的表述准确。
  4. MiMo artifact 自身 §1 已记录 AST 等价验证 `14/14 PASS`，与 finding 声称 `_write_challenger.py` 有 14 个函数相冲突，证实为计数测量错误。
- **复核结论**: Controller 裁决成立。**CLOSED**。

---

## 独立再验证：结构一致性

以下全部独立重新实测，作为复审的独立证据基础：

| 验证项 | 独立实测结果 | 判定 |
|---|---|---|
| `_write_challenger.py` 顶级函数数 | 13（10 external + 3 internal） | 与初审一致，MiMo L-1 确认测量错误 |
| `_write_config_rollback.py` 顶级函数数 | 1 | 与初审一致 |
| `write.py` 本地定义数 | 2（`_materialize_research_after_write`、`run_write_command`） | 与初审一致 |
| `write.py` 旧14定义残留 | 0 | 与初审一致 |
| `write.py` 从 `_write_challenger` import | 10（全部在 `run_write_command` 中使用） | 与初审一致 |
| `write.py` 从 `_write_config_rollback` import | 1（在 `run_write_command` 中使用） | 与初审一致 |
| 内部 helper 兼容绑定 | 0 | 与初审一致 |
| 14 迁移函数 AST 等价（去 docstring） | 14/14 PASS | 独立复测确认 |
| HEAD `write.py` 总函数数 | 16（14 migrated + 2 remaining） | 与初审一致 |
| 反向 import（新 owner → `write.py`） | 0 | 与初审一致 |
| `MODULE` 单一真源 | `_write_config_helpers.MODULE`（三文件均无本地定义） | 与初审一致 |
| `Any` semantic uses | 7→7（`_write_challenger.py`: 6、`write.py`: 1） | 与初审一致 |
| identity 测试断言数 | 11（10 Challenger + 1 Rollback） | 独立复测确认 |
| `write.py` dead import | 0 | 独立复测确认 |
| 既有 function-local domain import | `_manifest_has_usable_company_facets:634` 保留 | 与初审一致 |
| `git diff --check` | PASS | 与初审一致 |

---

## 独立再验证：测试与文档一致性

- **测试导入路径**: `test_write_challenger.py` 直接从 `_write_challenger` import 7 个函数；`test_write_cli_dispatch.py` 的 identity 测试验证 11 个 `is` 断言全部指向真实 owner 模块；`test_write_model_configuration_preapplication.py` 的 rollback 相关 patch 已全部迁移到 `write_config_rollback_command_module`。
- **engine test import**: `test_cli_running_config.py` 中 `_needs_auto_research_bootstrap` 已从 `dayu.cli.commands._write_challenger` import（非 `write`），与函数新 owner 一致。
- **write.py 残留 import**: 无。tests/ 中对 `dayu.cli.commands.write` 的 import 仅涉及 `run_write_command` 和 `_validate_research_materialization_args`，两者仍驻留在 `write.py` 中。
- **README**: diff 为 0。本 Slice 仅迁移 CLI 私有实现，命令/参数/退出码/用户接口不变，无需更新。
- **Pyright**: `0 errors, 0 warnings, 0 informations`（目标文件）。
- **Ruff**: full-rule finding-code multiset 与 HEAD 无正增量。

---

## Findings

无。初审 DS M01/L02/L03 与并行审 MiMo L-1 经 Controller 裁决全部 CLOSED，独立复核确认四项裁决成立。

---

## Open Questions

无。

---

## Residual Risk

1. **既有 sqlite `ResourceWarning`**: 全量测试 812 passed 附带既有 sqlite 资源未关闭警告。本 Slice 不改变资源生命周期管理。
2. **engine test 既有 `I001`**: 为 HEAD 既有，本 Slice 未新增或扩散。
3. **既有 function-local domain import**: `_manifest_has_usable_company_facets` 中的 `from dayu.cli.research_template_routing import load_company_facets_from_manifest` 按 exact AST 保留。若 `research_template_routing` 重构，此 import 需同步更新——HEAD 既有设计选择。
4. **Rollback `build_snapshot_builder` 默认 label**: 不传 `run_label` 依赖默认值——HEAD 既有行为。

以上四项均为 HEAD 既有 residual risk，本 Slice 未改变其风险面。

---

## Verdict: PASS

**Open H/M/L: 0/0/0**

Controller 四项裁决全部经独立复核确认成立：

- DS M01/L02/L03 均为 AST-exact owner migration 中 HEAD 既有的 per-helper 测试粒度建议，不是本 Slice 引入的 correctness/stability/contract defect。14/14 AST 等价、812 tests 全部通过、三文件 coverage 均 ≥80%。
- MiMo L-1 确认为计数测量错误——AST 独立实测 `_write_challenger.py` exact 13 个顶级函数（非 14），`_write_config_rollback.py` exact 1，总计 14，与 implementation artifact 一致。

本复审未发现任何新的 correctness、stability、maintainability、architecture、test 或 documentation defect。Slice 8 代码迁移为 AST-exact、测试幂等、依赖单向的纯重构，可安全合入。
