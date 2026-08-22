# Slice 2.3 Item 8 CI/runbook Fresh Re-review — DeepSeek V4 Pro

- 日期：2026-08-22
- 类型：Item 8 candidate 独立 re-review（fresh、单主模型、同 SHA 语义核对）
- Actual model：`deepseek-v4-pro[1m]`
- Harness：official Anthropic harness（Claude Code CLI，official Anthropic route）
- cwd：`/Users/wsk/workspace/dayu-agent`
- Controller frozen HEAD：`464aa00e590b23defa4eecc8d853bacd3f376904`，branch `codex/investment-platform`
- Candidate：`fe95120798aa9d545014d6212879a3f9721aefc14d745661e494c38155294091`（Controller 传递值）
- 真源输入：`AGENTS.md`；`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`（master plan，3918 行全文）；exact-four：
  - `ci-mainline`：SHA-256 `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d` / 288 行 / 9974 字节
  - `ci-pr`：SHA-256 `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770` / 198 行 / 7199 字节
  - `README`（tests/README.md）：SHA-256 `8153c52858141f355808a2d1ff1c0dac5701c59b498ab9953cae8048119e9fa0` / 622 行 / 133971 字节
  - `test module`（tests/investment/test_platform_migrations.py）：SHA-256 `18152a63b77b2192298525ed211e39cf5a0061d4031960bc8601143ec56ad899` / 3180 行 / 110116 字节
- START=END：本 re-review 在一次连续主模型会话内完成，无中断、无恢复、无历史 context 混入。

## 0. 边界声明

1. 严格单主模型执行：未使用 Task/Explore/Agent/子代理，未使用 Bash/shell/Git/glob/find/test/PG/Docker/network；全部读取仅由本模型以 Read 完成，未读目录、未自行定位文件、未读 MiMo/implementation/fix/任何旧 review。
2. 唯一写入：本 artifact 一次 Write；此后不再修改。
3. **SHA-256 与字节数无法在无 shell 边界下独立重算**：只读工具不提供哈希/字节计数。身份核对采用唯一可执行的替代——Read 完整行号与内容语义核对：

   | exact-four 文件 | identity 行数 | Read 显示 | 判定 |
   |---|---|---|---|
   | .github/workflows/ci-mainline.yml | 288 | 289（末行为空行，即尾随换行的显示） | 一致 |
   | .github/workflows/ci-pr-extended.yml | 198 | 199（同上） | 一致 |
   | tests/README.md | 622 | 623（同上） | 一致 |
   | tests/investment/test_platform_migrations.py | 3180 | 3181（同上） | 一致 |

   四文件均呈现「Read 行号 = identity 行数 + 1」且末行为空行，规律一致，判定为 Read 对尾随换行的统一显示行为；四文件内容语义与本 review 全部 oracle 闭合。SHA/字节数的最终确认依赖 Controller 侧 shell 复核，本 artifact 不伪称已计算。

## 1. Fresh 核 M1（master oracle #1：tests/README.md）

按任务给定检查点逐项核对（行号以 candidate 文件为准）：

- **三 pull**：README `:123-125` 为三个显式 `docker pull`：
  `postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`、
  `redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78`、
  `minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`，与 plan §14/§8.6 fixture 同源且与两份 workflow 逐字一致。**闭合**。
