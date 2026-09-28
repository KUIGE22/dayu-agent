# S32-A V3 实施作者报告与最终磁盘交接

## 状态、角色与基线

`IMPLEMENTED_VALIDATED_AUTHOR_REPORT / FORMAL_NONAUTHOR_CODE_REVIEW_PENDING`。这是 implementation-report 作者记录，不是 reviewer 结论。当前切片已完成下述实施及实际验证；正式非作者 code review、Controller 实现采纳、accepted slice commit 与后续交付尚待开展，本报告不授予其 PASS 或 Gate 权限。

cwd `/Users/wsk/workspace/dayu-agent`；branch `codex/candidate-intake-v3`；HEAD／accepted-plan commit `9f85fe085458e333cae41425751a4dad1aa297c5`；S31 delivery base `afe53dd2c544767dfbf017b2ce1e11cdd66dc32a`。本阶段只读最终 source/证据，新建本报告、`docs/reviews/s32-a-v3-final-disk-freeze-v1.json` 与五件 durable 镜像；未修改 production/tests/README/Git，未重新运行 PG，未 stage/commit。采用根 AGENTS 的中文、严格类型、职责文档规则与 gateflow 的 implementation artifact/residual-risk 结构，不启动或重排 Controller 门序。

Controller 本轮另有只读远端会话见证：S31 PR #3 为 OPEN、draft、unmerged，head afe53、statusCheckRollup=[]。这不是 CI PASS、已合并或 shipped；本作者没有运行网络命令。后续 S31 合并/rebase 与 S32 交付保持各自门序。

## 已采纳输入与范围

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `docs/plans/2026-09-28-slice-3.2-candidate-intake-v3.md` | `04cfb13a556fdec21fdba9bcebcad044133ae0364a089ef8487230687aec67ed` | 33858 | 151 |
| `docs/reviews/plan-review-20260928-084010.md` | `b4fce369dcb05ef62a491436b39e4a504a95b12028a32e76744c4cbef0c59f12` | 20712 | 100 |
| `docs/reviews/plan-acceptance-20260928-s32-a-v3-codex.md` | `8b44bf69b480a91232d51ae0560f682860bfb9ff5c810d010076a7af7029f1af` | 5044 | 33 |

三件均读至实际 EOF 并与 HEAD blob 相等。独立计划复审 fresh H/M/L 0/0/0 与 Controller 仅采纳 V3 的 S32-A 单个行为和允许文件；不证明实现、晋升或完整业务闭环。旧 V1 FAIL、V2 与其修复链按已提交 Controller 文档保留原字节。

实核 git tracked diff + untracked：**11 production Python + 8 modified/new test Python + 3 README = 22 件**。production 为4修改/7新增；tests 为4修改/4新增。8 tests 精确见 source 表；原 architecture guard/evidence-domain/auth test 属执行及冻结的未改 upstream，不算“新增实现”。`tests/investment/test_architecture_boundaries.py` 未修改，不放宽 escape/docstring guard。

另有历史 untracked `docs/reviews/implementation-20260928-s31-aggregate-retry-fix-v2-codex.md`，SHA `d46cc852c7dc59667c751a403d932a4eaf0a1d5b05f12b5c1d293f278f0b8b2b`，4456B/32LF：不属于新实现、不修改、不 stage。temporary SQL fragment、catalog probe、旧 coverage 不作为本次 durable implementation artifact。

## 实施计划项与 owner

