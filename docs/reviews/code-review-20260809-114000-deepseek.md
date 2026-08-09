# Slice 2 Adversarial Code Review — investment-agent-aapl-acceptance

- 时间：2026-08-09 11:40 CST
- 基线：`a99322c`（Slice 2 only）
- Reviewer lane：deepseek（只读）
- 审查范围：`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance.py`、`tests/test_investment_agent_acceptance.py`
- Accepted plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Implementation artifact：`docs/reviews/slice-2-aapl-acceptance-implementation-20260809-113054-codex.md`
- 执行边界：未修改任何文件、未执行 live/SEC/DeepSeek/MiMo/网络调用、未启动子 agent；只运行了只读 pytest 与 pyright。

## 结论

**FAIL**

不是因为工程质量差——恰恰相反，identity/argv/receipt/timeout 这几条最难做对的主链路做得相当扎实（见「已验证为正确的攻击面」）。判 FAIL 的唯一决定性理由是 **H-1**：live lane 的 freshness hard gate 在当前实现下被构造成恒真命题，`source_price_closed` 这个 accepted plan §6.1 gate 8 明确要求的 hard gate 对 latest-discovery 维度**永远不可能失败**。这是 gate 语义被架空，不是风格问题；在 Slice 5 真实 live 执行时，它会让"最新 10-K/10-Q 与本次 discovery 对齐"这一条以 PASS 姿态静默通过。

H-2（`download.json` 分段记录缺失）与 H-1 同源：正因为 receipt 里没有独立的 discovery 证据，`_evaluate_live_plan` 才只能回头从 inventory 自己造 discovery。修 H-2 是修 H-1 的前提。

其余 M/L findings 不单独构成 FAIL，但 M-1（fixed `/tmp` 根）在多用户机器上是真实可利用的拒绝服务面，建议与 H 一并处理。

## Findings

| ID | 级别 | 位置 | 摘要 |
|---|---|---|---|
| H-1 | High | `investment_agent_acceptance.py:2927-2942` | live freshness gate 自引用，`source_price_closed` 的 latest-discovery 分支恒真 |
| H-2 | High | `investment_agent_acceptance.py:2107-2151` | phase receipt 无分段 command records，违反 plan §5.2/§5.4 对 `download.json` 的硬性要求 |
| M-1 | Medium | `investment_agent_acceptance.py:2855-2861` | fixture verify 使用共享 `/tmp` 下固定路径 + 目录锁，可被预创建永久拒绝服务 |
| M-2 | Medium | `investment_agent_acceptance.py:2109-2117` | whole-run wall clock 耗尽被记为 `failed`/`partial_by_timeout=False`，与 plan §7/§8.1 冲突 |
| M-3 | Medium | `investment_agent_acceptance.py:2829` | stderr 只留布尔式分类码，未保存 plan §7 要求的「脱敏摘要和 SHA-256」 |
| M-4 | Medium | `investment_agent_acceptance.py:3015-3039` | 价格 material 闭合只比 `report_date`，未比对 `plan.price_material_sha256` |
| M-5 | Medium | `investment_agent_acceptance.py:966-967, 2026-2027` | `--untracked-files=normal` + `dirty=bool(status)` 使任何新增未跟踪文件都令 plan 失效 |
| L-1 | Low | plan §5.4 vs 实现 | `source-inventory.json` 在 run root 从未写出 |
| L-2 | Low | `investment_agent_acceptance.py:91, 2921-2925` | `_WINDOW_FORMS` 定义后无引用，同一组 form 字面量在 live 路径重复硬编码 |
| L-3 | Low | `investment_agent_acceptance.py:2849-2854, 2874-2888` | fixture 预算/wall/评估时刻为魔法数字，违反 AGENTS.md 禁令 |
| L-4 | Low | `investment_agent_acceptance.py:2746-2813` | `_atomic_write_bytes` 的残留临时文件会让整次 verify 因「未知 receipt」失败 |
| L-5 | Low | `investment_agent_acceptance.py:25-28` | 依赖私有模块 `dayu.cli.commands._research_template_materialize` 与三个具体 `Fs*Repository` 实现类 |

---

## H-1 — live freshness hard gate 自引用，构成恒真命题

**证据。** `utils/investment_agent_acceptance.py:2927-2942`：

