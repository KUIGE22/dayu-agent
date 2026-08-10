# Plan Review — Slice 1.1 Doc-owner Erratum（Terra）

## 审查范围

- 审查时间：2026-08-10 12:02 CST（本机系统时钟）。
- 只读审查：
  - `docs/plans/2026-08-10-investment-platform-restoration.md` 最新 Slice 1.1 的 S11-CTRL-08；
  - `docs/reviews/plan-fix-20260810-slice-1.1-doc-owner-codex.md`。
- 以项目 `AGENTS.md` 定义的 README 职责为真源，核对 `dayu/README.md` 与 `tests/README.md` 的 allowlist 增量是否最小且足以闭合 package/test 文档 gate。
- 现有 implementation WIP 仅作为冻结边界，不读取、不修改、不运行；本轮未修改 plan、代码、测试或既有文件。

## 核对的假设与证据

| 假设 | 结论 | 直接证据 |
| --- | --- | --- |
| `dayu/README.md` 是应同步 package owner/阅读顺序的文档 | 通过 | `AGENTS.md` 将其职责限定为开发手册总览、整体架构、稳定边界、扩展入口与代码阅读顺序。现有 §3.9 仍将 `dayu.investment` 描述为仅含 `domain/config/composition` 三个纯模块，并宣称三者均不导入 ORM；这与本 Slice 已接受的 `storage` SQL infra 冲突。S11-CTRL-08 只要求校正 owner 图、pure/storage 依赖边界以及 Alembic/13 表/RLS 的阅读顺序，符合该 README 的职责。 |
| `tests/README.md` 是应同步测试 lane/维护规则的文档 | 通过 | `AGENTS.md` 将其职责限定为测试分层、运行方式、约定与维护规则。现有 investment 段仍把全包写为不得导入 ORM，且没有 Slice 1.1 unit/真实 PG16 integration lane。S11-CTRL-08 只要求改为基于相对路径的 pure/storage guard，并登记两条 migration 测试 lane、禁止 SQLite/fake 与 Docker owner cleanup，均属于测试手册职责。 |
| allowlist 增量最小 | 通过 | Controller disposition 明确本勘误只增加上述两份 README。`dayu/investment/README.md` 和根 `README.md` 原已在 Slice 1.1 allowlist；S11-CTRL-08 不授权修改其他 package/test 历史、代码、migration 或 live/data/model/broker 状态。 |
| allowlist 足以闭合文档真源 | 通过 | `dayu/README.md` 承担跨 package 的 owner/阅读顺序，`dayu/investment/README.md`（原 allowlist）承接包内依赖真源；`tests/README.md` 承担 unit/integration 分层与运行维护。三者覆盖不同层级，S11-CTRL-08 对新增两者给出了精确同步内容，未留下需要另一份 README 才能完成的 package/test 文档契约。 |
| 实现冻结边界明确 | 通过 | disposition 指定仅最小 doc erratum，production/tests/migration 不变；任一 dual re-review 有 open H/M/L 时 implementation 继续冻结，且不得启动 code review。 |

## Findings

无。S11-CTRL-08 的两项新增 allowlist 同时满足最小性和充分性：前者纠正开发手册总览中的架构/阅读顺序真源，后者纠正测试手册中的 guard 与真实 integration lane 真源；没有授权与本次文档漂移无关的文件。

## Open Questions

无。

## Residual Risks

- 本结论只确认计划边界可实施。后续实际文档编辑仍须准确反映已验收的 Slice 1.1 状态，不能将 future slice 或 live/data/model/broker 标记为已实现。
- implementation WIP 及其后续代码审查不属于本次 doc-owner erratum；应按 Controller 的冻结/解冻 gate 单独验证。

## 结论

**PASS**（open H/M/L：**0 / 0 / 0**）。

`dayu/README.md` 与 `tests/README.md` 的 allowlist 增量为最小且充分的 package/test 文档真源修正；S11-CTRL-08 可进入既定的后续文档同步与 review gate。
