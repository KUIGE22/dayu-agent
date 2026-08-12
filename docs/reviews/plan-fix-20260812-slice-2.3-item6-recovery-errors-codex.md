# Slice 2.3 Item 6 Recovery Errors / Receipt Owner — Codex Corrective Plan Fix

- 日期：2026-08-12 22:46:01 +0800（本机系统时钟）
- 状态：CORRECTIVE PLAN ACCEPTED / FRESH SAME-SHA DEEPSEEK FLASH + MIMO PASS OPEN 0/0/0 / LOCAL ACCEPTED ITEM 6 CORRECTIVE-PLAN COMMIT NEXT / ITEM 2 IMPLEMENTATION FROZEN UNTIL ITEM 6 COMMIT SUCCEEDS / ITEM 1 ACCEPTED AT 4CFB932
- Gate：Gateflow Item 6 corrective plan acceptance bookkeeping；本artifact仍不是code acceptance，本地accepted plan commit尚未创建
- 分支：`codex/investment-platform`
- Metadata calibration HEAD / accepted Item 1 commit：`4cfb9326a2f35266cf238b6617507f0f6c5bb030`
- Prior accepted corrective-plan commit：`3f0de579e1c95b428b61e046bae2a0583a4e76d6`
- Accepted commit evidence：`2026-08-12 20:52:02 +0800`，`gateflow: accept corrective plan for slice-2.3-source-connectors-health`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Master control：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Target pre-edit SHA-256：`a3e3c6b13d68d2d62d3492a0c6c41a1a732112a62a4ed88e39b2d2122d97c578`
- Master pre-edit SHA-256：`44c78f6615cad61f04678d60f29070851662affe672d0b26d5d97b9cdb672d59`
- Target FINAL FROZEN candidate SHA-256：`e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c`
- Master FINAL FROZEN candidate SHA-256：`9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1`
- Fix FINAL FROZEN candidate SHA-256：`56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2`
- DeepSeek Flash fresh re-review：`docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-deepseek-flash.md`，SHA-256 `5eacc319da9765d436c8f405d44b4b9eacb576787d5257ae6c8c20d6803fb27c`，`PASS / open H/M/L=0/0/0`。
- MiMo fresh re-review：`docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-mimo.md`，SHA-256 `fe430e199f0f8b050061060c60090243cdc670f02e400ee36bf5563c7a45d37e`，`PASS / open H/M/L=0/0/0`。
- Controller acceptance：`docs/reviews/plan-acceptance-20260812-slice-2.3-item6-recovery-errors-codex.md`；本轮只写acceptance metadata，不自称commit已完成。
- 模型路由：本fix只由Codex internal model写入；DeepSeek Flash与MiMo只承担已完成的相互独立plan review，不参与实现。
- Item 1 closure：第五路deepreview `docs/reviews/code-review-20260812-232753.md`，artifact SHA-256 `3ebc80f3892bb0b2857303ae72833ea0e48596ac4be63fade66c1a52f48b8f80`，`PASS / open H/M/L=0/0/0`；本地accepted Item 1 commit `4cfb9326a2f35266cf238b6617507f0f6c5bb030`已成功。Item 2只有在本地accepted Item 6 corrective-plan commit成功后才可恢复。
- 外部边界：未运行network/provider/model/Broker/trading/deploy；未stage、commit、push或创建PR。

## 1. STOP动机与直接证据

Item 6只读code-generation inventory在进入production writer前发现两处合同互相矛盾。两者都会迫使实现者
自行发明public error分支或把Source-owned validation责任塞入generic JobService，因此触发target §15的
“计划合同无法构造即STOP”，动机成立且必须先做docs-only corrective closure。

