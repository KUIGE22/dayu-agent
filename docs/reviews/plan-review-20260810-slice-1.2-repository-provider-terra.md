# Slice 1.2 Repository/provider erratum — Terra plan review

- **审查范围**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..04，以及 `docs/reviews/plan-fix-20260810-slice-1.2-repository-provider-codex.md`。
- **审查方式**：只读对抗审查；逐项对照当前 composition、config、startup、protocol 与 Slice 1.1 已冻结的 13 表/RLS schema。未运行会启动 Docker 的测试，也未连接 live/broker 或修改实现。
- **基线状态**：工作区已有 plan 和 Codex fix 未提交改动；本审查不归属、未触碰它们。`git diff --check` 通过。
- **结论**：**FAIL**。open：**H0 / M2 / L0**。Slice 1.2 implementation 应继续冻结，直至两项 M 均以 plan 勘误闭合并经复审。

## 已确认的闭合项

- S12-CTRL-01 正确将 repository 的第一个公共参数锁为 `TenantScope`，并同时要求 transaction-local `set_config` 回读、显式 tenant predicate 和 RLS；这避免把 RLS 当成唯一边界。
- S12-CTRL-01 已明确 atomic company/security registration 的后续 insert 失败必须回滚前序 public-reference insert，S12-CTRL-03 也要求真实 PG16 验证 unique、CAS、rollback、setting cleanup 和跨租户读写拒绝；这排除了 SQLite/fake 伪 integration。
- S12-CTRL-02 把 `PlatformIdentityServiceProtocol` 的真源置于纯 `investment.composition`，只允许 Service 层 re-export；将 production provider 固定在既有 startup composition root、development 仍须显式注入，并禁止 future owner，依赖方向正确。
- allowlist 新增 `domain/source.py`、storage/protocol、具体 Service、startup 与 PG16 integration/doc owner，范围与 S12 的职责相符，未扩大至 schema/migration 或 future slice。

## Findings

### TERRA-S12-001 — Medium — UUID tenant admission 与 DTO/API 的可生成契约未闭合

- **位置**：S12-CTRL-01（plan 第 597–616 行）；当前 `dayu/investment/domain/identifiers.py` 第 49–95、271 行起；Slice 1.1 的 private-table/RLS UUID tenant schema。
- **问题类型**：输入 boundary / physical-schema contract / stable error。
- **当前写法**：计划要求所有 UUID 在 storage 前严格校验、每个 repository 方法接收 `TenantScope`，再将其写入 `SET LOCAL app.tenant_id`；DTO 仅以“至少包含”列出对象和 ID，未冻结字段、返回形态、错误映射，亦未规定无效 `TenantScope.tenant_id` 的 admission 所在层和异常。
- **直接证据**：当前 `TenantId` 继承 `_Identifier`，后者只拒绝空值与首尾空白；`TenantId("tenant-a")` 可构造，`TenantScope` 也接受它。该值进入 PG16 时，Slice 1.1 policy 的 `current_setting('app.tenant_id', true)::uuid` 需要 UUID，最终会成为 PostgreSQL 的低层 UUID cast/bind 错误。`identifiers.py` 又不在 Slice 1.2 allowlist 内。
- **反例/复现**：以现有 `Principal(TenantId("tenant-a"), ...).to_scope()` 取得 scope，调用任一 planned repository 方法。实现若先 `set_config` 再 query，会在 RLS `::uuid` 或 UUID parameter bind 处失败；实现若自行悄悄转换/放宽，则每个 repository 会重复定义 admission。两种行为都不能由当前 plan 的测试判定为唯一正确的 stable API。
- **为什么不能接受**：这不是实现细节：S12 以 `TenantScope` 作为所有事务隔离的入口，且 Slice 1.1 的 SQL physical type 已是 UUID。没有该边界的确切类型/错误契约，codegen 无法确定应改既有 identifier、在 repository preflight 校验、还是令 DTO 接受 UUID；也无法写出不依赖驱动错误文案的负例。类似地，“至少包含”不能唯一导出 create/update/request/projection 的字段、可更新性、ID 的生成方与每个 conflict/not-found/version error。
- **影响**：租户非法输入会泄漏为 database-specific 异常，或产生跨仓储不一致；DTO/protocol 的不同实现可能都声称满足计划，却不能互换。这会削弱 RLS 的 auditability 和严格类型目标。
- **最小修复**：在 S12-CTRL-01 增加一张 frozen API/physical mapping：逐个 company、security、source definition、subscription request/projection 的字段、Python strict type、UUID/text/enum/JSON/default 对应、生成/返回 ID、可变字段与每个稳定 error。并明确一个不扩 allowlist 的 tenant admission 路径，例如每个 Postgres entry 在开启 session 前以 `UUID(scope.tenant_id.value)` 预校验，失败映射为 protocol 声明的 `RepositoryInputError`，随后才执行 `set_config`；加入 invalid non-UUID scope 的 integration negative，断言无 SQL mutation/无 driver error。若选择把 `TenantId` 改为 UUID-only，则必须相应扩 allowlist、说明现有 caller migration 和覆盖测试，不能含蓄处理。
- **残余风险**：若选择全局 identifier 收紧，会影响 Slice 1.1 之外当前 Principal 的构造契约；故应先明确 owner 与迁移范围再解冻。

