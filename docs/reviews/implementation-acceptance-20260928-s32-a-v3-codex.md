# S32-A V3 implementation — Controller bounded acceptance

- 实际裁定时间 UTC：`2026-09-28T01:56:47.099593+00:00`；Controller：root。
- 冻结 cwd：`/Users/wsk/workspace/dayu-agent`；branch：`codex/candidate-intake-v3`；切片接受前 HEAD：`9f85fe085458e333cae41425751a4dad1aa297c5`；aggregate base：`afe53dd2c544767dfbf017b2ce1e11cdd66dc32a`。
- 结论：接受 S32-A V3 的本地实现与有界代码审查；fresh open H/M/L **0/0/0**，M1 closed。该文件是本次 slice Controller decision；aggregate/PR review/remote delivery 须分别取得新的证据与接受记录。
- 依据用户持续运行指令推进普通审查、提交与 draft delivery。shadow-only 业务边界继续有效。

## 绑定输入与正式裁定

| 输入 | SHA-256 | bytes / LF |
|---|---|---:|
| `docs/plans/2026-09-28-slice-3.2-candidate-intake-v3.md` | `04cfb13a556fdec21fdba9bcebcad044133ae0364a089ef8487230687aec67ed` | 33858 / 151 |
| `docs/reviews/plan-review-20260928-084010.md` | `b4fce369dcb05ef62a491436b39e4a504a95b12028a32e76744c4cbef0c59f12` | 20712 / 100 |
| `docs/reviews/plan-acceptance-20260928-s32-a-v3-codex.md` | `8b44bf69b480a91232d51ae0560f682860bfb9ff5c810d010076a7af7029f1af` | 5044 / 33 |
| `docs/reviews/implementation-20260928-s32-a-v3-codex.md` | `ecb3a709f2150202e1c2b99ee6a662048618f3e2db3d905b860984b7e2aa7b38` | 27972 / 218 |
| `docs/reviews/s32-a-v3-final-disk-freeze-v1.json` | `4521eaa30ac07ad50be0e84b42a88c436ebeee4499e0e5ab44cd020f1d5a1b4f` | 84287 / 3060 |
| `docs/reviews/code-review-20260928-094907.md` | `be2b48c8ca0a46a260aecb547fb059a3ca7d2e10c6b19cf4cb58d3c6b6d79728` | 37945 / 249 |
| `docs/reviews/code-review-20260928-095149.md` | `a43b904fdcad7e22992096b0690f7ea3c0f123ad093558fa84e81e4b0f6b8ba6` | 7605 / 60 |

- Controller 已完整读取正式报告及 NEW 锚点勘误，核对 source 调用链与证据身份，采用勘误后的引用。原正式报告逐字节保留。
- 两处更正是 review metadata 错误：locator parser 由 `dayu/fins/domain/evidence_locator.py:956` 支持；FinsService validate/read 的实际入口是 `dayu/services/fins_service.py:210` 与 `:227`。不会把 `service_runtime.py:956` 的 dataclass 字段或 `fins_service.py:193` 的 resolve 方法作为这些断言依据。
- M1：历史合法深 JSON 可能令 psycopg projection 触发 RecursionError，原 preview fresh 0/1/0；production `_project` 已将该错误收束为 storage failure，先于 request conflict 判断。最终四个 corrupt-history XML cases 均通过；正式 reviewer 复核后 closed。旧失败与中间四例 session witness 无独立持久日志，只按报告限定范围引用；实际 620-case 最终镜像是接受依据。

## 最终本地验证与身份核验

