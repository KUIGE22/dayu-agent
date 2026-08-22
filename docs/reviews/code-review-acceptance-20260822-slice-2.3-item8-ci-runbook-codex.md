# Slice 2.3 Item 8 CI/runbook code-review Controller acceptance

- **Role**: Codex Controller; not the implementation/fix writer and not either independent reviewer.
- **Gate**: Item 8 final CI/runbook implementation, post-fix code review, and local accepted-checkpoint authorization.
- **Date / timezone**: 2026-08-22 / Asia/Shanghai.
- **Repository / branch**: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform`.
- **Accepted base**: `464aa00e590b23defa4eecc8d853bacd3f376904`.
- **Accepted candidate diff SHA-256**: `fe95120798aa9d545014d6212879a3f9721aefc14d745661e494c38155294091`.
- **Verdict**: `ACCEPTED / open H/M/L = 0/0/0`.
- **Boundary**: only a local accepted Item 8 checkpoint is authorized; no push, PR, merge, D0 completion claim, or investment P0/F0 advance.

## 1. Frozen planning and prerequisite lineage

| artifact | SHA-256 / lines / bytes |
|---|---|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194 / 3917 / 314076` |
| Item 7 accepted checkpoint | `71dde28989c315b198318916ad8473512fefa202` |
| Item 8 Redis prerequisite accepted plan | `9ad3720b5f3c04fabca1be0602b4b6a79d080f33` |
| Item 8 Redis prerequisite accepted code | `464aa00e590b23defa4eecc8d853bacd3f376904` |

The Redis prerequisite fixed the real isolated-lane teardown defect before this Item 8 candidate resumed. Its accepted code and review evidence are already contained in the base commit and are not restaged here.

## 2. Accepted implementation and review lineage

| artifact | SHA-256 / lines / bytes | disposition |
|---|---|---|
| `docs/reviews/implementation-20260822-slice-2.3-item8-ci-runbook-codex.md` | `a6e589c60863182cf20066c3bde4a2041a6e9df5339c6b306e116dea79ea024d / 139 / 11327` | implementation evidence |
| `docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-deepseek-v4-pro.md` | `c6258205d51280298a936f61082925035844efa16aa2c93137099450dfb51c78 / 97 / 12425` | first review `FAIL / 0/1/1` |
| `docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-mimo.md` | `a7e1e7720f27e9baa0566ea46bf67867ce5ea1b2ef972af3cafe53adeb5b9492 / 58 / 2477` | first review `PASS / 0/0/0` |
| `docs/reviews/code-review-fix-20260822-slice-2.3-item8-ci-runbook-codex.md` | `40c28f287d9e502adf50fc2382252bc9bca1935421f3536216841cf3639ac49d / 74 / 6019` | accepted minimal fix evidence |
| `docs/reviews/code-rereview-20260822-slice-2.3-item8-ci-runbook-deepseek-v4-pro.md` | `574e981e8543973cccd40e368b14d6e252cac164b1de53550c01f2710cefcf90 / 95 / 11092` | final `PASS / 0/0/0` |
| `docs/reviews/code-rereview-20260822-slice-2.3-item8-ci-runbook-mimo.md` | `884f8a9297ee1f821e8b2f09ffa8d5deb591bcb7004bd5355ebf929b3825a210 / 110 / 4634` | final `PASS / 0/0/0` |

The acceptance artifact deliberately does not embed its own SHA-256 in its preimage. The Controller reports that identity after the file is closed.

## 3. First-review adjudication

### 3.1 DeepSeek V4 Pro

The actual `deepseek-v4-pro[1m]` route found two fresh defects on candidate `1e66741267c211aa4ac6191bab77ac666b6f253fbc2017528422b5eb5871890b`:

| finding | Controller disposition | closure |
|---|---|---|
| M1: the runnable README section still described the earlier `0006` prerequisite, listed two image pulls and seven owner lanes, omitted MinIO and the remaining aggregate, and retained positive `future CI` / `zero diff` language | **accepted** | `tests/README.md` now contains the three exact pinned pulls, nine independent lane commands, the aggregate with the same ordered nine ignores, and no competing current-state wording. |
| L1: the README file catalog and `test_platform_migrations.py` module docstring did not register the Item 8 workflow-audit responsibility | **accepted** | both locations now name the exact-three pull, nine-lane/nine-ignore, and non-lane-manifest drift contract. |

### 3.2 MiMo

The final first-review artifact from the actual `MiMo-V2.5 Xiaomi native` route returned `PASS / 0/0/0`. An earlier draft had mixed advisory notes with a zero finding count; the Controller rejected that inconsistent draft and required the same reviewer to rewrite the artifact with one unambiguous verdict. MiMo's PASS did not override DeepSeek M1/L1; both accepted findings were fixed before the final gate.

