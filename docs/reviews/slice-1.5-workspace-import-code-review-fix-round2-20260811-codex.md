# Slice 1.5 workspace import — code review fix round2

- **Work unit**：Investment Platform Restoration
- **日期**：2026-08-11
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Controller**：Codex（never-ask 模式下自裁 integration test 最小适配，Controller
  后续裁决确认允许）
- **Adjudication**：
  `docs/reviews/slice-1.5-workspace-import-code-review-adjudication-20260811-codex.md`
- **Round1 fix**：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-20260811-codex.md`
- **Round3 fix**（2026-08-11 1142 Terra 复审 finding，deepseek-flash）：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round3-20260811-deepseek-flash.md`

## 触发 review

- **Terra**：`docs/reviews/code-review-20260811-111012.md`，**FAIL**，0H/1M/0L。
  唯一 finding（1-中）：主开关 ``--import-existing-workspace`` 仍为
  ``action="store_true"``，重复出现被静默折叠为 True，无 ``*_seen`` /
  ``*_repeated`` 状态；`_ImportSemanticStore` 只注册给两个带值参数，两个调用分支
  均不读取主开关出现次数。重复主开关 + 合法 manifest/tenant 会继续 read-only
  staging 并可能完成一次 import，不是预期的 usage rejection；S15-CTRL-04 要求
  import 语义参数 unknown/missing/repeated 全部 fail closed。
- **MiM Native**：`docs/reviews/code-review-20260811-111313.md`，**PASS** 但漏报该
  finding；三条 observation（POSIX-only FD、bundle_key 去重专项测试、DB connect
  count 断言）均为非 finding，不扩修。

## Controller dispositions（round2）

| Observation | Disposition | Closure |
| --- | --- | --- |
| Terra 1-中：主开关重复被静默折叠 | **ACCEPTED / FIXED** | 主开关改用计数/typed action；双门严格要求 seen==1 且 not repeated；无缺字段 fallback。 |
| MiM Obs-1/2/3 | REJECTED / NON-FINDING | 设计选择（macOS）、防御性测试观察、结构保证，不扩修。 |

## Applied fixes

1. **arg_parsing.py**：`_ImportSemanticStore` 扩展支持 ``nargs=0`` 无值开关——
   `__init__` 增加 `nargs` 参数透传 argparse；`__call__` 首次出现时开关写
   ``True``（带值参数仍写值），后续出现只置 ``<dest>_repeated`` 并递增
   ``<dest>_seen``。主开关注册由 ``action="store_true"`` 改为
   ``action=_ImportSemanticStore, nargs=0, default=False``，与 manifest/tenant
   共用同一 typed import-semantic action。
2. **init.py `run_init_command`**：主开关分支改为
   ``seen != 1 or repeated`` 时在普通 init 任何副作用前以
   ``workspace_import_usage``/1 fail closed，仅 ``seen==1 且 not repeated`` 进入
   ``_run_import_existing_workspace``。
3. **init.py `_run_import_existing_workspace`**：函数最前部（任何
   ``Path.resolve()``/staging/prepare deps 之前）同样要求 ``seen==1 且
   not repeated``，直接调用路径同样 fail closed。
4. **测试**：
   - `tests/cli/test_workspace_migrations.py`：新增 parser 重复主开关测试
     （`import_existing_workspace_seen==2`、`repeated is True`）、单次主开关
     seen==1 测试、dispatch 真实测试（重复主开关 + 合法 manifest/tenant 返回 1、
     输出 ``workspace_import_usage``、stage/prepare 调用均为 0）、
     `_run_import_existing_workspace` 直接调用门测试、staging OSError →
     owner_invalid 测试；全部手工 Namespace 明确补
     ``import_existing_workspace_seen=1``、``import_existing_workspace_repeated=False``。
   - `tests/integration/investment/test_workspace_migration.py`：既有手工 Namespace
     补 ``import_existing_workspace_seen=1``、
     ``import_existing_workspace_repeated=False``（最小测试边界迁移，Controller
     裁决允许；该文件本就在 Slice 1.5 accepted test WIP 中）。