| V3 部分 | 实际行为及边界 |
| --- | --- |
| §3 可信 Service | `InvestmentResearchService.ingest_candidate(scope, context, raw_output)` 显式注入 Identity/CandidateIntake/Fins Protocol 和 UTC clock；按明确 company/security IDs 配对，ticker 原样一致。没有 Agent 调用、Session/ORM/Fins storage handle 或新 runtime registry。 |
| §4 strict JSON | 纯域九键 `fact_candidate.v1`；四 value arm、五 locator arm；复用 Fact bounded labels、38/12 finite Decimal、strict UTC/date、period 配对，保留定点scale与负零。拒绝 BOM/UTF-8、nested duplicate、float/constants、unknown/missing、surrogate/NUL、深递归及 raw/canonical 1MiB；闭合错误不泄露 raw。 |
| §5 owner/readback | 公共 locator parser → Fins validate → citation readback，完整 locator 与实际 bytes SHA 比较。片段未定位按固定业务码；owner/I/O/unknown/非法 return/clock 为 dependency unavailable、零写入。历史 receipt 在 parser/Fins 前恢复；witness 是一次观察，不承诺 commit/未来 freshness。 |
| §6 纯域／窄协议 | Context/RejectionCode/Witness/RecordRequest/Receipt 不依 Fins/service/SQL；协议仅 `find_intake_receipt`、`record_intake` 两方法。成功 proposed、业务 rejected 均首次版本1；rejected仅四键 safe envelope，raw/message/path/credential 不落库。 |
| §6 原子与首结果 | READ COMMITTED、tenant SET LOCAL，一个 SAVEPOINT candidate后receipt flush/readback。五个精确命名23505键先rollback整个SAVEPOINT，再按 requested tenant+operation 新SELECT核完整request与历史自闭合；合法异请求 conflict、损坏历史 storage failure。lost response/source改变/candidate mutable head不改首receipt。 |
| §7 0008 | 19列 receipt、4 FK RESTRICT、outcome IS TRUE、hash/count/schema/origin/extractor CHECK；FORCE RLS，app SELECT/INSERT，audit SELECT，复用旧 append-only guard。mapped25/physical34/private31/public3；仅新增0008 own table/constraints/index/policy/trigger/ACL，0001–0007原字节不改。 |
| §7 admission | bootstrap和精确own catalog准入；empty-only、ACCESS EXCLUSIVE NOWAIT、外部ACL/view/FK/依赖拒绝、DROP RESTRICT与失败整体rollback；旧guard及0007表保持。既有CLI workspace head plugin纳入0008，本次没有真实用户库迁移。 |
| §7–9 原测试 | 0007 schema/catalog upgrade显式pin0007、downgrade显式0006，保留33/30/3和原拒绝断言；head cycle精确0008/34/31/3。head fixture同批receipt+六表，pin0007仅旧六表；无CASCADE、停RLS/trigger/降FK。 |

