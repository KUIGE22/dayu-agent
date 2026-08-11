# Slice 1.5 old-workspace explicit import — implementation artifact

- **Work unit**：Investment Platform Restoration
- **Gate**：Slice 1.5 implementation worker（accepted plan 35915fe；本 gate 不启动 review）
- **Branch**：`codex/investment-platform`
- **Baseline**：`58b7dd28db6183f29caaac337b09dffc3db80a76`
- **Slice 1.2 repository/provider accepted commit**：`bf6761b` / `b45e0ee`
- **Slice 1.4 S3 repository accepted commit**：`87e8fc6` / `58b7dd2`
- **Implementation worker**：deepseek-flash（Slice 1.5 主体）；codex（S15-CTRL-15 首轮 code-review fix，见 §7）
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- **日期**：2026-08-11
- **Round2 fix**（2026-08-11 1112 Terra 复审 finding）：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round2-20260811-codex.md`

## 1. 实现范围（与 accepted contract 对应）

按 `S15-CTRL-01..14` 与 plan acceptance 逐字实现：

- **S15-CTRL-03 白名单**：全部新增/修改见 §3；未触碰白名单外文件（卫生审计逐文件核对）。
- **S15-CTRL-04**：`dayu-cli init --import-existing-workspace` 独立最前分支，
  `--import-manifest` / `--target-tenant-id`（仅 default organization）、与
  `--reset` / `--overwrite` 互斥；七个稳定错误类别逐字落地；import mode 不执行
  普通 init 的 mkdir/reset/copy config/copy assets/legacy in-place
  migrations/provider prompt/API key persistence/prewarm，不获取 workspace
  advisory lock。
- **S15-CTRL-05**：strict operator manifest v1；HK/CN/US market consistency
  gate 逐字实现；manifest 与 owner ticker 各自先证明 canonical 后 exact；
  `legacy_company_id` raw byte-exact；`companies=[]` 仅空 inventory 合法。
- **S15-CTRL-06**：`dayu.investment.domain.workspace_import` 唯一 strict
  DTO/canonical/fingerprint owner，全部 frozen slots、集合构造期 tuple 化；
  七类稳定错误；UUIDv5（`NAMESPACE_URL` + 五个固定前缀）逐字实现；无
  `Any/object/cast/ignore/getattr/hasattr` 与宽 dict 穿透；不接受
  caller-supplied UUID。
- **S15-CTRL-07**：`platform_import.stage_workspace_import` stage-before-connect；
  仅 import `dayu.fins.storage` public read-only repositories + bundle owner
  typed API；两 Fins 仓储 `create_directories=False`；manifest 与全部引用路径
  contained/regular/non-symlink；inventory 双向 exact-set；source definitions
  只由 storage root presence 派生；bundle typed closure cross-check；两个
  fingerprint canonical SHA-256。
- **S15-CTRL-08**：`0002_workspace_import` migration（`down_revision` 精确
  `0001_platform_foundation`），两表列/约束/FK/unique 逐字；RLS
  `ENABLE+FORCE` + 唯一 `tenant_isolation` policy；app 仅 `SELECT/INSERT`、
  audit `SELECT`、PUBLIC 全 revoke、default privileges 维持；locator 无冗余
  `company_id`；`repository_key='legacy-workspace'` closed enum；downgrade 先
  catalog 拒绝外部依赖（外部 view/rule 或其它表 FK）再按 locator→marker
  删除，无 CASCADE。
- **S15-CTRL-09**：`PostgresWorkspaceImportRepository.publish_import` 唯一 DB
  transaction owner（单 session、`SET LOCAL app.tenant_id`、schema probe、
  `pg_advisory_xact_lock`（sha256 前 8 字节 signed big-endian）、marker read、
  public reconcile、marker insert、locator inserts）；exact no-op / drift fail
  closed；commit/rollback 自动释放；返回 pure receipt。
- **S15-CTRL-10**：`WorkspaceImportService` 窄 Service（再次校验
  `DEFAULT_ORGANIZATION_ID`），稳定名 `workspace_import`，
  `PlatformWorkspaceImportServiceProtocol` 定义在纯 `composition`；
  `prepare_workspace_import_dependencies()` 只读 strict production
  settings/DSN、probe app role、构造一个 engine/session/repository/service 与
  幂等 close，不启动 Host/Fins/S3/Redis/auth/model，不注册进普通 Host runtime
  composition。
- **S15-CTRL-11**：状态仅 `unseen -> staged(in-memory) -> committed`。
- **S15-CTRL-12/13**：unit/CLI、repository unit、真实 PG16 integration、
  vertical CLI 全量补齐；逐文件 statement coverage ≥80%（见 §4.4 全表）；
  中文 docstring；`git diff --check` 干净；secret/path/raw-byte scanner 通过。

## 2. Pre-edit audit（零编辑停报检查）

- 工作树 clean，HEAD `4b9d626`；baseline `58b7dd2` 存在；baseline→HEAD 仅
  docs/plan/chore 变更；owner/protocol 事实与计划一致，无需停报。
- 关键 owner 事实核对：`FsCompanyMetaRepository` 缺 `create_directories`
  公开参数（白名单内最小补齐）；`FsSourceDocumentRepository` 已有该参数；
  `scan_company_meta_inventory` / `has_source_storage_root` 均为只读；bundle
  owner 无 typed closure API（白名单内新增）；`Principal(TenantId,
  str).to_scope()` 可直接构造 fixed default scope；`0001` 13 表/RLS/grants/
  downgrade 契约与 plan 一致。
- 未发现真实 plan gap；无需越白名单；真实 PG16 可验证（本机 pinned
  `postgres:16.14-bookworm` 镜像与 docker daemon 可用）。

## 3. 精确 diff（全部在白名单内）

新增 production（6）：

```
dayu/cli/workspace_migrations/platform_import.py
dayu/investment/domain/workspace_import.py
dayu/investment/storage/models_workspace_import.py
dayu/investment/storage/postgres_workspace_import.py
dayu/investment/storage/migrations/versions/0002_workspace_import.py
dayu/services/workspace_import.py
```

修改 production（10）：

```
dayu/cli/arg_parsing.py                                init parser 三个 import mode 参数
dayu/cli/commands/_research_template_bundle.py          typed closure API（DTO/Error/inspect）
dayu/cli/commands/init.py                              run_init_command 最前独立 import 分支
dayu/cli/workspace_migrations/__init__.py              docstring 澄清 platform_import 非 legacy runner
dayu/fins/storage/fs_company_meta_repository.py        对称暴露 create_directories 并透传
dayu/investment/composition.py                         PlatformWorkspaceImportServiceProtocol
dayu/investment/storage/__init__.py                    导出两个新 ORM 模型 + docstring
dayu/investment/storage/protocols.py                   WorkspaceImportRepositoryProtocol
dayu/investment/storage/migrations/versions/__init__.py  docstring 登记 0002
dayu/services/startup_preparation.py                   prepare_workspace_import_dependencies +
                                                        PreparedWorkspaceImportDependencies
