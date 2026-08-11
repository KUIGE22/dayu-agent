# Code Review — Slice 2.1 Durable Job Queue

## Scope

- **Mode**: current changes
- **Branch**: `codex/investment-platform`
- **Base**: `a457a7e`（HEAD）
- **Output file**: `docs/reviews/code-review-20260811-slice-2.1-durable-job-queue-mim.md`
- **Included scope**: 22 WIP paths（13 production + 9 test）+ 3 README，全部在 plan §2 allowlist 内
- **Excluded scope**: `dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/contracts/protocols.py`、架构守护；未触碰 Slice 2.2/2.3 owner
- **Parallel review coverage**: 6 个 explore subagent 分别深挖 postgres_jobs.py（事务/RLS/lock/clock/correlation）、domain/jobs.py（DTO/enum/builder/error）、job_service.py（orchestration/mapping/recover）、0003 migration（DDL/RLS/grant/trigger/downgrade）、startup_preparation.py（composition/lifecycle）、test files（覆盖/gaps/concurrency）

## Conclusion

**PASS / open H/M/L = 0/1/2**

实现整体正确，架构边界清晰。核心状态机（lease/fence/token 验证、claim heartbeat complete fail cancel recover correlation authorize reconcile 全链路）与 plan §4 一致；PG 时钟权威、RLS + tenant predicate 双保险、event sequence 原子递增、versioned lease CAS 设计扎实。测试覆盖全面，包含 3 个真实并发 `threading.Barrier` 竞态测试和 crash window 测试。以下 3 项 finding 不阻塞 merge，但应在后续 slice 修复。

---

## Findings

### M-001-未修复-中-parse_generic_attempt_receipt 依赖 assert 做类型守卫

- **入口/函数**: `dayu/investment/domain/jobs.py:parse_generic_attempt_receipt`
- **文件(行号)**: `dayu/investment/domain/jobs.py:768-793`
- **输入场景**: 从 DB 读取 receipt bytes 后调用 `parse_generic_attempt_receipt` 解析
- **实际分支**: 函数体内 7 处 `assert isinstance(...)` / `assert type(...) is ...`（L768, L770, L773, L775, L778, L780, L793），而非显式 `if not isinstance(...): raise JobInputError(...)`
- **预期行为**: 按文件其余 `_require_*` 系列函数的模式，以 `if` 检查 + `raise JobInputError` 做类型守卫
- **实际行为**: `python -O` 模式下 `assert` 被移除，类型安全依赖消失；后续代码可能在无类型保障下运行，触发 `ValueError`/`TypeError` 代替预期的 `JobInputError`。L809 的 `except (JobInputError, ValueError, TypeError, AssertionError)` 混捕说明作者意识到了这一点，但属于防御性编码而非根本修复
- **直接证据**: `dayu/investment/domain/jobs.py:768-793`，7 处 `assert isinstance` / `assert type is`
- **影响**: 在 `python -O` 运行模式下，类型安全守卫静默失效；虽然被外层 except 兜住，但错误类型不精确（`ValueError` 而非 `JobInputError`）
- **建议改法和验证点**: 将 7 处 `assert` 替换为 `if not isinstance(...): raise JobInputError(...)` 模式，与 `_require_nonempty_text` / `_require_positive_int` / `_require_sha256` 保持一致。验证：`python -O -m pytest tests/application/test_job_service.py::TestGenericAttemptReceipt -q`
- **修复风险（低）**: 纯重构，不改行为
- **严重程度（中）**:

### M-002-未修复-中-缺少并行 complete/fail 竞态测试

