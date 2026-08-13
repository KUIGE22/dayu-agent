# Code Review

## Scope

- Mode: current changes（Gateflow Item 4 Candidate 8 final frozen re-review）
- Review time: `2026-08-13 13:18:40 +0800`
- Branch: `codex/investment-platform`
- Base: `595564ebcbd398fb84a4eab21e0cd9e045f56dd5`
- Output file: `docs/reviews/code-review-20260813-item4-schema-candidate8.md`
- Included scope: `dayu/cli/workspace_migrations/platform_jobs.py`、`dayu/investment/storage/models_identity.py`、新增 `0005_source_connectors_health.py`、四条 Item 4 owner-test paths，以及 accepted plan、原 review、implementation/fix evidence。七条 code/test frozen SHA 分别为 `c397d005`、`d3e034f8`、`a5cbcac7`、`9d303e05`、`91370d76`、`5eb7fbb7`、`d9e494a2`；完整 SHA 与行数已在写入前连续两次复核一致。
- Excluded scope: Item 5 与 restoration-plan 的并行 docs-only 变更；`postgres_identity.py` 相对 base 为 zero diff；未重跑 once-only PostgreSQL migration/identity lanes，也未检查 Item 4 之外的生产路径。
- Parallel review coverage: 一个独立 mechanical reviewer 对七条 frozen paths 复核 changed-function/docstring/type/nested gate，并独立确认本 review 的新表 ACL catalog/test 漏检；最终证据链、严重度与结论由本 reviewer 重新核对。无其它并行 review 结论直接并入。

## Findings

### M4-未修复-中-0005 终态 ACL 自检忽略额外 grantee 与 grant option，downgrade 可在非 exact 权限目录上继续

- **入口/函数**: `downgrade()` -> `_downgrade_admission()` -> `_assert_0005_catalog()`；同一 helper 也由 `upgrade()` 在安装后调用。
- **文件(行号)**: `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py:2229-2283`；缺失的独立真实 PG oracle 位于 `tests/integration/investment/test_platform_migrations_postgres.py:4926-5070`，现有通用 grant tests 位于 `2530-2547`、`2802-2883`、`2920-2962`。
- **输入场景**: 在合法 0005 数据库且业务表为空时，bootstrap owner 给三张新表之一增加第四角色的 table grant（例如给 `pg_monitor` 授权）、增加 PUBLIC/第四角色的 column grant，或把既有 app/audit table/column grant 改为 `WITH GRANT OPTION`，随后执行 downgrade。
- **实际分支**: table ACL 查询先把 grantee 限定为 `PUBLIC`、app、audit，并只投影 `(grantee, table_name, privilege_type)`；column ACL 查询更只读取 app 的 `UPDATE` 并投影 `(table_name, column_name)`。上述漂移因此不进入 actual set，或因 `is_grantable` 被丢弃而与正常 grant 同形；其余 admission 成功后逆向 DDL 继续。
- **预期行为**: accepted plan §8.4 要求三新表的 grant manifest 唯一，catalog test 逐项比较 ACL；§8.5 step 11 要求 upgrade/downgrade 共用的 self-check 证明 ACL exact。任何额外 grantee、额外 privilege 或 grant-option 漂移都应在 destructive DDL 前 fail closed。
- **实际行为**: `_assert_0005_catalog()` 只证明已知 app/audit/PUBLIC 子集的部分 effective privilege identity，不能证明三新表完整 relation/column ACL 集合；downgrade 会接受并随 `DROP TABLE` 静默移除这些未纳入 manifest 的 grants。
- **直接证据**: `2229-2236` 的 `role_table_grants` 查询含 `grantee IN ('PUBLIC', app, audit)`，`2238-2249` 的 set 不含 `is_grantable`；`2250-2256` 的 `column_privileges` 查询固定 `grantee = app AND privilege_type = 'UPDATE'`，`2258-2283` 同样不含 grantee、privilege kind或 grant option。真实 PG exact test `5060-5070` 只用 `has_table_privilege` 检查 app SELECT/INSERT/DELETE 与 audit SELECT；通用 app/audit tests也只检查 effective boolean。H2 的 extra-grantee negatives只作用于 0004 baseline preflight，不覆盖 0005 三新表终态。
- **影响**: exact-catalog gate 与 destructive downgrade admission 可误绿；额外角色可能在漂移存续期间获得新表数据访问，grant-option 漂移可允许继续转授，而 review/迁移证据仍宣称 ACL exact。正常 upgrade DDL 本身仍安装正确 manifest，因此这是终态证明与 fail-closed 漂移检测缺口，不扩大为已闭合的 baseline H2。
- **建议改法和验证点**: 对三新表从 `pg_class.relacl CROSS JOIN LATERAL aclexplode(...)` 枚举全部 grantee，精确比较 owner/app/audit/PUBLIC relation ACL tuple，包含 `is_grantable`；从 `pg_attribute.attacl` 同样枚举全部列、全部 grantee、全部 privilege，期望集只含 app 的 exact column `UPDATE` 且 `is_grantable=false`。production self-check 与 test-owned PG oracle都应使用独立 exact set；新增 extra fourth-grantee、PUBLIC/第四角色 column grant、table/column `WITH GRANT OPTION` 负例，断言 downgrade 在 revision/table/column 未变时失败，清理后仍可 clean cycle。
- **修复风险（低/中/高）**: 中。需要正确处理 owner implicit relation privileges、显式 `relacl`/`attacl`、PUBLIC OID 与 `is_grantable`，避免重演 Candidate 7 把隐式 owner privilege误当作 column `attacl` 的假期望。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。

## Residual Risk

- 原 review 的 H1/H2/M1/M2/M3 已在 Candidate 8 frozen bytes 上逐项复证：7-table single-statement NOWAIT + READ COMMITTED downgrade gate及 `LockNotAvailable`/zero-mutation race证据；21-policy、24-table relation ACL与37条显式 column ACL exact preflight；七路径机械 changed-function gate；CLI exact-singleton raw branch coverage `100.0`；9 CHECK、51 affected constraints、28 affected indexes与11 trigger bindings的 production/test-owned exact oracle及 extra-object negatives。未发现这些已闭合项回归。
- once-only PG 证据仅作只读核验：migration owner目录 `/tmp/dayu-s23-item4-pg-candidate8.gBNdYO` 的 pre/post frozen hashes一致，JUnit为56 tests、0 failures/errors/skips，raw migration coverage `93.54120267260579`；identity目录 `/tmp/dayu-s23-item4-identity-c8.uC3QFD` 为17 tests、0 failures/errors/skips，镜像均解析为本地 pinned digest且 cleanup为空。既有56-pass lane未包含本 finding 的额外 grantee/grant-option negatives，不能消除该风险。
- 本 reviewer只运行 bounded non-PG/static probes：focused M1/CLI 7 passed、schema/H1-H2-M3 static contracts 5 passed；未写 pytest cache，未运行 locked PostgreSQL lane。
- ORM 与 DDL 的新增列、nullable/default、FK/UNIQUE/CHECK/index映射，以及 CLI current-head 行为未发现其它确定的 material defect；未覆盖区域不被表述为已证明正确。

## Conclusion

- **FAIL — open H/M/L: 0/1/0**。Candidate 8 在 M4 修复并由独立真实 PostgreSQL exact-ACL negatives复证前不应进入 Item 4 accepted gate。
