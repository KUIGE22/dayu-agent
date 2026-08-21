# Slice 2.3 Item 7 startup registration corrective plan fix

- 日期：2026-08-17
- 角色：Codex plan-fix writer；非Controller、非implementation writer、非reviewer
- 状态：``CONTROLLER ACCEPTED / FRESH SAME-SHA DUAL PASS / OPEN 0/0/0 / DOCS-ONLY LOCAL ACCEPTED PLAN COMMIT NEXT``
- 目标：把accepted master plan的Item 7 startup exact-four mapping补成可直接dispatch的bounded handoff
- 修改边界：本artifact与``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``；零代码、零测试执行、
  零stage/commit/push/PR

## 1. Frozen evidence

只读preflight观察到：

- branch ``codex/investment-platform``，HEAD ``d604d8df7613db0103076b3a727156fd74dd9e1b``；
- ``dayu/services/startup_preparation.py``：SHA-256
  ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e``，1689行；
- ``tests/application/test_service_startup_preparation.py``：SHA-256
  ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2``，4044行；
- 除上述两项preserved WIP外无implementation diff；index/untracked empty，``git diff --check`` clean；
- Item 6 accepted review artifact ``docs/reviews/code-review-20260814-182909.md:61-64``明确
  ``item7_started=false``、``item8_started=false``，Item 6 evidence不能证明Item 7；
- master §10已要求auto provider exact-four与one handler，但旧per-slice allowlist/validation未把真实PG black-box和
  README truth同步形成一个闭环；
- ``tests/integration/investment/test_identity_repositories_postgres.py:1625-1682``仍以
  ``test_production_provider_wires_exact_three_service_mapping``及three keys为真值；
- ``tests/README.md:53``仍描述exact-three；``dayu/README.md:155-156``与
  ``dayu/investment/README.md:268-269``仍称production execution registry为空；
- ``AGENTS.md:35``要求每个函数完整中文参数/返回值/异常docstring，``AGENTS.md:61-65``要求测试、Pyright与
  单文件覆盖，``AGENTS.md:68-92``要求tests变更同步测试手册、分层/装配变化同步开发总览；
- preserved application WIP中的
  ``test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four``只有单行docstring，
  是当前唯一Low documentation gap。

## 2. Closed plan decisions

没有``Blocking Questions For Controller``，不得把下列决定留给implementation writer：

1. **Preserve and adopt**：两个WIP是Item 7输入，不是可丢弃草稿。dispatch前复核上述SHA/行数/HEAD/status；漂移即STOP。
2. **Item 7 exact writable implementation set为六个path**：
   ``dayu/services/startup_preparation.py``、
   ``tests/application/test_service_startup_preparation.py``、
   ``tests/integration/investment/test_identity_repositories_postgres.py``、
   ``tests/README.md``、``dayu/README.md``、``dayu/investment/README.md``。
3. PG black-box、``tests/README.md``与``dayu/README.md``全部在Item 7修；``dayu/investment/README.md``也在Item 7修，
   因其已有直接失真文本。root README、Fins README、workflow与其它path全部zero diff。
4. Item 8收窄为两份extended workflow的final nine commands/nine ignores、static workflow audit，以及
   ``tests/README.md``的final-nine-lane运行方法；不得重写Item 7 exact-four/one-handler文本，两个Dayu README zero diff。
5. mandatory catalog从Item 6历史174增加为176：补
   ``test_production_provider_failure_disposes_one_engine_once``与
   ``test_production_provider_wires_exact_four_service_mapping``；Item 7五个startup names各exactly once。
6. 唯一Low只在implementation阶段给
   ``test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four``补中文``Args``
   （``monkeypatch``/``tmp_path``）、``Returns``、``Raises``；本plan gate不改代码。

## 3. Code-generation handoff

Master §10.1是normative delta。Writer不得发明新state，按以下顺序adopt现有实现：

