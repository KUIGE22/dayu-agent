# Code Re-Review — Slice 0.1 Round2 Final Corrective

## Scope

- Mode: current changes（Slice 0.1 round2 最终独立 corrective re-review，只读）
- Branch: `codex/investment-platform`
- Base: `884a3e4`
- Output file: `docs/reviews/code-rereview-20260810-085202-slice-0.1-mimo-native.md`
- Source reviews: `code-review-20260810-075628-slice-0.1-mimo-native.md`、`code-review-20260810-075628-slice-0.1-terra.md`
- Rereviews: `code-rereview-20260810-083133-slice-0.1-mimo-native.md`、`code-rereview-20260810-083133-slice-0.1-terra.md`
- Adjudication: `slice-0.1-investment-domain-skeleton-adjudication-20260810-080206-codex.md`（含 Round2 节）
- Round1 fix: `slice-0.1-investment-domain-skeleton-review-fix-20260810-080206-deepseek.md`
- Round2 fix: `slice-0.1-investment-domain-skeleton-review-fix-round2-20260810-084327-deepseek.md`
- Included scope: `dayu/investment/` 生产代码、`tests/investment/` 测试、`dayu/README.md`（§3.9）、`tests/README.md`（investment 节）、`dayu/investment/README.md`
- Excluded scope: 未修改的既有 production 模块、implementation artifact、既往 review source
- Parallel review coverage: 无，主 reviewer 独立完成全部走读
- Review clock: 2026-08-10 08:52:02 +0800

## Terra 083133 专项验证

### 1. TenantScope 私有 singleton 路径防御性拒绝 raw str

**验证目标**: Terra rereview F1 要求 `TenantScope.__init__` 即使携带模块内部真实单例 `_TENANT_SCOPE_TOKEN`，也必须防御性要求 `tenant_id` 是 `TenantId` 实例，raw str fail closed。

**直接证据**:

`dayu/investment/domain/identifiers.py:282-306`：

```python
def __init__(self, tenant_id: TenantId, _token: _TenantScopeToken | None = None) -> None:
    if _token is not _TENANT_SCOPE_TOKEN:
        raise TypeError("TenantScope 禁止公开构造，只能通过 Principal.to_scope() 创建")
    if not isinstance(tenant_id, TenantId):
        raise TypeError("租户标识必须是 TenantId 实例，禁止使用原始字符串")
    super(TenantScope, self).__setattr__("tenant_id", tenant_id)
```

两层独立守卫：
- 第 302 行：对象身份校验 `_token is _TENANT_SCOPE_TOKEN`（公开 API misuse guard）
- 第 304 行：`isinstance(tenant_id, TenantId)` 类型防御（即使第一层通过，raw str 仍被拒）

**测试覆盖**:

| 测试 | 位置 | 验证内容 |
| --- | --- | --- |
| `test_tenant_scope_direct_construction_rejected` | line 559-573 | 无 token → `TypeError` |
| `test_tenant_scope_rejects_forged_sentinel` | line 598-617 | 伪造新 `_TenantScopeToken()` 实例 → `TypeError` |
| `test_tenant_scope_rejects_raw_string_tenant_even_with_real_sentinel` | line 620-640 | 真实单例 + raw str `replace(scope, tenant_id="raw", _token=_TENANT_SCOPE_TOKEN)` → `TypeError` |
| `test_tenant_scope_accepts_real_sentinel_with_valid_identifier` | line 643-660 | 真实单例 + 合法 `TenantId` → 正常构造 |
| `test_tenant_scope_is_immutable_after_creation` | line 576-595 | `setattr` 改写 → `AttributeError` |

**结论**: PASS — raw str 在第二层被 `isinstance` 拒绝；公开 API 所有路径均 fail closed；类型和值边界完整。

### 2. 文档诚实性：token 仅 API misuse guard

**验证目标**: 所有文档不得把 `_TENANT_SCOPE_TOKEN` 描述为认证/provenance/安全能力；认证唯一 Principal producer 与 repository/RLS 属于相应后续边界。

