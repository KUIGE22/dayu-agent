# Plan Review：Slice 2 AcceptancePlan 运行身份闭包（adversarial）

- Reviewer lane: DeepSeek（只读 adversarial plan review）
- Date: 2026-08-09
- Branch: `feat/investment-agent-acceptance`
- Baseline: `a6cc350`
- Review 对象: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前**未提交**的 Slice 2 plan-fix diff
- 配套 fix artifact: `docs/reviews/plan-fix-20260809-101500-codex.md`
- Scope: 仅审 Slice 2 运行身份 contract 的可实现性与边界闭合；**不是** broad repo review，**未**执行任何 live/付费调用，**未**修改 plan / code / tests / README

## Verdict

**FAIL**（2 项 High 阻断）

Open High 2 / Open Medium 5 / Open Low 4。

方向判断先给结论：**Controller 的 ACCEPT A（扩展唯一 `AcceptancePlan`）/ REJECT B（独立 execution-plan envelope）是正确的**，且在当前代码上可实现（见「已验证成立的部分」）。FAIL 不是因为路线错，而是因为本次 plan-fix 只补了 plan 侧的**写入**闭包，没有同步补 receipt 侧的**输出**闭包与 `verify` 阶段的**自引用**闭包；按当前文本直接交给 implementer，会在两处必然撞墙，且其中一处在本仓库路径下 100% 复现。

---

## 1. 已验证成立的部分（不需修改，列出以免后续 revision 误删）

以下每条都有直接代码证据，可作为 Slice 2 的实现地基：

| 结论 | 证据 |
|---|---|
| 单一 plan identity 在结构上可实现：`to_json()` 是唯一序列化入口，`fingerprint` 直接由它派生，不存在第二条摘要路径 | `utils/investment_agent_acceptance_contracts.py:434`（`to_json`）、`:468-482`（`fingerprint = canonical_json_sha256(self.to_json())`） |
| 加字段不会产生第二 schema：`parse_acceptance_plan` 用 `_strict_object` 精确 key 集合，missing/unknown 均 fail closed | `:1726-1749`（18 键闭合集）、`:2511-2532`（`_strict_object` 同时拒 missing 与 unknown） |
| 「空 token fail closed」无需新原语：现成 helper 已拒空元素与空数组 | `:2918-2939`（`_string_tuple`，逐元素 `_require_nonempty_string`，`allow_empty=False` 拒空数组） |
| subprocess 前的 package 指纹漂移检查已可用，不需在 Slice 2 重造 | `:1948-1983`（`build_package_input_fingerprints`）、`:1986-2003`（`assert_package_input_fingerprints` 全等比较后抛 `FingerprintDriftError`） |
| research tree 的 symlink/非 regular file fail-closed 声明属实：检查发生在后缀过滤**之前**，不会被 `.txt` 类 symlink 绕过 | `:2413-2423`（`is_symlink()` / `S_ISREG` 判断在 `include_all_regular` 后缀过滤之前） |
| Slice 2 白名单排除 evaluator 是安全的：evaluator 对 `AcceptancePlan` 零引用，扩展 dataclass 不会破坏它 | 全文件 grep `AcceptancePlan` on `utils/investment_agent_acceptance_evaluator.py` → 0 命中 |
| schema 层面不存在「任意命令字符串注入」：plan 侧是 argv token tuple，runner 侧 `shell=False`，无 shell fragment 拼接 | plan §5.1 新增第 1 条、§4.2、Slice 2 变更内容第 3 条；`PhaseReceipt.argv` 已是 `tuple[tuple[str, ...], ...]`（`:506`） |

因此对用户提出的「是否产生 cycle / 第二真源 / 任意命令注入」三问，结论分别是：**cycle 有（H1）**、**第二真源有，但在 schema 内部而非 schema 之间（M2）**、**任意命令注入无，但缺结构 allowlist 兜底（M4）**。

---

## 2. High findings（阻断）

### PRF-H1（H）`verify` 阶段进入 ordered phase specs 会构成 fingerprint 自引用，数学上不可满足

**Plan 要求**：§5.1 新增第 1 条要求 ordered commands「精确覆盖三组 download、price import、process、write preflight、付费 write+materialize、validators 与 **verify**」，且第 2 条要求这些字段全部进入 `to_json()` 与唯一 `fingerprint`。

