# Plan Re-Review: S22-CTRL-012 离线 smoke POSIX venv launcher 勘误

- **日期**: 2026-08-12T10:37:19Z
- **Reviewer**: MiMo (independent re-reviewer)
- **Reviewed target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` (SHA256 `ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62`)
- **Reviewed corrective**: `docs/reviews/plan-fix-20260812-slice-2.2-offline-smoke-venv-codex.md` (SHA256 `02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6`)
- **Prior MiMo review**: `docs/reviews/plan-review-20260812-102554-slice-2.2-offline-smoke-mimo.md`
- **Implementation baseline**: `37cac2f`
- **Scope**: 验证 S22-CTRL-012 corrective 对 MiMo 原始 M-01/M-02/M-03 的闭合、codegen readiness、allowlist、POSIX/Windows 语义、sanitized parent/no-index 传播、tests、STOP/scope

## SHA-256 验证

| 文件 | 期望 SHA-256 | 实际 SHA-256 | 状态 |
|---|---|---|---|
| `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` | `ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62` | `ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62` | MATCH |
| `docs/reviews/plan-fix-20260812-slice-2.2-offline-smoke-venv-codex.md` | `02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6` | `02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6` | MATCH |

## Implementation baseline 验证

`git diff 37cac2f -- utils/smoke_test_offline_bundle.py tests/test_smoke_test_offline_bundle.py` 返回空——两个文件均无 WIP 变更，implementation 尚未开始。STOP 条件（双路 plan review + Controller 接受）正确生效。

## MiMo 原始 findings 闭合矩阵

| Finding | 原始严重程度 | Controller 裁决 | 闭合验证 |
|---|---|---|---|
| M-01: PIP_NO_INDEX 应用范围不明确 | M | CLARIFY | Controller 明确：parent 设置 `PIP_NO_INDEX=1`，utility 透传 `os.environ`，install scripts 保留硬编码 `--no-index --find-links`。当前 utility L124 `env = dict(os.environ)` 已满足——parent 环境变量自然流入子进程。无需 utility 额外注入。corrective L31 明确写入此语义。**闭合。** |
| M-02: Windows 测试分支覆盖策略 | M | ACCEPT (as MiMo M2 + DeepSeek Q1) | corrective 要求：(1) 抽取 pure `_venv_uses_symlinks(platform_name: str) -> bool`，返回 `platform_name != "nt"`；(2) owner tests 直接以 `"posix"` / `"nt"` 参数调用该 helper 并精确断言 `True` / `False`，禁止 monkeypatch 全局 `os.name`。plan § S22-CTRL-012 L195 明确写入。**闭合。** |
| M-03: POSIX symlink dylib 解析风险 | L | REJECT AS FINDING | Controller 接受 reviewer 自身确认：sanitized smoke test gate (L196) 已覆盖端到端验证——创建 venv + 安装 + import dayu + CLI help。若 symlink venv 有缺陷，ensurepip 或 install 阶段即失败。不另扩实现或测试范围。**闭合。** |

**总闭合**: 3/3 findings 已由 Controller 正式裁决并写入 corrective plan。无遗留 open finding。

## Codegen readiness 逐项验证

| # | 合约点 | Plan/Corrective 证据 | 代码状态 | 判定 |
|---|---|---|---|---|
| C1 | 抽取 `_venv_uses_symlinks(platform_name: str) -> bool` | S22-CTRL-012 L193: "pure `_venv_uses_symlinks(platform_name: str) -> bool`，只实现 `platform_name != "nt"`" | 尚未实现（STOP 生效） | READY |
| C2 | 新增 `_create_clean_venv(venv_root: Path) -> None` | S22-CTRL-012 L193: builder 精确为 `venv.EnvBuilder(with_pip=True, clear=True, symlinks=_venv_uses_symlinks(os.name))`，随后 `create(venv_root)` | 尚未实现 | READY |
| C3 | `main()` 只替换 builder 创建 | S22-CTRL-012 L193: "只以该 helper 替换当前两行 builder 创建"——当前 L188-189 `builder = venv.EnvBuilder(with_pip=True, clear=True)` / `builder.create(venv_root)` 替换为 `_create_clean_venv(venv_root)` | 尚未实现 | READY |
| C4 | 归档解析/解压/安装脚本选择/`_venv_paths`/smoke 命令不变 | S22-CTRL-012 L193 | 当前代码 L55-162 保持不变 | READY |
| C5 | Owner tests: pure helper 两分支 | S22-CTRL-012 L195: "直接以 `posix` 与 `nt` 参数调用 `_venv_uses_symlinks` 并分别精确断言 `True` 与 `False`" | 尚未实现 | READY |
| C6 | Owner tests: recording builder | S22-CTRL-012 L195: "以 recording builder 锁定 `_create_clean_venv` 构造参数精确为 `with_pip=True`、`clear=True`、当前真实 `os.name` 经 pure helper 得到的 `symlinks` 值，且 `create()` 精确接收传入的 `venv_root`；不得创建真实 venv" | 尚未实现 | READY |
| C7 | 既有 `test_run_smoke_checks_temporarily_skips_dayu_web` 继续通过 | S22-CTRL-012 L195 | 当前 L16-60 未被修改 | READY |

## 精确 allowlist 验证

Plan § S22-CTRL-012 (L193) + §3 allowlist 表确认仅扩大至：

1. `utils/smoke_test_offline_bundle.py` — 实现 `_venv_uses_symlinks` + `_create_clean_venv` + `main()` 替换
2. `tests/test_smoke_test_offline_bundle.py` — owner tests

**禁止项**（S22-CTRL-012 L194, L196）：
- 禁止新文件、新 dependency/lock
- 禁止动态探测 launcher/rpath/libpython、复制或重写 dylib
- 禁止设置 `DYLD_*` / `PYTHONHOME`、修改解释器、注入 platform 特殊路径
- 禁止修改 archive/install script / `--no-index --find-links` 流程或新增 fallback
- 禁止 CI/README 变更
- 禁止 system install
- 禁止 monkeypatch 全局 `os.name`

Allowlist 边界清晰、最小化，与 plan §3 一致。

## POSIX / Windows 语义验证

| 平台 | `_venv_uses_symlinks` 返回 | `EnvBuilder(symlinks=...)` 行为 | 证据 |
|---|---|---|---|
| POSIX (macOS/Linux) | `True` (`"posix" != "nt"`) | symlink mode——launcher 通过 symlink 指向完整 runtime，避免 rpath `@executable_path/../lib` 指向缺失 `lib/` 的问题 | S22-CTRL-012 L189: "python -m venv 与仓库 .venv 使用 symlink 且健康" |
| Windows | `False` (`"nt" != "nt"` 为 `False`) | copy mode——保持 Windows 原有行为 | S22-CTRL-012 L193: "Windows 保持 copy" |

语义正确：pure helper 的 `platform_name != "nt"` 是确定性 closed branch，不依赖运行时探测。

## Sanitized parent / no-index 传播验证

| 层级 | 变量设置 | 传播机制 | 证据 |
|---|---|---|---|
| Parent (test harness) | `PIP_NO_INDEX=1`，清空 `DYLD_LIBRARY_PATH` / `DYLD_FALLBACK_LIBRARY_PATH` / `DYLD_FRAMEWORK_PATH` / `DYLD_FALLBACK_FRAMEWORK_PATH` / `PYTHONHOME` / `PYTHONPATH` / `PIP_TARGET` / `PIP_USER` / `PYTHONUSERBASE` / `VIRTUAL_ENV` / `CONDA_PREFIX` / `PIP_FIND_LINKS`，清空 index/extra-index 及大小写 proxy 变量，fresh empty pip cache | S22-CTRL-012 L196 | 完整 |
| Utility | `env = dict(os.environ)` (L124) | 透传 parent 全部环境变量至 install script 子进程 | S22-CTRL-012 L196: "utility 现有 `dict(os.environ)` 环境复制必须原样透传该 sanitized parent" |
| Install script | 硬编码 `--no-index --find-links` | 归档 install scripts 继续使用既有硬编码参数 | S22-CTRL-012 L196: "归档 install scripts 继续以既有硬编码 `--no-index --find-links` 安装" |
| Child smoke | 继承 sanitized 环境 | 每项 smoke 是独立 child，继承 sanitized 环境 | S22-CTRL-012 L196: "安装完成后的每项 smoke 都是另起 child，且 child 同样继承 sanitized 环境" |

Controller 对 M-01 的 CLARIFY 裁决确认：parent 设置 `PIP_NO_INDEX=1`，utility 只透传，不自行注入。当前 utility L124 `env = dict(os.environ)` 已满足此语义——无需代码变更。

## Tests 验证

| 测试要求 | 来源 | 判定 |
|---|---|---|
| `_venv_uses_symlinks("posix")` 精确断言 `True` | S22-CTRL-012 L195 | READY |
| `_venv_uses_symlinks("nt")` 精确断言 `False` | S22-CTRL-012 L195 | READY |
| recording builder 锁定 `with_pip=True`, `clear=True`, `symlinks` 值, `create(venv_root)` | S22-CTRL-012 L195 | READY |
| 不创建真实 venv | S22-CTRL-012 L195 | READY |
| 禁止 monkeypatch 全局 `os.name` | S22-CTRL-012 L195 / corrective L45 | READY |
| 既有 `test_run_smoke_checks_temporarily_skips_dayu_web` 通过 | S22-CTRL-012 L195 | READY（未修改） |

## STOP / scope 验证

S22-CTRL-012 L201 明确 STOP 条件：

> 若修复需要新文件、新 dependency/lock、CI/README、system install、archive 安装语义、动态 loader hack 或平台特判，Windows copy 语义无法由 pure helper 的 closed branch 确定，owner/static/format 任一失败，或 sanitized 真实 smoke 仍失败，必须立即 STOP 回 Controller。

Corrective L37 补充：

> 需要新路径/dependency/lock/CI/README、platform hack/system install、Windows 语义不明确，或 sanitized 真实 smoke 仍失败时立即 STOP。

STOP 条件完整、明确、可执行。当前状态为 `CORRECTIVE CANDIDATE / AWAITING DEEPSEEK + MIMO RE-REVIEW`——implementation 冻结直到双路 review PASS 且 Controller 接受。

## 授权边界验证

| 授权项 | 状态 | 证据 |
|---|---|---|
| 联网 dependency validation | 已授权 | corrective L37 |
| push / PR | 未授权 | corrective L37 |
| live provider/model/broker | 未授权 | corrective L37 |
| 交易动作 | 未授权 | corrective L37 |
| Docker / dependency/network gate | 未授权 | 用户指令 |
| live market/model/provider/broker/trading | 未授权 | 用户指令 |

## Controller 裁决一致性验证

| 裁决项 | Controller 决定 | Re-review 验证 |
|---|---|---|
| DeepSeek L1 (根因 rpath) | ACCEPT | 已写入 S22-CTRL-012 L189 |
| DeepSeek L2 (sanitized gate) | ACCEPT | 已写入 S22-CTRL-012 L196，包含完整环境变量清空列表 |
| DeepSeek Q1 / MiMo M2 (pure helper) | ACCEPT | 已写入 S22-CTRL-012 L193+L195 |
| MiMo M1 (PIP_NO_INDEX) | CLARIFY | 已写入 corrective L31+L46 |
| MiMo M3 (E2E coverage) | REJECT AS FINDING | corrective L47: "reviewer 自身确认真实 E2E gate 已覆盖" |

所有裁决已正确反映在 corrective plan 中。

## 结论

**PASS**

S22-CTRL-012 corrective plan 与 plan-fix 均已正确闭合 MiMo 原始全部三个 findings。M-01 通过 Controller CLARIFY 闭合（parent 透传语义已明确），M-02 通过 ACCEPT 闭合（pure helper + 直接参数测试），M-03 通过 REJECT AS FINDING 闭合（E2E gate 已覆盖）。corrective 合约完整、codegen-ready：allowlist 精确最小化，POSIX/Windows 语义由 closed pure branch 确定，sanitized parent/no-index 传播链清晰，tests 合约无歧义，STOP 条件完备。implementation 冻结状态正确——源码无 WIP 变更。

Open H/M/L = 0/0/0.
