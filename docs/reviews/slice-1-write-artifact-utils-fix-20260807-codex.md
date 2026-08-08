# Slice 1 `_write_artifact_utils.py` Code Review 修复记录

- 状态：FIXED / AWAITING RE-REVIEW
- 日期：2026-08-07
- 基线：accepted plan commit `89ef61a`
- 修复代理：Codex
- DeepSeek review：`docs/reviews/code-review-20260807-204228.md`
- MiMo review：`docs/reviews/code-review-20260807-204238.md`

## 修改范围

本轮只修改：

1. `tests/application/test_write_artifact_utils.py`
2. `docs/reviews/slice-1-write-artifact-utils-implementation-20260807-codex.md`
3. `docs/reviews/slice-1-write-artifact-utils-fix-20260807-codex.md`

没有修改生产 helper、`tests/README.md` 或任何 `write_model_*.py`。

## Findings 裁决

### DeepSeek L-01 — ACCEPTED / FIXED

接受缺少 `format_utc` naive datetime 迁移前 characterization 的 finding。

新增 `test_format_utc_naive_matches_eligible_microseconds_family`，使用一个固定 naive
datetime，直接比较 shared `format_utc` 与三个 eligible HEAD microseconds 私有实现：

- `write_model_configuration_application._format_utc`
- `write_model_configuration_rollback_application._format_utc`
- `write_model_configuration_manual_recovery._format_utc`

测试不硬编码本地时区转换结果，因此不会把执行机器的时区写入期望值；它只锁定
shared 与迁移前 eligible 私有族在同一环境下的行为等价性。生产 helper 语义未改。

### DeepSeek L-02 — REJECTED WITH REASON

`_MissingOffsetTimezone.utcoffset` / `dst` 的 `-> None` 是合法的更窄返回类型：
基类契约允许 `timedelta | None`，测试子类刻意始终返回 `None` 来构造
“存在 tzinfo 但缺失 offset”的反例。Pyright 对实现和测试保持
`0 errors, 0 warnings, 0 informations`。扩大标注不会增加测试表达力，因此不修改。

### DeepSeek L-03 — REJECTED WITH REASON

`decode_base64_strict` 不捕获 `TypeError` 是 accepted plan C5-CTRL-03 明确要求的族 B
语义：shared 入参已收窄为 `text: str`，调用方先完成各自文本校验；helper 只保持
私有族 B 的标准 Base64、`binascii.Error` / `ValueError` 异常集合和
`"must be valid base64"` 文本。本轮不得把它改成族 A 行为。

### MiMo LOW-01 — REJECTED WITH REASON / NON-DEFECT OBSERVATION

`validated_fingerprint` 的 `str(value or "").strip().lower()` 正是 accepted plan 对
eligible A/G 族的精确规范；非法值仍被拒绝，大小写和错误文本差异已有固定反例。
MiMo review 自身也将其评估为“设计预期、风险为无”，无需修改。

### MiMo LOW-02 — REJECTED WITH REASON / NON-DEFECT OBSERVATION

`while chunk := stream.read(...)` 与私有实现的 `while True` + empty-chunk break
语义等价，多块读取差分测试已经直接比较指纹输出。循环风格差异不是缺陷。

### MiMo LOW-03 — REJECTED WITH REASON / NON-DEFECT OBSERVATION

`tests/README.md` 的新增条目由测试文件新增触发，位置和职责均符合 AGENTS.md；
MiMo review 自身也确认内容准确、不越界、风险为无。本轮不改 README。

## 验证

### 聚焦 pytest

```text
source .venv/bin/activate
python -m pytest tests/application/test_write_artifact_utils.py -q
```

结果：`22 passed in 0.64s`。

### 单文件覆盖率

当前 Python 3.13 环境直接在 Dayu 导入前启用 pytest-cov tracer 会触发 NumPy 的
`cannot load module more than once per process`。沿用实现阶段已记录的 workaround：
先导入 `dayu.services`，从 `sys.modules` 与 package attribute 移除目标 helper
模块，再启动 `coverage.Coverage(source=[module_name], timid=True)`，通过
`pytest.main(["tests/application/test_write_artifact_utils.py", "-q"])` 运行同一
聚焦测试，最后执行：

```python
cov.report(
    include=["dayu/services/_write_artifact_utils.py"],
    show_missing=True,
)
```

结果：

```text
22 passed
Name                                     Stmts   Miss  Cover
dayu/services/_write_artifact_utils.py      86      0   100%
TOTAL                                       86      0   100%
```

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/_write_artifact_utils.py tests/application/test_write_artifact_utils.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

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

## 残余风险

- `format_utc` 仍按 accepted plan 保留 microseconds 私有族的 naive datetime
  行为；本轮只增加跨实现差分守护，不改变其时区策略。
- 19 个生产调用文件仍等待 Slice 2A/2B 迁移。
- pytest-cov / NumPy / Python 3.13 的 tracer 兼容问题属于验证环境，本轮未扩大
  scope 修改依赖或测试基础设施。
