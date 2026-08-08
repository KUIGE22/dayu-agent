# CLI Write 架构重构 Master Plan（v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS）

- **日期**: 2026-08-07
- **分支**: `codex/dual-model-research-mvp`
- **HEAD**: `4c5bb1b`
- **审查来源**: v1～v4 多轮 review、`docs/reviews/plan-c5-source-audit-20260807-deepseek.md`（v4.1 源码审计）、`docs/reviews/plan-c5-v4.1-review-20260807-mimo.md`（v4.1 FAIL）、`docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md`（v4.2 fix）、`docs/reviews/plan-c5-v4.2-rereview-20260807-mimo.md`（v4.2 re-review）、`docs/reviews/plan-c5-v4.3-fix-20260807-deepseek.md`（v4.3 fix）、`docs/reviews/plan-c5-v4.3-rereview-20260807-mimo.md`（v4.3 re-review, PASS）、`docs/reviews/plan-c5-v4.3-final-adjudication-20260807-deepseek.md`（final adjudication）、`docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md`（v4.4 type erratum DeepSeek adjudication）、`docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md`（v4.4 type erratum MiMo adjudication）、`docs/reviews/plan-c5-v4.4-type-erratum-20260807-deepseek.md`（v4.4 type erratum DeepSeek plan fix）、`docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md`（v4.4 type erratum MiMo re-review, PASS）、`docs/reviews/plan-review-20260808-002853.md`（Slice 4 W16 DeepSeek type-contract review）、`docs/reviews/plan-review-20260808-002854.md`（Slice 4 W16 MiMo type-contract review）、`docs/reviews/plan-review-20260808-005559.md`（Slice 4 W16 DeepSeek final re-review, PASS）、`docs/reviews/plan-review-20260808-005600.md`（Slice 4 W16 MiMo final re-review, PASS with measurement-error LOW）、`docs/reviews/plan-review-20260808-010404.md`（Slice 4 W16 MiMo corrective re-review, PASS, measurement error CLOSED）、`docs/reviews/plan-review-20260808-013315.md`（Slice 5 dependency gap DeepSeek review）、`docs/reviews/plan-review-20260808-013316.md`（Slice 5 dependency gap MiMo review）、`docs/reviews/plan-review-20260808-015208.md`（Slice 5 v4.6 DeepSeek re-review, PASS）、`docs/reviews/plan-review-20260808-015209.md`（Slice 5 v4.6 MiMo re-review, PASS）、`docs/reviews/plan-review-20260808-020628.md`（Slice 5 v4.6 DeepSeek final re-review, PASS）、`docs/reviews/plan-review-20260808-020629.md`（Slice 5 v4.6 MiMo final re-review, PASS）、`docs/reviews/plan-review-20260808-023020.md`（Slice 5 v4.7 DeepSeek focused dependency/lint review）、`docs/reviews/plan-review-20260808-023021.md`（Slice 5 v4.7 MiMo focused dependency/lint review）、`docs/reviews/plan-review-20260808-024405.md`（Slice 5 v4.7 DeepSeek re-review, PASS, open H/M/L = 0）、`docs/reviews/plan-review-20260808-024406.md`（Slice 5 v4.7 MiMo re-review, PASS with 3 Low observations）、`docs/reviews/plan-review-20260808-025255.md`（Slice 5 v4.7 MiMo corrective re-review, PASS, 3 Low CLOSED）、`docs/reviews/plan-review-20260808-035654.md`（Slice 6/10 type-ownership DeepSeek review, PASS_WITH_ERRATA）、`docs/reviews/plan-review-20260808-035655.md`（Slice 6/10 type-ownership MiMo review, FAIL）、`docs/reviews/plan-review-20260808-041140.md`（v4.8 DeepSeek re-review, core PASS with 3 Low observations）、`docs/reviews/plan-review-20260808-041141.md`（v4.8 MiMo re-review, PASS, open H/M/L=0）、`docs/reviews/plan-review-20260808-042044.md`（v4.8 DeepSeek final corrective re-review, PASS, open H/M/L=0）、`docs/reviews/plan-review-20260808-042045.md`（v4.8 MiMo final re-review, PASS, open H/M/L=0）、`docs/reviews/plan-review-20260808-042837.md`（Slice 6 W12 cycle DeepSeek review, PASS_WITH_ERRATA）、`docs/reviews/plan-review-20260808-042838.md`（Slice 6 W12 cycle MiMo review, PASS with Medium finding）、`docs/reviews/plan-review-20260808-044555.md`（v4.9 DeepSeek final re-review, PASS, open H/M/L=0）、`docs/reviews/plan-review-20260808-044556.md`（v4.9 MiMo final re-review, PASS, open H/M/L=0）、`docs/reviews/plan-review-20260808-061001-deepseek.md`（Slice 7 runner ownership DeepSeek review, FAIL）、`docs/reviews/plan-review-20260808-061002-mimo.md`（Slice 7 runner ownership MiMo review, PASS with Medium/Low findings）、`docs/reviews/plan-review-20260808-061003-deepseek.md`（v5.0 DeepSeek re-review, PASS, open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-061004-mimo.md`（v5.0 MiMo re-review, core PASS with one Low observation）
- **v5.0 最终复审来源**: `docs/reviews/plan-review-20260808-061005-deepseek.md`（final corrective re-review, PASS, open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-061006-mimo.md`（final corrective re-review, PASS, open High/Medium/Low=0/0/0）
- **v5.1 Slice 9 审查来源**: `docs/reviews/plan-review-20260808-075500-deepseek.md`（Slice 9 ownership/DAG review, FAIL）、`docs/reviews/plan-review-20260808-075501-mimo.md`（Slice 9 focused review, PASS with plan fixes；其 preliminary allocation/算术不闭合，未采纳）
- **v5.1 Slice 9 re-review 来源**: `docs/reviews/plan-review-20260808-082000-deepseek.md`（PASS，初审 9 项全 CLOSED，open High/Medium/Low=0/0/2）、`docs/reviews/plan-review-20260808-082001-mimo.md`（PASS，初审 findings 全 CLOSED，open High/Medium/Low=0/0/0）
- **v5.1 Slice 9 final corrective re-review 来源**: `docs/reviews/plan-review-20260808-083500-deepseek.md`（PASS，082000 L-01/L-02 CLOSED，open High/Medium/Low=0/0/0）；与 MiMo 082001 PASS/open0 共同构成 final dual plan re-review
- **v5.2 Slice 10 focused review 来源**: `docs/reviews/plan-review-20260808-095100-deepseek.md`（FAIL，S10-R1..R6）、`docs/reviews/plan-review-20260808-095101-mimo.md`（FAIL，H01/H02/M01/M02/L01..L03）
- **v5.2 Slice 10 final re-review 来源**: `docs/reviews/plan-review-20260808-101000-deepseek.md`（PASS，095100 S10-R1..R6 全部 CLOSED，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-101001-mimo.md`（PASS，095101 H01/H02/M01/M02/L01..L03 全部 CLOSED，open High/Medium/Low=0/0/0）
- **v5.3 Slice 10/11 Protocol conformance review 来源**: `docs/reviews/plan-review-20260808-103000-deepseek.md`（FAIL，S10-TYPE-01/S11-TYPE-01/V53-MECH-01/V53-COUPLING-01/V53-EXT-01）、`docs/reviews/plan-review-20260808-103001-mimo.md`（FAIL，H01；其 Protocol 多继承方案被 Controller 拒绝）
- **v5.3 Slice 10/11 final plan re-review 来源**: `docs/reviews/plan-review-20260808-104500-deepseek.md`（PASS，5/5 初审 findings CLOSED，22/23 计数误差已纠正，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-104501-mimo.md`（PASS，H01 CLOSED，撤回 Protocol 多继承建议，open High/Medium/Low=0/0/0）
- **v5.4 Slice 10 propagation-boundary review 来源**: `docs/reviews/plan-review-20260808-111500-deepseek.md`（FAIL，S10-CALLGRAPH-01/LAYER-01/COUNT-01）、`docs/reviews/plan-review-20260808-111501-mimo.md`（方案 B 推荐，call-graph closure 与 42 计数确认）
- **v5.4 Slice 10 final plan re-review 来源**: `docs/reviews/plan-review-20260808-113000-deepseek.md`（PASS，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-113001-mimo.md`（PASS，open High/Medium/Low=0/0/0）
- **v5.5 Slice 11 Phase E/F/H focused review 来源**: `docs/reviews/plan-review-20260808-122456.md`（DeepSeek，FAIL，1 High + 1 Medium + 1 Low）、`docs/reviews/plan-review-20260808-122457.md`（MiMo，FAIL，1 High + 2 Medium，另有 2 Low observations）
- **v5.5 Slice 11 final plan re-review 来源**: `docs/reviews/plan-review-20260808-124536.md`（DeepSeek，PASS，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-124537.md`（MiMo，PASS，open High/Medium/Low=0/0/0）
- **v5.6 aggregate gate focused review 来源**: `docs/reviews/plan-review-20260808-150148.md`（DeepSeek，AGG-01..05）、`docs/reviews/plan-review-20260808-150149.md`（MiMo，FAIL，H01/M01/L01）
- **v5.6 aggregate gate final plan re-review 来源**: `docs/reviews/plan-review-20260808-152220.md`（DeepSeek，PASS，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-152221.md`（MiMo，核心 PASS，但 M-01/L-01 为 non-defect/measurement observations）、`docs/reviews/plan-review-20260808-153009.md`（MiMo corrective，PASS，open High/Medium/Low=0/0/0）
- **v5.7 Ruff ratchet baseline review 来源**: `docs/reviews/plan-review-20260808-154611.md`（DeepSeek，baseline/gate blocker review）、`docs/reviews/plan-review-20260808-154612.md`（MiMo，CI/configured-rule-set 独立审查）
- **v5.7 Ruff ratchet re-review 来源**: `docs/reviews/plan-review-20260808-160555.md`（DeepSeek，PASS，open 2 Low）、`docs/reviews/plan-review-20260808-160556.md`（MiMo，PASS，open 3 Low；V57-03/V57-09 为同一版本理由 observation）
- **v5.7 Ruff ratchet final corrective re-review 来源**: `docs/reviews/plan-review-20260808-161501.md`（DeepSeek，PASS，open High/Medium/Low=0/0/0）、`docs/reviews/plan-review-20260808-161502.md`（MiMo，PASS，open High/Medium/Low=0/0/0）
- **v5.8 Aggregate Fix RT-01 来源**: `docs/reviews/aggregate-cli-write-architecture-validation-20260808-codex.md`（aggregate validation，READY FOR AGGREGATE DEEPREVIEW）、`docs/reviews/code-review-20260808-aggregate-deepseek.md`（DeepSeek aggregate deepreview）、`docs/reviews/code-review-20260808-aggregate-mimo.md`（MiMo aggregate deepreview）、`docs/reviews/aggregate-code-review-adjudication-20260808-codex.md`（Controller finding adjudication）、`docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`（本次 plan-fix 记录）
- **v5.8 Aggregate Fix RT-01 plan review 来源**: `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-deepseek.md`（DeepSeek，PASS，open High/Medium/Low=`0/0/1`，L-PLAN-01）、`docs/reviews/plan-review-20260808-v5.8-aggregate-rt-mimo.md`（MiMo，PASS，open High/Medium/Low=`0/0/0`）
- **v5.8 Aggregate Fix RT-01 final plan re-review 来源**: `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-deepseek.md`（DeepSeek final corrective，PASS，L-PLAN-01 CLOSED，open High/Medium/Low=`0/0/0`）、`docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-mimo.md`（MiMo final，PASS，open High/Medium/Low=`0/0/0`）
- **v3.9→v4.0 变更**: V4-01: research_template action 34→39（全文一致）；V4-02: 审计命令上界 4817→4822，注明 HEAD 证据，实现后审计改用结构测试；C4-01 (controller HIGH): S0 仅测试 HEAD if-chain，不引用未来 adapter/mapping；S10 引入 mapping 时迁移 39-key 矩阵；S11 引入 adapter 时迁移 16-action 矩阵，各 slice 独立绿且 patch 目标当时存在；V4-03/V4-05: S0 覆盖清单与 patch 目标；V4-04: Slice 6 预估 diff 250–350 行及不可再拆理由；V4-06: §4.3 传播链补充 print_write_report；V4-07: REJECTED — 忠实现状，不新增 optional-path 重构
- **v4.0→v4.1 变更**（基于 AgentDS 逐函数源码审计）: SA-01: format_utc 拆为 microseconds/seconds 两族，auto 族 6 文件 defer；SA-02: is_relative_to 8 个实现全部为 `try: path.relative_to(root)` 非 resolve 模式，统一为 `is_subpath`，删除无 caller 的 resolve 版；SA-03: absolute_path spec 修正——校验 is_absolute() 非 is_dir()，依赖两族 _required_text 在调用方处理；SA-04: snapshot_fingerprint 5 个实现全含业务 validator，defer；SA-05: transaction_id 从 Group A 移至 Group C（不可安全抽取）；SA-06: decode_base64 全部现有实现为标准 b64decode(validate=True)，删除无 caller 的 urlsafe 模式；SA-07: persist_immutable 13 个实现分属 5 family，defer；SA-08: require_text 16 定义 8 族，仅族 1 有迁移证据；SA-09: require_exact_fields 8 exact family，全部 defer；SA-10: serialize challenger_promotion 缺 sort_keys 行为保持优先；SA-11: 所有 shared 函数必须有实际 Slice 2 eligible caller；SA-12: 全文自洽更新
- **v4.1→v4.2 变更**（基于 MiMo plan review + Controller rulings。详见 `docs/reviews/plan-c5-v4.2-fix-20260807-deepseek.md`）: C5-CTRL-01..09 + SA-REVIEW-01/04/06/07/08，18 项 follow-up 修正
- **v4.2→v4.3 变更**（基于 MiMo v4.2 re-review + Controller adjudication。详见 `docs/reviews/plan-c5-v4.3-fix-20260807-deepseek.md`）: C5-CTRL-10: require_mapping 保留 identity-return（非 dict(value)）；copy 族 2 文件（`incident_dossier_revalidation`、`gate_revalidation`）的 `_mapping` 使用 call-site adapter `dict(require_mapping(...))`；`gate_revalidation` 的 canonical/fingerprint 使用 `canonical_json_str(dict(value))` / `fingerprint_str(dict(value))`；`incident_dossier_revalidation` 的 fingerprint 使用 `fingerprint_str(dict(value))`；Slice 1 差分 corpus 新增 dict 子类 identity/copy 测试。RR-F01/RR-F02 REJECTED（evidence invalid——verification.py 已在 2B 表中，preflight fingerprint_str 已计入 12）
- **v4.3→v4.4 变更**（基于 Slice 2A type adjudication + Controller ruling + MiMo re-review。详见 `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md`（DeepSeek adjudication）、`docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md`（MiMo adjudication）、`docs/reviews/plan-c5-v4.4-type-erratum-20260807-deepseek.md`（DeepSeek plan fix）、`docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md`（MiMo re-review, 9/9 PASS, 零 findings））: C5-CTRL-10-ERRATUM: `require_mapping` 输入类型从 `ModelConfigJsonValue` 扩宽为 `ModelConfigJsonValue | JsonObject`。触发：5 个 public validator（`rollback.py`）`Mapping[str, Any]` payload 无法赋值给 `ModelConfigJsonValue`；经 `JsonObject`（`Mapping[str, ModelConfigJsonValue]`）协变分支通过。实现/返回/identity/17 helper count/2B copy adapter 均不变。Slice 1 commit 不重写——shared 实现在 Slice 1 已就位，类型调整（签名中 `| JsonObject`）随 Slice 2A commit 修改。Slice 1 差分 corpus 新增非-dict Mapping identity 测试（`MappingProxyType`，零 `Any`）；类型验证：直接 `pyright dayu/services/` — 5 个 public validator（`:840` `:1225` `:1316` `:1498` `:1831`）的 `Mapping[str, Any]` payload 经 `JsonObject` 协变分支通过，零 errors。方案 A ACCEPTED；方案 B（overload）/C（改 public 签名）/D（inline guard）/E（其他）REJECTED
- **v4.4→v4.5 变更**（基于 `docs/reviews/plan-review-20260808-002853.md` DeepSeek 与 `docs/reviews/plan-review-20260808-002854.md` MiMo 双路 type-contract review）: **W16-CTRL-01** — Slice 4 原计划新增的 `_append_research_workbook_section(sections: list[dict[str, object]], ...)` 违反 AGENTS 禁止新增 `object` 签名的硬约束。Controller 采纳 MiMo 更精确的三 TypedDict 方案：`_ResearchWorkbookEvidence`、`_ResearchWorkbookItem`、`_ResearchWorkbookSection`，helper 输入改为 `list[_ResearchWorkbookSection]`；public `build_research_workbook_payload(...) -> dict[str, object]` 为存量契约，保持不变；本模块 15 个存量函数签名共含 19 处 `dict[str, object]`（含 public builder 与 2 个私有 helper），均不在 W16 scope。W16 以 `pytest -k "research_workbook"` 与 `pyright` 验证；其余 slice 零语义变化
- **v4.5→v4.6 变更**（基于 `docs/reviews/plan-review-20260808-013315.md` DeepSeek 与 `docs/reviews/plan-review-20260808-013316.md` MiMo 双路 dependency review）: **S5-CTRL-01** — `_challenger_requested` 提前迁入 `_write_params_validation.py`，与三个 validator 组成 exact 4-function module；Slice 8 原源码连续 Challenger 组由 14 减为 exact 13，禁止 Slice 5 params 反向 import `write.py` 或尚不存在的未来模块。**S5-CTRL-02** — `_write_config_helpers.py` 从 `dependency_setup` 功能性 import `setup_model_name`，`write.py` 删除该 import，tests 中 13 处 monkeypatch 目标迁至 `_write_config_helpers.setup_model_name`，禁止 compatibility re-export/wrapper；v4.6 当时要求两个新模块的全部迁移函数均由 `write.py` 顶层 import，v4.7 的 S5-CTRL-04 基于真实 caller 证据收窄该绑定集合。**S5-CTRL-03** — `MODULE = "APP.WRITE"` 单一定义迁至 `_write_config_helpers.py`，`write.py` 及 Slice 6/7/8 目标模块按真实日志依赖正常 import；零复制、零反向 import。除 MODULE import 说明外，其他 slice 零语义变化
- **v4.6→v4.7 变更**（基于 `docs/reviews/plan-review-20260808-023020.md` DeepSeek 与 `docs/reviews/plan-review-20260808-023021.md` MiMo 双路 focused dependency/lint review）: **S5-CTRL-04** — 两个新模块继续各 exact 4 个函数、合计 exact 8 个定义；`write.py` 仅正常顶层 import/rebind 6 个真正功能 private symbol（config 4 个 + `_challenger_requested` + `_validate_research_materialization_args`），另行正常 import `MODULE`，但 MODULE 不计入 private function 数。删除并禁止 `_validate_challenger_run_plan_args`、`_validate_live_smoke_plan_args` 的 `write.py` compatibility re-export；engine test 的 live-smoke validator direct import 迁到 `_write_params_validation`，`_validate_challenger_run_plan_args` 没有旧 direct test，仅保留新 owner 模块定义。dispatch identity 仅锁定 6 个 functional binding。`setup_model_name` exact 13 patch、MODULE 单一真源、`_challenger_requested` 双 owner、engine line 5934、Slice 8 exact 13 与 coverage/pyright/Ruff 门禁均不变
- **v4.7→v4.8 变更**（基于 `docs/reviews/plan-review-20260808-035654.md` DeepSeek 与 `docs/reviews/plan-review-20260808-035655.md` MiMo 双路 type-ownership review）: **S6-CTRL-01** — Slice 0 与 Slice 6 忠实使用当时已存在的 `argparse.Namespace`；Slice 6 两个 config application 函数和两个 snapshot-builder 函数的 `args` 均精确为 `argparse.Namespace`，`ExecutionOptions` 与 `Mapping[str, ModelConfigJsonValue]` 不变。**S10-CTRL-01** — Slice 10 原子新建 `dayu/cli/arguments.py`，定义有运行时类型身份的 `DayuCliArguments(argparse.Namespace)` 与 `ResearchTemplateDispatchArguments`；`parse_arguments()` 通过 `parser.parse_args(namespace=DayuCliArguments())` 返回真实子类实例，禁止 alias/cast/glue。**S10-CTRL-02** — Slice 10 同 commit 机械传播 `DayuCliArguments` 到 `parse_arguments`、`run_research_template_command`、39 runners、`run_write_command` 与 Slice 6 四个函数；Slice 11 只追加 `WriteDispatchArguments` 和 context/adapter，不重复创建 `DayuCliArguments`。Callable 参数逆变意味着接受较宽 `argparse.Namespace` 的 runner 理论上可用于 `Callable[[DayuCliArguments], int]`；本计划仍为终态签名一致性选择机械收窄，不以错误的协变/逆变论断作为必要性依据。方案 B（Slice 6 提前创建 partial arguments module）与方案 C（alias/cast/forward-ref/glue）均 REJECTED。其余 slice 零语义变化
- **v4.8→v4.9 变更**（基于 `docs/reviews/plan-review-20260808-042837.md` DeepSeek 与 `docs/reviews/plan-review-20260808-042838.md` MiMo 双路 W12 cycle review）: **S6-W12-CYCLE-01** — 闭包 #1 随 `_run_write_model_configuration_application` 迁入 `_write_config_application.py` 后，必须在同模块以 `functools.partial(_build_fresh_application_routing_snapshot, args=args, paths_config=paths_config, execution_options=execution_options)` 构造 callback；为精确保留旧默认值语义，不显式绑定 `run_label`，且禁止 application 模块 import `_write_snapshot_builder`。闭包 #2–#5 在 Slice 6 的 `write.py` 中分别通过 `build_snapshot_builder` 绑定默认、默认、`configuration-manual-recovery-verification`、`configuration-manual-recovery-clearance`，后续 Slice 7/8 随各 runner 一并迁移 factory import/call。`_write_snapshot_builder.py → _write_config_application.py` 保持唯一依赖方向；方案 B（反转 ownership）与方案 C（DI/lazy import/compatibility glue）均 REJECTED。新增 import DAG、partial 数量、AST 零 nested helper、真实 callback、pyright/Ruff 与逐文件 coverage 门禁；其余 slice 零语义变化
- **v4.9→v5.0 变更**（基于 `docs/reviews/plan-review-20260808-061001-deepseek.md` 与 `docs/reviews/plan-review-20260808-061002-mimo.md`）: **S7-CTRL-01** — clean HEAD `b55f794` 的 `write.py` 精确含 14 个 `_run_write_model_configuration_manual_recovery_*` runner 与 1 个 Phase C `_check_write_model_configuration_manual_recovery_gate`；Slice 7 `_write_manual_recovery.py` ownership 改为 exact 15 个逐名函数，`_write_execution.py` 保持 exact 2，`write.py` 删除旧 17 definitions 并正常顶层 import 新 owner 的 exact 17 functional symbols。**S7-CTRL-02** — application / verification / clearance 三 runner 连同 `build_snapshot_builder` factory import/call 迁移，label 保持默认 / verification / clearance；CLI 内部依赖维持 `_write_manual_recovery.py → _write_snapshot_builder.py → _write_config_application.py` 单向，禁止 reverse import、cycle、nested helper、lazy import、compatibility/glue seam。**S7-CTRL-03** — direct runner tests 与其依赖 patch 迁至真实定义模块；验证 `run_write_command` / dispatch global lookup 的 characterization 继续 patch `write.<symbol>` 正常功能 binding，不能把正常 import 误判为 compatibility re-export。新增 exact definitions/import/identity、三处 factory、逐文件 coverage、pyright、Ruff delta 与 README decision 门禁。Phase A 14 条目、后续 adapter/Protocol、Slice 8 exact 13 等其他 slice 语义不变
- **v5.0 re-review observation**（基于 `docs/reviews/plan-review-20260808-061003-deepseek.md` 与 `docs/reviews/plan-review-20260808-061004-mimo.md`）: **S7-CTRL-04** — DeepSeek 全文 re-review PASS/open 0；Controller 接受 MiMo 新 Low，将 §1.3 的 HEAD `5821014` 行号与 awk 明确降为历史取证，当前 HEAD `b55f794` 验收改用 `run_write_command` 函数、首尾 predicate/call 锚点与 AST 结构命令，禁止在当前 worktree 执行旧行号 awk 并将空输出误判为 PASS。Phase A/adapter/Protocol/Slice 8 语义不变
- **v5.0 最终接受**: DeepSeek 061005 与 MiMo 061006 均 PASS，open High/Medium/Low=0/0/0；初审 runner-count/range/inventory findings 与 061004 新 Low 全部 CLOSED。Controller 接受 S7-CTRL-01..04，Slice 7 已达 code-generation-ready 且可实施
- **v5.0→v5.1 变更**（基于 `docs/reviews/plan-review-20260808-075500-deepseek.md` 与 `docs/reviews/plan-review-20260808-075501-mimo.md` 的事实 findings，以及 Controller 在 clean HEAD `1d0f9e6` 上的本地 AST 逐边复核）: **S9-CTRL-01** — Slice 9 从不闭合的 72-function 草案修正为迁移 exact 83 个非 runner/entry 函数：helpers/core/bundle/monitoring/materialize 分别 exact 22/26/12/11/12；`research_template.py` 终态只定义 entry 1 + runners 39，FunctionDef exact 40、ClassDef 0。两个 dataclass 与 7 个域常量迁入 helpers；存量 `_DATA_SOURCE_BINDING_CANDIDATES` 的 `object` 语义 occurrence 1→1，不新增签名或逃逸。**S9-CTRL-02** — 逐名锁定全部 83 函数、2 dataclass、7 constants，并以逐边 AST 结果锁定 DAG：main→all5；core→helpers；bundle→core+helpers；monitoring→bundle+core+helpers；materialize→monitoring+bundle+core+helpers；helpers 零内部 project-domain dependency。**S9-CTRL-03** — 主模块只正常 import retained entry/runner 真实调用的 exact 45 function bindings（helpers/core/bundle/monitoring/materialize = 6/18/6/9/6），其他 38 个迁移函数禁止 compatibility binding；`__all__` 从 68 删除 exact 13、保留 exact 55 functional/workbook/entry 项；direct-definition tests/imports/dependency patches 跟随真实 owner，只有 entry/runner global lookup characterization 保留 main owner，并新增 exact45 identity 回归。**S9-CTRL-04** — `write.py` 当前 line 81 的 materialize lazy import 迁至 `_research_template_materialize`；Slice 10 的 39 runner + entry 签名传播不变，但两个 dataclass 已在 helpers，不得重复迁移。五个 owner、主模块与 `write.py` 同一原子 Slice 自洽，新增 AST/identity/DAG/import-smoke/pyright/Ruff/逐文件 coverage/README/diff-check 门禁。两路 preliminary ownership/count 建议均因未闭合而拒绝，只采纳其事实 findings；v5.0 accepted 历史保持不变
- **v5.1 re-review observations 裁决**: DeepSeek 082000 与 MiMo 082001 均确认 v5.0 初审 findings 全部 CLOSED、核心计划 PASS。DeepSeek L-01 **REJECTED-WITH-REASON / CLOSED**：其“Slice 8 尚未实施”是事实错误，HEAD `1d0f9e6` 已是 Slice 8 accepted 后基线；line 81 为当前实测，且 §9e 同时以 `_materialize_research_after_write` 内 function-local import 语义锚点及旧/new exact 路径门禁锁定，不依赖盲目行号。DeepSeek L-02 **REJECTED-WITH-REASON / CLOSED**：review 自身承认不是 bug；§9d/§9e 已锁定 private owner `__all__` exact0、main 68 删除13→55、direct-owner/known consumer 迁移、compat0、import smoke 及 lazy 路径门禁；无本仓库证据的未知 star consumer 不构成 defect，为私有模块新增 `__all__` 反而扩大 surface。MiMo PASS/open0 **ACCEPTED**。Controller open High/Medium/Low=0/0/0，无语义 plan fix；DeepSeek corrective 083500 已复核两项裁决并确认 PASS/open0
- **v5.1 最终接受**: DeepSeek corrective 083500 与 MiMo 082001 均 PASS，open High/Medium/Low=0/0/0；初审 13 项（DeepSeek 9 + MiMo 4）与 DeepSeek 082000 新增 2 项 Low 全部 CLOSED。Controller 接受 S9-CTRL-01..04，Slice 9 达到 code-generation-ready 且可实施
- **v5.1→v5.2 变更**（基于 DeepSeek 095100、MiMo 095101 与 Controller 在 clean HEAD `8eface5` 的入口行为复核）: **S10-CTRL-03** — Slice 10 mapping 重构必须保留 `run_research_template_command` 的 HEAD dispatch/error 不变量：`setup_loglevel(args)` 顺序不变；selector 后在同一 `try` 内查 mapping；未知 action 静默返回 `1`；runner 的 `FileNotFoundError`、`FileExistsError`、`ValueError` 以精确 stderr `research-template error: {exc}` 转换为 `1`；禁止 `Log`、`MODULE`、新增输出或 `return 2`。**S10-CTRL-04** — selector 精确为 `str(getattr(args, "research_template_action", "") or "").strip().lower()`；该有界 `getattr` 只为保留 HEAD 对缺字段、`None` 与非字符串值的 defensive 语义，`ResearchTemplateDispatchArguments` 仍是静态类型边界。selector 是 Slice 10 deliverable 但不计入 45 个 `DayuCliArguments` args 签名传播；runner 内部表外存量 `getattr` 不在本 Slice 迁移范围。direct fixture owner、39-key mapping 矩阵与异常/未知 action 行为回归列为显式门禁。其余 slice 零语义变化
- **v5.2 最终接受**: DeepSeek 101000 与 MiMo 101001 均 PASS，open High/Medium/Low=0/0/0；DeepSeek 6/6、MiMo 7/7，合计 13 项初审 observations 全部 CLOSED。Controller 接受 S10-CTRL-03/04，Slice 10 达到 code-generation-ready 且可实施
- **v5.2→v5.3 变更**（基于 DeepSeek 103000、MiMo 103001 与 Controller 的 isolated pyright/runtime 证据）: **S10-CTRL-05** — Slice 10 在 `arguments.py` 中先定义 consumer 最小契约 `ResearchTemplateDispatchArguments(Protocol)`，再定义 producer `DayuCliArguments(argparse.Namespace)` 并显式声明 `research_template_action: str`；两者通过 structural subtyping 对接，Dayu 不继承 Protocol。**S11-CTRL-01** — Slice 11 新增 exact 20 字段的 `WriteDispatchArguments(Protocol)`（11+2+3 个 bool、3+1 个 optional path），并在既有 Dayu 类原子追加同名同类型 20 字段；Dayu 终态 exact 21 个 `AnnAssign`（research 1 + write 20）。Protocol 字段并集必须与 Dayu 字段集合精确相等，零 extra。禁止字段默认值、`__init__`、Protocol inheritance、cast、ignore、adapter 或 glue；表外 argparse 字段继续保持动态/存量 `getattr`，不把 Dayu 扩成 god bag。DeepSeek review 的 write 22/终态23 是计数误差，按计划逐字段实数修正为 20/21。S10-CTRL-03/04、45 args + 1 return、mapping/entry 行为与其他 slice 语义均不变
- **v5.3 最终接受**: DeepSeek 104500 与 MiMo 104501 均 PASS，open High/Medium/Low=0/0/0；DeepSeek 5/5 findings 与 MiMo H01 全部 CLOSED，MiMo 已撤回 Protocol 多继承建议，DeepSeek 22/23 measurement error 已纠正为 20/21。两路均确认 S10-CTRL-05/S11-CTRL-01，Slice 10 可恢复实施
- **v5.3→v5.4 变更**（基于 DeepSeek 111500、MiMo 111501 与 Controller 的真实 call-graph/pyright 复核）: **S10-CTRL-06** — 采纳方案 B：`_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` 是不读取 Dayu 专有字段的下层基础设施，终态保持 `argparse.Namespace`；仅 `_run_write_model_configuration_application` 作为 config application CLI runner 传播到 `DayuCliArguments`。Slice 10 传播计数由 v5.3 历史 exact45 修正为当前 exact42 args + 1 parse return（research entry+39 runners=40、write entry=1、config application runner=1）；rollback runner 与 exact15 manual recovery functions 全部保持 Namespace。`DayuCliArguments` IS-A `argparse.Namespace`，因此窄入口向宽 helper 传参类型安全；拒绝方案 A exact49 的偶然 call-chain 具体类型扩散与方案 C 的全 runner 扩 scope。S10-CTRL-05/S11-CTRL-01、S10-CTRL-03/04、mapping/entry 行为及其他 slice 语义不变
- **v5.4 最终接受**: DeepSeek 113000 与 MiMo 113001 均 PASS，open High/Medium/Low=0/0/0；初审 S10-CALLGRAPH-01/LAYER-01/COUNT-01 与 MiMo `config_application` 分组措辞纠正全部 CLOSED。DeepSeek 记录的两个实施期 Low residual（snapshot-builder Dayu import 清理、同模块宽/窄函数分层 docstring）均由既有 AST/docstring/pyright 门禁覆盖，不构成 plan defect。Controller 接受 S10-CTRL-06，Slice 10 可恢复实施
- **v5.4→v5.5 变更**（基于 DeepSeek 122456、MiMo 122457 与 Controller 对 clean HEAD `8c63d80` 的逐语句复核）: **S11-CTRL-02** — Slice 11 只把 Phase A 14 条目与 Phase B 2 条目替换为 accepted Protocol/context/adapter/phase-table dispatch，禁止新建不存在的 Phase E helper。Phase E 必须保留 HEAD 的 inline `required = any(...)`、真实 `_build_challenger_run_plan_from_args`、output-boundary assert、5 类异常映射与 `return 2`；Phase F 保留 fail-loud `assert challenger_run_plan is not None`，仅把已进入 Write Protocol 的 approval selector 改为直接属性；Phase H 保留 plan rebuild 四异常、两个 challenger-config build 调用点的 `ValueError` 与 materialize `Exception` partial-success `return 2`，变量名保持 `write_exit_code`。Phase C/D 仅把 exact20 selector 改为直接属性且语义不变；Phase G/H 同理只对 exact20 字段直接访问，所有 table-out argparse 字段与动态 Phase E inventory 保持 HEAD `getattr`，不得扩充 Dayu 字段或 blanket 改写。新增 Phase E/F/H AST、异常、顺序、调用次数与 phantom-zero 门禁；方案 A ACCEPTED，方案 B 新 helper extraction REJECTED。v5.4 accepted 历史与其他 slice 语义不变
- **v5.5 最终接受**: DeepSeek 124536 与 MiMo 124537 均 PASS，open High/Medium/Low=0/0/0；DeepSeek 122456 与 MiMo 122457 的 8/8 findings 全部 CLOSED，无新 finding。Controller 接受 S11-CTRL-02，Slice 11 达到 code-generation-ready 且可实施
- **v5.5→v5.6 变更**（基于 DeepSeek 150148、MiMo 150149 与 Controller 对 clean HEAD `2a4bafb` 的 AST/LOC 复核）: **AGG-CTRL-01** — 删除 aggregate completion 中 `write.py <=850` / `research_template.py <=800` 的历史粗估硬门槛；当前 `1014/1369` 仅作 informational measurement，不以当前值上浮为新的任意上限，改用 FunctionDef/AnnAssign/Assign、phase/dispatch 表项、owner binding、DAG 与 zero-compat 精确结构门禁。**AGG-CTRL-02** — aggregate terminal `research_template.py` 为 exact41，即 entry 1 + Slice 10 selector 1 + runners 39；Slice 9 基线的原始 FunctionDef 123 与 `83+40=123` 历史保持不变，因为当时 selector 尚未由 Slice 10 添加，拒绝把历史改写为 124。**AGG-CTRL-03** — accepted Slice 1–13 的 ownership 已闭合，不新增 Slice 14、不修改 code/tests/README；aggregate structural、behavior、type、lint-delta 与 machine gates 任一失败才阻止进入 deepreview。
- **v5.6 最终接受**: DeepSeek 152220 与 MiMo corrective 153009 均 PASS，open High/Medium/Low=0/0/0；初审 8 项与 MiMo 152221 的 2 项 re-review observations 全部 CLOSED。152221 的 M-01 为 non-defect，L-01 为 working-tree measurement error，均经 153009 corrective 复核关闭。Controller 接受 AGG-CTRL-01..03，aggregate validation 可恢复。
- **v5.6→v5.7 变更**（基于 DeepSeek 154611、MiMo 154612 与 Controller 对 `4c5bb1b`/`5821014`/`origin/main=2115c86` 的同算法 Ruff 复测）: **AGG-RUFF-CTRL-01** — architecture ratchet baseline 精确锁定 first accepted plan commit `f0a3ea1` 的唯一 parent `5821014`；拒绝 `origin/main` 的跨 work-unit 不对称比较，也拒绝 current HEAD 的 tautological baseline。**AGG-RUFF-CTRL-02** — architecture hard gate 固定 Ruff `0.16.1`、无显式 rule select 的 Slice-report rule set、相同目录 scope 与 rule-code Counter 算法；HEAD=`335`、BASE=`364`、positive=`{}`、negative=`I001:11 / TRY004:17 / UP035:1`。该算法不等于 `--select ALL`（HEAD=`11248`），也与 constraints/min-py311.txt 的 Ruff `0.15.11` E/F CI 环境区分。**AGG-RUFF-CTRL-03** — `origin/main=2115c86` 同算法 HEAD=`335`、BASE=`143`、per-code positive=`216`，作为 PR-level residual 强制输入 aggregate deepreview，但不阻断 architecture gate；CI required lane 不检查 production Ruff 的事实同样记录为 residual，不在本 work unit 修改 workflow。**AGG-RUFF-CTRL-04** — 不新增 Slice 14；机械修复 TRY004/B009/FURB162 会改变异常、argparse defensive access 或时区语义并违反 accepted contracts。拒绝任意 residual/current-HEAD baseline、MiMo 将 origin/main 用作 architecture hard ratchet 的建议及无工具证据的 changed-lines 算法。
- **v5.7 re-review observations 修复**（基于 DeepSeek 160555、MiMo 160556 与 Controller cross-version 复测）: **AGG-RUFF-CTRL-05** — Ruff `0.16.1` 是既有 Slice artifacts 与 ratchet 结果的精确复现版本，不是 CI 版本；同一 HEAD/scope 的 Ruff `0.15.11` 无显式 select 仅产生 exact8（`F401:7`、`F541:1`），而 `0.16.1` 产生 335，故两个版本不得混用。**AGG-RUFF-CTRL-06** — scope `dayu/cli/commands/ dayu/services/` 精确对应本 master plan C1/C3/C4/C5 production ownership；engine/fins/host/config 等不属于本 work unit，origin/main PR residual 仍严格使用同一 scope，不声称全 repo。§11 item23 显式记录 negative total29（`I001:11 / TRY004:17 / UP035:1`）为三类实际改善。DeepSeek L02 的 F811/F841/F401/F541 negative 仅为 optional positive context，非 architecture correctness 必需，拒绝扩展完成定义；MiMo V57-03/V57-09 合并为同一版本理由 observation。
- **v5.7 最终接受**: DeepSeek 161501 与 MiMo 161502 均 PASS，open High/Medium/Low=0/0/0；初审与 re-review observations 按 raw-item 口径 22/22、按合并 finding 口径 16/16 全部 CLOSED。Architecture Ruff positive=`{}`（0）、negative total=`29`；origin/main PR residual positive=`216` 继续作为 aggregate deepreview mandatory input，aggregate validation 可恢复。
- **v5.7→v5.8 变更**（基于 aggregate 双路 deepreview 与 Controller 对 `4d2535d`、`origin/main=2115c86`、architecture baseline `5821014` 的源码/Git/测试复核）: **AGG-RT-CTRL-01** — Aggregate Fix RT-01 只授权 `dayu/cli/commands/research_template.py::_run_validate_source_map` 将固定 `return 0` 改为 `return 0 if result.get("ok") is True else 1`；JSON stdout、dispatch key/owner/DAG、异常传播与其他 runner 均不变。同步把该函数中文 docstring 的 Returns 精确写为“校验成功返回 0，校验失败返回 1”。invalid CLI regression 必须使用 `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` 与 `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 构造 template mismatch，经真实 `run_research_template_command` 断言退出码 1、stdout JSON `ok is False` 且 `errors` 非空；valid regression 使用 consumer/consumer 并保持退出码 0 与 `ok is True`。该变更是对 Slice 9 stripped-docstring AST exact migration 与 Slice 10 behavior-preservation 的唯一有界例外；不授权 generic validate-runner 重构、不新增 Slice 14、不改变 manual recovery application 或 rollback 的默认 `run_label="configuration-application"` accepted design。因 production 字节将变化，Aggregate Fix 后必须重跑 Python 3.11 min-compat full suite，不得复用 Slice 13 的旧字节同一性证据。
- **v5.8 plan review observation 修复**: DeepSeek L-PLAN-01 `accepted / FIXED`——invalid/valid 真实 CLI regression 已锁定上述 financial/consumer template-mismatch 与 consumer/consumer 对称构造，禁止手写 payload 或另选不一致模式。MiMo initial plan review PASS/open0；Controller plan-review open High/Medium/Low=`0/0/0`，final 双路闭环见下一条。
- **v5.8 最终接受**: DeepSeek final corrective 与 MiMo final re-review 均 PASS，open High/Medium/Low=`0/0/0`；DeepSeek 初审 L-PLAN-01 已 FIXED/CLOSED，MiMo initial/final 均 PASS/open0，全部 plan findings CLOSED。AGG-RT-CTRL-01 code-generation-ready，Aggregate Fix RT-01 可实施；RT-01 code finding 本身仍为 open Medium exact1，必须经 implementation 与 aggregate re-review 才能关闭。
- **状态**: v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS（全部 plan findings CLOSED、Controller plan-review open0；Aggregate Fix RT-01 可实施。v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS 与更早 accepted 版本作为历史保留）

