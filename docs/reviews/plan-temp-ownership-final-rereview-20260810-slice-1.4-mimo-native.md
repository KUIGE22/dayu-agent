# Slice 1.4 temp-ownership final independent plan re-review（MiM Native，round 10）

## 审查范围与方法

- **本机时间**：2026-08-10 23:43:20 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，重点复核 temp-ownership fix（`plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`，ACCEPTED/FIXED-IN-PLAN）后的全部 focus area 闭合性。
- **已读真源**：根 `AGENTS.md`、master plan 当前 Slice 1.4（S14-CTRL-01..13 全部修订版）、`docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-terra.md`（Terra FAIL，S14-TO-THREAD-FINAL-01/02，2M）、`docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-mimo-native.md`（MiM Native PASS，open 0/0/0）、`docs/reviews/plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`（temp-ownership fix，ACCEPTED/FIXED-IN-PLAN）；并只读核验了 `cn_download_filing_workflow.py`（三段边界、`_unlink_temp_pdf`、stage-B `asyncio.to_thread`）与 S14-CTRL-12 网络边界契约、exhaustive 表、completeness gate、residual 列表。
- **边界**：仅新增本 artifact；未改 plan、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker、commit/push/PR。

## 已验证的假设

1. `provider_download_timeout_seconds` 是阶段 A 唯一 hard-bounded timeout，不覆盖阶段 B/C。
2. 阶段 B（`pdf_path.read_bytes` + 默认 Docling converter）在 begin_batch 前执行、worker 零 repo/batch/token 句柄、不承诺 interruptible/有限结束。
3. 阶段 C 无独立 hard duration timeout、无外部 await/Docling/provider I/O、含 precommit cancel_checker fence、commit-start 前 rollback/commit-start 后 journal recovery。
4. SEC streaming exception（无阶段 B，await-based 流式例外）与阶段 A provider timeout 覆盖逻辑一致。
5. 此前所有 closure（replace_source_meta / per-filing terminal / delete_entry S3 / upload overwrite / S14-CLOSURE-01/02 / S14-REREVIEW-02/03 / exact toolset names / S14-TERMINAL-01/02 / S14-TERMINAL-FINAL-01 / S14-TO-THREAD-FINAL-01/02）无回归。

## 复核：Focus Area 逐项验证

### Focus 1：active allowed/test scope no stale CN all-window token

| 项目 | 证据 | 结论 |
|------|------|------|
| Terra 原始 finding | Terra S14-TO-THREAD-FINAL-01 指出 plan:1452-1455 仍断言"SEC/CN list/download/Docling 期间恰有同一 active token + per-filing timeout" | 已 ACCEPTED |
| F1 闭合位置 | plan:492-500 明确"不再断言"旧 CN 全窗口 token 语义；plan:2254 S14-CTRL-10 disposition 表记录 ACCEPTED/FIXED-IN-PLAN | 闭合 |
| 当前 Allowed/test 清单（plan:1508-1521） | 精确区分：(1) SEC streaming 例外仍同 token；(2) CN 阶段 A/B 无 token、阶段 C 才单 token；(3) 阶段 A timeout 零 begin/零 publish；(4) 阶段 B 取消仅观测不声称终止；(5) 阶段 C commit-start 前后收敛；(6) 不把 SEC streaming 例外泛化给 CN | 与三段边界一致 |
| source code 事实 | `cn_download_filing_workflow.py:220-221`（阶段 B `read_bytes`）在 `begin_batch` 前；`:391-395`（Docling `to_thread`）在 begin_batch 前；阶段 C 才 begin | 与 plan 一致 |

**结论**：F1 已正确闭合。allowed/test 清单不再包含任何 stale CN 全窗口 token/timeout 断言。

### Focus 2：`_read_and_unlink_temp_pdf` single worker owner plus outer best-effort retry

