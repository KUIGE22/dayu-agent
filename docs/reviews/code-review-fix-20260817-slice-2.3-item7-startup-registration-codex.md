# Slice 2.3 Item 7 startup registration code-review fix evidence

- **Gate / work unit**: Gateflow code-review fix / Slice 2.3 Item 7 startup registration exact-seven
- **Writer role**: Codex fix worker；不是 Controller / reviewer，不启动或重排 Gateflow
- **Status**: `F-01 WRITER-FIXED / AWAITING SAME-REVIEWER RE-REVIEW`
- **Date / timezone**: 2026-08-22 / Asia/Shanghai
- **Repository / branch**: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform`
- **Accepted base HEAD**: `ee75d17955a4a8f30a56a02cae56fac34df79be5`
- **Pre-fix candidate diff SHA-256**: `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9`
- **Post-fix candidate diff SHA-256**: `cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9`
- **Index**: empty before and after；未 stage / commit / push / PR

## 1. START freeze

Fix 前先完整重读 Gateflow skill 与仓库 `AGENTS.md`，再执行只读 drift gate。全部命中：

| item | required / actual |
|---|---|
| branch / HEAD | `codex/investment-platform` / `ee75d17955a4a8f30a56a02cae56fac34df79be5` |
| index | empty |
| canonical pre-fix exact-seven diff | `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9` |
| implementation artifact | `4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f / 219 / 14375` |
| DeepSeek review | `0abf4379e6d1a53c8c8dfb50ceacf256ea503046ff96d28c8f5cf1fe503e8c94 / 156 / 22450`；`FAIL 0/0/1` |
| MiMo review | `561d594b76313ff2bfe6ae01b791bfbc415c008f19a5ec4207bd63dc9683ce64 / 156 / 12708`；`PASS 0/0/0` |
| fix artifact | absent |

START worktree ownership清晰：7 个 inherited exact-seven modified paths，以及 implementation / DeepSeek / MiMo 三个 untracked artifacts；本 fix writer 未把这些 inherited artifacts 当作自身写入。

## 2. Controller adjudication

### 2.1 Accepted finding

- **F-01 Low — accepted**: `tests/integration/investment/test_identity_repositories_postgres.py` module docstring 仍写 production startup exact-three，和同文件 exact-four black-box 直接矛盾。
- **Writer status**: `已修复`；该状态不是最终 re-review 权威，必须由同 reviewer 复核。

### 2.2 Open-question dispositions（不计 H/M/L）

- **OQ-01 — rejected as fix work**: Controller 已裁定 preserved WIP 是 accepted input；不 revert source 的历史格式字节。
- **OQ-02 — rejected as fix work**: Controller 已裁定当前 19-stage incremental matrix 足够；不新增 stage 或测试面。
- **OQ-03 — rejected as fix work**: application test module 的 Slice 0.2 引言是 non-exclusive historical introduction；不修改。

除 F-01 外没有接受其它 finding；未处理 MiMo（0/0/0）不存在的 finding，也未扩大 scope。

## 3. Persistent write set and exact mutation

本次唯一允许并实际发生的 persistent mutations：

1. 修改 `tests/integration/investment/test_identity_repositories_postgres.py`；
2. 创建本 artifact `docs/reviews/code-review-fix-20260817-slice-2.3-item7-startup-registration-codex.md`。

F-01 采用最小 docstring-only 修改：

- “production startup 组合精确承载三个真实 Service”改为“四个真实 Service”；
- `investment_identity` 后补入 `investment_sources`（`InvestmentSourcesService`）；
- 保留 `durable_jobs` / `durable_schedules`、导入图 future-module 边界、resource cleanup 与模块其它字节。

未修改 production code、application test、README、accepted plan/fix/acceptance、implementation artifact 或任一 reviewer artifact。

## 4. Proportionate validation

每次 Python execution 前均执行 `source .venv/bin/activate`。

### 4.1 Focused application owner

```text
python -m pytest -p no:cacheprovider tests/application/test_service_startup_preparation.py -q
```

结果：64 collected / 64 passed / exit 0。

### 4.2 AST exact-name and docstring gates

只读 `ast.parse` 两个 test owners，递归收集 `FunctionDef/AsyncFunctionDef`，并检查 application exact docstring 与 PG module docstring。

结果：

- required startup names exact-one = 5；
- historical names exact-zero = 4；
- application 中文 `Args` / `Returns` / `Raises` + `monkeypatch` / `tmp_path` = PASS；
- PG module exact-four、`investment_sources` / `InvestmentSourcesService` 存在、exact-three stale text zero = PASS；
- exit 0。

### 4.3 Pyright / Ruff

```text
pyright dayu/services/startup_preparation.py \
  tests/application/test_service_startup_preparation.py \
  tests/integration/investment/test_identity_repositories_postgres.py
