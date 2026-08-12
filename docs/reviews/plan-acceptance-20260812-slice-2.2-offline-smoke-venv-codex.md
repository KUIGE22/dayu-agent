# Slice 2.2 offline smoke venv 勘误接受记录

- **状态**：`ACCEPTED / DEEPSEEK + MIMO DUAL PLAN RE-REVIEW PASS / IMPLEMENTATION MAY RESUME`
- **Controller finding**：`S22-CTRL-012`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **Reviewed semantic target SHA-256**：`ea4f3c589678bd0a61457edf9b5380d0afab4adf06fd300d2045d0417dbd7a62`
- **Reviewed fix SHA-256**：`02b5563ac069206a736256d98b898a8a5031f56df0a5f08bbae8a24247d401b6`
- **Controller**：Codex

## 1. Source reviews 与裁决

- DeepSeek initial：`docs/reviews/plan-review-20260812-102211-slice-2.2-offline-smoke-deepseek.md`，artifact SHA-256 `6c363c670ff858f6f5754069eec00418fead24c90f2d3173db9dc22d04974e8f`，`PASS / open H/M/L=0/0/2`。
- MiMo initial：`docs/reviews/plan-review-20260812-102554-slice-2.2-offline-smoke-mimo.md`，artifact SHA-256 `f4124c076a96e32a2b1b8fb5d8cb1859433d5a455889020a85da40c0ad188fe6`，`PASS / open H/M/L=0/3/0`。

| Review item | Controller裁决 | 闭合结果 |
| --- | --- | --- |
| DeepSeek L1 | `accepted` | 根因叙述改为rpath `@executable_path/../lib`指向`bin/`兄弟目录`lib/`。 |
| DeepSeek L2 | `accepted` | sanitized gate补齐`PIP_TARGET`、`PIP_USER`、`PYTHONUSERBASE`、`VIRTUAL_ENV`、`CONDA_PREFIX`与`PIP_FIND_LINKS`清理。 |
| DeepSeek Q1 / MiMo M2 | `accepted` | 强制pure `_venv_uses_symlinks(platform_name)`并直接测试`posix`/`nt`，禁止monkeypatch全局`os.name`。 |
| MiMo M1 | `accepted`（clarification） | sanitized parent设置`PIP_NO_INDEX=1`；utility只原样透传，install scripts保留硬编码离线参数。 |
| MiMo M3 | `rejected-with-reason` | reviewer已确认真实端到端sanitized smoke覆盖该风险，不扩大实现或测试范围。 |

以上裁决均以修复uv-managed CPython POSIX copy-mode launcher失败的最小闭合为目标，不改变archive/install合同，不引入动态loader、平台探测或额外依赖。

## 2. Corrective re-reviews

- DeepSeek：`docs/reviews/plan-rereview-20260812-103719-slice-2.2-offline-smoke-deepseek.md`，artifact SHA-256 `1ae58a85d4005e4cbf6305bc25f3b9ad8f163b172be56d70224fab063a1694d7`，`PASS / open H/M/L=0/0/0`。
- MiMo：`docs/reviews/plan-rereview-20260812-103719-slice-2.2-offline-smoke-mimo.md`，artifact SHA-256 `1e4e09acb5191faf684c92d76ea474e01c1d51d7d573164a0d499b7e7e9e83fb`，`PASS / open H/M/L=0/0/0`。

两路均核验同一reviewed target与fix快照，确认allowlist、POSIX/Windows闭合分支、sanitized parent/no-index传播、owner tests及STOP/scope均code-generation-ready。Controller接受`S22-CTRL-012`，plan open H/M/L=`0/0/0`。

## 3. Implementation allowlist

本acceptance只恢复以下两条既有路径：

1. `utils/smoke_test_offline_bundle.py`
2. `tests/test_smoke_test_offline_bundle.py`

不得新增文件、dependency/lock、CI/README或system install，不得修改archive/install/`--no-index --find-links`语义，也不得采用动态rpath/libpython探测、dylib复制/改写、loader环境注入或platform fallback。任一既定owner/static/format/sanitized真实smoke门禁失败，按plan STOP回Controller。

## 4. 授权边界

本acceptance仅恢复本地implementation gate；本artifact-only收口未stage或commit，也不授权push、PR、merge、部署、live provider/model/broker、市场数据调用、交易或真实资金动作。计划验收不等于实现通过；修复后仍须完成真实sanitized offline smoke、其余Slice 2.2 implementation门禁及DeepSeek+MiMo最终独立code review。