| 项目 | 证据 | 结论 |
|------|------|------|
| 新增函数签名 | plan:2729-2730：`_read_and_unlink_temp_pdf(path: Path, *, module: str) -> bytes`，worker 读取 bytes 并在自身 `finally` 幂等 `unlink`（`missing_ok=True`） | 为 to-be-implemented 设计契约，code-generation-ready |
| 当前 `_unlink_temp_pdf` | `cn_download_filing_workflow.py:775-781`：只做 `path.unlink(missing_ok=True)` + OSError warn | 旧实现，plan 设计不矛盾——新函数包裹 read + cleanup |
| worker finally 覆盖 | plan:503-504：worker 自身 `finally` 幂等 unlink；outer cancel 也 best-effort unlink | 双重清理保证：POSIX 可撤目录项，Windows worker finally 重试 |
| Docling 只收已读 bytes | plan:507-508：Docling converter 只接收 `pdf_bytes`，不再持有 pdf path | 与阶段 B zero-repo/batch 一致 |
| 清理逻辑只接收 path/日志 | plan:2739：该清理逻辑只接收 path/日志输入，不接触仓储/batch/token | 无泄露 |

**结论**：F2 已正确闭合。单一 worker owner + outer best-effort retry 契约明确、不依赖隐式 finally。

### Focus 3：actual inner future retains bounded permit after outer cancellation

| 项目 | 证据 | 结论 |
|------|------|------|
| bounded gate 契约 | plan:2740-2744：阶段 B 所有 `to_thread` 经模块私有 bounded gate 执行，容量建议 1 | code-generation-ready |
| permit 绑定 inner future | plan:2743-2744：用 `asyncio.shield`/完成回调保证 outer 取消后仍由 inner 真正完成时 release permit | 关键约束：不取消即提前释放 |
| 禁止无限后台 worker | plan:2744："禁止取消即提前释放导致无限后台 worker" | 明确写入 stop condition |
| capacity residual | plan:2746-2747：worker 永不结束时 temp 文件与 permit 一并保留，上限 = 配置容量（每进程），不泄漏第二 writer | residual 有界 |

**结论**：F3 已正确闭合。permit 绑定 inner future 而非 outer await 是正确设计；取消不提前释放 permit 是关键安全约束。

### Focus 4：exact owned stale-temp sweep is safe/narrow/serialized and only before any active stage-B worker

| 项目 | 证据 | 结论 |
|------|------|------|
| 调用时机 | plan:2748-2749：在任何 CN/HK provider work 前、且无 active stage-B worker 时执行 | 正确：避免与正在读取的 worker 竞争 |
| owner | plan:2749-2750：单一 runtime/process 私有 helper（模块私有函数） | 单一 owner，无竞态 |
| lock | plan:2750-2751：持 exact temp-dir cleanup lock（`{tempdir}/dayu_cn_downloads/.cleanup.lock` 非阻塞 flock） | 串行化、非阻塞 |
| 范围限制 | plan:2752-2753：只限 `{tempdir}/dayu_cn_downloads/cninfo_*.pdf` 与 `dayu_hk_downloads/hkexnews_*.pdf` | 精确 glob，不广泛 |
| 文件过滤 | plan:2753-2754：只删 regular 非 symlink 且 mtime 早于模块级有限 stale 阈值 | 三重过滤 |
| fail-safe | plan:2754-2755：unknown/symlink/lock busy fail-safe 不删并记 metrics | 安全 |
| 与 CN pipeline 构造绑定 | plan:1416-1418（Allowed）：CN pipeline 构造（startup）单次调用阶段 B 私有 startup stale-temp sweep helper | 只在启动时执行一次 |

**结论**：F4 已正确闭合。sweep 足够 narrow/serialized，且只在无 active stage-B worker 前执行。

### Focus 5：never-ending worker/file count bounded by configured capacity

| 项目 | 证据 | 结论 |
|------|------|------|
| bounded gate 容量 | plan:2741-2742：模块级私有有限正数默认容量，建议 `1` | 有界 |
| worker 永不结束时 | plan:2746-2747：temp 文件与 permit 一并保留，上限 = 配置容量/进程 | temp + permit 双保留 |
| 不泄漏第二 writer | plan:2747：不泄漏第二 writer、不无限增长 | 明确约束 |
| stale-temp sweep 收敛 | plan:2763-2764：由 startup stale-temp sweep 收敛（仅删 owned stale） | 长期收敛机制 |
| residual 降级 | plan:2757-2763：CN 阶段 B 为无界 CPU/IO 工作但不持有 token/batch/repository；后续 filing 只在容量可用时可启动 | residual 诚实降级 |

**结论**：F5 已正确闭合。worker/file 上限 = 配置容量/进程，不会无限增长。

### Focus 6：stage A/B/C and all prior S3 closures remain coherent

