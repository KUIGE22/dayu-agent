# Slice 2.2 持久调度、Worker 与 Redis wake-up — implementation artifact

- 日期：2026-08-12
- Gate：Phaseflow / Gateflow implementation
- 分支：`codex/investment-platform`
- Implementation baseline：`37cac2f`
- Target plan：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- 编写模型：Codex 内部模型
- 独立最终审核：DeepSeek + MiMo（corrective re-review 双 PASS）
- 状态：**DUAL CORRECTIVE RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**

## Outcome

本 Slice 已完成 generic durable scheduler/worker runtime：PostgreSQL 是 job、schedule、lease、receipt、cursor 与 correlation 的唯一真源；Redis 只提供可丢失的 wake-up hint，任何消费仍回到 PostgreSQL claim/fence。实现包含：

1. PostgreSQL durable schedule schema、RLS、九方法 Store、PG-clock activation、DST/misfire/cursor、crash replay 与原子 materialization。
2. JobService / ScheduleService 的窄 typed gateway、execution registry、Host cancellation/governance 与 committed replay。
3. Worker、Scheduler、ProcessIntakeGate、soft drain、second-signal hard stop、heartbeat/cancel/recovery。
4. Redis RESP2 bytes-only adapter、严格 URL/codec、event-assisted 与 polling-degraded 状态机。
5. `dayu-cli platform worker|scheduler`、production Redis-first admission、integration PostgreSQL-only composition、CI 与五份 README。

本 Slice **没有**注册 source/research/Agent/Broker 业务 handler，不调用行情、模型、provider、Broker 或交易接口，也不交付生产 Compose/live trading。

## Scope audit

- Accepted implementation allowlist：55 paths。
- 实际 implementation delta：51 paths。
- Allowlist 外 implementation delta：0。
- 允许但保持不变：4 个 platform leaf lock；它们继续 include 更新后的 common lock。
- Plan 要求的 exact named tests：150 / 150 存在；缺失 0。
- 新 production Redis import owner：仅 `dayu/host/redis_wakeup.py`。
- Source/research/Broker production handler registration：0。
- Conflict marker / 临时产物路径：0 / 0。
- Secret-shape 命中仅为两份测试中的 dummy fixtures；用户提供的 key 前缀未进入 workspace。

## Validation evidence

### Behavior

| Gate | Result |
|---|---|
| Final clean non-integration suite（corrective 后） | `8493 passed, 5 skipped, 209 deselected in 199.96s`；以 `env -u SERPER_API_KEY` 排除本机继承的 live Serper key |
| PostgreSQL migrations lane | `40 passed` |
| PostgreSQL identity lane | `16 passed` |
| PostgreSQL schedules lane | `32 passed` |
| PostgreSQL jobs clean lane | `84 passed` |
| Final jobs rerun after constructor tightening | `83 passed`，1 个 fixture 在 `CREATE DATABASE` 前置阶段发生 `OperationalError`；该唯一节点立即单独重跑 `1 passed`，未出现 production assertion failure |
| Redis 8.4 + PostgreSQL integration lane（首次历史运行） | **FAIL**：`3 failed in 13.27s`，pytest process exit `1`，外部门禁命令 wall time `15.31s`；失败已由 RDX-001/RDX-002 裁决并修复 |
| Redis focused unit（修复后） | `32 passed in 2.04s` |
| Redis 8.4 + PostgreSQL full file（修复后） | `3 passed in 12.10s`，pytest process exit `0` |
| Redis owned Docker cleanup（修复后） | residual container `0`；residual network `0` |

### Static and coverage

| Gate | Result |
|---|---|
| Exact Pyright over all changed Python files | `0 errors, 0 warnings, 0 informations` |
| Ruff default and `F,I` over all changed Python files | PASS |
| `git diff --check` | PASS |
| Full-rule positive-delta ratchet | baseline `2352`，current `2351`，positive delta `{}` |
| Config / jobs domain / storage protocols | `99% / 88% / 100%` |
| Migration 0004 / PostgreSQL jobs / schedules | `>=95% / 82% / 80.8%` |
| Schedule domain / ScheduleService / JobService | `88% / 88% / 85%` |
| Process intake / Worker / Scheduler / Redis adapter / startup | `100% / 84% / 87% / 91% / 81%` |
| Changed CLI modules | `90%–100%` |

