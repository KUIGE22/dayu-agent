# PR #1 Rereview: CI Pytest 跨平台路径断言修复

**Reviewer**: DeepSeek (adversarial, read-only)
**Date**: 2026-08-07 10:56:45
**Scope**: 单文件单行变更 — `tests/application/test_write_run_comparison.py:378`
**Background**: GitHub run 31141645853 ratchet step success but required pytest lane failure. 硬编码 `champion\\run_summary.json` 在 Unix 失败。修复使用 `str(Path("champion") / "run_summary.json")` 产生平台原生分隔符。

---

## Findings

### F1: 断言语义完整保留 ✓

**Claim**: 修复保留了原始 `endswith` 语义，不弱化断言。

**Verification**:
- 原始断言 `endswith("champion\\run_summary.json")` 检查 `sources["champion"]` 路径以 Windows 反斜杠后缀结尾。
- 新断言 `endswith(str(Path("champion") / "run_summary.json"))` 在 macOS/Linux 产生 `champion/run_summary.json`，在 Windows 产生 `champion\run_summary.json`。
- 两者都是 `endswith` 后缀检查，语义等价——仅在分隔符产生方式上从硬编码改为平台自适应。
- 实测: macOS 上 `str(Path("champion") / "run_summary.json")` → `'champion/run_summary.json'`。
- 生产代码链路（`write_run_comparison.py:639`）: `sources["champion"] = str(champion_path)`，其中 `champion_path` 经 `_summary_path` → `Path(path).expanduser().resolve()` 产生平台原生路径，确保断言的后缀与生产代码输出一致。

**Verdict**: 语义完全保留，不弱化。

### F2: 跨平台正确性 ✓

**Claim**: `Path("champion") / "run_summary.json"` 在所有平台上产生正确分隔符。

