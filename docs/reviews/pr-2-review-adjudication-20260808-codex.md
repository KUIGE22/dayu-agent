# PR-2 双路初审 Controller 裁决

## Gate 与范围

- **Gate**: Draft PR gate / PR review adjudication
- **PR**: `https://github.com/KUIGE22/dayu-agent/pull/2`
- **Base / Head**: `main` ← `codex/dual-model-research-mvp-recovered` @ `783b15a`
- **DeepSeek 初审**: `docs/reviews/pr-2-review-20260808-212900-deepseek.md`
- **MiMo 初审**: `docs/reviews/pr-2-review-20260808-212901-mimo.md`
- **DeepSeek 纠正复审**: `docs/reviews/pr-2-rereview-20260808-230100-deepseek.md`
- **MiMo 纠正复审**: `docs/reviews/pr-2-rereview-20260808-230101-mimo.md`
- **Fix 记录**: `docs/reviews/pr-2-fix-20260808-codex.md`
- **Controller 规则**: 每项只裁决为 `accepted`、`rejected-with-reason`、
  `deferred-with-owner` 或 `needs-more-evidence`；只把 accepted finding 交给 fix agent。

## 总结

- **Accepted**: DeepSeek F3、F6；MiMo F1/F2（合并一个安全根因）、F8。
- **Rejected with reason**: DeepSeek F1/F2/F5/F7；MiMo F3/F5/F6/F7。
- **Deferred with owner**: DeepSeek F4 剩余 488 项；MiMo F4。
- **初审 accepted High/Medium/Low**: `1/1/2`；这些 finding 已全部修复并关闭。
- **Controller 最终 open High/Medium/Low**: `0/0/0`。
- **双路复审**: DeepSeek `PASS`，MiMo `PASS`；纠正复审发现的 Low
  fix-regression `RR-01` 已最小修正并由两路独立复测关闭。
- **Deferred-with-owner**: 2 项，分别进入 `production-docstring-compliance` 与
  `typed-write-payload-contracts` work unit，不计入本 PR open counts。
- **PR metadata**: 三个 GitHub checks 均 success，mergeable state 为 clean；PR 当前仍为
  普通 open PR（`draft=false`），不满足最终 `draft-PR-pass` 的 Draft 状态要求。

## Accepted findings

### PR2-SEC-01 — accepted — 非 `sk-` 凭据形态会越过共享脱敏边界

- **来源**: MiMo F1（High）与 F2（Medium），合并为一个根因和一个 fix scope。
- **裁决**: `accepted`，严重度 High。
- **直接证据**: `dayu/redaction.py` 的 `SECRET_KEY_PATTERN` 只识别 `sk-`；
  `RedactingArgumentParser` 与两个 handoff scanner 均复用该边界。带强特征前缀的
  Google/Gemini legacy key 和进程中实际配置的非 `sk-` provider key 可原文进入
  stderr 或 machine-readable report。
- **范围纠正**: 不接受裸 `{32,}` 十六进制模式。40/64 位十六进制值与 Git
  SHA-1/SHA-256 无法可靠区分，会让仓库扫描产生系统性误报。
- **Fix contract**:
  1. 静态形状增加具有可靠前缀的 provider key；
  2. 对名称符合 `*_API_KEY`、`*_AUTH_TOKEN`、`*_ACCESS_TOKEN`、`HF_TOKEN` 的
     当前环境变量值做动态、精确值脱敏，支持同进程轮换；
  3. 两个 scanner 统一通过 `has_secret_shapes` 判断，不能继续只调用静态 regex；
  4. 覆盖 argparse stderr、共享原语、Codex review gate、dual-model pipeline，且保留
     未配置的 40/64 位 Git SHA 不误报负例。

### PR2-ANTHROPIC-01 — accepted — `pause_turn` 被错误当作正常终态

- **来源**: DeepSeek F3（Medium）。
- **裁决**: `accepted`，严重度 Medium。
- **直接证据**: `dayu/engine/async_anthropic_runner.py` 把 `pause_turn` 映射为
  `stop`，而下游只对 `length` 继续；当前实现因此会把未完成回合静默报告为完成。
- **协议证据**: Anthropic 官方 stop-reason 文档要求把暂停响应内容作为 assistant
  message 回送并继续同一回合：
  `https://docs.anthropic.com/en/api/handling-stop-reasons`。
