# S32-B-Auth V1 实现作者报告

## 状态与明确边界

**AUTHOR_IMPLEMENTATION_COMPLETE_REQUIRES_NONAUTHOR_CODE_REVIEW。** 本报告是实现作者的本地验证和终盘见证，非独立代码PASS、Controller acceptance、slice commit、aggregate或交付Gate。非作者codeReview尚未执行，H/M/L=NOT_RUN，不填作者自判0/0/0。本单位只完成固定 `investment.fact.promote` 的私有授权查询，未实现 candidate→Fact 晋升或PIT。

实际repo `/Users/wsk/workspace/dayu-agent`，branch `codex/fact-promotion-auth`，accepted plan HEAD `69c32cd01af773d71f764c3fc690deb748f2b25f`；该HEAD来自Auth隔离baseline `c86b9e18dc9a92e7c3173aefe83a32795f74e5fb` 的5个docs/1229LF。实施后HEAD/index未改，无commit/push/PR/remote/Gateflow启动或其它gate。A PR4 branch仍由Controller另管；本次没有remote认证/CI/merge操作。

依据：[accepted child](/Users/wsk/workspace/dayu-agent/docs/plans/2026-09-28-slice-3.2-b-auth-fact-promoter-v1.md) `e2bdb1310f2b4863ad2a231806a90703dd15afe4189afb4791ee9aec514a6849` /25046B/190LF；[独立planreview](/Users/wsk/workspace/dayu-agent/docs/reviews/plan-review-20260928-103049.md) `e2c80b1bf939fdd831c05beb0f8f10ea37a975267581c96b1c3c718caf0d2b0d` /21569B/136LF，PASS0/0/0仅plan；[Controller采用](/Users/wsk/workspace/dayu-agent/docs/reviews/plan-acceptance-20260928-s32-b-auth-v1-codex.md) `39b6fb8c9d91062489d7fa48f0fb6bdf261a25af2acd6bb36ae4deff75cf3574` /4461B/40LF；[输入/输出freeze](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-implementation-input-output-freeze-v1.json) `50e45a9d46d428bab2677fa79bd19fe8cd8d6aacc70882e29bc3b9f5cdd39240` /17569B/529LF。旧freeze内baseline c86是其历史捕获前件，不伪写未来69 commit；当前外部handoff绑定69。

## 五路径的实际实现

| owner / path | final SHA256 | bytes / LF |
|---|---|---:|
| [dayu/investment/README.md](/Users/wsk/workspace/dayu-agent/dayu/investment/README.md) | `88ce43d754c1975e481c23a6c9ccf05fb743f26c5516fe965f0938a02f87188b` | 30887 /422 |
| [dayu/investment/storage/_evidence_review_auth.py](/Users/wsk/workspace/dayu-agent/dayu/investment/storage/_evidence_review_auth.py) | `19c8571366b9f70f7ca4ea07e8d240fc6c826bef0476864720f354d88c8647bc` | 18215 /541 |
| [tests/README.md](/Users/wsk/workspace/dayu-agent/tests/README.md) | `b71b5a78e23399fac407469a071f0400def2b9f993e78c70c4a051d4d0fc1bdf` | 138611 /656 |
| [tests/investment/test_candidate_promotion_auth.py](/Users/wsk/workspace/dayu-agent/tests/investment/test_candidate_promotion_auth.py) | `8bf70251e749f4eb7c45d9bc0de425b2da5834eda16639d38a26e1ab83abcfac` | 6697 /184 |
| [tests/integration/investment/test_postgres_candidate_promotion_auth.py](/Users/wsk/workspace/dayu-agent/tests/integration/investment/test_postgres_candidate_promotion_auth.py) | `a54496e19941cab3fbbf27d8dca24ad1f55971be830499797add32e44c3fc9f5` | 26092 /435 |

