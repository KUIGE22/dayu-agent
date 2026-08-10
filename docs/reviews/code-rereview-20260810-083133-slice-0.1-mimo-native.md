# Corrective Code Re-Review

## Scope

- Mode: read-only relative to `884a3e4`
- Branch: `codex/investment-platform`
- Base: `884a3e4`
- Output file: `docs/reviews/code-rereview-20260810-083133-slice-0.1-mimo-native.md`
- Source reviews: `code-review-20260810-075628-slice-0.1-mimo-native.md`、`code-review-20260810-075628-slice-0.1-terra.md`
- Adjudication: `slice-0.1-investment-domain-skeleton-adjudication-20260810-080206-codex.md`
- Review-fix: `slice-0.1-investment-domain-skeleton-review-fix-20260810-080206-deepseek.md`
- Included scope: `dayu/investment/`、`tests/investment/`、`dayu/README.md`（§3.9）、`tests/README.md`（investment 节）
- Excluded scope: 未修改的既有 production 模块、implementation artifact、既往 review source
- Parallel review coverage: 无，主 reviewer 独立完成全部走读
- Validation evidence: 108 passed、pyright 0 errors、ruff clean、coverage 100%（四个 production module）

## Finding Disposition Summary

| Finding | Source | Disposition |
| --- | --- | --- |
| F-01 强 ID runtime 构造 | Terra F-01 / MiM M-01 | **PASS** |
| F-02 Principal 构造边界 | Terra F-01 / MiM M-01 | **PASS** |
| F-03 TenantScope direct construction | Terra F-01 | **PASS** |
| F-04 TenantScope singleton identity | Terra F-01 controller 终收口 | **PASS** |
| F-05 TenantScope immutability | Terra F-01 controller 收口 | **PASS** |
| F-06 UTC semantic-naive | Terra F-02 | **PASS** |
| F-07 Test escape patterns | Terra F-03 | **PASS** |
| F-08 Test docstring completeness | Terra F-03 | **PASS** |
| F-09 README current-only | Terra F-04 | **PASS**（one residual note） |
| F-10 Module-private token vs authentication | Open question | **PASS**（by design） |

## Detailed Findings

### F-01 强 ID runtime 构造 — PASS

**原始 finding**: NewType direct construction 绕过 make_* 校验，强标识运行时无强制。

**修复状态**: 五个标识已从 `NewType` 改为 frozen slots 运行时值对象（`_Identifier` 不可变基类 + `_label` ClassVar）。直接构造 `TenantId("  bad  ")` 与 `make_tenant_id("  bad  ")` 执行同一 `_validate_identifier` 校验。

**验证证据**:
- `TenantId("  bad  ")` → `ValueError`（运行时验证通过）
- `TenantId("t-1")` → 正常构造（值为 `"t-1"`）
- 五个标识 `TenantId` / `CompanyId` / `SecurityId` / `PortfolioId` / `AccountId` 均为 distinct runtime type（`is not` 互斥，test line 441-444）
- 同值相等、跨类型不等（test `test_identifier_value_objects_are_distinct_and_value_semantic`）
- 构造期拒绝 `""` / `"   "` / `" abc"` / `"abc "` / `"\tabc"`（test `test_identifier_direct_construction_rejects_invalid`，parametrized 5 invalid × 5 type = 25 cases）
- `frozen=True, slots=True` 阻止动态属性添加
- `__str__` 返回原始字符串（test line 436）

**结论**: NewType runtime gap 已消除。五个标识的"强"现在是运行时真实的，不仅是静态类型提示。

### F-02 Principal 构造边界 — PASS

**修复状态**: `Principal.__post_init__` 增加 `isinstance(self.tenant_id, TenantId)` 类型边界（line 227-228），原始字符串租户输入抛 `TypeError`；`user_id` 维持 `_validate_identifier` 字符串校验。

**验证证据**:
- `Principal(tenant_id="raw", user_id="u-1")` → `TypeError`（test `test_principal_rejects_raw_string_tenant`，line 554-556，用 `dataclasses.replace` 注入原始字符串）
- `Principal(tenant_id=TenantId(""), user_id="u-1")` → `ValueError`（test `test_principal_rejects_invalid_tenant`）
- `Principal(tenant_id=TenantId("t-1"), user_id="")` → `ValueError`（test `test_principal_rejects_invalid_user`）
- `frozen=True` 保证不可变

**结论**: Principal 构造边界完整，类型与值双重校验。

### F-03 TenantScope direct construction — PASS

