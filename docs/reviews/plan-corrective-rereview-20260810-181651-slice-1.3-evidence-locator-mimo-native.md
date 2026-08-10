# Slice 1.3 Fins Evidence Locator Corrective Closure-Only Re-Review

- **Reviewer**: MiMo Native
- **日期**: 2026-08-10T18:16:51Z
- **目标**: `docs/plans/2026-08-10-investment-platform-restoration.md` §6.3/Slice 1.3/S13-CTRL-01..08/validation/stop
- **Controller fix**: `docs/reviews/plan-fix-20260810-slice-1.3-evidence-locator-codex.md`
- **初审 artifact**: `docs/reviews/plan-review-20260810-181019-slice-1.3-evidence-locator-mimo-native.md`
- **基线**: `b45e0ee`

## 1. Scope

Closure-only re-review。逐项验证初审 F1-F7 正文级 plan 修复，核对 Terra 两项 finding 的 plan 吸收，不扩审计范围。

## 2. F1-F7 逐项 Closure

### F1 (source_fingerprint 定义缺失) — CLOSED / FIXED

**Plan fix**: §6.3.3 S13-CTRL-03 第二条（line 383-387）精确定义：
- 唯一真源：`get_source_meta(...)["source_fingerprint"]`
- 格式：小写 64-hex SHA-256
- 来源：SEC/CN download 以排序后的 source asset descriptors 构建，upload 以排序后的 original assets 构建
- Slice 1.3 边界：只读/验证，不重算/不改写

**验证**: Implementation agent 无需猜测。`get_source_meta` 返回 `DocumentMeta = dict[str, Any]`，fingerprint 从该 dict 的 `"source_fingerprint"` key 读取。已由 ingestion pipelines 写入。✅ 可实施。

### F2 (XBRL fact canonical bytes 未定义) — CLOSED / FIXED

**Plan fix**: §6.3.2 table 第五行（line 373）精确定义：
- canonical row 13 字段：`concept, label, numeric_value, text_value, content_type, unit, decimals, period_type, period_start, period_end, fiscal_year, fiscal_period, statement_type`
- null 策略："所有键总是存在、缺值为 JSON null"
- exact concept 查询 + 逐 row 求 SHA + 恰好一条匹配

**验证**: 字段集合明确，null 策略明确，匹配规则明确。implementation agent 可直接实施 canonical serializer + SHA。✅ 可实施。

### F3 (table_cell records-only 强制) — CLOSED / DUPLICATE / ABSORBED

**Controller 裁决**: REJECT / DUPLICATE / CLOSED。初版 S13-CTRL-02 已逐字要求 "get_table 必须为 records data；markdown/越界/缺列拒绝"。

**验证**: 核对初版 §6.3.2 table 第四行（原始 plan line 355 位置），确实写明 "get_table 必须为 records data；row/column 唯一命中后...；markdown/越界/缺列拒绝"。初审 F3 复述了既有规则，Controller 裁决正确。✅ CLOSED。

### F4 (FileObjectMeta.sha256 / primary file 路径) — CLOSED / ABSORBED

**Plan fix**: §6.3.3 第三条（line 388-392）精确定义：
- 主文件：`SourceDocumentRepositoryProtocol.get_primary_file(...)` 返回 `FileObjectMeta`
- exact bytes：`get_primary_source(...).open()` 返回 source `Source` 对象后读 bytes
- 禁止读 `Source.uri` 或 `materialize()` 路径
- `FileObjectMeta.sha256` 若存在必须等于实算 SHA，不存在不能跳过实算

**验证**: 引用了 `repository_protocols.py:175-186` 的两个精确方法签名。implementation agent 可直接按此调用。✅ 可实施。

### F5 (citation path leak) — CLOSED / ABSORBED

**Plan fix**: §6.3.1 最后一条（line 360-363）明确：
- "所有 processed citation bytes 都是下表规定的 **evidence fragment**，不是完整 tool response"
- "必须移除 tool response 的顶层 `ticker`、`document_id`、`citation`、diagnostics/hint/推荐信息"
- "不得复制 `_build_citation()` 的任何字段"

