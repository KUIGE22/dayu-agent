# Slice 1.5 workspace import — code review fix round3

- **Work unit**：Investment Platform Restoration
- **日期**：2026-08-11
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Implementation worker**：deepseek-flash（round3 唯一最小 code fix）
- **Controller**：Codex（round3 补充裁决：不清理历史 object，新增 delta 严格为 0；最小 patch 不扩面）
- **触发 review**：`docs/reviews/code-review-20260811-114214.md`（Terra 复审），唯一 finding
  （1-未修复-低，FAIL 0H/0M/1L）：新代码违反 AGENTS 禁止 `object`/`Any`。
- **Adjudication**：
  `docs/reviews/slice-1.5-workspace-import-code-review-adjudication-20260811-codex.md`
- **Round1 fix**：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-20260811-codex.md`
- **Round2 fix**：
  `docs/reviews/slice-1.5-workspace-import-code-review-fix-round2-20260811-codex.md`

## 触发 review（round3）

Terra 复审 `code-review-20260811-114214.md` 提出唯一 finding（1-未修复-低）：

1. **arg_parsing**：`_ImportSemanticStore` 的 `default`/`values`/`value` 声明为
   `object`（arg_parsing.py:300/325/347），import 语义 gate 的核心输入/输出契约
   被宽化；
2. **leaf**：`parse_json_object` 对外返回 `dict[str, object]`
   （_research_artifact_content.py:73），JSON 边界暴露宽类型。

Controller 补充裁决（round3）：不清理历史 `object`（`_sha256_json_object` /
`validate_monitoring_source_map_payload` 等 baseline 既有 payload 契约不纳入本轮）；
新增签名 delta 严格为 0。若 `JsonValue` 的 dict 不变性导致历史调用方扩散，允许更小
方案：leaf 改为 `validate_json_object_text(text) -> str`，reader 分支对同一
immutable text 先 strict 校验、再走历史 owner 原有 `json.loads`；argparse 拆成
两个 Action。选择最小能 pyright 0 的方案立即完成。

## Controller dispositions（round3）

| Observation | Disposition | Closure |
| --- | --- | --- |
| finding 1a：`_ImportSemanticStore` 使用 `object` | **ACCEPTED / FIXED** | 拆为 `_ImportSemanticFlag`（无值开关，`values: Sequence[str] | None`，首次写 `True`）与 `_ImportSemanticValue`（单字符串值，`values: str | Sequence[str] | None`，非 str 一律 `argparse.ArgumentError` fail closed）；共享计数逻辑抽为模块级 `_record_import_semantic_occurrence`；注册与解析语义字节等价（flag `nargs=0, default=False`；value `default=None`）。无 cast/ignore/Any/object。 |
| finding 1b：`parse_json_object` 返回 `dict[str, object]` | **ACCEPTED / FIXED**（Controller 更小方案） | leaf 定义递归 `JsonValue` 别名 + `validate_json_object_text(text: str) -> str`：`parse_float`（`isfinite` 拒绝 `1e400` 溢出为无穷）+ `parse_constant`（拒绝 `NaN`/`Infinity`/`-Infinity` 字面量）+ 顶层必须为 object；校验通过原样返回同一 `text`。三个 reader 分支（helpers/workbook `_load_json_object`、bundle closure）先 `validate_json_object_text` 再对同一 text 走历史 owner 的 `json.loads`，同一文本无 TOCTOU。 |
| 附：`_enumerate_closure_reference_paths(payload: dict[str, object])`（本 Slice 新增签名，delta 扫描发现） | **ACCEPTED / FIXED** | 参数收敛为 `Mapping[str, JsonValue]`（新增签名不再含 object）；closure 以 `json.loads(validate_json_object_text(...))` 结果传入，pyright 通过。 |

## Applied fixes（round3）

1. **dayu/cli/arg_parsing.py**：删除 `_ImportSemanticStore`，新增
   `_record_import_semantic_occurrence`（模块级辅助，首现写值/重复置 repeated
   并递增 seen）与两个精确 action：
   - `_ImportSemanticFlag`：`__call__(values: Sequence[str] | None)`，忽略传入
     值只写 `True`；
   - `_ImportSemanticValue`：`__call__(values: str | Sequence[str] | None)`，
     非 `str` 时 `raise argparse.ArgumentError` fail closed，否则写字符串值。
   三个参数注册保持字节级语义（flag `action=_ImportSemanticFlag, nargs=0,
   default=False`；manifest/tenant `action=_ImportSemanticValue, default=None`）。
2. **dayu/cli/_research_artifact_content.py**：定义 `JsonScalar`/`JsonValue`
   递归类型别名；`parse_json_object` 替换为 `validate_json_object_text(text: str)
   -> str`（`parse_float` + `parse_constant` 运行期严格校验 + 顶层 object 强制，
   通过后原样返回同一 text）；模块 docstring 同步。
3. **dayu/cli/commands/_research_template_bundle.py**：import 改
   `validate_json_object_text` + `JsonValue`；`_enumerate_closure_reference_paths`
   参数 `dict[str, object]` → `Mapping[str, JsonValue]`；closure descriptor
   解析改 `json.loads(validate_json_object_text(decode_utf8_sig(descriptor_bytes)))`
   （原 `(ValueError, UnicodeError)` 捕获语义不变）。
4. **dayu/cli/commands/_research_template_helpers.py** 与
   **dayu/cli/commands/research_workbook.py**：`_load_json_object` reader 分支改
   `json.loads(validate_json_object_text(decode_utf8_sig(content_reader.read_bytes(path))))`，
   历史返回类型 `dict[str, object]` 与普通文件路径分支不变。
5. **测试**：
   - `tests/cli/test_research_template_command.py`：新增
     `TestValidateJsonObjectTextStrict`（合法对象原样返回、`NaN`/`Infinity`/
     `-Infinity` 字面量含嵌套、`1e400` 溢出、顶层非对象、非法 JSON 一律
     `ValueError`）+ `test_closure_reader_rejects_non_standard_json_descriptor`
     （reader 模式 closure 对含 NaN descriptor fail closed）；
   - `tests/cli/test_workspace_migrations.py`：新增 `TestImportSemanticAction`
     （flag/value 首现写值、重复只置 repeated 并递增 seen、非 str 输入
     `ArgumentError` fail closed）。

## 白名单（round3）

- production：`dayu/cli/arg_parsing.py`、`dayu/cli/_research_artifact_content.py`
  （既有 S15-CTRL-03 新增 leaf）、`dayu/cli/commands/_research_template_bundle.py`、
  `dayu/cli/commands/_research_template_helpers.py`、
  `dayu/cli/commands/research_workbook.py`（既有 S15-CTRL-15 透传 allowlist）。
  未触碰 `dayu/cli/commands/init.py`（round2 已验收的 gate 消费端，本轮无需改）；
  未触碰任何历史 payload 契约函数。
- tests：`tests/cli/test_workspace_migrations.py`、
  `tests/cli/test_research_template_command.py`（既有 allowlist）。
- docs：本批 round3 artifact + round1/round2/adjudication/implementation
  的状态更新（本文件）。

## Verification（round3）

- focused：`tests/cli/test_workspace_migrations.py` +
  `tests/cli/test_research_template_command.py` **357 passed**（round3 新增
  12 个：6 JSON adversarial + 1 reader NaN descriptor + 5 parser action）。
- 相关 affected suite：`test_init_command` + `test_arg_parsing_redaction` +
  `test_architecture_boundaries` + `test_storage_split_repositories` +
  `test_service_startup_preparation` **376 passed**；
  `tests/cli` + `tests/investment` + `tests/application` + `tests/fins`
  **4601 passed / 0 failed**。
- coverage（`COVERAGE_CORE=pytrace` + filesystem source 目录 + 独立
  `COVERAGE_FILE`）：`arg_parsing.py` **100%**；`_research_artifact_content.py`
  **100%**（round1 为 94%，adversarial 补齐后 100%）；`_research_template_bundle.py`
  **85%**；`_research_template_core.py` **89%**；`_research_template_helpers.py`
  **86%**；`research_workbook.py` **90%**；`research_template_routing.py` **84%**
  —— 全部 `>=80%`，与实现基线逐文件一致，无回归。
- pyright：修改 9 文件（7 production + 2 tests）**0 errors**。
- Ruff：修改 9 文件默认规则 **All checks passed**；`--select F,I` 仅剩 1 个
  既有 I001（`tests/cli/test_workspace_migrations.py` 中
  `dayu.investment.domain.workspace_import` 导入块的
  `LegacyBundleReference/VerifiedLegacyCompany` 顺序，round2 已登记的未触碰
  import 块遗留），round3 零新增。
- delta=0：相对 baseline `58b7dd28` 全量 `git diff -U0` 扫描，新增生产签名中
  `object`/`Any` = 0：`_ImportSemanticStore` 与 `parse_json_object` 已消除；
  `_enumerate_closure_reference_paths` 收敛为 `Mapping[str, JsonValue]`；diff 中
  其余 `dict[str, object]` 均为 baseline 既有签名重排（逐处核对 `-` 行同型，
  历史/外部依赖不扩大）。
- import smoke（7 个修改 production + init）通过；`git diff --check` 通过。

## Safety properties locked by tests（round3 增量）

- flag action：首次写 `True`/seen=1 无 repeated；重复不覆盖首值、只置
  repeated 并 seen=2；
- value action：首次写字符串；重复保留首值；非字符串输入（list/None）
  `argparse.ArgumentError` fail closed；
- 完整 parser 矩阵（单次/重复主开关、重复 manifest/tenant、plain init 零
  seen）全部保留通过，`run_init_command` 双 gate 语义未触碰；
- strict JSON：顶层非对象、`NaN`/`Infinity`/`-Infinity` 字面量（含嵌套数组/
  对象）、`1e400` 溢出为无穷、非法 JSON 一律 `ValueError`；reader 模式 closure
  对含 NaN 的 descriptor fail closed（`ResearchBundleClosureError`）；
- 同一 immutable text 先 validate 再 `json.loads`，无 TOCTOU；历史
  `_load_json_object` 返回 `dict[str, object]` 契约与普通文件路径 API 未改动。

## Residual Risk

- 未运行 PG16/Docker/live/network/model/broker（本轮无 DB/网络路径改动，
  复用既有 47 passed PG16 证据不重跑）。最终 Terra
  `docs/reviews/code-review-20260811-121322.md` 与 MiM Native
  `docs/reviews/code-review-20260811-121507-slice-1.5-final.md` 均
  PASS/open H/M/L=`0/0/0`；本 round3 finding 已 CLOSED。
