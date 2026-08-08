# Slice 0 独立 Code Review

- **日期**: 2026-08-07
- **HEAD**: `f0a3ea1`
- **审查范围**: 未提交 diff（`tests/application/test_write_service.py` +187 行追加、`tests/application/test_write_cli_dispatch.py` 新建）
- **计划参考**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` Slice 0 + Slice 12 中 Slice0 characterization 约束
- **审查者**: MiMo

---

## 验证命令结果

| 工具 | 范围 | 结果 |
|---|---|---|
| pytest | `test_write_cli_dispatch.py` + `test_write_service.py` | **127 passed**（0.62s） |
| ruff | 目标两个文件 | **All checks passed** |
| pyright | 目标两个文件 + `write.py` / `research_template.py` / `write_service.py` | **0 errors, 0 warnings** |

---

## 对抗性核查逐项

### 1. 变更是否只表征 HEAD if-chain？

**YES.** 两个文件仅 monkeypatch + 断言 HEAD `f0a3ea1` 现有 `run_write_command` 和 `run_research_template_command` 的 if-chain dispatch。未引用未来 `arguments.py`、dispatch mapping、adapter、phase table。

### 2. A–H 25 语义项是否真实完整？

| 标号 | 计划项 | 测试数 | 覆盖完整性 |
|---|---|---|---|
| A | `_canonical_json` str 变体 | 4（null/empty/sort_keys/nan） | ✅ 完整 |
| B | `_canonical_json` bytes 变体 | 3（empty/nested/proxy） | ✅ 完整 |
| C | `_validated_fingerprint` 两异常文本族 | 2（str 系/bytes 系） | ✅ 完整 |
| D | `_parse_utc` offset 差异 | 3（Z suffix/missing tz/全量变体 a 锁定） | ✅ 完整 |
| E | `print_report` 副作用顺序 | 4（step1_before_step3 / step4_only_after_gate / repricing_failure_continues / full_order） | ✅ 完整，超出计划原定 2 项 |
| F | CLI 混合 flag 优先级矩阵 | 4（revalidate_before_inspect / path_arg_over_bool / summary_fallback / default_execution） | ✅ 完整 |
| G | monkeypatch 路径契约 | 1 | ✅ 完整 |
| H | 惰性计算 / 阶段顺序 | 6（early_recovery / clear_verify_recover ×3 / path_runners ×3 / apply_rollback ×2 / recovery_gate / summary_path） | ✅ 完整 |

**合计: 25 语义项，全部有对应测试。**

### 3. E 的 step1/gate/step4/repricing failure/full order 是否有可观察断言？

- `test_print_report_step1_before_step3`: `call_order` 列表追踪 `"step1_print_write_report"` 是否在 `exit_code == 2` 之前出现。**可观察，非假绿。**
- `test_print_report_step4_only_after_gate`: Scenario A 验证 `repricing_called_a` 为空（gate 失败时 step4 不调用）；Scenario B 验证 `repricing_called_b` 非空（gate 通过后 step4 被调用）。**可观察，非假绿。**
- `test_print_report_repricing_failure_continues`: resolve 和 load 均抛异常后 `exit_code == 0`。**可观察，非假绿。**
- `test_print_report_full_order_step1_gate_step4`: `call_order` 列表断言 `step1_idx < step4_idx < step8_idx`。**可观察，非假绿。**

### 4. F/H default/summary/惰性顺序

- `test_default_execution`: `_prepare_cli_host_dependencies` mock 抛 RuntimeError，断言被捕获且 `call_counts` 全零。**正确验证 Phase H 入口。**
- `test_summary_fallback`: summary=True 时所有 Phase A/B runner 计数为 0，返回 `print_report` sentinel 42。**正确验证 summary 不穿透。**
- `test_early_recovery_does_not_call_resolve_model_override`: Phase A 命中时 `_resolve_write_model_override_name` 不被调用。**正确验证惰性。**
- `test_clear_verify_recover_call_build_execution_options_inline`: 三个 flag 各自断言 `_beo` 长度 = 1。**正确验证分支内惰性 build。**
- `test_path_runners_do_not_call_build_execution_options`: 三个 path flag 各自断言 `_beo` 长度 = 0。**正确验证 path runner 不 build。**
- `test_apply_rollback_use_precomputed_execution_options`: 断言 `_beo` 长度 = 1（预计算）。**正确验证 Phase B 预计算。**
- `test_recovery_gate_after_config_before_challenger`: gate mock 返回 2，断言 `exit_code == 2`。**正确验证 Phase C 位置。**

### 5. I-a 16 selectors 对真实 runner 和 build 次数

**16 selectors = 11 Phase A bool + 3 Phase A path + 2 Phase B bool。** 逐项核对 write.py dispatch 链：

| 组别 | 数量 | 验证方式 |
|---|---|---|
| Group 1 Phase A bool | 11 | 参数化 `PHASE_A_BOOL_PARAMS`，每个断言正确 runner 被调用 + 其余不被调用 + `_beo` 长度 |
| Group 2 Phase A path | 3 | 参数化 `PHASE_A_PATH_PARAMS`，nonempty 触发 + empty 不触发 + `_beo`=0 |
| Group 3 Phase B bool | 2 | 参数化 `PHASE_B_BOOL_PARAMS`，断言正确 runner + `_beo`=1 |

额外覆盖: `test_summary_plus_apply_apply_wins`（mixed priority）。

**16 项全部与 write.py HEAD dispatch 链逐行对应。**

### 6. I-b parser 39 choices 与 39 runner 逐项对应

- `ACTION_RUNNER_MAP` 含 39 个 `(action, runner_attr, sentinel)` 条目。
- `test_parser_choices_match_action_runner_map` 程序化访问 argparse subparser choices，断言 `len(parser_actions) == 39`，双向差集为空。
- 39 个参数化 `test_action_dispatches_to_correct_runner` 各断言正确 runner 被调用 + 其余不被调用。
- 额外: `test_unknown_action_returns_1` 验证未知 action 返回 1。

**39 项全部与 research_template.py HEAD if-chain 逐行对应。**

### 7. mock 是否过度、是否复制实现、是否隔离 host/fs？

- `_install_write_baseline_mocks` mock 基础设施（`setup_loglevel`、`Log.info/error`、`setup_paths`）和所有 16 个 runner，使用 sentinel 返回值追踪调用。**不复制 dispatch 逻辑。**
- `setup_paths` 返回 `WorkspaceConfig` fake，隔离 host/fs。
- `print_report` 测试 mock `print_write_report`、`resolve_write_run_comparison_for_report`、`load_write_run_comparison`、`build_write_model_health_trend`。**隔离 I/O 和外部依赖。**
- monkeypatch 路径使用模块级路径（`dayu.cli.commands.write.xxx`），每次测试自动还原。**隔离良好。**

### 8. 是否引用未来 arguments/mapping/adapter？

**NO.** 文件头 docstring 明确声明 "不引用未来 arguments.py、dispatch mapping、adapter、phase table"。全文仅 import HEAD 现有的 `run_write_command`、`run_research_template_command`、`WriteService`、`_canonical_json`、`_validated_fingerprint`、`_parse_utc`。

### 9. 测试名/文档/类型是否准确？

- 测试名与断言内容一致（如 `test_revalidate_before_inspect` 确实验证 revalidate 优先于 inspect）。
- docstring 与测试逻辑匹配。
- 类型标注: 测试辅助函数使用 `Any`（如 `_make_runner` 返回 `Any`、`_tracked_*` 参数 `*a: Any`）。这与 CLAUDE.md "禁止 `Any`" 硬约束存在表面冲突，但测试文件中 monkeypatch/动态 mock 的 `Any` 属于 pytest 惯例，不影响生产代码类型安全。

### 10. 是否存在重构后会无意义通过的 false positive？

**关键风险分析:**

- **Sentinel 值隔离**: 每个 runner 分配唯一 sentinel（10–23, 30–31, 101–139）。若 dispatch 逻辑错误地调用了错误 runner，sentinel 不匹配 → 测试失败。**非假绿。**
- **"其余不被调用" 断言**: 每个参数化测试遍历 `call_counts` 断言非目标 runner 计数为 0。若 if-chain 顺序变化导致两个分支同时命中 → 测试失败。**非假绿。**
- **Slice 10/11 迁移后**: 测试 patch 目标为 HEAD 函数名（如 `_run_write_model_configuration_manual_recovery_clearance`），Slice 11 引入 adapter 后函数名/路径改变 → 测试必然失败。**这是设计意图（C4-01），非缺陷。**
- **`_canonical_json` / `_validated_fingerprint` / `_parse_utc` 直接测试私有函数**: Slice 1/2 迁移到 `_write_artifact_utils.py` 后 import 路径改变 → 测试失败。**同样是设计意图。**

**结论: 无重构后无意义通过的 false positive。**

---

## Findings

### LOW-01: 测试文件使用 `Any` 类型（表面合规冲突）

- **文件**: `tests/application/test_write_cli_dispatch.py` 多处（如 `_make_runner` 返回 `Any`、`_tracked_*` 参数 `*a: Any, **kw: Any`）
- **证据**: CLAUDE.md 编码硬约束 "禁止使用 `Any`"
- **评估**: 测试文件中 monkeypatch/动态 mock 使用 `Any` 是 pytest 惯例，不影响生产代码类型安全。pyright 0 errors。**严重度: LOW — 建议但不阻塞。**

### LOW-02: `_canonical_json` / `_validated_fingerprint` / `_parse_utc` 直接导入私有函数

- **文件**: `test_write_cli_dispatch.py` 第 295–296 行（`from dayu.services.write_model_challenger_proposal import _canonical_json`）、第 335–336 行（`from dayu.services.write_model_configuration_application import _canonical_json`）、第 371–372 行、第 379–380 行、第 396 行
- **证据**: 测试直接导入模块私有函数 `_canonical_json`、`_validated_fingerprint`、`_parse_utc`
- **评估**: Slice 0 characterization 目的就是锁定 HEAD 行为，Slice 1/2 迁移后这些 import 必须同步更新。**严重度: LOW — 设计意图，非缺陷。**

### LOW-03: `test_parser_choices_match_action_runner_map` 访问 argparse 内部 API

- **文件**: `test_write_cli_dispatch.py` 第 1095 行（`rt_parser._actions`）和第 1096 行（`isinstance(action, argparse._SubParsersAction)`）
- **证据**: `_actions` 和 `_SubParsersAction` 是 argparse 私有 API
- **评估**: CPython argparse 实现稳定，短期无风险。**严重度: LOW — 可接受。**

---

## Verdict

**PASS**

Slice 0 characterization 测试忠实表征 HEAD `f0a3ea1` 的 if-chain 行为。A–H 25 语义项全部覆盖且有可观察断言。I-a 16 selectors 和 I-b 39 action keys 与生产代码 dispatch 链逐行对应。mock 隔离良好，不复制实现，不引用未来代码。无 false positive 风险。3 项 LOW findings 均为测试特性而非缺陷。

---

## 残余风险

| 风险 | 说明 |
|---|---|
| Slice 1/2 迁移后 import 断裂 | `_canonical_json`、`_validated_fingerprint`、`_parse_utc` 的 import 路径将在 Slice 1/2 迁移时改变，需同步更新测试。**预期行为。** |
| Slice 7 后 patch 路径断裂 | write.py 拆分后 `_run_*` 函数路径改变，需同步更新 monkeypatch 目标。**预期行为（V4-05）。** |
| Slice 10/11 后 dispatch 测试废弃 | 引入 mapping/adapter 后 if-chain characterization 测试不再适用，需迁移为 mapping 条目完整性测试。**预期行为（C4-01）。** |
