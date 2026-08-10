# Slice 1.4 S3 Fins blob repository pre-edit plan fix（corrective closure）

- **Work unit**：Investment Platform Restoration / Slice 1.4
- **Controller**：Codex
- **日期**：2026-08-10
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **基线**：`5d7e6bb`（branch `codex/investment-platform`）
- **目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **corrective fix artifact**：`docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`
- **final corrective fix artifact**：`docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`
- **final closure fix artifact**：`docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md`
- **final closure source reviews（只读）**：
  `docs/reviews/plan-final-rereview-20260810-213617-slice-1.4-terra.md`
  （Terra，FAIL，S14-REREVIEW-01..03，2H/1M）、
  `docs/reviews/plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`
  （MiM Native，PASS-WITH-RISKS，F-01 1M）

## Trigger

DeepSeek Flash 在 Slice 1.4 pre-edit audit 按 stop condition 零编辑停报。现有代码已经提供
可注入 `FileStore` 的共享 `FsStorageCore`、固定 `_build_store_key` 与 Slice 1.3 的
backend-independent evidence identity；但原 Slice 1.4 只有“选择一个 S3 client、checksum/
atomic put、真实 MinIO integration”等目标，无法唯一决定以下持久化边界：

1. `DAYU_PLATFORM_OBJECT_STORAGE` 的值 schema、credential env-name 与 secret-safe
   startup 行为；
2. S3 是替代 blob bytes 还是整套 FS repository，以及 bucket/key owner；
3. overwrite、partial cleanup、checksum、ETag 与 `FileObjectMeta` 的精确语义；
4. `DefaultFinsRuntime.create()` 与 startup composition 的唯一 backend selection；
5. 真实 MinIO 的镜像、资源 ownership、cleanup、marker 与测试目录。

worker 未修改任何文件；停报时 HEAD/worktree 为 `5d7e6bb`/clean。

## Direct repository evidence

- `FileStore` 已固定六方法；`FsStorageCore` 可接收单个注入 store，未注入时按 ticker 创建
  `LocalFileStore`。因此无需新增第二 repository protocol。
- `_build_store_key` 已固定 `ticker/filings|materials|processed/document_id/filename`；
  bucket 不应进入 key，investment/Agent 无需知道任何 object locator。
- company/source/processed meta、manifest 与 batch recovery 由 FS core 直接管理，而 blob
  bytes 通过 `FileStore`。最小且向后兼容的 backend 边界是 **FS metadata + S3 blob**。
- `DefaultFinsRuntime.create()` 当前无条件建立一个共享 FS repository set；startup当前
  无条件调用它。最小改动是 runtime 接受 optional `FileStore`，由 startup 基于严格
  platform settings唯一选择，runtime 本身不读 env。
- `PlatformSettings.object_storage_env` 明确只记录 env-name，provider应读取该名称指向的
  strict配置；当前测试中的 `minio://localhost:9000` 与 `s3://placeholder` 只是未被 owner
  解析的占位，不能升级为正式 contract。

## Round 1 Controller decisions（S14-CTRL-01..08，原 fix 内容）

### S14-CTRL-01 — client and dependency truth

- 唯一运行时 client是 boto3；production版本窗 `>=1.34,<2`，minimum/current pins与
  Python3.11 clean install lane在 master plan 精确列出。为遵守项目禁止宽类型逃逸的规则，
  dev lane增加匹配的 `boto3-stubs[s3]`，而不是把 dynamic client传播为 `Any`。
- 版本事实已用当前 PyPI resolver 只读复证：当前 direct版本 `1.43.67`，其匹配
  botocore/s3transfer/jmespath与typing packages已写入计划；若 clean resolver不闭合则
  stop，不让 worker自行漂移。

### S14-CTRL-02 — strict env-name configuration

- `DAYU_PLATFORM_OBJECT_STORAGE` 保存 strict JSON，字段为 backend、endpoint、region、
  bucket以及两个credential env-name；不保存 secret值。production enabled 才解析，其他
  profile继续 FS。
- endpoint拒绝 credentials/query/fragment；明文 HTTP只允许 loopback MinIO。client固定
  path-style，不读 ambient AWS profile/metadata/session token；missing secret fail-fast且错误
  不回显值。

### S14-CTRL-03 — storage boundary and identity

- FS继续拥有所有 repository metadata/manifest/recovery，S3只实现既有 `FileStore` 中的
  blob bytes。最终 key逐字复用 `_build_store_key`；bucket只在 store settings内。
- `FileObjectMeta.uri` 可以是 owner-private S3 URI，但 Evidence Locator保持
  `dayu.fins.public.v1`、不输出URI/bucket/key；FS/S3同bytes必须产生相同projection。

### S14-CTRL-04 — single-PUT staging and atomic copy

- 本 Slice不启用multipart；完整输入先spool并实算hash，再单PUT到reserved staging key，
  head验证后单次server-side copy发布final。这样caller读失败零远端副作用，final copy前失败
  保留旧对象，copy ambiguous completion可用final digest/size幂等判定。
- staging在finally bounded清理；ETag不冒充hash，`sha256`必须来自client实算且远端metadata/
  读回一致。hash mismatch、cleanup failure和不可判定copy一律fail closed。

### S14-CTRL-05/06 — composition and error contract

- `DefaultFinsRuntime.create(file_store=None)`保留FS；startup是唯一settings/env读取与S3选择
  owner。production S3做bounded bucket preflight，其他路径不触碰S3；platform provider不
  接收bucket/key。
- S3FileStore保持既有六方法和异常类别：invalid input=`ValueError`，missing=
  `FileNotFoundError`，client/checksum/cleanup=`OSError`固定安全消息。list分页、排序、
  staging过滤及presign上限均写成可测试契约。

### S14-CTRL-07/08 — real MinIO and gates

- integration统一放 `tests/integration/investment/`，不建立 Fins 第二lane。镜像固定为官方
  tag的multi-arch digest：
  `minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`。
  pytest不得pull；缺镜像hard fail并给出手动命令。
- 容器、bucket、credentials随机且以owner label绑定；无自定义network；bounded readiness；
  删除前复核name+label，只清本次资源。真实lane覆盖atomicity/checksum/drift/cleanup、FS/S3
  projection、runtime/startup selection；unit/static/coverage/dependency/README gates同步锁定。

## Dual plan review findings → Controller rulings（round 2 corrective）

Terra（`docs/reviews/plan-review-20260810-204331.md`，FAIL 3H/1M）与 MiM Native
（`docs/reviews/plan-review-20260810-204201-slice-1.4-s3-blob-repository-mimo-native.md`，
PASS-WITH-RISKS，M1–M5）的逐 ID 裁决、plan 位置与处置如下（全部按 Controller 裁决
唯一化进 master plan；两份 source review 保持只读）：

