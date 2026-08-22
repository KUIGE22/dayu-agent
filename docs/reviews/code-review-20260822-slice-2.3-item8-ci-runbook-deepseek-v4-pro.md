# 独立代码评审：Slice 2.3 Item 8 CI Runbook（DeepSeek V4 Pro）

- **Gate / work unit**：Slice 2.3 Item 8 explicit CI/runbook 独立代码评审（frozen target）。
- **实际模型**：`deepseek-v4-pro[1m]`（按 Controller 要求逐字记录）。
- **路由**：官方 Anthropic 路由（Claude Code harness）。
- **cwd**：`/Users/wsk/workspace/dayu-agent`（全程未切换）。
- **评审人角色**：DeepSeek V4 Pro 独立 reviewer；非 Controller、非 writer；未启动 Gateflow、未实现/修复/暂存/提交/push/PR。
- **START identity**（Controller 冻结）：branch `codex/investment-platform`；HEAD `464aa00e590b23defa4eecc8d853bacd3f376904`；candidate canonical binary diff SHA `1e66741267c211aa4ac6191bab77ac666b6f253fbc2017528422b5eb5871890b`。
- **END identity**：与 START 相同；本评审对工作树/代码/文档零变更，未运行 pytest、Docker、PostgreSQL、网络或任何 Git/shell 命令，未读 MiMo review artifact 与 Item8 implementation artifact。
- **冻结 exact-four identities**（Controller 冻结，本评审未复算，见 §5）：

| Path | SHA-256 / lines / bytes |
|---|---|
| `.github/workflows/ci-mainline.yml` | `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974` |
| `.github/workflows/ci-pr-extended.yml` | `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199` |
| `tests/README.md` | `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004` |
| `tests/investment/test_platform_migrations.py` | `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940` |

- **结论（verdict）**：`FAIL open0/1/1`（fresh H/M/L：H=0、M=1、L=1）。Gateflow 语义下 open>0 不可接受，需按最小修复处理后由 Controller 冻结新 SHA 并派发 fresh re-review。

## 1. 审查范围与 Route

1. 只读 `AGENTS.md`（内容与 `CLAUDE.md` 一致），确认代理硬约束。
2. 只读权威 master plan `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` 的 Item8/Item7 章节（§8.6、§10.1、§11、§12 step 8、§13.4）构建 oracle；只读 `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md`，确认 exact-four 冻结身份与 pinned digest 真源。
3. 逐字只读 exact-four 四文件全文（`tests/README.md` 分两页 1–378 / 379–613 完整覆盖）。
4. 对九个 aggregate ignore / lane 路径逐一直接只读首行，确认真实存在（九次读取全部成功）。
5. 未读 MiMo review artifact、Item8 implementation artifact；未执行任何测试/Docker/PG/网络/Git/shell 操作（遵循 Controller 与用户冻结边界）。

## 2. Oracle（master plan Item8 权威要求）

- **§12 step 8**：Item 8 只在 Item 7 local accepted checkpoint 后，更新两个 extended CI workflow 为 final 九 commands/九 ignores，运行 planned workflow static audit，并**只更新 `tests/README.md` 中 final nine-lane CI 运行方法段**；Item 7 已闭合文字与其它 README 零 diff。
- **§8.6**：workflow static test 与两份 workflow 只属 Item 8；final 九个独立 command / 九个 aggregate ignore；planned named test 为 `test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate`（§13.4 同名）。
- **§11 allowlist**：`ci-mainline.yml` 的 required non-integration 不变；`ci-pr-extended.yml` 仅 pinned pull 与 Slice 2.3 isolated lanes/aggregate ignores。
- **prerequisite plan §2.1/§7.2**：exact-four 冻结身份；三镜像 exact digest：`postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`、`redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78`、`minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`。
- **Item7 truth**：production mapping exact-four `investment_identity / investment_sources / durable_jobs / durable_schedules`、exact-one Source Sync handler、共享 PostgreSQL session factory。

## 3. 逐项核查结果

### 3.1 triggers/jobs/filters 保留 —— PASS
两份 workflow 的 job 键集合与 static test 冻结的 `_WORKFLOW_REQUIRED_JOB_KEYS`（`tests/investment/test_platform_migrations.py:106-127`）精确一致：ci-mainline 7 jobs、ci-pr-extended 5 jobs。非 lane 部分（triggers、concurrency、其余 job steps）由 `_WORKFLOW_NON_LANE_MANIFEST_SHA256`（同文件 :128-131）冻结；数值在本评审 no-shell 边界下无法复算，作为 Controller 冻结的 test 侧常量接受（见 §5）。

