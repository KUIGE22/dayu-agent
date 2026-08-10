# Slice 0.1 Investment Domain Skeleton Implementation

- Work unit：`investment-platform-restoration`
- Slice：`0.1 — Investment domain skeleton 与 dependency guard`
- Predecessor accepted commit：`884a3e4`
- Branch：`codex/investment-platform`
- Implementer：DeepSeek Flash implementation worker
- Status：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- Review fix：`docs/reviews/slice-0.1-investment-domain-skeleton-review-fix-20260810-080206-deepseek.md`（round1 修复详情与验证证据见该 artifact）
- Round2 corrective fix：`docs/reviews/slice-0.1-investment-domain-skeleton-review-fix-round2-20260810-084327-deepseek.md`（Terra re-review F1/F2 的修复详情见该 artifact）

## Scope

本 slice 只建立 pure domain 骨架与依赖方向守护测试，不实现任何业务行为，
不触碰既有模块。`dayu.investment` 从零创建（greenfield），与计划 §4.2
“完全不存在，因此是明确的 greenfield package”一致。

无 SQLAlchemy / FastAPI / Host / Web / Agent 依赖；无 `Any` / `object` /
`cast` / `type: ignore` / `getattr` / `hasattr` 逃逸；无 schema、migration、
composition、repository、connector 或任何持久化/外部动作。

## Changed Files（全部在 allowlist 内）

1. `dayu/investment/__init__.py` — 包导出层
2. `dayu/investment/domain/__init__.py` — domain 子包导出层
3. `dayu/investment/domain/identifiers.py` — 强标识、`Principal`、`TenantScope`
4. `dayu/investment/domain/money.py` — `Money`、`Quantity`、UTC 时间工具
5. `dayu/investment/README.md` — 投资域开发手册（新）
6. `tests/investment/test_architecture_boundaries.py` — AST 守护 + 严格反例
7. `dayu/README.md` — 相关文档链接、§3.9 investment 定位、§11 阅读顺序
8. `tests/README.md` — 目录分层新增 `tests/investment/` 说明

## 设计要点

- 五个标识均为 frozen slots 运行时值对象，直接构造与 `make_*` 工厂
  执行同样的严格校验，拒绝空值/仅空白/首尾空白（fail closed）。
- `Principal` 构造期校验租户/用户标识；`TenantScope` 禁止公开直接
  构造（`__init__` 以对象身份校验模块私有单例哨兵
  `_TENANT_SCOPE_TOKEN`，并防御性校验 `tenant_id` 必须是 `TenantId`
  实例，原始字符串即使携带真实单例也 fail closed），只能由
  `Principal.to_scope()` 经模块私有工厂派生，创建后不可变（frozen
  dataclass 只读 `__setattr__`），禁止调用链猜测租户；哨兵仅是公开
  API misuse guard，不是认证能力，`Principal` 唯一 producer 与
  repository/RLS enforcement 属于后续授权 slice。
- `Money` / `Quantity` 必须为有限非负 `Decimal`；`float` / `bool` /
  `int` / `str` 输入抛 `TypeError`，`NaN` / `Infinity` / 负数抛
  `ValueError`；货币代码限定三位大写字母（ISO 4217 形态，结构化校验，
  非封闭白名单）。金额加减/比较要求两侧货币相同，subtract 结果为负
  fail closed。
- 值对象提供最小算术（同货币 `add` / `subtract`、`__lt__`），属于
  值对象语义而非业务行为；账本分录、费用分摊等业务规则留给后续 slice。
- UTC 时间工具 `utc_now` / `parse_utc` / `to_utc_iso` 统一 UTC；
  `tzinfo` 为 `None` 或 `utcoffset()` 为 `None`（含语义 naive）的输入
  一律拒绝，不依赖本机时区。
- 所有模块/类/函数（含 `__post_init__` 与测试 helper）携带完整中文
  docstring，且包含 Args/Returns/Raises 三节。
- 显式 `__all__` 于四个 production 模块与两个 `__init__.py`。

### 决策说明

- **UTC helpers 归置 `money.py`**：Slice 0.1 allowlist 只有
  `identifiers.py` 与 `money.py` 两个 domain 模块，无独立 `time.py`
  位置。`identifiers.py` 承载身份/租户语义，与时间工具无关；故将
  UTC 时间工具归入承载“金额/数量”值类型的 `money.py`，模块 docstring
  明确其承载三类核心值（金额、数量、UTC 时间工具）。如 review 认为
  应另立模块，需放宽 allowlist。