Final code review corrective 后，Worker owner file 为 `45 passed`，Worker production coverage 更新为 `86%`（`614` statements / `87` missing）。标准 Coverage C tracer 路径稳定通过；一次显式 `COVERAGE_CORE=pytrace` 运行触发 coverage.py 自身 tracer stack error，另一次 Coverage API 重载造成定时型测试超时，均未作为行为通过证据，未修改 production 绕过。

本机 pytest-cov 注入偶发触发 NumPy/Pandas import instrumentation 问题；相关模块使用 fresh `COVERAGE_CORE=pytrace` / Coverage API 复证，普通 focused 与 clean suite 均通过，未通过修改 production 绕过。

## Dependency and deployment truth

- Runtime declarations：`redis>=8.1.0,<8.2.0`、`croniter>=6.2.4,<6.3.0`。
- Min/common locks：Redis `8.1.0`、croniter `6.2.4`，并包含 Python `<3.11.3` 所需 `async-timeout==5.0.1`。
- 五条 clean resolver lane 全部通过：Python 3.11 minimum macOS arm64 `196` packages；current Linux x64 `203`、macOS arm64 `195`、macOS x64 `195`、Windows x64 `193` packages。每条 lane 对适用 tracked constraints 均为 missing `0`、mismatch `0`。
- 四个 platform leaf locks 通过 common lock 获取上述 pins且无需改字节。被忽略、未跟踪的 `uv.lock` 不是真源，验证前后 SHA-256 保持 `d2f8f5e26314bafd9991f819399ff754a3931e7090a595c29a1e7b1d960d891a`。
- Fresh current project wheel SHA-256 为 `77c5e6abdf1c7f4f623c039e38fa05af06ff414dfd3ffdff0366fc8c5f20c91c`。fresh macOS arm64 offline archive SHA-256 为 `45b3530846c1701f8c1d23aa7a81a2c9c5434823432c9355cce233078d45cae8`，大小 `370733309` bytes，manifest 为 `172` 个 wheel、`0` 个 sdist；archive 根目录 project wheel 与 fresh wheel SHA 精确相同，archive `constraints.txt` SHA-256 为 `5f9e88ee827c3c4cd3f24608acebdd571be8eee96d26ae50400db81e76c709f7`。
- Repo `dayu/host/redis_wakeup.py` 与 fresh project wheel 内同名 member 的 SHA-256 均为 `d8e788282a469fb74ce8d0c952b7a1d65cc6171435794b3f97a7cf64397c0cb2`。
- 官方 offline smoke utility 在 `env -i`、非仓库 cwd、`PIP_NO_INDEX=1`、fresh empty pip cache且 loader/Python/PIP index/target/user/proxy/venv/Conda变量清空的 parent 中退出 `0`；`import dayu`及四条既有 CLI help smoke 全过，结束后 `PIP_CACHE_FILES=0`。
- 两份 CI workflow 已把五条真实 integration lane 拆为独立进程，并要求显式拉取固定 PostgreSQL/Redis digest；其它 full pytest invocation 排除 integration。

## External gate closure

### Redis：历史失败保留，RDX-001 / RDX-002 CLOSED

固定 Redis 8.4 digest 拉取、RepoDigest/image ID与`linux/arm64` identity核验成功。首次真实 full file运行确为`3 failed in 13.27s`：第一个节点在publish后首次read得到`NO_MESSAGE`；另两个节点因测试tenant未由migration seed而被正确的organization FK拒绝。该失败触发STOP并由Controller分别接受为：

- `RDX-001`：concrete subscriber未等待并严格验证server exact subscribe ACK；
- `RDX-002`：integration fixture未使用migration seed的authoritative default organization。

