# v5.7 Ruff Ratchet Baseline Erratum Controller 记录

- 日期：2026-08-08
- 当前基线：`4c5bb1b gateflow: accept cli write architecture plan v5.6`
- Architecture ratchet baseline：`5821014`（first accepted plan `f0a3ea1` 的唯一 parent）
- PR baseline：`origin/main=2115c86`
- 分支：`codex/dual-model-research-mvp`
- Gate：aggregate validation blocker 的 accepted plan closure
- Master plan：`docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- DeepSeek review：`docs/reviews/plan-review-20260808-154611.md`
- MiMo review：`docs/reviews/plan-review-20260808-154612.md`
- DeepSeek re-review：`docs/reviews/plan-review-20260808-160555.md`
- MiMo re-review：`docs/reviews/plan-review-20260808-160556.md`
- DeepSeek final corrective re-review：`docs/reviews/plan-review-20260808-161501.md`
- MiMo final corrective re-review：`docs/reviews/plan-review-20260808-161502.md`
- 状态：`v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS`
- Controller closure：`CLOSED`

## 1. Scope

本轮只修改 master plan 并新增本 Controller artifact。production、tests、README、CI
workflow 与两份外部 review 全部冻结；不新增 Slice 14，不实施 lint cleanup。

## 2. 直接测量证据

### 2.1 Baseline ownership

- `git show -s --format='%H %P %s' f0a3ea1` 确认 `f0a3ea1` 的唯一 parent 为
  `5821014`；这是 CLI write architecture work unit 开始前的真实代码树。
- `origin/main=2115c86` 早于本 work unit 之外的大量 feature commits，适合衡量最终 PR
  residual，但不适合隔离 architecture refactor 的 hard ratchet。
- current HEAD 作为 baseline 会使比较成为 tautology，不能提供 non-regression 证据。

### 2.2 Slice-report Ruff 算法

既有 Slice implementation artifacts 使用同一改动文件集合，将 baseline 文件通过
`git show <baseline>:<path>` 输入 Ruff，按 JSON finding 的 rule code 构造 `Counter`，
并以 `Counter(HEAD) - Counter(BASE)` 判断 positive delta。其报告包含 `B009`、
`TRY004`、`RUF*` 等非 E/F 规则，但不包含 `--select ALL` 会产生的大量 `D`/`ANN`
规则，因此必须固定为 Ruff `0.16.1` 的无显式 `--select` rule set，而不是凭名称猜测
“full-rule”。固定 leaf command：

```bash
uv run --no-project --with ruff==0.16.1 ruff check --no-cache \
  --output-format=json dayu/cli/commands/ dayu/services/
