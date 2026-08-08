# Slice 12 Write Report Implementation 记录

- **日期**: 2026-08-08
- **基线**: `d2801c6 gateflow: accept cli write architecture slice 11`
- **分支**: `codex/dual-model-research-mvp`
- **Gate**: Slice 12 implementation
- **Accepted plan**: v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS，C4、§4.3、C4-01
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## Code review 与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-140135.md`，PASS，提出 1 个 Low
  cosmetic finding。
- MiMo 初审：`docs/reviews/code-review-20260808-140137.md`，PASS，open
  High/Medium/Low=`0/0/0`；将同一 warning 风格明确归类为 pre-existing、non-blocking、
  out-of-scope。
- Controller 裁决：
  `docs/reviews/slice-12-code-review-adjudication-20260808-codex.md`。
- Controller accepted finding=`0`，open High/Medium/Low=`0/0/0`；无需修改 code、
  tests、README 或 accepted plan，当前等待双路 re-review。
- DeepSeek re-review：`docs/reviews/code-review-20260808-141807.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo re-review：`docs/reviews/code-review-20260808-141808.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- 双路复审确认 DS Low 与 MiMo O-1/O-2/O-3 全部 CLOSED；accepted finding=`0`，
  无需 fix，也无需修改 code、tests、README 或 plan。Slice 12 已达到 accepted commit
  gate 前置条件。

## Scope 与变更路径

生产代码：

- `dayu/services/_write_report.py`（新增）
- `dayu/services/write_service.py`

必要测试：

- `tests/application/test_write_service.py`

实现记录：

- `docs/reviews/slice-12-write-report-implementation-20260808-codex.md`

未实施 Slice 13，未改变 public CLI、`WriteService.print_report` 的公开签名、日志文本、
退出码、I/O 顺序或模型目录类型契约；未新增 compatibility re-export、wrapper、lazy
import、cast、`type: ignore` 或 glue seam。

## Pre-edit 审计结论

- clean HEAD 为 `d2801c6`，`_write_report.py` 尚不存在。
- `WriteService.print_report` 实测 exact15：`output_dir` positional + 14 keyword，
  与 accepted v5.5 fenced signature 一致。
- HEAD 控制流与 §1.4/ Slice 12 一致：步骤 1 总是先执行且仅基础退出码 `2` 立即
  返回；步骤 3 gate 后才进入步骤 4；成本重估失败只 warning 并继续；步骤 5/6/7/8–9
  的 `0/2/4` 退出码和异常边界闭合。
- 配置批准 issuance 与普通 request verification 共用原 HEAD 的加载/验证数据。
  为保持 I/O exact，orchestrator 在 issuance 时只调用 helper 7 完成原组合路径，
  非 issuance 时调用 helper 6；不会重复加载或验证。
- `model_catalog` 的 public signature 及向 row 2/row 8 的传播属于 §4.3 明确有界
  `object` 例外，无其它 owner、签名或异常 gap。

## 实现摘要

### 1. `_write_report.py` exact8 owner

新增 exact8 个模块级私有子流程，签名按 plan 逐项锁定：

1. `_validate_print_report_gate_conditions`
2. `_print_repriced_comparison`
3. `_handle_promotion_proposal_export`
4. `_handle_promotion_proposal_verification`
5. `_handle_config_change_request_export`
6. `_handle_config_change_request_verification`
7. `_handle_config_change_approval`
8. `_handle_health_trend_and_proposal_and_preflight`

模块与八个函数均提供完整、具体的中文概览及 Args/Returns/Raises docstring。模块没有
额外 FunctionDef/ClassDef，也不反向 import `write_service.py`。

### 2. `print_report` 只保留编排

- 公开 exact15 签名与返回类型相对 HEAD AST 完全一致。
- 步骤 1 `print_write_report(output_dir, model_catalog=model_catalog)` 仍在入口原位，
  是 docstring 后第一条可执行语句；基础退出码 `2` 仍立即返回。
- 固定调用顺序为 step1 → gate(step3) → repricing(step4) → promotion export/verify
  (step5) → config request export/verify + approval(step6–7) → health/proposal/preflight
  (step8–9)。
- `_print_repriced_comparison` 返回 `None`，重估和 fallback 读取失败只输出原 warning，
  不改变控制流。
- 其余返回 `int` 的 helper 非零即原样传播；最终仍返回基础报告 `exit_code`。
- `print_report` 终态 119 行，低于 accepted `<=150` 门槛。