- 唯一production [auth owner](/Users/wsk/workspace/dayu-agent/dayu/investment/storage/_evidence_review_auth.py:34)：Fact固定常量；L191 `FactPromoterAuthWitness`直接继承Actor并增加四grant UUID，是Reviewer sibling；L349 closed-two-purpose `_granted_auth_row`；L452固定 `authorize_fact_promoter(session,scope_hint,raw_token)`。
- 新入口依次canonical hint/bearer→已有Session事务/hidden bind→SET LOCAL与READ COMMITTED/readback→同一Factpermission SELECT→len8→七个非nil UUID及checked_at UTC→固定purpose witness。无begin/commit/rollback、无auth/业务写、无last_used_at更新、无caller witness/actor参数、无issuer/production permission seed或新schema/API/protocol。
- `_granted_auth_row`先要求真实str且恰为Claim review/Fact promote，非法purpose在SQL零调用前Usage；合法query唯一使用现有 `_REVIEWER_SQL`、四bind参数与固定ORDER/LIMIT。无行Unauthorized，损坏八列投影Storage；不是先Reviewer授权再改policy。
- 旧 `_auth_row(connection,tenant_id,token_hash,*,reviewer:bool)`签名/故障seam保留。True只传旧Claim常量，False仍原actor SQL；旧authorize_reviewer/active_actor的输入和policy不变。两个旧SQL assignment源段逐字节SHA仍为 `_ACTOR_SQL=3a0910d1dad8082a926359a2051597a34eaea5f97950ff72f6603f5a60839d7c`、`_REVIEWER_SQL=d521a37d60aec0a7e54911ef34fa7065e319529e5380b8ee9b9acb4d4e410352`；unit已冻结该字节边界，PG故障仍patch同变量。
- SQLAlchemyError退出except后才抛固定Storage，cause/context空；未catch未知Exception、BaseException或取消为deny。Unauthorized/Usage/Storage文本不变；witness不含raw/hash，repr和标准json/pickle边界验证。公开dataclass constructor可伪造，未声称认证provenance不可伪造；没有public API接受witness作为authority输入。
- tracked旧3文件diff为118 additions/7 deletions；新unit184LF、新PG435LF，共五个实现路径737 additions/7 deletions。新tests在实施前secure lstat absent；27输入及原/镜像完整核验后才改源。

## 真实验证：阶段与最终计数

1. 无cov预检真实执行22unit通过：新unit17+旧unit5，0.23s；三路径pyright0/0/0。初Ruff仅新PG一个unused import，已从该允许文件删除后重新通过，没有改其它owner。
2. 原计划module-cov命令在collection阶段exit2，0 items collected、四collection errors：SQLAlchemy inspection `AssertionError: Type <class 'object'> is already registered`。旧、新四模块均受影响，PG没有启动/执行；不把它记成auth测试失败或PG结果。原日志 [dev failed collector](/Users/wsk/workspace/dayu-agent/workspace/tmp/s32-b-auth-dev-tests.log) SHA `22d579f183eb5ca4bce27384a978b52eee5d59c99bf0bef29363f4f2cfc66389` /6088B/101LF；实际生成XML `5bdfc452dfb5e95357f319ad2f2dd99ea8b34b68b192b887d0229eb025d37d17` /5543B/76LF，XML四个collection-error entries不是执行四个测试。没有dev module-cov JSON文件。
3. Controller接受 `--cov=dayu/investment/storage` 文件系统fallback；同四模块dev执行43passed/24.51s，无fail/error/skip。生产代码和旧tests没有为collector错误修改。
4. 首次完整dev通过后按职责同步两README，再在最终五路径代码上执行以下最终命令及三路径工具，原始stdout/stderr真实capture到五个约定paths，无归一化、补造或摘要替代。

```sh
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
export PATH=/Library/Developer/CommandLineTools/usr/bin:$PATH
source .venv/bin/activate
python -m pytest -q tests/investment/test_candidate_promotion_auth.py tests/investment/test_evidence_review_auth.py tests/integration/investment/test_postgres_candidate_promotion_auth.py tests/integration/investment/test_postgres_evidence_auth.py --cov=dayu/investment/storage --cov-branch --cov-report=json:workspace/tmp/s32-b-auth-final-coverage.json --cov-report= --junitxml=workspace/tmp/s32-b-auth-final-tests.xml > workspace/tmp/s32-b-auth-final-tests.log 2>&1
pyright dayu/investment/storage/_evidence_review_auth.py tests/investment/test_candidate_promotion_auth.py tests/integration/investment/test_postgres_candidate_promotion_auth.py > workspace/tmp/s32-b-auth-final-pyright.log 2>&1
ruff check --select E4,E7,E9,F,I dayu/investment/storage/_evidence_review_auth.py tests/investment/test_candidate_promotion_auth.py tests/integration/investment/test_postgres_candidate_promotion_auth.py > workspace/tmp/s32-b-auth-final-ruff.log 2>&1
```

最终真实pytest exit0：**43 passed /0 failures/0 errors/0 skipped**，日志终行 `============================= 43 passed in 23.52s ==============================`；JUnit time=23.514s，按实际case classname分组，不使用collection推测：

| 类型/owner | actual passed |
|---|---:|
| NEW unit candidate_promotion_auth | 17 |
| old unit evidence_review_auth regression | 5 |
| NEW true PG16 candidate_promotion_auth | 20 |
| old true PG16 evidence_auth regression | 1 |
| total unit / PG / all | 22 /21 /43 |