- **`Money` / `Quantity` 恒 non-negative**：按计划 §6.2“金额使用
  Decimal + currency”与 Slice 0.1 “Decimal finite/non-negative rules”
  的字面要求执行；未来若出现负现金（margin）等业务需要，属于后续
  slice 的显式演进，不在本 slice 发明例外。
- **无 `UserId` newtype**：计划 Types 行只列五个标识，`Principal.user_id`
  使用 `str`，不发明计划外类型。

## Validation（全部在 `/Users/wsk/workspace/dayu-agent`、激活 `.venv` 后执行）

1. `python -m pytest tests/investment -q`
   - Exit：`0`
   - Result：`110 passed`（round2 新增真实单例 + 原始字符串租户防御
     反例与对照用例）
2. `python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing`
   - Exit：`0`
   - Result：逐 production module statement coverage：
     `dayu/investment/__init__.py 100%`、`domain/__init__.py 100%`、
     `domain/identifiers.py 100%`（68 stmts）、`domain/money.py 100%`
     （64 stmts），全部 >= 80%
3. `pyright dayu/investment tests/investment`
   - Exit：`0`
   - Result：`0 errors, 0 warnings, 0 informations`
4. `pyright`（全仓）
   - Exit：`0`（既有 17 errors）
   - Result：`17 errors, 0 warnings`，与基线 `884a3e4` 一致，无新增无扩散
5. `ruff check --select E4,E7,E9,F,I dayu/investment tests/investment`
   - Exit：`0`
   - Result：`All checks passed!`
6. `ruff check dayu/investment tests/investment`（默认全规则）
   - Exit：`0`
   - Result：`All checks passed!`
7. `git diff --check`
   - Exit：`0`，无 whitespace 错误
8. Final newline audit（全部新增/修改文件）
   - 结果：全部文件以换行结尾

## README 职责

- `dayu/investment/README.md`（新）：按计划 §9 文档职责维护依赖方向、
  模块 owner 与开发命令；当前无 schema/migration/composition，按
  AGENTS.md“以代码为准，不写未来设计”原则留待后续 slice 补充。
- `dayu/README.md`：仅追加相关文档链接、§3.9 investment 定位小节与
  §11 阅读顺序；未重复包文档内容。
- `tests/README.md`：仅追加目录分层说明；未越界。

## 未执行的外部动作

- 未 commit / push / 创建 PR（按分工，accepted commit 由 Controller 处理）。
- 未运行 network / live / model / broker，未启动 PostgreSQL / Redis /
  MinIO，未触碰 workspace 数据。
- 未修改既有模块、依赖文件或 schema。

## Residual Risks 与下一入口

| 风险 | 说明 | 下一入口 |
| --- | --- | --- |
| UTC helpers 归置 `money.py` 语义不纯 | 受 allowlist 约束；若 review 要求独立 `domain/time.py`，需 Controller 放宽 allowlist | code review / 后续 slice |
| `Money` / `Quantity` 恒非负可能不满足未来 margin 场景 | 当前按计划字面要求执行；负值语义需在组合账本 slice（5.1）显式演进 | Slice 5.1 |
| 反向 import 依赖 | 当前 AST guard 扫描 `dayu.investment` 自身；未来上层 slice 出现后需扩展 guard 覆盖反向方向 | Slice 0.2+ 时评估 |

## Dual re-review closure

- Terra final corrective re-review：
  `docs/reviews/code-rereview-20260810-085600-slice-0.1-terra.md`，
  **PASS**，open H/M/L = `0/0/0`。
- MiM final corrective re-review：
  `docs/reviews/code-rereview-20260810-085202-slice-0.1-mimo-native.md`，
  **PASS**，open H/M/L = `0/0/0`。
- Terra 083133 的 TenantScope raw-string 防御与 README/安全边界表述两项
  finding 均已关闭；初审 Terra F-01–F-04 与 MiM M-01 全部关闭。
- 最终复审验证为 `110 passed`、四个 production module coverage 100%、
  exact Pyright 0、Ruff 通过、`git diff --check` 通过。
- 本状态仅授权 Controller 创建本地 accepted commit；仍未授权 push、PR、
  网络、模型、broker 或 live 动作。
