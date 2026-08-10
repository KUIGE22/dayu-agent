# Slice 0.2 Platform Settings 与 Composition Contract Implementation

- Work unit：`investment-platform-restoration`
- Slice：`0.2 — Platform settings 与 composition contract`
- Predecessor accepted commit：`d5f024d`
- Branch：`codex/investment-platform`
- Implementer：DeepSeek Flash implementation worker
- Status：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**（一审 fix round 见 §11、
  corrective re-review round2 fix 见 §12、round3 fix 见 §13；未 commit、未 push / PR，
  未进入 0.3 / 1.1）
- Artifact path：`docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md`

## 1. Pre-edit 审计结论

- **Blocking plan gap：无**。0.2 是纯 settings/composition contract slice，allowlist 内全部可实现，
  不需要 future-slice import 或占位 adapter。
- **架构事实**：`tests/investment/test_architecture_boundaries.py` 的 AST guard 扫描
  `dayu.investment/**` 全部文件，禁止导入 `dayu.services` / `dayu.startup` / `dayu.fins`
  等上层包；因此 `config.py` / `composition.py` 必须保持纯依赖，Service Protocol 绑定只能
  发生在 `dayu.services.protocols.py` 与 `dayu.startup.platform.py`。
- **真实 startup 注入点**：`dayu/services/startup_preparation.py::prepare_host_runtime_dependencies()`
  是唯一主装配点（CLI `dayu/cli/dependency_setup.py:515`、WeChat `dayu/wechat/runtime.py:723`、
  Streamlit `dayu/web/streamlit_app.py:93` 共用）；新增可选参数 + 默认禁用组合根即保持现有行为。
- **既有测试直接构造 `PreparedHostRuntimeDependencies` 的两处**（`tests/engine/test_cli_running_config.py:8119`、
  `tests/application/test_wechat_main.py:1050`）在 pyright 全仓扫描中暴露，已通过给新字段
  默认禁用值闭合（见 §3 决策）。

## 2. Scope 与 Non-goals

- 只建立 strict settings、`PlatformCompositionProviderProtocol`、空/禁用状态与 startup 注入点。
- 本 slice 不导入或构造任何尚不存在的 PG / Fins / job repository；无 schema、migration、
  repository、connector、worker、scheduler。
- （初版 pre-erratum 记录）不修改 `dayu/investment/__init__.py`、`dayu/investment/README.md`、
  `tests/README.md`（当时不在 allowlist）；其中 `dayu/investment/README.md` 已由 plan
  erratum（`plan-fix-20260810-slice-0.2-readme-allowlist-codex.md`）加入 Slice 0.2
  allowlist，本 fix round 已同步该 README（见 §11）。
- 根 `README.md` 不做内容变更（见 §6 文档决策）。

## 3. Changed Files（全部在 allowlist 内）

1. `dayu/investment/config.py`（新，纯标准库）— `PlatformDeploymentProfile`、frozen
   `PlatformSettings`、`load_platform_settings(env)`、`PlatformSettingsError(ValueError)`、
   环境变量名称常量（`DAYU_PLATFORM_*`）。
2. `dayu/investment/composition.py`（新，纯标准库）— 泛型组合根
   `PlatformComposition[ServiceProtocolT]`（`enabled` + `services`），`disabled()` / `empty()`
   类方法表达空/禁用状态。
3. `dayu/services/protocols.py`（改）— 新增
   `PlatformCompositionProviderProtocol(BaseServiceProtocol, Protocol)`，
   方法 `provide_services() -> Mapping[str, BaseServiceProtocol]`，加入 `__all__`；
   顺带修正 import 块排序（isort）。
4. `dayu/startup/platform.py`（新）— `build_platform_composition(settings, provider=None)`
   注入点与 `PlatformCompositionError(RuntimeError)`。
