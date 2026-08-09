# Slice 1 AAPL acceptance dual-review adjudication

- Status: **CLOSED / DUAL RE-REVIEW PASS**
- Source review DS: `docs/reviews/code-review-20260809-090514.md`
- Source review MiMo: `docs/reviews/code-review-20260809-091934.md`
- Re-review MiMo: `docs/reviews/code-review-20260809-094216.md`
- Re-review DS: `docs/reviews/code-review-20260809-094218.md`
- Controller instruction: 仅修复裁决接受的 F1–F7；不得进入 Slice 2/3、live、commit、push 或 PR
- Scope: 两份 Slice 1 utils、focused test、原 implementation artifact，以及本轮 adjudication/fix artifacts

## Consolidated accepted fixes

| Fix | Source | Disposition |
|---|---|---|
| F1 | DS1 | **Accepted, scope-corrected Medium.** 固定 AAPL/technology 语义，不建通用 registry；contract/plan parser 与 inspection 在任何语义 dict 下标前要求精确固定 13 文件集合，错误统一为 `ContractError`。 |
| F2 | DS4 + MiMo1 | **Accepted Medium, duplicate merged.** valuation reference 判定与切片使用同一个 normalized line；合法缩进保持 PASS，缩进 mismatch 命中特定 mismatch code。 |
| F3 | MiMo5 | **Accepted Low.** 所有生产 artifact JSON 在 owner validator 前统一经过 strict JSON ingress，拒绝 NaN/Infinity；已解析 payload 在 workbook/monitoring/status 分支复用，path-only owner API 的内部读取不可避免。 |
| F4 | DS10 section half + MiMo8 | **Accepted Low, duplicate merged.** source-list 只允许唯一精确标题；topic 只允许当前中英/双语精确标题，重复、诱饵和组合标题不能以 substring/first-hit 满足一个或多个 topic。 |
| F5 | DS7 owner-result half | **Accepted Low, partial.** owner validator 非 JSON 可序列化结果在已有 ingress 归一化为 `ContractError`；最终 receipt sensitive-shape 仍 fail loud。 |
| F6 | DS12 test half | **Accepted Low, test-only.** 不假设 `/Users/`；从 owner artifact 的已知字段读取当前主机绝对路径，并证明生产字节不变且 receipt 不复制路径/内容。 |
| F7 | DS8 missing-field half | **Accepted Low, test-strength only.** 新增缺必填字段 strict schema 用例与精确错误；不全局要求 finding 集合完全等值，不拆分有意共享 gate code。 |

## DeepSeek DS1–DS12 disposition

| ID | Disposition | Rationale / owner |
|---|---|---|
| DS1 | **Accepted with severity/scope correction → F1** | 固定 13 文件是本验收 contract，不是可扩展 registry；问题是 mismatch 可能 `KeyError`，应在语义访问前 strict reject。 |
| DS2 | **Deferred, not open in Slice 1** | nonzero exit/status/termination/plan receipt binding 由 Slice 2 runner 实现，Slice 3 加 partial receipt 集成测试。当前 Slice 不伪造 runner 语义。 |
| DS3 | **Deferred, not open in Slice 1** | deterministic/live policy 与 plan binding 由 Slice 2 verify mode/preflight 强制。fixture IDs 有意不同，绝不增加三方相等要求。 |
| DS4 | **Accepted → F2** | 与 MiMo1 重复。 |
| DS5 | **Deferred optional hardening, not a defect** | 首个验收语义固定四段；contract 已固定，不在本轮改成动态 evidence schema。后续 owner：Slice 2/contract evolution 时再评估。 |
| DS6 | **Rejected / non-defect** | 当前所有 deterministic hard-gate finding 有意为 high；AST 已证明 finding gates 与固定 hard-gates 闭合，不扩展 severity/state machine。 |
| DS7 | **Split** | owner result serializability 接受为 F5；sanitizer/receipt 降级部分拒绝，最终 receipt 泄漏必须继续 fail loud，不能把敏感 shape 静默替换后通过。 |
| DS8 | **Split** | missing-required-field 测试接受为 F7；全局 exact finding-set、拆分共享 monitoring/artifact code、删除 happy gate 断言均拒绝，避免把有意同 gate 的并发诊断锁死。 |
| DS9 | **Rejected / non-defect for current scope** | 非尾部 `Z` 已由 datetime parser fail closed；不在本裁决中重写通用 datetime helper。 |
| DS10 | **Split** | section substring/first-hit 部分接受为 F4；非法 evidence 行仍产生 hard finding，不能形成 PASS escape，其是否参与 ID 集合不在本轮接受范围。 |
| DS11 | **Rejected** | 币种/`MATERIAL_OTHER`/SHA helper/不可用计数是独立 hardening 或既有明确语义，不属于裁决修复。 |
| DS12 | **Split** | test portability 接受为 F6；TypedDict/public surface 部分拒绝，后续 Slices 已有明确消费方，不删 public contract。 |