- **Fix contract**: 当前 `AgentMessage` 只保留字符串 assistant content，归一化还会
  丢弃 server-tool 内容块；把 `pause_turn` 伪装成 `length` 会发送额外 user continuation
  prompt，不是官方续传协议。因此本 PR 必须 fail-loud：流式与非流式都产生稳定的
  `anthropic_pause_turn_unsupported` 错误，不发成功 DONE；完整 continuation 另属独立
  Engine 架构 work unit。

### PR2-COVERAGE-01 — accepted — auth suppression 分支继承旧 `no cover`

- **来源**: DeepSeek F6（Low）。
- **裁决**: `accepted`，严重度 Low。
- **直接证据**: 认证失败 fingerprint 记录逻辑位于既有
  `except Exception  # pragma: no cover` 块内，但已有测试真实执行该异常分支。
- **Fix contract**: 只移除失真的 coverage 豁免并复跑目标文件 coverage；不改变 auth
  suppression 行为、生命周期或日志契约。

### PR2-DOC-01 — accepted — exact 6 个方法缺少完整中文 docstring

- **来源**: MiMo F8（Low）。
- **裁决**: `accepted`，严重度 Low。
- **精确范围**:
  - `dayu/engine/model_circuit_breaker.py` 两个私有 store 的 `locked_entry` / `reset`
    共 4 个方法；
  - `dayu/services/internal/write_pipeline/model_usage_ledger.py` 的 `record` /
    `build_summary` 共 2 个方法。
- **Fix contract**: 仅补准确的中文概览、参数、返回值、异常；不得改可执行行为、类型
  或数据契约。

## Rejected-with-reason findings

### DeepSeek F1 — rejected-with-reason / evidence invalid

DeepSeek 只直接调用了内层 `_validate_challenger_run_plan_args`，没有走真实入口。
`run_write_command` 在消费前先调用 `_validate_research_materialization_args`；完整链路已在
`_write_params_validation.py` 分别拒绝 Challenger + `--summary`、Challenger + `--infer`
和 run approval + `--preflight-only`。因此其“凭据先消费再短路”的路径不可达，不修改生产
代码。re-review 必须按完整入口而非内层 helper 复核。

### DeepSeek F2 / MiMo F3 — rejected-with-reason / accepted design

Accepted v5.3/v5.4/v5.5 明确把 `DayuCliArguments` 限定为 consumer Protocol 所需 exact21
字段，并明确保留表外 argparse 字段的存量动态读取，避免把 Namespace 子类扩成 god bag。
Selector 的 defensive `getattr` 及 Phase E 动态 inventory 也由计划锁定。F1 已证明不是该
边界的失败实例；本 PR 不 blanket 扩字段、不把 396 个调用点改成新的全仓类型迁移。

### DeepSeek F5 — rejected-with-reason / intentional behavior

Auth suppression 以 `(provider, sha256(key))` 为键，只在 auto 模式的 401/403 后生效；key
变化立即恢复尝试，显式 provider 不受抑制。现有测试锁定“同一失效凭据只尝试一次、换 key
恢复”的意图。该 finding 没有同一 key 从真实 auth failure 恢复后仍应自动重试的产品契约或
失败复现；TTL/registry 是独立可靠性设计，不并入本 PR fix。

### DeepSeek F7 — rejected-with-reason / non-material

`_ChangeSet.has_any_py_changes` 虽未进入最终判定，但被显式赋值并有 characterization 测试；
它不改变 fail-closed 结果、CI exit code 或报告。删除/新增短路都不是当前 correctness fix。

### MiMo F5 — rejected-with-reason / accepted CI ratchet

Pyright ratchet 是 accepted Slice 13 门禁；`_ensure_ref_available` 会在 shallow checkout 中按
base SHA fail-closed fetch。当前 GitHub required check 已 success，HEAD/BASE 均为零诊断。
把 ratchet 改回另一语义或只为 traceback 文案改 CI 不属于 accepted PR finding。

### MiMo F6 — rejected-with-reason / workflow scope is explicit

`dual-model-gates.yml` 是 handoff 文档与配套 gate 脚本的 focused workflow，其 paths 与
测试清单精确同源；生产代码由 `ci-pr-required.yml` 覆盖。纯 `dayu/**` 不触发 focused
handoff gate 是职责边界，不是门禁静默丢失。本 PR 同时修改 handoff 路径，真实 workflow
也已运行并成功。