```python
preliminary = build_source_inventory_from_repositories(
    RepositoryInventoryRequest(
        ...
        live_freshness_claimed=True,
        source_windows=windows,
        latest_discovery=(),
        ...
    )
)
latest_discovery = _latest_discovery_from_inventory(preliminary)
inventory = replace(preliminary, latest_discovery=latest_discovery)
```

`_latest_discovery_from_inventory`（:2984-3012）的选取逻辑：

```python
latest = max(candidates, key=lambda item: (item.filing_date, item.document_id))
```

evaluator 侧 `_evaluate_latest_discovery`（`investment_agent_acceptance_evaluator.py:1314-1339`）用**完全相同的比较函数**回查：

```python
latest = max(candidates, key=lambda item: (item.filing_date, item.document_id))
if latest.accession is None or latest_by_form.get(form) != latest.accession:
    findings.append(_high("inventory.latest_discovery", "source_price_closed", ...))
```

两侧同源同序，`latest_by_form.get(form)` 恒等于 `latest.accession`。该 finding 在 10-K/10-Q 上**在任何输入下都不可能产生**。

**为什么这是 High。** accepted plan §5.2 明确写：

> 最新 10-K/10-Q 必须与本次各自 SEC discovery 结果中的最新可用 accession 对齐。
> deterministic fixture 的 pinned accessions 只用于回归，不用于声明"今天最新"；**live freshness 只能由本次 discovery receipt 证明**。

plan §6.1 gate 8 把它列为 hard gate（`source_price_closed`），§6.1 抬头写明"任一失败则总结果 FAIL，不以分数抵消"。当前实现让这个 gate 的 latest-discovery 分支退化为对自身的一致性检查——它证明的是"仓储里最新的那份就是仓储里最新的那份"，而不是"仓储里最新的那份就是 SEC 本次告诉我们的最新那份"。真实失效场景：download 阶段因分页、限流或窗口边界少抓了一份刚发布的 10-Q，仓储里最新的是上一季度那份，当前 gate 依然 PASS。

`DEF 14A` 的处理进一步暴露了这个结构：evaluator 的 `required_forms` 含 `DEF 14A`，而 `_latest_discovery_from_inventory` 只为 `("10-K", "10-Q")` 构造 pair，因此 `DEF 14A` 的 `latest_by_form.get("DEF 14A")` 返回 `None`——那一条是可以真实触发的。同一个 gate，两个 form 恒真、一个 form 有效，说明 `latest_discovery` 的语义在生产路径上并没有真正的外部真源。

**最小修复。** 把 discovery 事实从 receipt 读，不从被校验对象读。依赖 H-2 先落地：

1. `_execute_phase` 为 `download` 阶段的每条命令解析 `dayu.cli download` 的 stdout discovery 摘要，写入 receipt 的分段 command records（H-2）。
2. `_evaluate_live_plan` 改为从 download receipt 的分段记录提取 `(form, accession)`，不再调用 `_latest_discovery_from_inventory`：

```python
latest_discovery = _latest_discovery_from_download_receipt(receipts)
inventory = replace(preliminary, latest_discovery=latest_discovery)
```

3. 删除 `_latest_discovery_from_inventory`；它的存在本身就是这个 gate 被短路的载体。
4. 补一条测试：注入一份 receipt 声明的 accession 与仓储最新文档不一致的 fixture，断言 `source_price_closed` 产生 High finding、verdict 为 `FAIL`。

若 Slice 2 阶段确实还拿不到 discovery receipt（Slice 3 才做 partial receipt integration），则**不能保留一个恒真实现冒充已闭合的 gate**——正确做法是让 `_evaluate_live_plan` 在 latest_discovery 无外部真源时直接 `raise ContractError`，fail closed，并在 plan 中把该 gate 的闭合显式记为 Slice 3 owner。

---

## H-2 — phase receipt 无分段 command records

**证据。** `utils/investment_agent_acceptance.py:2107-2151`，`_execute_phase` 对一个 phase 内的多条命令循环执行，但只写**一份聚合 receipt**：

```python
for command in spec.commands:
    ...
    result = _execute_command(command, ...)
    if result.status != "passed":
        break
...
safe_argv, digests = safe_argv_and_digests(spec.commands, ...)   # 注意：spec.commands，全量
receipt = PhaseReceipt(
    ...
    safe_argv=safe_argv,
    argv_digests=digests,
    exit_code=result.exit_code,      # 只有最后一条命令的
    stop_reason=result.stop_reason,  # 只有最后一条命令的
    ...
)
```