### 最终19 Python与3 README

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/domain/evidence.py` | `c515084ffa9147216e517ae180a094a912deabe09c6f469c26910a0ca10b78e6` | 79326 | 2401 |
| `dayu/investment/domain/candidate_intake.py` | `070e1b2fdc5d5e53d254b17b88febf3e17444aaeb16c5c7183e6cb0e422288f7` | 11413 | 325 |
| `dayu/investment/domain/candidate_parsing.py` | `f630677f2ac421f0480ee056bbc39590bd0543de4dfd6d7ef46980f9199f4a81` | 8364 | 234 |
| `dayu/investment/storage/candidate_intake_protocols.py` | `b4a649b13d89f25e98969f99700c4888feb1ba9e6a4d8efaadb598c4b6380076` | 1786 | 47 |
| `dayu/investment/storage/models_candidate_intake.py` | `9979f372c20257306b6ee1223515809fe3149c41b2cd66d5c0c34fb03e87a104` | 4313 | 77 |
| `dayu/investment/storage/postgres_candidate_intake.py` | `675f41964c8362ec21860915658b2d0bc1305bf8bfea84d732a9478cb0a10009` | 15328 | 335 |
| `dayu/investment/storage/migrations/versions/0008_candidate_intake.py` | `4f7630abd3aba54a38de6d7558e139ab0c8571f536bff4c166ecddb63f38ec55` | 15163 | 259 |
| `dayu/investment/storage/__init__.py` | `4d7f38c7a52fa13d452e2f089f9da5f5b146c1c6d847471259bf719ab9462995` | 2779 | 92 |
| `dayu/investment/storage/db.py` | `dcaf3b7d99be2508a596582c928812c5615ed33158378ae0a12339ec05c8efc2` | 4491 | 128 |
| `dayu/services/investment_research.py` | `d95fad970b26e49f9e0428379bdcacdcab3241aa5e720365d686770969374e97` | 9917 | 236 |
| `dayu/services/protocols.py` | `92ed4fc398f6b6e3437a92920d9ee128571ec40b1f387d7048570e76b7dd3852` | 12952 | 423 |
| `tests/investment/test_candidate_parsing.py` | `5eca1104ed4c11f029884c715fd81ab3c5f3ff7112a6e785dfe5cbbe3795eb41` | 9266 | 273 |
| `tests/investment/test_candidate_intake_contract.py` | `eb14c21583a10bc212d981386c504a3ca490afb722aabb23e4e9910407e087d1` | 6604 | 186 |
| `tests/investment/test_candidate_intake_service.py` | `0daf40c9b7326929c824038dd4ff6af1156ddc2f55fe47ef309286648f15eaac` | 20091 | 590 |
| `tests/investment/test_evidence_storage_contract.py` | `151163717af2641576b5db718829950b0414e4badaa6083cd64405d6cf4068ed` | 11727 | 293 |
| `tests/investment/test_platform_migrations.py` | `a17ab07d7afb6612db61b2376c3a9db150b9b2b93b83a89309cb47bb80f06b89` | 110518 | 3194 |
| `tests/integration/investment/test_postgres_candidate_intake.py` | `c35729f448df22d0868ff43001faf81d184a64ce93cc43a4207c5ecfd1baa7fa` | 69877 | 1818 |
| `tests/integration/investment/test_postgres_evidence.py` | `496c7006848399c95086127d646c53f008ff30b7d0c0d73ed74d1050ba7915db` | 101474 | 1978 |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `e2ada8052c8d06417bb7a0bdfbf18e3eeede08202dc2833c1b773a122fd6cc2c` | 313563 | 6941 |
| `dayu/README.md` | `0000f0ec44963c6c7b4576b9d9b5abb2b14fadcc55d70c4fcf65e0890d9b8c15` | 65599 | 1302 |
| `dayu/investment/README.md` | `1e7ac690e64b5af885f12ce1f31483275796196edc9bfaf94045890d68f3a64c` | 29741 | 410 |
| `tests/README.md` | `994e86a04a6b98219c6e07714fdce2df05762d77e1beac51fb86daa49f39e8d4` | 137780 | 654 |

每件 secure read：`O_RDONLY|O_NOFOLLOW`、regular、单hard link、读到实际EOF，前后dev/ino/size/mtime_ns/ctime_ns稳定。SHA/bytes/LF/CR/terminal-LF与descriptor入freeze；纳秒descriptor以精确十进制字符串编码，避免JSON/JS大整数精度损失。tracked最终owner另绑HEAD blob SHA，新增owner绑原缺席/当前new状态。未以diff摘要代final bytes。

## 最终验证与持久证据

实际命令由 Controller/root执行；仓库 .venv 已激活，`DEVELOPER_DIR=/Library/Developer/CommandLineTools`，PATH前置其usr/bin。本作者只核完成的输出，未补跑。完整argv：

```bash
python -m pytest -q tests/investment/test_candidate_parsing.py tests/investment/test_candidate_intake_contract.py tests/investment/test_candidate_intake_service.py tests/investment/test_evidence_domain.py tests/investment/test_evidence_storage_contract.py tests/investment/test_platform_migrations.py tests/investment/test_architecture_boundaries.py tests/integration/investment/test_postgres_candidate_intake.py tests/integration/investment/test_postgres_evidence.py tests/integration/investment/test_postgres_evidence_auth.py tests/integration/investment/test_platform_migrations_postgres.py --cov=dayu/investment/domain --cov=dayu/investment/storage --cov=dayu/services --cov-branch --cov-report=json:workspace/tmp/s32-a-full-final-coverage-attempt1.json --cov-report= --junitxml=workspace/tmp/s32-a-full-final-attempt1.xml --maxfail=1 > workspace/tmp/s32-a-full-final-attempt1.log 2>&1

