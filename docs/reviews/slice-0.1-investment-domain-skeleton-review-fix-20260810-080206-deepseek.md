# Slice 0.1 Investment domain skeleton review fix

- Status：**CLOSED / DUAL RE-REVIEW PASS**（round1；round2 corrective fix 见
  `slice-0.1-investment-domain-skeleton-review-fix-round2-20260810-084327-deepseek.md`）
- Adjudication：`docs/reviews/slice-0.1-investment-domain-skeleton-adjudication-20260810-080206-codex.md`
- Source reviews：`code-review-20260810-075628-slice-0.1-terra.md`、`code-review-20260810-075628-slice-0.1-mimo-native.md`
- Implementation artifact：`slice-0.1-investment-domain-skeleton-implementation-20260810-074602-deepseek.md`（状态已同步更新）
- No commit / push / PR；无网络 / live / model / broker / PG / Redis / MinIO 动作

## Fix dispositions

| Finding | Disposition | Applied fix |
| --- | --- | --- |
| Terra F-01 / MiM M-01 identifier and scope bypass（HIGH） | ACCEPTED | 五个标识由 `NewType` 改为 frozen slots 运行时值对象（共享 `_Identifier` 不可变基类），直接构造与 `make_*` 工厂执行同一 `_validate_identifier` 严格校验；`TenantScope` 改为“禁止公开构造 + 创建后不可变”类型：frozen slots dataclass（`init=False`）承载 `tenant_id` 字段，`__init__` 要求模块私有 `_TenantScopeToken` 哨兵（未携带即抛 `TypeError`），构造经 `super().__setattr__` 落值，frozen 只读 `__setattr__` 拒绝创建后的任何属性改写；唯一创建路径是模块私有 `_make_tenant_scope`，仅被 `Principal.to_scope()` 调用。 |
| Terra F-01 Controller 收口（不可变边界，不可 defer） | ACCEPTED | `TenantScope` 创建后不可变：新增 `test_tenant_scope_is_immutable_after_creation`（`setattr` 改写 `tenant_id` 抛 `AttributeError`）；本 artifact 中对应 residual 已删除。 |
| Terra F-01 Controller 终收口（哨兵单例身份校验，不可 defer） | ACCEPTED | 哨兵改为模块私有单例 `_TENANT_SCOPE_TOKEN`，`__init__` 以对象身份（`is`）校验 `_token is _TENANT_SCOPE_TOKEN`；任意非单例值（含模块内伪造的新 `_TenantScopeToken()` 实例）一律拒绝；新增 `test_tenant_scope_rejects_forged_sentinel` 验证伪造实例 runtime 拒绝（不使用 `object`/`cast`/ignore）。 |
| Terra F-02 semantic-naive timezone（HIGH） | ACCEPTED | 抽出共享守卫 `_is_aware_utc_offset`，`parse_utc` / `to_utc_iso` 同时检查 `tzinfo is None or utcoffset() is None`；新增 custom tzinfo（`utcoffset` 恒 `None`）语义 naive 反例。 |
| Terra F-03 test type escapes / docstrings（LOW） | ACCEPTED-IN-PART | 测试文件移除 `object`（工厂签名改精确 union `Callable[[str], TenantId | CompanyId | SecurityId | PortfolioId | AccountId]`；非法金额/数量/货币经 `dataclasses.replace` 注入运行时非法值）、三个 `# type: ignore[arg-type]`、`getattr`（改显式 AST `isinstance` 分支）、`hasattr`（改 `vars(package)` 成员判定）；全部测试函数与 helper 补完整中文 Args/Returns/Raises docstring；守护声明与扫描范围（仅 `dayu.investment` 生产代码）保持一致。 |
| Terra F-04 README future claims（LOW） | ACCEPTED | `dayu/investment/README.md` 删除 storage/connectors future modules、未来 guard 范围承诺与“后续 slice 补充”叙述，只写当前 domain 骨架、当前 AST guard 实际范围与开发命令；`dayu/investment/__init__.py` 包 docstring 同步删除 future slice 表述；`tests/README.md` 描述更新为新行为。 |

## 关键设计说明

- 标识值对象：`value: str` 字段 + 构造期校验 + `__str__` 返回原始字符串；
  同值同类型相等、跨类型不等；`slots=True` 阻止动态添加属性。
