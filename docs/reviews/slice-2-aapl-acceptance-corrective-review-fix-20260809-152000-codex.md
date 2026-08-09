# Slice 2 AAPL Acceptance Corrective Review Fix Round 2

- 时间：2026-08-09 15:20 CST
- 基线：`1c7e16160b23704558508e9c25522a116d67ad84`
- Codex review：`code-review-20260809-151500-codex.md` — FAIL，open H/M/L=2/1/0
- Terra review：`code-review-20260809-151501-terra.md` — PASS，open H/M/L=0/0/0
- Controller decision：CR-1 High、CR-2 High、CR-3 Medium **ACCEPTED / FIXED**
- 状态：**CLOSED / DUAL RE-REVIEW PASS**
- Live：**NOT AUTHORIZED / NOT RUN**

## CR-1 — evaluator-equivalent pre-persistence sanitizer

runner 只维护一个静态 field pattern，并在 fragment byte truncation、canonical receipt serialization 与 CLI output 前执行；不读取/枚举环境值。pattern 不区分大小写，接受冒号/等号与可选空白，覆盖：

- Authorization / Proxy-Authorization；
- Cookie / Set-Cookie；
- `api-key`、`api_key`、`x-api-key` 及带 provider 前缀的 API key；
- access token、token、secret、password assignments；
- 既有 `sk-`、`AIza`、POSIX/Windows home/provider path。

参数化 canonical-receipt tests 将 `Authorization = Bearer ...`、`Cookie=...`、`api-key = ...` 分别注入 stderr、owner title prefix、structure-reject 行，并在 CLI ContractError 中重放；12 个组合均断言原值消失，同时 receipt 保留 category/line、raw stream SHA。

## CR-2 — persisted terminal passed-only / no-resume

可选 `verify.json` 一旦存在，loader 除 identity/time/argv/digest/null-evidence 外，显式要求：

- terminal phase status 为 `passed`；
- 精确一条 command record；
- record status `passed`、exit code 0；
- stop reason、termination action 为空，`partial_by_timeout=false`。

failed、signal、timeout 三种 lifecycle-valid canonical terminal mutation 均由独立 verify 拒绝；预置 `acceptance-receipt.json` sentinel 保持 byte-identical，证明没有 resume/提升/覆盖。

## CR-3 — material persisted plan SHA binding

material reload validator 新增两个精确 equality gate：

- `evidence.price_json_sha256 == plan.price_snapshot_sha256`；
- `evidence.price_material_sha256 == plan.price_material_sha256`。

它们与已有 stable document ID、raw report date、repository meta/primary SHA closure并列；测试分别只篡改一个 64-hex SHA 并 canonicalize，loader 均 fail closed。

## Validation

| Gate | Result |
|---|---|
| focused | 185 passed |
| exact coverage | CLI 82%、contracts 87%、evaluator 87%、total 84.56% |
| six-file exact pyright | 0 errors / 0 warnings / 0 informations |
| Ruff default | pass |
| Ruff F/I | new utils/tests pass；formatter F pass，I001 为 HEAD baseline |
| key full-rule | new utils 0 findings |
| owner research-template | 128 passed / 88 deselected |
| owner source/write | 54 passed |
| deterministic fixture CLI | PASS / exit 0 |

## Scope / handoff

Production/test diff 仍仅为 accepted 六文件；formatter production delta仍精确一行 status。没有修改 plan、README、fixtures 或其它 production/tests；没有 live/network/SEC/provider/model/paid调用；没有 commit、push、PR、review 或 Slice 3。

历史状态：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Round 3 follow-up

Codex `152500` 在共享 stream lifecycle 发现 R3-1 Medium，Terra `152501` 为 PASS。Controller 已接受并修复；本 artifact 的统计由 `slice-2-aapl-acceptance-round3-review-fix-20260809-153000-codex.md` 取代，CR-1/CR-2/CR-3 保持 CLOSED。

## Final closure

Final Codex `153500` 与 Terra `153501` 均 PASS/open `0/0/0`；CR-1/CR-2/CR-3、R3-1 与此前全部 accepted findings 均 CLOSED。外部 DeepSeek/MiMo 402 记录保留。当前状态：**CLOSED / DUAL RE-REVIEW PASS**。
