# Slice 2.3 planning handoff：Source connectors、sync receipt 与 health

- 作者：Codex internal Terra（planning only）
- 日期：2026-08-12
- Gate：Slice 2.3 PLAN / high risk
- 基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`
- 对应计划：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- 本文性质：供 Controller、Codex implementer 与后续 DeepSeek/MiMo 独立 reviewer 使用的
  handoff/evidence record；不是自我 review、不是 code acceptance。

## 1. 本次 handoff 已冻结的决定

| 风险点 | 已冻结的方案 | 不能采用的方案 |
|---|---|---|
| 0001 append-only sync rows | 0005 扩展 `source_sync_runs` 为新 attempt 的不可变终态 receipt；旧 planned/running row 继续可读但 2.3 不读写。 | 原地 planned/running/succeeded 状态更新，或另建第二份 result truth。 |
| A/B lease overlap | 新 mutable `source_sync_operations` 作为 job-run 级 execution ownership/fence head；同 attempt receipt 只是结果，不承担在途 ownership。 | 仅以 `(job_id, attempt_id)` unique 防冲突，或 Redis lock。 |
| A lease 到期而仍在 Fins | B 遇未到期 head 返回 WAIT/`SOURCE_OPERATION_BUSY`，无 Fins；到期后 generation reclaim，A 的条件提交失败；Fins 前 PG 崩溃是 `max_attempts=3` 有界、只读 provider 重读。 | 把外部读说成 exactly-once，或 B 看不到 receipt 就盲目重放。 |
| Fins 调用路径 | 新 `FinsServiceProtocol.sync_worker_source()` 直委托 runtime，传 callback cancellation；Fins 自己拥有 ingest/storage/locator。 | Worker -> `FinsService.submit()` -> Host 嵌套，或 investment 读 Fins storage。 |
| locator/Fact | Fins 返回已验证、无路径 locator projection；source receipt 引用 locator+hash。 | 从 listing 猜 version/hash，或把 media/source clue 写成 Fact。 |
| health | PG health head 是唯一可变 current truth；snapshot/outbox 均 append-only，和 terminal receipt 同 transaction。 | snapshot 当 head、Redis health、非事务 alert。 |
| alert | episode/target-state/error dedupe key，outbox 仅事实，delivery 7.6。 | 本 Slice 发网络通知或保存 transport retry state。 |
| disabled | worker 不自动 re-enable；未公开 operator entry 有 version CAS。RBAC 仍为 7.1 residual。 | 失败成功后自动解除 disabled，或把没有路由误称已认证授权。 |
| schedule | 注册 source Job descriptor/handler，暂不注册循环 schedule。 | 静态 schedule payload 重用同一 source Job。 |

## 2. 直接检查的代码事实

以下是计划据以生成的当前代码事实，优先级高于历史文字：

1. `dayu/investment/storage/models_identity.py` 已声明 `source_sync_runs` 与
   `source_health_snapshots`，二者均无 updated/version；0001 DDL 对这两表 app role
   仅授予 INSERT/SELECT，且 run status 虽含 planned/running，但没有 repository。
2. `SourceRepositoryProtocol`/`PostgresIdentityRepository` 只做 source definition/
   subscription CRUD/CAS，当前没有 sync/health repository。
3. `JobExecutionRequest` 只有 tenant、definition、job、attempt、attempt number、descriptor、
   payload、deadline；Job execution handler 看不到 lease/fence/token/worker。
4. `JobExecutionRegistry` 已 append-only/idempotent，但没有 seal/count public contract；
   production 2.2 startup 注册的是空 registry。
5. `FinsService.submit()` 建立 Host session 并走 `host.run_operation_sync/stream`；这不适合
   Worker。`FinsRuntimeProtocol`/`FinsIngestionService.download_stream()` 已存在取消 callback
   链路，适合作为 Fins-owned 新窄入口的基础。
6. `EvidenceLocatorRequest` 需要 document version、source fingerprint、primary hash 与 locator
   hash；这些能在 `DefaultFinsRuntime` 内部验证，当前 `list_source_filings()` 不能作为
   investment 的安全替代。
7. `_build_production_services_provider()` 是 Host 已构造、composition publication 之前唯一
   合理 registration 点；其 job/schedule stores 共用 phase-1 session factory。
8. 0004 schedule occurrence 的 snapshot 包含静态 idempotency key/payload，因此没有 2.3
   额外 contract 前不能制作每次 fire 都唯一的 source request。

## 3. A/B overlap 时序：implementation/review 必查

```text
A 获得 Job attempt A 和 source operation generation 1
  -> PG 不持锁地调用 Fins（provider read-only，Fins document identity 幂等）
  -> A 的 Job lease 过期；2.2 recovery 可领取 attempt B
  -> B 锁 operation head：若 generation 1 未过期 => WAIT，不调 Fins
  -> 到期后 B 取得 generation 2；A 之后的 terminal conditional write = 0 rows，不能写 health/outbox
  -> B 执行/提交 terminal receipt + head + snapshot + semantic outbox，一次 PG transaction

