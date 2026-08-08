# Slice 11 Write Dispatch Implementation 记录

- **日期**: 2026-08-08
- **基线**: `122acd8 gateflow: accept cli write architecture plan v5.5`
- **分支**: `codex/dual-model-research-mvp`
- **Gate**: Slice 11 implementation
- **Accepted plan**: v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS，
  S11-CTRL-01/02、C3、C4-01
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## Code review 与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-132706.md`，结论 PASS，
  material open finding=0；其中 F-10 Low observation 经 Controller 裁决为
  `rejected-with-reason / non-defect`。
- MiMo 初审：`docs/reviews/code-review-20260808-132707.md`，结论 conditional PASS；
  F-01–F-08 均经 Controller 逐项裁决为 `rejected-with-reason`，accepted finding=0。
- Controller 裁决：
  `docs/reviews/slice-11-code-review-adjudication-20260808-codex.md`。
- Controller 当前 open High/Medium/Low=`0/0/0`；无需修改 code、tests、README 或
  accepted plan。MiMo 初审把 pre-existing 建议计为 open，且 reviewer metadata 写为
  codex、实际 review pane 为 MiMo，需双路 targeted/corrective re-review 闭环后再进入
  accepted commit gate。
- DeepSeek re-review：`docs/reviews/code-review-20260808-133850.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- MiMo corrective re-review：`docs/reviews/code-review-20260808-133851.md`，PASS，
  open High/Medium/Low=`0/0/0`；初审 reviewer metadata 与错误 open 计数已纠正。
- 双路复审确认 DS F-10 与 MiMo F-01–F-08 共 9 项 observations 全部 CLOSED，
  accepted finding=0，无需进一步修改 code、tests、README 或 plan；当前 Slice 已达到
  accepted commit gate 前置条件。

## Scope 与允许路径

生产代码：

- `dayu/cli/arguments.py`
- `dayu/cli/commands/_write_dispatch.py`（新增）
- `dayu/cli/commands/write.py`

必要测试与文档：

- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_challenger.py`
- `tests/engine/test_cli_running_config.py`
- `tests/README.md`

实现记录：

- `docs/reviews/slice-11-write-dispatch-implementation-20260808-codex.md`

明确未实施 Slice 12/13，未修改 public CLI 参数、退出码、日志、I/O 或其它模块
ownership；未新增 compatibility re-export、wrapper、lazy import 或 glue seam。

## 实现摘要

### 1. Arguments producer/consumer 边界

- 新增 `WriteDispatchArguments(Protocol)` exact20 字段：Phase A bool 11、Phase B
  bool 2、Phase D/F/G bool 3、Phase A path 3、Phase F path 1。
- `DayuCliArguments` 原子追加同名同类型 exact20 字段，终态 exact21
  `AnnAssign`（research 1 + write 20）。
- Dayu 仍仅继承 `argparse.Namespace`，零字段默认值、零 `__init__`、零 Protocol
  inheritance；两个 Protocol 字段并集与 Dayu 字段集合精确相等。
- `arguments.py` 仍只依赖 Python 标准库。

### 2. Phase-specific typed contexts

- 新建 `_write_dispatch.py`，只定义 exact4 个 `frozen=True` dataclass：
  `_WriteCommandContext`、`_WriteConfigurationContext`、
  `_EarlyWriteSubcommandEntry`、`_ConfigurationWriteSubcommandEntry`。
- 模块不定义 runner、不反向导入 `write.py`，依赖方向保持单向且 import smoke
  通过。

### 3. Phase A/B bounded replacement

- `write.py` 新增 exact16 个带完整中文 docstring 的 adapter：Phase A exact14、
  Phase B exact2。
- 新增两个 `Final[Sequence[...]]` 表，长度 exact14/2，runner 全部绑定命名
  adapter，零 lambda runner；优先级与 HEAD if-chain 一致。
- `run_write_command` 只将原 Phase A 14 个 if 与 Phase B 2 个 if 替换为：
  A context/loop → model override → shared execution options → B context/loop。
- clear/verify/recover 三个 Phase A adapter 各惰性构造 execution options exact1；
  其他 Phase A adapter 为 0；两个 Phase B adapter 只读预计算 context；A 未命中后
  shared build exact1 并继续供后续阶段复用。

### 4. S11-CTRL-02 保留语义

- exact20 selector 按 accepted 边界改为直接属性；table-out argparse 字段继续保持
  HEAD `getattr`，相对 HEAD 无新增或扩散。
- Phase E inline 三语句 subtree 与 `122acd8` AST exact：四字段 required-any、真实
  plan builder、output-boundary assert、五类异常、精确日志与 `return 2` 全部保留。