final pyright exit0，**0 errors/0 warnings/0 informations**；raw还保留工具升级提示及末尾空行，它不是类型warning，未改runtime/version去隐藏。final Ruff E4/E7/E9/F/I exit0，All checks passed。tracked三文件默认git diff --check exit0；两个NEW tests直接核零trailing whitespace。镜像raw pyright原空行保留，因此未来whole-stage默认blank-at-eof检查可能报告该日志，不能宣称未经检查的完整staged diff无例外。本阶段index始终空，由Controller负责后序stage/commit。

## 真实PG边界与对抗证据

- 只复用现有 `PlatformCluster/lifecycle_database/create_temporary_login/drop_temporary_login/run_alembic_*` 与平台engine/sessionfactory；pinned本地PG16.14、随机owned container/network/database/app login，head0008，未复制Docker harness、连接既有PG17、隐式pull或使用SQLite/mock替代授权权限。每PG用例随机库，finally dispose/drop login/downgrade；末尾owner-label过滤查询真实确认owned container/network各0残留。
- 四种Fact/Claimgrant组合：nogrant两deny但actor允许；claim-only拒Fact、fact-only拒Claim；both各返回自己的四grant IDs与固定purpose。真实token导出tenant/user/token，forged Principal user文本不参与。两tenant各合法Fact成功，错误hint/token组合拒绝；app设置tenantB时直接查询只见Btoken；真实跨tenant复合FK插入IntegrityError，未drop FK。
- 明确低UUID的第二Fact rolechain验证ORDER BY ur/rp/p LIMIT1整链选择，role名称不赋权限。仅test-owned admin seed固定权限、合成256-bit bearer；production没有seed或issuer行为。
- 五类token/user/org/user_role/role_permission各独立PG testcase：caller先开事务、第二不同backendPID连接先提交撤销→拒；另一事务先返回witness，第二连接在caller未结束时完成撤销，原witness不被追溯改，caller同一事务下一fresh SELECT拒。第二连接lock_timeout=1s/statement_timeout=3s，真实无helper锁阻塞；不是自然同时CPU调度race或commit永久授权证明。
- checked_at边界before/after均取同PG语句时刻；checked_at仍是statement_timestamp语句开始，未称精确snapshot获取或commit时间。严格expires_at>statement_timestamp SQL原字节保留，真实NULL、当前admin语句时刻及past expiry均拒；未来expiry正例。token revoked、user locked/disabled、org disabled及permission_key改变均拒。
- 当前0008/34 physical/31 FORCE RLS/3 public、app两个join SELECT/DELETE为true、UPDATE为false均真实核。无新增FOR SHARE/UPDATE/table/advisory lock或ACL权限。
- 独立无revokercase以auth七表 `row_to_json`全部实际列的长度分帧digest快照逐表前后相等（避免pytest打印token_hash值），其它全部actual platform业务表count相等；last_used_at仍NULL。不是只比较Fact/candidate count或不存在的grant status列。callercommit与异常rollback后连接池SETLOCAL为空。
- nonhidden Engine在grant SQL前拒；REPEATABLE READ/SERIALIZABLE拒；owned real-Connection readback事件注入错误tenant返回Storage并回滚。`_REVIEWER_SQL`故障注入覆盖长度3/9、七UUID逐个nil、UUID错类型、NULL/naive checked_at；真实PG source shape未被改变，不dropFK。不存在auth表的SQLAlchemyError固定Storage，无raw/hash/SQL原因cause/context/traceback泄露。
- INFO日志确有auth SQL但合成raw/hash不可见。KeyboardInterrupt/SystemExit在helper内部owned grant fault boundary动态传播，caller transaction context回滚、全auth列/业务counts不变。async task在同步helper成功后主动取消，CancelledError经caller/transaction context传播，快照零写/上下文清理；**这不是同步driver中途异步SQL取消能力证明**。

## 覆盖率及具体未覆盖owner

唯一修改production文件精确从JSON的 `files["dayu/investment/storage/_evidence_review_auth.py"]` 抽取：statement **159/163=97.5460122699%**（≥80）；branch **30/32=93.75%**；combined **189/195=96.9230769231%**。未用combined替statement，也未给test文件覆盖率作production门。

missing lines=[214,248,250,252]，missing branches=[[213,214],[251,252]]：均在原hint/token防御owner。L214为传入非exact TenantScope类型的早拒分支，本轮动态负例使用真实TenantScope的nil/uppercase/坏UUID及未初始化实例，未动态覆盖该类型分支；L248/250为标准b64 decoder异常路径，L252为decodedNone/长度异常防御，在先验43 ASCII pattern与canonical32-byte校验下本轮未注入stdlib decoder fault。Owner=Auth辅助与后续非作者review；不伪称分支全覆盖，不为补数字改源码或库行为。