---

## 0. Protocol Spike —— 已执行、已锁定

已在本轮 plan-writing 前执行完毕，作为 plan evidence 记录，不在任何 Slice 中提交空 fixture。

### Spike 1: WriteDispatchArguments Protocol

**命令**: `source .venv/bin/activate && pyright /tmp/protocol_spike_write.py`

**验证命题**: Protocol 声明字段访问 → 0 errors；故意拼错字段 → pyright error。

**结果**:
```
/tmp/protocol_spike_write.py:35:13 - information: Type of "valid_pred" is "(a: WriteDispatchArguments) -> bool"
/tmp/protocol_spike_write.py:44:73 - error: Cannot access attribute "nonexistent_field" for class "WriteDispatchArguments"
  Attribute "nonexistent_field" is unknown (reportAttributeAccessIssue)
1 error, 0 warnings, 3 informations
```

### Spike 2: ResearchTemplateDispatchArguments Protocol

**命令**: `source .venv/bin/activate && pyright /tmp/protocol_spike_rt.py`

**验证命题**: 同上。

**结果**:
```
/tmp/protocol_spike_rt.py:17:13 - information: Type of "valid_pred" is "(a: ResearchTemplateDispatchArguments) -> str"
/tmp/protocol_spike_rt.py:21:17 - error: Cannot access attribute "nonexistent_action" for class "ResearchTemplateDispatchArguments"
  Attribute "nonexistent_action" is unknown (reportAttributeAccessIssue)
1 error, 0 warnings, 2 informations
```

**结论**: Protocol 对声明字段零错误，错字产生 pyright error。两个方案已锁定。C2/C3 的 predicate lambda 依赖 Protocol 提供静态字段校验，pyright 在真实 predicate 代码上执行此检查。

---

## Closure Tables

### F-01..F-07（第三轮 MiMo review，v3.5 已 CLOSED，本轮保持）

| Finding | 处置 | 证据 Section |
|---|---|---|
| **F-01** (execution_options 预计算/重算矛盾) | CLOSED — Phase-specific typed contexts: `_WriteCommandContext`（Phase A，无 execution_options）+ `_WriteConfigurationContext`（Phase B，含 `execution_options: ExecutionOptions`）。Phase A adapter 9/10/14 惰性 build 一次；Phase B adapter 从 `config_ctx.execution_options` 读取，绝不重算。`_EarlyWriteSubcommandEntry.runner: Callable[[_WriteCommandContext], int]`，`_ConfigurationWriteSubcommandEntry.runner: Callable[[_WriteConfigurationContext], int]` | §11b, §11c, §11e |
| **F-02** (S0 空 pass 测试) | CLOSED — 删除两个 `pass` 空测试。S0 characterization 新增完整集成矩阵（I 部分，覆盖全部 16 write action flags + 全部 39 research-template action keys），通过 monkeypatch call trace 断言。Protocol spike evidence 保留在 §0 | §5 Slice 0 §I |
| **F-03** (self-contained 声明不成立) | CLOSED — implementation decisions and inventories are self-contained。Phase 边界以稳定函数名、首末 predicate 字段、前后调用锚点描述；行号仅作 HEAD 5821014 辅助证据 | §1.3 |
| **F-04** (代码块 `...`) | CLOSED — C5 17 helper inventory 改为完整表格（exact signature + 代表性现有实现位置 + json/bytes/error/overwrite 行为 spec + eligible callers + deferred variants）。C4 8 子流程列出完整精确类型签名和全部 15 参数类型。Phase H 完整调用链 | §5 Slice 1, §5 Slice 12, §5 Slice 11f |
| **F-05** (审计命令) | CLOSED — HEAD 5821014 历史取证通过 `git show 5821014:dayu/cli/commands/write.py` 后再按 4637–4822 范围筛选，真实输出 16 行（Phase A:14 + Phase B:2）。当前 HEAD `b55f794` 及后续实现不对 worktree 执行该旧行号 awk，改用 §1.3 的 AST 锚点命令与结构测试 | §1.3, §11c |
| **F-06** (Phase-specific context 缺失) | CLOSED — 新增 `_WriteConfigurationContext` frozen dataclass，精确含 `args`、`paths_config`、`write_model_override_name`、`execution_options`。Phase B 表使用 `_ConfigurationWriteSubcommandEntry`，runner 签名为 `Callable[[_WriteConfigurationContext], int]` | §11b, §11c |
| **F-07** (Phase A 计数歧义) | CLOSED — 全文统一 Phase A=14、Phase B=2、总计=16。inventory 表、§1.3、changelog 全部一致 | §1.3, §11c |

### R2-01..R2-08（前轮已关闭，本轮未重开）

全部保持 CLOSED。对应证据在 S6（零反向 import）、S1（ModelConfigJsonValue）、S0（characterization）、S10–11（Protocol dispatch）、§9（精确 CI YAML）、§1.6.7（异构变体 defer）。

### V4 Adjudication（第四轮 MiMo review，v4.0 新增）

| Finding | 严重度 | 处置 | 证据 Section |
|---|---|---|---|
| **V4-01** (34≠39) | MEDIUM | **ACCEPTED** — 全部 39 action key/runners 逐项列出。§1.5、Slice 9、Slice 10 dispatch mapping、S0 I-b 全部 39 | §1.5, §5 S9–10, §5 S0 |
| **V4-02** (审计范围) | LOW | **ACCEPTED** — 历史 HEAD 5821014 的上界 4817→4822；复现必须通过 `git show 5821014:<path>`，不得对当前 worktree 套用旧行号。当前/实现后审计改用符号/AST 锚点或 phase 表结构测试 | §1.3, §11c |
| **V4-03** (I-a 描述) | LOW | **ACCEPTED** — S0 I-a 描述精确化：11 项参数化覆盖全部 16 flag，逐类说明覆盖方式 | §5 S0 |
| **V4-04** (Slice6 diff) | LOW | **ACCEPTED** — §10 补充预估 250–350 行及不可再拆理由 | §10 |
| **V4-05** (patch 路径) | LOW | **ACCEPTED** — S0 注明 patch 目标为 HEAD `write.py`；S7 后需同步更新 | §5 S0 |
| **V4-06** (传播链) | LOW | **ACCEPTED** — §4.3 例外 (b) 补充 `print_write_report` | §4.3 |
| **V4-07** (Phase G 重复) | LOW | **REJECTED** — 忠实现状，不在本 task scope 新增 optional-path 重构 | §3 |
| **C4-01** (S0 测试时序) | **HIGH** | **ACCEPTED** — S0 仅提交 HEAD if-chain characterization（16 write + 39 rt）。S10 在引入 mapping 时新增 39-key 矩阵。S11 在引入 adapter 时新增 16-action 矩阵。每个 slice 独立绿 | §5 S0, §5 S10, §5 S11 |

### Final acceptance（`plan-review-20260807-164701.md`）

**Verdict**: PASS_WITH_RISKS。**0 HIGH blockers**。唯一 MEDIUM residual: Slice 10 的 39 runner 签名一致性由 `Mapping[str, Callable[[DayuCliArguments], int]]` 类型注解、pyright 静态检查及 39-key 参数化矩阵测试共同保证，设计上可接受。全部 7 项 V4 findings 已按 adjudication 处置（ACCEPTED 6 + REJECTED 1）。C4-01 HIGH finding 修正完整。F-01..F-07 和 R2-01..R2-08 全部保持 CLOSED。源码验证确认 39 action key、16 selectors（11+3+2）、4 次 `_build_execution_options` 调用、`print_write_report` object 传播链全部准确。无 v4.0 新回归。计划达到 code-generation-ready 标准，可进入 implementation phase。**这是 v4.0 的历史判决；当前 gate 状态始终以本文顶部当前 status 为准。**

---

## 1. 现状调用图 / 职责地图与量化证据

### 1.1 涉及文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `dayu/cli/commands/write.py` | 741 | `run_write_command` + 写后 research materialization helper（HEAD `1d0f9e6`） |
| `dayu/cli/commands/research_template.py` | 4145 | 顶层 FunctionDef 123：`run_research_template_command` 1 + runner 39 + Slice 9 待迁函数 83；另有 ClassDef 2 |
| `dayu/services/write_service.py` | 1078 | `WriteService` + `print_report` |
| `dayu/services/write_model_*.py` | 19 文件 | build/load/persist/verify/format |
| `dayu/cli/dependency_setup.py` | ~250 | `WriteCliConfig` (20 字段)、依赖装配 |
| `dayu/cli/arg_parsing.py` | ~2030 | argparse 解析器注册 |
| `dayu/cli/main.py` | ~85 | 命令路由 |
| `tests/application/test_write_service.py` | 1947 | WriteService + print_report 测试 |
| `tests/engine/test_cli_running_config.py` | ~9310 | CLI 集成测试 |

### 1.2 write.py 当前功能域分组（HEAD `1d0f9e6`，741 行）

| 功能域 | 定义锚点 | 顶层 FunctionDef |
|---|---|---:|
| 写后 research materialization helper | `_materialize_research_after_write` | 1 |
| 主调度 | `run_write_command` | 1 |

Slice 5–8 已将 config helpers/validators、configuration application/rollback、
snapshot、execution、manual recovery 与 Challenger helper 全部迁入真实 owner；
当前 `write.py` 只定义上述两个函数。Slice 9 仅修改 helper 内 line 81 的
function-local materialize import owner，不改变其定义数量或主调度语义。

### 1.3 run_write_command phase 边界（HEAD 5821014 历史取证；当前 HEAD `1d0f9e6` 按结构锚点验收）

下列 46xx–50xx 行号只对 HEAD `5821014` 的 Slice 0 历史 characterization
有效，不是当前 741 行 `write.py` 的验收行号。当前 HEAD `1d0f9e6` 与后续
实现的边界以 `run_write_command` 函数、首末 predicate/call 锚点与 AST
结构测试为准；禁止对当前 worktree 套用历史行号 awk 并把空输出当作
PASS。

**Phase A — Early Manual Recovery**：从 `run_write_command` 内第一个 dispatch 分支（predicate 字段 `revalidate_write_model_configuration_manual_recovery_incident_dossier`）到最后一个 Phase A dispatch 分支（predicate 字段 `recover_write_model_configuration`）。

源码锚点：
- 起点：`if bool(getattr(args, "revalidate_write_model_configuration_manual_recovery_incident_dossier", False)):`（HEAD 5821014 历史行 4636 附近）
- 末尾：`if bool(getattr(args, "recover_write_model_configuration", False)):`（历史行 4803）后紧跟 `_resolve_write_model_override_name(args)`（历史行 4809），标志 Phase A 结束

Phase A 内 `_build_execution_options(args)` 仅在以下 3 个分支内联调用：
- `clear_write_model_configuration_manual_recovery` 分支（历史行 4747）
- `verify_write_model_configuration_manual_recovery` 分支（历史行 4759）
- `recover_write_model_configuration` 分支（历史行 4807）

Phase A 共 **14 条目**。

**Phase B — Configuration**：从 `_resolve_write_model_override_name(args)` 调用（历史行 4809）和 `execution_options = _build_execution_options(args)`（历史行 4810）开始，到最后一个 Phase B dispatch 分支（predicate 字段 `rollback_write_model_configuration`，历史行 4817）结束。共 **2 条目**。

**Phase C–H**（顺序逻辑，不在 dispatch 表中）：
- C: Recovery Gate — `_check_write_model_configuration_manual_recovery_gate`（历史行 4823）
- D: Challenger Preflight — `_verify_challenger_preflight_approval_before_host`（历史行 4829）
- E: Challenger Run Plan — `_build_challenger_run_plan_from_args`（历史行 4848）
- F: Run Approval Verification — `_verify_and_consume_challenger_run_approval_before_host`（历史行 4869）
- G: Summary — `WriteService.print_report`（历史行 4887）
- H: Default Write Execution — `_prepare_cli_host_dependencies` → `_run_write_stage` 或 `_run_champion_challenger_experiment`（历史行 5044）

**Phase A + Phase B 历史证据复现**（HEAD 5821014；上界 4822 覆盖
Phase B 最后分支完整范围）：
```bash
git show 5821014:dayu/cli/commands/write.py \
  | rg -n "getattr" \
  | awk -F: '$1 >= 4637 && $1 <= 4822'
```
**历史真实输出: 16 行**（Phase A:14 + Phase B:2）。

**当前 HEAD `1d0f9e6` 验收命令**（不依赖行号；以首末 call 锚点切片并
精确计数顶层 `if`）：

```bash
.venv/bin/python - <<'PY'
import ast
from pathlib import Path

module = ast.parse(Path("dayu/cli/commands/write.py").read_text(encoding="utf-8"))
runner = next(
    node
    for node in module.body
    if isinstance(node, ast.FunctionDef) and node.name == "run_write_command"
)
calls_by_statement = [
    {
        node.func.id
        for node in ast.walk(statement)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for statement in runner.body
]
phase_a_start = next(
    index
    for index, calls in enumerate(calls_by_statement)
    if "_run_write_model_configuration_manual_recovery_incident_dossier_revalidation"
    in calls
)
configuration_start = next(
    index
    for index, calls in enumerate(calls_by_statement)
    if "_resolve_write_model_override_name" in calls
)
phase_c_start = next(
    index
    for index, calls in enumerate(calls_by_statement)
    if "_check_write_model_configuration_manual_recovery_gate" in calls
)
phase_a = runner.body[phase_a_start:configuration_start]
phase_b = runner.body[configuration_start:phase_c_start]
assert sum(isinstance(statement, ast.If) for statement in phase_a) == 14
assert sum(isinstance(statement, ast.If) for statement in phase_b) == 2
assert (
    "_run_write_model_configuration_manual_recovery_incident_dossier_revalidation"
    in calls_by_statement[phase_a_start]
)
assert (
    "_run_write_model_configuration_manual_recovery_application"
    in calls_by_statement[configuration_start - 1]
)
assert "_run_write_model_configuration_rollback" in calls_by_statement[phase_c_start - 1]
print("Phase A=14, Phase B=2; current structural anchors PASS")
PY
```

**预期输出**: `Phase A=14, Phase B=2; current structural anchors PASS`。Slice 11
实现 phase table 后，再以表长度与 14+2 参数化结构测试取代当前 if-chain
结构命令。

### 1.4 print_report 副作用顺序（write_service.py:439–1010）

| 步骤 | 操作 | 条件 |
|---|---|---|
| 1 | `print_write_report(output_dir, model_catalog=model_catalog)` | 总是执行 |
| 2 | 若返回 2，立即返回 2 | 步骤 1 失败 |
| 3 | 门禁校验（互斥检查、组合约束） | 步骤 1 成功 |
| 4 | 成本重估后运行比较打印 | 条件 |
| 5 | promotion proposal 导出/验证 | 条件 |
| 6 | config change request 导出/验证 | 条件 |
| 7 | config change approval 签发/验证 | 条件 |
| 8 | 模型健康趋势 + Challenger 提案导出/验证 | 条件 |
| 9 | preflight approval 签发 | 条件 |

**关键不变量**: 步骤 1（`print_write_report`）在步骤 3（门禁校验）之前执行。任何重构必须保持此顺序。

### 1.5 research_template.py 功能域分组（HEAD `1d0f9e6`，4145 行）

Slice 9 的 AST inventory 以顶层定义而非历史自然行段为真源。当前 123 个
FunctionDef 必须闭合为 83 个迁移函数 + 39 个 `_run_*` runner + 1 个入口；
2 个 dataclass 与 7 个域常量随 ownership 一并迁移到 helpers：

| 终态 owner | FunctionDef | ClassDef | 职责 |
|---|---:|---:|---|
| `_research_template_helpers.py` | **22** | **2** | 叶子 helper + `ResearchTemplate` / `ResearchTemplateRecommendation` + 7 constants |
| `_research_template_core.py` | **26** | 0 | 模板基础、监控规则/源映射、清单/usage 与 write-manifest binding |
| `_research_template_bundle.py` | **12** | 0 | Bundle 描述符、重绑定、回滚及 descriptor writer |
| `_research_template_monitoring.py` | **11** | 0 | 监控执行计划、状态与调度清单 |
| `_research_template_materialize.py` | **12** | 0 | 物化、workspace refresh、Portfolio |
| `research_template.py` | **40** | **0** | 入口 1 + CLI runner 39 |

**闭合**: `22 + 26 + 12 + 11 + 12 = 83` 个迁移函数；
`83 + 40 = 123` 个原顶层函数；原 2 个 ClassDef 全部迁至 helpers。

**Dispatch 模式**: **39 路** `if action == "xxx"` 线性链，key 为 `research_template_action`（argparse sub-subparser `dest=` 字符串）。源码验证: `grep -c 'if action ==' research_template.py` = 39，`grep -c '^def _run_' research_template.py` = 39。

39 个 action key（按源码出现顺序）: `list`, `show`, `scorecard`, `evidence`, `schema`, `checklist`, `materialize-checklist`, `copy`, `recommend`, `compose`, `monitoring-rules`, `research-workbook`, `validate-research-workbook`, `update-research-workbook`, `rollback-research-workbook`, `source-map`, `validate-source-map`, `package-manifest`, `materialize`, `refresh-workspace`, `list-bundles`, `validate-bundle`, `rebind-bundle`, `rollback-bundle-rebind`, `monitoring-plan`, `validate-monitoring-plan`, `list-monitoring-plans`, `monitoring-status`, `workbook-status`, `workbook-report`, `validate-workbook-report`, `workbook-report-status`, `materialize-portfolio`, `preview-portfolio`, `scheduler-manifest`, `validate-scheduler-manifest`, `source-bindings`, `rollback-source-bindings`, `source-binding-history`。

### 1.6 C5 重复工具函数 —— AST/语义等价分组

#### 1.6.1 canonical/fingerprint 变体

- `_canonical_json` str 变体: `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` → `str`。**10 文件**（标准 str 变体）。另有 str+dict 子变体：`json.dumps(dict(value), ...)` → `str`。**1 文件**（`gate_revalidation.py:65`）。两者合计 canonical_json_str direct definitions = **11**。`health.py` 使用内联 `json.dumps` 非 `_canonical_json` 定义，不计入此数。
- `_canonical_json` bytes 变体: `json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")` → `bytes`。**6 文件**。
- `_canonical_json` str+dict 变体: 同 str 变体但调用 `dict(value)`。**1 文件**（`write_model_configuration_manual_recovery_gate_revalidation.py:65`）。
- `_fingerprint` str 系: `hashlib.sha256(_canonical_json(v).encode("utf-8")).hexdigest()` → `f"sha256:{d}"`。**12 文件**（11 个私有 `_canonical_json` 返回 str → `.encode("utf-8")` 的文件 + `health.py` 内联 `json.dumps` 等价；`incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation` 的 `_fingerprint` 属此系——其底层 `_canonical_json` 返回 str，调 `.encode("utf-8")` 后 sha256）。
- `_fingerprint` bytes 系: `hashlib.sha256(_canonical_json(p)).hexdigest()` → `f"sha256:{d}"`。**5 文件**（`configuration_application`、`manual_recovery`、`manual_recovery_application`、`manual_recovery_clearance`、`rollback_application`——底层 `_canonical_json` 返回 bytes，sha256 直接）。

#### 1.6.2 validated_fingerprint —— 6 sub-family + 6 错误文本

16 个 `_validated_fingerprint` 定义分属 **6 个 sub-family**，差异在输入预处理策略（`str(value or "").strip()` vs `_required_text(value, maximum_length=...)`）、max_length（无/71/80/128）、是否 `lower()`、错误文本：

