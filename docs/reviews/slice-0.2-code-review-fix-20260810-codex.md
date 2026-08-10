# Slice 0.2 code-review fix artifact

- Work unit：`investment-platform-restoration`
- Gate：code review fix（slice-0.2 code-review -> fix -> re-review）
- Source reviews：
  - Terra：`docs/reviews/code-review-20260810-093200-slice-0.2-terra.md`
  - MiM：`docs/reviews/code-review-20260810-093200-slice-0.2-mimo-native.md`
- Adjudication：`docs/reviews/slice-0.2-code-review-adjudication-20260810-094100-codex.md`
- Plan gap：已关闭（`plan-fix-20260810-slice-0.2-readme-allowlist-codex.md`，
  双路 plan re-review 均 PASS，open H/M/L = 0/0/0）
- Base / predecessor accepted commit：`d5f024d`
- Branch：`codex/investment-platform`
- Fixer：DeepSeek Flash corrective fix worker
- Status：**CLOSED / DUAL RE-REVIEW PASS**
- Artifact path：`docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`

## Scope

在修订后的 Slice 0.2 allowlist 内修复全部 accepted code findings；不得
commit / push / PR，不进入 Slice 1.1。allowlist 见 master plan §Slice 0.2
（含 `dayu/investment/README.md`）。

## Per-finding fix status

| Finding | Disposition | Fix status | Closure |
| --- | --- | --- | --- |
| Terra 001 冷启动循环导入（高） | ACCEPTED | 已修复 | `dayu.startup.platform` 只依赖 `dayu.investment.composition/config` 纯层契约，不再导入 `dayu.services`；`dayu.services.protocols` 改为纯层契约的稳定 re-export；`python -c 'import dayu.startup.platform'` fresh interpreter 通过。 |
| Terra 002 非法 env-name 回显 secret（中） | ACCEPTED | 已修复 | `config.py` env-name 异常只报告字段与固定规则，不再格式化候选值；新增 DSN / object storage / Redis / auth key 四类 secret-shape 输入的异常 redaction 测试与"异常不回显候选值"测试。 |
| Terra 003 启动 admission 迟到（中） | ACCEPTED | 已修复 | `prepare_host_runtime_dependencies()` 把 `load_platform_settings` + `build_platform_composition` 前置到 `resolve_startup_paths` / HostStore schema / Host 构造 / Fins runtime / startup recovery 之前；缺四配置、缺 provider、provider 抛错三类场景分别断言 schema 初始化 / Host 构造 / recovery 副作用计数为零。 |
| Terra 004 + MiM 1/3 任意对象注入（高） | ACCEPTED | 已修复 | 纯 `dayu.investment.composition` 定义非空 `@runtime_checkable PlatformServiceProtocol`（只读 `platform_service_name`）与 `PlatformCompositionProviderProtocol`；`PlatformComposition` TypeVar 绑定该协议，`__post_init__` 校验注册键 / 名称 / 值并以 `MappingProxyType(dict(...))` 防御性快照；任意 str / dict / 无协议值、空 / 仅空白 / 键名不匹配、禁用携带注册一律 fail closed；`build_platform_composition` 对 provider 做非空运行时协议检查，组合契约异常转稳定 `PlatformCompositionError` 且不回显候选值；移除 `PlatformComposition[str]` 正向测试，新增协议边界 fail-closed 测试。 |
| Terra 005 测试 object/cast 逃逸（低） | ACCEPTED | 已修复 | `tests/application/test_service_startup_preparation.py` 移除全部新增 `cast(..., object())` / `object()` 与既有逃逸，改用 `__new__` 未初始化强类型桩 / `dataclasses.replace` 注入 / 精确 fake / Protocol；文件内新增 AST escape guard 自扫描该测试路径。 |
| Terra 006 + MiM 4 包 README 漂移（低） | ACCEPTED / PLAN GAP | 已修复 | `dayu/investment/README.md` 同步当前 `config.py` / `composition.py` owner、真实依赖边界与开发命令；`dayu/README.md` §3.9 同步协议契约真源与 re-export 归属。 |
| MiM 2 重复 validate()（低） | ACCEPTED | 已修复 | 删除 `load_platform_settings` 中构造后的重复 `settings.validate()`，保留 `__post_init__` 单一构造期校验真源。 |
| MiM 5 合法依赖观察 | REJECTED / CLOSED | 无需修复 | 不处理。 |

## Changed files（全部在修订后 allowlist 内）

1. `dayu/investment/composition.py`（改）— 新增 `PlatformServiceProtocol` /
   `PlatformCompositionProviderProtocol` / `PlatformCompositionContractError`，
   `PlatformComposition` 构造期校验 + `MappingProxyType` 快照。
2. `dayu/services/protocols.py`（改）— `PlatformServiceProtocol` 与
   `PlatformCompositionProviderProtocol` 改为纯层契约稳定 re-export，
   加入 `__all__`，删除重复定义。
3. `dayu/startup/platform.py`（改）— 只依赖纯层契约；provider 非空运行时
   协议检查；组合契约异常转 `PlatformCompositionError` 且不泄密；
   provider 自身异常原样传播。
4. `dayu/investment/config.py`（改）— 非法 env-name 异常不格式化候选值；
   删除重复 `settings.validate()`。
