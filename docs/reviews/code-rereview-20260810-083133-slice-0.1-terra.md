# Code Review

## Scope

- Mode: current changes（Slice 0.1 corrective re-review，只读）
- Branch or PR: `codex/investment-platform`
- Base: `884a3e4`
- Review clock: `2026-08-10 08:35:59 +0800`
- Output file: `docs/reviews/code-rereview-20260810-083133-slice-0.1-terra.md`
- Included scope: `dayu/investment/**`、`tests/investment/**`、`dayu/investment/README.md`、本次同步修改的 `dayu/README.md` 与 `tests/README.md`；两份 `20260810-075628` source reviews、`20260810-080206` Controller adjudication，以及 DeepSeek review-fix artifact。
- Excluded scope: 未修改的既有生产模块；尚未进入本 slice 的认证生产者、repository/RLS 与外部集成。全仓 pyright 的 17 个既有错误不在本次变更路径。
- Parallel review coverage: 无；主 reviewer 走读所有当前 investment 生产文件、完整测试文件及相关 README。

## Findings

### 1-未修复-中-TenantScope 的私有单例哨兵不能证明唯一 Principal 路径，且仍可把原始租户值写入 scope
- **入口/函数**: `TenantScope.__init__()`。
- **文件(行号)**: `dayu/investment/domain/identifiers.py:247-313`。
- **输入场景**: 同一 Python 进程内的调用方导入模块私有 `_TENANT_SCOPE_TOKEN`，执行 `TenantScope("raw-tenant", _token=_TENANT_SCOPE_TOKEN)`。
- **实际分支**: 296 行的身份判断通过；297 行直接将未作类型或值校验的 `tenant_id` 写入 frozen 实例。
- **预期行为**: Controller 对 Terra F-01 / MiM M-01 的收口要求是 `TenantScope` 仅由已校验 `Principal` 的受控路径产生，原始 tenant 输入不能形成 scope；同时本 slice 不应把 Python 的模块私有约定误称为认证或安全能力。
- **实际行为**: 本次复现得到 `TenantScope(tenant_id='raw-tenant')`。公开直构、错误 token 与新建的伪造 token 均正确抛出 `TypeError`，但模块下划线不阻止同进程导入真实单例；因此身份哨兵只能约束遵守模块边界的调用方，不能证明唯一生产者或认证 provenance。模块 docstring 247-253 行“公开调用方无法获得该单例”“无法绕过认证”的表述也不成立；`Principal` 目前仍是公开构造器，认证层的唯一 producer 尚未实现。
- **直接证据**: `_TENANT_SCOPE_TOKEN` 是模块级可解析属性（259 行），`TenantScope.__init__` 只检查 `_token is _TENANT_SCOPE_TOKEN`（295-297 行），且没有 `isinstance(tenant_id, TenantId)` 或 `_validate_identifier()`。复现命令在本次审查中实际输出 `private-singleton-with-raw OK TenantScope(tenant_id='raw-tenant')`；现有测试只覆盖无 token（572-573 行）与新 `_TenantScopeToken()`（615-617 行），没有覆盖真实单例被导入后的路径。
- **影响**: 当前尚无 repository/RLS 消费 scope，故不能据此声称已发生跨租户数据访问；但当前公开 domain 契约已经把可包含原始字符串的对象命名为租户边界。若后续 repository/RLS 把它当作已认证 provenance，调用方可选择 tenant，正是 Controller 明确禁止依赖调用方自律的路径。
- **建议改法和验证点**: 本 slice 应将哨兵准确限定为模块内部的构造组织机制，删除“无法获得”“认证”“唯一/安全边界”等不成立的声明；`TenantScope` 或私有工厂仍应防御性验证 `TenantId`，使被错误传入的原始字符串 fail closed。认证层落地后，由真实认证边界作为 `Principal` 的唯一 producer，并由 repository/RLS 独立实施 tenant enforcement；不要试图把 Python 私有名或 frozen 实现升级为安全认证。验证应分别断言公开 API 拒绝、私有辅助路径的类型防御，以及后续 Service/auth 到 repository/RLS 的授权闭环。
- **修复风险（低/中/高）**: 中（需要重新界定当前 domain 构造约束与后续认证/存储安全边界，不能以更隐蔽的 token 替代认证）。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-低-investment README 仍包含未来 slice 叙述，并声称不存在的反向依赖 guard
- **入口/函数**: `dayu/investment/README.md` 的依赖方向与模块 owner 说明。
- **文件(行号)**: `dayu/investment/README.md:21-23, 53`；`tests/investment/test_architecture_boundaries.py:91-104, 123-151, 284-301`。
- **输入场景**: 开发者依据 package README 判断当前 guard 的覆盖范围或当前已实现的职责边界。
- **实际分支**: `_iter_investment_files()` 只枚举 `dayu/investment/**/*.py`；依赖断言只分析这些文件的 import，无法检查 `dayu.investment` 以外的模块是否导入 investment domain。
- **预期行为**: Terra F-04 的 accepted closure 要求 README 只描述当前 Slice 0.1 实现与实际 guard 范围，不写未来 slice 承诺或把未实施的保障表示为当前事实。
- **实际行为**: README 21-23 行称“investment 以外的模块不得反向 import investment domain（由该 AST guard 守护）”，与实际扫描范围不符；53 行仍以“属于后续 slice”描述未实现业务。
- **直接证据**: 测试扫描根常量为 `_INVESTMENT_SRC = .../dayu/investment`（64-65 行），且 284-301 行只遍历该根；README 的两处表述如上。
- **影响**: 文档把未被当前测试守护的跨包依赖约束和未来实现计划呈现为当前事实，违反 README current-only 约束；不影响当前值对象运行行为。
- **建议改法和验证点**: 删除或改写反向 import 的 guard 归属，只陈述当前测试实际检查的 investment 内向依赖；将 53 行改成当前实现事实（例如“不实现账本分录或费用分摊”），不引用后续 slice。修改后以 README 与 AST 扫描根逐项对照。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。认证层成为 `Principal` 唯一 producer 是后续 slice 的明确边界；本 finding 不将其尚未落地本身视为本 slice 缺陷，只要求当前实现与文档不把私有命名约定误表述为已经完成的认证保证。

