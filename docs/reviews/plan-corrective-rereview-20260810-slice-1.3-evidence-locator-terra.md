# Slice 1.3 Evidence Locator corrective closure-only plan re-review

- **审查日期**：2026-08-10 18:16:37 CST（本机时钟）
- **审查目标**：最新 `docs/plans/2026-08-10-investment-platform-restoration.md`、`docs/reviews/plan-fix-20260810-slice-1.3-evidence-locator-codex.md`，并仅对照此前 Terra review 与当前 Fins/投资存储源码。
- **范围**：只复核此前 F-01、F-02 及 MiM canonical 修正；未扩展审计。
- **边界**：只读；未运行 live/network/model/broker，未修改 plan/code/tests/README/旧 review，未 commit/push/PR。本文件是本次唯一新增 artifact。

## 结论

**PASS（Open H=0 / M=0 / L=0）**。

## Closure 验证

| 原 finding / 修正点 | 当前计划闭包 | 当前源码依据 | 结论 |
| --- | --- | --- | --- |
| F-01：`source_kind` fallback、共享 cache 与 TOCTOU | §6.3.3 要求 exact/counterpart preflight；任一 ticker/document_id 双 kind 碰撞即 `ambiguous_source_identity` fail-closed；fragment 后 double-read exact/counterpart source meta、processed meta、primary bytes。§6.3.4 改为每次构造 request-scoped `FinsToolService`，不得调用 shared `DefaultFinsRuntime.get_tool_service()`；Slice 1.3 tests 明列 collision、shared-cache stale processor、pre/post race、processed `source_kind` missing/mismatch。 | 现有 tool API 的确不含 `source_kind`，且 `_resolve_source_kind()` 固定 filing→material（`dayu/fins/tools/service.py:1791-1815`）；processor cache 是 `FinsToolService` 实例字段，键仅 `(ticker, document_id)`（`dayu/fins/tools/service.py:155-165,1742-1754`；`dayu/fins/tools/cache.py:20-30`）。因此碰撞 preflight 使 fallback 无可选错误来源，fresh instance 消除跨请求 cache 污染，postflight 捕获读取期间 counterpart 新增/删除或 owner identity 漂移。无需改 `tools/cache`。 | 已关闭。 |
| F-02：公共 locator 复用与 A-to-B 私有关联 | §6.3.5 精确允许 tenant A/B 各自引用同一 public company/security/Fins locator；同时要求 Fact/Claim/ClaimVersion/EvidenceLink 均 tenant-private，所有 private endpoints 与 scope 同 tenant，以 `(tenant_id,id)` composite FK/unique、repository scope predicate、RLS 三层拒绝。Slice 3.1 invariant/tests 同步列出 A/B 成功复用及 composite FK/predicate/RLS 拒绝 A-to-B。 | 当前私有 source 模型已采用相同模式：`tenant_id` 非空、`UniqueConstraint(tenant_id,id)`，并以 `(tenant_id, foreign_id)` `ForeignKeyConstraint` 约束同租户端点（`dayu/investment/storage/models_identity.py:251-373,398-432`）；repository 已以 `SET LOCAL app.tenant_id`、显式 predicate 与 RLS 为双层边界（`dayu/investment/storage/postgres_identity.py:6-16,255-302`）。 | 已关闭。 |
| MiM F1/F4/F6：fingerprint 与 primary exact bytes | §6.3.3 将 fingerprint 固定为 ingestion 写入 source meta 的 lower-64-hex 值；primary bytes 唯一来自 `get_primary_source(...).open()`，可选 `get_primary_file(...).sha256` 仅作相等校验，禁止读取 URI/materialize。 | SEC fingerprint 使用排序描述符的 SHA-256 hex（`dayu/fins/downloaders/sec_downloader.py:534-560`）；source repository 公开所需 primary API（`dayu/fins/storage/repository_protocols.py:171-184`）。 | 已关闭。 |
| MiM F2/F7：canonical XBRL 与 processed fragment | §6.3.1 明确 processed bytes 移除 tool wrapper/citation；§6.3.2 将 document 固定为 sections/tables lists，XBRL 固定 13 字段、所有键存在、null 策略、exact concept 和 0/1/duplicate 规则。 | `FinsToolService` 已先输出归一化、确定性去重的 public fact rows（`dayu/fins/tools/service_helpers.py:1215-1254,1283-1340,1381-1421`）；计划只投影其中的显式 13 字段，排除派生 `scale`，不会把 wrapper、citation 或存储定位信息编码入 bytes。对公开 API 可见的重复 row 仍由 resolver 的“恰好一条 hash 匹配”fail-closed。 | 已关闭。 |
| MiM F3/F5：table records-only 与路径泄漏 | §6.3.2 保持 table records-only、markdown/越界/缺列拒绝；§6.3.1/1.3 tests 明定 fragment 去 wrapper 和递归 path/URI/bucket/handle scan。 | 现有 `get_table` public result 区分 records/markdown/raw_text；计划只允许 records 投影，且 owner API 表层 citation 已被排除。 | 已关闭。 |

## Findings

无。本次 closure-only 范围内未发现仍会迫使实施者发明 schema、owner、调用签名、allowlist 或缓存兼容层的 material gap。

## Open questions

无。

## Residual risks 与跟踪归属

- Slice 1.3 实施时必须实际执行计划列出的 collision、stale-cache、pre/post race、processed source-kind mismatch 和五类 canonical fragment tests；这是验证 gate，不是本次 plan blocker。
- Slice 3.1 实施时必须以真实 PostgreSQL integration 验证 composite FK、repository predicate 与 RLS 三层拒绝；公共 locator 不应承担 tenant admission。
- Slice 1.4 继续负责以 MinIO 验证同 owner bytes 的 FS/S3 canonical projection。

## 最终判定

**PASS（Open H=0 / M=0 / L=0）**。此前 Terra F-01 与 F-02 已由最小、可实施且与现有 owner API/存储模式一致的计划修正关闭；MiM canonical 修正未引入新的 closure gap。