### 3. 类型与 owner 边界

- `model_catalog` 在 public API、row 2、row 8 的函数签名中 exact3 个
  `Mapping[str, Mapping[str, object]]`，仅为 §4.3 accepted exceptions。
- 原 `proposal: Mapping[str, object] | None` 局部注解随真实 owner 迁移，semantic
  occurrence 1→1；没有新增其它 `object` 签名或逃逸。
- 新模块 `Any`/`cast`/`type: ignore` 均为 0。
- 原来 patch `write_service` 内部依赖的测试迁到 `_write_report` 真实 owner；步骤 1
  `print_write_report` 与 `run_write_pipeline` 的真实 lookup 继续属于
  `write_service`。AST 审计旧 moved-owner patch target=0。

## 测试变更与结果

### 聚焦测试

```text
source .venv/bin/activate
pytest tests/application/test_write_service.py -q
```

结果：`40 passed`（原 38 + 两个真实回归）。新增回归覆盖：

- step1 执行后六类 step3 gate 非法组合精确返回 `2`；
- promotion export 的 policy block=`4`、I/O failure=`2`；
- promotion verification I/O failure=`2`；
- config request export policy block=`4`、I/O failure=`2`。

既有真实路径继续覆盖 step1-before-step3、step4-only-after-gate、repricing
warning-continue、step1→step4→step8 完整顺序、promotion/config/health/proposal/preflight
成功与失败边界。

### 完整相关 write corpus

```text
source .venv/bin/activate
pytest tests/application/test_write*.py \
  tests/engine/test_cli_running_config.py -q
```

结果：`844 passed in 12.18s`。

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/ tests/application/test_write_service.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

- `ruff check --select F,I` 对两个生产文件与修改测试：PASS。
- 同三文件 HEAD/current full-rule finding-code multiset 均为 `{}`，positive
  delta=`{}`。

### 精确 coverage

使用聚焦 40-test 真实 public caller corpus、独立 data file 与 timid tracer：

```text
dayu/services/_write_report.py: 194/237=81.856540% missing=43
dayu/services/write_service.py: 161/184=87.500000% missing=23
```

两个实际修改生产文件均精确 `>=80%`。

## 结构与差分门禁

- `_write_report.py` FunctionDef exact8、ClassDef 0，函数名、参数顺序与返回注解匹配
  accepted 表格。
- `WriteService.print_report` args/return AST 与 HEAD exact，公开参数 total15。
- 编排 helper call order exact9：step1 + 8 helpers；step1 是第一条可执行语句。
- `model_catalog` accepted `object` signature occurrences exact3；新模块
  `Any`/cast/ignore=0；reverse import=0。
- 测试旧 moved-owner patch target=0；新 owner patch 覆盖真实 lookup。
- `git diff --check`：PASS。

## README 决策

- `tests/application/test_write_service.py` 已在 `tests/README.md` 当前测试入口清单中，
  本 Slice 只迁移 private dependency patch owner 并增强同一入口，不改变测试分层、
  运行方式或维护约定，因此 `tests/README.md` 无需修改。
- public CLI 命令、参数与用户工作流未变化，根 `README.md` 无需修改。
- 本 Slice 是 service 内部 owner 拆分，不改变稳定 UI→Service→Host→Agent 分层；
  `dayu/README.md` 无需在 Slice 13 前提前修改。

## Plan gap 与 residual risk

- Plan gap：无。公开签名、exact8 owner、步骤顺序、异常/退出码、model catalog 传播、
  真实 test patch owner 与 coverage 门槛全部闭合。
- `_write_report.py` 仍有 43 条未由聚焦 corpus 执行，主要是已参数化异常 tuple 中的
  等价异常成员及内部不变量防御分支；代表性 policy/I/O/status 路径、完整既有 public
  corpus 与精确 81.856540% coverage 已覆盖 accepted correctness boundary。该项分类为
  current-slice non-blocking covered-by-equivalent-path，不是未分类 residual。
- `write_service.py` 仍有 23 条未执行 statement，位于本 Slice 未改的其它 service
  路径；修改后的 `print_report` 真实编排与失败路径均已覆盖。该项分类为 pre-existing
  out-of-scope/non-blocking。
- 当前无 deferred、未分类或需要外部 owner 的风险；可进入 code review。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
