# Slice 1.4 terminal independent plan re-review（Terra）

## 审查范围

- **本机时间**：2026-08-10 22:54:25 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，重点复核 terminal corrective 对 S14-CORRECTIVE-01/02 的闭合性。
- **已读证据**：根 `AGENTS.md`、master plan 当前 Slice 1.4、Terra/MiM Native 的 final-corrective re-review、`plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md` 与此前 Slice 1.4 fix 历史；并只读核验了 storage、SEC/CN download/rebuild 调用链。
- **边界**：仅新增本 review；未改 plan、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker，未 commit/push/PR。

## 已验证的假设

1. S14-CTRL-12 已把 SEC/CN upload 的 company upsert、overwrite reset，以及 SEC rejection registry 写入纳入表 #1/#12/#2，并规定为 owner 内短 `AUTO_ATOMIC_ALLOWED` batch。
2. S14-CTRL-12 已明确每个 SEC/CN filing 使用独立同-core token，允许覆盖该 filing 的远端 fetch/Docling，但不得跨整个 ticker。
3. S14-CLOSURE-01 的 ingestion factory 同-core 传播、S14-REREVIEW-02/03 的 runtime/startup ownership 与 inventory contraction、exact toolset names 的既有契约，本轮未见计划回退。

但以上正向改动不足以使 terminal gate 通过：下面两项有直接源码反例。

## Findings

### S14-TERMINAL-01-未修复-[高]-admission inventory 仍遗漏绕过 `_execute_with_auto_batch` 的 `replace_source_meta` 生产写路径

- **位置**: master plan S14-CTRL-12 的 exhaustive inventory 表与 completeness gate（plan:2142-2198）。
- **问题类型**: 契约缺失 / 测试缺口。
- **当前写法**: plan:2142-2155 将「全部 `_execute_with_auto_batch` mutation」称为 exhaustive inventory；plan:2187-2197 的 AST gate 也只枚举该调用点。表 #14 更称 manifest helper 仅由 `_upsert_source_document`/`_upsert_processed` 内部调用。
- **反例/失败场景**: S3 模式下执行 SEC 或 CN rebuild。生产 rebuild 会调用 `replace_source_meta`，该入口不经过 `_execute_with_auto_batch`，先直接覆盖 source `meta.json`，再调用会自动 batch 的 manifest upsert。若前一次写成功、后一次 begin/commit 失败，source meta 与 manifest 不一致；若新 meta 收缩 `files`，它也绕过 S14-CTRL-13 要求的 inventory diff/delete-intent 路径。
- **为什么有问题**: 这直接否定「以 storage core 为真源的 exhaustive」及「仅以 `_execute_with_auto_batch` AST 完整性即可阻止遗漏」两个前提。它也说明 AUTO/EXPLICIT 分类无法约束所有跨 repository / inventory 不变量写入；实施者照当前 plan 完成 AST gate 仍会漏掉该真实生产路径。
- **直接证据**:
  - `dayu/fins/storage/_fs_source_document_core.py:323-398` 的公开 `replace_source_meta` 在 :354 直接 `_write_json(meta_path, normalized_meta)`，再在 :356-397 调用 `upsert_filing_manifest` 或 `upsert_material_manifest`；该方法不调用 `_execute_with_auto_batch`。
  - manifest helper 本身在 `dayu/fins/storage/_fs_storage_infra.py:898-917` 通过 `_execute_with_auto_batch`；无 active token 时，前述直接 meta 写已经落到 target（`_ticker_dir_for_write` 在无 token 时返回 target，`_fs_storage_infra.py:1115-1134`），随后才可能另开 batch。
  - `replace_source_meta` 是稳定仓储协议的一部分（`repository_protocols.py:157-165`），且有真实 production callers：CN rebuild `cn_download_rebuild.py:234-239`，SEC rebuild `sec_rebuild_workflow.py:386-404`。CN caller 所构造的 payload 明确含 `files`（`cn_download_rebuild.py:205-239`）。
- **影响**: S14-CORRECTIVE-01 未真正闭合；S3 下可产生 source meta/manifest 不一致，或在 inventory 收缩时留下未受 journal 管理的远端 bytes。现有 AST/unit gate 会错误报告完整。
- **建议改法和验证点**: 把 inventory 真源从「`_execute_with_auto_batch` 调用点」扩展为「storage core 全部公开写入口 + 直接 FileStore/blob 原语 + manifest/inventory helper」。至少把 `replace_source_meta` 与 SEC/CN rebuild callers 加入表、allowlist 与运行期 admission：若它可改变 files inventory，必须由 storage owner 在同一个 owner batch 内完成 old/new diff、delete intents、meta+manifest swap；否则必须明确禁止该路径。AST gate 应断言该完整写入口集合与分类表一一对应，并额外断言每个直接 `put_object`/`delete_entry`/直接 `_write_json` 后再写 manifest 的入口都有显式 batch/inventory disposition。新增 staged-store 的 SEC/CN rebuild 成功、manifest 写失败、files shrink、restart recovery 测试。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### S14-TERMINAL-02-未修复-[高]-per-filing timeout/cancel 没有把正常结束的 `FILING_FAILED` 明确映射为 rollback，且 commit 缺少 deadline 决策点