5. `dayu/services/startup_preparation.py`（改）— `PreparedHostRuntimeDependencies` 新增
   `platform_composition` 字段（默认禁用组合根）；`prepare_host_runtime_dependencies` 新增
   可选 `platform_provider` 参数，装配期 `load_platform_settings(os.environ)` →
   `build_platform_composition`；顺带归一 import 块（isort，修复 HEAD 既有 I001）。
6. `tests/investment/test_platform_config.py`（新）— 配置校验矩阵 + 组合根状态测试，28 例。
7. `tests/application/test_service_startup_preparation.py`（改）— 共享打桩 helper + 注入点
   直接测试 3 例 + 装配集成测试 3 例，共 8 例通过。
8. `dayu/README.md`（改）— §3.9 investment 章节按当前代码更新（新增 config/composition 与
   注入点描述），§3.5 startup preparation 职责追加一行平台组合根准备。

## 4. 实现决策

- **env-name-only**：`PlatformSettings` 只记录"环境变量名称已配置"这一事实（字段存环境变量名，
  不存在时 `None`），任何情况下都不持有/回显 secret 值；`load_platform_settings` 只做存在性
  检查，绝不读取并保留取值。
- **fail-fast 规则**（`PlatformSettings.__post_init__` → `validate()`）：
  - production 启用：四个基础设施环境变量名称（DSN / object / redis / auth key）任一缺失即抛
    `PlatformSettingsError`，且禁止 `use_in_memory_adapters=True`；
  - development 启用：必须显式 `use_in_memory_adapters=True`，且禁止配置任何 production
    基础设施环境变量（防止误连真实持久化设施）；
  - 平台禁用：不要求任何基础设施，但仍校验已配置名称的 env-name 形态
    （`[A-Z][A-Z0-9_]*`）；
  - 环境变量值非法布尔、未知 profile 一律 fail closed；未指定 profile 默认 development。
- **协议归属**：`PlatformCompositionProviderProtocol` 定义在 `dayu.services.protocols` 并继承
  `BaseServiceProtocol`——provider 本身即是 Service Protocol，满足"组合根只能接收/暴露
  Service Protocol"；本 slice 只定义契约，无任何实现。
- **组合根归属**：`PlatformComposition` 定义在 `dayu.investment.composition`（纯层），以协变
  TypeVar 承载 Service 协议类型；绑定到 `BaseServiceProtocol` 发生在依赖方向合法的
  `dayu.startup.platform` / `dayu.services.startup_preparation`，不构成反向依赖。
- **fail-fast 注入**：`build_platform_composition` 在 `settings.enabled=True` 且
  `provider is None` 时抛 `PlatformCompositionError`；禁用时返回 `disabled()` 组合根且不触碰
  provider。
- **默认禁用值**：`PreparedHostRuntimeDependencies.platform_composition` 用
  `field(default_factory=_default_platform_composition)` 默认禁用组合根。语义为"未显式装配
  平台组合 = 平台禁用"，与空/禁用状态契约一致；同时闭合两处既有测试的直接构造（非兼容 hack）。

## 5. Implemented plan items（对应计划文本）

| 计划文本 | 实现 |
| --- | --- |
| "配置只记录 env name，不回显 secret" | `PlatformSettings` 全字段仅记录环境变量名称 |
| "production 缺 DSN/object/redis/auth key fail-fast" | `_validate_production()` 四字段缺失即抛错 |
| "dev 可显式使用 in-memory adapters" | development 启用必须显式 `use_in_memory_adapters=True` |
| "建立 strict settings、`PlatformCompositionProviderProtocol`、空/禁用状态和 startup 注入点" | `config.py` + `protocols.py` + `composition.py` + `startup/platform.py` |
| "本 slice 不导入或构造尚不存在的 PG/Fins/job repository" | 无任何相关 import / 构造 |
| "启用 platform 但未注入 provider 时 fail-fast" | `build_platform_composition` 抛 `PlatformCompositionError` |
| "组合根只能接收/暴露 Service Protocol" | 组合根只持 `Mapping[str, ServiceProtocolT]`；绑定到 `BaseServiceProtocol` 在 startup 层完成 |

