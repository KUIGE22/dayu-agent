# Corrective plan re-review — AAPL acceptance Slice 2

- 评审时间：2026-08-09 13:00 CST
- 评审角色：DeepSeek corrective plan re-review（adversarial，只针对本次 corrective revision）
- 基线：`a99322c65aa7aedbfb3ab4516cb36d66311e71ba`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 diff（`176 insertions(+), 49 deletions(-)`，842 行）
- 伴随 artifacts：`docs/reviews/plan-fix-20260809-121500-codex.md`、`docs/reviews/plan-fix-20260809-124500-codex.md`
- 前轮 review：`docs/reviews/plan-review-20260809-123000-deepseek.md`（FAIL，H3/M4/L1）
- **结论：FAIL（open High = 2, Medium = 1；前轮 8 项中 7 项已闭合，Controller C-001 已闭合）**

本轮未修改 plan/production/tests/README，未运行 pytest/pyright/Ruff，无 live/网络/付费调用，未派生子 agent。

---

## 1. 前轮 finding 逐项闭合核验

| ID | 前轮结论 | 本轮核验 | 状态 |
|---|---|---|---|
| F-001 | `ProcessCommandEvidence.source_kind` 不可得 | plan L135/L151 已改为由六个固定 section header 派生 `source_kind/status`。核对 `cli_formatters.py:887-898`，`_format_process_result` 确实固定输出 `成功/跳过/失败 × filings/materials` 六节且顺序恒定 | **CLOSED** |
| F-002 | `--quiet` 不隔离第三方 stdout | plan L126 新增 frozen `subprocess_env_policy`（精确三项，进 fingerprint）；L130 明确 Popen 复制当前 env 后以三项覆盖并显式传 `env=`；L112 不再宣称 quiet 产生纯净 stdout，改为唯一 title anchor + 锚前前缀允许；L763 已加对应 stop condition | **CLOSED** |
| F-003 | material skip 分支必填字段堵死恢复路径 | plan L133/L150 已引入 action 判别与 stable-ID + primary SHA 闭合，方向正确，但**所用 owner 字段与真源不符**，见 G-001/G-002 | **NOT CLOSED** |
| F-004 | 自由文本 defeat exact grammar | plan L112/L135 已把 reason/message/warning/files 及其续行显式定义为 opaque tail、不进 evidence；L133 已删除 warning count。download 行的可信前缀（至 `failed_files=`）确与 `cli_formatters.py:421-428` 的固定位置一致 | **CLOSED**（process 行的残留问题另计 G-003） |
| F-005 | `todo=true` 替代分支未建模 | plan L135/L151 已把 counts summary 与固定 `- materials 处理: 未实现（TODO）` 声明为合法互斥两态，TODO 分支 counts null / `todo=true` / semantic stop。与 `cli_formatters.py:883-886` 一致 | **CLOSED** |
| F-006 | `DEF14A` 与 `DEF 14A` 缺归一化真源 | plan L136/L149/L154 已统一复用 production `dayu.fins.pipelines.sec_form_utils.normalize_form`。核对 `sec_form_utils.py:41-79`，该函数为 public、`"DEF14A" → "DEF 14A"` 在其 replacements 内，可直接复用 | **CLOSED** |
| F-007 | `fil_` 前缀非 accession 独有 | plan L136/L155 已固定正字法 `^[0-9]{10}-[0-9]{2}-[0-9]{6}$`，显式 fail closed `fil_sec_*`/`fil_cn_*`/其它来源，`mat_*` 排除在 accession 比较外 | **CLOSED** |
| F-008 | `verify.json` 写者未定 | plan L130/L214 已明确外层 `run` 是 terminal `verify.json` 唯一 writer，独立 verify 不创建/更新 phase receipt 且目录字节不变 | **CLOSED** |
| C-001 | download formatter 无顶层 status | plan L148/L363 授权唯一 production delta：`_format_download_result` 在 `- ticker:` 后、`- 汇总:` 前输出 `- status: {result.status}`。核对 `contracts/fins.py:285-295` 确有 `status: str` 字段；`sec_download_workflow.py:519` 确可产出 `cancelled`；allowlist 已加 `dayu/fins/cli_formatters.py` 与 `tests/fins/test_cli_formatters_coverage.py`。旁证：三个现存断言 `下载结果` 的冻结测试（`tests/fins/test_pipeline_cli.py:3380-3385` 等）只做 substring 断言，插入 status 行不会破坏它们 | **CLOSED** |

---

## 2. Remaining findings

### G-001-未修复-[高]-`material_action` 的 owner 值域没有 `skip`，`Literal["create","update","skip"]` 不可实现