pyright dayu/investment/domain/evidence.py dayu/investment/domain/candidate_intake.py dayu/investment/domain/candidate_parsing.py dayu/investment/storage/candidate_intake_protocols.py dayu/investment/storage/models_candidate_intake.py dayu/investment/storage/postgres_candidate_intake.py dayu/investment/storage/migrations/versions/0008_candidate_intake.py dayu/investment/storage/__init__.py dayu/investment/storage/db.py dayu/services/investment_research.py dayu/services/protocols.py tests/investment/test_candidate_parsing.py tests/investment/test_candidate_intake_contract.py tests/investment/test_candidate_intake_service.py tests/investment/test_evidence_storage_contract.py tests/investment/test_platform_migrations.py tests/integration/investment/test_postgres_candidate_intake.py tests/integration/investment/test_postgres_evidence.py tests/integration/investment/test_platform_migrations_postgres.py > workspace/tmp/s32-a-final-pyright.log 2>&1

ruff check --select E4,E7,E9,F,I dayu/investment/domain/evidence.py dayu/investment/domain/candidate_intake.py dayu/investment/domain/candidate_parsing.py dayu/investment/storage/candidate_intake_protocols.py dayu/investment/storage/models_candidate_intake.py dayu/investment/storage/postgres_candidate_intake.py dayu/investment/storage/migrations/versions/0008_candidate_intake.py dayu/investment/storage/__init__.py dayu/investment/storage/db.py dayu/services/investment_research.py dayu/services/protocols.py tests/investment/test_candidate_parsing.py tests/investment/test_candidate_intake_contract.py tests/investment/test_candidate_intake_service.py tests/investment/test_evidence_storage_contract.py tests/investment/test_platform_migrations.py tests/integration/investment/test_postgres_candidate_intake.py tests/integration/investment/test_postgres_evidence.py tests/integration/investment/test_platform_migrations_postgres.py > workspace/tmp/s32-a-final-ruff.log 2>&1

