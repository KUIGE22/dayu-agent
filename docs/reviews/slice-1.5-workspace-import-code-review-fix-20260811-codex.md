# Slice 1.5 workspace import — code review fix

- **Work unit**：Investment Platform Restoration
- **日期**：2026-08-11
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Adjudication**：
  `docs/reviews/slice-1.5-workspace-import-code-review-adjudication-20260811-codex.md`
- **Round2 fix**（2026-08-11 1112 Terra 复审 finding）：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round2-20260811-codex.md`
- **Round3 fix**（2026-08-11 1142 Terra 复审 finding，deepseek-flash）：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round3-20260811-deepseek-flash.md`

## Applied fixes

1. **Import-mode isolation**：无主开关、重复主开关及重复 import 语义参数在任何普通
   init side effect前 fail closed。
2. **Secure closure reader**：以唯一 root FD capability 完成 descriptor-first、
   member-second acquisition；component/leaf identity preflight→no-follow open→`fstat`
   exact；全部 member FD 绑定后才读；所有 validator 通过 immutable reader snapshot
   消费，不复制 parser、不落盘正文、不 global monkeypatch。
3. **Global identity uniqueness**：跨 company canonical security、bundle identity、
   repository locator 在 DB connect前拒绝。
4. **Independent descriptor digest**：移除 `or True`，由测试独立读取 descriptor bytes
   计算 SHA-256 并与 typed result/PG row比较。
5. **Artifact precision**：`object.__setattr__` 明确记为 AGENTS 允许的 frozen-dataclass
   构造期窄豁免，不声称源码不存在该调用。

## Safety properties locked by tests

- descriptor/member preflight→open identity race稳定拒绝；FD 后 pathname replacement
  只能读取已绑定 bytes；preflight 前 regular replacement必须继续通过完整 owner语义；
- descriptor/member/root/intermediate FD 在 success、exception、`BaseException` exact close；
- monitoring/source-map、workbook/progress、checklist、source manifest/company facets
  reader分支对 legacy source-tree ordinary I/O=0；package assets仍由原 owner读取；
- `content_reader=None` public return/error/warning/call order保持既有 golden；
- import 参数错误与跨 company duplicate均发生在 DB/文件副作用前。

## Verification

332 focused、733 unit、47 PG16、8108 clean Python 3.11 tests全部通过（round2 最终
数字；round1 fix 快照 8102 + round2 新增 6 项 CLI import 测试）；changed pyright/Ruff
为0；新增/修改 production逐文件 statement coverage均 `>=80%`；diff-check、allowlist、
DAG/import、secret/raw/temp卫生通过。

本 fix artifact 等待 Terra + MiM Native 双路 code re-review；未 commit、push、PR，未运行
live/network/model/broker。

Terra 复审（111012）提出唯一 finding——主开关重复被静默折叠；Controller ACCEPT 并已在
round2 fix artifact 中修复。本 round1 fix artifact 的验证结果均为 round1 快照，
round2 增量验证见 round2 fix artifact。

Terra 复审（114214）提出唯一 finding——新代码使用 `object`/`Any`；round3 fix artifact
（deepseek-flash）已修复：`_ImportSemanticStore` 拆为两个精确 action、
`parse_json_object` 改为 strict `validate_json_object_text`，新增生产签名
object/Any delta=0。最终 Terra `code-review-20260811-121322.md` 与 MiM Native
`code-review-20260811-121507-slice-1.5-final.md` 均 PASS/open0；本 artifact
随全部 round findings 一并 CLOSED。
