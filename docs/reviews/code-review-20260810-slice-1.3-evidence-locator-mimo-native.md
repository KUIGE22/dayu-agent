# Code Review

## Scope

- Mode: current changes
- Branch: `codex/investment-platform`
- Base: `3a70a16`
- Output file: `docs/reviews/code-review-20260810-slice-1.3-evidence-locator-mimo-native.md`
- Included scope: Slice 1.3 allowlist 内全部文件 — `dayu/fins/domain/evidence_locator.py`（新增）、`dayu/fins/domain/__init__.py`、`dayu/fins/service_runtime.py`、`dayu/services/fins_service.py`、`dayu/services/protocols.py`、`dayu/fins/README.md`、四份测试/testkit、`tests/application/test_fins_service.py`
- Excluded scope: `dayu/fins/tools/service.py`、storage implementation、engine processor、investment、migration、startup、根 `README.md`（均不在 Slice 1.3 allowlist）
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量代码走读。

## Findings

### 1-未修复-[中]-primary file meta 异常未包装为 primary_read_failed

- **入口/函数**: `DefaultFinsRuntime._read_primary_source` (`dayu/fins/service_runtime.py`)
- **文件(行号)**: `dayu/fins/service_runtime.py` — `_read_primary_source` 方法中 `self.source_repository.get_primary_file(...)` 调用处
- **输入场景**: source 主文件存在且 `get_primary_source().open()` 成功，但 `get_primary_file()` 抛出 `FileNotFoundError`（例如 primary file metadata 与 source 主文件不一致、仓储实现中间态、或 FS 路径部分删除）。
- **实际分支**: `get_primary_file()` 的 `FileNotFoundError` 未被 `try/except OSError` 捕获（该 `try` 只包裹 `source.open()` 与 `stream.read()`），异常直接沿调用栈传播。
- **预期行为**: 按 S13-CTRL-03 与已有 `primary_read_failed` 错误码语义，所有 source 主文件读取失败应统一包装为 `EvidenceLocatorError("primary_read_failed", ...)`，不泄漏仓储实现异常类型。
- **实际行为**: 调用方收到裸 `FileNotFoundError`，与 `primary_read_failed` 错误码约定不一致；若上层有 `except EvidenceLocatorError` 捕获则会漏过此异常，导致非确定性错误路径。
- **直接证据**: `service_runtime.py` `_read_primary_source` 方法：
  ```python
  source = self.source_repository.get_primary_source(...)
  try:
      with source.open() as stream:
          content = stream.read()
  except OSError as exc:
      raise EvidenceLocatorError("primary_read_failed", ...) from exc
  content_sha = sha256_hex(content)
  primary_file = self.source_repository.get_primary_file(...)  # ← 未在 try 内
  ```
  `get_primary_file()` 在 `try/except OSError` 块之外，`FileNotFoundError`（`OSError` 子类）不会被捕获。
- **影响**: 错误路径不确定性；上层若仅捕获 `EvidenceLocatorError` 则此异常逃逸；违背 plan 对 source 主文件读取统一 fail-closed 的语义。
- **建议改法和验证点**: 将 `get_primary_file()` 调用纳入同一 `try/except OSError` 块，或将 `get_primary_file` 的 `FileNotFoundError` 单独包装为 `primary_read_failed`。验证：新增测试 `_seed_source` 使 `get_primary_source` 成功但 `get_primary_file` 抛 `FileNotFoundError`，断言 `EvidenceLocatorError.code == "primary_read_failed"`。
- **修复风险（低）**: 仅扩大已有 `try` 块范围或新增一个 `except` 分支，不影响 happy path。
- **严重程度（中）**:

## Open Questions

无。所有 S13-CTRL-01..08 关键约束均有直接代码证据支撑，root cause 均来自同一逻辑/数据路径。

## Residual Risk

- 测试已覆盖五 kind 全组合、source/processed closure 全字段、dual-kind 碰撞、shared-cache 不复用、pre/post race（meta 漂移 + primary bytes 漂移）、citation 递归泄漏扫描，共 71 项。上述 Finding 1 的修复需补一个 `FileNotFoundError` 路径测试。
- `_postflight_identity` 中 `_read_primary_source` 会二次读取主文件全文（O(2N) memory/time），这是 TOCTOU 保护的必要代价，不视为 defect；若后续有超大文档性能需求可考虑 postflight 只读 SHA 元数据而非全文，但当前 plan 要求 full double-read。
- pyright 0 errors、ruff clean、71/71 tests passed。
