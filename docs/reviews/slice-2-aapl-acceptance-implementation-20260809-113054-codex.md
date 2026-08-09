# Slice 2 AAPL Acceptance Implementation

- 时间：2026-08-09 15:30 CST
- 当前基线：`1c7e16160b23704558508e9c25522a116d67ad84`
- Accepted plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Source reviews：`code-review-20260809-114000-deepseek.md`、`code-review-20260809-114001-mimo.md`
- Final replacement reviews：`code-review-20260809-150002-codex.md`、`code-review-20260809-150003-terra.md`（外部 DeepSeek/MiMo lanes 因 402 未形成结论）
- Corrective round 2 reviews：Codex `code-review-20260809-151500-codex.md` 为 FAIL（CR-1/2/3），Terra `code-review-20260809-151501-terra.md` 为 PASS；Controller 接受三项窄实现缺口并已修复。
- Round 3 reviews：Codex `code-review-20260809-152500-codex.md` 为 FAIL（R3-1 Medium），Terra `code-review-20260809-152501-terra.md` 为 PASS；Controller 接受共享 lifecycle 缺口并已修复。
- Final dual re-reviews：`code-review-20260809-153500-codex.md`、`code-review-20260809-153501-terra.md` 均 PASS，open H/M/L=`0/0/0`。
- Plan-fix closure：`plan-fix-20260809-121500-codex.md`、`plan-fix-20260809-124500-codex.md`、`plan-fix-20260809-131500-codex.md`、`plan-review-20260809-133000-deepseek.md`、`plan-review-20260809-133001-mimo.md`
- 状态：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- Live 状态：**NOT AUTHORIZED / NOT RUN**

## Scope 与边界

本 Slice 的 production/test diff 严格限于 accepted plan 六文件：

1. `utils/investment_agent_acceptance_contracts.py`
2. `utils/investment_agent_acceptance.py`
3. `utils/investment_agent_acceptance_evaluator.py`
4. `tests/test_investment_agent_acceptance.py`
5. `dayu/fins/cli_formatters.py`
6. `tests/fins/test_cli_formatters_coverage.py`

另更新本 implementation artifact，并新增 Controller adjudication/fix artifacts。没有修改 fixtures、README、tests/README 或 accepted plan；没有执行 live、SEC、Web、DeepSeek、MiMo、付费模型或其它外部调用；没有 commit、push、创建 PR、启动 re-review 或进入 Slice 3。

`dayu/fins/cli_formatters.py` 的 production diff 精确为一个可执行行：download formatter 在 ticker 后、summary 前输出唯一 `- status: <status>`。没有新增或依赖 `dayu.cli --json`；owner ingress 仍是 plan 锁定的 `--quiet` 人读 formatter。`prepare/run/verify --json` 仅属于 acceptance CLI 自身。

## Contract 与真源

- `AcceptancePlan` 保持唯一 schema v2 与唯一 fingerprint：canonical contained run root、有序 frozen phase specs、`ModelRoles`、price/material identity、package config/assets fingerprints、静态 subprocess env policy、三项环境名称/presence、预算与 wall identity 都由同一 strict contract 持有。
- `PhaseReceipt` fresh 升为 schema v3。每个 phase 保存实际执行前缀的 strict `CommandRecord`；每条记录闭合 index、safe argv、argv digest、开始/结束/耗时、exit/status/termination、stdout/stderr SHA、单一有界静态脱敏 summary 与 discriminated owner evidence。v1/v2、unknown/missing、NaN/Infinity、bool-as-int、非法 discriminator、失败后续 record、聚合与末条不一致均 fail closed。
- download/import/process evidence 分别由 frozen discriminated schema 表达。download discovery receipt 是 live latest discovery 唯一真源，不从待校验 inventory 反推；material action 与 owner status 正交；process 行内只信 document ID，quality/processed 状态只信窄 `ProcessedDocumentRepositoryProtocol`。
- evaluator 是 live contract、null rubric、score threshold、hard-gate 与 deterministic evaluator 的唯一规则真源；CLI 只负责 strict ingress、preflight、固定 allowlist 编排、receipt 与 artifact 写入。