## 4. Validation evidence

The implementation writer completed the full Item 8 validation ledger before first review:

- focused workflow static audit: `1 passed`;
- owner/architecture validation: `44 passed` / `171 passed`;
- Pyright: `0 errors / 0 warnings / 0 informations`;
- Ruff default, `F`, and `I`: PASS;
- nine pinned isolated integration processes: `56 / 24 / 17 / 103 / 36 / 30 / 19 / 11 / 3 passed`;
- remaining integration aggregate: `22 passed / 1 existing ground-truth skip / 8864 deselected`;
- deterministic non-integration/e2e lane: `8859 passed / 5 existing skipped / 322 deselected`;
- owner-labelled PostgreSQL, Redis, and MinIO container/network residue: zero;
- README, workflow, exact-four allowlist, UTF-8/LF/final-newline, `git diff --check`, index and untracked mechanics: PASS.

The minimal M1/L1 fix then reran the affected evidence:

- focused named workflow audit: `1 passed`;
- affected owner test file: `44 passed`;
- AST/docstring/runbook oracle: exactly three pulls, nine lanes, nine ignores, stale positive wording zero;
- Pyright `0/0/0`; Ruff default/F/I PASS;
- exact-four allowlist, UTF-8/LF, `git diff --check`, and empty index PASS.

No PostgreSQL, Docker, or network rerun was required by the docstring/runbook-only fix; the two workflow files and their already validated executable commands remained byte-identical.

## 5. Same-reviewer post-fix gate

Both original reviewer routes received candidate `fe95120798aa9d545014d6212879a3f9721aefc14d745661e494c38155294091` and the same exact-four identities. They were forbidden to read one another's output or the implementation/fix artifacts.

| route | final verdict | closure |
|---|---|---|
| `deepseek-v4-pro[1m]` through the official Anthropic harness | `PASS / open H/M/L = 0/0/0` | single main model reread `AGENTS.md`, the complete master plan, and exact-four; M1/L1 CLOSED; no fresh finding |
| `MiMo-V2.5 Xiaomi native` through the native MiMoCode route | `PASS / open H/M/L = 0/0/0` | fresh byte-zero exact-four review; M1/L1 CLOSED; no fresh finding |

The first DeepSeek rereview attempt was discarded before artifact creation because an Explore subagent requested shell approvals. The Controller rejected every approval, interrupted and cleared that attempt, then reran the review with the main DeepSeek model only. The accepted DeepSeek rereview explicitly records no subagent and no shell use.

Therefore the Gateflow requirement of two independent final PASS verdicts with open H/M/L exactly `0/0/0` on the same post-fix SHA is satisfied.

## 6. Accepted exact-four identities

| path | SHA-256 / lines / bytes |
|---|---|
| `.github/workflows/ci-mainline.yml` | `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974` |
| `.github/workflows/ci-pr-extended.yml` | `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199` |
| `tests/README.md` | `8153c52858141f355808a2d1ff1c0dac5701c59b498ab9953cae8048119e9fa0 / 622 / 133971` |
| `tests/investment/test_platform_migrations.py` | `18152a63b77b2192298525ed211e39cf5a0061d4031960bc8601143ec56ad899 / 3180 / 110116` |

## 7. Exact local-checkpoint staging authorization

The local accepted Item 8 checkpoint may contain exactly these eleven paths and no others:

1. `.github/workflows/ci-mainline.yml`
2. `.github/workflows/ci-pr-extended.yml`
3. `tests/README.md`
4. `tests/investment/test_platform_migrations.py`
5. `docs/reviews/implementation-20260822-slice-2.3-item8-ci-runbook-codex.md`
6. `docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-deepseek-v4-pro.md`
7. `docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-mimo.md`
8. `docs/reviews/code-review-fix-20260822-slice-2.3-item8-ci-runbook-codex.md`
9. `docs/reviews/code-rereview-20260822-slice-2.3-item8-ci-runbook-deepseek-v4-pro.md`
10. `docs/reviews/code-rereview-20260822-slice-2.3-item8-ci-runbook-mimo.md`
11. `docs/reviews/code-review-acceptance-20260822-slice-2.3-item8-ci-runbook-codex.md`

Before commit, the staged set must be exact-equal to this list, `git diff --cached --check` must pass, and the unstaged/untracked set must be empty. Use explicit path staging, never `git add -A` or directory staging.

## 8. Controller decision

The Item 8 final CI/runbook candidate is independently code-reviewed and validated with open H/M/L exactly `0/0/0`.

**Decision: `ACCEPTED_FOR_LOCAL_ITEM8_CHECKPOINT`.**
