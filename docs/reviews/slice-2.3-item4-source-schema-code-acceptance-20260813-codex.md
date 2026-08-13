# Slice 2.3 Item 4 Source Schema — code acceptance

- 日期：2026-08-13
- 分支：`codex/investment-platform`
- Implementation baseline：`595564ebcbd398fb84a4eab21e0cd9e045f56dd5`
- Accepted semantic code commit：`4101fb6da02eb08ddd245561a92e021046fdeccb`
- 状态：**ACCEPTED / SEMANTIC CODE COMMIT RECORDED / READY FOR METADATA-ONLY ACCEPTANCE COMMIT**

## Accepted outcome

Item 4交付Slice 2.3的数据源同步与健康状态schema底座：新增Alembic
`0005_source_connectors_health`，把平台catalog从24表推进到27表；扩展
`source_sync_runs`与`source_health_snapshots`，新增
`source_sync_operations`、`source_health_states`、
`source_health_alert_outbox`，并同步18-table ORM metadata与CLI current-head说明。

迁移以exact catalog、RLS/ACL、CHECK、FK/index、trigger、线性化downgrade
admission和无`CASCADE`逆序回滚闭合fail-closed边界。它没有实现Item 5--8的
repository/service/runtime/UI，也没有调用live provider、模型、Broker或交易接口。

## Accepted semantic commit and exact scope

本地semantic code commit为
`4101fb6da02eb08ddd245561a92e021046fdeccb`，parent为
`595564ebcbd398fb84a4eab21e0cd9e045f56dd5`，commit message为
`gateflow: accept slice-2.3 item4 source schema`。该commit精确包含以下12条路径：

1. `dayu/cli/workspace_migrations/platform_jobs.py`
2. `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py`
3. `dayu/investment/storage/models_identity.py`
4. `tests/cli/workspace_migrations/test_platform_jobs.py`
5. `tests/integration/investment/test_identity_repositories_postgres.py`
6. `tests/integration/investment/test_platform_migrations_postgres.py`
7. `tests/investment/test_platform_migrations.py`
8. `docs/reviews/code-review-20260813-104658.md`
9. `docs/reviews/code-review-20260813-item4-schema-candidate8.md`
10. `docs/reviews/code-review-20260813-item4-schema-candidate9-final.md`
11. `docs/reviews/fix-20260813-slice-2.3-item4-schema.md`
12. `docs/reviews/implementation-20260813-slice-2.3-item4-schema.md`

Commit后index为空；当时剩余dirty集合精确为以下四条foreign Item 5 docs，均未进入
Item 4 commit，也未被本acceptance修改或暂存：

- `docs/plans/2026-08-10-investment-platform-restoration.md`
- `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md`
- `docs/reviews/plan-review-20260813-slice-2.3-item5-storage-protocol-mimo.md`

## Frozen identities

| Artifact / production owner | Lines | SHA-256 |
| --- | ---: | --- |
| `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py` | 2674 | `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` |
| `dayu/investment/storage/models_identity.py` | 908 | `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd` |
| `docs/reviews/code-review-20260813-104658.md`（final formal metadata） | 152 | `5adf3516a08725fd202a7bc12d66850fb78507e9daca4a3b327bf47d6b949683` |
| `docs/reviews/code-review-20260813-item4-schema-candidate9-final.md` | 37 | `a6aed10b0ef1b0b894a62b3f9d56c689f01dda66b76217d21e09a02696325bf1` |
| `docs/reviews/implementation-20260813-slice-2.3-item4-schema.md` | 346 | `22140f93ed30250826e4c254ea90246167f663588bbfdfafa403464f41a5eca7` |
| `docs/reviews/fix-20260813-slice-2.3-item4-schema.md` | 286 | `5c50b848cb8dd813a8364f00ff61c20a0254fe2784b072121ac55b92c0c9155c` |
| `docs/reviews/code-review-20260813-item4-schema-candidate8.md` | 43 | `0c0c833fdf727aa00e28da2e746f4603fd523d776e97b5308dbc6059c0aa0b4a` |