**逐文件验证**:

| 文件 | 位置 | 内容 | 判定 |
| --- | --- | --- | --- |
| `dayu/investment/domain/identifiers.py` 模块 docstring | line 15-17 | "模块私有哨兵仅是公开 API misuse guard，不是认证能力；真正的 Principal 唯一 producer 与 repository/RLS 的租户边界实施属于对应后续授权 slice" | 诚实 |
| `_TenantScopeToken` 类 docstring | line 257-260 | "本哨兵仅是公开 API misuse guard，不是认证能力...不能证明唯一生产者或认证 provenance" | 诚实 |
| `TenantScope.__init__` docstring | line 288 | "哨兵仅是公开 API misuse guard，不是认证能力" | 诚实 |
| `_make_tenant_scope` docstring | line 310 | "模块私有，仅 Principal.to_scope 调用" | 准确（描述当前调用关系） |
| `Principal` 类 docstring | line 212-213 | "本模块不实现认证：Principal 当前是公开构造器，认证层作为 Principal 的唯一 producer 属于后续授权 slice" | 诚实 |
| `dayu/investment/README.md` 2.1 节 | line 41-44 | "模块私有哨兵仅是公开 API misuse guard，不是认证能力" | 诚实 |
| `tests/investment/test_architecture_boundaries.py` | line 625-626 | "该哨兵只是公开 API misuse guard，不是认证能力" | 诚实 |

**结论**: PASS — 全部文档一致且准确地声明哨兵仅为 API misuse guard，明确区分当前机制与后续认证/RLS 边界。未把 Python 私有名伪装成 security capability。

### 3. README 反向 import guard 范围

**验证目标**: README 反向 import guard 描述必须精确匹配 `_iter_investment_files()` 实际只扫描 `dayu/investment` 包内文件的范围。

**直接证据**:

- `dayu/investment/README.md:21-24`："依赖方向由 `tests/investment/test_architecture_boundaries.py` 的 AST guard 守护：它只枚举 `dayu.investment` 包内的 Python 文件，断言这些文件不导入上层包；它不扫描 `dayu.investment` 以外的模块，因此不构成对跨包反向 import 的检查。"
- `tests/investment/test_architecture_boundaries.py:64-65`：`_INVESTMENT_SRC = _REPO_ROOT / "dayu" / "investment"`
- `tests/investment/test_architecture_boundaries.py:91-104`：`_iter_investment_files()` 只从 `_INVESTMENT_SRC` 收集 `.py` 文件

**结论**: PASS — README 准确声明了 guard 只扫描 `dayu/investment` 包内文件、不构成跨包反向 import 检查。

### 4. Slice 0.1 不实现认证/RLS

**验证目标**: 不得要求在 Slice 0.1 实现认证/RLS。

- `dayu/investment/README.md` 无任何认证、RLS、授权相关实现声明
- `identifiers.py` 模块 docstring 明确认证/RLS 属于后续 slice
- `Principal` 当前为公开构造器，docstring 声明认证属于后续 slice
- `dayu/investment/README.md:55`："当前模块不实现账本分录或费用分摊规则"

**结论**: PASS — Slice 0.1 严格限于 domain 骨架，认证/RLS 明确 deferred。

## Regression Verification

| Item | Status | Evidence |
| --- | --- | --- |
| Tests | PASS | `110 passed, 0 failed`（round1 108 + round2 新增 2） |
| Pyright (investment) | PASS | `0 errors, 0 warnings, 0 informations` |
| Pyright (全仓) | PASS | 17 个既有错误，位于 `docling_processor.py` + engine tests，与基线一致，无新增无扩散 |
| Ruff (investment) | PASS | All checks passed |
| Coverage | PASS | 100%（4 production modules: 137 stmts, 0 missed） |
| git diff --check | PASS | 无 whitespace 错误 |

## Detailed Findings

### 直接构造/forged/frozen 验证