filesystem采集包含未修改storage其它文件：statement1769/5827=30.3586751330%、branch248/1626=15.2521525215%、combined2017/7453=27.0629276801%。这是当前四模块运行的storage扫描范围，不是全仓测试覆盖率或其它modified owner门；不能将该低扫描值或唯一auth97.55%冒充完整storage/全仓覆盖。

## README、冻结原件与实际raw镜像

`dayu/investment/README.md`更新当前private固定Fact query、registered-user token/statement snapshot/无业务写与witness输入边界，并登记两test职责；`tests/README.md`登记单元/真实PG16权限、五类撤销、全auth列和caller取消。没有写promotion/PIT/HostService装配已实现，没有修改根/Fins/Host/Engine README。

27 input sources中仅三个允许旧文件auth/两README发生变化；其余24件完整EOF/SHA/bytes/LF/原descriptor精确不变，含原0001–0008、旧两tests/conftest、domain/models/db/repository及约束文档。三original/mirror pair保持byteexact、原计划/审查/Controller/fullfreeze身份不变；historical excluded `implementation-20260928-s31-aggregate-retry-fix-v2-codex.md` 仍d46cc852c7dc59667c751a403d932a4eaf0a1d5b05f12b5c1d293f278f0b8b2b/4456B/32LF，未stage或更改。

以下NEW durable目录只有五个真实最终raw文件的byteexact镜像，全部O_EXCL/fsync/0444/reopen；原workspace/tmp paths均有fulltuple，pyright空行原bytes不改：

| durable final validation | SHA256 | bytes / LF |
|---|---|---:|
| [s32-b-auth-final-tests.xml](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-validation/s32-b-auth-final-tests.xml) | `938c96a54c9459bc94b7dd80b54457e2fea0b8cdabe1ae7f70ede67dd5990bac` | 7212 /0 |
| [s32-b-auth-final-coverage.json](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-validation/s32-b-auth-final-coverage.json) | `6457e63f9746112c07898cedf428651d1f92ed7c8c1fe4b8854770f295a5d33c` | 543280 /0 |
| [s32-b-auth-final-tests.log](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-validation/s32-b-auth-final-tests.log) | `ba22030abc14ee0a74d5d79f4cd14dea53c5ee2ad08ba490532e5d5b06c60a5c` | 1332 /20 |
| [s32-b-auth-final-pyright.log](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-validation/s32-b-auth-final-pyright.log) | `3ad2d843353727d542e7367b203d155ef69e68c7e533e1a57e7c5f8a2337fa84` | 191 /4 |
| [s32-b-auth-final-ruff.log](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-validation/s32-b-auth-final-ruff.log) | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | 19 /1 |

NEW [final-disk freeze](/Users/wsk/workspace/dayu-agent/docs/reviews/s32-b-auth-final-disk-freeze-v1.json)将完整27 original/final source descriptor、两个newtests、原件/镜像、accepted记录、上述five raw original/mirror、dev实际证据和本报告actualtuple绑定；它不含自身hash或未来commit。报告正文不填自身SHA/freezeSHA来制造循环；实际hash由外部handoff返回。源码和证据发布后不再由作者改写。

## Findings状态、remaining authority与下一门

- 此acceptedchild plan的独立finding为0/0/0；当前implementation非作者codeReview未运行，不自评PASS。作者实际修复仅Ruff unused import；module-cov collector是公开记录的运行工具边界，已按Controller接受filesystem fallback验证，无权限/SQL/fixture语义弱化。
- Auth owner/非作者reviewer：检查本五路径代码及真实数据/错误/取消证据；未知程序错误/各驱动异常细类和同步driver中途取消未穷尽动态测试。本地43pass、97.55% stmt不证明所有运行环境或后续授权到commit的窗口已关闭。
- auth管理/issuer owner：生产grant provisioning、真实用户token发行/轮换、真人在场/MFA与typed service provenance仍未实施；本helper仅接受既有合法registered-user bearer，构造witness本身不可作认证来源证明。
- PIT owner：真实publisher、revision ingestion/availability及source_published独立计划/采用/实现；B1 owner：candidate CAS、Fact immutable/receipt及写前/锁后fresh授权；Claim/Visibility/ServiceActor均另立单位，parent/B1/PIT未由本单位采用或交付。
- V8/十shape/H2/S5/D0/Gate与shadow-only原目标仍独立OPEN/active；本作者没有运行或修改V8 scratch/normative source/candidate/runtimenamespace，无broker/order权限。

唯一下一门：Controller读取本报告/终盘freeze后派非作者codeReview；若有acceptedfinding则scope内修复/re-review，其后才由Controller决定accepted slice commit、aggregate/delivery。当前没有Auth实施commit或PR，不提前门序。

作者终盘系统UTC：`2026-09-28T02:48:09.288807+00:00`；本报告NEW O_EXCL/fsync/0444/secure trueEOF复读，原sources/artifacts不覆盖。