### MiMo F7 — rejected-with-reason / historical artifact, current evidence exists

Aggregate validation artifact 记录的是其当时 HEAD；后续 RT-01 有独立 implementation、
双路 re-review 与 accepted commit。Recovery commit 的 tree 与原 accepted head 逐字节一致，
本次 PR review 又在 `783b15a` 上复跑 tests/pyright/CI。历史 artifact 不应伪装成当前 commit，
但它没有声称验证未来 commit；无需改写历史记录。

## Deferred-with-owner findings

### DeepSeek F4 — deferred-with-owner / scope-corrected docstring debt

- **事实纠正**: 494 缺失计数可复现，但其中 478 个 private、9 个 dunder、7 个
  public-name；MiMo exact6 已由 PR2-DOC-01 当前修复。494/494 在本 architecture work-unit
  前置基线 `4586e04` 已缺失，迁移没有删除既有 docstring。
- **严重度纠正**: Medium → Low maintainability debt，无当前行为错误。
- **Owner / destination**: 后续独立 `production-docstring-compliance` work unit，由仓库
  maintainer/Controller 负责；输入是固定 AST inventory，扣除本轮 exact6 后剩余 exact488，
  以中文概览 + Args/Returns/Raises validator 和逐文件小 slice 治理。
- **为什么不在本 fix 扫荡**: 一次性给 488 个 private/dunder/nested 函数补文档会把三个
  correctness/security fix 扩成无界 30 文件重写，显著降低可审查性。

### MiMo F4 — deferred-with-owner / typed payload migration

Finding 指向的 `Mapping[str, Any]` / `dict[str, Any]` 大多属于 architecture work-unit 前置
payload 契约；accepted v4.4 还精确保留了若干 public validator 的 Mapping 边界。没有提交
具体错误 payload、静默分支或相对 accepted plan 的类型扩散证据。

- **Owner / destination**: 后续独立 `typed-write-payload-contracts` work unit，由 Service
  owner/仓库 maintainer 负责，按 payload family 逐个引入 TypedDict/dataclass，不与本 PR
  的协议、安全和 docstring fix 混做。
- **当前处理**: 不声称这些签名满足 AGENTS 理想终态；只确认它们不是本轮可有界修复的
  material PR defect。

## Fix handoff

Fix agent 只可处理 PR2-SEC-01、PR2-ANTHROPIC-01、PR2-COVERAGE-01、PR2-DOC-01；
不得处理 rejected/deferred finding，不得创建兼容 wrapper、cast/type-ignore/noqa，不得进入
commit/push/PR/re-review gate。修复后必须产出 `docs/reviews/pr-2-fix-20260808-codex.md`，
运行受影响测试、pyright、Ruff、逐文件 coverage、三个 machine-readable gates，并按触发
规则裁决 README 是否更新。

## 双路复审闭环

- **PR2-SEC-01**: 已修复。静态 `AIza` 形状、动态环境凭据精确值、同进程轮换、两个
  scanner 显式 matcher 与 Git SHA 负例均通过复测。
- **RR-01**: DeepSeek 首轮复审发现，若匹配名环境变量被设置为普通短语，仅长度门槛会
  误报正常文本。Controller 接受为 Low fix-regression，并限定为值形态资格修正。当前实现
  要求动态候选至少 16 位、无空白且具备混合字符 token 形态；至少 32 位纯十六进制只在
  已由环境变量名筛选的候选阶段放行，不对任意扫描文本增加裸 hex matcher。DeepSeek 与
  MiMo 均独立复测普通短语、纯字母值、hex key、未配置 Git SHA 和两个 scanner，结论
  `CLOSED`。
- **PR2-ANTHROPIC-01 / PR2-COVERAGE-01 / PR2-DOC-01**: 均按 fix contract 关闭；
  未发现修复引入的新 blocker。
- **验证**: redaction/scanner focused `261 passed`；`dayu/redaction.py` `29 passed`、
  coverage `100%`；全仓 pyright `0 errors / 0 warnings / 0 informations`；变更 Python
  Ruff 通过；三个 machine-readable JSON gates 均 `ok=true`；`git diff --check` clean。
- **最终状态**: `DUAL PR RE-REVIEW PASS / READY FOR ACCEPTED PR REVIEW COMMIT`。