- Phase F 使用 direct approval selector，并保留
  `assert challenger_run_plan is not None` fail-loud 不变量。
- `run_write_command` 全部 `ExceptHandler` AST 与 HEAD exact，覆盖 Phase H plan
  rebuild 四异常、两个 challenger-config `ValueError` 与 materialize `Exception`
  partial-success；变量名保持 `write_exit_code`。
- 生产源码与当前 plan contract 中不存在 phantom Phase E helper；未新增 nested helper。

## 测试修改

- 将原 16-selector if-chain characterization 升级为 phase-table/adapter 契约：
  Phase A bool 11、Phase A path 3、Phase B bool 2，继续覆盖 mixed priority、空 path、
  lazy/shared build 与真实 runner 参数。
- 新增 arguments 1/20/21、dispatch exact4 frozen dataclass、adapter exact16、table
  14+2、runner identity 与 bounded ordering AST 测试。
- 新增 Phase E 四 required fields、全空 inventory、五类异常；Phase F fail-loud；
  Phase H plan rebuild 四异常、preflight/main challenger-config 两个 `ValueError` 与
  materialize partial-success 回归。
- `test_write_challenger.py` 与 `test_cli_running_config.py` 的真实 write-entry direct
  fixture 在测试边界补齐 parser 正常写入的 exact20 selector 默认值；生产 Dayu 不加
  默认值，也未恢复 defensive `getattr`。

## 验证结果

### Pytest

1. 聚焦 dispatch：

   ```text
   source .venv/bin/activate &&
   pytest tests/application/test_write_cli_dispatch.py -q
   ```

   结果：`124 passed`（原 102 + 新增 22 个参数化实例）。

2. 完整相关 write corpus：

   ```text
   source .venv/bin/activate &&
   pytest tests/application/test_write*.py \
     tests/engine/test_cli_running_config.py -q
   ```

   结果：`842 passed in 12.97s`。

### Pyright

```text
source .venv/bin/activate &&
pyright dayu/cli/ \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_challenger.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

- 生产路径与聚焦 application tests 的 `ruff check --select F,I`：PASS。
- `tests/engine/test_cli_running_config.py` 当前仍有 HEAD 已存在的一个 `I001`；未做
  全块排序噪音。
- 六个 Python 改动路径的 HEAD/full-rule finding-code multiset：

  ```text
  HEAD={'I001': 1, 'PIE804': 4, 'UP035': 1}
  CURRENT={'I001': 1, 'PIE804': 4, 'UP035': 1}
  POSITIVE_DELTA={}
  ```

### 精确 coverage

使用同一 842-test 真实 caller corpus 与独立 timid coverage data file：

```text
dayu/cli/arguments.py: 48/48=100.000000% missing=0
dayu/cli/commands/_write_dispatch.py: 24/24=100.000000% missing=0
dayu/cli/commands/write.py: 187/205=91.219512% missing=18
```

三个实际修改生产文件均精确 `>=80%`。

### 结构、依赖与差分

- Arguments AST：Research/Write/Dayu=`1/20/21`，Protocol union=Dayu exact。
- Dispatch AST：exact4 frozen dataclass、顶层函数 0、reverse import 0。
- Write AST：adapter exact16、table exact14/2、lambda runner 0、nested helper 0。
- Build 计数：Phase A lazy adapters 3×exact1；Phase B adapters 0；shared exact1。
- Phase E AST=HEAD；全部 exception handlers=HEAD；table-out `getattr` positive
  delta=0；phantom=0；import DAG 与 import smoke=PASS。
- `Any`/`object`/`cast` semantic count 与 HEAD 分别保持 `134/152/33`，positive
  delta=0；没有新增 `type: ignore` 或 `noqa`。
- `git diff --check`：PASS。

## README 决策

- `tests/README.md` 已将 write 测试入口从 if-chain characterization 更新为当前
  Protocol/phase-table/Phase E-F-H 契约。
- 用户命令、参数与使用方式未变化，根 `README.md` 不需更新。
- 稳定分层边界未变化，`dayu/README.md` 不需更新。

## Plan gap 与 residual risk

- Plan gap：无。16 inventory、target signature、Phase E/F/H AST、异常集合、真实
  test owner 与 coverage 门槛均与 accepted v5.5 一致。
- 未覆盖 statements：`write.py` 仍有 18 条未由本 corpus 执行，但精确 coverage 为
  91.219512%；核心迁移路径与 accepted failure corpus 均已覆盖，不构成 blocking
  residual。
- Ruff 既有 `I001`/`PIE804`/`UP035` 由 HEAD baseline 持有，当前 positive delta=0，
  本 Slice 不扩大格式化 scope。
- 当前没有 deferred、未分类或需要外部 owner 的风险；可进入 code review。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
