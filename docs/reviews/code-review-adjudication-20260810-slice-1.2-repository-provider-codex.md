# Slice 1.2 code review adjudication（Controller 裁决）

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：code review adjudication / fix 轮
- **Reviewed artifact**：`docs/reviews/slice-1.2-repository-provider-implementation-20260810-deepseek.md`
- **Review inputs**：
  - `docs/reviews/code-review-20260810-slice-1.2-repository-provider-terra.md`
    （**FAIL**，open H/M/L = **1/3/1**，TERRA-S12-001..005）
  - `docs/reviews/code-review-20260810-slice-1.2-repository-provider-mimo-native.md`
    （**PASS-WITH-RISKS**，open H/M/L = **0/1/1**，001/002）
- **Branch**：`codex/investment-platform`
- **Date**：2026-08-10

## Controller 裁决

- **Terra TERRA-S12-001..005：ACCEPT / FIX（全部 5 项）**
  - 001（高）：production 默认 provider 返回前必须做无业务写入的
    admission probe（连接 + 角色/application 校验），unreachable /
    malformed / wrong-role 统一 safe `PlatformCompositionError`，
    Host/Fins side effects 零、无 callback residue；
  - 002（中）：nil UUID 与 bool version/CAS 必须 fail-closed；
  - 003（中）：guard 必须以 AST owner/parent 关系绑定当前 class 的
    直接 `__post_init__(self)` 与本类 AnnAssign field，补 nested
    function / nested class / cross-class field / 非 self 参数 negatives；
  - 004（中）：`PreparedHostRuntimeDependencies.close()` 与 atexit
    registration 协调，manual close 后 callback 真正 no-op；
  - 005（低）：新增 unit test 的 `hasattr` 移除，改显式 protocol
    引用 / AST 签名。
- **MiM 001/002：REJECT / CLOSED（measurement-error / stale-source）**
  - 001 报“config defensive copy 为浅拷贝，不满足递归 deep-freeze”：
    `dayu/investment/domain/source.py` 705/738/794 已实现
    `_deep_freeze` 递归冻结（T34 落地），MiM 自身 Verified 段落亦已
    确认 JSONB codec / guard / lifecycle 全部通过——finding 基于旧
    片段，不按旧片段修复；
  - 002 报“guard 尚未实现 `object.__setattr__` 豁免”：豁免已由
    1968b13 erratum 接受并在 `test_architecture_boundaries.py` 396+
    实现（T35 落地），MiM Verified 已确认 guard 通过——stale-source。
- **保留**：pre-review correction 已闭环的 nested JSON codec 与
  lifecycle exact-once 修复（T36-T38），不因本轮 revert。

## Fix scope（worker 实际执行）

| Finding | 状态 | 修复位置 |
| --- | --- | --- |
| TERRA-S12-001 | FIXED | `dayu/services/startup_preparation.py` `_probe_production_engine` |
| TERRA-S12-002 | FIXED | `dayu/investment/domain/source.py`、`storage/postgres_identity.py` |
| TERRA-S12-003 | FIXED | `tests/investment/test_architecture_boundaries.py` guard |
| TERRA-S12-004 | FIXED | `dayu/services/startup_preparation.py` lifecycle 协调 |
| TERRA-S12-005 | FIXED | `tests/investment/test_identity_repositories.py` |
| MiM 001 | REJECTED | 无改动（stale-source） |
| MiM 002 | REJECTED | 无改动（stale-source） |

裁决与逐项 fix 证据见
`docs/reviews/slice-1.2-repository-provider-code-review-fix-20260810-deepseek.md`。

---

# Round 2 adjudication（Terra re-review，2026-08-10 16:31）

- **Review input**：`docs/reviews/code-review-20260810-slice-1.2-repository-provider-rereview-terra.md`
  （**FAIL**，open H/M/L = **0/3/0**，TERRA-S12-RR-001..003）

## Controller 裁决

