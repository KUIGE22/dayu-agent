# Plan Re-Review（corrective）：Slice 2 AcceptancePlan v2 运行身份闭包

- Reviewer lane: DeepSeek（只读 corrective re-review）
- Date: 2026-08-09
- Branch: `feat/investment-agent-acceptance`
- Baseline: `a6cc350`
- Review 对象: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 diff（mtime 10:30:14）+ `docs/reviews/plan-fix-20260809-101500-codex.md`（mtime 10:30:14）
- 前序 finding 真源: `docs/reviews/plan-review-20260809-101700-deepseek.md`（FAIL，H2/M5/L4）
- Scope: **仅**核对前序 H2/M5/L4 是否关闭。未做广审，未复审 Slice 0/1/3/4/5，未修改任何文件，未运行 live/付费/联网命令。

## Verdict

**PASS**

Open High **0** / Open Medium **1** / Open Low **1**。

两项 High 已用正确的机制性修复关闭，不是文字规避：verify 自引用通过「terminal action 移出 fingerprinted specs、指纹算完后派生」在数学上消解；PhaseReceipt raw argv 泄漏通过「schema v2 + 三 placeholder 安全 token matrix + raw argv digest」在数据结构上消解，且我复核确认该方案不需要改动 evaluator（这一点原 plan-fix 的论据是错的，本次也已同步修正）。5 项 Medium、4 项 Low 全部关闭，其中 M2 的修复（纯构造器重建 + canonical equality）强于我原本建议的成对一致性校验。

新增的 1 Medium / 1 Low 均为 v2 契约与 plan 既有章节的**同步缺口**，不改变上述结论，但应由 Controller 在 Slice 2 恢复前一并 adjudicate。

---

## 1. 前序 findings 逐项关闭核对

### PRF-H1 verify fingerprint 自引用 — **CLOSED**

新文本（§5.1）：`fingerprinted ordered specs 不包含 terminal verify argv`；plan 增加第 (5) 项 `terminal action 精确等于 verify`；`runner 只在 plan canonical SHA-256 已计算并核对后，由固定 terminal action 派生 verify --plan <plan> --fingerprint <computed> --json，不得接受用户覆盖`。ordered specs 收窄为「三组 download、price import、process、write preflight、付费 write+materialize 与五个 validators」。

核对：不动点方程被拆除——fingerprint 只对不含自身的 specs 计算一次，verify argv 是 fingerprint 的**下游派生**而非上游输入。采纳的是我建议的方案 1（runner-owned 终局步骤），且比我的表述更严：terminal action 本身作为 enum 进入 fingerprint，所以「是否执行 verify」仍受篡改保护，只有其 `--fingerprint` 值位不进入。plan-fix artifact L25 同步描述一致。Slice 2 预期断言新增「plan fingerprint 一次计算完成且 terminal verify 在其后派生；不存在 fingerprint 占位符、二次写回或自引用」，可机械验证。

§10 L520 仍展示 `verify --plan ... --fingerprint <exact-fingerprint>` 的 argv 形状——与新规则一致（它正是派生出的终局命令，不是 fingerprinted spec），非残留矛盾。

### PRF-H2 PhaseReceipt raw absolute argv 与 sanitizer 冲突 — **CLOSED**

新文本（§5.1）：`PhaseReceipt` 升 schema v2，`只持久化以 <PYTHON>、<RUN_ROOT>/...、<PACKAGE_CONFIG>/... 精确替换的安全 argv token matrix，以及每条 raw argv canonical JSON 的 SHA-256`；raw argv 只存在于 local plan 与进程内存；`parse_phase_receipt()` 拒绝 v1、home 绝对路径、未知 placeholder 或 digest 数量不闭合。