git diff --check
```

实际 **620 passed / failures0 / errors0 / skipped0**；log241.38s，JUnit time=241.376，timestamp=2026-09-28T09:22:05.444933+08:00。逐 testcase 复算 **unit400 + PG220**，PG new intake141 + evidence21 + auth1 + platform57。19-path pyright 0 errors/0 warnings/0 informations；升级提示不是代码错误，未升级环境。Ruff E4/E7/E9/F/I All checks passed。Controller见证上述命令与diff-check exit0；diff-check无独立日志，不伪造artifact。pytest配置关于pyproject忽略的现存提示不当作测试失败。

| 实际 XML 模块（类聚合回模块） | 执行项数 |
| --- | ---: |
| `tests.investment.test_candidate_parsing` | 57 |
| `tests.investment.test_candidate_intake_contract` | 11 |
| `tests.investment.test_candidate_intake_service` | 73 |
| `tests.investment.test_evidence_domain` | 38 |
| `tests.investment.test_evidence_storage_contract` | 6 |
| `tests.investment.test_platform_migrations` | 44 |
| `tests.investment.test_architecture_boundaries` | 171 |
| `tests.integration.investment.test_postgres_candidate_intake` | 141 |
| `tests.integration.investment.test_postgres_evidence` | 21 |
| `tests.integration.investment.test_postgres_evidence_auth` | 1 |
| `tests.integration.investment.test_platform_migrations_postgres` | 57 |

以下五件由 tmp原件逐byte镜像到新durable路径，O_EXCL创建、fsync、只读冻结、reopen核EOF；SHA与原件相等。XML/coverage本来0LF、无terminalLF，不补换行：

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `docs/reviews/s32-a-v3-validation/s32-a-full-final-attempt1.log` | `fb5eb450081893dcc979de0138eac4d1ccf401634632b172e809b722f70f0de8` | 2705 | 37 |
| `docs/reviews/s32-a-v3-validation/s32-a-full-final-attempt1.xml` | `b2afe35e571c447f0b4d99a8f592b9f36b2282e705c555da489eaae700d7c128` | 119495 | 0 |
| `docs/reviews/s32-a-v3-validation/s32-a-full-final-coverage-attempt1.json` | `2a2125f7fcfef6159b3c1b1927a87bac4183645fb1c2cffaac92e588db270191` | 2579039 | 0 |
| `docs/reviews/s32-a-v3-validation/s32-a-final-pyright.log` | `3ad2d843353727d542e7367b203d155ef69e68c7e533e1a57e7c5f8a2337fa84` | 191 | 4 |
| `docs/reviews/s32-a-v3-validation/s32-a-final-ruff.log` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | 19 | 1 |

原件/镜像双路径、descriptor与byte_equal入freeze。log/XML/coverage同一final attempt1，不拼旧运行，不拿collection当运行。真实数据库为既有PG16临时独占随机库；Fins为本地公共protocol替身。没有真实broker、网络模型/owner来源、live资金或真实credentials验证；bearer/SQL只用合成身份。

### 11生产coverage

statement=covered_lines/num_statements；branch=covered_branches/num_branches；combined=(covered_lines+covered_branches)/(num_statements+num_branches)。0branch标“—”，不伪称分支100%。逐原始JSON重算，11件statement均≥80%：

| 修改生产文件 | statement 已覆/总数 | statement % | branch 已覆/总数 | branch % | combined % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dayu/investment/domain/evidence.py` | 941/1020 | 92.255% | 297/376 | 78.989% | 88.682% |
| `dayu/investment/domain/candidate_intake.py` | 136/146 | 93.151% | 48/58 | 82.759% | 90.196% |
| `dayu/investment/domain/candidate_parsing.py` | 106/106 | 100.000% | 50/50 | 100.000% | 100.000% |
| `dayu/investment/storage/candidate_intake_protocols.py` | 8/8 | 100.000% | 0/0 | —（0 分支） | 100.000% |
| `dayu/investment/storage/models_candidate_intake.py` | 30/30 | 100.000% | 0/0 | —（0 分支） | 100.000% |
| `dayu/investment/storage/postgres_candidate_intake.py` | 133/149 | 89.262% | 38/48 | 79.167% | 86.802% |
| `dayu/investment/storage/migrations/versions/0008_candidate_intake.py` | 71/80 | 88.750% | 15/24 | 62.500% | 82.692% |
| `dayu/investment/storage/__init__.py` | 7/7 | 100.000% | 0/0 | —（0 分支） | 100.000% |
| `dayu/investment/storage/db.py` | 27/27 | 100.000% | 0/0 | —（0 分支） | 100.000% |
| `dayu/services/investment_research.py` | 87/92 | 94.565% | 22/24 | 91.667% | 93.966% |
| `dayu/services/protocols.py` | 68/68 | 100.000% | 0/0 | —（0 分支） | 100.000% |

11件合计：statement **1614/1733 = 93.1333%**，branch **470/580 = 81.0345%**，combined **2084/2313 = 90.0994%**。

三coverage源目录全扫描口径：statement **8554/28226 = 30.305%**、branch **998/9566 = 10.433%**、combined **9552/37792 = 25.275%**。含大量本次未测/未改源，**不能充作项目全仓coverage**。全部missing_lines/missing_branches已原样入durable coverage和freeze；migration62.5%、repository79.167%、evidence78.989% branch等有限执行边界保留，不宣称每个防御分支均运行。

## 故障修复及证明边界

### M1 深度JSONB历史损坏

本轮静态预审曾报fresh H/M/L **0/1/0**，**无durable reviewer artifact**，不作为formal code review/Gate。实际M1：`_project` candidate SELECT触发psycopg JSONB json.loads RecursionError，越过原except。

Controller以真实PG合法JSONB、深度1500的deep_json corruptcase复现，先 **1failed/3.84s**；仅生产补catch RecursionError和中文comment，四corruptcases随后 **4passed/5.41s**。两个中间结果仅有root实际exec会话见证，无磁盘日志，不伪造artifact/traceback。最终源 `postgres_candidate_intake.py:189` 与测试 `test_postgres_candidate_intake.py:748` 在freeze内；final JUnit明确包含payload/origin/operation_fingerprint/deep_json四case全通过。作者状态为修复并验证，非作者须另复核。

### 测试／infra修复

