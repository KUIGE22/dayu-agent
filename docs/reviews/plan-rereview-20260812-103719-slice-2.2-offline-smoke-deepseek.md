# Slice 2.2 offline smoke venv corrective re-review（DeepSeek，closure-only）

- 日期：2026-08-12（本机系统时钟 `20260812-103942`）
- Reviewer：DeepSeek（closure-only 独立 plan re-review，非 Controller、非 implementer）
- Review target：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（`S22-CTRL-012` 勘误，含 §3 allowlist 两行、§9 slice E、§11 门禁 8、§12 STOP 条目与状态行）
  - target SHA-256（已校验一致）：`ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62`
- 对照 corrective 来源：`docs/reviews/plan-fix-20260812-slice-2.2-offline-smoke-venv-codex.md`
  - SHA-256（已校验一致）：`02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6`
- 自身初审来源：`docs/reviews/plan-review-20260812-102211-slice-2.2-offline-smoke-deepseek.md`（PASS，open H/M/L=0/0/2，含 L1/L2/Q1）
- Repo / branch / HEAD：`codex/investment-platform` @ `5c74991282cdca3b3d42675c38b361407f15194b`（工作树含未提交 corrective docs diff）
- Implementation baseline（two-path diff 审计基线）：`37cac2f`
- 按任务约束：不检查任何 MiMo review artifact（包括 plan 引用的 MiMo 文件）；只审 corrective 闭合与代码生成就绪度
- 结论：**PASS / open H/M/L = 0/0/0**

## 1. 审查范围与闭合前提核验

本次是 closure-only 复审：只验证 S22-CTRL-012 corrective 是否逐字闭合初审 L1/L2/Q1 与 fix 文档 Controller 裁决矩阵，并做回归扫描确认 codegen 就绪、allowlist 精确、POSIX/Windows 语义、sanitized parent/no-index 传播、tests、STOP/scope 六项一致。

前提事实核验：

| 前提 | 证据 | 结果 |
| --- | --- | --- |
| 两文档字节与任务给定 SHA-256 一致 | `shasum -a 256` 两者均逐字匹配 | 成立 |
| corrective diff 只改 plan 文档 | `git diff HEAD --stat -- docs/` 仅 plan 文件 23+/4-；工作树 `utils/smoke_test_offline_bundle.py`、`tests/test_smoke_test_offline_bundle.py` 均未修改（实现仍冻结） | 成立 |
| 两 allowlist 文件在 `37cac2f` 与 HEAD 间字节不变 | `git diff 37cac2f HEAD -- <两文件>` 为空，two-path diff 审计良定义 | 成立 |
| plan 状态行与 fix 文档一致 | plan：`OFFLINE SMOKE VENV ERRATUM CORRECTIVE CANDIDATE / AWAITING DEEPSEEK + MIMO RE-REVIEW / IMPLEMENTATION FROZEN` | 成立 |

## 2. L1 / L2 / Q1 闭合核验（逐条对照 corrective）

| 初审项 | 初审要求 | corrective 现状 | 闭合 |
| --- | --- | --- | --- |
| L1（根因叙述「同目录」） | 改为 rpath `@executable_path/../lib` 指向 `bin/` 兄弟目录 `lib/` | plan L189「却不复制其rpath `@executable_path/../lib`所指向的`bin/`兄弟目录`lib/`及其中`libpython3.11.dylib`」；fix L16 同叙述；全文 `rg 同目录` 0 命中 | 已闭合 |
| L2（sanitized 缺 6 变量） | 补 `PIP_TARGET/PIP_USER/PYTHONUSERBASE/VIRTUAL_ENV/CONDA_PREFIX/PIP_FIND_LINKS` | plan item 4 与 fix L31 均列出全部 12 个清空变量（4×DYLD + PYTHONHOME + PYTHONPATH + 6 新增），另 `PIP_NO_INDEX=1`、清 index/extra-index 与大小写 proxy、fresh empty pip cache | 已闭合 |
| Q1（分支闭合测试机制） | 强制 pure `_venv_uses_symlinks()` helper，避免 monkeypatch 全局 `os.name` | plan item 1 强制抽取 `_venv_uses_symlinks(platform_name: str) -> bool`，只实现 `platform_name != "nt"`；item 3 要求直接以 `"posix"`/`"nt"` 调用并精确断言 `True`/`False`，明确「禁止monkeypatch全局`os.name`、依赖本机平台或放宽为truthy断言」 | 已闭合 |
| MiMo M2（recording builder） | recording builder 锁定 exact kwargs 与 create path | plan item 3：锁 `with_pip=True`、`clear=True`、当前真实 `os.name` 经 pure helper 得到的 `symlinks` 值、`create()` 精确接收传入 `venv_root`；不得创建真实 venv | 已闭合 |
| MiMo M1（sanitized parent 提供环境、utility 只透传） | CLARIFY 后落地为「parent 设 PIP_NO_INDEX=1；utility 只透传」 | plan item 4：utility 现有 `dict(os.environ)` 复制原样透传 sanitized parent，install scripts 保留硬编码 `--no-index --find-links`，utility 不得另行注入/覆盖/改脚本 | 已闭合 |
| MiMo M3（真实 E2E gate 已覆盖） | REJECT AS FINDING | plan L191 与 fix 矩阵均记录「不接受为 finding」，与自身初审 R2（CI lane 不在本 gate）一致 | 与 fix 一致，无扩散 |

fix 文档裁决矩阵与 plan L191 的裁决表述（接受 L1/L2/Q1 与 M2、M1 澄清、M3 拒绝）逐字一致。

