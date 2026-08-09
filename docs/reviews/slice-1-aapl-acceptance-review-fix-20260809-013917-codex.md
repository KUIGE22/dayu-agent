# Slice 1 AAPL acceptance review fix

- Status: **CLOSED / DUAL RE-REVIEW PASS**
- Adjudication: `docs/reviews/slice-1-aapl-acceptance-review-adjudication-20260809-013917-codex.md`
- Source reviews: `code-review-20260809-090514.md`, `code-review-20260809-091934.md`
- Re-reviews: `code-review-20260809-094216.md`, `code-review-20260809-094218.md`
- No live/external/model calls; no commit/push/PR; no Slice 2/3 implementation

## Applied changes

1. 新增单一固定 `REQUIRED_RESEARCH_ARTIFACTS` contract；contract/plan parsing 把等价集合规范化为固定顺序，非精确集合拒绝。`inspect_research_artifacts` 在 root 读取和语义下标前重复保护，missing/renamed semantic artifact 均只抛 `ContractError`，不泄漏 `KeyError`。
2. valuation reference 逐行只做一次 `strip()`，命中与 payload slicing 共享 normalized 字符串。
3. 13 文件 inventory 完整后，所有 `.json` artifact 先由 `load_json_file` + strict owner mapping 预载；workbook、monitoring、status snapshots 复用同一 payload。bundle/monitoring path-only owner API 仍需由 owner 内部读取，但在调用前 strict preflight 已完成。
4. owner validator 的五个宽返回序列化点均以 `allow_nan=False` 约束，并将 `TypeError`/`ValueError` 归一化为带稳定 label 的 `ContractError`；最终 receipt sensitive-shape 自检未弱化。
5. source-list 和 topic 使用 case-insensitive exact aliases，且只接受唯一匹配；当前五个中英/双语 fixture 标题保持兼容，诱饵、重复或合并标题 fail closed。
6. portability test 从 `research-template.manifest.json.templates[technology].template_file` 和 monitoring rules `source_template_file` 读取主机实际绝对路径；逐字段证明 receipt 不含路径且生产字节 byte-identical。
7. 新增 missing required field 精确错误测试，以及 fixed-13 missing/renamed、indented valid/mismatch、NaN artifact、combined/decoy heading、non-JSON owner result 测试。

## Validation evidence

| Command | Exit | Evidence |
|---|---:|---|
| `uv run python -m pytest tests/test_investment_agent_acceptance.py -q` | 0 | `46 passed` |
| focused pytest + exact coverage | 0 | contracts `799 statements / 94 miss / 88%`；evaluator `856 statements / 115 miss / 87%`；total `87%`；`46 passed` |
| related research owner tests | 0 | `128 passed, 88 deselected` |
| source-list/execution-summary/write-service owner tests | 0 | `54 passed` |
| exact `pyright` for two utils + focused test | 0 | `0 errors, 0 warnings, 0 informations` |
| Ruff default | 0 | all checks passed |
| Ruff `F,I` | 0 | all checks passed |
| key full-rule production audit (`C416,C901,E501,FBT,PERF401,PLR0912,PLR0913,PLR0915,PLR2004,RUF022,TC001`) | 0 | all checks passed |
| AST class/function docstring audit（两 utils + focused test） | 0 | all class/function docstrings contain `Args`/`Returns`/`Raises` |
| forbidden escape `rg` audit | 1（无匹配是预期） | production modules 无禁用 escape |
| tracked diff-check + six owned-file trailing-whitespace audit | 0 / 1（无匹配是预期） | 无 whitespace error |

## Safety and scope audit

- Production modules仍无 `Any`、`object`、`cast`、`type: ignore`、`getattr`、`hasattr` 或 `noqa` 逃逸。
- evaluator 无 subprocess、网络、模型、stdout 或生产 artifact 写入；测试写入仅限 pytest 隔离目录。
- fixture、`dayu/`、README、tests/README 与 Slice 2+ production 文件未修改。
- 两份 source review artifacts 是 review 输入，不由本 fix 改写。
- `git status --short` 中两份 source review 仍为原有 untracked review 输入；本轮自有变更只涉及两个 utils、focused test、原 implementation artifact 和两份新 adjudication/fix artifacts。

## Dual re-review result

- MiMo：**PASS / ACCEPT**，open `H0/M0/L0`。
- DeepSeek：overall **PASS**；其 `M2/L1` observations 均由 Controller **REJECT/CLOSED non-defect**：固定 AAPL/technology 内部 filename literal 不需要 generic registry；固定四段 evidence 属已接受 contract，未来 schema evolution 作为 residual；`.md` 非 JSON，且所有 `.json` 已在 path-only owner 调用前 strict preflight，已知 owner boundary limitation 无当前绕过。
- Controller closure 后，本 Slice open finding 为 `H0/M0/L0`。
- DS2/MiMo2 仍归 Slice 2 runner 与 Slice 3 partial receipt integration/recovery；DS3 仍归 Slice 2 verify mode/preflight deterministic/live plan binding。fixture IDs 有意不同，不增加相等要求。

## Handoff

F1–F7 已应用并在最新树验证。所有初审及复审 findings/observations 的 accepted/rejected/deferred/duplicate disposition 见 adjudication artifact。当前状态为 **CLOSED / DUAL RE-REVIEW PASS**；仅 Controller 可创建 accepted commit。implementation worker 未 commit/push/PR，也未进入 Slice 2。
