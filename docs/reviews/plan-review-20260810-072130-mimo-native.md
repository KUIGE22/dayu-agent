# Plan Review: Investment Platform Restoration

- **Review target**: `docs/plans/2026-08-10-investment-platform-restoration.md`
- **Baseline**: `d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **Branch**: `codex/investment-platform`
- **Reviewer**: MiMo (independent plan review)
- **Timestamp**: 2026-08-10T07:21:30

## Assumptions Tested

1. **Investment domain can be built incrementally on existing Dayu architecture** - FALSE: investment domain 不存在，需从零构建
2. **PostgreSQL/Redis/S3 dependencies are available** - FALSE: pyproject.toml 中无相关依赖
3. **36 slices are code-generation-ready** - PARTIAL: 部分 slices 缺乏足够实施细节
4. **Fins storage boundary is clear** - FALSE: investment 与 fins 数据访问边界未明确
5. **Existing Host can be extended for investment jobs** - NEEDS EVIDENCE: 无 durable job 实现证据

## Findings

### 001-未修复-[严重]-investment domain 从零开始但 slice 0.1 假设已有骨架

- **Plan位置**: Slice 0.1 (line 246-252)
- **问题类型**: 动机不成立 / 不可直接实施
- **当前写法**: "建立纯 domain 包和导入方向测试，不实现业务行为"；allowed files 包括 `dayu/investment/domain/identifiers.py`、`dayu/investment/domain/money.py`
- **反例/失败场景**: glob 结果 `dayu/investment/**/*.py` 返回 "No files found"。investment domain 完全不存在，但 plan 假设可以从 "skeleton" 开始，暗示某种基础结构已存在。implementation agent 需要从零创建整个包结构，而非 "skeleton" 增量。
- **为什么有问题**: plan 4.2 声称 "已证实缺口" 包括 "没有投资域 PostgreSQL schema"，但 slice 0.1 的措辞暗示存在某种可增量扩展的骨架。对 implementation agent 而言，"建立 skeleton" 和 "从零创建" 是两种完全不同的工作量和指导粒度。
- **直接证据**: glob 结果 `dayu/investment/**/*.py` 返回空；plan line 246-248 列出的 allowed files 全部不存在。
- **影响**: Implementation agent 需要自行决定包结构、__init__.py exports、类型定义位置等基础架构决策，偏离 plan 预期的 "code-generation-ready" 标准。可能导致 Phase 0 产出与后续 Phase 1-8 的接口假设不一致。
- **建议改法和验证点**: 明确声明 investment domain 是 greenfield 项目。Slice 0.1 应显式列出需要创建的完整目录结构、__init__.py exports、以及与现有 dayu 包的集成点。验证点：检查 investment domain 是否可以被 dayu 顶层导入而不引入循环依赖。
- **修复风险（低）**: 低风险，仅需修改 plan 措辞和 allowed files 列表
- **严重程度（严重）**: 高影响，影响所有后续 slices 的接口假设

---

### 002-未修复-[严重]-PostgreSQL/Redis/S3 依赖缺失且无迁移策略

- **Plan位置**: Slice 1.1 (line 262-268), Phase 1 整体
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: plan 6.1 声称 "PostgreSQL 16 是投资域真源"，slice 1.1 允许修改 `pyproject.toml`、`requirements*.txt`
- **反例/失败场景**: pyproject.toml 中无 `sqlalchemy`、`psycopg`、`redis`、`s3`、`minio`、`pgvector` 依赖。grep 结果无 `FOR UPDATE`、`SKIP LOCKED`、`pgvector` 代码证据。Host 当前使用 SQLite (证据：`dayu/host/protocols.py` line 369 "底层 SQLite")。Plan 没有说明如何处理现有 SQLite Host 与新 PostgreSQL investment domain 的共存策略。
- **为什么有问题**: Plan 假设 PostgreSQL 可以作为 "全新 schema" 直接引入 (line 128)，但没有解释：(1) 现有 Host SQLite 与新 PostgreSQL 如何共存；(2) 是否需要 dual-write 或迁移期；(3) 依赖安装顺序和兼容性。Implementation agent 在 slice 1.1 需要一次性添加所有依赖并确保不破坏现有测试。
- **直接证据**: pyproject.toml line 36-61 无数据库/缓存依赖；dayu/host/protocols.py line 369 提到 "底层 SQLite"。
- **影响**: Slice 1.1 可能导致现有测试失败，或迫使 implementation agent 做出未在 plan 中记录的架构决策（如是否保留 SQLite 作为 Host 真源）。
- **建议改法和验证点**: 在 Phase 1 开头增加 "共存策略" 小节，明确：(1) Host 继续使用 SQLite；(2) investment domain 使用 PostgreSQL；(3) 两者通过 Service 层隔离，无跨库事务需求。验证点：确保添加 SQLAlchemy 依赖后，现有 `pytest -q` 仍通过。
- **修复风险（低）**: 低风险，仅需增加策略说明
- **严重程度（严重）**: 影响 slice 1.1 的实施正确性

---

### 003-未修复-[高]-Fins storage 与 investment domain 边界模糊

- **Plan位置**: Slice 1.3 (line 275-279), plan 5 (line 108-120)
- **问题类型**: 架构边界 / 过度耦合
- **当前写法**: "对象存储的财报/材料实现仍放在 `dayu.fins.storage`；投资域只保存安全 locator、hash 和 repository id" (line 120)；Slice 1.3 允许 "现有 `dayu/fins/storage` 中新增 S3 实现"
- **反例/失败场景**: dayu/fins/storage/ 已有完整的文件系统实现 (fs_*.py)，且有 DocumentBlobRepositoryProtocol。但 investment domain 如何引用 fins storage 的 locator？plan 没有定义 investment domain 的 locator 类型与 fins storage 的 DocumentHandle/SourceHandle 之间的映射关系。Implementation agent 可能创建重复的 locator 类型或导致跨层依赖。
- **为什么有问题**: Plan 声称 "投资域只保存安全 locator、hash 和 repository id"，但没有定义这些 locator 的具体类型、如何从 fins storage 生成、以及 investment domain 如何在不导入 fins 实现的情况下使用它们。这违反了 plan 自己的硬依赖规则 (line 113-120)。
- **直接证据**: dayu/fins/storage/repository_protocols.py line 92-186 定义了 SourceDocumentRepositoryProtocol，使用 SourceHandle/ProcessedHandle 类型；plan line 120 说 "投资域只保存安全 locator" 但未定义 locator 类型。
- **影响**: 可能导致 investment domain 直接依赖 fins storage 实现（违反架构边界），或创建不兼容的 locator 系统（导致后续集成困难）。
- **建议改法和验证点**: 在 plan 5 中增加 "InvestmentLocator" 类型定义小节，明确：(1) locator 包含 repository_id + object_key + content_hash；(2) 由 fins storage 的 Service 在文档入库时生成；(3) investment domain 只消费 locator，不导入 fins 实现。验证点：检查 investment domain 代码无 fins.storage 导入。
- **修复风险（中）**: 需要修改 plan 5 和 slice 1.3
- **严重程度（高）**: 影响架构边界正确性

---

### 004-未修复-[高]-36 slices 缺乏实施依赖图和关键路径

- **Plan位置**: Phase 0-8 整体 (line 239-479)
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: 36 个 slices 按 phase 线性排列，每个 slice 有 allowed files 和 tests，但无显式依赖关系
- **反例/失败场景**: Slice 5.3 (optimizer) 依赖 Slice 4.1 (forecast) 的数据，但 plan 没有说明这种依赖如何在 schema 和 API 层体现。Slice 6.1 (broker) 依赖 Slice 5.5 (decision) 的状态机，但 plan 没有说明 decision_approved 状态如何触发 order_intent 创建。Implementation agent 可能并行执行有隐式依赖的 slices，导致集成失败。
- **为什么有问题**: Plan 声称 "每个 slice 都必须单独执行" (line 241)，但没有列出 slice 间的依赖关系。对于 36 个 slices 的大型计划，缺乏依赖图会导致：(1) 实施顺序错误；(2) 接口假设不一致；(3) 集成测试困难。
- **直接证据**: plan line 239-479 列出 36 个 slices，但无依赖关系声明；slice 5.3 (line 369-374) 的 input 是 "approved expected return/risk/cost/liquidity"，但这些数据的来源 (forecast/valuation) 在 slice 4.1-4.2 才定义。
- **影响**: Implementation agent 可能需要重新设计 slice 间的接口，或在集成阶段发现大量接口不匹配，导致返工。
- **建议改法和验证点**: 在 Phase 0 之后增加 "依赖图" 小节，用 DAG 形式列出关键 slices 间的依赖关系。至少标明：哪些 slices 可以并行、哪些必须串行、哪些有 schema 依赖。验证点：检查每个 slice 的 allowed files 是否包含其依赖 slice 的产出文件。
- **修复风险（中）**: 需要重新梳理 36 个 slices 的依赖关系
- **严重程度（高）**: 影响实施效率和正确性

---

### 005-未修复-[高]-Fact/Claim/Evidence trust 模型缺乏验证边界

- **Plan位置**: Slice 3.1-3.2 (line 305-323), plan 6.2 (line 142-148)
- **问题类型**: 状态机漏洞 / 测试缺口
- **当前写法**: "Agent 输出先进入 `research_candidates`：`proposed -> validated -> accepted/rejected`；只有 Service 可以 promote" (line 148)；"所有 Claim 必须最终指向可定位的 Document/Fact/Evidence locator" (line 61)
- **反例/失败场景**: Plan 定义了 Claim 的状态机 (line 186-191)，但没有说明：(1) Claim 的 "confidence" 字段如何量化和验证；(2) "valid_until" 过期后 Claim 如何处理；(3) 当多个 Claim 互相矛盾时的仲裁规则。Slice 3.2 的 tests 只提到 "cross-company link reject"，但没有说明同一公司内矛盾 Claim 的处理。
- **为什么有问题**: 投研平台的核心价值是 "严格 Fact/Claim/Evidence"，但 trust 模型缺乏边界条件定义。Implementation agent 可能实现一个无法处理矛盾 Claim 的系统，导致 "严格" 只是口号。
- **直接证据**: plan line 146-148 定义了 ClaimVersion 的字段，但没有 confidence 验证规则；line 186-191 定义了状态机，但没有 invalidation 触发条件；slice 3.2 (line 315-317) 的 tests 只提到 "cross-company link reject"。
- **影响**: 系统可能接受低置信度 Claim 作为 "approved"，或无法处理过期/矛盾 Claim，导致下游 forecast/decision 基于不可靠输入。
- **建议改法和验证点**: 在 Slice 3.1 中增加 "Trust Boundaries" 小节，明确定义：(1) confidence 阈值和验证规则；(2) valid_until 过期处理（自动 supersede 或 manual review）；(3) 矛盾 Claim 仲裁规则（时间优先、证据强度、人工干预）。验证点：添加矛盾 Claim 场景的测试用例。
- **修复风险（中）**: 需要增加 trust model 定义
- **严重程度（高）**: 影响平台核心价值主张

---

### 006-未修复-[高]-Optimizer/backtest look-ahead 防护缺乏具体实现指导

- **Plan位置**: Slice 5.3-5.4 (line 369-381), plan 6.4 (line 219)
- **问题类型**: 不可直接实施 / 测试缺口
- **当前写法**: "backtest 必须防 look-ahead、记录数据版本、训练/验证窗口、交易成本和基准" (line 219)；"Tests：walk-forward split、look-ahead trap、delisting/missing price" (line 380)
- **反例/失败场景**: Plan 声称要防 look-ahead，但没有定义：(1) 如何在 schema 层面标记数据的 "as-of" 时间；(2) 如何在 optimizer 输入中验证无未来数据；(3) backtest 如何划分 train/validation/test 窗口。Implementation agent 可能实现一个 "防 look-ahead" 的接口，但实际验证逻辑依赖人工检查。
- **为什么有问题**: Look-ahead bias 是量化策略最常见的陷阱之一。Plan 的 "防 look-ahead" 只是声明，没有提供实现机制。对于 "code-generation-ready" 的标准，这不够具体。
- **直接证据**: plan line 219 只说 "backtest 必须防 look-ahead"，没有机制定义；slice 5.4 (line 378-381) 的 tests 只列出 "look-ahead trap" 作为测试项，但没有说明如何构造这个测试。
- **建议改法和验证点**: 在 Slice 5.3 中增加 "Look-ahead Prevention" 小节，定义：(1) 所有时间序列数据必须带 as_of_date 字段；(2) Optimizer input 快照必须包含 data_version + as_of_date；(3) Backtest runner 在每个时间点验证 input as_of_date <= current_date。验证点：构造一个使用未来数据的测试用例，验证系统拒绝执行。
- **修复风险（中）**: 需要增加 schema 和验证逻辑定义
- **严重程度（高）**: 影响策略回测正确性

---

### 007-未修复-[高]-Kill switch 双端检查缺乏实现细节

- **Plan位置**: Slice 5.5 (line 382-386), plan 6.4 (line 221)
- **问题类型**: 状态机漏洞 / 契约缺失
- **当前写法**: "Kill switch 在 Service 和 broker adapter 两端都检查；任一侧关闭都不得提交新单" (line 221)；"Tests：... kill switch ..." (line 386)
- **反例/失败场景**: Plan 声称 kill switch 在 "Service 和 broker adapter 两端都检查"，但没有定义：(1) kill switch 的存储位置（PostgreSQL? Redis? 配置文件?）；(2) 如何确保两端状态一致；(3) Broker adapter 如何获取 kill switch 状态（轮询? 推送? 事件?）。Implementation agent 可能实现一个只在 Service 端检查的 kill switch，broker adapter 绕过检查。
- **为什么有问题**: Kill switch 是 "不在没有...kill switch...的情况下启用真实自动交易" 的核心约束 (line 63)。双端检查是必要的，但缺乏实现细节会导致 implementation agent 做出不安全的简化。
- **直接证据**: plan line 221 只说 "两端都检查"，没有存储和同步机制；slice 5.5 (line 382-386) 的 tests 只列出 "kill switch" 作为测试项。
- **建议改法和验证点**: 在 Slice 5.5 中增加 "Kill Switch Mechanism" 小节，定义：(1) Kill switch 状态存储在 PostgreSQL，通过 Redis 发布变更事件；(2) Broker adapter 在每次 submit_order 前从 PostgreSQL 读取 kill switch 状态；(3) 双端检查的日志和审计。验证点：模拟 kill switch 开启场景，验证 order 提交被拒绝。
- **修复风险（中）**: 需要增加机制定义
- **严重程度（高）**: 影响自动交易安全性

---

### 008-未修复-[中]-RBAC/tenant 隔离缺乏多租户考虑

- **Plan位置**: Slice 7.1 (line 416-421), plan 6.2 (line 170-171)
- **问题类型**: 范围漂移 / 最佳实践偏离
- **当前写法**: "Roles: viewer, analyst, portfolio_manager, trader, admin" (line 419)；"Users, roles, permissions, user_roles, api_tokens" (line 170)
- **反例/失败场景**: Plan 定义了 RBAC roles，但没有提到 tenant 隔离。对于 "完整公司投研与交易平台"，多租户是常见需求（如不同基金团队隔离）。如果 plan 不考虑 tenant，后续添加会非常困难（需要修改所有 schema 和 query）。
- **为什么有问题**: Plan 声称是 "完整公司投研与交易平台" (line 11)，但 RBAC 设计只考虑单租户。对于投研平台，不同基金团队的数据隔离是基本需求。如果当前 plan 不考虑，后续迁移成本极高。
- **直接证据**: plan line 170-171 定义了 users/roles/permissions 表，但无 tenant_id 字段；slice 7.1 (line 416-421) 的 roles 定义无 tenant scope。
- **建议改法和验证点**: 在 plan 6.2 中明确声明 "当前 scope 为单租户"，并在 residual risks 中添加 "多租户迁移" 作为 deferred item。验证点：检查所有 schema 是否可以未来添加 tenant_id 而不破坏现有数据。
- **修复风险（低）**: 仅需声明 scope 和风险
- **严重程度（中）**: 影响未来扩展性，但不阻塞当前实施

---

### 009-未修复-[中]-Redis/S3 failure 降级策略过于简略

- **Plan位置**: Plan 6.1 (line 131), Residual Risks (line 542)
- **问题类型**: 最佳实践偏离 / 测试缺口
- **当前写法**: "Redis 不可用时 API 仍可入 PostgreSQL 队列，worker 通过轮询退化运行" (line 131)；"Redis/通知不可用 | PostgreSQL truth + retry/outbox；通知失败不丢业务事件" (line 542)
- **反例/失败场景**: Plan 声称 Redis 不可用时退化到 PostgreSQL 轮询，但没有定义：(1) 轮询间隔和性能影响；(2) 如何检测 Redis 恢复并切换回 pub/sub；(3) 退化模式下的并发治理是否仍有效。Implementation agent 可能实现一个轮询间隔过长（导致延迟）或过短（导致数据库压力）的退化策略。
- **为什么有问题**: 生产环境中 Redis 故障是常见场景。Plan 的降级策略只是声明，缺乏实现细节。对于 "code-generation-ready" 的标准，这不够具体。
- **直接证据**: plan line 131 只说 "轮询退化运行"，没有参数定义；Residual Risks line 542 只说 "retry/outbox"，没有机制定义。
- **建议改法和验证点**: 在 Phase 2 中增加 "Redis Degradation" 小节，定义：(1) 轮询间隔配置（默认 5s，可调整）；(2) Redis 健康检查机制（每 30s ping）；(3) 自动切换逻辑（连续 3 次 ping 失败切换到轮询）。验证点：模拟 Redis 不可用场景，验证 worker 继续处理任务。
- **修复风险（低）**: 仅需增加配置和机制定义
- **严重程度（中）**: 影响生产可用性，但有明确退化路径

---

### 010-未修复-[中]-Live broker owner 和授权流程不清晰

- **Plan位置**: Slice 8.4 (line 474-479), plan 10 (line 515-516)
- **问题类型**: open question 未收敛
- **当前写法**: "Precondition: 用户选择具体 Broker、账户类型和市场；Broker 官方 sandbox/paper API 可用；独立 plan review；单独外部授权" (line 476)；"真实 Broker、live data、付费模型...都是独立外部授权 gate" (line 515-516)
- **反例/失败场景**: Plan 把 live broker 作为 "独立外部授权 gate"，但没有定义：(1) 谁是 "owner"（用户? 运维? 合规?）；(2) 授权流程的具体步骤；(3) Broker API key 的存储和轮换机制；(4) 跨市场（US/HK/CN）的 broker 差异处理。Implementation agent 在 slice 8.4 可能无法开始，因为缺少授权流程定义。
- **为什么有问题**: Live broker 是平台的高风险功能。Plan 把它推迟到 Slice 8.4，但没有收敛授权流程的 open questions。对于 "code-generation-ready" 的标准，这不够具体。
- **直接证据**: plan line 476 定义了 precondition，但没有 owner 和流程；line 515-516 只说 "独立外部授权"，没有细节。
- **建议改法和验证点**: 在 plan 10 中增加 "Live Broker Authorization" 小节，定义：(1) Owner 为用户（非系统）；(2) 授权流程：用户手动配置 broker credentials -> 系统验证 -> sandbox 测试 -> paper 测试 -> live 授权；(3) Credentials 存储在环境变量或 secret manager，不在 PostgreSQL。验证点：检查 broker adapter 不硬编码 credentials。
- **修复风险（低）**: 仅需增加流程定义
- **严重程度（中）**: 影响 live broker 实施，但可推迟到 Slice 8.4 前收敛

---

### 011-未修复-[中]-Overengineering: 36 slices 可能过度拆分

- **Plan位置**: Phase 0-8 整体 (line 239-479)
- **问题类型**: 过度设计
- **当前写法**: 36 个 slices，平均每个 slice 约 15 行描述
- **反例/失败场景**: 36 个 slices 意味着 36 次 implementation -> code review -> fix -> re-review -> commit 循环。对于一个 "恢复" 项目，这可能过度拆分。例如，Slice 4.1-4.5 (forecast/valuation/thesis/graph/report) 可能可以合并为 2-3 个更大的 slices，因为它们共享相似的 domain model 和 storage patterns。
- **为什么有问题**: Plan 声称是 "恢复" 项目 (line 11)，暗示已有某种基础。但 36 个 slices 的粒度更像是 greenfield 项目。过度拆分会导致：(1) 实施效率低（频繁 context switch）；(2) 集成测试困难（每个 slice 只验证 happy path）；(3) Review 负担重。
- **直接证据**: plan line 239-479 列出 36 个 slices；Phase 4 有 5 个 slices (forecast/valuation/thesis/graph/report)，它们共享相似的 domain patterns。
- **建议改法和验证点**: 在 plan 8 之后增加 "Slice Rationale" 小节，说明为什么选择这个粒度。对于可合并的 slices（如 Phase 4），考虑合并为 2-3 个更大的 slices，减少循环次数。验证点：检查合并后的 slices 是否仍然 "code-generation-ready"。
- **修复风险（中）**: 需要重新评估 slice 粒度
- **严重程度（中）**: 影响实施效率，但不影响正确性

---

### 012-未修复-[低]-Tests 分层缺乏 integration lane 定义

- **Plan位置**: Plan 9 (line 481-506)
- **问题类型**: 测试缺口
- **当前写法**: "PostgreSQL slices 使用真实 PostgreSQL 16 integration lane" (line 496)；"Integration lane：PostgreSQL/Redis/MinIO/Compose 单独标记并在 CI 执行" (line 504)
- **反例/失败场景**: Plan 声称有 "integration lane"，但没有定义：(1) integration tests 的目录结构；(2) 如何在 CI 中配置 PostgreSQL/Redis/MinIO；(3) integration tests 的运行频率（每次 commit? 每天? 每周?）。Implementation agent 可能将 integration tests 混入 unit tests，导致 CI 时间过长。
- **为什么有问题**: 对于依赖外部服务的 slices (PostgreSQL/Redis/S3)，integration tests 是必要的。但 plan 缺乏具体定义，可能导致 implementation agent 做出不一致的测试策略。
- **直接证据**: plan line 496 和 504 提到 "integration lane"，但没有目录结构和 CI 配置定义。
- **建议改法和验证点**: 在 Plan 9 中增加 "Integration Test Structure" 小节，定义：(1) 目录：`tests/integration/`；(2) 标记：`@pytest.mark.integration`；(3) CI：每日夜间构建或 PR 触发。验证点：检查 integration tests 不在 `pytest -q` 默认运行。
- **修复风险（低）**: 仅需增加结构定义
- **严重程度（低）**: 影响 CI 效率，但不影响正确性

---

### 013-未修复-[低]-Documentation sync 缺乏投资域 README 定义

- **Plan位置**: Slice 0.1-0.2 (line 246-258), Plan 10 (line 509-516)
- **问题类型**: 测试缺口
- **当前写法**: Slice 0.1 allowed files 包括 "dayu/README.md, tests/README.md"；Slice 0.2 allowed files 包括 "README.md, dayu/README.md"
- **反例/失败场景**: Plan 要求更新 README，但没有定义投资域文档的职责边界。例如，`dayu/investment/README.md` 应该写什么？是用户手册还是开发手册？与 `dayu/README.md` 的关系是什么？Implementation agent 可能创建重复或冲突的文档。
- **为什么有问题**: AGENTS.md 定义了严格的 README 职责边界 (line 76-97)。投资域是新增包，需要明确其文档职责，避免与现有 README 冲突。
- **直接证据**: AGENTS.md line 76-97 定义了各 README 的固定职责；plan slice 0.1-0.2 只说 "更新 README"，没有定义投资域文档职责。
- **建议改法和验证点**: 在 Slice 0.1 中增加 "Documentation" 小节，定义：(1) `dayu/investment/README.md` 为开发手册，只写 domain model、storage protocols、service contracts；(2) 用户手册放在根目录 README.md 的 "投资平台" 小节。验证点：检查文档职责不越界。
- **修复风险（低）**: 仅需增加文档定义
- **严重程度（低）**: 影响文档一致性，但不影响功能

---

## Open Questions

1. **Host SQLite 与 PostgreSQL 共存策略**: 现有 Host 继续使用 SQLite，新 investment domain 使用 PostgreSQL，两者通过 Service 层隔离。这个假设是否正确？
2. **Investment domain 与 fins storage 的 locator 映射**: InvestmentLocator 类型的具体定义是什么？如何从 fins storage 的 DocumentHandle 生成？
3. **Claim confidence 验证规则**: 置信度阈值是多少？如何量化？过期 Claim 如何处理？
4. **Optimizer input 的 data_version 定义**: 如何在 schema 层面标记数据版本？
5. **Kill switch 存储位置**: PostgreSQL? Redis? 配置文件? 如何确保双端一致？
6. **Tenant 隔离是否在当前 scope 内**: 如果不在，如何确保 schema 可扩展？
7. **Live broker credentials 存储**: 环境变量? Secret manager? 如何轮换？
8. **Integration tests CI 配置**: 如何在 CI 中配置 PostgreSQL/Redis/MinIO?

## Residual Risks

| Risk | Owner / Destination |
|------|---------------------|
| Investment domain greenfield 工作量被低估 | Implementation agent (Slice 0.1-0.2) |
| PostgreSQL 依赖添加可能导致现有测试失败 | Implementation agent (Slice 1.1) |
| Fins storage 边界模糊可能导致架构违规 | Plan owner (Slice 1.3 + Plan 5) |
| 36 slices 依赖关系不清可能导致集成失败 | Plan owner (增加依赖图) |
| Trust model 边界不清可能导致低质量 Claim 被接受 | Implementation agent (Slice 3.1-3.2) |
| Look-ahead 防护缺乏实现细节可能导致回测错误 | Implementation agent (Slice 5.3-5.4) |
| Kill switch 双端检查缺乏细节可能导致安全漏洞 | Implementation agent (Slice 5.5) |
| 多租户未考虑可能导致未来迁移困难 | Plan owner (声明 scope + residual risk) |
| Redis 降级策略缺乏细节可能导致生产问题 | Implementation agent (Phase 2) |
| Live broker 授权流程不清可能导致 Slice 8.4 阻塞 | User (授权流程) |
| 36 slices 可能过度拆分影响效率 | Plan owner (评估 slice 粒度) |
| Integration tests 结构不清可能导致 CI 问题 | Implementation agent (Plan 9) |
| 文档职责越界可能导致 README 冲突 | Implementation agent (Slice 0.1-0.2) |

## Conclusion

**pass-with-risks**

Plan 整体结构清晰，覆盖了 11 组硬需求和完整的业务闭环。但存在以下 material risks：

1. **Investment domain greenfield 工作量被低估**：plan 措辞暗示增量扩展，但实际需要从零创建。
2. **PostgreSQL/Redis/S3 依赖缺失**：需要在 Phase 1 开头添加依赖并确保兼容性。
3. **Fins storage 边界模糊**：需要明确 locator 类型和跨层访问规则。
4. **36 slices 缺乏依赖图**：需要补充 slice 间的依赖关系，避免集成失败。
5. **Trust model/Look-ahead/Kill switch 细节不足**：需要增加实现机制定义。

这些 risks 不阻塞 plan 的整体方向，但需要在 implementation 前收敛，否则会导致大量返工。建议 plan owner 在 accepted plan commit 前，优先修复 Finding 001-007。

**Open**: 13 findings (0 H, 7 M, 6 L)