```

对 `4c5bb1b` 与 `5821014` 的相同 scope 测量：

- HEAD total：`335`
- BASE total：`364`
- positive：`{}`
- negative：`I001:11`、`TRY004:17`、`UP035:1`，合计 `29`

因此 architecture ratchet hard gate 实际通过。显式 `--select ALL` 在同一 HEAD/scope
得到 `11248`，不是 Slice-report 算法；`constraints/min-py311.txt` 固定 Ruff `0.15.11`，
其 CI/default E/F 语义也不能替换上述 architecture gate。Ruff `0.16.1` 的选择不是任意
升级，而是为了精确复现既有 Slice implementation artifacts 与 per-Slice ratchet；只读
cross-version 复测确认，`0.15.11` 对同一 HEAD/scope 无显式 select 时仅产生 exact8
（`F401:7`、`F541:1`），与 `0.16.1` 的 335 不可混用。

scope `dayu/cli/commands/ dayu/services/` 是本 master plan C1/C3/C4/C5 的 production
ownership 边界。`dayu/engine/`、`dayu/fins/`、`dayu/host/`、`dayu/config/` 等不属于
本 work unit；origin/main PR residual 仍使用相同 scope，本 artifact 不声称全 repo Ruff
状态。

### 2.3 PR-level residual

用同一 Ruff `0.16.1`、scope 与 Counter 算法比较 `origin/main=2115c86`：

- HEAD total：`335`
- BASE total：`143`
- per-code positive total：`216`
- positive codes：`B009:53`、`BLE001:3`、`FURB162:12`、`ISC004:1`、
  `RUF010:22`、`RUF022:2`、`SIM102:1`、`TRY004:118`、`UP012:2`、
  `UP035:2`

该差异反映完整 PR 相对 main 的 lint residual，必须原样输入 aggregate deepreview。
它不阻断 architecture-scoped ratchet，但不能被隐藏或误称为 CI 已覆盖。

## 3. Controller 裁决

### 3.1 DeepSeek `154611`

- `H01`：baseline bug 的事实 `ACCEPTED / CLOSED-BY-PLAN-TEXT`；architecture hard
  ratchet 改为 exact `5821014`。其“用 current HEAD 建 residual baseline”方案
  `REJECTED-WITH-REASON`，因为该比较是 tautology，无法证明本 work unit 无退化。
- `M01`：rule-set 歧义 `ACCEPTED / CLOSED-BY-PLAN-TEXT`；固定 Ruff `0.16.1`、无显式
  select、JSON Counter、相同 scope 与 baseline archive。拒绝把 `--select ALL` 当成既有
  Slice-report 算法。
- `M02`：CI required lane 不检查 production Ruff 的事实 `ACCEPTED AS RESIDUAL`；本
  work unit 不修改 workflow，该事实进入 aggregate deepreview residual，不作为当前 plan
  的代码修复。
- `L01/L02`：比较范围与既有债务上下文 `ACCEPTED AS CONTEXT / CLOSED`；scope 保持
  `dayu/cli/commands/ dayu/services/`，architecture baseline 与 PR baseline 分层记录。

### 3.2 MiMo `154612`

- `RUFF-01`：configured rule set 与 `--select ALL` 必须区分的事实 `ACCEPTED /
  CLOSED-BY-PLAN-TEXT`。Controller 以实际 Slice artifact 与 Ruff `0.16.1` 测量为准；
  constraints Ruff `0.15.11` 的 E/F 环境另行标注，不把版本差异混作同一门禁。
- `RUFF-02`：CI 不执行 production Ruff `ACCEPTED AS PR RESIDUAL / CLOSED`；不扩大到
  workflow 修改。
- `RUFF-03`：原 review 的测量不确定性已由本地相同算法复测关闭；origin/main positive
  精确为 `216`。
- `RUFF-04`：完整 PR 债务不能全部归因于 architecture refactor 的判断 `ACCEPTED /
  CLOSED`；以 `5821014` 隔离 architecture hard gate，以 origin/main 保留 PR residual。
- `RUFF-05`：无需 Slice 14 `ACCEPTED / CLOSED`；但其建议在当前范围直接 cleanup
  `REJECTED-WITH-REASON`，因为机械 TRY004/B009/FURB162 修复会改变异常类型、argparse
  defensive fallback 或 timezone 语义并违反 accepted contracts。
- `RUFF-06`：把 origin/main 用作 architecture hard ratchet `REJECTED-WITH-REASON`；
  origin/main 仅作为 PR-level residual baseline 保留。

### 3.3 其他替代方案

- 任意 residual count/current HEAD baseline：`REJECTED-WITH-REASON`，会把已知结果写成
  自证门槛，失去 architecture non-regression 价值。
- changed-lines 算法：`REJECTED-WITH-REASON`，当前 Ruff/仓库没有受支持、可复现且能
  正确处理 move/rename 的实现证据。
- `--select ALL`：`REJECTED-WITH-REASON`，同 scope HEAD=`11248`，与 Slice-report
  multiset 明显不同。

### 3.4 Re-review observations（160555/160556）

- DeepSeek `L01`：`ACCEPTED / FIXED`。§11 item23 已显式记录 negative total=`29`
  （`I001:11`、`TRY004:17`、`UP035:1`），并说明本 work unit 实际改善三类 finding。
- DeepSeek `L02`：`REJECTED-WITH-REASON / CLOSED / NON-DEFECT`。F811/F841 消除与
  F401/F541 减少是可选正面 context；architecture correctness 已由完整 positive
  Counter 与 negative29 闭合，不要求把 origin/main 的所有 negative code 扩入完成定义。
- MiMo `V57-03` 与 `V57-09`：两项为重复的版本选择/跨版本量化 observation，合并
  `ACCEPTED / FIXED`。Ruff `0.16.1` 用于复现既有 Slice artifacts，而非模拟 CI；
  Ruff `0.15.11` 同 scope exact8（`F401:7`、`F541:1`）对比 `0.16.1` exact335，证明
  两个版本不得混用。
- MiMo `V57-08`：`ACCEPTED / FIXED`。scope 精确对应 C1/C3/C4/C5 production
  ownership；engine/fins/host/config 等排除路径不属本 work unit，origin/main residual
  仍用相同 scope，不宣称全 repo。
- DeepSeek 160555 与 MiMo 160556 的核心结论均为 PASS；Controller 当前 open
  High/Medium/Low=`0/0/0`。

### 3.5 Final corrective re-review closure（161501/161502）

- DeepSeek 161501：`PASS`，open High/Medium/Low=`0/0/0`；按 raw-item 口径确认
  初审与 re-review observations `22/22 CLOSED`。
- MiMo 161502：`PASS`，open High/Medium/Low=`0/0/0`；按合并 finding 口径确认
  `16/16 CLOSED`，无新 finding。
- 两份 artifact 的计数口径不同但结论一致：全部 observations 已 CLOSED，Controller
  accepted findings=`0`、open High/Medium/Low=`0/0/0`。
- Architecture Ruff 核心指标保持 positive=`{}`（0）、negative total=`29`
  （`I001:11 / TRY004:17 / UP035:1`）；origin/main PR residual positive=`216`
  仍是 aggregate deepreview mandatory input。

Controller 状态：`v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS`；本 plan fix 已 CLOSED，
aggregate validation 可恢复。

## 4. Master plan 修订

- header/status/tail 改为
  `v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，
  HEAD 更新为 `4c5bb1b`，v5.6 accepted 历史保留。
