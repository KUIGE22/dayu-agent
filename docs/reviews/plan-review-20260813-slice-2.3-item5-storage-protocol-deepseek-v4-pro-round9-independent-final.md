# Slice 2.3 Item 5 Storage Protocol — DeepSeek V4 Pro Round 9 Independent Final Review

- 日期：2026-08-13 16:23:43 +0800（本机系统时钟，`date '+%Y-%m-%d %H:%M:%S %z'`）
- 模型：DeepSeek V4 Pro（model ID `deepseek/deepseek-v4-pro`）
- 分支：`codex/investment-platform`
- HEAD：`45154597d3d01be13287393f4123003a1444f0eb`（Item 4 metadata acceptance commit，parent = semantic commit `4101fb6da02eb08ddd245561a92e021046fdeccb`）
- Index preflight：empty（`git diff --cached --name-only` = 0 文件）
- 复核身份（首读 + 写 artifact 前 double-freeze，两次完全一致）：

| 文档 | 角色 | SHA-256 | lines |
|---|---|---|---|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | target | `c51e89ddce927300ba03dd293cb15e8927de2ecb341f5955f5fe9b097b440988` | 3248 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | master | `1db7eb076637dc3ec8eaed92bcd422b36b8c102076c32b957fc99ed650b5b87a` | 4405 |
| `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | fix | `62b6d2dae6a91caf7ee189c4a408028b24b1998b8bc80f457d50976f80cf822f` | 349 |

- 证据边界：只读 `AGENTS.md`、planreview skill、真实 HEAD 契约（`dayu/investment/domain/**`、
  `dayu/investment/storage/**` 的已提交身份）与 target/master/fix 三份 frozen docs；未 glob/list/open/read
  任何 prior plan-review artifact，其结论不作为证据。零 stage/commit/push/network/PG 动作。

## 1. Reviewed target and scope

本轮独立复审目标：Item 5 storage-protocol corrective candidate 的以下八个被冻结的语义合同是否已
唯一化、可 codegen，且没有引入新的自相矛盾：

1. 七方法 protocol 的 exact direct-import 集与唯一 concrete class/constructor；
2. Item 4 accepted dependency manifest 与 0005-only repository 前置；
3. already-LEASED Job 的 definition-status 语义；
4. 穷尽 request/execution/repository 三阶段 failure taxonomy；
5. `get_source_receipt` 的 0001 legacy receipt 读取语义；
6. §13.3 exact 53 项的 per-slice/file 归属（Item 5 PG27 + Item 6 APP4/JOB15/OP5/HEALTH2）；
7. 159 named catalog / 43 coverage keys / Item 5 exact 五 path 不扩面；
8. rollback outcome 高于 original typed lock 的唯一全序，及 §13.3 #6/#23 四组合覆盖。

## 2. Assumptions tested（逐一证伪尝试）

| # | Assumption | 直接证据 | 结论 |
|---|---|---|---|
| A1 | `SourceSubscriptionId` 唯一 owner 是 `domain/source.py`，protocol 不能经 sync owner/root re-export | `dayu/investment/domain/source.py:233` `class SourceSubscriptionId`；`source_health.py:18`、`source_evidence.py:19`、`source_payload.py:22`、`source_sync.py:27` 均 `from dayu.investment.domain.source import SourceSubscriptionId` | 成立 |
| A2 | 七方法 annotation 所需的四个 sync DTO owner 均已在 HEAD 物化 | `SourceExecutionBinding`=`source_payload.py:57`、`SourceSyncAttemptReceipt`=`source_evidence.py:522`、health DTO=`source_health.py:71/91/190/209`、operation DTO=`source_operation.py:76/115/228/261` | 成立 |
| A3 | 单一 `sessionmaker[Session]` constructor 是 project-local 一致约定 | `postgres_jobs.py:580`、`postgres_schedules.py:1253` 均 `def __init__(self, session_factory: sessionmaker[Session]) -> None` | 成立 |
| A4 | `tests/application/test_source_sync_execution.py` 在 HEAD 不存在且 untracked，是 Item 6 scope | `ls` 无此文件；`git ls-files` 无输出 | 成立（coverage-owner 修正的根因确证） |
| A5 | Item 4 manifest 五项已由 accepted commit 冻结且字节可验 | 0005 migration SHA `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` / 2674 行；`models_identity.py` SHA `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd` / 908 行，均与 fix §S23-I5-ITEM4-DEPENDENCY-03、target §12 逐字相等 | 成立 |
| A6 | §13.3 五组 ordinal 赋值 pairwise-disjoint、union=`{1..53}`、count=`27+4+15+5+2=53` | 手工按 1-based ordinal 枚举 53 项（target 2842–2894）并对照赋值表（2899–2905） | 成立（详见 §3.6） |
| A7 | §9 六行 transaction outcome 全序无重叠、无遗漏、read 与 write 同序 | target §9 2290–2302；§6.1 1542–1545；§15 3118–3121 三处语义逐字一致 | 成立（详见 §3.8） |
| A8 | 43 keys 只发生一处 singleton tuple 永久修正，且 Item 5 两个 production key 的 tuple 均可物化 | target §11.1 2537–2579（43 key 枚举）；`source_sync_protocols.py`→`(test_source_sync_storage_protocols.py,)`；`postgres_sources.py`→`(test_postgres_sources.py,)` | 成立 |

## 3. Mechanical audit（逐项核对，全部通过）

### 3.1 七方法 protocol exact import 集（target §9 2174–2193）
直接 import 精确为 `typing.Protocol/runtime_checkable`、`uuid.UUID`、`identifiers.TenantScope`、
`source.SourceSubscriptionId`、`source_evidence.SourceSyncAttemptReceipt`、health 四个 DTO
（Projection/ReenableRequest/SnapshotCursor/SnapshotPage）、operation 四个 DTO
（AcquireDecision/AcquireRequest/TerminalRecordDecision/TerminalRecordRequest）、
`source_payload.SourceExecutionBinding`。七方法签名与 §9 2203–2248 精确一致（`get_executable_binding`、
`acquire_operation`、`record_terminal`、`get_source_receipt`、`get_health`、`list_health_snapshots`、
`reenable_health`）。`source_sync.py` 不在 annotation 集内；其 closed exceptions 只由 concrete 按分支
import。与 fix §S23-I5-PROTOCOL-OWNER-01 的 Fix 逐字一致。✓

### 3.2 唯一 concrete class/constructor（target §9 2251–2275）
`dayu/investment/storage/postgres_sources.py` 唯一拥有
`PostgresSourceSyncRepository(SourceSyncRepositoryProtocol)`，constructor exact 为
`__init__(self, session_factory: sessionmaker[Session]) -> None`，禁止额外 dependency/setter，
constructor 只 assignment、零 I/O；startup 沿用 `_PlatformPreparation.engine/session_factory` 单一 factory。
与 fix §S23-I5-CONCRETE-CONSTRUCTOR-02 逐字一致。✓

### 3.3 Item 4 accepted manifest / 0005-only（target §12 2658–2685）
五项 manifest（`item4_accepted_commit`、`item4_migration_sha256`、`item4_models_identity_sha256`、
`item4_acceptance_artifact`、`item4_final_review_artifacts`）已闭合为 two-commit identity；Item 5 repository
只面向已由 startup admission 升级到 0005 的 schema，不查 `alembic_version`、不 0004 fallback、不回改
migration/models。与 fix §S23-I5-ITEM4-DEPENDENCY-03 一致；migration/models SHA 已在 §2-A5 对真实 HEAD 验证。✓

### 3.4 already-LEASED definition status（target §6.1 1506–1560、§9 2317/2318）
已 LEASED Job 的 `job_definitions.status` 不是 acquire/terminal 的 live predicate；active admission 只属于
generic Job owner 在 lease 形成前；两条 Source 路径仍按 `job_run→job_definition` 顺序 `FOR UPDATE NOWAIT`
锁 definition 以串行化 identity/descriptor 与并发 status update；status update 占锁产生的 original typed
`55P03` 在 rollback 成功时 `unavailable`、rollback 失败时 `transaction_aborted`；disable 已提交后重试在
其余 live 条件成立时仍可成功。§15 3104–3105 STOP 条件与之一致。与 fix §S23-I5-CONSTRUCT-05 一致。✓

### 3.5 穷尽 phase taxonomy 与 legacy receipt（target §9 2285–2335、§8.2 1973–1980）
- 六行全序（§3.8）+ 逐七方法 request/execution code 矩阵：`invalid_input`/`job_lineage_mismatch`/
  `payload_hash_mismatch`/`snapshot_mismatch`/`subscription_not_found`/`binding_non_executable`/
  `job_not_live`/`lease_lost`/`persisted_invariant`；`tenant_identity_mismatch` 对当前七方法不可达。
- `get_source_receipt`：runtime input/scope 非法→`invalid_input` 零 SQL；scoped missing/cross-tenant→`None`；
  合法 0001 13-core-all-null legacy row→`None`；只有 v1 13-core-all-full 经 strict parse/canonical re-encode/
  stored SHA/lineage 全一致才返回 receipt；partial/illegal-full/canonical/SHA/lineage drift→
  `persisted_invariant`。
- 与 fix §S23-I5-CONSTRUCT-06/07 逐字一致；`13-core`（presence CHECK，不含
  `latest_source_observed_date`）与 `14 column`（total，§8.2 1877、§13.4 2926、§8.5 2145）的区分精确且
  无矛盾。✓

### 3.6 §13.3 exact 53 项 per-slice/file 归属（target 2896–2919）
按 1-based ordinal 枚举 53 项并逐项对照赋值表：

| 组 | ordinals | count | file |
|---|---|---|---|
| Item 5 PG27 | 1,2,6,9,10,11,17,20,23,28,29,32,36–47,49,51,52 | 27 | `tests/integration/investment/test_postgres_sources.py` |
| Item 6 APP4 | 3,4,8,18 | 4 | `tests/application/test_source_sync_execution.py` |
| Item 6 JOB15 | 5,7,12,19,21,22,24–27,30,31,33,34,50 | 15 | `tests/integration/investment/test_source_sync_job.py` |
| Item 6 OP5 | 13–16,48 | 5 | `tests/investment/test_source_operation_domain.py` |
| Item 6 HEALTH2 | 35,53 | 2 | `tests/investment/test_source_health_domain.py` |

五组 pairwise-disjoint、union=`{1..53}`、count `27+4+15+5+2=53`。被 CONSTRUCT-05/07/09 扩展的三个既有
测试名分别落位：ordinal 6、23、20（PG27）、32（PG27，definition/security concurrency）——全部在 Item 5
唯一 PG 文件内，无越界。✓

### 3.7 159 / 43 / five paths（target §11、§13）
- named catalog：158→159，唯一新增 `test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact`
  （§13.1 2732），无删除/改名。
- `COVERAGE_OWNER_TESTS`：43 个 key（§11.1 2537–2579 手工枚举 = 43），唯一语义修正是
  `source_sync_protocols.py` tuple 永久收窄为 `(test_source_sync_storage_protocols.py,)`；其余 42 tuple
  不变。Item 5 两个 production key（`source_sync_protocols.py`、`postgres_sources.py`）的 tuple 均为
  singleton 且 member 均在 Item 5 exact 五 path 内可物化。
- Item 5 exact 五 path：`source_sync_protocols.py`、`postgres_sources.py`、
  `test_source_sync_storage_protocols.py`、`test_postgres_sources.py`、`test_architecture_boundaries.py`
  （§11 2616–2620）。✓

### 3.8 Critical global order：rollback 高于 original typed lock（target §9 2290–2302）
六行从高到低唯一全序，且 §6.1 1542–1545、§15 3118–3121 三处语义逐字一致：

| Priority | 事实 | 结果 |
|---|---|---|
| 1 | rollback 被调用且自身任一 SQLAlchemy/DBAPI failure（含 rollback 自身 exact `55P03`/`LockNotAvailable`） | `transaction_aborted`，覆盖 original typed lock/unavailable、request/execution rejection、`persisted_invariant` |
| 2 | rollback 成功且 original exact `55P03`，或该 typed lock 无需 rollback | `unavailable` |
| 3 | 第一条 SQL 成功后 statement/flush/commit 非 lock DB failure + rollback 成功 | `transaction_aborted` |
| 4 | 入口→第一条 SQL 成功前 session/enter/checkout/first-SQL 非 lock DB failure + cleanup 成功或无需 rollback | `unavailable` |
| 5 | SQL 成功返回后 reconstruction 失败 + rollback 成功 | `persisted_invariant` |
| 6 | request/execution rejection + rollback 成功或无需 rollback | 保留 method matrix exact code |

全序无重叠、无遗漏、read 与 write 同序；programming `BaseException` 不 catch、不 message-match。
§13.3 #6 同名扩展精确覆盖四组合：original `55P03`+rollback success→`unavailable`、
original `55P03`+rollback failure→`transaction_aborted`、rollback 自身 `55P03`→`transaction_aborted`、
无需 rollback 的 original `55P03`→`unavailable`；#23 同名 parameterized 覆盖 admission/post-admission
cleanup 与 rollback outcome。均不新增 named test。与 fix §S23-I5-CONSTRUCT-09 一致。✓

## 4. Findings

无 material findings。CONSTRUCT-05..09 五个既有 blocker 均已由 evidence-based 的机械合同唯一化，
且未被新的自相矛盾替代（见 §3.4/3.5/3.6/3.8 逐项反证）。未发现：

- scope/ownership/file-boundary 不清；
- code-generation 前迫使 writer 重新设计的歧义；
- 过度耦合、跨层穿透或 architecture 反向依赖；
- data loss / 不可逆状态 / idempotency / 并发恢复 / ordering 缺口；
- empty-state / unavailable-dependency 行为未定义；
- schema drift / migration hazard / 兼容回归；
- 只证明 happy path 的 test 缺口（#6/#23 均含 rollback failure 与 admission/post-admission 反例）。

## 5. Open questions

无（open H/M/L = 0/0/0）。所有合同分支均已收敛，没有需要用户选择的剩余分支。

## 6. Residual risks and tracking destination

以下为既有的显式 accepted residual，非本 candidate 引入，不构成 finding：

1. Source terminal 与 Job terminal 非同事务；最后 attempt crash 可能使 Job envelope 失败而 source truth
   成功（target §16.2）。destination：既有 §16 residual 清单。
2. Source execution 对同步 repository 的 owned-thread reap 无 wall-clock 上界（§16.8，SQLAlchemy/psycopg/
   connect/pool 永不返回时无限等待）。destination：后续 platform reliability gate 的 bounded timeout 配置。
3. Item 6 为 OP5/HEALTH2 额外获得两个 domain-ratchet test write path，属 per-slice 授权而非 Item 5/production
   scope 扩张；Item 6 修改后必须重跑 `source_operation.py`/`source_health.py` exact owner coverage/static
   （§13.3 2915–2919）。destination：Item 6 handoff 前置。
4. §13.3 的 ordinal→file 归属是冻结的测试实现责任分配；个别测试（如 ordinal 1 的 heartbeat/terminal 交互）
   名义上属 source+job 交互，但按赋值落入 PG27。该归属不改变 production owner/public contract/allowlist，
   且五组 disjoint/count 已被机械审计锁定。destination：Item 5/Item 6 gate 的 named collector 审计。

## 7. Final conclusion

**PASS / open H/M/L = 0/0/0**

本 DeepSeek V4 Pro Round 9 independent final review 对 frozen target
`c51e89dd…/3248`、master `1db7eb07…/4405`、fix `62b6d2da…/349` 完成独立复审。八项被冻结语义合同
（七方法 protocol/concrete constructor、Item 4 accepted manifest/0005-only、leased-definition status、
穷尽 request/execution/repository phase taxonomy、legacy receipt、§13.3 exact 53 项 split、
159/43/five paths、rollback-vs-original-typed-lock 唯一全序）均已唯一化、可 codegen，机械审计
（53=`27+4+15+5+2`、43 keys、159 names、五 path、#6/#23 四组合）全部通过，无 material finding，
无 open question。Item 4 exact accepted manifest 已闭合且不可替换；43-key matrix 只发生一个永久
singleton tuple 修正，当前 Item 5 tuple 全部可物化。本结论只证明上述三个 same-new-SHA 语义字节，
不构成 Item 5 implementation dispatch 或 accepted commit 证据——仍待 MiMo 独立复审与 Controller acceptance。