### 3.2 exact pinned PG16 / Redis8.4 / MinIO —— PASS
两份 workflow 的 pull 步骤各 3 条命令，与 `_PINNED_IMAGE_PULL_COMMANDS`（`tests/investment/test_platform_migrations.py:90-94`）逐字一致，且与 accepted prerequisite §7.2 的 digest 同源。PG 为 digest-only pin（`postgres@sha256:64154d…`，无 tag 可漂移），Redis 为 `8.4.0-bookworm` digest pin，MinIO 为 `RELEASE.2025-09-07T16-13-09Z` digest pin。

### 3.3 九个独立 integration 命令 + 九个 aggregate ignore 且路径真实 —— PASS
- 两份 workflow 各 9 条 `pytest tests/integration/investment/<lane>.py -q -m integration --timeout=120`，顺序与 `_ISOLATED_INTEGRATION_LANES`（`tests/integration/test_platform_migrations.py` 同文件 :95-105）完全一致，并逐字等于 static test :191-199 构造的 `expected_isolated_commands`。
- 九个路径逐一直接读取首行确认真实存在（全部成功）：`test_platform_migrations_postgres.py`、`test_job_request_identity_migration_postgres.py`、`test_identity_repositories_postgres.py`、`test_postgres_jobs.py`、`test_postgres_schedules.py`、`test_postgres_sources.py`、`test_source_sync_job.py`、`test_fins_s3_blob_repository_minio.py`、`test_redis_queue_wakeup.py`。
- aggregate 的 `--ignore` 集合与 lane 路径同序一致（`aggregate_ignores == _ISOLATED_INTEGRATION_LANES`），`count("--ignore=")==9`、`count("pytest ")==1`。

### 3.4 命令引号 / pytest markers / timeouts —— PASS
`-m "integration and not e2e"` 位于 YAML 字面块标量内，双引号原样进入 bash 命令；九 lane 使用无引号需求的 `-m integration --timeout=120`；行尾反斜杠续行在字面块标量下不被 YAML 吞掉、由 bash 正确拼接；required lanes 保持 `--timeout=60 -m "not integration and not slow and not e2e"`。

### 3.5 aggregate 不能重跑 lanes —— PASS
aggregate 恰好排除全部九个 lane 路径（同序），且每个文件只出现一次 pytest 入口，不存在隐藏的第二条 aggregate 命令；lane 步骤失败时 job 中止（GitHub Actions 默认 `bash -e`），aggregate 不会在 lane 失败后单独放行。

### 3.6 static test 抗 order/path/digest 漂移与 pytest9 输出假设 —— PASS
`test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate`（`tests/investment/test_platform_migrations.py:173-282`）将 lane 顺序、路径、digest、ignore 顺序、`docker pull ` 出现次数（==3）全部字面冻结，两份 workflow ledger 必须相等（:282）；非 lane manifest 由 frozen SHA-256 冻结。全文件 3178 行中不存在任何 pytest 输出解析或 pytest 版本相关假设（唯一 subprocess 是 Item4 基线 git diff helper :904-917，与 pytest 输出无关）。

### 3.7 README 与可执行 CI 一致 —— FAIL
见 M1 / L1。

### 3.8 Item7 truth 无漂移 —— PASS
`tests/README.md:53` 的 production provider mapping（`investment_identity / investment_sources / durable_jobs / durable_schedules` 四个 Service）、exact-one Source Sync handler、共享 PostgreSQL session factory 与 §10.1 逐项一致；static test 与两份 workflow 不触碰 Item7 语义；无 Item7 旧名（如 empty registry / exact-three）残留。

## 4. Findings（fresh）

