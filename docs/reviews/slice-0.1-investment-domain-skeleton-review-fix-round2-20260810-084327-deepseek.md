# Slice 0.1 Investment domain skeleton review fix（round2）

- Status：**CLOSED / DUAL RE-REVIEW PASS**
- Gate：`implementation -> code review -> fix -> re-review -> fix`（round2 corrective）
- Work unit：`investment-platform-restoration`
- Slice：`0.1 — Investment domain skeleton 与 dependency guard`
- Source review（round2）：`code-rereview-20260810-083133-slice-0.1-terra.md`（FAIL，中 1 / 低 1）、
  `code-rereview-20260810-083133-slice-0.1-mimo-native.md`（PASS）
- Adjudication：`slice-0.1-investment-domain-skeleton-adjudication-20260810-080206-codex.md`（Round2 节）
- Round1 fix：`slice-0.1-investment-domain-skeleton-review-fix-20260810-080206-deepseek.md`
- Implementation artifact：`slice-0.1-investment-domain-skeleton-implementation-20260810-074602-deepseek.md`（状态已同步更新）
- No commit / push / PR；无网络 / live / model / broker / PG / Redis / MinIO 动作

## Fix dispositions

| Finding | Disposition | Applied fix |
| --- | --- | --- |
| Terra F1（中）：TenantScope 私有哨兵不能证明唯一 Principal 路径，且仍可把原始租户值写入 scope | ACCEPTED | `TenantScope.__init__` 在对象身份哨兵校验之后新增 `isinstance(tenant_id, TenantId)` 防御：即使调用方携带模块内部真实单例 `_TENANT_SCOPE_TOKEN`，raw str 也一律抛 `TypeError` fail closed（`identifiers.py`）。同步收敛全部不实表述：模块 docstring、`_TenantScopeToken` 类 docstring、`TenantScope` 类 docstring、`__init__` docstring、`_make_tenant_scope` docstring 删除“无法获得/无法绕过认证/唯一安全 producer”等声明，改为“哨兵仅是公开 API misuse guard，不是认证能力；`Principal` 唯一 producer 与 repository/RLS enforcement 属于对应后续授权 slice”。 |
| Terra F2（低）：investment README 仍含未来 slice 叙述并声称不存在的反向依赖 guard | ACCEPTED | `dayu/investment/README.md`：反向 import guard 描述改为精确匹配实际范围——AST guard 只枚举 `dayu/investment` 包内 Python 文件并断言不导入上层包，不扫描包外模块，故不构成跨包反向 import 检查；2.1 节“已认证主体/唯一载体”改为当前事实（`Principal` 当前为公开构造器、哨兵非认证能力）；2.2 节“属于后续 slice”改为“当前模块不实现账本分录或费用分摊规则”。 |

## 补测

- `test_tenant_scope_rejects_raw_string_tenant_even_with_real_sentinel`：
  从模块导入真实单例 `_TENANT_SCOPE_TOKEN`（同模块/测试允许边界，非公开契约），
  经 `dataclasses.replace(scope, tenant_id="raw", _token=_TENANT_SCOPE_TOKEN)`
  注入原始字符串并携带真实单例，断言 `TypeError`——精确证明 raw str 仍被
  `TenantId` 类型检查拒绝。
- `test_tenant_scope_accepts_real_sentinel_with_valid_identifier`：真实单例 +
  合法 `TenantId` 对照用例，证明哨兵校验与 `TenantId` 类型防御是两层独立检查。
- 保留公开直构 / 伪 token / frozen 测试：`test_tenant_scope_direct_construction_rejected`、
  `test_tenant_scope_rejects_forged_sentinel`、`test_tenant_scope_is_immutable_after_creation` 未改动。

## 关键设计说明

- `TenantScope.__init__` 现有两层守卫：(1) `_token is _TENANT_SCOPE_TOKEN`
  对象身份校验（公开 API misuse guard）；(2) `isinstance(tenant_id, TenantId)`
  类型防御。两层独立：伪造实例或缺失哨兵在第一层被拒；携带真实单例的
  raw str 在第二层被拒。哨兵不构成认证或 provenance 证明，仅为构造组织机制。
- `Principal` 当前是公开构造器，本模块不实现认证；认证层作为 `Principal`
  唯一 producer 与 repository/RLS 的租户边界实施是后续授权 slice 的职责，
  本 slice 不把 Python 私有名伪装成 security capability。
- README 反向依赖描述与 `_iter_investment_files()` 实际扫描范围逐项对照：
  guard 根为 `dayu/investment`，只断言包内文件不导入上层包。

## Validation evidence（`/Users/wsk/workspace/dayu-agent`、激活 `.venv`）

| Command | Exit | Evidence |
|---|---:|---|
| `python -m pytest tests/investment -q` | 0 | `110 passed`（round1 108 + round2 新增 2） |
| `python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing` | 0 | `__init__.py 100%`、`domain/__init__.py 100%`、`domain/identifiers.py 100%`（68 stmts）、`domain/money.py 100%`（64 stmts），单文件 coverage 全部 >= 80% |
| `pyright dayu/investment tests/investment` | 0 | `0 errors, 0 warnings, 0 informations` |
| `pyright`（全仓） | 0（既有 17 errors） | 17 errors 全部位于既有 `docling_processor.py` + engine tests，与基线一致，无新增无扩散 |
| `ruff check --select E4,E7,E9,F,I dayu/investment tests/investment` | 0 | all checks passed |
| `ruff check dayu/investment tests/investment`（默认全规则） | 0 | all checks passed |
| `git diff --check` | 0 | 无 whitespace 错误 |
| allowlist audit | 0 | 变更仅限 Slice 0.1 allowlist + review artifacts，见下 |

## Allowlist 与 scope audit

- 本轮变更文件：`dayu/investment/domain/identifiers.py`、`dayu/investment/README.md`、
  `tests/investment/test_architecture_boundaries.py`。
- 本轮更新 artifact：implementation artifact、adjudication（Round2 节）、round1 review-fix（状态指引）、
  本 round2 fix artifact。
- 未修改 accepted plan、allowlist 外代码、既有 source review 文件
  （`code-rereview-*`、`code-review-*` 均保持只读）。
- `dayu/investment` 生产代码仍无 `Any` / `object` / `cast` / `type: ignore` /
  `getattr` / `hasattr` / `noqa` 逃逸（AST guard 断言通过）；测试文件新增用例
  亦未引入上述逃逸（`dataclasses.replace` 注入，无 cast/ignore）。

## Residual risks

- `TenantScope` 哨兵不能阻止同一进程内解析真实单例的调用方；这是本 slice
  已明确的设计边界——哨兵仅约束公开 API 误用，跨租户数据访问的最终防线
  是后续 repository/RLS enforcement 与认证层（唯一 producer）。
- 其余 round1 residual（UTC helpers 归置、Money 恒非负、反向 import 依赖扩展）
  不变，由后续 slice 承接。

## Handoff

Terra re-review F1（中）、F2（低）均按 adjudication Round2 处置并在最新树验证。
最终独立复审为：Terra
`code-rereview-20260810-085600-slice-0.1-terra.md` PASS，MiM
`code-rereview-20260810-085202-slice-0.1-mimo-native.md` PASS；两路 open
H/M/L 均为 `0/0/0`。当前状态为 **CLOSED / DUAL RE-REVIEW PASS**，accepted
commit 仅由 Controller 创建。fix worker 未 commit / push / 创建 PR，也未进入
Slice 0.2。
