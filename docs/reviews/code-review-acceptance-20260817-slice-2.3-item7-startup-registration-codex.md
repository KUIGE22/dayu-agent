# Slice 2.3 Item 7 startup registration code-review Controller acceptance

- **Role**: Codex Controller；不是 implementation/fix writer，也不是 DeepSeek/MiMo reviewer
- **Gate**: Item 7 post-fix code-review adjudication and local accepted-checkpoint authorization
- **Date / timezone**: 2026-08-22 / Asia/Shanghai
- **Branch / accepted base**: `codex/investment-platform` / `ee75d17955a4a8f30a56a02cae56fac34df79be5`
- **Accepted candidate diff SHA-256**: `cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9`
- **Verdict**: `ACCEPTED / open H/M/L = 0/0/0`
- **Boundary**: only a local accepted Item 7 checkpoint is authorized；no push、PR、Item 8、D0 completion claim or investment P0/F0 advance

## 1. Frozen lineage

Accepted planning lineage remained byte-identical throughout implementation and review:

| artifact | SHA-256 / lines / bytes |
|---|---|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194 / 3917 / 314076` |
| `docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md` | `a57ec452e71f7f8136b96f7da855546a3ff29cbd0f43d3101f83f62658e5640d / 236 / 19145` |
| `docs/reviews/plan-acceptance-20260822-slice-2.3-item7-startup-registration-codex.md` | `67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9 / 136 / 9986` |
| implementation | `4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f / 219 / 14375` |
| DeepSeek first review | `0abf4379e6d1a53c8c8dfb50ceacf256ea503046ff96d28c8f5cf1fe503e8c94 / 156 / 22450` |
| MiMo first review | `561d594b76313ff2bfe6ae01b791bfbc415c008f19a5ec4207bd63dc9683ce64 / 156 / 12708` |
| code-review fix | `8b3599bb3c5e5f865132ad6a64f82d0f065d956b2a4a74c0c58736780677be15 / 162 / 8827` |
| DeepSeek rereview | `9891e8255ba5dc7be0625e88b2b0aa7970af5c72a46fe09e905c27954d708fab / 140 / 22556` |
| MiMo rereview | `4242a260e91599f9932edd4c08508412eeb6500e38610df42b05b6f3a03ab567 / 186 / 11948` |

The acceptance artifact deliberately does not embed its own SHA-256 in its preimage. The Controller reports that identity after the file is closed.

## 2. First-review adjudication

### 2.1 DeepSeek V4 Pro first review

Actual route `deepseek-v4-pro[1m]` returned `FAIL / open H/M/L = 0/0/1` on the pre-fix candidate `2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9`.

| item | Controller disposition | closure |
|---|---|---|
| F-01 Low: PG black-box module docstring still said three real Services while the same file asserted exact-four | **accepted** | Writer changed only that module docstring to four Services and added `investment_sources` / `InvestmentSourcesService`; PG file became `1cefaee3...`, affected validation passed, and both same-route rereviews independently marked it CLOSED. |
| OQ-01: preserved WIP formatting bytes vs non-goal | **non-finding / retain** | These bytes were frozen as accepted preserve-and-adopt input and were not changed by the Item 7 writer. Rereview found no semantic defect. |
| OQ-02: five pre-existing phase-2 constructors not injected into the 19-stage matrix | **non-finding / no scope expansion** | The 19 stages cover every Item 7 incremental seam and exercise the shared exception/close path; existing constructors remain under that same owner boundary. |
| OQ-03: application-test module introduction still mentions Slice 0.2 | **non-finding / retain** | The statement remains true and non-exclusive; it is not a competing current mapping truth. |

The DeepSeek boundary observation that `dayu/README.md` elsewhere says 15 ORM tables while an existing owner test expects 18 is not in the Item 7 candidate hunk or authorized README replacement. It is recorded for a separate docs-only work unit and does not alter this gate.

### 2.2 MiMo first review

Actual route `xiaomi/mimo-v2.5` returned `PASS / open H/M/L = 0/0/0` for the pre-fix candidate and had no finding. This did not override DeepSeek F-01; the accepted Low was fixed before the final gate.

## 3. Post-fix validation evidence

The fix writer froze post-fix candidate `cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9` and reported:

- focused Item 7 suite: `64 passed`;
- AST/name truth: five current Item 7 names exact-one, four historical names zero, application and PG module docstring contracts PASS;
- Pyright: `0 errors / 0 warnings / 0 informations`;
- Ruff default, `F`, and `I`: PASS;
- pinned PostgreSQL 16 isolated lane: `17 passed`, with owner-labelled container/network/role/database cleanup all zero;
- exact-seven allowlist, four-README contract, UTF-8/LF/final-newline, `git diff --check`, index and artifact mechanics: PASS.

The implementation evidence preceding the docstring-only fix also remains applicable: architecture `171/171`, fresh singleton branch coverage `80.48%`, and the deterministic non-integration/e2e lane `8858 passed / 5 existing skipped / 322 deselected`.

## 4. Same-reviewer post-fix gate

Both reviewers used their original model routes, received the same post-fix candidate SHA and exact-seven identities, were forbidden to read the other route's output, and independently reread the accepted contract, their own lineage, the full candidate, and the relevant real call chain.

| route | artifact | final verdict |
|---|---|---|
| `deepseek-v4-pro[1m]` | `docs/reviews/code-rereview-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md` | `PASS / open H/M/L = 0/0/0`; F-01 CLOSED; no fresh finding |
| `xiaomi/mimo-v2.5` | `docs/reviews/code-rereview-20260817-slice-2.3-item7-startup-registration-mimo.md` | `PASS / open H/M/L = 0/0/0`; F-01 CLOSED; no fresh finding |

Therefore the Gateflow requirement “dual final PASS with open H/M/L exactly `0/0/0` on the same post-fix SHA” is satisfied.

## 5. Accepted exact-seven identities

| path | SHA-256 / lines / bytes |
|---|---|
| `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e / 1689 / 63289` |
| `tests/application/test_service_startup_preparation.py` | `2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545 / 4123 / 130135` |
| `tests/integration/investment/test_identity_repositories_postgres.py` | `1cefaee33dd0a2e93b236e36171efc2aced09dba4863872982eabe54b64c492e / 2124 / 73611` |
| `README.md` | `d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94 / 2407 / 153621` |
| `tests/README.md` | `1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f / 612 / 132898` |
| `dayu/README.md` | `8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5 / 1297 / 65205` |
| `dayu/investment/README.md` | `1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331 / 333 / 22921` |

## 6. Exact local-checkpoint staging authorization

The local accepted checkpoint may contain exactly these fourteen paths and no others:

1. `README.md`
2. `dayu/README.md`
3. `dayu/investment/README.md`
4. `dayu/services/startup_preparation.py`
5. `tests/README.md`
6. `tests/application/test_service_startup_preparation.py`
7. `tests/integration/investment/test_identity_repositories_postgres.py`
8. `docs/reviews/implementation-20260817-slice-2.3-item7-startup-registration-codex.md`
9. `docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md`
10. `docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-mimo.md`
11. `docs/reviews/code-review-fix-20260817-slice-2.3-item7-startup-registration-codex.md`
12. `docs/reviews/code-rereview-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md`
13. `docs/reviews/code-rereview-20260817-slice-2.3-item7-startup-registration-mimo.md`
14. `docs/reviews/code-review-acceptance-20260817-slice-2.3-item7-startup-registration-codex.md`

Before commit, the staged set must be exact-equal to this list, `git diff --cached --check` must pass, and the unstaged/untracked set must be empty. The checkpoint is local only. It does not authorize Item 8, push, PR, D0 acceptance, or any investment implementation.

## 7. Controller decision

The accepted Item 7 candidate is code-reviewed and validated with open H/M/L exactly `0/0/0`.

**Decision: `ACCEPTED_FOR_LOCAL_ITEM7_CHECKPOINT`.**
