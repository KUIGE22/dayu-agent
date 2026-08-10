# Slice 1.3 Fins Evidence Locator plan acceptance

- **Controller**：Codex
- **日期**：2026-08-10
- **基线**：`b45e0ee`
- **状态**：ACCEPTED / DUAL PLAN RE-REVIEW PASS

## Accepted contract

Slice 1.3 按 master plan 的 S13-CTRL-01..08 实施：

- Fins持有唯一pathless evidence locator与canonical citation bytes；
- repository namespace固定为`dayu.fins.public.v1`，content由version/fingerprint/primary/
  locator hashes绑定；
- source/processed identity exact closure、双source-kind碰撞拒绝、request-scoped tool与
  pre/post owner double-read；
- document/page/section/table_cell/xbrl_fact五种严格payload与artifact组合；
- `FinsService -> FinsRuntime -> repositories/tool`唯一调用路径；
- public locator允许不同tenant各自引用，private Fact/Claim/EvidenceLink跨tenant连接由
  Slice3.1 composite FK + repository predicate + RLS拒绝。

## Review closure

- Initial Terra：FAIL，2H；F-01/F-02 accepted/fixed。
- Initial MiM Native：PASS-WITH-RISKS；正文F1–F7全部adjudicated并closed。
- Corrective Terra：PASS，open H/M/L=`0/0/0`。
- Corrective MiM Native：PASS，open H/M/L=`0/0/0`。

Review paths与逐项裁决记录在master plan及
`docs/reviews/plan-fix-20260810-slice-1.3-evidence-locator-codex.md`。

## Authorization boundary

只解冻 Slice 1.3 allowlist内的 deterministic code/tests/README与implementation artifact。
不授权Slice1.4、MinIO/S3、investment evidence schema、live data/model/broker、push或PR。
