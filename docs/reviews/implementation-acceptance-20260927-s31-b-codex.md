# S31-B Controller 限定验收：严格证据 PostgreSQL 仓储

## 裁定与范围

- 仓库 `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，验收前 HEAD `c639cf8c23eea98c37c3da66fcfc642fd00919c2`。原 Slice 3.1 V9 计划 SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`；已接受的 S31-B 澄清 V2 SHA-256 `61785cdcc9a2642e6083322094eed68ceafb3f213a4f112dc7048a51bf0c6f91`，已在本 HEAD 中。0007 与 S31-Auth 没有因本片更改。
- 原六文件独立代码审查 `docs/reviews/code-review-20260927-232544.md` SHA-256 `585960fb6331adf73f9a8d7d44f312de02baf50c5cc9d61dc703fc1ef182461b` 为 FAIL，fresh H/M/L `0/2/0`：Fact series 跨公司列表混链、真 PG 状态及历史 copy 补证缺失。澄清 V2 独立 plan review `docs/reviews/plan-review-20260927-233855.md` SHA-256 `38e9432a263b3ad95c17d87bb8a3a8107d2db2b312315047cb2cc6931f478847` 为 PASS `0/0/0`。
- 修复后的六文件非作者代码复审 `docs/reviews/code-review-20260927-235250.md` SHA-256 `54f2e22b49fdf3b3fbd8ac1dd99d872bc50f87c6de72c45d5b25f59e62621a48` 为 bounded PASS，**fresh open H/M/L `0/0/0`**。M1/M2 按 V2 精确补证关闭；此 PASS 不向未测路径传递。
- **Controller 限定接受 S31-B 本地切片**：十三个证据仓储入口、单事务版本与认证边界、公司定界 Fact revision 列表、候选 proposed 持久化及局部 Claim 资格。可按下述最终身份暂存并提交；接受不包含 S3.2 Fins 实时 owner/readback/freshness、最终 forecast/decision readiness、V8/H2 十形状物理闭包、S5/D0/Gate 或交易。

## 最终六文件身份

以下均为验收时最终磁盘内容，末尾 LF、零 CR；非作者复审逐文件 O_NOFOLLOW 读至物理 EOF 核 SHA。

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/storage/evidence_protocols.py` | `0a0434dd6622f70c2d3c2af6ec350330a4bcea04d15f1b44c57d5ea22a1fbfda` | 12418 | 381 |
| `dayu/investment/storage/postgres_evidence.py` | `9bc05db495d67c92ea0fc71c82d408dd6c98e35c2fe77ef715f9d985dd301698` | 78519 | 1803 |
| `tests/investment/test_evidence_storage_contract.py` | `21c41c182fee37ee00e94d112359cefba244c8e5f0f6089e868ff6f12fae527e` | 11689 | 293 |
| `tests/integration/investment/test_postgres_evidence.py` | `8653a974b39aa5d26ac387c5f70861cc3735e9d94245d35b0e141dddd094528f` | 90545 | 1793 |
| `dayu/investment/README.md` | `5dea00177d474d092cd0d94ef228a88dcaff78232f95ad1c89191de26e0f604f` | 26711 | 372 |
| `tests/README.md` | `1d22e9800ec6922e2ff6e442ad650323c39476db66cd9ef50f83486e2658ff22` | 135859 | 635 |

## 验证证据及限制

- 作者同身份联跑 app-role PG16 auth→evidence→migration 三文件：**77 passed / 62.93 s**；新增 C01/C02 的三个 PG 用例作者定向 **3 passed**。非作者独立重跑这三个 PG 用例 **3 passed / 4.64 s**，另独立协议与架构 **177 passed / 1.88 s**。Controller 独立重跑受影响协议、领域、架构、auth unit 与迁移静态测试共 **264 passed**（220+44），四个 Python 路径定向 pyright **0 errors / 0 warnings**、Ruff `E4,E7,E9,F,I` PASS。未把全仓 pyright 既存 84 项当成本片错误归零。
- 作者单独运行 repository PG 的 **19 tests passed / 28.44 s**；仓储文件语句覆盖 `530/640=82.8125%`，满足 AGENTS.md 的单文件 ≥80% 语句目标；含分支综合值 `79.4725%`，仍是独立残余风险。一次带 coverage 的三文件 PG 联跑为 **76 passed / 1 failed**，唯一失败是未改的 auth 测试 `test_postgres_evidence_auth.py:588` 比较 PostgreSQL `statement_timestamp()` 与宿主 `datetime.now()`，差 5.565 ms；同身份无 coverage 联跑重跑 77/77。不能抹去首次时间断言失败，也不能把它当成 S31-B 仓储失败。
- C01：同 tenant 两公司交错写同 series 的各自 rev1/rev2，再以 tenant+company+series 查询，分别返回本链；不存在/跨租户为空，跨公司 prior 拒绝。C02：append copy 在 head 前进后同 operation 返回原不可变版与完整 links、零新行；异 operation/payload/mode 拒绝；reviewer 的 invalidated/superseded 与 bearer 重开、ordinary append 状态门由真 PG 和失败前后完整 Version/Link JSONB 快照证明。新的 README 与当前签名/测试职责同步。
- 历史协议局部审查 `docs/reviews/code-review-20260927-223804.md` SHA-256 `ca2e8fc6619c4075a2e91a9d7f40a723e6eba76d99557630e64c19d2b3e304ff` 的 README L，已由 `docs/reviews/code-review-20260927-224031.md` SHA-256 `48b12ffd522d9b7710ada9e2f8d41fc8eddac45fcfb9fce45c0c2d7f9adcf641` 有界复审关闭；这两份记录保留，不代替本次六文件审查。

## 后续边界与提交门

- `review_required→begin_claim_revision` 的直接成功真 PG 例仍未单列；现有 domain validator 与共享仓储分支可读，但不冒充该入口的 PG 执行证明。fixture setup 失败注入未运行；nonmaterial conflict resolution 与 resolved conflict 的 open-operation retry 投影仍待单独规则。上述残余不被本片写成已验证。
- 接受后仅暂存上表六路径、本报告及三份 S31-B 代码审查记录 `223804`、`224031`、`235250`。核实际 index 路径与冻结 SHA、运行非空 index 的 `git diff --cached --check` 并审 staged diff；任一路径/字节漂移先停止、重新审查。通过后提交本片，随后才进入 S3.2 计划澄清。原 FAIL 与后续 PASS 均随提交保存。