`safe_argv`/`argv_digests` 覆盖该 phase 的**全部计划命令**，而 `exit_code`/`stop_reason`/`duration_seconds` 只反映**最后执行的那一条**。第 2 条 download 失败时，`download.json` 里写的仍是三条 argv，读者无从判断是哪一条失败、前面两条各花了多久、各自 discovery 出了什么。

现有测试 `test_slice2_runner_nonzero_stops_at_every_exact_allowed_prefix`（tests diff:874-934）参数化了 `failure_index` 0/1/2 三个 download 下标，但断言只到 `result.stop_phase == "download"` 与 `len(factory.calls) == failure_index + 1`——**没有任何断言检查 receipt 能区分这三种情况**，因为 receipt 确实无法区分。测试与实现在同一个盲点上一致。

**为什么这是 High。** plan §5.2 逐字要求：

> `download.json` 在一个 phase receipt 内按执行顺序记录**三个完整 argv、分段 exit/duration/discovery 摘要与聚合 verdict**。

plan §5.4 同样要求 `download.json` "内含三个有序 command records"，`price-snapshot-import.json` "绑定 canonical JSON、Markdown、Fins material document_id 与 source fingerprint"，`process.json` "记录唯一 argv、filing/material summary、exit/duration 和返回的 document status"。当前 `PhaseReceipt` v2 的字段集（contracts:724-725 附近）里没有任何承载分段结果或 owner 返回值的位置——不是"没填"，是 schema 里根本没有这个概念。

连带后果：plan §8.1 的恢复语义依赖 "保留已执行的 command records"，当前 receipt 无法支撑这一恢复决策。H-1 的自引用也是这个缺口的直接产物。

**最小修复。** 在 contracts owner 中为 `PhaseReceipt` v2 增加分段记录（不是新建第二份 receipt schema）：

```python
@dataclass(frozen=True)
class CommandRecord:
    """phase 内单条命令的执行事实。"""
    safe_argv: tuple[str, ...]
    argv_digest: str
    status: str
    exit_code: int | None
    duration_seconds: float
    stop_reason: str | None
```

`PhaseReceipt.command_records: tuple[CommandRecord, ...]` 替代平铺的 `safe_argv`/`argv_digests`，`__post_init__` 校验 records 数量 ≤ 计划命令数、前缀成功、聚合 `status` 与末条一致。`_execute_phase` 在循环内逐条 append。这同时让 receipt 前缀校验（`_load_planned_receipt_prefix`:2610-2640）能验证"已执行前缀"而非"计划全量"。

---

## M-1 — fixture verify 的固定共享临时根可被预创建拒绝服务

**证据。** `utils/investment_agent_acceptance.py:2855-2861`：

```python
temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
workspace = temporary_parent / "dayu-investment-agent-aapl-fixture-verify"
lock = temporary_parent / "dayu-investment-agent-aapl-fixture-verify.lock"
try:
    lock.mkdir()
except FileExistsError as exc:
    raise ContractError("fixture verify 已有并发实例") from exc
```

`/tmp` 在 macOS/Linux 上是 world-writable（`drwxrwxrwt`）。任意本地用户 `mkdir /tmp/dayu-investment-agent-aapl-fixture-verify.lock` 后，本项目的 fixture verify **永久返回 exit 2**，且 `finally` 里的 `lock.rmdir()` 只在本进程成功取得锁后才会执行，所以受害者无法自愈。同理，预创建 `workspace` 目录会命中 :2863 的 "stale 状态" 分支。没有 owner/PID/mtime 检查来区分"别人的恶意占位"和"自己的并发实例"。

implementation artifact 第 46 行给出的理由是"为保持相同输入的 artifact SHA/receipt 字节稳定"——这个动机成立（owner materializer 会把 workspace 绝对路径写进产物），但**固定路径不必须落在共享 `/tmp`**。

**最小修复。** 把固定 canonical 根迁到仓库内已被 `.gitignore` 覆盖的私有目录（`.gitignore:3` 已含 `workspace`）：

```python
temporary_parent = (repository_root / "workspace/tmp").resolve(strict=True)
```

路径仍固定、字节仍稳定，但目录权限归本用户所有，消除跨用户占位面。锁语义与 fail-closed 策略保持不变。

