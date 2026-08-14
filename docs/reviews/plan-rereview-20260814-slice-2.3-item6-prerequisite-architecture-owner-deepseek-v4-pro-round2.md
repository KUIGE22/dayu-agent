# Slice 2.3 Item 6 prerequisite architecture-owner 计划复审（DeepSeek V4 Pro Round 2）

- 日期：2026-08-14
- 时间戳：20260814-084807（本机系统时钟，CST）
- 角色：fresh independent DeepSeek V4 Pro plan re-reviewer（只读复审，不实现、不修复、不运行 test/PG，不 stage/commit/push/PR/network）
- Model / route：model ``deepseek-v4-pro[1m]``；route 为本机 Claude Code CLI 会话（用户直接 dispatch 的内联复审指令），无外部 API/网络调用。
- 未读取、未采信任何 Round 2 MiMo output：本 item 不存在名为 prerequisite-architecture-owner 的 MiMo round2 artifact；
  目录中仅有的 ``*-mimo-round2*.md`` 属于另一 item（job-request-identity），本轮未打开。
- Gate：Gateflow Item 6 prerequisite architecture-owner corrective plan（exact13 candidate）fresh same-SHA Round 2 复审。
- 结论：``PASS / open H/M/L=0/0/0``。本结论只是双路复审中的一路；Controller acceptance 仍须 fresh MiMo Round 2
  独立 ``PASS / open H/M/L=0/0/0``。

## 1. Reviewed frozen identity（SHA/行数均为本轮直接实测）

| File | SHA-256 | Lines |
|---|---|---:|
| ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``（target） | ``451daa12bc53750aa7f7d59e7f6a966ee7469b6bdce662a59999f3c0f0710204`` | 3614 |
| ``docs/plans/2026-08-10-investment-platform-restoration.md``（master） | ``47c130f6cf99e188dbec2a8040fa6f3b1a7144e320bfcdad62d88776312097fb`` | 4566 |
| ``docs/reviews/plan-fix-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md``（fix） | ``f1b7e8b3bb28e2c1dfea713ec555c094b57c39d6bf5427b27cfccdfcc1a5fcb0`` | 169 |

三份 SHA 与 dispatch 指令给定值逐一相等，与 Round 1 所锁旧三 SHA（target ``db4d4d3c…``/3607、master
``6b50135e…``/4554、fix ``e07fc4c8…``/156）不同，与 fix doc 声明的"字节已变化、须重新冻结"一致。

## 2. 不可变先前评审（均已完整读取）

| Artifact | SHA-256 | Lines | Verdict |
|---|---|---:|---|
| ``plan-review-20260814-080306.md``（initial，immutable） | ``b588832ef852dea72652b93cef4a4bc0dbafec6a8504bce80d24527c100a7e06`` | 55 | ``FAIL / 1/0/0``，唯一 High ``S23-I6-PR-01`` |
| ``…-owner-deepseek-v4-pro.md``（Round 1，immutable） | ``5e4aed3533d85d8fdb28af2b0a698624f9d7439aaa34abe425dd1285b868e7ba`` | 87 | ``FAIL / 0/0/1``，唯一 Low ``S23-I6-DSV4P-REREVIEW-01-L`` |
| ``…-owner-mimo.md``（Round 1，immutable） | ``3ad043a43feacc1ca0b1c3730d03799c46437188d529c888081c1259d4b5bcef`` | 134 | ``PASS / 0/0/0``，锁定修复前旧三 SHA，因字节变化 ``SUPERSEDED`` |

本复审不改写任何先前结论，也不把历史 Round 4 ``PASS`` 或 Round 1 MiMo ``PASS`` 当作本轮 closure evidence。

## 3. 唯一 Low 的闭合判定（S23-I6-DSV4P-REREVIEW-01-L）

Round 1 Low：fix doc 把 85→87 计数误标给生产 ``dayu/investment/storage/postgres_sources.py``，而计数实际属于
gate 被扫描主体 ``tests/integration/investment/test_postgres_sources.py``。本轮判定为**已闭合**，直接证据：

