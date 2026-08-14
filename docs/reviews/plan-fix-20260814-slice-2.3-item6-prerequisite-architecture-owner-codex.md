# Slice 2.3 Item 6 prerequisite architecture-owner plan fix

- 日期：2026-08-14
- 角色：Codex Controller docs-only corrective writer
- Gate：Gateflow plan-fix；接受且只修复immutable source review的唯一High与Round 1 DeepSeek V4 Pro的唯一Low
- 状态：``CONTROLLER ACCEPTED / FRESH SAME-SHA ROUND 2 DUAL PASS OPEN H/M/L=0/0/0 / INITIAL HIGH AND ROUND 1 LOW ACCEPTED+CLOSED / EXACT-9 DOCS-ONLY ACCEPTED PLAN COMMIT NEXT``
- 实施边界：未修改implementation WIP，未运行test/PG，未stage/commit/network/push/PR

## Immutable source review

- Artifact：``docs/reviews/plan-review-20260814-080306.md``
- SHA-256：``b588832ef852dea72652b93cef4a4bc0dbafec6a8504bce80d24527c100a7e06``
- 行数：55
- Conclusion：``FAIL / open H/M/L=1/0/0``
- Finding：``S23-I6-PR-01``，High，accepted；无其它High/Medium/Low。

该review保持immutable。本artifact不改写其FAIL结论，也不把历史Round 4的
``PASS / open H/M/L=0/0/0``当作本轮closure evidence。

## Frozen inputs

- HEAD：``e58e63c785646950dce297e6f50b152f6a0e49a1``
- 修复前target：SHA-256
  ``c95a74d4b62dcf3a9a828fb4461798d555b2b5990930ea79cf16e8946e428659``，3583行
- 修复前master：SHA-256
  ``0e85bc99d76f30b06551ba5785c9dbad01bac8b714437599394791d081c97ead``，4512行
- 历史accepted job-request-identity fix：SHA-256
  ``99a03329c491e7d7e1e10f700167b3edebc2a9df58a09c0d5bdf2d65fe9565ac``，340行
- 历史Round 4 Controller acceptance：SHA-256
  ``a18a15188203740720240134ba41860db61d820f00441f821796d03529b74926``，159行

## Accepted evidence and correction

architecture owner-contract扫描主体``tests/integration/investment/test_postgres_sources.py``在HEAD为85个函数
（top-level 58、nested 27）；当前冻结WIP已新增两个top-level provenance tests，SHA-256为
``26092014cfa0e64afc4a7e30256e636260f78d557cf2c5937b317c731cbe5ad6``，4519行，AST总数为87
（top-level 60、nested 27）。production ``dayu/investment/storage/postgres_sources.py``冻结WIP SHA-256为
``4104d4ed6b4fbdd973368cd4188c321917ad7322ed35ef945bcbe2de00ecc84d``，3004行，AST总数保持71，
与该owner-contract 85 -> 87计数无关。

既有``tests/investment/test_architecture_boundaries.py::test_integration_tests_carry_chinese_docstrings``调用
``_collect_postgres_source_owner_contract_violations``时仍硬编码``expected_function_count=85``。该文件SHA-256为
``aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48``，3842行，且不在历史exact12
allowlist；但计划Gate 6同时要求该architecture/static lane green。因此历史exact12不可构造。

Controller接受review的最小修复路径：future prerequisite writable allowlist由exact12改为exact13，只新增
``tests/investment/test_architecture_boundaries.py``。该文件唯一允许的delta为：

- 保持既有test名``test_integration_tests_carry_chinese_docstrings``；
- 保持既有``_collect_postgres_source_owner_contract_violations``调用与adversarial owner-contract gate；
- 只把``expected_function_count=85``更新为``expected_function_count=87``；
- 不新增architecture test名；
- 不放宽module/class scope sync/async function collector、中文docstring、类型、``Args``/``Returns``/``Raises``、
  forbidden escape或任何adversarial owner-contract规则。

## Exact13 prerequisite writable manifest

Production（4）：

1. ``dayu/investment/storage/migrations/versions/0006_job_request_identity.py``
2. ``dayu/cli/workspace_migrations/platform_jobs.py``
3. ``dayu/investment/storage/postgres_jobs.py``
4. ``dayu/investment/storage/postgres_sources.py``

Tests（7）：

