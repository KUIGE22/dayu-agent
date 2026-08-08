# Slice 2B write artifact caller 迁移实现记录

- **日期**: 2026-08-07
- **基线**: `ba8b83e` (`gateflow: accept write artifact callers slice 2a`)
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT
- **范围**: Slice 2B Cohort B 9 个生产文件及其直接测试入口

## 允许与实际修改路径

生产代码：

- `dayu/services/write_model_configuration_application.py`
- `dayu/services/write_model_configuration_rollback_application.py`
- `dayu/services/write_model_configuration_manual_recovery.py`
- `dayu/services/write_model_configuration_manual_recovery_application.py`
- `dayu/services/write_model_configuration_manual_recovery_clearance.py`
- `dayu/services/write_model_configuration_manual_recovery_verification.py`
- `dayu/services/write_model_configuration_manual_recovery_incident_dossier.py`
- `dayu/services/write_model_configuration_manual_recovery_incident_dossier_revalidation.py`
- `dayu/services/write_model_configuration_manual_recovery_gate_revalidation.py`

测试与索引：

- `tests/application/test_write_artifact_utils.py`
- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/application/test_write_model_configuration_manual_recovery_gate_revalidation.py`
- `tests/README.md`

实现记录：

- `docs/reviews/slice-2b-write-artifact-callers-implementation-20260807-codex.md`

Cohort A 10 个生产文件、shared helper 和 master plan 均未修改。

## 逐文件迁移

| 文件 | 删除的 eligible 定义 | shared 替换 | 保留/defer |
|---|---|---|---|
| `write_model_configuration_application.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc`, `_is_relative_to`, `_serialize`, `_decode_base64` | `canonical_json_bytes`, `fingerprint_bytes`, `file_fingerprint`, `bytes_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `format_utc`, `is_subpath`, `serialize_pretty`, `decode_base64` | 族 C `_validated_fingerprint`、snapshot/transaction/persist |
| `write_model_configuration_rollback_application.py` | 同 application 的 11 个 eligible 定义 | 同 application 的 11 个 shared helper | 族 B `_validated_fingerprint`、snapshot/transaction/persist |
| `write_model_configuration_manual_recovery.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_format_utc`, `_serialize`, `_decode_base64` | bytes fingerprint 族、`require_mapping`, `require_text`, `absolute_path`, `format_utc`, `serialize_pretty`, `decode_base64_strict` | 族 D `_validated_fingerprint`、persist |
| `write_model_configuration_manual_recovery_application.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_absolute_path`, `_is_relative_to`, `_serialize`, `_decode_base64`, `_format_utc` | bytes fingerprint 族、`require_mapping`, `absolute_path`, `is_subpath`, `serialize_pretty`, `decode_base64`, `format_utc_seconds` | 族 2 `_required_text`、族 B `_validated_fingerprint`、snapshot/transaction/persist |
| `write_model_configuration_manual_recovery_clearance.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_required_text`, `_is_relative_to`, `_serialize`, `_format_utc` | bytes fingerprint 族、`require_mapping`, `require_text`, `is_subpath`, `serialize_pretty`, `format_utc_seconds` | 族 B `_validated_fingerprint`、persist |
| `write_model_configuration_manual_recovery_verification.py` | `_canonical_json`, `_bytes_fingerprint`, `_mapping` | `canonical_json_bytes`, `bytes_fingerprint`, `require_mapping` | 族 2 `_required_text`、族 E `_validated_fingerprint`、snapshot/transaction |
| `write_model_configuration_manual_recovery_incident_dossier.py` | `_canonical_json`, `_fingerprint`, `_mapping`, `_required_text`, `_is_relative_to`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `require_mapping`, `require_text`, `is_subpath`, `serialize_pretty` | 族 B `_validated_fingerprint`、transaction/persist |
| `write_model_configuration_manual_recovery_incident_dossier_revalidation.py` | `_canonical_json`, `_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_is_relative_to`, `_serialize` | `canonical_json_str`, `fingerprint_str(dict(...))`, `bytes_fingerprint`, `dict(require_mapping(...))`, `is_subpath`, `serialize_pretty` | 族 6 `_required_text`、auto `_format_utc`、族 B `_validated_fingerprint`、persist |
| `write_model_configuration_manual_recovery_gate_revalidation.py` | `_canonical_json`, `_fingerprint`, `_bytes_fingerprint`, `_mapping`, `_is_relative_to`, `_serialize` | `canonical_json_str(dict(...))`, `fingerprint_str(dict(...))`, `bytes_fingerprint`, `dict(require_mapping(...))`, `is_subpath`, `serialize_pretty` | 族 7 `_required_text`、auto `_format_utc`、族 F `_validated_fingerprint`、persist |