| ID | finding（source） | Controller 裁决 | plan 位置 | 处置 |
| --- | --- | --- | --- | --- |
| Terra S14-01 | 注入 FileStore 未覆盖现有 Fins 的 source/blob 实际读写面：`get_source`/`get_primary_source` 仍走 `_local_path_from_uri`+`LocalFileSource`，`read_file_bytes`/`list_entries`/`_delete_entry_impl` 直接操作本地路径，会形成只写不读的半替换 | 接受。S3 是 authoritative blob bytes，FS 只持 metadata/journal；列出并允许修改所有实际绕过 FileStore 的 source/blob/processed storage owner，明确 create/read/list/delete/process/evidence 全路径；新增 FileStore-backed Source adapter，close ownership 清楚；禁止本地 bytes fallback 或双写 | S14-CTRL-03（byte-path matrix + allowlist 精确展开）；S14-CTRL-06（get/open 流契约） | **CLOSED-IN-PLAN** |
| Terra S14-02 | FS batch 与 S3 final object 缺少共同 journal、恢复和补偿状态机；staging/final 孤儿与 metadata 悬挂无恢复方向 | 接受。在现有 FS batch/recovery owner 内加入最小 remote-operation journal：逐状态、字段、commit ordering、幂等恢复、只删除 operation-owned staging/final 写清楚；覆盖 put 后 crash、final 发布后 metadata 前 crash、metadata commit 后 cleanup 失败、重启、overwrite、auto/explicit batch；不得只靠 finally 或全前缀扫删 | S14-CTRL-04（状态机/commit ordering/恢复规则）；S14-CTRL-05（startup recovery 重放） | **CLOSED-IN-PLAN** |
| Terra S14-03 | CopyObject 只保证单对象可见性，未定义跨进程写入的并发所有权与覆盖语义，存在静默 last-writer-wins | 接受。当前 production topology 固定为单 Fins writer + 同一共享 workspace；必须写出可执行的 startup/runtime admission 与持有/释放生命周期，拒绝第二 writer，不能只写部署约定；多 host 多 writer 明确归后续 durable job ownership，不可暗中 last-writer-wins | S14-CTRL-09（writer lease admission/lifecycle）；S14-CTRL-05（startup 时序） | **CLOSED-IN-PLAN** |
| Terra S14-04 | startup 的 S3 preflight 顺序允许已创建 production provider side effect 后才发现 endpoint 不可用；原计划允许两个不等价顺序 | 接受。startup 顺序固定：load settings -> strict config/explicit credentials/build store/head_bucket/recovery/admission -> provider builder/probe -> composition/runtime/Host；任何 S3 失败时 provider/workspace/Host 均未调用，所有已创建 S3/lease 资源有确定 cleanup | S14-CTRL-05（exact order + 失败 cleanup）；S14-CTRL-08（startup 顺序记录 fake 测试） | **CLOSED-IN-PLAN** |
| MiM M1 | S3 staging orphan 超出现有 FS batch recovery 观测范围，无 startup/background 清理路径 | 接受。remote-operation journal 覆盖 crash 恢复：put 后 crash 的 staging keys 由 journal 重放删除，只删 operation-owned，禁全前缀扫删 | S14-CTRL-04；S14-CTRL-03 | **CLOSED-IN-PLAN** |
| MiM M2 | `stat_object` 强制下载完整对象实算 hash 违背 stat（HEAD）语义，高频 evidence 路径慢 100–1000x | 接受其核心修正：`stat_object` 必须 HEAD-only 验证 size/metadata；完整 bytes SHA 校验移到 `get_object`/`Source.open` 真实读取并返回 owner 明确、seekable、已验证的 `BinaryIO`，不得让 StreamingBody 泄漏；禁止本地 bytes fallback 或双写 | S14-CTRL-06（stat/get/open 契约） | **CLOSED-IN-PLAN（Controller 修正契约）** |
| MiM M3 | startup S3 preflight 若在 provider composition 后执行，provider 失败/engine 已建时 S3 资源不受控 | 接受。S3 preflight 固定在 `_default_provider_or_fail` 之前；startup 失败路径统一 dispose engine + 关闭 S3 client + 释放 lease，零 atexit 残留 | S14-CTRL-05（exact insertion point + cleanup）；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| MiM M4 | `list_objects` 协议未明确全量/排序/pagination 契约边界 | 接受。list contract 明确为：返回全量 `list[FileObjectMeta]`、内部穷尽 pagination、按 key 排序、排除 reserved staging；`LocalFileStore` 同步补齐排序 | S14-CTRL-06（list contract） | **CLOSED-IN-PLAN** |
| MiM M5 | MinIO fixture 缺少进程 hang 的 force-kill cleanup 路径 | 接受。`docker stop --time=1` bounded 等待后仍存活则 `docker kill`，再 `docker rm -f`；删除前复核 name+label，cleanup bounded 总超时 | S14-CTRL-07（TERM->bounded KILL + owner label 复核） | **CLOSED-IN-PLAN** |

逐 ID 均无 **RE-REVIEW-REQUIRED**：契约已在 corrective fix 内唯一化；最终闭合仍以
Terra + MiM Native 双路 plan re-review PASS 且 open H/M/L=`0/0/0` 为 gate。

## Corrective contract changes（唯一化要点）

- **S14-CTRL-03（REVISED）**：S3 authoritative bytes + FS 只持 metadata/journal；
  byte-path matrix 列出全部真实字节 owner（source/blob/processed/rejected/tool_snapshot
  read/list/delete/reset/cleanup/XBRL 探测/process/evidence）并允许修改对应文件；新增
  FileStore-backed `Source` adapter；禁止本地 fallback/双写；allowlist 精确展开到文件级；
  `file_store.py` 仅允许 `list_objects` docstring 契约化（方法签名/语义不改）。
- **S14-CTRL-04（REVISED）**：最小 remote-operation journal 并入现有 FS batch owner；
  **顶层 `phase` 仅表 batch/meta 阶段（`staged -> metadata_committed -> cleanup_done`，
  旁路 `rolled_back`/`cleanup_pending`），bytes 发布进度由每个 target 的
  `publish_state`（`staged|final_verified`）独立表达**；commit ordering 为
  publish-before-swap，逐 target copy 前后原子持久；copy 响应或 journal 写模糊时以 head
  final digest/size 判定本 target 完成；恢复逐 target 独立判定（final 已匹配则 verified、
  未发布但 staging 存在则完成发布、staging 缺失 fail closed），全部 targets verified 且
  FS staging 完整才 metadata roll-forward，FS staging 缺失/损坏 fail closed 保留
  journal/远端 objects；只删 operation-owned staging，禁全前缀扫删。