```

新增 test（2）与修改 test（6）：

```
新增 tests/cli/test_workspace_migrations.py             domain/staging/CLI/parser（82 tests）
新增 tests/integration/investment/test_workspace_migration.py  PG16 repository/vertical（14 tests）
修改 tests/investment/test_platform_migrations.py       13→15 表 + 0002 专项契约
修改 tests/investment/test_architecture_boundaries.py  workspace_import 纯域边界专项
修改 tests/application/test_service_startup_preparation.py  prepare + 真实 service 测试
修改 tests/integration/investment/test_platform_migrations_postgres.py  15 表 catalog + 0002 循环/downgrade/权限
修改 tests/cli/test_research_template_command.py        bundle typed closure 7 tests
修改 tests/fins/test_storage_split_repositories.py      no-create 构造回归
```

docs（4 + artifact）：

```
README.md / dayu/README.md / dayu/investment/README.md / tests/README.md
docs/reviews/slice-1.5-workspace-import-implementation-20260811-deepseek-flash.md（本文档）
```

`dayu/cli/workspace_migrations/runner.py` 保持字节不变（S15-CTRL-04：platform
import 不挂入 legacy runner）。

## 4. 验证

### 4.1 测试（真实 corpus，全部通过）

受影响集成集（clean env，unset 全部 provider key）：**888 passed / 0 failed**。

- `tests/investment`（含 architecture guards / migrations unit / platform config）
- `tests/cli/test_workspace_migrations.py`（82：domain/staging/CLI/parser unit）
- `tests/cli/test_research_template_command.py`（223，含 closure 7 tests）
- `tests/fins/test_storage_split_repositories.py`（18，含 no-create 回归）
- `tests/application/test_service_startup_preparation.py`（31，含 prepare + 真实 service）
- `tests/cli/test_init_command.py` / `test_arg_parsing_redaction.py` / `workspace_migrations/`
- `tests/integration/investment/test_platform_migrations_postgres.py`（33，真实 PG16）
- `tests/integration/investment/test_workspace_migration.py`（14，真实 PG16）

**Python 3.11 full non-integration lane**
（`.venv/bin/python` 3.11.15，`pytest -q --timeout=60 -m "not integration and not slow
and not e2e"`，clean env unset 全部 provider key）：**8073 passed / 5 skipped /
81 deselected / 0 failed**。（worker gate 历史快照；当前树最终数字见 §7 与
round2 fix artifact：8108 passed / 0 failed。）