| Evidence | Exact fact | Plan consequence |
| --- | --- | --- |
| `dayu/investment/domain/jobs.py:233-234` at `3f0de57` | `JobRepositoryFailureError`只是无字段的`RuntimeError` subclass，docstring只承诺closed repository failure，不携带cause细节；没有typed `code` | Source facade不能可靠区分infra failure与persisted tamper；按message/row shape分支会制造未声明public contract |
| `dayu/investment/domain/schedules.py:167-168` at `3f0de57` | `ScheduleRepositoryError`同样没有typed `code`；现有Store虽传内部message，但domain没有把message定义为稳定枚举 | Source facade不能把某些message映射`persisted_invariant`、另一些映射`unavailable` |
| `dayu/services/job_service.py:519-545` at `3f0de57` | 现有`JobService.enqueue`拥有registry gate、Store enqueue与post-commit wakeup publish；它不是Source payload parser owner | 新read-only idempotency lookup若构造receipt或publish，会把查询变成有副作用路径并耦合Source schema |
| `dayu/investment/domain/jobs.py:1057-1089` at `3f0de57` | `JobEnqueueReceipt`构造要求`state is JobState.READY`；`idempotency_reused`表达enqueue语义，不是current Job projection | response-loss recovery可从immutable record重建READY/reused receipt，但构造必须发生在Source intent验证之后 |
| Target pre-edit §3.4 / §5.1 / §5.2 | 一处写`JobService`重建receipt；三处又把Job/Schedule persisted malformed映射`persisted_invariant` | 与generic lookup owner、无typed-code异常和§9 authoritative table同时冲突 |
| Target pre-edit §9 | authoritative downstream table已把`JobRepositoryFailureError / ScheduleRepositoryError`统一映射`SourceServiceUnavailableError(unavailable)` | 最小且owner-correct方案是让§3.4/§5与§9对齐，而不是扩异常public surface |

## 2. Controller finding裁决

### S23-I6-RECOVERY-ERROR-01-已修复-[高]-无typed code的Job/Schedule repository error不能稳定生成persisted_invariant

- **问题类型**：public error contract / failure handling / code-generation blocker。
- **失败场景**：同一`JobRepositoryFailureError()`可来自连接/事务失败，也可来自row parse或persisted drift；
  exception object没有typed discriminator。实现者若按message、cause、SQL或row shape分支，同一public输入会
  随Store内部文案变化而得到不同Source code，且测试只能锁死private implementation detail。
- **Controller decision**：`accepted`。
- **Fix**：Source facade实际调用的全部Job/Schedule lookup/enqueue/ensure路径，对
  `JobRepositoryFailureError`与`ScheduleRepositoryError`统一精确映射
  `SourceServiceUnavailableError(unavailable)`；禁止message、cause、SQLSTATE、row/persisted shape或自由字符串
  分支。caller-intent conflict仍原样传播既有typed conflict；其它§9 typed exception矩阵不变。
- **Source repository carve-out**：`SourceSyncRepositoryFailure(code)`由Source自己拥有closed typed code；其中
  `persisted_invariant`保持原语义，不因Job/Schedule异常收窄而删除或改名。
- **可观测性裁决**：当前public surface诚实地丢失infra/tamper细分。若产品未来必须公开区分，另开typed
  Job/Schedule repository-error contract plan；当前Slice不得猜。
- **验证点**：exhaustive Source mapping test分别向Job lookup/enqueue与Schedule lookup/ensure注入两类异常，
  用不同message/persisted形状仍逐案得到exact `unavailable`，且零追加mutation。

### S23-I6-RECEIPT-OWNER-02-已修复-[高]-JobService lookup与Source facade receipt reconstruction职责倒置

- **问题类型**：architecture boundary / ownership / overcoupling / response-loss recovery。
- **失败场景**：若`JobService.get_by_idempotency_key`直接构造`JobEnqueueReceipt`，它必须理解Source payload
  schema/caller intent，或在未验证caller intent时先声称idempotent reuse；前者违反generic Job owner，后者可能
  把same key/different intent误报为成功。若lookup复用enqueue publish path，还会让read产生wakeup side effect。
- **Controller decision**：`accepted`。
- **Fix**：`JobStoreProtocol`与`JobService.get_by_idempotency_key` exact返回
  `JobIdempotencyRecord | None`；`JobService`只read-only delegate一次并原样返回，不parse Source payload、
  不比较caller intent、不构造receipt、不publish、不读取current Job projection、不mutation。
- **Receipt owner**：`InvestmentSourcesService.enqueue_manual_sync`在lookup hit后依次strict parse persisted
  manual Source payload、比较caller intent、验证record/descriptor/tenant/key/payload/hash/time identity；全部通过
  后才唯一构造`JobEnqueueReceipt(..., state=JobState.READY, idempotency_reused=True)`。current Job state、
  definition active状态及current Source binding漂移仍不是recovery拒绝条件。