---

## M-2 — wall clock 耗尽被分类为 failed 而非 timeout

**证据。** `utils/investment_agent_acceptance.py:2109-2117`：

```python
if remaining <= 0:
    result = CommandResult(
        status="failed",
        exit_code=None,
        stop_reason="whole_run_wall_clock_exhausted_before_start",
        termination_action=None,
        partial_by_timeout=False,
    )
    break
```

plan §7 要求 timeout 路径一律 "写 `status=timeout`、`termination_action`、elapsed/remaining 与 `partial_by_timeout=true` receipt"，§8.1 的恢复决策依赖 `partial_by_timeout` 区分"预算耗尽的部分产物"与"命令自身失败"。当前实现把预算耗尽伪装成普通失败，恢复方无法从 receipt 判断该 run 是否需要 Controller 重新批准预算。

契约侧存在张力：`_validate_timeout_phase_status`（contracts:3026-3043）要求 `timeout` receipt 必须带 `termination_action ∈ {terminate, kill, termination_unconfirmed}`，而"启动前就耗尽"没有进程可终止，所以实现被迫退回 `failed`。这是 schema 设计缺口，不是实现偷懒。

**最小修复。** 在 contracts 中允许一个明确的 no-process 终止态：

```python
_TERMINATION_ACTIONS = frozenset({"terminate", "kill", "termination_unconfirmed", "not_started"})
```

`_validate_timeout_phase_status` 接受 `not_started` 且要求此时 `exit_code is None`；`_execute_phase` 的耗尽分支改为 `status="timeout"`、`termination_action="not_started"`、`partial_by_timeout=True`。补一条测试：注入 monotonic 前进超过 `max_wall_seconds` 的时钟，断言 receipt 为 `timeout` + `not_started` + `partial_by_timeout=True`。

---

## M-3 — stderr 摘要与 SHA-256 未落盘

**证据。** `utils/investment_agent_acceptance.py:2816-2829`：

```python
def _stderr_stop_reason(stderr: str) -> str:
    return "command_failed_with_stderr" if stderr else "command_failed"
```

plan §7 结尾逐字要求：

> 日志与 phase receipt 必须通过现有 `dayu.redaction` secret shape 规则再输出；**stderr 只保存脱敏摘要和 SHA-256**，不在 baseline 中复制完整 provider error body。

当前只保留了"stderr 是否非空"这一个比特，脱敏摘要与 SHA-256 都没有。诊断上，`command_failed_with_stderr` 无法区分鉴权失败、额度耗尽与内容策略拒绝——而 plan §8.1 明确要求"不得自动重试鉴权、额度、内容策略或预算错误"，这个区分正是人工恢复决策的输入。

需要说明：当前实现在**安全方向上是过度保守而非不足**，泄漏风险为零。但它没有落实 plan 明确要求的证据保留，属于契约未闭合。

**最小修复。** 在 `CommandRecord`（见 H-2）中增加两个字段，复用既有静态脱敏：

```python
stderr_digest: str | None          # hashlib.sha256(stderr.encode()).hexdigest()
stderr_summary: str | None         # SECRET_KEY_PATTERN.sub(REDACTED_SECRET, stderr)[:_STDERR_SUMMARY_LIMIT]
```

`_STDERR_SUMMARY_LIMIT` 作为模块级常量（避免魔法数字）。摘要必须走既有 `SECRET_KEY_PATTERN`，**不得**改用会枚举宿主环境变量值的 `redact_secret_shapes`（见「已验证为正确的攻击面」第 5 条）。receipt 侧新增校验：`stderr_summary` 命中 secret shape 或绝对路径时 fail closed。

---

## M-4 — 价格 material 闭合未比对 plan 指纹

**证据。** `utils/investment_agent_acceptance.py:3015-3039`：

```python
candidates = tuple(
    item
    for item in inventory.documents
    if item.source_kind == "material"
    and item.form == "MATERIAL_OTHER"
    and item.report_date == price.market_date
    and item.ingest_complete
)
if len(candidates) != 1:
    raise ContractError("价格 MATERIAL_OTHER 文档必须按 report_date 唯一闭合")
return candidates[0].document_id
```