ruff check <same-three-paths>
ruff check --select F <same-three-paths>
ruff check --select I <same-three-paths>
```

结果：Pyright `0 errors, 0 warnings, 0 informations`；Ruff default / F / I 均 `All checks passed!`；全部 exit 0。

### 4.4 Pinned PG16 isolated lane

```text
docker image inspect \
  postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8 \
  --format '{{json .RepoDigests}}'
```

本地 exact digest 命中 / exit 0；未 pull、未用 tag 代替、未联网。

```text
python -m pytest -p no:cacheprovider -m integration --timeout=120 \
  tests/integration/investment/test_identity_repositories_postgres.py
```

结果：独立 process 17 collected / 17 passed / 17.03s / exit 0；exact-four black-box collected and passed。fixture teardown 后 owner-labelled container 0 / network 0，临时 role/database 随 owned cluster teardown 为 0 residual。

### 4.5 README / mechanical / boundary

- `git diff --check`: exit 0。
- 根 README replacement 以外 `cmp` byte-identical；`README.md:134` byte-identical；四 README current contract assertions PASS。
- exact-seven UTF-8 / final LF 7/7；CR 0；NUL 0。
- F-01 stale exact-three module text zero；exact-four/module service names存在。
- tracked diff exact-seven；pre-artifact untracked exact为 inherited implementation + DeepSeek + MiMo 三 artifacts；index empty。
- implementation、DeepSeek、MiMo artifacts identities逐项复核未变。

本次只改 PG module docstring，不影响 production statements/branches，因此不重跑 fresh production coverage；不影响全仓其它 owners，因此不重跑 8858-case non-integration aggregate。受影响的 exact owner、AST/type/style 和真实 PG lane 已完整重跑，未削弱任何测试。

## 5. Post-fix exact-seven identities

| path | SHA-256 | lines | bytes |
|---|---:|---:|---:|
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e` | 1689 | 63289 |
| `tests/application/test_service_startup_preparation.py` | `2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545` | 4123 | 130135 |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `1cefaee33dd0a2e93b236e36171efc2aced09dba4863872982eabe54b64c492e` | 2124 | 73611 |
| `README.md` | `d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94` | 2407 | 153621 |
| `tests/README.md` | `1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f` | 612 | 132898 |
| `dayu/README.md` | `8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5` | 1297 | 65205 |
| `dayu/investment/README.md` | `1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331` | 333 | 22921 |

相对 pre-fix candidate，只有 PG owner identity 从 `b0049d210864fd3246562c50e926b90793169b6fc694a60401b88d4478004d53 / 2123 / 73549` 变为上表值；其它六个 exact-seven identities 不变。

## 6. Canonical post-fix candidate

使用 implementation artifact §6 同一冻结命令：

```text
git diff --binary --no-ext-diff --full-index \
  ee75d17955a4a8f30a56a02cae56fac34df79be5 -- \
  dayu/services/startup_preparation.py \
  tests/application/test_service_startup_preparation.py \
  tests/integration/investment/test_identity_repositories_postgres.py \
  README.md tests/README.md dayu/README.md dayu/investment/README.md \
| shasum -a 256
```

结果：`cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9`。本 fix artifact 与 reviewer/implementation artifacts 均不进入 exact-seven candidate hash。

## 7. Residual risk and stop

- **Accepted finding residual**: F-01 writer fix 已落地；最终标题状态与 gate verdict 必须由同 DeepSeek reviewer re-review 决定。
- **New blocking / open question**: 0。
- **Unclassified residual**: 0。
- **Deferred scope**: 沿 accepted plan 保持 Item 8、research/Agent/Broker handlers、真实 provider/model/Broker/trading 为后续 owner；本 fix 不改变其分类。
- **Boundary**: 未 stage / commit / push / PR；未编辑 reviewer artifacts；不自行进入 re-review、accepted commit 或其它 Gateflow gate。

Writer 在 post-fix candidate 与 fix evidence freeze 后停止，交回 Controller 派发 same-reviewer re-review。