Controller会话记录的fixture import、organization真实列display_name/status、race barrier monkeypatch恢复、module coverage numpy额外collection选择修复，属于测试/infra，不冒充生产业务finding或review结论。中间失败不被改写为PASS，final620由自己log/XML/coverage支持；实际命令明确unit7+PG4。

### race、named injection与SQL

自然两连接竞争真实观察一个三个candidate命名unique键内的psycopg23505，rollback SAVEPOINT后新RC SELECT恢复同receipt；不宣称5键全部自然首先命中。五键分类另通过owned PG trigger产生带精确constraint的真实23505，验证driver/事务分类路径，不能替代自然键顺序证明。

直接SQL测19列、15NOT NULL、五hash、outcome NULL闭合、合法双arm、new candidate/security复合FK、父DELETE RESTRICT、app/audit ACL、admin旧guard、unset/wrong tenant RLS，每个拒绝核SQLSTATE/实际命名约束与七表fullsnapshot。四新FK catalog精确列序/target/RESTRICT；org/company DELETE记录实际先命中的旧FK，不为孤立冗余FK停约束或造不可能数据。0008有行、view/FK、role/column ACL与NOWAIT失败后revision/行完整回滚由真实PG验证。

## README decision

已只读核最终源与三README diff。investment README记录实际ingest/parser/repo、历史receipt/Finsreadback、0007/0008不同manifest、witness freshness；tests README记录当前unit入口、真实PG、自然race/namedfault、七表/六表fixture；dayu开发总览只补显式protocol装配及包级导航。属于各自职责，Controller已更新，本作者未改。入口签名/装配与当前源一致，未将future promotion写成已实现，未将新Service称已注册Host，也未将Fins替身当网络owner验证。

## 未修改相关upstream pins