**三个 placeholder 的充分性我逐条复核过**：§10 全部 argv 中的绝对 token 只有三类来源——解释器（`.venv/bin/python`，本仓库下为 `/Users/wsk/workspace/dayu-agent/.venv/...`，属 home 路径，由 `<PYTHON>` 覆盖）、run root 派生路径（`--base <run-root>/data-workspace`、`--output <run-root>/write`、`--research-base <run-root>/research`、`--files <run-root>/inputs/...`、validators 的 `--base <run-root>/research` 与 13 产物路径，由 `<RUN_ROOT>` 覆盖）、resolved config dir（`--config`，由 `<PACKAGE_CONFIG>` 覆盖）。外部 price snapshot JSON 的原绝对路径本就被 §5.1 既有条款禁止入 receipt。**无第四类绝对 token**，三 placeholder 闭合。

**evaluator 无需修改这一点已代码复证**：`utils/investment_agent_acceptance_evaluator.py:37` 导入 `PhaseReceipt`；`:892` `phase_payloads = tuple(receipt.to_json() for receipt in inputs.runtime.phase_receipts)` 并入 `_evaluate_acceptance_owned_outputs`；`:96-99` `_HOME_PATH_PATTERNS` 已实现 POSIX `/(?:Users|home)/[^/\s]+` 与 Windows `[A-Z]:\\Users\\` 两种形态。因此 (a) v2 输出会被自动扫描，(b) 我上一轮要求的「home 判定口径」已有现成真源，implementer 无需自创规则，(c) Slice 2 白名单不含 evaluator 是安全的。plan §4.2 与 plan-fix L18 均已把耦合事实改写为「真实跨模块边界是 `PhaseReceipt.to_json()` 被 evaluator 扫描」，与代码相符。

Slice 2 预期断言新增「给定真实 home 下的 absolute run/config argv，PhaseReceipt v2 输出只含三个受控 placeholder 与 raw argv digest，evaluator sanitizer 不产生 finding；v1 receipt 与 plan 均明确拒绝」——正是我要求的反向证明形态。

### PRF-M1 run root 规范形式 — **CLOSED**

