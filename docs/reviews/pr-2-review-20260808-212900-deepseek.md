# Code Review

## Scope

- Mode: PR
- Branch or PR: PR-2，https://github.com/KUIGE22/dayu-agent/pull/2；head `codex/dual-model-research-mvp-recovered` @ `783b15a`
- Base: `main`（本机无本地 `main`，实际使用 `origin/main`，merge-base `2115c86`）
- Output file: `docs/reviews/pr-2-review-20260808-212900-deepseek.md`
- Included scope: `git diff origin/main...HEAD` 全量（460 files，+171444 / -697）；重点走读 `dayu/cli/commands/_write_params_validation.py`、`dayu/cli/commands/write.py`、`dayu/cli/commands/_write_challenger.py`、`dayu/cli/arguments.py`、`dayu/cli/arg_parsing.py`、`dayu/engine/async_anthropic_runner.py`、`dayu/engine/tools/web_search_providers.py`、`dayu/services/write_model_configuration_application.py`、`dayu/cli/commands/research_template.py`、`utils/ci_pr_pyright.py`、`.github/workflows/ci-pr-required.yml`；核对 `AGENTS.md` / `CLAUDE.md`、accepted master plan v5.8、aggregate validation / adjudication / RT-01 artifacts
- Excluded scope: `workspace/` 下的数据与产物文件（体量占本次 diff 绝大部分，非行为代码）；`dayu/render/`、`utils/` 按 AGENTS.md 豁免测试与覆盖率要求（仍作为 CI gate 逻辑走读）
- Parallel review coverage: 无。本次未使用 subagent（本机 Agent 后端返回 `API Error: 400 本站仅支持以下模型`，4 次尝试均失败），全部结论由主 reviewer 直接走读代码路径得出

## Verdict

> **最终状态（Controller 裁决 + PR re-review 后回写）**：本文件为**初审快照**。经 Controller 裁决与
> `docs/reviews/pr-2-rereview-20260808-230100-deepseek.md` 复核，最终结论为 **`PASS`**，
> **open High / Medium / Low = `0 / 0 / 0`**（2 项 deferred-with-owner 另列，不计入 open）。
> 下方初审结论与「Open High/Medium/Low counts」保留原文存证，**已被最终裁决取代**，不得作为当前状态引用。
> 各 finding 的最终状态见其小节标题。

### 初审结论（历史快照，已被取代）

`REQUEST CHANGES`。

存在 1 项 High：Challenger 双跑一次性治理授权可被 `--summary` / `--infer` / `--preflight-only` 消费后短路，凭据被不可逆烧毁而双跑从未执行，且该路径已用真实 parser 复现。

> **该 High 已被证伪**：初审只直接调用了内层 helper `_validate_challenger_run_plan_args`，未走真实入口。
> `run_write_command` 在凭据消费前先调用外层 `_validate_research_materialization_args`，三种形态在 re-review 的
> 真实 parser + 外层校验链实测中全部 `BLOCKED`。详见 F1 小节与 re-review 的「DeepSeek F1」节。

同时确认：recovery commit `783b15a` **未**掩盖或改变实际代码（树与 `172de45` 逐字节一致）；RT-01 修复真实存在且精确匹配 v5.8 `AGG-RT-CTRL-01`；pyright 全仓 0 error / 0 warning / 0 information。（该三条经 re-review 复核仍然成立。）

## Findings

### F1-已关闭（rejected / 证据失效）-[原报高]-Challenger 一次性双跑授权被非双跑形态消费后短路，凭据烧毁但双跑从未执行

> **最终状态（re-review 回写）**: `rejected-with-reason / evidence invalid`。裁决见 `docs/reviews/pr-2-review-adjudication-20260808-codex.md`，复核见 `docs/reviews/pr-2-rereview-20260808-230100-deepseek.md`。
> 本 finding 的取样点错误：只调用了内层 `_validate_challenger_run_plan_args`，未经过真实入口 `run_write_command` 中更早执行的 `_validate_research_materialization_args`。经真实 parser + 外层校验链穷举实测，`--summary` / `--infer` / `--preflight-only` 三种形态**全部 BLOCKED**（拦截点 `_write_params_validation.py:1545-1546`、`:1547-1548`、`:1852-1853`，均早于 `write.py:632` 的凭据消费），因此「凭据先消费再短路」路径不可达。生产代码未修改。
> 下方原始内容保留以供追溯，其结论已失效。

