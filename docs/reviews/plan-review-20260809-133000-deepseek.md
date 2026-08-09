# Final corrective plan re-review — AAPL acceptance Slice 2

- 评审时间：2026-08-09 13:30 CST
- 评审角色：DeepSeek final corrective plan re-review（adversarial，closure-only）
- 基线：`a99322c65aa7aedbfb3ab4516cb36d66311e71ba`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 diff（`195 insertions(+), 49 deletions(-)`，861 行）
- 伴随 artifact：`docs/reviews/plan-fix-20260809-131500-codex.md`
- 前轮 review：`docs/reviews/plan-review-20260809-130000-deepseek.md`（FAIL，H2/M1）
- **结论：PASS（open High = 0, Medium = 0, Low = 0）**

本轮为 closure-only review，未扩大审计范围；未修改 plan/production/tests/README，未运行 pytest/pyright/Ruff，无 live/网络/付费调用，未派生子 agent。

---

## 1. Scope

只核验前轮 DeepSeek G-001/G-002/G-003 与 MiMo new L-1/L-2（含 MiMo open question）是否真正闭合，并对闭合所依赖的 owner 事实做必要交叉核对。不重新审计已在 12:30 / 13:00 两轮 CLOSED 的 F-001~F-008 与 C-001。

---

## 2. 逐项闭合核验

### G-001（高）— `material_action` 值域错误 → **CLOSED**

- plan §5.1 L134 已改为 `owner_status: Literal["ok","skipped"]` 与 `material_action: Literal["create","update"]` 两个正交字段，`source_fingerprint/report_date` 明确"按 owner_status 条件可空"，delete/其它 action 或其它 status 立即 fail closed。
- §5.2 L152 与 §8.1 L271 同步改写，措辞一致："`material_action` 只表示 owner create/update intent，不能表示 skip"。
- §9 L363 的 runner 语义、L375 的测试要求、§13 L784 的 stop condition 三处全部对齐，无残留旧措辞。
- **Owner 交叉核对**：`resolve_upload_action`（`docling_upload_service.py:903-928`）值域确为 create/update/delete；skip 走 `UploadOperationResult(status="skipped", ...)`（`:198-213`），经 `_resolve_upload_status`（`sec_upload_workflow.py:473-488`）原样透传为顶层 `status`。plan 现在的判别字段与 owner 真源一致。

### G-002（高）— 全局 "仅允许 ok" 与 skip 分支冲突 → **CLOSED**

- §5.1 L139 已把统一 status gate 拆成 per-command 允许集合：download `Literal["ok","downloaded","skipped","cancelled"]` 但仅 `ok` 可继续；process `Literal["ok","cancelled"]` 但仅 `ok` 可继续；upload material 仅 `{ok, skipped}` 可继续，且 `skipped` 强制 stable document ID + repository meta/primary SHA 等于 plan material identity。前轮冲突的 "acceptance 仅允许 `ok` 继续" 全局表述已被删除，无双写残留。
- §13 L784 的 price material stop condition 已改为按允许集合表述；§14 L817 新增 residual，记录 upload owner status 在 production 是开放字符串、新状态必须安全停机且不得静默映射到 ok/skip。
- **Owner 交叉核对**：download 顶层 status 由 `sec_download_workflow.py:519` 产出 `ok`/`cancelled`；process 由 `sec_process_workflow.py:630` 产出 `ok`/`cancelled`。plan 的 download Literal 比 owner 实际可达值域宽（含 `downloaded`/`skipped`，来自 `cli/commands/fins.py:235-236` 的成功白名单），但这是**安全方向**的保守闭集——多余成员不可继续、其余一律拒绝，不构成缺陷。

### G-003（中）— process 行内 `quality` 非可信前缀 → **CLOSED**

- §5.1 L134 的 `ProcessCommandEvidence` 已删除 `quality`，仅保留逐文档 `document_id/source_kind/status`，并明写 "stdout-derived quality 不进入 evidence"。
- §5.1 L136 已把 process 行内可信字段收窄到 "**只到 document_id**"，其后的行内 status/reason/form/quality 一律 opaque；`source_kind/status` 仍由六节派生。
- §5.2 L153 指定 quality 唯一来自 `ProcessedDocumentRepositoryProtocol` 状态指纹并与 source inventory 闭合；§9 L376 已要求构造 `reason="... | quality=fake"` 的注入回归；§13 L781 与 §14 L818 同步。
- **Owner 交叉核对**：`quality` 确可经该 protocol 取得——`list_processed_documents` 返回 `DocumentSummary`，其 `quality: str = "full"`（`dayu/fins/domain/document_models.py:530-547`），写入路径见 `_fs_processed_core.py:338`。属既有能力，未新增依赖，与 §5.2 L154 源清单契约已有的 quality 读取同源，无第二真源。

### MiMo new L-1（低）— 空 `form=` 触发 normalizer 异常 → **CLOSED**

