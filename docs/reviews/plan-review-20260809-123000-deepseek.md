# Plan review — AAPL acceptance Slice 2 code-review-triggered plan fix

- 评审时间：2026-08-09 12:38:37 CST（系统时钟；artifact 文件名按 Controller 指定的 `123000-deepseek` 固定）
- 评审角色：DeepSeek plan re-review（adversarial）
- 基线：`a99322c65aa7aedbfb3ab4516cb36d66311e71ba`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 diff
- 伴随 artifact：`docs/reviews/plan-fix-20260809-121500-codex.md`
- Finding 真源（只读引用，不重复裁决）：`docs/reviews/code-review-20260809-114000-deepseek.md`、`docs/reviews/code-review-20260809-114001-mimo.md`
- 冻结范围：`dayu/`、`utils/`、`tests/`、README 全部未修改；本轮未执行 pytest、pyright、live、网络或付费调用；未派生子 agent
- **结论：FAIL（open High = 3, Medium = 4, Low = 1）**

---

## 1. Reviewed scope

只审两个 artifact：plan 当前 revision 与 12:15 plan-fix。source code reviews 仅用于确认 finding 出处，不重新裁决其 accept/reject。

为了证伪 plan 的 owner 假设，对 `dayu/` 做了**只读**代码事实核对（未修改任何文件）：

- `dayu/fins/cli_formatters.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`、`dayu/cli/dependency_setup.py`
- `dayu/cli/commands/init.py`
- `dayu/log.py`
- `dayu/fins/pipelines/sec_download_workflow.py`、`sec_process_workflow.py`、`sec_form_utils.py`
- `dayu/fins/pipelines/docling_upload_service.py`

---

## 2. Assumptions tested

| # | Plan assumption | 位置 | 结果 |
|---|---|---|---|
| A1 | 固定 `--quiet` 后 stdout 只剩单一 owner formatter 文本，可做 exact 解析 | §4.2 L111、§5.2 L144 | **证伪**（F-002） |
| A2 | `process` owner 输出提供逐文档 `source_kind` | §5.1 L132、§5.2 L146 | **证伪**（F-001） |
| A3 | `upload_material` owner 输出稳定提供 `document_id/source_fingerprint/report_date` | §5.1 L132、§5.2 L145、fix L15 | **证伪**（F-003） |
| A4 | owner formatter 是可被 exact grammar 描述的封闭语法 | §4.2 L111 | **部分证伪**（F-004） |
| A5 | `process` 一定输出 `materials 汇总` 行 | §5.2 L146 | **证伪**（F-005） |
| A6 | plan argv 的 `DEF14A` 与 owner discovery `form` 值可直接闭合 | §5.2 L149、§9 L363 | **证伪**（F-006） |
| A7 | `fil_<SEC-accession>` 可作为 accession 的严格唯一反解形状 | §5.1 L132 | **证伪**（F-007） |
| A8 | exit 0 不等于成功；`cancelled` 已被覆盖 | §5.2 L144/L146 | **通过**（`_FINS_DOWNLOAD_SUCCESS_STATUSES`/`_FINS_PROCESS_SUCCESS_STATUSES` 含 `cancelled`，plan 已显式 stop） |
| A9 | `dayu.cli` 无 `--json`，`--quiet` 存在 | §5.2 L144 | **通过**（`arg_parsing.py:119`；无 `--json`） |
| A10 | `PhaseReceipt v3 CommandRecord` 字段充分且非 God schema | §5.1 L130-134 | **通过**（见 §5 non-findings） |
| A11 | evaluator 是评分唯一真源，Slice 2 allowlist 已含 evaluator | §4.2 L108/L110、§9 L344/L350 | **通过** |
| A12 | Popen/timeout/fixture lock 协议完整 | §7 L253-254、§4.1 L94 | **通过** |
| A13 | verify 的文件写入 allowlist 内部自洽 | §5.1 L129 vs §5.4 L182 | **证伪**（F-008） |

---

## 3. Findings

### F-001-未修复-[高]-`process` owner formatter 从不输出 `source_kind`，`ProcessCommandEvidence` 该字段在计划 ingress 下不可得

