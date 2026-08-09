# 投资平台恢复计划独立复审（Terra）

- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **审查性质**：Controller 修订后的独立、只读 plan re-review
- **已完整读取的前置材料**：根 `AGENTS.md`、Terra 初审 `docs/reviews/plan-review-20260810-072034-terra.md`、MiM 初审 `docs/reviews/plan-review-20260810-072130-mimo-native.md`、Controller 修复 `docs/reviews/plan-fix-20260810-072408-codex.md`。
- **本地审查时间**：2026-08-10T07:38:27+08:00
- **范围**：仅审计划可否安全移交 implementation；未修改计划、代码、测试或既有 artifact。

## 结论

**FAIL**。修订版已用可核查的契约关闭 Terra T-01--T-08 与 MiM M-001--M-003、M-005--M-013；实际 slice 数也已从原先不一致的 35 项改为 **37 项**。但 M-004（DAG）未完全关闭：现有 DAG 仍允许两个 slice 在其明确需要的前置产物不存在时开始。它与“每 slice 只能修改 allowlist、发现 gap 必须停报”的执行规则直接冲突，因此尚不能进入 implementation。

**Open 汇总：H=0，M=1，L=0。**

## 已验证的假设与仓库事实

1. `dayu/investment/` 目前不存在；计划第 100 行已准确把它限定为 greenfield package。
2. 当前实际 Fins 默认组合根仍固定装配 FS repositories：`dayu/fins/service_runtime.py:1271-1316`；启动期通过 `dayu/services/startup_preparation.py:161-199` 创建它。计划 Slice 1.4 已把两个真实组合根及黑箱验证纳入 allowlist/测试（计划:364-369）。
3. 当前 FastAPI router 注册集中于 `dayu/web/fastapi_app.py:22-55`，Streamlit 详情页 tab 组合在 `dayu/web/streamlit/pages/main_page.py:55-98`。计划 Slice 7.1--7.5 已分别纳入必要的 composition roots（计划:516-545）。
4. Fins source 读取需要 `ticker + document_id + source_kind`，blob 读取要求 Fins handle（`dayu/fins/storage/repository_protocols.py:148-184,224-253`）。计划 §6.3 已定义不暴露路径的强 `EvidenceLocator` 及 Fins-owned resolver/validator/citation projection（计划:202-215）。
5. Host SQLite 仍独占 session/run/pending turn/reply outbox/permit（`dayu/host/host_store.py:31-122`），而且已有 CAS/fence recovery 约束（`dayu/host/README.md:187-215`）。计划 §6.1 已清楚划分 Host/PG owner、correlation 和 query-before-retry（计划:144-150）。
6. `rg '^#### Slice '` 对计划的直接计数为 **37**；编号覆盖 Slice 0.1 至 8.4，且计划在第 296 行明确该总数。

## Terra T-01--T-08 复核

| 初审项 | 复审结论 | 直接计划证据 |
| --- | --- | --- |
| T-01 workspace migration | 已关闭 | Slice 1.5 明确 `dayu-cli init --import-existing-workspace`、唯一 marker/fingerprint、stage/validate/单事务发布、rollback/rerun 及“不复制 Host/Fins bytes”（计划:371-376）。这也符合现有统一迁移 runner 的登记模式（`dayu/cli/workspace_migrations/runner.py:1-80`）。 |
| T-02 production composition roots | 已关闭 | Slice 1.4 覆盖 Fins runtime 和 startup composition；Slice 2.2 覆盖平台 startup；7.1--7.5 覆盖 FastAPI/Streamlit roots；8.2 给出 Compose 启动顺序与 smoke（计划:364-369、387-392、516-545、561-566）。 |
| T-03 tenant/RBAC sequencing | 已关闭 | TenantId/Principal/TenantScope 在 0.1；identity 与 RLS 在第一张 PG schema；私有表 non-null tenant、显式 scope、`SET LOCAL app.tenant_id` 与 repository predicate 双层隔离均已冻结（计划:326-332、343-355、160-167）。 |
| T-04 Fins exact locator | 已关闭 | `EvidenceLocator` 定义 repository/document/source kind/version/hash/精确片段 locator，FS/S3 canonical projection 一致，drift/删除/跨 ticker fail-closed（计划:202-215、357-362）。 |
| T-05 execution recovery / kill switch | 已关闭 | Decision、OrderIntent、BrokerOrder、Ledger/Reconciliation 分 aggregate、唯一键、CAS/fence、unknown-submit query-before-retry、late fill 和 kill-switch partial-fill 策略均已明确（计划:243-255；Slice 5.5、6.1--6.2：482-500）。 |
| T-06 point-in-time | 已关闭 | effective/published/ingested/available/revision、universe/corporate action/FX/fill policy 和 fingerprint 已冻结；Slice 5.3--5.4 给出 late filing/revision/delisting/时区等反例（计划:264-274、468-480）。 |
| T-07 Host-PG recovery | 已关闭 | SQLite/PG 责任、immutable `AgentRunCorrelation`、外层 job truth、Host terminal 分支及 cancel projection 已明确；Slice 2.1 的 crash matrix 覆盖对应路径（计划:144-150、380-385）。 |
| T-08 slice count | 已关闭 | 计划显式为 37 slices（计划:294-296），实际标题直接计数也是 37；不再声称 36。 |