- 首次运行（未 unset）为 8072 passed / 1 failed：`tests/engine/test_web_tools.py::
  test_search_with_serper_requires_api_key` 因本机 shell 残留 `SERPER_API_KEY`，
  使"未配置应拒绝"的测试真实触网（proxy 不可达 → ProxyError）。根因与环境相关，
  与本 gate 改动无关；clean env（unset provider key）重跑该测试与全量 lane 全部
  通过。已在本文档如实记录。

真实 PG16 覆盖（`postgres:16.14-bookworm`）：fresh `upgrade head` 15 表 exact
catalog；`0001→0002→0001→0002` 循环（内部 rows downgrade 成功、外部 dependent
view 整次 rollback）；marker/locator 的 app SELECT/INSERT + UPDATE/DELETE 拒绝；
publish 后 rows exact；exact rerun no_op 时间不变；fingerprint/row/business-key
drift fail closed；advisory key 算法 exact（外部持锁阻塞）；两线程 race 恰一
imported 一 no_op；trigger fault（companies/source/locators/markers 各阶段）整次
rollback 零行；winner rollback 后 loser 完整发布；RLS unset/cross-tenant 不可见
不可写；locator 无冗余 company_id（app-role join 解析）；vertical
`dayu-cli init --import-existing-workspace`（真实 stage/Service/repository，独立
audit `SET ROLE` 回读 bundle_sha256==descriptor 实际 SHA-256，legacy tree
entry/type/size/mtime 前后完全一致）。

### 4.2 pyright（changed/new exact 0 + 全树独立证据）

- changed/new production+tests 逐文件 `0 errors`。
- 全树 `pyright dayu/ tests/` = 17 errors，全部位于**本 gate 未触碰文件**，逐文件
  独立核对：
  - `dayu/engine/processors/docling_processor.py`（2）
  - `tests/engine/test_docling_processor_helpers.py`（2）
  - `tests/engine/test_web_tools.py`（13）
- baseline 数值未复证：本 gate 明令禁止 git stash/checkout 等状态操作，无法重跑
  baseline 快照；上述"错误全部位于未触碰文件 + changed/new exact 0"是独立可直接
  验证的事实，证明本 gate 改动 0 新增错误。
- `_raise_repository_failure` 改为保留 `__cause__`（稳定消息仍只含 safe code）。

### 4.3 Ruff（changed/new full-rule 0 + 全树独立证据）

- changed/new production+tests `ruff check`（full rules）全部 `All checks passed!`。
- 全树 `ruff check dayu/` = 80 fixable，均位于本 gate 未触碰文件（改动文件
  full-rule 已 0）；baseline 数值未复证（原因同 §4.2），不构成对"改动 0 新增"
  的依赖。
- 本 gate 新增/修改文件额外验证 `--select E4,E7,E9,F,I` 亦通过。