**验证**: Controller 指出初审声称 `_build_citation` 复制 `files[].uri` 与源码不符——核对 `service.py:1450-1464`，`_build_citation` 构建 citation dict 确实从 meta.json 读取数据，但 evidence locator 的 citation 走完全不同的路径（canonical fragment bytes 的 SHA），不复用 `_build_citation`。✅ 已吸收。

### F6 (document locator "主文件" 语义) — CLOSED / FIXED

**Plan fix**: §6.3.2 table 第一行（line 369）：
- source citation bytes："为 `get_primary_source(...).open()` 读得的 exact bytes"
- processed citation bytes：只编码 `sections_result["sections"]` 与 `tables_result["tables"]`

**验证**: 引用了精确的 repository method。implementation agent 无需自行决定 "主文件" 选取规则。✅ 可实施。

### F7 (document processed canonical JSON 不完整) — CLOSED / FIXED

**Plan fix**: §6.3.1 最后一条（line 360-363）+ §6.3.2 table 第一行（line 369）：
- "必须移除 tool response 的顶层 `ticker`、`document_id`、`citation`"
- processed citation bytes 只序列化 `sections_result["sections"]` 和 `tables_result["tables"]`，不编码整个 tool response

**验证**: canonical fragment 只包含结构化数据子集，不包含动态/路径字段。SHA 可复现。✅ 可实施。

## 3. Terra Findings Verification

### Terra F-01 (TOCTOU / cache stale) — CLOSED / FIXED

**Plan fix**: §6.3.4 S13-CTRL-04（line 418-424）：
- "每次 evidence fragment resolve 必须用同一 repositories/registry 新建 **request-scoped `FinsToolService`**"
- "禁止调用或污染 `DefaultFinsRuntime.get_tool_service()` 的共享 cache"
- "request-scoped 实例只能在 exact/counterpart source preflight 通过后读取"
- "读取后还必须完成 S13-CTRL-03 double-read"

**验证**: request-scoped tool + preflight/postflight 解决了 cache stale 和 TOCTOU 问题。S13-CTRL-07 tests 还要求覆盖 "shared-cache stale processor 不被使用" 和 "pre/post source race"。✅ 可实施。

### Terra F-02 (same-tenant private endpoints) — CLOSED / FIXED

**Plan fix**: §6.3.5 S13-CTRL-05（line 430-439）：
- "Fact、Claim、ClaimVersion、EvidenceLink 均带 non-null tenant id"
- "全部 private endpoints（至少 Fact 与 ClaimVersion）必须与调用 `TenantScope` 同 tenant"
- "使用 `(tenant_id,id)` composite FK/unique 或等效数据库约束、repository 首参 scope+显式 predicate 与 RLS 三层拒绝"
- Slice 3.1 tests 证明 A/B 可独立复用同一 public locator、A 不能读写 B 的 Fact/ClaimVersion

**验证**: 现有 Slice 1.1 RLS 架构（private表 default-deny + `SET LOCAL app.tenant_id`）和 Slice 1.2 composite FK 为该修复提供了基础。Slice 3.1 负责实际验证。✅ 可实施。

## 4. Conclusion

**PASS — open H/M/L = 0/0/0**

初审 F1-F7 全部 CLOSED：5 项 ACCEPT/FIXED（F1/F2/F6/F7/F4）、1 项 REJECT/DUPLICATE（F3）、1 项 ABSORBED（F5）。Terra 两项 FINDINGS 全部 CLOSED/FIXED。

Plan 的 Slice 1.3 section 现在对 implementation agent 足够确定性：
- `source_fingerprint` 有 owner、来源和格式定义
- XBRL canonical row 有 13 字段精确清单和 null 策略
- table_cell records-only + markdown reject 已在原始 plan 中
- document "主文件" 绑定 `get_primary_source(...).open()` exact bytes
- processed citation 只编码 evidence fragment，剥离 tool wrapper/citation
- source/processed closure 有 preflight/postflight/double-read 和 dual-kind collision reject
- request-scoped `FinsToolService` 解决 cache stale/TOCTOU
- Slice 3.1 private endpoints 有 composite FK + scope + RLS 三层拒绝

Open: 0 High / 0 Medium / 0 Low。