`AcceptancePlan` 携带 `price_material_sha256`（contracts 中已指纹化），但这里从未与候选文档的 primary SHA 比对。plan §5.2 要求 "JSON→Markdown→Fins material 指纹闭合"，§6.1 gate 8 同样把它列入 `source_price_closed`。当前只要 `report_date` 与 `form` 对上、`ingest_complete=true`，任意内容的 material 都会被接受为估值基准。

`_preflight_run` 阶段确实校验了 `inputs/price-snapshot.material.md` 的字节指纹（:2041-2073），但那证明的是"本地文件没被改"，不是"仓储里被 import 的那份就是它"。两者之间隔着一次 `upload_material` 子进程。

**最小修复。**

```python
if candidates[0].primary_sha256 != plan.price_material_sha256:
    raise ContractError("价格 material 与 plan 指纹不闭合")
```

字段名以 `SourceDocument` 上实际存在的 primary SHA 字段为准。补一条测试：篡改仓储中 material 的 primary SHA，断言 live verify fail closed。

---

## M-5 — dirty 判定过宽导致 plan 极易失效

**证据。** `utils/investment_agent_acceptance.py:966-967` 与 `:2026-2027`：

```python
status = subprocess.run(
    (self.git_executable, "status", "--porcelain", "--untracked-files=normal"), ...
).stdout
...
if state.git_sha != plan.git_sha or state.dirty != plan.dirty:
    raise ContractError("HEAD/dirty drift")
```

`--untracked-files=normal` 会列出未跟踪文件，`dirty=bool(status)`。因此在 `prepare` 与 `run` 之间**任何**未跟踪文件的出现都会使已 prepare 的 plan 永久失效——包括本审查产物 `docs/reviews/code-review-*.md`、编辑器临时文件，以及 operator 在 `workspace/` 外做的任何笔记。live run 是付费且不可自动恢复的，plan 失效意味着必须重跑整个 `prepare`。

需要明确：**严格是对的**，代码修改必须使 plan 失效。问题在于粒度——把"新增一个 markdown 笔记"和"改了 `dayu/fins/` 的实现"等同处理，是把脆弱性当成了严格性。而且 `PackageInputFingerprints` 已经独立覆盖了真正关键的 config/assets 闭包（`assert_package_input_fingerprints`，:2034），生产代码漂移有专门的更强真源。

**最小修复。** 收窄为已跟踪文件的修改：

```python
(self.git_executable, "status", "--porcelain", "--untracked-files=no")
```

未跟踪文件不影响已导入代码的行为，而 package 指纹闭包继续覆盖 config/assets。若需保留对未跟踪 `.py` 的敏感度，则应显式过滤扩展名，而不是整棵工作树一刀切。

---

## Low findings

**L-1 — `source-inventory.json` 从未写出。** plan §5.4 的固定 run root 清单包含 `source-inventory.json`，但全仓 grep 只在 `investment_agent_acceptance_evaluator.py:69` 命中 fixture 文件名 `source-inventory-v1.json`；`_evaluate_live_plan` 构建的 inventory 只进内存，从未落盘。要么在 verify 阶段原子写出，要么在 plan 中删除该条目——当前状态是文档与实现不一致。

**L-2 — `_WINDOW_FORMS` 死代码 + 字面量重复。** `:91` 定义 `_WINDOW_FORMS = (("10-K",), ("10-Q",), ("8-K", "DEF 14A"))`，全文件无第二处引用；`_evaluate_live_plan:2921-2925` 把同一组 form 字面量重新写了一遍。删除其一，让 window 构造成为单一真源。

**L-3 — fixture 路径的魔法数字。** `:2849-2854` 硬编码 `20 / 200_000 / Decimal("5") / "CNY"`，`:2874-2877` 硬编码 `max_wall_seconds=3_600 / actual_wall_seconds=120.0`，`:2887` 硬编码 `timedelta(hours=1)`。AGENTS.md「禁止魔法数字、魔法字符串」无 fixture 例外。提取为模块级具名常量（如 `_FIXTURE_APPROVED_BUDGET`、`_FIXTURE_EVALUATION_OFFSET`）。

**L-4 — 临时文件残留会毒化整次 verify。** `_atomic_write_bytes`（:2746-2813）在 `phase-receipts/` 内创建临时文件后 rename；若进程在两步之间被 SIGKILL，残留文件会让 `_validate_receipt_root`（:2578-2585）的 `path.name not in allowed_files` 判定整个 receipt 目录非法，已完成的合法 run 从此无法 verify。建议临时文件写在 run root 下的专用子目录，或在 allowlist 校验中显式识别并拒绝该固定前缀（给出可操作的错误信息，而非笼统的"未知 receipt"）。