**冲突证据**：§10 第 512 行给出的终局 verify argv 是
`... verify --plan <run-root>/acceptance-plan.json --fingerprint <exact-fingerprint> --json`。
`<exact-fingerprint>` 就是本 plan 自身的 fingerprint。若该 argv 作为 token tuple 写进 plan，则
`fingerprint = SHA256(canonical_json(plan含fingerprint))`
是一个不动点方程，SHA-256 下无法构造解。§5.1 第 2 条同时禁止「额外 argv」和「空 token」，implementer 无法用占位符合法绕过。

**影响**：Slice 2 第一条 happy-path 测试（ordered phase specs strict round trip）就会卡死；implementer 只能自行发明未经 review 的规避方式（占位 token / 事后替换 / 私自剔除 verify），而这正是本次 plan-fix 想消灭的「自行造第二真源」。

**最小修复建议**（三选一，需在 plan 中写死，不留给 implementer 判断）：
1. 把 verify 从 ordered phase specs 中移出，声明为 runner 拥有的**终局固定步骤**，其 argv 由 runner 从「plan 文件路径 + 实时计算的 plan 文件 canonical SHA-256」构造；plan 只绑定「verify 必须作为最后一步执行」这一布尔/枚举事实。
2. 保留 verify 在 specs 中，但明确规定其 argv token tuple 中 `--fingerprint` 的值位以 plan-owned 常量占位符（例如 `"@plan-fingerprint"`）表示，parser 强制该位必须精确等于该占位符，runner 在执行时替换；占位符本身进入 fingerprint，替换值不进入。
3. 取消 §10 中 verify 的 `--fingerprint` 传参，改为 `verify --plan <path>` 自证（读取 plan 文件自算摘要并与内部一致性校验）——但这会削弱 §5.1「live-mode verify 必须同时接受 `--plan --fingerprint`」的互斥模式设计，不推荐。

推荐方案 1：它同时消除 M4 中「`只允许执行计划中列出的 python -m dayu.cli argv` 覆盖不到 verify 阶段」的表述矛盾。

---

### PRF-H2（H）现有 `PhaseReceipt` 原样序列化 raw argv，与新增的 acceptance-owned 输出脱敏 hard gate 直接冲突，且在本仓库路径下必然触发

**Plan 要求**：§5.1 新增第 3 条要求「phase receipts、acceptance receipt、completion report 与可提交 baseline 只输出 package/run-relative locator、argv digest 与 SHA-256，**不复制 raw absolute argv 或 run root**」，并要求 sanitizer 命中 POSIX/Windows home 绝对路径即 fail closed。§6.1 hard gate 9 与 §13 相应 stop condition 同口径。

**冲突证据（已 accepted 的 Slice 1 代码）**：
- `utils/investment_agent_acceptance_contracts.py:506` — `argv: tuple[tuple[str, ...], ...]` 是 raw argv 字段；
- `:535` — `to_json()` 直接 `"argv": [list(command) for command in self.argv]`，无摘要化、无脱敏、无 locator 转换；
- `:1842-1854` — `parse_phase_receipt` 用 `_string_tuple` 原样接收 argv，未做任何绝对路径约束（对比 `FileFingerprint.locator` 走 `_require_safe_locator`，`:258`、`:3001-3020` 明确拒绝绝对路径 / `..` / `~` / 反斜线）。

**必然触发的证据**：§10 每条 argv 都含 `--base <run-root>/data-workspace` 与 `--config <resolved-package-config-dir>`；`resolve_package_config_path()` 返回 `Path(__file__).resolve().parent.parent / "config"` 的绝对路径（`dayu/startup/config_file_resolver.py:24-34`）。本仓库位于 `/Users/wsk/workspace/dayu-agent`，home 为 `/Users/wsk`，故 run root 与 config dir 双双是 home 绝对路径。任何一次真实 `run` 写出的 `phase-receipts/*.json` 都会包含 home 绝对路径 → 命中 hard gate 9 → 每次 live run 必然自判 FAIL。