- **入口/函数**: `dayu write` 命令主流程 `dayu/cli/commands/write.py` → `_validate_challenger_run_plan_args` → `_verify_and_consume_challenger_run_approval_before_host`
- **文件(行号)**:
  - 禁用清单：`dayu/cli/commands/_write_params_validation.py:79-90`（放行返回 `dayu/cli/commands/_write_params_validation.py:91`）
  - 调用点：`dayu/cli/commands/_write_params_validation.py:1938-1941`
  - 授权消费：`dayu/cli/commands/write.py:630-638`；实际消费落盘 `dayu/cli/commands/_write_challenger.py:451-455`
  - 短路点：`dayu/cli/commands/write.py:639`（`--summary`）、`dayu/cli/commands/write.py:823`（`--preflight-only`）、`dayu/cli/commands/write.py:933`（`--infer`）
- **输入场景**:
  ```
  dayu write --ticker AAPL --template t.md --output o --challenger-output co \
    --web-provider auto --write-max-model-requests 10 --write-max-total-tokens 100 \
    --write-max-estimated-cost 1.0 --write-budget-currency CNY --model-name m --no-resume \
    --routing-history-root <root> --routing-proposal-input <proposal.json> \
    --routing-challenger-run-approval-input <approval.json> \
    --summary        # 或 --infer，或 --preflight-only
  ```
- **实际分支**: `_validate_challenger_run_plan_args` 逐条走完 `dayu/cli/commands/_write_params_validation.py:79-90` 的禁用清单，`--summary` / `--infer` / `--preflight-only` 均不在清单内，落到 `:91 return None`（放行）→ `write.py:630` 条件成立 → `write.py:632` `_verify_and_consume_challenger_run_approval_before_host` 校验通过并在 `_write_challenger.py:451` 调用 `consume_write_model_challenger_run_approval` 写入 consumption 记录 → 返回 0 → `write.py:639 if args.summary:` 命中，打印上次运行报告并 return，Champion/Challenger 双跑从未启动
- **预期行为**: 该禁用清单的设计意图是「已审批的一次性双跑授权只能用于真实双跑执行」，因此已显式拦截 `--fast` / `--force` / `--chapter` / `--research-template` / `--materialize-research` / research 物化参数。`--summary`（只读报告）、`--infer`（只做 facet 归因后 return）、`--preflight-only`（只做预检）同样不产生任何双跑，应在授权校验阶段返回错误消息、拒绝进入消费
- **实际行为**: 授权校验返回 `None` 放行；一次性凭据被消费落盘；随后立刻短路返回。凭据进入已消费终态，重放同一凭据会在 `_write_challenger.py:456-458` 命中 `WriteModelChallengerRunApprovalConsumedError` 并返回退出码 4
- **直接证据**: 用仓库真实 parser `dayu.cli.arg_parsing._create_parser()` 复现，同一组 base 参数只改附加 flag：

  ```
  []                               -> None
  ['--fast']                       -> Challenger 双跑授权不允许使用 --fast
  ['--force']                      -> Challenger 双跑授权不允许使用 --force
  ['--chapter', 'c']               -> Challenger 双跑授权不允许使用 --chapter
  ['--infer']                      -> None          <-- 放行
  ['--summary']                    -> None          <-- 放行
  ['--preflight-only']             -> None          <-- 放行
  ['--materialize-research']       -> Challenger 双跑授权不允许使用 --materialize-research
  ```

  消费先于短路的顺序由 `write.py:630-638`（消费）严格早于 `write.py:639`（`if args.summary:` 短路）证明；`--infer` 的短路在 `write.py:933 if bootstrap_exit_code != 0 or bool(getattr(args, "infer", False)): return bootstrap_exit_code`