- `TenantId("  bad  ")` → `ValueError`（line 418-419）
- `TenantId("t-1")` → 正常构造（值对象，frozen slots）
- 五个标识 `is not` 互斥（line 441-444）
- `TenantScope(tenant_id=TenantId("other-tenant"))` → `TypeError`（line 572-573）
- `_TenantScopeToken()` 新实例 → `TypeError`（line 615-617）
- `setattr(scope, ...)` → `AttributeError`（line 594-595）

### semantic-naive UTC 验证

- `_is_aware_utc_offset` 检查 `tzinfo is not None and utcoffset() is not None`（`money.py:274`）
- `to_utc_iso(datetime(2026, 8, 10, tzinfo=NoOffsetTimezone()))` → `ValueError`（line 1137-1139）
- `parse_utc("2026-08-10T07:46:02")` → `ValueError`（line 1085-1086）
- `parse_utc("2026-08-10T15:46:02+08:00")` → 正确 UTC（line 1066-1068）

### Escape pattern 验证

- 测试文件：无 `Any`/`object`/`cast`/`getattr`/`hasattr` 调用（工厂签名 `Callable[[str], TenantId | CompanyId | SecurityId | PortfolioId | AccountId]`，line 67）
- 唯一 `# type: ignore` 出现在 line 178 的检测逻辑字符串字面量中，非实际 ignore 注释
- 生产代码 AST guard 通过（line 317-321）

### Docstring 验证

- 所有生产模块/类/函数均含中文 docstring（AST guard line 324-341 通过）
- 所有测试函数/helper 均含完整 Args/Returns/Raises docstring
- `_NoOffsetTimezone` 类及三个方法（line 227-277）均有完整 docstring

### `__all__` 一致性

- `identifiers.py`（12）、`money.py`（5）、`domain/__init__.py`（17）、`investment/__init__.py`（17）
- union 等于全集，测试 `test_all_exports_resolve_to_attributes`（line 1165-1180）验证每个符号可解析

## Findings

未发现实质性问题。

## Open Questions

- 无

## Residual Risk

- `TenantScope` 哨兵不能阻止同一进程内解析真实单例的调用方；这是本 slice 已明确的设计边界——哨兵仅约束公开 API 误用，跨租户数据访问的最终防线是后续 repository/RLS enforcement 与认证层（唯一 producer）。
- `parse_utc` 的 `utcoffset() is None` 分支对字符串输入不可达（`fromisoformat` 只能产生带偏移或 naive 输入），与 `to_utc_iso` 共享守卫是合理设计。
- 测试未覆盖 `Money`/`Quantity` 运算右操作数的非本类型输入；受"禁止 `object`/`Any`/`cast`/`type: ignore`/无类型签名"约束，以 `dataclasses.replace` 注入覆盖构造期类型校验，运算路径类型错误在静态层即被 pyright 拒绝。

## Conclusion

**PASS** — open findings: **高 0 / 中 0 / 低 0**

Terra 083133 两项均已正确关闭：

1. **TenantScope raw str 防御**: `__init__` 两层独立守卫（哨兵身份 + `isinstance(tenant_id, TenantId)`）均正常工作；补测 `test_tenant_scope_rejects_raw_string_tenant_even_with_real_sentinel` 精确证明即使携带真实单例，raw str 仍被 `TenantId` 类型检查拒绝。
2. **文档诚实性**: 全部文档一致声明哨兵为 API misuse guard，非认证能力；认证唯一 producer 与 repository/RLS 明确属于后续 slice。
3. **README 反向 guard 范围**: 精确匹配 `_iter_investment_files()` 只扫描 `dayu/investment` 包内文件的实际范围。
4. **不把 Python 私有名误判为 auth**: 所有相关声明已清理，未发现误判。
5. **不要求 Slice 0.1 实现认证/RLS**: 认证/RLS 明确 deferred。

所有 prior findings（Terra F-01 through F-04 / MiM M-01）均已正确解决。回归验证全部通过（110 tests, 100% coverage, pyright 0 errors, ruff clean）。无新增 findings。无 regressions。
