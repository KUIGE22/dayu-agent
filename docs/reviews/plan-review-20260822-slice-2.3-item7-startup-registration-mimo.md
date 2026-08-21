# Slice 2.3 Item 7 startup registration plan review

- 日期：2026-08-22 06:20:10 UTC+8
- 角色：独立 MiMo plan reviewer；非Controller、非planner、非implementation writer、非fix writer
- 模型：mimo-v2.5（xiaomi/mimo-v2.5）
- CWD：/Users/wsk/workspace/dayu-agent
- 状态：FRESH SAME-SHA INDEPENDENT ADVERSARIAL PLAN REVIEW

## 1. Frozen identity

- branch：codex/investment-platform
- HEAD：d604d8df7613db0103076b3a727156fd74dd9e1b
- target：docs/plans/2026-08-12-slice-2.3-source-connectors-health.md，SHA-256 `65007079da72782d21ea35d4c2ebc502661665983229f6c651be8c80aef21403`，3859行，308008字节
- fix：docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md，SHA-256 `363e8916ffcf245581bfa0747a5b0d7a82da0f6d08f065e37cf791641d388644`，132行，9796字节
- WIP source：dayu/services/startup_preparation.py，SHA-256 `73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`，1689行，63289字节
- WIP test：tests/application/test_service_startup_preparation.py，SHA-256 `a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`，4044行，127443字节
- START = END HEAD（read-only review，no git mutation）

## 2. Scope of review

独立 adversarial review 整个 Item 7 plan：motivation、handoff/code-generation readiness、exact six scope、sequencing、architecture boundary、best practice、optimal solution、overengineering、overcoupling、lifecycle/failure/recovery、validation/residual。不读取或引用任何 DeepSeek review artifact 或结论。

## 3. Independent old test name mechanical audit

plan-fix §8 claims to writeback four old test names to master §13.1 (`:3011-3018`) and §14.0.3 (`:3320-3328`) for AST zero-residual assertion. Independent grep on HEAD `d604d8df`:

| Old name | Exists in codebase | Evidence |
|---|---|---|
| `test_production_provider_wires_exact_three_service_mapping` | **YES** | `tests/integration/investment/test_identity_repositories_postgres.py:1625` |
| `test_production_explicit_provider_keeps_custom_composition_after_redis_admission` | **NO** | grep 0 matches across all `*.py` |
| `test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry` | **NO** | grep 0 matches across all `*.py` |
| `test_source_handler_registration_remains_absent_until_slice_2_3` | **NO** | grep 0 matches across all `*.py` |

**结果**：plan-fix声称的四个old names中，三个在当前HEAD已不存在。plan-fix §8 writeback基于过期或错误的codebase状态假设。§14.0.3 AST zero-residual assertion对这三个已不存在的名字将trivially pass。

## 4. Independent new test name verification

| New name | Exists in WIP | Evidence |
|---|---|---|
| `test_production_provider_wires_exact_four_service_mapping` | **NO** | grep 0 matches；这是Item 7 implementation将创建的新test |
| `test_production_provider_failure_disposes_one_engine_once` | **YES** | `tests/application/test_service_startup_preparation.py:3231` |
| `test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four` | **YES** | `tests/application/test_service_startup_preparation.py:3101` |

Item 7 incremental catalog：前两个新test不在当前codebase，后两个已在WIP中。plan声称Item 7 delta为2（总数174→176），与WIP状态一致。

## 5. Findings

### S23-I7-PR-01-未修复-[严重]-plan-fix引用三个不存在的旧test name作为残余审计基线