## MiMo1–MiMo11 disposition

| ID | Disposition | Rationale / owner |
|---|---|---|
| MiMo1 | **Accepted → F2** | 与 DS4 重复。 |
| MiMo2 | **Deferred, not open in Slice 1** | 与 DS2 重复；owner 为 Slice 2 runner + Slice 3 partial receipt integration。 |
| MiMo3 | **Rejected / non-defect** | expected artifact SHA 是调用方可选绑定，owner validators 与 derived fingerprints 仍验证内容；不在本轮改变默认 PASS 契约。 |
| MiMo4 | **Rejected / non-defect** | primary owner SHA 可缺失时仍计算并记录实际 blob SHA；是否强制 owner metadata SHA 属 owner contract 变更，不在 Slice 1。 |
| MiMo5 | **Accepted → F3** | strict JSON ingress 缺口成立。 |
| MiMo6 | **Rejected / non-defect** | sanitizer 对明确给定 acceptance-owned outputs 做有界扫描；空元组表示无该类输出，不引入第四态或虚假 residual。 |
| MiMo7 | **Rejected** | source-list 缺失后的早返保持单一根因诊断；不扩展本轮诊断聚合语义。 |
| MiMo8 | **Accepted → F4** | 与 DS10 section half 重复。 |
| MiMo9 | **Rejected / maintenance-only** | Markdown 二级标题判定简化不构成独立验收缺陷；F4 修改时仅移除与 exact matching 直接相关的冗余条件。 |
| MiMo10 | **Rejected** | 与 DS9 重复。 |
| MiMo11 | **Rejected / intentional residual** | `not_started` 由 workbook open/status residual 明示，不等于投资报告质量未通过；不收紧 gate。 |

## Deferred ownership closure

- Slice 2：phase nonzero/status/termination、plan fingerprint receipt binding、deterministic/live verify mode 与 preflight policy。
- Slice 3：partial/failed phase receipt 的端到端恢复与集成测试。
- 后续 contract evolution：若四段 evidence 语义不再固定，再统一调整 schema 与所有消费者；当前不开放。
- Rejected/non-defect 项不是本 Slice 的 open finding，不得作为进入 Slice 2 前的隐含扩项。

DS2/MiMo2 明确保留给 Slice 2 runner（phase status/exit/termination 与 plan receipt binding）及 Slice 3 partial receipt integration/recovery。DS3 明确保留给 Slice 2 verify mode/preflight 的 deterministic/live policy 与 plan binding；fixture IDs 有意按 artifact 独立，绝不要求相等。

## Dual re-review closure

- MiMo re-review：**PASS / ACCEPT**，open `H0/M0/L0`。
- DeepSeek re-review：overall **PASS**；报告了 `H0/M2/L1` observations，Controller 逐项关闭如下。
  1. 新 Finding 1：**REJECT/CLOSED non-defect**。固定 AAPL/technology 验收语义已接受；外部 `required_research_artifacts` 非精确固定 13 集合时 fail closed，内部 filename literal 只随受审代码变更，不引入 generic registry。
  2. 新 Finding 2：**REJECT/CLOSED non-defect**。固定四段 evidence 是既有已接受 contract，且此前已经裁决；若未来 schema 演进，作为 contract evolution residual 统一修改。
  3. 新 Finding 3：**REJECT/CLOSED non-defect / measurement framing**。`.md` 不是 JSON；全部 `.json` 均在 path-only owner 调用前经过 strict preflight。owner API 的 path-only limitation 已知，但不存在绕过 strict ingress 的当前缺陷。
- Controller closure 后，本 Slice open finding 为 `H0/M0/L0`。

## Adjudication outcome

DS1–DS12 与 MiMo1–MiMo11 均已有唯一 disposition；重复项已合并，接受项均映射到 F1–F7，deferred 项均有 owner/destination。复审 observations 也已逐项裁决关闭。当前状态为 **CLOSED / DUAL RE-REVIEW PASS**，实现可交由 Controller 创建 accepted commit。
