# Slice 5 C1 v4.6 依赖勘误记录

- **日期**: 2026-08-08
- **Gate**: plan fix / dependency erratum
- **基线计划**: v4.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **接受计划**: v4.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **控制项**: S5-CTRL-01..03
- **状态**: ACCEPTED / DUAL PLAN RE-REVIEW PASS

## 输入证据

- DeepSeek planreview:
  `docs/reviews/plan-review-20260808-013315.md`
- MiMo planreview:
  `docs/reviews/plan-review-20260808-013316.md`
- DeepSeek 首轮 re-review:
  `docs/reviews/plan-review-20260808-015208.md`
- MiMo 首轮 re-review:
  `docs/reviews/plan-review-20260808-015209.md`
- DeepSeek final re-review:
  `docs/reviews/plan-review-20260808-020628.md`
- MiMo final re-review:
  `docs/reviews/plan-review-20260808-020629.md`
- Master plan:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- 源码基线:
  `dayu/cli/commands/write.py`
- 直接测试:
  `tests/application/test_write_service.py`
  `tests/application/test_write_cli_dispatch.py`
  `tests/engine/test_cli_running_config.py`

## 源码事实

1. `_validate_research_materialization_args` 在当前源码中直接调用
   `_challenger_requested`；后者还被 `run_write_command` 三处调用。按 v4.5
   分到未来 Slice 8 会让 Slice 5 独立 commit 只能形成 params→write→params
   循环或使用禁止的临时复制/lazy import。
2. `_resolve_write_model_override_name` 的 Python function globals 会绑定在
   其定义模块。迁移后，重绑 `write.setup_model_name` 不会改变
   `_write_config_helpers.setup_model_name`。
3. `tests/engine/test_cli_running_config.py` 当前精确包含 13 处
   `dayu.cli.commands.write.setup_model_name` monkeypatch。
4. `_log_write_preflight_result` 与 `write.py` 80+ 个真实日志 caller 共用
   `MODULE = "APP.WRITE"`；常量需要单一、无反向 import 的真源。
5. 原源码从 `_challenger_requested` 到 `_build_auto_bootstrap_args` 的连续组
   共 14 个函数；提前迁走 1 个后，Slice 8 剩余 exact 13。

## Controller 裁决

### S5-CTRL-01 — 接受 DeepSeek F01

`_challenger_requested` 提前迁入 `_write_params_validation.py`，与原三个
validator 组成 exact 4-function module。`write.py` 正常顶层 import 这四个
private symbol；params 禁止 import `write.py` 或尚不存在的未来
`_write_challenger.py`。

Slice 8 exact 13 函数为：

1. `_challenger_preflight_cli_args`
2. `_verify_challenger_preflight_approval_before_host`
3. `_build_challenger_run_plan_from_args`
4. `_assert_challenger_run_output_boundaries`
5. `_load_current_challenger_proposal`
6. `_persist_challenger_run_authorization_after_preflight`
7. `_verify_and_consume_challenger_run_approval_before_host`
8. `_build_challenger_write_config`
9. `_preflight_champion_and_challenger`
10. `_run_champion_challenger_experiment`
11. `_manifest_has_usable_company_facets`
12. `_needs_auto_research_bootstrap`
13. `_build_auto_bootstrap_args`

MiMo 的 14→12 建议 REJECTED。计数真源是源码连续组 14 个函数，迁走
`_challenger_requested` 后为 13；三个所谓未分配 auto-bootstrap helper 已
明确列入这 13 个，不存在缺项。

MiMo 将 `_challenger_requested` 归 `_write_config_helpers` 的 ownership 建议
REJECTED。它的唯一直接函数 caller 是参数 validator，与
`_validate_research_materialization_args` 同域可以消除编译期耦合；write
仅通过正常 import 使用。

### S5-CTRL-02 — 接受 DeepSeek F02

`_write_config_helpers.py` 从 `dayu.cli.dependency_setup` 功能性 import
`setup_model_name`。`write.py` 删除该 import，不提供 compatibility
re-export、wrapper 或同步 seam。13 处测试 patch 全部迁到
`dayu.cli.commands._write_config_helpers.setup_model_name`；旧目标 0、新目标
13。

MiMo 的 setup re-export 方案 REJECTED。Python 函数的 globals 绑定在定义
模块；重绑 `write.setup_model_name` 不会影响已迁移函数内部解析，因此该
re-export 既不能保存真实 monkeypatch 行为，也会成为无生产 caller 的兼容
转发。

`write.py` 对本 Slice 8 个 private symbol 的顶层 import 都是
`run_write_command` 或迁移期间 caller 的功能依赖，继续自然支持现有
`write.<private>` direct import/monkeypatch 和 global lookup，不属于兼容
转发。包括 application test 对
`write._validate_research_materialization_args` 的 direct import 在内，这
8 个 private import 均按计划保留，不迁到新模块。

### S5-CTRL-03 — 接受 DeepSeek F03 与 MiMo MODULE 结论

`MODULE = "APP.WRITE"` 单一定义迁到 `_write_config_helpers.py`。`write.py`
和 Slice 6/7/8 中实际记录日志的目标模块正常 import MODULE；不复制常量，
不反向 import `write.py`。`write.MODULE` 因真实 caller 的顶层功能 import
仍自然可见，但 Slice 8 终态不再声称本地定义。

## 其他 observations 裁决

- **DeepSeek O-01 — dependency_setup cycle 风险**:
  CLOSED / NON-DEFECT。`dependency_setup.py` 当前不 import `write.py` 或
  `commands` 私有模块；Slice 5 增加 import smoke、全 `dayu/cli/` pyright
  与依赖方向检索。
