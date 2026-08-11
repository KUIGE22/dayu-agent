# Slice 1.5 secure closure reader — plan acceptance

- **Work unit**：Investment Platform Restoration
- **Gate**：Slice 1.5 implementation code-review plan-gap closure
- **Controller**：Codex
- **日期**：2026-08-11
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**

## Accepted contract

S15-CTRL-15 采用唯一 root FD capability 与两阶段 FD acquisition：

1. descriptor relative to root capability 完成 component/leaf identity preflight、no-follow
   open、`fstat` exact，仅读取一次并保持 FD；
2. bundle owner 对 immutable descriptor payload 做唯一的纯词法 reference canonicalization；
3. 所有 member 逐段 identity preflight、no-follow open、`fstat` exact，全部 member FD
   绑定后才读取 member bytes；
4. 所有 validator 只消费 immutable reader mapping；reader lookup 零 filesystem I/O，
   `content_reader=None` 保持既有行为；
5. 合同明确不是 filesystem-wide 原子快照：preflight 前 regular replacement 可作为 current
   candidate并接受完整 owner validation，preflight→open race 拒绝，FD 后 pathname replacement
   不改变已绑定 bytes。

## Review evidence

- Initial Terra：`docs/reviews/plan-review-20260811-101156.md`，FAIL，2H/1M；
- Initial MiM Native：
  `docs/reviews/plan-review-20260811-101422-slice-1.5-secure-closure-reader-mimo-native.md`，
  PASS，open 0/0/0；
- First corrective Terra：`docs/reviews/plan-review-20260811-102102.md`，FAIL，1H；
- First corrective MiM Native：
  `docs/reviews/plan-review-20260811-102202-slice-1.5-corrective-rereview-mimo-native.md`，
  PASS，open 0/0/0，但早于第二次 Controller correction；
- Final Terra：`docs/reviews/plan-review-20260811-102650.md`，PASS，open 0/0/0；
- Final MiM Native：
  `docs/reviews/plan-review-20260811-102848-slice-1.5-final-corrective-closure.md`，
  PASS，open 0/0/0。

`S15-ERR-01/02/03` 全部 CLOSED。最终 plan-review open H/M/L=`0/0/0`。

## Authorization boundary

本 acceptance 只解除 Slice 1.5 B/C/D implementation 冻结。它不关闭既有 code findings，
不授权 live/network/model/broker，也不授权 push 或 PR。实现必须遵守 exact allowlist、逐文件
coverage `>=80%`、PG16、clean Python 3.11、changed pyright/Ruff、DAG/import smoke、
reader=None golden、完整 replacement/FD-close adversarial matrix，随后经 Terra 与 MiM Native
双路 code re-review open 0。