- **位置**：§5.1 L133（`MaterialImportCommandEvidence` … `material_action: Literal["create","update","skip"]`）、§5.2 L150（"`create/update` evidence 要求 …；`skip` 允许 source_fingerprint/report_date 为 null"）、fix artifact L25/L53
- **问题类型**：契约缺失 / 不可直接实施（owner 事实错误）
- **当前写法**：把 `skip` 建模为 `material_action` 的第三个取值，并以该判别式决定 `source_fingerprint`/`report_date` 是否必填。
- **反例/失败场景**：material 已存在且指纹未变时，owner 走 skip 路径，但 `material_action` 字段仍是 `create` 或 `update`；strict Literal 解析永远拿不到 `"skip"`，于是 evidence 落入 create/update 分支并要求三字段必填——而这正是 F-003 已证实会缺行的场景。F-003 想修的重试路径依旧被堵死，只是失败点从 "字段缺失" 变成 "action 判别错误"。
- **为什么有问题**：owner 把 "是否跳过" 建模在**顶层 `status`** 上，而非 `material_action` 上。`sec_upload_workflow.py:421/447` 的 `material_action=normalized_action` 来自 `resolve_upload_action(...)`，其 docstring 与实现明确 "仅可能为 `create`、`update` 或 `delete`"（`docling_upload_service.py:903-928`）。skip 由 `DoclingUploadService` 内部 `_can_skip_upload` 命中后返回 `UploadOperationResult(status="skipped", ...)`（`:198-213`），再经 `_resolve_upload_status`（`sec_upload_workflow.py:473-488`，只把 `"uploaded"` 映射为 `"ok"`，其余原样透传）成为顶层 `status="skipped"`。两个字段正交，plan 混用了它们。
- **直接证据**：
  - `dayu/fins/pipelines/docling_upload_service.py:903-928`（`resolve_upload_action` 值域仅 create/update/delete）
  - `dayu/fins/pipelines/sec_upload_workflow.py:160`、`:421`、`:447`（`material_action = normalized_action`）
  - `dayu/fins/pipelines/docling_upload_service.py:198-213`（skip 走 `status="skipped"`，payload 只加 `skip_reason="already_uploaded"`）
  - `dayu/fins/pipelines/sec_upload_workflow.py:473-488`（`_resolve_upload_status` 不改写 `skipped`）
  - `dayu/fins/cli_formatters.py:766-776`（formatter 无条件输出 `- status:` 与 `- material_action:` 两行，二者独立）
- **影响**：实施 Agent 按 plan 定义的 Literal 写解析器，在 skip 场景下要么 fail closed（恢复路径不可达，等同 F-003 未修），要么被迫自行改判别式（偏离 plan 且无授权）。三组 download 的付费成本在 import 重试失败时全部作废。
- **建议改法和验证点**：把判别式从 `material_action` 换成 **owner 顶层 `status`**：(1) `material_action: Literal["create","update"]`（本 plan 不传 `--action`，`delete` 不可达，可显式排除并对 `delete` fail closed）；(2) 新增 `owner_status: Literal["ok","skipped"]` 作为条件必填的判别式；(3) `owner_status == "ok"` 时 `source_fingerprint`/`report_date` 必填，`owner_status == "skipped"` 时允许为 null 并改由 stable document ID + repository meta/primary SHA 闭合。验证点：用真实 `format_fins_cli_result(FinsCommandName.UPLOAD_MATERIAL, ...)` 构造 `status=ok/material_action=create` 与 `status=skipped/material_action=update`（后者省略 `source_fingerprint`/`report_date` 行）两份 stdout，断言两条路径都不 fail closed 且 skip 路径经 primary SHA 闭合；断言 `material_action=delete` 或 `status` 为其它值时 fail closed。
- **修复风险（低/中/高）**：低（纯 plan 文本，把判别字段换正确）
- **严重程度**：**高**

---

### G-002-未修复-[高]-§5.1 "owner status 仅允许 `ok` 继续" 与 §5.2 允许 material skip 直接冲突

- **位置**：§5.1 L137（"owner status 是有界非空 scalar，但 acceptance 仅允许 `ok` 继续"）、§5.2 L150（"`skip` 允许 source_fingerprint/report_date 为 null，但 …"）、§13 L766
- **问题类型**：契约缺失 / 状态机漏洞（plan 内部矛盾）
- **当前写法**：L137 对全部 evidence 子类型统一规定 owner status 非 `ok` 即不得继续；L150 又要求 material import 的 skip 场景可以继续并走 primary SHA 闭合。
- **反例/失败场景**：material 已存在且未变更（重试、或同 run-id 恢复），owner 返回顶层 `status="skipped"`。按 L137 该命令必须 semantic stop；按 L150 它应当继续并闭合。两条规则同时命中同一条 stdout，plan 无法裁决，实施 Agent 只能猜。
- **为什么有问题**：L137 的 "仅允许 `ok`" 对 download 与 process 是正确且必要的（`cli/commands/fins.py:235-239` 把 `cancelled` 列入成功白名单，正是 exit-0 语义失败的根源），但对 upload_material 过度收紧——`skipped` 在该命令上是**合法的幂等成功态**，不是失败。plan 把三类命令的 status gate 写成了同一条规则，丢失了 per-command 语义。
- **直接证据**：
  - `dayu/fins/pipelines/docling_upload_service.py:198-213` 与 `sec_upload_workflow.py:473-488`（skip ⇒ 顶层 `status="skipped"`，不映射为 `ok`）
  - plan §5.1 L137 与 §5.2 L150 的文本冲突
  - plan §8.1 L264 明确依赖 owner 的 create/update/skip 幂等语义做重试