**L-5 — 私有模块与具体实现类耦合。** `:25` 导入 `dayu.cli.commands._research_template_materialize.materialize_research_workspace`（下划线前缀私有模块），`:26-28` 直接导入三个具体 `FsSourceDocumentRepository` / `FsProcessedDocumentRepository` / `FsDocumentBlobRepository`。AGENTS.md 要求"模块间依赖最小化，优先接口或协议，避免上层直接依赖具体实现细节"，plan §4.2 也以仓储协议描述这一边界。当前构造点位于 `_evaluate_live_plan` 内部，无法注入替代实现——这也是 live 路径难以离线测试的原因之一。建议由调用方注入协议实例。注意：`utils/` 下脚本按 AGENTS.md 免测试/免覆盖率，此项优先级最低。

---

## 已验证为正确的攻击面（列出以说明这些点已被逐条证伪，不是未检查）

1. **terminal verify 无 self-reference — PASS。** `prepare_acceptance` 在 fingerprint 计算后才派生 terminal command，并有两条显式断言：`fingerprinted phase specs 不得自引用 plan fingerprint` 与 `terminal verify 未绑定计算后的 plan fingerprint`。`build_phase_specs` 产出的 12 条 spec 中不含 `verify`，测试 `test_slice2_prepare_builds_atomic_v2_plan_skeleton_and_terminal_after_fingerprint`（tests diff:584, 590-596）双向断言。

2. **structural allowlist / field-argv equality — PASS，且 `command[4]` IndexError 猜想被证伪。** 我最初怀疑 `_assert_structural_allowlist:3489` 的 `command[4]` 会在恶意 plan 上越界（`_MIN_COMMAND_TOKEN_COUNT = 4` 只保证下标 0-3）。实际执行序：:3484 先比对 `command[3]` 与固定 subcommand tuple，:3486-3488 对每条命令调用 `_validate_cli_command_shape`，其中 `command.count("--config") == 1 and command.count("--base") == 1`（:3511）保证任何通过的命令至少 8 个 token，:3489 才取 `command[4]`。恶意 plan 在到达越界点之前已被 `ContractError` 拒绝。`main` 只捕获 `(ContractError, OSError)` 是安全的。

3. **三 placeholder 完整性 — PASS。** `_is_safe_placeholder_token`（contracts:2904-2926）对 `<PYTHON>` 只允许精确相等，对 `<RUN_ROOT>` / `<PACKAGE_CONFIG>` 允许 `/` 子路径且显式拒绝 `..` 与反斜杠；`_looks_absolute_path` 覆盖 POSIX 绝对、`~` 前缀与 `^[A-Za-z]:[\\/]` 三形态。未覆盖 Windows UNC（`\\server\share`），但该形态无法通过 `_validate_command_matrix` 的 `_require_canonical_absolute_path`（:2869）进入 plan，因而不可达。测试 `test_slice2_safe_argv_uses_only_three_placeholders_and_digest_binds_raw_command`（tests diff:816-818）字节级断言编码后不含 run root / config root / python 路径。

4. **prepare atomic staging — PASS。** staging 落在 run root 同父目录（保证同文件系统 rename 原子性），`BaseException` 兜底只清理本次精确 staging，正式 run root 在失败路径上不出现。测试 `test_slice2_prepare_failure_cleans_exact_staging_without_publishing_run_root`（tests diff:620-654）双向断言正式目录与 staging glob 均不存在。

5. **secret redaction 不枚举 env 值 — PASS。** `:29` 只导入 `REDACTED_SECRET, SECRET_KEY_PATTERN`；`_redact_cli_text:1964` 仅 `SECRET_KEY_PATTERN.sub(...)`。`dayu/redaction.py` 中会枚举 `os.environ` 值的 `_known_environment_secret_values()` / `redact_secret_shapes()` / `RedactingArgumentParser` **均未被引用**，自定义 `_PresenceSafeArgumentParser`（:770）走的是静态 pattern。环境访问严格限于名称 membership（`OsEnvironmentPresenceProvider` 对计划外名称直接 `ContractError`，tests diff:1223-1224 断言）。