- **位置**：§5.1 L132（`ProcessCommandEvidence` … 逐文档 `document_id/source_kind/status/quality`）、§5.2 L146、§9 L363、fix artifact L72
- **问题类型**：契约缺失 / 不可直接实施（owner 事实错误）
- **当前写法**：plan 把 `source_kind` 列为 `ProcessCommandEvidence` 的必填逐文档字段，并要求由 `--quiet` 后的 owner formatter 文本严格解析得到；未知/缺失字段一律 fail closed。
- **反例/失败场景**：live `process` 成功返回，parser 在每条文档行上找不到 `source_kind=`，按 plan 的 "missing → fail closed" 规则在**任何付费 write 之前**停机。100% 复现，不是边缘情况。
- **为什么有问题**：`dayu/fins/cli_formatters.py:990-1019` 的 `_format_process_items()` 通过 `_collect_optional_parts()` 只渲染 `reason / form_type / fiscal_year / quality / has_xbrl / section_count / table_count / skip_reason`——**不含 `source_kind`**。`source_kind` 在该文件中仅出现于 `format_process_stream_event_line()`（L153-164）与 coercer（L822）。而 stream event 行经 `dayu/cli/commands/fins.py:339-341` 走 `Log.info`/`Log.verbose`，`--quiet` 将日志级别设为 ERROR（`dayu/cli/arg_parsing.py:119`），恰好把这条唯一携带 `source_kind` 的输出抹掉。即 plan 的两个要求（固定 `--quiet` + 解析 `source_kind`）在 owner 事实下**互斥**。
- **直接证据**：
  - `dayu/fins/cli_formatters.py:1003-1015`（`_collect_optional_parts` 字段清单，无 `source_kind`）
  - `dayu/fins/cli_formatters.py:154`、`:164`（`source_kind` 只在 stream event 行）
  - `dayu/cli/commands/fins.py:339-341`（progress 走 `Log.info`/`Log.verbose`）
  - `dayu/cli/arg_parsing.py:119`（`--quiet` → ERROR）
- **影响**：实施 Agent 要么发现无法实现而 STOP（浪费一个 slice），要么为了让测试通过而放宽 parser 或私自把 `source_kind` 置 null——后者直接违反 plan §13 "不得 fallback、宽 regex" 的 stop condition，并让 process 阶段的 filing/material 区分失去证据。
- **建议改法和验证点**：`source_kind` 改为**由 section header 结构性派生**，而不是逐行字段解析。`_format_process_result()`（L887-898）固定输出六个分节标题：`成功处理的 filings:` / `跳过的 filings:` / `失败的 filings:` / `成功处理的 materials:` / `跳过的 materials:` / `失败的 materials:`。plan 应显式写明：parser 按这六个固定 section header 建立 `(source_kind, status)` 二元组，section 内每行只解析 `document_id` 与 `| quality=`；`status` 同样由 section 派生而非行内字段。同时把 "六个 section header 必须全部出现且顺序固定" 写成 fail-closed 条件。验证点：用真实 `format_fins_cli_result(FinsCommandName.PROCESS, ...)` 构造含 filing+material 且三种 status 齐备的样本，断言 evidence 的 `source_kind/status` 全部由 section 派生正确，并断言缺任一 section header 时 fail closed。
- **修复风险（低/中/高）**：低（纯 plan 文本收敛到已验证的 owner 结构）
- **严重程度**：**高**

---

### F-002-未修复-[高]-`--quiet` 只抑制 dayu 自身日志；第三方 stdout 噪声未被控制，而 plan 明确不要求 `init`

- **位置**：§4.2 L111、§5.1 L122（"不要求用户先 `init`"）、§5.2 L144、§7 L254（Popen 规格）、§13 L724
- **问题类型**：架构边界 / 隐藏假设 / 不可直接实施
- **当前写法**：plan 断言固定一个 `--quiet` 即可 "隔离默认写入 stdout 的 INFO 日志"，随后对**完整 stdout** 做 exact grammar 解析，任何 unknown/noise 行 fail closed；同时在 §5.1 L122 显式声明 "不要求用户先 `init`"；§7 L254 规定 `Popen` 固定 `cwd/stdin/shell=False`，但**未规定 `env`**。
- **反例/失败场景**：`process` 阶段拉起 docling/OCR/transformers 栈。若运行终端未配置第三方降噪环境变量，tqdm 进度条与 HF/transformers 提示会写入被 pipe 捕获的 stdout。parser 命中 unknown 行 → 在**已完成三组付费前 download + material import 之后**安全停机。这不是理论风险：整个降噪机制的唯一配置入口就是 `init`，而 plan 恰好声明不跑 `init`。
- **为什么有问题**：`dayu/log.py` 只治理 dayu 自己的 logger（ERROR 以下 → stdout，ERROR 以上 → stderr），`--quiet` 把 dayu 日志压到 ERROR 因而离开 stdout——这部分 plan 判断正确。但第三方库输出由 `TQDM_DISABLE=1`、`HF_HUB_DISABLE_PROGRESS_BARS=1`、`TRANSFORMERS_VERBOSITY=error` 三个环境变量控制，它们**只**由 `dayu-cli init` 写入用户 shell profile（`dayu/cli/commands/init.py:428-432` 的 `_THIRD_PARTY_OUTPUT_QUIET_ENV`，`:596-632` 的 `_configure_third_party_output_quiet_env`）。`dayu/docling_runtime.py` 与 `dayu/log.py` 均不在运行时兜底设置它们（只读核对：`docling_runtime.py` 中仅 `DOCLING_DEVICE_ENV` 一处 `os.environ`）。因此 plan 同时持有 "不要求 init" + "exact fail-closed stdout parser" + "Popen 不控制 env" 三条，构成可证伪的组合。
- **直接证据**：
  - `dayu/cli/commands/init.py:428-432`（三个降噪变量的唯一定义处）
  - `dayu/cli/commands/init.py:596-632`（唯一写入路径，经 `_persist_env_var` 落到 shell profile）
  - plan §5.1 L122 "不要求用户先 `init`"
  - plan §7 L254 Popen 规格只锁 `cwd`/`stdin`/`shell`，无 `env`
  - `dayu/log.py`（`_ALWAYS_WARNING_LOGGERS` 只覆盖 logging 体系，不覆盖 tqdm/HF 直写 stdout）
