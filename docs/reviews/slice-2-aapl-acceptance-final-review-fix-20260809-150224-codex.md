# Slice 2 AAPL Acceptance Final Review Fix

- 时间：2026-08-09 15:02 CST
- 基线：`1c7e16160b23704558508e9c25522a116d67ad84`
- Replacement reviews：`code-review-20260809-150002-codex.md`、`code-review-20260809-150003-terra.md`
- External lanes：DeepSeek/MiMo 因 402 未形成结论
- Controller decision：H1/H2/H3/M1/M2/L1 **ACCEPTED**
- 状态：**CLOSED / DUAL RE-REVIEW PASS**
- Live 状态：**NOT AUTHORIZED / NOT RUN**

## Accepted findings closure

### H1 — material date 与 truthful repository failure

- evaluator owner ingress 对 filing 严格要求 `filing_date`，只允许其可选 `report_date` 回退到 filing date；对 material 严格要求 `report_date` 并以该值满足 frozen source contract，不读取/回退 material `filing_date`。
- canonical upload argv 保持 accepted plan 的唯一 `--report-date`，没有修改 argv/fingerprint。
- phase runner 在 evidence 已解析后捕获 repository/strict semantic `ContractError`，生成 `status=failed`、`exit_code=0`、`stop_reason=owner_semantic_contract_reject` record；保留 evidence、stdout/stderr SHA/summary、safe argv/digest，随后原子写 phase receipt 并停止。

### H2 — persisted phase/domain evidence authenticity

- loader 在 strict schema、canonical bytes、argv digest 后调用纯 phase-aware/domain-aware validator；不调用 source inventory writer。
- download passed record 必须为 `DownloadCommandEvidence`，且 ticker、planned/canonical forms、start/end 与对应 raw argv 精确相等；共享 semantic gate 重放 owner status、failed summary、usable/required discovery、row canonical form 与 start/end window。
- material/process passed records分别要求对应 evidence；material 重放 raw report-date、plan SHA/ID、owner semantic 与当前 repository meta/primary closure；process 重放 status/summary/TODO/rows 与当前 processed repository closure。
- write-preflight/write/validations/terminal records 强制 evidence null。
- canonical tamper tests 覆盖 process null、cross type、cancelled、failed summary、wrong window、wrong forms、non-domain evidence；全部 fail closed，且 loader 不生成 `source-inventory.json`。

### H3 — pre-persistence static sanitizer

- `_stream_summary` 在 fragment 截断与 receipt serialization 前使用静态 sanitizer，不读取或枚举 `os.environ` values。
- 覆盖 Authorization、Proxy-Authorization、Cookie、Set-Cookie、X-API-Key、常见 `*_API_KEY`/`*_TOKEN`/`*_SECRET`/`PASSWORD` assignment、`sk-`、`AIza`、POSIX/Windows home/provider path。
- stderr、owner prefix noise、structure reject 与 CLI error 共用静态规则；canonical receipts/CLI output 不含原值，同时保留 category 与 line 诊断。

### M1 — timeout partial/cumulative streams

- 捕获首次 `TimeoutExpired.output/stderr`；terminate/kill 后分别使用固定 grace 的 bounded `communicate` drain。
- 按 Python Popen cumulative retry 语义，非空 final complete 替代 partial；绝不拼接造成 digest 重复。若 drain/termination 无法确认，则保留最后可取得 partial bytes。
- terminate、kill、termination_unconfirmed 三路测试精确断言 stdout/stderr SHA 与 sanitized summary。

### M2 — terminal runtime 与 Popen deadline

- terminal validator 返回可选 persisted first `verify.json`；存在时纳入 evaluator `phase_receipts`、`acceptance_owned_outputs` 与首 phase → terminal end 的 actual wall。
- 独立 verify 当前 clock 只用于新的 acceptance evaluation time，不进入 original run wall。
- `_execute_command` 在 start 前固定 monotonic deadline，Popen 返回后重算 remaining；slow-start test 证明 29 秒启动只给 child 剩余 1 秒，而非原 30 秒。

### L1 — Git object-id single truth

- contracts 导出唯一 `GIT_OBJECT_ID_PATTERN`；CLI `GitRepositoryStateProvider` 直接复用，不保留本地 regex。
- tests 锁定 40/64 位小写接受，uppercase/39/65 拒绝，并断言 CLI/contract pattern 是同一对象。

## Validation

| Gate | Result |
|---|---|
| focused | 168 passed |
| exact coverage | CLI 82%、contracts 86%、evaluator 87%、total 84.44% |
| six-file exact pyright | 0 errors / 0 warnings / 0 informations |
| Ruff default | pass |
| Ruff F/I | new utils/tests pass；formatter F pass，I001 保持 HEAD baseline |
| key full-rule | new utils 0 findings |
| owner research-template | 128 passed / 88 deselected |
| owner source/write | 54 passed |

## Scope / handoff

Production/test diff 仍精确限于 accepted 六文件；formatter production diff 仍精确一行 status。没有修改 plan、README、fixtures 或其它 production/tests；没有 live/network/SEC/model/paid 调用；没有 commit、push、PR、review 或 Slice 3。

历史状态：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Corrective round 2 follow-up

后续 Codex `151500` 发现 CR-1/CR-2/CR-3，Terra `151501` 为 PASS。Controller 接受三项并已在同一 Slice 2 scope 修复；本 artifact 的验证统计由 corrective artifact `slice-2-aapl-acceptance-corrective-review-fix-20260809-152000-codex.md` 取代。状态保持 **REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

Round 3 的 Codex `152500` 进一步发现 R3-1，Terra `152501` 为 PASS；Controller 已接受并修复，最新验证统计见 `slice-2-aapl-acceptance-round3-review-fix-20260809-153000-codex.md`。

## Final closure

Codex `153500` 与 Terra `153501` 均 PASS/open `0/0/0`。本 artifact 所有 H1/H2/H3/M1/M2/L1 fixes，以及后续 CR-1/2/3、R3-1 均 CLOSED；此前六份 source/corrective reviews 的 accepted findings 全部 CLOSED。外部 DeepSeek/MiMo 402 状态不变。当前状态：**CLOSED / DUAL RE-REVIEW PASS**。
