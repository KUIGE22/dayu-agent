# Slice 2.3 Item 6 Job Request Identity — Controller Plan Acceptance

- 日期：2026-08-14 06:25:55 +0800（Asia/Shanghai）
- 状态：**CORRECTIVE PLAN CONTROLLER ACCEPTED / FRESH SAME-NEW-SHA DEEPSEEK V4 PRO + MIMO ROUND 4 PASS OPEN H/M/L=0/0/0 / ALL 12 FINDINGS ACCEPTED+CLOSED / LOCAL ACCEPTED CORRECTIVE-PLAN COMMIT NEXT / ITEM 6 AND EXACT-12 PREREQUISITE IMPLEMENTATION FROZEN UNTIL COMMIT SUCCEEDS**
- Gate：Gateflow Item 6 job-request-identity corrective-plan acceptance bookkeeping；本文不宣称本地accepted plan commit已经创建
- 分支：`codex/investment-platform`
- HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`
- Index preflight：empty
- Boundary preflight：写回前worktree精确为本轮target/master/fix、formal、MiMo R1–R4与DeepSeek V4 Pro R3–R4共十path；acceptance path原先不存在，无其它dirty path
- 外部边界：未改production/test/README/workflow；未运行test、PostgreSQL、Docker、network、provider、model、Broker、交易或部署；未stage、commit、push或创建PR

## 1. Reviewed semantic snapshot

Fresh Round 4两路独立review共同锁定下列pre-acceptance metadata字节。review结论只覆盖这组三份semantic
candidate，不能由§6 metadata写回后的closure SHA替代：

| Reviewed file | SHA-256 | Lines |
|---|---|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `dc210d4a3a6c0c4b7f5521e6e372f5ec0cc7e236c9c09a52460ad6847d432fa0` | 3564 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `83680025d05881ef535c124120e39aefd3c964615abab237aca0b54f30acef62` | 4498 |
| `docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md` | `9066d39e98525e4d4a068ae03fe54679fc5690e1da72490fcec0ad92e8a697e1` | 331 |

Controller在metadata写回前保存了三份byte-for-byte snapshot并重新计算上述SHA/行数，三项全部匹配；branch、HEAD与
empty index亦无漂移，允许进行metadata-only closure。

## 2. Fresh independent Round 4 closure

| Reviewer | Artifact | Artifact SHA-256 | Lines | Model / route evidence | Conclusion |
|---|---|---|---:|---|---|
| DeepSeek V4 Pro | `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round4.md` | `9a41173eb6c88c17f3bb0e0e8a1e0f21d7b511c18a8bff44977f82d71fdac378` | 93 | artifact记录official DeepSeek Anthropic endpoint（Controller核验）；model `deepseek-v4-pro[1m]` | `PASS / open H/M/L=0/0/0` |
| MiMo | `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round4.md` | `8bb545597568e836447249fbd7620cc15d1d2cb9fbd46661e29f8cfcc816c393` | 563 | artifact本身未记录actual route/model；Controller在clear/dispatch前于pane `remote-cli-session:2.1`的`/status`观察到Anthropic base URL `https://api.xiaomimimo.com/anthropic`与model `mimo-v2.5-pro` | `PASS / open H/M/L=0/0/0` |

两份artifact相互独立、锁定§1完全相同的target/master/fix identity，均无finding、blocking open question或
deferred risk。MiMo route/model只作为Controller-observed dispatch provenance，不冒充artifact-contained fact；MiMo artifact的
Round 3 identity占位不具实质性，权威R3 identity由§3精确补记且不编辑immutable R4。

## 3. Immutable review provenance and superseded history

下列review artifact在acceptance前后均保持immutable；任何后续字节变化都会使本acceptance失效：

