# Slice 2.3 Item 8 explicit CI/runbook — implementation evidence

## 1. Gate、基线与边界

- Gate：Gateflow implementation；work unit 为 Slice 2.3 Item 8 explicit CI/runbook。
- Repository / branch / HEAD：/Users/wsk/workspace/dayu-agent；codex/investment-platform；464aa00e590b23defa4eecc8d853bacd3f376904。
- Authoritative plan：docs/plans/2026-08-12-slice-2.3-source-connectors-health.md = 13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194 / 3917 / 314076；执行 §12 Item8、§14、§15。
- Redis fixture prerequisite accepted plan commit：9ad3720b5f3c04fabca1be0602b4b6a79d080f33。
- Redis fixture prerequisite accepted implementation commit / current HEAD：464aa00e590b23defa4eecc8d853bacd3f376904。
- Persistent implementation write set：下述 exact-four existing paths，以及验证全绿后创建的本 artifact；除此之外没有持久写入。
- 非目标：不修改 production、migration、Item7 accepted bytes、root/dayu/investment README、其它 tests/workflows；不执行 network、pull、install、真实 provider/model/Broker；不 stage、commit、push、PR 或进入 code review。

## 2. Exact-four START / END

| Path | HEAD START SHA-256 / lines / bytes | Candidate END SHA-256 / lines / bytes |
|---|---|---|
| .github/workflows/ci-mainline.yml | d7a9113d39e7e054deb054131cf365ee04b6e9b0227022cc813dacffbcf8e153 / 279 / 9049 | 697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974 |
| .github/workflows/ci-pr-extended.yml | 0a8f761951c16fec3aae9a323b8e354b54d7b834e4a4156fb112f922bc35cee3 / 189 / 6274 | 0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199 |
| tests/README.md | 1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f / 612 / 132898 | 798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004 |
| tests/investment/test_platform_migrations.py | b600d5552f19894d75bcd912323d0431230e61faa0f7f7b48f70dda76979cc23 / 2978 / 102638 | 8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940 |

- Canonical candidate diff SHA-256：1e66741267c211aa4ac6191bab77ac666b6f253fbc2017528422b5eb5871890b。
- 计算范围：current HEAD 到 working tree exact-four 的 git diff --binary，路径顺序与上表一致。

## 3. Implemented plan items

1. 两份 extended workflow 保留原 triggers、required jobs、filters、PG16/Redis digest，并新增同源 pinned MinIO pull：
   minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e。
2. 两份 workflow 的 isolated ledger 逐字、逐序一致，为九个独立 pytest process：
   - tests/integration/investment/test_platform_migrations_postgres.py
   - tests/integration/investment/test_job_request_identity_migration_postgres.py
   - tests/integration/investment/test_identity_repositories_postgres.py
   - tests/integration/investment/test_postgres_jobs.py
   - tests/integration/investment/test_postgres_schedules.py
   - tests/integration/investment/test_postgres_sources.py
   - tests/integration/investment/test_source_sync_job.py
   - tests/integration/investment/test_fins_s3_blob_repository_minio.py
   - tests/integration/investment/test_redis_queue_wakeup.py
3. Remaining integration aggregate 以同序 exact-nine --ignore 排除全部 isolated owners；两个 workflow 的 image/command/ignore ledger 相等。
4. tests/investment/test_platform_migrations.py 物化唯一命名 static audit：
   test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate。
   它独立验证 exact-three pulls、exact-nine commands/ignores、双 workflow 等价、required jobs/filters/non-lane manifest与无组合/重复 lane。
5. tests/README.md 只替换 final CI/runbook 方法段；Item7 exact-four startup/black-box truth 保持。

## 4. Validation evidence provenance

### 4.1 Controller-retained gates — 本 resume 未重跑

这些门禁在同一 exact-four candidate 上已经执行并由 Controller 明确要求保留；本 resume 只读复核 candidate identity，不用重复成功掩盖历史。

| Gate | Exact command / evidence | Retained result |
|---|---|---|
| Focused static audit | .venv/bin/python -m pytest -p no:cacheprovider tests/investment/test_platform_migrations.py::test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate -q | 1 passed |
| Platform migration owner | .venv/bin/python -m pytest -p no:cacheprovider tests/investment/test_platform_migrations.py -q | 44 passed |
| Pyright | .venv/bin/pyright tests/investment/test_platform_migrations.py | 0 errors, 0 warnings, 0 informations |
| Ruff default/F/I | 三次 .venv/bin/ruff check，含 --select F 与 --select I | 全部 exit 0 |
| Architecture | .venv/bin/python -m pytest -p no:cacheprovider -q tests/investment/test_architecture_boundaries.py | 171 passed |
| Named catalog | pytest 9 tree-compatible collector + AST owner audit | expected/actual normalized names均176，missing/extra空，definitions exact-one |
| Ordinal audit | §13.3 direct owner assignment | 27 / 4 / 15 / 5 / 2，union exact 53 |
| Pinned image preflight | Docker daemon + exact PG16/Redis/MinIO digest readback | 三个 exact local image均存在；无 pull |

### 4.2 Nine isolated lanes — carried one-time final ledger

每条均为独立 pytest process，参数为 -q -m integration --timeout=120；本 resume 按 Controller 命令不重复已通过的 lanes。