**修复状态**: `TenantScope` 改为 `frozen=True, slots=True, init=False` dataclass（line 263）；`__init__` 要求模块私有 `_TenantScopeToken` 哨兵（line 276），未携带即抛 `TypeError`（line 295-296）；`super().__setattr__` 落值（line 297）；唯一创建路径是模块私有 `_make_tenant_scope`（line 300-313），仅被 `Principal.to_scope()` 调用（line 244）。

**验证证据**:
- `TenantScope(tenant_id=TenantId("other-tenant"))` → `TypeError`（test `test_tenant_scope_direct_construction_rejected`，line 572-573）
- `TenantScope(tenant_id=TenantId("other"), _token=None)` → `TypeError`（`__init__` 默认 `_token=None`，line 276）
- `Principal(tenant_id=TenantId("t-1"), user_id="u-1").to_scope()` → 正常工作（test line 480-484）
- `scope.tenant_id == TenantId("t-1")` 成立（line 483）

**结论**: 公开直接构造一律失败，受控路径仅 `Principal.to_scope()`。

### F-04 TenantScope singleton identity — PASS

**修复状态**: 哨兵改为模块私有单例 `_TENANT_SCOPE_TOKEN`（line 259），`__init__` 以对象身份（`is`）校验 `_token is _TENANT_SCOPE_TOKEN`（line 295）。伪造新实例或任意非单例值均被拒绝。

**验证证据**:
- `_TenantScopeToken()` 新实例（非单例）→ `TypeError`（test `test_tenant_scope_rejects_forged_sentinel`，line 615-617）
- 运行时验证：伪造实例 `is not _TENANT_SCOPE_TOKEN`，校验失败

**结论**: 单例身份校验有效，伪造入口不可达。

### F-05 TenantScope immutability — PASS

**修复状态**: `frozen=True` dataclass 生成只读 `__setattr__`（`FrozenInstanceError`，`AttributeError` 子类）；构造期内用 `super().__setattr__` 落值（line 297）。

**验证证据**:
- `setattr(scope, "tenant_id", TenantId("other-tenant"))` → `AttributeError`（test `test_tenant_scope_is_immutable_after_creation`，line 594-595）

**结论**: 创建后不可变，运行时 `__setattr__` 拒绝任何属性改写。

### F-06 UTC semantic-naive — PASS

**修复状态**: 抽出共享守卫 `_is_aware_utc_offset`（line 256-274），同时检查 `tzinfo is not None and utcoffset() is not None`；`parse_utc`（line 292）与 `to_utc_iso`（line 311）均使用该守卫。

**验证证据**:
- `to_utc_iso(datetime(2026, 8, 10, tzinfo=NoOffsetTimezone()))` → `ValueError`（test `test_to_utc_iso_rejects_semantic_naive_datetime`，line 1094-1096）
- `to_utc_iso(naive_datetime)` → `ValueError`（test `test_to_utc_iso_rejects_naive_datetime`，line 1076-1078）
- `parse_utc("2026-08-10T07:46:02")` → `ValueError`（test `test_parse_utc_rejects_naive_or_malformed_input`，line 1042-1043）
- `parse_utc("2026-08-10T15:46:02+08:00")` → 正确转 UTC（test line 1023-1025）
- `_NoOffsetTimezone` 正确继承 `tzinfo`（line 227-277），`utcoffset` 恒返回 `None`

**结论**: 语义 naive 拒绝逻辑完整，custom tzinfo 反例覆盖到位。

**Residual note**: `parse_utc` 的 `utcoffset() is None` 分支对字符串输入不可达（`fromisoformat` 只能产生带偏移或 naive 输入），但与 `to_utc_iso` 共享守卫是合理设计——`_is_aware_utc_offset` 作为单一真相源，消除了两处逻辑漂移风险。

### F-07 Test escape patterns — PASS

**修复状态**: 测试文件移除 `object`（工厂签名改精确 union `Callable[[str], TenantId | CompanyId | SecurityId | PortfolioId | AccountId]`，line 67）、`# type: ignore`（grep 确认唯一匹配是 line 178 的检测逻辑字符串字面量，非实际 ignore 注释）、`getattr`（改显式 AST `isinstance` 分支，line 214-220）、`hasattr`（改 `vars(package)` 成员判定，line 1136-1137）。

**验证证据**:
- AST 扫描测试文件：`ast.Name` 中无 `Any` / `object`；`ast.Call` 中无 `cast` / `getattr` / `hasattr`（line 85-86 定义的 `_ESCAPE_NAME_IDS` / `_ESCAPE_CALL_NAMES` 在测试文件中无匹配）
- `grep` 确认测试文件中唯一 `# type: ignore` 出现在 line 178 的检测逻辑字符串中（`if "# type: ignore" in line:`），非实际 type ignore 注释
- 非法金额/数量/货币通过 `dataclasses.replace` 注入运行时非法值（line 667, 723, 889, 904），而非 `object` 类型逃逸