| 子族 | 输入预处理 | max_length | lower() | 错误文本 | 文件数 | 示例文件 |
|---|---|---|---|---|---|---|
| A | `str(value or "").strip()` | 无 | 是 | `"must be a sha256 fingerprint"` | 6 | `write_model_configuration_change.py:187` |
| B | `_required_text(value, maximum_length=80)` | 80 | 是 | `"must be a sha256 fingerprint"` | 5 | `write_model_configuration_manual_recovery_clearance.py:432` |
| C | `_required_text(value, maximum_length=80)` | 80 | **否** | `"must use sha256"` / `"is invalid"` | 1 | `write_model_configuration_application.py:307` |
| D | `_required_text(value, maximum_length=128)` | 128 | **否** | `"must be a SHA-256 fingerprint"` | 1 | `write_model_configuration_manual_recovery.py:372` |
| E | `_required_text(value, maximum_length=80)` | 80 | 是 | `"is not a SHA-256 fingerprint"` | 1 | `write_model_configuration_manual_recovery_verification.py:207` |
| F | `_required_text` + regex fullmatch | 71 | **否** | `"is not a SHA-256 fingerprint"` | 1 | `write_model_configuration_manual_recovery_gate_revalidation.py:156` |
| G | `str(value or "").strip()`（类型注解 `value: str`） | 无 | 是 | `"must be a sha256 fingerprint"` | 1 | `write_model_challenger_proposal.py:68` |

**v4.2 纠偏（C5-CTRL-01）**: shared `validated_fingerprint` 强制 `lower()` 且只有一个 `error_label` 参数。族 C（两种错误文本）、族 D（`int(digest,16)` 校验）、族 F（regex fullmatch）不使用 `lower()`，族 C/D/F 校验算法也不同于 shared 的逐字符 hex 检查。族 B-F **全部保留私有 `_validated_fingerprint` 与 `_required_text`**，不得经预处理后调用 shared。仅族 A/G（7 文件，`str(value or "").strip().lower()` 策略）迁移至 shared `validated_fingerprint`。

#### 1.6.3 mapping/required_text/exact_fields

- `_mapping` 静默版（**3 文件**: `challenger_proposal.py:49`, `health.py:61`, `write_run_comparison.py:19`）→ `optional_mapping(value: ModelConfigJsonValue) -> JsonObject`
- `_mapping` 严格版（**14 文件**，含 `gate_revalidation.py` 返回 `dict(value)`）→ `require_mapping(value: ModelConfigJsonValue | JsonObject, *, name: str) -> JsonObject`
- `_required_text` —— **v4.2**: 16 个私有定义分属 **8 个行为家族**（源码 `rg -l "^def _required_text"` 确认 16 个，family 表 6+2+2+2+1+1+1+1=16），不可用单一签名统一：

| 族 | NFKC | 控制字符检查 | 空白处理 | max_length | 文件数 | 代表性文件 |
|---|---|---|---|---|---|---|
| 1 | 是 | ord(c)<32 | 静默 strip | 必需参数 | **6**（私有 eligible） | `write_model_configuration_application.py:204`, `write_model_configuration_rollback.py:246`, `write_model_configuration_rollback_application.py:246`, `write_model_configuration_manual_recovery.py:283`, `write_model_configuration_manual_recovery_clearance.py:414`, `write_model_configuration_manual_recovery_incident_dossier.py:95` |
| 2 | 是 | **无** | 静默 strip | 必需参数 | **2** | `write_model_configuration_manual_recovery_verification.py:159`, `write_model_configuration_manual_recovery_application.py:252` |
| 3 | 否 | unicodedata.category C | **拒绝首尾空白** | 默认 4096 | **2** | `write_model_configuration_change.py:230`, `write_model_configuration_preapplication.py:242` |
| 4 | 否 | unicodedata.category C | **拒绝首尾空白** | 必需参数 | **2** | `write_model_challenger_run_approval.py:204`, `write_model_challenger_preflight_approval.py:127` |
| 5 | 否 | **无** | **拒绝首尾空白** | 默认 4096 | **1** | `write_model_challenger_promotion.py:158` |
| 6 | 否 | ord(c)<32 | 静默 strip | 必需参数 | **1** | `write_model_configuration_manual_recovery_incident_dossier_revalidation.py:159` |
| 7 | 否 | **无** | 静默 strip | 必需参数 | **1** | `write_model_configuration_manual_recovery_gate_revalidation.py:115` |
| 8 | 否 | **无** | 静默 strip | **无参数** | **1** | `write_model_live_smoke_plan.py:83` |

仅族 1（6 文件私有 eligible，不含未跟踪 public helper）可纳入 shared。族 2-8（10 文件）各有不同校验完整性，迁移即改变行为，全部 **defer**。

- `_exact_fields` / `_validate_exact_fields` —— **v4.1**: 15 个定义分属 **3 命名 + 4 错误格式 = 8 个 exact family**：

| 族 | 命名 | expected 类型 | 错误分隔符 | 多余字段词 | 文件数 |
|---|---|---|---|---|---|
| 6A | `_validate_exact_fields` | `set[str]` | 逗号 | "unexpected" | 5 |
| 6B | `_exact_fields` | `set[str]` | 分号 | "extra" | 6 |
| 6B' | `_exact_fields` (一行) | `set[str]` | 冒号 | "extra" | 1 |
| 6B'' | `_exact_fields` (一行) | `set[str]` | 分号 | "extra" | 1 |
| 6C | `_exact_fields` | `frozenset[str]` | 分号 | "unexpected" | 2 |

8 个 family 的错误文本格式无法用单个参数化函数等价覆盖。**全部 defer**，不在本 plan 的 `_write_artifact_utils.py` 中提供 `require_exact_fields`。15 个文件各自保留私有定义。后续独立 plan 治理。

#### 1.6.4 Group A — AST 等价（纳入 Slice 1–2）

| 函数 | 文件数 | Proposed 精确签名 | 代表性现有实现位置 | 行为 spec |
|---|---|---|---|---|
| `_file_fingerprint` | 10 | `file_fingerprint(path: Path) -> str` | `challenger_run_approval.py:159`（walrus 风格） | `hashlib.sha256()` + 1MB 块读取 + `f"sha256:{digest.hexdigest()}"` |
| `_bytes_fingerprint` | 10 | `bytes_fingerprint(value: bytes) -> str` | `configuration_application.py:292` | `f"sha256:{hashlib.sha256(value).hexdigest()}"` |
| `_format_utc` microseconds 族 | **3** | `format_utc(value: datetime) -> str` | `configuration_application.py:255` | `value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")`。**v4.2**: 私有 eligible caller 3 文件（`configuration_application`、`rollback_application`、`manual_recovery`），不计未跟踪 public helper |
| `_format_utc` seconds 族 | 2 | `format_utc_seconds(value: datetime) -> str` | `manual_recovery_application.py:309` | **v4.2 精确 spec**: 先检查 `value.tzinfo is None or value.utcoffset() is None`，naive 则 `raise ValueError("now must include a timezone")`；再 `value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")`。不调用 `_normalize_now`，不依赖 Group D。截断微秒 |
| `_format_utc` auto 族 | 6 | — | — | **DEFER**。`isoformat()` 无 timespec 参数，依赖 Python 版本 auto 语义，不等价于 microseconds/seconds。6 文件：`configuration_change`、`challenger_run_approval`、`challenger_preflight_approval`、`configuration_rollback`、`manual_recovery_gate_revalidation`、`manual_recovery_incident_dossier_revalidation` |
| `_is_relative_to` | 8 | `is_subpath(path: Path, root: Path) -> bool` | `configuration_application.py:475` | `try: path.relative_to(root) except ValueError: return False; return True`。**不解析符号链接**。**v4.1**: 8 个现有实现全部使用 `path.relative_to(root)` 的 try/except 模式，无一使用 resolve。删除无 caller 的 resolve 版 `is_relative_to` |
| `_absolute_path` | 7（三族 `_required_text`） | `absolute_path(text: str, *, name: str) -> Path` | `configuration_change.py:315` | **v4.2（C5-CTRL-02）**: `text: str` 入参（非 `ModelConfigJsonValue`）。先 `Path(text).expanduser()`，在 resolve 前检查 `is_absolute()`，否则 `raise ValueError(f"{name} must be absolute")`，再 `return path.resolve()`。text 校验由调用方各自的 `_required_text` 处理——7 个定义分属三族：族 1（NFKC+ord<32）4 文件（`configuration_application`、`rollback_application`、`manual_recovery`、`configuration_rollback`）、族 2（NFKC+无控制字符）1 文件（`manual_recovery_application`）、族 3（无 NFKC+cat C）2 文件（`configuration_change`、`configuration_preapplication`）。`_validated_absolute_path`（`challenger_run_approval.py:375`，不 expanduser）**defer** |
| `_snapshot_fingerprint`（含业务 validator） | 5 | **DEFER** | — | 5 个私有实现全部先调用 `validate_write_scene_model_routing_snapshot(snapshot)` 再提取 `snapshot["snapshot_fingerprint"]`。注入 `validator: Callable[[JsonObject], None]` 需精确类型、5 个 validator 实参映射及 pyright 可行性验证，当前缺少充分证据。5 文件各自保留 `_snapshot_fingerprint` |
| `_transaction_id` | 5 | **DEFER**（移至 Group C） | — | **v4.2**: 5 个私有定义分属 4 个行为家族：(a) 1 个 null-byte 分隔 hash（`configuration_application`）；(b) 1 个 domain-tagged null-byte 分隔 hash（`rollback_application`）；(c) 2 个 newline+version-suffix 分隔 hash（`manual_recovery_application`、`manual_recovery_verification`）；(d) 1 个输入校验器（`incident_dossier`）。hash material 算法各异，不可用一个统一签名替换。全部 5 个保留原位。HEAD 81df373 无 public `transaction_id` helper |
| `_decode_base64` 族 A | 4 私有 + 1 inline = **5** | `decode_base64(text: str, *, name: str) -> bytes` | `configuration_application.py:420` | **v4.2（C5-CTRL-03）**: `text: str` 入参（非 `ModelConfigJsonValue`）。`base64.b64decode(text, validate=True)`。错误文本 `"{name} is invalid"`。捕获 `(binascii.Error, TypeError, ValueError)`。各 caller 先用各自 `_required_text` 族得到 text 后传入 shared。**无 urlsafe 参数**（零 caller）。4 私有定义文件：`configuration_application`、`rollback_application`、`manual_recovery_application`、`configuration_rollback`；1 inline 调用：`configuration_preapplication` |
| `_decode_base64` 族 B | 1 | `decode_base64_strict(text: str, *, name: str) -> bytes` | `manual_recovery.py:385` | **v4.2（C5-CTRL-03）**: `text: str` 入参。`base64.b64decode(text, validate=True)`。错误文本 `"{name} must be valid base64"`。捕获 `(binascii.Error, ValueError)`（**缺 TypeError**）。行为保持——不补 TypeError、不改为族 A 错误文本 |

#### 1.6.5 Group B — 需保留差异（纳入 Slice 1–2）

| 函数 | 文件数 | Proposed 精确签名 | 行为 spec |
|---|---|---|---|
| `_serialize`（含 sort_keys=True，13 文件） | 13 | `serialize_pretty(payload: JsonObject) -> str` | `json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"` |
| `_serialize`（**缺 sort_keys**，1 文件） | 1 | **DEFER** | `write_model_challenger_promotion.py:804` 的 `_serialize` 缺 `sort_keys=True`。**v4.1**: 行为保持优先——不顺手修复。此文件不迁移到 `serialize_pretty`，保留私有 `_serialize` |
| `serialize_compact` | 0（无现有等价 caller） | **DEFER** | 无现有私有 `_serialize` 使用 compact 格式（无 indent+compact separators）。`serialize_compact` 为 net-new helper，不在 C5 消除重复的 scope 内，删除 |
| `_persist_immutable` | 13（5 family） | **DEFER** | **v4.1**: 13 个 `_persist_immutable` 实现分属 **5 个 family**，核心差异如下。需多个 flags 才能保持语义，参数爆炸——defer，不追求 shared helper 数量：

| Family | 文件数 | 原子方法 | symlink 检查 | Path 解析 | 反序列化异常 | 返回 |
|---|---|---|---|---|---|---|
| 1: hard-link+symlink guard | 4 | `os.link` | 3x（前后+FileExistsError 内） | `resolve()` | `OSError, JSONDecodeError` | `target` |
| 2: hard-link no guard | 5 | `os.link` | 无 | `resolve()` | `OSError, JSONDecodeError` | `target` |
| 3: hard-link raw Path | 2 | `os.link` | 无 | 调用者预解析 | `OSError, JSONDecodeError` | `target` |
| 4: absolute+symlink guard+UnicodeError | 2 | `os.link` | 3x | `absolute()` | `OSError, UnicodeError, JSONDecodeError` | `target.resolve()` |
| 5: public atomic | 1 | `os.replace` | 1x (ValueError) | `expanduser()`+symlink check+`resolve()` | `OSError, JSONDecodeError` | `target` |

统一 `persist_immutable_atomic` 需至少 4 个 flags（`check_symlinks`、`path_resolution`、`catch_unicode_error`、`return_resolved`）——参数爆炸。13 个文件各自保留私有 `_persist_immutable` |

#### 1.6.6 Group C/D — Deferred（v4.1 扩充）

- **Group C**（不可安全抽取）:
  - `_validate_source`（8 文件，业务 schema 差异）
  - `_load_json_object`（10 文件，异常消息与业务上下文强绑定，且与 `research_template.py:3887` 同名不同返回类型 `tuple[Path, dict]` vs `dict`）
  - `_source_reference`（7 文件，与 `_validate_source` 耦合）
  - `_transaction_id`（5 文件，4 个行为家族：3 种 hash-material 算法各异的 SHA-256 hex 生成器 + 1 个输入校验器）——**v4.1 从 Group A 移入**。HEAD 81df373 无 public `transaction_id` helper，旧草稿中的已随 C5-CTRL-06 删除
  - `_snapshot_fingerprint`（5 文件，含业务 validator `validate_write_scene_model_routing_snapshot`，注入 `Callable[[JsonObject], None]` 需精确类型+pyright 可行性验证）——**v4.1 从 Group A 移入**
  - `_exact_fields` / `_validate_exact_fields`（15 文件，3 命名+4 错误格式=8 个 exact family，参数爆炸）——**v4.1 从 Group A 移入**
- **Group D**（异构变体，不统一）:
  - `_normalize_now` 三变体：变体 a `astimezone(UTC).replace(tzinfo=None)`（不去微秒，7 文件）、变体 b `replace(microsecond=0)`（去微秒不转 UTC，3 文件）、变体 c `astimezone(UTC).replace(microsecond=0, tzinfo=None)`（去微秒+转 UTC，1 文件）——语义意图不同，不统一
  - `_parse_utc` 两变体：变体 a `fromisoformat(text.replace("Z", "+00:00"))` 正确处理 offset（6 文件）、变体 b `fromisoformat(text).replace(tzinfo=UTC)` 对 offset 覆盖时区不调时间值（2 文件）——Slice 0 characterization 确认不等价
  - `_format_utc` auto 族（6 文件）：`isoformat()` 无 timespec，依赖 Python 版本 auto 语义，不等价于 microseconds/seconds——**v4.1 从 Group A 移入**
  - `_serialize` 缺 sort_keys（1 文件，`write_model_challenger_promotion.py:804`）：行为保持优先，不顺手修复——**v4.1 从 Group B 移入**
  - `_decode_base64` 族 B（1 文件，`manual_recovery.py:385`）：`"must be valid base64"` 错误文本 + 缺 TypeError 捕获——行为保持，不改为族 A——**v4.1 从 Group A 拆出**
  - `_persist_immutable`（13 文件，5 family）：os.link vs os.replace、symlink guard、absolute vs resolve、UnicodeError 捕获——参数爆炸，defer——**v4.1 从 Group B 移入**
  - `_required_text` 族 2-8（10 文件，7 种不同校验完整性）：NFKC/控制字符/空白处理/max_length 各有差异，不可统一——**v4.1 从 Group A 移入**
  - `_validated_absolute_path`（1 文件，`challenger_run_approval.py:375`）：不 expanduser、错误文本不同——**v4.1 新增**

#### 1.6.7 C5 `_write_artifact_utils.py` 最终 shared 函数清单（v4.2，17 函数）

> **v4.2**: 每个 shared helper 必须有实际 Slice 2 eligible caller（基于 HEAD 81df373 私有实现计数，不计算未跟踪 `_write_artifact_utils.py` 自身）。旧草稿中的 `transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、`persist_immutable_atomic`、`serialize_compact`、resolve 版 `is_relative_to` 全部删除。

| # | 函数 | 类别 | 签名 | Slice 2 caller 文件数 | 备注 |
|---|---|---|---|---|---|
| 1 | `canonical_json_str` | canonical | `(value: ModelConfigJsonValue) -> str` | **11** | str 系 `_canonical_json` 直接定义数（`health.py` 使用内联 `json.dumps`，不计入 `canonical_json_str` 直接 caller；仅计入 `fingerprint_str`） |
| 2 | `canonical_json_bytes` | canonical | `(payload: JsonObject) -> bytes` | 6 | bytes 系 _canonical_json |
| 3 | `fingerprint_str` | fingerprint | `(value: ModelConfigJsonValue) -> str` | **12** | canonical str → .encode("utf-8") → sha256（v4.2: 含 incident_dossier/incident_dossier_revalidation/gate_revalidation） |
| 4 | `fingerprint_bytes` | fingerprint | `(payload: JsonObject) -> str` | **5** | canonical bytes → sha256 直接（v4.2: 仅 _canonical_json 返回 bytes 的 5 文件） |
| 5 | `file_fingerprint` | fingerprint | `(path: Path) -> str` | 10 | 3 种循环写法等价 |
| 6 | `bytes_fingerprint` | fingerprint | `(value: bytes) -> str` | 10 | 完全等价 |
| 7 | `validated_fingerprint` | validation | `(value: ModelConfigJsonValue, *, name: str, error_label: str = "must be a sha256 fingerprint") -> str` | **7** | **仅族 A（6）+ 族 G（1）**。`str(value or "").strip().lower()` 策略。族 B-F（9 文件）全部保留私有，不得经预处理后调用 shared（C5-CTRL-01） |
| 8 | `require_mapping` | validation | `(value: ModelConfigJsonValue \| JsonObject, *, name: str) -> JsonObject` | 14 | 严格版，**identity-return**（`return value`）。12 个 identity-return 文件直接迁移；copy 族 2 文件（`incident_dossier_revalidation`、`gate_revalidation`）使用 call-site adapter `dict(require_mapping(value, name=...))`（v4.4 C5-CTRL-10-ERRATUM） |
| 9 | `optional_mapping` | validation | `(value: ModelConfigJsonValue) -> JsonObject` | 3 | 静默版 |
| 10 | `require_text` | validation | `(value: ModelConfigJsonValue, *, name: str, maximum_length: int) -> str` | **6** | 仅族 1（NFKC+ord<32+必需max_length）私有 eligible caller。不含未跟踪 public helper |
| 11 | `format_utc` | time | `(value: datetime) -> str` | **3** | microseconds 族：`configuration_application`、`rollback_application`、`manual_recovery` |
| 12 | `format_utc_seconds` | time | `(value: datetime) -> str` | 2 | seconds 族：先检查 `value.tzinfo is None or value.utcoffset() is None`，naive → ValueError("now must include a timezone")，再 astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")。不依赖 Group D（C5-CTRL-05/SA-REVIEW-04） |
| 13 | `is_subpath` | path | `(path: Path, root: Path) -> bool` | 8 | `try: path.relative_to(root) except ValueError: return False; return True`。不 resolve |
| 14 | `absolute_path` | path | `(text: str, *, name: str) -> Path` | 7 | `text: str` 入参（C5-CTRL-02）。`Path(text).expanduser()` → `is_absolute()` → `resolve()`。text 校验由调用方各自 `_required_text` 处理 |
| 15 | `serialize_pretty` | serialize | `(payload: JsonObject) -> str` | 13 | `sort_keys=True, indent=2 + "\n"`。不含缺 sort_keys 的 1 文件 |
| 16 | `decode_base64` | codec | `(text: str, *, name: str) -> bytes` | **5**（4 私有 + 1 inline） | `text: str` 入参（C5-CTRL-03）。族 A：标准 `b64decode(validate=True)`，错误文本 `"is invalid"`。无 urlsafe 参数 |
| 17 | `decode_base64_strict` | codec | `(text: str, *, name: str) -> bytes` | 1 | `text: str` 入参（C5-CTRL-03）。族 B：标准 `b64decode(validate=True)`，错误文本 `"must be valid base64"`，缺 TypeError 捕获 |

**Eligible callers 合计**: 19 个 `write_model_*.py` 中对应的全部 17 个 shared 函数（每函数有明确文件映射，无未使用 helper）。**Deferred variants**（不迁移，保留原位）: 见 §1.6.6 Group C/D 完整列表。

**从旧草稿删除的函数（6 个，不进入 v4.2 清单）**: `transaction_id`、`snapshot_fingerprint`、`require_exact_fields`、`persist_immutable_atomic`、`serialize_compact`、resolve 版 `is_relative_to`（替换为 `is_subpath`）。

### 1.7 W12/W15/W16

- **W12（v4.9 S6-W12-CYCLE-01）**: `_snapshot_builder` 嵌套函数 5 处（源码行号仅作历史辅助，以包围函数为结构锚点）。全部零参数闭包包裹 `_build_fresh_application_routing_snapshot`，但迁移方式必须按依赖方向分流：闭包 #1 位于 `_run_write_model_configuration_application`，随 runner 迁入 `_write_config_application.py` 后使用同模块 `functools.partial`，精确绑定 `args`、`paths_config`、`execution_options` 且不显式绑定 `run_label`，沿用函数默认值；闭包 #2/#3 在 Slice 6 的 `write.py` 中使用 `build_snapshot_builder` 默认 label；闭包 #4/#5 分别显式使用 `configuration-manual-recovery-verification` 与 `configuration-manual-recovery-clearance`。禁止 `_write_config_application.py` import `_write_snapshot_builder.py`；后续 Slice 7/8 随各 runner 迁移其 factory call 与 import
- **W15**: `write_model_challenger_proposal.py:385`，`finish()` 闭包捕获 5 变量，5 提前返回点调用。方案：直接内联 `_finalize_payload(...)` 调用，删除嵌套定义
- **W16（v4.5 W16-CTRL-01）**: `research_workbook.py:50` 的 `append_current_section` 闭包捕获 4 个局部状态。模块内新增三个私有 TypedDict：`_ResearchWorkbookEvidence`（`source: str`, `reference: str`, `finding: str`）、`_ResearchWorkbookItem`（`item_id: str`, `prompt: str`, `status: str`, `response: str`, `evidence: list[_ResearchWorkbookEvidence]`, `analyst_notes: str`, `evidence_required: bool`）、`_ResearchWorkbookSection`（`section_id: str`, `title: str`, `category: str`, `items: list[_ResearchWorkbookItem]`）；提取 exact helper `_append_research_workbook_section(sections: list[_ResearchWorkbookSection], *, normalized: str, current_title: str, current_category: str, current_items: list[str]) -> None`。同步精化局部 `sections: list[_ResearchWorkbookSection]` 与 `items: list[_ResearchWorkbookItem]`，替换 heading 切换 flush 与 EOF flush 两个调用点。public builder 的存量 `dict[str, object]` 返回契约保持不变；本模块 15 个存量函数签名共含 19 处 `dict[str, object]`（含 public builder 与 2 个私有 helper），均不在 W16 scope；禁止新增 `Any`/`object`/`cast`/`type: ignore`/glue wrapper。验证：`pytest -k "research_workbook"` + `pyright`

### 1.8 monkeypatch 契约

`test_cli_running_config.py:9310`: `monkeypatch.setattr("dayu.cli.commands.write.WriteService.print_report", ...)`。`WriteService` 在 `write.py:182` 顶层 import，不受 Slice 8 迁移影响。Slice 0 characterization 显式锁定此契约。

**S5-CTRL-02**: Slice 5 后 `_resolve_write_model_override_name` 的
`setup_model_name` 全局绑定位于 `_write_config_helpers.py`。因此
`tests/engine/test_cli_running_config.py` 中精确 13 处
`dayu.cli.commands.write.setup_model_name` monkeypatch 必须全部迁为
`dayu.cli.commands._write_config_helpers.setup_model_name`；旧 patch 目标
最终为 0，新目标为 13。`write.py` 删除 `setup_model_name` import，禁止为旧
测试路径新增 compatibility re-export、wrapper 或同步 seam。该测试文件若
直接测试 `setup_model_name`，应从功能真源 `dayu.cli.dependency_setup`
import，不通过 `write.py`。

Slice 5 的两个新模块仍各定义 exact 4 个函数、合计 exact 8 个迁移定义；
`write.py` 只正常顶层 import/rebind 下列 6 个真正功能 private symbol，作为
`run_write_command` 的真实全局依赖：
`_resolve_write_model_override_name`、`_resolve_write_company_name`、
`_build_write_run_config`、`_log_write_preflight_result`、
`_challenger_requested`、`_validate_research_materialization_args`。
`MODULE` 由 `write.py` 另行正常 import，但不计入 private function 数。
这 6 个 functional binding 的
`dayu.cli.commands.write.<private>` direct import/monkeypatch 路径和
`run_write_command` global lookup 行为保持不变；包括
`tests/application/test_write_challenger.py` 从 `write.py` direct import
`_validate_research_materialization_args`。

`write.py` 删除且禁止对 `_validate_challenger_run_plan_args` 与
`_validate_live_smoke_plan_args` 建立 compatibility re-export。engine test
对 `_validate_live_smoke_plan_args` 的 direct import 必须迁到真实 owner
`dayu.cli.commands._write_params_validation`；
`_validate_challenger_run_plan_args` 没有旧 direct test，只在新 owner 模块
保留定义。dispatch import identity 仅锁定上述 6 个 functional binding。

**`_challenger_requested` 双 owner 语义（首轮 re-review clarification）**:

- `dayu.cli.commands.write._challenger_requested` 是
  `run_write_command` 内 3 个 global call site 的正确 monkeypatch owner；
  patch 该绑定必须控制真实 `run_write_command` 路径。
- `dayu.cli.commands._write_params_validation._challenger_requested` 是真实
  `_validate_research_materialization_args` 函数内部调用的正确 monkeypatch
  owner；patch 该绑定必须控制 validator 内部路径。
- 禁止把所有旧 `write._challenger_requested` patch blanket 迁到 params。
  monkeypatch 必须按被测 call site 的函数 globals 选择 owner。
- `tests/engine/test_cli_running_config.py` 当前约 line 5934 同时 patch
  `write._validate_research_materialization_args` 与
  `write._challenger_requested`，服务于 `run_write_command` 路径，保持不变。

---

## 2. 目标模块边界与依赖方向

### 2.1 目标文件结构

```
dayu/cli/
├── arguments.py                          # Slice 10：ResearchTemplateDispatchArguments(Protocol)
│                                         #   + DayuCliArguments(argparse.Namespace)，显式 research 字段
│                                         # Slice 11：WriteDispatchArguments(Protocol)
│                                         #   + Dayu 原子追加 exact20 write 字段（终态 exact21）
│                                         #   零 import dayu.cli 模块（import-neutral）
├── arg_parsing.py                        # parse_arguments() → DayuCliArguments
├── main.py
├── commands/
│   ├── write.py                          # run_write_command(args: DayuCliArguments) -> int
│   │                                     #   + 2 phase 表 + 16 adapter 命名函数
│   ├── _write_dispatch.py                # _WriteCommandContext + _WriteConfigurationContext
│   │                                     #   + _EarlyWriteSubcommandEntry + _ConfigurationWriteSubcommandEntry
│   ├── _write_config_helpers.py          # MODULE 单一真源 + _resolve_write_model_override_name,
│   │                                     #   _resolve_write_company_name, _build_write_run_config,
│   │                                     #   _log_write_preflight_result
│   ├── _write_execution.py               # _run_write_stage, _run_write_preflight
│   ├── _write_challenger.py              # Slice 8 exact 13 函数（v4.6）
│   ├── _write_config_application.py      # _build_fresh_application_routing_snapshot
│   │                                     #   + _run_write_model_configuration_application
│   ├── _write_config_rollback.py         # _run_write_model_configuration_rollback
│   ├── _write_manual_recovery.py         # exact 14 manual recovery runners
│   │                                     #   + Phase C gate check（exact 15 definitions）
│   ├── _write_params_validation.py       # _challenger_requested + 3 validators（exact 4）
│   ├── _write_snapshot_builder.py        # → _write_config_application（正向，非反向）
│   ├── research_template.py              # aggregate terminal FunctionDef exact41：entry1 + selector1 + runners39；ClassDef0
│   ├── _research_template_core.py        # exact26 functions
│   ├── _research_template_bundle.py      # exact12 functions
│   ├── _research_template_monitoring.py  # exact11 functions
│   ├── _research_template_materialize.py # exact12 functions
│   ├── _research_template_helpers.py     # exact22 functions + 2 dataclasses + 7 constants；叶子
│   └── research_workbook.py              # _append_research_workbook_section 模块级（W16 后）

dayu/services/
├── write_service.py                      # WriteService 类 + print_report 编排（~500 行）
├── _write_report.py                      # print_report 8 个子流程模块级函数
├── _write_artifact_utils.py              # 17 共享函数（v4.1），零 object/Any/Callable[...]
├── write_model_*.py                      # 19 个业务模块（迁移后 eligible helper 零重复）
```

### 2.2 依赖方向

```
main.py → arg_parsing.py → arguments.py（Slice 10 起）
main.py → write.py → arguments.py（Slice 10 起）, _write_dispatch.py（Slice 11 起）
main.py → research_template.py → arguments.py（Slice 10 起）

write.py → _write_dispatch.py → arguments.py（只 import 类型，零 import dayu.cli 其他模块）
write.py → _write_config_helpers / _write_execution / _write_challenger /
           _write_config_application / _write_config_rollback /
           _write_manual_recovery / _write_params_validation /
           _write_snapshot_builder → _write_config_application

_write_config_application / _write_execution / _write_manual_recovery /
_write_challenger / _write_config_rollback → _write_config_helpers（MODULE 真源）

_write_manual_recovery → _write_snapshot_builder → _write_config_application
（仅此单向 CLI 内部依赖；零 reverse import / cycle）

research_template.py → _research_template_helpers / _research_template_core /
                         _research_template_bundle / _research_template_monitoring /
                         _research_template_materialize

_research_template_core → _research_template_helpers
_research_template_bundle → _research_template_core + _research_template_helpers
_research_template_monitoring → _research_template_bundle +
                                _research_template_core +
                                _research_template_helpers
_research_template_materialize → _research_template_monitoring +
                                 _research_template_bundle +
                                 _research_template_core +
                                 _research_template_helpers