## 6. 文档决策

- `dayu/README.md`：§3.9 更新为当前实现（domain + config + composition + 注入点），§3.5 追加
  平台组合根准备职责。未写未来设计。
- 根 `README.md`：无内容变更。平台尚未具备任何用户可用能力（无 provider、无持久化），按
  AGENTS.md"以代码为准、不写未来设计"原则，不在用户手册记录尚未可运维的 env 开关；该决策
  留待 1.2 首次真实装配 slice 再补。
- （初版 pre-erratum 记录）`dayu/investment/README.md` / `tests/README.md`：当时不在本
  slice allowlist，未修改；`dayu/investment/README.md` 已由 plan erratum 加入 allowlist，
  fix round 已按当前实现同步（见 §11），`tests/README.md` 仍不在 allowlist。

## 7. Validation（全部在 `/Users/wsk/workspace/dayu-agent`、激活 `.venv` 后执行）

1. `python -m pytest tests/investment tests/application/test_service_startup_preparation.py -q`
   → `146 passed`
2. 全仓 unit lane `python -m pytest -q --timeout=60 -m "not integration and not slow and not e2e"`
   → `7512 passed, 5 skipped, 9 deselected`，1 个失败
   `tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key`，**HEAD 基线复跑
   同样失败**（本地代理 127.0.0.1:7897 不可达的 ProxyError），与本改动无关。
3. 受影响调用方：`tests/application/test_wechat_main.py` + `test_entrypoints.py` → 35 passed；
   `test_cli_running_config.py::test_prepare_cli_host_dependencies_runs_unified_startup_recovery`
   → 1 passed。
4. 逐变更 production coverage（`--cov-report=term-missing`）：
   - `dayu/investment/config.py`：`100%`（78 stmts）
   - `dayu/investment/composition.py`：`100%`（16 stmts）
   - `dayu/startup/platform.py`：`100%`（12 stmts）
   - `dayu/services/startup_preparation.py`：`86%`（缺失 100-102、246-272，均为既有未覆盖
     区域：scene preparer 真实体与 `prepare_host_admin_dependencies` 轻量路径；新增逻辑全覆盖）
   - `dayu/services/protocols.py`：纯协议文件，方法体仅 `...`，无可执行语句可测。
5. `pyright`（全仓）：`17 errors`，与基线 `d5f024d` 一致，无新增无扩散；所有新增/修改文件
   单独 `pyright` 均 `0 errors, 0 warnings, 0 informations`。
6. `ruff check --select E4,E7,E9,F,I <7 个变更 python 路径>` → `All checks passed!`
7. `ruff check <7 个变更 python 路径>`（默认全规则）→ `All checks passed!`
8. `git diff --check` → 无 whitespace 错误。
9. Final newline audit（全部新增/修改文件）→ 全部以换行结尾。
10. 说明：`--cov=dayu.services.startup_preparation` 经 pytest-cov 与 tests/application
    conftest 组合在 HEAD 基线同样触发 numpy/pandas ImportError（既有工具链怪癖），故该模块
    覆盖率改用 `python -m coverage run -m pytest` 测得（§7.4）。

## 8. Plan gaps

无。pre-edit inventory / callgraph / owner / signature / fixture 审计未发现计划与仓库事实的
偏差；全部 allowlist 文件已按计划意图实现。

## 9. Residual Risks（分类）

