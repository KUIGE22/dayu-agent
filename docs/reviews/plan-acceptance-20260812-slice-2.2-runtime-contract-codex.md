# Slice 2.2 runtime contract corrective plan acceptance

- **状态**：`ACCEPTED / DEEPSEEK + MIMO FINAL2 PASS / IMPLEMENTATION MAY RESUME`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **reviewed target semantic SHA-256**：`6287a159552ca49edeb08b276e8480b01264367f32f34ac30c7108305de229a0`
- **reviewed fix SHA-256**：`21a3eb1e3260b66107e31b14e594f9be4bd54abc9e7849a62413dfeff3a9ef76`
- **closure target SHA-256**：`d47574b8943f5c3fdea208a0569d298081d424a52e423a9dd46a5edf1c62781d`（仅增加status/review metadata）；
- **closure fix SHA-256**：`b49bc222c55290604b2313f86807fba4ad5d468187d50b60c3b3980a8bb04b54`（仅增加final closure metadata）；
- **写入模型边界**：实现全部由Codex内部模型完成；DeepSeek与MiMo保留为独立审核，Terra仅作补充，MiM不参与以控制费用。

## 1. 接受结论

Controller接受`S22-CTRL-009`及首轮/closure观察的全部最终裁决。最终合同已经闭合：

1. lookback/scan-limit natural-key collision由两态scan origin、dominant audit合并、distinct双audit与batch构造期重复拒绝解决；
2. croniter-valid但无candidate在registration固定seed拒绝，持久表达式runtime exhaustion分别锁定activation只读、due只读与scheduler exit 1；
3. governance result携带correlation/job/attempt identity，Service集中构造并验证page一一对应，Worker按完整action矩阵消费；repository failure使用独立strict阈值，成功清零，耗尽安全退出；
4. pure Redis types归Worker，concrete adapter是唯一redis-py owner，settings失败不提前导入；URL query/fragment、surrogate和运行期意外异常边界均有精确门禁。

当前ScheduleService草稿、JobService/Redis WIP、尚未创建的Worker/Scheduler/startup/CLI都只是未接受实现现场。它们必须按计划恢复、补齐测试并重新通过所有门禁，不能从本plan acceptance推导为code acceptance。

## 2. 最终独立复审

- DeepSeek：`docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-final2-deepseek.md`，`PASS / open H/M/L=0/0/0`；
- MiMo：`docs/reviews/plan-review-20260812-072323-slice-2.2-runtime-corrective-final2-mimo.md`，`PASS / open H/M/L=0/0/0`。

历史source reviews保持原样：

- `docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-deepseek.md`；
- `docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-mimo.md`；
- `docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-final-mimo.md`。

## 3. 恢复与限制

- 恢复顺序：pure governance/config contracts → ScheduleService cron/audit → Worker-owned Redis ports/adapter → Worker/Scheduler → startup/CLI/CI/docs →真实PG/Redis/SIGTERM lanes。
- 每个changed production module必须独立coverage不少于80%，exact Pyright 0、Ruff、diff/allowlist/docs gates全部通过。
- 实施完成后必须再次取得DeepSeek与MiMo独立code review `PASS / open H/M/L=0/0/0`，才能创建accepted implementation commit。
- 本验收不授权live provider/model/broker/交易、不授权push或PR。

## 4. 计划文档门禁

- target/fix scoped `git diff --check`通过；
- source/final review artifacts保持独立身份；
- closure metadata不改变最终双审锁定的合同语义；
- accepted plan-fix commit只允许包含本计划、fix、source reviews与本acceptance artifact，严禁混入implementation WIP。