- **影响**: 不可恢复的治理状态破坏。一次误用即让已审批凭据永久失效，必须重新走完整「提案 → preflight 审批 → run 审批」链路。属于「返回成功但治理状态被单向推进」，且无任何日志提示授权被用在了非执行形态上
- **建议改法和验证点**:
  1. 把 `summary`、`infer`、`preflight_only` 加入 `_write_params_validation.py:79-90` 禁用清单；
  2. 更稳的做法是把黑名单改为白名单——由 `_validate_challenger_run_plan_args` 显式枚举允许的执行形态，任何未枚举的执行意图一律拒绝，这样后续新增 flag 不会默认落进「允许」；
  3. 验证点：新增 CLI 级回归，对每种短路形态断言退出码非 0 **且** workspace 中未生成 consumption 记录文件（仅断言退出码不足以证明凭据未被消费）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F2-已关闭（rejected / accepted design）-[原报中]-授权门禁全部走 getattr 字符串键，DayuCliArguments 未声明这些字段，pyright 对键名零校验

> **最终状态（re-review 回写）**: `rejected-with-reason / accepted design`。accepted plan v5.3/v5.4/v5.5 明确把 `DayuCliArguments` 限定为 consumer Protocol 所需 exact21 字段，并保留表外 argparse 字段的动态读取，以避免把 Namespace 子类扩成 god bag。F1 既已证伪，本项失去唯一已实现实例，退化为无失败实例的类型学观察。fail-open 语义客观存在但不构成本 PR 的 material defect。

- **入口/函数**: `_validate_challenger_run_plan_args` 及全部 write 参数校验；类型载体 `DayuCliArguments`
- **文件(行号)**: `dayu/cli/arguments.py:44-66`（`DayuCliArguments` 仅声明 21 个字段）；`dayu/cli/commands/_write_params_validation.py:70`、`:73-74`、`:77-90`（全部 `getattr(args, "<字面量>", <默认值>)`）
- **输入场景**: 任一次 parser dest 重命名或校验侧键名拼写漂移，例如 `--fast` 的 dest 从 `fast` 改为 `fast_mode`（`dayu/cli/arg_parsing.py:625`）
- **实际分支**: `getattr(args, "fast", False)` 取不到属性 → 返回默认 `False` → `if bool(False)` 不成立 → 该条禁用直接被跳过，函数继续向下并最终 `return None` 授权通过
- **预期行为**: 门禁字段不存在应是 fail-closed（拒绝授权或抛错），而不是取默认值后静默放行
- **实际行为**: 同一函数内两套失败方向并存——`:69-72` 的必填项循环 fail-closed（缺失即报错），`:77-90` 的禁用项全部 fail-open（缺失即视为未使用、放行）。且 `argparse.Namespace` 在 typeshed 中定义了 `def __getattr__(self, name: str) -> Any`，因此 pyright 对 `getattr(args, ...)` 与 `args.<任意名>` 均不产生任何诊断，`DayuCliArguments` 的字段声明对这些门禁不提供静态保护
- **直接证据**: `dayu/cli/arguments.py:44-66` 声明字段中不含 `fast` / `force` / `chapter` / `research_template` / `materialize_research` / `research_base` / `overwrite_research` / `resume` / `model_name` / `audit_model_name`，而这些正是 `_write_params_validation.py:73-90` 门禁读取的全部键；`dayu/cli/` 下 `getattr(args` 出现 335 次（`origin/main` 为 57 次）
- **影响**: 静默失效风险。类型层无保护、门禁默认放行，F1 属于同一根因的已实现实例
- **建议改法和验证点**: 门禁读取改为直接属性访问（由 `DayuCliArguments` 完整声明字段，缺失即 `AttributeError` 而非默认值），或封装 `_require_flag(args, name)` 显式区分「字段不存在」与「字段为假」；验证点：补一条测试，构造缺少某禁用字段的 Namespace，断言校验函数拒绝而不是返回 `None`
- **修复风险（低/中/高）**: 中（需同步补全字段声明，触及较多调用点）
- **严重程度（低/中/高/严重）**: 中