- `Principal.__post_init__` 增加 `isinstance(tenant_id, TenantId)` 类型边界
  （原始字符串租户输入抛 `TypeError`），`user_id` 维持字符串校验。
- “原始字符串直构 `TenantScope`”在静态层即被 pyright 拒绝（`tenant_id:
  TenantId` 参数），运行时未携带单例哨兵也一律抛 `TypeError`；受控创建链
  （`Principal -> _make_tenant_scope -> 单例哨兵身份校验 __init__`）的非法
  租户输入由 `TenantId` 构造校验先行拦截。
- `TenantScope` 创建后不可变：frozen dataclass 生成只读 `__setattr__`
  （`FrozenInstanceError`，`AttributeError` 子类），构造期内用
  `super().__setattr__` 落值；生产代码不出现 `object` 名称逃逸。
- 哨兵为模块私有单例 `_TENANT_SCOPE_TOKEN`，`__init__` 以对象身份
  （`is`）校验；伪造新实例或任意非单例值均无法绕过受控构造。
- `parse_utc` 的输入是字符串，`fromisoformat` 无法携带 custom tzinfo；
  语义 naive 拒绝逻辑与 `to_utc_iso` 共用同一 `_is_aware_utc_offset`
  守卫，custom-tzinfo 反例经 `to_utc_iso` 公开路径验证。

## Validation evidence（`/Users/wsk/workspace/dayu-agent`、激活 `.venv`）

| Command | Exit | Evidence |
|---|---:|---|
| `python -m pytest tests/investment -q` | 0 | `108 passed` |
| `python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing` | 0 | `__init__.py 100%`、`domain/__init__.py 100%`、`domain/identifiers.py 100%`（66 stmts）、`domain/money.py 100%`（64 stmts），单文件 coverage 全部 >= 80% |
| `pyright dayu/investment tests/investment` | 0 | `0 errors, 0 warnings, 0 informations` |
| `pyright`（全仓） | 0（既有 17 errors） | 17 errors 全部位于既有 `docling_processor.py` + engine tests，与基线一致，无新增无扩散 |
| `ruff check --select E4,E7,E9,F,I dayu/investment tests/investment` | 0 | all checks passed |
| `ruff check dayu/investment tests/investment`（默认全规则） | 0 | all checks passed |
| `git diff --check` | 0 | 无 whitespace 错误 |
| allowlist audit | 0 | 变更仅限 Slice 0.1 allowlist + implementation/review artifacts，见下 |

## Allowlist 与 scope audit

- 变更文件：`dayu/investment/domain/identifiers.py`、`dayu/investment/domain/money.py`、
  `dayu/investment/__init__.py`、`dayu/investment/README.md`、
  `tests/investment/test_architecture_boundaries.py`、`tests/README.md`、`dayu/README.md`（本轮未改动）。
- 本轮更新 artifact：implementation artifact（状态/设计要点/验证数字）、本 review-fix artifact。
- 未修改 accepted plan、allowlist 外代码、既有 review source 文件。
- `dayu/investment` 生产代码仍无 `Any` / `object` / `cast` / `type: ignore` /
  `getattr` / `hasattr` / `noqa` 逃逸（AST guard 断言通过）。

## Residual risks

- `parse_utc` 的 `utcoffset() is None` 分支对字符串输入不可达（`fromisoformat`
  只能产生带偏移或 naive 输入），该拒绝逻辑与 `to_utc_iso` 共享守卫并已有
  语义 naive 反例覆盖。
- 测试未覆盖 `Money` / `Quantity` 运算右操作数的非本类型输入；受“禁止
  `object`/`Any`/`cast`/`type: ignore`/无类型签名”约束，以 `dataclasses.replace`
  注入覆盖构造期类型校验，运算路径类型错误在静态层即被 pyright 拒绝。

## Handoff

Terra F-01–F-04 与 MiM M-01 均已按 adjudication 处置并关闭。round2 的
Terra `083133` 两项由 `085600` Terra 与 `085202` MiM 独立复审确认关闭，
两路均 PASS、open H/M/L = `0/0/0`。当前状态为
**CLOSED / DUAL RE-REVIEW PASS**；accepted commit 仅由 Controller 创建。
implementation worker 未 commit / push / 创建 PR，也未进入 Slice 0.2。
