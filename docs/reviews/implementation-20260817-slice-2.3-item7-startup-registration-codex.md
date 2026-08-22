# Slice 2.3 Item 7 startup registration implementation evidence

- **Gate / work unit**: Gateflow D0 implementation / Slice 2.3 Item 7 startup registration exact-seven
- **Writer role**: Codex implementation worker；不是 Controller / reviewer，不启动或重排 Gateflow
- **Status**: `IMPLEMENTATION_VALIDATED_AWAITING_INDEPENDENT_CODE_REVIEW`
- **Date / timezone**: 2026-08-22 / Asia/Shanghai
- **Repository / branch**: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform`
- **Accepted implementation base**: `ee75d17955a4a8f30a56a02cae56fac34df79be5`
- **Index**: empty before and after；未 stage / commit / push / PR
- **Candidate diff SHA-256**: `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9`

## 1. Accepted plan lineage and frozen entry

本次只执行 Controller 已接受的 Item 7 contract，不重做 plan/review，也不修改下列 accepted artifacts：

| artifact | SHA-256 | lines | bytes |
|---|---:|---:|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194` | 3917 | 314076 |
| `docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md` | `a57ec452e71f7f8136b96f7da855546a3ff29cbd0f43d3101f83f62658e5640d` | 236 | 19145 |
| `docs/reviews/plan-acceptance-20260822-slice-2.3-item7-startup-registration-codex.md` | `67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9` | 136 | 9986 |

入口 preflight 逐项命中：branch 与 HEAD 如上；index empty；worktree 当时仅有两项 Controller 冻结的 preserved WIP；本 artifact 路径当时不存在；其余五个 implementation path 命中 frozen baseline。两项 WIP 被 preserve-and-adopt，未 reset、覆盖或丢弃。

## 2. Scope and non-goals

### 2.1 Persistent implementation write set（exact-seven）

1. `dayu/services/startup_preparation.py`
2. `tests/application/test_service_startup_preparation.py`
3. `tests/integration/investment/test_identity_repositories_postgres.py`
4. `README.md`
5. `tests/README.md`
6. `dayu/README.md`
7. `dayu/investment/README.md`

全部 source/docs mutation 使用 `apply_patch`。验证全部通过后只额外创建本 implementation evidence artifact。未持久修改任何其它 tracked/untracked path。

### 2.2 Explicit non-goals

- 不实现 research / Agent / Broker handler，不调用真实 provider、模型、Broker、交易或资金接口。
- 不进入 Item 8 final CI / nine-lane scope。
- 不修改 `dayu/fins/**`、`workflows/**`、accepted plan/fix/acceptance 或旧 reviewer artifact。
- 不运行网络、pull/tag 替代、stage、commit、push、PR 或独立 code review。

## 3. Exact-seven identities

| path | before SHA-256 / lines / bytes | after SHA-256 / lines / bytes |
|---|---|---|
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e / 1689 / 63289` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e / 1689 / 63289` |
| `tests/application/test_service_startup_preparation.py` | `a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2 / 4044 / 127443` | `2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545 / 4123 / 130135` |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `91370d76725aabc363e247cfa0bbf077c80e9352a246f5bafaaefd89c132b145 / 2102 / 72114` | `b0049d210864fd3246562c50e926b90793169b6fc694a60401b88d4478004d53 / 2123 / 73549` |
| `README.md` | `7aaff711420bbc9109a9d998ad2b86dd2700cb0f093be800052b18f7d0dcf852 / 2406 / 153419` | `d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94 / 2407 / 153621` |
| `tests/README.md` | `16e2bcdc783b2a4af580f4f4a97e22f3fdb47b7b464e528cf7e4200f733be69c / 612 / 132796` | `1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f / 612 / 132898` |
| `dayu/README.md` | `8ce2507fb9c1ef1204d5085486bca8c94f38ebb92048277c642a1ec867a05666 / 1296 / 65078` | `8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5 / 1297 / 65205` |
| `dayu/investment/README.md` | `a0420ba3ce4b5ed0e7ef2ec9f910d600e650e180c6b234dd4156dfe3e4ff46a7 / 333 / 22886` | `1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331 / 333 / 22921` |

Production source 的 before/after identity 相同，证明 Controller 指定的 source WIP 被原样 preserve-and-adopt；测试与文档只在 accepted Item 7 范围内补齐。

## 4. Implemented accepted contract

### 4.1 Startup composition

Preserved source WIP 已闭合 accepted contract：共享一个真实 PostgreSQL session factory；装配 Job / Schedule / public Source / private Source execution；descriptor 与 handler 各 exact-one；依次 register 后 seal；在 startup recovery 前只发布一次 exact-four service mapping；explicit provider 路径保持既有 identity 与 eager Fins runtime 且不产生 Source-specific 跨平台副作用；19-stage failure matrix 按反向依赖顺序 close，shared engine 仍只 dispose once。