- 最终 pytest：**620 passed / errors 0 / failures 0 / skipped 0**；400 unit + 220 PostgreSQL（141 new intake + 21 evidence + 1 auth + 57 platform）；stdout 241.38s，XML 241.376s。使用真实 PostgreSQL 测试 fixture，未用 SQLite 替代。
- 最终 19 个受影响 Python 文件 pyright：0 errors / 0 warnings / 0 informations；Ruff E4/E7/E9/F/I：All checks passed；git diff --check 通过。具体命令、XML case、coverage 缺失行/分支与五份镜像均在冻结文件和 implementation report 中逐项保存。
- 11 个受影响 production 文件的 statement coverage 均 >=80%；最低 0008 为 71/80=88.75%。受影响文件合计 statement 1614/1733=93.1332948644%，branch 470/580=81.0344827586%，combined 2084/2313=90.0994379594%。扫描到的三个目录整体覆盖率不作全项目覆盖率或全部分支通过的证据。
- 本次写入前重新以 O_RDONLY|O_NOFOLLOW / regular / nlink1 / actual EOF / pre-post fstat+lstat stable 核验 freeze 的 78 个 distinct 绑定文件；SHA/bytes/LF/CR/terminalLF 和所有捕获 descriptor 均匹配。27 个历史 plan base blobs 与 41 个 upstream 在 base/HEAD 的真实 Git blobs 一致，五组源证据和 durable mirror 逐字节相等。
- implementation report 的 terminal LF=false 予以保留；freeze 的 HEAD、状态、权限字段是 author 捕获时的历史事实，不回写成为本次接受状态。正式报告和勘误 SHA/bytes/LF 新鲜核验通过。索引在本次 decision 写入前为空。

## 接受的实现范围（22 source paths）

| source | SHA-256 | bytes / LF |
|---|---|---:|
| `dayu/investment/domain/evidence.py` | `c515084ffa9147216e517ae180a094a912deabe09c6f469c26910a0ca10b78e6` | 79326 / 2401 |
| `dayu/investment/domain/candidate_intake.py` | `070e1b2fdc5d5e53d254b17b88febf3e17444aaeb16c5c7183e6cb0e422288f7` | 11413 / 325 |
| `dayu/investment/domain/candidate_parsing.py` | `f630677f2ac421f0480ee056bbc39590bd0543de4dfd6d7ef46980f9199f4a81` | 8364 / 234 |
| `dayu/investment/storage/candidate_intake_protocols.py` | `b4a649b13d89f25e98969f99700c4888feb1ba9e6a4d8efaadb598c4b6380076` | 1786 / 47 |
| `dayu/investment/storage/models_candidate_intake.py` | `9979f372c20257306b6ee1223515809fe3149c41b2cd66d5c0c34fb03e87a104` | 4313 / 77 |
| `dayu/investment/storage/postgres_candidate_intake.py` | `675f41964c8362ec21860915658b2d0bc1305bf8bfea84d732a9478cb0a10009` | 15328 / 335 |
| `dayu/investment/storage/migrations/versions/0008_candidate_intake.py` | `4f7630abd3aba54a38de6d7558e139ab0c8571f536bff4c166ecddb63f38ec55` | 15163 / 259 |
| `dayu/investment/storage/__init__.py` | `4d7f38c7a52fa13d452e2f089f9da5f5b146c1c6d847471259bf719ab9462995` | 2779 / 92 |
| `dayu/investment/storage/db.py` | `dcaf3b7d99be2508a596582c928812c5615ed33158378ae0a12339ec05c8efc2` | 4491 / 128 |
| `dayu/services/investment_research.py` | `d95fad970b26e49f9e0428379bdcacdcab3241aa5e720365d686770969374e97` | 9917 / 236 |
| `dayu/services/protocols.py` | `92ed4fc398f6b6e3437a92920d9ee128571ec40b1f387d7048570e76b7dd3852` | 12952 / 423 |
| `tests/investment/test_candidate_parsing.py` | `5eca1104ed4c11f029884c715fd81ab3c5f3ff7112a6e785dfe5cbbe3795eb41` | 9266 / 273 |
| `tests/investment/test_candidate_intake_contract.py` | `eb14c21583a10bc212d981386c504a3ca490afb722aabb23e4e9910407e087d1` | 6604 / 186 |
| `tests/investment/test_candidate_intake_service.py` | `0daf40c9b7326929c824038dd4ff6af1156ddc2f55fe47ef309286648f15eaac` | 20091 / 590 |
| `tests/investment/test_evidence_storage_contract.py` | `151163717af2641576b5db718829950b0414e4badaa6083cd64405d6cf4068ed` | 11727 / 293 |
| `tests/investment/test_platform_migrations.py` | `a17ab07d7afb6612db61b2376c3a9db150b9b2b93b83a89309cb47bb80f06b89` | 110518 / 3194 |
| `tests/integration/investment/test_postgres_candidate_intake.py` | `c35729f448df22d0868ff43001faf81d184a64ce93cc43a4207c5ecfd1baa7fa` | 69877 / 1818 |
| `tests/integration/investment/test_postgres_evidence.py` | `496c7006848399c95086127d646c53f008ff30b7d0c0d73ed74d1050ba7915db` | 101474 / 1978 |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `e2ada8052c8d06417bb7a0bdfbf18e3eeede08202dc2833c1b773a122fd6cc2c` | 313563 / 6941 |
| `dayu/README.md` | `0000f0ec44963c6c7b4576b9d9b5abb2b14fadcc55d70c4fcf65e0890d9b8c15` | 65599 / 1302 |
| `dayu/investment/README.md` | `1e7ac690e64b5af885f12ce1f31483275796196edc9bfaf94045890d68f3a64c` | 29741 / 410 |
| `tests/README.md` | `994e86a04a6b98219c6e07714fdce2df05762d77e1beac51fb86daa49f39e8d4` | 137780 / 654 |

