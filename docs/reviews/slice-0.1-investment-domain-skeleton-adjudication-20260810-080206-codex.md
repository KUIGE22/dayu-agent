# Slice 0.1 code-review adjudication

- **Base**：`884a3e4`
- **Branch**：`codex/investment-platform`
- **Terra review**：`docs/reviews/code-review-20260810-075628-slice-0.1-terra.md`
- **MiM review**：`docs/reviews/code-review-20260810-075628-slice-0.1-mimo-native.md`
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**

## Controller dispositions

| Finding | Disposition | Required closure |
| --- | --- | --- |
| Terra F-01 / MiM M-01 identifier and scope bypass | ACCEPTED / HIGH | 保留静态distinct identifier typing，但公开runtime constructor必须校验；`TenantScope`不得通过公开dataclass initializer从任意string/identifier创建，只能由已校验Principal的受控路径产生。补direct empty/whitespace/valid other-tenant、raw str和factory/provenance测试。 |
| Terra F-02 semantic-naive timezone | ACCEPTED / HIGH | `parse_utc`与`to_utc_iso`同时检查`tzinfo is None or utcoffset() is None`；custom tzinfo反例必须拒绝，不得依赖本机时区。 |
| Terra F-03 test type escapes/docstrings | ACCEPTED-IN-PART / LOW | 本次handoff明确覆盖test helper；移除新增测试中的`object`、`type: ignore`、`getattr`、`hasattr`，用精确union/Protocol/AST分支表达；新增/修改测试函数补完整中文Args/Returns/Raises。守护说明必须与实际扫描范围一致。 |
| Terra F-04 README future claims | ACCEPTED / LOW | investment README只描述当前Slice 0.1已落地domain与guard范围；删除future modules/未来补充承诺，后续slice实现后再更新。 |

## Controller constraints

- 不能把`NewType + factory`文档约定当成安全修复；repository/RLS边界不能依赖调用者自律。
- 不修改accepted plan、allowlist外代码或既有review source；可更新implementation artifact并新增review-fix artifact。
- focused tests、逐production module coverage、exact Pyright、Ruff、diff/whitespace/allowed-path必须全部重跑。
- 修复后状态为`REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW`，不能自行标记PASS或commit。

## Round2 corrective adjudication（Terra re-review 20260810-083133）

| Finding | Disposition | Required closure |
| --- | --- | --- |
| Terra F1（中）：TenantScope 私有哨兵不能证明唯一 Principal 路径，且仍可把原始租户值写入 scope | ACCEPTED | `TenantScope.__init__` 即使携带模块内部真实单例，也必须防御性要求 `tenant_id` 是 `TenantId` 实例，raw str fail closed；删除所有“模块私有 token 不可获得 / 无法绕过认证 / 唯一安全 producer”的不实表述，明确哨兵仅为 public API misuse guard，不是认证能力；`Principal` 唯一 producer 与 repository/RLS enforcement 属于对应后续授权 slice。不得把 Python 私有名伪装成 security capability。 |
| Terra F2（低）：investment README 仍含未来 slice 叙述并声称不存在的反向依赖 guard | ACCEPTED | README 只陈述当前事实；反向 import guard 描述必须精确匹配 AST guard 只扫描 `dayu/investment` 包内文件的实际范围；“属于后续 slice”改为“当前模块不实现账本分录或费用分摊规则”。 |

Round2 补测要求：导入真实 private singleton 不是公开契约，但可在同模块/测试允许边界精确证明 raw str 仍被 `TenantId` 类型检查拒绝；保留公开直构 / 伪 token / frozen 测试。

Round2 状态：`REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW`；fix artifact 为
`slice-0.1-investment-domain-skeleton-review-fix-round2-20260810-084327-deepseek.md`。
不 commit / push / PR；不进 Slice 0.2。

## Final closure

- Terra final corrective re-review：
  `docs/reviews/code-rereview-20260810-085600-slice-0.1-terra.md`，
  PASS，open H/M/L = `0/0/0`。
- MiM final corrective re-review：
  `docs/reviews/code-rereview-20260810-085202-slice-0.1-mimo-native.md`，
  PASS，open H/M/L = `0/0/0`。
- 初审与 corrective review 的全部 accepted findings 均为 **CLOSED**；
  Controller 当前 open H/M/L = `0/0/0`，无需继续修改 production、tests、
  README 或 plan。
- Python 私有哨兵只作为 API misuse guard；认证 producer 与 repository/RLS
  enforcement 仍由已接受总计划中的对应后续 slice 承担，不构成本 slice
  的开放 finding。