_wr..._artifact_utils（零入度叶子）
_wr..._report → _wr..._artifact_utils
write_model_*.py → _wr..._artifact_utils
```

**依赖方向证明**:
- `_write_params_validation.py` 内部定义 `_challenger_requested` 并由
  `_validate_research_materialization_args` 直接调用；禁止 import
  `write.py` 或 Slice 5 尚不存在的 `_write_challenger.py`，因此 Slice 5
  独立 commit 无循环
- `_write_config_helpers.py` 从 `dayu.cli.dependency_setup` 功能性 import
  `setup_model_name`，并单一定义 `MODULE`；`write.py` 和后续目标模块只向该
  叶子依赖，不存在反向路径
- `_write_snapshot_builder.py` → `_write_config_application.py`：两者在 Slice 6 同一 commit 创建，前者从后者顶层 import，且 application 模块禁止反向 import builder。`_run_write_model_configuration_application` 在 application 模块内以精确一次 `functools.partial(_build_fresh_application_routing_snapshot, args=args, paths_config=paths_config, execution_options=execution_options)` 构造闭包 #1 callback，不显式绑定 `run_label`；闭包 #2–#5 由 `write.py` 向 builder 的单向 factory 调用处理，因而无循环路径
- snapshot chain 的三个下层 helper（`_build_fresh_application_routing_snapshot`、
  `_build_snapshot_for_args`、`build_snapshot_builder`）只透传 `args` 或交给同样接收
  `argparse.Namespace` 的 `setup_write_config`，不读取 Dayu 专有 selector 字段。因此它们
  保持宽 `argparse.Namespace`；config application CLI runner 接收
  `DayuCliArguments` 并可按 IS-A 关系安全传给宽 helper。此边界阻止
  research/write dispatch concrete type 沿偶然 callback call chain 污染 rollback/manual
  recovery 基础设施
- Slice 0–9 的 CLI args 真源仍是 `argparse.Namespace`。Slice 10 原子创建
  `arguments.py`，先声明 consumer 最小 Protocol，再声明带显式 research selector
  字段的 producer `DayuCliArguments`；`arg_parsing.py` 让 `parse_arguments()` 返回
  真实子类实例。write/research-template 只在同一 Slice 10 commit 完成签名传播后
  import 该类型。Slice 11 新增 Write Protocol 并向既有 Dayu 类原子追加 exact20
  同名同类型字段，不重复创建该类。Dayu 始终只继承 `argparse.Namespace`，通过
  structural subtyping 满足两个 Protocol，避免 Protocol data attributes 导致
  `DayuCliArguments()` 的 `reportAbstractUsage`
- `_write_artifact_utils.py`：零入度叶子（不 import 任何 `write_model_*.py`）
- `_research_template_helpers.py`：零内部 project-domain dependency 的叶子；拥有
  exact 22 functions、2 dataclasses 与 7 constants。其余四个 owner 只能按上述
  DAG 向下依赖，五个新模块均禁止 import `research_template.py`
- `arguments.py`：仅定义数据类型，零 import `dayu.cli` 模块

---

## 3. 非目标（Explicit Non-Goals）

| 项 | 原因 |
|---|---|
| C6/C7/C9（`async_anthropic_runner.py`/`protocols.py` 类型安全） | 非 CLI write scope，属 engine/services 层治理 |
| W14（`WriteCliConfig` 字段拆分） | 20 字段在当前上下文中可接受 |
| W21/W22（根目录文档整理） | 文档工程治理，非架构重构 scope |
| W23（中英文警告混用） | 纯文本统一，无架构影响 |
| W27（测试文件过大拆分） | 测试工程治理 |
| W28（`_FakeClock` 重复提取） | 测试工程治理 |
| W29（跨进程测试超时） | 测试工程治理 |
| C5 Group C（`_validate_source`、`_load_json_object`、`_source_reference`） | 业务 schema 差异导致不可安全抽取，后续独立 plan 治理 |
| C5 Group D（`_normalize_now` 三变体、`_parse_utc` 两变体） | 语义意图不同 / offset 输入不等价，后续按功能域统一治理 |
| Phase G Path 重复模式（V4-07 REJECTED） | HEAD 现状忠实反映。可选 `_resolve_optional_path` helper 抽取不在本 task scope |
| Slice 6 提前创建 `arguments.py`（方案 B） | 会把 CLI 类型系统拆成 partial-definition 中间态并扩大 C1+W12 scope；类型所有权统一归 Slice 10 |
| `DayuCliArguments` type alias、cast、forward ref 或 glue（方案 C） | 无运行时类型身份，且违反零 cast/零兼容 glue 约束；Slice 10 必须构造真实 `argparse.Namespace` 子类实例 |
| `DayuCliArguments` 多继承一个或多个 Protocol | REJECTED：isolated full instantiation pyright 对 `DayuCliArguments()` 报 `reportAbstractUsage`；runtime/MRO 可工作不足以关闭静态实例化门禁。采用显式字段 + structural subtyping |
| Slice 10 方案 A：将 rollback + 3 manual runner 收窄并把传播扩大到 exact49 | REJECTED：四个 runner 仅因偶然调用 snapshot factory 被污染，实际不需要 Dayu 专有字段；破坏同域 runner 一致性并扩大 fixtures/scope |
| Slice 10 方案 C：将 rollback + 全部 15 manual functions 收窄 | REJECTED：把具体 CLI dispatch 类型扩散到不使用相关字段的下层函数，违反最小契约与分层边界 |

---

## 4. 不变量（Invariants）

### 4.1 Public API 不变量

| 不变量 | 验证 |
|---|---|
| Slice 10 前 `run_write_command(args: argparse.Namespace) -> int`；Slice 10 起 `run_write_command(args: DayuCliArguments) -> int` | 各 Slice pyright + `main.py:73` 编译通过 |
| Slice 10 前 `run_research_template_command(args: argparse.Namespace) -> int`；Slice 10 起 `run_research_template_command(args: DayuCliArguments) -> int` | 各 Slice pyright + `main.py` research-template 路径编译通过 |
| `WriteService.print_report(output_dir, *, model_catalog, ...)` — 15 total（output_dir + 14 keyword）全部保持 | pyright + 1947 行测试通过 |
| Slice 10 前 `parse_arguments() -> argparse.Namespace`；Slice 10 起 `parse_arguments() -> DayuCliArguments` 且返回真实子类实例 | pyright + runtime `isinstance` + `main.py` |
| 所有 `dayu.services.write_model_*` 模块 public 导出符号不变 | 各模块测试 |

### 4.2 行为不变量

| 不变量 | 验证 |
|---|---|
| write 退出码不变（0/2/4/6/130） | CLI 集成测试 |
| `run_research_template_command` 退出码不变（含未知 action 与 caught exception 返回 1） | CLI 集成测试 |
| `print_report` 副作用顺序不变（步骤 1 先于步骤 3） | test_write_service.py 全量 |
| argparse 参数名不变（`arg_parsing.py` 中 `add_argument` 调用不改） | grep diff |
| 错误消息文本不变（含异常文本） | Slice 0 characterization |
| 文件格式不变（JSON schema、指纹 `sha256:` + 64 hex、canonical JSON 字节级） | Slice 0 characterization |

**S10-CTRL-03 dispatch/error 不变量**：Slice 10 只把 research-template
if-chain 换成 mapping，不改变入口行为。`setup_loglevel(args)` 仍先执行；未知 action
不产生 stdout/stderr 并返回 `1`；runner 抛出的 `FileNotFoundError`、
`FileExistsError` 或 `ValueError` 仍打印精确
`research-template error: {exc}` 到 stderr 并返回 `1`。入口禁止引入 `Log`、
`MODULE`、新错误文本或 `return 2`。

### 4.3 类型不变量 —— 规则与有界例外

1. **零 `Any`** —— 参数和返回值精确类型注解
2. **零裸 `object`** —— 使用 `ModelConfigJsonValue` 或精确 TypedDict/Protocol。**三个有界存量例外**: (a) `WriteService.print_report` 的 `model_catalog: Mapping[str, Mapping[str, object]]` 是 HEAD 5821014 现存的公开 API 签名，保留不改；(b) 该值由 `config_loader.load_llm_models()` 返回，传播至 `print_write_report`（HEAD 现存 API，同签名）、`_print_repriced_comparison`、`_handle_health_trend_and_proposal_and_preflight`。在 Python 类型系统内无法不经 `cast`/`type: ignore` 收窄为 `Mapping[str, Mapping[str, ModelConfigJsonValue]]`。`_write_report.py` 的其余 6 个 helper（`_validate_*`、`_handle_promotion_*`、`_handle_config_change_*`）不接收 `model_catalog`，零 `object` 类型（V4-06: 传播链补充 `print_write_report`）；(c) Slice 9 的 `_DATA_SOURCE_BINDING_CANDIDATES` 是 HEAD `1d0f9e6` 已存在的数据常量类型，纯 owner migration 时 semantic occurrence 1→1，不新增函数签名、传播或逃逸，后续精确类型治理不属于本 Slice
3. **零新增无界 `getattr`** —— 原则上使用直接属性访问或 Protocol predicate；
   Slice 10 selector 唯一有界例外精确为
   `str(getattr(args, "research_template_action", "") or "").strip().lower()`，只为
   保留 HEAD 对缺字段、`None` 与非字符串值的 defensive 语义。Protocol 仍提供静态
   类型边界；39 runners 内部的存量表外 `getattr` 不在 Slice 10 迁移范围
4. **零 `hasattr`** —— `isinstance` + 精确类型收窄
5. **零 `type: ignore`** —— 不压制类型错误
6. **零 `Callable[..., ...]`（Ellipsis）** —— `Callable[[DayuCliArguments], int]` 等精确签名
7. **零无类型签名** —— 每参数和返回值显式注解
8. **零兼容性 re-export / wrapper**
9. **Protocol/producer 字段闭合** —— Slice 10 `ResearchTemplateDispatchArguments`
   与 Dayu 各 exact1 字段；Slice 11 `WriteDispatchArguments` exact20，Dayu 终态
   exact21。两个 Protocol 字段并集与 Dayu 字段集合精确相等，零 extra；Dayu 不继承
   Protocol、不声明默认值或 `__init__`。表外 argparse 字段保持动态，不扩成 god bag
10. **Dayu 传播止于真实 consumer** —— dispatch entry、39 research runners 与 config
    application runner 使用 `DayuCliArguments`；snapshot chain、rollback runner 与 15 个
    manual recovery functions 保持 `argparse.Namespace`。宽 helper 可接收 Dayu 子类；
    禁止因偶然 call chain 反向扩大 concrete-type dependency

---

## 5. 原子 Slice 序列（0..13，15 个，每个恰好一个 accepted commit）

```
Slice 0:  Characterization tests + 集成矩阵
Slice 1:  C5 — _write_artifact_utils.py（重构/替换为 17 函数）+ 聚焦 + 差分 characterization 测试
Slice 2A: C5 — canonical/fingerprint/mapping/serialize 族迁移（~10 文件）
Slice 2B: C5 — path/time/codec/validation/剩余 fingerprint 族迁移（~9 文件）
Slice 3:  W15 — finish() 内联消除
Slice 4:  W16 — append_current_section 提取
Slice 5:  C1 — _write_config_helpers + _write_params_validation
Slice 6:  C1+W12 — _write_config_application + _write_snapshot_builder + ExecutionOptions
Slice 7:  C1 — _write_execution + _write_manual_recovery
Slice 8:  C1 — _write_challenger + _write_config_rollback + write.py 清理
Slice 9:  C2 — research_template.py 5 私有模块（单 commit）
Slice 10: C2 — Protocol dispatch + arguments.py runtime type ownership/传播
Slice 11: C3 — Phase-aware Protocol dispatch（phase-specific contexts + 16 adapter）
Slice 12: C4 — print_report 拆分
Slice 13: README/docs + 最终门禁
```

### Slice 0: HEAD if-chain Characterization（C4-01 修正）

**原则**: Slice 0 仅提交对 HEAD 5821014 现有 if-chain 的可运行 characterization。**不引用** Slice 10 才引入的 `DayuCliArguments` 与 dispatch mapping，也不引用 Slice 11 才引入的 adapter 与 phase table。每个测试的 patch 目标为当前 `write.py` / `research_template.py` 中实际存在的函数（V4-05: Slice 7 迁移后需同步更新 patch 路径）。

**新建文件**: `tests/application/test_write_cli_dispatch.py`、`tests/application/test_write_service.py`（追加测试）

**A–H 测试矩阵**（25 项）:

A. `_canonical_json` str 变体（seam: `write_model_challenger_proposal._canonical_json`）: null/empty_dict/sort_keys/nan_raises
B. `_canonical_json` bytes 变体（seam: `write_model_configuration_application._canonical_json`）: empty/nested/proxy
C. `_validated_fingerprint` 6 sub-family 行为矩阵: 族 A `str(value or "").strip()` / 族 B `_required_text(max_len=80)` / 族 C `"must use sha256"`+`"is invalid"` / 族 D `"must be a SHA-256 fingerprint"`(max_len=128) / 族 E `"is not a SHA-256 fingerprint"` / 族 F regex+max_len=71。锁定 shared `validated_fingerprint` 仅替代族 A/G（7 文件），其余 defer
D. `_parse_utc` offset 差异（锁定 defer）
E. `print_report` 副作用顺序: step1_before_step3 + full_order
F. CLI 混合 flag 优先级矩阵: revalidate_before_inspect / path_arg_over_bool / summary_fallback / default_execution
G. monkeypatch 路径契约: `test_write_service_top_level_import_in_write_py_is_stable`
H. 惰性计算 / 阶段顺序: early_recovery_does_not_call_resolve_model_override / clear_verify_recover_call_build_execution_options_inline / evidence_plan_approval_do_not_call_build_execution_options / apply_rollback_use_precomputed_execution_options / recovery_gate_after_config_before_challenger / summary_path_does_not_resolve_non_summary_paths

**I. HEAD if-chain 集成表征矩阵**（通过 monkeypatch call trace 断言，不复制实现。16 selectors = 11 Phase A bool + 3 Phase A path + 2 Phase B bool。V4-03: 三组参数化完整覆盖）:

**I-a. write if-chain characterization**（patch 目标为 HEAD `write.py` 中的 `_run_write_model_configuration_*` 函数）:

**Group 1 — Phase A boolean selectors（11 个）**: `test_write_ifchain_phase_a_boolean[selector_field,current_runner]` 参数化。Slice 0 只表征当时 HEAD，因此对每个 bool flag 构造 `argparse.Namespace`，触发 `run_write_command`，monkeypatch 断言对应 HEAD runner 被调用、其余不被调用；不得引用 Slice 10 才创建的 `DayuCliArguments`。selector fields: `revalidate_write_model_configuration_manual_recovery_incident_dossier`, `inspect_write_model_configuration_manual_recovery_incident`, `audit_write_model_configuration_manual_recovery_history`, `revalidate_write_model_configuration_manual_recovery_gate_verification`, `verify_write_model_configuration_manual_recovery_gate`, `check_write_model_configuration_manual_recovery_gate`, `revoke_write_model_configuration_manual_recovery_clearance`, `restart_write_model_configuration_manual_recovery_after_clearance_revocation`, `clear_write_model_configuration_manual_recovery`, `verify_write_model_configuration_manual_recovery`, `recover_write_model_configuration`。**惰性 build 断言**: clear/verify/recover 三个 flag 额外断言 `_build_execution_options` call trace = 1（adapter 内部惰性调用）；其余 8 个 flag 断言 call trace = 0。patch 目标 `dayu.cli.commands.write._run_*`。

**Group 2 — Phase A path-valued selectors（3 个）**: `test_write_ifchain_phase_a_path[selector_field,current_runner]` 参数化。每个 path flag 两个 sub-case：(a) nonempty 值 → runner 被调用；(b) empty/None → runner 不被调用。全部 3 个 path flag 断言 `_build_execution_options` call trace = 0（path adapter 不 build）。selector fields: `challenger_config_manual_recovery_receipt_input`, `challenger_config_manual_recovery_plan_output`, `challenger_config_manual_recovery_approval_output`。patch 目标 `dayu.cli.commands.write._run_*`。

**Group 3 — Phase B boolean selectors（2 个）**: `test_write_ifchain_phase_b[selector_field,current_runner]` 参数化。对 `apply_write_model_configuration` 和 `rollback_write_model_configuration` 分别断言正确 runner 被调用，且 `_build_execution_options` call trace = 1（在 `run_write_command` 中预计算一次，adapter 不重算）。patch 目标 `dayu.cli.commands.write._run_*`。

**Mixed priority 独立保留**: `test_write_ifchain_mixed_priority` — summary=True + apply=True → apply runner call trace = 1, summary runner call trace = 0。

**I-b. research-template if-chain characterization**（patch 目标为 HEAD `research_template.py` 中的 `_run_*` 函数）: **39** action key × 参数化测试，验证 `research_template_action` 与 parser subcommand 一一对应。**Slice 10 迁移后测试更新为验证 dispatch mapping 条目完整性**。

验证: `pytest tests/application/test_write_cli_dispatch.py tests/application/test_write_service.py -v`。

---

### Slice 1: C5 — `_write_artifact_utils.py` 重构/替换（17 函数）+ 聚焦 + 差分 characterization 测试

**操作模式**: 重构/替换（非新建）。当前 worktree 中存在未跟踪旧草稿 `_write_artifact_utils.py`（623 行，20 函数），基于旧 v4.0 spec，与 v4.2 spec 存在 6 处实质性行为不等价。Slice 1 将其完全替换为符合 v4.2 spec 的实现。若文件不存在则创建。

**逐函数操作清单**:

*删除（6 个，旧草稿中存在但 v4.2 spec 不需要）*:
- `is_relative_to`（resolve 版）→ 替换为 `is_subpath`
- `transaction_id` → defer（语义异构，§1.6.6 Group C）
- `snapshot_fingerprint` → defer（含业务 validator，§1.6.6 Group C）
- `require_exact_fields` → defer（8 exact family，§1.6.6 Group C）
- `persist_immutable_atomic` → defer（5 family，§1.6.6 Group D）
- `serialize_compact` → 删除（零 eligible caller）

*新增（3 个，v4.1 spec 要求但旧草稿中不存在。20 − 6 删除 + 3 新增 = 17 最终）*:
- `is_subpath(path: Path, root: Path) -> bool` — try/except 非 resolve 模式
- `format_utc_seconds(value: datetime) -> str` — seconds 族，含 tz-aware + utcoffset 前检查
- `decode_base64_strict(text: str, *, name: str) -> bytes` — 族 B 错误文本，缺 TypeError 捕获

*修正（3 个，旧草稿中存在但签名/行为需修改）*:
- `decode_base64` — 删除 `urlsafe` 参数，签名改为 `(text: str, *, name: str) -> bytes`
- `absolute_path` — 签名改为 `(text: str, *, name: str) -> Path`（C5-CTRL-02）
- `format_utc` — microseconds 族，caller 数 3

*保留不变（11 个，旧草稿中实现已符合 v4.2 spec）*:
- `canonical_json_str`、`canonical_json_bytes`、`fingerprint_str`、`fingerprint_bytes`、`file_fingerprint`、`bytes_fingerprint`、`validated_fingerprint`、`require_mapping`、`optional_mapping`、`require_text`、`serialize_pretty`

**迁移前自检 checklist**:
- [ ] 旧草稿 20 函数逐一核对：6 删、3 修正、11 保留；再新增 3（`is_subpath`、`format_utc_seconds`、`decode_base64_strict`），最终 17 函数
- [ ] 旧草稿 `__all__` 与 17 函数清单一致
- [ ] 旧草稿 `decode_base64` 的 `urlsafe` 参数/分支完全删除（零 caller）
- [ ] 旧草稿 resolve 版 `is_relative_to` 完全替换为 `is_subpath`
- [ ] 旧草稿 `absolute_path` 签名从 `ModelConfigJsonValue` 改为 `text: str`

**类型基础**:
```python
from collections.abc import Mapping
from datetime import datetime, UTC
from pathlib import Path
from typing import TypeAlias
from dayu.contracts.model_config import ModelConfigJsonValue

JsonObject: TypeAlias = Mapping[str, ModelConfigJsonValue]
```

**17 个函数完整签名**（同 §1.6.7 v4.2 清单，每个函数包含完整中文 docstring 含参数/返回值/异常）:

1. `canonical_json_str(value: ModelConfigJsonValue) -> str`
2. `canonical_json_bytes(payload: JsonObject) -> bytes`
3. `fingerprint_str(value: ModelConfigJsonValue) -> str`
4. `fingerprint_bytes(payload: JsonObject) -> str`
5. `file_fingerprint(path: Path) -> str`
6. `bytes_fingerprint(value: bytes) -> str`
7. `validated_fingerprint(value: ModelConfigJsonValue, *, name: str, error_label: str = "must be a sha256 fingerprint") -> str`
8. `require_mapping(value: ModelConfigJsonValue | JsonObject, *, name: str) -> JsonObject`
9. `optional_mapping(value: ModelConfigJsonValue) -> JsonObject`
10. `require_text(value: ModelConfigJsonValue, *, name: str, maximum_length: int) -> str`
11. `format_utc(value: datetime) -> str`
12. `format_utc_seconds(value: datetime) -> str`
13. `is_subpath(path: Path, root: Path) -> bool`
14. `absolute_path(text: str, *, name: str) -> Path`
15. `serialize_pretty(payload: JsonObject) -> str`
16. `decode_base64(text: str, *, name: str) -> bytes`
17. `decode_base64_strict(text: str, *, name: str) -> bytes`

**聚焦测试 + 差分 characterization / 固定反例 corpus**（→ `tests/application/test_write_artifact_utils.py`，本 slice commit 含。C5-CTRL-07）:

*聚焦测试*:
- 族 1 `require_text` vs 族 2-8 的独立 characterization（`test_require_text_family_1_behavior`），确保 shared 版本不意外改变 defer 族行为
- `format_utc` vs `format_utc_seconds` 精度差异 characterization（`test_format_utc_microseconds_vs_seconds_precision`）
- `is_subpath` 非 resolve 行为 characterization（`test_is_subpath_does_not_resolve_symlinks`）

*差分 characterization / 固定反例 corpus（C5-CTRL-07）*:
- `test_validated_fingerprint_case_sensitivity` — 大小写 fingerprint 反例（`SHA256:` vs `sha256:`），验证 shared 的 `lower()` 行为
- `test_validated_fingerprint_error_text_variants` — 验证各族错误文本差异：`"must be a sha256 fingerprint"`（A/B）、`"must use sha256"`（C）、`"is invalid"`（C 第二文本）、`"must be a SHA-256 fingerprint"`（D）、`"is not a SHA-256 fingerprint"`（E/F）
- `test_format_utc_seconds_naive_raises` — naive datetime（`tzinfo is None or utcoffset() is None`）必须抛 `ValueError("now must include a timezone")`
- `test_absolute_path_relative_raises` — relative path → `ValueError`
- `test_decode_base64_standard_vs_urlsafe_rejection` — 标准 b64decode vs urlsafe 差异，锁定 shared 接受标准、拒绝 urlsafe 填充变体
- `test_decode_base64_error_text_families` — `"is invalid"` vs `"must be valid base64"`
- `test_require_mapping_identity_vs_copy` — 使用自定义 `dict` 子类（零 `Any`/`object`/`cast`/`type: ignore`）验证：identity 族 `require_mapping(value) is value`（同一对象）；copy 族 adapter `dict(require_mapping(value)) is not value` 且 `== value`（值相等）；str+dict canonical `canonical_json_str(dict(value))` 与旧 `_canonical_json`（内调 `json.dumps(dict(value))`）输出完全一致；`fingerprint_str(dict(value))` 与旧 `_fingerprint`（内调 `_canonical_json(dict(value)).encode(...)`）输出完全一致
- `test_require_mapping_non_dict_mapping_identity` — 使用 `MappingProxyType` 构造精确 `Mapping[str, ModelConfigJsonValue]` 非 `dict` 映射（零 `Any`/`object`/`cast`/`type: ignore`）验证：`require_mapping(value) is value`（identity-return 对任意 Mapping 成立）
> **v4.4 类型验证**: 不新增运行时测试。直接 `pyright dayu/services/` 验证 `write_model_configuration_rollback.py` 5 个 public validator（`:840` `:1225` `:1316` `:1498` `:1831`）的 `Mapping[str, Any]` payload 经扩宽类型 `ModelConfigJsonValue | JsonObject` 的 `JsonObject` 协变分支通过，零 errors。Slice 1 commit 不重写——shared 实现在 Slice 1 已就位，签名中的 `| JsonObject` 随 2A commit 修改。Slice 1 差分 corpus 新增非-dict Mapping identity 测试（v4.4 C5-CTRL-10-ERRATUM）

*Slice 2A/2B 测试迁移说明（C5-CTRL-07 修正）*: 迁移前差分 characterization 测试通过固定反例 corpus 对比 eligible 私有实现的行为（导入实际私有函数验证）。Slice 2A/2B 后：
- 对已删除的 eligible 定义（如族 A 的 `_validated_fingerprint`、str 系 `_fingerprint` 等），保留同一 expected corpus，测试改为 `from dayu.services._write_artifact_utils import ...` 直接断言 shared helper 行为——私有实现被 shared 函数替换，等价性由 corpus 在迁移前后一致来保证；
- 对 deferred 族（B-F `_validated_fingerprint`、族 2-8 `_required_text`、auto `_format_utc` 等），继续保持私有 characterization，不修改——这些私有函数未被删除，测试继续导入它们即可；
- 不得导入已经删除的私有函数，也不得通过 `importlib` 动态加载已删除符号做脆弱对比。零 `type: ignore` / `Any` / `object` / `cast` 逃逸。

验证: `pyright dayu/services/_write_artifact_utils.py`（0 errors expected）+ `pytest tests/application/test_write_artifact_utils.py -v`。

---

### Slice 2A: C5 — Cohort A 文件全部 eligible helper 迁移（10 文件，文件集合不交叠 2B）

**设计原则（C5-CTRL-08 修正）**: 非重叠文件 cohort，非 helper-family 分段。Cohort A 的每个文件在一次 commit 中完成该文件**全部** eligible shared helper 迁移；不得留 "→2B" 跨 slice 的半迁移状态。auto 族/defer 仍保留原位。

**Cohort A 文件集合（10 文件）**: `write_model_configuration_change.py`, `write_model_configuration_rollback.py`, `write_model_configuration_preapplication.py`, `write_model_challenger_run_approval.py`, `write_model_challenger_preflight_approval.py`, `write_model_challenger_promotion.py`, `write_model_challenger_proposal.py`, `write_model_health.py`, `write_model_live_smoke_plan.py`, `write_run_comparison.py`

**前置依赖**: Slice 1（`_write_artifact_utils.py` 重构完成）

**禁止修改**: Cohort B 的 9 个文件（见 Slice 2B）

**每文件完整迁移表（v4.2，C5-CTRL-01/02/03/04/05/08 已纠正。每行完成该文件全部 eligible 迁移，无 →2B）**:

| 文件 | 迁移的私有定义 | 替换为 shared 函数 | 保留原位/defer 项 |
|---|---|---|---|
| `write_model_configuration_change.py` | `_canonical_json` (str), `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint` (族 A), `_mapping`, `_absolute_path`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping`, `absolute_path`, `serialize_pretty` | `_required_text` (族 3, 保留用于 absolute_path 预处理), `_format_utc` (auto→DEFER), `_persist_immutable`（HEAD 81df373 此文件无 `_decode_base64` 定义，不参与 codec 迁移） |
| `write_model_configuration_rollback.py` | `_canonical_json` (str), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_validated_fingerprint` (族 A), `_mapping`, `_required_text` (族 1), `_absolute_path`, `_is_relative_to`, `_serialize`, `_decode_base64` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `bytes_fingerprint`, `validated_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `is_subpath`, `serialize_pretty`, `decode_base64` | `_format_utc` (auto→DEFER), `_snapshot_fingerprint`, `_persist_immutable` |
| `write_model_configuration_preapplication.py` | `_canonical_json` (str), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_validated_fingerprint` (族 A), `_mapping`, `_absolute_path`, `_serialize`, inline `b64decode` → `decode_base64` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `bytes_fingerprint`, `validated_fingerprint`, `require_mapping`, `absolute_path`, `serialize_pretty`, `decode_base64` | `_required_text` (族 3, 保留用于 absolute_path/decode_base64 预处理), `_persist_immutable` |
| `write_model_challenger_run_approval.py` | `_canonical_json` (str), `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint` (族 A), `_mapping`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping`, `serialize_pretty` | `_required_text` (族 4), `_format_utc` (auto→DEFER), `_validated_absolute_path`, `_persist_immutable` (Family 3) |
| `write_model_challenger_preflight_approval.py` | `_canonical_json` (str), `_fingerprint`, `_validated_fingerprint` (族 A) | `canonical_json_str`, `fingerprint_str`, `validated_fingerprint` | `_required_text` (族 4), `_format_utc` (auto→DEFER)。HEAD 81df373 此文件无 `_mapping` 定义 |
| `write_model_challenger_promotion.py` | `_canonical_json` (str), `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint` (族 A), `_mapping` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping` | `_required_text` (族 5), `_serialize` (缺 sort_keys→DEFER) |
| `write_model_challenger_proposal.py` | `_canonical_json` (str), `_fingerprint`, `_validated_fingerprint` (族 G), `_mapping` (静默) | `canonical_json_str`, `fingerprint_str`, `validated_fingerprint`, `optional_mapping` | — |
| `write_model_health.py` | `_fingerprint` (内联 `json.dumps` 等价 `fingerprint_str`), `_mapping` (静默) | `fingerprint_str`, `optional_mapping` | —（`health.py` 无 `_canonical_json` 定义，不计入 `canonical_json_str` 直接 caller） |
| `write_model_live_smoke_plan.py` | `_canonical_json` (str), `_fingerprint`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `serialize_pretty` | `_required_text` (族 8), `_file_fingerprint_if_present`, `_persist_immutable` (Family 3) |
| `write_run_comparison.py` | `_mapping` (静默) | `optional_mapping` | — |

**迁移规则（v4.2 Cohort A）**:
- `_fingerprint` → `fingerprint_str`: 9 文件在此 cohort（8 个 `_canonical_json` 返回 str 的 + `health.py` 内联等价）。剩余 3 在 2B
- `validated_fingerprint`: 仅族 A（6）+ 族 G（1）= 7 文件全部在此 cohort 迁移。族 B-F 全部在 2B 保留私有
- `_serialize` → `serialize_pretty`: 5 文件在此 cohort（`configuration_change`, `configuration_rollback`, `configuration_preapplication`, `challenger_run_approval`, `live_smoke_plan`）。`challenger_promotion` 缺 sort_keys → defer。剩余 8 在 2B
- `_format_utc` auto 族: `configuration_change`、`configuration_rollback`、`challenger_run_approval`、`challenger_preflight_approval` → 全部 defer（auto 族），不迁移
- `absolute_path`: 族 3 文件（`configuration_change`、`configuration_preapplication`）用各自 `_required_text`（族 3）预处理 text 后调用 shared；族 1 文件（`configuration_rollback`）`require_text` 已迁移 → 直接调 shared
- `decode_base64`: `configuration_rollback`（族 1）`require_text` 已迁移 → 直接调 shared；`configuration_preapplication`（族 3 + inline b64decode）用本地 `_required_text` 预处理后调 shared。`configuration_change` 无 b64 定义，不参与
- `canonical_json_str` 直接定义迁移: 8 文件在此 cohort。剩余 3 在 2B。合计 11（`health.py` 不计入——内联 `json.dumps` 仅等价于 `fingerprint_str`）
- `require_mapping` 严格版: 2A 5 文件（`configuration_change`、`configuration_rollback`、`challenger_run_approval`、`challenger_promotion`、`configuration_preapplication`）+ 2B 9 文件 = 14。`optional_mapping` 静默版: 2A 3 文件（`challenger_proposal`、`health`、`write_run_comparison`）。`challenger_preflight_approval.py` 无 `_mapping` 定义，不参与。闭合计数 14 + 3 = 17 全部 `_mapping` 定义。**v4.4**: 2A 中 5 个 public validator（`rollback.py`）的 `Mapping[str, Any]` payload 经扩宽类型 `ModelConfigJsonValue | JsonObject` 的 `JsonObject` 协变分支通过；shared 实现在 Slice 1 commit 中已就位，类型调整随 2A commit 修改签名

验证: `pytest tests/application/test_write_artifact_utils.py -v` + `pyright dayu/services/`（cohort A 10 文件零新增 errors）。

---

### Slice 2B: C5 — Cohort B 文件全部 eligible helper 迁移（9 文件，文件集合与 2A 不交叠，合计 19）

**设计原则**: Cohort B 的每个文件在一次 commit 中完成该文件**全部** eligible shared helper 迁移。文件集合与 Cohort A 严格不交叠，两 slice 合计覆盖全部 19 文件。

**Cohort B 文件集合（9 文件）**: `write_model_configuration_application.py`, `write_model_configuration_rollback_application.py`, `write_model_configuration_manual_recovery.py`, `write_model_configuration_manual_recovery_application.py`, `write_model_configuration_manual_recovery_clearance.py`, `write_model_configuration_manual_recovery_verification.py`, `write_model_configuration_manual_recovery_incident_dossier.py`, `write_model_configuration_manual_recovery_incident_dossier_revalidation.py`, `write_model_configuration_manual_recovery_gate_revalidation.py`

**前置依赖**: Slice 1 + Slice 2A（2A 先合入，shared 函数和 import 已就位）

**禁止修改**: Cohort A 的 10 个文件

**每文件完整迁移表（v4.2）**:

| 文件 | 迁移的私有定义 | 替换为 shared 函数 | 保留原位/defer 项 |
|---|---|---|---|
| `write_model_configuration_application.py` | `_canonical_json` (bytes), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc` (microseconds), `_is_relative_to`, `_serialize`, `_decode_base64` | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `format_utc`, `is_subpath`, `serialize_pretty`, `decode_base64` | `_validated_fingerprint` (族 C, **禁止迁移**), `_snapshot_fingerprint`, `_transaction_id` (族 2), `_persist_immutable` |
| `write_model_configuration_rollback_application.py` | `_canonical_json` (bytes), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc` (microseconds), `_is_relative_to`, `_serialize`, `_decode_base64` | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `format_utc`, `is_subpath`, `serialize_pretty`, `decode_base64` | `_validated_fingerprint` (族 B, **禁止迁移**), `_snapshot_fingerprint`, `_transaction_id` (族 2), `_persist_immutable` |
| `write_model_configuration_manual_recovery.py` | `_canonical_json` (bytes), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc` (microseconds), `_serialize`, `_decode_base64` (族 B) | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `format_utc`, `serialize_pretty`, `decode_base64_strict` | `_validated_fingerprint` (族 D, **禁止迁移**), `_persist_immutable` (Family 1) |
| `write_model_configuration_manual_recovery_application.py` | `_canonical_json` (bytes), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_absolute_path`, `_is_relative_to`, `_serialize`, `_decode_base64`, `_format_utc` (seconds) | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `absolute_path`, `is_subpath`, `serialize_pretty`, `decode_base64`, `format_utc_seconds` | `_validated_fingerprint` (族 B, **禁止迁移**), `_required_text` (族 2), `_snapshot_fingerprint`, `_transaction_id`, `_persist_immutable` (Family 1) |
| `write_model_configuration_manual_recovery_clearance.py` | `_canonical_json` (bytes), `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_is_relative_to`, `_serialize`, `_format_utc` (seconds) | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `require_text`, `is_subpath`, `serialize_pretty`, `format_utc_seconds` | `_validated_fingerprint` (族 B, **禁止迁移**), `_persist_immutable` |
| `write_model_configuration_manual_recovery_verification.py` | `_canonical_json` (bytes), `_bytes_fingerprint`, `_mapping` | `canonical_json_bytes`, `bytes_fingerprint`, `require_mapping` | `_validated_fingerprint` (族 E, **禁止迁移**), `_snapshot_fingerprint`, `_transaction_id` (族 2), `_required_text` (族 2) |
| `write_model_configuration_manual_recovery_incident_dossier.py` | `_canonical_json` (str), `_fingerprint` (**→fingerprint_str**), `_mapping`, `_required_text`, `_is_relative_to`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `require_mapping`, `require_text`, `is_subpath`, `serialize_pretty` | `_validated_fingerprint` (族 B, **禁止迁移**), `_transaction_id` (族 3), `_persist_immutable` (Family 1) |
| `write_model_configuration_manual_recovery_incident_dossier_revalidation.py` | `_canonical_json` (str), `_fingerprint`（调 `_canonical_json(dict(value))` → **→fingerprint_str**）, `_bytes_fingerprint`, `_mapping` (dict copy 族), `_is_relative_to`, `_serialize` | `canonical_json_str`, `fingerprint_str(dict(value))`, `bytes_fingerprint`, `dict(require_mapping(value, name=...))`, `is_subpath`, `serialize_pretty` | `_validated_fingerprint` (族 B, **禁止迁移**), `_required_text` (族 6), `_format_utc` (auto→DEFER), `_persist_immutable` (Family 4)。`_fingerprint` 原调 `_canonical_json(dict(value))`，迁移后使用 call-site `fingerprint_str(dict(value))`；`_mapping` 原返回 `dict(value)`，用 `dict(require_mapping(...))` adapter（v4.4 C5-CTRL-10-ERRATUM） |
| `write_model_configuration_manual_recovery_gate_revalidation.py` | `_canonical_json` (str+dict 子变体), `_fingerprint` (**→fingerprint_str**), `_bytes_fingerprint`, `_mapping` (dict copy 族), `_is_relative_to`, `_serialize` | `canonical_json_str(dict(value))`, `fingerprint_str(dict(value))`, `bytes_fingerprint`, `dict(require_mapping(value, name=...))`, `is_subpath`, `serialize_pretty` | `_validated_fingerprint` (族 F, **禁止迁移**), `_required_text` (族 7), `_format_utc` (auto→DEFER), `_persist_immutable` (Family 4)。str+dict 子变体与 copy 族 mapping 通过 call-site `dict()` adapter 保持等价（v4.4 C5-CTRL-10-ERRATUM） |

**迁移规则（v4.2 Cohort B）**:
- `_fingerprint` → `fingerprint_str`（3 文件）: `incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation` 的 `_fingerprint` 正确映射为 `fingerprint_str`（底层 `_canonical_json` 返回 str → `.encode("utf-8")`，C5-CTRL-04）。Cohort A 覆盖 9，合计 12
- `_fingerprint` → `fingerprint_bytes`（5 文件）: `configuration_application`、`rollback_application`、`manual_recovery`、`manual_recovery_application`、`manual_recovery_clearance`（底层 `_canonical_json` 返回 bytes，C5-CTRL-04）
- `validated_fingerprint`: 所有族 B/C/D/E/F（9 文件）**全部保留私有**，不得调用 shared（C5-CTRL-01）。标注 "**禁止迁移**"
- `_serialize` → `serialize_pretty`: 8 文件在此 cohort（`configuration_application`、`rollback_application`、`manual_recovery`、`manual_recovery_application`、`manual_recovery_clearance`、`incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation`）。Cohort A 迁移 5，`challenger_promotion` defer 1，合计 13 迁移 + 1 defer = 14 全部
- `absolute_path`: 各 caller 先用各自 `_required_text` 族得到 `text: str`，再调用 `absolute_path(text, *, name=name)`（C5-CTRL-02）
- `decode_base64` / `decode_base64_strict`: 各 caller 先用各自 `_required_text` 族得到 `text: str`，再调用 shared codec（C5-CTRL-03）
- `_format_utc` auto 族: `gate_revalidation`、`incident_dossier_revalidation` → defer（auto 族）
- `_format_utc` → `format_utc_seconds`: `manual_recovery_application`、`manual_recovery_clearance`
- `_format_utc` → `format_utc` (microseconds): `configuration_application`、`rollback_application`、`manual_recovery`。Cohort A 无 microseconds caller，合计 3
- `canonical_json_str` 直接定义迁移: 3 文件在此 cohort（`incident_dossier`、`incident_dossier_revalidation`、`gate_revalidation`）。Cohort A 8，合计 11
- `require_mapping` identity vs copy（v4.4 C5-CTRL-10-ERRATUM）: shared `require_mapping` 签名 `(value: ModelConfigJsonValue | JsonObject, *, name: str) -> JsonObject`，identity-return（`return value`）。输入类型扩宽后仍接受 `ModelConfigJsonValue` 及 `Mapping[str, Any]`（经 `JsonObject` 协变分支）。12 个 identity-return 文件直接迁移。copy 族 2 文件（`incident_dossier_revalidation`、`gate_revalidation`——原 `_mapping` 返回 `dict(value)`）使用 call-site adapter `dict(require_mapping(value, name=...))`。`gate_revalidation` 的 canonical/fingerprint 使用 `canonical_json_str(dict(value))` / `fingerprint_str(dict(value))`；`incident_dossier_revalidation` 的 fingerprint 使用 `fingerprint_str(dict(value))`。实现/返回/identity/17 helper count/2B copy adapter 均不变

**文件集合唯一性**: Cohort A 10 + Cohort B 9 = 19。两集合严格不交叠。

验证: `pytest tests/application/ -v -k "write_model"` + `pyright dayu/services/`（19 文件零新增 errors）。

---

### Slice 3: W15 — finish() 内联消除

**文件**: `dayu/services/write_model_challenger_proposal.py`。5 个 `return finish()` → 直接 `return _finalize_payload(payload, history_fingerprint=normalized_history_fingerprint, selected_run_count=selected_run_count, recent_run_count=recent_run_count, baseline_run_count=baseline_run_count)`。删除嵌套 `def finish()`。验证: `pytest -k "challenger_proposal"` + `pyright`。

---

### Slice 4: W16 — append_current_section 提取

**文件**: `dayu/cli/commands/research_workbook.py`。

**W16-CTRL-01 类型勘误（v4.5）**: 原 `sections: list[dict[str, object]]`
会新增 AGENTS 禁止的 `object` 签名，不得实施。新增以下三个模块私有
TypedDict，字段必须完整且全部为 required：

```python
from typing import TypedDict