**结论**: 测试文件自身无逃逸违规，与守护声明一致。

### F-08 Test docstring completeness — PASS

**验证证据**: 所有测试函数与 helper 均携带完整中文 Args/Returns/Raises docstring（line 284-1137，逐函数验证通过）。`_NoOffsetTimezone` 及其三个方法（`utcoffset` / `dst` / `tzname`）也有完整 docstring（line 227-277）。

**结论**: 测试文件 docstring 契约完整。

### F-09 README current-only — PASS（one residual note）

**修复状态**: `dayu/investment/README.md` 已删除 storage/connectors future modules、未来 guard 范围承诺与"后续 slice 补充"叙述。当前只写 domain 骨架、当前 AST guard 实际范围与开发命令。

**验证证据**:
- README 无"后续 slice 补充"、无"storage/connectors"、无未实现 guard 承诺
- Line 53 "本模块只提供值对象语义；账本分录、费用分摊等业务规则属于后续 slice。" — 这是**当前模块边界声明**（what this module does NOT do），不是 future design 承诺。等价于"本模块只做 X，不做 Y"，描述当前职责范围。
- `dayu/investment/__init__.py` 包 docstring 无 future slice 表述
- `dayu/README.md` §3.9 正确添加 investment 架构定位与代码阅读顺序链接
- `tests/README.md` 正确描述 investment 测试目录

**结论**: README 当前只描述已落地内容，符合 root AGENTS.md 约束。

### F-10 Module-private token vs authentication — PASS（by design）

**设计说明**: `_TENANT_SCOPE_TOKEN` 是模块私有哨兵，不是认证本身。`TenantScope` 的公开 API 已 fail closed（无哨兵即 `TypeError`）。认证层作为 `Principal` 的唯一 producer 属于后续 slice 的职责，当前 domain 层不承担认证职责——这符合 `dayu/investment/README.md:8-12` 描述的"纯领域包"定位。

**验证证据**:
- 公开 API 中无任何路径可构造 `TenantScope`（无哨兵 → `TypeError`）
- `_make_tenant_scope` 是模块私有函数（以下划线开头，不在 `__all__` 中）
- `_TenantScopeToken` 类和 `_TENANT_SCOPE_TOKEN` 实例均不在 `__all__` 中
- `Principal.to_scope()` 是唯一的公开派生路径（line 231-244）

**结论**: 当前 domain 层正确守住 fail closed 边界；认证 Principal 作为唯一 producer 的实现 defer 到后续 slice 是合理的架构分层。

## Regression Check

| Item | Status | Evidence |
| --- | --- | --- |
| Tests | PASS | 108 passed, 0 failed |
| Pyright | PASS | 0 errors, 0 warnings |
| Ruff | PASS | All checks passed |
| Coverage | PASS | 100% (135 stmts, 0 missed) |
| __all__ consistency | PASS | identifiers.py(12), money.py(5), domain/__init__.py(17), investment/__init__.py(17) — union equals full set |
| No reverse imports | PASS | AST guard confirms no forbidden imports in `dayu/investment/` |
| No escape patterns in production code | PASS | AST guard confirms no `Any`/`object`/`cast`/`type: ignore`/`getattr`/`hasattr` in `dayu/investment/` |
| No new findings | PASS | All prior findings resolved; no new findings discovered |

## Conclusion

**PASS** — open findings: **高 0 / 中 0 / 低 0**

All four original findings (Terra F-01 through F-04 / MiM M-01) have been correctly resolved in the review-fix:

1. **Strong ID runtime construction**: NewType → frozen slots dataclass with `__post_init__` validation. Direct construction and factory execute same validation.
2. **TenantScope fail closed**: Sentinel-gated `__init__` with singleton identity check + frozen immutability. Only `Principal.to_scope()` can create instances.
3. **UTC semantic-naive**: Shared `_is_aware_utc_offset` guard checking both `tzinfo` and `utcoffset()`. Custom tzinfo反例 covered.
4. **Test escapes/docstrings**: All `object`/`type: ignore`/`getattr`/`hasattr` removed from test file. Complete Args/Returns/Raises docstrings on all test functions.
5. **README current-only**: Future-slice claims removed. Only current domain skeleton and actual guard scope documented.

Residual risk from original review (NewType runtime gap, UTC semantic naive, test escape precedent) are all resolved. No regressions. No new findings.
