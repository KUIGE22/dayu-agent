# Adversarial Rereview: PR #1 CI min-compat pytest 修复

**Reviewer**: MiMo (第二路独立 reviewer)
**日期**: 2026-08-07
**审查范围**: `tests/application/test_write_run_comparison.py` 一行跨平台路径断言 + `docs/reviews/pr-fix-ci-min-compat-deepseek-20260807.md` 证据追加

---

## 1. Diff 审查

### 1.1 测试变更 (`tests/application/test_write_run_comparison.py:378`)

**旧**: `assert comparison["sources"]["champion"].endswith("champion\\run_summary.json")`
**新**: `assert comparison["sources"]["champion"].endswith(str(Path("champion") / "run_summary.json"))`

#### 数据流验证

1. `compare_write_run_paths(champion_dir, challenger_dir)` → `load_write_run_summary(champion_path)` → `_summary_path(path)`
2. `_summary_path` (`write_run_comparison.py:56-60`) 调用 `Path(path).expanduser().resolve()`，返回平台原生 `Path`
3. `load_write_run_summary` 返回 `(resolved_champion_path: Path, champion: dict)` (line 70-81)
4. `compare_write_run_summaries` 接收 `champion_path=resolved_champion_path`，存入 `sources["champion"] = str(champion_path)` (line 639)
5. `str(Path)` 在 Unix 产生 `/`，Windows 产生 `\\`

**结论**: 数据流完整追溯，`str(champion_path)` 确实产生平台原生分隔符路径。

#### 语义保真性

- **旧断言**: 验证 `sources["champion"]` 以 `champion<sep>run_summary.json` 结尾
- **新断言**: `str(Path("champion") / "run_summary.json")` 在各平台产生对应分隔符：
  - Unix/macOS: `"champion/run_summary.json"`
  - Windows: `"champion\\run_summary.json"`
- **语义等价**: 新断言等价于旧断言，只是分隔符从硬编码 `\\` 改为平台自适应

#### 跨平台正确性

| 平台 | `str(Path("champion") / "run_summary.json")` | `str(champion_path)` 产生 | endswith 匹配 |
|---|---|---|---|
| macOS | `"champion/run_summary.json"` | `"/tmp/.../champion/run_summary.json"` | ✓ |
| Linux | `"champion/run_summary.json"` | `"/tmp/.../champion/run_summary.json"` | ✓ |
| Windows | `"champion\\run_summary.json"` | `"C:\\...\\champion\\run_summary.json"` | ✓ |

#### 是否掩盖错误

- `endswith` 保留了原有的后缀匹配语义
- 不是 `in` 检查，不会匹配路径中间意外出现的子串
- `Path("champion")` 是字面量，不依赖任何运行时状态
- 不会掩盖路径中 `champion` 目录名不存在的情况（因为 `endswith` 需要完整后缀匹配）

#### 可选替代方案对比

| 方案 | 优点 | 缺点 |
|---|---|---|
| `endswith(str(Path(...)))` (当前) | 保留完整后缀语义，覆盖目录名+文件名 | 略显冗长 |
| `.name == "run_summary.json"` | 更简洁 | 只验证文件名，丢失目录名验证 |
| `in` 检查 | — | 可能误匹配路径中间子串 |

**评估**: 当前方案是最优选择，在保真性、鲁棒性、可读性之间取得平衡。

### 1.2 证据文档 (`docs/reviews/pr-fix-ci-min-compat-deepseek-20260807.md`)

新增 "回合 2" 节，包含：

- **失败测试**: 准确列出两个失败用例
- **根因**: 正确描述 `_summary_path` → `Path(path).expanduser().resolve()` → `str(champion_path)` 数据流
- **修复**: 准确描述一行改动
- **验证**: 完整记录隔离 venv + constraints 环境下的验证结果

**证据准确性**: 所有代码路径引用 (`write_run_comparison.py:639`) 经核实正确。

---

## 2. Findings

| # | 严重性 | 描述 |
|---|---|---|
| 1 | — | 无发现。一行修复语义等价、跨平台正确、不掩盖错误。 |

---

## 3. Open Questions

无。

---

## 4. Residual Risk

- **低风险**: 测试未覆盖 `challenger` source 的后缀断言（原始测试即未覆盖，非本次引入）
- **无风险**: `Path("champion") / "run_summary.json"` 是确定性字面量计算，无运行时歧义

---

## 5. Verdict

**ACCEPTED**

一行修复正确解决跨平台路径分隔符问题，语义保真、证据准确、无 material blocker。
