# Slice 2.3 Item 3 Fins source-sync implementation record

- **Gate / slice**: Slice 2.3, implementation Item 3
- **Status**: `IMPLEMENTATION FROZEN / READY FOR INDEPENDENT CODE REVIEW`
- **Accepted plan**: `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Accepted corrective plan commit**: `3f0de579e1c95b428b61e046bae2a0583a4e76d6`
- **Implementation baseline / current HEAD**: `e3167d71e1ecad90fdb9294f9058d94ccc146551`
- **Branch**: `codex/investment-platform`
- **Implementation owner**: Codex

## 1. Scope and non-goals

This item implements only the accepted Fins worker contracts, Fins runtime/source connector,
download-stream ownership correction, SEC rejected-artifact persistence correction, and their
owner tests. It does not implement Source PostgreSQL storage, migrations, Source execution
services, composition/startup registration, public Investment service APIs, provider exactly-once
delivery, or later health/outbox behavior.

The following concurrent Item 2 paths remained outside this writer's read/write scope:

- `dayu/services/job_service.py`
- `dayu/investment/domain/jobs.py`
- `tests/application/test_job_service.py`
- `tests/integration/investment/test_postgres_jobs.py`

Storage, migration, startup, other service owners, `dayu/fins/pipelines/download_events.py`,
`dayu/fins/pipelines/sec_download_event_mapping.py`, `dayu/fins/cli_support.py`, and
`dayu/fins/ingestion/job_manager.py` also remain zero-diff. No network, provider, push, PR,
stage, or commit action was performed.

## 2. Changed paths

Production paths (exactly 19):

- `dayu/fins/domain/__init__.py`
- `dayu/fins/domain/source_sync.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/ingestion/pipeline_backends.py`
- `dayu/fins/ingestion/service.py`
- `dayu/fins/pipelines/base.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/source_sync_runtime.py`
- `dayu/investment/connectors/__init__.py`
- `dayu/investment/connectors/source.py`
- `dayu/services/fins_service.py`
- `dayu/services/protocols.py`

Writable test paths (exactly 20):

- `tests/application/test_fins_service.py`
- `tests/fins/test_cli_helpers_coverage.py`
- `tests/fins/test_cn_download_filing_workflow.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_runtime_source_sync.py`
- `tests/fins/test_fins_source_sync_runtime.py`
- `tests/fins/test_ingestion_factory.py`
- `tests/fins/test_ingestion_job_manager.py`
- `tests/fins/test_ingestion_service.py`
- `tests/fins/test_per_filing_terminal_state.py`
- `tests/fins/test_pipeline_backends.py`
- `tests/fins/test_pipeline_cli.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_rejection_registry.py`
- `tests/integration/investment/test_fins_s3_blob_repository_minio.py`
- `tests/investment/test_architecture_boundaries.py`
- `tests/investment/test_source_connectors.py`
- `tests/investment/test_source_evidence_domain.py`

This file is the sole implementation artifact added for the gate. All 18 accepted
coverage-only test inputs were executed without modification.

## 3. Implemented contracts

1. Added frozen, slotted `FinsWorkerSyncRequest`, `FinsWorkerSourceDocument`,
   `FinsWorkerSyncResult`, and the closed `FinsWorkerSyncOutcome` enum. Constructors enforce
   canonical ticker identity through the existing `normalize_ticker` truth source, exact MIC,
   form/date/cap bounds, locator hash/readback shape, deterministic document ordering, counts,
   latest-date identity, and outcome matrices.
2. Added `DefaultFinsWorkerSourceSyncRuntime` with only the accepted pipeline factory, source
   repository, and locator-owner dependencies. It implements pre-stream market/form rejection,
   the exact existing pipeline call, bounded DownloadEvent ingress, SEC/CN/HK correlation,
   nested/flat terminal identity, candidate-not-found, clean terminal result correlation,
   strict metadata/primary-byte locator construction and readback, and the accepted outcome
   priority. Raw legacy file payloads are not recursively interpreted.
3. Added eager ownership and exact one-call delegation through `DefaultFinsRuntime`,
   `FinsRuntimeProtocol`, `FinsServiceProtocol`, and `FinsService`; the Service alone adapts the
   typed cancellation signal to the required keyword-only checker.
4. Added `FinsSourceConnector` and immutable `SourceConnectorRegistry`. The connector derives
   the exact worker request, converts verified pathless locator projections through the
   Investment parser, and maps every closed Fins outcome to the sole Source terminal candidate
   or typed cancelled decision.
5. Replaced the download-only chain's 18 direct-owner return contracts with
   `collections.abc.AsyncGenerator[..., None]`. Every wrapper binds its direct inner generator
   and closes it exactly once in `finally` across success, error, domain cancellation,
   `asyncio.CancelledError`, and outer `aclose` paths.
6. Replaced SEC normal-flow compatibility fallback with the typed stream path. Rejected-artifact
   persistence now uses its private exact downloader protocol, direct mapping helpers, the
   accepted keyword-only surface, and no longer accepts the five legacy helper dependencies.
7. Added the real pinned-MinIO FS/S3 byte-identical, pathless locator projection assertion and
   exact owner/architecture/state-machine tests required by Item 3.

Final adversarial review found and closed three narrow P2 defects before freeze: external
cancellation is now checked before an event one-over invariant, and request ticker validation now
uses `normalize_ticker` rather than a wider local regular expression. A final boundary pass also
made aggregate DTO validation recursively revalidate each exact document and made the connector
map any forged/non-closed worker result to `fins_invariant` before interpreting cancellation. The
independent final reread reported no remaining finding in the rest of the implementation.

## 4. Validation evidence

Toolchain: Python `3.11.15`, Pyright `1.1.408`, Ruff `0.15.11` from the existing project venv.

| Gate | Result |
| --- | --- |
| Item 3 named-test audit | `PASS`, 42/42 names present |
| All 19 writable non-integration test files | `PASS`, 539 passed |
| Focused final source-sync runtime tests | `PASS`, 56 passed |
| Exact pinned-MinIO locator test | `PASS`, 1 passed; existing local image digest used, no pull/network |
| Exact Pyright over all 19 production + 20 test paths | `PASS`, 0 errors / 0 warnings / 0 informations |
| Ruff default / `F` / `I` over all changed Python paths | `PASS` / `PASS` / `PASS` |
| Ruff configured JSON finding set | `PASS`, zero findings / empty code set |
| Architecture owner/forbidden checks | `PASS` within the 538-test run |
| `git diff --check` | `PASS` |
| Scope audit | `PASS`, exactly 19 production + 20 writable test paths |
| Forbidden-path audit | `PASS`, zero diff |
| Coverage-only catalog audit | `PASS`, all 18 files zero diff |

Fresh, branch-enabled exact-singleton coverage results (combined statement + branch percentage):

| Production owner | Percent |
| --- | ---: |
| `dayu/fins/domain/source_sync.py` | 97.07317073170732 |
| `dayu/fins/source_sync_runtime.py` | 85.14190317195326 |
| `dayu/investment/connectors/source.py` | 89.24731182795699 |
| `dayu/investment/connectors/__init__.py` | 100.0 |
| `dayu/services/fins_service.py` | 90.54054054054055 |
| `dayu/fins/ingestion/pipeline_backends.py` | 84.0 |
| `dayu/fins/ingestion/service.py` | 89.65517241379311 |
| `dayu/fins/domain/__init__.py` | 100.0 |
| `dayu/fins/downloaders/sec_downloader.py` | 89.93089832181639 |
| `dayu/fins/pipelines/base.py` | 100.0 |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 83.1304347826087 |
| `dayu/fins/pipelines/cn_download_workflow.py` | 85.81560283687944 |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 85.1063829787234 |
| `dayu/fins/pipelines/sec_download_persistence.py` | 97.67441860465117 |
| `dayu/fins/pipelines/sec_download_workflow.py` | 94.44444444444444 |
| `dayu/fins/pipelines/cn_pipeline.py` | 92.9384965831435 |
| `dayu/fins/pipelines/sec_pipeline.py` | 87.95454545454545 |
| `dayu/fins/service_runtime.py` | 86.66044776119404 |

`dayu/services/protocols.py` is the single explicit coverage defer authorized by the Controller:
its normative tuple depends on Item 6/8 owner tests that do not exist yet. This item did not add a
placeholder, delete the tuple, or substitute an import-only test. Final exact Gate 1 for that owner
therefore remains with Item 6/8.

## 5. Documentation decision and residuals

No public README, API guide, deployment guide, or migration documentation changed because this
item exposes an internal worker/runtime/connector boundary and does not enable a public endpoint or
operational deployment behavior. This implementation record is the only documentation addition.

The accepted plan's requested `§3.2.4` heading does not exist in the tracked document; the
Controller explicitly ruled that `§3.2.2`, `§3.3`, and `§4` are the normative sources. The
coverage matrix also referenced a planned-new CN filing workflow owner test absent from the
baseline; this item created it in the accepted writable test path.

Ruff validation used the existing offline `0.15.11` binary as directed. No newer tool was fetched;
the later-toolchain full-rule positive-delta gate is not claimed here and remains an environment
residual for the Controller/final Item 8 gate. The local default, `F`, `I`, and configured-rule
results are all clean.

An informational `ruff format --check` (not an accepted Item 3 gate) reports 24 mixed legacy/new
paths would be reformatted by Ruff 0.15.11. This item did not introduce a bulk formatting-only diff;
the accepted Ruff lint gates are clean.

The real MinIO test used the locally present pinned multi-arch image
`minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.
It did not pull an image or access the public network.

There is no open implementation STOP for Item 3. Provider reads remain not exactly once by
accepted design; durable operation replay, PostgreSQL concurrency, health/outbox, startup
registration, final service-protocol coverage, full extended gates, and independent acceptance
review belong to later items. The worktree is intentionally unstaged and uncommitted pending
review.