- **影响**：live run 在最贵的阶段之后、付费 write 之前不可复现地停机；operator 无法从 receipt 区分 "owner 格式漂移"（真安全停机）与 "宿主环境缺降噪变量"（伪停机）。若实施 Agent 为绕过而放宽 parser，则同时破坏 F-001/F-004 的安全语义。
- **建议改法和验证点**：在 §7 Popen 规格中把 `env` 提升为显式契约：`Popen` 传入**显式构造**的 environment，在继承所需 key（含三个 credential name）之外，强制设置 `TQDM_DISABLE=1`、`HF_HUB_DISABLE_PROGRESS_BARS=1`、`TRANSFORMERS_VERBOSITY=error`；这三个 key/value 进入 `AcceptancePlan` fingerprint（与 `termination_grace_seconds` 同等待遇），并在 §13 加入 "子进程 env 未包含这三项降噪设置" 的 stop condition。**不得**为此修改 `dayu/`——这是 acceptance harness 侧的 subprocess 构造，不越界。验证点：Popen 测试除现有 cwd/stdin/shell 断言外，增加 env 断言；并增加一个 stdout 前置注入 tqdm 样式噪声行的用例，断言在**未设置**降噪 env 的对照分支中 fail closed、在设置后 happy path 通过。
- **修复风险（低/中/高）**：低
- **严重程度**：**高**

---

### F-003-未修复-[高]-§8.1 的 `skip` 幂等重试语义与 §5.1 的 material evidence 必填字段互相矛盾

- **位置**：§5.1 L132（`MaterialImportCommandEvidence` 必填 `document_id/source_fingerprint/report_date`）、§5.2 L145、§8.1 L264（"重试仅能用 … 现有 upload 自动 create/update/skip 语义"）、fix artifact L15/L71
- **问题类型**：状态机漏洞 / 契约缺失 / 恢复路径不可达
- **当前写法**：`MaterialImportCommandEvidence` 被定义为 frozen strict、unknown/missing 全拒的结构，必须记录 owner status、`document_id`、`source_fingerprint`、`report_date` 并与 `plan.price_material_sha256` 闭合；同时 §8.1 规定 import 失败后的重试路径**依赖** owner 的 `create/update/skip` 幂等语义。
- **反例/失败场景**：import 因瞬时原因失败后按 §8.1 重跑同一 plan。owner 判定 material 已存在、返回 `material_action=skip`。`_format_upload_material_result()` 通过 `_append_optional_field_lines()` 渲染可选字段，而该 helper 在 `value is None or value == ""` 时**直接跳过整行**（`dayu/fins/cli_formatters.py:1042-1045`）。skip 路径下 `source_fingerprint`（或 `report_date`）可为 `None`，对应行根本不出现在 stdout。strict parser 判 "missing → fail closed"，恢复路径被自身的证据契约堵死。
- **为什么有问题**：plan 把 "owner 一定会输出这三个字段" 当作既成事实（fix artifact L15 直接写 "upload_material 提供 document_id/source_fingerprint/report_date"），但 owner 的实际契约是**条件输出**。这使 §8.1 承诺的恢复能力在最常见的重试形态（skip）下不可达，且失败表现为一个语义误导的 "格式漂移" 停机。
- **直接证据**：
  - `dayu/fins/cli_formatters.py:1035-1045`（`_append_optional_field_lines`：`None`/`""` 跳过整行）
  - `dayu/fins/cli_formatters.py:766-798`（`_format_upload_material_result` 把 `document_id`/`source_fingerprint`/`report_date` 全部放进可选字段列表）
  - `dayu/fins/cli_formatters.py:731-763`（`_coerce_upload_material_result` 用 `_first_non_empty_text`，允许 `None`）
  - plan §8.1 L264 明确依赖 skip 语义
- **影响**：单次 live run 的成本已由三组 SEC download 支付；import 重试失败即整轮作废并需重新 `prepare`（新 run-id、新 fingerprint、重跑 download）。这正是 plan §8.1 想避免的结果。
- **建议改法和验证点**：把 `MaterialImportCommandEvidence` 的字段必填性**按 owner `material_action` 判别**，而不是无条件必填：(1) `create`/`update` 分支保持三字段必填；(2) `skip` 分支允许 `source_fingerprint`/`report_date` 为 null，但此时**必须**由仓储协议侧（`DocumentBlobRepositoryProtocol` 读得的 primary file SHA-256）单独完成与 `plan.price_material_sha256` 的闭合——plan §5.2 L145 已要求读取 repository primary SHA，把它提升为 skip 分支的唯一权威闭合点即可，不新增能力。同时把 `material_action` 本身加入 evidence 的必填 Literal 字段（owner 在 `_format_upload_material_result` L774 无条件输出 `- material_action:`，可安全 exact 解析）。§8.1 L264 补一句指向该判别规则。验证点：用真实 `format_fins_cli_result(FinsCommandName.UPLOAD_MATERIAL, ...)` 分别构造 `create` 与 `skip`（后者省略 `source_fingerprint`/`report_date` 行）两份 stdout，断言 create 走三字段闭合、skip 走 repository primary SHA 闭合且均不 fail closed；再断言 skip 且 repository primary SHA ≠ `plan.price_material_sha256` 时 fail closed。
- **修复风险（低/中/高）**：低
- **严重程度**：**高**

