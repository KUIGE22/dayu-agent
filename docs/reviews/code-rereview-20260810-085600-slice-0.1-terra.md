# Code Re-Review — Slice 0.1 Round2 Final Corrective

## Scope

- Mode: current changes（Slice 0.1 round2 最终独立 corrective re-review，只读）
- Branch: `codex/investment-platform`
- Base: `884a3e4`（Slice 0.1 predecessor accepted commit）
- Review clock: `2026-08-10 08:53:28 +0800`
- Output file: `docs/reviews/code-rereview-20260810-085600-slice-0.1-terra.md`
- Included scope: 根 `AGENTS.md` / `CLAUDE.md`；accepted plan 的 Slice 0.1；两份 `075628` source review、两份 `083133` re-review、Controller adjudication、round1/round2 fix 与 implementation artifact；`dayu/investment/**`、`tests/investment/**`、`dayu/investment/README.md`、`dayu/README.md`、`tests/README.md`。
- Excluded scope: 未修改的既有生产模块；认证 Principal producer、repository/RLS 与外部集成（accepted plan 明确属于后续授权/存储边界）。
- Parallel review coverage: 无；按本次独立复审约束单独走读。

## Findings

未发现实质性问题。

## Terra 083133 专项复核

1. `TenantScope` 的真实私有 singleton 路径已防御性拒绝原始字符串：`identifiers.py:302-305` 先以对象身份检查 `_TENANT_SCOPE_TOKEN`，再以 `isinstance(tenant_id, TenantId)` 拒绝 raw `str`。测试 `test_tenant_scope_rejects_raw_string_tenant_even_with_real_sentinel`（`tests/investment/test_architecture_boundaries.py:620-640`）以真实单例精确覆盖该分支；无 token、伪 token、创建后改写分别由 `:559-617` 覆盖。合法 `TenantId` 加真实单例的对照用例位于 `:643-660`。
2. 文档与代码没有把 Python 私有名误作认证/provenance/security capability。模块文档（`identifiers.py:15-17`）、`Principal` 文档（`:212-213`）、私有 token 文档（`:256-260`）、`TenantScope.__init__` 文档（`:285-299`）和 package README（`dayu/investment/README.md:41-44`）均明确：哨兵仅为 public API misuse guard；当前 `Principal` 是公开构造器；认证层作为唯一 producer、repository/RLS 的租户隔离均是后续边界。
3. README 的 AST guard 说明与实现相符：`dayu/investment/README.md:21-24` 明确只扫描 `dayu.investment` 包内文件、不构成跨包反向 import 检查；实现 `_INVESTMENT_SRC` 与 `_iter_investment_files()` 位于测试文件 `:64-65, :91-104`，实际扫描范围一致。
4. semantic-naive UTC 已关闭：`money.py:256-274` 同时要求 `tzinfo` 与 `utcoffset()` 非空；`parse_utc()` / `to_utc_iso()` 在 `:277-313` 统一使用该守卫。custom `tzinfo` 的回归测试在 `test_to_utc_iso_rejects_semantic_naive_datetime`（测试 `:1124-1139`）。

## Verification

| 检查 | 结果 |
| --- | --- |
| `python -m pytest -p no:cacheprovider tests/investment -q` | PASS — 110 passed |
| coverage | PASS — 4 个 production module 均 100%（137 statements，0 missed） |
| `pyright dayu/investment tests/investment` | PASS — 0 errors, 0 warnings, 0 informations |
| `pyright` | Slice 无新增/扩散；命令仍报告既有 17 errors，均在 `dayu/engine/processors/docling_processor.py` 与既有 engine tests，未触及本 Slice |
| `ruff check --select E4,E7,E9,F,I dayu/investment tests/investment` | PASS |
| `ruff check dayu/investment tests/investment` | PASS |
| `git diff --check` / cached check | PASS — 无 whitespace 错误 |
| 直接构造、forged token、frozen、semantic-naive UTC | PASS — 对应负例与对照用例均已执行 |

## Open Questions

- 无。

## Residual Risk

- 私有 token 不能阻止同一进程解析真实单例；当前代码和文档已准确把它限制为 API misuse guard。认证产生 `Principal`、repository 显式 scope predicate 与 PostgreSQL RLS 的真正租户隔离尚未落地，且不应被误报为 Slice 0.1 缺陷。
- `parse_utc()` 的 `utcoffset() is None` 路径对 ISO 字符串解析结果不可达；保留共享守卫可避免与 `to_utc_iso()` 的语义漂移。
- 全仓 pyright 的 17 项既有诊断不在本次变更路径，仍需由其所属模块单独处理。

## Conclusion

**PASS** — open findings: **高 0 / 中 0 / 低 0**。

Terra 083133 的两项 corrective finding 均已按 Controller disposition 关闭；未将 Python 私有 token 误判为认证，也未要求 Slice 0.1 提前实现认证或 RLS。