- **九 lane**：README `:132-140` 为九个独立 pytest 进程，顺序 0005 migration → 0006 migration → identity → jobs → schedules → sources → source-sync job → MinIO → Redis，与 plan §14 Gate 2 九 lane 顺序及两份 workflow 逐字一致。**闭合**。
- **九 ignore**：README `:147-156` remaining aggregate 以同序九个 `--ignore` 排除上述九 owner，与两份 workflow 逐字一致。**闭合**。
- **aggregate**：README `:143-145`「运行 remaining integration aggregate 时，必须以相同顺序排除上述九个 owner，避免同一 workflow 重复 collect」+ `:57`「remaining `integration and not e2e` aggregate 以同序九个 `--ignore` 防止重复 collect」表述成立，无合并 invocation、无二次 collect。**闭合**。
- **stale zero**：全文件无 stale CI 表述——`:53` production black-box 为 exact-four（`investment_identity`/`investment_sources`/`durable_jobs`/`durable_schedules` 四个 Service）并保留「exact-one Source Sync handler 与共享 PostgreSQL session factory」（Item 7 已接受文字未被改写）；无 exact-three mapping 残留；无「future final-CI defer」残留；`:118-120` 已收口为「历史 0006 corrective prerequisite 的增量账本由其 accepted artifact 保留；当前可运行入口以 Item 8 final ledger 为准」，与 Item 8 完成态一致。**闭合**。
- **L1 两处职责**：README §1 目录分层中与 Item 8 相关的两处职责描述——
  1. `:47` unit lane（`tests/investment/test_platform_migrations.py`）职责含「同时负责 Item 8 extended workflow audit，锁定 exact-three pinned pulls、nine independent lanes / nine aggregate ignores 及 non-lane manifest」；
  2. `:49-58` integration lane 段职责含「extended CI 的 final ledger 精确为九个独立 pytest 进程……两份 workflow 显式 pull 同源 pinned PostgreSQL 16、Redis 与 MinIO digest，remaining aggregate 以同序九个 `--ignore` 防止重复 collect」。
  两处均与实际 workflow/test module 状态逐字一致，非未来设计、非 stale。**闭合**。

M1 全部闭合，0 material open。

## 2. master Item 8 oracle 复核（plan §12 Item 8、§14 Gate 2/3 workflow mutation、§13.4）

1. **三 pinned 镜像显式 pull 且保留既有 PG/Redis digest**：两 workflow 的 `Pull pinned durable platform images` step 均逐字 pull 上述三个 pinned digest，PG 与 Redis digest 为既有值。**闭合**。
2. **九 lane 每命令独立 pytest 进程**：两 workflow `Run isolated durable platform integration lanes` 均为九个独立 `pytest tests/integration/investment/<owner>.py -q -m integration --timeout=120` 命令，无进程组合。**闭合**。
3. **remaining aggregate 九 ignore**：两 workflow `Run remaining extended integration lane` 均为 `pytest -q --timeout=120 -m "integration and not e2e"` + 同序九 `--ignore`。**闭合**。
4. **两 workflow 命令清单逐字一致**：ci-mainline `:114-141` 与 ci-pr `:35-62` 的三 pull、九 lane、aggregate+九 ignore 逐字相同。**闭合**。
5. **required non-integration jobs/filters 不变**：ci-mainline 保留 `pr-required-min-compat`（pyright + `pytest -m "not integration and not slow and not e2e"`）与 `pr-required-lock-smoke`（locked env + Docling smoke + offline bundle），extended-integration 的 push/schedule/dispatch filter 及四个 full-platform-validation jobs 原样；ci-pr 保留 `full-integration` label gate 与四个 full-platform-validation jobs 原样。**闭合**。
6. **workflow static audit 真实物化**：named test `test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate` 在 `tests/investment/test_platform_migrations.py:176` 定义 exactly once，与 plan §13.4 exact name 逐字一致；以 YAML parser + AST 断言（非手工说明）核对：
   - `_PINNED_IMAGE_PULL_COMMANDS` 三行与两 workflow pull step 逐字一致，且每 workflow `source.count("docker pull ") == 3` 在当前字节下成立；
   - `_ISOLATED_INTEGRATION_LANES` 九项与两 workflow 九 lane 文件及顺序逐字一致；`expected_isolated_commands` 逐行匹配，每命令恰含一次 `tests/integration/investment/` 与一次 `.py`；
   - `expected_aggregate_lines`（前八个 ignore 带续行符、末个不带）与两 workflow 逐行一致；`--ignore=` 计数恰 9、aggregate run 中 `pytest ` 恰 1；
   - `_WORKFLOW_REQUIRED_JOB_KEYS`：ci-pr 五 jobs / ci-mainline 七 jobs，与两 workflow 实际 job key 集合逐项相等；
   - 三个 step 名（Pull pinned durable platform images / Run isolated durable platform integration lanes / Run remaining extended integration lane）在两 workflow 各存在且唯一；
   - 双 workflow ledger 全等断言（`workflow_ledgers[0] == workflow_ledgers[1]`）与 non-lane manifest SHA 锁定存在且逻辑自洽。
   **闭合**（non-lane manifest 两个 SHA 值与 normalized JSON 哈希结果需 Controller 侧 shell/测试运行确认，见边界）。