- **入口/函数**: `tests/integration/investment/test_postgres_jobs.py`
- **文件(行号)**: `tests/integration/investment/test_postgres_jobs.py:666-756`（现有竞态测试区域）
- **输入场景**: 两个独立 PG engine 对同一 attempt 并发调用 `complete` 和 `fail`
- **实际分支**: 现有 3 个 `threading.Barrier(2)` 竞态测试覆盖 claim race（L666-702）、event sequence two-writer（L704-756）、terminal vs recover（L2038-2086），但无"两个 worker 同时对同一 attempt 结算"的竞态测试
- **预期行为**: 两个并发 complete/fail 只有一方成功（被 `FOR UPDATE` 行锁 + fence predicate 串行化），另一方应得到 `JobLeaseLostError`
- **实际行为**: 该竞态路径未被测试覆盖。虽然 `FOR UPDATE` 行锁在理论上保证了正确性，但缺少显式测试验证
- **直接证据**: `tests/integration/investment/test_postgres_jobs.py` 全文无 `threading.Barrier` + `complete`/`fail` 组合
- **影响**: 并发结算竞态的正确性未被显式证明；如果未来重构 lock 路径，可能引入回归
- **建议改法和验证点**: 新增 `TestConcurrentCompleteFail` 类，使用两个独立 engine + `threading.Barrier(2)` 测试：(1) 并发 complete+fail → 只一方成功；(2) 并发 complete+complete → 只一方成功。验证：`pytest tests/integration/investment/test_postgres_jobs.py -q --timeout=120`
- **修复风险（低）**: 仅新增测试
- **严重程度（中）**:

### L-001-未修复-低-JobService.cancel 缺少公共 API 路径集成测试

- **入口/函数**: `tests/application/test_job_service.py`、`tests/integration/investment/test_postgres_jobs.py`
- **文件(行号)**: `tests/application/test_job_service.py` 全文、`tests/integration/investment/test_postgres_jobs.py` 全文
- **输入场景**: 通过 `JobService.cancel()` 公共 API 路径取消 job
- **实际分支**: 单元测试中 `_FakeJobStore.cancel` 直接 `raise AssertionError("该测试不应调用")`（`test_job_service.py` fake）；集成测试直接调 `store.cancel()` 而非 `service.cancel()`
- **预期行为**: `JobService.cancel` 应有至少一个端到端集成测试覆盖 Service → Store 完整路径
- **实际行为**: `JobService.cancel` 的公共 API 路径无集成测试覆盖。虽然 Store 层 `cancel` 被充分测试，但 Service 层的委托路径未被验证
- **直接证据**: `test_job_service.py` 中 `_FakeJobStore.cancel` 行为是 `raise AssertionError`；`test_postgres_jobs.py` 中所有 cancel 测试直接调 `store.cancel()`
- **影响**: Service 层 `cancel` 委托路径的正确性未被端到端证明（低风险，因为是纯委托）
- **建议改法和验证点**: 新增一个集成测试通过 `JobService.cancel()` 公共 API 路径验证 ready cancel 和 leased cancel。
- **修复风险（低）**: 仅新增测试
- **严重程度（低）**:

## Open Questions

- `_persist_receipt()` 执行裸 INSERT（无 `ON CONFLICT DO NOTHING`），DDL 层有 `UNIQUE(tenant_id, attempt_id)` 约束。在两个并发 terminalize 路径（`authorize_agent_run_start` 的 deadline terminalize + `reconcile_agent_run_terminal` 的 Host terminalize）同时命中同一 attempt 时，第二个 INSERT 会收到 UNIQUE constraint violation。当前锁序（`reconcile` 路径先锁 correlation 再锁 job，`authorize` 路径先锁 job 再锁 correlation）在理论上可能导致两个事务持有不同行锁后互相等待，但 `authorize` 路径的 deadline terminalize 是在 correlation 锁之前执行的（L2250-2257），而 `reconcile` 路径的 receipt 写入是在 correlation 锁之后。实际死锁风险极低（需要两个事务精确交叉在各自 commit 前），但 `_persist_receipt` 的无 `ON CONFLICT` 设计依赖上层锁序的正确性。建议在后续 slice 中评估是否需要 `ON CONFLICT DO NOTHING` 作为 defense-in-depth。

## Residual Risk

- **测试 gaps**: (1) 无并行 complete/fail 竞态测试（M-002）；(2) `time_module.sleep()` 依赖在慢 CI 环境可能导致 flaky test；(3) 无 `recover_agent_run_after_no_host` 的 sha256 直接伪造测试；(4) `TestReservedHostCrashWindows` 未覆盖"Host entry 成功但 finalize 前崩溃"窗口。
- **CI gaps**: 未检查 CI 配置；三条独立 PG16 lane 的验证依赖本地执行。
- **未覆盖区域**: `dayu/investment/domain/jobs.py:880-960`（`build_agent_run_terminal_receipt` 及 Host receipt 相关逻辑）未被 subagent 深入逐行走读，但该 builder 的结构与 generic receipt builder 一致，且被集成测试覆盖。
