# S32-B-Auth V1 — Controller plan acceptance

## 限域结论

**PLAN_ACCEPTED；fresh independent open H/M/L=0/0/0。** Controller完整读 child190LF及非作者review136LF，按五路径仅采用 S32-B-Auth-1 固定 `investment.fact.promote` 私有授权查询。没有实现、测试或PG执行证据；parent/PIT/B1/ServiceActor/Claim/Visibility及完整Slice3.2仍未采用或交付。

- task cwd：`/Users/wsk/Documents/ChatGPT/投资agent`（非Git）；actual source repo：`/Users/wsk/workspace/dayu-agent`。
- 新分支：`codex/fact-promotion-auth`；实施前 baseline：`c86b9e18dc9a92e7c3173aefe83a32795f74e5fb`，来自已完成draft交付的A finalhead，tracked tree/index clean。
- 旧852→c86精确新增3docs：`code-review-20260928-101417.md`、`pr-review-acceptance-20260928-s32-a-v3-codex.md`、`final-closeout-20260928-s32-a-v3-codex.md`；27个源码逐EOF/SHA/descriptor/HEADblob相等。此docs-only重新绑定不改变child语义。
- 复用已释放的本地checkout并创建独立非protected分支；A PR4分支保留c86，不把Auth写入A draft。

## 原件与逐字节镜像

| role | repo镜像 | SHA-256 | bytes / LF |
| --- | --- | --- | ---: |
| accepted_child_plan | `docs/plans/2026-09-28-slice-3.2-b-auth-fact-promoter-v1.md` | `e2bdb1310f2b4863ad2a231806a90703dd15afe4189afb4791ee9aec514a6849` | 25046 / 190 |
| unaccepted_parent_background | `docs/plans/2026-09-28-slice-3.2-b-candidate-promotion-parent-v1.md` | `ed7f3cd28082c33c3e6652767fdb83e45d61dccbb4df52969d4f3fc28155ca52` | 62342 / 334 |
| independent_child_plan_review | `docs/reviews/plan-review-20260928-103049.md` | `e2c80b1bf939fdd831c05beb0f8f10ea37a975267581c96b1c3c718caf0d2b0d` | 21569 / 136 |

镜像均为原件完整字节；原件absolute path及完整descriptor在freeze。parent镜像仅背景AUTHOR_CANDIDATE，**不是accepted parent规范**，Auth不依赖其PIT/B1采用。

## Exact implementation handoff

1. `_evidence_review_auth.py`：Fact固定常量、Actor sibling typed witness、closed-two-purpose私有grant query及固定Fact入口；旧两SQL逐字节、旧_auth_row签名与fault seam保持。
2. NEW `tests/investment/test_candidate_promotion_auth.py`。
3. NEW `tests/integration/investment/test_postgres_candidate_promotion_auth.py`。
4. `dayu/investment/README.md`。
5. `tests/README.md`。

其它production、models/protocol/Service/Fins/CLI/Host/Agent、0001–0008、旧auth两test与conftest只读。authority仅当前statement snapshot；无FOR SHARE/UPDATE/ACL扩散、auth写、productionpermission seed或tokenissuer。registered user不证明真人/MFA或service identity。未来promotion自行fresh授权，禁止publiccaller传witness获取authority。

## Validation、残余风险与后序门

按child L132–139真实执行四文件unit+PG16，old5unit/old1PG独立计数；实际XML而非collection；三受影响Python pyright/Ruff；唯一prod statement>=80，branch/combined/missing单列；兩职责README随后同步。测试包含onlyclaim/onlyfact/both/nogrant、真实两tenant/多grant链、五类两连接撤销、同事务fresh读取、旧ACL/RLS/SQL/seam、所有auth列零写、redaction和caller取消，不能弱化旧测试。当前未执行，不预填casecounts或PASS。

残余owner：Auth author/非作者code reviewer负责实际fault/取消/PG/types/coverage；PIT owner负责真实publisher与revision ingestion/availability，B1 owner负责CAS/Fact/receipt及freshcurrent-use，Visibility owner负责历史as_of许可，ServiceActor/Claim另单位；auth管理owner负责合法productiongrant/issuer。不扩大本child。

freeze：`docs/reviews/s32-b-auth-implementation-input-output-freeze-v1.json` SHA `50e45a9d46d428bab2677fa79bd19fe8cd8d6aacc70882e29bc3b9f5cdd39240` / 17569B / 529LF。完整27source及三mirror pins、newtests/validationpaths、excludedhistoricalfile写入，未来acceptedplancommit由外部handoff实际绑定，freeze不包含自身/未来commit SHA。

唯一historical untracked `implementation-20260928-s31-aggregate-retry-fix-v2-codex.md` SHA d46cc852c7dc59667c751a403d932a4eaf0a1d5b05f12b5c1d293f278f0b8b2b /4456B/32LF已核；不stage。created_at=2026-09-28T02:32:53.111459+00:00。所有NEW记录O_EXCL/fsync/0444/reopen；当前下一门为accepted plan commit，再assigned五路径implementation及非作者codeReview。用户持续授权覆盖普通本地推进和draft交付；不把planPASS提升为实现、CI或业务Gate。
