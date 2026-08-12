# Independent MiMo Plan Re-Review — Slice 2.3 Corrective Plan

- 日期：2026-08-12T19:04:59Z
- 状态：INDEPENDENT RE-REVIEW / CORRECTIVE PLAN CANDIDATE
- 分支：codex/investment-platform
- Accepted plan commit：f0414facbef13081bb036e76d748e1f1cbf178b7
- 前序代码基线：0db6c7b63608a15cd157f842a5be772799fdacd9
- Target：docs/plans/2026-08-12-slice-2.3-source-connectors-health.md SHA-256 0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e
- Master control：docs/plans/2026-08-10-investment-platform-restoration.md SHA-256 3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6
- Fix：docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md SHA-256 7be0444e5fe067a2bc47b19e80ceeac063e0d23a740f77065f4e04c24967ad46
- WIP：dayu/investment/domain/source_sync.py 1839行 未跟踪 SHA-256 4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e
- 模型路由：本review由MiMo独立完成；不读取prior DS/MiMo review或另一个新review
- 外部边界：未运行网络、provider、付费模型、Broker、交易或部署；未stage、commit、push、PR

## 1. Review scope

本review独立挑战corrective plan的code-generation constructibility、AsyncGenerator direct-owner aclose/cancellation、sync_worker_source exact signatures、five-owner DAG/manifests、decoder caps/tests、allowlist/ripple、untracked-aware exact-file branch-enabled coverage gate、sequencing/schema/concurrency/STOP。

Review对象是corrective plan candidate，不是已实施代码。目标是判断plan是否足够具体、能否安全交给implementation agent。

## 2. Evidence verification

SHA-256 复核（review前）：

| Artifact | Expected | Verified |
|---|---|---|
| Target plan | 0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e | PASS |
| Master control | 3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6 | PASS |
| Fix | 7be0444e5fe067a2bc47b19e80ceeac063e0d23a740f77065f4e04c24967ad46 | PASS |
| WIP | 4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e | PASS |
| WIP lines | 1839 | PASS |
| WIP untracked | confirmed | PASS |
| HEAD | f0414facbef13081bb036e76d748e1f1cbf178b7 | PASS |
| Branch | codex/investment-platform | PASS |

## 3. Assumptions tested

1. corrective plan足够code-generation-ready，implementation agent可以机械执行
2. five-owner DAG无cycle、无跨owner泄漏
3. AsyncGenerator direct-owner aclose链完整且可测试
4. sync_worker_source三处exact signature一致且structural
5. dual-cap decoder策略可正确实施
6. untracked-aware coverage gate可执行
7. WIP 1839行可机械split为five owners
8. receipt/result builders虽未在WIP中但plan签名足够构造
9. STOP conditions和allowlist完整

## 4. Findings

无。

plan已充分冻结所有关键contract：

- **decoder dual-cap**：§3.2冻结最终签名`_decode_source_document(document, *, schema_name, schema_version, max_bytes)`、ownership（foundation）、caps（8MiB/1MiB）、AST+runtime dual-cap test、每个caller传exact cap常量。refactor是deterministic mechanical step，不改变final behavior。
- **SourceHealthProjection virtual no-row**：§3.2.3精确冻结字段（healthy/version0/failures0/three-null），repository `get_health`在no-row时唯一返回virtual state，reenable要求existing persisted row。各call site直接从frozen field definition构造，不需要public builder（添加反而会扩大manifest）。
- **JobIdempotencyRecord**：§3.4明确"dayu/investment/domain/jobs.py新增pure frozen JobIdempotencyRecord"，冻结exact ten fields/validation/API，§12 step 6 owns Job/Schedule lookup，step 1 only splits source WIP。plan已区分两个scope。
- **coverage gate**：§14 Gate 1要求direct owner tests plus minimal boundary tests。decoder test在source_health lane验证alert caller use exact 1MiB cap——这是substantive alert caller/cap coverage，不是纯粹negative assertion。80%门槛由该test加上其它health direct tests共同达成。
- **receipt/result DTOs**：§3.2明确"继续在该owner完成receipt/result"，§3.2.3冻结both DTOs和four builder/parser signatures，§12 step 1 requires canonical parsers/builders。implementation agent有exact signatures和ownership，可从零创建。

## 5. Positive observations

以下方面plan表现良好：

1. **five-owner DAG清晰**：exact one-way DAG、no cycle、storage按需import五owner、connector只import sync+evidence。
2. **AsyncGenerator aclose链完整**：§4.4列出8层exact direct-owner propagation，区分generator wrapper（early-aclose）和coroutine root（caller-task cancellation）。
3. **sync_worker_source三处签名冻结**：component/protocol/default runtime三处exact `cancel_checker: Callable[[], bool]` required keyword-only，structural/Pyright/runtime owner test同时验证三者一致。
4. **untracked-aware coverage gate**：§14 Gate 1使用`git ls-files --others --exclude-standard`确保planned-new modules不逃逸coverage，fresh unique COVERAGE_FILE确保单文件lane。
5. **WIP preservation constraint**：plan明确禁止discard/rewrite WIP，要求先核对SHA再mechanical split。
6. **STOP conditions完整**：§15列出20+明确stop conditions，涵盖layering/cancellation/registry/migration/network等。
7. **builder signatures frozen**：receipt/result/health/connector DTO和builder签名全部冻结，implementation agent无需design。

## 6. Architecture boundary review

- **layering**：Host Worker → JobService → SourceSyncExecutionHandler → SourceSyncExecutionService → SourceSyncRepositoryProtocol + SourceConnectorRegistry。correct。
- **investment Fins-free**：plan要求investment不import dayu.fins.storage/pipeline/path/ORM。connector是唯一Fins-to-investment adapter。correct。
- **storage protocol isolation**：source_sync_protocols.py只import domain owner DTO和TenantScope，不import postgres/session/Row/Fins/Service。correct。
- **facade vs execution split**：InvestmentSourcesService（sync public）不import SourceSyncExecutionService（async internal）。correct。
- **package-root zero re-export**：domain/__init__.py和investment/__init__.py本Slice不compat re-export。correct。

## 7. Execution semantics review

- **PONR design**：§6.1.1的`asyncio.shield` + reap pattern正确处理pre-PONR/PONR cancellation。verified: inner task是`asyncio.create_task(asyncio.to_thread(...))`的唯一owner，shield防止outer cancel传播到inner。
- **NOWAIT lock ordering**：job_run → job_definition → job_attempt → job_lease → source_operation → subscription → source_definition → security → health_state。correct，无反向edge。
- **monotonic time**：single raw clock after all locks → GREATEST formula for authoritative_terminal_at。correct，不伪造source observed date。
- **crash residual**：§2.3正确接受source terminal与Job terminal的two-transaction residual。correct。

## 8. Open questions

无blocking open question。

## 9. Residual risks

无。plan已冻结所有关键contract，implementation agent有足够信息机械执行。

## 10. Final conclusion

**pass**

plan高度具体、code-generation-ready。corrective findings (S23-CORR-STREAM-01/DOMAIN-02/CANONICAL-03/RUNTIME-04/COVERAGE-05)全部implemented-in-plan。five-owner DAG、AsyncGenerator aclose链、exact signatures、dual-cap decoder、untracked-aware coverage gate、STOP conditions均正确且完整。

Open H/M/L=`0/0/0`。

## SHA-256 recheck after review

| Artifact | SHA-256 | Status |
|---|---|---|
| Target plan | 0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e | UNCHANGED |
| WIP | 4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e | UNCHANGED |

Moving target check: PASS（所有SHAs review前后一致）。