## Prepare / Run / Verify

### Prepare

- 完全离线校验固定 AAPL / Apple Inc. / technology、UTC as-of、显式预算/wall、六字段价格与 max-age、resolver package config/assets/model pricing、Git identity、env-name presence。
- pure `build_phase_specs` 固定三 downloads → price upload `MATERIAL_OTHER` → process → write preflight → paid write/materialize → 五 validators；terminal verify 在 plan fingerprint 后派生，不参与 fingerprint 自引用。
- 同父目录专属 staging 构建 canonical inputs、data-workspace、quality skeleton、argv/plan，再原子 rename；失败只清理本次 staging，不发布正式 run root。

### Run

- 首个 `Popen` 前重验 plan/fingerprint、canonical builder equality、HEAD/dirty、run root、package fingerprints、price JSON/Markdown/material identity、预算、env presence 与 exact subprocess env policy。任一 drift 在子进程前停止。
- 所有进程使用 argv tuple、`shell=False`、repository cwd、`stdin=DEVNULL`、stdout/stderr bytes pipes 与 plan 精确 env；whole-run remaining timeout 不按 phase 重置。
- 每条 command 返回后先解析 strict owner evidence，再写 record，随后才允许下一条。exit-0 `cancelled`、failed summary、结构缺失/重复/乱序、empty form、material delete/unknown、process TODO/failed 等都 semantic stop。
- timeout 使用 `terminate → 10s → kill → 10s`；等待/OSError 均可收口为 `termination_unconfirmed`。首命令或 terminal 前预算耗尽记录 `timeout/not_started/partial_by_timeout=true`。不 cleanup、不 resume。
- source discovery 与 repository closure、stable price material ID/primary SHA、process result/processed meta 都严格闭合；fresh run 出现额外/malformed filing fail closed。

### Verify

- deterministic `--fixture` 与 live `--plan + --fingerprint` 两模式严格互斥；fixture 强制 deterministic/offline，live 强制 non-deterministic/external/live-freshness，fixture ID 与 live ID 有意不要求相等。
- receipt discovery 与 repository latest accession 闭合；inventory 只走三个 repository Protocol，不扫描 workspace/portfolio。严格 round-trip 后原子写 canonical `source-inventory.json`，相同内容幂等，不同内容/symlink 拒绝。
- fixture 使用 repository-private owner runtime root、atomic lock 与 stale 诊断；cleanup 有主异常时附 note，无主异常时 fail loud，不盲 suppress。
- terminal `verify.json` 只由 run 写；独立 verify 不修改 phase receipts。固定 clock 下相同 deterministic 输入得到 byte-identical acceptance receipt。

Slice 1 deferred DS2/MiMo2 已由 v3 lifecycle、actual prefix、exit/status/termination/plan fingerprint closure 收口；DS3 已由两种 parser/policy lane fail-closed 收口。Slice 3 的 partial receipt/evaluator integration owner 保留不变。

## Final replacement review fixes

