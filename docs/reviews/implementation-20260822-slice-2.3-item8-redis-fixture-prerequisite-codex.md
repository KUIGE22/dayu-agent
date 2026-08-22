# Slice 2.3 Item 8 Redis fixture prerequisite implementation

## 1. Gate 与冻结身份

- **Role**：Gateflow implementation worker；不是 Controller 或 reviewer。
- **Work unit / Slice**：`Slice 2.3 Item 8 Redis fixture prerequisite / S23-I8-RFP-01`。
- **Accepted-plan commit / HEAD**：`9ad3720b5f3c04fabca1be0602b4b6a79d080f33`。
- **Accepted plan**：`docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`。
- **Plan acceptance**：`docs/reviews/plan-acceptance-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `a3533e22725376247c540b2113748c588362e71f6fdac072fd142e99870ee0b9 / 44 / 3453`，`ACCEPTED FOR IMPLEMENTATION / open H/M/L=0/0/0`。
- **Implementation START**：`tests/integration/investment/test_redis_queue_wakeup.py` = `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`。
- **Implementation END**：`tests/integration/investment/test_redis_queue_wakeup.py` = `f0c1f316b586b14fbbcb377975e6891eca97f65b81d99f5bca285a6bf708d116 / 755 / 21032`。
- **Canonical candidate diff SHA-256**：`e2849db2e46d1524c565ac02b0846a7a58e0e96857c277f0db8624cee2c5ce60`，由 `git diff --binary -- tests/integration/investment/test_redis_queue_wakeup.py | shasum -a 256` 计算，只覆盖本 prerequisite implementation path。
- **Persistent implementation write set**：上述 Redis test 与本 artifact，exact two。Item 8 exact-four 是 pre-existing preserved WIP，不属于本 prerequisite mutation。

## 2. Scope / Non-goals

### 2.1 已实施

唯一修改 `tests/integration/investment/test_redis_queue_wakeup.py`：

1. SQLAlchemy import加入 `text`。
2. 新增 `_SCHEMA = "dayu_platform"` 与 frozen child-first `_MIGRATED_DATABASE_CLEANUP_TABLES`。
3. tuple包含真实 job FK descendants，保留 `job_schedule_occurrences`，排除无 job FK 的 `job_schedules`，不含 `CASCADE`。
4. 新增 `_clear_migrated_jobs_database(bootstrap_dsn: str) -> None`：只创建一个 bootstrap engine；一个 `engine.begin()` transaction内按tuple顺序逐表 `DELETE`；原异常传播；`finally`恰好一次 `dispose()`。
5. `migrated_jobs_database` teardown先调用cleanup helper，成功后再运行真实 `run_alembic_downgrade(bootstrap_dsn)`；同步fixture中文docstring。

### 2.2 明确未做

- 未改migration、production、shared fixture、workflow、README、三个业务测试名/断言/顺序、镜像、timeout或marker。
- 未放宽`0006` empty-`job_runs` admission，未吞异常、skip/xfail、direct role drop、disable FK/RLS/trigger或使用`CASCADE`。
- 未新增第四个test、第二implementation path、兼容fallback或helper-side count。
- 未运行network/pull/install/provider/model/Broker；未stage/commit/push/PR；未进入code review。

## 3. 已知旧失败与 root cause

Item 8原始隔离Redis lane曾执行同一完整文件：精确收集3，结果`2 passed + 2 fixture errors`。第二个test teardown中，`0006_job_request_identity.downgrade()`因`job_runs`非空fail closed；migration chain未继续到`0001`删除cluster-global group roles，因此第三个test setup再因`dayu_platform_app`已存在失败。

该证据未被隐藏或改写为“首次即绿”。本实现只清理由Redis test-owned jobs产生的真实FK descendants，让严格migration admission继续作为权威readback；不通过弱化migration规避失败。

## 4. Validation evidence

所有Python命令均在`source .venv/bin/activate`后执行；pytest均使用`PYTHONDONTWRITEBYTECODE=1`和`-p no:cacheprovider`。没有pull或网络替代。

| Gate | Command / evidence | Result |
|---|---|---|
| Branch/worktree preflight | branch、HEAD、empty index/untracked、accepted plan/acceptance、Redis baseline、Item 8 exact-four | exit 0；全部exact |
| Unique owner + AST names | `rg --files ...` + direct AST module-scope collector | 唯一Redis owner；三个exact sync tests；无第四项 |
| Collection | `python -m pytest -p no:cacheprovider --collect-only -q tests/integration/investment/test_redis_queue_wakeup.py` | exit 0；exact 3；pytest tree output正确处理 |
| Docker daemon | `docker info --format '{{.ServerVersion}}'` | exit 0；server `29.5.2` |
| PG16 image | `docker image inspect postgres@sha256:64154d0...efa8 --format '{{json .RepoDigests}}'` | exit 0；resolved digest exact |
| Redis image | `docker image inspect redis:8.4.0-bookworm@sha256:c22af04b...0d78 --format '{{json .RepoDigests}}'` | exit 0；resolved digest exact |
| Full isolated Redis file | `pytest -p no:cacheprovider tests/integration/investment/test_redis_queue_wakeup.py -q -m integration --timeout=120` | exit 0；`3 passed in 7.51s`；单process恰一次 |
| PG resource cleanup | container/network filters `label=dayu-slice11.owner` | `0 / 0` |
| Redis resource cleanup | container/network filters `label=dayu-slice22.redis-owner` | `0 / 0` |
| Pyright | `python -m pyright tests/integration/investment/test_redis_queue_wakeup.py` | exit 0；`0 errors, 0 warnings, 0 informations` |
| Ruff default | `python -m ruff check tests/integration/investment/test_redis_queue_wakeup.py` | exit 0 |
| Ruff F | `python -m ruff check --select F tests/integration/investment/test_redis_queue_wakeup.py` | exit 0 |
| Ruff I | `python -m ruff check --select I tests/integration/investment/test_redis_queue_wakeup.py` | exit 0 |
| Architecture | `python -m pytest -p no:cacheprovider -q tests/investment/test_architecture_boundaries.py` | exit 0；`171 passed in 1.19s` |
| Diff mechanics | `git diff --check -- tests/integration/investment/test_redis_queue_wakeup.py` | exit 0 |
| Encoding | direct bytes readback | UTF-8；final LF=true；CR=0；NUL=0 |
| Cleanup contract oracle | AST frozen tuple/body scan | exact 12 tables；occurrence present；schedule parent absent；`CASCADE` absent |
| Changed-path allowlist | sorted `git diff --name-only` | exact Item 8 preserved four + Redis prerequisite test；无其它tracked mutation |
| Index/untracked before artifact | `git diff --cached --quiet`; `git ls-files --others --exclude-standard` | index 0；untracked 0 |

### 4.1 Validation harness incident与corrective re-dispatch

首次执行§7.4 mechanical wrapper时，shell局部变量误命名为zsh特殊变量`path`，覆盖了该子shell的`PATH`；首个`git diff --check`因此报`zsh:3: command not found: git`。Controller裁定它是validation harness error而非product/repo failure，并只重派mechanical finish，不要求重跑已经通过的collection/images/Redis/Pyright/Ruff/architecture。

corrective wrapper改用`candidate_file`等非特殊变量；§7.4全部机械检查exit 0，并再次只读确认两类owner label container/network均为0。该incident与corrective evidence均保留在本artifact，未伪装或省略。

## 5. Preserved Item 8 exact-four END

| Path | END SHA-256 / lines / bytes | Status |
|---|---|---|
| `.github/workflows/ci-mainline.yml` | `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974` | unchanged / unstaged |
| `.github/workflows/ci-pr-extended.yml` | `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199` | unchanged / unstaged |
| `tests/README.md` | `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004` | unchanged / unstaged |
| `tests/investment/test_platform_migrations.py` | `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940` | unchanged / unstaged |

## 6. Docs decision

`README = NO CHANGE`。本变更只收口fixture内部teardown，不改变测试命令、分层、真实Redis owner path、用户接口或runbook；preserved `tests/README.md` 已准确描述Item 8 nine-lane运行方法，修改它会越过prerequisite scope。

## 7. Plan gaps 与 residual risks

- **Plan gaps**：none。accepted exact-one test-file方案可构造，未需要第二path或合同选择。
- **Future migration增加新job FK descendant**：归属future migration owner；必须同步该migration涉及的lifecycle fixtures。当前tuple已与frozen migration DAG核对。
- **Cleanup SQL失败**：保留fail-closed；one-transaction回滚、migration不继续，完整lane非零。不得吞异常；若review构造此反例，由当前slice在唯一test path内修复或STOP交Controller。
- **相似fixture cleanup重复**：本slice不抽shared helper；若未来出现多处真实同步漂移，归属独立later work unit。
- **Redis/PG sibling teardown order**：`job_runtime`先关闭adapter/app engine/login；后续不依赖sibling finalizer相对顺序。owner-label `0/0`是本轮实证。
- **Item 8 remaining aggregate/full validation**：仍归属恢复后的Item 8 gate，本prerequisite不执行也不声称完成。

## 8. Completion / Stop

- **Implementation status**：`READY FOR INDEPENDENT CODE REVIEW`。
- **Review target**：Redis test END identity、candidate diff SHA与本artifact；reviewer须独立检查FK ownership、transaction/dispose/login/downgrade顺序、migration safety、exact-three证据、owner cleanup与Item 8 WIP preservation。
- **Gate boundary**：implementation writer不自评Gateflow PASS；未stage/commit/push/PR，不进入code review或accepted commit。