---

### F-004-未修复-[中]-owner formatter 把网络/SEC 来源的自由文本原样内插进结构化行，exact line grammar 与 warning count 都不成立

- **位置**：§4.2 L111（"exact 严格 ingress"）、§5.1 L133（"owner 原始 warning/reason/message/files 文本不进入 evidence，只有 warning count"）、§14 residual L755
- **问题类型**：最佳实践偏离 / 契约缺失（把不封闭语法当封闭语法）
- **当前写法**：plan 把 `format_fins_cli_result` 的完整文本当作可以写出 exact grammar 的封闭语法，并要求从中稳定得出 `warning count` 与按 `|` 分段的 discovery rows；把格式漂移列为 residual（L755）但仍假定语法本身是良定义的。
- **反例/失败场景**：某个 filing 下载失败，SEC/HTTP 返回的错误文本被带入 `reason_message`。`_format_filing_items()` 直接把它内插进 `... | reason={reason} | message={message}`（`cli_formatters.py:421-428`），**未经 `_format_value_inline` 的空白折叠/截断**。若该文本含换行，一条 filing 行会裂成多行，其续行既不匹配 `  - ` 条目语法也不匹配 section header → unknown line → fail closed。若含 ` | `，字段分段直接错位。warnings 同理：`_format_download_result()` L393-396 按 `  - {warning}` 原样内插 raw warning 文本，含换行即令 "warning count" 变成不可靠计数。
- **为什么有问题**：这不是 "未来 owner 改文案" 的 drift（plan 已作为 residual 接受），而是**当前语法在当前实现下就非封闭**：注入源是网络错误消息，不受 acceptance harness 控制。plan §5.1 L133 承诺 "只保留 warning count" 的降级本身依赖一个不可靠的计数。更关键的是失败面偏斜——恰在需要诊断 download 失败时，parser 最可能因错误文本而停机，operator 拿到的 receipt 只有 digest，没有可读线索。
- **直接证据**：
  - `dayu/fins/cli_formatters.py:421-428`（`_format_filing_items` 原样内插 `reason`/`message`，无 `_format_value_inline`）
  - `dayu/fins/cli_formatters.py:452-501`（`_resolve_download_reason_fields` 从 payload 的 `reason_message`/`message`/`error` 取原始文本，仅做 `strip()`）
  - `dayu/fins/cli_formatters.py:393-396`（warnings 原样内插）
  - 对照：`_append_optional_field_lines` → `_format_value_inline`（L1106-1123）才做空白折叠与 180 字符截断，filing/warning 条目**不走**这条路径
- **影响**：合法的 owner 输出被判为 "格式漂移"；`warning count` 作为 evidence 字段可能失真而无人察觉；诊断能力在最需要时归零。
- **建议改法和验证点**：把 grammar 从 "全文件 exact 行解析" 收敛为 **"section-anchored + 只信任前缀确定的字段"**：(1) parser 以固定 section header 与 `- 汇总:` 行为锚点；(2) filing 条目行只 exact 解析 `|` 之前的 `document_id` 与 `form=`/`filing_date=`/`report_date=`/`status=`/`downloaded_files=`/`skipped_files=`/`failed_files=` 这段**位置与顺序均固定**的前缀，`reason=`/`message=` 之后的剩余部分显式声明为 opaque tail 并整体丢弃（不进 evidence、只进 stdout digest）；(3) `warning count` 不再从文本行计数，改为**不进入 evidence**——plan §5.1 L133 已禁止 warning 文本落盘，把 count 一并移除即可，8-K 缺失的 warning 语义由 discovery rows 的存在性判定承接（§5.2 L149 已有该规则，无需 warning count）。同时在 §14 residual 中把 "owner 自由文本非封闭" 从隐含假设升级为显式记录。验证点：构造 `reason_message` 含换行与 ` | ` 的真实 `DownloadResultData`，断言前缀字段仍被正确解析、opaque tail 被丢弃、evidence 中无任何 owner 文本、且**不**误判为格式漂移；另断言 section header 缺失或 `- 汇总:` 行缺失时仍 fail closed。
- **修复风险（低/中/高）**：中（需要 plan 明确区分 "结构锚点" 与 "opaque tail"，但不改 `dayu/`）
- **严重程度**：**中**

---

### F-005-未修复-[中]-`process` 在 `material_summary.todo=true` 时不输出 `materials 汇总` 行，plan 未规定该替代分支

