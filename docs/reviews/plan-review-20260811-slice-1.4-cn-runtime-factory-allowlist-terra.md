# Slice 1.4 CN runtime-factory 测试 allowlist 独立对抗复核

- **复核时间**：2026-08-11T02:54:57+0800
- **复核目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **Controller artifact**：`docs/reviews/plan-fix-20260811-025009-slice-1.4-cn-runtime-factory-allowlist-codex.md`
- **基线**：`codex/investment-platform`，`87e8fc638a21ef667a1401bb7439bbf6f40ed3b6`
- **复核范围**：仅本次 candidate：将 `tests/fins/test_cn_download_runtime.py` 加入 Slice 1.4 精确测试 allowlist，并在该测试 double 显式接收、原样转发 `batching_repository` 与 `preparation_gate`，以身份断言验证 runtime 共享实例传播。未审计或授权任何生产、README、依赖、既有 WIP 或其它 artifact 改动。

## 动机与边界判断

动机成立，且修复范围最小。当前 runtime 已将两个实例作为必传 keyword 从
`DefaultFinsRuntime._build_pipeline_for_ticker` 传至 `_build_pipeline`，后者再传给
`get_pipeline_from_normalized_ticker`；CN/HK 分支已把二者传给真实 `CnPipeline`。
现有 runtime-download 测试 monkeypatch 的 factory double 仍停留在旧签名，因而是测试
double 与已接受生产契约不同步，而不是生产链应回退为兼容旧 fake 的证据。

本 candidate 只把该失败文件纳入 allowlist，并禁止反射、`TypeError` fallback、compat
wrapper 或条件性漏传；未引入新生产接口、跨层依赖、共享状态 owner 或 future-slice 工作。
这是比改生产端兼容旧测试 double 更安全且更可维护的路径。

## 已验证的关键假设

| 假设 | 直接证据 | 结论 |
| --- | --- | --- |
| 失败可真实复现且根因唯一 | 本地执行指定同步用例，报 `TypeError: _RuntimeCnPipelineFactory.build_pipeline() got an unexpected keyword argument 'batching_repository'`，栈为 `runtime.execute → _build_pipeline_for_ticker → _build_pipeline → factory double`。 | 成立。 |
| 全量 `tests/fins` 失败未隐藏第二类回归 | 本地 `pytest -q tests/fins --tb=short`：2126 collected，2 failed、2124 passed；仅 `test_cn_download_runtime.py` 的同步与流式用例失败，两个栈均为上述旧签名。 | 成立。 |
| 生产传播链必须保持显式同实例传递 | `dayu/fins/service_runtime.py:892-921` 将两实例传给 factory；`:1981-1996` 从 runtime 持有的 `batching_repository` 与 `_preparation_gate` 传入；`dayu/fins/pipelines/factory.py:56-121` 在 CN/HK 分支原样构造 `CnPipeline`。 | 成立；不得加入兼容分支。 |
| 测试可独立证明身份，而非仅验证参数可接受 | candidate 明确要求 fake 原样传给真实 `CnPipeline`，并以 `is` 分别比较 runtime 的 `batching_repository` 和私有 `_preparation_gate`。既有 `tests/fins/test_runtime_batch_injection.py:65-81` 已采用同一 identity 判据验证生产 direct 链，证明访问方式与项目测试约定一致。 | 成立；实现时两项断言均须保留。 |
| 类型与导入可实施 | `BatchingRepositoryProtocol` 已由 `dayu.fins.storage` 公开导出；`CnPreparationGate` 已由 `dayu.fins.pipelines.cn_download_protocols` 定义并被 runtime 使用。对当前相关生产模块与目标测试运行 `pyright --level error` 为 `0 errors, 0 warnings`。 | 成立。 |
| 不存在隐藏 allowlist/耦合扩张 | 计划 `:1587-1598` 已将目标文件作为测试修改项，并把允许修改精确限制为该 double、原样转发和身份断言；Controller artifact 同步禁止生产 compat glue。 | 成立。 |

## Findings

无 material findings。

### Open findings（H/M/L）

| 高 | 中 | 低 |
| ---: | ---: | ---: |
| 0 | 0 | 0 |

## Open Questions

无。所需签名、实例 owner、调用路径、精确修改文件与验证门禁均已由计划和当前代码闭合。

## 剩余风险与跟踪建议

无本 candidate 特有的未闭合风险。实施后仍必须按 Controller gate 重跑目标文件和完整
`tests/fins/` corpus；这是验收条件，不构成当前 plan gap。当前工作区的其它 WIP 继续由
既有 Slice 1.4 gate/owner 跟踪，不应搭载进本次 allowlist 勘误。

## 结论

**PASS**。本勘误可安全进入双路 re-review gate：它修复已复现的测试接口漂移，使用明确、
可类型检查的参数与 identity 断言验证同一实例传播，并保持生产契约、分层边界与 WIP 冻结不变。

## 执行记录

- `source .venv/bin/activate && pytest -q tests/fins/test_cn_download_runtime.py::test_runtime_download_sync_uses_cn_pipeline_and_builds_contract_result`：预期失败，确认根因。
- `source .venv/bin/activate && pytest -q tests/fins --tb=short`：`2 failed, 2124 passed, 16 warnings in 33.74s`；两项失败均为目标旧 fake 签名。
- `source .venv/bin/activate && pyright --level error tests/fins/test_cn_download_runtime.py dayu/fins/service_runtime.py`：`0 errors, 0 warnings`。