1. 同一session factory构造Job/Schedule/Source stores；同一Host注入Job reader/canceller与Fins gateway；同一既有
   ``DefaultFinsRuntime``只构造一个``FinsService``。
2. 构造Job、Schedule、Fins connector、Source repository/connector registry/public facade/private execution/handler。
3. single composition owner依次register descriptor、register exact handler、seal descriptor registry、seal execution
   registry，断言双sealed、count 1/1、lookup equal、handler identity。
4. 断言完成后才建立exact-four provider，并只调用一次``build_platform_composition``发布；publish先于startup recovery。
5. 任一constructor/register/seal/assert/provider/publish失败均无partial mapping，outer owner按既有逆序close且engine只
   dispose一次；不新增Source-specific lifecycle owner。
6. explicit provider identity/mapping/两registry内部identity/count/sealed状态不变，所有Source-specific trap零调用。

PG black-box唯一rename为exact-four，除保留identity register/double-close外，还断言第四项满足
``PlatformSourceSyncServiceProtocol``并是``InvestmentSourcesService``，其真实
``PostgresSourceSyncRepository``与Job/Schedule stores共享production session factory。README只陈述该已物化事实。

Non-goals：不修改domain/repository/migration/workflow/Host Worker/Scheduler/Fins内部或registry并发模型；不增加第二
handler、Agent/research/Broker/QMT；不重构startup composition；不做格式清理、外部访问或Git repository-health清理。

## 4. Executable validation contract

Master §14.0给出唯一命令与预期，implementation artifact必须逐条记录真实exit/count/hash：

- focused application owner与architecture owner分进程PASS；
- AST机械验证Item 7五名唯一、旧exact-three零残留，并验证唯一Low的中文``Args/Returns/Raises``完整；
- exact三Python path Pyright ``0/0/0``，Ruff default/F/I各exit 0；
- ``startup_preparation.py`` fresh branch-enabled exact-singleton coverage raw combined ``>=80.0``；
- 只读inspect exact pinned PG16 digest后，PG black-box owner独立plain process一次，全部PASS且owned resource零残留；
- required deterministic ``not integration and not e2e``全仓lane独立PASS；
- 三README truth audit、exact-six allowlist、LF/final newline、``git diff --check``、index/untracked audit通过。

不得pull/install、用tag/alternate digest、skip/waive PG、复用coverage data、组合有状态PG owners、运行provider/model/
network/Broker，或把未执行命令写成PASS。

## 5. Artifact and dual-review gate

1. Codex writer产出
   ``docs/reviews/implementation-20260817-slice-2.3-item7-startup-registration-codex.md``，冻结exact-six每文件
   SHA/行数与统一``candidate_diff_sha256``。
2. DeepSeek V4 Pro与MiMo在同一cwd/HEAD/candidate SHA/manifest上并行首审，互不共享prompt、发现或artifact：
   ``docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``与
   ``docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-mimo.md``。
3. Controller逐项裁决；Codex只修accepted findings，写
   ``docs/reviews/code-review-fix-20260817-slice-2.3-item7-startup-registration-codex.md``并按影响重跑门。
4. 各自同一reviewer/model route对同一post-fix SHA独立复审，写两个``code-rereview`` artifact。只有两路均
   ``PASS / open H/M/L=0/0/0``才可Controller acceptance。402、model/cwd/SHA不明或缺artifact表示review未执行。
5. local accepted checkpoint只stage exact-six与本Item implementation/review/fix/re-review/acceptance artifacts；不stage
   其它path，不push、不开PR、不推进Item 8。

当前本plan-fix自身仍需先与master冻结同一semantic SHA，并由DeepSeek V4 Pro与MiMo互不共享首审内容地独立plan
review到``PASS / open H/M/L=0/0/0``，再由Controller acceptance并创建docs-only local accepted plan checkpoint。

## 6. Residual

