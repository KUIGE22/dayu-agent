# Slice 2.3 Item 8 Redis fixture prerequisite — code-review fix Round2

## 1. Gate 与冻结输入

- **Gate**：Gateflow `code re-review -> fix Round2`；本 writer 不启动 re-review、不推进 gate、不 commit。
- **Repository / branch / HEAD**：`/Users/wsk/workspace/dayu-agent`；`codex/investment-platform`；`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Round1 candidate START**：`tests/integration/investment/test_redis_queue_wakeup.py` = `28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`；candidate diff `6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`。
- **Round1 fix artifact**：`docs/reviews/code-review-fix-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `372f133d1cb764ca9517e8a025d6b86aaf1461fc757df180491e759b2b0ce12c / 73 / 7364`。
- **Domain continuation**：`docs/reviews/code-rereview-20260822-slice-2.3-item8-redis-fixture-prerequisite-domain.md` = `847adce515731f8e68e328164e15baa70ee94190eabee000be40d8c5cf6f599f / 58 / 7022`；`CR-DOM-001` 仍为 Medium open。
- **State/storage re-review**：`docs/reviews/code-rereview-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md` = `909efa5c3fca74dc7477e27f7ed71d9cae582972730a6de08e3430e5544050f8 / 88 / 10042`；`CRR-SS-001` Medium open。
- **Controller adjudication**：两份 review 指向同一未闭合 owner-key 根因并共同接受；只修 tenant predicate，不扩张测试或 implementation scope。
- **Persistent Round2 write set**：修改 Redis test，并创建本 artifact，exact two；全部 mutation 使用 `apply_patch`。

## 2. Round1 partial 与共同根因

Round1 已把 blanket cleanup 收窄为 Redis job type 下的四类正常 descendant和对应 root，但 owner predicate 只绑定 `_JOB_TYPE`。真实数据库 identity 是 `(tenant_id, job_type)`；另一个 tenant 可合法复用同一 job type，因此 Round1 仍会删除跨 tenant foreign evidence。

- `CR-DOM-001`：Round1 为部分修复；job-type 维度已闭合，tenant 维度缺失。
- `CRR-SS-001`：与上述 continuation 同一根因；不是新的 table-set、transaction 或 lifecycle 问题。
- 修复前两组 DELETE 都只传 `{"job_type": _JOB_TYPE}`，没有消费既有 `_TENANT_UUID`。

## 3. Round2 最小修复

### CR-DOM-001 / CRR-SS-001 — fixed, awaiting independent re-review

1. 四类 child DELETE 在既有 `(child.tenant_id, child.job_run_id) -> job_runs -> job_definitions` 复合 lineage 上新增 `owned_run.tenant_id = :tenant_id`。
2. 最终 `job_runs` root DELETE 同样新增 `owned_run.tenant_id = :tenant_id`。
3. 两次 execute params 都精确绑定 `{"tenant_id": _TENANT_UUID, "job_type": _JOB_TYPE}`；definition join继续要求 tenant/id复合相等。
4. Owner identity 因而精确为 `(_TENANT_UUID, _JOB_TYPE)`；另一 tenant 的同名 root/children保留给 `0006` empty-table admission拒绝。
5. Child tuple、DELETE 顺序、one transaction、rollback、`finally dispose()`、closed dynamic identifiers与异常传播均未改变；无 `CASCADE` 或 fallback。

## 4. Exact-three test constraint

Controller 明确冻结 exact-three catalog，不新增或改名第四个测试。完整 Redis 文件真实执行 default-tenant正常路径；跨 tenant hostile case由两组literal tenant+job-type bind、tenant-scoped definition UQ/FK和下一步独立 re-review静态复核。新增第二 implementation path或抽象测试框架均不在本 Round2 scope。

## 5. Post-fix validation

所有 Python 命令均先 `source .venv/bin/activate`；没有 network、pull、install、provider/model 或 Broker 调用。

| Gate | Command / evidence | Result |
|---|---|---|
| Full Redis file | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/integration/investment/test_redis_queue_wakeup.py -q -m integration --timeout=120` | exit 0；exact 3；`3 passed in 7.72s`；Round2 post-fix 单process恰一次 |
| PG owner residue | Docker filters `label=dayu-slice11.owner` | containers/networks `0/0` |
| Redis owner residue | Docker filters `label=dayu-slice22.redis-owner` | containers/networks `0/0` |
| Pyright | `pyright tests/integration/investment/test_redis_queue_wakeup.py` | exit 0；`0 errors, 0 warnings, 0 informations` |
| Ruff default/F/I | 三次 `ruff check`，含 `--select F` 与 `--select I` | 全部 exit 0 |
| Architecture | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q tests/investment/test_architecture_boundaries.py` | exit 0；`171 passed in 1.16s` |
| Static owner predicate oracle | direct AST/text readback | exact 3 tests；tenant predicate 2、job-type predicate 2、复合 definition join 2、双参数 bind 2；无 `CASCADE` |
| Diff/encoding | `git diff --check` + direct bytes | exit 0；UTF-8；final LF=true；CR=0；NUL=0 |
| Changed tracked paths | `git diff --name-only` | Item 8 preserved exact-four + Redis test；无第二 implementation path |

## 6. Frozen Round2 candidate

- **Redis test END**：`f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`。
- **Canonical candidate diff SHA-256**：`26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`，由 accepted-plan HEAD 到当前 Redis test 的 binary diff 计算。
- **Item 8 exact-four preserved**：
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`；
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`；
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`；
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`。
- **README decision**：`NO CHANGE`；tenant owner predicate收窄不改变test命令、catalog、marker或runbook。

## 7. Residual risk 与边界

- 跨 tenant hostile branch未增加动态第四测试；按Controller裁决由closed SQL/FK证据和独立 re-review负责最终关闭，不由fix writer自评 PASS。
- Cleanup仍与当前四类正常 Job descendant FK DAG绑定；未来新增正常 descendant时由migration/test owner同步。
- Prior review、re-review、Round1 fix和implementation artifacts保持逐字不变。
- Index保持空；未stage、commit、push、PR，也未进入re-review。
- **Status**：`READY FOR RE-REVIEW`。
