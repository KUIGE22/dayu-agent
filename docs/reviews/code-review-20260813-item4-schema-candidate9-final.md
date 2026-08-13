# Code Review

## Scope

- Mode: current changes（Gateflow Slice 2.3 Item 4 Candidate 9 FINAL frozen re-review）
- Review time: `2026-08-13 14:00:50 +0800`
- Branch/base: `codex/investment-platform` / `595564ebcbd398fb84a4eab21e0cd9e045f56dd5`
- Output file: `docs/reviews/code-review-20260813-item4-schema-candidate9-final.md`
- Inputs fully re-read: `AGENTS.md`、accepted plan、Candidate 8 review（SHA-256 `0c0c833fdf727aa00e28da2e746f4603fd523d776e97b5308dbc6059c0aa0b4a`）、formal review metadata（pre-review SHA-256 `fb84abab03d39941a59f07c55ccdc8dd77755c9713e0c7bab09e7fc198625d0c`）、implementation（`22140f93ed30250826e4c254ea90246167f663588bbfdfafa403464f41a5eca7`）与 fix evidence（`5c50b848cb8dd813a8364f00ff61c20a0254fe2784b072121ac55b92c0c9155c`）。
- Frozen code/test scope: `platform_jobs.py` `c397d005`/114、`models_identity.py` `d3e034f8`/908、migration `90b66245`/2674、CLI owner `9d303e05`/176、identity PG owner `91370d76`/2102、migration PG owner `1ea9b84c`/6785、unit owner `5595d2b2`/2770。写入前连续两次复核完整 SHA、行数、HEAD 与 empty index 均稳定；`postgres_identity.py` 相对 base 为 zero diff。
- Excluded scope: Item 5 与 restoration-plan 的并行 docs-only 工作；未重跑 once-only PostgreSQL migration/identity lanes，未 stage/commit、未修改生产代码或测试。
- Parallel coverage: independent mechanical reviewer复核 frozen identities、M4 exact ACL与最终允许变更集合；本 reviewer独立重读并裁决全部证据与代码路径。

## Findings

未发现实质性问题。

## Verification

- Candidate 8 的 M4 已闭合：`_assert_0005_catalog()` 直接对三个新表的 `pg_class.relacl` 与全部非 dropped column 的 `pg_attribute.attacl` 使用 `aclexplode`，不按角色或权限预过滤，并以 `(table[, column], grantee, privilege, is_grantable)` exact set 比较。relation ACL期望为 30 tuples（21 owner、6 app、3 audit），column ACL期望为仅 app `UPDATE` 且不可转授的14 tuples；任何额外 grantee、额外 privilege、PUBLIC column grant或 grant option 均进入 actual set并 fail closed（migration `2264-2318`）。
- 真实 PG oracle不导入 production manifest，独立枚举同一完整 ACL catalog（PG owner `4979-5177`）。四个 downgrade negatives覆盖 `pg_monitor` table grant、PUBLIC column grant、app table `WITH GRANT OPTION` 与 app额外 `DELETE`；每个分支均断言 admission失败、revision/27表 schema/注入 ACL 保留，再清理并完成 clean down/up/down（`5179-5463`）。
- 原 H1/H2/M1/M2/M3 无回退：七表 single-statement `ACCESS EXCLUSIVE NOWAIT` 与 READ COMMITTED gate仍先于 admission读取，race test精确断言 `LockNotAvailable` 而非依赖 timeout误绿；baseline 21-policy、24-table relation ACL与37条显式 column ACL仍是 full exact sets；七路径 changed-function AST ratchet仍检查完整中文 docstring、严格类型、禁 `Any`/`object` 与 nested helper；CLI exact-singleton branch coverage仍为100%；9 CHECK、51 affected constraints、28 affected indexes与11 trigger bindings仍有 production exact self-check及独立 PG oracle/extras。
- 持久化 Candidate 9 migration-owner evidence `/tmp/dayu-s23-item4-pg-candidate9.BRYp5m` 经只读复核：唯一 pytest process exit 0，JUnit `56/0/0/0`，`56 passed in 111.46s`；coverage为 branch-enabled exact singleton migration file，374 statements/362 covered、78 branches/65 covered，raw `94.46902654867256%`。pre/post三文件 SHA一致，HEAD/base/index与 pinned PostgreSQL digest一致，cleanup为空。
- unchanged identity owner沿用 frozen Candidate 8 evidence：17 tests、0 failures/errors/skips，identity test与 zero-diff production SHA前后一致；models与CLI exact-singleton evidence分别为77 passed/raw100%与6 passed/raw100%。本 reviewer另跑 bounded non-PG/static probe：两条 review/engineering-ratchet contracts加CLI owner共 `8 passed in 1.69s`，未启动 PostgreSQL。

## Open Questions

- 无。

## Residual Risk

- 本次遵守 Gate 2 once-only约束，没有重跑 locked PostgreSQL lanes；结论依赖上述冻结字节与持久化原始 exit/JUnit/log/coverage/pre-post SHA。任何 code/test byte变化都会使本 PASS失效并要求新 candidate。
- migration self-check和独立 PG catalog oracle共同覆盖 exact DDL/ACL；运行时业务语义仍由后续 Item 5--8 repository/service实现与各自 Gate承担，不属于本 Item 4 schema review。

## Conclusion

- **PASS — open H/M/L: 0/0/0**。Candidate 9 已闭合原 review 的 H1/H2/M1/M2/M3 与 Candidate 8 的 M4，可进入 Item 4 accepted gate。