既有``git fsck``旧worktree/missing-object问题是独立repo-health residual。本work unit不删worktree/ref/object、不运行
reflog expire/gc/prune、不改Git元数据，也不宣称该问题已修。只有它实际阻止本计划的冻结、验证或local commit时才保留
原始错误并STOP，由Controller另开工作单；它不是清理授权，也不能冒充Item 7 finding closure。

## 7. Plan-fix verdict

``HANDOFF-READY CANDIDATE / OPEN PLAN QUESTIONS 0``。这不是review PASS或implementation授权；下一步仅为fresh
same-SHA DeepSeek V4 Pro + MiMo独立plan review。

## 8. S23-I7-DSV4P-01 accepted Low corrective writeback

- Controller只接受DeepSeek V4 Pro本轮的``S23-I7-DSV4P-01`` Low；本writer不扩展finding、不自行裁定关闭或PASS。
- master START为``e75e77e3382bccfa7f2ecd891381761176e9ea163f38b8c60f22391b716c517e``/3852/307390；
  本次只在§13.1的incremental named-test audit与§14.0.3的AST zero-residual assertion写回同一个exact-four旧名集。
- 该集保留原``test_production_provider_wires_exact_three_service_mapping``，并新纳入
  ``test_production_explicit_provider_keeps_custom_composition_after_redis_admission``、
  ``test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry``与
  ``test_source_handler_registration_remains_absent_until_slice_2_3``；任一旧名残留或与new name双名并存都fail closed。
- 精确writeback为master``:3011-3018``与``:3320-3328``；未改动normative implementation contract、
  exact-six allowlist、validation command、path/lane或Item 8边界，也未修改或执行production/test文件。
- 状态仍为``PLAN-FIX WRITTEN / AWAITING FRESH SAME-SHA DUAL PLAN REVIEW``；必须由DeepSeek V4 Pro与MiMo对同一
  post-fix master/fix artifact冻结identity各自重新审查，本条目不是review PASS。

## 9. SA24 DeepSeek rereview accepted findings corrective writeback

- START精确为master
  ``65007079da72782d21ea35d4c2ebc502661665983229f6c651be8c80aef21403`` / 3859行 / 308008字节，本artifact
  ``363e8916ffcf245581bfa0747a5b0d7a82da0f6d08f065e37cf791641d388644`` / 132行 / 9796字节；preserved source/test WIP
  仍为``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 / 63289与
  ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 / 127443。
- accepted source rereview为
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``，SHA-256
  ``07b918fe6ce8b48c2d3bd67f702589018c9a77cf8ca13611cf6f8481197fea0f`` / 203行 / 17178字节，
  verdict ``FAIL / open H/M/L=0/1/1``。Controller只接受新``S23-I7-DSV4P-RR-01`` Medium与
  ``S23-I7-DSV4P-RR-02`` Low；本writer不改review artifact、不自行关闭finding或宣称PASS。
- ``S23-I7-DSV4P-RR-01`` corrective candidate：master active Item 7 implementation set从exact-six收口为
  exact-seven，唯一新path为``README.md``；它只允许修改当前``:385-387``的一个失真段落，其余root README
  字节zero diff。§11 allowlist/count、§12 Item 7/8切片与linear dispatch、§14.0 allowlist/四README审计/artifact/
  reviewer/staging、Item 8 zero-diff、§15 STOP及§16 residual的active wording已同步；master END为
  ``ad9b95b37c614286c18aa34f27b96bb6932f889a2266c2a15fca101da8c73033`` / 3883行 / 310791字节。
- ``S23-I7-DSV4P-RR-02`` corrective candidate：master header与§17.2已冻结historical initial DeepSeek review、
  current DeepSeek rereview ``FAIL 0/1/1``、current MiMo review ``PASS 0/0/0``、accepted findings及writeback surface；
  docs-only checkpoint的唯一artifact families收口为本master + Item 7 ``plan-fix`` + ``plan-review-*`` +
  ``plan-rereview-*`` + ``plan-acceptance-*``，preserved WIP不得混入。
