# Slice 6 v4.9 W12 Cycle Erratum

- **日期**: 2026-08-08
- **基线**: `6720879 gateflow: accept cli write architecture plan v4.8`
- **Gate**: plan fix / W12 dependency-cycle erratum
- **计划**: v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **状态**: v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **允许修改**:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md` 与本 artifact
- **代码/测试状态**: clean，未进入 Slice 6 implementation；未修改 production、
  tests、README 或外部 review artifact

## 输入证据

- DeepSeek：`docs/reviews/plan-review-20260808-042837.md`，
  PASS_WITH_ERRATA，open 7-01 Medium、7-02 Low。
- MiMo：`docs/reviews/plan-review-20260808-042838.md`，PASS with Medium
  finding，open F-01 Medium。
- DeepSeek final re-review：`docs/reviews/plan-review-20260808-044555.md`，
  PASS，open High/Medium/Low=0/0/0。
- MiMo final re-review：`docs/reviews/plan-review-20260808-044556.md`，PASS，
  open High/Medium/Low=0/0/0。
- HEAD `6720879` 直接证据：5 个 nested `_snapshot_builder` 中，闭包 #1 位于
  待迁入 `_write_config_application.py` 的
  `_run_write_model_configuration_application` 内；闭包 #2–#5 仍位于
  `write.py` 的 rollback、manual recovery application、verification、clearance
  runners。
- v4.8 的依赖合同要求 `_write_snapshot_builder.py` 顶层 import
  `_write_config_application.py`，且不存在反向路径。若闭包 #1 迁移后反向调用
  `build_snapshot_builder`，将形成 application↔builder 循环。

两路 review 对根因和最小方案结论一致：闭包 #1 必须在 application 模块内直接
使用 `functools.partial`，闭包 #2–#5 才使用公共 factory。

## Controller 裁决

### DeepSeek 7-01 Medium — “替换 5 处”未区分迁移后的 ownership

- **裁决**: ACCEPT。
- **修正**: W12 与 Slice 6 分别锁定闭包 #1 和 #2–#5 的实现路径。闭包 #1
  随 runner 迁入 application 模块后，直接对同模块
  `_build_fresh_application_routing_snapshot` 做 `functools.partial`；其余四处在
  Slice 6 的 `write.py` 调 `build_snapshot_builder`。
- **语义约束**: 闭包 #1 迁移前未传 `run_label`，因此 direct partial 只绑定
  `args`、`paths_config`、`execution_options`，不得显式绑定 `run_label`；调用时继续
  使用函数默认值，而不是把当前默认字面量提前固化到 caller。

### DeepSeek 7-02 Low — 缺失 application→builder 反向 import gate

- **裁决**: ACCEPT。
- **修正**: Slice 6 validation、Ready-for-Review checklist 与风险表新增双向 import
  结构审计：application→builder 为 0；builder→application 的目标 import 精确存在；
  builder→write 为 0。同时锁定 application 中 `functools.partial` 精确 1 和 AST
  nested `_snapshot_builder` 为 0。

### MiMo F-01 Medium — application runner callback 构造方式未指定

- **裁决**: ACCEPT。
- **修正**: 与 DeepSeek 7-01 同源，纳入 **S6-W12-CYCLE-01**。MiMo 示例显式
  传入 `run_label="configuration-application"`，Controller 按 HEAD 旧调用的真实
  语义进一步收紧为“不显式绑定 `run_label`”，避免把 callee 默认值复制为 caller
  魔法字符串。
- **路径纠正**: MiMo 文中的 `dayu.cli.write._write_snapshot_builder` 是错误路径；
  本仓库正确模块路径为
  `dayu.cli.commands._write_snapshot_builder`。计划和实施门禁只使用正确路径。

## S6-W12-CYCLE-01 精确合同

1. `_write_config_application.py` 中
   `_run_write_model_configuration_application` 使用精确一次：

   ```python
   functools.partial(
       _build_fresh_application_routing_snapshot,
       args=args,
       paths_config=paths_config,
       execution_options=execution_options,
   )
   ```

   不传 `run_label`，不 import `_write_snapshot_builder`。
2. `_write_snapshot_builder.py` 继续顶层 import
   `_build_fresh_application_routing_snapshot`，并以模块级
   `_build_snapshot_for_args` + `build_snapshot_builder` factory 服务其余 callers；
   不 import `write.py`。
3. Slice 6 的 `write.py` 中闭包 #2/#3 调 factory 并沿用默认 label；闭包 #4/#5
   分别显式传
   `configuration-manual-recovery-verification`、
   `configuration-manual-recovery-clearance`。
4. Slice 7/8 迁移相关 runner 时，连同已建立的 factory call 和单向 import 一并
   迁移；不得恢复 nested helper 或改变 label。
5. 不修改四个 Slice 6 函数的 accepted 签名，不增加 compatibility re-export、
   wrapper、DI 参数、lazy import、cast、type-ignore、`Any` 或 `object`。

## 方案裁决

### 方案 A — ACCEPTED

application 内闭包 #1 使用同模块 direct partial，其余四处使用 builder factory。
该方案保持 builder→application 唯一依赖方向、旧 callback 调用时序和五组 label
语义，同时不新增抽象层。

### 方案 B — REJECTED

反转 ownership、把核心 snapshot 构建逻辑迁入 builder 会使职责命名与依赖语义
倒置，并扩大已接受 Slice 6 文件所有权；没有必要。

### 方案 C — REJECTED

通过额外 callable 参数、lazy import、compatibility wrapper 或其他 glue seam 绕开
循环会修改函数合同或制造间接依赖，违反 AGENTS 与 accepted scope。

## 测试与门禁

- factory 真实 callback test：调用 `build_snapshot_builder` 返回的零参数 callback，
  由依赖 stub 捕获并断言 `args`、`paths_config`、`execution_options`、默认/显式
  `run_label` 和返回 mapping。
- application runner 真实依赖路径：transaction dependency stub 必须实际调用收到的
  `snapshot_builder` 并断言 mapping/runner 结果，证明 direct partial callback 可用。
- **拒绝 MiMo 的临时不可 import 测试建议**：人为令
  `_write_snapshot_builder` 不可 import 会把行为测试耦合到 Python import cache、加载
  顺序和 monkeypatch 细节，脆弱且不能比 AST/rg 更好地证明 DAG；改用真实 runner
  dependency stub 加静态结构门禁。
- AST/rg：application→builder import 0；builder 从 application import
  `_build_fresh_application_routing_snapshot` 精确 1；builder→write import 0；
  application `functools.partial` 精确 1；application+write
  nested `_snapshot_builder` 合计 0；Slice 6 的 `write.py` factory call 精确 4，label
  依次为默认、默认、verification、clearance。
- 既定 application/engine write 测试通过；`pyright dayu/cli/` 零 errors；Ruff F/I
  与 HEAD full-rule finding-code multiset delta=0；三个改动生产文件精确 statement
  coverage 逐文件 `>=80%`；`git diff --check` 通过。

## Plan 修改摘要

- header、状态、尾注升级为 v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS；v4.8
  accepted 历史保留。
- 审查来源与 changelog 纳入 042837/042838 和 S6-W12-CYCLE-01。
- W12、依赖证明、Slice 6、Slice 7/8、validation、风险与 Ready-for-Review
  checklist 均同步同一依赖/label/测试合同。
- v4.9 仅关闭 W12 cycle gap，不改变其他 Slice 行为、public CLI、类型 ownership 或
  既有 accepted 签名。

## Final dual plan re-review 结论

- DeepSeek `docs/reviews/plan-review-20260808-044555.md` 与 MiMo
  `docs/reviews/plan-review-20260808-044556.md` 均为 PASS，open
  High/Medium/Low=0/0/0。
- 042837 的 7-01 Medium、7-02 Low 与 042838 的 F-01 Medium 均已由
  S6-W12-CYCLE-01 精确关闭；两路 final review 未发现新增 finding、反向依赖、
  循环、glue seam 或 scope regression。
- v4.9 已达到 ACCEPTED / DUAL PLAN RE-REVIEW PASS；Slice 6 可按本计划恢复
  implementation。

## Residual 与停止状态

- 当前无未分类技术 residual；两个初审的 3 个 findings 均 CLOSED，open
  High/Medium/Low=0/0/0。
- v4.9 已 accepted，Slice 6 plan gate 阻塞解除，可进入 implementation。
- 未 stage、commit、push；未进入 code/test/README 修改。