语义边界保持：

- 前五个 bytes fingerprint caller 与后三个 str fingerprint caller 未混用。
- 九个私有 `_validated_fingerprint` 全部保留，且没有调用 shared `validated_fingerprint`。
- application、rollback application 与 manual recovery 使用 microseconds
  `format_utc`；manual recovery application 与 clearance 使用 seconds
  `format_utc_seconds`；两个 revalidation 文件的 auto `_format_utc` 原样保留。
- 路径与 codec 仍先经过对应的 shared 或 deferred 本地
  required-text family；manual recovery 的严格 base64 仍使用
  `decode_base64_strict`。
- 七个 identity mapping caller 直接使用 `require_mapping`；两个 copy
  mapping caller 在每个 call site 使用 `dict(require_mapping(...))`，相关
  canonical/fingerprint call site 继续保留 `dict(...)` adapter。
- snapshot、transaction、persist 与业务级 fingerprint family 保持原位。
- 类型仅沿既有校验边界传播；未新增 helper、public API、`Any`、`object`、
  `cast` 或 `type: ignore` 逃逸。

## 测试与验证

### 聚焦与 application write-model 测试

```text
source .venv/bin/activate
pytest tests/application/test_write_artifact_utils.py -q
```

结果：`23 passed`。已删除 eligible 私有 seam 的测试改为对同一固定 corpus
直接断言 shared helper；所有 deferred 私有 family characterization 继续保留。

完整 application 目录在收集期受当前环境未安装可选 `streamlit` 依赖影响：

```text
pytest tests/application -k write_model --collect-only -q
```

结果：四个无关 Streamlit 测试模块出现 `ModuleNotFoundError: streamlit`；
同时成功选出 `237` 个 write-model 测试。排除这四个无关收集入口后运行：

```text
pytest tests/application \
  --ignore=tests/application/test_streamlit_chat_stream_runtime.py \
  --ignore=tests/application/test_streamlit_chat_tab.py \
  --ignore=tests/application/test_streamlit_filing_runtime.py \
  --ignore=tests/application/test_streamlit_filing_tab.py \
  -k write_model -q
```

结果：`237 passed, 1 skipped, 1082 deselected`。

迁移测试同步完成：

- CLI 私有 helper import 改为 shared helper 固定 corpus。
- preapplication 的 application、rollback 及 recovery 链路继续覆盖迁移后的
  caller；新增真实 malformed dossier/evidence/intent 分支回归。
- gate revalidation 增加真实 malformed top-level corpus。
- `tests/README.md` 仅将当前 helper 测试入口说明更新为迁移后语义。

### 单文件覆盖率

Python 3.13/NumPy 导入期会干扰 pytest-cov tracer。沿用已记录的 preload +
`coverage.Coverage(source=[module_name], timid=True, data_file=...)`
workaround；每个目标使用独立 data file，并运行对应 caller corpus。

| 生产文件 | statements / missing | 精确覆盖率 | corpus |
|---|---:|---:|---:|
| `write_model_configuration_application.py` | 719 / 143 | 80.11% | 166 passed |
| `write_model_configuration_rollback_application.py` | 1198 / 239 | 80.05% | 163 passed |
| `write_model_configuration_manual_recovery.py` | 551 / 97 | 82.40% | 140 passed |
| `write_model_configuration_manual_recovery_application.py` | 706 / 123 | 82.58% | 140 passed |
| `write_model_configuration_manual_recovery_clearance.py` | 1283 / 198 | 84.57% | 140 passed |
| `write_model_configuration_manual_recovery_verification.py` | 452 / 68 | 84.96% | 140 passed |
| `write_model_configuration_manual_recovery_incident_dossier.py` | 186 / 34 | 81.72% | 140 passed |
| `write_model_configuration_manual_recovery_incident_dossier_revalidation.py` | 251 / 50 | 80.08% | 163 passed |
| `write_model_configuration_manual_recovery_gate_revalidation.py` | 243 / 48 | 80.25% | 163 passed |

