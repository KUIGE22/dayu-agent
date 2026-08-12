# Slice 2.3 Item 6 Recovery Errors / Receipt Owner — Controller Plan Acceptance

- 日期：2026-08-12 23:21:05 +0800（本机系统时钟）
- 状态：CORRECTIVE PLAN ACCEPTED / FRESH SAME-SHA DUAL PASS OPEN 0/0/0 / LOCAL ACCEPTED ITEM 6 CORRECTIVE-PLAN COMMIT NEXT / ITEM 2 IMPLEMENTATION FROZEN UNTIL ITEM 6 COMMIT SUCCEEDS / ITEM 1 ACCEPTED AT 4CFB932
- Gate：Gateflow Item 6 corrective plan acceptance bookkeeping；本文不宣称本地accepted plan commit已创建
- 分支：`codex/investment-platform`
- Initial bookkeeping HEAD（historical）：`3f0de579e1c95b428b61e046bae2a0583a4e76d6`
- Metadata calibration HEAD / accepted Item 1 commit：`4cfb9326a2f35266cf238b6617507f0f6c5bb030`
- Metadata calibration index：empty
- Item 1 fifth deepreview：`docs/reviews/code-review-20260812-232753.md`，artifact SHA-256 `3ebc80f3892bb0b2857303ae72833ea0e48596ac4be63fade66c1a52f48b8f80`，`PASS / open H/M/L=0/0/0`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Master：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Fix：`docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md`
- 外部边界：未运行network/provider/model/Broker/trading/deploy；未stage、commit、push或创建PR

## 1. Reviewed semantic snapshot

两路review共同锁定下列pre-acceptance metadata字节；这些SHA是review结论唯一覆盖的semantic candidate，不能由
metadata写回后的closure SHA替代：

| Reviewed file | SHA-256 | Lines |
|---|---|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c` | 2942 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1` | 4296 |
| `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md` | `56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2` | 126 |

## 2. Fresh independent reviews

| Reviewer | Artifact | Artifact SHA-256 | Conclusion |
|---|---|---|---|
| DeepSeek Flash | `docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-deepseek-flash.md` | `5eacc319da9765d436c8f405d44b4b9eacb576787d5257ae6c8c20d6803fb27c` | `PASS / open H/M/L=0/0/0` |
| MiMo | `docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-mimo.md` | `fe430e199f0f8b050061060c60090243cdc670f02e400ee36bf5563c7a45d37e` | `PASS / open H/M/L=0/0/0` |

两份artifact相互独立、锁定同一组三份reviewed semantic SHA，均无finding、open question或deferred risk；
Controller接受该same-SHA candidate。review artifacts在bookkeeping前后均保持只读，任何后续字节变化都会使本
acceptance失效。

## 3. Controller acceptance decision

1. 接受`S23-I6-RECOVERY-ERROR-01`：无typed code的`JobRepositoryFailureError`与
   `ScheduleRepositoryError`在Source facade的Job/Schedule lookup/enqueue/ensure路径统一精确映射
   `SourceServiceUnavailableError(unavailable)`；禁止message/cause/SQL/row-shape猜测。Source自有typed
   `SourceSyncRepositoryFailure(persisted_invariant)`不变。
2. 接受`S23-I6-RECEIPT-OWNER-02`：`JobService.get_by_idempotency_key`只read-only delegate并返回
   `JobIdempotencyRecord | None`；只有`InvestmentSourcesService`在strict Source payload、caller intent与
   record identity验证全部成功后构造`READY/idempotency_reused=True` receipt。
3. accepted scope仍是docs-only corrective contract；不新增public surface，不扩大production/test write set、
   §11 allowlist、coverage matrix、STOP或其它§1–§17 semantic合同。
4. 158项named tests保持唯一；本轮metadata写回没有修改任一测试名、allowlist、owner或断言语义。

## 4. Post-metadata closure identity

Controller只把status、gate、review links、acceptance metadata与next action写回existing三doc；reviewed semantic
字节另由§1保留。Item 1 accepted commit后的metadata-only calibration继续只更新当前HEAD/Item 1 closure状态，
不改变Item 6 semantic contract。校准后的closure identity为：