- MiMo artifact
  ``docs/reviews/plan-review-20260822-slice-2.3-item7-startup-registration-mimo.md``（SHA-256
  ``989ee6197f752a7800f374bde7566a0a6f03702061d448e12ae67d2ef296e8b9`` / 129行 / 12617字节，
  ``PASS / open H/M/L=0/0/0``）已记账；Controller将``S23-I7-PR-01``/``S23-I7-PR-02``均裁决为
  ``rejected-with-reason``。PR-01把current WIP误当frozen HEAD，而HEAD中的三个历史名使negative AST集成为有意的
  regression guard；PR-02的docstring修复位于已允许test path且由``AGENTS.md``硬约束触发，不扩scope。
- 为保留完整fix history，§§1–8未改写；其中``exact-six``、root README zero-diff与旧review状态只是
  SA23及更早轮次的historical wording，均被本节与master当前§11/§14.0/§17.2的exact-seven真值supersede，
  不得再作为active dispatch输入。本轮未修改root或其他README、code、test、review artifact。
- 状态为``POST-REVIEW FIX WRITTEN / AWAITING FRESH SAME-SHA DUAL PLAN REREVIEW``；仍禁止implementation/test/PG，
  不是plan review PASS或Controller acceptance。

## 10. SA25 Round-2 accepted findings corrective writeback

- START精确为master
  ``8564c49f2657af61fe08d56480fac1e4f327be29d353efb33c58691f06162584`` / 3883行 / 310791字节，本artifact
  ``8f3eb2008663ef4ed5deb9c9a97c48a89330ff74c612ee3dc56c240fb2dd9cf5`` / 165行 / 12822字节；preserved source/test WIP
  仍为``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 / 63289与
  ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 / 127443。
- accepted DeepSeek V4 Pro Round-2 source rereview为
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round2.md``，SHA-256
  ``a6e7044062da0e56c839e1b237a052fc53593d3fc624c412bd282d55aa2f6ae5`` / 320行 / 29220字节，
  ``FAIL / open H/M/L=0/1/2``。Controller接受全部三项fresh finding，本writer不改review artifact、不自行关闭
  finding或宣称PASS。
- ``S23-I7-DSV4P-RR2-01`` Medium corrective candidate：master§10.1``:2609-2618``现精确列举root
  ``README.md``、``tests/README.md``、``dayu/README.md``与``dayu/investment/README.md``四份README，每文件职责与
  §11/§14.0.8一致，四者均不得写Item 8尚未物化的final CI结果。
- ``S23-I7-DSV4P-RR2-02`` Low corrective candidate：§8.6``:2304-2306``、§13.4``:3259-3260``与
  ``:3275-3277``都冻结Item 6 phase historical catalog=174、Item 7/aggregate final=176；imperative collector必须在
  各自phase证明对应计数，§13 names/counts、Item 6 main51、prerequisite12与file ownership均未改。
- ``S23-I7-DSV4P-RR2-03`` Low corrective candidate：§11``:2740-2744``的root README future replacement保留
  ``本仓库当前不提供 production Compose``部署真值，且``README.md:134``及该replacement paragraph以外字节
  zero diff；§14.0.8``:3400-3407``仅对原``:385-387`` replacement paragraph做case-sensitive/术语精确断言，
  不把部署``production Compose``与platform ``production composition``互为旧真值命中。exact-seven与四README集合不变。
- MiMo Round-2 artifact已记账：
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round2.md``，SHA-256
  ``5606010369b3a566599e88b66a9ceaa988a7d3729f7cb30417973a0ac41944cf`` / 183行 / 11298字节，
  ``PASS / open H/M/L=0/0/0``。master header/§17.2已记录Round-2双路verdict、三项accepted finding与writeback surface。