- **位置**：§5.2 L146（"`process.json` 的单条 command evidence 记录 filing/material summary … 任一 summary `failed>0`/`todo=true` … 停止"）、§5.1 L132、fix artifact L72
- **问题类型**：契约缺失 / 切片不可直接实施
- **当前写法**：plan 要求 evidence 同时记录 filing 与 material 的 `total/processed/skipped/failed/todo`，并把 `todo=true` 作为 semantic failure 停机条件，隐含假设两条 summary 行都存在。
- **反例/失败场景**：`todo=true` 时 `_format_process_result()` 输出的是 `- materials 处理: 未实现（TODO）`，**替代**而非附加 `- materials 汇总: total=…` 行。parser 找不到预期的 materials 汇总行 → 归类为 unknown/missing → fail closed。结果虽然同样是停机，但停机 **reason 是错的**（报 "格式漂移" 而非 "material 处理未实现"），且 evidence 无法记录 plan 要求的 `todo: bool`。
- **为什么有问题**：plan 把 `todo` 建模为 summary 内的一个 boolean 字段，而 owner 把它建模为**互斥的输出分支**。二者结构不同构，strict parser 无法在不知道该分支的情况下正确产出 evidence。
- **直接证据**：`dayu/fins/cli_formatters.py:883-886`
  ```
  if result.material_summary.todo is True:
      lines.append("- materials 处理: 未实现（TODO）")
  else:
      lines.append(_format_process_summary_line("materials", result.material_summary))
  ```
- **影响**：停机原因误分类，operator 依据 §13 会去排查 owner 文案漂移而非 material 处理能力；`ProcessCommandEvidence.todo` 字段在该分支下无法被真实填充。
- **建议改法和验证点**：在 §5.2 L146 显式写明 materials 行有两个合法互斥形态：`- materials 汇总: total=…, processed=…, skipped=…, failed=…`（`todo=false`）与固定字面量 `- materials 处理: 未实现（TODO）`（`todo=true`）；后者命中时 evidence 的 material summary 计数记为 null 而 `todo=true`，并以**语义失败**（非格式漂移）停机。两个形态之外的任何 materials 行仍 fail closed。验证点：分别构造 `todo=true`/`todo=false` 的真实 `ProcessResultData`，断言两条路径都被正确识别、`todo=true` 产出语义失败 stop_reason 且在付费 write 前停止。
- **修复风险（低/中/高）**：低
- **严重程度**：**中**

---

### F-006-未修复-[中]-plan argv 用 `DEF14A`，owner discovery 输出规范化后的 `DEF 14A`，必需表单闭合缺少归一化契约

- **位置**：§5.2 L149（"至少存在一份 10-K、一份 10-Q 和一份 DEF 14A"、"必须分别与 … discovery rows 的最新可用 accession 对齐"）、§9 L363、§10 L479（`--forms 8K DEF14A`）、§5.1 L132（evidence `forms: tuple[str, ...]`）
- **问题类型**：契约缺失 / 不可直接实施
- **当前写法**：plan 在 argv 侧固定 `--forms 8K DEF14A`（无空格简写），在 evidence 侧记录 "计划 forms"，又在 gate 侧要求按 `10-K`/`10-Q`/`DEF 14A` 判定必需 discovery 是否齐备，但**没有**规定两种拼写之间的归一化规则，同时 §13 L724 禁止任何 "宽松" 处理。
- **反例/失败场景**：owner 通过 `dayu/fins/pipelines/sec_form_utils.py:65` 的映射把 `DEF14A` 规范化为 `DEF 14A`，discovery 行输出 `form=DEF 14A`。若实施 Agent 按 plan 字面用 argv token `DEF14A` 做相等比较，DEF 14A 必需表单判定恒为缺失 → 恒 FAIL；若它自行放宽为模糊匹配，则违反 §13 的 "禁止宽 regex"。同理 `10K` vs `10-K`、`8K` vs `8-K`。plan 对这三对拼写都没有给出真源。
- **为什么有问题**：这正是 plan 反复强调要消灭的 "字段/argv 双写不一致"（§5.1 L126），但在 form 维度上自己留了一处双写而未指定 canonical 侧。plan §9 L363 把 "缺 10-K、10-Q 或 DEF 14A discovery" 列为必须断言的用例，该断言在缺归一化契约时会锁死一个错误行为。
- **直接证据**：
  - `dayu/fins/pipelines/sec_form_utils.py:65`：`"DEF14A": "DEF 14A"`
  - `dayu/fins/pipelines/sec_form_utils.py:15`：`DEFAULT_FORMS_US = ["10-K", "20-F", "10-Q", "6-K", "8-K", "DEF 14A", "SC 13D/G"]`
  - `dayu/fins/cli_support.py:318`：`--forms` help 明示 "支持简写，如 10Q 10K DEF14A"
  - plan §10 L479 argv 使用简写；plan §5.2 L149 gate 使用规范名