- 新增 `AGG-RUFF-CTRL-01..04`，锁定 architecture baseline、确定性 Ruff 算法、PR
  residual 与 no-Slice14/contract-preservation 边界。
- §9 新增完整可执行的 baseline archive + Ruff JSON + Counter 比较命令，并修正 stop
  conditions：architecture positive 非零阻断；origin/main residual 不阻断 architecture
  validation，但遗漏 residual 会阻断 aggregate deepreview closeout。
- §10 增加 CI 未覆盖 production Ruff 的 residual 分类。
- §11 增加 exact architecture ratchet 与 PR residual 完成项。
- re-review fix 补入 Ruff `0.16.1` 选择理由、`0.15.11` exact8 cross-version 证据、
  C1/C3/C4/C5 scope 理由及 negative29 改善说明。

## 5. 验证

- 限定 diff：PASS；本轮写范围仅 master plan 与本 artifact。
- 状态锚点：PASS；v5.7 accepted header/status/tail 一致，v5.6
  accepted 历史保留。
- Baseline/算法锚点：PASS；`5821014`、Ruff `0.16.1`、固定 scope、HEAD335/BASE364、
  positive `{}` 与 negative 29 全文一致。
- PR residual 锚点：PASS；origin/main 2115c86、HEAD335/BASE143、per-code positive216
  全文一致且明确 nonblocking architecture / mandatory deepreview input。
- Cross-version/scope 锚点：PASS；Ruff0.15.11 exact8 与 Ruff0.16.1 exact335、
  C1/C3/C4/C5 production ownership scope 及 negative29 全文一致。
- 尾随空白、文件末尾换行与 `git diff --check`：PASS。

## 6. Residual

- v5.7 已通过 DeepSeek 161501 与 MiMo 161502 最终双路 plan re-review，全部
  observations CLOSED、open High/Medium/Low=`0/0/0`；aggregate validation 可恢复。
- origin/main positive216 是 aggregate deepreview 的 mandatory PR-level residual；后续
  Controller 必须对 review finding 继续裁决，不能在 architecture gate 中静默吸收。
- 当前没有 code/tests/README/CI fix，也没有新增 Slice 14。
