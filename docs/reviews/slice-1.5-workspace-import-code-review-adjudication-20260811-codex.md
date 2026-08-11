# Slice 1.5 workspace import — code review adjudication

- **Work unit**：Investment Platform Restoration
- **Controller**：Codex
- **日期**：2026-08-11
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Implementation**：
  `docs/reviews/slice-1.5-workspace-import-implementation-20260811-deepseek-flash.md`
- **Round2 fix**（2026-08-11 1112 Terra 复审 finding）：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round2-20260811-codex.md`

## Source reviews

- Terra：`docs/reviews/code-review-20260811-093914.md`，FAIL，2H/1M；
- MiM Native：`docs/reviews/code-review-20260811-093805.md`，正文 7L；其 summary
  把 non-findings 当作 open，且遗漏 untracked production scope，不能直接沿用计数。

## Controller dispositions

| Observation | Disposition | Closure |
| --- | --- | --- |
| Terra 1：import 专用参数绕过显式模式 | ACCEPTED / FIXED | `_ImportSemanticStore` 记录 presence/repetition；无主开关或主开关重复均在普通 init 的 mkdir/reset/copy/lock 等副作用前拒绝；参数矩阵已回归。 |
| Terra 2：closure 校验后仍按路径重读 | ACCEPTED / FIXED AFTER PLAN ERRATUM | S15-CTRL-15 已完成双路 plan acceptance；实现唯一 root capability、descriptor-first/member-second FD acquisition、neutral snapshot reader与四 owner optional透传；reader-mode普通 source-tree I/O=0，None golden保持。 |
| Terra 3：跨 company 重复 security 延后为 drift | ACCEPTED / FIXED | staging 在任何 DB dependency 前执行 global canonical security/bundle/repository locator uniqueness，冲突稳定拒绝。 |
| MiM 01：advisory key 截断碰撞 | REJECTED / ACCEPTED DESIGN / CLOSED | key 只用于串行化；碰撞只增加串行，不破坏事务正确性，计划已明确。 |
| MiM 02、04、05 | REJECTED / NON-FINDING / CLOSED | reviewer 正文已验证 FIFO/device、空 manifest 与 downgrade external dependency 行为符合合同。 |
| MiM 03：`object.__setattr__` | REJECTED / NON-DEFECT / CLOSED | 仅 frozen-dataclass 构造期窄豁免；没有 `object` 类型传播、cast/ignore 或宽边界。implementation artifact 不再表述为“完全没有 object 字样”。 |
| MiM 06：hidden directory | REJECTED / OPTIONAL HARDENING / CLOSED | hidden inventory 属 Fins owner既有契约，未证明本 Slice staging correctness defect。 |
| MiM 07：`or True` | ACCEPTED / FIXED | 移除弱断言；`bundle_sha256` 与 `hashlib.sha256(descriptor.read_bytes()).hexdigest()` 独立精确比较。 |

## Validation evidence

- Fix B/C/D focused：332 passed；受影响 unit：733 passed；
- PostgreSQL 16.14 Bookworm integration：47 passed；
- clean Python 3.11 non-integration（round1 exact clean env）：8108 passed /
  5 skipped / 81 deselected / 0 failed（round2 最终数字；round1 fix 快照 8102 +
  round2 新增 6 项 CLI import 测试）；
- changed/new production逐文件 coverage全部 `>=80%`，新增 leaf 94%，bundle 85%，
  core 89%，helpers 86%，workbook 90%，routing 84%，platform import 91%；
- changed pyright 0、Ruff 0；DAG/import smoke、reader=None golden、FD lifecycle、
  replacement/security spies、diff/whitelist/secret/raw/temp gates通过。

## Current gate

Controller accepted findings全部已实现，但本 adjudication 不自行关闭 code review gate。
Terra 与 MiM Native 必须针对当前最终树独立 re-review；只有两路 PASS/open H/M/L=`0/0/0`
后，才能进入 accepted commit。

## Round2 fix（Controller 裁决，2026-08-11）

Terra 复审 `code-review-20260811-111012.md` 提出唯一 finding（1-中）：主开关
``--import-existing-workspace`` 仍为 ``store_true``，重复出现被静默折叠，重复主开关 +
合法 manifest/tenant 会继续执行 staging。Controller ACCEPT 并完成最小修复：

- 主开关改用与 ``--import-manifest``/``--target-tenant-id`` 同类的计数/typed action
  （``_ImportSemanticStore`` 支持 ``nargs=0`` 无值开关），解析期保留
  ``import_existing_workspace_seen`` 与 ``import_existing_workspace_repeated``；
- ``run_init_command`` 与 ``_run_import_existing_workspace`` 在任何
  ``Path.resolve()``/staging/prepare deps 前严格要求 ``seen==1`` 且
  ``not repeated``（无缺字段 fallback、不放宽合同）；
- 重复主开关 + 合法 manifest/tenant 返回 ``workspace_import_usage``/1，
  ``stage_workspace_import`` 与 ``prepare_workspace_import_dependencies`` 调用均为 0；
  普通无主参数 init 行为不回归；
- 白名单（round2）：``dayu/cli/arg_parsing.py``、``dayu/cli/commands/init.py``、
  ``tests/cli/test_workspace_migrations.py``、既有 WIP
  ``tests/integration/investment/test_workspace_migration.py``（仅手工 Namespace 补
  ``import_existing_workspace_seen=1``、``import_existing_workspace_repeated=False``，
  Controller 批准）+ 本批 review/fix artifacts。

MiM Native 复审 `code-review-20260811-111313.md` PASS，三条 observation（POSIX-only FD、
bundle_key 去重测试、DB connect count 断言）均为非 finding，不扩修。round2 不重跑
PG16（无 DB 路径改变，复用 47 passed，已在 round2 fix artifact 说明）。

## Round3 fix（Controller 裁决，2026-08-11，deepseek-flash）

Terra 复审 `code-review-20260811-114214.md` 提出唯一 finding（1-未修复-低）：新代码
违反 AGENTS 禁止 `object`/`Any`。Controller 裁决：不清理历史 object，新增 delta 严格
为 0，最小 patch 不扩面。round3 已完成：

- `_ImportSemanticStore`（default/values/value 为 `object`）拆为
  `_ImportSemanticFlag`（`values: Sequence[str] | None`）与 `_ImportSemanticValue`
  （`values: str | Sequence[str] | None`，非 str 一律 `argparse.ArgumentError`
  fail closed），共享计数逻辑抽为模块级 `_record_import_semantic_occurrence`；
- leaf 定义递归 `JsonValue` 别名，`parse_json_object` 改为
  `validate_json_object_text(text: str) -> str`（`parse_float` 拒绝 `1e400`
  溢出 + `parse_constant` 拒绝 NaN/Infinity/-Infinity + 顶层 object 强制）；
  三个 reader 分支对同一 immutable text 先 validate 再走历史 owner 的
  `json.loads`，历史 `dict[str, object]` 契约不改、无 TOCTOU；
- delta 扫描消除 `_enumerate_closure_reference_paths(payload: dict[str, object])`
  （新签名收敛为 `Mapping[str, JsonValue]`），新增生产签名 object/Any = 0；
- 新增 12 个 parser/JSON adversarial 测试；focused 357、related 376、
  cli+investment+application+fins 4601 全过；changed pyright 0、Ruff 0 新增；
  changed production coverage 全部 >=80%；`git diff --check` 干净。
- 完整证据见
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round3-20260811-deepseek-flash.md`。

## Final dual re-review closure

- Terra：`docs/reviews/code-review-20260811-121322.md`，PASS，open
  H/M/L=`0/0/0`；独立复核 round3 类型边界、严格 JSON、重复参数双 gate、
  B/C/D 与 AST signature delta，并运行 focused 357、pyright 0、Ruff/diff-check。
- MiM Native：`docs/reviews/code-review-20260811-121507-slice-1.5-final.md`，
  PASS，open H/M/L=`0/0/0`；独立运行 focused 357、broader 4601、pyright 0、
  Ruff/diff-check，并确认 round3 与 B/C/D 无回归。
- Controller closure：Terra 093914/111012/114214 的 2H/1M、1M、1L 与
  MiM 093805 中唯一接受的测试 finding 全部 FIXED/CLOSED；其余 observations
  保持既有 non-finding/accepted-design 裁决。当前 open H/M/L=`0/0/0`，
  无 deferred code finding，可进入 accepted commit。