class _ResearchWorkbookEvidence(TypedDict):
    """描述研究手册单条证据的精确字段。"""

    source: str
    reference: str
    finding: str


class _ResearchWorkbookItem(TypedDict):
    """描述研究手册章节内单项的精确字段。"""

    item_id: str
    prompt: str
    status: str
    response: str
    evidence: list[_ResearchWorkbookEvidence]
    analyst_notes: str
    evidence_required: bool


class _ResearchWorkbookSection(TypedDict):
    """描述研究手册章节的精确字段。"""

    section_id: str
    title: str
    category: str
    items: list[_ResearchWorkbookItem]
```

提取的模块级 helper exact signature：

```python
def _append_research_workbook_section(
    sections: list[_ResearchWorkbookSection],
    *,
    normalized: str,
    current_title: str,
    current_category: str,
    current_items: list[str],
) -> None:
```

实现约束：

- helper 保持现有 early return、`section_index = len(sections)`、section/item
  hash material、截断长度、字段值与 append 时序，提供完整中文
  Args/Returns/Raises docstring。
- `build_research_workbook_payload` 内局部变量改为
  `sections: list[_ResearchWorkbookSection] = []`；helper 内局部变量显式标注
  `items: list[_ResearchWorkbookItem] = []`。
- 两个调用点均改为显式传入同一 `sections`、`normalized`、
  `current_title`、`current_category`、`current_items`：第一处在 heading
  切换时 flush 上一 section，第二处在 EOF 后 flush 最后一 section。
- public `build_research_workbook_payload(...) -> dict[str, object]` 是存量契约，
  保持不变；本模块 15 个存量函数签名共含 19 处
  `dict[str, object]`（含 public builder 与 2 个私有 helper），均不在 W16
  scope。
- 禁止新增 `Any`、`object`、`cast`、`type: ignore` 或 glue
  wrapper；不得改变 public API、JSON shape、ID 稳定性或重复 heading/bullet
  的防碰撞语义。

验证：

```text
pytest tests/cli/test_research_template_command.py -k "research_workbook" -q
pyright dayu/cli/commands/research_workbook.py tests/cli/test_research_template_command.py
```

现有基线为 `35 passed`、pyright `0 errors`；实现后必须维持。重点断言包括完整
section/item shape、stable IDs、重复 heading/bullet ID 唯一性、BOM 与生成
payload 自验证。

---

### Slice 5: C1 — _write_config_helpers + _write_params_validation

**S5-CTRL-01..04（v4.7 exact scope；v4.6 accepted history retained）**:

1. 新建 `dayu/cli/commands/_write_config_helpers.py`：
   - 单一定义 `MODULE = "APP.WRITE"`；
   - 从 `dayu.cli.dependency_setup` 功能性 import `WriteCliConfig` 与
     `setup_model_name`；
   - exact 迁移 4 个函数：
     `_resolve_write_model_override_name`、
     `_resolve_write_company_name`、
     `_build_write_run_config`、
     `_log_write_preflight_result`。
2. 新建 `dayu/cli/commands/_write_params_validation.py`，exact 迁移 4 个函数：
   - `_challenger_requested`
   - `_validate_challenger_run_plan_args`
   - `_validate_live_smoke_plan_args`
   - `_validate_research_materialization_args`

   `_validate_research_materialization_args` 直接调用同模块
   `_challenger_requested`；本模块禁止 import `write.py`，也禁止 import
   Slice 5 时尚不存在的未来 `_write_challenger.py`。
3. `write.py`：
   - 从 `_write_config_helpers` 正常顶层 import `MODULE` 与该模块 4 个 private
     函数；
   - 从 `_write_params_validation` 正常顶层 import
     `_challenger_requested` 与
     `_validate_research_materialization_args`；
   - 不 import/re-export `_validate_challenger_run_plan_args` 与
     `_validate_live_smoke_plan_args`；这两个 validator 只在真实 owner
     `_write_params_validation.py` 定义；
   - 删除本地 `MODULE = "APP.WRITE"`、`setup_model_name` 的
     `dependency_setup` import，以及上述 8 个旧定义；
   - `MODULE` 为单独的正常功能 import，不计入 private function；上述 config
     4 个 + params 2 个合计 6 个 functional private binding 均有真实 caller，
     必须保持其 `dayu.cli.commands.write.<private>` direct
     import/monkeypatch 和 global lookup 行为；
   - 禁止为两个不再由 `write.py` 调用的 validator 添加 compatibility
     re-export，也不得添加 wrapper、lazy import 或同步 seam。
4. 测试边界迁移：
   - `tests/engine/test_cli_running_config.py` 中精确 13 处
     `dayu.cli.commands.write.setup_model_name` patch 全部改为
     `dayu.cli.commands._write_config_helpers.setup_model_name`；
   - 旧 patch 目标必须为 0，新目标必须为 13；
   - 该测试对 `setup_model_name` 自身的直接 import 改从
     `dayu.cli.dependency_setup` 获取；
   - 6 个 functional private binding 的 `write.<private>` direct import 与
     monkeypatch 路径保持不变；包括 application test 对
     `_validate_research_materialization_args` 的 `write.py` direct import，
     不迁到新模块；
   - engine test 对 `_validate_live_smoke_plan_args` 的 direct import 改从
     `dayu.cli.commands._write_params_validation` 获取；
   - `_validate_challenger_run_plan_args` 没有旧 direct test，只验证其在
     `_write_params_validation.py` 的新 owner 定义；dispatch identity 测试
     只锁定上述 6 个 functional binding；
   - 新增真实回归一：patch
     `dayu.cli.commands.write._challenger_requested`，触发真实
     `run_write_command`，断言其 3 个 global call site 所在路径由该 binding
     控制；
   - 新增真实回归二：patch
     `dayu.cli.commands._write_params_validation._challenger_requested`，调用真实
     `_validate_research_materialization_args`，断言 validator 内部路径由该
     binding 控制；
   - 不得 blanket 迁移旧 `write._challenger_requested` patch。现有 engine
     test 约 line 5934 同时 patch validator 本身与
     `write._challenger_requested`，用于 `run_write_command` 路径，保持不变。
5. 两个新模块必须有中文模块概览，各 exact 4 个函数、合计 exact 8 个定义；
   8 个迁移函数保持 exact 签名、控制流、返回值、异常与日志语义，并补齐
   完整中文 Args/Returns/Raises docstring。
   禁止新增或传播 `Any`、`object`、`cast`、`type: ignore`、glue seam；不得
   顺手迁移其他函数。

验证：

```text
pytest tests/application/test_write_service.py \
  tests/application/test_write_cli_dispatch.py -v
pytest tests/engine/test_cli_running_config.py -v -k "write"

python -c "from dayu.cli.commands._write_config_helpers import MODULE, _resolve_write_model_override_name; from dayu.cli.commands._write_params_validation import _challenger_requested, _validate_research_materialization_args; from dayu.cli.commands.write import run_write_command"

rg 'dayu\.cli\.commands\.write\.setup_model_name' tests
→ 0
rg 'dayu\.cli\.commands\._write_config_helpers\.setup_model_name' tests
→ 13
rg '^MODULE = \"APP\.WRITE\"' dayu/cli/commands
→ 仅 _write_config_helpers.py 1 处
rg '^def (_resolve_write_model_override_name|_resolve_write_company_name|_build_write_run_config|_log_write_preflight_result|_challenger_requested|_validate_challenger_run_plan_args|_validate_live_smoke_plan_args|_validate_research_materialization_args)\b' dayu/cli/commands/write.py
→ 0
两个新模块上述定义合计 → 8
rg '(_validate_challenger_run_plan_args|_validate_live_smoke_plan_args)' dayu/cli/commands/write.py
→ 0
rg 'from dayu\.cli\.commands\._write_params_validation import _validate_live_smoke_plan_args' tests/engine/test_cli_running_config.py
→ 1

pyright dayu/cli/
ruff check --select F,I <changed paths>
Ruff 全规则 finding code multiset vs HEAD → delta 0
git diff --check
```

使用上述 application + engine 真实 caller corpus，对
`_write_config_helpers.py`、`_write_params_validation.py`、修改后的 `write.py`
逐文件计算精确 coverage，三个文件均必须 `>= 80%`。额外断言
`write.py` 中 6 个 functional private binding 与新模块函数对象 identity；
分别 patch
`write._challenger_requested` 与
`_write_params_validation._challenger_requested` 的两条真实回归必须证明
run path / validator path 按 call-site owner 独立受控。若只迁移测试 patch
字符串且测试入口/分层未改变，`tests/README.md` 不更新；否则按实际入口同步。

---

### Slice 6: C1+W12 — 组合 commit（零反向 import 中间态）

**单 commit 原子创建**:

1. `dayu/cli/commands/_write_config_application.py`: exact 迁移 `_build_fresh_application_routing_snapshot(*, args: argparse.Namespace, paths_config: WorkspaceConfig, execution_options: ExecutionOptions, run_label: str = "configuration-application") -> Mapping[str, ModelConfigJsonValue]` + `_run_write_model_configuration_application(*, args: argparse.Namespace, paths_config: WorkspaceConfig, execution_options: ExecutionOptions) -> int`。从 `_write_config_helpers` import `MODULE` 及所需 helper，并从 `dependency_setup`、`write_model_configuration_preapplication` import 其余功能依赖；`ExecutionOptions` 使用 CLI 标准导入路径 `dayu.execution.options`（规范定义位于 `dayu.contracts.execution_options`），`ModelConfigJsonValue` 从 `dayu.contracts.model_config` import；不定义本地 MODULE。**S6-W12-CYCLE-01**：runner 内的闭包 #1 改为精确一次 `functools.partial(_build_fresh_application_routing_snapshot, args=args, paths_config=paths_config, execution_options=execution_options)`；不得显式传 `run_label`，以继续使用 `_build_fresh_application_routing_snapshot` 的默认值；本模块禁止 import `_write_snapshot_builder` 或其任何符号。

2. `dayu/cli/commands/_write_snapshot_builder.py`: `_build_snapshot_for_args(args: argparse.Namespace, *, paths_config: WorkspaceConfig, execution_options: ExecutionOptions, run_label: str = "configuration-application") -> Mapping[str, ModelConfigJsonValue]`（模块级函数）+ `build_snapshot_builder(*, args: argparse.Namespace, paths_config: WorkspaceConfig, execution_options: ExecutionOptions, run_label: str = "configuration-application") -> Callable[[], Mapping[str, ModelConfigJsonValue]]`（`functools.partial` factory）。从 `_write_config_application` 顶层 import（**非** `write.py`）；`ExecutionOptions` 使用 CLI 标准导入路径 `dayu.execution.options`（规范定义位于 `dayu.contracts.execution_options`），`ModelConfigJsonValue` 从 `dayu.contracts.model_config` import。全部类型使用 `ExecutionOptions`（非 `Any`）、`Mapping[str, ModelConfigJsonValue]`（非 `Mapping[str, Any]`）；Slice 6 不 import 尚未存在的 `DayuCliArguments`。

3. `write.py`: 闭包 #1 随 `_run_write_model_configuration_application` 迁出并按 item 1 转为同模块 direct partial；其余闭包 #2–#5 全部替换为 `build_snapshot_builder(...)`，其中 #2/#3 不显式传 `run_label`，#4 精确传 `"configuration-manual-recovery-verification"`，#5 精确传 `"configuration-manual-recovery-clearance"`。六处相关 `execution_options: Any` → `ExecutionOptions`；删除 `_build_fresh_application_routing_snapshot`、`_run_write_model_configuration_application` 定义。禁止 compatibility re-export、反向 import、lazy import 或 DI/glue seam。

commit message: `refactor: extract routing snapshot + snapshot builder + ExecutionOptions types in one commit`

验证: `pytest tests/application/test_write_service.py tests/application/test_write_cli_dispatch.py tests/engine/test_cli_running_config.py -v -k "write"` + `pyright dayu/cli/` + Ruff F/I 与 HEAD full-rule finding-code multiset delta=0。三个改动生产文件 `_write_config_application.py`、`_write_snapshot_builder.py`、`write.py` 必须逐文件按精确 statement 百分比达到 `>=80%`。测试必须包含两条真实 callback 证据：(1) 直接调用 `build_snapshot_builder` 返回的零参数 callback，以依赖 stub 捕获并断言 `args`、`paths_config`、`execution_options`、默认/显式 `run_label` 与返回 mapping；(2) 真实调用 `_run_write_model_configuration_application`，由 transaction dependency stub 实际调用其收到的 `snapshot_builder` 并断言 mapping/结果，从而覆盖同模块 direct partial 路径。不得通过临时令 `_write_snapshot_builder` 不可 import 来证明依赖方向，该做法脆弱且把测试耦合到 import 机制。

结构门禁：Slice 6 四个新/迁移函数的 `args` 均为 `argparse.Namespace`；六处相关 `execution_options: Any` 为 0；两个新模块 `DayuCliArguments` 引用为 0；对 `_write_config_application.py` 与 `write.py` 做 AST 审计，nested `_snapshot_builder` 定义合计为 0，五处旧闭包全部闭环；application 模块 import `_write_snapshot_builder` 为 0；builder 模块从 `_write_config_application` import `_build_fresh_application_routing_snapshot` 精确 1 且 import `write.py` 为 0；application 模块的 `functools.partial` 调用精确 1；`write.py` 的 `build_snapshot_builder` 调用精确 4，且四处 label 为默认、默认、verification、clearance。测试 import/monkeypatch 路径随真实 owner 迁移，禁止 compatibility re-export。

---

### Slice 7: C1 — _write_execution + _write_manual_recovery

**基线与目标**: clean HEAD `b55f794` 的 `write.py` 精确含 14 个
`_run_write_model_configuration_manual_recovery_*` runner、1 个独立 Phase C
`_check_write_model_configuration_manual_recovery_gate` 与 2 个 execution helper。
本 Slice 原子新建两个真实 owner，合计迁移 exact 17 个函数；除定义 owner、正常功能
import、测试 patch owner 与 W12 factory import owner 外，参数、返回值、异常映射、
日志、打印顺序、持久化顺序、Phase A/C dispatch 顺序与 public CLI 语义全部不变。

1. **`dayu/cli/commands/_write_execution.py`（exact 2 definitions）**:
   - `_run_write_stage`
   - `_run_write_preflight`

   两个函数按 HEAD 签名与控制流 exact 迁移；从 `_write_config_helpers` 正常 import
   `MODULE` 与 `_log_write_preflight_result`，不复制本地常量、不反向 import
   `write.py`。模块概览与两个函数补齐完整中文 Args / Returns / Raises docstring；
   禁止新增 `Any`、`object`、`cast`、`type: ignore`、lazy import 或 glue seam。

2. **`dayu/cli/commands/_write_manual_recovery.py`（exact 15 definitions）**:

   14 个 runner 按当前源码出现顺序逐名锁定：

   1. `_run_write_model_configuration_manual_recovery_evidence`
   2. `_run_write_model_configuration_manual_recovery_plan`
   3. `_run_write_model_configuration_manual_recovery_approval`
   4. `_run_write_model_configuration_manual_recovery_application`
   5. `_run_write_model_configuration_manual_recovery_verification`
   6. `_run_write_model_configuration_manual_recovery_clearance`
   7. `_run_write_model_configuration_manual_recovery_clearance_revocation`
   8. `_run_write_model_configuration_manual_recovery_restart`
   9. `_run_write_model_configuration_manual_recovery_gate_check`
   10. `_run_write_model_configuration_manual_recovery_gate_verification`
   11. `_run_write_model_configuration_manual_recovery_gate_revalidation`
   12. `_run_write_model_configuration_manual_recovery_audit_timeline`
   13. `_run_write_model_configuration_manual_recovery_incident_dossier`
   14. `_run_write_model_configuration_manual_recovery_incident_dossier_revalidation`

   第 15 个定义为独立 Phase C helper：
   `_check_write_model_configuration_manual_recovery_gate`。其中 application、
   verification、clearance 三个 runner 继续接受
   `execution_options: ExecutionOptions`；其余 11 个 runner 与 Phase C helper 保持
   HEAD 精确签名。所有函数体、异常/退出码、I/O 与 fail-closed 语义 exact 迁移；
   模块概览和全部 15 个函数使用完整中文 Args / Returns / Raises docstring。

   本模块从 `_write_config_helpers` 正常 import `MODULE`，不定义或 re-export 本地
   常量。application / verification / clearance 连同
   `_write_snapshot_builder.build_snapshot_builder` 的单向功能 import 与三处 factory
   call 一并迁入；label 精确保持：application 默认、verification 为
   `configuration-manual-recovery-verification`、clearance 为
   `configuration-manual-recovery-clearance`。CLI 内部依赖只能为
   `_write_manual_recovery → _write_snapshot_builder → _write_config_application`；
   manual 模块不得 import `write.py` 或 `_write_config_application`，snapshot/application
   不得反向 import manual。禁止 cycle、nested helper、lazy import、compatibility
   wrapper/re-export 或 DI/glue seam。

3. **`dayu/cli/commands/write.py`**:
   - 删除 `_run_write_stage`、`_run_write_preflight`、14 个 manual-recovery runner 与
     `_check_write_model_configuration_manual_recovery_gate` 的旧定义，旧定义 AST
     合计必须为 0。
   - 从两个新 owner 正常顶层 import exact 17 个 functional symbols；这些 symbol
     均被 `run_write_command`、当前仍位于 `write.py` 的 Challenger helper 或后续
     dispatch global lookup 实际调用，因此不是 compatibility re-export。
   - 删除迁出函数独占的 service/typing imports；保留当前仍有真实 caller 的依赖。
     manual 三处 factory 迁出后，`write.py` 只为 Slice 8 rollback runner 保留
     `build_snapshot_builder` 默认-label import/call exact 1。

4. **测试 ownership**:
   - 直接调用 `_run_write_stage` / `_run_write_preflight` 的测试，以及只为验证两者
     内部依赖而做的 patch，迁到 `_write_execution` 真实 owner。
   - 直接调用 14 个 manual runner / Phase C gate 的测试，以及只为验证这些函数
     内部 service 依赖而做的 patch，迁到 `_write_manual_recovery` 真实 owner。
   - 验证 `run_write_command`、Phase A/C dispatch 短路顺序或当前 Challenger helper
     global lookup 的 characterization，继续 patch `write.<symbol>` 正常功能 binding；
     禁止 blanket 把全部旧 patch path 迁走，也禁止为测试新增 compatibility seam。
   - 新增/更新 identity 回归：`write.py` 的 exact 17 个 functional bindings 分别与
     两个新 owner 中的函数对象相同；direct-owner 与 dispatch-owner 两类回归都必须
     真实执行至少一条对应路径。

5. **结构与验证门禁**:
   - `_write_execution.py` 顶层目标定义 exact 2；`_write_manual_recovery.py` 顶层目标
     定义 exact 15；`write.py` 上述旧定义 exact 0；两个新 owner 合计 exact 17，
     `write.py` 从它们正常 import exact 17。
   - manual 模块 `build_snapshot_builder` import exact 1、call exact 3，labels 为
     默认 / verification / clearance；`write.py` factory call 剩余 exact 1（rollback
     默认）；三个相关模块 nested `_snapshot_builder` 定义为 0。
   - manual → snapshot import exact 1，snapshot → config-application 既有 import
     exact 1；manual → write、snapshot → manual、config-application → manual 均为 0；
     同进程 import smoke 与 AST gate 必须证明无 cycle。
   - 相关测试至少运行全部 application `test_write*.py` 与
     `tests/engine/test_cli_running_config.py`；聚焦 owner/dispatch 测试另行记录。
   - `pyright dayu/cli/` 及修改测试为 0 errors；Ruff F/I 与 HEAD full-rule
     finding-code multiset 的 gate rule 保持不变，实施目标 delta=0；
     `_write_execution.py`、`_write_manual_recovery.py`、`write.py` 三份生产文件按
     精确 statement 百分比逐文件 `>=80%`；`git diff --check` 通过。
   - tests 若只迁 owner/patch 且入口与分层不变，`tests/README.md` 不更新；CLI
     private 模块拆分不改变用户命令/参数时根 README 不更新；若实现审计发现当前
     README 的入口、分层或稳定架构描述与代码不一致，才按职责最小同步并记录。

**Non-goals**: Phase A 14 条目与顺序、Phase C gate 调用位置、Slice 10/11 的
adapter/Protocol 设计、Slice 8 exact 13 Challenger + rollback ownership 均不改变；
本 Slice 不提前实现 dispatch table、`DayuCliArguments`、Challenger/rollback 迁移或
任何新业务语义。

commit message: `refactor: extract write execution and manual recovery commands`

---

### Slice 8: C1 — _write_challenger + _write_config_rollback + write.py 清理

**S5-CTRL-01 exact ownership**: `_challenger_requested` 已在 Slice 5 迁入
`_write_params_validation.py`。Slice 8 从原源码连续 14 函数组中迁移剩余
exact 13 个到 `_write_challenger.py`：

1. `_challenger_preflight_cli_args`
2. `_verify_challenger_preflight_approval_before_host`
3. `_build_challenger_run_plan_from_args`
4. `_assert_challenger_run_output_boundaries`
5. `_load_current_challenger_proposal`
6. `_persist_challenger_run_authorization_after_preflight`
7. `_verify_and_consume_challenger_run_approval_before_host`
8. `_build_challenger_write_config`
9. `_preflight_champion_and_challenger`
10. `_run_champion_challenger_experiment`
11. `_manifest_has_usable_company_facets`
12. `_needs_auto_research_bootstrap`
13. `_build_auto_bootstrap_args`

同时新建 `_write_config_rollback.py`。rollback runner 迁移时必须连同其既有
`build_snapshot_builder` 默认-label factory call 与从
`_write_snapshot_builder` 的单向 import 一并迁移，禁止改回 nested helper 或
引入反向 import。两个模块在存在真实日志 caller 时从
`_write_config_helpers` 正常 import `MODULE`，不得本地定义或反向 import
`write.py`。`write.py` 删除全部对应旧定义，降至约 660 行，仅保留
`run_write_command`、`_materialize_research_after_write` 及其正常功能 imports；
`MODULE` 仍因 `write.py` 内真实日志 caller 而自然可见，但定义真源唯一位于
`_write_config_helpers.py`，Slice 8 终态不得声称 `write.py` 本地定义
MODULE。除 MODULE import 与 14→13 ownership 修正外，Slice 8 语义不变。

---

### Slice 9: C2 — research_template.py 5 私有模块（单 commit）

**基线与原子性**: clean HEAD `1d0f9e6`。本 Slice 同一 accepted commit
创建五个真实 owner、迁移全部 83 个非 runner/entry 函数、迁移两个 dataclass
与七个域常量、更新主模块 functional imports / `__all__` / tests，以及更新
`write.py` 当前 line 81 的 materialize lazy import。禁止拆成会留下缺失符号、
反向 import 或 compatibility facade 的中间 commit。

#### 9a. Exact ownership inventory（83 functions）

`dayu/cli/commands/_research_template_helpers.py` 顶层 FunctionDef **exact 22**：

1. `_print_definition_header`
2. `_resolve_materialize_research_target`
3. `_build_research_portfolio_preview`
4. `_portfolio_target_artifact_paths`
5. `_recommendation_payload`
6. `_company_facets_from_args`
7. `_load_company_facets_from_manifest`
8. `_load_json_object`
9. `_load_workbook_evidence_records`
10. `_resolve_template_dir`
11. `_normalize_template_name`
12. `_read_template_title`
13. `_as_str_list`
14. `_dedupe`
15. `_normalize_research_target`
16. `_identifier_component`
17. `_scheduler_state_from_plan_inspection`
18. `_discover_research_artifact_paths`
19. `_sha256_file`
20. `_sha256_json_object`
21. `_source_map_sources_by_name`
22. `_inspect_source_binding_snapshot`

helpers 同时拥有顶层 ClassDef **exact 2**：`ResearchTemplate`、
`ResearchTemplateRecommendation`；拥有下列模块常量定义 **exact 7**：
`_TEMPLATE_DIR_NAME`、`_TEMPLATE_SUFFIX`、`_FALLBACK_TEMPLATE_NAME`、
`_BUNDLE_ARTIFACT_KEYS`、`_COMMON_DATA_SOURCE_CANDIDATES`、
`_TEMPLATE_DATA_SOURCE_CANDIDATES`、`_DATA_SOURCE_BINDING_CANDIDATES`。
最后一项的存量 `object` 类型/值语义必须原样 1→1 迁移，不新增 `object`
签名、用法或 escape，也不在纯 owner migration 中擅自收窄业务值结构。

`dayu/cli/commands/_research_template_core.py` 顶层 FunctionDef **exact 26**：

1. `list_research_templates`
2. `load_research_template`
3. `copy_research_template`
4. `compose_research_template`
5. `materialize_research_checklist`
6. `recommend_research_templates`
7. `extract_monitoring_variables`
8. `build_monitoring_rules_payload`
9. `build_monitoring_source_map_payload`
10. `validate_monitoring_source_map_payload`
11. `build_monitoring_source_binding_preview`
12. `write_monitoring_source_binding_approval`
13. `build_monitoring_source_binding_rollback_preview`
14. `write_monitoring_source_binding_rollback`
15. `inspect_monitoring_source_binding_history`
16. `build_research_template_package_manifest`
17. `get_monitoring_data_source_candidates`
18. `write_monitoring_rules_payload`
19. `write_monitoring_source_map_payload`
20. `write_research_template_package_manifest`
21. `build_research_template_usage_guide`
22. `write_research_template_usage_guide`
23. `_resolve_template_selection_from_write_manifest`
24. `_build_source_write_manifest_binding`
25. `_build_write_manifest_binding_semantics`
26. `_resolve_template_path`

`dayu/cli/commands/_research_template_bundle.py` 顶层 FunctionDef **exact 12**：

1. `build_research_template_bundle_descriptor`
2. `_recompute_bundle_monitoring_integrity`
3. `_recompute_bundle_checklist_integrity`
4. `validate_research_template_bundle_descriptor`
5. `inspect_research_template_bundle`
6. `build_research_template_bundle_rebind_preview`
7. `write_research_template_bundle_rebind`
8. `_prepare_research_template_bundle_rebind`
9. `build_research_template_bundle_rebind_rollback_preview`
10. `write_research_template_bundle_rebind_rollback`
11. `discover_research_template_bundles`
12. `write_research_template_bundle_descriptor`

`dayu/cli/commands/_research_template_monitoring.py` 顶层 FunctionDef **exact 11**：

1. `build_monitoring_execution_plan`
2. `validate_monitoring_execution_plan`
3. `inspect_monitoring_execution_plan`
4. `discover_monitoring_execution_plans`
5. `build_monitoring_status_snapshot`
6. `write_monitoring_status_snapshot`
7. `build_monitoring_scheduler_manifest`
8. `validate_monitoring_scheduler_manifest`
9. `inspect_monitoring_scheduler_manifest`
10. `write_monitoring_scheduler_manifest`
11. `write_monitoring_execution_plan`

`dayu/cli/commands/_research_template_materialize.py` 顶层 FunctionDef **exact 12**：

1. `_materialization_artifact_paths`
2. `_snapshot_materialization_artifacts`
3. `_rollback_materialization_artifacts`
4. `materialize_research_template_bundle`
5. `materialize_research_workspace`
6. `build_research_workspace_refresh_preview`
7. `write_research_workspace_refresh`
8. `materialize_research_bundle_from_write_manifest`
9. `materialize_research_portfolio`
10. `build_research_portfolio_preview`
11. `_resolve_materialize_template_selection`
12. `_prepare_research_portfolio_targets`

**闭合不变量**: 五组互斥且并集为原模块除
`run_research_template_command` 与 39 个 `_run_*` 之外的 exact 83 个
FunctionDef；迁移后原模块上述 83 个定义为 0，`research_template.py`
只定义 entry 1 + runners 39（FunctionDef exact 40）且 ClassDef exact 0。
`_print_definition_header` 必须迁至 helpers，不得留置。

#### 9b. Exact import DAG 与行为迁移

只允许下列 project-domain 边：

```text
research_template.py → helpers + core + bundle + monitoring + materialize
core → helpers
bundle → core + helpers
monitoring → bundle + core + helpers
materialize → monitoring + bundle + core + helpers
helpers → （零内部 project-domain dependency）
```

五个新 owner 均不得 import `research_template.py`；不得出现 reverse edge、
cycle、lazy owner import、compatibility re-export/wrapper、DI/glue seam 或仅为
旧测试保留的 binding。全部 83 函数、2 dataclass、7 constants 按去除
docstring 后 AST exact 迁移；签名、默认值、控制流、异常文本/类型、退出码、
文件 I/O、JSON/哈希字节、排序与持久化时序均保持。五个新模块提供中文概览，
全部迁移/修改函数提供完整中文 Args/Returns/Raises docstring；不得新增或传播
`Any`、`object`、`cast`、`type: ignore` 或无理由 `getattr`/`hasattr`。

#### 9c. Main facade functional bindings（exact 45）

`research_template.py` 只正常顶层 import entry/runner 真实调用的下列 exact 45
function bindings；它们是当前执行路径的功能依赖，不是 compatibility re-export：

- helpers **exact 6**: `_company_facets_from_args`、`_load_json_object`、
  `_load_workbook_evidence_records`、`_print_definition_header`、
  `_recommendation_payload`、`_resolve_materialize_research_target`
- core **exact 18**: `build_monitoring_rules_payload`、
  `build_monitoring_source_binding_preview`、
  `build_monitoring_source_binding_rollback_preview`、
  `build_monitoring_source_map_payload`、
  `build_research_template_package_manifest`、`compose_research_template`、
  `copy_research_template`、`inspect_monitoring_source_binding_history`、
  `list_research_templates`、`load_research_template`、
  `materialize_research_checklist`、`recommend_research_templates`、
  `validate_monitoring_source_map_payload`、`write_monitoring_rules_payload`、
  `write_monitoring_source_binding_approval`、
  `write_monitoring_source_binding_rollback`、
  `write_monitoring_source_map_payload`、
  `write_research_template_package_manifest`
- bundle **exact 6**: `build_research_template_bundle_rebind_preview`、
  `build_research_template_bundle_rebind_rollback_preview`、
  `discover_research_template_bundles`、`inspect_research_template_bundle`、
  `write_research_template_bundle_rebind`、
  `write_research_template_bundle_rebind_rollback`
- monitoring **exact 9**: `build_monitoring_execution_plan`、
  `build_monitoring_scheduler_manifest`、`build_monitoring_status_snapshot`、
  `discover_monitoring_execution_plans`、`inspect_monitoring_execution_plan`、
  `inspect_monitoring_scheduler_manifest`、`write_monitoring_execution_plan`、
  `write_monitoring_scheduler_manifest`、`write_monitoring_status_snapshot`
- materialize **exact 6**: `_resolve_materialize_template_selection`、
  `build_research_portfolio_preview`、`build_research_workspace_refresh_preview`、
  `materialize_research_portfolio`、`materialize_research_workspace`、
  `write_research_workspace_refresh`

其余 **38** 个迁移函数不得在主模块建立 compatibility binding。新增 exact45
identity 回归，逐一断言主模块 binding 与真实 owner 函数对象相同。

#### 9d. `__all__` 与 tests ownership

`research_template.py.__all__` 从当前 exact 68 删除下列 exact 13：

1. `ResearchTemplate`
2. `ResearchTemplateRecommendation`
3. `build_research_template_bundle_descriptor`
4. `build_research_template_usage_guide`
5. `extract_monitoring_variables`
6. `get_monitoring_data_source_candidates`
7. `materialize_research_template_bundle`
8. `materialize_research_bundle_from_write_manifest`
9. `validate_research_template_bundle_descriptor`
10. `validate_monitoring_execution_plan`
11. `validate_monitoring_scheduler_manifest`
12. `write_research_template_bundle_descriptor`
13. `write_research_template_usage_guide`

其余 functional/workbook/entry 条目 **exact 55** 保留；只能依赖 item 9c 的
真实 functional imports 与既有 workbook imports，禁止 solely-for-compat import。
五个私有 owner 模块均不定义 `__all__`，不扩大 star-import surface。

测试按被测 call site 的 globals 精确迁移：直接测试迁移定义、dataclass、常量
或 owner 内依赖的 import/monkeypatch 必须指向五个真实 owner；只验证
`run_research_template_command` 或 retained runner global lookup 的
characterization 才保留 `research_template.<symbol>`。当前
`tests/cli/test_research_template_command.py` 的 direct definition imports 与
dependency patches 按上述规则迁移，禁止为测试新增 facade。可在现有测试文件内
按 owner 分组 import；是否拆测试文件只由可读性与真实分层决定，不是强制目标。

#### 9e. write lazy import、后续 Slice 与验证

`dayu/cli/commands/write.py` 当前 line 81 的
`materialize_research_bundle_from_write_manifest` function-local import 从
`dayu.cli.commands.research_template` 改为
`dayu.cli.commands._research_template_materialize`；保留既有 lazy 时序与调用
语义，不上移。Slice 10 仍只机械传播 retained entry + 39 runners 的
`DayuCliArguments` 签名；两个 dataclass 已在 helpers，Slice 10 不再迁移或
重复定义它们。

至少执行并记录：

```text
pytest tests/cli/test_research_template_command.py \
  tests/cli/test_research_template_definitions.py \
  tests/application/test_write_cli_dispatch.py -v
