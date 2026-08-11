# Slice 2.1 identity docstring guard 计划勘误 — MiMo adversarial review

- **状态**：`PASS / open H/M/L=0/0/0`
- **Reviewer**：MiMo（独立 plan reviewer）
- **目标文档**：`docs/reviews/plan-fix-20260811-slice-2.1-identity-docstring-guard-codex.md`
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **基线**：`489a910`
- **审查时间**：`2026-08-11`

## 裁决

**PASS**。`S21-CTRL-DOC-001` 是关闭 hard gate 的最小充分授权；stripped-AST + full-lane 双门禁足以证明零行为变化；不存在更窄方案。未读取另一 reviewer artifact。

## Finding 列表

### H-001：frozen hash 验证依赖声明式断言（已关闭 — 非阻塞）

**严重性**：Low → 已关闭

**描述**：勘误 §4 声明 tracked/untracked diff SHA-256 与 architecture guard 文件 SHA-256；reviewer 环境为只读，无法独立验证这些 hash。这是冻结协议的标准做法——reviewer 负责验证逻辑一致性而非重新计算 hash，implementation 恢复后的验证步骤（§3 第 1-5 项）会独立确认。

**证据**：勘误 §4 行 75-85 声明三个 hash；§3 行 59-66 列出恢复后必须执行的五项验证，其中第 1 项（stripped-docstring AST 对 `489a910` exact-equivalence）直接覆盖 AST 完整性。

**裁决**：非阻塞。hash 声明是冻结协议的标准形式；恢复后 §3 验证步骤独立覆盖。

---

## 问题 1 逐项分析：S21-CTRL-DOC-001 是否最小充分

**结论：是。**

### 冲突识别

勘误 §1 正确识别了不可调和的三方约束：

1. **AGENTS.md 编码硬约束**（行 35-36）：函数必须提供完整中文 docstring。
2. **Architecture guard**（`test_architecture_boundaries.py` 行 933-951）：`test_integration_tests_carry_chinese_docstrings` 扫描 `tests/integration/investment/**/*.py` 的全部 `FunctionDef`/`AsyncFunctionDef`/`ClassDef`/`Module`，缺少中文 docstring 即 fail。
3. **Baseline `489a910` 的 STOP 条件**（目标计划 §9 行 478-479）：禁止修改该 helper 的可执行 AST。

**证据**：
- 基线 helper（`489a910`，行 1442-1444）：
  ```python
  def _counted_read_postgres_dsn(settings: PlatformSettings) -> str:
              placeholder_read_calls[0] += 1
              return original_read_postgres(settings)
  ```
  无 docstring。
- Full lane 结果（勘误 §1 行 16-17）：`8183 passed, 1 failed`，唯一失败指向该 helper。
- Guard 扫描逻辑（`test_architecture_boundaries.py` 行 753-778）：`ast.get_docstring(node)` 为 `None` 或不含 CJK 字符即记录违规。`_counted_read_postgres_dsn` 是 `FunctionDef`，被 `ast.walk` 遍历命中。

### 授权精确性

`S21-CTRL-DOC-001` 的五项约束逐一对应可验证的不变量：

| 约束 | 验证方式 |
|---|---|
| ① 只插入 docstring 为函数体首句 | stripped-AST 对 `489a910` exact-equivalence |
| ② 不改 signature/closure/counter/reader/return/exception/monkeypatch target | stripped-AST exact-equivalence（任何字节差异都会被检测） |
| ③ 去除 docstring 后 AST 与 `489a910` 精确相同 | 实施后必须执行的验证步骤 |
| ④ 不借此清理其它 baseline 债务 | STOP 条件（勘误 §3 行 68-69）：必须修改其它内容才能通过即 STOP |
| ⑤ 不修改 architecture guard | guard 文件 frozen hash 声明 + STOP 条件 |

### 指定 docstring 内容

勘误 §2/目标计划 §7E 指定的 docstring：

```python
"""计数并转发 PostgreSQL DSN 读取。

Args:
    settings: 平台设置。

Returns:
    原读取函数返回的 PostgreSQL DSN。

Raises:
    透传原读取函数抛出的异常。
"""
```

**验证**：
- 含 CJK 字符（"计数"、"转发"、"平台设置"、"透传"等），满足 guard 的 `_contains_cjk` 检查。
- Args/Returns/Raises 完整，满足 AGENTS.md 编码硬约束。
- 语义准确：函数确实计数（`placeholder_read_calls[0] += 1`）并转发（`return original_read_postgres(settings)`）。
- 不与基线任何其它函数的 docstring 冲突。

---

## 问题 2 逐项分析：stripped-AST + full-lane 双门禁是否充分

**结论：是。**

### Stripped-AST 门禁

"去除新增 docstring 后 AST 与 `489a910` 精确相同"是一个强不变量：

- **AST exact-equivalence** 意味着：源码的语法结构（不含 docstring 文本）完全相同。Python AST 不包含注释、空行等表面差异，因此即使插入了空行或调整了缩进，只要 AST 不同就会被检测。
- **覆盖范围**：整个函数的完整 AST，包括闭包捕获的 `placeholder_read_calls`、`original_read_postgres`、参数 `settings`、返回类型注解 `str`、所有可执行语句。
- **不可绕过**：无法通过添加非 docstring 的 AST 节点来"伪装"通过，因为任何新增节点都会导致 stripped AST 与基线不同。