**为何是 plan 缺陷而非实现缺陷**：Slice 2 白名单**已**包含 `utils/investment_agent_acceptance_contracts.py`（本次 plan-fix 新增），因此修改 `PhaseReceipt` 在权限上可行；但 Slice 2 的「变更内容」与「预期断言」两节**完全没有提到** `PhaseReceipt` / `parse_phase_receipt` 的 argv 表示需要改造，新增的那条 contract 测试断言只覆盖「run root、ordered phase/commands、model binding、required environment names/presence」。implementer 按字面执行会保留原 raw argv 序列化，直到 Slice 5 才在 live 阶段炸开——而 Slice 5 是不可重跑的付费阶段。

**最小修复建议**：
- 在 §5.1 新增第 3 条后补一句所有权声明：`PhaseReceipt` 的 argv 表示必须在 Slice 2 一并收窄为「run-relative / package-relative locator token + 整条 argv 的 canonical SHA-256（argv digest）」，raw absolute argv 只允许存在于 `.gitignore` 覆盖的 `acceptance-plan.json` 与进程内存中；
- 在 Slice 2「允许文件」不变的前提下，把该改造写入「变更内容」，并在「预期断言」补一条：给定含 home 绝对路径的 run root 与 config dir，`PhaseReceipt.to_json()` 输出经 sanitizer 扫描无命中，且 argv digest 与内存中 raw argv 的 canonical SHA-256 相等；
- 同时明确 sanitizer 的 home 判定口径（`Path.home()` 前缀匹配 / `~` 展开 / Windows `C:\Users\` 形态），否则 §5.1「POSIX/Windows home 绝对路径」在实现上无判定标准。

---

## 3. Medium findings

### PRF-M1（M）`规范化 run root` 的规范形式未定义，与现有 locator 校验原语不兼容

§4.2 与 §5.1 只写「解析后的精确 run root」/「规范化 run root」，未规定：绝对 resolved 路径还是仓库相对路径？是否要求位于 `workspace/acceptance/investment-agent-aapl/<run-id>/` 之下？run-id 段的合法字符集？父目录 symlink 拒绝规则是否复用 `_require_regular_directory`（`:2459-2475`）？

代码约束是硬的：现成的 `_require_safe_locator`（`:3001-3020`）**明确拒绝绝对路径**，无法直接复用于 run_root；implementer 必须新造一个校验器，而 plan 没有给出它的规则。同时 §8.3 cleanup 已经要求「只允许接收一个已解析、位于 `workspace/acceptance/investment-agent-aapl/` 下的精确 run-id 目录」——这条 containment 规则应当在 plan 层就绑到 run_root 字段上，而不是只写在 cleanup 段。

另一未言明的后果：若 run_root 以绝对路径入 fingerprint，则 plan fingerprint 变为**机器绑定**，跨机 `verify` 必然失败，且 Slice 2 的「fixed-clock byte stability」测试不能钉死字面 digest（必须从 tmp_path 派生期望值）。这一点需要显式写进 plan，否则 implementer 会写出在 CI 上不稳定的测试。

**最小修复**：在 §5.1 规定 run_root 的 canonical 形式（建议：绝对 resolved POSIX 字符串）、containment 前缀、run-id 字符集、父目录非 symlink 要求，并在 §8.2 复现段补一句「plan fingerprint 因含绝对 run root 而机器绑定，跨机复核只比对 package/price/budget/as-of 子指纹」。

### PRF-M2（M）模型名、run root、config dir 在同一 schema 内出现两次，parser 未被要求校验其一致性 —— 第二真源被从「schema 之间」搬进了「schema 内部」

plan-fix 的核心论证是「另造 envelope 会让 evaluator/runner/verify 依赖不同身份」。但按当前文本，扩展后的单一 `AcceptancePlan` 内部会同时存在：
- 独立字段 `primary=deepseek-v4-pro` / `audit=mimo-v2.5-pro-thinking`，**以及** write argv token 中的 `--model-name deepseek-v4-pro` / `--audit-model-name mimo-v2.5-pro-thinking`（§10 L476-489、L494-510）；
- 独立字段 run_root，**以及** 每条 argv 中的 `--base <run-root>/data-workspace`、`--output <run-root>/write`、`--research-base <run-root>/research`；
- package config tree 指纹，**以及** 每条 argv 中的 `--config <resolved-package-config-dir>`。

§5.1 第 2 条只列举了「missing、unknown、重复 phase/command、顺序变化、空 token、绝对程序替换或模型/env-name 漂移」fail closed，**没有要求 parser 校验字段与 argv 的互相一致**。结果：一份 fingerprint 完全合法的 plan 可以声明 `primary=deepseek-v4-pro` 却在 argv 里写另一个模型名，或字段 run_root 与 argv 内 run root 指向不同目录。这正是 REJECT B 想避免的失效模式，只是换了个位置。

顺带一处表述矛盾：§4.2 说「Slice 2 **最小扩展**」，但同时要求把全部 argv 塞进同一 frozen dataclass；结合 AGENTS.md「禁止 God dataclass」（`AGENTS.md:45`），需要在 plan 中明确 ordered phase specs 是一个独立的 frozen 子类型（例如 `PhaseCommandSpec`）组成的 tuple，由 `AcceptancePlan` 持有，而不是把 argv 平铺进 `AcceptancePlan` 字段。

**最小修复**：在 §5.1 第 2 条补一条 parse 期不变量：「argv token 中出现的 run root 前缀、config dir、model name 必须与同 plan 内对应字段精确相等，不等即 fail closed」；在 §4.2 明确子类型分层，避免 God dataclass。

### PRF-M3（M）environment presence 的读取边界，§5.1 与 §13 自相矛盾；presence 只在 prepare 采样，付费阶段前不再复核

- §5.1 第 2 条：「只有获授权的 live `prepare` 才读取环境变量是否存在」。
- §13 stop condition 第 3 条：「live `prepare`/`run` 中 `MIMO_API_KEY`/`DEEPSEEK_API_KEY`/`SEC_USER_AGENT` 所需名称缺失……立即停止」——明确把 `run` 纳入检查主体。

两条不能同时成立。按 §5.1 实现的后果是实质性的：presence boolean 在 prepare 时被写入 fingerprint，`run` 只做 fingerprint 比对而不重读环境；于是「prepare 时 key 在，run 前 key 被移除或换 shell」这一常见场景下，三组 SEC download、material import、process 会全部照常执行（这些不需要模型 key），直到进入 write 才因鉴权失败中断——已消耗 wall-clock 与 SEC 配额，且落在 §8.1「write 中断需 Controller 再次确认剩余预算」的昂贵恢复路径上。

**最小修复**：统一为「presence 由一个显式 presence provider 提供；deterministic 测试注入 mapping，live 路径的 provider 读取 `os.environ` 的 key 存在性；`prepare` 与 `run` **都**调用该 provider，`run` 侧结果与 plan 内 presence 不一致时在首次 `Popen` 前 fail closed」。这既满足「deterministic 不读宿主 env」，也消除 §13 的矛盾，且仍然不读取/不 hash/不持久化值。

### PRF-M4（M）argv 安全仅依赖 fingerprint 完整性，缺结构 allowlist；且「只允许 `python -m dayu.cli` argv」覆盖不到 verify 阶段

§5.1 第 1 条禁止「任意 command string、shell fragment、未知 phase 或额外 argv」，Slice 2 变更内容称「只执行……每个 `dayu.cli` argv」。但：
1. 终局 verify 阶段执行的是 `python -m utils.investment_agent_acceptance`，不是 `dayu.cli`，规则文本自身覆盖不全；
2. 全部防线是「`run` 要求 `--fingerprint` 精确匹配」。fingerprint 保证的是**完整性**（plan 未被篡改），不是**安全性**（plan 内容本身合法）。一份 plan 文件 + 其配套 fingerprint 成对提供时（例如从他人处拷贝一个 run root 目录、或 prepare 逻辑本身被改动过），fingerprint 校验会全部通过，而 argv[0] 可以是任意可执行程序。§5.1 提到「绝对程序替换……fail closed」，但没有给出判定规则。

**最小修复**：在 §5.1 规定 phase spec 的结构 allowlist，且必须在 parse 期（而非 run 期）执行：
- argv[0] 必须精确等于当前解释器（`sys.executable`）；
- argv[1] 必须为 `-m`；argv[2] ∈ `{"dayu.cli", "utils.investment_agent_acceptance"}`（若采纳 H1 方案 1，则收窄为仅 `dayu.cli`）；
- argv[3]（子命令）必须属于固定枚举 `{download, upload_material, process, write, research-template}`；
- 所有形如路径的 token 必须以 run_root 或 resolved config dir 为前缀；
- phase name 必须属于 plan-owned 固定枚举，且 specs 序列必须精确等于固定顺序（不得排序规范化，见 PRF-L2）。

### PRF-M5（M）ordered phase specs 与 `PhaseReceipt` 之间无闭合要求，执行侧可声明计划外阶段

`parse_phase_receipt`（`:1846`）对 `phase_name` 只做 `_require_nonempty_string`，argv 只做 `_string_tuple`，不与任何 plan 校验。本次 plan-fix 在 plan 侧建立了 ordered specs，却没有在 §5.4 或 Slice 2 断言中要求「每个 phase receipt 的 phase_name 必须命中 plan specs 中的同名 phase，且其 argv（或 argv digest）必须与该 spec 精确一致，且 receipt 序列必须是 specs 的前缀」。缺了这条，run 身份闭包只覆盖「计划写了什么」，不覆盖「实际跑了什么」，§6.1 hard gate 4（wall-clock 不得重置）与 §8.1 的「只执行允许的前缀阶段」在 verify 侧无可机械复核的依据。

**最小修复**：在 §5.4 补「phase receipt ↔ plan specs 的前缀闭合规则」，并在 Slice 2 预期断言补一条：注入一个 phase_name 不在 specs 中、或 argv 与 spec 不符的 receipt，`verify` 必须 FAIL。

---

## 4. Low findings

### PRF-L1（L）plan-fix artifact 的 Controller 决策依据与代码不符
`docs/reviews/plan-fix-20260809-101500-codex.md:18` 称「其 `AcceptanceInputs.plan` 继续消费同一扩展 dataclass」。对 `utils/investment_agent_acceptance_evaluator.py` 全文件 grep `AcceptancePlan` → **0 命中**。结论（evaluator 不入白名单）依然正确且更安全，但论据不成立，应改为「evaluator 当前对 `AcceptancePlan` 零引用，扩展不影响它」。副作用是：plan↔evaluator 之间当前**没有任何**类型级耦合校验，新增的运行身份字段不会被 evaluator 复核——这一点应作为 residual 写入 §14。

### PRF-L2（L）现有 helper 会规范化顺序，与「reorder 必须 fail closed」相反，存在照抄风险
`_fixed_research_artifacts`（`:2961-2979`）对输入按 `frozenset` 比较后**返回常量顺序**，即输入顺序被丢弃。ordered phase specs 的要求恰好相反（§5.1 第 2 条：「顺序变化……fail closed」）。plan 应显式声明「phase 顺序是 fingerprint 敏感字段，禁止排序规范化」，避免 implementer 复用该模式。

### PRF-L3（L）`_PLAN_SCHEMA_VERSION` 是否 bump 未决，且现存 literal 与常量不一致
新增 4 组必填字段是 breaking schema change，plan 未说明 `_PLAN_SCHEMA_VERSION`（`:33`，当前为 1）保持还是升 2。另注意 `parse_acceptance_plan` 在 `:1750-1752` 硬编码字面量 `1`，而 `parse_acceptance_receipt` 在 `:1891-1895` 使用 `_RECEIPT_SCHEMA_VERSION` 常量——AGENTS.md 明令禁止魔法数字（`AGENTS.md:41`）。implementer 本就要改这段，plan 应顺带指定：bump 到 2，并把字面量改为常量引用，使旧的本地 `acceptance-plan.json` 以明确的 schema_version 失败而非 unknown-field 失败。

### PRF-L4（L）新增运行身份字段不进入 deterministic 验收 lane，仅有单测覆盖
Slice 0 允许文件中没有 plan fixture，§11 的 deterministic 验收命令是 `verify --fixture <dir>`，该路径不消费 `AcceptancePlan`。因此 run root / ordered specs / model binding / env presence 只被 round-trip 单测与 fake-runner 测试覆盖，永远不进入「deterministic 端到端」证据链。这是可接受的取舍，但应写入 §14 残余风险表，否则易被误读为「deterministic lane 已验证运行身份」。

---

## 5. 用户指定检查点的逐项结论

| 检查点 | 结论 | 关联 finding |
|---|---|---|
| 单一 plan identity 是否可实现 | **可实现**，`to_json`/`fingerprint`/`_strict_object` 结构支持；但 verify 阶段自引用使当前文本不可满足 | PRF-H1 |
| run_root 严格字段是否足以闭合 | **不足**：canonical 形式、containment、run-id 字符集、父目录 symlink 规则全部未定义 | PRF-M1 |
| ordered phase command specs 是否足以闭合 | **不足**：缺结构 allowlist、缺与 receipt 的前缀闭合、缺「禁止排序规范化」声明 | PRF-M4 / M5 / L2 |
| model binding 是否足以闭合 | **不足**：与 argv 内模型名构成 schema 内双写，parser 未被要求校验一致 | PRF-M2 |
| env presence 是否足以闭合 | **不足**：§5.1 与 §13 矛盾；presence 只在 prepare 采样，付费阶段前不复核 | PRF-M3 |
| deterministic 与 live env 读取边界 | **不闭合**，同上；建议统一为显式 presence provider | PRF-M3 |
| raw absolute argv 与 acceptance-owned sanitizer 边界 | **冲突且在本仓库必然触发**：`PhaseReceipt` 原样序列化 raw argv，run root 与 config dir 均在 home 下 | PRF-H2 |
| Slice 2 允许文件是否完整 | **完整**（contracts + acceptance.py + tests）；evaluator 排除可验证安全，但排除理由的论据不成立 | PRF-L1 |
| Slice 2 测试断言是否完整 | **不完整**：缺 PhaseReceipt 脱敏断言、缺 receipt↔specs 闭合断言、缺 argv 结构 allowlist 断言 | PRF-H2 / M4 / M5 |
| Stop conditions 是否完整 | **基本覆盖**（§13 已含 run root 漂移），但缺「plan 内字段与 argv 不一致」「argv 程序不在 allowlist 形状」两条 | PRF-M2 / M4 |
| 是否产生 cycle | **是**：verify 阶段 `--fingerprint` 自引用 | PRF-H1 |
| 是否产生第二真源 | **是，但在 schema 内部**：模型名 / run root / config dir 双写且无一致性校验 | PRF-M2 |
| 是否产生任意命令注入 | **否**（token tuple + `shell=False`，无字符串拼接）；残余风险是缺结构 allowlist 时 fingerprint 只保完整性不保安全性 | PRF-M4 |

---

## 6. 放行条件

修复以下项后可进入下一轮双路 plan re-review：

1. **PRF-H1**：在 plan 中固定 verify 阶段的去自引用方案（推荐移出 ordered specs，作为 runner-owned 终局步骤）。
2. **PRF-H2**：在 §5.1 与 Slice 2 变更内容/预期断言中显式声明 `PhaseReceipt` argv 表示改为 locator + argv digest，并给出 home 绝对路径的判定口径。
3. **PRF-M1..M5**：按各条最小修复补齐 run_root 规范形式与 containment、argv↔字段一致性不变量、presence provider 统一边界、argv 结构 allowlist、receipt↔specs 前缀闭合。
4. **PRF-L1..L4**：修正 plan-fix 论据、声明顺序敏感、指定 schema_version 处置、把「运行身份字段不入 deterministic lane」写进残余风险表。

未修复前，Slice 2 **不得**恢复实施。本 review 不授权任何 SEC / Web / DeepSeek / MiMo / 真实凭据检查或付费运行；Slice 5 维持 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED`。

---

## 7. Review 边界声明

- 本 review 只读；未修改 plan / 生产代码 / 测试 / README。
- 未运行任何 live、付费或联网命令；未运行 pytest / pyright（本轮为 plan review，非 code review）。
- 代码证据来自 baseline `a6cc350` 的工作树；plan 证据来自当前未提交 diff。
- 未覆盖：Slice 0/1 已 accepted 内容的重审、evaluator 评分规则、Slice 3–5 的实现细节、仓库其它模块。
