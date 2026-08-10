# Slice 1.3 Fins Evidence Locator pre-edit plan fix

- **Work unit**：Investment Platform Restoration / Slice 1.3
- **Controller**：Codex
- **日期**：2026-08-10
- **状态**：ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED
- **基线**：`b45e0ee`
- **目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`

## 1. Stop 事实

DeepSeek Flash implementation worker 在任何编辑前执行只读 owner/call-graph 审计；Controller
同时独立核对源码。工作树保持 clean，Slice 1.3 production/tests/README 零编辑。原 contract
不可直接实施：

1. 仓库中没有 `repository_id` production 真源；从 workspace path/backend/随机值派生会
   泄漏或导致 FS/S3 projection 不同。
2. §6.3 只列 locator kind，没有 page/table cell/section/XBRL/document payload schema，
   implementation 必须自行猜测 persisted public contract。
3. `ProcessedDocumentRepositoryProtocol` 没有 processed primary file；processed meta 真实使用
   `source_document_version/source_fingerprint/reprocess_required`，原计划未定义它与 source
   primary bytes 的闭包。
4. Fins 文档按 master plan 是 public reference，locator projection 无 tenant 字段，现有
   Fins protocols/runtime也不接收 `TenantScope`；“Fins 层 cross-tenant reject”不可证明。
5. 原 allowlist只允许改 `FinsServiceProtocol`，不允许改其真实实现
   `dayu/services/fins_service.py`；新增 protocol API 后调用链不闭合。

## 2. Controller 裁决

- **ACCEPT / PLAN DEFECT**。不是实现自由度，也不能用测试 seam、路径 hash、宽 JSON、
  fallback source kind 或 investment-side wrapper解决。
- 固定 `dayu.fins.public.v1` 为 backend/path/tenant-independent 逻辑 repository namespace。
  同一 owner bytes 在 FS/S3 下 projection相同；content identity由 document/version/
  fingerprint/primary/locator hashes组成。
- 固定五类 payload、artifact组合与 citation bytes；XBRL 用 canonical fact row SHA唯一定位，
  table cell只接受 records data。
- `primary_content_sha256` 对两种 artifact均绑定 source primary exact bytes；processed额外闭合
  current source version/fingerprint、未删除、无需reprocess，locator hash保护 processed片段。
- cross-tenant私有关联验证归 Slice 3.1，Fins locator保持公共且无 tenant。
- allowlist最小补入 domain export 与真实 `FinsService` delegate；不改 storage实现、processor、
  investment、migration或 startup。

## 3. Review questions

Terra 与 MiM Native 必须独立挑战：

1. logical repository namespace是否既满足 FS/S3 canonical又不会造成未绑定内容误接受；
2. 五 payload是否能仅用当前 public owner API唯一解析，尤其 XBRL duplicate 与 table markdown；
3. processed/source identity closure是否完整覆盖 reprocess、parser输出与可选 FileObjectMeta SHA；
4. public Fins reference 与 Slice 3.1 tenant owner拆分是否符合现有 RLS/identity计划；
5. allowlist/call path是否覆盖真实 Service implementation且没有反向依赖或第二 storage真源；
6. validation matrix能否证明 persisted projection重放、bytes漂移和无路径泄漏。

任一路 open H/M/L 非零时 Slice 1.3 implementation继续冻结；Controller只修 master plan，随后
再次双路 review。PASS/open0 前不得编辑 code/tests/README。

## 4. Scope audit

本 gate 仅允许修改 master plan 与本 artifact。未运行 live/network/model/broker；未修改
production/tests/README、未 commit/push/PR、未进入 Slice 1.4。

## 5. Initial dual review adjudication

- Terra：`docs/reviews/plan-review-20260810-slice-1.3-evidence-locator-terra.md`
  = FAIL，open H/M/L=`2/0/0`。
- MiM Native：
  `docs/reviews/plan-review-20260810-181019-slice-1.3-evidence-locator-mimo-native.md`
  = PASS-WITH-RISKS。其正文列出 F1/F2/F3/F6/F7 五项 Medium 与 F4/F5两项Low；结论的
  `4M/1L` 是计数错误，Controller按正文 `5M/2L` adjudicate。

| Finding | 裁决 | Plan fix |
| --- | --- | --- |
| Terra F-01 | ACCEPT / FIXED | 不扩大现有 tool/cache API；以 exact+counterpart preflight、每次 fresh request-scoped `FinsToolService`、postflight double-read解决 fallback/cache/TOCTOU，并补collision/stale-cache/race tests。 |
| Terra F-02 | ACCEPT / FIXED | Slice 3.1明确 public locator可被A/B分别复用；所有private endpoints以same-tenant composite FK + scope predicate + RLS拒绝真正cross-tenant link。 |
| MiM F1 | ACCEPT / FIXED | `source_fingerprint`锁为当前 ingestion写入source meta的lower-64-hex字段；Slice1.3只读不重算。 |
| MiM F2 | ACCEPT / FIXED | canonical XBRL row固定13字段、null策略、exact concept与0/1/duplicate规则。 |
| MiM F3 | REJECT / DUPLICATE / CLOSED | 初版S13-CTRL-02已逐字要求records且“markdown/越界/缺列拒绝”；finding复述既有规则。 |
| MiM F4 | INFO / ABSORBED / CLOSED | 明确exact bytes来自`get_primary_source(...).open()`，meta来自`get_primary_file()`；不改变原语义。 |
| MiM F5 | INFO / ABSORBED / CLOSED | canonical fragment明确移除整个tool citation/ticker/document等wrapper；递归泄漏scan保留。其声称`_build_citation`复制`files[].uri`与源码不符。 |
| MiM F6 | ACCEPT / FIXED | source document主文件唯一绑定`get_primary_source(...).open()` exact bytes。 |
| MiM F7 | ACCEPT / FIXED | processed document只编码`sections_result["sections"]`与`tables_result["tables"]`，不编码tool wrapper/citation。 |

该初次adjudication阶段Controller open plan findings=`0/0/0`，但当时尚不等于plan
accepted；Slice 1.3曾继续冻结至下节记录的corrective dual review完成。

## 6. Corrective closure

- Terra：
  `docs/reviews/plan-corrective-rereview-20260810-slice-1.3-evidence-locator-terra.md`
  = PASS，open H/M/L=`0/0/0`。
- MiM Native：
  `docs/reviews/plan-corrective-rereview-20260810-181651-slice-1.3-evidence-locator-mimo-native.md`
  = PASS，open H/M/L=`0/0/0`。

两路均独立确认：dual-kind碰撞拒绝 + request-scoped tool + owner double-read足以在不改
tool/cache API的前提下关闭 source-kind/cache/TOCTOU；public locator 多租户独立复用与
private endpoints same-tenant三层隔离已分清；source fingerprint、primary bytes、XBRL
13字段、records-only table cell和剥离wrapper的canonical fragment均可直接实施。

本 erratum现为 CLOSED。S13-CTRL-01..08 accepted，Slice 1.3 implementation可恢复；
accepted plan不替代后续code review，也不授权Slice1.4/live/network/broker。