- **影响**：与 G-001 叠加后，material import 的幂等重试在 plan 层面被两条互斥规则同时否决；§8.1 承诺的恢复能力仍然不可达，而 §13 的 stop condition 会把它报成一个语义误导的失败。
- **建议改法和验证点**：把 L137 的 status gate 按命令拆开写明：download 与 process 仅允许 `ok`（显式含 exit-0 `cancelled` 必停）；upload_material 允许 `ok` 与 `skipped` 两态，其余一律停机，且 `skipped` 必须同时满足 stable document ID 相等与 repository primary SHA 等于 `plan.price_material_sha256`。同时在 §13 L766 的 price material 条目中把 "owner status 非 ok" 改为 "owner status 不在该命令允许集合内"。验证点：断言 upload_material `status=skipped` 在 SHA 闭合时继续、在 SHA 不等时 fail closed；断言 download/process 的 `cancelled` 仍必停。
- **修复风险（低/中/高）**：低
- **严重程度**：**高**

---

### G-003-未修复-[中]-process row 的 `quality` 不是可信结构前缀，无法与 opaque tail 安全分离

- **位置**：§5.1 L133（`ProcessCommandEvidence` … 逐文档 `document_id/source_kind/status/quality`）、§5.1 L135（"行内只取 document_id/quality 等可信前缀"）、§5.2 L151、§9 L374
- **问题类型**：最佳实践偏离 / 契约缺失（F-004 的 process 侧残留）
- **当前写法**：plan 在 download 侧正确地把 "固定位置前缀" 与 "opaque tail" 分开，但在 process 侧把 `quality` 也归入 "可信结构前缀"。
- **反例/失败场景**：`_format_process_items` 的行结构是 `  - {document_id} | status={status}` 之后再拼接**条件省略、可变长度**的 optional parts，且顺序为 `reason → form_type → fiscal_year → quality → has_xbrl → …`。`reason` 是自由文本且排在 `quality` 之前。若某条 skipped/failed 文档的 `reason` 含 ` | ` 或 `quality=` 字样（provider/异常文本可控），按 `|` 切分或按 `quality=` 扫描都会取到错误值，或在启用 fail-closed 时把合法输出判为漂移。`_format_value_inline` 仅做空白折叠与 180 字符截断（`:1106-1123`），不转义 `|`。
- **为什么有问题**：process 行的**唯一**位置确定的可信前缀是 `  - {document_id} | status={status}`；其后的一切都在 opaque tail 之内。plan 已经为 download 建立了 "只信固定位置前缀" 的正确原则，却在 process 侧把一个位置不固定、且被自由文本前置的字段当成可信结构，与自己在 L135 定下的原则不一致。
- **直接证据**：
  - `dayu/fins/cli_formatters.py:1004-1015`（optional parts 顺序：`reason` 在 `quality` 之前）
  - `dayu/fins/cli_formatters.py:1062-1076`（`_collect_optional_parts` 对 `None`/`""` 整段省略 ⇒ 位置不固定）
  - `dayu/fins/cli_formatters.py:1106-1123`（`_format_value_inline` 不转义 `|`）
  - 对照 plan §5.1 L135 自身确立的 "只信固定结构" 原则
- **影响**：`quality` 可能被静默取错值并进入 receipt evidence（污染 §6 质量闭合的输入），或在合法输出上触发假的格式漂移停机。
- **建议改法和验证点**：把 process 行的可信前缀显式限定为 `  - {document_id} | status={status}`，`quality` 从 `ProcessCommandEvidence` 的行内解析来源中移除。若质量状态仍需闭合，改由 `ProcessedDocumentRepositoryProtocol` 的 `quality` 状态指纹提供——§5.2 L152 的源清单契约已经要求读取该字段，属于既有能力，不新增依赖。验证点：构造 `reason` 含 ` | quality=fake` 的真实 `ProcessDocumentResultItem`，断言 evidence 中不出现被污染的 quality、不误判为漂移；断言 quality 闭合走仓储协议真源。
- **修复风险（低/中/高）**：低
- **严重程度**：**中**

---