| Closure | 证据 | 结论 |
|---------|------|------|
| replace_source_meta AUTO_ATOMIC_ALLOWED | plan:2479 表 #12b + completeness gate :2603-2625 | 无回归 |
| per-filing terminal state machine | plan:2675-2700：PENDING/COMPLETED/FAILED、commit-start 决策点 | 无回归 |
| delete_entry S3 stage-delete | plan:2797-2813：S14-CTRL-13 destructive 状态机 | 无回归 |
| upload overwrite in execute_upload batch | plan:2590-2601：overwrite reset 移入 per-document batch | 无回归 |
| S14-CLOSURE-01 同-core ingestion 链 | plan:2441-2460：Host ingestion factory 同-core 唯一链 | 无回归 |
| S14-REREVIEW-02/03 | plan:2240-2242：runtime owner + inventory contraction | 无回归 |
| exact toolset names | plan S14-CTRL-11（fins/ingestion exact name fail-closed） | 无回归 |
| S14-TO-THREAD-FINAL-01/02 | plan:2328-2342：temp-ownership fix 后 ACCEPTED/FIXED-IN-PLAN | 已闭合 |
| 三段边界（stage A/B/C） | plan:2627-2766：阶段 A 唯一 hard-bounded、阶段 B 不承诺有限结束、阶段 C 无独立 timeout + cancel fences | 无回归 |

**结论**：所有 prior closures 无回归；三段边界与 temp-ownership fix 在 S14-CTRL-12 内连贯一致。

## Findings

### 无新增 findings。

temp-ownership fix（`plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`）正确实施：
- F1 闭合：active allowed/test 清单已改为三段断言（SEC streaming 例外仍同 token；CN 阶段 A/B 无 token、阶段 C 才单 token；阶段 A timeout 零 begin/零 publish；阶段 B 取消仅观测；阶段 C commit-start 前后收敛）。
- F2 闭合：`_read_and_unlink_temp_pdf` 单一 worker owner + outer cancel best-effort unlink + Docling 只收已读 bytes。
- F3 闭合：bounded gate permit 绑定 inner future（shield/完成回调），outer 取消不提前释放。
- F4 闭合：stale-temp sweep 精确限 temp-dir、只删 owned regular 非 symlink 且 mtime 早于有限阈值、在无 active stage-B worker 前执行、持 exact lock、unknown/symlink/lock busy fail-safe 不删。
- F5 闭合：worker 永不结束时 temp/permit 上限 = 配置容量/进程，由 startup sweep 收敛。
- 所有 prior closures 无回归。

## Open Questions

无。所有 focus area 均可由当前 master plan 与源码直接确认。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| CN 阶段 B（read_bytes + Docling）为无界 CPU/IO 工作，不持有任何 token/batch/repository | 低（已知 residual） | 由 cancel_checker + warning/metrics 缓解；bounded gate 限制并发；后续 filing 只在容量可用时可启动 |
| commit-start 后同步窗口不可取消 | 低（已知 residual） | 按 S14-CTRL-04 journal/recovery 收敛 |
| outer cancellation 不回收已运行的 Python thread | 低（已知 residual） | 由"worker 不得访问 repo/batch"契约保护仓储一致性 |
| worker 永不结束时 temp 文件与 permit 保留 | 低（已知 residual） | 上限 = 配置容量/进程；startup stale-temp sweep 只删 owned stale |
| 本次是计划审查，未执行 MinIO/fault injection/pyright/coverage/Docker | 低 | implementation gate |

## Final plan review conclusion

**PASS**

**Open H/M/L：0 / 0 / 0。**

temp-ownership fix 正确闭合了 Terra S14-TO-THREAD-FINAL-01（stale CN 全窗口 token/timeout 断言）和 S14-TO-THREAD-FINAL-02（阶段 B 取消后临时 PDF 清理责任未定义）；三段边界、stage A/B/C 和所有 prior S3 closures 无回归；_read_and_unlink_temp_pdf worker owner + outer best-effort retry、bounded gate permit 绑定 inner future、stale-temp sweep 安全/窄/串行化且仅在无 active stage-B worker 前、worker/file 上限 = 配置容量/进程 均已正确规格化。Slice 1.4 满足 Terra + MiM Native 双路 **final dual plan re-review PASS** 条件。