- **验证点**：新增exact JobService delegation owner test；manual lost-response test锁定strict validation先于
  唯一receipt construction并证明零publish/零mutation。

## 3. Exact edited scope

本candidate只写三份docs：

1. `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
   - 文件头status/gate/accepted commit/freeze metadata；
   - §3.4 Job idempotency record与receipt owner；
   - §5.1 manual与§5.2 schedule recovery error mapping；
   - §9 authoritative exception table说明（表中既有`unavailable` action不改）；
   - §12 Item 6 ownership文字；
   - §13.1 exact named tests与assertion ownership；
   - §15 STOP、§16 residual、§17 corrective bookkeeping。
2. `docs/plans/2026-08-10-investment-platform-restoration.md`
   - 顶部状态、Slice 2.3 evidence index、revision changelog与Slice 2.3 current gate摘要。
3. `docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md`
   - 本直接证据、裁决、scope与review gate artifact。

明确零修改：production、tests、README、CI、migration、现有review/acceptance artifacts、Item 1 WIP；不新增
public method/type/error code，不扩大§11 production/test/docs allowlist或Item 6 exact write set。

## 4. Test与contract ratchet

- exact named tests由157项变为158项，只新增一个此前没有等价owner的
  `test_job_service_idempotency_lookup_returns_record_without_receipt_reconstruction_or_publish`。
- manual lost-response named test同步改名，显式锁定“strict persisted Source intent validation完成后，只有
  Source facade构造READY/reused receipt”。
- 既有exhaustive Source exception mapping test扩断言，不再新增重复test：四个Job/Schedule调用seam分别注入
  repository failure，统一assert `SourceServiceUnavailableError(unavailable)`且禁止message/shape分支。
- production/test path与coverage owner matrix完全不变；该纠错不扩implementation surface。

## 5. Architecture / best-practice / optimality / overengineering / overcoupling review

- **Architecture boundary**：generic JobService只暴露generic immutable record；Source schema与caller intent仍由
  InvestmentSourcesService拥有，依赖方向不反转。
- **Best practice**：stable public error必须由typed discriminator驱动；没有typed code时选择单一closed
  `unavailable`比解析内部message更可靠、可测试。
- **Optimal solution**：本Slice不需要扩Job/Schedule error hierarchy；统一映射是满足当前用户可见语义的最小
  修复。未来诊断需求用独立typed contract承接。
- **Overengineering**：拒绝为两条recovery路径新增wrapper、adapter、compat alias或第二receipt builder。
- **Overcoupling**：read-only lookup不复用enqueue/publish路径，Source validation不下沉到jobs domain，避免一次
  Source schema变化要求generic Job owner同步修改。

## 6. Review gate与结论

1. target与master已冻结为本artifact头部记录的candidate SHA；任何后续字节变化都使review失效。
2. DeepSeek Flash与MiMo必须相互独立review同一target/master candidate及本artifact；不得互看结论。
3. 两路都必须记录exact SHA、给出`PASS / open H/M/L=0/0/0`，随后由Controller adjudicate/accept；任何finding
   被接受后必须修改candidate并重新执行fresh same-SHA双审。
4. 在双审与Controller acceptance前，Item 1 code/tests、两份code-review artifact与后续Item 2–8 implementation
   全部保持冻结；不得把本fix当作implementation授权。
5. 本pass只做docs机械验证；没有运行pytest/coverage/Pyright，因为production/tests零编辑。exact three-doc
   scoped diff、`git diff --check`、LF/final newline、stale-term scan、158项named-test uniqueness与target/master
   SHA冻结均已通过；artifact自身final SHA由写入完成后的只读hash计算并交Controller。

**结论：REVIEWED SEMANTIC CANDIDATE已获fresh same-SHA DeepSeek Flash + MiMo双路`PASS / open H/M/L=0/0/0`并由Controller接受；下一入口仅为exact six-doc本地accepted Item 6 corrective-plan commit。本文不宣称code pass、commit已完成或ready-to-open-draft-PR。**