## MiM M-001--M-013 复核

| 初审项 | 裁决/复审结论 | 直接计划证据 |
| --- | --- | --- |
| M-001 greenfield 误判 | Controller 拒绝有据，已关闭 | 明说 `dayu/investment/` 不存在且全部业务从零建立（计划:89-100）；Slice 0.1 的目标是创建 skeleton（计划:326-333），并不假设已有实现。 |
| M-002 缺依赖 | 已关闭 | Slice 1.1 锁定 SQLAlchemy/psycopg/Alembic/Python 3.11/PostgreSQL 16 验证；1.4/2.2/3.3 分别锁 S3/Redis/pgvector 兼容性（计划:343-349、364-369、387-392、416-421）。 |
| M-003 Fins boundary | 与 T-04 重合，已关闭 | 见 §6.3 与 Slice 1.3（计划:202-215、357-362）。 |
| M-004 slice DAG | **未完全关闭；见唯一 open finding** | 已新增 DAG 和 lane（计划:298-322），但边仍遗漏 0.2 与 2.3 的实质前置条件。 |
| M-005 Claim trust | 已关闭 | confidence 不自动批准、expiry 转 `review_required`、material conflict 人工 resolve 前阻止下游；有对应 domain tests（计划:173-178、213-215、403-408）。 |
| M-006 look-ahead | 与 T-06 重合，已关闭 | 见 §6.5、Slice 5.3--5.4（计划:264-274、468-480）。 |
| M-007 kill switch | 已关闭 | PG control 真源、Redis 仅 invalidation、Service/adapter 双读、scope、dual-role reopening 和 partial-fill hold/reconcile 均已写入（计划:251-255、496-500）。 |
| M-008 tenant | 已关闭 | 从第一张私有表 tenant-ready，含 default organization、RLS 与 worker/search/backup/audit scope（计划:59-61、162-167）。 |
| M-009 Redis degradation | 已关闭 | 5 秒 poll、30 秒 health、3 次阈值及 event-assisted/polling-degraded 转换和测试已固定（计划:152-156、387-392）。 |
| M-010 live broker owner | 已关闭 | user/admin/trader-compliance owner、secret reference/rotation/revocation，以及 read-only 到 policy-auto 的逐级 gate 已冻结（计划:574-581）。 |
| M-011 slices 过多 | Controller 拒绝有据，已关闭 | 37 项的安全边界和独立 review 理由明确，避免把 schema/tenant/execution 真源合并（计划:294-296）。 |
| M-012 integration lane | 已关闭 | 目录、marker、PR 受影响 lane 与 nightly 全集均已指定（计划:320-322、595-606）。 |
| M-013 README 职责 | 已关闭 | investment/root/dayu/tests README 的固定职责和 hard gate 已明确（计划:609）。 |

## Findings