### F3-已修复（accepted / PR2-ANTHROPIC-01）-[原报中]-Anthropic runner 把 pause_turn 映射为终态 stop，回合被静默截断

> **最终状态（re-review 回写）**: `accepted 已修复`，裁决编号 `PR2-ANTHROPIC-01`。`pause_turn -> stop` 映射已删除（`async_anthropic_runner.py:19-29`）；流式（`:413-421`）与非流式（`:553-565`）均 fail-loud 产出稳定 `anthropic_pause_turn_unsupported`，不产出成功 `DONE`，未伪装为 `length`。新增测试 `tests/engine/test_async_anthropic_runner.py:303`、`:434`；`dayu/engine/README.md:124` 已同步契约。完整同回合续传属独立 Engine 消息契约 work unit。

- **入口/函数**: `AsyncAnthropicRunner` 流式响应的 stop_reason 归一化
- **文件(行号)**: `dayu/engine/async_anthropic_runner.py:15-23`，其中 `:22` 为 `"pause_turn": "stop"`
- **输入场景**: Anthropic Messages API 在长回合中返回 `stop_reason="pause_turn"`（协议语义为「本次响应暂停、需把当前响应回传以继续同一回合」，而非回合结束）
- **实际分支**: 命中 `_STOP_REASON_MAP` 的 `pause_turn` → 归一化为 `"stop"`。下游 `dayu/engine/async_agent.py:1160-1176` 只在 `truncated` 为真时继续下一轮，而 `truncated` 仅在 `finish_reason == "length"` 时被置位（`dayu/engine/async_openai_runner.py:1670`），因此 `"stop"` 直接走正常收敛
- **预期行为**: `pause_turn` 是「未完成、需继续」信号，应触发 continuation，或在暂不支持时显式失败并留下可观测记录
- **实际行为**: 被当作正常自然结束，回合静默终止，章节产出可能不完整且无任何 warn/error
- **直接证据**: 全仓 `grep -rn "pause_turn"` 仅命中 `dayu/engine/async_anthropic_runner.py:22` 这一处——无测试、无文档、无下游分支处理；`dayu/config/llm_models.json` 已为 `claude-sonnet-4-6` / `claude-sonnet-4-6-thinking` 配置 `"runner_type": "anthropic"`，该 runner 是活跃路径
- **影响**: 错误 answer / 静默失效（协议层「未完成」被误判为产品层「已完成」，属于协议事实与产品语义混淆）
- **建议改法和验证点**: 将 `pause_turn` 从终态映射中移除，改为映射到可继续语义（复用 `truncated` 通道或新增显式 continuation 信号）；若当前明确不支持 server-side 长回合，则应显式抛错而非静默收敛。验证点：新增单测构造 `stop_reason="pause_turn"` 的 SSE 流，断言 agent 继续下一轮或抛出明确异常
- **修复风险（低/中/高）**: 中（需确认 continuation 协议的请求重放形态）
- **严重程度（低/中/高/严重）**: 中
- **证据链说明**: 映射与下游行为均为静态可证；`pause_turn` 在当前 Dayu 工具形态下的实际触发频率未经运行时验证。但该 key 是本 PR 作者主动写入的，说明已预期其可达

### F4-已延期（deferred-with-owner，未修复）-[严重度纠正为低]-PR 新增生产代码存在 494 处缺失中文 docstring，违反 AGENTS.md 硬约束

> **最终状态（re-review 回写）**: `deferred-with-owner / 未修复`。**不得称为 fixed。**
> 494 缺失计数可复现，Controller 事实纠正为 478 private / 9 dunder / 7 public-name；其中 exact6 已由 `PR2-DOC-01` 修复，**剩余 exact488 仍然缺失**，包括本 finding 点名的 `write_model_configuration_application.py` 原子事务链路全部函数。
> 严重度经复核纠正 Medium → Low maintainability debt：无当前行为错误，且 494/494 在架构 work-unit 前置基线 `4586e04` 已缺失，本 PR 的模块迁移未删除既有 docstring，非本 PR 引入的回归。
> **Owner**: 后续独立 `production-docstring-compliance` work unit，由仓库 maintainer / Controller 负责；输入为固定 AST inventory（exact488）。