- master END为``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` / 3903行 /
  312988字节。为保留轮次历史，§§1–9未改写；本轮未修改README、code、test或review artifact。
- 状态为``ROUND-2 FIX WRITTEN / AWAITING FRESH SAME-SHA DUAL PLAN REREVIEW``；仍禁止implementation/test/PG，
  不是plan review PASS或Controller acceptance。

## 11. SA26 Controller acceptance metadata writeback

- 本节是唯一SA26追加；§§1–10是immutable historical ledger，不重写。SA26 START精确为master
  ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` / 3903行 / 312988字节与本artifact
  ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b`` / 196行 / 15624字节；branch
  ``codex/investment-platform``、HEAD ``d604d8df7613db0103076b3a727156fd74dd9e1b``。
- Reviewed semantic snapshot还冻结两项preserved WIP且SA26不修改：
  ``dayu/services/startup_preparation.py`` =
  ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689行 / 63289字节；
  ``tests/application/test_service_startup_preparation.py`` =
  ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044行 / 127443字节。
- Fresh DeepSeek V4 Pro Round-3 artifact
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round3.md`` =
  ``945cecd1329a22576d2132d5e22a465d0bbceec96d8d11c3c31f9aa3218686e8`` / 228行 / 19879字节；actual model
  ``deepseek-v4-pro[1m]``、route ``local Claude Code CLI user-dispatch``、``PASS / open H/M/L=0/0/0``。
  Fresh MiMo Round-3 artifact
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round3.md`` =
  ``b015293d8ef980ccb8a63b71840093aedf792d7170b714239da7250da92d32f2`` / 259行 / 17265字节；actual model
  ``xiaomi/mimo-v2.5``、route ``MiMoCode native (mimo agent, xiaomi/mimo-v2.5)``、
  ``PASS / open H/M/L=0/0/0``。两路独立锁定同一master/fix semantic snapshot。
- Controller接受并关闭``S23-I7-DSV4P-RR2-01`` Medium、``S23-I7-DSV4P-RR2-02`` Low与
  ``S23-I7-DSV4P-RR2-03`` Low；Round-3新增material finding为0。MiMo ``OBS-RR3-01``是被本artifact §9
  supersede声明闭合的non-finding observation，不计H/M/L、不要求改operative contract；DeepSeek五条信息性说明也
  不计finding。accepted open H/M/L为``0/0/0``，无blocking question、deferred、needs-more-evidence或
  unclassified finding。
- SA26只改master header/Gate/§17.2、本artifact顶部status/本节，并新建Controller acceptance artifact；master
  §10.1/§11/§12/§14/§15逐字不动。它们的reviewed START section SHA-256/行/字节分别为：§10.1
  ``ddda833e4ab16446b22f41e8c8d19dc05652f40b6cbd655b295b6d9c83fcd638`` / 46 / 4116，§11
  ``0c85b634b968687fa04fc6b500a12301e88963993d296320601a051c2258f9d2`` / 232 / 20374，§12
  ``2d1462cfc962123ba1ecd58dcb9c00efbdb2193d4ab8f8c1bdf1524af6a37f3e`` / 98 / 8997，§14
  ``8795602e80f31883be02682b0cab455ca74b9732ed9f7b4517a8b55ead097a99`` / 283 / 20975，§15
  ``f419f0f10ba0fa7e65e03bcace8ecb585b06c4aa7a966467f241af275ddf400b`` / 70 / 6656；post-metadata
  reverse audit必须逐值相同。
- Master post-metadata identity冻结为
  ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` / 3917行 / 314076字节；本artifact与
  acceptance artifact的post-metadata identity由最终只读readback冻结，避免自包含SHA循环。
- 当前状态精确为``CONTROLLER ACCEPTED / FRESH SAME-SHA DUAL PASS / OPEN 0/0/0 / DOCS-ONLY LOCAL ACCEPTED PLAN COMMIT NEXT``。
  下一入口只允许acceptance artifact中的exact-ten docs evidence创建local docs-only accepted plan commit；两项WIP与
  所有implementation paths排除。该commit前不授权implementation/test/PG，且本节不是implementation或code-review PASS。
