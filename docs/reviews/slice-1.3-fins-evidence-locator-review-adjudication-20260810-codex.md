# Slice 1.3 Fins Evidence Locator code-review adjudication

- **Work unit**：Investment Platform Restoration / Slice 1.3
- **Controller**：Codex
- **日期**：2026-08-10
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **基线**：`3a70a16`

## Review sources

- Terra：`docs/reviews/code-review-20260810-slice-1.3-evidence-locator-terra.md`
  - 结论：FAIL，open H/M/L = `2/1/0`。
- MiM Native：`docs/reviews/code-review-20260810-slice-1.3-evidence-locator-mimo-native.md`
  - 结论：FAIL，open H/M/L = `0/1/0`。

## Controller adjudication

### S13-CR-01 — ACCEPTED / HIGH / OPEN

- 来源：Terra F-01。
- 事实：公开 Runtime/Service 接口接收 typed DTO，但 `_to_evidence_identity()` 与
  `_locator_to_evidence_identity()` 丢弃 request 的 `schema_version`、两类 DTO 的
  `repository_id`，并且没有执行与 strict parser 等价的完整 invariant 校验。
- 影响：调用方可绕过 parser，令 unknown schema/repository 或 kind/payload 不一致的
  DTO 进入 resolve/validate/read；citation 还会保留未经校验的 caller locator。
- 裁决：必须在 domain owner 提供 DTO invariant validator，并由三个 Runtime public
  方法在任何 identity 投影前调用。direct-construction 反例必须进入持久测试。

### S13-CR-02 — ACCEPTED / HIGH / OPEN

- 来源：Terra F-02。
- 事实：counterpart 的 `is_deleted=true` 会被当前 preflight 当作 inactive，但底层
  `FinsToolService` 的 source-kind fallback 只依赖 handle/meta 存在，仍可能 filing-first
  读取逻辑删除的 counterpart。
- 影响：processed fragment bytes 可能来自错误 source kind，而 locator identity、primary
  SHA 与 processed closure 仍绑定请求 source，形成可通过现有 postflight 的错误证据归属。
- 裁决：在当前不修改 tools public API 的边界内，只要 counterpart 对工具仍可发现就必须
  fail closed，包括逻辑删除。补双向、三个 public API 和 processed kind 前置拒绝测试。

### S13-CR-03 — ACCEPTED / MEDIUM / OPEN

- 来源：Terra F-03。
- 事实：四个 non-document nested payload 未执行 exact-key 校验，多余字段被静默丢弃。
- 影响：raw payload 与 canonical projection 不再一一对应，违反 strict schema contract。
- 裁决：page/section/table_cell/xbrl_fact 均须拒绝 missing/unknown nested 字段，并覆盖 request
  与 projection parser。

### S13-CR-04 — ACCEPTED / MEDIUM / OPEN

- 来源：MiM Native Finding 1。
- 事实：`get_primary_file()` 位于现有 `try/except OSError` 之外，仓储 metadata 的
  `FileNotFoundError` 会裸逃逸。
- 影响：上层仅捕获 `EvidenceLocatorError` 时无法获得稳定 fail-closed 错误路径。
- 裁决：将该失败统一包装为 `EvidenceLocatorError(code="primary_read_failed")`，并补
  `get_primary_source().open()` 成功但 metadata 读取失败的回归测试。

## Duplicate and rejected observations

- 无 duplicate。
- 无 rejected finding。

## Required closure gates

1. 四项 accepted finding 均有生产修复和 adversarial regression。
2. 原 71 项新增测试不得回归；相关 Fins/services/application/architecture 测试通过。
3. 修改的 production/tests Pyright 为 0，Ruff 与 `git diff --check` 通过。
4. 每个修改 production 文件 statement coverage 不低于 80%。
5. 修复后必须由 Terra 与 MiM Native 各自独立 corrective re-review，二者均 PASS 且
   open H/M/L=`0/0/0` 才能进入 accepted commit。

## Scope and safety