## Residual Risk

- Terra F-02 已关闭：`_is_aware_utc_offset()` 同时检查 `tzinfo` 与 `utcoffset()`（`money.py:256-274`）；custom `tzinfo` 返回 `None` 的 `to_utc_iso()` 负例（测试 1081-1096 行）通过，未发生本机时区换算。
- Terra F-03 已关闭：完整测试文件未见实际 `object` / `Any` / `cast` / `type: ignore` / `getattr` / `hasattr` 逃逸；所有函数 docstring 均含 Args/Returns/Raises。AST guard 的扫描范围已在 README 70-73 行正确说明为 production `dayu.investment`。
- 标识运行时严格性已关闭：五个 frozen slots 标识直接构造与工厂均走 `_Identifier.__post_init__()` 的字符串校验（`identifiers.py:45-199`），相关 direct-construction 负例通过；`Principal.__post_init__()` 对 raw `tenant_id` 执行 `isinstance(TenantId)` 拒绝（227-229 行）。
- 公开 TenantScope 行为与 frozen 不变性已验证：无 token、错误 token、非单例 token 均拒绝，`setattr` 修改派生 scope 抛 `FrozenInstanceError`；这些结论不等价于认证或不可伪造 capability。
- 验证：`python -m pytest -p no:cacheprovider tests/investment -q` 为 108 passed；逐模块 coverage 均为 100%；`pyright dayu/investment tests/investment` 为 0 errors；`ruff check dayu/investment tests/investment` 与 `git diff --check` 通过。全仓 `pyright` 仍有 17 个既有错误，位于 `dayu/engine/processors/docling_processor.py` 与既有 engine tests，未扩散至本 slice。

Review conclusion: **FAIL**；open findings：**高 0 / 中 1 / 低 1**。
