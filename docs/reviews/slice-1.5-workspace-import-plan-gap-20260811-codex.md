# Slice 1.5 code-review fix — STOP plan gap（Terra 2 无法在白名单内可靠闭合）

- **Work unit**：Investment Platform Restoration
- **Gate**：Slice 1.5 首轮 code-review fix（Controller 裁决 Terra 1/2/3 ACCEPT/FIX、MiM 07 ACCEPT/FIX、MiM 01/02/03/04/05/06 disposition）
- **Branch**：`codex/investment-platform`
- **Fix worker**：codex（deepseek-flash）
- **日期**：2026-08-11
- **状态**：**CLOSED / PLAN ERRATUM AND DUAL CODE RE-REVIEW PASS**

## 1. 停报结论

Terra 2（High）的“检查后替换 TOCTOU 全闭合”要求，在 S15-CTRL-03 白名单
约束下**无法可靠实现**。已穷尽白名单内全部闭合路径，确认任一路径均违反
白名单或明确禁令：

- 注入特殊 `Path` 子类让白名单外读取走内存快照：validator 内 `Path(raw)`
  重新构造会丢失子类（`Path(x)` 走 `os.fspath` 得普通 `Path`），不可靠；
- 在 `_research_template_bundle.py` 内复制白名单外函数等价解析逻辑：构成
  “第二套 validator”，明确禁止；
- 运行时 monkeypatch（全局/局部）：明确禁止；
- 预读 bytes 落盘临时文件后重写 payload 路径：复制研究产物正文，
  违反 S15-CTRL-01/07 的“不复制研究产物正文”；
- 事前/事中重新 lstat 验证：仅缩小窗口，不闭合；“仅事后 metadata 检测”
  已被 Controller 拒绝，事前等价方案不满足“闭合”。

故按 S15-CTRL-14 stop condition 停报，等待 Controller plan erratum。

## 2. 已保留的通过/基础改动（不宣称 B 已修）

### 2.1 Fix A（Terra 1，已完成并通过）

- `dayu/cli/arg_parsing.py`：新增 `_ImportSemanticStore` action，记录
  `import_manifest`/`target_tenant_id` 的 `<dest>_seen` 计数与
  `<dest>_repeated` 标志（`default=None` 时普通 init Namespace 不受影响）。
- `dayu/cli/commands/init.py`：
  - `_import_semantic_args_present()`：普通 init 分支最前 gate，无主开关携带
    import 语义参数（含重复）→ `workspace_import_usage` 返回 1，先于
    `Path.resolve()`、`mkdir`、advisory lock、copy config/assets、
    `apply_all_workspace_migrations`、prompt、prewarm 等全部副作用；
  - `_run_import_existing_workspace()`：主开关下缺失/重复语义参数同样
    `workspace_import_usage`。
- 测试（`tests/cli/test_workspace_migrations.py`）：
  - parser 层：完整参数解析、普通 init 无 import 参数（含 seen=0）、
    重复 `--import-manifest` / `--target-tenant-id` 记录 repeated+seen；
  - behavior 层：主开关下重复参数 usage；无主开关 A1 双参 / A2 仅 manifest /
    A3 仅 tenant 三态 usage；无主开关场景普通 init 副作用 calls=0（
    `_NORMAL_INIT_SYMBOLS` 全部打桩）+ source tree `(type,size,mtime_ns)`
    完全不变 + 输出含稳定 code 且不含 absolute path。
- 验证：`tests/cli/test_workspace_migrations.py` 87 passed（含全部既有 +
  新增）；parser 矩阵既有测试无回归。

### 2.2 Fix B（Terra 2，部分正确基础，未宣称已修）

`dayu/cli/commands/_research_template_bundle.py`（白名单内）已落地：

- `_require_regular_contained()`：lstat non-symlink regular + resolve +
  contained，先于任何 parse/validator/read/hash；
- `_open_regular_no_follow()`：自 source root 目录 FD 起逐段
  `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` + `dir_fd` 打开中间组件，末端
  `O_RDONLY|O_NOFOLLOW`，`fstat` 证明 regular（Linux/macOS 均可用）；
- `_load_json_object_no_follow()` / `_hash_regular_no_follow()`：descriptor
  读取与全部 closure 内容 hash 均经上述安全 FD（size 与 sha256 同 FD）；
- `_enumerate_closure_reference_paths()`：纯结构枚举（不访问文件系统）；
- `inspect_research_template_bundle_closure()` 重排为：descriptor 预检 →
  FD 读取解析 → 全部引用预检 → FD 哈希构造 entries → 复用既有 validator →
  typed result。
- 既有 7 个 closure 测试通过、`pyright` 0 errors。

**未闭合部分（本停报核心）**：validator
（`validate_research_template_bundle_descriptor`）在闭包入口仍按路径重读
artifacts，见 §3。docstring 已诚实化（明确“validator 重读窗口未在白名单内
完全闭合，见 plan-gap 说明，不宣称已修”）。

## 3. 阻塞点精确定位

`validate_research_template_bundle_descriptor(payload)` 的两个分支调用
**白名单外模块**的读取函数，它们接收 `Path` 并自行打开文件（跟随 symlink）：