### M1 —— `tests/README.md` 运行方式段与可执行 CI 不一致（final nine-lane runbook 未物化）
- **位置**：`tests/README.md:118-150`（关键行 :128、:134-145、:149）。
- **场景**：Item8 两份 workflow 已物化 final ledger（`ci-mainline.yml:112-141`、`ci-pr-extended.yml:34-63`：3 条 pinned pull、9 条独立 lane 命令、1 条 aggregate 命令带 9 个 `--ignore`），但 `tests/README.md` 的"运行方式"段仍是 0006 prerequisite 时代文本。
- **直接证据**：
  1. `tests/README.md:128` 仍写 "identity/schedules/Redis/final九lane仍属于 Item 8 future CI…本阶段两份 workflow 保持 zero diff"——与同一 candidate 内两份 workflow 已含九 lane 变更直接矛盾，也与同一文件 :57 已写 "extended CI 的 final ledger 精确为九个独立 pytest 进程" 自相矛盾；
  2. `tests/README.md:140-145` 本地镜像准备只列 2 条 pull（PG、Redis），缺 MinIO pull（workflow 为 3 条）；:149 仍写 "future CI 会先显式 pull 两个 digest"；
  3. 运行方式段实际只覆盖 9 条 lane 中的 7 条（缺 `test_source_sync_job.py` 与 `test_fins_s3_blob_repository_minio.py` 两条 lane 命令）；
  4. aggregate 命令（`pytest -q --timeout=120 -m "integration and not e2e"` + 9 个 `--ignore`）在 README 全文不存在（1–613 行已完整阅读确认）。
- **影响**：违反 master plan §12 step 8（Item8 必须 "只更新 tests/README.md 中 final nine-lane CI 运行方法段"）与项目 README 规则（文档必须与当前代码一致）。operator 按 README 无法本地准备 MinIO 镜像、找不到 2 条 lane 的运行命令，并被 "zero diff / future CI" 表述误导为 CI 尚未物化。
- **最小修复**：将运行方式段的 prerequisite 叙事替换为 final nine-lane runbook：3 条 pinned pull（含 MinIO）、9 条 `pytest tests/integration/investment/<lane>.py -q -m integration --timeout=120`、1 条 aggregate（同序 9 个 `--ignore`）；删除 "本阶段两份 workflow 保持 zero diff"、"final九lane仍属于 Item 8 future CI"、"两个 digest" 等过期表述；:57 的 final ledger 文字保持不动。

### L1 —— 测试职责描述未登记 Item8 workflow audit 合同
- **位置**：`tests/README.md:47`；`tests/investment/test_platform_migrations.py:1-26`（模块 docstring）。
- **场景**：candidate 在该 static test 文件内新增/保留 planned named test（`tests/investment/test_platform_migrations.py:173-282`，名字与 §13.4 逐字一致），但模块 docstring 的覆盖清单与 README:47 的文件职责描述均未提及该 CI workflow audit 合同。
- **直接证据**：模块 docstring（`tests/investment/test_platform_migrations.py:2-4`）只列 "S11-CTRL-07 / S15-CTRL-08 / Slice 2.2 durable schedules / Slice 2.3 source connector health"；`tests/README.md:47` 的职责描述同（未提 workflow audit）。
- **影响**：职责文档与代码不同步，维护者无法从文档得知 "workflow 变更会触发 unit lane 失败" 这一守护关系。
- **最小修复**：两处各补一句该文件的 Item8 workflow audit 职责（exact-three pull / nine lanes / nine ignores / non-lane manifest 冻结）。

## 5. 验证局限（no-Git / no-shell 边界）

- 四个 exact-four SHA/lines/bytes、candidate diff SHA、HEAD 均按 Controller 冻结值接受，未在本地复算（约束禁止 shell/Git）。
- `_WORKFLOW_NON_LANE_MANIFEST_SHA256` 两个常量值无法执行复算，作为冻结 test 侧常量接受；结构一致性（job 键集合、lane/aggregate/pull 逐字内容、双 workflow ledger 相等）已人工比对通过。
- 未执行任何测试；static test 的可运行性基于 3178 行全文的静态推断（无 pytest 输出解析、无网络、无数据库依赖）。
- `tests/README.md` 行数：Read 工具显示 613 total，Controller 冻结为 612（wc -l 口径）；差异为尾部换行的计数口径，按 Controller 冻结值记录，不作漂移判定。
- 未读 implementation artifact 与 MiMo artifact（按指令排除），本评审结论独立于其内容。

## 6. 结论

- **verdict**：`FAIL open0/1/1`（fresh H/M/L：H=0、M=1、L=1）。
- 未发现 workflow 行为或测试 oracle 的正确性、稳定性 High；M1 是 Item8 自身 README 范围（§12 step 8）未完成的直接证据，L1 为职责文档缺口。
- 建议：M1/L1 按最小修复处理后由 Controller 冻结新 SHA 并派发 fresh re-review；本 artifact 不对代码作任何修改，不声称 PASS。