### TERRA-S12-002 — Medium — production default-provider 的真实 startup black-box 路径未被验收强制执行

- **位置**：S12-CTRL-02（第 626–633 行）与 S12-CTRL-03（第 635–643 行）；当前 `dayu/services/startup_preparation.py` 第 133 行起、`dayu/startup/platform.py` 第 39 行起，以及现有 startup unit 的 explicit-provider/absence 分支。
- **问题类型**：composition admission / integration coverage / secret error boundary。
- **当前写法**：计划要求在 production、platform enabled、未显式注入 provider 时读取 `postgres_dsn_env` 并构造 real provider；同时要求 PG16 integration 证明“production startup 组合只含一个真实 service”。但没有要求测试通过当前实际 public startup 调用、以 `platform_provider=None` 进入该条件分支；也未锁定 missing/blank DSN 在该分支的稳定脱敏错误和零 side-effect 断言。
- **直接证据**：当前 `prepare_host_runtime_dependencies()` 取得 settings 后将可选 `platform_provider` 交给 `build_platform_composition()`；后者当前在 enabled 且 provider 缺失时 fail-fast。现有 unit 覆盖的正向路径是显式注入 fake provider，缺失 provider 也是预期失败。因此一份 integration 可以自行构造真实 repository/provider 后断言 composition 含一个 service，仍然不执行计划要求新增的 default-provider 分支。
- **反例/复现**：未来实现在 helper 中构造 provider 却没有从 `prepare_host_runtime_dependencies(..., platform_provider=None)` 调用它，或读取了错误的环境变量/带 password 的错误消息。手工注入的 real provider integration 仍可通过 S12-CTRL-03 列出的 service count、RLS/CAS 测试，production default path 则继续 fail-fast 或泄漏 DSN。
- **为什么不能接受**：production default provider 是本次勘误引入的安全关键变化；没有从真正 public startup entrance 的无注入 black-box，无法证明优先级、settings lookup、真实 PG16 connection、future-import exclusion 或 secret redaction。计划也未明确发生 startup 失败时 engine/session/fixture owner 资源必须为零。
- **影响**：上线配置即使合法也可能仍无法装配，或在错误配置中暴露 DSN password；测试对依赖注入路径绿而 production 路径红。
- **最小修复**：在 S12-CTRL-03 明定一个真 PG16 startup black-box：完成 Slice 1.1 migration 后，仅提供 production profile、`postgres_dsn_env` 所指的 runtime application-role DSN 与必要非秘密 settings，调用实际 `prepare_host_runtime_dependencies(..., platform_provider=None)`（或明列的 public 等价入口），断言 default 分支被走到、注册精确只有 concrete `investment_identity`、可用该服务完成一次真实 repository 操作且无 future import。再以同一 public path 覆盖 env 缺失与空值：断言 stable redacted `PlatformCompositionError`、消息/日志不含 raw DSN、URL password 或环境值、没有 Host/Fins/engine/session owner 残留。测试 finally 必须复用 Slice 1.1 owner-label cleanup 并断言 PG17 未被枚举/触碰。
- **残余风险**：该 black-box 需要定义最小 production config fixture；应只放在允许的 PG16 integration lane，不应把真实 engine 伪装成 unit fixture。

## Open questions

无。两项均是现有代码与计划文本可直接对照得出的缺口，不依赖 future owner 决策。

## Residual risk

除上述 open 项外，S12 仍必须保持 Slice 1.1 的 13 表、RLS policy/ACL、migration 与 Docker fixture 为真源；本勘误不可借 repository 实现偷偷改变 schema、引入 `create_all()`、SQLite/fake integration、development implicit provider 或 jobs/evidence/portfolio imports。

## 最终裁决

**FAIL，open H0 / M2 / L0。** 修订已显著收敛 repository、Service 与 provider 的 owner，但尚未将 UUID tenant admission/DTO API 和 production default-provider public black-box 固化为可唯一实现、可回归验证的契约。完成以上最小 plan 修复后再进行 closure re-review；本次未实施任何代码、测试、README、plan 或既有 artifact 改动，未 commit/push/PR。