1. ``tests/cli/workspace_migrations/test_platform_jobs.py``
2. ``tests/investment/test_platform_migrations.py``
3. ``tests/integration/investment/test_platform_migrations_postgres.py``
4. ``tests/integration/investment/test_job_request_identity_migration_postgres.py``
5. ``tests/integration/investment/test_postgres_jobs.py``
6. ``tests/integration/investment/test_postgres_sources.py``
7. ``tests/investment/test_architecture_boundaries.py``

Docs（2）：

1. ``tests/README.md``
2. ``dayu/investment/README.md``

除此之外全部zero diff。新增第十三path不改变production key或coverage mapping tuple，只关闭既有architecture owner
truth ratchet；``domain/jobs.py``、``services/jobs.py``、protocol/models、accepted ``0005``、root README、两份CI
workflow及Item 6 main exact20 path继续zero diff。

## Frozen unchanged ledgers

- prerequisite production/test owner由exact10改为exact11，docs仍2，合计exact13；
- prerequisite新增named tests仍精确12项，名称、文件归属与断言均不改变；
- coverage mapping仍精确44 keys；
- final named catalog仍精确174；
- migration/PG owner ledger仍精确六个，dedicated ``0006`` owner与既有``0005`` owner不合并；
- final isolated lane/aggregate-ignore ledger仍九个；本prerequisite不修改workflow、不运行future workflow audit；
- Item 6 main仍exact20 writable paths / 51 named tests；
- Item 8 workflow/docs slice继续defer。

保持不变的12项prerequisite named tests为：

1. ``test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key``
2. ``test_0006_exact_job_request_identity_columns_checks_trigger_acl_rls_and_head_catalog``
3. ``test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity``
4. ``test_0006_upgrade_rejects_retry_mutated_available_at_without_partial_ddl``
5. ``test_0006_upgrade_rejects_legacy_payload_schema_mismatch_without_partial_ddl``
6. ``test_0006_downgrade_rejects_rows_or_external_dependencies_without_cascade``
7. ``test_0006_nowait_lock_conflict_fails_closed_without_partial_ddl``
8. ``test_0006_clean_upgrade_downgrade_upgrade_cycle_preserves_exact_0005_catalog``
9. ``test_new_enqueue_strictly_validates_canonical_payload_before_session_fingerprint_or_publish_and_persists_original_identity``
10. ``test_retry_mutates_only_current_available_at_and_preserves_original_request_identity_columns``
11. ``test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance``
12. ``test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed``

## Implementation WIP byte freeze

本轮docs-only修复前后，下列历史exact12 implementation WIP必须保持逐字节相同：

| Path | SHA-256 | Lines |
|---|---|---:|
| ``dayu/investment/storage/migrations/versions/0006_job_request_identity.py`` | ``d67272cfaab8074886b5f1e1ed2741a253631eed20f4b000d35279a22f10d890`` | 1597 |
| ``dayu/cli/workspace_migrations/platform_jobs.py`` | ``a5a7ddb2b7dd1740af828bc46e99faba39710a7596f25410a205c7dcc076f382`` | 114 |
| ``dayu/investment/storage/postgres_jobs.py`` | ``ebfd6554e070f9921e9d84175d9345d34d73a445ad5853b17414b880515b7b3f`` | 5401 |
| ``dayu/investment/storage/postgres_sources.py`` | ``4104d4ed6b4fbdd973368cd4188c321917ad7322ed35ef945bcbe2de00ecc84d`` | 3004 |
| ``tests/cli/workspace_migrations/test_platform_jobs.py`` | ``2dfa3837e8b8288245d37401e0728dd836e6eb774e13c9e6748e04edff22bc84`` | 176 |
| ``tests/investment/test_platform_migrations.py`` | ``6fa7419fb627c2188a65707da7415e8293d4d355744832141a40850fbe183a0b`` | 2951 |
| ``tests/integration/investment/test_platform_migrations_postgres.py`` | ``8aece2a4f76af66f610f65aca96357e22855280c16832a20252102a9da87282f`` | 6827 |
| ``tests/integration/investment/test_job_request_identity_migration_postgres.py`` | ``cbe9b6ca999e4df05ed7cdec985be605ba0e94b9f9dfc7fc005e1ea2c4fe5496`` | 1061 |
| ``tests/integration/investment/test_postgres_jobs.py`` | ``cb0473ea0194b3c0001a233c530a9a8e4642954cbfaca8e475362d8a3c2b0189`` | 4494 |
| ``tests/integration/investment/test_postgres_sources.py`` | ``26092014cfa0e64afc4a7e30256e636260f78d557cf2c5937b317c731cbe5ad6`` | 4519 |
| ``tests/README.md`` | ``16e2bcdc783b2a4af580f4f4a97e22f3fdb47b7b464e528cf7e4200f733be69c`` | 612 |
| ``dayu/investment/README.md`` | ``a0420ba3ce4b5ed0e7ef2ec9f910d600e650e180c6b234dd4156dfe3e4ff46a7`` | 333 |