新增专条：`Path.resolve(strict=False)` 绝对 POSIX 字符串；父目录必须真实存在、resolved、非 symlink；精确位于 repository root 的 `workspace/acceptance/investment-agent-aapl/` 下；run-id 段 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`；目标本身必须不存在。四项缺口全补。首字符类排除 `.`，故 `..` 与隐藏段不可构造，containment 无法被相对段绕过。机器绑定后果已显式写入（「跨机或换目录必须重新 `prepare`，不得复用 fingerprint」）并进入残余风险表，消除了我提出的「跨机 verify 必失败 / CI 测试不能钉死字面 digest」隐患。

### PRF-M2 schema 内双写、无一致性校验（第二真源） — **CLOSED**

新文本要求 `run preflight 通过同一纯构造器从 plan scalars、runtime resolver 与 sys.executable 重建完整 specs 并要求 canonical equality`，并把「字段/argv 双写不一致」列入 fail closed。

这比我建议的「逐字段与 argv 成对比对」更强：重建-比对使 argv 成为 plan scalars 的**纯函数**，任何字段/argv 分叉在构造阶段即不可表达，而非事后检测。同时 §4.2 明确「复用既有 `ModelRoles`」（模型名单一真源，避免第三处定义）与「ordered specs 使用独立 frozen 子类型组成 tuple，禁止把 argv 平铺成 God dataclass」，同时关闭我附带指出的 AGENTS.md:45 God dataclass 风险。

### PRF-M3 presence 读取边界矛盾 — **CLOSED**

新增专条：显式 provider；deterministic 注入 mapping 且禁读宿主环境；`live prepare 与 run 都读取 os.environ 的 key 是否存在`；`run` 在首次 `Popen` 前要求与 plan 内三个 `true` 精确一致；`verify` 只读不重读环境；任何路径不读取/hash/回显/持久化值。与 §13 L645（`live prepare/run 中 ... 名称缺失`即 stop）现已同口径，矛盾消除。我指出的「prepare 后 key 失效 → 烧完 SEC 配额与 wall-clock 才在 write 炸」这一昂贵失效路径被前移到首次 `Popen` 前拦截。Slice 2 断言含「live fake presence provider 在 prepare 后移除任一 required name，`run` 必须在首次 `Popen` 前停止」，可复证。

### PRF-M4 缺 argv 结构 allowlist — **CLOSED**

新文本：`argv[0] 必须等于本次解释器，argv[1:3] 必须等于 -m dayu.cli，subcommand/phase/flags 属固定 allowlist；run-root、config、model 与 budget tokens 必须与 plan 字段和本次 resolver 结果一致`；显式拒绝 command string、shell fragment、未知 phase、额外 argv、空 token、任意 executable。

我上一轮指出的「`只允许 dayu.cli argv` 覆盖不到 verify 阶段」的表述矛盾也随 H1 一并消失：verify 已移出 ordered specs，故 `-m dayu.cli` 对全部 specs 成为**无例外**约束，而 terminal verify 是零用户输入的固定派生命令，无注入面。fingerprint 只保完整性、不保内容合法性的缺口，由 parse 期结构校验 + run 期重建等价共同补上。

### PRF-M5 receipt 与 specs 无闭合 — **CLOSED**

新增专条：非 terminal receipt 的 `phase_name`、安全 argv 与 digest 必须精确命中同名 planned spec；已有 receipts 顺序只能是 ordered specs 的**成功前缀**；首个 nonzero/timeout/signal/mismatch 后不得存在后续 receipt；terminal verify receipt 只允许在全部 specs 成功后出现；未知/重复/skip/reorder/digest mismatch 在 `verify` 中 FAIL。

粒度问题我另行核对过：§5.4 的 receipt 文件比 specs 粗（`download.json` 含 3 条命令、`validations.json` 含 5 条），而 spec 定义为「phase name + **one-or-more** argv token tuples」，故 phase↔receipt 文件仍是 1:1，前缀闭合规则可实现，不存在映射歧义。这使 §6.1 hard gate 4（wall-clock 不得重置）与 §8.1「只执行允许的前缀阶段」首次具备可机械复核的依据。

### PRF-L1 plan-fix evaluator 论据不成立 — **CLOSED**

plan-fix L18 已改为「它当前不导入或消费 `AcceptancePlan`，扩展 dataclass 不影响 evaluator；真实跨模块耦合是 evaluator 会把 `PhaseReceipt.to_json()` 作为 acceptance-owned output 扫描」。经代码复证属实（见 H2 段）。结论（evaluator 不入白名单）不变且论据现在正确，并顺带把真实耦合点显式化——这正是 H2 修复必须落在 contracts owner 的理由。

### PRF-L2 顺序敏感 vs 现有排序规范化 helper — **CLOSED**

新文本：`phase name 与顺序是 fingerprint-sensitive，禁止排序规范化`。可避免 implementer 照抄 `_fixed_research_artifacts`（contracts.py:2961-2979，该 helper 按 `frozenset` 比较后返回常量顺序、丢弃输入顺序）的模式。

### PRF-L3 schema version 处置未决 — **CLOSED（plan 侧）**

新文本：`_PLAN_SCHEMA_VERSION 升为 2，parser 使用常量而非 magic literal，并明确拒绝 v1、不写兼容分支`。同时 `PhaseReceipt` 升 v2 且 `parse_phase_receipt()` 拒绝 v1。符合 AGENTS.md:51「默认按全新设计，不为旧实现保留兼容逻辑」。我另行确认工作树中不存在任何已生成的 `acceptance-plan.json`（`find` 零命中），故拒绝 v1 无现存数据代价。残留的常量化措辞缺口见 PRR2-L1。

### PRF-L4 运行身份字段不入 deterministic lane — **CLOSED**

§14 残余风险表新增行：「AcceptancePlan v2 的 run root、命令与 env presence 只由 Slice 2 contract/fake-runner tests 覆盖，不进入 fixture-only deterministic verify；且 fingerprint 有意绑定当前机器与 run-id」，跟踪去向含「跨机或换 run-id 必须重新 prepare，Slice 5 gate 展示当前机器生成的 exact fingerprint」。与 §11 的 `verify --fixture` deterministic 命令边界一致，不再可能被误读为「deterministic lane 已验证运行身份」。

---

## 2. 本轮新增 findings

### PRR2-M1（M）§5.4 产物 inventory 未随 v2 同步：缺 terminal verify receipt 文件，且字段清单仍写 `argv`

两处证据（§5.4，plan L163-169 与 L197）：

1. `phase-receipts/` 固定树只列 `prepare / download / price-snapshot-import / process / write-preflight / write / validations` 七个文件，**没有** terminal verify receipt 的文件名。但 §5.1 新增条款要求「terminal verify receipt 只允许在全部 specs 成功后出现，其 raw digest 由固定派生命令重算」，且 receipt 前缀闭合逻辑必须能定位它。implementer 将被迫自行发明该文件名——而 receipt 身份正是本次 plan-fix 要收归 plan-owned 的东西。
2. 同节末段仍写「所有 phase receipt……统一记录 `status/started_at/ended_at/duration_seconds/remaining_wall_seconds/**argv**/exit_code/stop_reason`」。v2 下持久化的不再是 `argv` 而是安全 token matrix + raw argv digest。§5.4 若被当作权威字段清单读取，会与 §5.1 的 v2 契约冲突。

影响：不会导致「错误但通过」的运行，属 plan 内部一致性缺口；但它落在刚刚用于关闭 H2/M5 的两条规则上，建议在 Controller 关闭本轮 findings 时一并修。

**最小修复**：§5.4 树中补 terminal verify receipt 的确定文件名（例如 `verify.json`），并把末段字段清单改为「`status/started_at/ended_at/duration_seconds/remaining_wall_seconds/safe_argv/argv_digests/exit_code/stop_reason`」，同时注明该文件为可选、只在全部 specs 成功后出现。

### PRR2-L1（L）schema-version 常量化只对 plan parser 明写，phase receipt parser 未明写

§5.1 只说「`_PLAN_SCHEMA_VERSION` 升为 2，parser 使用常量而非 magic literal」。但 `parse_phase_receipt` 现有实现同样存在 magic literal：`utils/investment_agent_acceptance_contracts.py:1834-1836` 硬编码 `_expect_equal(..., 1, "phase_receipt.schema_version")`，而同文件 `parse_acceptance_receipt`（:1891-1895）已使用 `_RECEIPT_SCHEMA_VERSION` 常量。implementer 本轮必须改这一行（v1→v2），若照原样写字面量 `2` 即违反 AGENTS.md:41 魔法数字禁令。

**最小修复**：把 §5.1 该句改为「`_PLAN_SCHEMA_VERSION` 与 `_PHASE_SCHEMA_VERSION` 均升为 2，两个 parser 都使用常量而非 magic literal」。

---

## 3. 本轮结论与放行条件

- 前序 **H2 / M5 / L4 共 11 项 findings 全部 CLOSED**，均有可复证的 plan 文本 + 代码证据，无文字规避、无把问题下推给 implementer 的情况。
- 本 corrective revision 在我这一路 **PASS**。
- 新增 PRR2-M1 / PRR2-L1 属 plan 内部同步缺口，不阻断本次 corrective scope 的判定；建议 Controller 在关闭本轮 findings 时一并处理，再按 gate 规则（DeepSeek + MiMo 双路 PASS 且全部 findings 关闭）放行 Slice 2 恢复实施。
- 本 review 不授权 SEC / Web / DeepSeek / MiMo / 真实凭据检查或付费运行；Slice 5 维持 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED`。

## 4. Review 边界声明

- 只读；未修改 plan / 生产代码 / 测试 / README / fixture。
- 未运行 live、付费、联网命令；未运行 pytest / pyright（本轮为 plan re-review）。
- 代码证据取自 baseline `a6cc350` 工作树：`utils/investment_agent_acceptance_evaluator.py:37/96-99/892`、`utils/investment_agent_acceptance_contracts.py:1834-1836/1891-1895/2961-2979`、`dayu/startup/config_file_resolver.py:24-34`。
- 未覆盖：Slice 0/1 已 accepted 内容重审、evaluator 评分规则、Slice 3–5 实现细节、MiMo lane findings 的独立复核、仓库其它模块。
