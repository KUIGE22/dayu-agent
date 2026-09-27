# Slice 3.1 汇总认证时钟修复 V3（待独立接受）

## 审查裁定与实现

- 基线 `a1720512f9043318e74a8c4dea1f756a5fd4a29d`，branch `codex/investment-platform`；V9及生产 auth/domain/ORM/0007/public protocol 不改。
- 独立 `code-review-20260928-073840.md` SHA `4b5f02d8fc8b0cafd87a502923083d1ba74072af167fb665b700fe8af3f0209e`，FAIL fresh `0/0/1`。前两项重试 M 已在最终真PG范围关闭；新的L1是新增auth测试把PG授权时刻与宿主now比较。最终完整77运行为76 passed/1 failed，PG领先19.430ms，后续auth检查未执行。保留失败与此前接受记录，不用重跑或容差抹掉。
- Controller接受L1。仅改auth测试：在同一 READ COMMITTED session 的 authorize 前后取 `statement_timestamp()`，第二界在另一连接撤销提交之后，断言两界为datetime且 `before <= witness.checked_at <= after`，保留事务与四种撤销循环；移除宿主now/timezone。生产授权SQL和线性化点不变。tests README同步测试时间来源。
- 前版M1/pair/M2实现报告保留原字节；本版生产仓储及evidence PG用例保持V2最终身份。

## 最终五文件身份

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/storage/postgres_evidence.py` | `5d66d1f85a5b91d5e1089eae58efd5c3f337bb240879e316672e75556d046326` | 78910 | 1809 |
| `tests/integration/investment/test_postgres_evidence.py` | `00ebe6855d1bd044e62cd4ff087c28c2ff36f4f0315f929b5533dc962677a288` | 97477 | 1915 |
| `tests/integration/investment/test_postgres_evidence_auth.py` | `e9c9519b7ffdffabb827393a4b62ca6c3057c00819bb3f116bd1cfeba4e93686` | 27717 | 695 |
| `dayu/investment/README.md` | `84fd1d020e7814685167245dae73d29cde7f295f77d473fb9e24851349e3568c` | 27459 | 380 |
| `tests/README.md` | `235c08c2d046fe47ff27f474cf1d1cd72b1c2195e81292f77d2a56d5356a7c5f` | 136246 | 635 |

## 实测与待完成Gate

- Root最终auth用例：**1 passed / 2.64s**。串行用例完整执行了四类撤销、REPEATABLE READ拒绝与SQL故障回滚/脱敏；该结果在真正修复后获得，没有扩大宿主时钟容差。该Python文件pyright **0 errors/0 warnings**、Ruff `E4,E7,E9,F,I` PASS；diffcheckPASS。
- 独立前版同生产身份的repository19/migration57已绿；实际statement534/645=82.7906976744%、branch168/238=70.5882352941%、combined702/883=79.5016987542%。它不是本版auth77成功证明；本版五文件的独立77+coverage正在单lane运行。
- 当前L1为已修复候选，完整aggregate历史docs链核对仍待非作者结论；不据Root测试自行接受aggregate、PR、S3.2、十shape/H2或总目标。
- 已分类残余沿V9：非material conflict及resolved open retry语义待独立owner；direct review_required→begin成功PG未单列、fixture setup-failure未注入、不可合法损坏的immutable source缺失仅静态guard；实际branch未达80%，AGENTS语句门已满足；Fins最终owner/freshness与full ten-root/30arm/legal-history另属后续Gate。
- S32 V1/V2/V3与planreview是另一docs lane，排除本实现暂存。下一入口为独立fullaggregate结论、必要fix/re-review、Controller裁定、精确index验证和accepted deepreview commit，然后按用户原授权进入交付Gate。