- **入口/函数**: 本 PR 新增/修改的生产模块（排除 `tests/`、`utils/`）
- **文件(行号)**: 集中在本 PR 全新文件，Top 8：
  ```
   54  dayu/services/write_model_configuration_rollback_application.py
   51  dayu/services/write_model_configuration_manual_recovery_clearance.py
   47  dayu/services/write_model_configuration_manual_recovery_application.py
   42  dayu/services/write_model_configuration_application.py
   24  dayu/services/write_model_configuration_manual_recovery_verification.py
   22  dayu/services/internal/write_pipeline/model_usage_ledger.py
   22  dayu/services/write_model_configuration_manual_recovery.py
   22  dayu/services/write_model_health.py
  ```
  典型样本（原子事务核心链路，全部无 docstring）：`dayu/services/write_model_configuration_application.py:1242 _assert_target_bytes_current`、`:1260 _stage_content`、`:1292 _replace_staged_file`、`:1325 _verify_applied_snapshot`、`:1420 _restore_operations`、`:1563 _recover_interrupted_transaction`
- **输入场景**: 不适用（静态约束违反）
- **实际分支**: 不适用
- **预期行为**: AGENTS.md「编码硬约束」第 1 条：「函数必须提供完整中文 docstring，至少包含参数、返回值、异常」，无例外条款（仅 `dayu/render/`、`utils/` 被豁免测试与覆盖率，未被豁免 docstring）
- **实际行为**: AST 统计本 PR 触及的生产文件共 1530 个函数定义，其中 494 个（32.3%）无任何 docstring，分布于 30 个文件；缺失最严重的恰是补偿回滚、人工恢复、原子应用等最需要契约文档的高风险链路
- **直接证据**: 对 `git diff --name-only origin/main...HEAD` 结果做 `ast.get_docstring` 统计；上述 8 个文件经 `git cat-file -e origin/main:<path>` 验证均为本 PR 全新增文件，故不属于 pre-existing 债务
- **影响**: 仅局部行为错误之外的可维护性风险——补偿式回滚与人工恢复链路的前置条件、副作用、异常契约完全未文档化，后续修改容易引入回归
- **建议改法和验证点**: 至少优先补齐 `write_model_configuration_application.py`、`write_model_configuration_rollback_application.py`、`write_model_configuration_manual_recovery_*.py` 中涉及文件替换、指纹校验、补偿恢复的函数；验证点：在 CI 增加 AST 级 docstring 检查，避免继续扩散
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F5-已关闭（rejected / intentional behavior）-[原报中]-搜索 provider 认证失败抑制集是进程级全局可变状态，无 TTL 与重置路径

> **最终状态（re-review 回写）**: `rejected-with-reason / intentional behavior`。抑制键为 `(provider, sha256(key))`，仅 auto 模式 401/403 生效，换 key 立即恢复，显式 provider 不受抑制；现有测试 `tests/engine/test_web_tools.py:862` 精确锁定该产品意图。本 finding 未能提交「同一 key 从真实 auth failure 恢复后仍应自动重试」的产品契约或失败复现，举证不足。TTL/registry 属独立可靠性设计，不并入本 PR。