### 4.4 Coverage（S15-CTRL-03 全部 modified/new production 逐文件 ≥80%）

测量方式：`COVERAGE_CORE=pytrace` + filesystem source 目录（`--cov=dayu/xxx`，
非 dotted module）+ 独立 mktemp `COVERAGE_FILE` + 已通过的真实 pytest corpus，
每次一个 source；本机 coverage C-tracer 下 `numpy` 导入失败为环境问题（普通
`pytest` 无 coverage 不受影响），已在 `tests/README.md` 登记。

| 文件（全部 modified/new production） | 覆盖 | 真实 corpus |
| --- | --- | --- |
| dayu/investment/domain/workspace_import.py | 88.7% | test_workspace_migrations + PG16 |
| dayu/cli/workspace_migrations/platform_import.py | 90.4% | test_workspace_migrations |
| dayu/investment/storage/postgres_workspace_import.py | 82.2% | PG16 integration |
| dayu/investment/storage/models_workspace_import.py | 100% | PG16 integration |
| dayu/investment/storage/protocols.py | 100% | PG16 integration |
| dayu/investment/composition.py | 100% | test_platform_config + workspace_migrations + PG16 |
| dayu/services/workspace_import.py | 100% | startup 单测 + vertical CLI |
| dayu/services/startup_preparation.py | 81.7% | startup 单测 + vertical CLI |
| dayu/fins/storage/fs_company_meta_repository.py | 100% | storage_split + workspace_migrations |
| dayu/cli/commands/_research_template_bundle.py | 83.2% | test_research_template_command |
| dayu/cli/commands/init.py | 94.1% | test_init_command + workspace_migrations |
| dayu/cli/arg_parsing.py | 100% | test_init_command + arg_parsing_redaction + workspace_migrations（含 parser 矩阵） |
| dayu/cli/workspace_migrations/__init__.py | 100% | CLI 测试集 |
| dayu/investment/storage/__init__.py | 100% | investment + PG16 |
| dayu/investment/storage/migrations/versions/0002_workspace_import.py | 98.4% | PG16 migrations + unit |
| dayu/investment/storage/migrations/versions/__init__.py | 100%（无语句） | — |

注：arg_parsing.py 首测仅 7.6%（现有 corpus 未调用 `parse_arguments()`）；按
S15-CTRL-12 的 parser mode 矩阵要求补齐
`TestCliParserImportMode`（`tests/cli/test_workspace_migrations.py`）后，真实
corpus 触发完整 parser 注册，实测 100%。

### 4.5 import smoke / architecture / diff-check / secret / raw-byte / temp

- import smoke：14 个新增/修改模块全部可导入。
- architecture/import-direction/docstring/forbidden-type guard：
  `tests/investment/test_architecture_boundaries.py` 151 passed（含 workspace_import
  纯域边界专项）。
- `git diff --check`：干净。
- whitelist：`git status` 变更集合逐文件 ⊆ S15-CTRL-03 allowlist + 本文档 artifact，
  无越界。
- secret/path scanner：新增/修改代码无 DSN、password、api key 明文；唯一命中为
  既有 S3 `credentials.secret_key` 构造行（非本 slice 新增）。
- raw-byte：vertical 与 tree-manifest 测试证明 legacy source tree
  entry/type/size/mtime 完全不变；staging 不枚举/读取/hash/复制任何
  source/processed document。
- temp cleanup：本 slice 产生的 `/tmp/cov.*`、`/tmp/covjson.*`、`/tmp/.cov_*`、
  `/tmp/ws_fixture`、`/tmp/hk_fixture`、`/tmp/empty_fixture`、
  `/tmp/out_manifest.json`、`/tmp/pyright_*.txt`、`/tmp/ruff_*.txt` 均已删除；
  `git stash list` 为空；无其它本 slice 遗留。

### 4.6 已知环境限制（不影响行为断言）

- `tests/integration/investment/test_identity_repositories_postgres.py::
  TestProductionStartupBlackBox` 3 个测试在 baseline 与当前 alike 失败
  （`DAYU_PLATFORM_OBJECT_STORAGE` 需合法 JSON，本机 env 未提供），与本 slice
  无关；其失败会泄漏 cluster 级 group role 导致整目录合跑级联失败，本 slice
  验证按文件单独运行。该文件不在白名单，未修改。