pyright dayu/cli/ <all changed tests>
ruff check --select F,I <changed paths>
Ruff full-rule finding-code multiset vs HEAD 1d0f9e6 → positive delta 0
git diff --check
```

结构/行为门禁：

- AST 验证原 83 函数按 owner 为 `22/26/12/11/12`，无 missing、extra、
  overlap；主模块 FunctionDef exact40、ClassDef0，旧定义 exact0。
- helpers ClassDef exact2、七个常量 exact7；`_DATA_SOURCE_BINDING_CANDIDATES`
  的存量 `object` semantic occurrence 1→1。
- 主模块从五 owner 的 functional binding exact45，分布 `6/18/6/9/6`，
  identity exact45；其他迁移函数 compatibility binding exact0。
- `research_template.py.__all__` exact55，删除集与 item 9d exact13 一致；五个
  private owner `__all__` 定义 exact0。
- 用 AST free-global/call graph 验证 item 9b 的全部允许边，任何反向/额外边为
  失败；同进程 import smoke 覆盖 main、五 owner 与 `write.py`。
- `write.py` 旧 lazy owner 路径 exact0，新 materialize owner 路径 exact1；
  真实 write materialization caller 测试保持通过。
- 去除 docstring 后，对 83 函数、2 dataclass 与 39 retained runner/global
  lookup 做迁移前后 AST/行为证据；JSON、ID、duplicate、BOM、validation、
  rollback 与 materialization 行为 corpus 不变。
- 使用足够的现有真实 caller corpus逐文件计算
  `research_template.py` 与五个新 production owner，以及因 lazy import 修改的
  `write.py` 精确 statement coverage，七个修改生产文件均 `>=80%`；不得使用
  seam/pragma/noqa/dummy branch 提升覆盖率。
- tests 若只迁 owner/import/patch 且入口、分层和运行命令不变，
  `tests/README.md` 不更新；CLI private owner 拆分不改变用户命令/参数时根
  `README.md` 不更新。若实际入口或稳定架构说明改变，才按 AGENTS 职责最小同步。

**Non-goals**: 不提前实施 Slice 10 dispatch/type propagation、Slice 11 adapter、
Slice 12 report、其他 helper 重构或 public compatibility facade。

---

### Slice 10: C2 — Protocol dispatch + argument type ownership（C4-01）

**Slice 9 handoff**: `ResearchTemplate` 与
`ResearchTemplateRecommendation` 已在 Slice 9 迁至
`_research_template_helpers.py`；Slice 10 不得再次迁移、复制或在
`research_template.py` 建立 compatibility binding。Slice 10 的类型传播目标仍为
retained `run_research_template_command` + 39 runners，数量与签名责任不变。

**基线**：clean HEAD `e329992`。Slice 10 必须在同一原子 commit 完成 runtime
arguments owner、42 个 args 签名 + 1 个 parse return、selector、mapping 与入口行为
回归，不允许留下临时兼容层。

**原子新建 `dayu/cli/arguments.py`**：本 Slice 是该文件与
`DayuCliArguments` 的唯一创建 owner。模块只能 import 标准库，不得 import 任何
`dayu.cli` 模块：

```python
import argparse
from typing import Protocol


class ResearchTemplateDispatchArguments(Protocol):
    """声明 research-template selector 读取的 consumer 最小字段。"""

    research_template_action: str


class DayuCliArguments(argparse.Namespace):
    """声明 argparse producer 写入字段并提供稳定运行时类型身份。"""

    research_template_action: str
```

定义顺序必须是 Research Protocol → Dayu concrete class。Protocol 是 selector 的
consumer 最小契约；Dayu 是 parser namespace producer，显式声明 parser 会写入的
selector 字段，并通过 structural subtyping 满足 Protocol。`DayuCliArguments` 只继承
`argparse.Namespace`，不得继承任何 Protocol；它不是 type alias、wrapper 或
compatibility facade。Slice 10 类体必须有 exact1 个无默认值 `AnnAssign`，不得新增
`__init__`。禁止用 `cast`、`type: ignore`、字符串 forward reference、adapter 或 glue
转换伪造返回类型；表外 argparse 字段不因本 Slice 被机械加入 Dayu 类。

**`parse_arguments` 运行时构造契约**：

```python
def parse_arguments() -> DayuCliArguments:
    return _create_parser().parse_args(namespace=DayuCliArguments())
```

该调用必须返回真实子类实例；不能仅修改返回注解而继续返回普通
`argparse.Namespace`。新模块必须有完整中文概览 docstring；两个新类型有中文类
docstring；修改后的 `parse_arguments` 保持完整中文 Args/Returns/Raises docstring。

**Selector helper**（Protocol 实际被调用，非装饰；S10-CTRL-04 exact contract）:
```python
def _resolve_research_template_action(args: ResearchTemplateDispatchArguments) -> str:
    """规范化 research-template action，同时保留入口的防御性兼容语义。

    Args:
        args: 提供 research-template action 的类型化参数对象。

    Returns:
        去除首尾空白并转换为小写的 action；缺字段或空值返回空字符串。

    Raises:
        本函数不显式抛出异常。
    """
    return str(getattr(args, "research_template_action", "") or "").strip().lower()
```

这里的 `getattr` 是唯一、精确、有界的 selector 例外：它忠实保留 HEAD 对缺字段、
`None` 与非字符串值先 `str(...)` 再规范化的 defensive 语义，不能扩展成一般反射式
参数访问。`ResearchTemplateDispatchArguments` 仍是正常调用路径的静态类型边界。
selector 是 Slice 10 的明确 deliverable，但不是 `DayuCliArguments` args 签名传播项，
因此不计入下方 42 个签名。

**同 commit 的机械类型传播（唯一 owner）**：

| 模块 | 精确目标 | Slice 10 前 | Slice 10 后 |
|---|---|---|---|
| `dayu/cli/arg_parsing.py` | `parse_arguments()` 返回类型与 runtime namespace | `argparse.Namespace` | `DayuCliArguments` |
| `dayu/cli/commands/research_template.py` | `run_research_template_command` | `argparse.Namespace` | `DayuCliArguments` |
| `dayu/cli/commands/research_template.py` | 下方 39-key mapping 对应的全部 39 个 `_run_*` runner | `argparse.Namespace` | `DayuCliArguments` |
| `dayu/cli/commands/write.py` | `run_write_command` | `argparse.Namespace` | `DayuCliArguments` |
| `dayu/cli/commands/_write_config_application.py` | `_build_fresh_application_routing_snapshot` | `argparse.Namespace` | `argparse.Namespace`（下层基础设施，保持不变） |
| `dayu/cli/commands/_write_config_application.py` | `_run_write_model_configuration_application` | `argparse.Namespace` | `DayuCliArguments` |
| `dayu/cli/commands/_write_snapshot_builder.py` | `_build_snapshot_for_args`、`build_snapshot_builder` | `argparse.Namespace` | `argparse.Namespace`（下层基础设施，保持不变） |

上述 42 个 `args` 签名（research entry 1 + research runners 39 + write entry 1 +
config application runner 1）与 1 个 `parse_arguments` 返回签名由 Slice 10 唯一负责，
不留给 Slice 11。直接调用这 42 个目标的 tests 必须在同 commit 改为构造真实
`DayuCliArguments`；直接调用三个宽 snapshot helper 的 tests 继续构造真实
`argparse.Namespace`，禁止 blanket fixture 迁移或 cast/glue。
selector helper 另行作为 Slice 10 deliverable 实现，其 Protocol 参数不改变
“42 args + 1 return”的传播计数；39 runners 内部表外 helper/`getattr` 保持原样。

**S10-CTRL-06 分层边界**：`_build_fresh_application_routing_snapshot` 最终把 args
交给 `setup_write_config(args: argparse.Namespace, ...)`，另外两个 snapshot helper
仅捕获/透传该值；三者都不读取 `research_template_action` 或未来 Write Protocol 字段，
因此终态精确保持 `argparse.Namespace`。`DayuCliArguments` 是 Namespace 子类，
`_run_write_model_configuration_application(args: DayuCliArguments)` 可安全调用宽 helper。
`_run_write_model_configuration_rollback` 与 `_write_manual_recovery.py` 的 exact15 个
functions 全部保持 Namespace，不纳入本 Slice 传播。

**Callable 类型事实**：`Callable` 的参数类型是逆变的，因此一个接受较宽
`argparse.Namespace` 的 runner 理论上可赋给
`Callable[[DayuCliArguments], int]`；本计划仍将 39 个 runner 机械收窄，是为了
终态 API 一致、owner 清晰与 targeted rg 可审计，不得把相反的协变/逆变论断写成
迁移必要性。

**Dispatch mapping — 39 条目完整列表**:
```python
_RESEARCH_TEMPLATE_ACTION_DISPATCH: Final[Mapping[str, Callable[[DayuCliArguments], int]]] = {
    "list": _run_list,
    "show": _run_show,
    "scorecard": _run_scorecard,
    "evidence": _run_evidence,
    "schema": _run_schema,
    "checklist": _run_checklist,
    "materialize-checklist": _run_materialize_checklist,
    "copy": _run_copy,
    "recommend": _run_recommend,
    "compose": _run_compose,
    "monitoring-rules": _run_monitoring_rules,
    "research-workbook": _run_research_workbook,
    "validate-research-workbook": _run_validate_research_workbook,
    "update-research-workbook": _run_update_research_workbook,
    "rollback-research-workbook": _run_rollback_research_workbook,
    "source-map": _run_source_map,
    "validate-source-map": _run_validate_source_map,
    "package-manifest": _run_package_manifest,
    "materialize": _run_materialize,
    "refresh-workspace": _run_refresh_workspace,
    "list-bundles": _run_list_bundles,
    "validate-bundle": _run_validate_bundle,
    "rebind-bundle": _run_rebind_bundle,
    "rollback-bundle-rebind": _run_rollback_bundle_rebind,
    "monitoring-plan": _run_monitoring_plan,
    "validate-monitoring-plan": _run_validate_monitoring_plan,
    "list-monitoring-plans": _run_list_monitoring_plans,
    "monitoring-status": _run_monitoring_status,
    "workbook-status": _run_workbook_status,
    "workbook-report": _run_workbook_report,
    "validate-workbook-report": _run_validate_workbook_report,
    "workbook-report-status": _run_workbook_report_status,
    "materialize-portfolio": _run_materialize_portfolio,
    "preview-portfolio": _run_preview_portfolio,
    "scheduler-manifest": _run_scheduler_manifest,
    "validate-scheduler-manifest": _run_validate_scheduler_manifest,
    "source-bindings": _run_source_bindings,
    "rollback-source-bindings": _run_rollback_source_bindings,
    "source-binding-history": _run_source_binding_history,
}
```

**入口函数**:
```python
def run_research_template_command(args: DayuCliArguments) -> int:
    """分派 research-template 子命令并保持既有错误边界。

    Args:
        args: 已由 argparse 解析的 CLI 参数。

    Returns:
        runner 的退出码；未知 action 或已知输入/文件异常返回 1。

    Raises:
        runner 抛出的非 FileNotFoundError、FileExistsError、ValueError 异常原样传播。
    """
    setup_loglevel(args)
    action = _resolve_research_template_action(args)
    try:
        runner = _RESEARCH_TEMPLATE_ACTION_DISPATCH.get(action)
        if runner is None:
            return 1
        return runner(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"research-template error: {exc}", file=sys.stderr)
        return 1
```

`try` 必须覆盖 mapping lookup、未知 action 分支与 runner 调用；
`setup_loglevel(args)` 和 selector 调用顺序不得移动。入口禁止 import/引用 `Log` 或
`MODULE`，禁止新增未知 action 输出，也禁止 `return 2`。

**同步新增/迁移测试**（C4-01 + S10-CTRL-01/02）:

- 39-key parser→selector→runner 参数化矩阵：每个 action key 都有对应 mapping
  条目且 runner callable 可调用；patch 目标为 `research_template.py` mapping。
- monkeypatch `sys.argv` 为一个当前真实、最小有效的 write 命令（例如
  `dayu-cli write --summary`），调用真实 `parse_arguments()`，断言
  `isinstance(result, DayuCliArguments)`、`result.command == "write"`、
  `result.summary is True`，并断言至少一个 argparse 默认字段仍存在且值不变，证明
  `namespace=` 没有丢失 parser 写入字段。
- 对 39 runners、write entry 与 config application runner 的既有 direct tests 同步
  改用真实 `DayuCliArguments`；三个宽 snapshot helper 的 direct tests 保持真实
  `argparse.Namespace`。测试行为断言不变。
- direct fixture owner 清单至少覆盖
  `tests/cli/test_research_template_command.py`、
  `tests/cli/test_research_template_definitions.py`、
  `tests/application/test_write_cli_dispatch.py`、
  `tests/application/test_write_challenger.py`、
  `tests/engine/test_cli_running_config.py` 与
  `tests/application/test_write_model_configuration_preapplication.py`；实施时以 AST/`rg`
  对 42 个 Dayu 目标函数和 3 个 Namespace helper 的全部直接调用分别复核，不得
  blanket 改动表外 Namespace fixture。`test_write_model_configuration_preapplication.py`
  中 application runner fixture 迁 Dayu，但 snapshot callback/helper fixtures 保持
  Namespace。
- 新增入口行为矩阵：未知 action 必须 stdout/stderr 均为空且返回 `1`；mapping runner
  分别抛出 `FileNotFoundError`、`FileExistsError`、`ValueError` 时，逐项断言 stderr
  精确为 `research-template error: {exc}\n` 且返回 `1`；selector 对缺字段、`None`
  与非字符串值的结果必须与 HEAD 相同。

验证：`pytest -k "research_template or write_cli_dispatch or cli_running_config"` +
`pyright dayu/cli/`。逐个实际 modified production file 的精确 statement coverage 必须
`>=80%`：预期为 `arguments.py`、`arg_parsing.py`、`research_template.py`、`write.py`、
`_write_config_application.py`；`_write_snapshot_builder.py` 在三签名/import 精确恢复
HEAD 后若 `git diff --name-only HEAD -- <path>` 为零，则不属于本 Slice modified-file
coverage gate；若仍有任何真实 diff，则必须同样达到 `>=80%`，不得机械豁免。
Targeted gates：

```text
rg 'def parse_arguments\(\) -> argparse\.Namespace' dayu/cli/arg_parsing.py
rg '^def run_write_command\(args: argparse\.Namespace\)' dayu/cli/commands/write.py
rg '^def (run_research_template_command|_run_[a-z0-9_]+)\(args: argparse\.Namespace\)' dayu/cli/commands/research_template.py
```

以上三个 targeted 旧签名命中均为 0。另以 AST 精确断言
`_run_write_model_configuration_application.args` 为 `DayuCliArguments`；
`_build_fresh_application_routing_snapshot.args`、`_build_snapshot_for_args.args`、
`build_snapshot_builder.args` 均为 `argparse.Namespace`；snapshot-builder 模块
`DayuCliArguments` import/reference 为 0，config-application 模块同时保留真实
`argparse` 与 `DayuCliArguments` imports。rollback runner 与 manual recovery exact15
functions 的 args 仍为 Namespace，且 `pyright dayu/cli/` 为 0 errors。
另以 AST 断言 `arguments.py` 中定义顺序为
`ResearchTemplateDispatchArguments(Protocol)` 后接
`DayuCliArguments(argparse.Namespace)`，两者各 exact1 个同名同类型
`research_template_action: str`；Dayu bases 仅 `argparse.Namespace`，其
`AnnAssign` exact1、赋值默认值 0、`__init__` 0，且
`parse_args(namespace=DayuCliArguments())` 精确 1。Protocol 字段集合必须为 Dayu
字段集合的子集且在本 Slice 两集合精确相等；真实 parse runtime 测试继续断言
`isinstance(result, argparse.Namespace)` 与 `isinstance(result, DayuCliArguments)`。
39-runner gate 必须以 mapping
完整清单或 AST 函数集合为边界，不能错误要求 `research_template.py` 中所有
`argparse.Namespace` 或 `getattr` 命中为 0（表外 `_company_facets_from_args` 仍可
接受宽类型，runner 内部存量 `getattr` 也不属于本 Slice）。另以 AST/聚焦文本门禁
确认 selector exact1、入口 mapping lookup 位于 `try` 内、catch tuple exact、
`Log`/`MODULE`/未知 action 新输出/`return 2` 为 0；39-key mapping 参数化矩阵、未知
action 静默 `1`、三类 caught exception exact stderr 与 selector defensive corpus 全绿。

---

### Slice 11: C3 — Phase-aware Protocol dispatch（C4-01: 引入 adapter 时迁移测试）

#### 11a. `dayu/cli/arguments.py` — WriteDispatchArguments Protocol

Slice 11 在 Slice 10 已原子创建的 `arguments.py` 中新增
`WriteDispatchArguments`，并在既有 `DayuCliArguments` 类体原子追加同名同类型的
exact20 write 字段；不得重复创建/替换 `DayuCliArguments` 或
`ResearchTemplateDispatchArguments`，也不再次承担 Slice 10 的签名传播。
Write Protocol 是 predicate consumer 最小契约，Dayu 是 argparse producer 声明；
两者通过 structural subtyping 对接，禁止 Protocol inheritance。

```python
class WriteDispatchArguments(Protocol):
    """Protocol declaring write dispatch selector fields.

    Only fields used in predicate lambdas are declared.
    Wrong field name → pyright reportAttributeAccessIssue error (§0 Spike 1).
    """
    # boolean selector flags — Phase A
    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    # boolean selector flags — Phase B
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    # boolean selector flags — Phase D/F/G
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    # path-valued selector flags — Phase A
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    # path-valued selector flags — Phase F（v3.6 追加）
    routing_challenger_run_approval_input: str | None
```

上方 Write Protocol 的精确字段数是 **20**：Phase A bool 11 + Phase B bool 2 +
Phase D/F/G bool 3 + Phase A path 3 + Phase F path 1。DeepSeek 103000 中的 22 是
计数误差。Slice 11 必须同时把这 20 个字段原子追加到既有 Dayu 类，终态精确为：

```python
class DayuCliArguments(argparse.Namespace):
    """声明 argparse producer 写入字段并提供稳定运行时类型身份。"""

    # Slice 10 research selector（1）
    research_template_action: str
    # Slice 11 Phase A bool（11）
    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    # Slice 11 Phase B bool（2）
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    # Slice 11 Phase D/F/G bool（3）
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    # Slice 11 Phase A path（3）
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    # Slice 11 Phase F path（1）
    routing_challenger_run_approval_input: str | None