- **S14-CTRL-05（REVISED）**：startup 顺序固定为 load settings -> S3 config/credentials/
  build store/head_bucket -> writer lease/recovery -> provider -> composition/runtime/Host；
  任一 S3 失败零 provider/workspace/Host 调用、已建 S3/lease 资源确定性 cleanup；shutdown
  owner 评估（`PreparedHostRuntimeDependencies.close`/`_OwnedLifecycleRegistration`）与
  exact files/functions/tests 列出。
- **S14-CTRL-06（REVISED）**：`stat_object` HEAD-only 验证 size/metadata；SHA 校验移至
  `get_object`/`Source.open` 返回 owner 明确、seekable、已验证 BinaryIO，StreamingBody
  不泄漏；list 全量/内部穷尽 pagination/按 key 排序/排除 staging。
- **S14-CTRL-07（REVISED）**：MinIO fixture TERM->bounded KILL、owner label 复核、
  bounded 总超时；fault injection + restart recovery、两个独立 writer 等真实 lane 矩阵。
- **S14-CTRL-08（REVISED）**：test matrix（unit/journal/lease/startup/integration）与
  stop conditions 精确列出。
- **S14-CTRL-09（NEW）**：单 Fins writer + 同一共享 workspace 的 flock 式 admission 与
  持有/释放生命周期，拒绝第二 writer；多 host 多 writer 归后续 durable job ownership。
- **S14-CTRL-10（NEW）**：source findings 逐 ID disposition 表。

## 追加自审修正（multi-target crash gap，总控自审发现）

自审发现并闭合一个必须收敛的 crash gap：原 S14-CTRL-04 只有顶层 `phase`，当一次
operation 含 2+ targets 时，若 `commit_batch` 已发布第 1 个 final 后在继续 copy 前
crash，顶层 phase 仍可能为 `staged`，旧恢复规则会误判“finals 从未发布”而删除 staging
并回退，造成已发布 bytes 与 metadata 悬挂。修正（全部唯一化进 master plan S14-CTRL-04）：

1. journal target 新增 per-target `publish_state`（`staged|final_verified`），并保留
   target 期望 digest/size 作为 head 完成判定真值；顶层 `phase` 仅表示 batch/meta
   阶段（`staged -> metadata_committed -> cleanup_done`，旁路 `rolled_back`/
   `cleanup_pending`），不得从顶层 phase 推导 bytes 发布状态。
2. commit 逐 target：copy 前持久 `staged`、copy 后立即原子持久 `final_verified`
   （temp+replace 原子写）；copy 响应或 journal 写入模糊时，以 head final digest/size
   与本 target 期望值判定自己的完成（相等幂等 verified；不相等且 staging 存在重试
   copy；staging 缺失 fail closed）。
3. recovery 逐 target 独立判定：final digest+size 匹配 => 置 verified（即使 journal 仍
   写 `staged`）；不匹配且 staging 存在 => 完成发布后 verified；不匹配且 staging 缺失
   => FAIL CLOSED，保留 journal/远端 objects 供人工恢复，不删除、不宣称已恢复。全部
   targets verified 且 FS batch staging 目录完整才执行 metadata roll-forward；FS
   staging 缺失/损坏 => FAIL CLOSED。绝不把部分 publish 当全未 publish。
4. unit/MinIO fault matrix 新增：2+ targets 在第 1 个 copy 后 crash（顶层仍 `staged`）、
   copy 后 journal 写前 crash（head digest/size 判定）、recovery 完成剩余发布且最终
   metadata 与全部 bytes digest 一致。
5. Allowed 新增 `dayu/fins/storage/file_store.py`（仅 `list_objects` docstring contract
   修改，方法签名/语义不改），消除“public protocol 冻结”与可修改清单的歧义。

其余裁决（Terra S14-01..04、MiM M1/M3/M4/M5、MiM M2 HEAD-only stat + verified get、
单 writer 拓扑、startup 顺序、依赖/pinned MinIO/secret/locator identity、S14-CTRL-10
逐 ID CLOSED-IN-PLAN）全部保持不变。

## Review questions resolution

1. strict JSON env-name contract 是否仍存在 secret/ambient credential/bucket path 泄漏？
   否。S14-CTRL-02 保持 accepted；credential 只按 env-name 读取，client 禁 ambient chain。
2. FS metadata + S3 blob 是否产生未覆盖的不一致窗口？否。S14-CTRL-04 remote journal
   状态机 + S14-CTRL-05 startup recovery 重放闭合所有 crash 窗口。
3. single-PUT staging + CopyObject 是否足以证明 atomicity/ambiguous/cleanup？是。
   S14-CTRL-04 固定 publish-before-swap ordering；5 GiB 上限内不启用 multipart。
4. `stat_object` 远端 metadata + exact bytes 实算是否闭合 hash drift？否，已修正为
   HEAD-only（size/metadata）；完整 SHA 校验移至 `get_object`/`Source.open`（S14-CTRL-06）。
5. startup fail-fast 顺序是否唯一且无旁路？是。S14-CTRL-05 固定顺序 + S3 失败零
   provider/workspace/Host + 确定性 cleanup。
6. pinned digest MinIO fixture 是否具备可验证 owner cleanup？是。S14-CTRL-07 增加
   TERM->bounded KILL、owner label 复核与 bounded 总超时。

## Round 3 Controller rulings（final re-review：Terra 211302 + MiM 211155）

Terra（`docs/reviews/plan-review-20260810-211302.md`，FAIL，S14-FINAL-01..04：3H/1M）与
MiM Native（`docs/reviews/plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`，
PASS-WITH-RISKS，MR1/MR2/MR3）的逐 ID 裁决如下（全部按 Controller 裁决唯一化进 master
plan S14-CTRL-03..13；两份 final source review 保持只读）：