| # | 触发分支 | 白名单外调用点 | 文件:行 | 读取方式 |
| --- | --- | --- | --- | --- |
| 1 | `source_write_manifest` 存在 | `_build_write_manifest_binding_semantics(source_path.resolve())` | `dayu/cli/commands/_research_template_core.py:1230` | `_load_json_object` / `_load_company_facets_from_manifest` |
| 2 | 同上 | `_resolve_template_selection_from_write_manifest(source_path.resolve())` | `dayu/cli/commands/_research_template_core.py:1134` | `_load_json_object` / `_load_company_facets_from_manifest` |
| 3 | 同上 | `_sha256_file(source_path)` | `dayu/cli/commands/_research_template_helpers.py:607` | `path.open("rb")`（trivial hash，可白名单内自算，**非阻塞**） |
| 4 | `research_progress_report` 存在 | `inspect_research_workbook_report(Path(report_raw), Path(workbook_raw))` | `dayu/cli/commands/research_workbook.py:499` | `read_text` / `_load_json_object` |
| 5 | 1/2 内部 | `load_company_facets_from_manifest(path)` | `dayu/cli/research_template_routing.py:83` | `path.read_text` |

第 1/2/4/5 项是白名单外（`_research_template_core.py`、
`research_workbook.py`、`research_template_routing.py` 均未列入 S15-CTRL-03
allowlist），且 validator 调用它们时用 `Path(raw)` 重新构造路径，任何注入
型 Path 子类均被破坏。

## 4. 所需最小 owner allowlist 扩展与接口契约（供 plan erratum）

### 4.1 推荐方案：可选 content-reader 注入（默认行为字节级不变）

allowlist 精确展开（只加函数级最小修改，不改变其它行为）：

- `dayu/cli/commands/_research_template_core.py`
- `dayu/cli/commands/research_workbook.py`
- `dayu/cli/research_template_routing.py`
- tests：`tests/cli/test_research_template_command.py`（已在 S15 allowlist）

接口契约（私有 Protocol，定义于 `_research_template_bundle.py`）：

```python
class _ClosureContentReader(Protocol):
    """闭包安全检查注入的只读内容源；只服务已预检/预读的路径。"""

    def is_regular_file(self, path: Path) -> bool: ...
    def read_bytes(self, path: Path) -> bytes: ...
```

- 被改函数统一增加 keyword-only 参数
  `content_reader: _ClosureContentReader | None = None`：
  - `None` 时读取行为与现实现字节级一致（所有既有 caller 不受影响）；
  - 非 `None` 时，对 source-tree 文件的全部读取（`_load_json_object` /
    `read_text` / `is_file` / manifest 解析）改走 `content_reader`
    （`read_bytes` 后自行 `json.loads`/解码，不复制解析逻辑）；
  - `_resolve_template_path` 等读 package assets 的调用**保持真实文件系统**，
    不纳入 reader。
- `_ClosureSnapshotReader` 实现（closure 入口构造）：仅对 preflight 后经
  `_open_regular_no_follow` 预读的路径提供内容；未预读路径
  `is_regular_file` 返回 `False`、`read_bytes` 抛错 → validator 相应分支
  fail closed，绝不打开普通路径。

### 4.2 备选：白名单外函数完全不动，仅依赖 §2.2 现状

即接受 validator 重读窗口为 cooperative-FS 残余 —— **Controller 已明确
拒绝该选项**，列此仅供完整性，不作为建议。

## 5. plan erratum 后待办测试设计

- preflight 后替换 `source_map` / `research_workbook` /
  `research_checklist` / `source_write_manifest` 为指向 source root 外文件
  的 symlink，断言：`ResearchBundleClosureError`、ordinary path read=0、
  结果来自安全快照或明确拒绝（`Path.open` / `_load_json_object` /
  `_sha256_file` / `read_text` 全链 spy）。
- descriptor symlink：external read/hash spy=0。
- 既有 7 个 closure 测试 + `_workspace_migrations.py` staging 相关全部无回归。

## 6. 验证状态（当前工作树）

- `tests/cli/test_workspace_migrations.py`：87 passed（Fix A 全套）。
- `tests/cli/test_research_template_command.py -k closure`：7 passed（Fix B
  基础无回归）。
- `pyright dayu/cli/commands/_research_template_bundle.py`：0 errors。
- 未运行：focused 全量 / 888 相关 / PG16 / coverage / Ruff / 卫生审计
  （等待 plan erratum 后 B 闭合再统一执行）。
- 未 commit / push / stash；未触碰白名单外文件（§3 所列模块零修改）。

## 7. 计划勘误后恢复实施（closure）

Controller 采纳本停报的第 4.1 推荐方案并扩展为 `S15-CTRL-15`（唯一 root
capability + descriptor-first/member-second 两阶段 FD acquisition + neutral
content-reader leaf + 四 owner keyword-only optional 透传），经 Terra 与
MiM Native 双路 plan re-review open0 后 accepted
（`plan-acceptance-20260811-slice-1.5-secure-closure-reader-codex.md`）。

Fix B/C/D 已按 accepted 合同恢复实施并全门禁通过（implementation artifact
§7）；本停报所列表格中的第 1/2/4/5 项白名单外重读已由
`content_reader` 快照注入闭合，不再保留 validator 按路径重读窗口。
实施阶段未使用 stash/临时文件/复制 validator，本文件不再代表阻塞。
最终 Terra `code-review-20260811-121322.md` 与 MiM Native
`code-review-20260811-121507-slice-1.5-final.md` 均 PASS/open0；该 plan gap、
对应实现 findings 与后续 round2/round3 findings 全部 CLOSED。