- §5.1 L138 明写：download row 的 `form=` 为空时**不得**调用 `normalize_form`，直接产生 `structure_reject`，类别与行号写入 `stdout_summary` 并按预期 fail closed，不得让 `ValueError` 逃逸为 unexpected exit 2。§9 L374 与 §13 L781 同步。
- **Owner 交叉核对**：`normalize_form`（`sec_form_utils.py:52-56`）在 `normalized` 为空时确实 `raise ValueError("form_type 不能为空")`；而 `_format_filing_items`（`cli_formatters.py:421`）在 `item.form_type` 为 None 时输出 `form=`（空值），二者叠加确实可达。plan 的前置分类拦截正确且必要。

### MiMo new L-2（低）— upload sparse grammar 未枚举 → **CLOSED**

- §5.1 L137 新增完整 upload grammar：五行必需有序（`上传材料结果 → - pipeline → - ticker → - status → - material_action`），随后 15 个固定顺序可选行可缺席但不得重排/重复，`files:` 必需唯一且在全部可选行之后，其后 file rows 全部 opaque。§9 L375 与 §13 L781 同步。
- **Owner 交叉核对**：与 `_format_upload_material_result`（`cli_formatters.py:766-798`）逐项比对——必需五行顺序完全一致；可选字段序列 `form_type, material_name, company_id, company_name, document_id, internal_document_id, primary_document, uploaded_files, document_version, source_fingerprint, filing_date, report_date, overwrite, skip_reason, message` 共 15 项，与 plan 枚举**逐项同序同名**；`files:` 确在其后。缺席规则由 `_append_optional_field_lines`（`:1035-1045`）的 `None`/`""` 跳过语义支撑，与 plan "按 owner 空值规则缺席" 一致。

### MiMo open question — `material_action=delete/unknown` → **CLOSED**

§5.1 L134、§5.2 L152、§8.1 L271、§9 L375、§13 L784 五处均明确 delete/unknown action fail closed。本 plan 不传 `--action`，owner 自动判定不可能返回 delete（`docling_upload_service.py:909-914`），该 gate 是防御性且无副作用。

---

## 3. 本轮附带确认（无 finding）

- §12 裁决表 L761-768 六行与 fix artifact 的 finding mapping 完全对应，无遗漏 ID、无 "统计为 0" 的越权声明；表下方明确保留 "final corrective dual plan re-review 尚未运行，不能写 open H/M/L=0 或 plan accepted"。
- §9 实施 allowlist 保持精确六文件，本轮未扩大；production delta 仍限于 C-001 的 `_format_download_result` 单行。
- §14 residual 新增两条（upload 开放 status、process optional tail 未版本化），均有对应的安全停机路径与回归测试要求，不是被搁置的风险。
- 前轮已闭合的 F-001~F-008 与 C-001 相关文本本轮未被撤销或弱化（抽查 L112 title anchor、L126 env policy、L130 receipt writer、L136 六节派生、L138 accession 正字法、L148 status 行，均保持）。

---

## 4. Open questions

无。前轮两个 open question 已由本次修订直接回答：`owner_status` 命名已在 download/upload/process 三处统一；§6 质量 rubric 不依赖 process stdout 的 quality（§5.2 L153/L154 均走仓储协议）。

---

## 5. Residual risks and tracking destination

本轮不新增 residual。plan §14 现有条目已覆盖全部已知残余风险，跟踪去向明确：

| 残余风险 | 跟踪去向 |
|---|---|
| upload owner status 是开放字符串，未来新增合法状态 | §14 L817；只允许 ok/skipped，新状态安全停机并重新 plan |
| process optional parts 位置/内容未版本化，quality 前有自由 reason | §14 L818；stdout 只收 document_id，quality 走 repository 真源，reason 注入回归测试 |
| owner formatter drift、第三方 stdout 通道、opaque tail 不可审计、fresh workspace 来源不变量、v3 不兼容、stale fixture lock | §14 既有条目，本轮无变化 |

---

## 6. Final plan review conclusion

**PASS**

- Open High：0
- Open Medium：0
- Open Low：0
- G-001 / G-002 / G-003 / MiMo new L-1 / MiMo new L-2 / MiMo open question：全部 CLOSED IN PLAN，且闭合所依赖的 owner 事实已逐项交叉核对通过

本次 final corrective revision 的修正是精确的最小收敛：把 upload 的 action 与 status 正交建模（G-001/G-002）、把 process 行内可信边界收窄到 `document_id` 并让 quality 回归 `ProcessedDocumentRepositoryProtocol` 既有真源（G-003）、把空 form 的异常路径提前分类拦截（L-1）、把 upload sparse grammar 完整枚举（L-2）。四处都没有新增抽象、没有扩大实施 allowlist、没有增加 production delta，也没有撤销前两轮已闭合的任何契约。

从可实施性看，plan 现在对实施 Agent 是 code-generation-ready 的：三类 stdout 的 grammar 边界（必需行、固定顺序可选行、section header、可信前缀、opaque tail）逐一枚举且与 owner formatter 实现逐字段对齐；三类命令的 status gate 各自独立且值域封闭；evidence union 闭集并绑定 `_PHASE_SCHEMA_VERSION`；每条契约都有对应的 §9 断言与 §13 stop condition。

DeepSeek 侧本轮无 open findings。是否恢复 Slice 2 implementation 由 Controller 在 MiMo 同 revision final corrective re-review 也 PASS 后裁决。**Slice 5 / live 仍为 NOT AUTHORIZED / NOT RUN**，本 review 不构成任何 live 授权。