- **建议改法和验证点**：在 §5.1 evidence 契约中指定 **canonical form 侧为 owner 规范化值**（`10-K`/`10-Q`/`8-K`/`DEF 14A`），并把 argv 简写 → canonical 的映射写成 plan 内的固定、封闭、指纹化查找表（三对，非正则）。`DownloadCommandEvidence.forms` 同时记录 argv token 与 canonical 值两个 tuple，二者必须按该表一一对应，否则 fail closed。§5.2 L149 的必需表单判定与 §9 L363 的断言统一使用 canonical 侧。验证点：断言 `--forms 8K DEF14A` 的 evidence canonical forms 精确为 `("8-K", "DEF 14A")`；构造只含 8-K discovery 的 stdout，断言 DEF 14A 缺失被正确判为硬失败；构造含 `form=DEF 14A` 的 discovery，断言判定为齐备而非缺失。
- **修复风险（低/中/高）**：低
- **严重程度**：**中**

---

### F-007-未修复-[中]-`fil_` 前缀并非 accession 独有形状，"严格反解 accession" 的前提在仓储层不成立

- **位置**：§5.1 L132（"accession 只允许从当前 owner 契约的 `fil_<SEC-accession>` document_id 严格反解"）、§5.2 L150（receipt-derived discovery 与 repository 最新文档不一致 → `source_price_closed` High / FAIL）、§13 L724-725
- **问题类型**：架构边界 / 隐藏假设
- **当前写法**：plan 把 `fil_<SEC-accession>` 当作可以据以严格反解 accession 的唯一 document_id 形状，并在此基础上建立 "receipt discovery 最新 accession" ↔ "repository 最新文档" 的强一致 gate。
- **反例/失败场景**：`fil_` 前缀在 owner 侧至少对应三种不同构造：SEC download 路径产出 `fil_<accession>`（`sec_download_workflow.py:432`），而 upload 路径产出 `fil_sec_<sha1>`（`docling_upload_service.py:1053-1054`）与 `fil_cn_<sha1>`（`:1014-1015`）。plan 的 strict 反解若只按 `fil_` 剥前缀，会把 `fil_sec_<sha1>` 误解析成 accession `sec_<sha1>`，进而与 discovery 侧比较得到一个语义无意义的 "不一致" → 产生假的 `source_price_closed` High/FAIL。
- **为什么有问题**：本次 run root 的 `data-workspace/` 是全新的，理论上只有 download 来源的 filing——但 plan **从未把这条不变量写下来**，也没有把 price material（`mat_<digest>`，`docling_upload_service.py:864`）排除在 "repository 最新文档" 比较范围之外。gate 的正确性依赖一个未声明的隐含前提，任何后续 slice 或恢复流程引入 upload 来源的 filing 都会静默破坏它。
- **直接证据**：
  - `dayu/fins/pipelines/sec_download_workflow.py:432`：`document_id = f"fil_{filing.accession_number}"`
  - `dayu/fins/pipelines/docling_upload_service.py:1053-1054`：`internal_document_id = f"sec_{digest}"` → `document_id = f"fil_{internal_document_id}"`
  - `dayu/fins/pipelines/docling_upload_service.py:1014-1015`：`fil_cn_<digest>`
  - `dayu/fins/pipelines/docling_upload_service.py:864`：`material_document_id = f"mat_{digest}"`
- **影响**：一个本应精确的 High-severity gate 可能产生假阳性 FAIL（浪费整轮 live 成本）或在未来引入 upload filing 时产生假阴性。
- **建议改法和验证点**：(1) 把 accession 反解从 "剥 `fil_` 前缀" 收紧为**对 SEC accession 字面形状的正字法校验**（`\d{10}-\d{2}-\d{6}`，作为 plan 内固定常量），不匹配即拒绝该 document_id 参与 accession 比较；(2) 在 §5.1 显式写下不变量："本 run root 的 `data-workspace/` 只允许由本 plan 的三组 download 与唯一 price material import 产生；出现任何其它来源的 filing document_id 即 fail closed"；(3) 明确 "repository 最新文档" 比较范围仅限 `fil_` 且通过正字法校验的 SEC filing，`mat_*` 不参与。验证点：注入 `fil_sec_<sha1>` 形状的 repository 文档，断言 fail closed 且**不**产生假的 `source_price_closed` 不一致 finding；注入 `mat_*` 断言其被排除在 accession 比较之外。
- **修复风险（低/中/高）**：低
- **严重程度**：**中**

---

### F-008-未修复-[低]-`verify` 的写入 allowlist 与 §5.4 的 `verify.json` terminal receipt 相互矛盾，写者未指明