| Artifact / lineage | SHA-256 | Lines | Immutable status |
|---|---|---:|---|
| Formal `docs/reviews/plan-review-20260813-234659.md` | `4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0` | 227 | `FAIL / open H/M/L=2/3/0`；五项accepted、现closed |
| MiMo R1 `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md` | `ac1193fe28cd02a3a06df5ba1ae67f380dd22e5f9239a159dd2903025cc0ba22` | 218 | self-claimed PASS0；`SUPERSEDED / REJECTED / IMMUTABLE`，漏后续1H/1M |
| MiMo R2 `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round2.md` | `dc849d2d60184beb0dcaeeaf20711435706804b40995fdc4ce03a19062d2b139` | 312 | self-claimed PASS0；`SUPERSEDED / REJECTED / IMMUTABLE`，漏后续2H/2M |
| MiMo R3 `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round3.md` | `624c2690b86e616e9aaae74abca5a326713e68ffa02948049e89b80abc070390` | 539 | old-triple PASS0；`SUPERSEDED / REJECTED / IMMUTABLE`，未覆盖DSV4P R3 Low fix |
| DeepSeek V4 Pro R3 `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round3.md` | `e8739eecd9c505e607efe94f0d70f6464ec6c8d8c7dd5be37d5b5809dfece103` | 104 | `FAIL / open H/M/L=0/0/1`；唯一Low accepted、fixed、现closed；artifact保持FAIL |
| MiMo R4 | `8bb545597568e836447249fbd7620cc15d1d2cb9fbd46661e29f8cfcc816c393` | 563 | current `PASS / open H/M/L=0/0/0` |
| DeepSeek V4 Pro R4 | `9a41173eb6c88c17f3bb0e0e8a1e0f21d7b511c18a8bff44977f82d71fdac378` | 93 | current `PASS / open H/M/L=0/0/0` |

MiMo R1/R2/R3的PASS不能跨candidate SHA使用；DeepSeek V4 Pro R3的FAIL也不得被改写成PASS。Round 1/2
DeepSeek actual-route HTTP 402尝试无artifact、verdict或PASS，不计入任何gate。

## 4. Controller finding adjudication

| Finding | Severity | Controller decision | Closure |
|---|---|---|---|
| `S23-I6-PLAN-01` | High | accepted | immutable original enqueue time与mutable retry eligibility已分离，closed |
| `S23-I6-PLAN-02` | High | accepted | request payload schema identity成为durable fact，closed |
| `S23-I6-PLAN-03` | Medium | accepted | lookup收窄为可观察definition scope，closed |
| `S23-I6-PLAN-04` | Medium | accepted | Schedule owner唯一cron validation-only seam与ordering已闭合，closed |
| `S23-I6-PLAN-05` | Medium | accepted | schema-valid conflict与malformed persisted row分流，closed |
| `S23-I6-REDTEAM-R2-01` | High | accepted | prerequisite scope/CI/README ownership经后续R3收敛为exact12，closed |
| `S23-I6-REDTEAM-R2-02` | Medium | accepted | fingerprint前strict canonical bytes admission，closed |
| `S23-I6-REDTEAM-R3-01` | High | accepted | workflow mutation延后Item 8，前两级zero diff，closed |
| `S23-I6-REDTEAM-R3-02` | High | accepted | new enqueue pre-session canonical admission由PostgresJobStore唯一拥有，closed |
| `S23-I6-REDTEAM-R3-03` | Medium | accepted | prerequisite retry test只读durable columns，不越界future lookup，closed |
| `S23-I6-REDTEAM-R3-04` | Medium | accepted | `tests/README.md`与`dayu/investment/README.md` owner完整，closed |
| `S23-I6-DSV4P-R3-01` | Low | accepted | backfill sensitive-key矩阵与migration-local/domain pure equivalence pin已闭合，closed |

精确十二项finding全部`accepted / closed`。没有`rejected-with-reason`、`deferred-with-owner`、
`needs-more-evidence`、unclassified finding或blocking open question。

## 5. Accepted mechanical contract and residual owners

Accepted candidate的机械账本保持：

- 0006 prerequisite：exact12 writable paths（production/test 10 + docs 2）与12项新增tests；两份workflow和root README保持zero diff；
- `COVERAGE_OWNER_TESTS`：44 exact keys（29 tracked-existing + 15 planned-new）；
- concrete PG/migration owners：6；
- final isolated PG/source-job/MinIO/Redis lanes与aggregate ignores：9，只在Item 8 final CI/docs gate闭合；
- global exact named catalog：174（历史159 + 15 new；两个rename不增量）；
- Item 6 main：exact20 writable paths / 51 tests；必须等待prerequisite accepted commit后的新clean baseline。

既有residual不因plan acceptance消失，owner/destination如下：