1. 新 fix doc L34–39 已明确：owner-contract 扫描主体为 ``tests/integration/investment/test_postgres_sources.py``，
   HEAD 85 个函数（top-level 58、nested 27），冻结 WIP 新增两个 top-level provenance tests 后为 87（top-level 60、
   nested 27）；production ``dayu/investment/storage/postgres_sources.py`` 冻结 WIP SHA
   ``4104d4ed6b4fbdd973368cd4188c321917ad7322ed35ef945bcbe2de00ecc84d`` / 3004 行，AST 总数保持 71，
   与 85 -> 87 计数无关。
2. 新 target §8.6 L2298–2300 已改为：gate "继续检查当前 ``tests/integration/investment/test_postgres_sources.py``
   全部module/class scope sync/async函数；production ``dayu/investment/storage/postgres_sources.py``的AST总数保持71，
   与该85 -> 87计数无关"。
3. 新 target §17.1 L3607–3608 与 master L320–321 同句修正。
4. 本轮 AST 实测（只读静态解析，未运行测试）：WIP 集成测试文件函数总数 87（module/class scope top-level 60；
   nested = 总数 − module-body top-level = 27）；HEAD 版 85（top-level 58，nested 27）；生产
   ``postgres_sources.py`` WIP 与 HEAD 均为 71。85/87、58 -> 60、nested 27 全部且只属于
   ``tests/integration/investment/test_postgres_sources.py``；生产 AST 71 不参与该 owner-contract 计数。
5. gate 真源 ``_POSTGRES_SOURCE_OWNER_PATH`` 指向集成测试文件这一事实由 Round 1 实测（L77）；该文件本轮不在
   git dirty set，字节未变，结论延续有效。

## 4. 窄幅修正全量复审

1. **exact13 结构**：target §8.6 L2281–2293 精确为 production 4（0006 migration、platform_jobs、postgres_jobs、
   postgres_sources）+ tests 7（含新增的 ``tests/investment/test_architecture_boundaries.py``）+ docs 2
   （tests/README.md、dayu/investment/README.md），与 fix doc L56–82 exact13 manifest 逐 path 相等；
   "除此之外全部zero diff"。
2. **唯一实现 delta**：只允许在既有 ``test_integration_tests_carry_chinese_docstrings`` 内把
   ``_collect_postgres_source_owner_contract_violations(..., expected_function_count=...)`` 由 85 改 87；
   不新增 architecture test 名，不放宽 collector 遍历范围、中文 docstring、``Args``/``Returns``/``Raises``、
   类型或 adversarial owner-contract 规则（target L2295–2302；fix L46–54；master L311–314、L365–367、L4194–4197）。
3. **architecture 文件未动**：``tests/investment/test_architecture_boundaries.py`` 不在 git dirty set，
   仍为冻结 HEAD 字节 ``aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48`` / 3842 行；
   Round 1 实测的 L1208 ``expected_function_count=85`` 与完整 collector/adversarial cases 未变。
4. **仓库状态**：HEAD ``e58e63c785646950dce297e6f50b152f6a0e49a1``（与 fix doc 冻结 HEAD 一致），分支
   ``codex/investment-platform``，index 为空，``git diff --check HEAD`` exit 0；dirty set 恰为 exact13 中 12 个
   已改/未跟踪 WIP path（architecture 文件除外）+ target/master 两份计划 + 四份 docs/reviews artifact，
   无越界 path；root README 与两份 CI workflow zero diff。

## 5. 前提条件复核（全部成立）

1. **12 项 named tests**：target §13.4 L3112–3123 十二名与 fix doc L97–108 逐名相等；文件归属 1/7/2/2
   （L3145–3152）合计 12；L3161–3162 明确"prerequisite仍是12项、overall仍174项"，不新增测试名。
2. **44 coverage keys**：§11.1 matrix 逐行计数为 44 个 production key（L2695–2738），L2771–2772 明确
   "当前mapping为exact 44 keys"；新增第十三 path 是 test path，不改变任何 production key 或 owner tuple。