| ID | finding（source） | Controller 裁决 | plan 位置 | 处置 |
| --- | --- | --- | --- | --- |
| Terra S14-FINAL-01 | Host scene 的真实 Fins tool path（`ScenePreparer._build_tool_registry` → registrar → `_get_cached_fins_runtime`）自行构造 FS runtime，绕过 S3 store 与 writer lease | 接受。禁止 module global cached FS runtime；`toolset_registrars.py` 改为 `build_fins_toolset_registrars(runtime)` 返回持有已装配 runtime 的 typed frozen callable 只读映射；`DefaultScenePreparer`/`Host` 接受只读 `toolset_registrar_overrides`，`_build_tool_registry` 按 name 优先 override、否则才 load 配置 path；Fins-owned toolset 缺 override fail closed；startup 用唯一 runtime 构造 override 传 Host，Host/contracts 不 import Fins、bucket/key 不越层；真实 Host scene read/ingestion/process/evidence 同一 repository_set black-box | S14-CTRL-11；S14-CTRL-05；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-FINAL-02 | remote journal 未跨越真实 blob 写 + 随后 FS metadata 写，publish-before-swap 无法成立 | 接受。复用现有 `BatchingRepositoryProtocol`；S3 模式 `store_file`/`store_rejected_filing_file` 必须已有 active explicit BatchToken 否则稳定失败 `s3_write_requires_batch`，只 stage 不 publish；SEC/CN/Docling upload/tool snapshot/rejected rescue/retriage 七条真实调用链逐一 allowlist 并在最高原子边界显式 begin/commit/rollback；每个 producer 配 blob 后 kill、metadata 前 kill、overwrite 后 kill 真实测试；`build_fs_repository_set`/`create` 参数互斥、窄 repo 共享同一 core/token | S14-CTRL-12；S14-CTRL-04；S14-CTRL-05；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-FINAL-03 | delete/reset/cleanup 先删 S3 bytes 后删 FS metadata 不可恢复，journal 未建模 delete target | 接受。journal target `action` 闭合 `publish|delete`；delete/reset/clear/stale cleanup 先 head 记录 expected sha/size + delete intent、更新 FS staging metadata 但不远端删；commit 先验证 remote 仍匹配再 FS swap 后幂等 remote delete；post-commit delete 失败 => success+cleanup_pending、startup 重试；missing after commit => 幂等 cleaned；digest drift swap 前 abort；任何路径禁止先删 remote；fault matrix 覆盖 single delete/reset/processed clear/filing clear/stale cleanup/missing/ambiguous delete/kill 每 phase | S14-CTRL-13；S14-CTRL-04；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-FINAL-04 | “已验证、seekable、caller-owned BinaryIO”与冻结公共协议文档不一致 | 接受。`FileStore.get_object` 与 engine `Source.open` docstring 只锁跨实现共同语义（caller-owned、caller close、seekable、读取异常）；checksum 是 S3 concrete adapter 契约，不虚构 Local 相同 remote metadata 验证；`FileStore.list` docstring 保留 | S14-CTRL-06；allowlist 精确展开（`file_store.py` get_object + `engine/processors/source.py`） | **CLOSED-IN-PLAN** |
| MiM MR1 | begin_batch copytree 在 S3 模式只拷贝本地 metadata 不拷贝 S3 bytes，recovery roll-forward 依赖本地 staging 完整性 | 接受。S3 模式 `begin_batch` copytree 精确声明只复制 FS metadata/manifest/journal tree；blob 不在本地；staging 缺损 fail closed 保留 journal 供人工恢复并有测试，不伪造自动重建 | S14-CTRL-04 | **CLOSED-IN-PLAN** |
| MiM MR2 | `_write_json` 非原子写入可能损坏 journal | 接受。remote_op_journal 使用独立 atomic JSON helper（same-dir temp、flush+fsync、os.replace、parent dir fsync），不复用 `_write_json`。只读核验注：`_write_json`（`_fs_storage_utils.py:439-463`）当前实现本身已是 temp+replace+dir-fsync 原子写，本裁决不改动它 | S14-CTRL-04 | **CLOSED-IN-PLAN** |
| MiM MR3 | staged capability 的 isinstance 检查是类型安全的 | 不修复（verified non-finding）。`_StagedFileStore` 用 `@runtime_checkable` 私有 Protocol + isinstance，类型安全且不违反 AGENTS.md | S14-CTRL-06 | **VERIFIED-NON-FINDING / CLOSED** |

逐 ID 均无 **RE-REVIEW-REQUIRED**（MR3 为 VERIFIED-NON-FINDING）：契约已在 final
corrective fix 内唯一化；最终闭合仍以 Terra + MiM Native 双路 final corrective plan
re-review PASS 且 open H/M/L=`0/0/0` 为 gate。原 round 1/2 裁决（Terra S14-01..04、
MiM M1..M5）保持历史记录不变。

## Round 4 Controller rulings（final closure：Terra 213617 + MiM Native 213634）

Terra（`docs/reviews/plan-final-rereview-20260810-213617-slice-1.4-terra.md`，FAIL，
S14-REREVIEW-01..03：2H/1M）与 MiM Native
（`docs/reviews/plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`，
PASS-WITH-RISKS，F-01 1M）的逐 ID 裁决如下（合并 2H/2M，全部按 Controller 裁决唯一化
进 master plan S14-CTRL-04/05/08/10/11/12/13；两份 final closure source review 保持
只读）：

| ID | finding（source） | Controller 裁决 | plan 位置 | 处置 |
| --- | --- | --- | --- | --- |
| Terra S14-REREVIEW-01 | S14-CTRL-12 没有可实施的同-core BatchToken 传播路径，且 allowlist 排除必经编排点（`_build_pipeline`/factory/pipelines 均不在 Allowed） | 接受。`DefaultFinsRuntime` 从同一 `_FsRepositorySet` 构造并持有唯一 `FsBatchingRepository`；`_build_pipeline_for_ticker`→`_build_pipeline`→`get_pipeline_from_normalized_ticker`→`SecPipeline`/`CnPipeline` 逐层显式传递 `batching_repository`；`SecDownloadWorkflowHost`/`CnDownloadWorkflowHost` 暴露该能力并在 per-ticker 循环显式 begin/commit/rollback；七条 producer（SEC active、SEC rejected[与 active 共享同一 per-ticker batch]、CN filing、Docling upload、tool snapshot、rejected rescue、rejected retriage）各自边界显式 begin/commit/rollback；注入路径 pipeline 不再自建第二 core；Host/Agent 不见 repository/core；allowlist 精确展开（factory/sec_pipeline/cn_pipeline/sec_download_workflow/cn_download_workflow/cn_download_protocols/fs_batching_repository 等） | S14-CTRL-12；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-REREVIEW-02 | S14-CTRL-05 对 `file_store`/`repository_set` 参数互斥的规定与其固定 startup 步骤（同传两者）互相矛盾 | 接受。startup 先 `build_fs_repository_set(workspace_root, file_store=s3_store)`，再只调 `DefaultFinsRuntime.create(workspace_root, repository_set=repository_set)`；`create` 只接受可选 `repository_set`、不新增 `file_store`；`PreparedHostRuntimeDependencies` 独占并关闭 S3 store/lease；startup unit 锁 exact args/单次 recovery/同一 repository_set/唯一 close owner | S14-CTRL-05；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-REREVIEW-03 | destructive state machine 未覆盖 processed 更新的文件移除，`meta.files` 前提也未为 processed 建立 | 接受。所有改变 blob inventory 的 metadata mutation（processed `financials` present→None、source files shrink）比较 old/new authoritative inventory，local swap 前 journal delete intents；processed meta 显式持久化 authoritative files inventory；逐 phase kill 测试；禁 prefix sweep | S14-CTRL-13；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| MiM F-01 | S3 模式 `_execute_with_auto_batch` auto-begin 行为与 `s3_write_requires_batch` 约束存在实现歧义 | 接受。`_execute_with_auto_batch` FS/local 保留 auto-begin；S3 模式（`_StagedFileStore` isinstance）无 active token fail-loud `s3_write_requires_batch`、禁自动 begin/commit；有同-core active token 才复用；模式判定不靠类型猜测/动态属性 | S14-CTRL-12；S14-CTRL-08 | **CLOSED-IN-PLAN** |