## 白名单（round2）

- `dayu/cli/arg_parsing.py`、`dayu/cli/commands/init.py`、
  `tests/cli/test_workspace_migrations.py`、
  `tests/integration/investment/test_workspace_migration.py`（既有 WIP + 本 minimal
  适配）+ 本批 review/fix artifacts。`git status` 其余变更为 Slice 1.5 WIP 既有
  集合（S15-CTRL-03 allowlist 内），round2 未触碰白名单外文件。

## Verification

- focused：`tests/cli/test_workspace_migrations.py` **96 passed**（round2 新增 6 个：
  2 parser + 1 dispatch + 1 直接调用门 + 1 seen/repeated 门 + 1 staging OSError）。
- 相关：init/engine/cli + investment/application/fins 相关集 **1142 passed**；
  其中 round1 的 332/225/888 对应集合全部仍通过。
- coverage（artifact 口径 `COVERAGE_CORE=pytrace`）：
  `dayu/cli/arg_parsing.py` **100%**；`dayu/cli/commands/init.py` **95%**（含全部
  import mode 门与新增分支）。
- pyright：修改 4 文件 **0 errors**；全树 17 errors 全部位于既有未触碰文件
  （docling_processor 2、test_docling_processor_helpers 2、test_web_tools 13），
  与 artifact 基线一致，round2 零新增。
- Ruff：修改 4 文件默认规则 **All checks passed**；`--select I001` 仅报既有
  import 排序遗留（init.py 在 baseline 已存在；test 文件 I001 位于未触碰 import
  块），arg_parsing.py I001 干净，round2 未新增。
- clean Python 3.11 non-integration（round1 exact clean env：
  `env -u DAYU_PLATFORM_POSTGRES_DSN -u DAYU_PLATFORM_OBJECT_STORAGE -u
  SERPER_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u DAYU_REDIS_DSN -u
  DAYU_MINIO_ENDPOINT -u DAYU_MINIO_ACCESS_KEY -u DAYU_MINIO_SECRET_KEY
  python -m pytest -q --timeout=60 -m 'not integration and not slow and not e2e'`）：
  **8108 passed / 5 skipped / 81 deselected / 0 failed**；
  首次未 unset provider env 时 `test_search_with_serper_requires_api_key` 因
  env key 残留真实触网失败（代理 127.0.0.1:7897 不可达），clean env 下该测试
  走 mock 回退通过，0 failed 成立。
- `git diff --check`：通过。
- **PG16**：无 DB 路径改变，复用 round1 的 47 passed，不重跑（本轮限制）。

## Safety properties locked by tests（round2 增量）

- 重复主开关 + 合法 manifest/tenant → `workspace_import_usage`/1，stage/prepare
  调用 0；
- 手工 Namespace 缺 seen / seen=0 / seen=2+repeated / seen=1+repeated 均
  fail closed（无缺字段 fallback）；
- 直接调用 `_run_import_existing_workspace` 同样要求主开关精确一次；
- 普通无主参数 init 行为不回归（普通 init 零副作用 gate 保持）。

## Residual Risk

- 依赖 PG16 复用结论（本轮未运行 live/Docker/network）；最终须 Terra + MiM Native
  双路 re-review 后关闭 code review gate。

Terra 复审（114214）提出唯一 finding——新代码使用 `object`/`Any`；round3 fix artifact
（deepseek-flash）已修复：`_ImportSemanticStore` 拆为两个精确 action、
`parse_json_object` 改为 strict `validate_json_object_text`，新增生产签名
object/Any delta=0。最终 Terra `code-review-20260811-121322.md` 与 MiM Native
`code-review-20260811-121507-slice-1.5-final.md` 均 PASS/open0；重复主开关
finding 与 round3 类型 finding 均 CLOSED。