- **入口/函数**: `search_public_web` → `_candidate_providers` / `_remember_search_provider_auth_failure`
- **文件(行号)**: `dayu/engine/tools/web_search_providers.py:26-27`（模块级 `set` + `Lock`）、`:191-192`（写入）、`:331-338`（读取抑制）、`:341-348`（记录）、`:447-449`（auto 候选过滤）
- **输入场景**: `provider="auto"` 时，tavily 或 serper 返回一次 HTTP 401/403——包括服务端瞬时 401、代理层注入的 401、key 轮换窗口期内的短暂 401
- **实际分支**: `:191` `resolved_provider == "auto" and _is_search_provider_auth_failure(exc)` 成立 → `:348` 把 `(provider, sha256(key))` 加入模块级 `_AUTH_FAILED_PROVIDER_KEY_FINGERPRINTS` → 此后 `:447/:449` 的 `not _is_search_provider_auth_suppressed(...)` 恒为假，该 provider 被永久排除，降级到 duckduckgo
- **预期行为**: 认证失败抑制应有 TTL、重试计数或退避窗口，允许瞬时故障恢复；抑制状态不应是模块级全局可变状态
- **实际行为**: `:348` 的 `add` 之后，全模块无任何 `discard` / `clear` / 过期逻辑。在长驻进程（Host 会话、交互模式）中，一次瞬时 401 会让付费高质量 provider 在整个进程生命周期内不可用，且告警只发一次（测试 `tests/engine/test_web_tools.py:930` 断言 `len(captured_warns) == 1`），后续降级完全静默
- **直接证据**: 全仓 `grep -rn "_AUTH_FAILED_PROVIDER_KEY_FINGERPRINTS"` 的写操作仅 `:348` 的 `add`；唯一的清空发生在测试内 `tests/engine/test_web_tools.py:880-883` 的 `monkeypatch.setattr(..., set())`，生产路径无对应能力。现有测试 `test_search_web_auto_suppresses_auth_failed_key_until_key_changes` 只覆盖「换 key 后恢复」，未覆盖「同 key 在瞬时故障后应恢复」
- **影响**: 静默降级（搜索质量长期劣化且无可观测信号），非数据损坏
- **建议改法和验证点**: 为抑制项加入时间窗或失败计数退避；并把该状态从模块级全局收敛到 provider 实例/注册表，避免跨请求跨会话共享可变状态。验证点：新增测试断言抑制在窗口过期后自动解除
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F6-已修复（accepted / PR2-COVERAGE-01）-[原报低]-新增认证抑制逻辑落在 pragma no cover 块内，覆盖率被排除

> **最终状态（re-review 回写）**: `accepted 已修复`，裁决编号 `PR2-COVERAGE-01`。`dayu/engine/tools/web_search_providers.py:190` 的 `# pragma: no cover` 已移除，diff 为单行，块内认证判定、fingerprint 记录与日志调用逐字未变。该文件 clean-env coverage = 96%。

- **入口/函数**: `search_public_web` 的 provider 失败回退分支
- **文件(行号)**: `dayu/engine/tools/web_search_providers.py:190-192`
- **输入场景**: 任一 provider 抛出异常
- **实际分支**: 新增的 `_is_search_provider_auth_failure` / `_remember_search_provider_auth_failure` 调用被写在标注 `# pragma: no cover - 失败路径由单测通过 monkeypatch 覆盖` 的 `except Exception` 块内
- **预期行为**: 新增的治理/降级判定逻辑应纳入覆盖率统计；`pragma: no cover` 的原注释是为旧的纯日志分支写的，新增分支逻辑继承该豁免并不成立
- **实际行为**: 该分支的两行新判定被排除在覆盖率之外，AGENTS.md「单文件测试覆盖率目标 >= 80%」对这段逻辑失去约束力
- **直接证据**: `:190` 的 pragma 注释与 `:191-192` 新增逻辑处于同一被豁免块；该 pragma 在 `origin/main` 版本中已存在，但当时块内仅有 `_log_search_provider_failure` 调用
- **影响**: 仅局部——覆盖率信号失真
- **建议改法和验证点**: 把认证判定提取到 pragma 块之外的独立分支，或移除该 pragma 并依赖已有的 monkeypatch 测试
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F7-已关闭（rejected / non-material）-[原报低]-CI pyright ratchet 中 has_any_py_changes 为 dead field

> **最终状态（re-review 回写）**: `rejected-with-reason / non-material`。字段被显式赋值并有 characterization 测试（`tests/test_ci_pr_pyright.py:156/168/482`），不改变 fail-closed 判定、CI exit code 或报告内容。本轮 fix 未触碰该文件。

