# Slice 2B 双路 code review Controller 裁决

- **日期**: 2026-08-07
- **基线**: `ba8b83e` (`gateflow: accept write artifact callers slice 2a`)
- **范围**: Slice 2B 初审 findings 的逐项裁决
- **状态**: CODE REVIEW PASS / AWAITING DUAL RE-REVIEW

## 输入证据

- DeepSeek 初审:
  `docs/reviews/code-review-slice-2b-20260807-deepseek.md`
- MiMo 初审:
  `docs/reviews/code-review-slice-2b-20260807-mimo.md`
- accepted plan v4.4:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- 实现记录:
  `docs/reviews/slice-2b-write-artifact-callers-implementation-20260807-codex.md`

## Controller 总结

DeepSeek 与 MiMo 均确认 Slice 2B 的 eligible helper 迁移、defer 保留、
fingerprint/time/mapping family 分流、测试和静态门禁均正确。Controller 对两份
初审列出的 8 项 observation 逐项复核后，未接受任何代码、测试、README 或
plan finding：DeepSeek 3 Medium + 2 Low 全部为 non-defect；MiMo 3 Low
均为 HEAD baseline 或 accepted-design observation。当前 open
High/Medium/Low 均为 `0`，无需 implementation fix，进入双路 re-review。

## DeepSeek findings 裁决

### DS M1 — REJECT / non-defect

**初审主张**：Slice 2B 每文件表未逐一列出 `_parse_utc`、`_target_path`、
`_validate_source` 等私有函数，因此 plan accuracy 不足。

**裁决理由**：

- Slice 2B 表是 17 个 shared candidate 的完整 eligible migration map，
  不是每个文件所有私有函数的 inventory。
- accepted plan 的全局 Group C/D 与 migration scope 已明确
  `_parse_utc`、`_target_path`、`_validate_source` 为 defer；实现完整保留
  这些行为边界。
- 初审自身也确认 eligible 定义零残留、deferred 定义完整保留、运行时门禁
  全绿，因此没有实现缺陷或遗漏。
- Slice 2B 明确禁止修改 accepted plan；为一项非缺陷 observation 改写 plan
  会越过本 slice scope。

**结论**：拒绝，不修改 plan 或代码。re-review 应按 eligible map 与全局
defer 清单组合审计，不应把逐文件表误读为全私有函数清单。

### DS M2 — REJECT / non-defect

**初审主张**：四个私有 `_validate_source` 的静态输入类型未人为统一。

**裁决理由**：

- 私有 validator 的精确静态签名由各自真实 caller 边界决定；
  `ModelConfigJsonValue` 与
  `ModelConfigJsonValue | Mapping[str, ModelConfigJsonValue]` 的差异反映
  实际输入来源，不构成公共契约差异。
- 各函数运行时校验、异常行为与 public API 均未改变。
- `pyright dayu/services/` 为零错误，说明现有类型边界闭合；人为统一反而会
  扩宽无此需要的 caller 或隐藏精确信息。

**结论**：拒绝，不统一私有签名；后续只有在独立 validator 治理计划改变真实
边界时才重新评估。

### DS M3 — REJECT / non-defect

**初审主张**：五个 deferred `_validated_fingerprint` 的类型注解变化造成
diff 噪声。

**裁决理由**：

- 从 `object` 精化到 `ModelConfigJsonValue` 是接入 shared helper 精确签名
  所需的类型传播，同时消除 eligible migration path 上的 `object` 逃逸，
  且没有新增类型逃逸。
- 函数体、运行时校验与公共契约未改变；类型精化由真实 caller 支撑并通过
  pyright。
- review 可读性不是要求撤销正确类型边界的理由。

**结论**：拒绝；这是必要的正向修改，不是 maintainability defect。

### DS L1 — REJECT / non-defect

**初审主张**：Ruff 将 `dict(require_mapping(...))` 格式化为多行，单行 grep
不易审计。

**裁决理由**：

- 当前格式是 Ruff 接受的标准多行格式，不影响行为或可维护性。
- 结构审计应使用 multiline regex、AST 或上下文检索，不能要求生产代码迎合
  一个不完整的单行 grep。
- 两个 copy-mapping 文件的所有 adapter 已通过多行审计确认。

**结论**：拒绝，不改代码；re-review 使用 multiline/AST 审计。

### DS L2 — REJECT / non-defect

**初审主张**：`tests/README.md` 未逐项记录新增 malformed corpus。

**裁决理由**：

- `tests/README.md` 是当前测试入口索引，不是逐测试目录或 coverage ledger。
- 入口说明已准确更新为迁移后固定 corpus；新增 caller 回归和精确覆盖率已在
  implementation artifact 完整记录。
- 扩写逐测试细节会降低入口索引的稳定性，且没有修复任何行为缺陷。

**结论**：拒绝，不修改 README。

## MiMo findings 裁决

### MiMo L1 — REJECT / non-defect

**初审主张**：九个文件仍有 Ruff baseline 规则码。

**裁决理由**：

- 这些规则码在 `HEAD` 已存在；逐文件 rule-code multiset 差分确认本 slice
  零新增，且多处计数下降。
- HEAD baseline、无 delta regression 的信息不构成本 slice finding。

**结论**：拒绝，open count 归零。

### MiMo L2 — REJECT / closed-as-accepted-design

**初审主张**：`manual_recovery_application.py` 保留族 2 `_required_text`
及其 `object` 输入。

**裁决理由**：

- accepted plan 明确将 required-text 族 2–8 defer，因 NFKC、控制字符、
  空白与长度校验语义不同，不得顺手统一。
- 实现保留原运行时语义，测试与静态门禁均显示零 delta regression。

**结论**：拒绝为缺陷，按 accepted design 关闭。

### MiMo L3 — REJECT / closed-as-accepted-design

**初审主张**：两个 revalidation 文件保留 auto `_format_utc`。

**裁决理由**：

- accepted plan 明确 auto precision family defer；其 `.isoformat()` 语义
  不等价于 microseconds 或 seconds shared helper。
- 两个定义与 caller 均原样保留，characterization 与 write-model 回归全绿，
  零 delta regression。

**结论**：拒绝为缺陷，按 accepted design 关闭。

## MiMo §2.5 证据措辞纠正要求

MiMo 初审 §2.5 将 absolute-path/codec 的前置校验概括为所有 caller 均调用
shared `require_text`，该措辞不精确。正确事实是：

- `configuration_application.py`、`rollback_application.py`、
  `manual_recovery.py` 三个 family 1 caller 使用 shared `require_text`；
- `manual_recovery_application.py` 属于 family 2，继续使用 retained local
  `_required_text`；
- 所有 absolute-path/codec caller 都先经过**对应 text validator**，再把
  `text: str` 传给 shared `absolute_path`、`decode_base64` 或
  `decode_base64_strict`。

该问题是 review artifact 的证据措辞错误，不是实现 finding。MiMo re-review
必须明确核验并纠正此事实，不得再次声称所有 caller 都使用 shared
`require_text`。

## Re-review 验收条件

双路 re-review 应确认：

1. 上述 DS M1–M3、L1–L2 与 MiMo L1–L3 均已按 Controller 裁决关闭，
   open High/Medium/Low 为 `0`。
2. 无需且没有 production/test/README/plan fix。
3. eligible/defer、identity/copy mapping、fingerprint/time/codec family 及
   Cohort A/shared/plan 零 diff 结论维持。
4. MiMo §2.5 使用“对应 text validator”的正确描述，并准确区分三个
   family 1 shared caller 与一个 family 2 local caller。