**风险点**：`ast.get_docstring` 在 AST 层面将 docstring 存储为函数体第一个 `ast.Expr(ast.Constant(str))` 节点。去除 docstring 即删除该节点。如果实施者在 docstring 后还添加了其它语句（如空 `pass`），stripped AST 会不同 → 验证失败 → STOP。这是正确的防线。

### Full-lane 门禁

`env -u SERPER_API_KEY pytest -q --timeout=60 -m "not integration and not slow and not e2e"` 通过意味着：

- **Architecture guard 通过**：`test_integration_tests_carry_chinese_docstrings` 不再报告 `_counted_read_postgres_dsn` 缺失。
- **其它 8182 个测试未受影响**：docstring 插入是纯注释语义，不影响运行时行为。
- **Escape guard 未被触发**：docstring 中无 `Any`/`object`/`cast`/`getattr`/`hasattr`。

**互补性**：stripped-AST 防止代码逻辑被修改；full-lane 防止表面修改引入未预期的副作用。两者交叉覆盖：

| 威胁 | stripped-AST 检测 | full-lane 检测 |
|---|---|---|
| 修改函数逻辑 | ✅ | ✅ |
| 修改闭包变量 | ✅ | ✅ |
| 修改 monkeypatch target | ✅ | ✅ |
| Docstring 触发语法错误 | N/A | ✅ |
| Docstring 影响其它测试 | N/A | ✅ |
| 修改 architecture guard | N/A | ✅（guard 本身也是 lane 的一部分） |

### PG16 lane 回归

勘误 §3 第 3 项要求 `pytest tests/integration/investment/test_identity_repositories_postgres.py -q` 作为独立 PG16 lane 之一通过。虽然 `_counted_read_postgres_dsn` 本身只在非 integration lane 中被 guard 扫描（guard 测试标记为 `@pytest.mark.unit`），但 PG16 lane 确保：

- 该测试文件中的 PG16 测试（如 `test_production_provider_wires_real_identity_service`、`test_production_provider_close_disposes_engine_once`）不因文件变更而回归。
- 作为三条独立 PG16 lane 之一，保留真实退出码。

---

## 问题 3 逐项分析：是否存在更窄方案

**结论：不存在。**

考虑的替代方案：

| 方案 | 评估 | 结论 |
|---|---|---|
| 修改 architecture guard 添加 baseline allowlist | 违反勘误 §2 第 5 项"不修改 architecture guard"；违反 AGENTS.md 最高约束"最佳实践优先"（allowlist 是表面修复） | ❌ 排除 |
| 给 guard 添加 nested function 豁免 | 大幅弱化 guard 覆盖范围；所有 future nested helper 都可无 docstring | ❌ 排除 |
| 把 `_counted_read_postgres_dsn` 移到模块级 | 修改 helper 可执行 AST + 闭包语义变化 + 违反 STOP 条件 | ❌ 排除 |
| 删除该 helper（移除计数功能） | 修改 test 行为 + 违反 §7E 授权 | ❌ 排除 |
| 跳过该测试 | 违反勘误 §2 第 5 项"不以跳过 full lane 关闭失败" | ❌ 排除 |
| **插入 docstring**（当前方案） | 纯注释语义、AST preserved、guard 通过、零行为变化 | ✅ 唯一可行 |

---

## 观察（非 Finding）

### Obs-1：勘误 STOP 条件跨 erratum 引用

勘误 §3 行 68-69 的 STOP 条件引用了"五项精确列出的变更"，其中 ①②③④ 涉及 provider allowlist erratum 的授权范围。这不是本 review 的评估对象——本 review 仅评估 `S21-CTRL-DOC-001`（docstring 插入）的充分性。Provider allowlist 变更的正确性已由先前双审确认（目标计划行 10-11 引用的 `plan-review-20260811-slice-2.1-provider-allowlist-corrective-mim.md` 与 `...corrective-closure-spark.md` 均 PASS）。

**评估**：不阻塞。STOP 条件中的跨 erratum 引用是保守的安全措施；本勘误的核心授权（`S21-CTRL-DOC-001`）独立自足。

### Obs-2：模块 docstring ③ 的更新描述

目标计划 §2 第 ③ 项授权"只把文件模块 docstring 中'仅一个 identity service / 不含 jobs'的陈述改为当前 exact two-service contract"。基线模块 docstring（行 11-12）包含：

> production startup 组合只含一个真实 ``investment_identity`` Service，
> 且导入图不含 jobs/evidence/portfolio future module；

这确实是"仅一个 identity service / 不含 jobs"的表述。更新为 two-service contract 的授权是正确的。

**评估**：不阻塞。属于 provider allowlist erratum 范围，且授权精确。

---

## 结论

`S21-CTRL-DOC-001` 是关闭 architecture guard hard gate 的**最小充分**授权：

1. **最小**：只插入一个 docstring，不修改任何可执行代码、guard 或其它文件。
2. **充分**：stripped-AST exact-equivalence 保证零代码逻辑变化；full-lane 通过保证 guard 满足且无回归；PG16 lane 保证 integration 测试不回归。
3. **可执行**：docstring 内容完全指定；验证步骤明确；STOP 条件清晰。
4. **无遗漏**：不存在更窄方案；architecture guard 不可修改；helper 可执行 AST 不可修改；full lane 不可跳过。
5. **无事实错误**：基线 helper 位置、guard 扫描逻辑、lane 失败原因均与代码一致。

**Verdict: PASS / open H/M/L=0/0/0**