- **入口/函数**: `utils/ci_pr_pyright.py` 的 `_ChangeSet`
- **文件(行号)**: `utils/ci_pr_pyright.py:108`（声明）、`:297`（赋值）
- **输入场景**: 任一次 PR CI 运行
- **实际分支**: 该字段被声明、被赋值、被测试引用，但生产判定逻辑中从未读取
- **预期行为**: 要么参与「无 Python 改动则跳过比对」的短路判定，要么删除
- **实际行为**: 字段悬空，形成「看起来有 Python 改动守卫、实际没有」的误导性契约
- **直接证据**: 全仓检索该字段的读取点，仅存在于声明、赋值与测试断言中
- **影响**: 仅局部——可维护性与误读风险；`utils/` 按 AGENTS.md 豁免测试与覆盖率要求，但本文件是 required CI lane 的实际门禁实现
- **建议改法和验证点**: 删除该字段，或补上真实短路逻辑并新增对应用例
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 明确排除项（非本 PR defect）

以下项在审查中出现，但经证据核对后判定**不构成 PR finding**，单列以便 Controller 区分：

1. **`tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key` 失败 —— pre-existing + environment-only，不计入 findings**
   - 现象：本机跑 required lane 得到 `1 failed, 7121 passed, 5 skipped, 9 deselected`
   - 归因证据：该测试在 `origin/main:tests/engine/test_web_tools.py:1388` 已逐字存在，`git diff origin/main...HEAD -- tests/engine/test_web_tools.py` 对该测试体无任何改动；被测函数 `_search_with_serper` 的 key 守卫（`dayu/engine/tools/web_search_providers.py:560-562`）在本 PR 中未被修改
   - 真实成因：本机 shell 已设置 `SERPER_API_KEY`，守卫不触发，测试穿透到 `:576 requests.post(...)` 并因代理不可用抛 `ProxyError`。测试自身未 `monkeypatch.delenv`，属于既有的环境依赖缺陷
   - 结论：不是本 PR 引入。但需注意 governance artifacts 引用的 `7121 passed` 与本机计数完全一致，说明该失败在此前验证环境中同样存在或同样被环境掩盖

2. **Recovery commit `783b15a` 完整性 —— 核查通过，声明属实**
   - `git diff --stat 172de45 783b15a` 输出为空，两棵树逐字节一致
   - 44 个生产文件、+14187/−10989 的大 diff 来源于 `write.py` / `research_template.py` 的合法模块拆分，**未**掩盖或改变实际代码

3. **RT-01 修复 —— 核查通过，真实且精确**
   - `dayu/cli/commands/research_template.py:595-614` 的 `return 0 if result.get("ok") is True else 1` 与 docstring（`:602` 成功 0 / 失败 1）精确匹配 v5.8 `AGG-RT-CTRL-01`

4. **pyright —— 全仓 0 error / 0 warning / 0 information**

5. **配置应用事务原子性 —— 走读后判定设计良好**
   - `dayu/services/write_model_configuration_application.py` 的 stage-all-then-commit-all（`mkstemp` + `fsync` + `os.replace`）、逐文件前后指纹校验、`except BaseException` 触发的反序补偿恢复（`:1420`，`hmac.compare_digest`）、`rolled_back` / `rollback_failed` 回执状态、`finally` 清理 staged 并释放跨进程 `StateDirSingleInstanceLock`，均未发现 correctness 缺陷（docstring 缺失问题已并入 F4）

## Open High/Medium/Low counts

### 最终 counts（Controller 裁决 + re-review 复核后）

- Open High: `0`
- Open Medium: `0`
- Open Low: `0`
- Deferred-with-owner（**未修复**，按裁决不计入 open）: `1`（F4 剩余 exact488，owner = `production-docstring-compliance` work unit）

最终逐项状态映射：

