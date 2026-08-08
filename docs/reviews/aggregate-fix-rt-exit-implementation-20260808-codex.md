# Aggregate Fix RT-01 实现记录

- 状态：`DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT`
- 日期：2026-08-08
- 实现基线：`a0c469a`
- 接受计划：CLI write architecture master plan v5.8，`AGG-RT-CTRL-01`
- 当前 Gate：Aggregate Fix RT-01 dual re-review 已通过；等待 Controller 创建 accepted commit，尚未进入 PR gate

## 范围与实现

本轮实现严格限定为一处生产语义修复及对应真实 CLI 回归测试：

1. `dayu/cli/commands/research_template.py`
   - `_run_validate_source_map` 的 `Returns` 文档明确为校验成功返回 `0`、校验失败返回 `1`。
   - 原固定 `return 0` 改为精确契约：`return 0 if result.get("ok") is True else 1`。
   - JSON stdout、dispatch、异常边界、owner/DAG 及其他 runner 均未改变。
2. `tests/cli/test_research_template_command.py`
   - 保留 `consumer` rules 与 `consumer` source-map 的真实入口成功回归，断言退出码 `0` 与 stdout `ok is True`。
   - 新增计划指定的真实 mismatch 回归：通过 `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` 与 `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 构造输入，经真实 `run_research_template_command` 断言退出码 `1`、stdout `ok is False` 且 `errors` 非空。

未修改 README、master plan、其他生产代码、其他测试、CI 或外部 review artifact。

## 验证结果

仓库迁移至非云盘路径 `/Users/wsk/workspace/dayu-agent` 后，最终验证闭环如下：

- focused validate-source-map：`3 passed, 213 deselected`。
- aggregate behavior（write CLI dispatch、research template、write service）：`380 passed`。
- Python 3.11 clean min-compat full suite，`SERPER_API_KEY` unset：`7122 passed, 5 skipped, 9 deselected`。
- 真实 caller coverage corpus：`920 passed`；目标生产文件 `304/378 = 80.423280%`，满足精确 `>=80%` 门槛。
- 目标 pyright：`0 errors, 0 warnings, 0 informations`。
- `ci_pr_pyright` ratchet：HEAD `219`、BASE `219`、new `0`，PASS。
- Ruff F/I：PASS。
- Ruff `0.16.1` architecture ratchet：当前计划 scope 复证为 `335`。迁移后的本地仓库缺少 baseline `5821014` 的 tree object，无法在新路径重新归档该历史树；复用迁移前相同算法的权威结果 BASE `364`、positive delta `{}`、negative delta `I001: 11`、`TRY004: 17`、`UP035: 1`，并以当前 `335` 未变闭环，PASS。
- AST delta：PASS。除 `_run_validate_source_map` 的 docstring 与最终 `Return` 外，其余函数 AST 不变；终态 `FunctionDef=41`、research-template runners `=39`。
- dual-model focused corpus：`699 passed`。
- `python -m utils.validate_handoff_docs --json`：`ok: true`。
- `python -m utils.codex_review_gate --allow-waiting --json`：`ok: true`；`WAITING_FOR_TASK` 是允许的 gate 状态。
- `python -m utils.dual_model_pipeline_check --json`：`ok: true`，全部子检查通过。
- `git diff --check`、冲突标记、secret key shape、未合并索引、artifact 尾随空白和最终换行检查：PASS。
- 工作树只包含本实现允许的两个代码/测试修改与本 artifact；仓库根目录无 `.coverage*`，本轮 `/tmp/dayu-rtfix-final-*` 临时文件已精确清理。

## 环境说明

原 Finder/iCloud Documents 仓库曾发生宿主文件系统 `read(2)` 阻塞；采样证明该问题不是 pytest collection 或测试逻辑失败。迁移至非云盘本地仓库后，Python 3.11 full suite 与全部剩余门禁均已正常完成，因此该环境阻塞已关闭。

新仓库未携带 `5821014` 的完整历史 tree；这只影响 architecture baseline 的本地重建，不影响当前树 Ruff `335` 的复证。baseline 采用迁移前同版本、同命令、同 scope 的已记录权威结果，不把缺失历史误报为代码 finding。

## 文档决策

无需更新 README。本修复只使既有 `validate-source-map` 命令在校验失败时返回非零退出码，命令、参数、JSON 输出和用户工作流均未改变；accepted v5.8 也将 README 排除在实现范围外。

## 计划差异与残余风险

- 未发现 plan gap；实现与测试严格匹配 `AGG-RT-CTRL-01`。
- 当前没有阻塞 code review 的已知代码缺陷或未覆盖行为。
- 新仓库缺少 Ruff baseline 历史 tree，已由迁移前权威测量与当前计数复证闭环；这是可追溯的验证环境限制，不是产品风险。
- v5.7 已记录的 origin/main Ruff PR residual 不属于本修复范围，本轮 architecture ratchet positive delta 仍为 `0`。

## 双路初审与 Controller 裁决

- DeepSeek review：`docs/reviews/code-review-20260808-195939.md`，PASS，open High/Medium/Low=`0/0/0`，无 material findings。
- MiMo review：`docs/reviews/code-review-20260808-115535.md`，PASS，open High/Medium/Low=`0/0/0`，无 material findings。
- Controller accepted findings：`0`；Controller open High/Medium/Low=`0/0/0`。
- 无需 code、test、README 或 master plan fix；本 Gate 未修改 production/tests/README/plan，也未启动 dual re-review。
- Controller 裁决记录：`docs/reviews/aggregate-fix-rt-exit-code-review-adjudication-20260808-codex.md`。

## 双路复审闭环

- DeepSeek re-review：`docs/reviews/code-review-20260808-200226.md`，PASS，open High/Medium/Low=`0/0/0`。
- MiMo re-review：`docs/reviews/code-review-20260808-201507.md`，PASS，open High/Medium/Low=`0/0/0`。
- 两路均确认初审裁决正确：Controller accepted findings=`0`，无需 fix，也无需 production、tests、README 或 master plan 变更。
- 所有 review Gate 证据已闭合；下一步仅由 Controller 执行 accepted commit，本 worker 未执行 add、commit、push 或 stash。