- 单一 InvestmentResearchService → strict parser → public Fins locator/content identity → 原子 candidate+receipt；同 tenant+operation 历史闭包和全 request identity 优先于重新解析/读取，五个 exact unique constraints 的 race relookup 受限且 storage corruption 收束。
- 0008 独立追加 schema、metadata 25 / physical 34 / private 31 / public 3；旧 0001–0007、S31 evidence/auth/Fins/Host/runtime/CLI/workspace migration 与架构边界保持冻结。空库 downgrade、RESTRICT、ACL/lock/catalog 漂移的全事务回滚由最终测试及静态审查支持。旧 0007 catalog 测试显式维持旧版本预期。

## Residual risk 的具体处置

- 0008 九个 admission 防御行/部分 branches、repository/service 的报告列明分支尚无逐条动态覆盖；采用已有动态 gate 与完整静态 call-chain 审查作为本次有界接受依据。未观察到可复现缺陷；如出现具体边界风险，由相应 storage/service owner 在后续工作单元补证与修复。
- KeyboardInterrupt 已有 unit witness；SystemExit/async cancellation/DB flush BaseException 的逐类动态测试未执行。Python context/transaction 的 propagation/rollback 已静态审查，不能据此宣称所有取消情形动态验证。
- FinsService 真实 owner 静态链与 local Fins protocol fake 的动态证明分开；本次不宣称真实网络 backend 的业务新鲜度。后续 promotion 与消费仍须重新 validate/read back。
- S32-B promotion、grant/action authority、token-derived actor 与 PIT/source-time 语义须单独规划并经过审查；该责任归后续 S32-B/Phase 7.1，当前 candidate intake 无权伪造或推定这些事实。
- aggregate/PR review/remote CI/draft delivery 待后续独立 gate；目前不宣称 CI success、PR delivery、whole Slice 3.2 或 shadow-only 业务闭环完成。
- V8 规则/constructor 与十种 shape 完整递归闭包仍有自身独立 gate，当前 slice 接受不授予 effective H2、H1/V13/V17 或 S5/D0/Gate 权限。

## 提交 allowlist 与历史保留

- 下一 slice 接受提交仅含上述 22 source paths、implementation report、final freeze、五个 validation mirrors、正式 code review、NEW correction、当前 Controller decision，共32文件。接收 commit identity 将由后续 aggregate report 在实际 commit 后绑定；该文不嵌入自身 SHA 或未知 commit。
- `docs/reviews/implementation-20260928-s31-aggregate-retry-fix-v2-codex.md` 是保留的 untracked 历史文件：`d46cc852c7dc59667c751a403d932a4eaf0a1d5b05f12b5c1d293f278f0b8b2b` /4456B/32LF，不加入本切片提交。
- aggregate 比较以 afe53 为 base，预计包含已接受 plan 链6文件及本切片32文件；以实际 Git names/tree 为准。

**Controller result：S32-A V3 slice IMPLEMENTATION_ACCEPTED；fresh open H/M/L=0/0/0；M1 closed；后续按 aggregate → draft PR → PR review/remote identity → closeout 推进。**
