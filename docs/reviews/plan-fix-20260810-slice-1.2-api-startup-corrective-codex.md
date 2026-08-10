# Slice 1.2 API/startup corrective plan fix

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Controller**：Codex
- **状态**：**CLOSED / DUAL PLAN RE-REVIEW PASS**
- **Source reviews**：Terra FAIL `0/2/0`；MiM Native 两项 observation
- **Implementation state**：frozen，零 code/test/README 编辑

## Accepted findings

1. **TERRA-S12-001 / Medium**：现有 `TenantId` 接受 non-UUID，DTO/API 与 stable
   errors 未冻结。S12-CTRL-05 已固定 canonical UUID boundary、exact request/projection、
   closed enums/JSON、protocol signatures、safe error hierarchy、CAS/not-found privacy 与
   invalid-scope no-SQL negative。
2. **TERRA-S12-002 / Medium**：production default provider 可被手工注入测试绕过。
   S12-CTRL-06 已要求 public `prepare_host_runtime_dependencies(..., provider=None)` 真实
   PG16 black-box、missing/blank/bad DSN safe failure、side-effect/engine cleanup、explicit
   provider priority 与 development fail-fast。
3. **MiM-001 / Low**：error class 未命名。已由 S12-CTRL-05 的五类 stable hierarchy
   闭合。
4. **MiM-002 / Low**：atomic rollback 未说明 DB transaction。已锁单 transaction，
   禁止 application-level delete/补偿与 partial commit。

## Scope integrity

修复不修改 `identifiers.py`、schema/migration、37-slice DAG 或后续 owner；generic ID
仍可服务现有非 PG caller，PostgreSQL physical admission 在 DTO/repository boundary 严格
收窄。没有 live/data/model/broker 外部动作。

## Corrective final review follow-up

MiM Native 已 PASS/open0。Terra 确认本 artifact 的四项 source findings 均闭合，但新增
`TERRA-S12-FINAL-001`：成功态 auto-created engine 缺 public/type-safe shutdown owner。
Controller 已接受，并在 S12-CTRL-07 与
`plan-fix-20260810-slice-1.2-lifecycle-corrective-codex.md` 冻结
`PreparedHostRuntimeDependencies.close()`、纯层 minimal lifecycle、exact-once `atexit`
兜底及 explicit-provider caller ownership。implementation 继续冻结等待最终双路复审。

## Final closure

Terra 与 MiM Native final closure 均 PASS、open H/M/L=`0/0/0`。全部 accepted finding
与 lifecycle follow-up 已 CLOSED，无 remaining plan gap。
