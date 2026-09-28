# Slice 3.1 汇总重试修复 V2（待独立接受）

## 原报告和本版裁定

- 基线仍为 `a1720512f9043318e74a8c4dea1f756a5fd4a29d`，branch `codex/investment-platform`。V9、auth、domain、ORM、0007与public protocol签名均不改。
- 原 M1 `code-review-20260928-072218.md` SHA `2b7e054e43a874ffe989082063196888354f72f2ea5641efc8cb16f206277304`、首次实现记录 SHA `9b9e9a37f42ae13f279f4819bb7982bd7375927481756ac2ac1936764bb5944c` 保留。
- 首次复审 `code-review-20260928-073107.md` SHA `9fd97242fe2e6e4d61205d9edd32890ec5fb717890f009c6f554f1492ef80517` FAIL `0/1/0`：M1 caller分类部分已修，持久FP pair不一致仍被当caller conflict。Controller接受，增加持久 pair guard 与合法rawConflict FP漂移PG反例。
- 继续aggregate的 `code-review-20260928-073330.md` SHA `a035ade41a928592ad7848791e500cecc581d68bd47680e0a393a7c77a17cf2b` FAIL `0/1/0`：Aggregate-M2，通用copy重试把source.version_no与本次caller expected比较。Controller接受，按同一V9规则修append/begin/review。所有旧FAIL不覆盖，不叠加成新的fresh计数或假PASS。

## 最终四文件变更与身份

- resolve retry：以持久Conflict查原successor；transition、持久fingerprint pair、witness pair、copy source自身邻接先闭合。完整request/actor fingerprint不同为稳定业务冲突；相同fingerprint下的持久投影/links差异为存储失败。
- 通用copy retry：mode差异先返回业务冲突；持久copy模式缺source仍存储失败；source与已提交successor的自身邻接校验不消费本次caller expected。随后完整request fingerprint分类caller变化；原copy历史重试不依赖current head。
- 真PG已有用例增加真实第二reviewer、resolve的八种caller变化、append/begin/review的same-operation changed expected、同主体新token原请求成功、合法Conflict fingerprint/policy漂移精确storage failure及复原成功。完整head/Version/Link/Conflict JSONB快照证明失败/重试不改历史。没有关闭RLS、删除immutable行、降低约束或伪造认证grant。
- README只同步这两条稳定错误边界与测试职责。

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/storage/postgres_evidence.py` | `5d66d1f85a5b91d5e1089eae58efd5c3f337bb240879e316672e75556d046326` | 78910 | 1809 |
| `tests/integration/investment/test_postgres_evidence.py` | `00ebe6855d1bd044e62cd4ff087c28c2ff36f4f0315f929b5533dc962677a288` | 97477 | 1915 |
| `dayu/investment/README.md` | `84fd1d020e7814685167245dae73d29cde7f295f77d473fb9e24851349e3568c` | 27459 | 380 |
| `tests/README.md` | `58c73e2f59d777eaa339a104d95cc9bdb83a7cf6412e9213f1dba3b3dd621b18` | 136137 | 635 |

## 实际验证及下一 Gate

- 最终5d66/00ebe身份关键PG用例 **1 passed / 3.80s**，覆盖三个通用入口新增changed expected、resolve全部caller与两类历史漂移。最终两Python路径，激活venv并指定正确pythonpath：pyright **0 errors/0 warnings**；Ruff `E4,E7,E9,F,I` PASS；非暂存diff check PASS。
- 中间254ad8/9591身份曾跑全repository **19 passed / 29.32s**，statement `534/644=82.9193%`、branch `167/236=70.7627%`、combined `79.6591%`。这是有身份限定的前版结果；不拿它冒充本版最终coverage/full-suite pass。最终全部PG/coverage由独立aggregate lane下一步实测。
- 当前M1/pair/M2均为已修复候选，尚待非作者复审；完整aggregate仍INCOMPLETE。此报告不是accepted slice/deepreview、PR、S3.2或十shape/H2接受。
- 新operation携stale expected的CAS拒绝已有repository路径与测试；同operation变化在新PG断言中明确business conflict，不把两者混淆。真缺source/version因DB FK/append-only而不能合法破坏，guard静态核对，未声称做过降约束破坏测试；独立review裁决该残余。
- `material=False` resolution与resolved后open-operation retry规则、direct review_required→begin成功PG单列、fixture setup-failure、source消费freshness及原auth host/PG时钟偶发比较仍保留原owner与边界。后续业务阶段与完整十shape递归要求不缩减。
- 下一入口：独立review继续剩余base→HEAD新增/改动路径，必要真PG auth→evidence→migration三文件验证；无blocking finding、覆盖完整、残余分类后才Controller接受并stage精确本Gate文件。S32 V1/V2计划与planreview属另一docs lane，不能混入本实现提交。
