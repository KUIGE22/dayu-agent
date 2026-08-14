# Slice 2.3 Item 6 prerequisite architecture-owner 计划独立复审（DeepSeek V4 Pro）

- 日期：2026-08-14
- 角色：fresh independent DeepSeek V4 Pro plan re-reviewer（只读复审，不实现、不修复、不运行 test/PG、不 stage/commit/push/PR/network）
- Model / route：model ``deepseek-v4-pro[1m]``；route 为本机 Claude Code CLI 会话（用户直接 dispatch 的内联复审指令），无外部 API/网络调用。
  未读取、未采信任何 MiMo output；worktree 中未跟踪的 ``docs/reviews/plan-rereview-20260814-slice-2.3-item6-prerequisite-architecture-owner-mimo.md`` 未打开。
- Gate：Gateflow Item 6 prerequisite architecture-owner corrective plan（exact12 -> exact13）复审。

## 1. Reviewed frozen identity（SHA/行数均实测核对，与 dispatch 指令给定值逐一相等）

| File | SHA-256 | Lines |
|---|---|---:|
| ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``（target） | ``db4d4d3c1eb47f41358eeb007c5a62ca5bdcb14988046ed903913aca64337b79`` | 3607 |
| ``docs/plans/2026-08-10-investment-platform-restoration.md``（master） | ``6b50135eec9c49379b605c7b7a971a3069e1166352f1ed879552912c70c61d7c`` | 4554 |
| ``docs/reviews/plan-fix-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md``（fix） | ``e07fc4c894bb962a5ed5ce99ef6fc1a91f6bc5b642f3dc7c689be05fa0d6290f`` | 156 |
| ``docs/reviews/plan-review-20260814-080306.md``（immutable finding） | ``b588832ef852dea72652b93cef4a4bc0dbafec6a8504bce80d24527c100a7e06`` | 55 |

Immutable finding 结论 ``FAIL / open H/M/L=1/0/0``，唯一 High ``S23-I6-PR-01``；本复审不改写其结论，也不引用历史
Round 4 ``PASS / open H/M/L=0/0/0`` 作为 closure evidence。

## 2. 已核实的闭合点

1. **exact13 结构**：target §8.6（L2281–2293）精确为 production 4 + tests 7 + docs 2，唯一新增 path 为
   ``tests/investment/test_architecture_boundaries.py``；与 fix doc 的 exact13 manifest 逐 path 相等。
2. **唯一实现 delta**：只允许在既有 ``test_integration_tests_carry_chinese_docstrings`` 内把
   ``_collect_postgres_source_owner_contract_violations(..., expected_function_count=...)`` 由 85 改 87；不新增
   architecture test 名，不放宽任何检查。实测 ``tests/investment/test_architecture_boundaries.py``
   （SHA ``aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48`` / 3842 行，worktree 未修改）：
   L1208 仍硬编码 ``expected_function_count=85``；collector（L803–913）仍完整保留函数总数断言、中文 docstring、
   ``Args:``/``Returns:``/``Yields:``/``Raises:`` 独立标题、签名占位模板禁令、参数/返回注解与字符串注解检查、
   direct-assert/SQLAlchemyError 契约及全部 adversarial cases（L1273–1329），无一被削弱。
3. **矛盾闭合**：实测 gate 真源 ``_POSTGRES_SOURCE_OWNER_PATH = _INTEGRATION_TESTS_SRC / "test_postgres_sources.py"``
   （L77）。AST 实测：HEAD 版该测试文件 85 个函数（top 58 / nested 27），冻结 WIP 版 87 个（top 60 / nested 27，
   即新增两个 top-level provenance tests），与 immutable finding 的 85 vs 87 漂移及 fresh lane 170/171 观察一致。
   因此 85 -> 87 ratchet 是真实、必要且充分的；``tests/integration/investment/test_postgres_sources.py`` 的 WIP
   SHA ``26092014cfa0e64afc4a7e30256e636260f78d557cf2c5937b317c731cbe5ad6`` / 4519 行与 fix doc 冻结表一致。
4. **12 项 prerequisite named tests**：fix doc 所列 12 名与 target §13.4（L3110–3121）逐名相等，文件归属
   1/7/2/2（L3143–3150）合计 12，不新增测试名。
5. **44 coverage keys**：target §11.1 matrix 逐行计数为 44 个 production key；新增第十三 path 是 test path，
   不改变任何 production key 或 owner tuple。
