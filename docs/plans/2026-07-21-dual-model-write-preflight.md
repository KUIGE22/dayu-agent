# Dual-Model Write Preflight Implementation Plan

> **For implementers:** execute this plan task-by-task and keep model credentials out of repository files.

**Goal:** 为现有写作流水线补齐 DeepSeek 主写、MiMo 审核模式的运行前体检，使模型配置或密钥缺失时在 Host 会话创建前失败，并向 CLI 提供不泄密的可读诊断。

**Architecture:** 复用现有 `WriteService`、scene manifest 与 `SceneExecutionAcceptancePreparer` 作为唯一配置真源。Service 根据本次运行模式选择真正可能执行的 scene 并汇总其环境变量问题，同时验证 manifest 恢复签名依赖的完整 scene 模型配置；CLI 只负责展示结果。现有 Host、Agent、审计门禁和写作流水线保持不变。

**Tech Stack:** Python 3.11、dataclasses、argparse、pytest、pyright。

---

## Task 1: 定义稳定的体检契约

**Files:**
- Modify: `dayu/services/contracts.py`
- Modify: `dayu/services/protocols.py`
- Test: `tests/application/test_write_service.py`

1. 为体检结果、scene 模型选择和问题项增加类型明确的 Service DTO。
2. 在 `WriteServiceProtocol` 增加同步 `preflight()` 契约。
3. 先写测试，验证结果不包含环境变量值。

## Task 2: 实现模式感知的 Service 体检

**Files:**
- Modify: `dayu/services/write_service.py`
- Test: `tests/application/test_write_service.py`

1. 根据 `infer`、`fast`、章节过滤和完整报告模式选择所需 scene。
2. 复用现有 scene 解析器解析主写与审核模型。
3. 汇总缺失环境变量和模型配置错误。
4. `run()` 在创建 Host session 前执行同一体检；失败时抛出带结构化结果的明确异常。
5. 成功结果复用于流水线，避免体检和执行使用不同模型解析结果。

## Task 3: 接入 CLI 显示与仅体检模式

**Files:**
- Modify: `dayu/cli/arg_parsing.py`
- Modify: `dayu/cli/commands/write.py`
- Modify: `dayu/cli/dependency_setup.py`
- Test: `tests/engine/test_cli_running_config.py`

1. 增加 `write --preflight-only`。
2. 输出每个相关 scene 的模型名称、温度和所需环境变量名称，不输出密钥值。
3. 体检失败返回退出码 2，成功返回 0；仅体检模式不得启动 Host run。
4. 普通写作体检失败使用同一诊断格式。

## Task 4: 文档、回归和静态检查

**Files:**
- Modify: `README.md`
- Modify: `dayu/config/README.md`

1. 写出 DeepSeek 主写、MiMo 审核的命令示例和失败语义。
2. 运行相关 pytest 文件与新增测试。
3. 运行受影响文件的 pyright。
4. 检查 git diff，确认没有改动 Host、Agent、交易权限或用户原有文件。

## Task 5: 双模型最终复核

1. 把最终 diff 摘要交给 DeepSeek 检查结构、重复实现和成本风险。
2. 把最终 diff 摘要交给 MiMo 检查失败语义、审计边界和遗漏测试。
3. 只采纳与现有分层和 MVP 目标一致的意见，再跑一次验证。
