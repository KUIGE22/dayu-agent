# S31-Auth 参数日志增补 V1：Controller 计划接受

- 决定：**接受** `docs/plans/2026-09-27-slice-3.1-s31-auth-logging-addendum-v1.md`，最终磁盘 SHA-256 `dbf930b922ee80c1461c1f7466a6fa47728b775bfb5a4ac0e27d5583d30b4117`，6230 bytes / 32 LF；仅对已接受 Slice 3.1 V9 的 S31-Auth 日志安全修复生效。V9 SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2` 保持不变。
- 直接 finding：`docs/reviews/code-review-20260927-200816.md`，SHA-256 `a3721fd1dfc9b0ab3699686bcc390ca41fb444b4a5142950a1aa5ee049fe4022`，独立 code review `FAIL H/M/L=0/1/0`；token hash 的 SQLAlchemy INFO 参数日志是尚未修复的唯一 M。
- 独立 planreview：`docs/reviews/plan-review-20260927-201209.md`，SHA-256 `8ece7f7eea0d3847304cda1070075b45988303803d79820b4e06001186a77f3c`，fresh `PASS H/M/L=0/0/0`。审查确认增补仅扩 `dayu/investment/storage/db.py` 的平台 Engine 隐藏参数设置，并把同一事务 Connection 上的校验、SET LOCAL/readback、授权 SELECT 与 PG INFO 日志正反例写成可实施契约。
- Controller 裁决：该变更修补 V9 §3.3 既有 raw/hash 不进日志的安全条件，动机来自真实执行路径；不改变业务目标或 S31-A/B、0007、issuer、Fins、十 shape 范围。增补 §2 与 §3 在 S31-Auth 的参数日志实施方式上优先；V9 其余条款继续适用。允许按增补实施最小修复，并以独立 code re-review 决定旧 M 是否真正闭合。
- 当前 Gate：`S31-Auth code-review fix`；后续依次为验证、独立 re-review、accepted slice commit。**计划 PASS 不清除代码 M**，也不授权 S31-A、V7 authority、accepted slot、S5、D0、Gate 或任何真实交易。