### 4.2 Application owner

- `test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four` 的中文 docstring 增加独立 `Args`（逐名 `monkeypatch`、`tmp_path`）、`Returns`、`Raises`。
- 增加 queue admission closed-shape 分支测试，机械覆盖 NOT_REQUIRED / POSTGRES_ONLY / REDIS 的非法严格矩阵，使 plan 要求的 fresh branch coverage 达标；没有改变生产契约。

### 4.3 PG black-box owner

- 唯一旧 exact-three 测试 rename 为 `test_production_provider_wires_exact_four_service_mapping`。
- mapping 精确断言 `investment_identity`、`investment_sources`、`durable_jobs`、`durable_schedules`。
- 断言 `PlatformSourceSyncServiceProtocol`、`InvestmentSourcesService`、`PostgresSourceSyncRepository` 与 Source/Job/Schedule 三个 store 共享同一 session factory。
- 保留 identity registration 行为与 double-close proof；其它 PG behavior zero semantic expansion。

### 4.4 Documentation decision

- 根 `README.md` 只替换原 `:385-387` 段；`:134` 与该 replacement 之外的全部字节保持不变。
- replacement 明确 exact-one Source Sync handler、platform production composition、无 research/Agent/Broker handler、无真实 provider/model/Broker/trading side effect；保留“本仓库当前不提供 production Compose”，并区分 Compose deployment 与 platform composition。
- `tests/README.md` 记录 PG black-box exact-four、`investment_sources`、exact-one handler 与 shared session factory。
- `dayu/README.md` 与 `dayu/investment/README.md` 同步当前物化真值，不声明 Item 8 完成。

## 5. Validation evidence（accepted §14.0 exact eight）

每个 Python command 均先执行 `source .venv/bin/activate`。所有 pytest process 均使用 `-p no:cacheprovider`，未以 focused 结果替代 PG 或 full-suite gate。

### 5.1 Step 1 — preflight / allowlist

- read-only branch/HEAD/index/status/SHA/line/byte checks：exit 0；命中 `codex/investment-platform` / `ee75d17955a4a8f30a56a02cae56fac34df79be5`、index empty、仅两项 preserved WIP。
- accepted plan/fix/acceptance、两项 WIP、五个 baseline 与 absent artifact 全部 exact；drift 0。

### 5.2 Step 2 — focused + architecture independent processes

```text
source .venv/bin/activate
python -m pytest -p no:cacheprovider tests/application/test_service_startup_preparation.py -q
```

- 最终重跑：64 collected / 64 passed / exit 0。

```text
source .venv/bin/activate
python -m pytest -p no:cacheprovider tests/investment/test_architecture_boundaries.py -q
```

- 独立 process：171 collected / 171 passed / exit 0。

### 5.3 Step 3 — exact named tests + docstring AST

```text
source .venv/bin/activate
python - <<'PY'
# ast.parse both owners; collect FunctionDef/AsyncFunctionDef names;
# assert five required exactly once, four historical names zero;
# ast.get_docstring exact application test and assert Chinese plus
# Args/Returns/Raises headings and monkeypatch/tmp_path entries.
PY
```

结果：`required_exact_once=5`、`forbidden_exact_zero=4`、`docstring_contract=PASS`、exit 0。

### 5.4 Step 4 — Pyright / Ruff

```text
source .venv/bin/activate
pyright dayu/services/startup_preparation.py tests/application/test_service_startup_preparation.py tests/integration/investment/test_identity_repositories_postgres.py
ruff check dayu/services/startup_preparation.py tests/application/test_service_startup_preparation.py tests/integration/investment/test_identity_repositories_postgres.py
ruff check --select F dayu/services/startup_preparation.py tests/application/test_service_startup_preparation.py tests/integration/investment/test_identity_repositories_postgres.py
ruff check --select I dayu/services/startup_preparation.py tests/application/test_service_startup_preparation.py tests/integration/investment/test_identity_repositories_postgres.py
```

- 首次 Pyright：exit 1，PG test 通过 `JobStoreProtocol` / `ScheduleStoreProtocol` 直接访问 `_session_factory` 产生 2 errors；在同一 allowlist test 内增加 `PostgresJobStore` / `PostgresScheduleStore` concrete narrowing 后重跑完整 gate。
- 最终 Pyright：`0 errors, 0 warnings, 0 informations` / exit 0。
- Ruff default / F / I：各 `All checks passed!` / exit 0。

### 5.5 Step 5 — fresh exact-singleton branch coverage

```text
source .venv/bin/activate
python -m coverage run --branch --include=dayu/services/startup_preparation.py \
  -m pytest -p no:cacheprovider tests/application/test_service_startup_preparation.py
python -m coverage json -o <fresh-dir>/coverage.json
python <shape-check> <fresh-dir>/coverage.json
python -m coverage report --fail-under=80
```

