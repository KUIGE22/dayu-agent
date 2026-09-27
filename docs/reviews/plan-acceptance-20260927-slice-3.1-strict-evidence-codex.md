# Slice 3.1 Strict evidence — accepted plan checkpoint

## Controller decision

- Recorded: `2026-09-27T19:39:49+08:00`.
- Work unit: `Slice 3.1 Strict evidence domain 与 repositories`.
- Gate: accepted plan; next entry is **S31-Auth implementation**.
- Repository/branch/precommit HEAD: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform` / `bd9210ad8366af74916e1980ef282217627213dd`; precommit tree `812075962bf26d2fda1a321db6e1bea4fad57292`; prewrite porcelain empty.
- Decision: **ACCEPTED FOR IMPLEMENTATION, fresh open H/M/L = 0/0/0**. This is a local plan checkpoint, not PG evidence, accepted code, S5/Gate acceptance, final Fins readiness or completed shadow decision pipeline.

## Accepted source and review lineage

- Exact plan: `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` = SHA256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2` / 47,288 bytes / 134 LF; byte-identical copy of frozen V9 diagnostics source. Its candidate heading remains the historical review target; this separate decision accepts that exact byte stream.
- V8 A/B: `docs/reviews/plan-review-20260927-192729.md` = `299e782ee061dd6335bfae190fe0e60d483d161a96b7ae737b3434a8ebe2cdb4` and `docs/reviews/plan-review-20260927-192638.md` = `382b5d0f4c7017fd3058a68526ed2adefdcd8f8991630ab341b4b83ac144c394`; both FAIL, each fresh H/M/L 0/1/0, same physical EvidenceLink target/FK nullability defect.
- V9 independent A/B: `docs/reviews/plan-review-20260927-193813.md` = `7a33c0d8854206cff377906ba4174d7c22ceb2fb44d241224b208925f98b59b3`; `docs/reviews/plan-review-20260927-193251.md` = `9a1c535494e0074fd9608d46de06d0db841e91751848c1be320b8878252f1865`. Each independently reviewed the same V9 SHA, PASS with fresh H/M/L 0/0/0; A declared no access to concurrent B. The V8 finding is **已修复于计划 V9** by Fact NOT NULL/equal-ticker CHECK, exact two-arm EvidenceLink CHECK, nonnull direct FK tuple, raw PG negatives and double-MIC positive.

## Exact implementation entry

Proceed in plan §6 order: S31-Auth, S31-A, S31-B. Each needs implementation artifact, affected unit/PG16/pyright verification, independent code review, fix/re-review and accepted slice commit before the next slice. S31-Auth first uses only existing 0006 auth schema and the plan §2 allowlist. Before each write, recheck branch/HEAD/tree/status and accepted plan identity; any drift needs Controller reconciliation. Keep reviewer authority token-derived; do not treat `Principal` or `TenantScope` as a credential.

## Classified residual risks

- **Fixed in current Slice 3.1 work unit**: PG16 raw CHECK/FK/MATCH SIMPLE/trigger/index/NUMERIC/RLS/ACL/migration and concurrency/retry behavior, to be demonstrated in S31-Auth/A/B. S31-B code review must verify retry compares caller new version/link IDs with committed projection and preserves frozen V7 expiry/locator cases.
- **Covered by later approved Slice 3.2**: Fins owner/readback/freshness and final forecast/decision readiness. 3.1 emits only `locally_ready_requires_fins_validation`.
- **Assigned to later work unit**: unattended physical expiry sweep, later shadow TradeProposal/simulation/ledger/risk/cost/human-decision slices, and V7/U2 ten shape full recursive value/bad-child/legal-history/S5 closure. These tracks remain separate and OPEN.
- No plan-stage PG, migration, test, push, PR, broker, paper or live trade was executed. No blocking open question remains for starting S31-Auth.