6. **174 final names**：target §13 明确 159 + 15 new、两个 rename 不增量 = 174；§13.3 53 项子集不变。
7. **四 PG 进程**：exact13 tests 中受 prerequisite 影响的 PG owner 文件仍精确为
   ``test_platform_migrations_postgres.py``（0005 full-chain head/cycle 更新）、
   ``test_job_request_identity_migration_postgres.py``（0006 dedicated）、``test_postgres_jobs.py``、
   ``test_postgres_sources.py`` 四个；§14 六个 PG/migration owner ledger 不变。
8. **Item 6 main exact20/51 与 Item 8 defer**：target §12（L2815–2817）与 §17.1 保持 48+3=51、exact20 path；
   Item 8 workflow/docs 仍 defer（§8.6 L2313–2316、§12 step 8）。root README 与两份 CI workflow 保持 zero diff。
9. **WIP 逐字节冻结**：fix doc 冻结表中全部 13 个文件 SHA/行数实测一致；
   ``tests/investment/test_architecture_boundaries.py`` 未进入 dirty set，符合"plan gate 完成后才按 85 -> 87 恢复"。
10. **repo 状态**：HEAD ``e58e63c785646950dce297e6f50b152f6a0e49a1``（与 fix doc 冻结 HEAD 一致），分支
    ``codex/investment-platform``，index 为空；dirty set 恰为 exact13 WIP（production 4 + tests 6 已改/未跟踪、
    architecture 未改）+ docs 2 + target/master/fix 三份 docs-only artifact + immutable review doc，无越界 path。
11. **stale exact12 扫描**：target 与 master 中所有 exact12/twelve 表述均位于标注 historical 的条目
    （master L294、L303、L373、L379–380、L4134、L4255；target L6、L17.1 历史段）；当前条目全部使用 exact13
    （target L4–5、§8.6、§17.1；master L304–317、L355–365、L4139–4144、L4188–4191、L4257–4268），
    未发现把 exact12 当作当前授权的 stale 语句，也未发现隐藏 scope 扩张。

## 3. Open findings

### S23-I6-DSV4P-REREVIEW-01-L-已复现-低-85→87 计数证据链文件归属误标

- **位置**：fix doc L34–38（Accepted evidence and correction）；target §8.6 L2295–2300。
- **问题类型**：证据链准确性。
- **状态**：open（docs-only 措辞问题，不改变任何 operative scope 或实现 delta）。
- **事实**：fix doc 写"HEAD 版 ``dayu/investment/storage/postgres_sources.py`` 的 owner-contract 函数总数为 85；
  当前冻结 WIP 的同文件……AST 总数为 87（top-level 58 -> 60，nested 27 不变）"。AST 实测：生产文件
  ``dayu/investment/storage/postgres_sources.py`` HEAD 与 WIP 均为 71 个函数（top 59 / nested 12），不存在
  58 -> 60；85/87 与 58 -> 60、nested 27 全部属于 ``tests/integration/investment/test_postgres_sources.py``
  （HEAD 85/58/27 -> WIP 87/60/27）。target §8.6 相应句子称 gate"继续检查当前 postgres_sources.py 全部
  module/class scope sync/async 函数"，而 gate 实际扫描的是 ``_POSTGRES_SOURCE_OWNER_PATH`` 指向的
  ``tests/integration/investment/test_postgres_sources.py``。
- **为什么是 Low**：允许的唯一 delta（architecture 文件 85 -> 87）与 allowlist 均不依赖该句文件名；
  误标方向偏保守（声称生产文件多出 2 个函数，而非掩盖真实变更），且可直接由代码事实证伪；
  无法导致错误实现或错误 PASS，只会让按字面审计者发现矛盾后 STOP（fail-safe）。
- **建议改法**：fix doc L34–38 与 target §8.6 改为明确 85/87、58 -> 60、nested 27 属于
  ``tests/integration/investment/test_postgres_sources.py``（gate 的被扫描主体）；生产
  ``postgres_sources.py`` 冻结 WIP 的 AST 总数 71 不参与该 owner-contract 计数。纯文档修正，不触及 WIP、
  不运行 test/PG。

## 4. Verdict

``FAIL / open H/M/L = 0/0/1``。

唯一 open 项为上述 Low 证据链文件归属误标；不存在其它 open、deferred 或未分类 finding。
按 fix doc 自定规则（任一 fresh review 仍有 open finding 即 STOP），当前不得恢复 WIP、运行 PG 或引用历史
Round 4 PASS 越过本 gate；建议 Controller 接受该 Low 并作 docs-only 措辞修正后重新冻结三份 SHA 并发起
fresh same-SHA 双路复审。