下列 **41件** 当前bytes同时与S31 afe53和HEAD blob相等，包含完整旧0001–0007、旧repo/models/auth/protocol、Fins相关pure/runtime/Service、startup/composition registry、CLI init和全部workspace_migrations Python，以及未改architecture/evidence-domain/auth测试与PGharness。已另核独立计划报告27个历史输入blob全部匹配afe53；此表是相关身份冻结，**不宣称整个Fins树/全仓语义审查**。

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `AGENTS.md` | `a23286913c328e1041659a8bc58c49345a23cec89ab78127123228a532f9296e` | 7200 | 109 |
| `CLAUDE.md` | `a23286913c328e1041659a8bc58c49345a23cec89ab78127123228a532f9296e` | 7200 | 109 |
| `dayu/cli/commands/init.py` | `3ffa8da3d46b34194fa9f44fc66bbd4c091413ee66a76b6f4724daf990793bda` | 73230 | 2115 |
| `dayu/cli/workspace_migrations/__init__.py` | `4cfe116f94420792b9292ceb262996200712f1932578b8d5abd8eb41de4ff3ff` | 1199 | 28 |
| `dayu/cli/workspace_migrations/conversation_archive_init.py` | `93c8b38968971980f5ba6089d29fae307005d3ec63e4ae5f3e501d0a2592abc0` | 4696 | 132 |
| `dayu/cli/workspace_migrations/host_store_rename_concurrency_lane.py` | `402d3ea2025f67b66c5696917b0def9ab49c07a03eb6235b9b1084882450b18d` | 4449 | 127 |
| `dayu/cli/workspace_migrations/host_store_strip_max_output_tokens.py` | `7ba140394febc6d32f426243b08207a0a66ff9f2ee12ece2acb1df1bdbca58f2` | 4123 | 121 |
| `dayu/cli/workspace_migrations/platform_import.py` | `f6ca030c75a6c249e63ea19cd4f375c9c065c3ceecc5a5ee48e4041b10124c25` | 33230 | 1007 |
| `dayu/cli/workspace_migrations/platform_jobs.py` | `a5a7ddb2b7dd1740af828bc46e99faba39710a7596f25410a205c7dcc076f382` | 3632 | 114 |
| `dayu/cli/workspace_migrations/run_json_market_download_lanes.py` | `4b45b0d042bf63d215293c6b00c190d446b23826a8f6ce845e8a801d64182434` | 2372 | 75 |
| `dayu/cli/workspace_migrations/run_json_utils.py` | `21862936dcb6efb3868f549b61605b8f0f50d77f8904008b572909a529216c9f` | 2736 | 101 |
| `dayu/cli/workspace_migrations/run_json_write_chapter_lane.py` | `d1154d764d04cca2eb1c1b22b5707fe0ce2a8e36e570490bbd527e823bb5fdbf` | 2300 | 70 |
| `dayu/cli/workspace_migrations/runner.py` | `f171638ad9217c07d4d834328e1ac7957f331c3be5ae9368c011a67cbf6663a7` | 3469 | 84 |
| `dayu/fins/domain/document_models.py` | `07b85647765e768f4ba525aa4c8f0fd83f77eabdb8c40495ea5127bd66389fa0` | 20563 | 755 |
| `dayu/fins/domain/evidence_locator.py` | `c801cc957117f6bd98857c044830e9338050fffafa746503b1af4be3e441e237` | 41535 | 1385 |
| `dayu/fins/service_runtime.py` | `e34e4a59ca4b247b00c7a50b18fe3249fd98a6b5e5d55053376a847582e403f8` | 118605 | 3189 |
| `dayu/investment/composition.py` | `e9dd8c5fdb51a2f6d7e901afe0d7dd81453d51865e7deb912bd79f8c3e0c2ac7` | 17470 | 563 |
| `dayu/investment/storage/_evidence_review_auth.py` | `08c239848fd82f125dc5159bbcb3d91dbfcbb8a0c904f16753146d59f1a50e06` | 14334 | 444 |
| `dayu/investment/storage/evidence_protocols.py` | `0a0434dd6622f70c2d3c2af6ec350330a4bcea04d15f1b44c57d5ea22a1fbfda` | 12418 | 381 |
| `dayu/investment/storage/migrations/versions/0001_platform_foundation.py` | `9c666192ca251cf8e4153125fd5702044796eb6035a04cf050f9676007efe518` | 30839 | 784 |
| `dayu/investment/storage/migrations/versions/0002_workspace_import.py` | `ab727e038f0f9efccaccd0c55c3aa3fbe289e72dc21356e521cedf1b08a1cc87` | 12063 | 374 |
| `dayu/investment/storage/migrations/versions/0003_durable_jobs.py` | `08c46c705f3cfe019ee69c50685f1935301a1dd6a09c9f853b01ae667b4b32b0` | 36049 | 1032 |
| `dayu/investment/storage/migrations/versions/0004_durable_schedules.py` | `6e45bfcc1890dccf5b4b675fb54d531fb81e653387932ecb041b7bc81212536e` | 26810 | 732 |
| `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py` | `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` | 104809 | 2674 |
| `dayu/investment/storage/migrations/versions/0006_job_request_identity.py` | `33dd4f9ba71c4aed2e167a6887979324dad1b5651f60a56b2c3bb3f75c4bd01d` | 65099 | 1594 |
| `dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | `1a4197b34b7d732b48bf6f30bb78ddfc2f52468f6e8e7cbedd1763b5c0a14ce6` | 44136 | 674 |
| `dayu/investment/storage/models_auth.py` | `e17944f13cbd6cc35cadd0a9e90d816a9a7f3a7c32ba5d7c7473255138c19207` | 9592 | 251 |
| `dayu/investment/storage/models_evidence.py` | `77f4250524951420b70ee2a4de54bedbabeb4ba15795be9c048eaf834669d6e5` | 27274 | 317 |
| `dayu/investment/storage/models_identity.py` | `5d266741efec51b7b83178de4228b86a0dc87785a16b3a9bb3a2fc283f090a78` | 38494 | 910 |
| `dayu/investment/storage/postgres_evidence.py` | `dcc20a632aced7c88b21f97bf003955fcdd2a6b54bb9f4cc9b47367b08e26d8d` | 78915 | 1809 |
| `dayu/investment/storage/postgres_identity.py` | `23f7a2ae3fe6ea4d354df1fae56c32257bb69bb31a76a73911a2521635ea783e` | 38622 | 1195 |
| `dayu/investment/storage/protocols.py` | `6879a01c520cd3e5653c9502a3521d15e32af68f84a16546490655edae14ca10` | 29940 | 968 |
| `dayu/services/__init__.py` | `49ca9e70677bf4b64fd0ecf42b0f40087232a95fce9dd56d59248b44b9e55c57` | 2312 | 81 |
| `dayu/services/fins_service.py` | `21b427d0ec9b420235081a734252b81421e74da6597d19146a711f8dfb919fc7` | 8657 | 276 |
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e` | 63289 | 1689 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `a758d614bc7f9c794509a548bc7c2dead75440a870669ef4085c5cc347e3b1ec` | 419511 | 4572 |
| `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` | `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2` | 47288 | 134 |
| `tests/integration/investment/conftest.py` | `f89ebfc631c5fb6f89a33e1b6559282171ce0abf39b89bb16c70de1e835e7401` | 20566 | 717 |
| `tests/integration/investment/test_postgres_evidence_auth.py` | `e9c9519b7ffdffabb827393a4b62ca6c3057c00819bb3f116bd1cfeba4e93686` | 27717 | 695 |
| `tests/investment/test_architecture_boundaries.py` | `d20dfdf7cc8af216f7a8caceca5a6a731b3969df0057129a79b6cb40e0d3c3d9` | 131873 | 3842 |
| `tests/investment/test_evidence_domain.py` | `9176ab86e751745c0ce6ba22a3df51986eaeebaa9267d0e0ffe2e5dd6fadb0e2` | 28813 | 812 |

