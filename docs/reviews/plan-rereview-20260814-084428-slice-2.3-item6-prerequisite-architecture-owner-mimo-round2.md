# Slice 2.3 Item 6 prerequisite architecture-owner plan re-review (MiMo Round 2)

- 日期：2026-08-14
- 角色：Fresh independent MiMo Round 2 plan re-reviewer
- Model：MiMo（mimo-v2.5-pro），经由 Claude Code CLI 路由
- Gate：Gateflow Item 6 prerequisite architecture-owner correction；review exact13 candidate closure
- 状态：``PASS / open H/M/L=0/0/0``

## Reviewed frozen triple SHA/lines

| Artifact | SHA-256 | Lines |
|---|---|---:|
| target ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`` | ``451daa12bc53750aa7f7d59e7f6a966ee7469b6bdce662a59999f3c0f0710204`` | 3614 |
| master ``docs/plans/2026-08-10-investment-platform-restoration.md`` | ``47c130f6cf99e188dbec2a8040fa6f3b1a7144e320bfcdad62d88776312097fb`` | 4566 |
| fix ``docs/reviews/plan-fix-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md`` | ``f1b7e8b3bb28e2c1dfea713ec555c094b57c39d6bf5427b27cfccdfcc1a5fcb0`` | 169 |

以上SHA-256与行数均经本机 ``shasum -a 256`` 与 ``wc -l`` 实测确认。

Immutable source review ``docs/reviews/plan-review-20260814-080306.md`` SHA-256
``b588832ef852dea72652b93cef4a4bc0dbafec6a8504bce80d24527c100a7e06`` / 55行，结论
``FAIL / open H/M/L=1/0/0``，唯一High ``S23-I6-PR-01``。本re-review不改写其结论。

Round 1 MiMo artifact ``docs/reviews/plan-rereview-20260814-slice-2.3-item6-prerequisite-architecture-owner-mimo.md``
SHA-256 ``3ad043a43feacc1ca0b1c3730d03799c6437188d529c888081c1259d4b5bcef`` / 134行，
``PASS / open H/M/L=0/0/0``，已``SUPERSEDED``（三份candidate字节变化），不用于本轮gate。

Round 1 DeepSeek V4 Pro artifact ``docs/reviews/plan-rereview-20260814-slice-2.3-item6-prerequisite-architecture-owner-deepseek-v4-pro.md``
SHA-256 ``5e4aed3533d85d8fdb28af2b0a698624f9d7439aaa34abe425dd1285b868e7ba`` / 87行，
``FAIL / open H/M/L=0/0/1``，唯一Low ``S23-I6-DSV4P-REREVIEW-01-L``（85→87计数证据链文件归属误标）。
本re-review已独立验证该Low在当前frozen triple中已关闭。

## Review scope

本re-review只裁决：
1. Round 1 DeepSeek Low ``S23-I6-DSV4P-REREVIEW-01-L``是否在当前frozen triple中已关闭；
2. exact13 candidate是否正确闭合``S23-I6-PR-01``的exact12-vs-Gate6矛盾；
3. 是否存在hidden scope、stale distinctions或其它material finding。

不读取Round 2 DeepSeek output。不实施fix、不运行test/PG/network、不stage/commit/push/PR。

## Evidence

### 1. Round 1 DeepSeek Low closure verification

**Round 1 Low内容**：fix doc与target将85→87、top-level 58→60、nested 27的计数归属误标为production
``dayu/investment/storage/postgres_sources.py``；实则该计数属于``tests/integration/investment/test_postgres_sources.py``。

**target当前写法**（lines 2297–2300）：
> ``_collect_postgres_source_owner_contract_violations(..., expected_function_count=...)``的真实计数``85 -> 87``，
> 并以该既有adversarial owner-contract gate继续检查当前
> ``tests/integration/investment/test_postgres_sources.py``全部module/class scope sync/async函数；production
> ``dayu/investment/storage/postgres_sources.py``的AST总数保持71，与该85 -> 87计数无关。