- 本机 shell 残留 provider key（`SERPER_API_KEY` 等）会使"未配置应拒绝"类既有
  测试触网；clean env 下全量 lane 通过（见 §4.1）。
- coverage C-tracer + numpy 环境限制（见 §4.4）。

## 5. Residual / 未覆盖项

- 按 S15-CTRL-14：multi-listing mapping 与 non-default tenant/authenticated
  actor 归 Slice 7.1；source subscriptions 归 Slice 2.3；legacy-root 运行时
  resolver 与旧资料移动/删除归两个独立 future migration work unit；locator 表
  只登记 `repository_key + relative_locator + hashes`；`repository_key` closed
  enum 有意要求 future schema migration（未放宽 CHECK）。
- 未声称已有 auth、multi-tenant import、resume、scheduler、automatic migration
  或删除旧 workspace。
- 未 commit/push/PR（本 gate 只产出工作树变更与本文档）。

## 6. 实施过程纪律记录（如实）

- 全程未读取/复制 Host/Fins 原始 bytes；未猜 MIC/currency/type（US 只形状
  验证）；未放宽 tenant；未发明兼容 glue 或第二事务真源；未修改白名单外
  owner；未运行 live/network/model/broker；未 commit/push/PR。
- **一次性纪律偏差（已纠正、无残留）**：实现早期曾用 Python
  `open(path, "w")` / shell `cat >>` / heredoc 追加/改写测试文件，并在 `/tmp`
  创建调试脚本 `/tmp/debug_depend.py`。Controller 两次纠正后已全部停止，改用
  Edit/Write 工具完成后续所有文件修改；`/tmp/debug_depend.py` 已删除；受影响的
  测试文件内容已逐文件审阅并通过 pyright/ruff/测试验证，无残留问题。
- **baseline 对比偏差说明**：早期曾两次用 `git stash`/`git stash -u` 做 baseline
  ratchet 对比（均已 pop 恢复、`git stash list` 为空）；收到禁止后未再使用。
  本文档的 baseline 表述已改为独立证据（§4.2/§4.3），不以 stash 作为合规证据。
- 发布顺序修正说明：`_publish_new` 中 locator 的复合 FK
  `(tenant_id, import_marker_id)` 要求 marker 先存在，实际 DML 顺序为 public
  reconcile → source reconcile → marker insert → locator inserts（与 plan 的
  transaction 阶段描述一致，符合其精确 schema）。

## 7. Code-review fix applied（S15-CTRL-15 两阶段 secure snapshot reader）

在首轮 code review（Terra 2H/1M、MiM 0H/0M/7L）与计划勘误双路
PASS/open0（`plan-acceptance-20260811-slice-1.5-secure-closure-reader-codex.md`）
之后，本 artifact 进入 REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW：

- **A（Terra 1，已完成）**：`_ImportSemanticStore` + `_import_semantic_args_present`
  保留；无主开关携带 import 语义参数（含重复）在普通 init 副作用前拒绝。
- **B（Terra 2 + S15-CTRL-15，本轮完成）**：新增 neutral private leaf
  `dayu/cli/_research_artifact_content.py`（Protocol + 纯 bytes helper，stdlib
  依赖，不 import 任何 owner）；四个 owner
  （`_research_template_core/_research_template_helpers/research_workbook/
  research_template_routing`）增加 keyword-only optional `content_reader=None`
  透传，None 保持既有行为；bundle owner 的
  `inspect_research_template_bundle_closure` 改为 S15-CTRL-15 两阶段 FD
  acquisition：filesystem-root 逐段 no-follow 绑定唯一 root capability →
  descriptor 逐段 preflight identity→no-follow open→fstat exact 只读一次 →
  纯词法枚举 canonical member → 全部 member FD 绑定后才读 bytes → 快照
  reader（零 filesystem I/O）供 validator 消费。ExitStack 在
  success/exception/BaseException 全 FD exact close。
