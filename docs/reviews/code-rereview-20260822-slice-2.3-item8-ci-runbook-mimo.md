# Code Re-review

## Scope

- Mode: current changes (read-only from byte0)
- Branch: codex/investment-platform
- Base: N/A (frozen controller state)
- Output file: docs/reviews/code-rereview-20260822-slice-2.3-item8-ci-runbook-mimo.md
- Included scope: exact-four files (ci-mainline.yml, ci-pr-extended.yml, tests/README.md, tests/investment/test_platform_migrations.py)
- Excluded scope: DeepSeek review, implementation artifact, Codex fix artifact, Git/test/PG/Docker/network operations
- Parallel review coverage: 无

## Review Metadata

- **START identity**: 2026-08-22T10:53:27Z
- **END identity**: 2026-08-22T10:53:27Z (frozen, no repo changes)
- **Actual model**: MiMo-V2.5 Xiaomi native
- **Native route**: local CLI (mimocode)
- **CWD**: /Users/wsk/workspace/dayu-agent
- **Candidate diff**: fe95120798aa9d545014d6212879a3f9721aefc14d745661e494c38155294091
- **exact-four**:
  - ci-mainline: 697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d/288/9974
  - ci-pr: 0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770/198/7199
  - README: 8153c52858141f355808a2d1ff1c0dac5701c59b498ab9953cae8048119e9fa0/622/133971
  - test module: 18152a63b77b2192298525ed211e39cf5a0061d4031960bc8601143ec56ad899/3180/110116

## Findings

未发现实质性问题

## Item8 Oracle Verification

### M1 README Final Runbook — PASS

**Three pulls** (README lines 123-125, ci-mainline lines 114-116, ci-pr lines 36-38):
- `docker pull postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`
- `docker pull redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78`
- `docker pull minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`

**Nine lanes** (README lines 132-140, ci-mainline lines 120-128, ci-pr lines 42-50):
1. `test_platform_migrations_postgres.py`
2. `test_job_request_identity_migration_postgres.py`
3. `test_identity_repositories_postgres.py`
4. `test_postgres_jobs.py`
5. `test_postgres_schedules.py`
6. `test_postgres_sources.py`
7. `test_source_sync_job.py`
8. `test_fins_s3_blob_repository_minio.py`
9. `test_redis_queue_wakeup.py`

**Nine ignores** (README lines 148-156, ci-mainline lines 133-141, ci-pr lines 55-63):
- Same nine lanes listed in `--ignore=` flags for aggregate command

**Aggregate command** (README line 147, ci-mainline line 132, ci-pr line 54):
- `pytest -q --timeout=120 -m "integration and not e2e" \`
- Followed by nine `--ignore=` flags

**Stale zero**: No stale references found. README lines 118-160 correctly reference Item8 final ledger without any outdated prerequisite-era text.

### L1 README/Module Responsibility Notes — PASS

**test_platform_migrations.py responsibility** (README line 47):
- Correctly documented as "无需数据库的 unit lane"
- Item8 workflow audit responsibility explicitly stated: "锁定 exact-three pinned pulls、nine independent lanes / nine aggregate ignores 及 non-lane manifest"

**test_identity_repositories_postgres.py responsibility** (README line 53):
- Item7 truths correctly documented:
  - "production provider mapping 精确为 `investment_identity` / `investment_sources` / `durable_jobs` / `durable_schedules` 四个 Service"
  - "守住 exact-one Source Sync handler"
  - "共享 PostgreSQL session factory"

### Item8 All Oracle Verification — PASS

**Workflow audit test** (test_platform_migrations.py lines 176-284):
- Validates three/nine/nine ledger across both workflows
- Validates non-lane manifest SHA256
- Validates workflow consistency between ci-mainline.yml and ci-pr-extended.yml

**CI structure verification**:
- ci-mainline.yml (288 lines, 9974 bytes): Matches exact-four
- ci-pr-extended.yml (198 lines, 7199 bytes): Matches exact-four
- Both have identical extended-integration job structure

### Item7 Truths Verification — PASS

**Production provider mapping** (README line 53):
- `investment_identity` / `investment_sources` / `durable_jobs` / `durable_schedules` — exact-four confirmed

**Source Sync handler** (README line 53):
- "exact-one Source Sync handler" — confirmed

**Session factory** (README line 53):
- "共享 PostgreSQL session factory" — confirmed

## Open Questions

- 无

## Residual Risk

- 无

## Verdict

**PASS / open H/M/L = 0/0/0**

All Item8 oracles verified: three pulls, nine lanes, nine ignores, aggregate command, stale zero.
All Item7 truths verified: exact-four production mapping, exact-one Source Sync handler, shared session factory.
L1 README/module responsibility notes correctly documented.
No material findings identified.