| 风险 | 分类 / destination |
| --- | --- |
| `PlatformComposition` 泛型容器在投资包内、绑定在 startup 层，未来如有其他消费者需重复绑定 | 覆盖于后续 slice（1.2 首次真实装配使用同一注入点）；如 review 要求收窄请回 controller |
| `PlatformSettings` 的 development/production 规则是 0.2 冻结契约，未来若需本地 PG dev 模式需显式演进 | 后续 slice 显式演进，不在本 slice 发明例外 |
| 根 README 未记录平台 env 开关，用户可能不知晓该开关存在 | 1.2 首次真实装配时随 operator workflow 一并补充（assigned to later slice） |
| 环境布尔开关接受 `1/true/yes/on`，非法值 fail closed | 已固定；无 owner 变更 |

## 10. 未执行的外部动作

- 未 commit / push / 创建 PR；未启动 review；未进入 0.3 / 1.1。
- 未运行 network / live / model / broker，未启动 PostgreSQL / Redis / MinIO，未触碰
  workspace 数据。
- 未修改 allowlist 之外的模块、依赖文件或 schema。

## 11. Fix-round 状态更新（20260810）

- 一审 code review 后进入 fix round：`docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`。
- 状态：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。
- fix round 主要修订（相对本 artifact §3-§7）：
  1. `dayu.investment.composition` 内移入非空 `PlatformServiceProtocol` /
     `PlatformCompositionProviderProtocol`，组合根构造期校验 + 防御性快照；
  2. `dayu.services.protocols` 只做稳定 re-export；`dayu.startup.platform`
     只依赖纯层契约，冷启动导入修复；
  3. `config.py` env-name 异常不格式化候选值、删除重复 validate；
  4. `prepare_host_runtime_dependencies` 平台设置/组合构建前置到全部
     Host / Fins 副作用之前；
  5. 测试移除 object/cast 逃逸并新增 side-effect sentinel / redaction /
     escape guard 覆盖。
- 未 commit / push / PR；未进入 0.3 / 1.1。

## 12. Corrective re-review round2 fix 状态更新（20260810）

- 双路 corrective re-review 后进入 round2 fix：
  `docs/reviews/slice-0.2-corrective-rereview-fix-round2-20260810-codex.md`。
- 状态：**REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW**。
- round2 主要修订（Terra 两项 accepted 中 finding，open H/M/L = 0/2/0）：
  1. `load_platform_settings()` 未知 profile 异常只写 `DAYU_PLATFORM_PROFILE`
     与固定允许值（development / production），不再格式化候选值；
  2. `PlatformSettings.validate()` 单一边界新增 `_validate_field_types()`：
     `enabled` / `use_in_memory_adapters` 精确 `bool`、`profile` 为
     `PlatformDeploymentProfile`、四个基础设施字段为 `str | None` 后才做
     regex；所有失败消息稳定且不回显候选值；
  3. 新增 profile secret-shape redaction 与公开构造器反例测试
     （`enabled=1` / `"yes"` / 未知字符串 profile / 非字符串 env-name）。
- 未 commit / push / PR；未进入 0.3 / 1.1。

## 13. Round3 corrective fix 状态更新（20260810）

- final corrective re-review 后进入 round3 fix：
  `docs/reviews/slice-0.2-corrective-rereview-fix-round3-20260810-codex.md`。
- 状态：**REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW**。
- round3 主要修订（Terra final 唯一 accepted finding，open H/M/L = 0/1/0）：
  1. `load_platform_settings()` 未知 profile 异常改为 `raise ... from None`，
     不再把含候选值的 `ValueError` 保留为 `__cause__`，完整 traceback 不再泄密；
  2. 3 个 profile secret-shape 测试扩展断言 `str(error)` 无候选、
     `error.__cause__ is None`、`traceback.format_exception` 全文本无候选。
- 未 commit / push / PR；未进入 0.3 / 1.1。

## 14. Final dual re-review closure（20260810）

- Terra：`docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
  → PASS，open H/M/L = 0/0/0。
- MiM Native：
  `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`
  → PASS，open H/M/L = 0/0/0。
- 全部 findings 均 CLOSED；无需继续修改 production / tests / README / plan。
- 当前状态为 **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**；仍未 push / PR / live。
