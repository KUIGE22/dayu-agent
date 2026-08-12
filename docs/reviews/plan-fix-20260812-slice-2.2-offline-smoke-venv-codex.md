# Slice 2.2 offline smoke venv plan fix

- 日期：2026-08-12
- Target：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- Plan baseline HEAD：`5c74991282cdca3b3d42675c38b361407f15194b`
- Implementation baseline：`37cac2f`
- 状态：**CLOSED / DUAL PLAN RE-REVIEW PASS**
- DeepSeek review：`docs/reviews/plan-review-20260812-102211-slice-2.2-offline-smoke-deepseek.md`
- MiMo review：`docs/reviews/plan-review-20260812-102554-slice-2.2-offline-smoke-mimo.md`

## 直接证据与根因

- Python 3.11 minimum与四平台tracked-lock resolver均已通过。
- macOS arm64归档包含`172`个wheel、`0`个sdist；归档构建成功。
- 官方smoke utility在uv-managed CPython 3.11.15执行默认copy-mode `EnvBuilder`时，于归档安装前的ensurepip阶段`SIGABRT`。
- uv launcher通过rpath `@executable_path/../lib`依赖`bin/`兄弟目录`lib/`中的`libpython3.11.dylib`；POSIX copy没有带上该目录。`python -m venv`与仓库`.venv`使用symlink且健康，因此失败owner是utility的OS venv策略，不是resolver或archive install。

## 最小计划修复（implementation-blocking erratum）

implementation allowlist仅增加：

1. `utils/smoke_test_offline_bundle.py`
2. `tests/test_smoke_test_offline_bundle.py`

实现必须抽pure `_venv_uses_symlinks(platform_name: str) -> bool`，只返回`platform_name != "nt"`；私有`_create_clean_venv(venv_root: Path) -> None`只把`os.name`传给该helper，再以`venv.EnvBuilder(with_pip=True, clear=True, symlinks=_venv_uses_symlinks(os.name))`创建并精确调用`create(venv_root)`。Windows copy、所有非Windows symlink。`main()`只能以该helper替换现有builder创建，不能改变归档解析、解压、安装脚本选择、`_venv_paths`或smoke命令集合。

owner tests直接以`"posix"`/`"nt"`调用pure helper并精确断言`True`/`False`，禁止monkeypatch全局`os.name`。recording builder另锁exact kwargs、当前`os.name`经helper得到的`symlinks`值与exact create path，且不创建真实venv。

禁止动态rpath/libpython探测、复制或改写dylib、`DYLD_*`/`PYTHONHOME`注入、runtime probing、archive/install或`--no-index --find-links`改写、fallback、新文件、新dependency/lock或系统安装；既有archive extraction安全不在本勘误扩大。

真实验收须从清空`DYLD_LIBRARY_PATH`、`DYLD_FALLBACK_LIBRARY_PATH`、`DYLD_FRAMEWORK_PATH`、`DYLD_FALLBACK_FRAMEWORK_PATH`、`PYTHONHOME`、`PYTHONPATH`、`PIP_TARGET`、`PIP_USER`、`PYTHONUSERBASE`、`VIRTUAL_ENV`、`CONDA_PREFIX`、`PIP_FIND_LINKS`、index/extra-index及大小写proxy变量，并使用fresh empty pip cache的sanitized parent启动，固定`PIP_NO_INDEX=1`。utility现有环境复制只透传该parent；归档install scripts继续使用既有硬编码`--no-index --find-links`，utility不得另行注入/覆盖环境或修改脚本。官方utility必须新建venv、从既有archive安装，再以同样sanitized环境的独立child完成`import dayu`和既有CLI help smoke，证明不依赖loader注入或外部package location。

`utils/`免coverage，但以下门禁必须全过：`uv run pytest tests/test_smoke_test_offline_bundle.py -q`、两条路径的exact Pyright、Ruff default/F/I、两文件`ruff format --check`、sanitized真实archive smoke、以`37cac2f`为baseline的exact two-path diff审计及`git diff --check`。

## STOP 与授权边界

需要新路径/dependency/lock/CI/README、platform hack/system install、Windows语义不明确，或sanitized真实smoke仍失败时立即STOP。用户授权仅覆盖联网dependency validation；不包含live provider/model/broker、交易、push、PR。双路plan review及Controller接受前不得进入implementation。

## Controller 裁决矩阵

| Review item | 裁决 | Corrective |
| --- | --- | --- |
| DeepSeek L1 | ACCEPT | 根因改为rpath `@executable_path/../lib`指向兄弟`lib/`。 |
| DeepSeek L2 | ACCEPT | sanitized gate增加六个package/venv环境变量清理。 |
| DeepSeek Q1 / MiMo M2 | ACCEPT | 强制pure `_venv_uses_symlinks(platform_name)`；tests直接传`posix`/`nt`，禁止monkeypatch全局`os.name`。 |
| MiMo M1 | CLARIFY | parent设置`PIP_NO_INDEX=1`；utility只透传，install scripts保留硬编码离线参数。 |
| MiMo M3 | REJECT AS FINDING | reviewer自身确认真实E2E gate已覆盖，不另扩实现或测试范围。 |

历史candidate阶段状态为**CORRECTIVE CANDIDATE / AWAITING DEEPSEEK + MIMO RE-REVIEW**；当时双路open0且Controller接受前implementation冻结。

## Closure

- Reviewed semantic target SHA-256：`ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62`
- Reviewed fix SHA-256：`02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6`
- DeepSeek re-review：`docs/reviews/plan-rereview-20260812-103719-slice-2.2-offline-smoke-deepseek.md`，SHA-256 `1ae58a85d4005e4cbf6305bc25f3b9ad8f163b172be56d70224fab063a1694d7`，`PASS / open H/M/L=0/0/0`
- MiMo re-review：`docs/reviews/plan-rereview-20260812-103719-slice-2.2-offline-smoke-mimo.md`，SHA-256 `1e4e09acb5191faf684c92d76ea474e01c1d51d7d573164a0d499b7e7e9e83fb`，`PASS / open H/M/L=0/0/0`

Controller已接受本corrective；implementation只可按精确双路径allowlist恢复。本closure只更新plan gate元数据，不改变上述candidate阶段的根因、合同、裁决矩阵、STOP或授权边界。