**Verification**:
- `pathlib.Path` 的 `/` 运算符在所有平台上产生原生分隔符（POSIX `/`，Windows `\`）。
- `str()` 返回平台原生字符串表示。
- 测试使用 `tmp_path`（pytest fixture），产生平台原生临时目录路径。
- 生产代码 `_summary_path` 使用 `pathlib.Path` 的 `/` 运算符和 `.resolve()`，输出平台原生路径。
- 测试断言的后缀与生产代码输出使用相同的平台约定 → 跨平台一致性。

**Edge cases considered and cleared**:
- macOS `/private/var` vs `/var` symlink: `resolve()` 产生规范路径，后缀不受前缀影响。
- `tmp_path` 中含有 `champion/run_summary.json` 子串: pytest 生成 UUID 级唯一目录名，不会偶然匹配。
- `sources["champion"]` 为 `None`: 在 `compare_write_run_paths` 调用路径中，`resolved_champion_path` 始终为 `Path`（由 `_summary_path` 保证返回非 None Path），`str()` 产生有效字符串。

**Verdict**: 跨 Windows/Linux/macOS 正确。

### F3: 未引入错误掩盖 ✓

**Adversarial question**: 如果生产代码路径构建方式改变（如目录名变更、文件名变更），测试是否会错误通过？

**Analysis**:
- 若 `_SUMMARY_FILE_NAME` 从 `"run_summary.json"` 改为其他值 → 断言失败（后缀不匹配）→ 正确暴露变更。
- 若 `_summary_path` 不再对目录追加文件名 → `sources["champion"]` 路径不以 `run_summary.json` 结尾 → 断言失败 → 正确暴露变更。
- 若 `sources["champion"]` 的构建逻辑被移除或改变 → 路径结构变化 → 断言失败 → 正确暴露变更。
- 唯一的理论边界：如果某人在路径中引入包含 `champion/run_summary.json` 但不正确的中间目录（如 `/tmp/old_champion/run_summary.json_bak/test_xxx/champion/run_summary.json`），`endswith` 仍通过。但这与原始断言的 `endswith` 弱点一致，不是本次修复引入的新风险，且 pytest `tmp_path` 的唯一性使其在实践中不可触发。

**Verdict**: 未掩盖任何错误，测试对生产代码变更的敏感度与原始断言相同。

### F4: 类型安全 ✓

- `comparison["sources"]["champion"]` 类型: `str`（由 `write_run_comparison.py:639` 的 `str(champion_path)` 保证）。
- `str(Path("champion") / "run_summary.json")` 类型: `str`。
- `str.endswith(str)` → `bool`。
- pyright 验证: `tests/application/test_write_run_comparison.py` — 0 errors, 0 warnings。
- 未引入 `Any`、`object`、`type: ignore`、`cast`。

**Verdict**: 完全类型安全。

### F5: Serper 测试不修改代码的判断正确 ✓

**Claim**: `test_search_with_serper_requires_api_key` 失败是环境泄露，不应修改代码。

**Verification**:
- 测试意图: 验证无 `SERPER_API_KEY` 时 `_search_with_serper` 抛出 `RuntimeError`。
- 失败原因: CI 或本机 shell 环境中的 `SERPER_API_KEY` / 代理变量使生产代码绕过了 key 缺失检查。
- 修复方式: `env -u SERPER_API_KEY -u SERPER_API_KEYS -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy` 清除环境变量后测试通过。
- 这是正确的处理方式——测试本身无误，问题在于环境隔离不充分。

**Verdict**: 不修改 Serper 测试代码的判断合理。

### F6: 证据准确性 ✓

| Doc 声明 | 实际代码 | 匹配 |
|---|---|---|
| `write_run_comparison.py:639` — `sources["champion"]` | Line 639: `"champion": str(champion_path)` | ✓ |
| `_summary_path` → `Path(path).expanduser().resolve()` | Line 57: `Path(path).expanduser().resolve()` | ✓ |
| `str(champion_path)` 存入 sources | Line 639: `str(champion_path)` | ✓ |
| 测试行 378 | Diff 确认 line 378 | ✓ |
| diff 范围: 1 行，`-`/`+` 各 1 | git diff 确认 | ✓ |

**Verdict**: 所有证据引用准确。

---

## Open Questions

### OQ1: `endswith` 断言本身是否足够强？

当前断言只检查路径后缀。更严格的版本可以检查完整路径结构：
```python
champion_source = Path(comparison["sources"]["champion"])
assert champion_source.parent.name == "champion"
assert champion_source.name == "run_summary.json"
```

**评估**: 这是对既有测试模式的改进建议，不是本次修复的缺陷。`endswith` 在 `tmp_path` 唯一目录的约束下已足够可靠。优先级: 低，可在后续测试加固中考虑。

### OQ2: CI 环境变量隔离策略

Serper 测试暴露了 CI 环境变量泄露问题。当前修复是手动 `env -u` 清除，CI workflow 中是否已固化此策略？

**评估**: 不在此次 review scope（本次只审 pytest 断言修复），但值得在 CI workflow 中显式清除敏感环境变量以避免同类问题。

---

## Residual Risk

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| `endswith` 弱断言在极端构造的路径中误通过 | Low | Very Low | `tmp_path` 唯一性使其不可触发；与原始断言风险等级相同 |
| CI 中其他测试存在类似环境变量泄露 | Low | Low | Serper 测试已暴露问题，其他测试暂未受影响；建议 CI workflow 统一清理 |
| 若 `pathlib` 在极罕见平台上行为异常 | Negligible | Negligible | pathlib 是 Python 标准库核心模块，所有 Tier 1 平台行为一致 |

---

## Verdict: **ACCEPTED**

**理由**:
1. 断言语义完整保留，`endswith` 检查强度不降级。
2. 跨 Windows/Linux/macOS 正确，`pathlib.Path` 运算符产生平台原生分隔符。
3. 未引入错误掩盖，测试对生产代码变更的敏感度不变。
4. 类型安全，pyright 0 errors。
5. 测试通过（macOS 本机验证: 1 passed，pyright 0）。
6. 所有引用的证据行号和代码链路经独立验证准确。
7. Serper 不修改代码的判断正确——问题在环境泄露，不在测试逻辑。

**无 material blocker。建议合入。**
