# Slice 1.4 CN Runtime Factory Test Allowlist 独立对抗复核

- **时间**: 2026-08-11T02:53:47+0800
- **目标计划**: `docs/plans/2026-08-10-investment-platform-restoration.md`
- **Controller artifact**: `docs/reviews/plan-fix-20260811-025009-slice-1.4-cn-runtime-factory-allowlist-codex.md`
- **复核范围**: 仅复核 Controller artifact 中的 candidate fix，不修改任何 production/test/README/依赖
- **分支**: `codex/investment-platform`
- **HEAD**: `87e8fc6`

## Reviewed Target & Scope

独立复核 Slice 1.4 runtime-factory test allowlist 勘误 candidate：
1. 将 `tests/fins/test_cn_download_runtime.py` 加入精确 allowlist
2. 测试 fake `_RuntimeCnPipelineFactory.build_pipeline` 显式新增 `batching_repository` 和 `preparation_gate` 参数
3. 两个对象原样转发给真实 `CnPipeline`
4. 测试断言 identity 与 runtime 共享实例相同
5. 严禁 production compatibility glue

## Assumptions Tested

| 编号 | 假设 | 验证结果 |
|------|------|----------|
| A1 | Production callgraph 确实传递 `batching_repository` 和 `preparation_gate` | **CONFIRMED** |
| A2 | 测试 fake 签名不匹配是 failure 的根因 | **CONFIRMED** |
| A3 | 类型/import 可实施性无阻碍 | **CONFIRMED** |
| A4 | Identity 断言可观察 | **CONFIRMED** |
| A5 | 无隐藏范围或更小安全方案 | **CONFIRMED** |

## Confirmed Facts（已确认事实，非未决 finding）

以下四项均为独立验证确认的已知事实，不构成开放 finding：

### F01-CONFIRMED-测试 Fake 签名与 Production Callgraph 不匹配（根因）

- **位置**: `tests/fins/test_cn_download_runtime.py:186-234`
- **类型**: 已确认根因
- **事实**: `_RuntimeCnPipelineFactory.build_pipeline` 显式签名不包含 `batching_repository` 和 `preparation_gate`，而 production callgraph 显式传递这两个参数（S14-CTRL-12 / S14-TEMP-OWNERSHIP-FINAL-01）
- **直接证据**:
  - `service_runtime.py:1994`: `batching_repository=self.batching_repository`
  - `service_runtime.py:1995`: `preparation_gate=self._preparation_gate`
  - `factory.py:67-68`: `get_pipeline_from_normalized_ticker` 接收这两个参数
  - `cn_pipeline.py:124-125`: `CnPipeline.__init__` 接收这两个参数
- **状态**: 已由 Controller artifact 正确识别并给出修复方案

### F02-CONFIRMED-Identity 断言可观察性

- **位置**: Controller artifact 第 29-33 行
- **类型**: 已确认可实施性
- **事实**: `runtime.batching_repository`（public）和 `runtime._preparation_gate`（private but accessible）均可访问，identity 断言可实现
- **直接证据**:
  - `service_runtime.py:2029-2058`: `DefaultFinsRuntime.create` 构造时设置这两个属性
  - Python 无真正 private 属性，测试可访问 `_preparation_gate`
- **状态**: Controller artifact 的断言要求可实施

### F03-CONFIRMED-隐藏范围检查：无额外风险

- **位置**: 全局
- **类型**: 已确认无隐藏范围
- **事实**: 只有 `test_cn_download_runtime.py` 的 fake factory 有签名不匹配问题；`test_fins_runtime_tool_service.py` 使用 `**_kwargs` 兼容额外参数（line 614）
- **直接证据**: `grep` 搜索 `get_pipeline_from_normalized_ticker` 显示 23 处引用，仅此一处有问题
- **状态**: Controller artifact 范围正确

### F04-CONFIRMED-更小安全方案评估：无更优选择

- **位置**: 全局
- **类型**: 已确认方案充分性
- **事实**: 显式参数优于 `**kwargs`，原样转发符合 DRY 原则，Controller artifact 方案是最小且充分的
- **状态**: 无更优替代方案

## Open Questions

无。所有关键假设均已通过直接代码证据验证。

## Residual Risks

无。Controller artifact 的修复方案是最小且充分的，没有遗漏的范围或隐藏风险。

## Open Findings Summary

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| High | 0 | — |
| Medium | 0 | — |
| Low | 0 | — |
| **Total** | **0** | 所有已确认事实（F01-F04）均为非未决 finding |

## Final Plan Review Conclusion

**PASS** — open H/M/L = 0/0/0

Controller artifact 的修复方案正确且充分，无开放 finding：
1. 根因识别准确：测试 fake 签名与 production callgraph 不匹配（F01 已确认）
2. 修复范围最小：只修改一个测试文件（F03 已确认无隐藏范围）
3. 类型兼容性无阻碍：`CnPipeline.__init__` 确实接收这两个参数（F01 证据）
4. Identity 断言可观察：runtime 属性可访问（F02 已确认）
5. 无更优方案：显式参数优于 `**kwargs`（F04 已确认）

该 candidate 可以安全交给 implementation agent 执行。