## 3. Non-findings（本轮尝试证伪但站得住）

- **`upload_material` 缺 `--company-name` 会失败**：已证伪。`_validate_company_meta_args` 仅在 `existing_company_meta is None` 时触发（`cli_support.py:901-906`），而三组 download 先行执行且 `sec_download_workflow.py:371` 调用 `host._upsert_company_meta(...)` 写入同一 `--base <run-root>/data-workspace` 的 company meta。plan 固定的 download → import 顺序天然满足该前置条件。
- **`--document-id` 传入会被 owner 拒绝**：已证伪。`cli_support.py:427-432` 明确该 flag 为可选且 "若传入则必须与稳定 ID 一致"；plan L126/L507 用 owner `build_material_ids(form_type="MATERIAL_OTHER", material_name="aapl-price-snapshot", fiscal_year=None, fiscal_period=None)` 生成（`docling_upload_service.py:826-865`，签名与参数名精确匹配），不复制 SHA-1 seed，符合 owner 校验路径。
- **新增 `- status:` 行会破坏冻结测试**：已证伪。三个引用 `下载结果` 的现存测试均为 substring/独立字段断言，未锁定行序或行数。
- **`subprocess_env_policy` 进 fingerprint 是过度设计**：不成立。它直接决定 stdout 是否可解析，属于运行身份的一部分，与 `termination_grace_seconds` 同级，且 L763 已配套 stop condition。
- **evidence union 闭集 + bump schema 约束**：与 `_PHASE_SCHEMA_VERSION` 治理一致，非过度设计。
- **`CommandRecord` 增 `stdout_summary` 后是否成 God schema**：仍否。新字段与 `stdout_sha256` 分工明确（digest 是完整性真源，summary 是有界诊断），且两个 summary 共用 `_STREAM_SUMMARY_MAX_BYTES=512` 上界，未引入第二真源。

---

## 4. Open questions

1. G-001 建议新增的 `owner_status` 字段与 `ProcessCommandEvidence`/`DownloadCommandEvidence` 已有的 "owner status" 是否统一命名？建议统一为 `owner_status` 并在 L137 按命令给出各自允许集合，避免三处各写一遍。
2. G-003 移除行内 `quality` 后，§6 质量 rubric 是否有任何环节仍依赖 process stdout 的 quality？本轮核对未发现依赖（§5.2 L152 已走仓储协议），但需 Controller 确认。

---

## 5. Residual risks and tracking destination

| 残余风险 | 跟踪去向 |
|---|---|
| upload_material 顶层 status 值域未在 owner 侧被 Literal 约束（`_resolve_upload_status` 原样透传内部状态），未来新增内部状态会变成安全停机 | 计入 §14 residual；acceptance 侧维持闭集允许 `ok`/`skipped`，其余 fail closed |
| process row optional parts 顺序与省略规则未版本化，未来新增字段可能改变行形状 | 计入 §14 residual；G-003 修正后 acceptance 只依赖固定前缀，暴露面已最小化 |
| plan 已有的 owner formatter drift、第三方 stdout 通道、opaque tail 不可审计、fresh workspace 来源不变量、v3 不兼容、stale fixture lock 六项 residual | 保持现状，本轮无新增变更需求 |

---

## 6. Final plan review conclusion

**FAIL**

- Open High：2（G-001、G-002）
- Open Medium：1（G-003）
- Open Low：0
- 前轮 F-001~F-008 中 7 项已闭合，Controller C-001 已闭合

本次 corrective revision 的整体方向正确：F-002 的 static env policy、F-004 的 trusted-prefix/opaque-tail 分离、F-006 的 `normalize_form` 单一真源、F-007 的 accession 正字法、F-008 的 receipt writer 归属，都是精确、最小且可实施的收敛，未引入新抽象或扩大 production 面。C-001 选择的单行 formatter delta 也是补齐顶层 truth 的最小手段。

剩余两个 High 同源于一处未核对的 owner 事实：**upload_material 的 "跳过" 语义位于顶层 `status`，而非 `material_action`**。plan 把判别式挂在了错误字段上（G-001），并在 §5.1 用一条全局 "仅允许 `ok`" 规则否决了 §5.2 自己允许的 skip 分支（G-002）。二者叠加使 F-003 实际未闭合——§8.1 承诺的幂等重试路径依旧不可达。G-003 是 F-004 原则在 process 侧的未贯彻残留。

三处修正都是 plan 文本级、单点、无新增依赖，不需要扩大 §9 的实施 allowlist，也不需要额外 production delta。

**Slice 2 保持 FROZEN**，不得恢复 implementation，直到 G-001/G-002/G-003 由 Controller 裁决关闭并完成同一 revision 的双路 corrective re-review。**Slice 5 / live 保持 NOT AUTHORIZED / NOT RUN。**