**fix当前写法**（lines 34–39）：
> architecture owner-contract扫描主体``tests/integration/investment/test_postgres_sources.py``在HEAD为85个函数
> （top-level 58、nested 27）；当前冻结WIP已新增两个top-level provenance tests……AST总数为87
> （top-level 60、nested 27）。production ``dayu/investment/storage/postgres_sources.py``冻结WIP SHA-256为
> ``4104d4ed……``，3004行，AST总数保持71，与该owner-contract 85 -> 87计数无关。

**master当前写法**（lines 307–317）：
> ……prerequisite WIP为``tests/integration/investment/test_postgres_sources.py``新增两条top-level test后，既有
> ``test_integration_tests_carry_chinese_docstrings``的Postgres source owner function-count合同必须由85变为87……

**AST实测确认**：
- ``tests/integration/investment/test_postgres_sources.py``：87函数（top 60 / nested 27）
- ``dayu/investment/storage/postgres_sources.py``：71函数（top 59 / nested 12）

**结论**：三方一致将85→87计数明确归给``test_postgres_sources.py``（gate的被扫描主体），production
``postgres_sources.py`` AST为71且明确标注与此计数无关。Round 1 DeepSeek Low已关闭。

### 2. exact13 allowlist正确性

target lines 2281–2300明确prerequisite为"精确十三个writable path"：
- production（4）：``0006_job_request_identity.py``、``platform_jobs.py``、``postgres_jobs.py``、``postgres_sources.py``
- tests（7）：``test_platform_jobs.py``、``test_platform_migrations.py``、``test_platform_migrations_postgres.py``、
  ``test_job_request_identity_migration_postgres.py``、``test_postgres_jobs.py``、``test_postgres_sources.py``、
  ``test_architecture_boundaries.py``
- docs（2）：``tests/README.md``、``dayu/investment/README.md``

master lines 311–317一致。fix lines 56–81一致。三方manifest逐path相等。

### 3. Architecture owner delta唯一性

target lines 2295–2300明确：
- 只允许更新``expected_function_count=85 -> 87``
- 不得新增architecture test名
- 不得放宽collector遍历范围、中文docstring、Args/Returns/Raises、类型或adversarial owner-contract规则
- 除该单一ratchet外，architecture文件必须zero diff

master lines 311–313一致。fix lines 46–53一致。三方一致。

### 4. Architecture test当前状态

``tests/investment/test_architecture_boundaries.py`` line 1208当前为``expected_function_count=85``。
文件SHA-256 ``aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48`` / 3842行。
git status中该文件不在dirty set，确认85→87 delta尚未执行，符合"plan gate完成后才可恢复"。

### 5. 12项prerequisite named tests

target lines 3112–3123列出12项名称。fix lines 97–108列出相同12项。三方逐名相等。不新增测试名。

### 6. 44 coverage keys / 174 final names

target line 3538："44 coverage keys（29 tracked-existing + 15 planned-new）"。
target line 3539："exact named catalog为174"。
master一致。fix lines 86–87一致。新增第十三path是test path，不改变任何production key或owner tuple。

### 7. 四PG进程

exact13 tests中受prerequisite影响的PG owner文件精确为：
``test_platform_migrations_postgres.py``、``test_job_request_identity_migration_postgres.py``、
``test_postgres_jobs.py``、``test_postgres_sources.py`` 四个。
§14 六个PG/migration owner ledger不变。

### 8. Item 6 main exact20/51与Item 8 defer

target lines 2817–2818："48项named handoff加本candidate三项service/schedule测试，共51项"。
target line 2304："exact20/51与Item 8 workflow/docs defer全部保持不变"。
fix line 91–92一致。target lines 3318、3332确认Item 8 workflow defer。

### 9. Stale exact12 / hidden scope扫描