若 A 在 Fins 返回后、PG transaction 前崩溃：head 到期后 B generation reclaim；这是最多三次
attempt 的有界 provider read，不能宣称 exactly once。若 A 在 PG terminal 后、Job completion 前
崩溃：B 从 terminal head/receipt 重放，无 Fins 调用。
```

`source_sync_operations` 是 execution state 真源，不复制 receipt/business result；
`source_sync_runs` 是 immutable terminal result 真源；health current truth 只有
`source_health_states`。每类事实恰有一个 owner。

## 4. 实现顺序与细粒度验收

1. 先实现 pure source/Fins DTO、canonical parser/builder 和 connector registry；确认 unknown,
   deferred, form, stale, rate, cancel 都为 closed typed result。
2. 再实现 Fins direct worker boundary；测试显式证明未调用 `submit`、Host operation 或 Fins
   storage 从 investment import。
3. 实现 0005 + ORM + real PG repository，先验证 catalog/RLS/grant/trigger，再验证 operation
   acquire/expiry/fenced stale commit。
4. 在 source service/handler 接 transaction command，最后才扩 registry seal/startup
   composition；启动只在 handler registration 成功后 publication。
5. 最后真实 PG16 + offline Fins fixture 制造两个 crash cut point，跑 static/coverage/docs gates。

代码生成不得把步骤 1--5 合并成一份跨层 god-module；不应在任何中间阶段创建真实 provider
network test 或新 CLI/web route。

## 5. 精确 reviewer prompts

DeepSeek 与 MiMo 独立 review 至少要分别证伪下列主张：

- operation generation 是否确实阻断旧 attempt 在 lease expiry 后提交 health/outbox；
- B 是否在 active 未到期 head 时完全不触 Fins/provider；
- 可重放 terminal receipt 是否与 Job payload SHA、job run/attempt FKs 和 locator hashes 都闭合；
- `source_sync_runs` 的新 row 是否绝无 UPDATE，old row 的 migration compatibility 是否成立；
- Fins Worker API 是否完全绕过 Host，但未让 investment 读 Fins storage；
- complete/partial/failed/cancelled 与 `healthy/degraded/failing/disabled` 是否没有混同；
- disabled 是否无自动 re-enable，operator authorization residual 是否诚实标注；
- outbox 是否只保留 PG semantic event、dedupe 是否在恢复后的新 epoch 可再触发；
- startup 是否只有一个 Fins runtime、Host、session factory/lifecycle，registry 是否 sealed exactly one；
- real PG fault tests 是否真正覆盖 A/B overlap、Fins-before-PG 和 PG-before-Job cut points。

## 6. STOP 条件与残余 owner

若 Fins 不能从自己 runtime/storage 产生 verified locator 和 source-observed time；如果实现需
nested Host、第二 lifecycle、修改 0001--0004、扩张 Job request 暴露 token/fence；若产品坚持
本 Slice 内循环 schedule；或 real provider network 是唯一测试路径，则实现必须 STOP 并回报
Controller。

残余所有者不在本 Slice 隐藏处理：provider at-least-once read/Fins connector owner；动态
schedule template/Schedule owner；outbox delivery/7.6；operator auth/RBAC/7.1；RSS/industry/
manual bytes/future connector；Fact extraction/review/future evidence slice。

## 7. 交付前必填 completion report

实现者必须报告：实现 commit SHA、实际文件清单、0005 revision/head、sealed registry job
types/count、Fins 无 Host 调用证据、PG16/Fins fixture/coverage/pyright/ruff/docs 命令结果、
两个 crash cut point 的结果、是否触发 STOP、全部 residual owner；Controller 收到 DeepSeek
和 MiMo 两份独立 accepted review 后，才可推进 Slice 2.3 code acceptance。