- **TERRA-S12-RR-001（中）：ACCEPT / FIX**
  - storage `_canonical_uuid` 也必须拒绝 `parsed.int == 0`（与 source
    DTO 一致），覆盖 `TenantId`/`CompanyId`/`SecurityId`/source 各类
    entry 至少一个 pre-session/zero-SQL 断言，稳定
    `RepositoryInputError`。
- **TERRA-S12-RR-002（中）：ACCEPT / FIX**
  - parent 链遇 `ast.Lambda` 及所有嵌套执行作用域（comprehension）即拒；
  - `__post_init__` 唯一参数名精确 `self`，拒 posonly/vararg/kwonly/
    kwargs；
  - decorator `frozen`/`slots` 仅接受 `ast.Constant value is True`，
    拒 `1` 等真值；
  - 补三个直接反例及相近 scope negatives。
- **TERRA-S12-RR-003（中）：REJECT / CLOSED（reviewer-environment /
  non-defect）**
  - reviewer 侧 fixture 因缺本机 pinned digest 镜像（
    `postgres@sha256:64154d0babcb…`）全部 setup error；Controller
    docker image inspect 锁定 digest 成功，同树 DeepSeek / Controller
    真实 PG16 14 pass、全量 1744 pass、isolated coverage 已复证。
    Reviewer sandbox 缺镜像不是 code finding，不产生代码修复。
  - 本机 PG16.14 digest 已本地存在，integration lane 全绿（14 passed），
    每修改生产文件 isolated coverage >=80% 已复证。

## Round 2 fix scope

| Finding | 状态 | 修复位置 |
| --- | --- | --- |
| TERRA-S12-RR-001 | FIXED | `dayu/investment/storage/postgres_identity.py` `_canonical_uuid` |
| TERRA-S12-RR-002 | FIXED | `tests/investment/test_architecture_boundaries.py` guard |
| TERRA-S12-RR-003 | REJECTED | 无改动（reviewer-environment / non-defect） |

Round 2 逐项 fix 证据见
`docs/reviews/slice-1.2-repository-provider-code-review-fix-round2-20260810-deepseek.md`。

---

# Round 3 adjudication（final re-review，2026-08-10）

- **Review inputs**：
  - Terra final re-review（
    `code-review-20260810-slice-1.2-repository-provider-final-rereview-terra.md`）
    **FAIL**，open H/M/L = **0/1/0**；
  - MiM final re-review（
    `code-review-20260810-slice-1.2-repository-provider-final-rereview-mimo-native.md`）
    **PASS**（open 0/0/0）。

## Controller 裁决

- **TERRA-S12-FRR-001（中）：ACCEPT / FIX REQUIRED**
  - `_is_frozen_slots_dataclass` 以装饰器末段名称和跨 decorator 聚合
    判定 dataclass：不校验来源（模块级标准 import）、不要求同一 call
    同时携带 frozen/slots，允许同名伪 decorator 或分散 flag 绕过豁免，
    普通可变类可借 `object.__setattr__` 真实改写字段。
  - 修复必须收紧为：仅模块级 `from dataclasses import dataclass`
    解析得到、未被模块级重绑定的直接 `ast.Name` decorator；attribute
    callee（`fake.dataclass`）、本地/模块同名伪 decorator、无标准导入
    一律拒绝；`frozen=ast.Constant(True)` 与
    `slots=ast.Constant(True)` 必须在同一个唯一
    `ast.Call(ast.Name(resolved_binding), ...)` 内，不得跨 decorator
    聚合；重复关键字/模糊绑定 fail closed；保留合法 direct standard
    decorator positive；新增至少 4 类 negative。
- **MiM final PASS：保留**（RR-001/002 独立闭合、lifecycle/startup/
  RLS/JSON codec 全部验证通过），但当前树在 TERRA-S12-FRR-001 修复后
  需再双审。