5. `dayu/services/startup_preparation.py`（改）— 平台设置/组合构建前置到
   所有 Host / Fins 副作用之前；imports 全部取纯层契约，不再从
   `dayu.services.protocols` 回绕。
6. `tests/investment/test_platform_config.py`（改）— 协议边界 fail-closed
   测试、快照隔离 / 只读测试、secret-shape redaction 测试；移除
   `PlatformComposition[str]`。
7. `tests/application/test_service_startup_preparation.py`（改）— 移除
   object/cast 逃逸；三类 side-effect sentinel 顺序测试；文件内 AST
   escape guard。
8. `dayu/investment/README.md`（改）— 当前 config/composition owner、依赖
   边界与开发命令。
9. `dayu/README.md`（改）— §3.9 协议契约真源 / re-export / 冷导入表述。
10. `docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`（新）—
    本 artifact。
11. `docs/reviews/slice-0.2-code-review-adjudication-20260810-094100-codex.md`
    （改）— 状态更新为 AWAITING DUAL RE-REVIEW。
12. `docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md`
    （改）— 追加 fix round 状态。

## Validation（`.venv` 激活后）

- 聚焦：`tests/investment/test_platform_config.py tests/application/test_service_startup_preparation.py`
  → 66 passed。
- owner：`tests/investment` → 162 passed；含 `test_architecture_boundaries.py`
  AST guard（110 passed）。
- 受影响调用方：`tests/application/test_wechat_main.py`、
  `tests/application/test_entrypoints.py`、
  `tests/engine/test_cli_running_config.py::test_prepare_cli_host_dependencies_runs_unified_startup_recovery`
  → 36 passed。
- SERPER 未设置全量 unit lane：
  `pytest -q --timeout=60 -m "not integration and not slow and not e2e"`
  → **7543 passed, 5 skipped, 9 deselected**，无失败。
- 逐变更 production coverage：`config.py` 100%、`composition.py` 100%、
  `startup/platform.py` 100%、`startup_preparation.py` 86%（缺失 122-124、
  273-299 为既有未覆盖区域：scene preparer 真实体与
  `prepare_host_admin_dependencies` 轻量路径；新增逻辑全覆盖）。
- pyright：变更 production + test 文件 0 errors；全仓 17 errors 与基线
  `d5f024d` 一致（docling/test_web_tools 既有），无新增无扩散。
- Ruff：`--select E4,E7,E9,F,I` 与默认全规则均通过。
- 冷启动：fresh interpreter `import dayu.startup.platform` /
  `dayu.investment.composition` / `dayu.investment.config` /
  `dayu.services.protocols` / `dayu.services.startup_preparation` /
  `dayu.services` / `dayu.web.streamlit_app` 全部成功。
- `git diff --check` 无 whitespace 错误；allowlist 外文件未修改。

## Plan gaps

无新增。既有 plan gap（README allowlist）已由双路 plan re-review 关闭。

## Residual Risks（分类）

| 风险 | 分类 / destination |
| --- | --- |
| `PlatformComposition` 注册键与 `platform_service_name` 一致是冻结契约；未来 provider 若需同服务多注册名需显式演进 | 后续 slice 显式演进，不在本 fix 发明例外 |
| `PlatformServiceProtocol` 目前仅承载 `platform_service_name`；未来 Service 能力扩展需演进该协议 | 后续 slice（1.2 首次真实装配）显式演进 |
| 根 README 未记录平台 env 开关，用户可能不知晓该开关存在 | 1.2 首次真实装配时随 operator workflow 一并补充（assigned to later slice） |

## 未执行的外部动作

- 未 commit / push / 创建 PR；未启动 re-review；未进入 0.3 / 1.1。
- 未修改 plan、source code reviews、plan reviews。
- 未运行 network / live / model / broker。

## Round2 corrective fix 记录（20260810）

- 双路 corrective re-review（Terra
  `code-rereview-20260810-101622-slice-0.2-terra.md`、MiM
  `code-rereview-20260810-101856-slice-0.2-mimo-native.md`）后，Terra 新开
  两项 settings 边界 finding（未知 profile 异常泄密 / 公开构造器运行时
  边界不严格）由 Controller accepted（open H/M/L = 0/2/0）。
- round2 fix 见 `docs/reviews/slice-0.2-corrective-rereview-fix-round2-20260810-codex.md`；
  本 artifact 状态随之推进为
  **REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW**。

## Round3 corrective fix 记录（20260810）

- Terra final review（`code-rereview-20260810-102450-slice-0.2-terra-final.md`）
  复现 round2 后未知 profile 异常仍经 `from error` 保留含候选值的 cause，
  完整 traceback 泄密；Controller round3 disposition accepted（open H/M/L
  = 0/1/0）。
- round3 fix 见 `docs/reviews/slice-0.2-corrective-rereview-fix-round3-20260810-codex.md`；
  状态维持 **REVIEW FIX APPLIED / AWAITING FINAL DUAL RE-REVIEW**。

## Final closure（20260810）

Terra 与 MiM Native 的最终 closure reviews 均 PASS、open H/M/L = **0/0/0**；
本 fix artifact 状态为 **CLOSED / DUAL RE-REVIEW PASS**：

- `docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
- `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`