Codex内部模型在既有allowlist内修复后，resubscribe只有在有界读取到exact ACK时返回`True`，正常读取继续忽略subscribe frame；integration fixture改用`DEFAULT_ORGANIZATION_ID`，production tenant bootstrap保持不变。复证为unit `32 passed`、真实Redis+PostgreSQL full file `3 passed`、adapter coverage `91%`、Pyright/Ruff/diff-check全过，结束后owned container/network均为`0`。因此首次失败只作为历史证据保留，Redis external gate现为**CLOSED / PASS**。

### Resolver / offline bundle：CLOSED

Python 3.11 minimum与四个current platform resolver共五条lane均missing `0`、mismatch `0`；fresh current wheel、archive manifest与SHA已复核。S22-CTRL-012的POSIX symlink/Windows copy修复通过owner tests与两文件static/format/diff审计，真实sanitized/no-index archive smoke exit `0`且empty cache文件数为`0`。因此dependency/offline external gate现为**CLOSED / PASS**。

### Final review：CLOSED / DUAL CORRECTIVE RE-REVIEW PASS

- DeepSeek source review：`FAIL / open H/M/L = 0/1/0`；artifact 为 `docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-deepseek.md`。
- MiMo source review：`PASS / open H/M/L = 0/0/0`；artifact 为 `docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-mimo.md`。
- Controller 裁决：`docs/reviews/slice-2.2-scheduler-worker-redis-code-review-adjudication-20260812-codex.md`；接受正常 poll 重复 SUBSCRIBE 丢 hint，以及 Worker owner 取消/handler 程序异常未完整 reap 两项 Medium。
- Codex internal corrective fix：正常 event-assisted poll 复用已建立 subscription；任一真实 Redis failure 使 process-local subscription 状态失效，degraded health 仍 ping+resubscribe。Worker attempt、correlation 第二 heartbeat、阻塞 sync inner call与subscriber创建均由抗重复取消的 owner 完整收口，资源登记后才传播取消，且不写假 terminal。
- 冻结 SHA-256：`dayu/host/worker.py` = `a478ea195676ebd9746e1059bd64c5d02129d6cee78f990f6079598981633d9b`；`tests/application/test_platform_worker.py` = `9550543f213c383ea4ac73f805727c4cff593dac169db0b0ce6569359cda21cc`。
- Corrective focused `45 passed`；Worker coverage `86%`；exact Pyright `0 errors, 0 warnings, 0 informations`；Ruff default/F/I 与 `git diff --check` PASS。
- DeepSeek corrective re-review：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-deepseek.md`，`PASS / open H/M/L = 0/0/0`。
- MiMo corrective re-review：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-mimo.md`，`PASS / open H/M/L = 0/0/0`。
- Independent corrective gate：相关 `399 passed`；Pyright `0/0/0`；Ruff default/F/I PASS；full-rule baseline `2352`、current `2351`、positive delta `{}`；implementation allowlist `51/55`、outside `0`；staged paths在acceptance前仍为`0`。
- Corrective后全仓clean non-integration：`8493 passed, 5 skipped, 209 deselected in 199.96s`。

双路均对上述同一冻结bytes给出open H/M/L=`0/0/0`，所有accepted findings CLOSED；当前可形成implementation accepted local commit。

## Explicit non-actions

- 联网动作仅用于拉取计划固定Redis digest以及clean resolver/offline wheelhouse构建；未访问行情、模型、provider、Broker或交易服务。
- 真实Redis首次失败后只按Controller裁决修改既有allowlist内adapter/tests并完成focused与full-file复证；未扩大production tenant/bootstrap或Redis真源边界。
- 未执行 live market、SEC、模型、provider、Broker 或交易动作。
- 未提交 implementation、未 push、未创建 PR。
- DeepSeek 与 MiMo 未参与代码编写；首轮只读审核已完成，全部 production/test 写入与 corrective fix 均由 Codex 内部模型完成。

## Handoff

Redis与dependency/offline external gates、corrective后clean non-integration suite及DeepSeek + MiMo corrective re-review均已PASS；所有accepted findings CLOSED。handoff现为Controller创建本地accepted implementation commit。未授权push、PR、merge、部署或任何live交易动作。