九个文件均以未四舍五入的精确值达到 `>= 80%` 门槛。补充的 corpus 走真实
public caller 与 validator 路径，未增加生产 seam 或 coverage pragma。

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/ \
  tests/application/test_write_artifact_utils.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/application/test_write_model_configuration_manual_recovery_gate_revalidation.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

```text
source .venv/bin/activate
ruff check --select F,I001 <9 production files> <4 changed test files>
```

结果：`All checks passed!`

逐生产文件以 `git show HEAD:<path>` 通过 stdin 运行全规则 Ruff，并比较
rule-code multiset。九个文件均无新增规则码：所有 HEAD `I001` 已消除；
application、rollback application、manual recovery、manual recovery
application、clearance、verification、incident dossier revalidation 与 gate
revalidation 的 `TRY004` 分别减少，incident dossier 当前全规则结果为空。
其余 `BLE001`、`FURB162`、`RUF022`、`UP012` 均为 HEAD 既有基线。

### 结构与范围审计

```text
rg <eligible private definitions> <9 Cohort B files>
rg '^def _validated_fingerprint' <9 Cohort B files>
rg '(?<!_)validated_fingerprint\(' <9 Cohort B files> --pcre2
rg 'require_mapping' <2 copy-mapping files>
git diff --name-only -- <10 Cohort A files>
git diff -U0 | rg '^\+.*(\bAny\b|\bobject\b|cast\(|type:\s*ignore)'
git diff --check
```

结果：

- eligible 私有定义为零。
- 九个 deferred `_validated_fingerprint` 定义完整保留，shared helper 调用为零。
- deferred `_required_text` 为 4 个，auto `_format_utc` 为 2 个；copy 与
  canonical/fingerprint dict adapters 均存在于计划指定 call site。
- Cohort A diff 为零，禁止类型逃逸新增为零。
- `git diff --check` 通过。

## 双路初审与 Controller 裁决

- DeepSeek 初审:
  `docs/reviews/code-review-slice-2b-20260807-deepseek.md`
- MiMo 初审:
  `docs/reviews/code-review-slice-2b-20260807-mimo.md`
- Controller 裁决:
  `docs/reviews/slice-2b-code-review-adjudication-20260807-codex.md`

Controller 逐项拒绝 DeepSeek M1–M3/L1–L2 与 MiMo L1–L3，判定其均为
non-defect、HEAD baseline 或 accepted-design observation。无需代码、测试、
README 或 plan fix；Controller 裁决后 open High/Medium/Low 均为 `0`。
Controller 同时要求 MiMo re-review 纠正初审 §2.5 的证据措辞：
absolute-path/codec 均先经“对应 text validator”，其中三个 family 1 caller
使用 shared `require_text`，manual recovery application family 2 使用
retained local `_required_text`。

## 双路 re-review 闭环

- DeepSeek:
  `docs/reviews/code-rereview-slice-2b-20260807-deepseek.md`
- MiMo:
  `docs/reviews/code-rereview-slice-2b-20260807-mimo.md`

两路复审均为 **PASS**，确认 DS M1–M3/L1–L2 与 MiMo L1–L3 共 8 项
observation 全部 **CLOSED**，无需 production/test/README/plan fix。当前
open High/Medium/Low 均为 `0`。

MiMo re-review 已纠正并独立核验初审 §2.5 的证据措辞：所有
absolute-path/codec caller 均先经“对应 text validator”；三个 family 1
caller 使用 shared `require_text`，manual recovery application family 2
使用 retained local `_required_text`。

## 残余风险

- 族 B/C/D/E/F validated-fingerprint、族 2/6/7 required-text、auto
  `_format_utc` 以及 snapshot/transaction/persist 均为 accepted plan 明示
  defer；本 slice 没有试图统一其业务差异。
- 当前开发环境未安装可选 `streamlit`，因此 application 全目录需排除四个
  与本 slice 无关的 Streamlit 收集模块；被选中的 237 个 write-model 测试
  已全部通过。
- 两个 copy-mapping 文件依赖逐 call-site `dict(...)` adapter 保持历史
  copy 语义；结构审计已锁定，但后续重构仍需保留该差异。