| Ordinal | Exact test file | Result |
|---:|---|---:|
| 1 | tests/integration/investment/test_platform_migrations_postgres.py | 56 passed |
| 2 | tests/integration/investment/test_job_request_identity_migration_postgres.py | 24 passed |
| 3 | tests/integration/investment/test_identity_repositories_postgres.py | 17 passed |
| 4 | tests/integration/investment/test_postgres_jobs.py | 103 passed |
| 5 | tests/integration/investment/test_postgres_schedules.py | 36 passed |
| 6 | tests/integration/investment/test_postgres_sources.py | 30 passed |
| 7 | tests/integration/investment/test_source_sync_job.py | 19 passed |
| 8 | tests/integration/investment/test_fins_s3_blob_repository_minio.py | 11 passed |
| 9 | tests/integration/investment/test_redis_queue_wakeup.py | accepted prerequisite post-fix exact 3 passed |

所有 PG/Redis/MinIO owner-labelled container/network residue均为0；Redis prerequisite最终由accepted commit 464aa00e590b23defa4eecc8d853bacd3f376904冻结。

### 4.3 本 resume 新运行 gates

1. Exact nine-ignore remaining integration aggregate：

       source .venv/bin/activate
       PYTHONDONTWRITEBYTECODE=1 pytest -q --timeout=120 -m "integration and not e2e" \
         --ignore=tests/integration/investment/test_platform_migrations_postgres.py \
         --ignore=tests/integration/investment/test_job_request_identity_migration_postgres.py \
         --ignore=tests/integration/investment/test_identity_repositories_postgres.py \
         --ignore=tests/integration/investment/test_postgres_jobs.py \
         --ignore=tests/integration/investment/test_postgres_schedules.py \
         --ignore=tests/integration/investment/test_postgres_sources.py \
         --ignore=tests/integration/investment/test_source_sync_job.py \
         --ignore=tests/integration/investment/test_fins_s3_blob_repository_minio.py \
         --ignore=tests/integration/investment/test_redis_queue_wakeup.py

   Result：exit 0；23 selected；22 passed、1 skipped、8864 deselected；50.60s。唯一 skip 为既有 tests/integration/fins/test_fins_tools_ground_truth.py，不属于九个 pinned isolated owners。

2. Required deterministic non-integration：

       source .venv/bin/activate
       PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -m "not integration and not e2e" tests -q

   Result：exit 0；8864 selected；8859 passed、5 skipped、322 deselected；133.58s。

3. Final mechanics：
   - git diff --check exact-four：exit 0；
   - tracked changed paths exact-equal four；index 0；artifact前untracked 0；
   - 两份 workflow exact-three pulls、nine commands、nine ignores且顺序/bytes ledger相等；
   - tests README final ledger与Item7 exact-four/Source handler truth同时存在；
   - named static audit AST exact-one；
   - exact-four UTF-8、final LF=true、CR=0、NUL=0；
   - README.md、dayu/README.md、dayu/investment/README.md 相对HEAD zero diff；
   - tests/README.md diff精确为1 insertion / 1 deletion。

## 5. Preserved failure and correction history

以下过程证据没有被最终绿灯覆盖或隐藏：

1. Initial workflow static run 因 MinIO owner path 写成不存在的 tests/integration/test_fins_s3_blob_repository_minio.py 而失败；Controller 以 rg --files 直接证据纠正为 tests/integration/investment/test_fins_s3_blob_repository_minio.py。
2. First exact176 collector 使用与 pytest 9 tree output 不兼容的旧 parser而 false-fail；read-only diagnostic证明 expected/actual normalized names均176、missing/extra为空、AST exact-one、ordinal counts 27/4/15/5/2。未用 source patch掩盖 harness问题。
3. First Pyright run报告8个 reportTypedDictNotRequiredAccess；只在 static test中增加显式 runtime key narrowing，未用 cast/ignore信任未验证 YAML；post-fix Pyright为0/0/0。
4. Controller 曾错误授权非investment MinIO path，实际 lane exit 4 / 0 collected；direct rg证据纠正到唯一真实 investment path，随后MinIO lane为11 passed。该失败不是产品语义失败，但保留在ledger。
5. 初次 Redis lane 为3 collected、2 passed并出现2个fixture errors：第二测试teardown被0006 nonempty job_runs admission拒绝，下一测试setup观察到残留global role。独立 prerequisite 先经accepted plan commit 9ad3720b5f3c04fabca1be0602b4b6a79d080f33，再经双轮ownership fix/re-review，由accepted implementation commit 464aa00e590b23defa4eecc8d853bacd3f376904关闭；最终exact3通过。
6. 本 resume 首次 mechanical wrapper 在shell执行前因Markdown反引号进入JavaScript模板而产生SyntaxError；没有命令执行或文件变化。去除模板歧义后的 corrective wrapper exit 0；不把它记为repo/product failure。

## 6. Docs decision

- tests/README.md：CHANGED，仅同步当前 final nine-lane CI/runbook方法。
- README.md、dayu/README.md、dayu/investment/README.md：NO CHANGE，逐字保持Item7 accepted职责与平台真值。
- 其它README/文档：NO CHANGE。

## 7. Plan gaps、residuals 与停止状态

- Plan gap已由独立 Redis fixture prerequisite处理并以commit 464aa00e冻结；Item8 exact-four无需再修改Redis test。
- Remaining aggregate的1个skip与deterministic lane的5个skip均为既有marker/environment分支；没有failed/error，且不属于九个必须真实执行的pinned lanes。九个lanes均已有真实pass evidence。
- 本地只验证当前macOS环境与静态workflow contract；Linux/Windows/macOS CI matrix仍由后续CI执行，不冒充已运行。
- Independent DeepSeek V4 Pro + MiMo code review尚未开始；本writer不自评review PASS或D0 acceptance。
- 未stage、commit、push、PR；未启动code review或aggregate deepreview。
- Completion status：READY FOR INDEPENDENT CODE REVIEW。