- **位置**：§5.1 L129（"对 production owner artifacts 只读的 `verify` … 只可原子写本节列明的 harness-owned `source-inventory.json` 与 acceptance receipt"）、§5.4 L182/L209（`phase-receipts/verify.json` 为 terminal receipt）、§5.1 L134（"terminal verify 精确 1 record"）、§9 L354（"`verify` … 允许重复运行"）
- **问题类型**：契约缺失 / open question 未收敛
- **当前写法**：§5.1 把 verify 的写入面收敛为**恰好两个**文件；§5.4 又要求存在第三个 harness-owned 文件 `phase-receipts/verify.json`。plan 未指明该文件由 `run`（把 verify 作为 terminal subprocess 执行后写入）还是由 `verify` 自身写入。
- **反例/失败场景**：实施 Agent 若判定由 `verify` 写入，则违反 §5.1 的两文件 allowlist；若判定由 `run` 写入，则 §9 L354 允许的独立重复 `verify` 不产生/不更新 terminal receipt，而 §5.1 L134 的 "terminal 精确 1 record" 闭合规则对独立 verify 场景失去定义。两种解读都能自圆其说，plan 无法裁决。
- **为什么有问题**：这是本 plan 一贯坚持的 "单一 owner、无歧义" 标准下的一处遗漏；receipt 写者不明确会直接影响 §5.1 L134 的机械闭合规则能否被实现和测试。
- **直接证据**：plan §5.1 L129 与 §5.4 L182 的文本冲突；§9 L354 与 §5.1 L134 的场景覆盖缺口。
- **建议改法和验证点**：在 §5.1 L129 明确 `phase-receipts/verify.json` 由 **`run` 在 terminal verify 子进程退出后写入**，`verify` 自身的写入面保持为 `source-inventory.json` + acceptance receipt 两项；并在 §9 L354 补一句：独立重复 `verify` 不写、不更新 `verify.json`，其幂等性仅由 source-inventory 的同字节校验与 acceptance receipt 的 normalized 稳定性保证。验证点：断言独立 `verify --plan --fingerprint --json` 运行后 `phase-receipts/` 内容字节不变；断言 `run` 路径下 `verify.json` 恰含 1 record。
- **修复风险（低/中/高）**：低
- **严重程度**：**低**

---

## 4. 按 Controller 指定 focus 的逐项裁决

| Focus 项 | 裁决 | 依据 |
|---|---|---|
| PhaseReceipt v3 `CommandRecord`/evidence 字段是否充分 | **不充分**（F-001/F-003/F-005/F-006/F-007） | 四个 evidence 字段在 owner 事实下不可得或不同构 |
| `CommandRecord` 是否成为 God schema | **否**，通过 | 17 个字段全部围绕 "一次子进程执行" 这一单一聚合根；`evidence` 已外提为 discriminated union；`stderr_summary` 有界且与 digest 分工清晰。不构成 God dataclass |
| `--quiet` owner formatter exact fail-closed parser 是否可实现 | **当前规格下不可实现**（F-001/F-002/F-004/F-005） | 需按 F-001/F-004 收敛为 section-anchored 语法 + F-002 的 env 控制后方可实现 |
| discovery external truth / DEF14A | **有缺陷**（F-006/F-007） | 缺 form 归一化真源；accession 反解前提不成立 |
| exit 0 semantic failure | **通过** | `cancelled` 在 owner 成功白名单内（`fins.py:235-238`），plan §5.2 L144/L146 已显式覆盖 status≠ok、summary failed>0、todo |
| material closure | **有缺陷**（F-003） | skip 分支字段缺失 |
| process closure | **有缺陷**（F-001/F-005） | `source_kind` 不可得；todo 分支未建模 |
| scoring truth / evaluator owner | **通过** | §4.2 L108/L110 与 §9 L344/L350 一致；Slice 2 allowlist 已含 evaluator；§13 L735 有对应 stop condition；`utils/investment_agent_acceptance_evaluator.py` 已存在于 Slice 1 accepted 范围 |
| timeout 协议 | **通过** | §7 L253 的 `not_started` / `terminate → 10s grace → kill` / `termination_unconfirmed` 三态完整，`termination_grace_seconds` 进 fingerprint |
| stderr 处理 | **通过** | digest + 有界静态脱敏分类摘要，`_STDERR_SUMMARY_MAX_BYTES=512`，拒绝 sidecar，UTF-8 截断安全性已写明 |
| Popen 规格 | **不完整**（F-002） | `cwd`/`stdin`/`shell` 已锁定，缺 `env` |
| fixture lock | **通过** | §4.1 L94 原子目录创建、非 PII owner.json、fail closed 不破锁、cleanup 不掩盖主异常，均完整 |
| source-inventory contract | **通过**（写者歧义见 F-008） | §5.4 L211 的 canonical bytes / 原子写 / 同字节 overwrite 拒绝 / 同一 frozen object 规格完整 |
| json contracts | **通过** | §9 L349/L369、§10 L452 三子命令 `--json` 必填、删除 dead `json_output`、两模式互斥与 exit 2 用例齐备 |
| allowed files | **通过** | Slice 2 四文件白名单与 fix artifact L77-80 一致；§11 引用的其它测试文件为只读执行，未越界 |
| tests | **基本充分，但会锁死错误行为** | §9 L360-374 用例密度高；但 L363 的 DEF 14A 断言在 F-006 未修前会固化错误比较，L362/L363 的 process/material 断言在 F-001/F-003 未修前不可能通过 |
| stop conditions | **通过，需增补** | §13 覆盖面完整；需按 F-002 增补 "子进程 env 缺降噪设置" 一条 |
| residual | **基本完整，需增补** | §14 已含 owner formatter drift、v3 不兼容、stale lock 等；需增补 "owner 自由文本非封闭"（F-004）与 "data-workspace 来源不变量"（F-007） |

---