7. **Item 8 未改写 Item 7 已接受文字**：README `:53` exact-four black-box 职责、`investment_sources`、exact-one Source Sync handler 表述保留；candidate 四文件中无 Item 7 四个旧 startup 测试名、无旧 exact-three 表述残留。**闭合**。
8. **candidate 集合**：会话起始 git status 快照显示 modified 恰为两份 workflow、`tests/README.md`、`tests/investment/test_platform_migrations.py`，与 exact-four 一致，未观察到 allowlist 外实现/README 文件被改（快照为辅助证据，最终 allowlist audit 由 Controller shell 复核）。

Item 8 全部 oracle 闭合，0 material open。

## 3. master Item 7 truths 复核（可观察面）

- `tests/README.md:53` black-box exact-four / `investment_sources` 职责保留且无 drift（§10.1/§14.0.8 Item 7 已接受文字）。
- `tests/README.md:55` 保留「该 fixture 不隐式 pull」Redis fixture 真值（Item 8 redis fixture prerequisite 合同），与 §14 Item 8 显式 pull 分工一致。
- candidate 四文件不含 Item 7 的五个 startup named test 定义、四个旧名及 PG black-box owner 文件，Item 8 未触碰 Item 7 的 exact-seven 文件（本 review 不读这些文件本身，仅按 candidate 集合核对）。
- 未发现 Item 7 truth 与 Item 8 candidate 冲突。

## 4. 边界与未覆盖项（如实记录）

1. 四文件 SHA-256 与字节数未独立重算（无 shell 边界）；仅行号规律与内容语义核对，见 §0。
2. `_WORKFLOW_NON_LANE_MANIFEST_SHA256` 的两个冻结值与运行时 YAML 归一化哈希的一致性依赖测试执行；静态上 test 的归一化逻辑确定、job key 集合与实际一致。
3. 未读 `README.md`、`dayu/README.md`、`dayu/investment/README.md`、两 workflow 之外的任何文件；它们的 Item 8 zero diff 由 Controller shell 复核，本 review 无法声称已验证。
4. candidate 提交身份（`fe9512079…`）与工作区字节是否严格对应，由 Controller 侧 `git` 复核；本 review 以 Read 所得工作区字节为核对对象。
5. 未运行 pytest/pyright/ruff；test module 的 AST 断言与 workflow 当前字节的静态核对结果见 §2，运行级 PASS 证据属于 Item 8 implementation 账本。

## 5. Verdict

**PASS / open H/M/L = 0/0/0**

- High：0；Medium：0；Low：0。
- Fresh 核 M1（README 三 pull、九 lane、九 ignore、aggregate、stale zero、L1 两处职责）全部闭合。
- master Item 8 全部 oracle 闭合；master Item 7 truths 在可观察面上全部闭合。
- 无 material open；上述边界项均为无 shell 边界的验证限制，不构成 code/material finding。

Reviewer：deepseek-v4-pro[1m]（single main model，official Anthropic harness）；artifact 由本模型一次 Write 生成，未使用任何子代理或 shell。