```

Slice 11 终态 Dayu `AnnAssign` exact21（research 1 + write 20）；
`ResearchTemplateDispatchArguments` 与 `WriteDispatchArguments` 的字段并集必须和 Dayu
字段集合精确相等，既不能缺字段，也不能增加 `command` 等表外 argparse 字段。
Dayu bases 仍只含 `argparse.Namespace`，零字段默认值、零 `__init__`、零 Protocol
inheritance/cast/ignore/adapter/glue。表外字段继续由 argparse 动态写入，存量 runner
内部表外 `getattr` 保持不变。

#### 11b. `dayu/cli/commands/_write_dispatch.py` — Phase-specific typed contexts

```python
from dataclasses import dataclass
from collections.abc import Callable
from dayu.cli.arguments import DayuCliArguments, WriteDispatchArguments
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.execution.options import ExecutionOptions


@dataclass(frozen=True)
class _WriteCommandContext:
    """Phase A context: 仅 args + paths_config。

    Phase A 的 14 条目不依赖 execution_options。
    条目 9/10/14（clear/verify/recover）的 adapter 内部惰性调用
    _build_execution_options(ctx.args)，与 HEAD 5821014 历史现状行
    4747/4759/4807 一致；当前验收使用§1.3结构锚点。
    """
    args: DayuCliArguments
    paths_config: WorkspaceConfig


@dataclass(frozen=True)
class _WriteConfigurationContext:
    """Phase B context: 含预计算的 execution_options。

    run_write_command 在 Phase A 未命中后，按现状顺序 resolve
    model override + build execution options 各一次，创建此 context。
    Phase B 的 2 个 adapter 从 config_ctx.execution_options 读取，
    绝不重算 _build_execution_options。
    """
    args: DayuCliArguments
    paths_config: WorkspaceConfig
    write_model_override_name: str
    execution_options: ExecutionOptions


@dataclass(frozen=True)
class _EarlyWriteSubcommandEntry:
    """Phase A dispatch 条目。runner 接受 _WriteCommandContext。"""
    predicate: Callable[[WriteDispatchArguments], bool]
    runner: Callable[[_WriteCommandContext], int]


@dataclass(frozen=True)
class _ConfigurationWriteSubcommandEntry:
    """Phase B dispatch 条目。runner 接受 _WriteConfigurationContext。"""
    predicate: Callable[[WriteDispatchArguments], bool]
    runner: Callable[[_WriteConfigurationContext], int]
```

#### 11c. 完整 Action Inventory 表

下表 `Src Line` 只是 HEAD 5821014 历史映射，不是当前 worktree
验收行号。历史结果必须通过 `git show` 复现；当前 HEAD `1d0f9e6` 使用
§1.3 的 AST 锚点命令，Slice 11 实现后使用 phase 表 14+2 结构测试：

```bash
git show 5821014:dayu/cli/commands/write.py \
  | rg -n "getattr" \
  | awk -F: '$1 >= 4637 && $1 <= 4822'
```
**历史真实输出: 16 行**（Phase A:14 + Phase B:2）。

| # | Src Line (HEAD 5821014 historical) | Phase | Predicate Field | Type | Adapter | Adapter-Lazy Compute |
|---|---|---|---|---|---|---|
| 1 | 4637 | A | `revalidate_...incident_dossier` | `bool` | `_run_incident_dossier_revalidation_adapter` | — |
| 2 | 4653 | A | `inspect_...incident` | `bool` | `_run_incident_dossier_adapter` | — |
| 3 | 4669 | A | `audit_...history` | `bool` | `_run_audit_timeline_adapter` | — |
| 4 | 4680 | A | `revalidate_...gate_verification` | `bool` | `_run_gate_revalidation_adapter` | — |
| 5 | 4694 | A | `verify_...gate` | `bool` | `_run_gate_verification_adapter` | — |
| 6 | 4705 | A | `check_...gate` | `bool` | `_run_gate_check_adapter` | — |
| 7 | 4716 | A | `revoke_...clearance` | `bool` | `_run_clearance_revocation_adapter` | — |
| 8 | 4727 | A | `restart_...after_...revocation` | `bool` | `_run_restart_after_revocation_adapter` | — |
| 9 | 4738 | A | `clear_...recovery` | `bool` | `_run_clearance_adapter` | `_build_execution_options(ctx.args)` |
| 10 | 4750 | A | `verify_...recovery` | `bool` | `_run_verification_adapter` | `_build_execution_options(ctx.args)` |
| 11 | 4763 | A | `...receipt_input` | `str\|None` | `_run_evidence_adapter` | — |
| 12 | 4777 | A | `...plan_output` | `str\|None` | `_run_plan_adapter` | — |
| 13 | 4791 | A | `...approval_output` | `str\|None` | `_run_approval_adapter` | — |
| 14 | 4803 | A | `recover_...configuration` | `bool` | `_run_recover_adapter` | `_build_execution_options(ctx.args)` |
| 15 | 4811 | B | `apply_...configuration` | `bool` | `_run_apply_adapter` | —（读 `config_ctx.execution_options`） |
| 16 | 4817 | B | `rollback_...configuration` | `bool` | `_run_rollback_adapter` | —（读 `config_ctx.execution_options`） |

#### 11d. Phase 常量表

```python
from collections.abc import Sequence
from typing import Final
from dayu.cli.commands._write_dispatch import (
    _WriteCommandContext, _WriteConfigurationContext,
    _EarlyWriteSubcommandEntry, _ConfigurationWriteSubcommandEntry,
)

_WRITE_PHASE_EARLY_RECOVERY: Final[Sequence[_EarlyWriteSubcommandEntry]] = (
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.revalidate_write_model_configuration_manual_recovery_incident_dossier),
        runner=_run_incident_dossier_revalidation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.inspect_write_model_configuration_manual_recovery_incident),
        runner=_run_incident_dossier_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.audit_write_model_configuration_manual_recovery_history),
        runner=_run_audit_timeline_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.revalidate_write_model_configuration_manual_recovery_gate_verification),
        runner=_run_gate_revalidation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.verify_write_model_configuration_manual_recovery_gate),
        runner=_run_gate_verification_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.check_write_model_configuration_manual_recovery_gate),
        runner=_run_gate_check_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.revoke_write_model_configuration_manual_recovery_clearance),
        runner=_run_clearance_revocation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.restart_write_model_configuration_manual_recovery_after_clearance_revocation),
        runner=_run_restart_after_revocation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.clear_write_model_configuration_manual_recovery),
        runner=_run_clearance_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.verify_write_model_configuration_manual_recovery),
        runner=_run_verification_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool((a.challenger_config_manual_recovery_receipt_input or "").strip()),
        runner=_run_evidence_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool((a.challenger_config_manual_recovery_plan_output or "").strip()),
        runner=_run_plan_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool((a.challenger_config_manual_recovery_approval_output or "").strip()),
        runner=_run_approval_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda a: bool(a.recover_write_model_configuration),
        runner=_run_recover_adapter,
    ),
)