| Metadata-closed file | SHA-256 | Lines |
|---|---|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `503b16b83937861e282a1f0473e2161cedc6c46eb0933090b647f74e62040c98` | 2955 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `2e33f6e4921ff80c7af703fd8a30bf1ad4ae2321ab9cf3afa3639c5ace29427d` | 4316 |
| `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md` | `9eb9047d77af78e97bff44c04590eeac584af3817489df5a32f0f9fbb591185c` | 130 |

本acceptance artifact不自引SHA；其final SHA/line count由完成后的只读核验报告给Controller。

## 5. Semantic reverse audit

使用bookkeeping开始前的三份byte-for-byte snapshots执行反向审计：

- target §1–§16 pre/post逐字节相同，SHA-256均为
  `d92455977860b47380eb2fd5c329ef8f1bc257dc2b217352f58724b8a01fe38b`；§17原有prefix逐字节相同，只替换
  最后review gate/next-action metadata；文件头只改status/gate/review/acceptance/freeze metadata。
- fix §1–§5 pre/post逐字节相同，SHA-256均为
  `2a882957e7fd44c0c9948dfbbd2a70a599496753accccd2460051405c79a5aaf`；§6结论之前逐字节相同，只改文件头
  acceptance metadata与最终status/next action。
- master从`## 1`起，在精确mask `Slice status`及`Current gate / next entry`两段metadata后，pre/post逐字节
  相同，SHA-256均为`323e308a853021acd0860e950d5031f056c7183e36f58cc9994f51597cbcb08b`；`## 1`前只改顶部status、
  review/acceptance index与revision bookkeeping。
- 因而implementation contract、allowlist、158项named tests、STOP与residual语义均未被acceptance metadata
  改写。
- Item 1 closure calibration另以pre-calibration byte snapshots锁定四doc：target
  `13629ec32dde66f64f0bf667a95ca31e9db30d977d3509f5fa7163a04a89c9c3`（2951行）、master
  `b23b88b7b8ab1fdbbf0a16ff1ccf04bbaef1375f672e96cfb210e5342e350980`（4308行）、fix
  `053a4393390a998e516d37dbd174dd4fb0a42e9552dc526f195b00f4af1efb49`（129行）与本acceptance
  `5e55deabde3cb3105f8c65266ce5d808cf57182b8ca3e39c458007af0c1ebeb0`（101行）。反向审计确认target
  §1–§16逐字节不变，fix §1–§6正文逐字节不变，master掩蔽Slice status/current gate元数据后实施正文逐字节
  不变，本acceptance只改HEAD/Item 1状态、closure identity与freeze/next-action bookkeeping。

## 6. Exact future local accepted-plan commit scope

Controller后续只允许stage下列exact six docs；本bookkeeping未stage：

1. `docs/plans/2026-08-10-investment-platform-restoration.md`
2. `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
3. `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md`
4. `docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-deepseek-flash.md`
5. `docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-mimo.md`
6. `docs/reviews/plan-acceptance-20260812-slice-2.3-item6-recovery-errors-codex.md`

若stage集合出现任何production/test、Item 1 code-review、其它review/plan或未知path，立即STOP，不得创建commit。

## 7. Freeze and next entry

- Item 1第五路deepreview已`PASS / open H/M/L=0/0/0`，本地accepted commit
  `4cfb9326a2f35266cf238b6617507f0f6c5bb030`已成功；本次metadata calibration没有读取或修改
  Item 1 source/tests或任一code-review artifact。
- Item 2 implementation只能在Controller核验exact six-doc scope并成功创建本地accepted Item 6
  corrective-plan commit后恢复；acceptance artifact本身不能解除该commit gate。
- 本地commit成功前不得继续Item 2 implementation；未授权push、PR、部署、真实provider、网络、模型、Broker、
  交易或资金动作。

**结论：ITEM 6 CORRECTIVE PLAN ACCEPTED；FRESH SAME-SHA DEEPSEEK FLASH + MIMO PASS OPEN 0/0/0；
LOCAL ACCEPTED ITEM 6 CORRECTIVE-PLAN COMMIT NEXT；仅ITEM 2 IMPLEMENTATION仍冻结。**
