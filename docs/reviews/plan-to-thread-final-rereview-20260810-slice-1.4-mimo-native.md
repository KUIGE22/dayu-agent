# Slice 1.4 final independent plan re-review after to-thread boundary fix（MiM Native，round 9）

## 审查范围与方法

- **本机时间**：2026-08-10 23:31:24 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，重点复核 to-thread boundary fix（reviewer option 2 诚实三段边界）的闭合性。
- **已读真源**：根 `AGENTS.md`、master plan 当前 Slice 1.4（S14-CTRL-01..13 全部修订版）、`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-terra.md`（FAIL，S14-TERMINAL-FINAL-01，1M）、`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-mimo-native.md`（PASS，open 0/0/0）、`docs/reviews/plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`（to-thread boundary fix，ACCEPTED/FIXED-IN-PLAN）；并只读核验了 S14-CTRL-12 网络边界契约、exhaustive 表、completeness gate、residual 列表与 stop conditions。
- **边界**：仅新增本 artifact；未改 plan、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker、commit/push/PR。

## 已验证的假设

1. `provider_download_timeout_seconds` 是阶段 A 唯一 hard-bounded timeout，不覆盖阶段 B/C。
2. 阶段 B（`pdf_path.read_bytes` + 默认 Docling converter）在 begin_batch 前执行、worker 零 repo/batch/token 句柄、不承诺 interruptible/有限结束。
3. 阶段 C 无独立 hard duration timeout、无外部 await/Docling/provider I/O、含 precommit cancel_checker fence、commit-start 前 rollback/commit-start 后 journal recovery。
4. SEC streaming exception（无阶段 B，await-based 流式例外）与阶段 A provider timeout 覆盖逻辑一致。
5. 此前所有 closure（replace_source_meta / per-filing terminal / delete_entry S3 / upload overwrite / S14-CLOSURE-01/02 / S14-REREVIEW-02/03 / exact toolset names）无回归。

## 复核：Focus Area 逐项验证

### Focus 1：provider_download_timeout_seconds 只 hard-bounds 阶段 A

| 项目 | 证据 | 结论 |
|------|------|------|
| 参数定义 | plan:2559-2563：keyword-only `provider_download_timeout_seconds: float`，模块级私有有限正数默认常量，非法值 fail-fast | 正确 |
| asyncio.timeout 作用域 | plan:2563-2564：`asyncio.timeout(provider_download_timeout_seconds)` 包裹阶段 A 的 await 窗口（SEC 异步 listing/download；CN provider download 的 await） | 仅阶段 A |
| 阶段 C 不受约束 | plan:2543-2544：`provider_download_timeout_seconds` 只约束阶段 A，不约束已开始的阶段 C | 正确 |
| 阶段 A 有限性 | plan:2526-2530：每个独立请求由既有 per-request timeout 有界（SEC `_request_timeout_seconds` 默认 30s；CN `request_timeout_seconds`） | 可证明终止 |
| SEC streaming exception | plan:2548-2569：SEC 无阶段 B，per-filing batch 与下载流共存，timeout 覆盖网络请求与同 token 写窗口；该 timeout 不约束 CN 已开始的阶段 C | 连贯一致 |

**结论**：`provider_download_timeout_seconds` 严格只 hard-bounds 阶段 A，与所有声称一致。

### Focus 2：CN 阶段 B 在 begin_batch 前，零 repo/batch/token 句柄，不承诺 interruptible/有限结束

| 项目 | 证据 | 结论 |
|------|------|------|
| 阶段 B 在 begin_batch 前 | plan:2394-2401：CN 编排三段——阶段 A → 阶段 B（read_bytes :220-221 + Docling :391-395）→ 阶段 C 才 begin explicit batch | 正确 |
| 零 repo/batch/token 句柄 | plan:2533-2534：worker 只接收 immutable/path input，绝不持有 repository/batch/token 句柄 | 正确 |
| 不承诺 interruptible | plan:2535-2536：明确不纳入 hard timeout、不承诺 interruptible/最终有限结束，不用 asyncio.timeout 伪装 | 正确 |
| outer cancellation 丢弃 late result | plan:2537-2538：丢弃 late result 但不宣称回收 worker，记录 warning/metrics/residual | 正确 |
| STOP 条件 | plan:2538-2539：开始此阶段前若实现发现 worker 会持有 repo/batch 句柄 => STOP 并逐名报告 | 保留安全网 |
| 阶段 A/B 无 active token | plan:2551：CN 的阶段 A/B 期间无 active token，token 只在阶段 C | 正确 |

**结论**：阶段 B 的诚实三段边界完全闭合 Terra S14-TERMINAL-FINAL-01 的矛盾。

### Focus 3：CN 阶段 C 无独立 hard duration timeout、无外部 await，含 cancel fences + rollback/journal recovery

