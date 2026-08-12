# Slice 2.2 Scheduler / Worker / Redis — corrective review fix

- 日期：2026-08-12
- Implementation baseline：`37cac2f`
- Accepted plan HEAD：`82cc7d4c5c369f776e12a8dd5a44d6557445ee33`
- Controller adjudication：`docs/reviews/slice-2.2-scheduler-worker-redis-code-review-adjudication-20260812-codex.md`
- 状态：**CLOSED / DUAL CORRECTIVE RE-REVIEW PASS**

## Source reviews

- DeepSeek Flash：`FAIL / open H/M/L = 0/1/0`，source artifact `docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-deepseek.md`。
- MiMo v2.5 Pro：`PASS / open H/M/L = 0/0/0`，source artifact `docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-mimo.md`。
- Controller supplemental concurrency review独立复现了与handler-exception同根的outer-cancellation owner leak，并在第一版修复后继续复现了重复取消与subscriber创建期取消两个资源边界；均在本fix收口。

## Fixed findings

### S22-CR-001 — fixed — normal poll 不再重复 SUBSCRIBE

- `PlatformWorker`新增private、process-local subscription truth；startup首次订阅成功后，普通event-assisted poll直接复用，不再把queued message当作下一次SUBSCRIBE ACK消费。
- create/subscribe/read/ping的closed Redis failure统一使该truth失效；进入polling-degraded必源于failure，因此health probe在ping成功后仍强制resubscribe，完整成功才恢复event-assisted。
- PG仍是claim/lease/fence真源；Redis只提供可丢hint，公开协议、settings阈值与health interval未变。

### S22-CR-002 — fixed — Worker-owned work 抗重复取消并先于资源关闭收口

- attempt owner第一次或重复收到`task.cancel()`后，把handler/heartbeat cleanup交给唯一独立task，并循环shield直到真实完成；最终仍传播`CancelledError`。
- handler先收到协作取消；非协作handler与阻塞heartbeat/to_thread均必须真实返回后才能离开attempt。期间subscriber close保持0，且不调用complete/fail。
- complete/fail转入governance-required后创建的第二heartbeat由correlation wait自己以相同抗重复取消语义回收。
- handler未分类异常先stop/reap heartbeat，再由`run()`映射为exit 1；无orphan heartbeat。
- subscriber factory是资源生产边界：owner取消发生在阻塞create时，Worker仍等待真实结果、校验并登记subscriber，然后传播取消，由`run.finally` exact-once close；不会泄漏已创建但未登记的PubSub。
- 通用sync bridge在重复取消时仍等待真实thread inner task结束；不会把outer cancellation误当作inner已经停止。

## Scope

Production/test修改严格为：

- `dayu/host/worker.py`
- `tests/application/test_platform_worker.py`

另更新Controller adjudication、本fix与既有implementation artifact。未修改plan、Redis adapter、PostgreSQL/domain/Service、CLI/startup、dependency/lock、README或workflow。

冻结SHA-256：

- `dayu/host/worker.py`：`a478ea195676ebd9746e1059bd64c5d02129d6cee78f990f6079598981633d9b`
- `tests/application/test_platform_worker.py`：`9550543f213c383ea4ac73f805727c4cff593dac169db0b0ce6569359cda21cc`

## Validation

- Worker owner file：`45 passed`。
- Worker coverage：`614 statements / 87 missing / 86%`，门槛`>=80%` PASS。
- exact Pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff default、F/I：PASS。
- `git diff --check`：PASS。
- Adversarial dynamic checks：active non-cooperative handler + blocked heartbeat双cancel；correlation第二heartbeat双cancel；blocked PubSub/close重复取消；subscriber factory单/双取消；handler RuntimeError；normal poll queued hints；degraded health recovery。所有路径均在barrier未释放时owner未结束且subscriber未关闭，释放后才传播取消或返回exit 1；close exact once，complete/fail为0，无live child。
- 一次显式pytrace coverage运行触发coverage.py内部tracer stack error，另一次Coverage API重载导致定时测试超时；标准Coverage C tracer随后稳定执行45项并得86%，未修改production规避工具问题。

## Gate

DeepSeek与MiMo已分别对同一冻结bytes完成corrective re-review：

- `docs/reviews/code-review-20260812-113500-slice-2.2-corrective-deepseek.md`：`PASS / open H/M/L = 0/0/0`；
- `docs/reviews/code-review-20260812-113500-slice-2.2-corrective-mimo.md`：`PASS / open H/M/L = 0/0/0`。

Corrective后related tests `399 passed`，全仓clean non-integration `8493 passed, 5 skipped, 209 deselected`；full-rule positive delta `{}`，allowlist outside `0`。本fix现为READY FOR ACCEPTED COMMIT。仍未commit/push/PR，未调用行情、模型、provider、Broker或交易接口。