### 1-未修复-中-DAG 仍允许组合根与 source-sync 在必要基础设施之前实施
- **位置**: §8.0 DAG、Slice 0.2、1.2、2.1--2.3（计划:298-322、335-339、351-355、380-399）。
- **问题类型**: 切片过粗 / 不可直接实施 / production composition root 与依赖排序漏洞。
- **当前写法**: DAG 强制 `0.1 -> 0.2 -> 1.1 -> 1.2`，却要求 Slice 0.2 的“真实 startup composition 创建 platform settings、repositories 和 Service bundle”（计划:301、337-339）。同一 DAG 允许 `1.4 -> 1.5 -> 2.3`，没有 `2.1/2.2 -> 2.3` 边（计划:301-317）；但 2.3 完成条件要求 production composition registry 注册 handler，并把 receipt 绑定 PostgreSQL job attempt（计划:394-399）。
- **反例/失败场景**: 当前仓库没有 `dayu/investment/`（审查时直接检查为 absent）。0.2 先于 1.1/1.2 时，既没有投资域 PostgreSQL schema，也没有 Slice 1.2 才定义的 repository protocols/repositories；为完成“创建 repositories/Service bundle”，实施者只能越 allowlist 提前实现后续模块，或用未类型化的临时对象/空 adapter。后者违反项目禁止 `Any/object` 和兼容 facade 的约束，前者违反计划第 294 行的 slice allowlist。类似地，2.3 若在 2.1/2.2 前执行，不存在它所需的 `JobHandlerProtocol`、PostgreSQL job attempt/receipt、worker registry 与 scheduler lifecycle，无法完成其自身注册/receipt completion predicate。
- **为什么有问题**: Controller 已接受 M-004，并在计划中要求每个 slice artifact 列 predecessor accepted commit 和 production composition root（计划:320-322）。这两条缺失边会让 agent 在正确遵守 DAG 时仍必须自行重设计接口或偷跑 future-slice work；正是 code-generation-ready 要避免的情形。
- **直接证据**: Slice 0.2 的 repository/Service bundle completion（计划:337-339）早于 Slice 1.1 的 DB schema（343-349）与 Slice 1.2 的 repository protocols（351-355）。Slice 2.3 的 handler/job-attempt completion（394-399）早于其在 DAG 中实际要求的 2.1 job contract（380-385）和 2.2 registry/worker（387-392）。现有唯一 Fins/runtime 装配仍是 `dayu/services/startup_preparation.py:161-199`，并不存在可复用的 investment repository bundle；因此这不是假设的现成基础设施。
- **影响**: 实施 Agent 跑偏 / 临时 seam 或反向依赖 / production composition root 无法黑箱验收 / source-sync recovery receipt 无 owner / 后续 accepted commit 边界失真。
- **建议改法和验证点**: 将 0.2 收缩为纯 settings/配置验证，或把其“创建 repositories 与 Service bundle”的实现和 composition black-box test 移至以 1.2 为 predecessor 的 slice，并相应扩展该 slice 的 composition-root allowlist。DAG 至少增加 `2.1 -> 2.3` 和 `2.2 -> 2.3`；若 2.3 不能脱离 scheduler/registry 完成，则明确三者串行。修订后逐项验证：任何 DAG-ready slice 的所有 imports、schema、protocol、registry 和 completion predicate 都已由 predecessor accepted commit 提供；按 DAG 顺序运行 0.2/2.3 的受影响 unit + integration command，不使用占位 adapter。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open questions

无独立 open question。真实 Broker vendor/account/market 仍是 Slice 8.4 明确的外部授权 gate（计划:574-581），不属于本 deterministic plan 的未收敛缺口。

## Residual risks 与建议跟踪去向

| 风险 | 状态 | 建议 destination |
| --- | --- | --- |
| DAG/implementation order 仍不自洽 | Open M；阻止 implementation | Controller 仅修订 target plan 后进行双路 re-review |
| broker vendor-specific 规则与凭据 | 合理的外部授权 gate | Slice 8.4 独立 plan review + 用户外部授权 |
| 数据供应商变更、过拟合、broker 乱序、Redis/S3 故障 | 已有 owner，但不得以 residual 表替代 slice 验收 | 计划 §12 与相应 slice 的 integration/acceptance |

## 最终复审结论

**fail**：Open **H=0 / M=1 / L=0**。Controller 先关闭 Finding 1 并更新 target plan；随后 Terra 与 MiM 均需复审通过且 H/M/L 清零，才能创建 accepted plan commit。