| Residual | Owner / destination |
|---|---|
| provider读取非exactly-once | Fins document identity + Source operation idempotency；后续provider reliability |
| Source terminal与Job terminal双事务窗口 | Source recovery/idempotency contract；后续platform reliability |
| Redis wakeup可丢/重复/乱序 | PostgreSQL truth + worker polling；Redis只hint |
| disabled Source仍可能生成scheduled no-op Job | operator schedule-disable workflow |
| RSS/industry/manual connector不可执行 | later Source connector slices |
| semantic alert只持久化 | later Telegram/Obsidian delivery slice |
| Fins date-only freshness | provider metadata/freshness follow-up |
| owned-thread无wall-clock上界 | platform reliability timeout configuration/fault gate |
| Job/Schedule repository public failure无typed code | independent typed repository-error contract work unit |
| 0006对不可证明legacy row fail closed | independent legacy identity migration/public unavailable work unit |

无新增或未分类residual。

## 6. Post-metadata closure identity

Controller只写回header/status、current review/acceptance、revision/current-gate/stop/completion metadata；§1的reviewed
semantic identity永久保留。metadata closure后的三份identity为：

| Metadata-closed file | SHA-256 | Lines |
|---|---|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `c95a74d4b62dcf3a9a828fb4461798d555b2b5990930ea79cf16e8946e428659` | 3583 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `0e85bc99d76f30b06551ba5785c9dbad01bac8b714437599394791d081c97ead` | 4512 |
| `docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md` | `99a03329c491e7d7e1e10f700167b3edebc2a9df58a09c0d5bdf2d65fe9565ac` | 340 |

本acceptance artifact有意不自引SHA；其final identity只在完成后的只读Controller handoff中报告。

## 7. Semantic reverse audit

使用metadata写回前保存的byte-for-byte snapshots执行反向审计：

- target §1–§16 pre/post逐字节相同，区域SHA-256均为
  `50381e58b46a2e8550f9f15e9e79b002a32c5c234657d9b60497b2f17703c636`；变化只在header与§17.1 current bookkeeping；
- fix §1–§6 pre/post逐字节相同，区域SHA-256均为
  `19b58382038c64ac4e24b3021298b3316a7fdc549c489a80ad0e57098dc47115`；变化只在header、§7 stop state与§8 completion metadata；
- master在精确mask顶部status、2026-08-14 current revision entry、Slice status、current corrective truth、current
  review closure与current gate/next entry六个bookkeeping块后，pre/post逐字节相同，normalized SHA-256均为
  `2d091923da1bbaf43a2d1da727388199073691005441c8db10649a1c02026d55`；
- 因而0006 schema/admission/downgrade、lookup/cron/schedule合同、exact12/44/6/9/174、Item 6 exact20/51、STOP与
  residual语义均未被acceptance metadata改写。

## 8. Exact future local accepted-plan commit scope

Controller下一步必须逐path显式stage下列exact十一path；禁止glob，当前bookkeeping没有stage：

1. `docs/plans/2026-08-10-investment-platform-restoration.md`
2. `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
3. `docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md`
4. `docs/reviews/plan-review-20260813-234659.md`
5. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md`
6. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round2.md`
7. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round3.md`
8. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round4.md`
9. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round3.md`
10. `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round4.md`
11. `docs/reviews/plan-acceptance-20260814-slice-2.3-item6-job-request-identity-codex.md`

任何缺失、额外production/test/README/workflow、其它plan/review、unknown path或index漂移都立即STOP。推荐commit
message：`gateflow: accept slice-2.3 item6 job request identity plan`。

## 9. Freeze and next gate

- 当前index仍须empty；本acceptance未stage、commit、push或创建PR。
- 当前唯一未满足的deterministic gate是§8 exact十一path local accepted corrective-plan commit；owner为Controller。
- 只有该local plan commit成功后，才可dispatch exact12 implementation prerequisite；不得直接进入Item 6 main。
- prerequisite完成focused/coverage/static/PG/mechanical validation、独立deepreview/fix/re-review与单独local accepted commit后，
  才以新clean baseline恢复Item 6 main exact20-path writer。
- 未授权push、PR、merge、部署、真实provider、network、model、Broker、交易或资金动作。

**结论：ITEM 6 JOB REQUEST IDENTITY CORRECTIVE PLAN CONTROLLER ACCEPTED；FRESH SAME-NEW-SHA DEEPSEEK V4 PRO +
MIMO ROUND 4 PASS OPEN 0/0/0；ALL 12 FINDINGS ACCEPTED+CLOSED；LOCAL ACCEPTED CORRECTIVE-PLAN COMMIT NEXT；
COMMIT成功前ITEM 6与EXACT-12 PREREQUISITE IMPLEMENTATION继续冻结。**