`dayu/investment/storage/postgres_identity.py`保持zero diff，冻结SHA-256为
`23f7a2ae3fe6ea4d354df1fae56c32257bb69bb31a76a73911a2521635ea783e`。

## Review closure

- Formal review接受H1、H2、M1、M2、M3，未reject或defer任何finding。
- Candidate 8 re-review发现并接受M4（0005新表terminal ACL exactness），结论当时为
  `FAIL / open H/M/L = 0/1/0`。
- Candidate 9闭合M4，并确认H1/H2/M1/M2/M3无回退。
- Final independent re-review结论为
  **`PASS / open H/M/L = 0/0/0`**；formal metadata状态同步为
  **`CLOSED / PASS`**。
- Controller最终裁决：H1、H2、M1、M2、M3、M4全部resolved，无blocking open
  question、deferred finding或未分类residual。

## Final gates

- Candidate 9 PostgreSQL migration-owner evidence：
  `/tmp/dayu-s23-item4-pg-candidate9.BRYp5m`；唯一pytest process exit 0，
  **56 passed in 111.46s**，JUnit为56 tests、0 failures/errors/skips。
- 同一coverage data为branch-enabled exact singleton migration owner：374 statements、
  362 covered lines、78 branches、65 covered branches，raw combined
  **94.46902654867256%**；pytest/JSON/shape/report四个exit均为0。
- Candidate 9 migration、PG owner、unit owner的pre/post SHA一致；PostgreSQL镜像解析为
  exact pinned digest，post-run digest不变，owned-container cleanup为空；durable evidence
  digest校验通过。
- Identity PostgreSQL owner沿用unchanged Candidate 8冻结证据：
  `/tmp/dayu-s23-item4-identity-c8.uC3QFD`，**17 passed in 24.11s**，
  JUnit为17 tests、0 failures/errors/skips；当前identity test SHA与zero-diff
  `postgres_identity.py`前后均一致，cleanup为空。
- Models exact-owner evidence：`/tmp/dayu-s23-item4-models-c9.eYa6yw`，
  77 passed，`branch_coverage=true`，exact singleton，174/174 statements，raw
  **100.0%**，run/JSON/shape/report均exit 0。
- CLI exact-owner evidence：`/tmp/dayu-s23-item4-cli-coverage.p9WBCS`，
  6 passed，`branch_coverage=true`，exact singleton，30/30 statements、6/6
  branches，raw **100.0%**，run/JSON/shape/report均exit 0。
- Focused non-PostgreSQL owners：48/48 passed；integration collect-only精确73项，
  由migration owner 56项和identity owner 17项组成。
- 七条production/test path的interpreter-bound Pyright为
  `0 errors, 0 warnings, 0 informations`；Ruff default与`F,I`均PASS。
- M1机械inventory覆盖106个changed/new functions且0 violation；计划要求的14个
  migration named tests与5个corrective tests全局各存在且唯一。
- `git diff --check`、UTF-8/LF/final newline、forbidden-path zero diff、HEAD、
  branch、empty index与exact allowlist审计全部PASS。

## Residual risk and authority

- 本acceptance只证明Item 4 schema/ORM/CLI-head边界；repository、service、runtime与
  UI业务语义由approved Item 5--8及其各自Gate继续承担，不把未来实现写成已完成。
- PostgreSQL lane遵守once-only约束；其结论绑定上述冻结字节。任何production/test byte
  变化都会使Candidate 9证据与final review PASS失效，并要求新candidate。
- Repository-wide full-rule lint/format存量债务不在Item 4 scope；本Item要求的Pyright、
  Ruff default/F/I及工程规范ratchet均已通过，后续由repository maintenance owner处理。
- 本地semantic code commit已经生成；本artifact是随后单独metadata-only acceptance
  commit的唯一推荐stage path。为避免不可能的hash自引用，本artifact**有意不记录未来
  metadata-only commit SHA**；Controller完成该commit后应在controller state中记录其SHA。
- 未执行或授权push、PR、merge、部署、live行情、模型/provider、Broker或交易动作。
