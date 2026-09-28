# Slice 3.1 汇总审查 M1 修复记录（待独立复审）

## 范围与裁定

- 仓库 `/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，修复基线 `a1720512f9043318e74a8c4dea1f756a5fd4a29d`。上轮提交为实际进展；本轮独立审查产生新可执行缺陷及新计划候选，不属于仅状态复述。
- 非作者报告 `docs/reviews/code-review-20260928-072218.md` SHA-256 `2b7e054e43a874ffe989082063196888354f72f2ea5641efc8cb16f206277304`：有界 FAIL fresh H/M/L `0/1/0`，完整 aggregate INCOMPLETE。Controller 接受 M1：真实函数把已提交冲突解决的 caller/actor 变化误归存储损坏；修复属于已接受 V9 的 stable-conflict 契约，无新 schema/authority。
- 当前状态 **M1 已修复候选、未独立接受**；完整 aggregate 仍 INCOMPLETE，不能进入 accepted deepreview/PR Gate。原 report 不改、不覆盖。

## 变更

- `_retry_resolution` 以持久 Conflict 的 successor/operation 查询原 Version，先核 transition/witness 和 copy source 自身 predecessor 关系；不以本次 selected_claim_id 查历史而制造假缺失。mode 变化稳定冲突，原 source 缺失/自关系漂移仍存储失败。
- 重算完整 request/actor fingerprint 后将差异返回 `EvidenceConflictError`；相同 fingerprint 下才核 request 与存储投影、完整 Links 的一致性，差异仍为 `EvidenceRepositoryError`。不将整个历史 guard 一律改成业务冲突。
- 原 PG reviewer/copy retry 用例增加同租户真实第二 reviewer+grant；异 actor 与八种 DTO 请求变化必须精确 `evidence_conflict`。前后完整两 Claim Version/Link 和 Conflict JSONB 快照相同；同主体新 token 的原始重试仍返回原对象。合法历史 policy drift 仍精确 `evidence_storage_failure`，不可变版本/链接保持。
- 生产及测试 README 同步这两条错误边界；无 domain、protocol signature、auth、0007、ORM、Fins 或交易更改。未来 3.2 V1 只是独立计划文档，明确排除本修复 target。

## 最终实现身份

| 路径 | SHA-256 | bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/storage/postgres_evidence.py` | `29b4cf415e2d35c9b2974d150c58ac35ab6f978a74e0cc270e8a011053c7873d` | 78917 | 1809 |
| `tests/integration/investment/test_postgres_evidence.py` | `afd42ca37e395ccb919aafdf2ef4ba460c199a5b7a7f4e7ee484d6ca63990f94` | 94669 | 1873 |
| `dayu/investment/README.md` | `cc8b1c279978e3a3c3776f75accbbf265a0367ddab5460515e8579c3c78b077d` | 27149 | 377 |
| `tests/README.md` | `066ebea6ff9f3231d7feff52b487fd82e0bdceff2d078e3e4d4d15833a4f4bd3` | 136019 | 635 |

## 实际验证

- 真实 PG16 定向 `test_repository_review_begin_and_conflict_copy_retry`：**1 passed / 4.35s**。全 `test_postgres_evidence.py` 带分支 coverage：**19 passed / 28.29s**；未改 auth fixture/降 RLS，不连接用户真实库或券商。
- 修复两个 Python 文件，激活 `.venv` 后显式 `pyright --pythonpath .venv/bin/python`：**0 errors / 0 warnings**。首次未激活且未指定解释器的命令报 11 项 missing imports/连带 Optional，属于命令环境失败；正确解释器重跑不是修改代码/ignore/stub 消除。
- Ruff `E4,E7,E9,F,I` PASS；非暂存 `git diff --check` PASS，最终 staged Gate 尚未运行。仓储语句 coverage `534/644=82.9193%`，branch `167/236=70.7627%`，combined `79.6591%`；精确数据由 `workspace/tmp/s31-aggregate-retry-coverage.json` 保存，不能用终端四舍五入的80%当作全部分支已覆盖。

## 残余风险与下一入口

- 新 M1 真实 PG 证明请求分类/认证/历史不变；missing original Version/source 和同 fingerprint 投影损坏仍由静态 guard保护，未对 DB 禁止出现的缺失行实施降约束式破坏测试。不把未执行故障注入写为已通过；交独立复审裁决剩余证据是否充分。
- 原 B direct `review_required→begin` PG成功单列、fixture setup失败注入、nonmaterial resolution/open retry规则仍有原owner；全仓pyright既存错误不由本修复关闭。完整aggregate未覆盖范围由原独立报告明确保留，后续独立审查继续补齐。
- 先完成针对此四文件的非作者复审，再按报告补齐完整 aggregate；接受前不stage/commit此实现。独立审查运行器上轮GPT/DS/local均在配置/模型边界退出，没有执行review，不把它们当PASS。现在已有a1独立lane实际产出上述FAIL；无需读取凭据或修认证配置。
- Slice 3.2 candidate intake V1及十shape/V8/H2、S5/整体业务闭环均未完成；本修复不授予这些边界的接受。
