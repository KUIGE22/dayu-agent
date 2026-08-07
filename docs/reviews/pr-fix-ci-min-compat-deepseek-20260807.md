# Draft PR #1 CI min-compat Pyright 修复

**实现日期**: 2026-08-07
**脚本**: `utils/ci_pr_pyright.py` 920 行 18 AST 顶层函数，`tests/test_ci_pr_pyright.py` 985 行，pytest 收集 51 cases
**main()**: 74 源码行（AST 818–891）

---

## 问题

`.github/workflows/ci-pr-required.yml` 直接运行全仓 `pyright`，约 305 既有债务无法通过。
本 PR 另引入 86 条新诊断（25+25+35+1），已全部修复。

---

## 设计

### 全仓诊断 ratchet

- **全仓 pyright**：始终 HEAD/BASE 双端运行，无 .py 变更也不跳过。
- **双点直接比较**：`git diff base head`，不依赖 merge-base，浅克隆可用。
- **五元组**: `(文件, 1i行, severity, rule, message)`。pyright JSON 0-indexed → +1 统一。
- **Counter 多重集**：每条 BASE 诊断最多消耗一次。
- **按文件状态分类**：新增/修改(行映射)/未变更(identity)/重命名(路径+内容)/删除。
- **TypedDict 零宽类型**：`_PyrightPosition`/`_PyrightRange`/`_PyrightDiagnostic` + `JsonValue`/`JsonObject` TypeAlias + `_ChangeSet`/`_FileDiffInfo` dataclass。
- **逐字段 JSON 校验**：`_validate_and_build_diagnostics` 检查每条诊断的 file/severity/message/range/start.line/character（int≠bool、≥0）、rule 可选类型，返回构造的 `list[_PyrightDiagnostic]`。
- **Fail-closed**：--head 不一致→2、diff name-status malformed→2、pyright 异常/JSON 非法→3。
- **拆分 main**：74 行编排，18 函数 + `_ChangeSet`/`_FileDiffInfo` 2 dataclass。

### 86→0 类型修复（零 ignore/宽类型）

| 文件 | 修复方式 |
|---|---|
| `tests/engine/test_cli_running_config.py` (25) | 38 SimpleNamespace→WorkspaceConfig + output_dir |
| `tests/cli/test_research_template_command.py` (25) | isinstance 精确收窄；`_fake_materialize` `-> dict[str, JsonValue]`；`_fail_second_guide` 精确参数签名 |
| `tests/engine/test_prompt_assets.py` (35) | isinstance 逐级收窄替代 cast(dict[str, Any], ...) |
| `tests/engine/test_write_pipeline_scene_replay.py` (1) | assert 收窄 Optional |

---

## 修改文件

| 文件 | 操作 |
|---|---|
| `utils/ci_pr_pyright.py` | 新增 — 全仓 ratchet 920行 18函数 |
| `tests/test_ci_pr_pyright.py` | 新增 — 985行 pytest 51 cases |
| `.github/workflows/ci-pr-required.yml` | 修改 — `--head ${{ github.sha }}` + "full-repo ratchet" |
| `tests/engine/test_cli_running_config.py` | 修改 — 38 WorkspaceConfig |
| `tests/cli/test_research_template_command.py` | 修改 — isinstance 收窄 |
| `tests/engine/test_prompt_assets.py` | 修改 — isinstance 收窄 |
| `tests/engine/test_write_pipeline_scene_replay.py` | 修改 — Optional 收窄 |
| `tests/README.md` | 修改 — ratchet 条目 |

---

## 最终验证 (2026-08-07)

- **真实 ratchet**: HEAD 219, BASE 219, 全部 Counter 匹配 → exit 0
- **Pyright** (全部修改文件): 0 errors
- **Ruff**: 新 ratchet 文件 + research_template + prompt_assets scoped clean；cli_running_config/scene_replay 存在 PR 前既有 Ruff 债务，本轮新增行无新 Ruff finding
- **51 ratchet cases**: passed
- **Scoped suite** (26 files, excluding pre-existing playwright timeout): 1938 passed
- **三项 gates**: OK
- **git diff --check**: clean
- **git diff 新增行**: 零 `Any`/`object`（仅注释）/ `type: ignore`/`pyright: ignore`
- **AST**: Lambda 0, missing annotations 0

---

## 回合 2: CI min-compat pytest 修复 (2026-08-07)

### 失败测试

1. **`tests/application/test_write_run_comparison.py::test_comparison_can_load_directories_and_persist_artifact`** — 硬编码 `endswith("champion\\run_summary.json")`，Windows `\\` 在 macOS/Linux 上不匹配 `/`。
2. **`tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key`** — 本机 `SERPER_API_KEY` 或代理环境变量污染导致 `_search_with_serper` 不抛 `RuntimeError`。

### 根因

- **比较测试**: `compare_write_run_paths` → `load_write_run_summary` → `_summary_path` 调用 `Path(path).expanduser().resolve()` 返回平台原生 `Path`，再经 `str(champion_path)` 存入 `sources["champion"]`（`write_run_comparison.py:639`）。macOS 上得到 `/tmp/.../champion/run_summary.json`，但测试写死 Windows 反斜杠后缀。
- **Serper 测试**: 本机 shell 环境中 `SERPER_API_KEY` 或代理变量使 `_search_with_serper` 绕过 key 缺失检查，属于环境泄露而非代码 bug。

### 修复

只修改比较测试（Serper 是环境问题，不修改代码）。

**`tests/application/test_write_run_comparison.py:378`**：`endswith("champion\\run_summary.json")` → `endswith(str(Path("champion") / "run_summary.json"))`。利用已导入的 `pathlib.Path` 运算符产生平台原生分隔符，保留原始 `endswith` 语义，不弱化断言、不引入宽类型。

### 验证 (隔离 venv Python 3.11 + constraints/min-py311.txt)

| 检查项 | 结果 |
|---|---|
| `test_comparison_can_load_directories_and_persist_artifact` (隔离 venv) | 1 passed |
| `test_search_with_serper_requires_api_key` (`env -u SERPER_API_KEY -u SERPER_API_KEYS -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy`) | 1 passed |
| `tests/application/test_write_run_comparison.py` 全文件 | 17 passed |
| `pyright tests/application/test_write_run_comparison.py` | 0 errors, 0 warnings |
| `git diff --check` | clean |
| diff 范围 | 1 行，`-`/`+` 各 1 |

---

## 浅克隆设计

- diff 使用双点 `base head`，不依赖 merge-base
- `--head` 传 `github.sha`，脚本 resolve+验证一致性
- base ref 按需 `depth=1 fetch`
- `test_shallow_clone_direct_comparison` 用 file:// bare repo + `--depth=1` clone + fetch base 后断言 merge-base 仍不可用