- **位置**: fix artifact §8 (`:120-130`)、master plan §13.1 (`:3015-3018`)、§14.0.3 (`:3320-3325`)
- **问题类型**: open question 未收敛 / 假设不成立
- **当前写法**: plan-fix §8 声称"该集保留原 `test_production_provider_wires_exact_three_service_mapping`，并新纳入 `test_production_explicit_provider_keeps_custom_composition_after_redis_admission`、`test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry` 与 `test_source_handler_registration_remains_absent_until_slice_2_3`；任一旧名残留或与 new name 双名并存都 fail closed。精确writeback为master `:3011-3018` 与 `:3320-3328`。"
- **反例/失败场景**: 当前HEAD `d604d8df` 只存在四个old names中的一个。三个已不存在的名字被写入master plan的residual audit文本，§14.0.3 AST assertion将trivially pass对这三个名字的检查。审计的退化使plan-fix的writeback行为看起来像是基于过期codebase状态做出的决定，而非基于当前HEAD的精确实证。如果后续controller或reviewer依赖该writeback证明"旧名零残留"已验证，将获得虚假信心。
- **为什么有问题**: plan-fix writer声称对当前HEAD做read-only preflight（§1），但四个old names中三个不存在，说明preflight要么未实际执行，要么基于不同baseline。这损害plan-fix artifact的可信度。虽然不影响plan本身的implementation路径（writer仍会正确rename exact-three→exact-four），但使§14.0.3的residual audit退化为对不存在名字的no-op检查。
- **直接证据**: `grep -r "test_production_explicit_provider_keeps_custom_composition_after_redis_admission" --include="*.py"` 返回0匹配；同理另外两个名字。只有 `test_production_provider_wires_exact_three_service_mapping` 存在于 `tests/integration/investment/test_identity_repositories_postgres.py:1625`。
- **影响**: plan-fix的§8 writeback失去实际审计价值；controller/ reviewer可能对不存在的名字投入不必要的验证注意力；但不影响Item 7 implementation正确性（writer仍会执行rename）。
- **建议改法和验证点**: Controller acceptance时标注该发现，明确§14.0.3 AST assertion的实际验证目标仅为现存的 `test_production_provider_wires_exact_three_service_mapping` 零残留；其余三个名字的zero-residual可从当前HEAD直接确认为已满足。不建议为此修改plan本身——plan的implementation guidance仍是正确的。
- **修复风险（低）**: Controller在acceptance metadata中添加注释即可
- **严重程度（中）**: 不block implementation，但损害plan-fix artifact可信度

### S23-I7-PR-02-未修复-[低]-Documentation-only Low是否属于Item 7 scope边界

- **位置**: fix artifact §2 (`:51-53`)、§6
- **问题类型**: 范围漂移（borderline）
- **当前写法**: plan-fix §2 item 6："唯一Low只在implementation阶段给 `test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four` 补全中文 `Args`（`monkeypatch`/`tmp_path`）、`Returns`、`Raises`；本plan gate不改代码。"
- **反例/失败场景**: Item 7核心是startup registration的exact-four mapping。Documentation-only Low是一个独立的docstring补全任务，理论上可以是任何包含该test的slice的附带工作。将其显式纳入Item 7增加了一行scope，但风险极低。
- **为什么有问题**: plan-fix声称基于AGENTS.md §35 docstring requirement将该Low纳入Item 7。该决定合理（该test已在Item 7 WIP中，且docstring缺失是既有事实），但未充分说明为什么不在Item 8或单独fix中处理。不过鉴于该Low只涉及一行docstring且测试已在Item 7 scope内，纳入是合理的。
- **直接证据**: `tests/application/test_service_startup_preparation.py:3101` 的 `test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four` 当前只有单行docstring。AGENTS.md §35要求完整中文参数/返回值/异常docstring。
- **影响**: 极小。该Low不影响Item 7的implementation路径、validation gates或architecture boundary。
- **建议改法和验证点**: 可保持现状。如果controller认为scope应更严格，可将该Low defer到Item 8；但鉴于该test已在Item 7 exact-six test path中，纳入是务实的。
- **修复风险（低）**: N/A，当前决策可接受
- **严重程度（低）**: 不block任何gate

## 6. Five lenses assessment

### Architecture boundary review
Item 7正确保持分层：startup_preparation.py作为Service层对启动期暴露的preparation API，只做composition wiring，不反向import domain/connector。exact-six allowlist精确限制了可修改路径，不触及domain/connector/storage/migration。WIP中的imports（lines 83-130）正确引用composition/connector/domain类型但不破坏分层。**无finding。**

