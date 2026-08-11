# Plan Review: Slice 2.1 identity docstring guard 最小计划勘误

- **状态**：`PLAN RE-REVIEW / PASS`
- **Reviewer**：MiM
- **时间**：`2026-08-11 22:17:08 +0800`
- **Gate**：plan re-review（dual review 第二路）
- **Baseline**：`489a910`
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Controller 勘误**：`docs/reviews/plan-fix-20260811-slice-2.1-identity-docstring-guard-codex.md`
- **主计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`

## 1. Review Scope

本 review 独立审查 Controller 勘误 `plan-fix-20260811-slice-2.1-identity-docstring-guard-codex.md` 的 `S21-CTRL-DOC-001` 裁决，验证其是否为关闭当前 hard gate 的最小充分授权。

**已读取文档**：
- 根 `AGENTS.md`
- `docs/plans/2026-08-10-investment-platform-restoration.md`
- `docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`（完整）
- `docs/reviews/plan-fix-20260811-slice-2.1-identity-docstring-guard-codex.md`
- `tests/investment/test_architecture_boundaries.py`（完整）
- `tests/integration/investment/test_identity_repositories_postgres.py`（HEAD + WIP diff）

**未读取**：另一 reviewer artifact、production/README/WIP（除上述已读）、任何外部调用。

## 2. Assumptions Tested

| # | Assumption | 验证结果 |
| --- | --- | --- |
| A1 | 架构守护 `test_integration_tests_carry_chinese_docstrings` 扫描 `tests/integration/investment/` 下全部 `.py` 文件的模块/类/函数节点，要求每个节点有含中文的 docstring | **成立**。`test_architecture_boundaries.py:934-951` 明确遍历 `_iter_integration_test_files()` 收集的全部文件，调用 `_collect_docstring_violations` 检查 `ast.get_docstring(node)` 非 None 且 `_contains_cjk` 为 True。 |
| A2 | `_counted_read_postgres_dsn` 在 `489a910` baseline 存在且无 docstring | **成立**。`git show 489a910:tests/integration/investment/test_identity_repositories_postgres.py` 中该 helper 函数体首句为 `placeholder_read_calls[0] += 1`，无 docstring。 |
| A3 | architecture guard 测试是 full-lane 唯一失败项 | **成立**。Controller 报告 `env -u SERPER_API_KEY pytest -q --timeout=60 -m "not integration and not slow and not e2e"` 得 `8183 passed / 1 failed / 5 skipped / 138 deselected`，唯一失败即 `test_integration_tests_carry_chinese_docstrings`。 |
| A4 | `S21-CTRL-DOC-001` 的五项约束足以防止 scope creep | **成立**。约束精确到：(1) 仅插入 docstring 于函数体首句；(2) 不改 signature/closure/counter/reader/return/exception/monkeypatch；(3) stripped-AST 对 `489a910` exact；(4) 文件其它变更限于 §2 已列项；(5) 不改 architecture guard。 |
| A5 | 无需修改 architecture guard、production 或其他 test helper 的更窄方案不存在 | **成立**。修改 architecture guard 本身或添加 baseline/skip 被 §5 STOP 条件显式禁止；修改 production 代码超出勘误范围；其他 test helper 均已有 docstring。唯一 gap 即该 nested helper 缺 docstring。 |

## 3. Findings

**无 findings。**

`S21-CTRL-DOC-001` 是关闭当前 hard gate 的最小充分授权：

1. **最小性**：仅授权一个机械动作——在既有一个嵌套 helper 的函数体首句插入一段固定 docstring。不改 signature、不改 closure、不改可执行 AST、不改 counter、不改异常传播、不改 monkeypatch target。

2. **充分性**：architecture guard `test_integration_tests_carry_chinese_docstrings` 扫描全部 integration test 文件的所有函数节点；该 helper 是唯一缺少中文 docstring 的节点；插入后 guard 测试通过。

3. **可执行性**：
   - **stripped-docstring AST equivalence**：去除新增 docstring 后，helper 的 AST 必须与 `489a910` 精确相同。这可通过 `ast.parse` + `ast.dump` 或逐节点比较机械验证。
   - **architecture guard test**：`pytest tests/investment/test_architecture_boundaries.py::TestArchitectureBoundaries::test_integration_tests_carry_chinese_docstrings -q` 直接验证。
   - **identity integration lane**：`pytest tests/integration/investment/test_identity_repositories_postgres.py -q` 验证 §2 允许的其它变更（test rename、import cleanup、module docstring）无回归。
   - **full lane**：`env -u SERPER_API_KEY pytest -q --timeout=60 -m "not integration and not slow and not e2e"` 验证零行为变化。

4. **无范围扩大**：勘误不改任何 production owner、schema、migration、PG16 lane、business behavior、test fixture、Slice 2.2/2.3 边界。§2 允许的 test 文件变更（module docstring、test rename、import cleanup）均属先前 provider-allowlist erratum 已授权的范围，本勘误仅追加 docstring 插入。

5. **无遗漏 STOP**：§9 STOP 条件完整覆盖了所有不应发生的行为：不改 helper 可执行 AST、不改 architecture guard、不加 ignore/baseline、不扩 allowlist。

6. **无事实错误**：baseline `489a910` 确认 `_counted_read_postgres_dsn` 无 docstring；`_counted_build_production_identity_provider` 在 baseline 中存在（由 §2 已授权移除）；full lane 唯一失败确为该 docstring 缺失。

## 4. Open Questions

无。

## 5. Residual Risks

| Risk | 归属 | 跟踪 |
| --- | --- | --- |
| stripped-docstring AST equivalence 验证依赖 implementation worker 正确执行 | Slice 2.1 verification gate | §3.2 第 1 项验证 |
| full lane 的 `SERPER_API_KEY` 环境污染需显式清除 | 运行环境 | §3.2 第 4 项验证 |

## 6. Conclusion

**PASS** / open H/M/L = **0/0/0**

`S21-CTRL-DOC-001` 是关闭当前 hard gate 的最小充分、可执行、无范围扩大的授权。双路 plan re-review 第二路通过；implementation 可恢复，按 §3.2 验证矩阵执行后提交。