``tests/investment/test_architecture_boundaries.py``同样保持上述
``aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48``字节，直到本轮plan gate完成后才可按唯一
85 -> 87 delta恢复exact13 implementation。

## Finding disposition

### S23-I6-PR-01-已修复-[高]-exact12遗漏必需architecture owner

- Decision：``ACCEPTED / FIXED-IN-PLAN``。
- Closure：target与master已把当前future prerequisite allowlist、bookkeeping、sequencing改为exact13，并冻结唯一
  architecture delta；历史Round exact12记录保留为historical，不再充当当前授权。
- Open H/M/L after this docs-only fix candidate：``0/0/0``，但这只是fix作者处置，不是独立review verdict。

### S23-I6-DSV4P-REREVIEW-01-L-已修复-[低]-85→87计数证据链文件归属误标

- Decision：``ACCEPTED / FIXED-IN-PLAN``。
- Round 1 evidence：MiMo artifact SHA-256
  ``3ad043a43feacc1ca0b1c3730d03799c46437188d529c888081c1259d4b5bcef`` / 134行为
  ``PASS / open H/M/L=0/0/0``；DeepSeek V4 Pro artifact SHA-256
  ``5e4aed3533d85d8fdb28af2b0a698624f9d7439aaa34abe425dd1285b868e7ba`` / 87行为
  ``FAIL / open H/M/L=0/0/1``。两份artifact保持immutable。
- Closure：target与本fix已把85/87、top-level 58 -> 60、nested 27明确归给被扫描的integration test owner，
  并明确production ``postgres_sources.py`` AST为71且与此计数无关。
- Round 1 MiMo PASS只锁定修复前旧三SHA，因本轮candidate字节变化而``SUPERSEDED``；不得用于Round 2 gate。

## Validation and next gate

本轮只允许机械docs检查：authorized-path diff、stale-current exact12 scan、implementation WIP SHA复核、
``git diff --check``、line/SHA/status/index freeze；未运行pytest、PG或network。

Round 2 closure：

- MiMo artifact ``docs/reviews/plan-rereview-20260814-084428-slice-2.3-item6-prerequisite-architecture-owner-mimo-round2.md``，SHA-256 ``19e8a592510fd84bf2066b7586bee269ff6421db988e20afb94cf2baddb1f353`` / 189行，actual model ``mimo-v2.5-pro``、Claude Code CLI route，``PASS / open H/M/L=0/0/0``。
- DeepSeek artifact ``docs/reviews/plan-rereview-20260814-slice-2.3-item6-prerequisite-architecture-owner-deepseek-v4-pro-round2.md``，SHA-256 ``06aacf4e8ff252ae490a8f83a6fba67cf00fe4df3425c60142f87a6a4cf8b7a6`` / 129行，actual model ``deepseek-v4-pro[1m]``、local Claude Code CLI user-dispatch route，``PASS / open H/M/L=0/0/0``。
- 两路独立锁定同一reviewed semantic triple：target ``451daa12bc53750aa7f7d59e7f6a966ee7469b6bdce662a59999f3c0f0710204`` / 3614、master ``47c130f6cf99e188dbec2a8040fa6f3b1a7144e320bfcdad62d88776312097fb`` / 4566、fix ``f1b7e8b3bb28e2c1dfea713ec555c094b57c39d6bf5427b27cfccdfcc1a5fcb0`` / 169。
- Controller接受并关闭initial High ``S23-I6-PR-01``与Round 1 Low ``S23-I6-DSV4P-REREVIEW-01-L``；无rejected、deferred、needs-more-evidence或unclassified finding。acceptance为``docs/reviews/plan-acceptance-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md``。

唯一后续顺序现为：

1. 只stage Controller acceptance冻结的exact9 docs evidence并创建local docs-only accepted plan commit；exact13 implementation WIP明确不属于该stage；
2. 以该commit为新baseline恢复exact13 WIP，先只完成architecture 85 -> 87 owner ratchet，再按既定prerequisite
   implementation/review/accepted commit闭环；
3. 其后才恢复原Item 6 main exact20/51。

exact9 local docs-only commit成功前不得恢复WIP、运行PG或引用历史PASS越过本gate。
