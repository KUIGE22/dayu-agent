# Phase 1 Integration Corrective Re-review（Terra）

## Findings

### 1. 中 — close-failure 测试会吞掉 cleanup 失败，未真实证明“仍完成清理”（P1-INT-FIX-02）

- **入口/触发**：`TestProductionStartupBlackBox.test_production_provider_close_propagates_failure_and_still_cleans()` 中首次 `prepared.close()` 按预期抛出 `RuntimeError`，同时 cleanup helper 内的 `drop_temporary_login()` 或 `_migrate_down_and_assert()` 任一失败。
- **实际分支**：测试捕获首次 close 错误到局部变量 `close_error`；`finally` 调用 `_cleanup_production_startup_resources()`，该 helper 确实逐项尝试 prepared/env/login/migration 并收集异常。可是当 `close_error is not None` 时，测试把非空 `cleanup_errors` 传给 `_report_cleanup_errors(primary_exception=close_error, ...)`；该函数只给这个局部、随后不再抛出的 `close_error` 添加 note，随后测试继续以 `close_calls == 2` 成功结束。
- **预期行为**：failure-path 测试应在模拟 close 失败后，使任何 cleanup failure 令测试失败，同时保留首次 close 失败这一事实；这样才能证明 schema/group role/login 的收口不是被测试控制流掩盖。
- **直接证据**：[tests/integration/investment/test_identity_repositories_postgres.py](/Users/wsk/workspace/dayu-agent/tests/integration/investment/test_identity_repositories_postgres.py:1769) 捕获并不重新抛出 `close_error`；[同文件](/Users/wsk/workspace/dayu-agent/tests/integration/investment/test_identity_repositories_postgres.py:1787) 对有主错误的 cleanup error 仅调用记录 note 的 helper；[同文件](/Users/wsk/workspace/dayu-agent/tests/integration/investment/test_identity_repositories_postgres.py:461) 的 helper 在主错误存在时不 raise。因此即使 migration downgrade/assert 或临时 LOGIN 删除失败，测试仍可通过。
- **影响**：P1-INT-FIX-02 的实现 helper 已具备“尽力执行全部清理步骤、常规主异常不被 cleanup 覆盖”的控制流，但新增 close-failure 测试没有证明其最关键的 cleanup 成功语义；74 Docker PASS 因而不能作为该 failure-path 的充分回归证据。
- **修复方向**：仅收紧该测试：在已捕获预期 close error 的分支显式断言 `cleanup_errors` 为空（或将其作为测试失败重新抛出），并保留对首次 close 错误及第二次重试的断言。无需改变生产代码或 cleanup helper。
- **修复风险**：低。
- **严重程度**：中。

## 已核对的已闭合项

- **P1-INT-FIX-01**：通过。`_install_black_box_startup_stubs()` 只替换 `S3FileStore.head_bucket()`；真实 `_build_s3_store_from_settings()` 仍依次执行严格 JSON 解析、凭证读取、`S3FileStore` 构造与 probe 调用。placeholder 负例断言 `_read_postgres_dsn`、显式 provider 及 production provider 三类计数均为 0，证明在 PG/provider 动作前失败。
- **P1-INT-FIX-02（实现部分）**：通过。`_cleanup_production_startup_resources()` 对 prepared、env、login、migration 各自独立捕获并累计异常；正常测试路径中的主异常仍由原始 `raise` 传播，cleanup 错误以 note 附着，不会覆盖主错误。上方 finding 仅限新增 failure-path 测试未验证 cleanup 成功。
- **P1-INT-FIX-03**：通过。wrong-role 用例先完成 `_migrate()`，之后才在 `try/finally` 覆盖范围内创建临时 LOGIN；migration 失败时尚无 cluster-wide LOGIN，创建成功后 cleanup 必达。
- **P1-INT-FIX-04**：通过。当前 diff 已移除私有 `_FsRepositorySet`、`_bare` 与 `TypeVar`；stub 返回显式 `_FakeRepositorySet`，没有新增 production seam。
- **Docker 74 证据**：数值与当前测试集合相符：identity 文件 16 项，另三 lane 为 33、11、14 项，合计 74。Flash artifact 的 §9.2 已明确记录 corrective 后 74 passed；但 §9.3 仍误写为“72/72”，属于 artifact 内部文字不一致，且本复核不具备原始 Docker 日志，不能以此消除上述 failure-path 测试缺口。

## Open Questions

无。上述问题可由当前控制流直接证明。

## Residual Risk

除 finding 外，真实 S3 admission、provider/role 主链路、close 幂等性和 Docker lane 总数均有当前代码与 artifact 的直接佐证。未执行 Docker，以遵守本次只读复核范围。

## Conclusion

**FAIL** — open H/M/L：**0 / 1 / 0**。P1-INT-FIX-02 的 close-failure 测试须使 cleanup failure 可见后，才可作为该修复的闭环证据。