- **位置**: master plan S14-CTRL-12 网络边界契约（plan:2200-2238）。
- **问题类型**: 状态机漏洞 / 不可直接实施 / 测试缺口。
- **当前写法**: plan:2217-2223 只规定在 `run_download_stream_impl`/`run_cn_download_stream_impl` 新增 keyword-only `per_filing_timeout_seconds`，用 `asyncio.timeout` 包住 begin 到 commit 的窗口，并宣称 timeout/cancel/network error 一律 rollback、零 publish；CN 则保持 `FILING_FAILED` 后继续下一 filing。
- **反例/失败场景**: 单 filing 的下载或 Docling 失败可被现有 async generator 转化为 `FILING_FAILED` 事件后正常 `return`，而非异常。若外围仅按异常 rollback、正常结束 commit（当前 plan 未定义另一种 outcome），已写入 staging 的 PDF/source meta 会被 commit，违反零 publish；CN 随后仍会继续下一个 filing。SEC 也存在同样的正常失败终态，故「SEC 向上传播」并非当前代码事实。另一个边界是 `BatchingRepositoryProtocol.commit_batch()` 为同步方法；`asyncio.timeout` 只能在 await 边界注入取消，不能取消已开始的同步 commit，因此不能无条件承诺 deadline 在 commit 中触发后仍 rollback/零 publish。
- **为什么有问题**: 计划没有指定 transactional terminal-outcome 状态机、失败事件的识别点、commit 前 cancel/deadline fence，或 commit 已开始时的恢复语义；单靠函数签名、默认常量和 `asyncio.timeout` 无法让实现者安全决定 commit/rollback。它同时造成 SEC/CN 的 continue/propagate 描述与现有 generator 行为相矛盾。
- **直接证据**:
  - CN `run_cn_download_single_filing_stream` 在 PDF 下载失败时 yield `FILING_FAILED` 后 :218 正常返回，在 Docling 转换失败时 yield `FILING_FAILED` 后 :412 正常返回（`cn_download_filing_workflow.py:202-218,396-412`）；外层 `run_cn_download_stream_impl` 在 :259-299 仅 `async for` 并继续 candidate 循环，只有抛出的 `CancelledError`/`Exception` 走 :300-324 的异常分支。
  - SEC 单 filing 在 6-K 预取失败、rejected artifact 失败、文件下载失败时同样 yield `FILING_FAILED` 后正常返回（`sec_download_filing_workflow.py:310-323,347-360,460-473`）；外层 `sec_download_workflow.py:425-462` 只消费事件并继续循环。
  - `BatchingRepositoryProtocol.commit_batch`/`rollback_batch` 均为同步 `-> None`（`repository_protocols.py:29-45`），现有实现的 `commit_batch` 也是同步过程（`_fs_storage_infra.py:201-257`）。
- **影响**: S14-CORRECTIVE-02 的核心验收「network error/timeout/cancel rollback 且零 publish」无法由计划保证；实现可能在失败 filing 发布 partial staged metadata/blob，或在 deadline 与 commit 竞争时作出不可恢复的错误决策。
- **建议改法和验证点**: 在两个 outer workflow 中唯一规定一个私有 per-filing transaction state：消费单 filing event 时记录唯一 terminal outcome；`FILING_FAILED`（包括已有 blob/source staging 后失败）、`CancelledError`、`TimeoutError` 和 pre-commit cancel/deadline 均必须 rollback，随后按现有事件契约继续下一 CN/SEC filing，避免凭空改变 SEC 外部语义。只有 `FILING_COMPLETED`/明确 skip 通过最终 cancel/deadline 检查后可进入 commit。明确 commit-start 为不可取消决策点：deadline 在此前触发必须 rollback 零 publish；commit 已开始则按 S14-CTRL-04 journal/recovery 收敛，不能继续声称零 publish。将此私有状态机、参数透传点、`sec_download_workflow.py`/`cn_download_workflow.py`、相关 pipeline/protocol 与测试文件纳入 allowlist；测试必须分别覆盖 SEC/CN 的正常 `FILING_FAILED`、已 stage 后失败、timeout 在 commit 前、cancel 在 commit 前、commit 开始后的恢复，并断言每个 filing 不跨 ticker 且只使用一个 token。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

## Open Questions

无。两项 finding 均由当前公开仓储入口及 SEC/CN generator 的直接控制流证明，不依赖 MinIO 或外部运行环境。

## Residual Risks

- 即使完成上述计划修复，CN Docling 的 `asyncio.to_thread` 不能被中途强杀；应将它保留为资源占用 residual，而不是把 timeout 表述为可中断的 CPU 执行。
- 本次是计划审查，未执行 MinIO/fault-injection/pyright/测试；这些仍应按计划的 implementation gate 验收。

## 无回归复核

| 项目 | 结论 | 计划证据 |
| --- | --- | --- |
| ingestion 同-core 链（S14-CLOSURE-01） | 无回归 | plan:2018-2049 仍固定 runtime → ingestion factory → pipeline 的同一 `batching_repository` 实例。 |
| runtime owner / startup（S14-REREVIEW-02） | 无回归 | plan S14-CTRL-05 与 S14-CTRL-12 保持 `repository_set` 唯一构造和 Host 不见 core 的边界。 |
| inventory contraction（S14-REREVIEW-03） | 无回归但受 finding 01 阻塞 | plan S14-CTRL-13 仍要求 old/new inventory 与 delete intent；`replace_source_meta` 是未纳入该规则的缺口。 |
| exact toolset names | 无回归 | plan S14-CTRL-11 仍以 `fins`/`ingestion` exact name fail-closed。 |

## Final plan review conclusion

**FAIL**

**Open H/M/L：2 / 0 / 0。**

S14-CORRECTIVE-01 的 upload、overwrite reset 与 rejection registry 修复方向成立，但 exhaustive gate 被真实 rebuild metadata 写入口绕过；S14-CORRECTIVE-02 的 per-filing 边界方向成立，但正常 `FILING_FAILED` 与同步 commit 的 terminal-outcome 语义未闭合。完成以上两项最小计划修复并经终审复核前，Slice 1.4 不应进入 implementation gate。