逐 ID 均无 **RE-REVIEW-REQUIRED**：契约已在 final closure fix
（`docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md`）内唯一化；最终
闭合仍以 Terra + MiM Native 双路 **final closure plan re-review** PASS 且 open
H/M/L=`0/0/0` 为 gate。原 round 1/2/3 裁决（Terra S14-01..04、MiM M1..M5、Terra
S14-FINAL-01..04、MiM MR1/MR2、MR3）保持历史记录不变。另按 Controller 额外精确化：
Fins-owned toolset fail-closed 改为以 protected exact toolset names（`fins`/`ingestion`，
注册真源 `dayu/config/toolset_registrars.json`）判定，不再用 import-path prefix
（S14-CTRL-11）。

## Round 5 Controller rulings（final closure corrective：Terra final-closure + MiM Native 220137）

Terra（`docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-terra.md`，FAIL，
S14-CLOSURE-01/02：2H）与 MiM Native
（`docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`，PASS，
open 0/0/0，记录为证据但未覆盖下述两缺口）的逐 ID 裁决如下（全部按 Controller 裁决
唯一化进 master plan S14-CTRL-12/13；两份 final closure corrective source review 保持
只读）：

| ID | finding（source） | Controller 裁决 | plan 位置 | 处置 |
| --- | --- | --- | --- | --- |
| Terra S14-CLOSURE-01 | Host ingestion factory 绕过计划规定的唯一 batching 传播链：真实 Host `ingestion` toolset 走 `build_ingestion_service_factory()`，`dayu/fins/ingestion/factory.py` 不在 allowlist，factory 链无 `batching_repository` 参数，Host scene ingestion 无法获得同-core batch capability | 接受。`DefaultFinsRuntime.batching_repository` → `build_ingestion_service_factory(... batching_repository=self.batching_repository)` → `dayu.fins.ingestion.factory.build_ingestion_service_factory` → `build_ingestion_service_from_normalized_ticker` → `get_pipeline_from_normalized_ticker` → `SecPipeline`/`CnPipeline` 逐层显式传递同一实例/同一 core；`ingestion/factory.py` 加入 allowlist；Host/Agent/tool contract 不见 repository/core；禁第二 `FsBatchingRepository`/global cache/wrapper；`test_runtime_batch_injection.py` 扩展 runtime direct + ingestion factory 的 US/CN 与真实 Host ingestion 写 producer 同-core/零无-token admission | S14-CTRL-12；S14-CTRL-08 | **CLOSED-IN-PLAN** |
| Terra S14-CLOSURE-02 | S3 fail-loud 与真实下载/快照工作流的 boundary 顺序矛盾：company upsert/overwrite clear/stale cleanup 位于指定 SEC/CN 下载循环之外、snapshot pre-cleanup 位于 `export_tool_snapshot` 边界之前，S3 admission 使这些真实 mutation 在 token 前后确定性失败 | 接受。S14-CTRL-12/13 逐名列出 S3 fail-loud 全 mutation 最小 explicit boundary：SEC/CN company upsert（`sec_download_workflow.py:371-376`/`cn_download_workflow.py:201-206`）、SEC/CN overwrite clear（`:378-379`/`:224`）、SEC stale cleanup（`:475`）、source reset、processed clear（`sec_process_workflow.py:328`/`cn_pipeline.py:989`）、snapshot pre-cleanup+export 上移到 `_export_tool_snapshot_for_document`（`sec_pipeline.py:1754`/`cn_pipeline.py:1502`）一次 boundary 覆盖；每段 metadata/delete-only mutation 最小 begin/commit/rollback、异常 rollback、禁跨网络长期持有 token、export 不建第二 batch（复用 active same-core token）、S3 不恢复 auto-begin；`sec_process_workflow.py` 加入 allowlist；S14-CTRL-08 测试矩阵与 stop conditions 同步 | S14-CTRL-12；S14-CTRL-13；S14-CTRL-08 | **CLOSED-IN-PLAN** |

逐 ID 均无 **RE-REVIEW-REQUIRED**：契约已在 final closure corrective fix
（`docs/reviews/plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`）内
唯一化；最终闭合仍以 Terra + MiM Native 双路 **final corrective plan re-review** PASS
且 open H/M/L=`0/0/0` 为 gate。原 round 1/2/3/4 裁决全部保持历史记录不变。

## Terminal corrective 补充（round 6：Terra S14-CORRECTIVE-01/02 + MiM Native final-corrective rereview）

