# Slice 0.2 code-review adjudication

- Branch：`codex/investment-platform`
- Base / predecessor accepted commit：`d5f024d`
- Terra review：`docs/reviews/code-review-20260810-093200-slice-0.2-terra.md`
- MiM review：`docs/reviews/code-review-20260810-093200-slice-0.2-mimo-native.md`
- Implementation：`docs/reviews/slice-0.2-platform-settings-composition-implementation-20260810-deepseek.md`
- Status：**CLOSED / DUAL RE-REVIEW PASS**

## Controller dispositions

| Finding | Disposition | Required closure |
| --- | --- | --- |
| Terra 001 cold-import cycle | **ACCEPTED / HIGH** | `python -c 'import dayu.startup.platform'` 必须在 fresh interpreter 成功；稳定 owner 不得依赖 import order，也不得用 function-local lazy import 掩盖循环。 |
| Terra 002 invalid env-name secret echo | **ACCEPTED / MEDIUM** | 所有非法 env-name 异常只报告字段与固定规则，不格式化候选值；补 DSN/auth/object/redis secret-shaped 输入的异常 redaction 测试。 |
| Terra 003 late startup admission | **ACCEPTED / MEDIUM** | settings/provider admission 必须在 HostStore schema、Host 构造、Fins runtime 与 startup recovery 等副作用之前；缺配置、缺 provider、provider 抛错分别证明副作用计数为零。 |
| Terra 004 + MiM 1/3 arbitrary service object | **ACCEPTED / HIGH** | 空的 `BaseServiceProtocol` 不能作为 runtime guard。定义非空、runtime-checkable 的 platform-exposed Service Protocol，并让纯 composition contract、provider 返回值、startup binding 与 tests 共用这一真源；任意 string/dict/裸值、键名不匹配与非协议对象必须 fail closed。不得新增 `Any/object/cast/ignore`。 |
| Terra 005 test type escapes | **ACCEPTED / LOW** | 新增 startup tests 移除本轮引入的 `object` / `cast`，改为精确 fake / Protocol；把 escape AST guard 扩到该变更测试路径。 |
| Terra 006 + MiM 4 package README drift | **ACCEPTED / LOW / PLAN GAP** | master plan §9 要求 `dayu/investment/README.md` 同步 composition，但 Slice 0.2 allowlist 漏列该文件。先完成最小 plan erratum 与双路 plan re-review，再在 code fix 中同步当前 owner/依赖/命令。 |
| MiM 2 duplicate `validate()` | **ACCEPTED / LOW** | 删除 `PlatformSettings.__post_init__` 之后的重复显式 `settings.validate()`，保持单一构造期校验真源。 |
| MiM 5 legal dependency observation | **REJECTED / NON-FINDING / CLOSED** | `dayu.services -> dayu.investment` 是向纯低层 contract 的合法依赖；真实循环来自 `startup.platform -> services package initializer -> startup_preparation`，已由 Terra 001 单独接受。 |

## Controller design boundary

- 不采用 MiM 建议的 `isinstance(value, BaseServiceProtocol)`：该 Protocol 为零成员，
  任意值都会结构性通过，不能关闭 finding。
- 最小可靠方向是在纯 `dayu.investment.composition` 中定义非空
  `PlatformServiceProtocol` 与 provider contract；`dayu.services.protocols` 只做稳定
  re-export / 服务层入口，`dayu.startup.platform` 直接依赖纯 contract，从而同时消除
  cold-import cycle 与任意对象注入。具体签名由 code fix 在 accepted plan 范围内闭合，
  不导入 future repository 或 placeholder adapter。
- `PlatformComposition` 应对 service registry 做 defensive snapshot；frozen dataclass
  不等于其内部可变 mapping 自动冻结。
- 当前代码/tests/README WIP 在 plan-fix/re-review 期间冻结；冻结 diff SHA-256：
  `878e17b19982f092c3e6dff50af8065ad43236d2240cf6fefc2367c65653d2d4`。

## Current open count

合并重复项后 open H/M/L = **2/2/3**。必须先关闭 plan gap，再进入 code fix；
不得 commit / push / PR，也不得开始 Slice 1.1。

## Plan-gap closure

README allowlist erratum 已由 Terra
`plan-review-20260810-094300-slice-0.2-terra.md` 与 MiM
`plan-review-20260810-094300-slice-0.2-mimo-native.md` 独立复审通过；两路 open
H/M/L 均为 `0/0/0`。master plan 已恢复 `ACCEPTED / DUAL PLAN RE-REVIEW PASS`。
现授权 implementation worker 在修订后的 Slice 0.2 allowlist 内修复本 artifact 的
全部代码 findings；code finding open H/M/L 仍为 **2/2/3**，不得直接标记 PASS。

## Code-fix round 状态更新（20260810）

- Fix artifact：`docs/reviews/slice-0.2-code-review-fix-20260810-codex.md`
- 状态：**CODE FIX APPLIED / AWAITING DUAL RE-REVIEW**
- accepted findings 全部按 fix artifact per-finding 表处理；MiM 5 为
  rejected，无需修复。
- 未 commit / push / PR；不得开始 Slice 1.1，直到双路 corrective
  re-review 通过 open H/M/L 归零并创建 accepted local commit。

## Final closure（20260810）

最终 Terra 与 MiM Native closure reviews 均 PASS，open H/M/L = **0/0/0**：

- `docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
- `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`

本 artifact 的全部 accepted findings 及后续 corrective findings 均 CLOSED。
