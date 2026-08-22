# Slice 2.3 Item 8 Redis fixture prerequisite — code-review fix

## 1. Gate 与冻结输入

- **Gate**：Gateflow `code review -> fix`；本 artifact 仅记录 Controller 已接受 finding 的修复，不启动 re-review、不推进 gate。
- **Repository / branch / HEAD**：`/Users/wsk/workspace/dayu-agent`；`codex/investment-platform`；`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Accepted plan**：`docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Plan acceptance**：`docs/reviews/plan-acceptance-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `a3533e22725376247c540b2113748c588362e71f6fdac072fd142e99870ee0b9 / 44 / 3453`。
- **Implementation artifact**：`docs/reviews/implementation-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `003f0f1deedc388917ab168e0df3e2e5a2fa6169a39e26a10ffb09b4935ffaf5 / 98 / 9293`。
- **Domain review**：`docs/reviews/code-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-domain.md` = `e03eedbea2dd2c2b45810b36eb64cabe56eb2bebcc3c3acb00aed779270139bf / 49 / 7917`；verdict `FAIL 0/1/0`。
- **State/storage review**：`docs/reviews/code-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md` = `c94902e2a21c4d600e741b67b5e53c27135f903e9ec26ae318bddc675c4f076b / 104 / 9601`；verdict `PASS 0/0/0`。
- **Pre-fix Redis candidate**：`tests/integration/investment/test_redis_queue_wakeup.py` = `f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`；candidate diff `e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`。
- **Persistent fix write set**：修改上述 Redis test，并创建本 artifact，exact two。所有 mutation 均使用 `apply_patch`。

## 2. Controller adjudication

- **Accepted**：`CR-DOM-001` Medium。无条件全表 DELETE 会抹除 foreign job evidence，使 migration admission false-green。
- **No-fix lane**：state/storage review fresh `0/0/0`，没有需要修改的 finding。
- **Scope decision**：保持 exact-three test catalog；不新增、改名或弱化测试，不修改 migration、production、plan、review、implementation artifact、README 或 Item 8 exact-four。

## 3. 修复内容

### CR-DOM-001 — fixed, awaiting re-review

1. 新增唯一模块级 owner 真源 `_JOB_TYPE = "test.redis.integration"`；`_descriptor()` 复用它，避免 cleanup 与 enqueue identity 双真源。
2. cleanup child tuple 收敛为正常 enqueue/claim 会产生的 exact four：`job_events`、`job_attempt_receipts`、`job_leases`、`job_attempts`。
3. 每个 child DELETE 均在同一 transaction 内按 `(tenant_id, job_run_id)` join `job_runs`，再按 `(tenant_id, definition_id)` join `job_definitions`，并以 bind parameter `job_type = _JOB_TYPE` 证明 owner。
4. 最后只删除相同 owner predicate 下的 `job_runs`。不删除 `source_*`、`job_schedule_occurrences`、`agent_run_correlations` 或 foreign job roots。
5. 如果 unexpected cross-domain row 引用 Redis-owned job，最终 `job_runs` DELETE 由 FK fail closed，整个 transaction rollback，后继 downgrade 不运行；foreign job root 保留给正式 `0006` admission 拒绝。
6. 继续使用一个 `engine.begin()` transaction、`finally dispose()`、closed identifier tuple；没有 `CASCADE`、异常吞噬或 migration contract 弱化。

### Plan gap

Accepted plan 的 blanket descendant tuple 在 fresh domain review 中被证明会擦除 foreign evidence。Controller 的 post-review adjudication 明确以 Redis job root ownership 取代该旧 tuple；本 fix 按裁决记录这个 plan gap，没有回写或静默改写 accepted plan 历史。

### 为什么不新增第四个测试

Controller 明确冻结本 work unit 的 exact-three catalog boundary。正常 owner path 已由完整 Redis 文件真实执行；foreign root 保留和 unexpected cross-domain FK rollback 分支由 closed SQL predicate、真实 FK DAG、静态机械 oracle以及下一步独立 re-review 证明。新增第四个动态 hostile test 会越过已接受的 test catalog/scope，故本 fix 不自行扩张。

## 4. Post-fix validation

所有 Python 命令均先 `source .venv/bin/activate`；没有 network、pull、install、provider/model 或 Broker 调用。

| Gate | Command / evidence | Result |
|---|---|---|
| Full Redis file | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/integration/investment/test_redis_queue_wakeup.py -q -m integration --timeout=120` | exit 0；exact 3；`3 passed in 7.42s`；post-fix 单process恰一次 |
| PG owner residue | Docker filters `label=dayu-slice11.owner` | containers/networks `0/0` |
| Redis owner residue | Docker filters `label=dayu-slice22.redis-owner` | containers/networks `0/0` |
| Pyright | `pyright tests/integration/investment/test_redis_queue_wakeup.py` | exit 0；`0 errors, 0 warnings, 0 informations` |
| Ruff default/F/I | 三次 `ruff check`，含 `--select F` 与 `--select I` | 全部 exit 0 |
| Architecture | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q tests/investment/test_architecture_boundaries.py` | exit 0；`171 passed in 1.18s` |
| Static ownership oracle | direct AST/text readback | exact 3 tests；`_JOB_TYPE` 单真源；exact-four child tuple；两处 owner bind；无旧跨域 table literals、无 `CASCADE` |
| Diff/encoding | `git diff --check` + direct bytes | exit 0；UTF-8；final LF=true；CR=0；NUL=0 |
| Changed tracked paths | `git diff --name-only` | Item 8 preserved exact-four + Redis test，未新增其它 tracked mutation |

## 5. Frozen candidate

- **Redis test END**：`28136cd733e960979e92254379d09cd347bcffa7fda83c306fcfcff452faa819 / 774 / 22002`。
- **Canonical candidate diff SHA-256**：`6b55950a3738b70c25ba9e4acf303c486ff25cae28eb9b6f1555f53726e6faf9`，由 accepted-plan HEAD 到当前 Redis test 的 binary diff 计算。
- **Item 8 exact-four preserved**：
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`；
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`；
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`；
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`。
- **README decision**：`NO CHANGE`。本 fix 只收窄 fixture teardown ownership，不改变运行命令、test catalog、marker、用户接口或 runbook。

## 6. Residual risk 与边界

- 未新增动态 hostile test；该未覆盖分支由 Controller 归入 exact-three catalog boundary，并交给独立 re-review 复核 SQL/FK fail-closed 证明，不是 implementation writer 自评关闭。
- Cleanup 与当前 migration FK DAG 绑定；未来若正常 Redis enqueue/claim 新增必需 descendant，migration/test owner 必须同步更新 closed tuple。
- 本 fix 未修改或裁决 Item 8 exact-four、aggregate Item 8、D0 或其它 work unit。
- Index 保持空；未 stage、commit、push、PR，也未进入 re-review。
- **Status**：`READY FOR RE-REVIEW`；finding 的最终 CLOSED/PASS 只能由独立 re-review 与 Controller 裁决。