terminal corrective re-review 新增 findings（Terra
`docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-terra.md`
S14-CORRECTIVE-01/02，2H；MiM Native
`docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据，不覆盖 Terra 直接反例）由
`docs/reviews/plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md` 详细展开。
Controller 架构修正：**放弃对每个业务 caller 逐一包事务 wrapper（会把事务知识泄漏到
所有 workflow），改为 storage owner 显式 per-operation admission**，已全部唯一化进
master plan S14-CTRL-12/13：

- **(A) 完整 mutation inventory + admission 分类（闭合 S14-CORRECTIVE-01）**：不再用
  "八类"；以全部 `_execute_with_auto_batch` 调用点与 dayu/fins production callers 的
  交叉为真源写 exhaustive 分类表（新增 SEC/CN upload company upsert +
  overwrite reset + SEC rejection registry save 等真源），并加 AST/unit completeness
  gate（每个调用点显式传 `BatchAdmission` 分类，缺失/未知即 fail；未归类 caller 即
  STOP）。上传/registry 路径零业务 wrapper：单短 `AUTO_ATOMIC_ALLOWED` batch、
  无嵌套、同 core/recovery；上传测试 owner
  `tests/fins/test_sec_pipeline_upload_filing_stream.py`/`test_sec_pipeline_upload_material_stream.py`/
  `test_cn_pipeline.py` 加入 allowlist。
- **(B) S3 batch admission 改为 per-operation 分类（修正 MiM F-01 闭合语义）**：
  `_fs_storage_infra` 新增私有 typed/frozen `BatchAdmission`
  （`EXPLICIT_REQUIRED` vs `AUTO_ATOMIC_ALLOWED`，S3 无隐式默认）；S3
  EXPLICIT_REQUIRED 无同-core active token => `s3_write_requires_batch` 零 auto
  begin/commit；AUTO_ATOMIC_ALLOWED 方法自身即完整原子语义单元、至多一个短内部
  batch；FS/local 保留 auto-begin；active token 一律复用（禁嵌套）。跨
  repository/blob+metadata 原语（`store_file`/`store_rejected_filing_file`/
  `delete_entry`）分类 EXPLICIT_REQUIRED，其 producer 边界保持显式同-core；完整
  单-repository metadata/destructive 操作（company upsert、独立 clear/reset/stale
  cleanup、rejection registry save、processed clear 等）分类 AUTO_ATOMIC_ALLOWED。
- **(C) 网络边界契约（闭合 S14-CORRECTIVE-02）**：删除"不得跨网络持 token"绝对约束；
  SEC/CN 每个 filing 在调用 `run_*_download_single_filing_stream` 之前 begin 一个
  同-core 显式 batch，允许覆盖该 filing 的远端 listing/download（及 CN Docling
  转换）与随后 blob+metadata 写入直到 commit/rollback；**token 绝不扩到整个 ticker
  循环**。生命周期由既有 per-request timeout + cancel_checker + 任务取消有界，并
  **新增 bounded `per_filing_timeout_seconds` 契约**（`asyncio.timeout` 包裹整个
  per-filing 窗口；当前不存在 per-filing/overall 聚合 timeout，不假装存在）；
  timeout/cancel/network error 无条件 rollback、零 publish，继续/停止行为保持现有
  owner contract；长持风险降为明确 residual（慢源占用同 ticker active batch、不泄漏
  第二 writer、由 timeout/cancel/metrics 缓解）。

Terra S14-CORRECTIVE-01/02 全部 **CLOSED-IN-PLAN**（S14-CTRL-12/13）；MiM F-01 闭合
语义修订为 per-operation admission 分类（非全局 S3 fail-loud）；S14-CLOSURE-01、
S14-REREVIEW-02/03、exact toolset names 保持 closed 无回归。master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL DUAL PLAN RE-REVIEW**；两份 final
corrective source review（final-corrective-rereview terra/mimo-native）保持只读。


## Terminal final corrective 补充（round 7：Terra S14-TERMINAL-01/02 + MiM terminal rereview 三项）

terminal plan re-review 新增 findings（Terra
`docs/reviews/plan-terminal-rereview-20260810-slice-1.4-terra.md`
S14-TERMINAL-01/02，2H；MiM Native
`docs/reviews/plan-terminal-rereview-20260810-slice-1.4-mimo-native.md`
delete_entry High + upload overwrite Medium + CN timeout Medium）全部 ACCEPT 并合并
闭合，由 `docs/reviews/plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`
详细展开，全部唯一化进 master plan S14-CTRL-03/04/08/10/12/13：
(1) **completeness 真源升级（闭合 Terra S14-TERMINAL-01）**——inventory 真源从
"`_execute_with_auto_batch` 调用点"扩展为"storage core 全部公开写入口 + 直接
FileStore/blob 原语 + manifest/inventory helper"；`replace_source_meta`
（`_fs_source_document_core.py:323-398`，公开协议 `repository_protocols.py:157-165`，
真实 SEC/CN rebuild callers `sec_rebuild_workflow.py:399`/`cn_download_rebuild.py:234-239`）
改为同一 storage-owner `_execute_with_auto_batch` + `BatchAdmission.AUTO_ATOMIC_ALLOWED`，
在 owner batch 内完成 old/new files inventory diff、removed delete intents、source
meta + filing/material manifest staging/swap，禁止先直接写 target；AST gate 断言公开
写入口集合与分类表一一对应并抓直接 put/delete/write-json+manifest 绕过；SEC/CN
rebuild 真实 owner/tests 加入 allowlist；
(2) **per-filing terminal 状态机（闭合 Terra S14-TERMINAL-02）**——SEC/CN outer
workflow 定义私有 typed/frozen PENDING/COMPLETED/FAILED 状态消费 single-filing
events；只有恰好一个 FILING_COMPLETED（含现有 skip）且 pre-commit cancel/deadline
fence 通过才 commit；FILING_FAILED 正常 return、缺/重复/矛盾 terminal、
CancelledError、TimeoutError、其它 exception 均 rollback 同一 token；外部 event 与
现有 continue/stop 语义不变；`commit_batch` 同步开始后为不可取消决策点（此前
deadline 保证 rollback 零 publish，开始后异常/crash 只按 S14-CTRL-04
journal/recovery 收敛，不宣称 timeout 能中断同步 commit）；
(3) **delete_entry S3 唯一行为（闭合 MiM delete_entry H）**——S3+active batch 绝不
直接 remote delete，用私有同-core stage-delete helper 记录 final key、expected
sha/size 为 journal `action=delete`/`delete_state=pending`（仅改 staging local），
remote delete 只在 metadata swap 后 cleanup/recovery；destructive AUTO 方法从 old
authoritative inventory 逐 key 复用同一 helper 后只 rmtree/unlink staging、无 prefix
sweep；FS/local 保留本地删除；
(4) **upload overwrite（闭合 MiM upload-overwrite M）**——company upsert 保持独立短
AUTO；overwrite reset 移进 `DoclingUploadService.execute_upload` 已有 per-document
显式 batch（begin → `reset_source_document` 复用 token → store_file + source meta →
commit；失败 rollback 保留旧 source/bytes）；workflow 不得预先 reset，无外层
wrapper/嵌套 batch；
(5) **CN blocking timeout（闭合 MiM CN timeout M）**——`asyncio.timeout` 只取消 outer
task，to_thread worker 可继续到现有有限 provider/request timeout（CN PDF download
底层 `request_timeout_seconds`）但不得访问 repo/batch；outer timeout 立即
rollback/清 active token/丢弃 late result；底层无有限 timeout 的 to_thread 路径不得
纳入"可中断"承诺并 STOP；Docling 转换段保留 round 6 residual。

Terra S14-TERMINAL-01/02 与 MiM 三项（delete_entry/upload overwrite/CN timeout）全部
**CLOSED-IN-PLAN**；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
exact toolset names 保持 closed 无回归。allowlist、test matrix、stop conditions、
residuals、finding table、completion 全部同步；两份 terminal source review
（plan-terminal-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL FINAL DUAL PLAN RE-REVIEW**；最终 gate
为 Terra + MiM Native 双路 **terminal final plan re-review** PASS 且 open
H/M/L=`0/0/0`。


## To-thread boundary 补充（round 8：Terra S14-TERMINAL-FINAL-01 + MiM terminal-final PASS）

terminal final plan re-review 新增 findings（Terra
`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-terra.md`
S14-TERMINAL-FINAL-01，一项 Medium）按 **ACCEPTED / FIXED-IN-PLAN** 处置；MiM Native
`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`
详细展开，唯一化进 master plan S14-CTRL-12 网络边界契约（reviewer option 2 诚实三段
边界，不扩 subprocess framework）：
(A) **阶段 A（provider download/request）唯一 hard-bounded**——`per_filing_timeout_
seconds` 更名为 keyword-only `provider_download_timeout_seconds`，`asyncio.timeout`
只包裹阶段 A 的 await 窗口；每个独立请求继续由既有 per-request timeout 有界；仅此
可宣称 hard bounded；
(B) **阶段 B（preparation：`pdf_path.read_bytes`
`cn_download_filing_workflow.py:220-221` 与默认/注入 Docling converter :391-395→
`docling_export.py:76-101`）明确不纳入 hard timeout、不承诺 interruptible/最终有限
结束、不用 `asyncio.timeout` 伪装**——worker 只接收 immutable/path input、零
repo/batch/token 句柄；outer cancellation 丢弃 late result（零写入）但不宣称回收
worker，记录 warning/metrics/residual；开始此阶段前若 worker 会持有 repo/batch =>
STOP 并逐名报告；
(C) **阶段 C（repository transaction）**——阶段 A/B 成功 + cancellation fence（仅
cancel_checker）后才 begin 同-core explicit repository batch，所有 blob/meta writes
在短事务窗口内；**阶段 C 无独立 hard duration timeout、不含外部 await/Docling/
provider I/O**（`provider_download_timeout_seconds` 只约束阶段 A，不约束已开始的
阶段 C）；commit 前再查 cancel_checker（precommit fence）；**staging/commit 失败
或取消在 commit-start 前 => rollback，commit-start 后 => 只按 S14-CTRL-04
journal/recovery 收敛**；CN 阶段 A/B 期间无 active token、token 只在阶段 C 存在；
SEC 无阶段 B（await-based streaming 例外，其网络与同 token 写窗口由
`provider_download_timeout_seconds` 覆盖）。

删除/修正 round 7 的冲突承诺："完整 per-filing window 包含 Docling"、"任一被
`per_filing_timeout` 覆盖的 to_thread 无有限 timeout 即 STOP"、"fake worker 自身
有限结束"、"timeout 后下一 filing 必可启动"；`test_cn_blocking_timeout` 改为
`test_cn_to_thread_boundary`（真实默认 Docling/read_bytes 在 begin_batch 前、worker
零 repo/batch 句柄、late result 零写入、provider fake 有限 timeout 可证明终止、
preparation 取消后无 token/零 publish 但后台 work 仅观测不声称终止、后续 filing 只在
容量可用时可启动、repository transaction failure/cancellation/rollback/terminal-state 测试保留）。

Terra S14-TERMINAL-FINAL-01 按 **ACCEPTED / FIXED-IN-PLAN** 处置；Terra 上一轮
S14-TERMINAL-01/02 与 MiM 三项（delete_entry/upload overwrite/CN timeout）及
`replace_source_meta`、per-filing terminal rollback/commit fence、S3 stage-delete、
upload overwrite、既有 closure 全部保持 closed 无回归。allowlist、test matrix、stop
conditions、residuals、finding table、completion 全部同步；两份 terminal final source
review（plan-terminal-final-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；最终 gate 为
Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open H/M/L=`0/0/0`。


## Temp-ownership 补充（round 9：Terra S14-TO-THREAD-FINAL-01/02 + MiM to-thread-final PASS）

to-thread final plan re-review 新增 findings（Terra
`docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-terra.md`
S14-TO-THREAD-FINAL-01/02，两项 Medium）逐项按 **ACCEPTED / FIXED-IN-PLAN** 处置；
MiM Native `docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md` 详细展开，
唯一化进 master plan S14-CTRL-12：
(F1) **修正 active Allowed/test 清单的旧 CN token/timeout 断言（闭合
S14-TO-THREAD-FINAL-01）**——`tests/fins/test_cn_download_workflow.py` 等测试修改项
不再断言"SEC/CN list/download/Docling 期间恰有同一 active token + per-filing
timeout"：SEC streaming 例外仍同 token（`provider_download_timeout_seconds` 覆盖其
网络与同 token 写窗口）；CN 阶段 A/B 无 token、阶段 C 才单 token；阶段 A
`provider_download_timeout_seconds` 超时/失败 => 零 begin（无 token、零 publish）；
阶段 B 取消仅观测后台 work（零 token、零 publish、不声称终止）；阶段 C 已 begin 后
repository transaction failure/cancel 按 commit-start 前后收敛（commit-start 前
rollback、之后 journal/recovery）；不把 SEC streaming 例外泛化给 CN。
(F2) **唯一化临时 PDF owner 与容量（闭合 S14-TO-THREAD-FINAL-02，
code-generation-ready 不实现）**——`cn_download_filing_workflow` 私有
`_read_and_unlink_temp_pdf(path, module) -> bytes`（worker 自身 `finally` 幂等
unlink `{tempdir}/dayu_cn_downloads/cninfo_*.pdf` 与 `dayu_hk_downloads/
hkexnews_*.pdf`，`delete=False`；outer cancel 也 best-effort unlink，POSIX 可撤目录
项、Windows 由 worker finally 重试；Docling converter 只接收已读 bytes 不再持 pdf
path）；阶段 B 所有 `to_thread`/`run_in_executor` 经**模块私有 bounded gate**（模块
私有有限正数默认容量，建议 1），**permit 绑定实际 inner future**（shield/完成回调，
outer 取消不提前释放、不产生无限后台 worker），worker 零 repo/batch/token；worker
永不结束时 temp/permit 保留、上限 = 配置容量/进程；新增**bounded startup stale-temp
sweep owner**（CN pipeline 构造时、任何 CN/HK provider work 前、无 active stage-B
worker，单一 runtime/process 私有 helper 持 exact temp-dir cleanup lock，只限上述
两个 `*.pdf` 形态、只删 regular 非 symlink 且 mtime 早于模块级有限 stale 阈值的
文件，unknown/symlink/lock busy fail-safe 不删并记 metrics，禁止广泛 temp sweep）；
`tests/fins/test_cn_temp_pdf_ownership.py` 加入 allowlist（worker 完成删除、outer
取消 + worker 稍后完成删除、永不结束时文件/permit 数量有界、重启 startup sweep 只删
owned stale 且不删 fresh/unknown/symlink、无 token/零 publish）。

Terra S14-TO-THREAD-FINAL-01/02 全部 **ACCEPTED / FIXED-IN-PLAN**（未提前
ACCEPTED）；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、MiM delete_entry/upload overwrite/CN
timeout、exact toolset names 及 `replace_source_meta`、per-filing terminal、S3
stage-delete、upload overwrite 全部保持 closed 无回归。allowlist、test matrix、stop
conditions、residuals、finding table、completion 全部同步；两份 to-thread final
source review（plan-to-thread-final-rereview terra/mimo-native）保持只读。master
plan 状态置 **REVIEW OBSERVATIONS FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；
最终 gate 为 Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open
H/M/L=`0/0/0`。


## Preparation-gate 补充（round 10：Terra S14-TEMP-OWNERSHIP-FINAL-01 + MiM temp-ownership-final PASS）

temp-ownership final plan re-review 新增 findings（Terra
`docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-terra.md`
S14-TEMP-OWNERSHIP-FINAL-01，一项 Medium）按 **ACCEPTED / FIXED-IN-PLAN** 处置；
MiM Native `docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md` 详细展开，
唯一化进 master plan S14-CTRL-12：
(A) **共享 `CnPreparationGate`**——私有 `CnPreparationGate`（容量有限正数默认 1）是
`DefaultFinsRuntime`/`PreparedHostRuntimeDependencies` owner 的共享实例（生产 startup
唯一 runtime；所有经 runtime direct + ingestion factory 创建的 `CnPipeline` 显式传播
同一实例、不得 per-pipeline 另建；与 `batching_repository` 同一传播链
runtime → `_build_pipeline`/`build_ingestion_service_factory` →
`get_pipeline_from_normalized_ticker` → `CnPipeline` → host protocols →
`run_cn_download_stream_impl`；Host/Agent/tool contract 不见 gate、不改 public domain
protocol/Host imports）；
(B) **slot 先于 provider 获取**——每个 CN/HK filing 在提交阶段 A provider worker 之前
先 acquire slot；等待 slot 不启动 provider、不创建临时 PDF；同一 slot 跨阶段 A provider
future 与阶段 B read+Docling 实际 inner futures、最后 inner 真正完成才 release；
(C) **阶段 A 语义**——`provider_download_timeout_seconds` 只从真正进入阶段 A 后计时
（等待 slot 不计时、零 token/临时文件/provider 调用）；阶段 A timeout/outer cancel
不能取消 provider inner future（`asyncio.shield`）；late `DownloadedReportAsset` 由
completion callback 只做 exact temp unlink + metrics 后 release slot（禁止进入
read/Docling/repo）；provider exception 后 release；正常 provider 成功继续持 slot；
(D) **阶段 B/C 时序**——`_read_and_unlink_temp_pdf` finally 删 path、再 Docling、
Docling 实际 future 完成后 release slot；outer cancel 不提前 release；slot/gate 绝不
持有 repo/batch/token；阶段 C 在 slot 正常完成/release 后 + cancel fence 才 begin
batch；
(E) **容量与进程上限**——files/workers bound = 每唯一 production runtime `<=` 容量
（生产 startup 唯一 runtime closure 保证进程实际上限；测试多 runtime 各自隔离
per-runtime gate、不宣称全 OS 进程单例，不同 runtime 仅 test isolation residual）；
(F) **startup stale-temp sweep 前置条件收紧**——只在共享 gate 尚未 admit 任何 work
（无 active slot）时持 exclusive cleanup lock 运行；
(G) **传播链 allowlist/test 扩展**——精确扩展既有 runtime → ingestion factory →
`CnPipeline` 传播链（`preparation_gate` 与 `batching_repository` 同链显式传递）；
`test_runtime_batch_injection.py` 扩展同 runtime 多 `CnPipeline` 并发断言（容量 1：
第二条 provider 前等待、temp 文件数 `<= 1`、cancel 阶段 A late asset 被 callback 删
且 slot 最终 release、cancel 阶段 B 仍按前轮）；不同 runtime 仅 test isolation
residual。

Terra S14-TEMP-OWNERSHIP-FINAL-01 按 **ACCEPTED / FIXED-IN-PLAN** 记录（未提前
ACCEPTED）；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、S14-TO-THREAD-FINAL-01/02、MiM
delete_entry/upload overwrite/CN timeout、exact toolset names 及
`replace_source_meta`、per-filing terminal、S3 stage-delete、upload overwrite 全部保持
closed 无回归。allowlist、test matrix、stop conditions、residuals、finding table、
completion 全部同步；两份 temp-ownership final source review
（plan-temp-ownership-final-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；最终 gate 为
Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open H/M/L=`0/0/0`。

## Final dual plan re-review PASS（round 11：Slice 1.4 ACCEPTED）

Terra `docs/reviews/plan-preparation-gate-final-rereview-20260810-slice-1.4-terra.md`
与 MiM Native `docs/reviews/plan-preparation-gate-final-rereview-20260810-slice-1.4-mimo-native.md`
双路 **final dual plan re-review 均 PASS / open H/M/L=`0/0/0`**；
S14-TEMP-OWNERSHIP-FINAL-01 与此前全部 findings（S14-CORRECTIVE-01/02、
S14-CLOSURE-01/02、S14-REREVIEW-02/03、S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、
S14-TO-THREAD-FINAL-01/02、MiM delete_entry/upload overwrite/CN timeout、Terra
S14-01..04、MiM M1..M5、S14-FINAL-01..04、MR1/MR2、MR3 等）全部 **CLOSED / open0**；
Slice 1.4 implementation gate 恢复（可恢复依赖 resolution、镜像拉取与实现编辑，
随后按 implementation gate 完成 unit/MinIO/静态检查验收）。状态置
**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**；两份 final dual plan re-review
source review（plan-preparation-gate-final-rereview terra/mimo-native）保持只读。
Production/tests/README/deps 冻结状态随实现 gate 恢复解冻（仅限 Slice 1.4 allowlist
内文件），其余 work unit 冻结不变。

## Gate status

- **SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**：Terra 与 MiM Native 双路 final
  dual plan re-review 均 PASS、open H/M/L=`0/0/0`；S14-TEMP-OWNERSHIP-FINAL-01 与此前
  全部 findings CLOSED；Slice 1.4 implementation gate 恢复。
- 未运行 live data/model/broker，未 commit/push/PR。
