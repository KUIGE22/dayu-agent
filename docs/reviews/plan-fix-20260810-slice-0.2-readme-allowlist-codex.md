# Slice 0.2 README allowlist plan fix

- Plan：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Trigger：Slice 0.2 code review Terra 006 / MiM 4
- Base / predecessor accepted commit：`d5f024d`
- Status：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**

## Proven gap

Master plan §9 把 `dayu/investment/README.md` 的依赖方向、模块 owner、
composition 与开发命令列为 hard gate；Slice 0.2 实际新增 `config.py` 和
`composition.py`，但其 allowlist 没有该 README。worker 若遵守 allowlist，包级文档
就继续错误声称只有 Slice 0.1 domain 骨架；若更新 README，则越过 accepted allowlist。
两项契约无法同时满足，因此是计划缺口，不是单纯实施遗漏。

## Bounded correction

1. 只把 `dayu/investment/README.md` 加入 Slice 0.2 allowed paths。
2. 只在 Slice 0.2 completion 增加当前 `config.py` / `composition.py` owner、依赖边界
   与开发命令同步要求。
3. 不改变任何 production schema、protocol signature、runtime behavior、DAG、slice
   count、integration lane、Paper/Live gate 或后续 owner。
4. code-review 的 circular import、secret redaction、startup atomicity、runtime Service
   protocol 与 test escape findings 仍由 code fix 关闭，不能以本 plan erratum 代替。

## Freeze evidence

plan-fix 期间 production/tests/README WIP 不得编辑。进入 plan-fix 前的 bounded WIP
diff SHA-256 为
`878e17b19982f092c3e6dff50af8065ad43236d2240cf6fefc2367c65653d2d4`。

## Review request

请 Terra 与 MiM 独立确认：allowlist 与 §9 文档 hard gate 已一致；纠正没有扩大
Slice 0.2 runtime scope、没有引入 future owner，也没有改变 37-slice DAG。双路 open
H/M/L 必须为 `0/0/0` 后，code fix 才能恢复。

## Dual plan re-review closure

- Terra：`docs/reviews/plan-review-20260810-094300-slice-0.2-terra.md`，
  PASS，open H/M/L = `0/0/0`。
- MiM：`docs/reviews/plan-review-20260810-094300-slice-0.2-mimo-native.md`，
  PASS，open H/M/L = `0/0/0`。
- 两路均确认 erratum 只增加一个 README allowlist 路径及对应 completion，未改变
  runtime、schema、protocol、DAG、37-slice count、future owner 或 live gate。
- 冻结 WIP SHA-256 仍为
  `878e17b19982f092c3e6dff50af8065ad43236d2240cf6fefc2367c65653d2d4`。
- plan gap 已关闭；这不关闭 `slice-0.2-code-review-adjudication-20260810-094100-codex.md`
  中的代码 findings，code fix/re-review 仍为必需。
