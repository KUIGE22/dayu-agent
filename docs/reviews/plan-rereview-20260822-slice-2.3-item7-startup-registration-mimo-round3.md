# Plan Rereview — Slice 2.3 Item 7 Startup Registration

- 日期：2026-08-22
- 角色：独立 plan rereviewer（MiMo-V2.5）；非 Controller、非 plan writer、非 implementation writer
- 状态：``FRESH SAME-SHA DUAL PLAN REREVIEW / AWAITING SECOND LANE``
- actual model：xiaomi/mimo-v2.5
- actual route：MiMoCode native (mimo agent, xiaomi/mimo-v2.5)
- 基线 branch：codex/investment-platform
- reviewed scope：master plan + plan-fix artifact 对 Item 7 startup registration corrective plan 的完整 hostile review；不 review implementation/test code 本身，不 review DeepSeek artifact

## 1. START identities

| Artifact | SHA-256 | Lines | Bytes |
|---|---|---|---|
| master plan ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`` | ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` | 3903 | 312988 |
| plan-fix ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md`` | ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b`` | 196 | 15624 |
| preserved WIP ``dayu/services/startup_preparation.py`` | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` | 1689 | 63289 |
| preserved WIP ``tests/application/test_service_startup_preparation.py`` | ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` | 4044 | 127443 |

All five START identities verified by ``shasum -a 256`` and ``wc -l -c`` in this session. No identity drift.

## 2. 方法与五视角

### 2.1 方法

- 从 byte0 完整读取 master plan（3903行）、plan-fix（196行）、implementation WIP（1689行）与 test WIP（4044行）。
- 逐 section 走读 master plan 中 Item 7 相关合同：§2.1/§3.1/§3.3/§10/§10.1/§11/§11.1/§12/§13/§13.1/§13.4/§14/§14.0/§15/§16/§17.2。
- 逐行核对 plan-fix corrective writeback 与 master plan 当前 wording 的一致性。
- 核对 preserved WIP 代码与 plan contract 的对齐。
- hostile review：默认怀疑，寻找最强的基于证据的理由说明该 plan 还不该 PASS。

### 2.2 五视角

**Correctness**：plan contract 是否自洽、是否可 code-generation-ready 执行。
**Stability**：state machine、exception handling、resource lifecycle、concurrent/sequential ordering 是否闭合。
**Maintainability**：architecture boundary、owner separation、overcoupling 是否合理。
**Completeness**：validation contract、artifact bookkeeping、residual risk 是否充分。
**Adversarial**：最强反例、false positive 风险、未覆盖 failure mode。

## 3. Round-2 accepted findings 闭合验证

Round-2 双路 review（DeepSeek V4 Pro ``FAIL 0/1/2``、MiMo ``PASS 0/0/0``）产生三项 accepted finding。Controller 均已接受，plan-fix SA25 已写回。本轮 fresh 验证闭合：

### S23-I7-DSV4P-RR2-01 — Medium — 四 README 明确列举

- **master plan 写回位置**：§10.1 ``:2609-2618`` 现精确列举 root ``README.md``、``tests/README.md``、``dayu/README.md`` 与 ``dayu/investment/README.md`` 四份 README，每文件职责与 §11/§14.0.8 一致；§11 ``:2732-2753`` 列出 exact-seven 实现 allowlist 含四份 README；§14.0.8 ``:3400-3407`` 定义四 README 机械断言。
- **闭合证据**：master plan 当前 wording 已包含四份 README 的精确职责划分与 zero-diff 约束。四者均不得写 Item 8 尚未物化的 final CI 结果。闭合。

### S23-I7-DSV4P-RR2-02 — Low — historical catalog=174 与 final=176 阶段限定

- **master plan 写回位置**：§8.6 ``:2304-2306`` 冻结 prerequisite phase historical catalog=174、Item 7/aggregate final=176；§13.4 ``:3259-3260`` 同步该阶段限定；§13.1 ``:3275-3277`` 要求 mechanical collector 在 Item 6 phase 证明 174 及在 Item 7/aggregate phase 证明 176。
- **闭合证据**：三处 wording 均已写回，Item 6 main 51/prerequisite 12/file ownership 未改。闭合。

### S23-I7-DSV4P-RR2-03 — Low — production Compose 与 production composition case-sensitive 区分

- **master plan 写回位置**：§11 ``:2740-2744`` 的 root README future replacement 保留``本仓库当前不提供 production Compose`` 部署真值，且 ``README.md:134`` 及该 replacement paragraph 以外字节 zero diff；§14.0.8 ``:3400-3407`` 仅对原 ``:385-387`` replacement paragraph 做 case-sensitive/术语精确断言，不把部署 ``production Compose`` 与 platform ``production composition`` 互为旧真值命中。
- **闭合证据**：两个 case-sensitive term 在 plan 全文中严格区分，无混淆。闭合。

**Round-2 三项闭合结论**：全部三项 accepted finding 已在 master plan 当前 wording 中闭合，无遗留。

## 4. Hostile review — Item 7 plan 全面审查

### 4.1 §10.1 / §11 / §12 / §14 / §15 — exact-seven 一致性

| Section | 引用 exact-seven 的位置 | 一致？ |
|---|---|---|
| §10.1 ``:2578-2618`` | 列出 seven paths 并逐文件定义修改边界 | ✓ |
| §11 ``:2732-2753`` | exact-seven allowlist 含七个且仅七个 path | ✓ |
| §12 step 7 ``:2871`` | "只写§11 exact-seven" | ✓ |
| §14.0 ``:3296-3434`` | 八步验证覆盖全部 seven paths | ✓ |
| §15 ``:3639-3644`` | STOP 条件引用 exact-seven | ✓ |
| §17.2 ``:3894-3897`` | "exact-seven；PG black-box exact-four" | ✓ |

Plan-fix §2 ``:39-43`` 列出 "exact-six" 而非 exact-seven（缺少 ``README.md``），但 plan-fix §9 ``:161-163`` 已明确声明 §§1–8 为 historical wording 被 §11/§14.0/§17.2 的 exact-seven 真值 supersede。master plan 当前所有 normative sections 一致使用 exact-seven。**无矛盾**。

### 4.2 四 README 与 root README 单段 zero-diff

- root ``README.md``：只允许改当前 ``:385-387`` 一个失真段落，保留 ``本仓库当前不提供 production Compose`` 部署真值，其余字节 zero diff（§11 ``:2740-2744``、§14.0.8 ``:3400-3407``）。
- ``tests/README.md``：只把 black-box 职责从 exact-three 同步为 exact-four/one Source handler；final CI 命令 defer Item 8（§11 ``:2745``）。
- ``dayu/README.md``：只同步整体分层、production composition 与 startup 职责中已失真的 empty registry/Service 装配表述（§11 ``:2746``）。
- ``dayu/investment/README.md``：只把 production empty registry 同步为 exact-one Source Sync handler 及无 research/Agent/Broker handler（§11 ``:2747-2748``）。
- 四者都不得写 Item 8 尚未物化的 final CI 结果（§10.1 ``:2618``）。
- ``README.md:134`` 的现有 production Compose 部署声明不进入 replacement 断言集且字节 zero diff（§14.0.8 ``:3406``）。

**无矛盾**。

### 4.3 Item 8 defer 一致性

- §12 step 8 ``:2875-2879``：Item 8 只在 Item 7 local accepted checkpoint 后更新两个 extended CI workflow 为 final nine commands/nine ignores，运行 planned workflow static audit，并只更新 ``tests/README.md`` 中 final nine-lane CI 运行方法段。
- Item 7 已闭合的 exact-four startup/black-box 文字、``README.md``、``dayu/README.md`` 与 ``dayu/investment/README.md`` 不属于 Item 8，禁止重复改写。
- §15 ``:3628-3629`` STOP 条件：prerequisite 或 Item 6 main 修改两份 CI workflow、materialize/collect/run future workflow static test、把 future final nine-lane workflow 冒充 incremental 证据，或修改 root ``README.md``。
- Item 8 zero-diff 约束在 §11 ``:2752``："``dayu/fins/README.md``、两份 workflow 及其它 production/test/docs 一律 zero diff"。

**一致**。

### 4.4 Item 6 historical catalog=174 与 Item 7/final aggregate=176

三处引用均一致：
- §8.6 ``:2304-2306``：prerequisite phase historical catalog=174（Item 7 后 final aggregate=176）
- §13.4 ``:3259-3260``：prerequisite 仍是 12 项、Item 6 phase 当时 overall 仍 174 项；Item 7 完成后的 final aggregate 为 176 项
- §13.1 ``:3275-3277``：要求 mechanical collector 在 Item 6 phase 证明新增 15 项、两个 rename、historical 总数 174 及 Item 6 main51/prerequisite12 的 file ownership，并在 Item 7/aggregate phase 证明 final 总数 176

**一致**。

### 4.5 deployment production Compose 与 platform production composition

plan 全文 12 处引用均严格区分：
- ``production Compose`` 仅指部署编排文件（§11 ``:2743``、§14.0.8 ``:3405``）
- platform ``production composition`` 仅指平台装配（§11 ``:2746``、§14.0.8 ``:3405``）
- 两个 case-sensitive term 不得互为旧真值命中（§14.0.8 ``:3405``）
- ``README.md:134`` 现有 production Compose 部署声明不进入 replacement 断言集（§14.0.8 ``:3406``）

**一致**。

### 4.6 preserved exact-two WIP

- 文件头 Gate 冻结 ``startup_preparation.py`` SHA ``73309aba…`` / 1689 行 / 63289 字节与 ``test_service_startup_preparation.py`` SHA ``a0010b1e…`` / 4044 行 / 127443 字节。
- §10.1 ``:2580-2584``：Writer 必须先逐字节复核并 preserve-and-adopt 当前两项 WIP；若任一 SHA、行数、HEAD、tracked/untracked/index 集合与文件头 Gate 不一致，立即 STOP。
- §15 ``:3639``：Item 7 未保留文件头两个 WIP 身份、改写/丢弃其字节，或 exact-seven 之外出现实现/README diff → STOP。

**一致**。

### 4.7 exact-seven writer allowlist

§11 ``:2732-2753`` 列出七个且仅七个 path：

1. ``dayu/services/startup_preparation.py``（preserved WIP）
2. ``tests/application/test_service_startup_preparation.py``（preserved WIP）
3. ``tests/integration/investment/test_identity_repositories_postgres.py``
4. ``README.md``（仅 ``:385-387`` 单段）
5. ``tests/README.md``
6. ``dayu/README.md``
7. ``dayu/investment/README.md``

§11 ``:2752-2753``：任一 exact-seven 之外的实现或 README 需要立即 STOP。

**闭合**。

### 4.8 PG black-box exact-four

- §11 ``:2738-2739``：``test_identity_repositories_postgres.py`` 只 rename/收紧 production startup black-box exact-three 为 exact-four 并断言真实 Source service/repository/shared factory；其它 PG 行为零改。
- §13.1 ``:3019-3028``：PG black-box 唯一位于 ``test_identity_repositories_postgres.py``；五个 startup names 各 exactly once；四个旧名各零次。
- §14.0 step 6 ``:3380-3390``：pinned PG16 isolated black-box 验证 exact-four collect/pass 且旧 exact-three 不 collect。

**闭合**。

### 4.9 validation / coverage / process isolation

§14.0 八步 validation contract：

1. Frozen preflight / allowlist
2. Focused + architecture（两个独立 pytest process）
3. Exact named tests + docstring AST（exit 0）
4. Exact Pyright / Ruff（0/0/0）
5. Fresh exact-singleton branch coverage（>=80.0）
6. Pinned PG16 isolated black-box
7. Required deterministic non-integration
8. README / mechanical

每步有明确命令、预期输出与 failure 行为。任一非零立即 STOP。**完整**。

### 4.10 artifact / staging / reviewer round bookkeeping

- §5 ``:91-104``：implementation artifact → DeepSeek V4 Pro + MiMo 首审 → Controller 裁决 → accepted fix → 同 reviewer re-review → 双路 PASS 后 Controller acceptance。
- §14.0 ``:3413-3434``：exact-seven implementation/review/fix/re-review/acceptance artifacts 冻结；只 stage exact-seven 与 Item 7 artifacts；不 push、不开 PR、不推进 Item 8。
- §17.2 ``:3864-3903``：完整 review 账本含所有历史 review SHA、verdict 与 accepted findings。

**完整**。

### 4.11 architecture boundary

- §2.1 ``:54-76``：分层与唯一 owner 定义，Host Worker 不改，Fins runtime 与 investment 严格分离。
- §3.3 ``:721-788``：Connector 与平台 Service 协议，FinsSourceConnector 只委托 FinsWorkerGatewayProtocol。
- §10.1 ``:2605-2607``：explicit-provider 分支保持 caller provider/mapping/registry identity 逐项不变；所有 cross-platform Source constructor/register/seal trap 为零调用。
- preserved WIP ``startup_preparation.py`` 中 ``_build_production_services_provider``（``:623-715``）保持 public facade（``InvestmentSourcesService``）与 private execution（``SourceSyncExecutionService``）分离；handler 只委托一次。

**一致**。

### 4.12 best practice / optimal solution / overengineering / overcoupling

- composition 使用 frozen dataclass + protocol，无 God object。
- registration/seal/assert 在同一 composition owner 内顺序执行，无并发注册语义（§10.1 ``:2596-2597``）。
- failure matrix 19 阶段覆盖 constructor/register/seal/assert/provider/publish，零 partial mapping（§10.1 ``:2602-2604``）。
- reverse-order cleanup（§10.1 ``:2603``）：writer lease → S3 store → queue admission → platform lifecycle。
- 无 overengineering：只物化已有 startup contract，不重新设计 composition。

**合理**。

### 4.13 state / recovery / partial failure

- §2.3 ``:111-126``：crash residual，不伪称跨事务原子性。
- §10.1 ``:2602-2604``：任一 phase-2 failure 不发布 partial mapping；outer owner 按既有逆序 close；engine 只 dispose 一次。
- §16 residual #2：source terminal 与 Job terminal 不是同事务；handler 返回 completion 后的 Worker cancellation 后置门可能把 envelope 收窄为 HANDLER_REJECTED。
- preserved WIP ``startup_preparation.py:1569-1579`` 的 exception handler 正确管理 lifecycle/lease/S3/queue 的 reverse-order close。

**闭合**。

### 4.14 manifest / count / command constructibility

- §11.1 ``:2757-2810``：44-key COVERAGE_OWNER_TESTS manifest，每个 key 与 production allowlist exact-equal，每个 tuple 非空/无重复。
- §13 ``:2956-2960``：176 exact names 各一次；Item 6 main 51、prerequisite 12、Item 7 five startup names。
- §14.0 ``:3296-3434``：八步命令模板可直接执行，无 missing 命令。

**可执行**。

### 4.15 blocking questions 和 residual risk

- §17.2 ``:3894``：无 ``Blocking Questions For Controller``。
- §16 ``:3646-3678``：11 项已知 residual，均与 Item 7 scope 无关或已接受。
- plan-fix §6 ``:111-113``：``git fsck`` 旧 worktree/missing-object 为独立 repo-health residual；本 work unit 不删/不改 Git 元数据。

**无阻塞**。

## 5. Findings

未发现实质性问题。

## 5.1 Non-finding Observations

以下 observation 不计 H/M/L，不构成 plan 可执行性阻塞：

### OBS-RR3-01 — plan-fix §2 historical exact-six 与 current exact-seven 不一致（superseded，非 finding）

- **位置**：plan-fix ``:39-43``
- **观察**：plan-fix §2 列出 "exact writable implementation set 为六个 path"（缺少 ``README.md``），而 master plan §10.1/§11/§12 当前 normative wording 为 "exact-seven"。
- **不计为 finding 的理由**：plan-fix §9 ``:161-163`` 明确声明 "§§1–8 未改写；其中 exact-six、root README zero-diff 与旧 review 状态只是 SA23 及更早轮次的 historical wording，均被本节与 master 当前 §11/§14.0/§17.2 的 exact-seven 真值 supersede，不得再作为 active dispatch 输入"。plan-fix §3 ``:57`` 同时引用 "§10.1 是 normative delta"。master plan 所有 normative sections 一致使用 exact-seven。该不一致已被 plan-fix 自身的 supersede 声明显式覆盖，implementation writer 应以 master plan §11 为唯一 allowlist 真源。

## 6. Open Questions

无。

## 7. Residual Risk

- plan-fix §§1–8 保留完整历史轮次 wording，已由 §9 声明 supersede；本轮未发现其它被历史 wording 覆盖的 active 不一致。implementation writer 应以 master plan §11 为唯一 allowlist 真源。

## 8. Verdict

``PASS / open H/M/L=0/0/0``

本轮 fresh independent review 对 Item 7 startup registration corrective plan 的 master plan + plan-fix artifact 进行完整 hostile review。Round-2 三项 accepted finding 已全部闭合。未发现实质性 finding（plan-fix §2 historical exact-six wording 已被 §9 supersede 声明覆盖，记为 non-finding observation）。master plan 所有 normative sections（§10.1/§11/§12/§14/§15/§17.2）一致使用 exact-seven、exact-four README、exact-two preserved WIP、exact-one Source handler，并有完整的 validation contract、artifact bookkeeping 与 residual risk 记录。

## 9. END identities

| Artifact | SHA-256 | Lines | Bytes |
|---|---|---|---|
| master plan | ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` | 3903 | 312988 |
| plan-fix | ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b`` | 196 | 15624 |
| preserved WIP ``startup_preparation.py`` | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` | 1689 | 63289 |
| preserved WIP ``test_service_startup_preparation.py`` | ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` | 4044 | 127443 |

END identities 与 START identities 逐字节相同，review 期间无任何文件修改。

## 10. 边界证明

- 未读取任何文件名含 ``deepseek-v4-pro`` 的 plan-review/plan-rerereview artifact。
- 未运行 Git、tests、pyright、PG、Docker、网络或任何写操作（除本 artifact 写入）。
- 未修改 master plan、plan-fix、WIP、README 或任何旧 review artifact。
- 未启动 Gateflow、未实施、未修复、未测试、未 stage/commit/push/PR。
- actual model 为 xiaomi/mimo-v2.5，未切换或替代。