- 不授权修改 `dayu/fins/tools/service.py`、storage implementation、processor、investment、
  migration、startup、根 README 或 master plan。
- 不授权 live/network/model/broker、commit、push、PR 或进入 Slice 1.4。

## Fix handoff

- 修复实现：`docs/reviews/slice-1.3-fins-evidence-locator-review-fix-20260810-deepseek.md`。
- Controller focused 复验：105 passed；目标 production/tests Pyright 0；Ruff 通过。
- S13-CR-01..04 均已落盘并有针对性回归，但在 Terra 与 MiM Native corrective
  re-review 均 PASS 前仍视为 open。

## Corrective re-review round 1

- MiM Native：`docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-mimo-native.md`
  判定 PASS、open H/M/L=`0/0/0`；该结果只证明其覆盖面内的四项原 finding 已闭合，
  不能覆盖 Terra 随后发现的新反例。
- Terra：`docs/reviews/code-rereview-20260810-slice-1.3-evidence-locator-terra.md`
  判定 FAIL、open H/M/L=`0/1/1`。

### S13-CR-05 — ACCEPTED / MEDIUM / OPEN

- direct DTO 的 `PageLocatorPayload(page_no=True)` 与
  `TableCellLocatorPayload(row_index=True)` 会利用 Python `bool` 是 `int` 子类的语义
  穿过 validator；page 反例已真实进入 Runtime 并生成 projection。
- 修复必须把真实 int、非 bool、正数/非负数范围收敛为 domain 单一 helper，由 parser
  与 DTO validator 复用；补 page/row 的 bool、非 int、负值 direct-DTO 反例，并覆盖
  resolve/validate/read 和 processor-before-reject。

### S13-CR-06 — ACCEPTED / LOW / OPEN

- 新增 domain owner、runtime helper 与 testkit 明确新增多处 `object`/
  `Mapping[str, object]` 签名，违反根 `AGENTS.md` 与 S13-CTRL-08；implementation/fix
  artifact 的“无新增 object”声明不符合当前 diff。
- 修复必须使用严格递归 `JsonValue`/`JsonObject`、现有 domain/protocol 类型及精确回调
  签名替代本 Slice 新增的 `object`；不得以 `Any`、`cast`、ignore、getattr/hasattr 或新
  seam 转移问题。以 diff-added-line forbidden scan、Pyright 和 Ruff 作为闭环证据。

## Corrective fix round 2 handoff

- 修复证据：
  `docs/reviews/slice-1.3-fins-evidence-locator-corrective-review-fix-20260810-deepseek.md`。
- S13-CR-05：domain 新增共享 `_require_real_int`，parser 与 direct DTO validator
  共同拒绝 `bool`/非 `int`，并保留 page 正数、row 非负数约束。
- S13-CR-06：本 Slice 新增 owner/testkit/tests 已改用递归 `JsonValue`/`JsonObject`
  与精确协议类型；untracked 新文件 forbidden scan 为 0。tracked runtime diff 中唯一
  命中的 `Any` 是 HEAD 已存在的 typing import，未新增语义用法。
- Controller 独立复验：核心三文件 `116 passed`，application/runtime owner
  `36 passed`；目标 production/tests Pyright `0 errors`；Ruff F/I 与
  `git diff --check` 通过。
- 当前仍保持 `REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW`；S13-CR-01..06
  只有在 Terra 与 MiM Native 最终复审均 PASS、open H/M/L=`0/0/0` 后才关闭。

## Final closure

- Terra 最终复审：
  `docs/reviews/code-final-rereview-20260810-slice-1.3-evidence-locator-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- MiM Native 最终复审：
  `docs/reviews/code-final-rereview-20260810-202442-slice-1.3-evidence-locator-mimo-native.md`，
  PASS，open H/M/L=`0/0/0`。
- Controller 结论：S13-CR-01..06 全部 CLOSED，当前 open H/M/L=`0/0/0`，
  无需进一步 code/test/README/plan fix；Slice 1.3 可进入 accepted commit。