- **C（Terra 3，本轮完成）**：`stage_workspace_import` 在 owner identity
  cross-check 后、任何 DB 依赖前执行 `_require_global_identity_uniqueness`，
  跨 company 重复 canonical security / bundle identity / repository locator
  一律 `workspace_import_identity_inconsistent`。
- **D（MiM 07，本轮完成）**：移除 `or True` 空断言，`bundle_sha256` 直接
  等于 descriptor bytes 独立 SHA-256；PG16 vertical 已有同款独立断言。
- 验证：Fix B/C/D 相关 332 项 unit（含 20 个 S15-CTRL-15 adversarial +
  3 个 Fix C staging）全过；受影响 unit corpus 733 passed；真实 PG16
  integration 47 passed；clean-env Python 3.11 full non-integration
  8108 passed / 5 skipped / 81 deselected / 0 failed（round2 最终数字；
  round1 fix 快照为 8102，round2 新增 6 项 CLI import 测试后为 8108）；changed/new
  production 逐文件 coverage 全部
  >=80%（leaf 94%、bundle 85%、core 89%、helpers 86%、workbook 90%、
  routing 84%、platform_import 91%）；changed pyright 0、Ruff 0；
  `git diff --check` 干净；whitelist ⊆ allowlist；secret/raw/temp 干净。
- 本 artifact 不关闭既有 code findings；等待 Terra 与 MiM Native 双路
  code re-review open 0。

## 8. Code-review fix round3 applied（deepseek-flash，2026-08-11）

Terra 复审 `code-review-20260811-114214.md` 提出唯一 finding（1-未修复-低）：新代码
违反 AGENTS 禁止 `object`/`Any`。Controller 裁决：不清理历史 object，新增 delta
严格为 0，最小 patch 不扩面。round3 已完成并保持
REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW：

- **A（`_ImportSemanticStore` 的 `object`）**：拆为 `_ImportSemanticFlag`
  （`values: Sequence[str] | None`，无值开关首现写 `True`）与
  `_ImportSemanticValue`（`values: str | Sequence[str] | None`，非 str 一律
  `argparse.ArgumentError` fail closed）；共享计数逻辑抽为模块级
  `_record_import_semantic_occurrence`；注册与解析语义字节等价。无
  cast/ignore/Any/object。
- **B（`parse_json_object` 的 `dict[str, object]`）**：leaf 定义递归 `JsonValue`
  别名，函数改为 `validate_json_object_text(text: str) -> str`（`parse_float`
  拒绝 `1e400` 溢出 + `parse_constant` 拒绝 NaN/Infinity/-Infinity + 顶层 object
  强制，通过后原样返回同一 text）；helpers/workbook `_load_json_object` 与 bundle
  closure 的 reader 分支先 validate 再对同一 immutable text 走历史 owner 的
  `json.loads`，历史 `dict[str, object]` 契约不改、无 TOCTOU。
- **delta 扫描**：相对 baseline 新增生产签名 object/Any = 0；
  `_enumerate_closure_reference_paths`（新签名）参数收敛为
  `Mapping[str, JsonValue]`；diff 中其余 `dict[str, object]` 均为 baseline 既有
  签名重排（逐处核对 `-` 行同型）。
- 验证：focused 357（新增 12 个 parser/JSON adversarial）、related 376、
  cli+investment+application+fins 4601 passed / 0 failed；changed pyright 0、
  Ruff 默认 0 新增（`--select F,I` 仅剩 round2 已登记的既有 I001）；changed
  production coverage 全部 >=80%（leaf 100%）；`git diff --check` 干净。
- 完整证据见
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round3-20260811-deepseek-flash.md`。
- 最终独立复审已闭合：Terra
  `docs/reviews/code-review-20260811-121322.md` 与 MiM Native
  `docs/reviews/code-review-20260811-121507-slice-1.5-final.md` 均为
  PASS、open H/M/L=`0/0/0`。Round1/round2/round3 findings 全部 CLOSED，
  本实现可进入 accepted commit；PG16/Docker/live/network/model/broker 未在
  round3 重跑或调用，既有 47 passed PG16 证据按限定范围复用。
