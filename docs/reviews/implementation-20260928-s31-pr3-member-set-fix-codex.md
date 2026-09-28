# S31 PR3 M1 UUID 集合修复与真实 PG 回归

状态：`FIX_IMPLEMENTED / AUTHOR_VALIDATED / INDEPENDENT_PR_REREVIEW_REQUIRED`。本机时间 2026-09-28T08:10:26.716448+08:00；cwd `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，HEAD `b18a5e2c6275f62457182084b85d4aac17389c1e`，base `7ae26fd1a343547600e4fdd7478a510780c14450`。未 stage/commit/push，PR3仍为旧head；总目标active/shadow-only。

## 发现裁决与最小实施

Controller接受独立报告 PR3-M1（报告 SHA40600eb57896142e983268cd3ef17b83efe0e65f0da290f59ac4ac1909cd66c1，fresh H/M/L0/1/0）。合法公司无关冲突路径在 Claim FOR UPDATE期间对 UUID list执行2*C次V线性扫描，静态Θ(C*V)成立。现在仅将同 tenant/company/claim 的全部历史版本UUID读取结果构造成set；两侧member判定的期望成本为O(V+C)。不宣称数据库查询O(1)、实测吞吐或锁延迟。SQL、RLS、0007、事务、expiry→material conflict→状态→supports优先级和公共协议原字节未改；仍读全部目标历史和公司open material冲突，规模验证归后续repository性能owner。

新增两项参数化真实PG行为回归：目标head前进至V5后，规范排序左右两侧的V1端点均阻断；同公司其它Claim的material和目标的nonmaterial冲突不阻断；material优先于peer的draft状态，局部读取不改完整head/Version/Link持久JSONB。既有resolved→review_required用例补not_approved断言，证明resolved不继续阻断。README仅同步当前集合匹配机制/测试边界。

## 首次失败及修复

首次新测试 SHA24fbfd3d594800eb46dab700e2953b72c4fc67e0d835e8f79be164f9cbdc2360（100971B/1973LF），生产源已是下表dcc20a身份。第一次21项 **19 passed / 2 failed /33.06s**：作者在创建历史版本时使用同内容、同evidence的draft空修订，被既存validate_append_transition正确拒绝。只改新测试statement为逐次真实内容修订；没有降低状态约束、改变production修复或把失败归基线。初次完整stdout/stderr和coverage以独立initial文件原字节保留；不得把initial计作全部PASS。最终测试为下表新身份。

## 实际验证与证据复用限度

最终单文件真实PG16：**21 passed /34.92s**，所有原19项和新增2项；fixture独占随机container/network/database/user并正常teardown，不操作既有PG17。命令为 `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120 --cov=dayu.investment.storage.postgres_evidence --cov-branch --cov-report=term --cov-report=json:workspace/tmp/s31-pr3-set-fix-final-coverage-20260928.json`。环境DEVELOPER_DIR=/Library/Developer/CommandLineTools，fallbackGit PATH首位，PYTHONDONTWRITEBYTECODE=1。最终statement **534/645=82.7906976744%**；branch 168/238，combined (534+168)/(645+238)，partial 68、missing branch 70；CLI rounded80%不代表branch/combined>=80%。机器JSON单独绑定新生产source，未覆盖旧4693957的77lane JSON。

修测试后新2Python路径定向pyright0errors/0warnings、Ruff E4/E7/E9/F/I PASS；git diff --check PASS（非staged gate）。此前独立264unit/architecture、77auth+repository+migration和16types结果仍为原5d66/b18a历史身份证据；本报告不将其改称新源码重跑或把21+77相加。其它14Python输入与b18a原字节相等，auth/DDL/0007/schema无新变更。全仓84基线类型错误/3I001仍由repository-quality owner后续处理，未加ignore或降低检查。GitHub PR3该旧head CIstatuses/checks/workflows为空，未声称CI PASS。

## 下一 gate 与残余分类

M1作者修复完成，关闭需独立PR复审及Controller接受，随后精确stage、非空cached diffcheck、accepted PR review commit/final push/真实远程核验。未把此报告当PR PASS或draft-PR-pass。未测性能SLA且仍线性加载→后续仓储规模验证；remote main-onlyCI/stackedmain未集成→platform delivery；full branch coverage/fixture异常注入→evidence test owner；direct-edge正式回归→同owner；Fins/S32/promotion/PIT最终readiness→原S32后续work unit；全十shape/30arm positive/bad-child/legal history、V8/H2/H1/V17/S5/D0→独立递归规则track。所有规则/冻结来源保持原字节。

## 终盘冻结输入与完整输出身份

O_NOFOLLOW regular single-link，读前后fstat稳定，真实EOF。index仍为空。精确4实施路径和5证据：

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| dayu/investment/storage/postgres_evidence.py | dcc20a632aced7c88b21f97bf003955fcdd2a6b54bb9f4cc9b47367b08e26d8d | 78915 | 1809 |
| tests/integration/investment/test_postgres_evidence.py | 95330269532323a9b7892b75be23177a15e5fdc2027464b3362bd65279171a4a | 101033 | 1974 |
| dayu/investment/README.md | 06e8b7182413f297bc9d6715f630777a2ab6b83ad9fd0477317f124aef63fd3c | 27647 | 382 |
| tests/README.md | 3ce84a03c880e898d82979262ee286c44293ead754bba19fb2e2d6b7aac9b21c | 136512 | 636 |
| docs/reviews/pr-3-review-20260928-080551.md | 40600eb57896142e983268cd3ef17b83efe0e65f0da290f59ac4ac1909cd66c1 | 26015 | 153 |
| docs/reviews/evidence/s31-pr3-set-fix-pg-initial-20260928.txt | fdf39afa5e2fb40fab0668ef680710bd764ca51375e368c9aec71786b3b362a3 | 8126 | 80 |
| docs/reviews/evidence/s31-pr3-set-fix-coverage-initial-20260928.json | be4ab2940fbdef0f44c97db8ab1c2f8aff17555c9782ff27dc40efc29ab441d2 | 50549 | 0 |
| docs/reviews/evidence/s31-pr3-set-fix-pg-final-20260928.txt | e20560f9dfc6ea4bfbc6aec1ad91f75eb7a52edfcd434486f2d023ac502d2d8b | 1478 | 24 |
| docs/reviews/evidence/s31-pr3-set-fix-coverage-final-20260928.json | 4d89d0288dc9be6fd5d345fe83a3657b8dd9391fa1d3696ef856501ef079e778 | 50549 | 0 |