- 首次真实 coverage run：63/63 tests passed，但 raw combined `78.56%`，shape threshold command exit 1。只在 application test owner 增加 accepted closed-shape branch coverage 后，重跑受影响的 focused / AST / Pyright / Ruff / coverage gates。
- 最终 fresh dir `/tmp/dayu-s23-item7-startup-coverage.HXnwB7`：64/64 tests passed；`branch_coverage=True`；files exact singleton `['dayu/services/startup_preparation.py']`；raw combined `80.48%`；coverage report exit 0。
- `.coverage` 与 `coverage.json` 逐文件 `/bin/unlink`，空目录 `rmdir`；`COVERAGE_CLEANUP=PASS`。
- 边界记录：一次包含不允许清理语法的 shell 请求被工具在执行前拒绝，未创建目录/未运行 validation；一次 diagnostic 在输出完整缺口后因误写不存在的 `/usr/bin/unlink` exit 127，随后以 exact `/bin/unlink` + `rmdir` 清理。两者均未产生持久第三 artifact。

### 5.6 Step 6 — pinned PG16 isolated black-box

```text
docker image inspect postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8 \
  --format '{{json .RepoDigests}}'
```

- exact local RepoDigest 命中 / exit 0；未 pull、未用 tag 替代、未联网。

```text
source .venv/bin/activate
python -m pytest -p no:cacheprovider -m integration --timeout=120 \
  tests/integration/investment/test_identity_repositories_postgres.py
```

- 单独 process 且该 file 恰好运行一次：17 collected / 17 passed / 15.10s / exit 0；renamed exact-four test collected and passed。
- fixture teardown 后 read-only owner-label audit：container 0、network 0；临时 database/role 随 owned cluster teardown 为 0 residual。

### 5.7 Step 7 — deterministic non-integration

```text
source .venv/bin/activate
python -m pytest -p no:cacheprovider -m "not integration and not e2e" tests -q
```

- 9185 collected / 322 deselected / 8863 selected；`8858 passed, 5 skipped, 322 deselected` / 137.21s / exit 0。
- 5 个既有 skip 不在 Item 7 focused/architecture/PG 禁止 unknown-skip 的三条 owner lane 中；没有用其替代任何 required gate。

### 5.8 Step 8 — README / mechanical / Git boundary

- `cmp <(git show HEAD:README.md | sed '385,387d') <(sed '385,388d' README.md)`：exit 0；root replacement 之外 byte-identical。
- HEAD/current `README.md:134` exact comparison：exit 0；byte-identical。
- UTF-8 exact read + four README contract assertions：`README_CONTRACT=PASS`。
- exact-seven：UTF-8 7/7、final LF 7/7、CR 0、NUL 0。
- `git diff --check`：exit 0。
- pre-artifact audit：worktree diff path count 7、exact allowlist equal；index count 0；untracked count 0。
- accepted master/fix/acceptance identity re-read exact；source WIP before/after exact。
- 边界记录：第一次只读 identity loop 使用 zsh 特殊变量名 `path`，导致 `PATH` 被覆盖并在首个 SHA 前 exit 127；改名 `filepath` 后完整命令 exit 0，无 mutation。

## 6. Canonical candidate diff

唯一 canonical candidate hash 定义为：

```text
git diff --binary --no-ext-diff --full-index \
  ee75d17955a4a8f30a56a02cae56fac34df79be5 -- \
  dayu/services/startup_preparation.py \
  tests/application/test_service_startup_preparation.py \
  tests/integration/investment/test_identity_repositories_postgres.py \
  README.md tests/README.md dayu/README.md dayu/investment/README.md \
| shasum -a 256
```

结果：`2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9`。本 implementation evidence artifact 不进入该 candidate hash。

## 7. Plan gaps and residual risks

- **Blocking implementation / validation residual**: 0。
- **Validation-driven closure**: preserved WIP 的 fresh branch coverage 初值为 78.56%；新增 closed-shape test 后为 80.48%。这是 accepted exact-seven 内的 test closure，不改变生产 contract。
- **Plan gap**: 0；所有修复均可在 exact-seven allowlist 内构造。
- **Deferred by accepted scope**: research/Agent/Broker handlers、real provider/model/Broker/trading、Item 8 final CI/nine-lane。
- **Independent assurance residual**: writer 未做 code review 或 Controller adjudication；candidate 必须由后续独立 reviewers 接收同一 HEAD、candidate diff SHA、七文件 identities 与本 artifact identity。
- **Repository action residual**: 未 stage / commit / push / PR；仅 Controller 可决定下一 gate。

## 8. Completion / stop

Item 7 exact-seven implementation 与 accepted §14.0 validation 已完成。本记录不宣称 independent review PASS 或 Gateflow advancement。Writer 在 implementation evidence freeze 后停止，等待 Controller 派发同一 candidate 的独立 code review。
