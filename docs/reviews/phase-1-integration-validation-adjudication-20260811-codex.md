# Phase 1 集成验收裁决

- Controller: Codex
- Branch / HEAD: `codex/investment-platform` / `b9e5b56`
- Scope: Phase 1（Slices 1.1–1.5）vertical integration closure
- Status: **CLOSED / DUAL CORRECTIVE RE-REVIEW PASS**

## 证据来源

- `docs/reviews/phase-1-integration-validation-20260811-codex-spark.md`
- `docs/reviews/phase-1-docker-integration-validation-20260811-deepseek-flash.md`

## Controller 裁决

### P1-INT-01 — Spark 无法访问 Colima socket

- Disposition: **ENVIRONMENT-LIMITATION / SUPERSEDED / CLOSED**
- Spark 的受限执行环境无法访问 Docker daemon，因此不能提供容器真值；这不是仓库缺陷。
- DeepSeek-Flash 在同一工作树、同一 HEAD 上使用本机 Colima 和本地 pinned digest 镜像完成了真实容器验收，取代 Spark 的 Docker 部分证据。
- Spark 的静态证据仍有效：架构边界 151 passed、migration/identity unit 60 passed、dependency boundary 29 passed、scoped pyright 0、Ruff PASS。

### P1-INT-02 — production startup black-box 使用失效 S3 占位配置

- Disposition: **ACCEPTED / TEST CONTRACT DEFECT / FIX REQUIRED**
- Severity: Medium（阻塞 Phase 1 closure，不是 production correctness regression）。
- 真实容器结果为 69 passed / 3 failed；三个失败均属于
  `TestProductionStartupBlackBox`：
  - `test_production_provider_wires_real_identity_service`
  - `test_production_provider_wrong_role_rejected`
  - `test_production_provider_close_disposes_engine_once`
- 三个测试仍把 `DAYU_PLATFORM_OBJECT_STORAGE` 设为 Slice 1.2 时代的
  `s3://placeholder`。Slice 1.4 已把 production startup 固定为严格 JSON S3 admission，
  因此测试在 identity provider / role / close lifecycle 断言前即抛 `S3SettingsError`。
- 第一个失败又因 migration downgrade 不在覆盖全部异常路径的 `finally` 中而遗留角色，
  导致同文件后续测试出现 `role already exists` 连锁失败。

## 精确修复契约

生产代码、migration、README、master plan 全部冻结。仅允许：

1. 修改 `tests/integration/investment/test_identity_repositories_postgres.py`；
2. 新增一份 Phase 1 integration fix artifact；
3. 让上述三个测试使用符合 Slice 1.4 严格契约的对象存储配置，并在真实网络 I/O 边界使用有类型的测试替身；不得恢复宽松解析、不得加入兼容分支；
4. 保留真实 PostgreSQL provider、role admission、service registration 与 engine lifecycle 路径；
5. 把 login、migration 与 role cleanup 纳入覆盖 startup/assertion 异常的可靠 `finally`，证明单测失败不会污染共享 cluster；
6. 先跑三个目标测试，再跑完整 identity integration 文件，最后复跑四条 Phase 1 integration lanes；验证 owned container/network/role 零残留。

## Closure gate

初始补丁由 Codex Spark 低成本实施，DeepSeek-Flash 负责真实 Docker 验证与运行期修正；随后由 Terra 与 MiMo 独立复审。两路 open H/M/L 全为 0、完整 Docker lane 全绿后，Controller 才能将 Phase 1 标为 accepted 并创建本地 closure commit。禁止 push/PR。

## 初审裁决（2026-08-11）

Review sources:

- `docs/reviews/phase-1-integration-fix-review-20260811-terra.md`
- `docs/reviews/phase-1-integration-fix-review-20260811-mim.md`

### Accepted / fix required

1. **P1-INT-FIX-01（Terra M1）**：接受。补丁把
   `_build_s3_store_from_settings()` 整体 stub，导致六键 JSON、credential 与真实 strict
   parser 未被目标 black-box 消费。修复必须保留该函数，network probe 只在
   `S3FileStore.head_bucket()` 边界替换；加旧 `s3://placeholder` 负例。
2. **P1-INT-FIX-02（Terra M2）**：接受。线性 teardown 会被 `prepared.close()` 或
   `drop_temporary_login()` 异常短路。改为状态化/嵌套 `try/finally`，保证 env、login、
   migration downgrade 都被尽力执行，且原始失败不被静默吞掉；增加 close-failure 清理
   证明。
3. **P1-INT-FIX-03（Terra M3）**：接受。wrong-role 先创建 cluster-wide login、后在
   cleanup scope 外 migrate，migration 失败会泄漏 login。顺序改为 migrate 成功后才创建
   login，并从创建时起进入 cleanup scope。
4. **P1-INT-FIX-04（Terra L1）**：接受为有界清理，随上面修复去除私有
   `_FsRepositorySet` 未初始化实例与 `_bare`/`TypeVar`；使用显式最小测试替身，不扩大
   production seam。

### Rejected / closed

- **MiM finding 1**：拒绝为 non-defect。目标测试有意多次调用 `prepared.close()` 来证明
  幂等性；finally 再调用是异常安全清理，不应删除该行为断言。
- **MiM finding 2**：拒绝为 non-defect/out-of-scope。missing-DSN 测试锁定最早的严格
  platform settings failure，在 object-store admission 之前返回；本 finding 未证明错误
  verdict 或测试漂移。目标三个 S3 black-box 将另有真实 strict parser 和 invalid 负例。
- **MiM finding 3**：拒绝原事实。`ObjectStoreTestDouble` 已被 `_bare()` 泛型签名使用；
  不过该 helper 会因 Terra L1 的有界清理一并删除。

当前结论：**REVIEW FIX REQUIRED / AWAITING CORRECTIVE DUAL RE-REVIEW**，Controller open
H/M/L = `0/3/1`。production、migration、README、master plan 继续冻结。

## Corrective closure

Corrective review sources:

- `docs/reviews/phase-1-integration-corrective-review-20260811-terra.md`
  （初轮 FAIL，唯一 M：failure-path 测试未使 cleanup error 可见）；
- `docs/reviews/phase-1-integration-corrective-review-20260811-mim.md`
  （PASS，open `0/0/0`）；
- `docs/reviews/phase-1-integration-final-review-20260811-terra.md`
  （最终 PASS，open `0/0/0`）。

Terra 最后一项 Medium 已接受并修复：close-failure 测试现在对任何非空
`cleanup_errors` 显式抛 `ExceptionGroup`，同时锁定首次 close 传播、第二次 cleanup retry
和资源零残留。DeepSeek-Flash 在修复后再次运行 identity `16/16` 与四条 Phase 1 lane
`74/74`，scoped pyright 0、Ruff F/I/default、diff-check 全绿，owned container/network/role
零残留。

最终 Controller open H/M/L = `0/0/0`。P1-INT-01/02、P1-INT-FIX-01..04、Terra
corrective Medium 全部 CLOSED；production/migration/README 未因验收修复发生变化。Phase 1
获准本地 accepted closure commit，仍禁止 push/PR。
