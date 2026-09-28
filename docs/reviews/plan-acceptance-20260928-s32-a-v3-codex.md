# S32-A V3 Controller 计划采纳与上游冻结

## 限定裁定

Controller 已完整读取冻结 V3 与独立报告，采用 **S32-A 单个行为增量**：可信 Service → 严格 Fact proposal parser → Fins owner validation/citation readback → 单 PG 事务 candidate + immutable intake receipt。独立计划复审 fresh H/M/L **0/0/0**；原 V1 三项 M、0008 downgrade OQ 与新 head receipt FK fixture 清理缺口仅在计划文本收束。此裁定允许按已审 V3 实施和验证，不接受尚未存在的实现，也不关闭 S32-B、完整 Slice 3.2 或业务闭环。

- cwd `/Users/wsk/workspace/dayu-agent`；上游最终 delivery commit **afe53dd2c544767dfbf017b2ce1e11cdd66dc32a**，branch `codex/investment-platform`。S31 closeout `docs/reviews/final-closeout-20260928-s31-codex.md` SHA `082170b6b1e3cc1fcaf9d7e1b49222286a07cdab3e1ed219cd484a99a18c17c8`，6996B/45LF。
- S31 PR #3 https://github.com/KUIGE22/dayu-agent/pull/3：draft/open/unmerged，base `codex/slice-3.1-base` SHA `7ae26fd1a343547600e4fdd7478a510780c14450`，head afe53；76 remote filenames 与 local diff集合一致；既有73 source-stage Git blob已核 ed887，afe53仅三件文档。statuses/workflow runs为空，不声称 CI PASS；afe53 check-runs 未重新查询，ed887实际为0。main仍 `7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`，不是 merged/shipped 状态。
- S31 上游本地汇总、PR scoped review 和 closeout已完成；未来上游合并的冲突/rebase仍属交付义务。S32在新本地分支 `codex/candidate-intake-v3` 从精确 afe53开始，当前PR3 head固定，不将新行为加入原PR3。用户自主继续指令构成 ordinary 实施/验证/草稿交付授权，无额外人工许可等待。

## 冻结输入和既有失败

| 输入 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `docs/plans/2026-09-28-slice-3.2-candidate-intake-v3.md` | `04cfb13a556fdec21fdba9bcebcad044133ae0364a089ef8487230687aec67ed` | 33858 | 151 |
| `docs/reviews/plan-review-20260928-084010.md` | `b4fce369dcb05ef62a491436b39e4a504a95b12028a32e76744c4cbef0c59f12` | 20712 | 100 |
| V1 `docs/plans/2026-09-28-slice-3.2-candidate-intake-v1.md` | `bbd71b8128b772767c429ed5a55ccb5999b9753cac5de89e712b0475a62ae566` | 26023 | 130 |
| V2 `docs/plans/2026-09-28-slice-3.2-candidate-intake-v2.md` | `aab710a616d89cd573baa3a237882494f951e60f360a016050b675403425a018` | 32210 | 149 |
| V1 FAIL `docs/reviews/plan-review-20260928-072815.md` | `18041a9e218fa79c032f04b4ad0d65f50743451527d8b962cec3b7bdf52a1df6` | 19014 | 109 |

V1 FAIL 0/3/0 与未审 V2 原字节保存，不能覆盖或追授 PASS。Controller 重读 V3/report 到 true EOF，按独立报告代码事实表逐件重核27个 tracked源的 SHA/bytes/LF、O_NOFOLLOW regular单link稳定fstat，并比对 afe53 HEAD blobs；tracked working tree/index为空。报告表是身份全集，实际计划语义覆盖仍限报告声明的相关章节，未扩成全仓审查。S31四项新代码/test/README身份与上游一致，旧77/264、PR3新21/独立4不算新S32执行。

## 实施允许范围、输出缺席与门序

允许的实际生产/测试/README路径严格采用 V3 §8；新增11路径实施前必须不存在。纯domain/parsing、窄CandidateIntakeRepository Protocol/实现、0008 own schema和research Service作为一个行为同时完成；禁止改Fins owner、旧0001–0007/auth helper、Host/Agent、registry、CLI、workspace import、交易。0008由既存 head plugin纳入，fresh独占PG16验证，不迁真实用户库；pin0007旧测试保留精确门，newhead fixture同批receipt+原六表清理，无CASCADE/停约束。

具体代码边界、九键/四value/五locator、closed拒绝码、first-committed immutable receipt、五命名unique恢复键、SAVEPOINT rollback后requestedtenant+operation full receipt、自闭合损坏分类、19列/FORCE RLS/append-only/empty-only NOWAIT downgrade和强矩阵全部按冻结V3，不由作者扩写未定义规范。未知必须变更owner或契约时新澄清版并独立审查。

本文件+V1/V2/V3+原FAIL+独立V3 PASS必须先 exact allowlist stage、nonempty index diff-check、disk/index blob身份一致后 commit，再写实现。accepted plan commit SHA由 Git 外部记录，不在本文件自引用。实现后实际unit/PG16/strict types/Ruff/每修改生产文件statement coverage≥80（branch/combined另报）→报告/职责README→非作者deepreview/fix/re-review→accepted slice commit→PR scoped review/closeout。shared PG一次一lane，未执行collection不能当运行。无外部review提交/评论/合并/批准/真实订单。

## 保持未闭合目标

十shape完整递归值/坏子/合法placement与readback/30arms/T1H-A2-G1 parents/RouteA、V8 source/H2/H1/V17/S5/D0/Gate保持OPEN；V8规则V2的限域PASS/输入冻结不能由S32采纳自动关闭。human/service promotion、候选CAS、精确source PIT、Fact/Claim+promotion审计同事务与每次消费Fins门归S32-B。原shadow-only业务目标active，无broker/live资金连接。