- H1：repository source ingress 按 source kind 分离日期真源；filing 严格要求 `filing_date`，material 严格要求 `report_date`，不做污染 filing 的全局 fallback。parsed evidence 后的 repository/semantic `ContractError` 被收敛成 truthful failed record/receipt，保留 streams、evidence 与 digests。
- H2：canonical receipt reload 新增纯 phase/domain validator。download evidence 精确绑定对应 raw argv forms/canonical forms/start/end 并重放 owner status、summary、usable/required discovery 与 row window；material/process 重放纯 semantic gate 与当前 repository closure；write/preflight/validators/terminal evidence 必须 null。该路径不写 source inventory。
- H3：stream fragment 在截断/落盘前经过不读取环境值的静态 sanitizer，覆盖 Authorization/Proxy-Authorization、Cookie/Set-Cookie、X-API-Key、常见 key/token/secret/password assignment、`sk-`/`AIza` 与 POSIX/Windows home/provider path；CLI error 使用同一规则。
- M1：`TimeoutExpired` partial stdout/stderr 被保留；terminate/kill 后用 bounded cumulative `communicate` drain，最终 complete bytes 优先而不与 partial 重复拼接，unconfirmed 保留最后可取得 partial。
- M2：Popen start 后从同一 monotonic deadline 重算 child timeout；persisted first terminal receipt 被 loader 返回并纳入 original run actual wall、runtime phase receipts 与 acceptance-owned outputs，独立 verify 当前时间不重复计入原始 wall。
- L1：CLI 直接复用/export contracts 唯一 `GIT_OBJECT_ID_PATTERN`，保持 40/64 位小写行为。

### Corrective review round 2

- CR-1：pre-persistence 静态 field sanitizer 与 evaluator 敏感形状同等闭合；统一处理冒号/等号、可选空白、大小写、连字符/下划线的 authorization/proxy authorization/cookie/set-cookie/API key/access token/token/secret/password assignments。参数化覆盖 stderr、prefix、structure reject 与 CLI。
- CR-2：persisted terminal 存在时显式要求 phase passed、精确一条 passed record、exit 0、无 stop/termination/partial 且 evidence null；failed/signal/timeout canonical terminal 全部阻止独立 verify/no-resume。
- CR-3：material persisted evidence 的 `price_json_sha256`、`price_material_sha256` 分别精确绑定 plan `price_snapshot_sha256`、`price_material_sha256`；两字段独立 canonical tamper 均拒绝。

### Round 3 shared stream lifecycle

- R3-1：共享 `CommandRecord` contract 只允许明确 `process_start_failed` 与 `timeout/not_started` records 使用 stdout/stderr SHA 双 null；其它 passed/failed/timeout/signal 已启动 records 必须两项均为小写 SHA-256，即使空流也使用空字节 digest。start-failure 若伪造 stream SHA 同样拒绝。

## Tests 与 adversarial evidence

Focused 共 195 tests，覆盖：

- v3 三类 evidence strict round-trip、v1/v2/unknown/missing/NaN/schema mutation、safe argv 独立 token 与 `--flag=/abs`；
- 真实 formatter download ok/cancelled status 唯一且顺序精确；download/upload/process title anchor、prefix、可信结构、opaque tail、duplicate/reorder/missing/empty form；
- download 三命令 evidence 前缀、usable discovery/repository closure、all skipped/failed/duplicate/malformed filing；
- upload full/sparse grammar × ok/skipped × create/update，以及 delete/unknown、files header/optional row 错序；
- process 六节、opaque quality、TODO/cancelled、repository quality/status/reprocess truth；
- 12 planned command + terminal failure prefix、exit-0 semantic stop、首/terminal not-started timeout、terminate/kill/OSError；
- source inventory atomic create/idempotent/drift/symlink、repo-private stale lock、cleanup primary exception note；
- actual child process 对 repository cwd、DEVNULL stdin、exact env policy 的端到端证明；
- acceptance CLI 三模式 `--json`、unexpected exception 静态脱敏、deterministic receipt stability。
- final replacement review adversarial：material-only report date、repository ContractError failed receipt、process-null/cross-type/cancelled/failed/wrong-window/wrong-forms/non-domain canonical tamper、material/process current repository drift、三种 timeout partial streams、三类 stream-summary 与 CLI 静态脱敏、slow Popen start、persisted terminal wall、Git 40/64 single truth。
- corrective round 2 adversarial：三种 evaluator-equivalent 等号/连字符 secret shapes × 四个输出入口、failed/signal/timeout terminal no-resume、两项 material plan SHA 独立 tamper。
- round 3 adversarial：passed terminal/write/validations records 的双 null、单 stdout null、单 stderr null 共九个 canonical tamper，以及合法 process-start-failure 双 null strict round-trip。

