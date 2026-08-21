# Plan Rereview: Slice 2.3 Item 7 Startup Registration — MiMo Round 2

- **日期**: 2026-08-22T06:45:19Z
- **Reviewer**: MiMo-V2.5 (Xiaomi) — independent fresh byte-0 rereview
- **Role**: independent plan rereview only; not Controller, not implementation writer, not first-round reviewer
- **Model**: `mimo-v2.5` (actual model: MiMo-V2.5 Xiaomi)
- **Status**: `FRESH REREVIEW / PASS / OPEN H/M/L=0/0/0`
- **Scope**: adversarial five-lens plan review of Item 7 corrective plan (master + fix artifact) from byte 0; no inheritance from prior round verdicts

## 0. Frozen START identity

| Artifact | SHA-256 | Lines | Bytes |
|---|---|---|---|
| Master plan `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `8564c49f2657af61fe08d56480fac1e4f327be29d353efb33c58691f06162584` | 3883 | 310791 |
| Fix artifact `docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md` | `8f3eb2008663ef4ed5deb9c9a97c48a89330ff74c612ee3dc56c240fb2dd9cf5` | 165 | 12822 |
| WIP `dayu/services/startup_preparation.py` | `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e` | 1689 | 63289 |
| WIP `tests/application/test_service_startup_preparation.py` | `a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2` | 4044 | 127443 |
| Branch | `codex/investment-platform` | | |
| HEAD | `d604d8df7613db0103076b3a727156fd74dd9e1b` | | |

All on-disk SHA/lines/bytes match frozen START. No drift detected.

## 1. Reviewed target and scope

- **Target**: Item 7 startup registration corrective plan — the combination of master plan (post-S24 writeback) and fix artifact (post-DSV4P-RR corrective writeback)
- **What changed since last review**: fix artifact §9 writeback expanded master §11 exact-six→exact-seven, §12 Item 7/8 boundary, §14.0 allowlist/README/artifact/staging, §15 STOP, and §17.2 review/stage ledger
- **Goal**: verify the corrective plan is code-generation-ready for an exact-seven writer with no drift, no scope creep, no structural risks

## 2. Assumptions tested

1. The exact-seven allowlist is consistently enforced across all active plan sections (§10.1, §11, §12, §14.0, §15, §17.2)
2. Root README is constrained to only `:385-387` distortion
3. Four-README audit is executable and aligns with AGENTS.md responsibilities
4. §17.2 review/checkpoint state is closed and consistent
5. Preserved WIP is not mixed into docs-only checkpoint
6. Negative AST regression set correctly guards frozen HEAD→WIP rename
7. 176 catalog count is correct and internally consistent
8. START=END identity holds with zero drift

## 3. Hostile review results

### Finding 1: exact-seven consistency across all active sections

**§11 (line 2729)**: "七个且仅七个path" — lists 7 paths ✓
**§10.1 (line 2582)**: "只写§11 exact-seven" ✓
**§12.7 (line 2866)**: "只写§11 exact-seven" ✓
**§12.8 (line 2872)**: "Item 7已闭合的exact-four startup/black-box文字、README.md、dayu/README.md与dayu/investment/README.md不属于Item 8" ✓
**§14.0 step 1 (line 3308)**: "changed implementation set exact-equal §11 Item 7 exact-seven" ✓
**§14.0 step 8 (line 3401)**: "exact-seven allowlist" ✓
**§14.0 (line 3406)**: "exact-seven manifest" ✓
**§15 (line 3630)**: "exact-seven之外出现实现/README diff" ✓
**§17.2 (line 3874)**: "Item 7 writer exact-seven" ✓

No inconsistency found. The exact-seven constraint is uniformly enforced.

### Finding 2: root README `:385-387` constraint

On-disk root README `:385-387`:
```
当前只交付 generic Scheduler/Worker 与 durable 队列基础设施：production execution registry
为空，不包含 source/research/Agent/Broker handler，不包含 production Compose，也不会自动调用
provider、模型、Broker 或执行真实交易。
```

§14.0 step 8 (line 3395): "root README.md只修改原`:385-387`一个失真段落"
§11 (line 2737-2739): root README "只允许把当前`:385-387`一个失真段落改为...该段以外root README字节zero diff"

The plan correctly constrains root README to this single 3-line segment. The rest of the 2406-line root README must remain zero-diff. §14.0 step 8 has an executable UTF-8 mechanical audit for this.

### Finding 3: four-README audit executability vs AGENTS.md

§14.0 step 8 (line 3394-3402) defines the four-README audit:
1. Root README `:385-387` → no longer claims empty registry; exact-one Source Sync handler; zero-diff elsewhere
2. `tests/README.md` → black-box is exact-four with `investment_sources`
3. `dayu/README.md` → no longer claims empty registry
4. `dayu/investment/README.md` → no longer claims empty registry; exact-one Source Sync handler

Current on-disk truth:
- `tests/README.md:53` says "精确为 `investment_identity` / `durable_jobs` / `durable_schedules` 三个 Service" (exact-three) → needs exact-four
- `dayu/README.md:155-156` says "execution registry 为空" → needs exact-one
- `dayu/investment/README.md:268-269` says "production descriptor/execution registry 当前为空" → needs exact-one

The audit is executable via UTF-8 read + string assertions. It aligns with AGENTS.md §68-74 (README sync: update only inconsistent parts, don't write "future design", check for stale terms).

### Finding 4: §17.2 checkpoint state closure

§17.2 (lines 3855-3883) records:
- Historical DeepSeek V4 Pro review: FAIL 0/0/1 (one Low accepted) ✓
- Current DeepSeek V4 Pro rereview: FAIL 0/1/1 (RR-01 Medium + RR-02 Low, both accepted) ✓
- Current MiMo review: PASS 0/0/0 (PR-01/PR-02 both rejected by Controller with reasons) ✓
- Checkpoint artifact families: master + plan-fix + plan-review-* + plan-rereview-* + plan-acceptance-* ✓
- "两个preserved WIP不得混入docs-only checkpoint" ✓

Fix artifact §5 (lines 91-107) confirms the same gate sequence. §17.2 state is closed and internally consistent.

### Finding 5: negative AST regression set

§14.0 step 3 (line 3323-3331) defines the AST check:
- Assert 5 Item 7 names each exactly once
- Assert 4 old names each zero: `test_production_provider_wires_exact_three_service_mapping`, `test_production_explicit_provider_keeps_custom_composition_after_redis_admission`, `test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry`, `test_source_handler_registration_remains_absent_until_slice_2_3`

These 4 old names exist in the WIP test file's git history but were renamed in the WIP. The AST check correctly guards against regression to the old names. §13.1 (lines 3014-3023) specifies the same set.

### Finding 6: 176 catalog count

§13 (line 2953-2955): "Item 7 corrective再把现有WIP遗漏的十九阶段failure matrix与既有PG black-box exact-three->exact-four rename各纳入一个唯一mandatory name，故当前总数精确为176"

Verification:
- Item 6 historical aggregate: 174
- Item 7 adds: `test_production_provider_failure_disposes_one_engine_once` (19-stage parameterized → 1 name) + `test_production_provider_wires_exact_four_service_mapping` (renamed from exact-three → 1 name) = +2
- Net: 174 + 2 = 176 ✓
- All 5 Item 7 startup names in §13.1 are present in the 176-catalog ✓

### Finding 7: §10.1 six-step, 19-stage, PG plain gate, singleton coverage, exact-seven writer

- §10.1 six-step (line 2577-2619): clear code-generation handoff with STOP on drift ✓
- 19-stage failure matrix: parameterized in `test_production_provider_failure_disposes_one_engine_once`, counted as 1 name after `[...]` suffix removal ✓
- PG plain gate (§14.0 step 6, line 3384): "postgres_identity.py本Item unchanged，因此该lane是plain Gate 2" ✓
- Singleton coverage (§14.0 step 5, line 3353-3372): exact-singleton branch coverage for `startup_preparation.py` ≥80% ✓
- exact-seven writer (§10.1, line 2579-2584): byte-by-byte preflight, STOP on drift, minimal WIP increment ✓

### Finding 8: architecture boundary, best practice, optimal, overengineering, overcoupling

- Architecture boundary: Item 7 only materializes accepted startup contract, does not redesign composition. Non-goals explicitly exclude domain/repository/migration/workflow changes ✓
- Best practice: single composition owner registers descriptor/handler/seals/asserts/publishes. Failure at any stage triggers reverse-order close with engine dispose-once ✓
- Optimal: minimal rename+expand (exact-three→exact-four) rather than redesign ✓
- Overengineering: no new abstractions, layers, builders, or protocols introduced ✓
- Overcoupling: README updates are coupled to implementation because they document the same facts. Appropriate coupling ✓

### Finding 9: failure/recovery, open questions, manifest/executability

- Failure recovery (§14.0): every step has explicit "任一非零立即STOP" ✓
- Open questions: fix artifact §7: "HANDOFF-READY CANDIDATE / OPEN PLAN QUESTIONS 0" ✓
- Manifest: exact-seven allowlist ✓, 176 catalog ✓, 44 mapping keys ✓, exact-five names ✓
- Command executability: all §14.0 steps have concrete bash commands with expected exit codes ✓

### Finding 10: START=END identity

| Check | START (file header Gate) | On-disk (verified) | Match |
|---|---|---|---|
| Master SHA | `8564c49f...` | `8564c49f...` | ✓ |
| Master lines | 3883 | 3883 | ✓ |
| Master bytes | 310791 | 310791 | ✓ |
| Fix SHA | `8f3eb200...` | `8f3eb200...` | ✓ |
| Fix lines | 165 | 165 | ✓ |
| Fix bytes | 12822 | 12822 | ✓ |
| WIP1 SHA | `73309ab...` | `73309ab...` | ✓ |
| WIP2 SHA | `a0010b1...` | `a0010b1...` | ✓ |

Zero drift. The plan-review of the plan (meta-level) does not modify any file; START=END is trivially satisfied by this rereview session.

## 4. Open questions

None. The plan has no blocking questions and zero open risks for the rereview gate.

## 5. Residual risks

- The `git fsck` old worktree/missing-object issue is an independent repo-health residual (§16 item 11). It does not block the plan gate. If it blocks implementation freeze, it triggers STOP and a separate work item. This is correctly handled.
- The docstring Low (`Args/Returns/Raises` for one test) is deferred to implementation phase, not plan gate. Correct.

## 6. Verdict

**PASS / OPEN H/M/L=0/0/0**

The corrective plan (master + fix artifact) is internally consistent across all five review lenses:
1. **exact-seven consistency**: uniformly enforced in §10.1, §11, §12, §14.0, §15, §17.2
2. **§17.2 checkpoint state**: closed, all review rounds and findings accounted for, artifact families correctly scoped
3. **Negative AST regression**: correctly guards frozen HEAD→WIP rename with 4 old names zero-assertion
4. **Architecture/overengineering**: minimal, focused, no new abstractions
5. **START=END identity**: zero drift across all four artifacts

No material findings. The plan is ready for fresh same-SHA dual plan rereview completion (Controller acceptance gate).

---

## Appendix: END identity (post-rereview)

| Artifact | SHA-256 (post-rereview) | Lines | Bytes |
|---|---|---|---|
| Master plan | `8564c49f2657af61fe08d56480fac1e4f327be29d353efb33c58691f06162584` | 3883 | 310791 |
| Fix artifact | `8f3eb2008663ef4ed5deb9c9a97c48a89330ff74c612ee3dc56c240fb2dd9cf5` | 165 | 12822 |

START=END confirmed. This rereview session performed zero file writes to plan/code/test/review files.
