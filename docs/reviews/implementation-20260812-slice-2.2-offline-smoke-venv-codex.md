# Slice 2.2 offline smoke venv 实施记录

- **状态**：`REAL SANITIZED SMOKE PASS / READY FOR SLICE 2.2 FINAL CODE REVIEW`
- **Controller finding**：`S22-CTRL-012`
- **Accepted plan commit**：`82cc7d4`
- **Diff audit baseline**：`37cac2f`
- **实施者**：Codex

## 1. 实施结果

- `utils/smoke_test_offline_bundle.py` 新增 pure `_venv_uses_symlinks(platform_name: str) -> bool`，精确实现 `platform_name != "nt"`。
- 新增 `_create_clean_venv(venv_root: Path) -> None`，以 `venv.EnvBuilder(with_pip=True, clear=True, symlinks=_venv_uses_symlinks(os.name))` 构造 builder，并把原路径精确传给 `create()`。
- `main()` 只以 `_create_clean_venv(venv_root)` 替换原 builder 两行；archive、extraction、install、环境透传与 smoke 命令语义未改。
- owner tests 直接断言 `"posix"` 为 `True`、`"nt"` 为 `False`；recording fake 锁定 exact kwargs 与 create path，且证明未创建真实 venv。既有 dayu-web skip 测试继续通过，未 monkeypatch `os.name`。

## 2. 已执行门禁

| 门禁 | 结果 |
| --- | --- |
| `source .venv/bin/activate && uv run pytest tests/test_smoke_test_offline_bundle.py -q` | `PASS`，3 passed |
| `uv run pyright utils/smoke_test_offline_bundle.py tests/test_smoke_test_offline_bundle.py` | `PASS`，0 errors / 0 warnings / 0 informations |
| `uv run ruff check <two paths>` | `PASS` |
| `uv run ruff check --select F <two paths>` | `PASS` |
| `uv run ruff check --select I <two paths>` | `PASS` |
| `uv run ruff format --check <two paths>` | `PASS`，2 files already formatted |
| `git diff --check 37cac2f -- <two paths>` | `PASS` |
| `git diff --name-only 37cac2f -- <two paths>` | `PASS`，精确为 owner test 与 utility 两条路径 |
| `git diff --unified=0 37cac2f -- <two paths>` | `PASS`，变化符合 S22-CTRL-012 closed contract |

结果文件 SHA-256：

- `utils/smoke_test_offline_bundle.py`：`ea0437c6e3c003bda395131faba03b5e526ac43d40d6de29209b0d6626140687`
- `tests/test_smoke_test_offline_bundle.py`：`9d3a425e56a9274cea6955987e312f78bc973cd62785dad4824fc97c392d2c2a`

## 3. 真实 sanitized offline smoke

Controller 已重建 current wheel 与 offline archive，并在 S22-CTRL-012 指定的 sanitized parent 环境中运行官方 utility：

- Fresh current wheel：`/private/tmp/dayu-s22-final.tXpPj7/dist/dayu_agent-0.1.4-py3-none-any.whl`，SHA-256 `77c5e6abdf1c7f4f623c039e38fa05af06ff414dfd3ffdff0366fc8c5f20c91c`。
- Offline archive：`/private/tmp/dayu-s22-final.tXpPj7/offline/dayu-agent-0.1.4-macos-arm64-offline.tar.gz`，SHA-256 `45b3530846c1701f8c1d23aa7a81a2c9c5434823432c9355cce233078d45cae8`，大小 `370733309` bytes，包含 `172` 个 wheel、`0` 个 sdist。
- Archive embedded project wheel SHA-256 与 fresh current wheel 相同：`77c5e6abdf1c7f4f623c039e38fa05af06ff414dfd3ffdff0366fc8c5f20c91c`。
- Redis source/wheel SHA-256：`d8e788282a469fb74ce8d0c952b7a1d65cc6171435794b3f97a7cf64397c0cb2`。
- Archive `constraints.txt` SHA-256：`5f9e88ee827c3c4cd3f24608acebdd571be8eee96d26ae50400db81e76c709f7`。
- 门禁使用 `env -i` sanitized parent 与非仓库 cwd，设置 `PIP_NO_INDEX=1` 并指向 fresh empty pip cache；loader、Python、PIP index/target/user、proxy、venv/Conda 相关变量均不存在。
- 官方 `utils/smoke_test_offline_bundle.py` 退出码为 `0`；`import dayu`、`dayu-cli --help`、`dayu-wechat --help`、`dayu-render --help` 与 `dayu-cli init --help` 全部通过。
- 门禁结束后 `PIP_CACHE_FILES=0`，证明未使用外部 pip cache 或网络 fallback。

## 4. 剩余边界

真实 sanitized smoke 已闭合，本实现可进入 Slice 2.2 最终 code review。本次未运行 Docker、live model/provider/broker/trading，未修改 dependency/lock/CI/README/system install，未 stage、commit、push 或创建 PR。共享 worktree 中既有 Slice 2.2 WIP 保持不动。
