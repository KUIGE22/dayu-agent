# Slice 1 `_write_artifact_utils.py` 实现记录

- 状态：IMPLEMENTED + REVIEW FIX APPLIED + DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT
- 日期：2026-08-07
- 基线：accepted plan commit `89ef61a`
- 实现代理：Codex
- 设计真源：`docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.3，Slice 1

## 允许修改范围

本 slice 仅修改或创建以下路径：

1. `dayu/services/_write_artifact_utils.py`
2. `tests/application/test_write_artifact_utils.py`
3. `tests/README.md`
4. `docs/reviews/slice-1-write-artifact-utils-implementation-20260807-codex.md`

未修改任何 `write_model_*.py`；这些调用方迁移仍属于 Slice 2A/2B。

## 实现摘要

- 完全替换 worktree 中未跟踪的 v4.0 旧草稿，不把旧草稿视为 accepted 实现。
- 删除旧草稿的 `transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、
  `persist_immutable_atomic`、`serialize_compact` 和 resolve 版 `is_relative_to`。
- 最终只公开 accepted plan 指定的 17 个 helper，`__all__` 与清单严格一致。
- `require_mapping` 对合法映射执行 identity-return；copy 语义留给 Slice 2 的
  call-site adapter。
- 路径、时间和 codec 分别落实 lexical `is_subpath`、microseconds/seconds
  两族以及 standard/strict Base64 两族的精确错误契约。
- 所有生产函数均使用精确类型签名和完整中文 docstring；没有新增
  `Any`、`object`、`cast`、`type: ignore`、动态属性访问或兼容 wrapper。

## 测试摘要

`tests/application/test_write_artifact_utils.py` 共 21 个测试函数、22 个 collected
case（`test_format_utc_seconds_naive_raises` 含两个参数），覆盖：

- canonical str/bytes、fingerprint str/bytes、文件与原始字节指纹的迁移前差分；
- validated fingerprint 大小写策略和 A-F 错误文本反例；
- `require_mapping` 的字典子类 identity/copy，以及 canonical/fingerprint
  dict adapter；
- `require_text` 族 1 等价性和族 2-8 的独立行为反例；
- UTC microseconds/seconds 精度、seconds 族拒绝 naive/缺失 `utcoffset()`，以及
  microseconds 族接受 naive datetime 时与三个 eligible HEAD 私有实现的迁移前差分；
- 不 resolve 符号链接的词法子路径语义（复用 `tests.conftest.requires_symlink`）；
- 绝对路径在 resolve 前校验；
- standard Base64 接受、URL-safe 变体拒绝和两族错误文本；
- 17 个公开 helper 的精确公开面。

`tests/README.md` 已同步为当前 17 helper 测试入口，不保留旧 20 函数说明。

## 验证结果

### 聚焦测试

```text
source .venv/bin/activate
python -m pytest tests/application/test_write_artifact_utils.py -q
```

结果：`22 passed`。

### 单文件覆盖率

当前 Python 3.13 环境若让 pytest-cov 在导入 Dayu 前启用 tracer，会触发环境中的
NumPy 错误 `cannot load module more than once per process`。因此先在 tracer 外预载
`dayu.services`，再用 `coverage.Coverage(..., timid=True)` 启动同一个
`pytest.main(["tests/application/test_write_artifact_utils.py", "-q"])`。测试结果仍为
`22 passed`，目标文件报告：

```text
Name                                     Stmts   Miss  Cover
dayu/services/_write_artifact_utils.py      86      0   100%
TOTAL                                       86      0   100%
```

覆盖率达到 AGENTS.md 的单文件 `>= 80%` 门槛。

### 类型与 lint

```text
source .venv/bin/activate
pyright dayu/services/_write_artifact_utils.py tests/application/test_write_artifact_utils.py
```

结果：`0 errors, 0 warnings, 0 informations`。

```text
source .venv/bin/activate
ruff check dayu/services/_write_artifact_utils.py tests/application/test_write_artifact_utils.py
```

结果：`All checks passed!`。

### Diff 健康度

```text
git diff --check
```

结果：通过，无空白错误。

### 双路 Re-review

- `docs/reviews/code-review-20260807-210146.md`：PASS（0 High/Medium/Low open）
- `docs/reviews/code-review-20260807-210147.md`：PASS（0 High/Medium/Low open）

## 残余风险

- 本 slice 只提供并验证 shared helper，尚未迁移 19 个调用文件；生产调用切换和
  私有定义删除需由 Slice 2A/2B 完成。
- `decode_base64_strict` 按既有族 B 契约只捕获 `binascii.Error` 与
  `ValueError`，不主动扩展为族 A 的 `TypeError` 捕获；其公开签名已限制为 `str`。
- `format_utc` 保留既有 microseconds 族行为，不额外增加 seconds 族的 timezone
  前置校验。
- pytest-cov 的 NumPy/Python 3.13 tracer 兼容问题属于当前验证环境，不由本 slice
  修改依赖或全局测试配置。
