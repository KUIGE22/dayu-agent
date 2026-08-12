# Plan Review: Slice 2.2 CLI Format-Scope Erratum (MiMo)

- **Reviewer**: MiMo
- **Date**: 2026-08-12
- **Target plan SHA256**: `5bf2541dbb6db43b6a8a652800160ac6f6146a0c98490ead5ef24999c90eb824`
- **Fix SHA256**: `f427a223a9e9c32f4e81eadc32fed716bd8ca7a3ae055aef50fa851fc3f6152f`
- **Controller finding**: `S22-CTRL-011`
- **Baseline commit**: `37cac2f`

## 1. 独立核对范围

本复审完全独立，未读取任何 DeepSeek review 文档。

## 2. SHA256 校验

| 文件 | 预期 SHA256 | 实际 SHA256 | 状态 |
|------|-------------|-------------|------|
| Target plan | `5bf2541dbb6db43b6a8a652800160ac6f6146a0c98490ead5ef24999c90eb824` | `5bf2541dbb6db43b6a8a652800160ac6f6146a0c98490ead5ef24999c90eb824` | ✓ MATCH |
| Fix document | `f427a223a9e9c32f4e81eadc32fed716bd8ca7a3ae055aef50fa851fc3f6152f` | `f427a223a9e9c32f4e81eadc32fed716bd8ca7a3ae055aef50fa851fc3f6152f` | ✓ MATCH |

## 3. Ruff 版本确认

仓库锁定 Ruff 版本：`0.15.11` ✓

## 4. 独立核对结果

### 4.1 Baseline 全文件 format 失败可复现

```text
$ git show 37cac2f:tests/application/test_write_cli_dispatch.py > /tmp/baseline_test.py
$ uv run ruff format --check /tmp/baseline_test.py
Would reformat: /tmp/baseline_test.py
```

**结论**: ✓ 可复现。Baseline 文件本身不满足 Ruff 0.15.11 全文件 format check。

### 4.2 Range 边界完整覆盖且不越界

- Baseline 文件行数：2371
- 当前文件行数：~2395（+24 net）
- Range 1-40：覆盖模块首行 docstring（行 1）与 import 区域（行 32-36）✓
- Range 1297-1372：
  - Baseline 中 decorator 在行 1293，def 在行 1294
  - Import 变更 +4 行偏移后，decorator 在当前文件行 1297
  - Range 起始 1297 精确覆盖 decorator ✓
  - 最后变更在当前文件行 1371（在 range 内）✓
  - 行 1372 为方法末行区域 ✓
  - 下一方法 `test_dispatch_module_contains_exact_four_frozen_dataclasses` 从行 1374 开始 ✓
- 两个 range 均不越界 ✓

### 4.3 零上下文 diff gate

```text
$ git diff --unified=0 37cac2f -- tests/application/test_write_cli_dispatch.py
```

变更精确落在且仅落在：
1. 行 1：模块 docstring（"与" → "、platform 与"）
2. 行 32-36：`from dayu.cli.arguments import` 改为多行并加入 `PlatformDispatchArguments`
3. 行 1295-1371（baseline 行号）/ 1299-1371（当前行号）：`test_protocol_and_dayu_fields_form_exact_union` 方法体

**结论**: ✓ 零上下文 diff 证明变更只落在获准区域，无修改其它历史测试。

### 4.4 Ruff format range check 通过

```text
$ uv run ruff format --check --range=1-40 tests/application/test_write_cli_dispatch.py
1 file already formatted ✓

$ uv run ruff format --check --range=1297-1372 tests/application/test_write_cli_dispatch.py
1 file already formatted ✓

$ uv run ruff format --check dayu/cli/arguments.py
1 file already formatted ✓
```

### 4.5 Allowlist/STOP/其余 CLI union 合同

- `dayu/cli/arguments.py` 仍执行全文件 `ruff format --check` ✓
- `tests/application/test_write_cli_dispatch.py` 只对获准变化执行 range check ✓
- 未修改 Ruff 版本/配置 ✓
- 未添加 `fmt` 跳过标记 ✓
- 未删除既有断言（只修改/扩展）✓
- 未扩大 implementation allowlist ✓
- Research exact1、Write exact20、Platform exact4、Dayu exact25 合同保持 ✓
- 单一 `argparse.Namespace` base、零 class default、零 custom init 合同保持 ✓

### 4.6 是否存在更小方案

使用 range check 替代全文件 format check 是同时满足"历史字节不变"和"新增代码格式化"的最小方案。无法找到更小的替代方案：全文件 format 会破坏历史字节，完全跳过 format check 会违反代码质量门禁。

## 5. Verdict

**PASS**

## 6. Open Findings

| Severity | Count |
|----------|-------|
| H (High) | 0 |
| M (Medium) | 0 |
| L (Low) | 0 |

## 7. 残余说明

该历史测试文件整体仍不满足当前 Ruff formatter（566 行 diff）；owner 只能在独立、明确授权的机械格式化 work unit 中处理，本 Slice 不顺手修复。这与 fix document §4 的残余声明一致。
