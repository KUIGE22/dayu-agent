# Manual-review handoff code final corrective re-review（Terra）

## Scope

- Mode: current changes final corrective re-review
- Role: 独立 Terra reviewer；只复核，不修复、不作 controller 裁决。
- Branch: `feat/investment-agent-acceptance`
- Base: `4d91a16`
- Output file: `docs/reviews/manual-review-handoff-code-final-rereview-terra.md`
- Included scope: 根 `AGENTS.md`/`CLAUDE.md`、accepted manual-review plan 链、Terra source review 与首次 re-review、DeepSeek implementation/review-fix/corrective-fix artifacts；`utils/investment_agent_acceptance.py`、`tests/test_investment_agent_acceptance.py` 的实际 diff，以及 contracts/evaluator 的质量 review 数据路径。
- Excluded scope: 未改动的 contracts/evaluator/dayu/、Slice 4 文档、Slice 5/live；未执行网络、密钥读取、付费、commit 或 push。
- Worktree fact before writing this artifact: 两个修改文件为 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py`；已有五份未跟踪 review artifacts。本文件是本次唯一新增 artifact。

## Findings

### MRH-004-回归-低-implementation artifact 的“corrective fix 后最终”工作树快照遗漏既有 Terra re-review artifact

- **入口/函数**: `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md` 的 Validation 工作树状态声明。
- **文件(行号)**: `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md:166-172`。
- **输入场景**: controller 依据该 implementation artifact 审计 corrective fix 后的实际 allowlist 与未跟踪 review artifacts。
- **实际分支**: artifact 将该状态表述为“corrective fix 后最终”，仅列出 source review、implementation、review-fix、corrective-fix 四份未跟踪文档，遗漏已存在的 `manual-review-handoff-code-rereview-terra.md`。
- **预期行为**: MRH-004 要求 review handoff artifact 如实记录所声明时点的工作树事实，不能省略既有未跟踪 artifact。
- **实际行为**: corrective-fix artifact 的同阶段最终快照已明确列出五份未跟踪文档，其中包含 `manual-review-handoff-code-rereview-terra.md`（`docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md:88-102`）；故 implementation artifact 的“corrective fix 后最终”快照与同一逻辑时点的直接证据矛盾。当前工作树也仍保留该文件。
- **直接证据**: implementation artifact 在最终状态列表中缺少该路径；corrective-fix artifact 的“最终工作树状态（如实）”列有该路径，且当前 `git status --short` 可直接复现其存在。
- **影响**: 不影响生产行为、PII fail-closed 或测试结果；但 controller 不能仅依赖 implementation artifact 完整审计该 gate 的工作树范围，MRH-004 的记录准确性未闭合。
- **建议改法和验证点**: 在后续获授权的 corrective documentation fix 中，将 implementation artifact 声明的“corrective fix 后最终”快照补齐该既有 re-review path，并与 `git status --short` 的同一时点结果逐项对照；本次按用户边界不修改既有 artifact。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Corrective verification

| 项目 | 结论 | 直接证据 |
|---|---|---|
| MRH-001 remaining：role/id、所有 rubric item evidence paths、所有 manual finding evidence paths 的 email/@ | 闭合 | `_read_quality_review_canonical()` 在 strict parse/canonical bytes 后调用 metadata ingress（`utils/investment_agent_acceptance.py:2376-2387`）；该 ingress 遍历 role/id、每个 `dimension.items[].evidence_paths` 与每个 `findings[].evidence_paths`，任一含 `@` 即 `ContractError`（2433-2443）。run 在 terminal command/process factory 前调用它（1707-1728）；verify 在 inventory、evaluator、任何 acceptance-owned output 前调用它（4536-4538）。
| MRH-001 remaining：secret/home 形状 | 闭合 | `_assert_quality_review_sanitized()` 对 canonical 的完整 payload 执行 secret、Google key、POSIX/Windows home-path 扫描（2403-2412），因此覆盖上述全部 evidence paths；该扫描先于 metadata email 检查，且共享 run/verify ingress。
| MRH-001 remaining：failure-path tests | 闭合 | evidence-path helper 分别注入 rubric 与 manual finding email（`tests/test_investment_agent_acceptance.py:7092-7125`）；run 用例断言仅 12 个 planned calls、无 terminal/output（7130-7171），verify 用例 patch 真实 CLI evaluator consumer 并断言调用数为 0、无 output（7176-7227）。reviewer role/id email 与 home-path 也有独立覆盖（6981-7089）。
| RER-001：两处宽 `object` | 闭合 | `_seed_real_live_chain()` 的 `source_meta` 与 `material_meta` 均使用 `JsonObject`（1166、1197）；对本次新增 diff 的 `Any`/`object`/`cast`/`type: ignore` 扫描无命中。
| MRH-002 | 无回归 | quality ingress 早于 output（4536-4538）；source inventory 仅在 repository/artifact/runtime closure 与 `evaluate_acceptance()` 成功后写入（4560-4610）。manifest/report/material/evaluator 四种 drift 用例保持 source inventory 与 acceptance receipt sentinel 字节、planned receipts 不变（7230-7332）。
| MRH-003 | 无回归 | strict-ingress tests 与 drift tests patch 的是 `acceptance_cli_module.evaluate_acceptance`，即真实 consumer；PASS/FAIL 测试通过真实 repository/artifact/evaluator 链并转发 spy，而未整体替换 `_evaluate_live_plan()`。
| MRH-004 | **有低优先级回归** | implementation artifact 的“corrective fix 后最终”快照遗漏了在同阶段 corrective-fix artifact 已明确存在的 `manual-review-handoff-code-rereview-terra.md`；详见本报告唯一 finding。|

## Validation

- `source .venv/bin/activate && python -m pytest tests/test_investment_agent_acceptance.py -q`：**220 passed**。
- `source .venv/bin/activate && pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py`：**0 errors, 0 warnings, 0 informations**。
- `source .venv/bin/activate && ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：**All checks passed**。
- `git diff --check 4d91a16 -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：通过。
- `git diff --name-only 4d91a16`：仅两份 allowlisted production/test 文件。

## Open Questions

无。

## Residual Risk

- 未执行 Slice 5/live、网络、密钥或付费调用；这符合本次 deterministic code re-review 边界，不构成本 correction 的 open finding。

## Conclusion

**FAIL。** corrective MRH-001-remaining 与 RER-001 已闭合，MRH-002、MRH-003 未见回归；MRH-004 存在一项工作树审计快照遗漏。Open High / Medium / Low：**0 / 0 / 1**。未实施修复，完成即停止。
