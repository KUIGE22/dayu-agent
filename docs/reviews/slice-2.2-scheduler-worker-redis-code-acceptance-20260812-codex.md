# Slice 2.2 Scheduler / Worker / Redis — code acceptance

- 日期：2026-08-12
- 分支：`codex/investment-platform`
- Implementation baseline：`37cac2f`
- Accepted plan HEAD：`82cc7d4c5c369f776e12a8dd5a44d6557445ee33`
- 状态：**ACCEPTED / READY FOR LOCAL IMPLEMENTATION COMMIT**

## Accepted outcome

Slice 2.2交付generic durable scheduler/worker runtime：PostgreSQL继续是job、schedule、lease、receipt、cursor与Agent correlation唯一真源；Redis只提供可丢wake-up hint，所有执行仍经PostgreSQL claim/fence。当前没有source/research/Agent/Broker业务handler，没有live行情、模型、provider、Broker或交易调用。

## Review closure

- DeepSeek首轮：`docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-deepseek.md`，`FAIL / open H/M/L = 0/1/0`。
- MiMo首轮：`docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-mimo.md`，`PASS / open H/M/L = 0/0/0`。
- Controller裁决：`docs/reviews/slice-2.2-scheduler-worker-redis-code-review-adjudication-20260812-codex.md`；S22-CR-001与S22-CR-002 accepted，其余observations rejected或deferred。
- Codex internal fix：`docs/reviews/slice-2.2-scheduler-worker-redis-corrective-review-fix-20260812-codex.md`。
- DeepSeek corrective：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-deepseek.md`，`PASS / open H/M/L = 0/0/0`。
- MiMo corrective：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-mimo.md`，`PASS / open H/M/L = 0/0/0`。

冻结corrective SHA-256：

- `dayu/host/worker.py`：`a478ea195676ebd9746e1059bd64c5d02129d6cee78f990f6079598981633d9b`；
- `tests/application/test_platform_worker.py`：`9550543f213c383ea4ac73f805727c4cff593dac169db0b0ce6569359cda21cc`。

## Final gates

- clean non-integration：`8493 passed, 5 skipped, 209 deselected in 199.96s`；
- corrective focused：`45 passed`；related suite：`399 passed`；
- Worker coverage：`614 statements / 87 missing / 86%`；
- exact Pyright：`0 errors, 0 warnings, 0 informations`；
- Ruff default/F/I：PASS；
- full-rule ratchet：baseline `2352`，current `2351`，positive delta `{}`；
- accepted implementation allowlist：实际`51/55`，outside`0`，未变为四个platform leaf locks；
- `git diff --check`：PASS；150/150 exact named tests存在；
- PostgreSQL真实lanes：migration`40`、identity`16`、schedules`32`、jobs clean`84`；
- Redis 8.4 + PostgreSQL真实full file：`3 passed`，owned container/network残留`0/0`；
- clean resolver五lane、fresh wheel/archive与sanitized no-index offline smoke：PASS。

Coverage工具的pytrace/API替代尝试曾触发tracer/pandas-numpy环境问题；标准Coverage C tracer稳定给出Worker 86%，普通测试与全仓clean suite不受影响。一次只读validator误设Pyright latest可能更新用户级缓存，随后使用仓库既有`.venv` Pyright 1.1.408复跑为0/0/0；repo关键文件identity与status未变化。

## Scope and authority

- Implementation allowlist外路径：0；staging前index为空。
- 全部production/test写入由Codex内部模型完成；DeepSeek与MiMo只独立审核。
- 本acceptance只授权Controller创建本地accepted implementation commit。
- 未授权push、PR、merge、部署、live行情、模型/provider/Broker或交易动作；下一Slice不得在本commit前启动。
