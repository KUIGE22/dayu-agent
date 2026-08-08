# Slice 6 v4.8 Argument Type Ownership Erratum

- **日期**: 2026-08-08
- **基线**: `2c50332 gateflow: accept cli write config params slice 5`
- **Gate**: plan fix / type-ownership erratum
- **计划**: v4.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **状态**: v4.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **允许修改**:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md` 与本 artifact
- **代码/测试状态**: clean，未进入 Slice 6 implementation

## 输入证据

- DeepSeek：`docs/reviews/plan-review-20260808-035654.md`，
  PASS_WITH_ERRATA，F01 High、F02 Medium、F03 Medium、F04 Low、F05 Medium。
- MiMo：`docs/reviews/plan-review-20260808-035655.md`，FAIL，F01 High、
  F02 Medium、F03 Low。
- DeepSeek 首次 re-review：`docs/reviews/plan-review-20260808-041140.md`，
  核心结论 PASS，报告 Rv4.8-F01/F02/F03 三项 Low 文字观察。
- MiMo 首次 re-review：`docs/reviews/plan-review-20260808-041141.md`，PASS，
  open High/Medium/Low=0/0/0。
- DeepSeek final corrective re-review：
  `docs/reviews/plan-review-20260808-042044.md`，PASS，open
  High/Medium/Low=0/0/0。
- MiMo final re-review：`docs/reviews/plan-review-20260808-042045.md`，PASS，
  open High/Medium/Low=0/0/0。
- HEAD 直接证据：`dayu/cli/arguments.py` 不存在；源码/测试中的
  `DayuCliArguments` 为 0；`parse_arguments`、write/research-template entries、
  Slice 6 待迁 caller 均使用 `argparse.Namespace`。

两路对 gap 的事实判断一致：v4.7 在 Slice 6 引用了尚不存在且没有创建 owner 的
`DayuCliArguments`，并在 Slice 10 错写“已定义”。

## 首次 Re-review 观察裁决

### Rv4.8-F01 Low — ExecutionOptions owner 措辞

- **裁决**: ACCEPT / TEXT FIX。
- **修正**: 将 `dayu.execution.options` 从“真实 owner”改称“CLI 标准导入路径”，
  并明确规范定义位于 `dayu.contracts.execution_options`；实际 import 路径不变。

### Rv4.8-F02 Low — v4.0 历史 verdict 可能误导当前 gate

- **裁决**: ACCEPT / CLARIFY。
- **修正**: 在 v4.0 `PASS_WITH_RISKS` 的“可进入 implementation”旁明确这是
  v4.0 历史判决，当前状态以顶部 v4.8 gate 为唯一权威。

### Rv4.8-F03 Low — Slice 0 原则排除列表未同步

- **裁决**: ACCEPT / TEXT FIX。
- **修正**: Slice 0 原则显式排除 Slice 10 的 `DayuCliArguments`/dispatch
  mapping 与 Slice 11 的 adapter/phase table，与实现级说明一致。

三项均为文字准确性修复，不改变 S6/S10/S11 合同；修复后进入 final dual
re-review，并由下述两份 final artifact 完成闭环。

## Final dual re-review 结论

- DeepSeek 042044 与 MiMo 042045 均 PASS，open High/Medium/Low=0/0/0。
- 初始 DS/MiMo 的 8 项事实 finding 与首次 DeepSeek re-review 的 3 项 editorial
  Low 全部 CLOSED；无 accepted finding 未修复、无 deferred 或
  needs-more-evidence 项。
- v4.8 已达到 ACCEPTED / DUAL PLAN RE-REVIEW PASS，Slice 6 可按 accepted
  S6-CTRL-01 与 W12 合同恢复实施。

## Controller 裁决

### DeepSeek F01 High — Slice 6 前向依赖不存在的类型

- **裁决**: ACCEPT。
- **修正**: Slice 6 `_build_snapshot_for_args` 的 `args` 改为精确
  `argparse.Namespace`；同一切片不创建/import `DayuCliArguments`。

### DeepSeek F02 Medium — Slice 10 创建职责歧义

- **裁决**: ACCEPT。
- **修正**: Slice 10 明确成为 `dayu/cli/arguments.py`、
  `DayuCliArguments(argparse.Namespace)` 与
  `ResearchTemplateDispatchArguments` 的原子创建 owner；Slice 11 只追加
  `WriteDispatchArguments`。

### DeepSeek F03 Medium — Slice 0 使用未来类型

- **裁决**: ACCEPT。
- **修正**: Slice 0 characterization 明确构造当时 HEAD 存在的
  `argparse.Namespace`，不得引用 Slice 10 的未来类型。

### DeepSeek F04 Low — Slice 6 config application 参数类型未写明

- **裁决**: ACCEPT。
- **修正**: Slice 6 两个 config application 函数的完整签名都明确
  `args: argparse.Namespace`、`execution_options: ExecutionOptions`；routing
  snapshot 返回 `Mapping[str, ModelConfigJsonValue]`。

### DeepSeek F05 Medium — Slice 10 缺少机械传播清单

- **裁决**: ACCEPT。
- **修正**: Slice 10 成为唯一传播 owner，原子更新：
  `parse_arguments` 返回和 runtime namespace、research-template entry、39 个
  mapping runners、write entry、Slice 6 四函数。45 个 args 签名加
  `parse_arguments` 返回均有唯一 owner；表外 helper 不扩大范围。

### MiMo F01 High — Slice 6 未声明前向类型

- **裁决**: ACCEPT，与 DeepSeek F01 同源。
- **修正**: Slice 6 四函数全部使用当时存在的 `argparse.Namespace`；
  `ExecutionOptions` 与 `Mapping[str, ModelConfigJsonValue]` 精确类型不变。

### MiMo F02 Medium — `arguments.py` 创建职责漂移

- **裁决**: ACCEPT，与 DeepSeek F02/F05 同源。
- **修正**: Slice 10 原子创建与传播；`parse_arguments()` 必须调用
  `parser.parse_args(namespace=DayuCliArguments())`，返回真实子类实例，不允许只改
  注解。

### MiMo F03 Low — Slice 0 类型不可能存在

- **裁决**: ACCEPT，与 DeepSeek F03 同源。
- **修正**: Slice 0 使用 `argparse.Namespace`，Slice 10 的 direct tests 再按真实
  owner 迁移到 `DayuCliArguments`。

## 选型

### 方案 A — ACCEPTED

- Slice 0–9 忠实使用 `argparse.Namespace`。
- Slice 10 原子创建真实 `DayuCliArguments` 子类与 research-template Protocol，
  通过 `namespace=DayuCliArguments()` 获得运行时身份，并同 commit 完成签名传播。
- Slice 11 仅追加 write Protocol/context/adapter。
- 每个切片独立可 import、可测试、可通过 pyright，不产生 partial type module。

### 方案 B — REJECTED

在 Slice 6 提前创建只含 `DayuCliArguments` 的 partial `arguments.py` 会扩大
C1+W12 scope，把类型系统建设拆成两个切片，并诱导 Slice 7–9 依赖未完成边界。

### 方案 C — REJECTED

type alias、空 compatibility shell、cast、字符串 forward reference 或 glue 转换均
不能证明真实 parser 返回类型，还违反零 cast/零 compatibility glue 的项目约束。

## Callable 参数类型事实

`Callable` 的参数类型是逆变的：接受较宽 `argparse.Namespace` 的函数理论上可作为
`Callable[[DayuCliArguments], int]` 使用，因为所有 `DayuCliArguments` 都是
`argparse.Namespace`。两份 review 中任何相反的“必须同签名才可赋值”论断均不作为
Controller 依据。计划仍机械收窄 39 runners，是为了终态签名一致、所有权清晰和
targeted rg 可审计，而不是因为错误的协变/逆变假设。

## 新增门禁

- runtime parser 测试：真实 `parse_arguments()` 结果满足
  `isinstance(result, DayuCliArguments)`，command、显式 flag 与至少一个默认字段均
  正确保留。
- `pyright dayu/cli/` 零新增/扩散错误。
- targeted rg/AST：Slice 6 四函数在 Slice 6 时精确使用 Namespace；Slice 10 后
  `parse_arguments`、两 entries、39 mapping runners 与 Slice 6 四函数的旧
  Namespace 签名为 0。
- `arguments.py` 中 Dayu/Research Protocol 各定义 1 次，`namespace=` 构造 1 次；
  Slice 11 只追加 Write Protocol。
- 禁止 cast/type alias/type-ignore/forward-ref/glue；各 Slice tests 独立绿。

## 影响与 residual

- v4.8 只修正类型所有权、创建时序、机械传播与对应测试门禁；不改变 CLI 参数名、
  dispatch 行为、退出码、W12 调用时序或其他 Slice 语义。
- Slice 6 implementation 已解除 plan-review 阻塞，可在 v4.8 accepted plan commit
  后实施。
- 当前无未分类技术 residual，open High/Medium/Low=0/0/0。
- 未修改 production、tests、README 或外部 review artifact；未执行 stage、commit、
  push。