## Validation evidence

| Gate | 精确结果 |
|---|---|
| focused | `195 passed`，exit 0 |
| exact coverage | CLI `82%`、contracts `87%`、evaluator `87%`、total `84.61%`；`--cov-fail-under=80`，195 passed |
| exact typing | 六个 production/test allowlist 文件：`0 errors, 0 warnings, 0 informations` |
| Ruff default | 六文件 `All checks passed` |
| Ruff F/I | 新 utils + tests 全通过；formatter F 通过，I001 与 HEAD 同文件 baseline 完全相同 |
| production key full-rule | 新 utils 三文件 `C416,C901,E501,FBT,PERF401,PLR0912,PLR0913,PLR0915,PLR2004,RUF022,TC001`：0 findings |
| formatter full-rule delta | 当前与 HEAD code multiset 均为 C901×2、E501×5、I001×1、PERF401×4、PLR0912×2、PLR2004×1；无新增 code/delta |
| owner research-template | `128 passed, 88 deselected` |
| owner source/write | `54 passed` |
| deterministic CLI | fixture verify verdict `PASS`，exit 0；canonical JSON stdout，无 stderr |
| whitespace | `git diff --check` exit 0 |
| whitelist | 仅六个允许 production/test 路径和三个本 Slice review artifacts |

## 职责与复杂度审计

新 CLI 虽长，但职责仍限于 Slice 2 strict ingress/preflight/fixed runner/receipt/verify composition，没有形成通用命令框架。AST 最大函数为 `build_phase_specs` 195 行：它是 13 个固定 argv 与顺序的唯一 canonical pure builder，拆成多个 public builder 会制造 allowlist/order 双真源。其后 `_execute_phase` 133 行只闭合 phase 内实际 command prefix，`prepare_acceptance` 112 行只负责 atomic staging，`_evaluate_live_plan` 105 行只组装严格 owner ingress 后调用 evaluator，`_execute_command` 97 行只负责单进程 lifecycle。

解析职责已按真实 grammar 边界拆为 download/material/process 小 helper；execution 参数以两个窄 frozen facts（command identity、timing）承载，未新增 wrapper seam、`Any`/`object`/`cast`/ignore/getattr/hasattr 逃逸。新 utils 三文件 key complexity/argument-count/full-rule findings 为 0，因此不需要越过白名单继续拆模块。

## Docs decision 与 residual ownership

- Slice 4 owner：operator runbook、README/tests README、fixture/live 隔离说明；本 Slice 不提前修改。
- Slice 3 owner：partial/nonzero receipts 与失败产物的 evaluator integration，以及 accepted run artifact/baseline 联调。
- Slice 5 owner：真实 SEC/provider/model/price/live budget 授权与 execution；当前 **NOT AUTHORIZED / NOT RUN**。
- owner human formatter 是刻意的 fail-closed availability boundary：文案变更必须重新 plan，不允许宽 regex、inventory fallback 或发明 dayu JSON mode。
- timeout `termination_unconfirmed`、stale runtime state、unknown temp/receipt 都交 operator 审计，不自动 resume/忽略。

## Handoff

## Final dual re-review closure

Codex `153500` 与 Terra `153501` 对同一 frozen tree 均为 **PASS**，open High/Medium/Low 均为 **0/0/0**。R3-1、CR-1/CR-2/CR-3，以及原 Codex `150002`、Terra `150003`、Codex `151500`、Terra `151501`、Codex `152500`、Terra `152501` 中全部 accepted findings 均为 **CLOSED**。外部 DeepSeek/MiMo lanes 因 402 未形成结论的事实保持不变，不改写为 PASS。

**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。实现与 Controller-adjudicated findings 已落盘并通过 deterministic gates；implementer 未 commit、push、开 PR、执行 live 或进入 Slice 3。
