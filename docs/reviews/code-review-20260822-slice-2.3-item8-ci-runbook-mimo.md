# Code Review

## Scope

- Mode: current changes (frozen WIP candidate)
- Branch: codex/investment-platform
- Base: 464aa00e590b23defa4eecc8d853bacd3f376904
- Output file: docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-mimo.md
- Included scope: .github/workflows/ci-mainline.yml, .github/workflows/ci-pr-extended.yml, tests/README.md, tests/investment/test_platform_migrations.py
- Excluded scope: tests/integration/investment/test_redis_queue_wakeup.py (prerequisite artifact), production code, migrations
- Parallel review coverage: 无，单一 reviewer 完成全部 review

## Identity

- **Actual model**: MiMo-V2.5 (Xiaomi native)
- **Route/pane**: MiMoCode build agent, primary session
- **CWD**: /Users/wsk/workspace/dayu-agent
- **START**: 2026-08-22T10:32:44Z
- **END**: 2026-08-22T10:35:12Z
- **Candidate diff SHA-256**: 1e66741267c211aa4ac6191bab77ac666b6f253fbc2017528422b5eb5871890b

## Findings

未发现实质性问题。

**Review notes**:

1. **ci-mainline.yml extended-integration job lacks needs**: Job DAG structure is existing baseline, not an Item8 correctness requirement. Item8 only added 9 isolated lanes and 9 ignores to the existing job.

2. **ci-mainline.yml macOS-x64 continue-on-error**: Baseline preserved truth for self-hosted runner stability. Not introduced by Item8.

3. **tests/README.md lines 128-129**: Text belongs to "0006 corrective prerequisite" historical section, documenting that prerequisite's scope. Current Item8 CI state is correctly documented at line 57 ("extended CI 的 final ledger 精确为九个独立 pytest 进程").

4. **test_platform_migrations.py hardcoded SHA256**: Deliberate frozen drift oracle design. Test validates workflow manifest structure against frozen snapshot; manual update expected when structure changes.

5. **ci-pr-extended.yml concurrency comment**: Style suggestion only, no correctness or stability impact.

## Open Questions

无

## Residual Risk

无

## Verdict

**PASS**

**Fresh H/M/L**: 0/0/0

Frozen Item 8 exact-four WIP meets all checklist requirements:
- Preserved triggers/jobs/filters in both workflows
- Exact pinned PG16/Redis/MinIO digests
- 9 independent commands with matching ignores using actual integration paths
- YAML/shell quoting, markers/timeouts, aggregate exclusion correct
- Static test uses YAML parser, no pytest9 parser overfit; detects missing/duplicate/reordered path/digest/ignore drift
- README mirrors runnable CI and preserves Item7 truths