- **Scope**：仅 `tests/investment/test_architecture_boundaries.py`；
  production/plan/README/其它 tests 不动。

## Round 3 hardening（re-review 前最终加固，同一 round3 范围）

- `import fake as dataclass` / `from fake import dataclass` 的本地别名
  绑定必须计入模块重绑定（标准 dataclasses 目标导入由 collector 单独
  处理，其余 import 视重绑定），否则可经 import 别名把标准名字顶掉；
- 豁免仅限**直接** module-level ClassDef（或等价完整解析 lexical
  shadowing），优先前者 fail-closed：ast.walk 会扫到函数内 nested
  class，局部同名伪 decorator 可遮蔽标准名字而绕过豁免；已确认
  `dayu/investment` 无 nested dataclass。
- 新增 import-rebinding 与 nested-local-fake decorator 负例。

## Round 3 fix scope

| Finding | 状态 | 修复位置 |
| --- | --- | --- |
| TERRA-S12-FRR-001 | FIXED | `tests/investment/test_architecture_boundaries.py` guard（provenance + single-call + fail-closed + import 绑定重绑定 + module-level-only 豁免） |

Round 3 逐项 fix 证据见
`docs/reviews/slice-1.2-repository-provider-code-review-fix-round3-20260810-deepseek.md`。
Status：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

---

# Round 4 adjudication（final closure，2026-08-10）

- **Review inputs**：
  - Terra final closure（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-terra.md`）
    **FAIL**，open H/M/L = **0/1/0**；
  - MiM final closure（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-mimo-native.md`）
    **PASS**（open 0/0/0）。

## Controller 裁决

- **TERRA-S12-FC-001（中）：ACCEPT / FIX**
  - 不要继续手工枚举 pattern AST；改为 Python 标准库 symtable 作为
    模块绑定真相：`_collect_escape_violations_from_source(source)` 将
    source 传给 dataclass trust collector；
  - 候选仍须是唯一模块级 `from dataclasses import dataclass
    [as alias]` 且 AST 无其它同名 import 模糊绑定，同时
    `symtable.symtable(source, ..., "exec").lookup(alias)` 必须
    `is_imported` True 且 `is_assigned` False——assignment/for/with/
    except/walrus/match capture/del/function/class 统一 fail closed；
  - 保留 top-level class / direct Name / unique same-call frozen=True
    slots=True 限制；
  - 新增 Terra 精确 match/case capture runtime-shape negative；最好加
    del binding negative 作为符号表边界。
- **MiM final closure PASS：保留**，但当前树在 TERRA-S12-FC-001 修复
  后需再双审。
- **Scope**：仅 `tests/investment/test_architecture_boundaries.py`；
  production/plan/README/其它 tests 冻结。

## Round 4 fix scope

| Finding | 状态 | 修复位置 |
| --- | --- | --- |
| TERRA-S12-FC-001 | FIXED | `tests/investment/test_architecture_boundaries.py` guard（symtable 绑定真源 + 单次 parse + match/case、del 负例） |

Round 4 逐项 fix 证据见
`docs/reviews/slice-1.2-repository-provider-code-review-fix-round4-20260810-deepseek.md`。
Status：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**（历史快照；
最终状态见下文 Artifact-only closure）。

## Artifact-only closure（round4 dual re-review PASS）

- **Round 4 dual re-review**：Terra final closure round4（
  `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`）
  **PASS**（open H/M/L = **0/0/0**）与 MiM final closure round4（
  `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`）
  **PASS**（open H/M/L = **0/0/0**）。
- **Findings closure**：TERRA-S12-FC-001、TERRA-S12-FRR-001、
  TERRA-S12-RR-001/002 与初审 findings（TERRA-S12-001..005）全部
  **CLOSED**；RR-003 reviewer-environment / non-defect；MiM 001/002
  REJECT（stale-source）保持事实记录。
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**（历史 FAIL/PASS 与各轮
  裁决保持事实记录）。
