# Slice 2.3 Item 8 explicit CI/runbook — code-review fix

## 1. Gate 与冻结输入

- Gate：Gateflow code review -> fix；本 writer 不执行 re-review、不推进 gate、不 commit。
- Repository / branch / HEAD：/Users/wsk/workspace/dayu-agent；codex/investment-platform；464aa00e590b23defa4eecc8d853bacd3f376904。
- Pre-fix candidate diff SHA-256：1e66741267c211aa4ac6191bab77ac666b6f253fbc2017528422b5eb5871890b。
- DeepSeek review：docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-deepseek-v4-pro.md = c6258205d51280298a936f61082925035844efa16aa2c93137099450dfb51c78 / 97 / 12425；verdict FAIL 0/1/1。
- MiMo review：docs/reviews/code-review-20260822-slice-2.3-item8-ci-runbook-mimo.md = a7e1e7720f27e9baa0566ea46bf67867ce5ea1b2ef972af3cafe53adeb5b9492 / 58 / 2477；verdict PASS 0/0/0。
- Controller adjudication：接受 DeepSeek M1 与 L1；MiMo 无 finding，不产生额外修复。
- Implementation artifact：docs/reviews/implementation-20260822-slice-2.3-item8-ci-runbook-codex.md = a6e589c60863182cf20066c3bde4a2041a6e9df5339c6b306e116dea79ea024d / 139 / 11327。
- Writable implementation scope：tests/README.md 与 tests/investment/test_platform_migrations.py exact two；另创建本 fix artifact。两份 workflow、reviewer artifacts、implementation artifact、master plan与 prerequisite均只读。

## 2. START exact-four

| Path | START SHA-256 / lines / bytes |
|---|---|
| .github/workflows/ci-mainline.yml | 697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974 |
| .github/workflows/ci-pr-extended.yml | 0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199 |
| tests/README.md | 798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004 |
| tests/investment/test_platform_migrations.py | 8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940 |

## 3. Accepted finding fixes

### M1 — fixed, awaiting same-reviewer re-review

- 将 tests/README.md 中 0006 prerequisite-era 运行方式收敛为当前 Item8 final runnable runbook。
- 保留一句历史边界：旧 prerequisite 增量账本仍由其 accepted artifact 保存；当前运行入口以 Item8 final ledger 为准。
- 逐字列出两份 workflow 使用的 exact-three pinned pull strings：PG16、Redis 8.4、MinIO。
- 逐字、同序列出九个独立 pytest integration commands，包含真实 investment 路径下的 source-sync job、MinIO 与 Redis。
- 增加 remaining integration aggregate及同序九个 --ignore。
- 删除 prerequisite-era 的 future Item8、workflow zero diff与two-digest正向陈述；继续禁止合并、-k/skip/fake或掩盖退出码。
- Item7 exact-four production mapping、exact-one Source Sync handler与共享 session factory文字未改。

### L1 — fixed, awaiting same-reviewer re-review

- tests/README.md 对 tests/investment/test_platform_migrations.py 的职责描述新增 Item8 workflow audit：exact-three pulls、nine lanes / nine ignores、non-lane manifest。
- 测试模块 docstring新增相同职责；测试逻辑、常量、helper与named audit函数均未重构。

## 4. Validation

所有Python命令均先使用项目 .venv；没有PG、Docker、network、pull或Git mutation。

| Gate | Exact command / evidence | Result |
|---|---|---|
| Focused named static | PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/investment/test_platform_migrations.py::test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate -q | exit 0；1 passed in 0.36s |
| Affected owner file | PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/investment/test_platform_migrations.py -q | exit 0；44 passed in 0.73s |
| AST/docstring/runbook oracle | direct UTF-8 parse + ast.parse | 3 pulls、9 commands、9 ignores、stale 0、module职责闭合、named static exact-one |
| Pyright | .venv/bin/pyright tests/investment/test_platform_migrations.py | exit 0；0 errors, 0 warnings, 0 informations |
| Ruff default/F/I | 三次 .venv/bin/ruff check，含 --select F 与 --select I | 全部 exit 0 |
| README/workflow consistency | direct literal/order comparison | README三pull/九lane/九ignore与 frozen workflow truth一致 |
| Diff/allowlist | git diff --check + changed-path readback | exact-four tracked WIP；本 fix只改变授权exact-two；index 0 |
| Encoding | direct bytes | exact-four与三existing artifacts均UTF-8、final LF=true、CR=0、NUL=0 |

## 5. END freeze

| Path | END SHA-256 / lines / bytes | Fix status |
|---|---|---|
| .github/workflows/ci-mainline.yml | 697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974 | unchanged |
| .github/workflows/ci-pr-extended.yml | 0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199 | unchanged |
| tests/README.md | 8153c52858141f355808a2d1ff1c0dac5701c59b498ab9953cae8048119e9fa0 / 622 / 133971 | M1 + L1 |
| tests/investment/test_platform_migrations.py | 18152a63b77b2192298525ed211e39cf5a0061d4031960bc8601143ec56ad899 / 3180 / 110116 | L1 module docstring only |

- Post-fix candidate diff SHA-256：fe95120798aa9d545014d6212879a3f9721aefc14d745661e494c38155294091。
- DeepSeek review identity保持 c6258205d51280298a936f61082925035844efa16aa2c93137099450dfb51c78 / 97 / 12425。
- MiMo review identity保持 a7e1e7720f27e9baa0566ea46bf67867ce5ea1b2ef972af3cafe53adeb5b9492 / 58 / 2477。
- Implementation artifact identity保持 a6e589c60863182cf20066c3bde4a2041a6e9df5339c6b306e116dea79ea024d / 139 / 11327。

## 6. Residual risk 与停止状态

- 本 fix只修复Controller接受的M1/L1；workflow行为没有变化，因此未重复integration/PG/Docker门禁。
- Independent same-reviewer re-review尚未执行；finding最终 CLOSED/PASS 由reviewer和Controller裁决，不由fix writer自评。
- Index保持空；未stage、commit、push、PR，也未进入re-review。
- Status：READY FOR SAME-REVIEWER RE-REVIEW。