3. **174 final names**：target §13 L2873–2876 明确 159 + 15 new = 174，两个 rename 不增量；§17.1 L3540–3542
   与 master 一致。
4. **四 PG 进程**：exact13 中受 prerequisite 影响的 PG owner 文件仍精确为
   ``test_platform_migrations_postgres.py``（0005 full-chain head/cycle 更新）、
   ``test_job_request_identity_migration_postgres.py``（0006 dedicated）、``test_postgres_jobs.py``、
   ``test_postgres_sources.py`` 四个（§8.6 L2306–2308、§13.4 归属表）；§14 六个 PG/migration owner ledger 不变。
5. **Item 6 main exact20/51**：§12 L2817–2819 保持 48+3=51、exact20 path，prerequisite 12 项不重复计为
   Item 6 main ownership。
6. **Item 8 defer**：§8.6 L2311–2317、§12 L2801–2803 与 L2819–2820 明确 workflow/九lane final CI 只属
   Item 8，prerequisite 与 Item 6 main incremental gate 不修改 workflow、不物化 workflow static test。
7. **frozen WIP / noPG**：target L3603–3604、master L315–316 与 L4267–4268 明确当前 WIP 逐字节冻结、
   未运行 PG；fix doc 冻结表 13 个 path 与 Round 1 实测 SHA/行数完全相同（WIP 字节在两轮之间未变，
   本轮 dirty set 与之吻合）。

## 6. Stale / 历史区分与隐藏 scope 扫描

- target 中 ``exact12``/十二 仅出现于：L6（历史 Round 4 语义快照）、L2818/L3145（"十二项named tests"，
  指 named tests 数量而非 writable paths，正确）、L3591–3611（历史段/修复前状态描述）。
- master 中 ``exact12``/twelve 出现于 L294、L303、L307、L315、L363、L378、L384、L385、L4139、L4261，
  全部位于历史 Round 3/4 叙事、changelog 历史条目或对修复前冻结状态的描述（如"现有exact12 WIP逐字节冻结"、
  "当时的exact-twelve-path prerequisite"、"Controller当时已接受全部exact12 findings"）；无把 exact12 当作
  当前授权的 stale 语句。
- 当前授权语句全部使用 exact13：target L5、L2281、L3541–3542、L3601–3602；master L311、L364、L4148、
  L4194、L4266。
- 隐藏 scope：git status 无 allowlist 外 path；§8.6 明确"除此之外全部zero diff"，root README、两份 workflow、
  domain/jobs.py、services/jobs.py、protocol/models、accepted 0005 及 Item 6 main exact20 继续 zero diff。
- 本复审过程中未修改任何文件、未运行 pytest/PG、未 stage/commit/push/network。

## 7. Open findings

无。

唯一 Round 1 Low ``S23-I6-DSV4P-REREVIEW-01-L`` 已在 target/master/fix 三份新字节中闭合；唯一 initial High
``S23-I6-PR-01`` 已由 Controller 接受并以 exact13 candidate 修复，本轮验证其修复（exact13 manifest、
唯一 85 -> 87 delta、ledger 不变、无 stale exact12、无隐藏 scope）成立。

## 8. Open questions

无。

## 9. Residual risks and suggested tracking

1. 本 PASS 只是双路复审中的 DeepSeek V4 Pro 一路；按 fix doc L159–169 的唯一后续顺序，须 fresh MiMo Round 2
   独立锁定同一三 SHA 并给出 ``PASS / open H/M/L=0/0/0``，Controller acceptance 后方可创建 exact docs-only
   accepted plan commit；之后才恢复 exact13 WIP，先只完成 architecture 85 -> 87 owner ratchet。
2. 85 -> 87 ratchet 落地后，fresh architecture lane 必须实证 171/171 全绿；若新增函数并非 stable Source PG
   owner 契约，须回 Controller 处置而非继续调整计数。由恢复后的 implementation/review gate 跟踪。

## 10. Final plan review conclusion

``PASS / open H/M/L=0/0/0``。