## 3. Regression-scan：六项一致性核验

1. **Codegen 就绪度**：helper 签名、builder 表达式、测试合同、门禁序列全部逐字给定。
   - `_venv_uses_symlinks(platform_name: str) -> bool`、`_create_clean_venv(venv_root: Path) -> None` 精确签名；
   - builder 表达式 `venv.EnvBuilder(with_pip=True, clear=True, symlinks=_venv_uses_symlinks(os.name))` 后 `create(venv_root)` 逐字给定；
   - `main()` 只以 helper 替换当前两行 builder 创建——与现网 utility L188-189（`builder = venv.EnvBuilder(with_pip=True, clear=True)` + `builder.create(venv_root)`）精确对应，不触碰 `_extract_archive`/`_venv_paths`/`_run_install_script`/`_run_smoke_checks`；
   - 既有 owner 测试 `test_run_smoke_checks_temporarily_skips_dayu_web`（现网 tests L16-60）被要求继续通过。无重新设计空间。
2. **Exact allowlist**：仅 `utils/smoke_test_offline_bundle.py` 与 `tests/test_smoke_test_offline_bundle.py` 两既有文件；§3 新增两行 owner 责任与 S22-CTRL-012 正文一致；无新 production/CI/README/lock 路径。
3. **POSIX/Windows 语义**：`platform_name != "nt"` 与 stdlib `venv.main()` 的 POSIX 默认 `symlinks=(os.name != "nt")` 逐字一致；Windows 保持 `symlinks=False`（copy）与现状字节不变，无回归面；Windows copy 分支由 closed pure helper + recording builder 锁定 `symlinks` 值而可判定。
4. **Sanitized parent / no-index 传播**：12 变量清空 + `PIP_NO_INDEX=1` + fresh empty cache + index/extra-index/proxy 清空构成 closed 合同；install child 经 `dict(os.environ)` 原样继承；install 后每项 smoke（`import dayu`、CLI help）均为独立 child 且继承同一 sanitized env；`PYTHON_BIN` 仍是既有唯一 env 增项（不属被禁的「注入/覆盖」清单）；禁仓库 `.venv` import、禁已装 site-packages、禁网络 fallback。
5. **Tests**：双分支闭合断言（`posix`→True、`nt`→False）+ recording builder exact kwargs/create path，零全局 `os.name` 突变、零真实 venv；`utils/` 免 coverage 既有规则被正确引用，owner tests 全过为门禁（`uv run pytest tests/test_smoke_test_offline_bundle.py -q`）。
6. **STOP/scope**：S22-CTRL-012 item 2、末段 STOP 与 §12 新增条目（L950）三处一致且可判定（新文件/dependency/lock/CI/README/system install/dylib hack/平台特判/archive 语义/Windows copy 不可闭合/owner/static/format 任一失败/sanitized smoke 仍失败）；§9 slice E（L725）与 §11 门禁 8（L918）同步改写，无残留旧「offline bundle smoke」表述。

## 4. 抗压测试（无 finding）

- **根因机制**：copy-mode 不带 rpath 指向的兄弟 `lib/`，symlink 经真实路径解析——修复方向与既有 `python -m venv`/仓库 `.venv` 行为一致，机制闭环。
- **过度耦合**：私有 helper、单文件职责、零跨层依赖；无 callback/bool seam、无兼容 wrapper。
- **假性 PASS 面**：分支断言精确 `True/False` 非 truthy；recording builder 锁 exact kwargs；two-path diff 审计以 `37cac2f` 为基线（已验证字节不变）限制修改形状；sanitized env 合同排除 loader 注入/外部 find-links 满足依赖的路径。
- **环境细节**：真实 smoke 用哪个解释器执行 utility 未逐字点名，但根因段（L189）已定义失败环境为 uv-managed CPython 3.11.15，真实门禁的目的即在该失败环境内回归证明；且 owner unit tests + two-path diff 审计独立锁定修复形状，解释器选择不会产生假性 PASS，故不构成 open finding（见 §6 R1 跟踪）。

## 5. Open Questions

无。

## 6. Residual Risks（非 open finding，跟踪至 implementation gate / CI lane）

- R1（跟踪至实施期真实 smoke 执行）：真实门禁的 utility 解释器与 `--archive` 调用形态未在 plan 逐字给出，实施者按根因段失败环境（uv-managed CPython 3.11.15）以既有入口 `utils/smoke_test_offline_bundle.py --archive <path>` 在 sanitized parent 中执行即可；若执行中暴露新继承变量或新失败，按既有 STOP 路径回 Controller，不绕过。
- R2（跟踪至 CI lane 结果）：macos CI lane 用 runner 自带 python 跑同一 utility，修复前是否已绿未验证；symlink mode 在 POSIX 严格强于 copy mode，无回归风险，且 CI 结果不在本勘误 gate 内，不影响本结论。

## 7. 结论

**PASS / open H/M/L = 0/0/0**。

初审 L1/L2/Q1 已由 S22-CTRL-012 corrective 逐字闭合，fix 文档裁决矩阵与 plan 正文一致，两文档 SHA-256 与任务给定值一致；allowlist、POSIX/Windows 语义、sanitized parent/no-index 传播、owner tests、STOP/scope 六项回归扫描全部一致，且两 allowlist 文件在 `37cac2f` 与 HEAD 间字节不变使 two-path diff 审计良定义。本 corrective 可进入双路 re-review 收口与 Controller 接受流程；接受前 implementation 保持冻结，符合 plan 状态行约束。