### Best-practice review
Item 7的validation gates（§14.0）结构合理：frozen preflight → focused + architecture → AST named test → Pyright/Ruff → singleton coverage → pinned PG16 → required deterministic lane → README/mechanical。每个gate有明确exit criteria。唯一潜在gap是§14.0.3的AST assertion因三个phantom old names而退化（Finding S23-I7-PR-01），但不影响整体best practice。**无独立finding。**

### Optimal-solution review
Item 7选择"preserve and adopt WIP"策略，而非discard and rewrite。这是正确的：WIP已包含1689行production code和4044行test code，且经过了部分验证。discard将浪费大量已验证工作。exact-six allowlist是合理的scope控制。**无finding。**

### Overengineering review
Item 7没有引入不合理的abstractions或过度设计。它精确地在既有WIP上完成startup registration的closing，包括registry seal、handler registration、composition publish和black-box rename。验证 gates虽然详细但都是必要的quality gates。**无finding。**

### Overcoupling review
Item 7的exact-six paths之间有正确的单向依赖：startup_preparation.py → (imports) → composition/connector/domain types；test file → (imports) → startup_preparation.py；integration test → (PG fixture) → startup_preparation.py。三份README只陈述事实，不引入代码依赖。无双向依赖或跨层穿透。**无finding。**

## 7. Assumptions tested

| Assumption | Status | Evidence |
|---|---|---|
| Item 7 motivation成立：startup exact-three→exact-four是必要的 | **成立** | §10.1冻结了production registry必须包含source service的contract；当前WIP `test_production_provider_wires_exact_three`仍以three为真值 |
| Plan-fix writeback基于正确codebase状态 | **不成立** | 三个old names在当前HEAD不存在（§3 mechanical audit） |
| WIP preserved and adopt策略是optimal | **成立** | WIP 1689+4044行已包含partial implementation，discard浪费大 |
| Exact-six allowlist不遗漏必要path | **成立** | startup_preparation.py + 3 test/docs paths覆盖implementation + validation + documentation |
| Exact-six allowlist不包含不必要path | **成立** | 无extra path；domain/connector/migration/Host Worker均zero diff |
| Item 7 validation gates可执行 | **成立** | §14.0每个gate有具体bash commands和exit criteria |
| 176 total named test catalog正确 | **未独立验证** | §13四个subsection test name enumeration无法通过grep独立审计（需逐名计数）；但plan声称的delta逻辑一致（174+2=176） |

## 8. Open questions

无blocking open questions。Item 7 plan scope收敛，implementation guidance code-generation-ready。

## 9. Residual risks

1. **§14.0.3 phantom old name assertion**（owned by S23-I7-PR-01）：三个不存在的old name在AST assertion中trivially pass。风险低——不影响implementation正确性，但降低审计价值。建议controller在acceptance metadata中注释。
2. **176 total catalog count**：未独立逐名验证176的精确性。风险低——plan内部delta逻辑一致（174+2=176），且只有Item 7 completed后才需要aggregate audit。

## 10. Final plan review conclusion

**PASS / open H/M/L=0/0/0**

Item 7 plan motivation成立，scope收敛，validation gates code-generation-ready，architecture boundary正确，无overengineering或overcoupling。S23-I7-PR-01（中）和S23-I7-PR-02（低）均为非blocker finding，不需要在plan review gate修复，可在controller acceptance时注释。

Plan-fix §8 writeback基于过期codebase状态的发现不改变Item 7 plan本身的正确性。writer仍会正确执行exact-three→exact-four rename和validation gates。

---

**Artifact identity**：
- path：docs/reviews/plan-review-20260822-slice-2.3-item7-startup-registration-mimo.md
- model：mimo-v2.5（xiaomi/mimo-v2.5）
- CWD：/Users/wsk/workspace/dayu-agent
- START=END HEAD：d604d8df7613db0103076b3a727156fd74dd9e1b
- target SHA：65007079da72782d21ea35d4c2ebc502661665983229f6c651be8c80aef21403（3859行）
- fix SHA：363e8916ffcf245581bfa0747a5b0d7a82da0f6d08f065e37cf791641d388644（132行）
- verdict：PASS / open H/M/L=0/0/0