target中``exact12``出现处：line 5（historical context描述Round 1 DS）、line 6（historical Round 4）、
line 3600（"现有exact12 WIP"描述pre-fix状态）。所有均在historical或pre-fix-state语境中。
当前授权语句一致使用exact13（lines 2281、2304、3538–3539、3601–3603）。

master中``exact12``出现处：lines 294、303、307、315、363、378、384–385、4139、4261，
全部为historical或pre-fix-state描述。当前条目使用exact13（lines 311、317、364、370、4148、4194、4266）。

无stale current-scope exact12 statement，无hidden scope扩张。

### 10. Implementation WIP逐字节冻结

| Path | Expected SHA | Actual SHA | Lines | Match |
|---|---|---|---:|---|
| ``0006_job_request_identity.py`` | ``d67272cf…`` | ``d67272cf…`` | 1597 | ✓ |
| ``platform_jobs.py`` | ``a5a7ddb2…`` | ``a5a7ddb2…`` | 114 | ✓ |
| ``postgres_jobs.py`` | ``ebfd6554…`` | ``ebfd6554…`` | 5401 | ✓ |
| ``postgres_sources.py`` | ``4104d4ed…`` | ``4104d4ed…`` | 3004 | ✓ |
| ``test_platform_jobs.py`` | ``2dfa3837…`` | ``2dfa3837…`` | 176 | ✓ |
| ``test_platform_migrations.py`` | ``6fa7419f…`` | ``6fa7419f…`` | 2951 | ✓ |
| ``test_platform_migrations_postgres.py`` | ``8aece2a4…`` | ``8aece2a4…`` | 6827 | ✓ |
| ``test_job_request_identity_migration_postgres.py`` | ``cbe9b6ca…`` | ``cbe9b6ca…`` | 1061 | ✓ |
| ``test_postgres_jobs.py`` | ``cb0473ea…`` | ``cb0473ea…`` | 4494 | ✓ |
| ``test_postgres_sources.py`` | ``26092014…`` | ``26092014…`` | 4519 | ✓ |
| ``tests/README.md`` | ``16e2bcdc…`` | ``16e2bcdc…`` | 612 | ✓ |
| ``dayu/investment/README.md`` | ``a0420ba3…`` | ``a0420ba3…`` | 333 | ✓ |
| ``test_architecture_boundaries.py`` | ``aed6d882…`` | ``aed6d882…`` | 3842 | ✓ |

13个WIP文件SHA-256与fix freeze table逐字节匹配。

### 11. Repo状态

- HEAD commit：``e58e63c785646950dce297e6f50b152f6a0e49a1``
- 分支：``codex/investment-platform``
- dirty set：12个WIP文件（exact12 pre-fix）+ 2个docs（target/master本次docs-only fix更新）+
  4个untracked（0006 migration、fix artifact、2个prior review artifact）
- ``test_architecture_boundaries.py``不在dirty set，确认85→87 delta未执行
- 无prerequisite scope外的production/test变更

## Findings

无。Round 1 DeepSeek Low已关闭；exact13 candidate正确闭合``S23-I6-PR-01``：
- allowlist从12扩大到13，只新增architecture owner path
- 唯一授权delta为``expected_function_count=85 -> 87``
- 不新增test名、不放宽任何collector/doc/type/adversarial规则
- 12项named tests、44 keys、174 names、四PG进程、六PG owner、Item6 main exact20/51、Item8 defer全部不变
- 85→87计数明确归给``test_postgres_sources.py``，production ``postgres_sources.py`` AST为71且无关
- 无stale current-scope exact12 statement、无hidden scope
- 13个WIP文件逐字节冻结

## Open H/M/L

``0/0/0``

## Verdict

``PASS``

## Repo status

- HEAD commit：``e58e63c785646950dce297e6f50b152f6a0e49a1``
- 分支：``codex/investment-platform``
- 未stage/commit/push/PR
- 未运行test/PG/network

## Frozen artifact

本artifact写入后SHA-256与行数将由Controller冻结。