- **DeepSeek O-02 — setup_loglevel/setup_paths patch 路径**:
  CLOSED / NON-DEFECT。两者仍由 `run_write_command` 在 `write.py` 中直接
  调用，本 Slice 不迁移；相关 application/engine tests 必须保持通过。
- **MiMo “未来模块无 cycle”观点**:
  REJECTED。Slice 5 是独立 accepted commit，此时 `_write_challenger.py`
  尚不存在；params→write 会与 write→params 立即构成循环，不能用未来 slice
  证明当前 commit 合法。
- **MiMo 14→12 及三个 helper 未分配观点**:
  REJECTED。源码连续组逐名审计给出 exact 13，三个 auto-bootstrap helper
  已明确归入 Slice 8。

## 首轮 re-review observations 与 Controller 裁决

输入：

- DeepSeek:
  `docs/reviews/plan-review-20260808-015208.md`
  （PASS，open High/Medium = 0，2 个 Low residual observations）
- MiMo:
  `docs/reviews/plan-review-20260808-015209.md`
  （PASS，open High/Medium = 0，O-01..O-04）

逐项裁决：

- **DeepSeek L-01 — Slice 6/7/8 MODULE import 实施验证**:
  CLOSED / NON-DEFECT。Master plan 已为各 slice 明确 MODULE 真源，并要求
  唯一定义、import smoke、依赖方向和 pyright 门禁；属于既有实施检查，不需
  扩大 plan。
- **DeepSeek L-02 — setup_loglevel/setup_paths 未来 patch 路径**:
  CLOSED / NON-DEFECT。二者当前仍由 `run_write_command` 在 `write.py`
  中真实调用，Slice 5 不迁移；未来若 ownership 改变，由对应未来 slice
  基于真实 call site 处理。
- **MiMo O-01 — `_challenger_requested` 内外两种 globals owner**:
  ACCEPTED / PLAN ENHANCED。`write._challenger_requested` 是
  `run_write_command` 三个 global call site 的正确 patch owner；
  `_write_params_validation._challenger_requested` 是真实 validator 内部
  调用的正确 patch owner。Plan 已新增两条真实回归分别锁定两条路径。
- **MiMo O-02 — blanket 迁移旧 write patch**:
  REJECTED。monkeypatch owner 由被测 call site 的函数 globals 决定，不能
  把所有 `write._challenger_requested` patch 迁到 params。当前 engine test
  约 line 5934 同时 patch validator 本身与 write challenger，服务
  `run_write_command` 路径，保持不变。
- **MiMo O-03 — application direct import validator 应迁新模块**:
  REJECTED / NON-DEFECT。`write.py` 对 8 个 private symbol 的顶层 import
  是真实功能依赖并承担已接受的 direct import/monkeypatch 契约；application
  test 继续从 `write.py` direct import，不迁移。
- **MiMo O-04 — import binding 替换定义的语义变化**:
  CLOSED / NON-DEFECT。`write.py` global binding 从本地定义变为顶层 import
  后，monkeypatch 仍替换同一 `write.__dict__` binding，行为等价且正是迁移
  计划目标。

## Final 双路 re-review 结论

- DeepSeek `docs/reviews/plan-review-20260808-020628.md`: PASS。
- MiMo `docs/reviews/plan-review-20260808-020629.md`: PASS。
- 两路均确认全部 16 项 findings CLOSED，open High/Medium/Low = 0。
- `_challenger_requested` 双 owner、Slice 8 exact 13 函数、
  `setup_model_name` exact 13 patch 与 `MODULE = "APP.WRITE"` 单一真源均已
  完整闭环；v4.6 达到 code-generation-ready 标准。

## Master plan 更新

- header、状态与底部状态改为
  `v4.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，保留 v4.5 accepted 历史。
- 审查来源追加两份 dependency review、两份首轮 re-review 与两份 final
  re-review。
- changelog 新增 S5-CTRL-01..03。
- 更新 write.py 功能域、架构树、依赖方向、monkeypatch 契约、Slice 5、
  Slice 6/7/8 MODULE 来源、Slice 8 exact 13 名单、验证与最终完成清单。
- 其他 slice 仅补充 MODULE 正常 import 真源，不改变实施语义。

## 实施门禁

Slice 5 必须验证：

- 计划既有两份 application tests 与相关 engine write tests；
- import/cycle smoke；
- 旧 setup patch 0、新 patch 13；
- `MODULE = "APP.WRITE"` 唯一定义；
- `write.py` 旧定义 0、两个新模块定义合计 8；
- 8 个 `write.<private>` identity、direct monkeypatch 与 global lookup；
- patch `write._challenger_requested` 控制真实 `run_write_command` 路径；
- patch `_write_params_validation._challenger_requested` 控制真实
  `_validate_research_materialization_args` 内部路径；
- `_write_config_helpers.py`、`_write_params_validation.py`、修改后的 `write.py`
  精确单文件 coverage 均 `>= 80%`；
- `pyright dayu/cli/`；
- Ruff F/I 与 HEAD 全规则 finding code multiset delta；
- `git diff --check`。

## 范围与 residual risk

- 本次只修改 master plan 并新增本 artifact；不修改 code/tests/README。
- Slice 6/7/8 实施前仍需按各自真实 call graph 核对 MODULE import；该风险已
  由 plan 写入单一真源与禁止反向 import 的可验证约束。
- 无未分类 plan risk；v4.6 已 accepted，Slice 5 可按 accepted contract
  进入实施。