6. **timeout terminate→kill 协议 — PASS。** `_terminate_timed_out_process`（:2300-2356）实现 terminate → 10s grace → kill → 10s grace → `termination_unconfirmed`，四条路径全部 `partial_by_timeout=True` 且不 cleanup、不 resume。测试覆盖温和 terminate 成功与 terminate 后存活再 kill 两条，并断言后续调用数为 0、run root 保留（tests diff:938-976, 1016-1019）。注意此 PASS 仅针对**进程超时**路径；预算耗尽路径见 M-2。

7. **receipt prefix / digest / status binding — PASS。** `_assert_no_existing_run_receipts` 保证不覆盖；`_validate_receipt_root` 拒绝 symlink/非普通/未知文件；`_load_planned_receipt_prefix` 强制顺序、拒绝 skip/reorder、逐 phase 重算 `safe_argv`/`argv_digests` 并要求精确相等、校验时间与剩余预算单调；`_validate_terminal_receipt` 要求完整成功前缀。测试参数化 digest tamper / skip / unknown suffix 三类变异（tests diff:1079-1120）。

8. **verify fixture/live policy 与 protocol inventory — PASS。** parser 严格互斥 `--fixture` 与 `--plan + --fingerprint`，四种非法组合在读取任何产物前以 exit 2 退出（tests diff:713-738）。fixture lane 强制 `deterministic ∧ ¬external ∧ ¬live_freshness`，live lane 强制其反面。inventory 只经三个仓储协议构建，未扫描 `workspace/portfolio`。

9. **CLI 3660 行 / 188 行 builder 是否隐藏 God 职责 — 判定为可接受。** 用户提到的 "3343 行" 实际为 3660 行（`wc -l`）。文件长度的主因是 accepted plan 固定的 13 条 argv、严格边界与全量中文 `Args/Returns/Raises` docstring；职责已按 prepare / run / verify / 校验 helper 分层，未见跨职责的可变共享状态。`build_phase_specs` 188 行是全部 fixed argv 的唯一 canonical pure builder，拆分会制造顺序/flag 双真源——implementer artifact 第 80 行的论证成立。**但**如果 H-2 落地后 `_execute_phase` 继续膨胀，该函数将成为下一个审查重点。

10. **独立复跑的只读 gate。** `pytest tests/test_investment_agent_acceptance.py -q` → **86 passed**；`pyright` 对三个文件 → **0 errors, 0 warnings**。与 implementation artifact 的声明一致。未复跑 coverage 与 ruff（不影响本次判定）。

---

## 修复优先级

1. **H-2 先于 H-1。** `PhaseReceipt` 增加 `CommandRecord` 分段记录是 H-1、M-3 的共同前提，且属于 contracts owner 的 schema 变更——按 AGENTS.md「schema 变更」条款，应按全新 schema 起库处理，不做 v2 兼容读取。
2. **H-1** 改用 receipt-derived discovery，删除 `_latest_discovery_from_inventory`。若 Slice 2 无法取得外部真源，则 fail closed 并把该 gate 显式记为 Slice 3 owner——不允许恒真实现继续冒充已闭合。
3. **M-1** 迁移 fixture 固定根到 `workspace/tmp/`，一行改动，消除跨用户 DoS 面。
4. **M-2 / M-3 / M-4** 随 H-2 的 schema 变更一并落地。
5. **M-5 / L-1..L-5** 可在同一 Slice 内清理，不阻塞。

每项修复都必须补齐对应测试并复跑 pyright；`utils/` 按 AGENTS.md 免覆盖率要求，但既有 86 条测试已覆盖这些路径，不应回退。

## 审查边界声明

- 全文读取：根 `AGENTS.md`（110 行）、accepted plan（716 行）、implementation artifact（92 行）、contracts diff（846 行）、`investment_agent_acceptance.py`（3660 行）、tests diff（1326 行）。
- 未修改任何生产或测试文件。
- 未执行 live、SEC、DeepSeek、MiMo、网络或任何付费调用。
- 未启动子 agent。
- 只读验证：`pytest -q`、`pyright`、`grep`、`git diff`。
- 临时文件 `workspace/tmp/contracts.diff`、`workspace/tmp/tests.diff` 为本次 diff 读取所建，位于 `.gitignore` 覆盖范围内，可安全删除。