| 项目 | 证据 | 结论 |
|------|------|------|
| 无独立 hard duration timeout | plan:2543-2544：阶段 C 无独立 hard duration timeout | 正确 |
| 不含外部 await | plan:2543：不含外部 await/Docling/provider I/O | 正确 |
| cancellation fence | plan:2540-2541：阶段 A/B 成功并经过 cancellation fence（仅 cancel_checker）后才 begin batch | 正确 |
| precommit fence | plan:2545-2546：commit 前再查 cancel_checker（precommit fence） | 正确 |
| commit-start 前 rollback | plan:2546-2547：staging/commit 失败或取消在 commit-start 前 => rollback | 正确 |
| commit-start 后 journal recovery | plan:2547：commit-start 后 => 只按 S14-CTRL-04 journal/recovery 收敛 | 正确 |
| commit_batch 同步不可取消 | plan:2590-2595：commit_batch 同步开始后为不可取消决策点，precommit fence 在 commit 前 | 准确反映同步 API 约束 |

**结论**：阶段 C 的所有契约与 rollback/journal recovery 语义正确、自洽。

### Focus 4：SEC streaming exception 连贯

| 项目 | 证据 | 结论 |
|------|------|------|
| SEC 无阶段 B | plan:2548：SEC 无阶段 B（await-based streaming） | 正确 |
| provider_download_timeout 覆盖 | plan:2548-2549：per-filing batch 与下载流共存，timeout 覆盖网络请求与同 token 写窗口 | 与阶段 A 唯一 hard-bounded 一致 |
| 不约束 CN 阶段 C | plan:2569：该 timeout 不约束 CN 已开始的阶段 C | 正确 |
| SEC streaming 例外在测试矩阵中 | plan:2629-2630：SEC list/download 流期间恰有同一 active token（streaming exception） | 与契约一致 |

**结论**：SEC streaming exception 与三段边界逻辑连贯。

### Focus 5：prior closures 无回归

| Closure | 证据 | 结论 |
|---------|------|------|
| replace_source_meta AUTO_ATOMIC_ALLOWED | plan:2479 表 #12b + completeness gate :2505-2513 | 无回归 |
| per-filing terminal state machine | plan:2570-2595：PENDING/COMPLETED/FAILED 状态机、commit-start 决策点 | 无回归 |
| delete_entry S3 stage-delete | plan:2659-2691：S14-CTRL-13 destructive 状态机 | 无回归 |
| upload overwrite in execute_upload batch | plan:2490-2496：overwrite reset 移入 execute_upload per-document batch | 无回归 |
| S14-CLOSURE-01 同-core ingestion 链 | plan:2336-2355 | 无回归 |
| S14-REREVIEW-02/03 | plan:2652-2657 runtime owner + plan:2692-2716 inventory contraction | 无回归 |
| exact toolset names | plan S14-CTRL-11（fins/ingestion exact name fail-closed） | 无回归 |

**结论**：所有既有 closure 无回归。

## Findings

### 无新增 findings。

to-thread boundary fix（reviewer option 2 诚实三段边界）正确实施：
- 删除了 round 7 的四项冲突承诺（"完整窗口含 Docling""任一无有限 timeout 即 STOP""fake worker 自身有限结束""timeout 后下一 filing 必可启动"）；
- 阶段 A 唯一 hard-bounded（`provider_download_timeout_seconds`）；
- 阶段 B 明确不纳入 hard timeout、不伪装、worker 零 repo/batch；
- 阶段 C 无独立 timeout、含 cancel fences + rollback/journal recovery；
- SEC streaming exception 连贯；
- 测试矩阵（`test_cn_to_thread_boundary`）已修订为真实默认 Docling/read_bytes 在 begin_batch 前、worker 零句柄、late result 零写入、provider fake 有限 timeout 可证明终止、preparation 取消后无 token/零 publish/仅观测不声称终止；
- residual 降级准确（CN 阶段 B 无界 CPU 工作、commit-start 后同步窗口、容量约束）。

所有 prior closures 无回归。

## Open Questions

无。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| CN 阶段 B（read_bytes + Docling）为无界 CPU/IO 工作，不持有任何 token/batch/repository | 低（已知 residual） | 由 cancel_checker + warning/metrics 缓解；后续 filing 只在容量可用时可启动；实现期若发现 worker 持有 repo/batch 则 STOP |
| commit-start 后同步窗口不可取消 | 低（已知 residual） | 按 S14-CTRL-04 journal/recovery 收敛 |
| outer cancellation 不回收已运行的 Python thread | 低（已知 residual） | 由"worker 不得访问 repo/batch"契约保护仓储一致性 |
| 本次是计划审查，未执行 MinIO/fault injection/pyright/coverage/Docker | 低 | implementation gate |

## Final plan review conclusion

**PASS**

**Open H/M/L：0 / 0 / 0。**

to-thread boundary fix 闭合了 Terra S14-TERMINAL-FINAL-01（CN `to_thread` "底层有限 timeout"前提与真实默认 Docling/本地读路径矛盾）：三段边界诚实区分阶段 A 唯一 hard-bounded、阶段 B 不承诺有限结束、阶段 C 无独立 timeout + cancel fences + rollback/journal recovery；删除 round 7 冲突承诺；SEC streaming exception 连贯；所有 prior closures 无回归。Slice 1.4 满足 final dual plan re-review PASS 条件。