| 编号 | 初审严重度 | 最终状态 |
|---|---|---|
| F1 | 高 | **已关闭**（rejected / 证据失效：只测内层 helper，外层校验链实测三形态全 BLOCKED） |
| F2 | 中 | **已关闭**（rejected / accepted design：exact21 字段边界由 v5.3–v5.5 锁定） |
| F3 | 中 | **已修复**（accepted → `PR2-ANTHROPIC-01`，`pause_turn` 改为 fail-loud） |
| F4 | 中→**低**（严重度经裁决纠正） | **已延期**（deferred-with-owner，**未修复**，不得称为 fixed；exact6 已由 `PR2-DOC-01` 修复，剩余 exact488） |
| F5 | 中 | **已关闭**（rejected / intentional behavior：auth suppression 语义有测试锁定，缺相反产品契约举证） |
| F6 | 低 | **已修复**（accepted → `PR2-COVERAGE-01`，移除失真 `pragma: no cover`） |
| F7 | 低 | **已关闭**（rejected / non-material：不改变 fail-closed 结果、exit code 或报告） |

### 初审 counts（历史快照，已被取代）

- Open High: `1`（F1）
- Open Medium: `4`（F2、F3、F4、F5）
- Open Low: `2`（F6、F7）

## Open Questions

- `pause_turn` 在当前 Dayu 工具形态（不使用 Anthropic server-side tools）下是否实际可达？`dayu/engine/async_anthropic_runner.py:22` 显式写入该 key 说明作者预期其可达，但仓库内无运行时证据。此问题只影响 F3 的严重度定级，不影响 finding 成立
- PR-2 的 GitHub metadata（title、author、head/base 分支、CI checks 实际结论）**无法读取**：本机 `gh` CLI 未认证（`please run gh auth login`）。按 skill 约束不编造 PR facts，故本报告的 base/head 完全依据用户 handoff 给定值与本地 git 事实
- governance artifacts（`aggregate-fix-rt-exit-code-review-adjudication-20260808-codex.md`、`plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`）均声明 open High/Medium/Low = `0/0/0`，但两者的审查基线是 `a0c469a`（RT-01 单点范围），与本次 PR-2 全量 `main...HEAD` 范围不同。F1 所在的 Challenger 授权链路是否曾进入过任一路 review 的实际 scope，无法从 artifacts 内容判定

## Residual Risk

- **未覆盖区域**：本次未使用 subagent（本机 Agent 后端模型不可用），受单 reviewer 上下文限制，以下区域仅做了接口级浏览而非逐行走读：`dayu/services/write_model_configuration_manual_recovery_*.py` 系列（5 个新增模块）的状态机完整路径、`dayu/services/write_model_health.py` 的健康趋势计算、`workspace/` 下产物文件。这些区域的 findings 状态应视为 **未知**，而非「已确认无问题」
- **测试缺口**：`_validate_challenger_run_plan_args` 的禁用清单在整个仓库中**没有任何测试**——`grep -rn "Challenger 双跑授权" tests/` 命中 0 次。F1 之所以能存活到 PR 阶段，直接原因就是该门禁零测试覆盖。修复 F1 时若只加分支不加测试，同类回归会再次发生
- **CI 门禁弱化**：`.github/workflows/ci-pr-required.yml` 已把硬 `pyright` 步骤替换为 `python -m utils.ci_pr_pyright` ratchet。当前基线为 0 诊断，ratchet 暂未掩盖任何问题；但门禁语义已从「必须零错误」变为「不得比 base 更差」，一旦基线被污染，后续 PR 将失去绝对约束。该变更本身是有意设计，不作为 finding，但作为剩余风险记录
- **类型安全信号失真**：pyright 报告 0 错误，但由于 `argparse.Namespace.__getattr__ -> Any`，`dayu/cli/` 下 335 处 `getattr(args, ...)`（`origin/main` 为 57 处）完全不受静态检查约束。「pyright clean」对 CLI 参数层是**空洞信号**，不应作为该层正确性的证据（详见 F2）
- **环境依赖测试**：required lane 中存在至少 1 个环境依赖测试（见「明确排除项」第 1 项），会在开发者本机产生假失败。虽非本 PR 引入，但会持续干扰后续 gate 的验证信号可信度