## 残余风险／计划缺口／owner

| 项目 | 分类、owner与去向 | 保留边界 |
| --- | --- | --- |
| M1深JSONB | 当前切片review前已修；Controller/root，下一formal非作者复核 | final四corrupt/620通过；旧无artifact预审不授Gate。 |
| intake后source漂移／无跨Fins-PG全局锁 | approved后续S32-B；research/Fins owner | promotion及每次消费重新owner/readback，不缓存永久freshness。 |
| human/service identity/grant/action、candidate CAS、精确source PIT、Fact/Claim+promotion audit事务 | later独立S32-B计划；domain/auth/storage/Fins owner | 当前A不晋升，不从Agent/filing_date补来源时间、不由receipt存在推权限。 |
| 旧trusted staging无receipt、raw不落库 | S32-B receipt准入；可信caller保存原raw | 无receipt不能冒称Fins校验，拒绝只safe envelope。 |
| app-role可信进程／未来对外API认证 | later Phase7.1；auth/API owner | 本次无对外bearer端点/自由reviewerID/真实credential读取。 |
| missing_lines/arcs、自然race键顺序有限证明 | assigned下一formal code-review work unit；Controller+非作者 | statement达门，branch/combined独报，review评估具体剩余风险，作者不豁免。 |
| V8/十根递归正负值与合法历史、T1h/A2/G1及30arms、H2/H1/V17/S5/D0/Gate | 独立R52work units；其Controller | 本slice不给任何权威，仍OPEN，不缩减十根。 |
| S31 draft未合并、未来S32交付/rebase | later交付work unit；Controller | 本作者无push/PR/merge/approve，不声明CI/shipped。 |
| shadow业务完整闭环／broker live资金 | 主计划后续阶段；Controller | 本次仅candidate intake，无交易执行或资金连接。 |

无须作者凭空扩owner的新增计划缺口；实现finding由formal非作者审查裁定。作者阶段完成，下一入口为本freeze的完整source和durable证据→formal code review→必要另版fix/re-review→Controller裁决；S32-B、整个Slice3.2和最终业务目标未完成。

## 冻结交接

本报告与五镜像首次O_CREAT|O_EXCL|O_NOFOLLOW、完整写入/fsync、mode0444后secure EOF核验，不覆盖既有产物。freeze随后绑定本报告SHA与22source、accepted三件、41upstream、27baseline、git清单、实际argv、XML/coverage与原件/镜像descriptor。freeze不自引用SHA；本报告只引用freeze文件名，避免相互hash循环。两个artifact最终SHA/bytes/LF由外部消息给Controller，冻结后不再改。