_WRITE_PHASE_CONFIGURATION: Final[Sequence[_ConfigurationWriteSubcommandEntry]] = (
    _ConfigurationWriteSubcommandEntry(
        predicate=lambda a: bool(a.apply_write_model_configuration),
        runner=_run_apply_adapter,
    ),
    _ConfigurationWriteSubcommandEntry(
        predicate=lambda a: bool(a.rollback_write_model_configuration),
        runner=_run_rollback_adapter,
    ),
)
```

#### 11e. 16 个 Adapter 函数

**Phase A adapters（14 个，接受 `_WriteCommandContext`）**:

```python
def _run_incident_dossier_revalidation_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_incident_dossier_revalidation(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_incident_dossier_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_incident_dossier(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_audit_timeline_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_audit_timeline(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_gate_revalidation_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_gate_revalidation(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_gate_verification_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_gate_verification(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_gate_check_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_gate_check(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_clearance_revocation_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_clearance_revocation(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_restart_after_revocation_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_restart(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_clearance_adapter(ctx: _WriteCommandContext) -> int:
    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_clearance(
        args=ctx.args, paths_config=ctx.paths_config,
        execution_options=execution_options)

def _run_verification_adapter(ctx: _WriteCommandContext) -> int:
    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_verification(
        args=ctx.args, paths_config=ctx.paths_config,
        execution_options=execution_options)

def _run_evidence_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_evidence(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_plan_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_plan(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_approval_adapter(ctx: _WriteCommandContext) -> int:
    return _run_write_model_configuration_manual_recovery_approval(
        args=ctx.args, paths_config=ctx.paths_config)

def _run_recover_adapter(ctx: _WriteCommandContext) -> int:
    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_application(
        args=ctx.args, paths_config=ctx.paths_config,
        execution_options=execution_options)
```

**Phase B adapters（2 个，接受 `_WriteConfigurationContext`）**:

```python
def _run_apply_adapter(ctx: _WriteConfigurationContext) -> int:
    return _run_write_model_configuration_application(
        args=ctx.args, paths_config=ctx.paths_config,
        execution_options=ctx.execution_options)

def _run_rollback_adapter(ctx: _WriteConfigurationContext) -> int:
    return _run_write_model_configuration_rollback(
        args=ctx.args, paths_config=ctx.paths_config,
        execution_options=ctx.execution_options)
```

**关键**: Phase B adapter 从 `ctx.execution_options` 读取，**绝不**调用 `_build_execution_options`。`execution_options` 在 `run_write_command` 中计算一次（行 4810 原位置），创建 `_WriteConfigurationContext` 时注入。每条路径 `_build_execution_options` 调用精确一次：Phase A adapter 9/10/14 内部各一次；Phase B `run_write_command` 内一次供两 adapter 共享；未命中 Phase B 后 default/preflight 路径复用同一次计算值。

**同步新增测试**（C4-01）: 16-action parser→predicate→adapter 参数化矩阵。16 selectors = 11 Phase A bool + 3 Phase A path + 2 Phase B bool。三组参数化覆盖全部 adapter：(G1) `test_write_dispatch_phase_a_boolean[selector_field,adapter_fn]` 覆盖 11 bool adapter，其中 clear/verify/recover 额外断言惰性 build；(G2) `test_write_dispatch_phase_a_path[selector_field,adapter_fn]` 覆盖 3 path adapter，断言 nonempty selected + empty skipped + 不 build；(G3) `test_write_dispatch_phase_b[selector_field,adapter_fn]` 覆盖 apply/rollback 两 adapter，断言预计算 context 读取 + 不重算。patch 目标为 `write.py` 中的 adapter 函数和 phase 表。此测试在本 slice commit **独立绿**。

验证: `pytest tests/application/test_write_cli_dispatch.py -v` + `pyright dayu/cli/`。
另以 AST 逐类收集顶层 `AnnAssign`：`ResearchTemplateDispatchArguments` exact1、
`WriteDispatchArguments` exact20、`DayuCliArguments` exact21；两个 Protocol 字段并集
必须是 Dayu 字段子集，且 Dayu 字段集合必须与该并集精确相等（零 extra）。同时断言
Dayu bases 仅 `argparse.Namespace`、字段默认值 0、`__init__` 0、Protocol inheritance 0，
并运行真实 `parse_args(namespace=DayuCliArguments())` + predicate/selector 调用和
`pyright dayu/cli/`，共同验证可实例化、runtime 字段保存与 structural conformance。

#### 11f. `run_write_command` bounded replacement 与 Phase E/F/H 精确保留契约（S11-CTRL-02）

Slice 11 的可执行改动边界只有两部分：

1. 用 11d/11e 的 phase tables 与 adapters 替换 HEAD `8c63d80` 中 Phase A 的
   14 个顶层 `if` 和 Phase B 的 2 个顶层 `if`；
2. 对 Write Protocol exact20 字段的既有 selector 读取改为直接属性访问。

除上述两项外，`run_write_command` 的前缀校验、Phase C–H 控制流、异常边界、
日志、退出码、I/O、变量时序与 table-out `getattr` 必须保持 HEAD。不得从旧的
“完整函数示意”重新生成整个函数；实施时必须以 HEAD 函数为真源，只做下方 bounded
replacement。禁止新建、导入或调用任何用于封装 Phase E 的新 helper。

**唯一 Phase A/B replacement**：从第一个调用
`_run_write_model_configuration_manual_recovery_incident_dossier_revalidation`
的顶层 `if` 起，到调用 `_run_write_model_configuration_rollback` 的顶层 `if`
止，精确替换为：

```python
phase_a_ctx = _WriteCommandContext(args=args, paths_config=paths_config)

# Phase A: Early Manual Recovery（14 条目，顺序与 HEAD 一致）
for entry in _WRITE_PHASE_EARLY_RECOVERY:
    if entry.predicate(args):
        return entry.runner(phase_a_ctx)

# Phase A 未命中后才解析模型覆盖并构造一次 execution options
write_model_override_name = _resolve_write_model_override_name(args)
execution_options = _build_execution_options(args)
phase_b_ctx = _WriteConfigurationContext(
    args=args,
    paths_config=paths_config,
    write_model_override_name=write_model_override_name,
    execution_options=execution_options,
)

# Phase B: Configuration（2 条目）
for entry in _WRITE_PHASE_CONFIGURATION:
    if entry.predicate(args):
        return entry.runner(phase_b_ctx)
```

Phase A adapter 9/10/14（clear/verify/recover）各自惰性调用
`_build_execution_options(ctx.args)` exact1；其他 11 个 Phase A adapter 为 0。
Phase B adapter 只读取 `ctx.execution_options`，调用
`_build_execution_options` 为 0。Phase A 未命中后，`run_write_command` 的共享
build exact1 同时供 Phase B 与未命中 Phase B 后的 Phase C–H 使用。因此每条真实
路径仍精确构造一次 execution options，不得提前、重复或在 adapter 间共享可变状态。

**exact20 selector 的直接属性边界**：

| 阶段 | Slice 11 允许的直接属性 |
|---|---|
| Phase A/B predicates | 11 个 Phase A bool、3 个 Phase A path、2 个 Phase B bool |
| Phase C | `args.summary` |
| Phase D | `args.preflight_only` |
| Phase F | `args.routing_challenger_run_approval_input` |
| Phase G | `args.summary`、`args.reprice_costs` |
| Phase H | `args.preflight_only` |

Phase C/D 的注释与契约均为“语义不变，exact20 selector 随 Protocol 改为直接属性”。
Phase G/H 除上表字段外，`output`、routing/proposal/config-change 路径、
`infer`、`materialize_research`、preflight/rollback 输入输出等所有 table-out
argparse 字段继续使用 HEAD 的 `getattr` 与原默认值。不得把这些字段加入
`WriteDispatchArguments` 或 `DayuCliArguments`，也不得 blanket 改成直接访问。
Dayu 终态仍为 exact21 AnnAssign（research 1 + write 20）。

**Phase E 精确保留**：该阶段不是 Slice 11 helper-extraction scope。下列 inline
结构、动态字段 inventory、调用、验证、异常与返回必须和 HEAD `8c63d80` 一致；
其中存量局部 `dict[str, Any] | None` 语义 1→1 保留，不属于新增 API 或类型扩散：

```python
challenger_run_plan: dict[str, Any] | None = None
challenger_run_plan_required = any(
    bool(str(getattr(args, attribute, "") or "").strip())
    for attribute in (
        "routing_challenger_run_plan_output",
        "routing_challenger_run_approval_request",
        "routing_challenger_run_approval_output",
        "routing_challenger_run_approval_input",
    )
)
if challenger_run_plan_required:
    try:
        challenger_run_plan = _build_challenger_run_plan_from_args(
            args=args,
            paths_config=paths_config,
            write_model_override_name=(write_model_override_name),
        )
        _assert_challenger_run_output_boundaries(
            plan=challenger_run_plan,
            workspace_dir=paths_config.workspace_dir,
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Challenger 双跑计划无效: {exc}",
            module=MODULE,
        )
        return 2
```

不得删除四字段 `any()`、不得把 `getattr` 改成 table 外直接访问、不得省略
`_assert_challenger_run_output_boundaries`，也不得改变 5 类异常、日志或 `return 2`。

**Phase F fail-loud 不变量**：selector 已进入 Write Protocol，故只允许把 selector
读取改为直接属性；HEAD 的 `assert`、验证调用与退出码必须保留：

```python
if bool((args.routing_challenger_run_approval_input or "").strip()):
    assert challenger_run_plan is not None
    run_approval_exit_code = _verify_and_consume_challenger_run_approval_before_host(
        args=args,
        paths_config=paths_config,
        execution_plan=challenger_run_plan,
    )
    if run_approval_exit_code != 0:
        return run_approval_exit_code
```

禁止把 `assert` 改为
`challenger_run_plan is not None and ...` 的 fail-silent guard。新增真实不变量测试
必须让 approval selector 非空、first build 返回 `None`、boundary stub 不抛异常，
并断言 Phase F 触发 `AssertionError`，从而区分两种语义。

**Phase H 异常与 partial-success 不变量**：Phase H 整体保留 HEAD executable
structure，并复用 Phase A 后唯一一次计算的 `execution_options` 与
`write_model_override_name`。下列三组边界不得遗漏：

1. 在 main challenger 路径中，`challenger_run_plan is not None` 时二次调用
   `_build_challenger_run_plan_from_args`；捕获
   `(FileNotFoundError, OSError, TypeError, ValueError)`，记录
   `Challenger 双跑计划复核失败: {exc}` 并返回 2；随后仍比较
   `current_plan != challenger_run_plan`，不一致时记录原消息并返回 2。
2. preflight challenger 与 main challenger 的两个
   `_build_challenger_write_config` 调用点均继续只捕获 `ValueError`，记录
   `str(exc)` 并返回 2；不得移除任一 try/except。
3. 写作已成功后，`_materialize_research_after_write` 继续捕获
   `Exception`（保留现有 BLE001 理由与 partial-success 语义），记录
   `研究工件 materialize 失败: {type(exc).__name__}: {exc}` 并返回 2；不得让异常
   逃逸或把已写报告误报为 exit 1。

Phase H 变量名精确保持 `write_exit_code`；后续判断、默认 runner 结果与
materialize 成功路径都使用该名称，不得恢复旧示意中的 `write_exit`。Phase E/H
的 `_build_challenger_run_plan_from_args` 调用时序仍为 Host 初始化前一次、需要复核
时 Host 初始化后一次；未请求计划时为 0。

**测试与结构门禁**：

- 16-action parser→predicate→adapter 矩阵继续使用 11e 的 G1/G2/G3：
  Phase A bool exact11、Phase A path exact3、Phase B bool exact2；验证表顺序、
  predicate、adapter identity、非空/空 path、惰性 build 与预计算 context。
- 新增 Phase E 真实回归：四个 required field 任一非空时 build + boundary assert
  各 exact1；全空时两者均为 0；5 类异常分别记录原错误并返回 2。
- 新增 Phase F fail-loud `AssertionError` 回归；不得用静默 guard 关闭该不变量。
- 新增 Phase H 回归：plan rebuild 四类异常、preflight/main 两个 challenger-config
  `ValueError` 分支、materialize 任一代表性 `Exception` 的 partial-success
  `return 2` 与精确日志。保留既有 mixed-priority 与 Phase C–H order tests。
- AST 断言 phase table 长度为 exact14/2、adapter 为 exact14/2、lambda runner 为 0；
  `run_write_command` 顺序为 A loop → resolve override → shared build →
  configuration context → B loop → Phase C–H。
- 全仓生产源码不得定义或调用任何额外 Phase E wrapper/helper；master plan 当前
  Slice 11 contract 同样不得再引用不存在的 Phase E helper。Phase E inline AST
  必须与 `git show 8c63d80:dayu/cli/commands/write.py` 对应 subtree 相同。
- AST 精确断言 Phase F direct selector + `assert`；Phase H 三组异常边界与
  `write_exit_code`；Phase C/D exact20 direct selector；table-out `getattr`
  inventory 相对 HEAD 不减少或扩散。
- `_build_execution_options` 路径计数：Phase A lazy adapter 9/10/14 各 exact1；
  Phase B adapter 0；A 未命中后的共享 build exact1，供 Phase B 与后续路径复用。
- Arguments AST：Research Protocol exact1、Write Protocol exact20、Dayu exact21，
  Protocol union 与 Dayu fields 精确相等，零 extra/default/`__init__`/Protocol
  inheritance。
- 验证至少包含
  `pytest tests/application/test_write_cli_dispatch.py tests/engine/test_cli_running_config.py -q`
  与相关 application `test_write*.py` caller corpus；`pyright dayu/cli/` 和修改
  tests 为 0 errors；Ruff F/I 与 HEAD full-rule finding-code multiset positive
  delta 为 0。
- `arguments.py`、新 `_write_dispatch.py`、`write.py` 等所有实际修改生产文件
  的精确 statement coverage 均 `>=80%`；若某文件最终对 HEAD 零 diff 才可不纳入。
- tests 入口语义从 if-chain 迁为 phase-table 后同步 `tests/README.md`；根 README
  仅在用户命令/参数/调用方式实际变化时更新，`dayu/README.md` 仅在稳定分层边界
  发生变化时更新。
- `git diff --check`、import smoke、零 reverse import/cycle、无新增
  `Any`/`object`/`cast`/`type: ignore`/`noqa`/glue/compat 全部通过。

**Stop condition**：若 HEAD 的 16 inventory、adapter target、Phase E/F/H AST、
异常集合、变量时序、真实 test owner 或 exact coverage 门槛与本节仍有不一致，
implementation agent 必须在编辑前停止并向 Controller 提交直接证据；不得自行发明
helper、改变错误边界、扩大 Dayu 字段或提前实施 Slice 12/13。

---

### Slice 12: C4 — print_report 拆分

**保留公开 API 签名**（HEAD 5821014 现存，15 total = `output_dir` positional + 14 keyword）:

```python
@staticmethod
def print_report(
    output_dir: str | Path,
    *,
    model_catalog: Mapping[str, Mapping[str, object]] | None = None,
    routing_history_root: str | Path | None = None,
    routing_proposal_input: str | Path | None = None,
    routing_proposal_output: str | Path | None = None,
    overwrite_routing_proposal: bool = False,
    routing_preflight_approval_request: str | Path | None = None,
    routing_preflight_approval_output: str | Path | None = None,
    challenger_promotion_proposal_input: str | Path | None = None,
    challenger_promotion_proposal_output: str | Path | None = None,
    challenger_config_change_request_input: str | Path | None = None,
    challenger_config_change_request_output: str | Path | None = None,
    challenger_config_change_approval_request: str | Path | None = None,
    challenger_config_change_approval_output: str | Path | None = None,
    challenger_config_change_approval_input: str | Path | None = None,
) -> int:
```

**`Mapping[str, Mapping[str, object]]` 说明**: 此为 HEAD 5821014 现存的公开 API 签名，本 plan **保留不改**。该类型通过 `model_catalog` 参数传播至 `_write_report.py` 的 row 2 (`_print_repriced_comparison`) 和 row 8 (`_handle_health_trend_and_proposal_and_preflight`) 两个内部 helper——这些 helper 接收由公开 `print_report` 入口传入的同一 `model_catalog` 值（来源为 `config_loader.load_llm_models()`），在 Python 类型系统内无法不经 `cast`/`type: ignore` 收窄为 `Mapping[str, Mapping[str, ModelConfigJsonValue]]`。其余 6 个 `_write_report.py` helper 不使用 `model_catalog`，零 `object` 类型。此例外已记录在 §4.3 例外 (b)。

**`_write_report.py` 8 个子流程函数（精确签名表格，零 `...` 占位）**:

| # | 函数 | 精确签名 | 职责 |
|---|---|---|---|
| 1 | `_validate_print_report_gate_conditions` | `(*, routing_preflight_approval_request: str \| Path \| None, routing_preflight_approval_output: str \| Path \| None, routing_proposal_input: str \| Path \| None, routing_proposal_output: str \| Path \| None, routing_history_root: str \| Path \| None, challenger_promotion_proposal_input: str \| Path \| None, challenger_promotion_proposal_output: str \| Path \| None, challenger_config_change_request_input: str \| Path \| None, challenger_config_change_request_output: str \| Path \| None, challenger_config_change_approval_request: str \| Path \| None, challenger_config_change_approval_output: str \| Path \| None, challenger_config_change_approval_input: str \| Path \| None) -> int \| None` | 步骤 3：参数互斥/组合校验。纯逻辑，无 I/O。返回 None=通过 |
| 2 | `_print_repriced_comparison` | `(output_dir: str \| Path, model_catalog: Mapping[str, Mapping[str, object]] \| None) -> None` | 步骤 4：成本重估 + 运行比较打印。**不含步骤 1**——步骤 1 (`print_write_report`) 由 `print_report` 入口原位执行。成本重估失败仅打印 warning 并继续，**永不改变控制流**（返回 `None`）——与 HEAD 行为一致。`model_catalog` 的 `object` 属 §4.3 传播例外 (b) |
| 3 | `_handle_promotion_proposal_export` | `(output_dir: str \| Path, challenger_promotion_proposal_output: str \| Path \| None) -> int` | 步骤 5a：导出 Challenger 晋升提案。返回 0/2/4 |
| 4 | `_handle_promotion_proposal_verification` | `(challenger_promotion_proposal_input: str \| Path \| None) -> int` | 步骤 5b：验证 Challenger 晋升提案。返回 0/2/4 |
| 5 | `_handle_config_change_request_export` | `(challenger_config_change_request_output: str \| Path \| None, challenger_promotion_proposal_input: str \| Path \| None) -> int` | 步骤 6a：导出配置变更请求 |
| 6 | `_handle_config_change_request_verification` | `(challenger_config_change_request_input: str \| Path \| None) -> int` | 步骤 6b：验证配置变更请求 |
| 7 | `_handle_config_change_approval` | `(challenger_config_change_approval_request: str \| Path \| None, challenger_config_change_approval_output: str \| Path \| None, challenger_config_change_approval_input: str \| Path \| None, challenger_config_change_request_input: str \| Path \| None) -> int` | 步骤 7：签发/验证配置变更批准 |
| 8 | `_handle_health_trend_and_proposal_and_preflight` | `(output_dir: str \| Path, routing_history_root: str \| Path \| None, model_catalog: Mapping[str, Mapping[str, object]] \| None, routing_proposal_output: str \| Path \| None, routing_proposal_input: str \| Path \| None, overwrite_routing_proposal: bool, routing_preflight_approval_request: str \| Path \| None, routing_preflight_approval_output: str \| Path \| None) -> int` | 步骤 8–9：模型健康趋势 + Challenger 提案导出/验证 + preflight approval。`model_catalog` 的 `object` 属 §4.3 传播例外 (b) |

**编排顺序**: `print_report` 入口原位执行 `print_write_report`（步骤 1），若返回 2 立即退出 → `_validate_print_report_gate_conditions`（步骤 3）→ `_print_repriced_comparison`（步骤 4，返回 `None`，不影响控制流）→ promotion export/verify（步骤 5）→ config change export/verify/approval（步骤 6–7）→ health+proposal+preflight（步骤 8–9）。返回 `int` 的子流程非 0 时立即传播退出码。

**Slice 0 新增 characterization**: `test_print_report_step1_inline_before_any_helper`（验证步骤 1 在 `print_report` 入口直接调用 `print_write_report`，不经任何 helper）。`test_print_report_step4_only_after_gate`（验证 `_print_repriced_comparison` 仅在 gate 通过后被调用）。`test_print_report_repricing_failure_continues`（验证 cost 重估失败时打印 warning 但继续执行后续步骤，不改变退出码）。

---

### Slice 13: README/Docs 同步 + 最终门禁

更新 `README.md`（确认 `dayu-cli write` 和 `dayu-cli research-template` 命令示例）、`dayu/README.md`（更新 CLI 模块组织说明）、`tests/README.md`（添加 `test_write_cli_dispatch.py`）。

---

## 6. 跨 Slice 排序理由

```
Slice 0 ── characterization（最先，无依赖）
  ├──▶ 1→2A→2B（C5 重构+两段迁移，2A 依赖 1，2B 依赖 2A）
  ├──▶ 3→4（W15/W16 低风险清理）
  ├──▶ 5→6→7→8（C1 四步拆分，Slice 6 组合 commit）
  ├──▶ 9→10（C2 拆分+dispatch）
  ├──▶ 11（C3 typed predicate dispatch）
  ├──▶ 12（C4 print_report 拆分，最后）
  └──▶ 13（docs）
```

---

## 7. 迁移策略

**零兼容转发，全部直接迁移。** 旧定义在原文件删除，新模块创建后主模块通过顶层 import 引用。

---

## 8. 硬约束合规

| 约束 | 合规 |
|---|---|
| 禁止 God file | C1/C2/C4 均以 exact ownership、AST inventory、DAG 与 zero-compat gate 验收；aggregate terminal `write.py=1014`、`research_template.py=1369` 仅为 informational LOC measurement，不是完成门槛 |
| 禁止 God function | W15 内联; W16 提取; W12 functools.partial; C3 runner factory; C4 拆分 |
| 禁止重复逻辑 | C5: 17 共享函数（v4.4） |
| 禁止 Any（新 API） | 零 — `ExecutionOptions` 同 Slice 6 commit；v5.5 fenced block 仅展示 HEAD Phase E 存量局部 `dict[str, Any]` 1→1，非新 API/传播 |
| 禁止裸 object（新 API） | 3 处 §4.3 存量签名例外（公开 API + 2 传播 helper）+ Slice 9 存量数据常量 semantic occurrence 1→1；零新增签名/传播/escape |
| 禁止 getattr（新 API） | 零 — C2 selector exact bounded fallback 1；C3 typed predicate 与 Phase F selector 直接属性；v5.5 仅额外展示 HEAD Phase E 动态四字段 inventory 的存量 `getattr` 1→1 |
| 禁止 hasattr（新 API） | 零 |
| 禁止 type: ignore（新 API） | 零 |
| 禁止 Callable[..., ...]（新 API） | 零 — `Callable[[WriteDispatchArguments], bool]` 等精确签名 |
| 禁止无类型签名 | 零 |
| 禁止嵌套函数 | W15 内联; W16 提取; W12 partial |
| 中文 docstring | 全部 |
| 依赖最小化 | 单向，零循环 |
| 禁止兼容性 re-export | 零过渡期转发 |

---

## 9. 门禁验证清单

### 每个 Slice 本地验证

```bash
source .venv/bin/activate
python -m pytest tests/application/test_write_service.py tests/application/test_write_cli_dispatch.py -v
python -m utils.ci_pr_pyright --base origin/main --head "$(git rev-parse HEAD)"
ruff check dayu/cli/commands/ dayu/services/
```

### 最终门禁（Slice 13，精确复刻 `.github/workflows/ci-pr-required.yml` + `dual-model-gates.yml`）

**门禁 1: Pyright ratchet**（来源 `ci-pr-required.yml:32-36`）:
```bash
python -m utils.ci_pr_pyright --base "$(git merge-base origin/main HEAD)" --head "$(git rev-parse HEAD)"
```

**门禁 2: min-compat 全量测试**（来源 `ci-pr-required.yml:28-39`，Python 3.11）:
```bash
python -m pip install --upgrade pip
pip install -e ".[test,dev,browser,web]" -c constraints/min-py311.txt
pytest -q --timeout=60 -m "not integration and not slow and not e2e"
```

**门禁 3: dual-model gates**（来源 `dual-model-gates.yml:52-81`）:
```bash
pytest -q tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py \
  tests/test_prepare_deepseek_task.py

ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py \
  utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py \
  tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py \
  tests/test_prepare_deepseek_task.py

git diff --check

python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
```

**Python 版本**: 仅 3.11。`ci-pr-required.yml`、`ci-mainline.yml`、`dual-model-gates.yml` 全部 lane 使用 Python 3.11。

### Aggregate pre-deepreview 结构与 Ruff ratchet 门禁（v5.7）

LOC 仅记录当前 measurement（`write.py=1014`、`research_template.py=1369`），不得作为
PASS/FAIL 阈值，也不得把当前数值加余量后改造成新的任意门槛。aggregate 必须在 clean
HEAD 上执行以下精确结构审计：

```bash
python - <<'PY'
import ast
from pathlib import Path

def parse(path: str) -> ast.Module:
    return ast.parse(Path(path).read_text(encoding="utf-8"))

write_tree = parse("dayu/cli/commands/write.py")
write_functions = [
    node.name
    for node in write_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
assert len(write_functions) == 18
assert sum(name.endswith("_adapter") for name in write_functions) == 16
assert set(write_functions) - {name for name in write_functions if name.endswith("_adapter")} == {
    "_materialize_research_after_write",
    "run_write_command",
}
write_tables = {
    node.target.id: node.value
    for node in write_tree.body
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
}
assert set(write_tables) == {
    "_WRITE_PHASE_EARLY_RECOVERY",
    "_WRITE_PHASE_CONFIGURATION",
}
assert isinstance(write_tables["_WRITE_PHASE_EARLY_RECOVERY"], ast.Tuple)
assert len(write_tables["_WRITE_PHASE_EARLY_RECOVERY"].elts) == 14
assert isinstance(write_tables["_WRITE_PHASE_CONFIGURATION"], ast.Tuple)
assert len(write_tables["_WRITE_PHASE_CONFIGURATION"].elts) == 2

research_tree = parse("dayu/cli/commands/research_template.py")
research_functions = [
    node.name
    for node in research_tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
]
assert len(research_functions) == 41
assert "run_research_template_command" in research_functions
assert "_resolve_research_template_action" in research_functions
assert sum(name.startswith("_run_") for name in research_functions) == 39
assert not any(isinstance(node, ast.ClassDef) for node in research_tree.body)
research_annassign = {
    node.target.id: node.value
    for node in research_tree.body
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
}
assert set(research_annassign) == {"_RESEARCH_TEMPLATE_ACTION_DISPATCH"}
dispatch = research_annassign["_RESEARCH_TEMPLATE_ACTION_DISPATCH"]
assert isinstance(dispatch, ast.Dict) and len(dispatch.keys) == 39
research_assign = {
    node.targets[0].id: node.value
    for node in research_tree.body
    if isinstance(node, ast.Assign)
    and len(node.targets) == 1
    and isinstance(node.targets[0], ast.Name)
}
assert set(research_assign) == {"__all__"}
exports = research_assign["__all__"]
assert isinstance(exports, ast.List) and len(exports.elts) == 55
PY

pytest -q tests/application/test_write_cli_dispatch.py \
  tests/cli/test_research_template_command.py \
  tests/application/test_write_service.py
python -m utils.ci_pr_pyright \
  --base "$(git merge-base origin/main HEAD)" \
  --head "$(git rev-parse HEAD)"
git diff --check
python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
```

**Architecture Ruff ratchet（AGG-RUFF-CTRL-01/02）**：baseline 必须是 first
accepted plan commit `f0a3ea1` 的唯一 parent `5821014`。两棵树必须使用相同目录 scope、
相同 Ruff `0.16.1`、相同无显式 rule-select 命令，并把 JSON findings 按 rule code 构造
multiset；`Counter(HEAD) - Counter(BASE)` 必须为空。禁止改用 `origin/main`、current HEAD、
任意 residual baseline 或 changed-lines 推断。

Ruff `0.16.1` 用于精确复现既有 Slice implementation artifacts 与 per-Slice ratchet
multiset，不是 CI 版本。只读 cross-version 复测确认，同一 HEAD/scope 在 Ruff `0.15.11`
无显式 select 时仅产生 exact8（`F401:7`、`F541:1`），而 `0.16.1` 产生 335；因此
constraints/min-py311.txt 的 `0.15.11` 与 architecture ratchet 的 `0.16.1` 不得混用。

scope `dayu/cli/commands/ dayu/services/` 精确覆盖本 master plan 的 C1/C3/C4/C5
production ownership；`dayu/engine/`、`dayu/fins/`、`dayu/host/`、`dayu/config/` 等不属
本 work unit。Architecture baseline 与 origin/main PR residual 都必须使用这一相同 scope；
本计划不声称测量全 repo Ruff 状态。

固定 leaf command 为：

```bash
uv run --no-project --with ruff==0.16.1 ruff check --no-cache \
  --output-format=json dayu/cli/commands/ dayu/services/
```

完整可复现比较命令为：

```bash
set -euo pipefail
cli_arch_repo="$(pwd)"
cli_arch_ruff_tmp="$(mktemp -d)"
trap 'rm -rf -- "$cli_arch_ruff_tmp"' EXIT
mkdir "$cli_arch_ruff_tmp/base"
git archive 5821014 | tar -xf - -C "$cli_arch_ruff_tmp/base"

run_cli_arch_ruff() {
  local tree="$1"
  local output="$2"
  local status
  set +e
  (
    cd "$tree"
    uv run --no-project --with ruff==0.16.1 ruff check --no-cache \
      --output-format=json dayu/cli/commands/ dayu/services/
  ) >"$output"
  status=$?
  set -e
  test "$status" -eq 0 -o "$status" -eq 1
}

run_cli_arch_ruff "$cli_arch_repo" "$cli_arch_ruff_tmp/head.json"
run_cli_arch_ruff "$cli_arch_ruff_tmp/base" "$cli_arch_ruff_tmp/base.json"
python - "$cli_arch_ruff_tmp/head.json" "$cli_arch_ruff_tmp/base.json" <<'PY'
from collections import Counter
import json
from pathlib import Path
import sys

head = Counter(item["code"] for item in json.loads(Path(sys.argv[1]).read_text()))
base = Counter(item["code"] for item in json.loads(Path(sys.argv[2]).read_text()))
positive = head - base
negative = base - head
assert sum(head.values()) == 335, head
assert sum(base.values()) == 364, base
assert not positive, positive
assert negative == Counter({"I001": 11, "TRY004": 17, "UP035": 1}), negative
print("architecture Ruff ratchet PASS: HEAD=335 BASE=364 positive={} negative=29")
PY
```

这里的 “Slice-report full-rule” 指固定 Ruff `0.16.1` 在无显式 `--select` 时使用的
rule set，不是 `--select ALL`；后者在同一 HEAD/scope 得到 `11248`，不得混作该门禁。
`constraints/min-py311.txt` 固定 Ruff `0.15.11`，其实测 exact8 E/F 结果也不能替代上述
architecture ratchet。版本、rule selection、scope 或 Counter 算法任一漂移均视为门禁失败。

**PR-level Ruff residual（AGG-RUFF-CTRL-03）**：以 `origin/main=2115c86` 运行同一
Ruff `0.16.1`/scope/Counter 算法时，HEAD=`335`、BASE=`143`，per-code positive
总计 `216`：`B009:53`、`BLE001:3`、`FURB162:12`、`ISC004:1`、`RUF010:22`、
`RUF022:2`、`SIM102:1`、`TRY004:118`、`UP012:2`、`UP035:2`。该结果不阻断
CLI architecture ratchet，但必须原样进入 aggregate deepreview residual；遗漏、淡化或
把它误称为 CI 已覆盖均阻止 deepreview closeout。`ci-pr-required` 不检查 production
Ruff，本 work unit 不修改 workflow。

### Aggregate Fix RT-01（v5.8，AGG-RT-CTRL-01）

**直接证据与目标**：`_run_validate_source_map` 当前会把
`validate_monitoring_source_map_payload(...)` 返回的 `{"ok": false, ...}` 原样打印到
stdout，却固定返回 `0`。该行为由 `7579e0d` 引入，不在 `origin/main=2115c86`，但早于
architecture baseline `5821014`；Slice 9 的 stripped-docstring AST exact migration 与
Slice 10 的 behavior-preservation 因而忠实保留了这个 PR-level correctness defect。
Aggregate Fix RT-01 的唯一目标是让真实 CLI 退出码与已经打印的校验结果一致。

**允许修改范围**：

- `dayu/cli/commands/research_template.py`；
- `tests/cli/test_research_template_command.py`；
- 本 Aggregate Fix 的 implementation/fix/re-review artifacts。

**精确实现契约**：

```python
def _run_validate_source_map(args: DayuCliArguments) -> int:
    # 既有 rules/source-map 加载、validator 调用与 JSON stdout 保持原顺序、原参数和原格式。
    result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1
```

- 只把既有固定 `return 0` 替换为精确条件表达式
  `return 0 if result.get("ok") is True else 1`；不得改 validator、dispatch mapping、
  action key、owner、DAG、JSON stdout、异常集合或异常传播。
- `_run_validate_source_map` 的完整中文 docstring 只同步真实返回契约：校验成功返回 `0`，
  校验失败返回 `1`；Args/Raises 继续准确描述当前输入和传播异常。
- 在 `tests/cli/test_research_template_command.py` 通过真实
  `run_research_template_command`/`validate-source-map` dispatch 路径新增 invalid payload
  回归：必须调用 `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` 与
  `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 写入 template
  mismatch 文件，经真实 entry 断言返回 `1`，解析 stdout 后断言
  `payload["ok"] is False` 且 `payload["errors"]` 非空。不得手写 payload 或另选不一致
  模式。valid 回归必须用 consumer rules + consumer source-map 的对称构造，继续断言返回
  `0` 与 stdout `ok is True`。
- 这是对 Slice 9 stripped-docstring AST exact migration 与 Slice 10
  behavior-preservation 的唯一有界例外；修后 AST delta 只允许该 Return 与对应 docstring。
  禁止顺手改变其他 38 runner、提取通用 validate wrapper、增加 compatibility/glue、
  新增 Slice 14，或改变 manual recovery application / rollback 使用默认
  `run_label="configuration-application"` 的 v4.9/v5.0 accepted design。
- README decision：根 README 已准确说明 `validate-source-map` 用于一致性校验，但未声明
  失败退出码；本次不修改 README。

**Aggregate Fix 验证**：production 与 tests 字节发生变化后，不得继续复用 Slice 13 的
Python 3.11 full-suite 字节同一性证据；修复与双路 re-review 必须完成以下门禁：

```bash
source .venv/bin/activate

# focused research 与 aggregate behavior suite
pytest -q tests/cli/test_research_template_command.py -k "validate_source_map"
pytest -q tests/application/test_write_cli_dispatch.py \
  tests/cli/test_research_template_command.py \
  tests/application/test_write_service.py

# type 与 architecture Ruff ratchet；Ruff exact baseline/版本/scope/Counter 沿用 v5.7
python -m utils.ci_pr_pyright \
  --base "$(git merge-base origin/main HEAD)" \
  --head "$(git rev-parse HEAD)"
# 复跑本节上方 AGG-RUFF-CTRL-01/02 的 Ruff 0.16.1 完整比较脚本，positive 必须为空。

# Python 3.11 min-compat full suite（必须真实重跑）
python -m pip install --upgrade pip
pip install -e ".[test,dev,browser,web]" -c constraints/min-py311.txt
pytest -q --timeout=60 -m "not integration and not slow and not e2e"

# dual-model focused 699 与三个 JSON machine gates
pytest -q tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py \
  tests/test_prepare_deepseek_task.py
python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
git diff --check
```

修后必须重新执行 DeepSeek + MiMo aggregate deepreview；若任一路提出 accepted finding，
按 aggregate fix → aggregate re-review 闭环。两路复审均 PASS、RT-01 CLOSED、Controller
open High/Medium/Low=`0/0/0` 前，不得创建 accepted deepreview commit 或进入
`ready-to-open-draft-PR`。

此外必须复证既有 owner FunctionDef `22/26/12/11/12`、functional binding
`6/18/6/9/6`、write Phase A/B adapter/table identity、manual→snapshot→application 与
research owner DAG、零反向 import、零 compatibility binding/re-export，以及 Ruff
architecture ratchet 相对 `5821014` 的 positive delta=`0`。任一结构、DAG、identity、
行为测试、Pyright ratchet、architecture Ruff positive delta、machine-readable gate 或
whitespace gate 失败，立即停止，不得进入 aggregate deepreview。LOC measurement 与已记录
的 origin/main PR-level Ruff residual 本身不阻断 architecture validation；但 residual 未被
完整带入 aggregate deepreview 时，必须停止，不得关闭 deepreview gate。

---

## 10. 残余风险

| 风险 | 严重度 | 缓解措施 |
|---|---|---|
| Slice 6 组合 commit 变更量大 | 中 | commit message 明确标注；Slice 0 characterization 安全网。**预估 diff**: `_write_config_application.py` ~140 行 + `_write_snapshot_builder.py` ~50 行 + `write.py` 修改（删除旧定义 ~80 行 + 替换 import/类型注解 ~20 行 + 删除嵌套 ~30 行）≈ **250–350 行**。不可再拆: `_write_snapshot_builder.py` 必须与 `_write_config_application.py` 同 commit 创建以消除反向 import 中间态（R2-01）；`execution_options: Any` → `ExecutionOptions` 必须同 commit 修复以消除 `Any` 中间态（F-06）（V4-04） |
| Slice 6 闭包 #1 若机械调用共享 factory 会形成 application↔builder cycle | 中 | S6-W12-CYCLE-01 锁定同模块 direct `functools.partial` 且不显式绑定 `run_label`；#2–#5 才走 factory。双向 import targeted rg、partial/call 数量、AST 零 nested helper、真实 callback 测试共同门禁；禁止 DI/lazy import/glue |
| Slice 7 runner count 或 patch owner 再次漂移 | 高 | S7-CTRL-01 逐名锁定 manual exact 14 + Phase C gate exact 1，execution exact 2；AST 验证新 owner exact 17 / write 旧定义 0。S7-CTRL-03 区分 direct-definition patch 与 `run_write_command`/dispatch 的 `write.<symbol>` functional-binding patch，并以 exact17 identity 回归防止 blanket 迁移或 compatibility seam |
| Slice 9 一次迁移 83 函数，ownership/import/test owner 易漂移 | 高 | S9-CTRL-01..04 逐名锁定 `22/26/12/11/12`、2 dataclass、7 constants、exact45 functional bindings 与 exact55 `__all__`；AST free-global DAG、去 docstring AST、identity45、真实 owner tests、import smoke 与七个生产文件逐文件 coverage `>=80%` 共同门禁。禁止 preliminary count 推断、compat facade 或跨 commit 中间态 |
| S11 adapter 函数 16 个 | 低 | 每个 3–5 行，命名清晰，职责单一 |
| Slice 10 `DayuCliArguments` runtime identity 或字段写入漂移 | 中 | `parse_args(namespace=DayuCliArguments())` 为唯一构造路径；runtime `isinstance` + command/flag/default 字段保存测试，禁止仅改注解或 cast |
| Slice 10 一次机械传播 42 个 args 签名（research entry+39 runners、write entry、config application runner；另含 `parse_arguments` 返回） | 中 | S10-CTRL-06 按真实 consumer 停止传播；42 个窄目标与 3 个宽 snapshot helper 分组 AST 审计，结合 mapping、pyright `dayu/cli/` 与真实 parser/runtime 测试。Callable 逆变与 Dayu IS-A Namespace 共同保证宽 helper 可安全接收窄入口 |
| Snapshot helper 若错误收窄会向 rollback/manual call chain 扩散 concrete CLI 类型 | 高 | 三 helper 终态精确 `argparse.Namespace`；rollback + manual exact15 保持 Namespace；targeted AST/import gate + full CLI pyright 防止 4 个 `reportArgumentType` 重现。禁止 exact49/全 runner 扩散 |
| Slice 10 mapping 重构漂移 research-template 入口的 silent-unknown/caught-exception 语义 | 高 | S10-CTRL-03 锁定 `setup_loglevel` 顺序、`try` 边界、未知 action 静默返回 1、三类异常 exact stderr + 返回 1；S10-CTRL-04 锁定缺字段/None/非字符串 selector corpus。禁止 `Log`/`MODULE`/新输出/return2 |
| Slice 10/11 Dayu 与 Protocol 结构不闭合，或 nominal Protocol inheritance 导致实例化失败 | 高 | S10-CTRL-05/S11-CTRL-01 锁定 consumer Protocol 与 producer Dayu 的显式字段；Slice 10 exact1，Slice 11 Write exact20/Dayu exact21，字段并集精确相等。AST bases/default/`__init__` 门禁 + isolated instantiation + full `pyright dayu/cli/`；禁止 Protocol inheritance/cast/ignore/adapter/glue/god-bag 扩张 |
| Aggregate Fix RT-01 若扩大为通用 runner 重构或改变输出/异常 | 中 | AGG-RT-CTRL-01 只允许 `_run_validate_source_map` 的单一 Return 与 docstring/真实 CLI 回归；stdout、异常、dispatch、owner/DAG、其他 runner、manual/rollback label 全部冻结。production/tests 字节变化后强制重跑 Python 3.11 full suite 与双路 aggregate re-review |
| origin/main PR-level production Ruff residual 未被 CI required lane 覆盖 | 中 | architecture hard ratchet 用真实 work-unit baseline `5821014` 且 positive `{}`；origin/main 同算法 positive `216` 强制作为 aggregate deepreview residual，逐 code 记录且不得隐藏。本 work unit 不改 CI workflow、不新增 Slice 14；机械 TRY004/B009/FURB162 修复会改变 accepted exception/argparse/timezone 契约，需后续独立治理 |
| `_parse_utc`/`_normalize_now` 未消除重复 | 低 | 明确 defer（Group D），后续独立 plan |
| S12 print_report 测试 1947 行 | 中 | Slice 0 副作用顺序 characterization + 全量测试 |

---

## 11. Ready-for-Review 完成定义

1. [ ] 15 个 Slice（0, 1, 2A, 2B, 3–13），每个恰好一个 accepted commit，通过三项项目门禁
2. [ ] aggregate terminal 精确结构闭合：`write.py` 顶层 FunctionDef exact18（16 adapter + materialize helper + entry）、AnnAssign exact2（Phase A 14 + Phase B 2）、零旧定义与零 compatibility re-export；`research_template.py` 顶层 FunctionDef exact41（entry 1 + Slice 10 selector 1 + runners 39）、AnnAssign exact1（39-key dispatch）、Assign exact1（55-entry `__all__`）、ClassDef0、五 owner functional binding exact45（`6/18/6/9/6`）、其他38 compatibility binding 0。当前 LOC `1014/1369` 仅为 informational measurement，不是完成门槛
3. [ ] `write_service.py` 中 `print_report` ≤ 150 行
4. [ ] `_write_artifact_utils.py` 17 函数（v4.2），全部精确类型，每函数有 Slice 2A/2B eligible caller（不计未跟踪旧草稿）
5. [ ] 19 个 `write_model_*.py` 中 eligible 17 helper 按 Slice 2A/2B 逐文件映射迁移，零重复定义。`validated_fingerprint` 仅族 A/G 迁移，族 B-F 全部保留私有。deferred helper 见 §1.6.6 Group C/D 完整列表，保留原位
6. [ ] `write.py` + `research_template.py` 零嵌套函数
7. [ ] C2 dispatch: `Mapping[str, Callable[[DayuCliArguments], int]]`，`_resolve_research_template_action(args: ResearchTemplateDispatchArguments) -> str` 实际调用 Protocol；selector exact bounded fallback 保留 missing/None/non-str HEAD 语义；入口保持未知 action 静默 `1`、三类 caught exception exact stderr + `1`，零 `Log`/`MODULE`/`return 2`
8. [ ] C3 dispatch: Phase A `_EarlyWriteSubcommandEntry`（`predicate: Callable[[WriteDispatchArguments], bool]` + `runner: Callable[[_WriteCommandContext], int]`）；Phase B `_ConfigurationWriteSubcommandEntry`（`predicate: Callable[[WriteDispatchArguments], bool]` + `runner: Callable[[_WriteConfigurationContext], int]`）
9. [ ] C3 execution_options 每条路径精确一次: Phase A adapter 9/10/14 各惰性 build 一次；Phase B 预计算一次注入 `_WriteConfigurationContext` → adapter 读取；未命中 Phase B 后 default/preflight 复用
10. [ ] C3 零 lambda runner、零闭包 factory、零 `Callable[..., ...]`
11. [ ] Phase F 零 getattr（`args.routing_challenger_run_approval_input` 直接访问）
12. [ ] `print_report` 步骤 1 先于步骤 3，1947 行测试全绿
13. [ ] W12 五处闭包全部闭环且依赖单向：`_write_config_application.py`
    import `_write_snapshot_builder` 为 0、同模块 `functools.partial` 精确 1 且
    不显式绑定 `run_label`；`_write_snapshot_builder.py` 从 application import
    `_build_fresh_application_routing_snapshot` 精确 1 且 import `write.py` 为 0；Slice 6 时 `write.py` 的
    `build_snapshot_builder` 调用精确 4，label 依次为默认、默认、verification、
    clearance；application+write AST 中 nested `_snapshot_builder` 合计 0，
    factory/真实 runner callback tests、pyright、Ruff 与三个生产文件精确 coverage
    `>=80%` 全部通过。后续 Slice 7/8 随 runner 迁移对应 factory call/import
14. [ ] Slice 7 `_write_execution.py` exact 2、`_write_manual_recovery.py`
    exact 15（14 runner + Phase C gate），`write.py` 旧 17 definitions 为 0 且
    正常 import exact 17 functional symbols；direct-owner / dispatch-owner 测试边界、
    identity、manual 三处 factory label、manual→snapshot→config-application 单向 DAG、
    pyright/Ruff 与三个生产文件精确 coverage `>=80%` 全部通过
15. [ ] Slice 9 五 owner 的 FunctionDef exact `22/26/12/11/12`，互斥并集
    exact83；helpers 同时拥有 2 dataclass + 7 constants；Slice 9 当时主模块
    FunctionDef exact40（entry1 + runners39）且 `83+40=123` 的历史闭合保持不变；
    Slice 10 新增 selector 后 aggregate terminal 主模块 FunctionDef exact41、
    ClassDef0/旧83定义0；允许 DAG、functional imports 与 identity
    exact45（`6/18/6/9/6`）、其他38 compatibility binding 0、`__all__`
    exact55/删除exact13、write lazy owner、direct-owner/dispatch-owner tests、
    pyright/Ruff 与七个生产文件精确 coverage `>=80%` 全部通过
16. [ ] Slice 10 原子新建 `dayu/cli/arguments.py`，定义顺序为
    `ResearchTemplateDispatchArguments(Protocol)` →
    `DayuCliArguments(argparse.Namespace)`，两者各显式声明 exact1 个
    `research_template_action: str`，零 import `dayu.cli`；`parse_arguments()` 通过
    `parse_args(namespace=DayuCliArguments())` 返回真实子类实例。Slice 11 新增
    exact20 字段的 `WriteDispatchArguments`，并在既有 Dayu 原子追加同名同类型
    exact20 字段，使 Dayu 终态 exact21；Protocol 字段并集与 Dayu 精确相等、零
    extra，Dayu 零 Protocol inheritance/default/`__init__`
17. [ ] Proposed code 新增 `Any`/`hasattr`/`type:ignore`/`Callable[..., ...]`/lambda runner/闭包 factory 均为 0；v5.5 fenced block 为精确保留 HEAD，仅展示 Phase E 存量局部 `dict[str, Any]` exact1（1→1，非新 API/传播）。`getattr` fenced code 合计 exact2：Slice 10 selector 的有界 defensive fallback exact1 + Phase E 动态四字段 inventory 的存量调用 exact1；runner 内部其他存量表外用法不纳入本 Slice 迁移。`object` 仅 3 处 §4.3 存量签名例外（公开 API + 2 传播 helper）及 Slice 9 存量数据常量 1→1；零新增签名/传播/escape
18. [ ] S0 零空 `pass` 测试
19. [ ] Slice 5 后 `MODULE = "APP.WRITE"` 仅在 `_write_config_helpers.py`
    定义；`_write_params_validation.py`、`write.py` 与 Slice 6/7/8 目标模块
    均无反向 import/cycle
20. [ ] Slice 5 后旧 `write.setup_model_name` monkeypatch 0、新
    `_write_config_helpers.setup_model_name` monkeypatch 13；`write.py` 只保留
    6 个 functional private binding 的 import/monkeypatch/global lookup
    契约与 identity；两个 validator compatibility re-export 为 0，engine
    live-smoke validator direct import 指向 `_write_params_validation`；两个
    新模块仍各 exact 4、合计 exact 8 个定义
21. [ ] `_challenger_requested` 双 owner 回归通过：patch
    `write._challenger_requested` 控制真实 `run_write_command` global
    call sites；patch `_write_params_validation._challenger_requested` 控制真实
    validator 内部调用；零 blanket patch 迁移
22. [ ] Type ownership timeline 无 gap：Slice 0–9（含 Slice 6 四函数）只使用
    当时存在的 `argparse.Namespace`；Slice 10 同 commit 将
    research-template entry + 39 runners、write entry、config application runner
    机械传播到 `DayuCliArguments`；三个 snapshot helper 保持 Namespace，rollback 与
    manual exact15 同样不收窄。runtime isinstance/字段保存、pyright 与 targeted
    AST 全部通过；selector 是额外 deliverable、不计入 args 传播，`parse_arguments`
    return 单独计 1，故 exact 42+1；零 alias/cast/forward-ref/glue
23. [ ] Architecture Ruff ratchet 使用 exact baseline `5821014`、Ruff `0.16.1`、
    无显式 `--select`、scope `dayu/cli/commands/ dayu/services/` 与 JSON rule-code
    Counter：HEAD=`335`、BASE=`364`、positive=`{}`、negative total=`29`
    （`I001:11 / TRY004:17 / UP035:1`），表明本 work unit 实际改善三类 finding。
    `--select ALL`、Ruff `0.15.11` E/F、current HEAD、`origin/main` 与
    changed-lines 均不得替换该 architecture hard gate。`origin/main=2115c86` 同算法
    positive `216` 必须作为 PR-level residual 完整输入 aggregate deepreview；它不阻断
    architecture validation，但遗漏 residual 会阻止 deepreview closeout
24. [ ] Aggregate Fix RT-01 只产生 `_run_validate_source_map` 的精确条件 Return、对应
    中文 Returns docstring 与真实 CLI valid/invalid 回归；invalid 精确使用 financial
    rules + consumer source-map template mismatch，返回 1、stdout `ok is False` 且 errors
    非空；valid 使用 consumer/consumer，返回 0 且 stdout `ok is True`。focused research、aggregate
    behavior suite、pyright、architecture Ruff positive `{}`、真实 Python 3.11
    min-compat full suite、dual-model focused 699、三个 JSON machine gates 与双路
    aggregate re-review 全部通过；其他 runner、stdout/异常、owner/DAG、manual/rollback
    default label 零变化

---

## 12. Proposed Code 自检

**方法 A — fenced Python blocks**（proposed implementation code）:
```bash
sed -n '/^```python$/,/^```$/p' docs/plans/2026-08-07-cli-write-architecture-refactor.md > /tmp/v39_pyblocks.py
```

**方法 B — Slice 12 section 全部 `object` 原始命中**（签名 + 描述全部计入）:
```bash
sed -n '1091,1138p' docs/plans/2026-08-07-cli-write-architecture-refactor.md | grep -on '\bobject\b'
```
**真实输出 7 行**: 相对行 10（公开 API fenced block 内 `print_report` 签名，1 处）· 行 27（说明段落，2 处）· 行 34（row2 `_print_repriced_comparison` 表格行：签名列 1 + 职责描述列 1，共 2 处）· 行 40（row8 `_handle_health_trend_and_proposal_and_preflight` 表格行：签名列 1 + 职责描述列 1，共 2 处）。

**方法 C — 仅类型签名 occurrence**（排除描述列和说明段落）:
- 公开 API `print_report` 签名中 `Mapping[str, Mapping[str, object]]`: **1**
- `_print_repriced_comparison` 签名列中 `Mapping[str, Mapping[str, object]]`: **1**
- `_handle_health_trend_and_proposal_and_preflight` 签名列中 `Mapping[str, Mapping[str, object]]`: **1**
- **类型签名合计: 3**

**结果表**:

| Token | 来源 | 原始 grep 命中 | 类型签名 occurrence | 判定 |
|---|---|---|---|---|
| `object` | py blocks | — | 1 | `print_report` 保留公开 API 签名 |
| `object` | Slice12 表格签名列 | — | 2 | row2 + row8 传播例外 helper |
| `object` | Slice12 描述/说明 | — | — | 不计入 proposed signature（解释性文本） |
| **`object` 合计** | | **7**（原始 grep） | **3**（类型签名） | §4.3 已声明例外 |
| `Any` | py blocks | 1 | — | v5.5 精确保留 HEAD Phase E 存量局部 `dict[str, Any]` 1→1；零新增 API/传播 |
| `getattr(` | py blocks | 2 | — | Slice 10 selector exact bounded fallback 1 + v5.5 Phase E 动态四字段 inventory 存量调用 1 |
| `hasattr(` | py blocks | 0 | — | ✅ |
| `type: ignore` | py blocks | 0 | — | ✅ |
| `Callable[..., ...]` | py blocks | 0 | — | ✅ |
| `lambda`（runner） | py blocks | 0 | — | predicate lambda 在常量表中，非 runner |

---

*本 plan v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS（clean HEAD `4d2535d`；aggregate 双路 deepreview 仅接受 RT-01。AGG-RT-CTRL-01 只授权 `_run_validate_source_map` 以 `result.get("ok") is True` 决定 0/1 退出码，并同步 docstring 与真实 CLI valid/invalid 回归；DeepSeek 初审 L-PLAN-01 已通过锁定 financial rules + consumer source-map template mismatch 与 consumer/consumer valid 对称构造 FIXED/CLOSED，DeepSeek final 与 MiMo initial/final 均 PASS/open0，全部 plan findings CLOSED。stdout、异常、dispatch、owner/DAG、其他 runner 及 manual/rollback default label 均冻结。修后必须重跑 Python 3.11 min-compat full suite、focused/aggregate/pyright/Ruff/machine gates 与双路 aggregate re-review，不新增 Slice 14；Aggregate Fix RT-01 现可实施，但 RT-01 code finding 在 implementation/re-review 前仍 open Medium exact1）。v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS 与更早 accepted 版本保持为历史。*
