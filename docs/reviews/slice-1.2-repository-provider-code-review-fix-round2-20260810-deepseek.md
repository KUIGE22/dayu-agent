# Slice 1.2 code review fix artifact — Round 2（TERRA-S12-RR-001/002）

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：code review fix（round 2）
- **Adjudication**：`docs/reviews/code-review-adjudication-20260810-slice-1.2-repository-provider-codex.md`
  （round 2 段落）
- **Review input**：`docs/reviews/code-review-20260810-slice-1.2-repository-provider-rereview-terra.md`
- **Branch**：`codex/investment-platform`
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**
- **Date**：2026-08-10

## TERRA-S12-RR-001（中）— repository canonical UUID 拒 nil

**Finding**：storage `_canonical_uuid` 未拒绝 nil UUID
（`00000000-0000-0000-0000-000000000000`），generic `TenantId` /
`CompanyId` / `SecurityId` 的 nil 值可越过 repository pre-session
admission 进入后续 SQL 路径。

**Fix**（`dayu/investment/storage/postgres_identity.py`）：

- `_canonical_uuid` 在 canonical comparison 前加
  `if parsed.int == 0: raise RepositoryInputError(...)`，与 source DTO
  的 `_validate_canonical_uuid` 判定一致；所有 repository entry 的
  `_validate_scope` / `_normalize_*_id` 均经由此 helper，一处修复全链
  生效。

**Tests**（`tests/investment/test_identity_repositories.py`）：

- 新增 `TestRepositoryRejectsNilIdsPreSession` 类，每类 entry 一个
  pre-session / zero-SQL 断言：
  - `test_nil_tenant_scope_rejected_before_session`（nil `TenantScope`）；
  - `test_nil_company_id_rejected_before_session`；
  - `test_nil_security_id_rejected_before_session`；
  - `test_nil_source_definition_id_rejected_before_session`；
  - `test_nil_subscription_id_rejected_before_session`。
- nil 值构造方式遵循 DTO 校验不放松：
  - generic 标识（`TenantId`/`CompanyId`/`SecurityId`）公开构造器接受
    nil（只拒空/空白），直接构造；
  - source 强标识（`SourceDefinitionId`/`SourceSubscriptionId`）DTO 已
    拒 nil，用 `object.__new__` + `object.__setattr__` 模拟不可信/反序
    列化来源绕过 DTO 校验后验证 repository 自身防御。
- 零 SQL 证明：`_RejectingSessionFactory` 是 `sessionmaker[Session]`
  子类，`__call__` 抛 `AssertionError`；所有校验发生在
  `_session_for_scope`（创建 Session）之前，factory 永不被调用，测试
  因 `RepositoryInputError` 通过即证明零 SQL。

## TERRA-S12-RR-002（中）— guard 收紧 lambda/self/decorator 形态

**Finding**（`tests/investment/test_architecture_boundaries.py`）：

1. 父链跨过 `ast.Lambda`（`callback = lambda: object.__setattr__(...)`）
   被误豁免；
2. `__post_init__(owner)` 只查参数个数不查名字；posonly/vararg/kwonly/
   kwargs 未拒；
3. `@dataclass(frozen=1, slots=1)` 经 `bool(value)` 被当作精确 True。

**Fix**：

- `_direct_post_init_owner` 父链新增 `ast.Lambda` / `ast.ListComp` /
  `ast.SetComp` / `ast.DictComp` / `ast.GeneratorExp` 即返回 `None`
  （嵌套执行作用域一律拒绝）；
- 新增 `_is_sole_self_param(args)`：`posonlyargs` 为空、`args` 恰好一
  个且名字精确 `self`、`vararg`/`kwonlyargs`/`kwarg` 全空；
- `_is_frozen_slots_dataclass` 改为仅接受 `ast.Constant` 且
  `value is True` 的 `frozen`/`slots`（`frozen=1`/`slots=1` 拒绝）。

**Tests**：负例矩阵新增 8 项（全部 fail-closed）：

- lambda 内调用；
- list comprehension 内调用；
- 参数名非 `self`（`__post_init__(owner)`）；
- posonly（`def __post_init__(self, /)`）；
- vararg（`*args`）；
- kwonly（`*, extra`）；
- kwargs（`**kwargs`）；
- `@dataclass(frozen=1, slots=1)` 真值常量。

## TERRA-S12-RR-003（中）— REJECT / CLOSED

reviewer sandbox 缺本机 pinned digest 镜像导致 integration fixture
setup error、coverage 被 pandas/numpy 导入阻断；Controller docker
image inspect 锁定 digest 成功，同树 DeepSeek/Controller 真实 PG16
14 pass、1744 pass、isolated coverage 已复证。**non-defect**，无代码
改动。

## Validation（本 fix 轮重跑）

```bash
pytest tests/investment tests/application/test_service_startup_preparation.py \
  tests/integration/investment -q        # 322 passed
pyright <slice 全部文件>                   # 0 errors
ruff check <slice 全部文件>                # All checks passed
git diff --check                          # clean
docker ps -a --filter "label=dayu-slice11.owner"   # 0 残留
docker ps --filter "name=investment-agent-platform" # PG17 5 容器 healthy 未动
```

- guard：`test_architecture_boundaries.py` 140 passed（+8 RR-002 负例）；
- `test_identity_repositories.py` 35 passed（+5 RR-001 nil pre-session）；
- 真实 PG16 integration 14 passed（含 startup black-box 4：
  wires/wrong-role/missing-DSN/close-dispose-once）。

## Residual risks

| 风险 | 分类 |
| --- | --- |
| generic `TenantId`/`CompanyId`/`SecurityId` 公开构造仍接受 nil（Slice 1.1 契约只拒空/空白）；repository 是最终防线 | 合理分层（repository 已拒） |
| `object.__new__`+`__setattr__` 伪造路径仅用于测试证明防御边界 | 测试手法，不影响生产 DTO 校验 |
| 输入校验分支类型系统不可达（原有防御分支） | 合理防御（见 implementation artifact） |

## Completion / stop status

- **Completed**：TERRA-S12-RR-001/002 修复并验证；RR-003 REJECT；
  322 tests 全绿、pyright 0、ruff clean、diff clean、零容器残留、PG17
  未动。
- **Not run**：未启动 review/commit/push/PR/live/Slice 1.3。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Artifact-only closure（round4 dual re-review PASS）

- **Round 4 dual re-review**：
  - Terra final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`）
    **PASS**，open H/M/L = **0/0/0**；
  - MiM final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`）
    **PASS**，open H/M/L = **0/0/0**。
- **Findings closure**：TERRA-S12-001..005、TERRA-S12-RR-001/002、
  TERRA-S12-FRR-001、TERRA-S12-FC-001 全部 **CLOSED**；RR-003
  （reviewer-environment / non-defect）与 MiM 001/002（stale-source）
  的 REJECT 保持事实记录。
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**（历史 FAIL/PASS 与各轮
  裁决保持事实记录）。