## 5. Non-findings（已尝试证伪但 plan 站得住）

- **`AcceptancePlan` 保持 v2 而 `PhaseReceipt` 升 v3**：两者 schema version 相互独立，v2 plan 的语义未因 receipt 结构变化而改变；plan §5.1 L128 已显式说明不因 receipt 修复升 plan 版本。判断正确。
- **run root 进入 fingerprint 从而绑定机器**：§5.1 L127 与 §14 residual 已把该后果显式化为 "跨机必须重新 prepare"，属有意识的 tradeoff，非缺陷。
- **拒绝 v1/v2 receipt 无兼容层**：符合 CLAUDE.md "默认按全新设计处理，不为旧实现保留兼容逻辑"；§14 residual 已记录旧 WIP run 不可恢复的处理方式。
- **`actual_wall_seconds` 用首尾 record 端到端跨度**：正确，避免按 phase duration 求和低估阶段间开销。
- **untracked dirty 严格判定保留（DS M-5 REJECT）**：裁决正确——未跟踪的 `.py` 确实可改变 import 行为。
- **绝对 home 路径 hard gate 只约束 harness-owned outputs**：§5.1 L136 与 §6.1 gate 9 的作用域切分精确，避免了改写生产 artifact 的越界冲动。

---

## 6. Open questions

1. F-002 的降噪 env 是否应与三个 credential name 一样进入 `AcceptancePlan` fingerprint？本 review 建议进入（与 `termination_grace_seconds` 同等待遇），但若 Controller 认为它属于宿主环境而非 plan 身份，需要在 §5.1 显式说明并给出替代的 fail-closed 检测点。
2. F-004 的 opaque tail 边界：`reason=` 之后整体丢弃是否会削弱 §9 L363 "download `summary.failed>0` 停止" 的诊断质量？本 review 认为不会（该判定来自 `- 汇总:` 行而非 filing 条目），但需 Controller 确认对 operator 诊断体验的接受度。
3. F-003 的 skip 分支若同时缺 `document_id`（owner 理论上也可能为 None），repository 侧还能否定位到唯一 price material？plan §5.2 L145 已声明 "不再只按 report_date 选 material"，需要明确 skip 分支的 material 定位键。

---

## 7. Residual risks and tracking destination

| 残余风险 | 建议跟踪去向 |
|---|---|
| owner formatter 的自由文本字段来自网络/SEC，语法非封闭（F-004 修复后仍存在 opaque tail 内容不可审计） | 计入 §14 residual 表；receipt 侧仅保留 stdout digest，operator 需要原文时在保留现场的 run root 中人工检查 |
| 第三方库未来新增直写 stdout 的输出通道（F-002 的三变量不构成完备封闭集） | 计入 §14 residual；格式漂移安全停机 + Slice 2 噪声注入测试作为回归网 |
| `data-workspace/` 单一来源不变量（F-007）依赖流程纪律而非机制强制 | 计入 §14 residual；Slice 2 加 document_id 形状校验测试 |
| plan 已有的 12 项 residual（owner drift、v3 不兼容、stale lock、web 工具、跨文件系统 rename 等） | 保持现状，无需变更 |

---

## 8. Final plan review conclusion

**FAIL**

- Open High：3（F-001、F-002、F-003）
- Open Medium：4（F-004、F-005、F-006、F-007）
- Open Low：1（F-008）

三个 High 的共同根因是同一类问题：本轮 plan fix 为了闭合 code review 的 evidence 缺口，把 `format_fins_cli_result` 的人读文本**当成了结构化 owner 契约**，但未对该 formatter 的实际实现做逐字段核对。结果是 `ProcessCommandEvidence.source_kind` 在计划 ingress 下不可得（F-001）、stdout 清洁度假设不成立（F-002）、strict evidence 契约堵死了 plan 自己承诺的恢复路径（F-003）。这三项都会让实施 Agent 在 Slice 2 中途撞墙，且撞墙时的两个出路（STOP 报 plan gap / 私自放宽 parser）分别意味着返工与违反 §13 stop conditions。

修复方向是收敛而非扩张——四处最小 plan 修正即可：

1. `source_kind`/`status` 改为由六个固定 section header 结构性派生（F-001）。
2. Popen 增加显式 `env` 契约并指纹化三个降噪变量（F-002）。
3. material evidence 字段必填性按 `material_action` 判别，skip 分支以 repository primary SHA 作为唯一闭合点（F-003）。
4. grammar 显式区分 "结构锚点前缀" 与 "opaque tail"，并移除不可靠的 warning count（F-004）。

四个 Medium 中 F-005/F-006/F-007 均为一句话级别的契约补全，F-008 为写者归属澄清。全部修正都不需要触碰 `dayu/`，不引入新抽象，不扩大 Slice 2 白名单。

**Slice 2 不得恢复 implementation 或进入 code re-review**，直到上述 open findings 由 Controller 裁决关闭并完成新一轮双路 plan re-review。Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED**。

本轮 review 未修改任何文件（本 artifact 除外），未执行 pytest / pyright / ruff，未进行任何 live、网络或付费调用，未派生子 agent。
