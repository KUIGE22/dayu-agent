# 大愚 Agent — 用户手册

`大愚 Agent` 是每个投资者的助理分析师。  
- `大愚 Agent` 是一个面向买方财报分析场景的 Agent 系统，但它不是简单的功能组合，`大愚 Agent` 让AI读财报的方式从丢给它整份财报“大海捞针”变成“按图索骥”，让数据有置信度，让投资结论、投资报告可审计、可追踪。  
- `大愚 Agent` 还具备完整的“宿主强约束下的 LLM in the loop 的能力”，基础架构能力上已经对齐 OpenClaw ，后续会加上现在 OpenClaw 能做的事情。

当前你可以用它完成四类工作：
- 财报数据管线：美股 / A 股 / 港股财报下载，美股 / A 股 / 港股财报上传。
- 投研问答：下载、上传财报后，执行 `prompt` 单次提问、`interactive` 多轮提问、或通过微信向`大愚 Agent` 提问。
- 买方分析报告写作：下载、上传财报后，执行 `write` 写作。
- 结果渲染：把 Markdown 报告渲染为 HTML / PDF / Word。

本文档面向读者：
- 最终使用者。

如果你要参与开发，而不是只使用系统：
- 总览开发手册：[dayu/README.md](dayu/README.md)
- Host 手册：[dayu/host/README.md](dayu/host/README.md)
- Engine 手册：[dayu/engine/README.md](dayu/engine/README.md)
- Fins 手册：[dayu/fins/README.md](dayu/fins/README.md)
- 配置手册：[dayu/config/README.md](dayu/config/README.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)

## 0. 如果你想参与项目
- 定性分析模板 读起来机械感还很强，还没写出差异化：
  - 同一章节里，不同行业公司写出明显不同的判断路径。
  - 同一行业里，不同公司写出公司自己的特殊结构变量。
- 位于 Engine 的 web tools 现在的对抗challenge能力很弱，很多网站无法访问。
- **GUI 尚未实现**；
- **Web UI 已支持自选股、财报下载和交互式分析，仍处于早期阶段**。
- **WeChat UI 仅支持文本消息首版，还可添加更多好玩的功能**。
- 财报电话会议记录音频转录文字后信息提取（起码要区分信息来自提问还是回答）尚未实现。
- 财报presentation信息提取尚未实现。
- 欢迎围绕以下方向提交 issue 或 PR：
  - 普通文件（非财报文件）信息提取还需要优化。
  - 优化 Fins 里的港股/A股/美股财报信息提取。
  - Durable memory / Retrieval layer（ Memory只实现了working memory 和 episode summary ）。
  - FMP 工具（调研工作已做，见 [docs/fmp_integration_research.md](docs/fmp_integration_research.md) ）尚未实现。
  - 更多LLM 工具。

## 1. 五分钟快速开始

### 1.1 安装

安装使用 `大愚 Agent` 前需安装 Python 3.11。

#### 1.1.1 在线安装

如果你当前机器可以联网，可以直接通过 `pip` 安装稳定版 wheel。

命令格式：

```bash
python -m pip install https://github.com/noho/dayu-agent/releases/download/<version>/dayu_agent-<version>-py3-none-any.whl
```

示例（替换为最新版本号）：

```bash
python -m pip install https://github.com/noho/dayu-agent/releases/download/v0.1.4/dayu_agent-0.1.4-py3-none-any.whl
```

这种方式最轻，但安装耗时和成功率会受网络、平台和上游依赖发布状态影响。最新稳定版请以 [Releases](https://github.com/noho/dayu-agent/releases) 页面为准，复制对应版本的 wheel URL。

如需安装 `main` 分支开发版（nightly），可以直接从 Git 安装：

```bash
python -m pip install --upgrade --force-reinstall "git+https://github.com/noho/dayu-agent.git@main"
```

也可以使用 `uv tool` 安装，让 `uv` 独立管理工具环境和 Python 3.11。`uv` 的安装方法请参考 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

```bash
uv tool install --force --managed-python --python 3.11 \
  "dayu-agent @ https://github.com/noho/dayu-agent/releases/download/<version>/dayu_agent-<version>-py3-none-any.whl"
```

安装 `main` 分支开发版（nightly）：

```bash
uv tool install --force --refresh --managed-python --python 3.11 \
  "git+https://github.com/noho/dayu-agent.git@main"
```

`uv tool install --force` 会替换已有的同名 `dayu-agent` 工具环境，但不会覆盖已有工作区数据和配置。安装后可用以下命令查看安装来源：

```bash
uv tool list --show-version-specifiers --show-python
```

#### 1.1.2 离线安装

从 [Releases](https://github.com/noho/dayu-agent/releases) 页面下载对应平台的离线安装包：

- Mac ARM芯片：`dayu-agent-<version>-macos-arm64-offline.tar.gz`
- Mac Intel芯片：`dayu-agent-<version>-macos-x64-offline.tar.gz`
- Windows：`dayu-agent-<version>-windows-x64-offline.zip`

Linux 用户请使用在线 wheel 安装或源码安装；当前不发布 Linux 离线安装包。

macOS 示例：

```bash
tar -xzf dayu-agent-0.1.4-macos-arm64-offline.tar.gz
cd dayu-agent-0.1.4-macos-arm64-offline
./install.sh
```

Windows PowerShell 示例：

```powershell
Expand-Archive .\dayu-agent-0.1.4-windows-x64-offline.zip -DestinationPath .
cd .\dayu-agent-0.1.4-windows-x64-offline
.\install.cmd
```
#### 1.1.3 clone 源代码安装

如果你要参与开发或本地调试源码，可以 clone 源代码后使用 editable 安装：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[test,dev,browser,web]" -c constraints/lock-macos-arm64-py311.txt
```

说明：

- macOS Intel 开发环境改用 `constraints/lock-macos-x64-py311.txt`
- Linux 开发环境改用 `constraints/lock-linux-x64-py311.txt`
- Windows 开发环境改用 `constraints/lock-windows-x64-py311.txt`
- `web` extras 启用 `dayu-web`（streamlit）入口；不需要 Web UI 时可从 extras 列表中省略

#### 1.1.4 安装额外依赖

安装完成后，还需要执行一次：  

```bash
playwright install chromium
```

如需使用 `dayu-render` 将 Markdown 导出为 **HTML、Word（.docx）或 PDF**，需要安装 `pandoc`，详见「§6 渲染输出」。可选安装方式：

- macOS：`brew install pandoc`
- Ubuntu / Debian：`sudo apt-get install pandoc`
- Windows：`choco install pandoc` 或从 [pandoc 官网](https://pandoc.org/installing.html) 下载安装

### 1.2 验证安装

安装完成后，先确认命令入口可用：

```bash
dayu-cli --help
dayu-wechat --help
dayu-render --help
```

`dayu-web` 入口需要先安装 `[web]` extras（参考 1.1.3 节示例命令），再执行：

```bash
dayu-web --help
```

### 1.3 初始化工作区与配置

安装后运行一次 `init`，交互式完成配置复制、模型供应商选择和 API Key 设置：

```bash
dayu-cli init
```

`init` 会依次执行：

1. 复制包内默认配置到 `./workspace/config/` ，复制包内默认写作模板到 `./workspace/assets/` 。
2. 让你选择初始化模型方案（Mimo / DeepSeek / OpenAI / Anthropic / Gemini / 通义千问 / 本地 Ollama / 自定义 OpenAI 兼容 API）。选中 Mimo / DeepSeek / Google Gemini 后会进入二级菜单挑选具体型号：
   - Mimo：Token Plan（默认）/ Token Plan SG / Pro 三档，三档各自独立 API Key
   - DeepSeek：Pro（默认）/ Flash 两档，共享 `DEEPSEEK_API_KEY`
   - Gemini：`gemini-2.5-flash`（默认）/ `gemini-2.5-pro` / `gemini-2.5-flash-lite` / `gemini-3.1-pro-preview` / `gemini-3.1-flash-lite-preview`
3. 输入对应 API Key 并永久写入环境变量。
4. 可选配置联网检索 API Key（TAVILY / SERPER / FMP）
5. 自动检测 HuggingFace 官方 Hub 连通性：不可达时默认启用镜像加速，可达时默认跳过。可选配置 `HF_TOKEN` 提升下载稳定性。
6. 自动配置 `transformers` / `huggingface_hub` / `tqdm` 输出降噪环境变量，避免下载进度打断终端状态栏。


可选参数：

```bash
dayu-cli init --base ./my_workspace    # 指定工作区目录（默认 ./workspace）
dayu-cli init --reset                  # 删除 .dayu / config / assets 后重新初始化
dayu-cli init --overwrite              # 覆盖已有配置
```

API Key 申请地址：
- MIMO_PLAN_API_KEY / MIMO_PLAN_SG_API_KEY / MIMO_API_KEY：https://platform.xiaomimimo.com/#/console/api-keys
- DEEPSEEK_API_KEY：https://platform.deepseek.com/api_keys
- FMP_API_KEY：https://site.financialmodelingprep.com/developer/docs/dashboard
- TAVILY_API_KEY：https://app.tavily.com/home
- SERPER_API_KEY：https://serper.dev/

说明：
- Anthropic 默认调用官方 `https://api.anthropic.com/v1/messages`，并原生支持文本、thinking、工具参数与 usage 的 SSE 增量；使用兼容代理时可设置 `ANTHROPIC_BASE_URL`，系统会自动补全 `/v1/messages`。
- 默认推荐 Mimo Token Plan（mimo-v2.5-pro-plan），性价比最优。（注： MIMO_PLAN_API_KEY / MIMO_API_KEY 是两个不同的KEY，不能混用）。
- 海外用户选Mimo Token Plan SG。
- 如需接入 OpenRouter 等聚合服务，可在 `init` 中选择”自定义 OpenAI 兼容 API”，填写 `CUSTOM_OPENAI_API_KEY`、Base URL、模型 ID 与最大上下文 tokens。
- 本地 Ollama 模型和自定义 OpenAI 兼容 API 在 `init` 时会根据最大上下文 tokens 自动配置 `conversation_memory`（>= 100 万 tokens 扩大工作记忆上限，< 100 万收紧情景记忆预算）；Ollama 的 `write_chapter` 并发 lane 默认设为 2。
- `--reset` 确认后会删除 `workspace/.dayu/`、`workspace/config/`、`workspace/assets/`，再按首次初始化流程重建；它比 `--overwrite` 更彻底，会一并清空运行时状态。
- 升级 dayu 后若运行命令时看到 `HostStore 检测到旧版 SQLite schema 与当前实现不兼容` 报错，按提示处理：优先删除报错信息里 `db_path` 指向的数据库文件后重启（仅丢失 host 运行状态，保留 conversation 历史与 `run.json`）；如果不方便定位也可以直接跑 `dayu-cli init --reset` 完整重建工作区。
- 联网搜索默认可走 `auto`，若配置了 Tavily / Serper，会优先使用对应 provider。
- 若运行环境需要访问 `localhost`、私网 IP 或内网域名，可在 `workspace/config/run.json` 的 `web_tools_config.allow_private_network_url` 中显式打开内网访问开关。
- 修改默认模型请参考 [8. 模型配置](#model-config)。

工作区最重要的目录：

```text
workspace/
├── config/           # 运行时配置（覆盖包内默认配置）
├── assets/           # 定性分析模板（覆盖包内默认模板）
├── .dayu/            # 系统隐藏工作目录（batch 暂存、备份恢复等）
├── portfolio/        # 每个 ticker 的财报与材料
├── draft/            # write 输出目录
└── output/           # tool trace 等辅助输出
```

说明：`workspace/.dayu/` 由系统自动维护，当前会承载财报仓储的 batch 暂存与 crash recovery 备份；不需要手动创建或清理。如果运行有异常全部删除也没有影响。  

### 1.4 跑通第一条命令

推荐先下载一份财报：

```bash
dayu-cli download --ticker AAPL
```

下载完成后，再跑一条单次 prompt：

```bash
dayu-cli prompt "总结最新财报的主要风险" --ticker AAPL
```

如果你已经通过 `download`、`upload_filing` 或 `upload_filings_from` 导入过 AAPL 的财报，也可以直接提问；命令会自动检测本地财报并挂载财报工具后返回结果。

如果你希望先不指定 `ticker`，也可以这样写：

```bash
dayu-cli prompt "总结苹果最新财报的主要风险"
```

> 也可在微信对话或`interactive`里发送"下载苹果财报"进行下载。


## 2. 系统入口总览

### 2.1 CLI 入口

统一入口：

```bash
dayu-cli <subcommand> [参数]
```

直接执行 `dayu-cli` 会打印总帮助和全部子命令简介；需要查看某个子命令的完整参数时，继续使用 `dayu-cli <subcommand> --help`。

当前支持的主命令：

| 命令 | 用途 |
|------|------|
| `prompt` | 单次问答 |
| `interactive` | 交互式终端对话 |
| `write` | 自动逐章写作报告；传 `--summary` 时打印上次写作结果摘要 |
| `download` | 下载 filings |
| `upload_filing` | 上传单份财报 |
| `upload_filings_from` | 扫描目录并生成批量上传脚本 |
| `upload_material` | 上传补充材料 |
| `process` | 全量预处理（最终用户可无视） |
| `process_filing` | 预处理单份 filing（最终用户可无视） |
| `process_material` | 预处理单份 material（最终用户可无视） |
| `conv` | 管理带 label 的可恢复 CLI 对话（最终用户可无视） |
| `sessions` | 列出或关闭宿主会话（最终用户可无视） |
| `runs` | 列出运行记录（最终用户可无视） |
| `cancel` | 取消运行中的 run（最终用户可无视） |
| `host` | 宿主维护（清理孤儿运行/查看状态，最终用户可无视） |
> 注：预处理命令仅供开发使用，最终用户可忽略。

共享参数：

| 参数 | 适用命令 | 说明 |
|------|------|------|
| `--base` | 全部主命令 | 工作区根目录，默认 `./workspace` |
| `--config` | 全部主命令 | 配置目录，默认 `workspace/config` |
| `--ticker` | `prompt` `write` | 股票代码；传入后会把该 `ticker` 作为当前研究对象 |
| `--log-level` | 全部主命令 | 直接指定日志级别，可选 `debug`、`verbose`、`info`、`warn`、`error` |
| `--debug` | 全部主命令 | 把日志级别设为 `DEBUG` |
| `--verbose` | 全部主命令 | 把日志级别设为 `VERBOSE` |
| `--info` | 全部主命令 | 把日志级别设为 `INFO` |
| `--quiet` | 全部主命令 | 把日志级别设为 `ERROR` |
| `--model-name` | `prompt` `interactive` `write` | 指定模型配置名称 |
| `--temperature` | `prompt` `interactive` `write` | 覆盖模型 temperature |
| `--label` | `prompt` `interactive` | 把当前对话绑定到可恢复 label；`prompt` 会进入 labeled multi-turn，对应 scene 为 `prompt_mt` |
| `--new-session` | `interactive` | 不续接上一次 interactive 多轮会话，改为从头开始一个新会话 |
| `--web-provider` | `prompt` `interactive` `write` | 指定联网检索 provider，如 `auto`、`tavily`、`serper`、`duckduckgo` |
| `--enable-tool-trace` | `prompt` `interactive` `write` | 开启工具调用追踪，覆盖 `run.json` 中的 trace 配置 |
| `--tool-trace-dir` | `prompt` `interactive` `write` | 指定 trace 输出目录，覆盖 `run.json` 中的 trace 配置 |
| `--thinking` / `--no-thinking` | `prompt` `interactive` | 控制是否在终端回显模型思考过程 |

说明：
- `--log-level`、`--debug`、`--verbose`、`--info`、`--quiet` 是同一组日志参数，使用其一即可。
- `prompt`、`interactive`、`write` 还支持更多 Agent 运行参数，例如 `--tool-timeout-seconds`、`--max-iterations`、`--doc-limits-json`、`--fins-limits-json`；需要时可用 `dayu-cli <subcommand> --help` 查看完整列表。
- 宿主管理命令同样支持 `--base` / `--config` / 日志参数；例如 `dayu-cli host --base ./workspace status`、`dayu-cli sessions --base ./workspace --source cli --scene interactive`、`dayu-cli conv --base ./workspace list`。
- `interactive` 默认会续接本地绑定的同一个多轮会话；如果上一次回答还没完整回显到终端，重启 CLI 会先把那次回答补完，再进入新的输入循环。

### 2.2 Web 入口（Streamlit）

基于 Streamlit 的 Web UI，可在浏览器中管理自选股、下载财报并进行按 ticker 绑定历史的交互式分析：

```bash
dayu-web
```

也可以用模块入口启动（等价）：

```bash
python -m dayu.web
```

默认使用 `./workspace` 作为工作区

启动后，默认打开 Local URL: http://localhost:8501 （如果 8501 端口被占用将按尝试其他端口）

功能说明：详见[dayu/web/README.md](dayu/web/README.md)

### 2.3 WeChat 入口

统一入口：

```bash
dayu-wechat <command> [参数]
```

直接执行 `dayu-wechat` 会打印总帮助和全部命令简介；需要查看某个命令的完整参数时，继续使用 `dayu-wechat <command> --help`。

当前支持的命令：

| 命令 | 用途 |
|------|------|
| `login` | 扫码建立微信登录态 |
| `run` | 以前台方式运行微信问答 daemon |
| `service install` | 安装后台托管配置 |
| `service start` | 启动后台托管 |
| `service restart` | 重启后台托管 |
| `service stop` | 停止后台托管 |
| `service status` | 查看后台托管状态 |
| `service list` | 列出当前 workspace 下已安装的后台托管实例 |
| `service uninstall` | 删除后台托管配置 |

常用参数：

| 参数 | 适用命令 | 说明 |
|------|------|------|
| `--base` | 全部命令 | 工作区根目录，默认 `./workspace` |
| `--config` | `login` `run` `service install` | 配置目录，默认 `workspace/config` |
| `--label` | 全部命令 | WeChat 实例标签，默认 `default`；状态目录映射到 `<base>/.dayu/wechat-<label>` |
| `--relogin` | `login` | 忽略已有登录态，强制重新扫码 |
| `--qrcode-timeout-sec` | `login` | 扫码登录超时秒数 |
| `--model-name` | `run` `service install` | 指定模型配置名称 |
| `--temperature` | `run` `service install` | 覆盖模型 temperature |
| `--web-provider` | `run` `service install` | 指定联网检索 provider |
| `--debug-sse` | `run` `service install` | 开启 SSE 高频调试日志 |
| `--debug-tool-delta` | `run` `service install` | 开启工具调用参数增量日志 |
| `--debug-sse-sample-rate` | `run` `service install` | 设置 SSE 调试日志采样率 |
| `--debug-sse-throttle-sec` | `run` `service install` | 设置 SSE 调试日志节流窗口 |
| `--tool-timeout-seconds` | `run` `service install` | 覆盖工具超时 |
| `--max-iterations` | `run` `service install` | 覆盖 Agent 最大迭代次数 |
| `--fallback-mode` | `run` `service install` | 覆盖超限处理模式 |
| `--fallback-prompt` | `run` `service install` | 覆盖超限补充提示 |
| `--max-consecutive-failed-tool-batches` | `run` `service install` | 覆盖连续失败工具批次上限 |
| `--max-duplicate-tool-calls` | `run` `service install` | 覆盖重复工具调用连续上限 |
| `--duplicate-tool-hint-prompt` | `run` `service install` | 覆盖重复工具调用提示词 |
| `--enable-tool-trace` | `run` `service install` | 开启工具调用追踪 |
| `--tool-trace-dir` | `run` `service install` | 指定 trace 输出目录 |
| `--doc-limits-json` | `run` `service install` | 覆盖文档工具 limits |
| `--fins-limits-json` | `run` `service install` | 覆盖财报工具 limits |
| `--typing-interval-sec` | `run` `service install` | 控制 typing 提示发送间隔 |
| `--delivery-max-attempts` | `run` `service install` | 控制微信 reply delivery 的最大发送次数 |

说明：
- `login` 用于建立或刷新登录态。
- `run` 用于在当前终端以前台方式运行。
- 同一个 `--label` 对应同一个 `state_dir`；当前实现会对 `state_dir` 加 daemon 单实例锁，避免前台 `run` 和后台 service 或两个前台进程并发运行导致重复补发。
- `service install/start/stop/status/list/uninstall` 用于以后台服务的形式运行。
- Windows 目前不支持 `service` 相关命令；在 Windows 上可继续使用 `login` 和 `run`。

## 3. 最常用工作流

### 3.1 财报下载：`download`

命令用途：
下载美股、A 股或港股财报到本地工作区，供后续问答、对话和写作复用。
A 股使用巨潮主源，港股使用披露易主源。

参数 / 说明：

| 参数 | 说明 |
|------|------|
| `--ticker` | 必填，股票代码，传入半角逗号分隔的股票代码标识有多地上市 |
| `--forms` | 可选，指定表单类型，如 `10K`、`10Q`、`DEF14A` |
| `--start` | 可选，开始日期，支持 `YYYY`、`YYYY-MM`、`YYYY-MM-DD` |
| `--end` | 可选，结束日期，支持 `YYYY`、`YYYY-MM`、`YYYY-MM-DD` |
| `--overwrite` | 可选，覆盖本地已存在结果 |
| `--rebuild` | 可选，只基于本地已下载文件重建 `meta/manifest`，不重新下载 |
| `--infer` | 可选，使用 FMP 推断跨市场 alias；成功时与 SEC alias 合并，失败时回退到 `--ticker` CSV 中的显式 alias |
| `--base` | 可选，工作区根目录，默认 `./workspace` |
| `--config` | 可选，配置目录，默认 `workspace/config` |

命令示例：

```bash
dayu-cli download --ticker AAPL
```

常见命令示例：

```bash
dayu-cli download --ticker AAPL --forms 10K 10Q --start 2024 --end 2025
dayu-cli download --ticker AAPL --forms 10K
dayu-cli download --ticker AAPL --rebuild
dayu-cli download --ticker 600519 --forms FY H1 Q1 Q2 Q3 Q4 --start 2024 --end 2026
dayu-cli download --ticker 0700 --forms FY H1 Q1 Q2 Q3 Q4 --start 2024 --end 2026
dayu-cli download --ticker 0700 --rebuild
dayu-cli download --ticker BABA,9988,9988.HK --infer
```

命令说明：
- `download` 会根据 `ticker` 自动路由到对应市场。
- `download`、`upload_filing`、`upload_material`、`upload_filings_from` 的 `--ticker` 支持 CSV（半角逗号分隔）；CSV 中**每个 token 都会走真源归一化**（如 `9988.HK`→`9988`）后再整体去重。首个归一化结果作为 canonical ticker，其余作为显式 alias 写入 meta，便于工具后续用任意跨市场变形命中同一公司。
- `--ticker` 支持 `0700.HK` / `HK.00700` / `600519.SH` / `sh600519` / `AAPL.US` / `BRK.B` 等常见变形，内部统一归一化到裸码（港 4 位补零、沪深 6 位、美股类股分隔符统一为横杠，如 `BRK.B`→`BRK-B`）。公司名仍可作为 ticker 传入，由仓储 alias 查表兜底。
- 显式传 `--infer` 时，CLI 会把 `--ticker` 里的显式 alias 与 FMP infer 结果合并；`download` 场景下 pipeline 还会继续与 SEC 返回的 alias 合并。
- 美股下载未显式传 `--start` 时，年报（`10-K`/`20-F`）默认覆盖 5 年，季报（`10-Q`/季报型 `6-K`）默认覆盖 2 年；`8-K`、SC13 等事件类表单仍按各自默认窗口处理。
- A 股下载当前使用巨潮主源，港股下载当前使用披露易主源，默认 forms 均为 `FY H1 Q1 Q2 Q3 Q4`；未显式传 `--start` 时，年报默认覆盖 5 年，半年报/季报默认覆盖 2 年；`Q2` 与 `H1`、`Q4` 与 `FY` 均作为独立期间处理，不互相归一。CN/HK 下载默认只保留中文/繁中文财报候选，英文财报会在 discovery 阶段过滤。下载完成定义为 PDF 落盘、`_docling.json` 落盘、source meta `ingest_complete=True` 且 `primary_document` 指向 `_docling.json`。中断后再次运行会优先复用已落盘 PDF，避免重复下载；`--rebuild` 只基于本地已下载的 PDF + Docling JSON 重建 meta/manifest，不访问主源。
- 港股 ticker 示例 `0700` / `00700` / `700.HK` 会归一化到同一 canonical ticker；A 股/港股缺失的独立季度报告会按 skipped 统计而不是 failed。
- 使用 `--infer` 功能需要申请FMP_API_KEY。
- 首次写入时会自动创建 `workspace/portfolio/{ticker}` 下的源文档目录，不要求你预先手动建好 `filings/`。
- `prompt`、`interactive` 在 `filings/` 缺失时不会直接退出；CLI 会提示当前无本地财报，并继续执行问答。
- 美股 / A 股 / 港股下载分别使用独立并发 lane；默认配置下同一市场下载串行执行，不同市场互不占用对方的下载许可。
- **也可在interactive / wechat中发送`下载xx公司财报`进行下载**

### 3.2 上传本地文件

命令用途：
上传本地下载好的财报。（A 股可通过 `download` 直接从巨潮下载；港股可通过 `download` 直接从披露易下载，也仍可上传本地整理的文件。）
把你已经准备好的补充材料纳入工作区，适合手动整理 PDF、电话会纪要、演示材料等场景。

参数 / 说明：

| 命令 | 关键参数 | 说明 |
|------|------|------|
| `upload_filing` | `--ticker` `--files` `--fiscal-year` `--fiscal-period` | 上传单份财报；`--action` 可选，默认按 document_id 自动判定 |
| `upload_filings_from` | `--ticker` `--from` | 扫描目录并生成批量上传脚本 |
| `upload_material` | `--ticker` `--forms` `--material-name` `--files` | 上传补充材料；`--action` 可选，`--fiscal-year/--fiscal-period` 可选并参与稳定 document_id 生成 |

命令示例：

```bash
dayu-cli upload_filing \
  --ticker 0300 \
  --files ./tmp/美的2025Q1.pdf \
  --fiscal-year 2025 \
  --fiscal-period Q1 \
  --company-name 美的集团
```

常见命令示例：

```bash
dayu-cli upload_filings_from \
  --ticker 0300 \
  --from ./workspace/source

dayu-cli upload_filing \
  --ticker BABA,9988 \
  --files ./tmp/alibaba_2025_q1.pdf \
  --fiscal-year 2025 \
  --fiscal-period Q1 \
  --infer

dayu-cli upload_material \
  --ticker AAPL \
  --forms EARNINGS_CALL \
  --material-name deck \
  --files ./tmp/deck.pdf
```

命令说明：
- `upload_filing` 和 `upload_material` 的 `--action` 现在都可省略；省略时会先按稳定 `document_id` 查工作区：不存在则 `create`，存在则 `update`，若原始上传文件指纹未变化则会在 Docling convert 前直接 `skip`。自动判定只覆盖 `create/update`；若要删除，必须显式传 `--action delete`。
- `upload_filing` 适合单份补录；每个 `ticker` 第一次上传财报时需要 `--company-name`，若显式传 `--infer`，则在工作区缺少公司级 `meta.json` 时可省略 `--company-name`，由 FMP 推断后补齐；若同时传了 `--company-name`，则以你显式传入的值为准；若 infer 失败且仍缺 `--company-name`，命令会直接失败。
- `upload_material` 的稳定 `document_id` 默认由 `form_type + material_name` 生成；若显式提供 `--fiscal-year/--fiscal-period`，它们也会参与 ID 生成。material 场景下 `document_id` 与 `internal_document_id` 恒等；显式传 `--document-id/--internal-document-id` 时，必须与这套稳定规则一致。
- `upload_filings_from` 不直接上传文件，而是先生成一份适配当前运行平台的可执行脚本；macOS / Linux 默认生成 `.sh`，Windows 默认生成 `.cmd`。
- `upload_filings_from` 未传 `--output` 时，默认把脚本写到 `--base` 指向的 workspace 根目录，文件名为 `upload_filings_{ticker}.sh` / `.cmd`。
- `upload_filings_from --infer` 只会在脚本生成阶段调用一次 FMP，并把“显式 CSV alias + infer alias”的合并结果，以及最终公司名直接 bake 到脚本正文；脚本头部的重生成命令仍会保留原始 `--ticker` 输入和 `--infer`。
- 使用 `--infer` 功能需要申请FMP_API_KEY。
- 生成脚本头部会附带一条注释形式的 `python -m dayu.cli upload_filings_from ...` 重跑命令；脚本正文里的批量上传命令也统一使用 `python -m dayu.cli`，这样在源码工作区里执行时不会依赖外部 `dayu-cli` entrypoint。
- `upload_filings_from` 默认不会在脚本正文里写死 `--action`，这样每条命令都会在执行时按当前工作区状态自动判定 `create/update/skip`；只有你显式传了 `--action`，生成脚本才会固定动作。
- 生成脚本中的每条上传命令都会透传脚本调用时的额外参数；macOS / Linux 使用 `"$@"`，Windows 使用 `%*`，因此可直接执行 `./upload_filings_xxx.sh --overwrite` 之类的批量覆盖调用。
- `upload_filing --overwrite` 和 `upload_material --overwrite` 会先重置当前 `document_id` 的源文档存储，再完整重建该文档；不会像 SEC download 的 ticker 级 overwrite 那样清空同 ticker 下的其他文档。
- `upload_filing` 和 `upload_material` 在首次实际写入时会自动创建 `workspace/portfolio/{ticker}` 下的源文档目录；`upload_filings_from` 只生成批量上传脚本，不直接写入源文档。

### 3.3 单次问答：`prompt`

命令用途：
执行一次性提问，适合快速验证观点、提炼结论或补充某个具体问题。

参数 / 说明：

| 参数 | 说明 |
|------|------|
| `prompt` | 必填，单次执行的问题文本 |
| `--ticker` | 可选，指定研究对象 |
| `--label` | 可选，把本次提问绑定到可恢复 conversation；首次创建时 scene 为 `prompt_mt` |
| `--model-name` | 可选，指定模型配置 |
| `--temperature` | 可选，覆盖模型 temperature |
| `--thinking` / `--no-thinking` | 可选，控制是否回显模型思考过程 |
| `--debug` / `--verbose` | 可选，仅调整日志级别，不改变会话行为 |

命令示例：

```bash
dayu-cli prompt "总结苹果最新财报中的主要风险"
```

常见命令示例：

```bash
dayu-cli prompt "总结最新财报中的主要风险" --ticker AAPL
dayu-cli prompt "总结苹果最新财报中的主要风险" --thinking
dayu-cli prompt --label apple "先总结苹果最新财报中的主要风险"
dayu-cli prompt "总结苹果最新财报中的主要风险" --model-name mimo-v2.5-pro
dayu-cli prompt "总结苹果最新财报中的主要风险" --debug
```

命令说明：
- 使用之前请先下载/上传财报。
- 两种写法都可以：要么在问题里直接写公司名或股票代码，要么用 `--ticker` 明确指定研究对象；一般不需要两边重复写。
- 不带 `--label` 时，`prompt` 保持 one-shot，不承诺后续恢复；带 `--label` 时，本次提问会挂到该 label 对应的可恢复 conversation 上，后续可继续用 `prompt --label <label>` 或 `interactive --label <label>` 接着问。
- 带 `--label` 的 prompt 在本轮拿到最终回答前会独占该 label；如果另一个进程此时也尝试复用同一个 label，CLI 会直接报错并提示等待当前对话结束，或改用新的 `--label`。
- 默认不回显模型思考过程；如需在终端查看，显式传 `--thinking`。

### 3.4 交互式对话：`interactive`

命令用途：
启动一个终端会话，多轮会话连续追问，适合逐步拆解问题。

参数 / 说明：

| 参数 | 说明 |
|------|------|
| `--model-name` | 可选，指定模型配置 |
| `--temperature` | 可选，覆盖模型 temperature |
| `--thinking` / `--no-thinking` | 可选，控制是否回显模型思考过程 |
| `--label` | 可选，恢复或创建指定 label 的可复用 conversation；首次创建时 scene 为 `interactive` |
| `--new-session` | 可选，不续接上一次多轮会话，改为从头开始一个新会话 |
| `--debug` / `--verbose` | 可选，仅调整日志级别，不改变会话行为 |

命令示例：

```bash
dayu-cli interactive
```

常见命令示例：

```bash
dayu-cli interactive --model-name mimo-v2.5-pro
dayu-cli interactive --temperature 0.2
dayu-cli interactive --thinking
dayu-cli interactive --label apple
dayu-cli interactive --new-session
dayu-cli sessions --source cli --scene interactive
dayu-cli conv status --label apple
dayu-cli interactive --verbose
```

命令说明：
- 使用之前请先下载/上传财报。
- `interactive` 默认每次进入都会续接同一个多轮会话，适合连续追问。
- `interactive` 会把当前会话绑定保存在 `<workspace>/.dayu/interactive/state.json`，重新启动时默认续接上一次会话历史。
- 如果你想从头开始一轮新的对话，显式传 `--new-session`；它会丢弃本地保存的旧会话绑定，改为新开一个会话。
- 如果你想显式复用某条长期对话，使用 `--label`。同一个 label 可在 `prompt --label` 与 `interactive --label` 之间互通；第一次通过 `prompt --label` 创建的会话底层 scene 为 `prompt_mt`，第一次通过 `interactive --label` 创建的会话底层 scene 为 `interactive`，之后恢复时沿用首次创建时的 scene。
- 带 `--label` 的 CLI 启动时，会明确提示当前是“新创建标签”还是“恢复标签”；`prompt --label` 在回答末尾还会再次打印标签提示框，方便你后续继续复用同一个 label。
- 同一个 label 在任意时刻只能被一个 CLI 进程占用：`interactive --label` 会在整个 REPL 生命周期内持有该 label，直到双 `Ctrl+D` 完整退出；`prompt --label` 会在本轮返回最终回答前持有该 label。若命中占用中的 label，CLI 会提示你等待当前对话结束后重试，或改用新的 `--label`。
- 如果你在 workspace 本地覆写了 `prompt_mt` 或其他带 label 会命中的 scene manifest，必须保留 `conversation.enabled=true`；否则 CLI 会直接拒绝执行该 labeled conversation。
- 如果某个 label 对应的底层 session 已经被 `dayu-cli sessions close` 关闭，下次再用同名 `--label` 时，CLI 会先提示“旧对话已关闭”，再按全新对话重新创建该 label；如果你是通过 `conv remove --label` 主动释放 label，则下次直接按普通新建处理，不额外提示。
- 如果你想查看底层 Host session，可用 `dayu-cli sessions --source cli --scene interactive` 或 `dayu-cli sessions --source cli --scene prompt_mt`；如果你想查看或释放 label 到会话的映射，使用 `dayu-cli conv list`、`dayu-cli conv list --all`、`dayu-cli conv status --label <label>` 与 `dayu-cli conv remove --label <label>`。其中 `conv list` 默认只展示 active 的 labeled conversation，`conv list --all` 额外包含已关闭对话；若某个 label 的 registry record 已漂移到不存在的 Host session，CLI 会先自动清理再继续执行，不再展示 `missing`。`conv remove --label` 会先关闭底层 session（若仍存在），再释放该 label；之后同名 `--label` 会从全新对话开始。若你通过 `sessions close` 关闭了某个带 label 的底层 session，下次同名 `--label` 会在提示后创建新的会话，而不是恢复旧 transcript。若你需要诊断底层 `session_id`，请用 `conv status --label <label>` 或直接查看 `sessions`。
- 默认不回显模型思考过程；如需在终端查看，显式传 `--thinking`。

### 3.5 微信对话 daemon：

命令用途：
以ClawBot的形式运行微信问答通道。

参数 / 说明：

| 命令 | 关键参数 | 说明 |
|------|------|------|
| `login` | `--label` `--relogin` `--qrcode-timeout-sec` | 建立或刷新登录态 |
| `run` | `--model-name` `--temperature` `--web-provider` `--debug-sse` `--fallback-mode` `--enable-tool-trace` | 在当前终端以前台方式运行 |
| `service install` | `--label` `--model-name` `--temperature` `--web-provider` `--debug-sse` `--fallback-mode` `--enable-tool-trace` | 安装后台服务 |
| `service start` | `--label` | 启动后台服务 |
| `service restart` | `--label` | 重启后台服务 |
| `service stop` | `--label` | 停止后台服务 |
| `service status` | `--label` | 查看后台服务状态 |
| `service list` | 无 | 列出当前 workspace 下已安装的后台服务实例 |
| `service uninstall` | `--label` | 删除后台服务 |

说明：
- 使用之前请先下载/上传财报。
- 首次使用时，一般先执行 `login`，再执行 `run` 或 `service install`。
- `run` 直接在命令行窗口前台运行。
- `service` 适合长期后台运行。
- `service` 相关命令目前支持 macOS 和 Linux；Windows 暂未支持。
- 用不同的 `--label`，并分别由不同扫码主体执行 `login`，可以多开。默认实例标签是 `default`，对应状态目录 `workspace/.dayu/wechat-default`。一个完整例子如下：

```bash
# 实例 A：扫码主体 A 登录，安装并启动 service
dayu-wechat login --label a
dayu-wechat service install --label a --model-name mimo-v2.5-pro-thinking
dayu-wechat service start --label a

# 实例 B：扫码主体 B 登录，安装并启动 service
dayu-wechat login --label b
dayu-wechat service install --label b --model-name deepseek-v4-flash-thinking
dayu-wechat service start --label b

# 列出当前 workspace 下已安装的实例
dayu-wechat service list
```

- 多开后，`start` / `restart` / `stop` / `status` / `uninstall` 都要继续带对应实例的同一个 `--label`，这样命中的才是同一个后台 service；忘记有哪些实例时可直接执行 `dayu-wechat service list`。

命令示例：

```bash
dayu-wechat login
dayu-wechat run
```

常见命令示例：

```bash
dayu-wechat login --relogin
dayu-wechat run --model-name mimo-v2.5-pro-thinking --temperature 0.4
dayu-wechat run --enable-tool-trace
dayu-wechat service install
dayu-wechat service start
dayu-wechat service restart
dayu-wechat service stop
dayu-wechat service status
dayu-wechat service list
dayu-wechat service uninstall
```

命令说明：
- 同一微信会话里的连续追问会自动延续上下文，适合做多轮分析。
- 当前版本主要支持文本问答；更适合问财报、公司、行业和研究相关问题。
- 首次使用时先执行 `dayu-wechat login`；命令会打印并尝试打开登录二维码链接，用手机微信扫码确认即可。若你在管理多实例，统一用 `--label` 指定实例标签。
- `dayu-wechat run` 依赖本地已有登录态；若登录态失效，重新执行同一个 `--label` 的 `login` 即可。
- 同一个 `--label` 的前台 `run` 和后台 service 不能并发运行；新的 daemon 若发现该 `state_dir` 已被占用，会直接拒绝启动。
- macOS / Linux：如果你希望它长期后台运行，先执行 `dayu-wechat service install`，再执行 `dayu-wechat service start`。后续可用 `service restart`、`service stop`、`service status`、`service list`、`service uninstall` 管理。
- `service install` 会把当前 shell 里已设置的关键环境变量快照进后台 service 定义，包括配置文件里 `{{ENV_VAR}}` 占位符引用到的变量，以及少量代码直读变量（如 `SEC_USER_AGENT`、联网检索/FMP API key）。如果你后来改了 API key，需要重新执行一次 `dayu-wechat service install`；若后台 service 已在运行，再执行 `dayu-wechat service restart` 让新配置生效。
- `dayu-wechat service status --label <name>` 会直接打印日志定位信息：macOS 打印 stdout/stderr 文件路径；Linux 打印 `journalctl --user -u <label>.service -f` 查看命令。
- `dayu-wechat service list` 只列出当前 workspace 下已安装的实例，并回显实例标签、状态目录、系统 service label、运行状态和是否已有登录态。
- macOS 下默认日志分流语义是：stdout 文件保留全量运行日志，stderr 文件额外记录真正错误与异常堆栈；因此 ERROR 会同时出现在两边。
- Windows：目前没有后台托管命令，使用方式是先执行 `dayu-wechat login`，再执行 `dayu-wechat run`，需要持续运行时请保持终端窗口开启。
- 若需要重新扫码登录，可重启命令并加上 `--relogin`。

### 3.6 自动写作：`write`

命令用途：
基于模板逐章生成买方分析报告，适合在财报与补充材料准备好后批量写作。

参数 / 说明：

| 参数 | 说明 |
|------|------|
| `--ticker` | 必选，指定研究对象 |
| `--chapter` | 可选，只写指定章节 |
| `--fast` | 可选，只执行写作，不运行 `audit` / `confirm` / `repair` |
| `--force` | 可选，允许1-9章audit失败也能写作第 0 章和第 10 章 |
| `--infer` | 可选，只执行公司级 facet 归因并写回 manifest |
| `--preflight-only` | 可选，只检查本次模式需要的 scene、模型和环境变量，不创建 Host run 或报告产物 |
| `--summary` | 可选，只打印上次写作结果摘要，不进入写作 |
| `--reprice-costs` | 可选，与 `--summary` 同用；按当前模型目录只读重估历史 usage 成本 |
| `--routing-history-root` | 可选，与 `--summary` 同用；审批后的共同 preflight、运行授权签发和完整双跑也用它重建当前路由历史 |
| `--routing-proposal-input` | 可选，与 `--summary --routing-history-root` 同用以只读验证 Challenger 提案；审批后的共同 preflight、运行授权签发和完整双跑也必须提供 |
| `--routing-proposal-output` | 可选，与 `--summary --routing-history-root` 同用；原子导出带来源指纹的 Challenger 提案 JSON |
| `--overwrite-routing-proposal` | 可选，允许覆盖内容不同的 Challenger 提案；相同内容无需此参数即可幂等导出 |
| `--routing-preflight-approval-request` | 可选，与 `--summary --routing-history-root --routing-proposal-input` 同用；读取人工共同 preflight 审批确认 JSON |
| `--routing-preflight-approval-output` | 可选，与审批请求参数同用；原子写入仅授权共同 preflight 的不可覆盖审批凭据 |
| `--routing-preflight-approval-input` | 可选，仅与 `--preflight-only` 和 Challenger 覆盖参数同用；在 Host 初始化前验证当前历史、提案、模型参数和审批有效期，也可在成功体检后导出精确运行计划或签发运行授权 |
| `--routing-challenger-run-plan-output` | 可选，与已审批的共同 `--preflight-only` 同用；体检通过后原子导出精确双跑计划 |
| `--routing-challenger-run-approval-request` | 可选，与已审批的共同 `--preflight-only` 和运行授权输出参数成对使用；读取绑定精确计划的人工授权请求 |
| `--routing-challenger-run-approval-output` | 可选，与运行授权请求参数成对使用；共同体检通过后原子写入一次性完整双跑授权 |
| `--routing-challenger-run-approval-input` | 完整 Champion/Challenger 双跑必选；在 Host 初始化前验证精确计划并原子消费一次性授权 |
| `--challenger-promotion-proposal-output` | 可选，与 `--summary` 同用；从已完成双跑的原始摘要和比较产物不可变导出仅供人工审查的晋升提案 |
| `--challenger-promotion-proposal-input` | 可选，与 `--summary` 同用；只读验证晋升提案绑定的三份来源产物是否仍保持当前 |
| `--challenger-config-change-request-output` | 可选，与 `--summary --challenger-promotion-proposal-input` 同用；不可变导出逐场景、仅供审批的配置变更请求 |
| `--challenger-config-change-request-input` | 可选，与 `--summary` 同用；只读验证配置变更请求，也用于绑定人工审批签发 |
| `--challenger-config-change-approval-request` | 可选，与配置变更请求输入和审批输出成组使用；读取人工确认 JSON |
| `--challenger-config-change-approval-output` | 可选，与人工确认参数成组使用；签发最长四小时、仅供未来单次应用的审批凭据，但不应用配置 |
| `--challenger-config-change-approval-input` | 可选，与 `--summary` 同用；只读验证审批凭据，不消费凭据、不修改配置 |
| `--resume` / `--no-resume` | 可选，控制是否断点恢复 |
| `--template` | 可选，写作模板路径，默认 `workspace/assets/定性分析模板.md`，回退 `dayu/assets/定性分析模板.md` |
| `--output` | 可选，输出目录，默认 `workspace/draft/{ticker}` |
| `--model-name` | 可选，主写作模型配置 |
| `--audit-model-name` | 可选，审计模型配置 |
| `--fallback-model-name` | 可选，主写作模型仅在供应商可用性故障时使用的显式后备模型 |
| `--audit-fallback-model-name` | 可选，审计模型仅在供应商可用性故障时使用的显式后备模型 |
| `--challenger-model-name` | 可选，启用隔离 Challenger 运行并覆盖其主写作模型 |
| `--challenger-audit-model-name` | 可选，启用隔离 Challenger 运行并覆盖其审计模型 |
| `--challenger-output` | 可选，Challenger 独立输出目录；默认使用 Champion 输出目录同级的 `<name>-challenger` |
| `--write-max-model-requests` | 可选，限制当前写作阶段的模型请求总数 |
| `--write-max-total-tokens` | 可选，限制当前写作阶段的输入与输出总 Token |
| `--write-max-estimated-cost` | 可选，限制当前写作阶段按模型目录价格估算的成本；需要同时指定币种 |
| `--write-budget-currency` | 成本预算币种，如 `CNY` / `USD`；需要与成本上限同时使用 |
| `--research-template` | 可选，按名称或 `auto` 使用研究模板；行业模板会在官方写作合同中注入 `common` + 行业深化章节，与 `--template` 互斥 |
| `--materialize-research` | 可选，写作成功后从最终 manifest 生成一致的 research bundle 与 workbook；需要 `--research-template` |
| `--research-base` | 可选，指定 research 工件根目录；默认 `workspace/{ticker}`，需要 `--materialize-research` |
| `--overwrite-research` | 可选，允许覆盖已存在的 research 生成工件；需要 `--materialize-research` |
| `--debug` / `--verbose` | 可选，仅调整日志级别，不改变会话行为 |

命令示例：

```bash
dayu-cli write --ticker AAPL
```

常见命令示例：

```bash
dayu-cli write --ticker AAPL --chapter "公司做的是什么生意"
dayu-cli write --ticker AAPL --chapter "经营表现与核心驱动" --fast
dayu-cli write --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --preflight-only
dayu-cli write --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --fallback-model-name mimo-v2.5-pro \
  --audit-fallback-model-name deepseek-v4-pro-thinking \
  --write-max-model-requests 60 \
  --write-max-total-tokens 1500000 \
  --write-max-estimated-cost 12 \
  --write-budget-currency CNY
dayu-cli write --ticker AAPL --research-template technology
dayu-cli write --ticker AAPL --research-template auto
dayu-cli write --ticker AAPL --research-template auto --infer
dayu-cli write --ticker AAPL --research-template auto --materialize-research
dayu-cli write --ticker AAPL --research-template technology --materialize-research \
  --research-base ./workspace/AAPL --overwrite-research
dayu-cli write --ticker AAPL --summary
dayu-cli write --ticker AAPL --summary \
  --routing-history-root ./workspace/draft
dayu-cli write --ticker AAPL --summary \
  --routing-history-root ./workspace/draft \
  --routing-proposal-output ./workspace/receipts/model-challenger.json
dayu-cli write --ticker AAPL --summary \
  --routing-history-root ./workspace/draft \
  --routing-proposal-input ./workspace/receipts/model-challenger.json
dayu-cli write --ticker AAPL --summary \
  --output ./workspace/experiments/AAPL-champion-20260724 \
  --challenger-promotion-proposal-output \
  ./workspace/receipts/challenger-promotion-review.json
dayu-cli write --ticker AAPL --summary \
  --challenger-promotion-proposal-input \
  ./workspace/receipts/challenger-promotion-review.json
dayu-cli write --ticker AAPL --summary \
  --challenger-promotion-proposal-input \
  ./workspace/receipts/challenger-promotion-review.json \
  --challenger-config-change-request-output \
  ./workspace/receipts/challenger-config-change-request.json
dayu-cli write --ticker AAPL --summary \
  --challenger-config-change-request-input \
  ./workspace/receipts/challenger-config-change-request.json \
  --challenger-config-change-approval-request \
  ./workspace/receipts/challenger-config-change-human-approval.json \
  --challenger-config-change-approval-output \
  ./workspace/receipts/challenger-config-change-approval.json
dayu-cli write --ticker AAPL --summary \
  --challenger-config-change-approval-input \
  ./workspace/receipts/challenger-config-change-approval.json
dayu-cli write --ticker AAPL --summary \
  --routing-history-root ./workspace/draft \
  --routing-proposal-input ./workspace/receipts/model-challenger.json \
  --routing-preflight-approval-request ./workspace/receipts/preflight-approval-request.json \
  --routing-preflight-approval-output ./workspace/receipts/preflight-approval.json
dayu-cli write --ticker AAPL \
  --model-name deepseek-v4-pro \
  --preflight-only \
  --challenger-model-name mimo-v2.5-pro \
  --routing-history-root ./workspace/draft \
  --routing-proposal-input ./workspace/receipts/model-challenger.json \
  --routing-preflight-approval-input ./workspace/receipts/preflight-approval.json
dayu-cli write --ticker AAPL \
  --model-name deepseek-v4-pro \
  --audit-model-name mimo-v2.5-pro-thinking \
  --preflight-only \
  --challenger-model-name mimo-v2.5-pro \
  --template ./workspace/assets/定性分析模板.md \
  --output ./workspace/experiments/AAPL-champion-20260724 \
  --challenger-output ./workspace/experiments/AAPL-challenger-20260724 \
  --web-provider auto \
  --write-max-model-requests 60 \
  --write-max-total-tokens 1500000 \
  --write-max-estimated-cost 12 \
  --write-budget-currency CNY \
  --no-resume \
  --routing-history-root ./workspace/draft \
  --routing-proposal-input ./workspace/receipts/model-challenger.json \
  --routing-preflight-approval-input ./workspace/receipts/preflight-approval.json \
  --routing-challenger-run-plan-output ./workspace/receipts/challenger-run-plan.json
dayu-cli write --ticker AAPL \
  --template ./workspace/assets/定性分析模板.md \
  --output ./workspace/draft/AAPL \
  --enable-tool-trace
```

双模型写作建议先运行一次 `--preflight-only`。上面的组合由 DeepSeek 负责 `write` / `regenerate` / `fix` / `repair` / `overview`，MiMo 负责 `infer` / `decision` / `audit` / `confirm`。体检会显示当前 `--infer`、`--chapter`、`--fast` 模式可能执行的 scene、模型名、温度和所需环境变量名称，同时验证 manifest 恢复签名依赖的完整 scene 模型配置；未执行模型的密钥不会被额外要求。它不会显示密钥值，也不会创建 Host run。任一模型不在 scene 允许名单、模型配置无效或本次所需环境变量缺失时，命令返回 `2`。普通 `write` 也会在创建 Host session 前执行同一体检，因此失败时不会产生半份报告。

写作预算按单次流水线阶段计算，Champion 与 Challenger 各自独立计量。运行器会在每个新 Scene 前原子预留预计请求、Token 与成本，并在 Scene 完成后按供应商返回的真实 usage 结算；并发章节也共享同一门禁。成本预算要求所有将执行的模型在 `llm_models.json` 中具有与预算币种一致的可审计价格，Token 或成本预算还要求供应商完整返回 usage。预算阻断后不会继续 audit、repair 或 overview，也不会生成新的最终报告；`run_summary.json` 会记录阻断维度和原因。已经发出的单个 Scene 可能包含多轮 Agent 请求，因此它可在结算时越过上限，系统会阻断该 Scene 的产出和所有后续调用，但这不是供应商账单层面的请求中途熔断。

Runner 默认启用供应商熔断：同一模型目录项连续 3 次出现网络、超时、限流或服务端健康故障后，后续请求在 60 秒冷却期内直接返回结构化 `model_circuit_open` 错误；冷却后只放行一个半开探针。鉴权、额度、输入校验、内容策略、工具错误和主动取消不会触发熔断。打包的 `run.json` 默认把状态写入 workspace 的 `.dayu/model_circuit_breaker.db`，因此指向同一 workspace 的 Python Worker 会共享状态，进程重启后冷却状态也不会丢失；SQLite 写事务保证跨 Worker 只有一个半开探针，持有探针的 Worker 崩溃后，探针租约到期可由其他 Worker 接管。将 `model_circuit_breaker_state_path` 留空可恢复进程内存模式。数据库只保存模型目录标识、计数、时间与错误类型，不保存密钥、请求或响应。Runner 本身不自动替换模型；写作 Service 只有在显式配置 `--fallback-model-name` / `--audit-fallback-model-name` 后，才会对网络、超时、限流、服务端、响应异常或 `model_circuit_open` 切换一次后备模型。鉴权、额度、输入/内容策略、工具/解析错误与取消绝不触发切换。主调用与后备调用分别经过预算预留和 usage 结算；后备模型计划写入 manifest 配置及恢复签名，运行摘要会按真实 scene/model 分开归因，并在 `model_routing` 中记录切换原因、后备调用状态和聚合次数。该路由凭证只保存稳定错误类型，不保存错误原文、Prompt 或密钥。阈值、冷却时间和状态路径均可在 `workspace/config/run.json -> runner_running_config` 调整。

传入任一 `--challenger-*-model-name` 表示请求 Challenger 模式，但完整双跑不会仅凭该参数启动：CLI 还要求有效的 `--routing-challenger-run-approval-input`。授权通过后，CLI 会先同时体检 Champion 与 Challenger，随后把 Challenger 写入审批绑定的独立新目录；它不会覆盖 Champion 报告，也不会自动晋升模型。两次运行完成后，系统会比较发布门禁、审计失败、返修次数、逐章退化、配置成本和后备路由表现，并在 Champion 输出目录生成 `challenger_comparison.json`。只有质量不退化、审计覆盖完整、模型计划确实变化且同币种成本完整可比时，结果才可能为 `promote_challenger`；如果本可自动晋升但 Challenger 的后备切换或后备调用错误增加，则降为 `manual_review`，不会把不同时间窗口中的供应商波动直接判成模型质量退化。

比较产物使用增量兼容的 `write_run_comparison_v2`，同时记录计价口径、请求数、Scene 调用数、Token、总成本、每个通过章节的估算成本，以及后备切换次数、后备调用错误数、调用完成率和后备调用占 Scene 调用的比例。旧摘要没有 `model_routing` 时，路由部分标记为不可比并保留原有推荐逻辑；新摘要若路由总数与 `routes[]` 明细不一致，则视为凭证损坏并阻止自动晋升。`write --summary` 会自动显示该比较；追加 `--reprice-costs` 时，会从两份源 `run_summary.json` 按当前模型目录只读重算后显示，不改写任一历史产物。若源摘要已移动，命令会告警并回退显示持久化比较。

当持久化比较的原始结论恰好为 `promote_challenger` 时，可用 `--challenger-promotion-proposal-output <文件>` 导出 `write_model_challenger_promotion_proposal_v1`。提案逐一绑定 Champion 摘要、Challenger 摘要和 `challenger_comparison.json` 的绝对路径与 SHA-256，并要求当前代码能从两份摘要精确重算出同一比较；它保留按场景记录的模型计划，若某个变化角色包含多个模型或场景覆盖不完整，会标记为歧义并要求人工消解。该文件没有时间性授权，不是配置补丁，只允许人工审查；它明确不授权模型调用、配置变更或晋升。写入采用不可覆盖语义：相同内容幂等，不同内容即使路径相同也拒绝。

`--challenger-promotion-proposal-input <文件>` 会只读校验严格 Schema、提案指纹、三份来源文件指纹、比较可重算性和当前策略下的提案指纹。结果为 `current` 时仍只表示可以进入人工审查；来源变化或策略重算变化返回 `4` 并停止，文件、JSON、Schema 或指纹损坏返回 `2`。输入和输出互斥，不需要 `--routing-history-root`。即使同时使用 `--reprice-costs`，晋升提案仍绑定原始持久化成本比较，不会把临时价格重估当成实验依据。

当前且所有变化角色无歧义的晋升提案，可以通过 `--challenger-config-change-request-output` 转换为 `write_model_challenger_configuration_change_request_v1`。请求逐场景记录已完成 Champion 运行中观察到的模型和拟采用的 Challenger 模型，并绑定晋升提案文件路径、文件 SHA-256 与内容指纹；这些记录不是“当前运行配置仍然如此”的断言。任何未来应用都必须重新核对当前配置、准备回滚方案、验证来源仍为当前，并通过独立命令消费一次性审批。本阶段没有配置补丁，也不会改写 `llm_models.json`、`run.json`、Prompt、环境变量或密钥。

人工确认文件使用 `write_model_challenger_configuration_change_approval_request_v1`，必须绑定变更请求与晋升提案指纹，提供审批人、审批引用、回滚引用、UTC `approved_at` / `expires_at`，有效期不超过四小时，并逐项确认安全边界。`--challenger-config-change-approval-output` 只会签发不可覆盖的 `write_model_challenger_configuration_change_approval_v1`；`--challenger-config-change-approval-input` 在只读验证模式下只检查它仍未过期且全部证据仍为当前。验证结果为 `approved` 也只代表可以进入独立应用门禁：验证命令本身不会消费凭据、不会调用模型，也不会修改任何配置。SHA-256 只提供完整性证据，不是公钥数字签名或审批人身份认证。

进入预应用核验时，使用 `--preflight-only --write-routing-snapshot-output <文件>` 可导出 `write_scene_model_routing_snapshot_v1`：它通过真实写作 preflight 固化九个签名 Scene 的当前模型、路由来源、temperature，以及 `run.json`、`llm_models.json` 和 Scene manifest 的路径与 SHA-256。追加 `--challenger-config-change-approval-input <审批>`、`--challenger-config-preapplication-plan-output <计划>` 可在当前路由与已观察 Champion 完全一致时生成 `write_model_challenger_configuration_preapplication_plan_v1`；计划逐文件保存应用前 manifest 的精确字节和回滚指纹。CLI 模型覆盖会被快照记录，但会阻止持久配置计划。使用 `--challenger-config-preapplication-plan-input <计划>` 会重新运行 preflight 并校验审批、快照和所有来源仍为当前。三个操作都不会应用配置、消费审批、改写 `run.json` / `llm_models.json`、调用模型或触碰密钥；真正变更由下面的独立、原子且一次性消费审批的应用门禁完成。

配置应用必须使用专用模式，且四个参数缺一不可：

```text
dayu-cli write --ticker AAPL \
  --apply-write-model-configuration \
  --challenger-config-application-plan-input <preapplication-plan.json> \
  --challenger-config-change-approval-input <approval.json> \
  --challenger-config-application-receipt-output <application-receipt.json>
```

该命令先取得配置根目录级单实例锁，再用新建的依赖和 `WriteService.preflight` 重新解析当前路由；只有审批、计划、来源文件、当前 Champion 和目标 manifest 原始字节全部仍然匹配，才会原子消费一次性审批并逐个替换计划指定的 `/model/default_name`。所有文件替换后再次用全新依赖执行 preflight；若替换或应用后体检失败，会按计划保存的精确原始字节逆序回滚并再次体检。进程若在审批消费后中断，重跑同一命令会先处理原事务：已有内部完成回执时只幂等重导出，尚无完成回执时先恢复未完成事务，绝不会再次应用。结果写入不可变的 `write_model_configuration_application_receipt_v1`：`applied` 返回 `0`，已精确回滚的 `rolled_back` 返回 `4` 并要求新审批，`rollback_failed` 返回 `6` 并要求人工恢复。成功应用后命令立即停止，不启动写作、不调用模型、不修改 `run.json`、`llm_models.json`、环境变量或密钥；该专用模式禁止 `--summary`、`--preflight-only`、模型/温度/后备覆盖、Challenger 操作和局部写作参数。

应用后可随时执行独立只读复核：

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json>
```

已应用回执通过完整路由复核后，可进入仍然只读的人工回滚计划和审批门禁。计划直接复用预应用计划保存的原始 manifest 精确字节，不根据模型名称重新推断旧配置：

```text
# 导出精确回滚计划
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-output <rollback-plan.json>

# 复核计划并签发最长四小时、一次性使用的人工审批
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-request <human-request.json> \
  --challenger-config-rollback-approval-output <rollback-approval.json>

# 再次复核审批，不消费审批
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-input <rollback-approval.json>

# Consume the rollback approval once and restore exact preapplication bytes
dayu-cli write --ticker AAPL \
  --rollback-write-model-configuration \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-input <rollback-approval.json> \
  --challenger-config-rollback-receipt-output <rollback-receipt.json>
```

The rollback command shares the configuration-root lock with configuration
application, writes an exact-byte intent before consuming approval, and runs a
fresh complete routing preflight after restoration. `rolled_back` returns `0`.
If rollback fails but exact applied bytes are recovered, `rolled_forward`
returns `4` and requires a new approval. `recovery_failed` returns `6` and
requires manual recovery. Retrying a consumed approval never performs a second
rollback; it exports the immutable internal receipt or restores the applied
state from the transaction intent first. The command does not start a write run,
call a model, or modify `run.json`, `llm_models.json`, secrets, or environment
variables.

Independently verify the resulting rollback receipt with a fresh, complete
routing preflight:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-rollback-receipt-input <rollback-receipt.json>
```

The read-only verifier compares both the full routing snapshot and each changed
scene. A current `rolled_back` receipt confirms the exact preapplication state.
A current `rolled_forward` receipt confirms the exact applied state and permits
only a new rollback cycle with a newly generated plan and newly issued
approval. Routing drift and `recovery_failed` return exit code `4`; malformed
evidence or a failed fresh preflight returns `2`. Verification never changes
configuration, consumes approval, starts writing, or calls a model.

For a `recovery_failed` receipt, export a separate immutable manual-recovery
evidence bundle without running preflight:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-receipt-input <recovery-failed.json> \
  --challenger-config-manual-recovery-evidence-output <manual-recovery-evidence.json>
```

This dedicated mode revalidates the original plan, approval, approval
consumption, application receipt, transaction identity, routing identities,
and exact operations. It observes each target twice without following a
target symlink or changing any bytes. A valid transaction intent produces
`complete` evidence containing the exact applied and preapplication candidate
bytes. If the intent is missing or invalid, the bundle is `partial`: exact
preapplication bytes remain available from the verified plan, while applied
bytes are explicitly unavailable and are never guessed. The bundle reports
`exact_applied`, `exact_preapplication`, `mixed_known`, or `indeterminate`, but
does not recommend a state or emit a recovery command. Successful evidence
export returns `0`; an ineligible receipt or changed source chain returns `4`;
malformed input or output failure returns `2`. It starts no Host or preflight,
calls no model, consumes no new approval, and mutates no configuration.

After independent review, the selector records exactly `applied` or
`preapplication`; the system never chooses. Build the exact-byte plan:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-evidence-input <manual-recovery-evidence.json> \
  --challenger-config-manual-recovery-selection-request <selection.json> \
  --challenger-config-manual-recovery-plan-output <recovery-plan.json>
```

`applied` requires `complete` evidence. A different person then issues a
single-use approval whose validity cannot exceed four hours:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-plan-input <recovery-plan.json> \
  --challenger-config-manual-recovery-approval-request <approval-request.json> \
  --challenger-config-manual-recovery-approval-output <recovery-approval.json>
```

Execute only through the dedicated transaction:

```text
dayu-cli write --ticker AAPL \
  --recover-write-model-configuration \
  --challenger-config-manual-recovery-plan-input <recovery-plan.json> \
  --challenger-config-manual-recovery-approval-input <recovery-approval.json> \
  --challenger-config-manual-recovery-receipt-output <recovery-receipt.json>
```

The execution shares the normal configuration lock, records exact starting and
selected bytes before consuming approval, and runs fresh full routing preflight
only after restoring the selected state. Any later failure restores the exact
starting bytes, never the unselected candidate. `recovered` returns `0`,
`starting_state_restored` returns `4`, and `recovery_failed` returns `6`.
Consumed retries never apply twice. Full request schemas and safety boundaries
are documented in
`docs/plans/2026-07-28-write-model-configuration-manual-recovery.md`.

Independently verify the immutable recovery result before issuing clearance:

```text
dayu-cli write --ticker AAPL \
  --verify-write-model-configuration-manual-recovery \
  --challenger-config-manual-recovery-verification-receipt-input \
    <recovery-receipt.json>
```

Only `current` returns `0` and makes the incident eligible for a separate
clearance decision. It does not by itself reopen normal writes. A recovered
receipt must still match both the selected target bytes and a fresh complete
routing snapshot. `starting_state_current` returns `4` and requires new
recovery evidence; `starting_state_changed` and `manual_recovery_required`
return `6`. Verification itself never modifies configuration, consumes an
approval, starts a write run, writes clearance, or calls a model. The full
contract is in
`docs/plans/2026-07-28-write-model-configuration-manual-recovery-verification.md`.

After an independent third operator reviews the current verification, create
a clearance request bound to the exact receipt fingerprint and transaction.
Ordinary recovery uses
`write_model_configuration_manual_recovery_clearance_request_v1`. A recovery
restarted from a revoked clearance has a v2 receipt and must use
`write_model_configuration_manual_recovery_clearance_request_v2`, copy its
complete `clearance_revocation_lineage`, and acknowledge
`reviewed_exact_clearance_revocation_lineage`. The clearance operator must
differ case-insensitively from both the state selector and recovery approver.
Issue the immutable clearance:

```text
dayu-cli write --ticker AAPL \
  --clear-write-model-configuration-manual-recovery \
  --challenger-config-manual-recovery-clearance-receipt-input \
    <recovery-receipt.json> \
  --challenger-config-manual-recovery-clearance-request \
    <clearance-request.json> \
  --challenger-config-manual-recovery-clearance-output \
    <clearance.json>
```

Issuance holds the shared configuration transaction lock while confirming
that the receipt is the latest internal recovery transaction, replaying the
complete verification, and recording the internal clearance. It changes no
configuration, consumes no approval, and calls no model. After any manual
recovery transaction, normal non-summary write and preflight commands fail
closed before Challenger approval consumption, Host construction, or model
execution until the latest transaction has a valid matching clearance.
Issuance produces clearance v1 for a v1 receipt and clearance v2 for a v2
receipt. A v2 clearance preserves the exact revocation lineage; each gate
assessment reloads its authoritative revoked receipt, prior clearance, and
revocation before allowing normal writes. Mixed v1/v2 artifacts and a valid
but different lineage fail closed.
Incomplete transactions, `starting_state_restored`, `recovery_failed`,
missing clearance, or a tampered clearance remain blocked. Read-only
`--summary` and dedicated configuration recovery controls remain available.
The v2 clearance contract is documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-clearance-lineage-v2.md`.

If an operator later discovers that the latest clearance should not authorize
normal writes, issue an immutable revocation:

```text
dayu-cli write --ticker AAPL \
  --revoke-write-model-configuration-manual-recovery-clearance \
  --challenger-config-manual-recovery-clearance-revocation-receipt-input \
    <recovery-receipt.json> \
  --challenger-config-manual-recovery-clearance-revocation-clearance-input \
    <clearance.json> \
  --challenger-config-manual-recovery-clearance-revocation-request \
    <revocation-request.json> \
  --challenger-config-manual-recovery-clearance-revocation-output \
    <revocation.json>
```

Revocation binds the exact latest receipt and authoritative clearance under
the shared transaction lock, writes the internal immutable record before its
external export, and immediately blocks normal writes. It does not require a
fourth independent operator because it only removes authority. The same
transaction cannot be unrevoked; re-exporting or reissuing its clearance does
not reopen the gate. A newer manual recovery transaction and its own clearance
are required. Configuration, approvals, Host dependencies, and models remain
untouched.

Restart that recovery path without manually traversing nested source files:

```text
dayu-cli write --ticker AAPL \
  --restart-write-model-configuration-manual-recovery-after-clearance-revocation \
  --challenger-config-manual-recovery-restart-receipt-input \
    <recovery-receipt.json> \
  --challenger-config-manual-recovery-restart-clearance-input \
    <clearance.json> \
  --challenger-config-manual-recovery-restart-revocation-input \
    <revocation.json> \
  --challenger-config-manual-recovery-restart-evidence-output \
    <new-recovery-evidence.json>
```

The command requires the gate to still be `clearance_revoked`, verifies that
all three supplied artifacts are byte-identical to the latest authoritative
records, follows the recovered receipt back to its exact original
`recovery_failed` rollback receipt, and exports fresh
`write_model_configuration_manual_recovery_evidence_v2`. Its strict
`clearance_revocation_lineage` binds the revoked recovery receipt, clearance,
revocation, their authoritative source files, and a lineage fingerprint. The
existing selection, plan, approval, recovery, and verification commands accept
that evidence and keep the exact lineage in their corresponding v2 artifacts.
The restart command does not remove the revocation, create a selection, issue
or consume approval, modify configuration, construct Host dependencies, or
call a model. Exit `4` means the revoked gate, exact artifacts, source chain,
current target bytes, or configuration lock are not safe; malformed paths or
output failures return `2`.

For this path, human-authored selection and approval requests must use their
v2 schemas, copy `clearance_revocation_lineage` without modification, and add
the required lineage acknowledgement. Every planning, approval, application,
receipt, and verification boundary compares that object exactly and replays
its authoritative source artifacts before proceeding. Changing or replacing
the revocation after evidence export therefore fails closed. Ordinary recovery
that starts directly from a `recovery_failed` rollback receipt remains on the
strict v1 contracts and gains no optional fields.

Inspect that gate directly without starting preflight or constructing Host
dependencies:

```text
dayu-cli write --ticker AAPL \
  --check-write-model-configuration-manual-recovery-gate
```

To retain an immutable audit snapshot, add an output path outside the
configuration root:

```text
dayu-cli write --ticker AAPL \
  --check-write-model-configuration-manual-recovery-gate \
  --challenger-config-manual-recovery-gate-output \
    <audit/manual-recovery-gate.json>
```

The check always reports the current gate state. It returns `0` for
`not_required` or `cleared`, `4` for a valid but unresolved incident
(including `clearance_revoked`) or a busy configuration lock, `6` for
malformed, unsafe, or semantically inconsistent internal evidence, and `2`
when the command has no configuration root or the requested audit export
path is invalid, collides with different content, or cannot be written. Gate
schema v4 binds the result to the command ticker and adds `assessed_at`, a
strict lineage status, the complete lineage when present, and a
`gate_fingerprint` over the full result. For a v2 latest receipt, every
receipt-backed status rechecks the authoritative revoked receipt, prior
clearance, and revocation, including `clearance_required` before a new
clearance exists. A current clearance additionally rechecks its routing
fingerprint, recovery/clearance time ordering, bound selector and approver
source identities, and independent clearer identity. A revoked result binds
the exact immutable revocation and its request source. Explicit export writes
the same gate immutably before returning, including for a valid blocked gate;
ordinary write checks do not create audit files.

Independently compare an exported gate with a fresh local assessment:

```text
dayu-cli write --ticker AAPL \
  --verify-write-model-configuration-manual-recovery-gate \
  --challenger-config-manual-recovery-gate-input \
    <audit/manual-recovery-gate.json>
```

To retain the self-contained verification receipt, add:

```text
  --challenger-config-manual-recovery-gate-verification-output \
    <audit/manual-recovery-gate-verification.json>
```

The dedicated verifier accepts only a strict gate v4 file outside the
configuration root, binds its exact file bytes, obtains a fresh gate
assessment, and then reads the source file again. A source path or byte change
during that interval fails closed. It compares every semantic gate field
except `assessed_at` and `gate_fingerprint`, whose expected changes do not make
an otherwise identical snapshot stale. The
`write_model_configuration_manual_recovery_gate_verification_v1` receipt
embeds both complete gates, their semantic-state fingerprints, the source-file
fingerprint, and the exact changed fields.

`current` returns `0`; `stale`, a source change during verification, or a busy
configuration lock returns `4`. Malformed external input and invalid or
colliding output paths return `2`; malformed current internal evidence returns
`6`. `current` means only that the exported semantic state matched a fresh
assessment. It does not authorize a normal write, consume approval, mutate
configuration, construct Host dependencies, or call a model. The SHA-256
fingerprints prove integrity, not signer identity or artifact authority.

Revalidate a saved gate-verification receipt and its bound source gate:

```text
dayu-cli write --ticker AAPL \
  --revalidate-write-model-configuration-manual-recovery-gate-verification \
  --challenger-config-manual-recovery-gate-verification-input \
    <audit/manual-recovery-gate-verification.json>
```

To retain the self-contained revalidation receipt, add:

```text
  --challenger-config-manual-recovery-gate-verification-revalidation-output \
    <audit/manual-recovery-gate-verification-revalidation.json>
```

This dedicated mode first validates the saved verification and binds its exact
file bytes. It then re-runs the existing gate-snapshot verifier against the
exact source path and source-file fingerprint recorded by that receipt, reads
the saved verification again to detect concurrent replacement, and compares
the old and fresh `current_gate` semantic states. `assessed_at` and
`gate_fingerprint` remain the only excluded fields.

`current` means the saved verification still describes the current semantic
gate state and returns `0`. `stale` reports every changed top-level gate field
and returns `4`. A changed bound gate, a verification receipt changed during
revalidation, or a busy configuration lock also returns `4`; malformed
external input or invalid/colliding output returns `2`; malformed fresh
internal evidence returns `6`. Revalidation does not authorize normal writes,
change configuration, consume approval, construct Host dependencies, or call
a model. Its SHA-256 fingerprints remain integrity evidence rather than
signatures or operator authority.

Audit the complete internal manual-recovery history and current gate in one
read-only snapshot:

```text
dayu-cli write --ticker AAPL \
  --audit-write-model-configuration-manual-recovery-history
```

To retain the self-contained timeline, add:

```text
  --challenger-config-manual-recovery-audit-timeline-output \
    <audit/manual-recovery-audit-timeline.json>
```

The dedicated audit scans every authoritative recovery transaction,
clearance, and revocation entry under the shared configuration transaction
lock. It rejects unsafe directory entries, malformed historical artifacts,
duplicate or orphan evidence, broken receipt-to-clearance-to-revocation
links, inconsistent tickers and timestamps, and disagreement between the
complete history and the embedded fresh gate. It scans the internal state
again after gate assessment and fails if any path, payload, file fingerprint,
or incomplete-transaction set changed during the audit.

`write_model_configuration_manual_recovery_audit_timeline_v1` embeds the
strict gate v4 result and each complete internal artifact, together with its
absolute authoritative path, exact file-byte fingerprint, content
fingerprint, deterministic sequence, evidence roots, counts, and sorted
incomplete transaction IDs. The final timeline fingerprint seals the entire
snapshot. Optional export is immutable and must remain outside both the
configuration root and the workspace's authoritative `.dayu` evidence root.

A valid timeline returns `0` even when its embedded gate blocks normal
writes; success means only that the history was safely audited. A changed
history during scanning or a busy configuration lock returns `4`, malformed
or inconsistent internal evidence returns `6`, and missing configuration or
invalid/colliding export paths return `2`. The audit does not authorize a
normal write, mutate configuration, consume approval, construct Host
dependencies, or call a model.

The request schemas, internal paths, status contracts, and exit codes are in
`docs/plans/2026-07-28-write-model-configuration-manual-recovery-clearance.md`
and
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-clearance-revocation.md`.
The revoked-clearance restart contract is documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-restart.md`;
the complete v2 lineage contract is in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-revocation-lineage-v2.md`.
The timestamped, fingerprinted gate and optional audit export are documented
in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-gate-v4.md`;
independent snapshot verification is documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-gate-verification-v1.md`;
saved verification revalidation is documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-gate-verification-revalidation-v1.md`;
complete internal history audit is documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-audit-timeline-v1.md`.

若结果为当前 `rolled_forward`，可从该回执导出第二轮的新计划：

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-rollback-receipt-input <rolled-forward-receipt.json> \
  --challenger-config-rollback-plan-output <retry-plan.json>
```

该只读门禁会重新校验完整当前路由，并逐一验证第一轮的原计划、已消费审批、审批消费记录和应用回执的文件及内容指纹；事务身份、路由指纹和精确恢复操作必须全部一致。新计划必须晚于 `rolled_forward` 回执，使用新的计划指纹，但保留同一组精确恢复字节。第一轮审批已绑定旧计划路径和指纹且已经消费，不能复用；第二轮必须走正常流程签发新的短期审批。`rolled_back`、`recovery_failed`、路由已漂移或来源证据变化时均拒绝导出。该命令不修改配置、不消费审批、不启动写作，也不调用模型。

计划会绑定应用回执、原预应用计划、完整应用后和恢复后路由指纹、每个目标 manifest 的应用后指纹和恢复字节。任何来源、完整路由或目标文件漂移都会停止；审批必须显式绑定计划和应用回执指纹，有效期最多四小时且只允许未来使用一次。实际回滚只允许通过上面的专用一次性命令执行；详细协议见 `docs/plans/2026-07-26-write-model-configuration-operator-rollback.md`。

该命令重新执行写作 preflight，并把当前完整 `write_scene_model_routing_snapshot_v1` 指纹与回执保存的应用后指纹比较；检查范围包括九个签名 Scene、所有 manifest 证据、`run.json`、`llm_models.json`、fallback 路由、temperature 和请求覆盖上下文，而不只是曾经修改的 Scene。`current` 返回 `0`；任一配置漂移返回 `routing_changed` 和退出码 `4`；历史回执记录 `rollback_failed` 时返回 `manual_recovery_required` 和退出码 `4`。只有 `current` 且回执状态为 `applied` 才标记为可进入后续人工回滚计划，但复核本身不授权回滚。该模式禁止任何路由覆盖、Challenger、其他配置工件操作和局部写作参数，不改配置、不消费审批、不启动写作，也不调用模型。

`write --summary --routing-history-root <目录>` 会递归发现该目录中的 `run_summary.json`，按摘要内的 UTC `completed_at` 排序，最多选择最近 20 次，并比较最近 5 次与更早基线。报告同时展示发布通过率、后备切换占 Scene 比例、后备调用错误率、单 Scene 成本和逐模型状态。旧摘要没有 `completed_at` 时会退回文件修改时间并单独计数；损坏时间或 JSON 不参与窗口。缺失路由凭证不会被当作零切换，计数与 `routes[]` 不一致则标记为无效。跨币种或成本不完整时不计算成本趋势；与 `--reprice-costs` 同用时，历史成本也按当前模型目录只读重估。

同一只读报告还会评估后备模型是否具备进入隔离 Challenger 双跑的最低证据。默认要求最近至少 3 次运行均有完整路由和发布凭证，主路由后备切换率至少 20%，后备至少完成 3 次真实切换且完成率不低于 90%；多个候选、调用凭证不完整或发布通过率过低都会封闭为人工复核。满足门槛时只输出角色覆盖和 JSON argv 形式的 `--challenger-model-name` / `--challenger-audit-model-name` 参数建议，仍须执行 Champion/Challenger 共同 preflight、隔离输出和质量/路由/成本比较。追加 `--routing-proposal-output <文件>` 可显式导出 `write_model_challenger_proposal_v2` 凭据，其中 `history_fingerprint` 绑定本次选中的原始摘要，`proposal_fingerprint` 绑定完整提案；当前价格目录重估不会改变这两个身份。写入使用临时文件、`fsync` 和原子替换，相同内容幂等，内容不同默认拒绝覆盖，只有显式追加 `--overwrite-routing-proposal` 才允许替换。它不会运行模型、修改 `llm_models.json`、交换主备配置或自动晋升 Challenger。

使用 `--routing-proposal-input <文件>` 时，系统会严格校验 Schema、提案指纹、历史窗口计数和允许的 Challenger argv，再用当前目录重新生成提案进行只读比对。结果为 `current` 时，只有当前提案仍为 `ready` 才展示预检参数；历史摘要变化返回 `stale_history`，同一历史在当前策略下生成不同内容则返回 `policy_changed`，这两种情况退出码均为 `4` 且不展示可用参数。JSON 损坏、指纹不符或非法参数返回 `2`。输入和输出参数互斥，验证流程不创建 Host、不调用模型、不修改配置，也不自动执行 preflight。

人工确认当前 `ready` 提案后，可同时提供 `--routing-preflight-approval-request` 与 `--routing-preflight-approval-output`。请求必须使用 `write_model_challenger_preflight_approval_request_v1`，绑定当前 `proposal_fingerprint` 和 `history_fingerprint`，包含审批人、审批引用、UTC `approved_at` / `expires_at`，且有效期最多 24 小时，并逐项确认 `common_preflight_only`、不调用模型、不改配置、不批准 Challenger 双跑和不批准晋升。系统会再次验证提案身份与有效期，再原子生成 `write_model_challenger_preflight_approval_v1`；输出固定为 JSON argv `["--preflight-only", ...角色覆盖参数]`，不同内容不能覆盖同一路径。过期、尚未生效、提案非 `ready` 或身份变化返回 `4`，格式和文件错误返回 `2`。该文件是带 SHA-256 完整性指纹的操作员确认记录，不是公钥数字签名，也不会自动执行 preflight。

实际执行已审批的共同 preflight 时，必须同时提供 `--preflight-only`、`--routing-history-root`、`--routing-proposal-input`、`--routing-preflight-approval-input`、提案中的精确 Challenger 覆盖参数，以及提案涉及角色的显式当前 Champion 模型参数。例如主写作角色被建议替换时，必须显式提供与提案 `current_model_name` 一致的 `--model-name`。CLI 会先重新扫描历史、重建当前提案，再验证审批有效期、历史和提案指纹、批准 argv、实际 Challenger argv 与当前 Champion 身份；任何不一致均在 `_prepare_cli_host_dependencies` 之前停止。身份过期或命令不一致返回 `4`，文件、Schema 或指纹损坏返回 `2`。审批模式禁止 `--challenger-output`、`--fast` 和 `--chapter`，也不能与审批签发参数同用。普通不含 Challenger 覆盖的 `--preflight-only` 不需要审批。

该审批只允许运行无模型调用的 Champion/Challenger 配置体检，不允许完整 Challenger 写作、配置变更或模型晋升；`--routing-preflight-approval-input` 因此不能用于非 `--preflight-only` 命令。完整 Challenger 实验使用下面的独立运行授权流程。

```json
{
  "schema_version": "write_model_challenger_preflight_approval_request_v1",
  "approval_type": "write_model_challenger_common_preflight",
  "scope": "champion_challenger_common_preflight_only",
  "approved_by": "operator@example.com",
  "approval_reference": "OPS-42",
  "approved_at": "2026-07-24T08:00:00Z",
  "expires_at": "2026-07-24T09:00:00Z",
  "proposal_fingerprint": "sha256:<提案中的 64 位摘要>",
  "history_fingerprint": "sha256:<提案中的 64 位历史摘要>",
  "acknowledgements": [
    "common_preflight_only",
    "no_model_execution",
    "no_configuration_change",
    "no_challenger_run_authorization",
    "no_challenger_promotion_authorization"
  ]
}
```

完整双跑采用“计划、人工授权、一次性消费”三步流程：

1. 使用已审批的共同 preflight，并显式提供模板、两个新输出目录、模型覆盖、Web Provider、每次运行预算和 `--no-resume`。只有 Champion 与 Challenger 两边都体检通过，系统才写出 `write_model_challenger_run_plan_v1`。计划绑定 ticker、模板绝对路径与 SHA-256、两个输出目录、当前与 Challenger 模型参数、显式 fallback、重试、温度、Provider 和预算。成本上限是“每次运行”上限，计划同时记录其两倍作为完整实验最大估算成本。
2. 操作员审阅导出的完整计划，创建 `write_model_challenger_run_approval_request_v1`。请求有效期最多 4 小时，必须嵌入未修改的完整 `execution_plan`，并绑定提案、历史和共同 preflight 审批指纹。随后再次运行完全相同的已审批共同 preflight，并成对提供 `--routing-challenger-run-approval-request` 与 `--routing-challenger-run-approval-output`；只有两边再次体检通过才签发 `write_model_challenger_run_approval_v1`。
3. 完整双跑移除 `--preflight-only` 和共同 preflight 审批输入，保留计划中的所有运行参数，并提供 `--routing-challenger-run-approval-input`。CLI 会在 Host 初始化前重建当前历史与精确计划，检查有效期、身份和两个输出目录，再按审批指纹原子写入 `.dayu/approvals/challenger-runs/*.consumed.json`。同一授权只能使用一次；即使后续 Host 初始化或自动 preflight 失败，授权也保持已消费，需要重新审批。

运行授权请求示例，其中 `execution_plan` 必须替换为导出的计划 JSON 完整对象，而不是文件路径：

```json
{
  "schema_version": "write_model_challenger_run_approval_request_v1",
  "approval_type": "write_model_challenger_isolated_run",
  "scope": "one_bounded_isolated_champion_challenger_run",
  "approved_by": "operator@example.com",
  "approval_reference": "OPS-RUN-42",
  "approved_at": "2026-07-24T08:00:00Z",
  "expires_at": "2026-07-24T10:00:00Z",
  "proposal_fingerprint": "sha256:<提案中的 64 位摘要>",
  "history_fingerprint": "sha256:<提案中的 64 位历史摘要>",
  "preflight_approval_fingerprint": "sha256:<共同 preflight 审批中的 64 位摘要>",
  "execution_plan": {
    "...": "完整复制 challenger-run-plan.json 的对象"
  },
  "acknowledgements": [
    "authorizes_champion_and_challenger_model_execution",
    "preflight_must_pass_before_execution",
    "isolated_outputs_are_new_and_distinct",
    "per_run_budget_applies_to_each_run_separately",
    "authorization_is_single_use",
    "no_configuration_change_authorization",
    "no_challenger_promotion_authorization"
  ]
}
```

签发运行授权时，重复计划导出命令中的全部参数，并追加：

```bash
  --routing-challenger-run-plan-output ./workspace/receipts/challenger-run-plan.json \
  --routing-challenger-run-approval-request ./workspace/receipts/challenger-run-request.json \
  --routing-challenger-run-approval-output ./workspace/receipts/challenger-run-approval.json
```

执行完整双跑时，使用计划中的相同运行参数，移除 `--preflight-only`、`--routing-preflight-approval-input` 和签发参数，并追加：

```bash
  --routing-history-root ./workspace/draft \
  --routing-proposal-input ./workspace/receipts/model-challenger.json \
  --routing-challenger-run-approval-input ./workspace/receipts/challenger-run-approval.json
```

授权模式强制要求显式 `--template`、`--output`、`--challenger-output`、`--web-provider`、三个预算上限与币种，并要求 `--no-resume`。它禁止 `--fast`、`--force`、`--chapter`、`--research-template` 和研究工件物化。两个输出必须不同、位于 workspace 内且尚不存在。策略、历史、时间、计划或授权复用冲突返回 `4`；损坏 JSON、Schema、指纹、文件或输出边界错误返回 `2`。授权和计划中的 SHA-256 用于内容完整性与精确绑定，不是公钥签名，也不验证审批人的密码学身份。运行授权不允许修改配置或自动晋升 Challenger。

研究模板库（`scorecard`、`evidence`、`schema`、`checklist` 为只读命令，直接查看行业模板的评分卡、证据要求、完整定义与分析师检查单，无需先物化 workspace）：

```bash
dayu-cli research-template list
dayu-cli research-template show consumer
dayu-cli research-template scorecard consumer
dayu-cli research-template evidence consumer --json
dayu-cli research-template schema technology --json
dayu-cli research-template checklist consumer
dayu-cli research-template checklist technology --json
dayu-cli research-template materialize-checklist consumer --base ./workspace
dayu-cli research-template materialize-checklist consumer \
  --base ./workspace --overwrite
dayu-cli write --ticker 600519 --research-template consumer
dayu-cli research-template recommend \
  --business-model-tag "消费品牌" \
  --constraint-tag "高营销费用驱动"
dayu-cli research-template compose consumer --base ./workspace
dayu-cli research-template monitoring-rules consumer --write --base ./workspace
dayu-cli research-template research-workbook consumer \
  --ticker 600519 \
  --company "贵州茅台" \
  --write \
  --base ./workspace/600519
dayu-cli research-template validate-research-workbook \
  --workbook ./workspace/600519/assets/research_templates/consumer.research-workbook.json
dayu-cli research-template update-research-workbook \
  --workbook ./workspace/600519/assets/research_templates/consumer.research-workbook.json \
  --item-id item-<stable-id> \
  --status answered \
  --response "需求增长由同店销售改善驱动" \
  --evidence-file ./evidence.json \
  --write
dayu-cli research-template rollback-research-workbook \
  --workbook ./workspace/600519/assets/research_templates/consumer.research-workbook.json \
  --backup ./workspace/600519/assets/research_templates/consumer.research-workbook.before-update.<sha256-prefix>.json \
  --write
dayu-cli research-template workbook-status \
  --base ./workspace \
  --recursive \
  --write
dayu-cli research-template workbook-report \
  --workbook ./workspace/600519/assets/research_templates/consumer.research-workbook.json \
  --write
dayu-cli research-template validate-workbook-report \
  --report ./workspace/600519/assets/research_templates/consumer.research-progress.md \
  --workbook ./workspace/600519/assets/research_templates/consumer.research-workbook.json
dayu-cli research-template workbook-report-status \
  --base ./workspace \
  --recursive \
  --write
dayu-cli research-template source-map consumer --write --base ./workspace
dayu-cli research-template validate-source-map \
  --rules ./workspace/assets/research_templates/consumer.monitoring-rules.json \
  --source-map ./workspace/assets/research_templates/consumer.source-map.json
dayu-cli research-template package-manifest --write --base ./workspace
dayu-cli research-template materialize consumer --base ./workspace
dayu-cli research-template materialize --manifest ./workspace/AAPL/write-manifest.json --base ./workspace/AAPL
dayu-cli research-template materialize technology --ticker 0700.HK --company "Tencent Holdings" --base ./workspace/0700.HK
dayu-cli research-template list-bundles --base ./workspace --json
dayu-cli research-template validate-bundle \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json
dayu-cli research-template refresh-workspace \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json
dayu-cli research-template refresh-workspace \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json --write
dayu-cli research-template rebind-bundle \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json
dayu-cli research-template rebind-bundle \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json \
  --write
dayu-cli research-template rollback-bundle-rebind \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json \
  --backup ./workspace/assets/research_templates/consumer.bundle.before-rebind.<sha256-prefix>.json \
  --write
dayu-cli research-template monitoring-plan \
  --bundle ./workspace/assets/research_templates/consumer.bundle.json \
  --write
dayu-cli research-template validate-monitoring-plan \
  --plan ./workspace/assets/research_templates/consumer.monitoring-plan.json
dayu-cli research-template list-monitoring-plans --base ./workspace --json
dayu-cli research-template monitoring-status --base ./workspace --write
dayu-cli research-template list-monitoring-plans --base ./workspace --recursive --json
dayu-cli research-template monitoring-status --base ./workspace --recursive --write
dayu-cli research-template materialize-portfolio \
  --portfolio ./portfolio.json \
  --base ./workspace
dayu-cli research-template preview-portfolio \
  --portfolio ./portfolio.json \
  --base ./workspace
dayu-cli research-template scheduler-manifest \
  --base ./workspace \
  --recursive \
  --timezone Asia/Shanghai \
  --write
dayu-cli research-template validate-scheduler-manifest \
  --manifest ./workspace/assets/research_templates/monitoring-scheduler.json
dayu-cli research-template source-bindings \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json \
  --approval ./consumer-bindings.approval.json
dayu-cli research-template source-bindings \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json \
  --approval ./consumer-bindings.approval.json \
  --write
dayu-cli research-template rollback-source-bindings \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json \
  --backup ./workspace/600519/assets/research_templates/consumer.source-map.before-bindings.<sha256-prefix>.json
dayu-cli research-template rollback-source-bindings \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json \
  --backup ./workspace/600519/assets/research_templates/consumer.source-map.before-bindings.<sha256-prefix>.json \
  --write
dayu-cli research-template rollback-source-bindings \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json \
  --backup ./workspace/600519/assets/research_templates/consumer.source-map.before-rollback.<sha256-prefix>.json \
  --write
dayu-cli research-template source-binding-history \
  --source-map ./workspace/600519/assets/research_templates/consumer.source-map.json
dayu-cli research-template copy consumer --base ./workspace
dayu-cli write --ticker AAPL \
  --template ./workspace/assets/research_templates/common-plus-consumer.md
```

`research-template` 会把包内行业模板复制到 `workspace/assets/research_templates/`，当前内置 `common`、`consumer`、`cyclical`、`technology`、`financial`。`recommend` 可根据手动传入的 facet 标签或包含 `company_facets` 的 write manifest 推荐模板；`compose` 会把通用深挖模板与行业模板合成为 `common-plus-*.md`，可直接作为 `write --template` 输入；`monitoring-rules` 会从模板的“监控变量”小节生成本地规则草案 JSON，并附带模板级数据源候选与 `binding_status=unbound`；`source-map` 会把这些候选源映射到 Dayu fins tools 或外部 provider 占位字段，仍不执行真实 provider 调用；`validate-source-map` 用于校验规则草案和 source-map 是否一致；`package-manifest` 会生成全部模板的索引、监控变量数量、数据源数量和 validation 摘要；`materialize` 会一键落盘指定模板或根据 write manifest 选择模板的合成模板、research workbook、初始 progress report、rules、source-map、package manifest、本地 research guide、`{template}.bundle.json`、已校验的 dry-run monitoring plan，以及 monitoring/workbook/report 三类状态快照。新 manifest 若包含完整 research-template provenance，materialize 会复用写作时已经确认的 resolved template；只有旧 manifest 缺少 provenance 时才回退到 facet 推荐，部分或非法 provenance 会直接失败。它会从 `manifest.config.ticker/company` 继承研究对象，也可由 `--ticker/--company` 显式覆盖；身份会继续进入 guide、bundle、monitoring-plan 和状态快照。其中 research guide 面向人工使用，bundle JSON 面向未来 Web UI、调度器和持仓监控读取，并保留 `automation_status=manual_review`，不会提前启用自动告警。`list-bundles` 会发现标准 workspace 目录中的 bundle 并汇总健康状态；`validate-bundle` 会重新检查 schema、workbook、progress report 指纹与所有本地工件，失效时返回非零退出码；自动生成的 monitoring plan 仍固定为 dry-run，未绑定源会阻止任务进入复核就绪状态，并且始终禁止自动执行；`monitoring-plan` 可在 bundle 或 source-map 变化后显式重建计划。`validate-monitoring-plan` 会核对计划结构、任务计数和输入文件 SHA-256，输入变化后会把旧计划标记为失效；初始化状态通常为 monitoring=`blocked`、workbook=`not_started`、report=`current`，三个 JSON 可直接作为 Web UI/看板入口。显式 `--recursive` 可扫描 `workspace/<ticker>/assets/research_templates/`，并在状态快照中生成逐 ticker 的组合级 rollup；默认仍只扫描当前 workspace。

使用 `write --research-template` 后，最终 `manifest.json` 的 `config` 会记录 `research_template_requested_name`、`research_template_resolved_name` 和 `research_template_selection_mode`。因此 auto 请求、实际行业路由和显式 named 选择均可审计；旧 manifest 缺少这些字段时仍按空值兼容读取。

`write --materialize-research` 是显式的写后动作：只有写作流水线成功后才读取最终 manifest，并生成 bundle、workbook、progress report、dry-run monitoring plan 与三类状态快照，默认写入 `workspace/{ticker}`。已有工件会失败关闭，除非同时传入 `--overwrite-research`；若报告已成功但 materialize 失败，命令返回 `2` 并保留已完成的报告，不会把部分成功伪装成整体成功。该选项不能与 infer-only 的 `--infer` 或 `--summary` 同时使用。

单目标 research materialize 采用进程内异常回滚：写入前会保存全部受保护工件的原始字节，任一生成步骤或最终 bundle 校验失败时，删除本次新建文件并逐字节恢复被覆盖文件。因此普通异常不会留下半套 bundle，也不会因 `--overwrite-research` 损坏已有研究进度；该保证不等同于操作系统断电级事务。

通过 `research-template materialize --manifest` 创建的 bundle 会额外保存源 write manifest 的绝对路径、整文件 SHA-256、研究语义 SHA-256 和当时的模板选择。研究对象、company facets 或模板 provenance 变化时，`validate-bundle` 会将旧 bundle 标记为 unhealthy；仅章节进度、审计备注等无关字段变化时保持 healthy，并产生文件已变化的 warning。`--ticker/--company` 的显式研究对象覆盖仍然有效，不会被源 manifest 强制改回。

`rebind-bundle` 用于确认并刷新同一模板的 source binding：默认只预览，`--write` 只更新 bundle descriptor，保留 `before-rebind.<sha>.json` 不可变备份，不会重写 workbook、模板、规则或 source-map。若当前 manifest 已路由到另一个模板，命令会拒绝执行，要求重新 materialize 新模板。

`rollback-bundle-rebind` 可预览或精确恢复同目录的内容寻址备份，并在写入前保存当前 descriptor 作为 redo 备份。恢复结果会报告当下 validation；即使旧绑定因当前源状态而 unhealthy，也不会隐瞒。生成的 redo 备份可再次传入同一命令恢复前进状态。

Portfolio manifest 示例：

```json
{
  "schema_version": 1,
  "portfolio_type": "research_monitoring_portfolio",
  "targets": [
    {"ticker": "AAPL", "company": "Apple Inc.", "template": "technology"},
    {"write_manifest": "workspace/0005.HK/manifest.json"}
  ]
}
```

`preview-portfolio` 会无写入解析全部目标，列出将创建或覆盖的工件，并在现有生成物需要 `--overwrite` 时返回非零。`materialize-portfolio` 会复用同一冲突门，再为每个 ticker 写入隔离目录、bundle 与 dry-run plan，最后生成 `research-portfolio.materialization.json` 和递归 `monitoring-status.json`。单个目标运行失败会记录在报告中并令命令返回非零，但不会抹掉其他成功目标；使用 `--overwrite` 可重建生成物。

`scheduler-manifest` 把 monitoring-plan 导出为平台无关任务清单，记录 cadence、timezone、计划指纹和验证命令 argv。所有 job 固定 `enabled=false`，trigger 仍为 `binding_status=unbound`；只有 `ready_for_review` 任务会标记为人工启用候选，本命令不会创建 cron、Windows 计划任务或调用数据 provider。`validate-scheduler-manifest` 会重新检查 disabled/unbound 安全约束、summary、argv、实时计划状态和 SHA-256；清单被改为启用或计划变化后返回非零。

Source binding approval 示例：

```json
{
  "schema_version": 1,
  "approval_type": "research_monitoring_source_binding",
  "template": "consumer",
  "approved_by": "research-owner",
  "approval_reference": "review-2026-001",
  "bindings": [
    {
      "source": "financial_statements",
      "selected_tool": "get_financial_statement",
      "selected_fields": ["revenue", "gross_profit"]
    }
  ]
}
```

`source-bindings` 默认只预览。`--write` 仅允许绑定 source-map 已声明的 `dayu_fins_tool`、候选 tool 和字段子集，修改前会创建带原内容 SHA-256 前缀的不可变备份。外部 placeholder 会被拒绝；source-map 更新后旧 monitoring-plan 会因输入指纹变化失效，需要重新生成并复核。

`rollback-source-bindings` 同样默认只预览，只接受与 source-map 同目录、模板和 source 集一致、文件名 SHA-256 前缀与内容吻合的 `before-bindings` 或 `before-rollback` 快照。`--write` 在每次恢复前都会先创建新的 `before-rollback` 内容寻址快照，再逐字节恢复目标 source-map；因此既能撤销绑定，也能恢复撤销前的绑定态。每次状态切换都会令旧 monitoring-plan 变为 stale，必须重新生成并复核。

`source-binding-history` 只读发现 source-map 同目录下的 `before-bindings` 与 `before-rollback` 快照，输出当前绑定态、快照类型、指纹、已绑定 source 和逐项诊断。内容损坏、文件名指纹伪造、模板或 source 集漂移不会被静默跳过，而会令 validation 失败并返回非零。

`research-workbook` 把模板中的买方问题、经营拆解、必查证据、监控变量、否决项和结论写法转换为机器可读 JSON。每项带稳定 ID、`status=open`、回答槽、证据槽和分析师备注，并保留 ticker/company 与源模板指纹；默认只预览，`--write` 才落盘，重复写入需显式 `--overwrite`。该工件仍为 `manual_review`，不会自动填写结论或调用外部数据源。

`materialize` 和 `materialize-portfolio` 会把 research workbook 作为标准 bundle 工件一并生成，guide 与 bundle descriptor 都会引用它，bundle capability 标记为 `track_research_evidence=true`。Portfolio 预览会把 workbook 纳入目标级冲突门，因此已有工作簿不会在缺少 `--overwrite` 时被重建。

`validate-research-workbook` 检查 schema、目标身份、模板指纹、section/item ID 唯一性、状态、回答和证据记录。`answered` 项必须有非空回答；当 `evidence_required=true` 时还必须至少包含一条带 `source`、`reference`、`finding` 的证据。命令会根据项目实时推导 `live_summary` 与完成态；工作簿内缓存的 summary/完成态过期只产生 warning，结构损坏、无证据结论或模板漂移则返回非零。

`validate-bundle` 会继续深检 bundle 引用的 research workbook，并核对 workbook 与 bundle 的 template、ticker、company 是否一致。合法研究进度中的缓存统计过期只作为 bundle warning；工作簿损坏、身份错配或证据完整性失败会令整个 bundle 不健康，并传播到 bundle discovery 与后续状态入口。

`update-research-workbook` 按稳定 item ID 更新状态、回答、分析师备注，并可从 `--evidence-file` 追加一条证据对象或对象数组。命令默认只预览；`--write` 会先创建 `before-update.<sha256>.json` 不可变备份，再自动刷新 summary 与 completion status，并且只有最终工作簿通过完整校验才会写入。证据对象最少包含 `{"source":"annual_report","reference":"2025 annual report p.42","finding":"同店销售同比增长 8%"}`。

`rollback-research-workbook` 默认预览，只接受同目录、文件名 SHA-256 与内容吻合、template/target 一致且通过完整校验的 `before-update` 快照。`--write` 在恢复前会把当前工作簿也保存成新的 `before-update` 快照，因此同一命令既能 rollback，也能用生成的 redo backup 恢复更新后的状态。

`workbook-status` 汇总 workspace 中工作簿的健康度、派生完成态和 item 状态计数；`--recursive` 可扫描 `workspace/<ticker>/assets/research_templates/` 并保留每个 ticker/company 的逐文件诊断。聚合只采信通过校验的 workbook，损坏文件仍会显示并令总体状态为 `unhealthy`；`--write` 可生成 `research-workbook-status.json` 供 Web UI 或组合看板读取。

`materialize-portfolio` 会在每个 ticker workspace 写入本地三类快照，并在批量结束后额外写入递归 monitoring、workbook 和 report status，把路径和完整状态嵌入 `research-portfolio.materialization.json`。若部分目标失败，组合快照只统计实际成功生成且通过校验的工件，失败目标仍保留在 materialization results 中。

通用与四个行业研究模板均包含独立的“估值与预期差”和“催化剂与时间轴”章节。工作簿将其提取为 `valuation` 与 `catalyst` 类别，要求研究者显式写出市场隐含假设、情景区间、下行保护、可交易预期差、验证日期和正反催化，而不是只给一个静态估值倍数或模糊事件清单。

所有模板还包含“管理层、治理与资本配置”，工作簿类别为 `management_governance`。通用问题检查指引兑现、激励、资本配置回报和少数股东风险；行业模板进一步检查渠道压货、周期高位扩产、股权激励稀释、金融风险文化等特有问题，避免用管理层访谈印象替代可追溯决策记录。

模板的“组合决策与风险预算”会生成 `portfolio_decision` 项，要求把研究边际、证据强度、下行/尾部损失、流动性、相关性和机会成本映射到初始/最大仓位，并预先写明加仓、减仓和退出条件。行业模板分别约束渠道与品牌尾部风险、商品 beta 与经营杠杆、高久期/技术替代、金融资产负债表杠杆，防止“看好”等同于无上限重仓。

`workbook-report` 把通过校验的 research workbook 忠实渲染为 Markdown 进度报告，展示实时完成态、逐项状态、回答、证据、分析师备注和所有开放研究缺口。默认只在终端预览；`--write` 写入同目录 `{template}.research-progress.md`，已有报告需 `--overwrite`。它不会调用模型、补写空白答案或把未完成草稿包装成投资结论。

标准 `materialize` 已自动生成第一版 progress report 并把它纳入 bundle。后续用 `update-research-workbook` 修改研究内容后，旧报告会被识别为 stale，bundle 也会暂时 unhealthy；运行 `workbook-report --write --overwrite` 刷新报告后恢复健康。旧版不含报告字段的 bundle 仍按原 schema 兼容校验。

`refresh-workspace` 把后续维护收束为一条安全命令：默认只预览，将 stale/缺失的 progress report、monitoring plan、三类 status 和 research guide 列为 create/refresh；`--write` 才在同一回滚边界内重建。它只处理可派生工件，workbook 损坏、核心 bundle 文件缺失、源 write manifest 语义漂移等问题会阻断刷新，必须先修复数据或使用对应的 rebind/rollback 流程。

报告首行包含机器可读双指纹：workbook 使用 canonical JSON 语义 SHA-256，Markdown body 使用独立 SHA-256。`validate-workbook-report` 会重新校验 workbook、来源指纹和正文完整性；只调整 JSON 缩进/键顺序不会误报，但研究内容更新会标记 `stale=true`，手工改报告正文会标记 `report_tampered=true`，两者都返回非零并要求重新生成或调查。

`workbook-report-status` 自动发现标准 `{template}.research-progress.md`，配对同目录 research workbook，并汇总 current、stale、tampered、missing-workbook 状态；`--recursive` 支持组合目录，`--write` 生成 `research-workbook-report-status.json`。只有双指纹与来源校验全部通过的报告计入 current，任何失效项都会保留逐文件诊断并令总体状态为 `unhealthy`。

命令说明：
- 写任何章节前，系统都会先检查当前 `ticker` 的写作 manifest 是否已有“公司级 facets”结果；若缺失，会自动先推理一次，再继续写作。
- 默认会复用 manifest 中已有的“公司级 facets”，不会每次重跑。
- 显式传 `--infer` 时，只会强制重跑一次“公司级 facets”并写回 manifest，随后立即退出，不进入章节写作。
- 按场景使用参数：
  - 第一次完整写报告：直接运行 `dayu-cli write --ticker AAPL`。
  - 上次写到一半中断，想从已有结果继续：直接重新运行同一条命令即可；默认就是 `--resume`。
  - 只想快速出初稿，不想等待审查和修复：加 `--fast`。
  - 上一次是用 `--fast` 跑的，想继续沿用这套“只写正文”的方式：继续加 `--fast` 再运行。
  - 只想重写某一章正文：用 `--chapter "章节名" --fast`。
  - 前面章节还没完全通过检查，但你仍然想先生成第 0 章或第 10 章看结果：加 `--force`。
  - 只想刷新公司级归因，不进入正式写作：用 `--infer`。
- 章节不满意时，推荐这样处理：
  - 正常模式 `write` 写完后，发现第 8 章不满意：先运行 `dayu-cli write --ticker AAPL --chapter "第8章的章节名"` 重写这一章；再运行 `dayu-cli write --ticker AAPL`，把新章节应用到整份报告。
  - `write --fast` 写完后，发现第 8 章不满意，且你还想继续保持“快速草稿”模式：先运行 `dayu-cli write --ticker AAPL --chapter "第8章的章节名" --fast` 重写这一章；再运行 `dayu-cli write --ticker AAPL --fast`，把新章节应用到整份草稿报告。
  - 单独重写某一章时，不会自动重建第 0 章和第 10 章。
  - 重写某一章后，再跑一次全文 `write` 时，系统会重新生成整份报告文件；但默认 `--resume` 会跳过当前模式下已经完成的章节，所以第 0 章和第 10 章如果已完成，通常不会自动重写。
  - 如果你改动了中间章节后，希望第 0 章和第 10 章也反映新的内容，建议依次重跑该中间章节、第 10 章、第 0 章，最后再运行一次全文 `write`。

### 3.7 财报预处理：`process`

命令用途：
把已下载或已上传的财报做结构化预处理，并导出快照。

参数 / 说明：

| 参数 | 说明 |
|------|------|
| `--ticker` | 必填，股票代码 |
| `--document-id` | 可选，仅处理指定文档 ID；可重复传入，也支持单个参数中用逗号分隔多个 ID |
| `--overwrite` | 可选，覆盖已存在结果 |
| `--ci` | 可选，额外导出 `search_document` 与 `query_xbrl_facts` 快照 |
| `--base` | 可选，工作区根目录，默认 `./workspace` |
| `--config` | 可选，配置目录，默认 `workspace/config` |

命令示例：

```bash
dayu-cli process --ticker AAPL --overwrite
```

常见命令示例：

```bash
dayu-cli process --ticker AAPL
dayu-cli process --ticker AAPL --ci
dayu-cli process --ticker AAPL --ci --document-id fil_001 --document-id fil_002
```

命令说明：
- 预处理命令主要供开发和数据准备场景使用，最终用户通常不需要手动执行。
- 快照会写入 `workspace/portfolio/{ticker}/processed`。
- 传入 `--document-id` 时，只会重建这些文档的快照；不会清空同一 ticker 下其它 processed 结果。

## 4. 自动写作详解

`write` 命令怎么用，在前面已经说明清楚。  
这一节更关心另一件事：

- 当你想把报告写成自己满意的样子时，应该怎么理解写作流程
- 理解流程后，应该优先改模板的哪里

### 4.1 写作流程

自动写作的顺序可以先记成一条主线：

1. `infer`
2. 第 1-9 章
3. 第 10 章
4. 第 0 章
5. 来源清单（如果模板中存在）

你可以这样理解这条流程：

- `infer` 先判断这家公司属于什么业务类型、有哪些关键约束。
- 第 1-9 章先把主体分析写出来，这部分是整份报告的事实和判断基础。
- 第 10 章再基于前面各章，回答“是否值得继续深研与待验证问题”。
- 第 0 章最后回填“投资要点概览”，它不是独立开写，而是对前面结果做浓缩。
- 来源清单最后统一整理，不需要你手写。

为什么先理解这个流程很重要：
- 因为模板不是“想到什么就加什么”。
- 某个内容应该放在第 1-9 章、第 10 章，还是第 0 章，取决于它在这条流程里承担什么作用。
- 你先知道系统怎么写，再去改模板，通常会少走很多弯路。

### 4.2 第 10 章、第 0 章和来源清单有什么特殊性

这三个部分和普通章节不一样，改模板时要单独看待。

第 10 章 `是否值得继续深研与待验证问题`：
- 它不是普通分析章，而是“研究决策章”。
- 它更适合回答：现在值不值得继续投入研究资源；如果继续，接下来最该验证什么。
- 这章的重点不是重复前文，而是基于前文做取舍和排序。
- 标题不要改。你可以改内容框架，但不要把它改名成别的标题。

第 0 章 `投资要点概览`：
- 它是整份报告最后给读者看的“快速入口”。
- 这章更适合浓缩结论、核心判断和最重要的不确定性，不适合再铺一遍细节。
- 标题不要改。你可以改里面的小节和表达方式，但不要改一级标题。

来源清单：
- 它是末章，用来汇总整份报告的证据出处。
- 这章主要是为了让你快速检查“这份报告到底引用了什么”，不是拿来承载新的分析。
- 标题也不要改。

一级章节修改时，建议记住这条边界：
- `投资要点概览`、`是否值得继续深研与待验证问题`、`来源清单` 这三个一级标题保留原名。
- 修改 `是否值得继续深研与待验证问题` 标题会使这一章变成普通章节。
- 删除 `来源清单` 报告里就没有 `来源清单` 。
- 除这三个之外，其它一级章节的标题、顺序和数量都可以按你的研究框架调整。

### 4.3 什么时候应该改模板

如果你遇到下面这些情况，优先改模板，而不是先改 prompt：

- 报告整体导向不对，例如总在证明公司“为什么好”
- 某一章总是写偏，例如写成竞争百科、管理层赞歌或财务复述
- 某些信息对你很重要，但模型总是不写
- 某些内容只适合少数公司，但模型总是机械地写出来

你可以把模板理解成几层：

- high level：整篇文章怎么组织
- detail level：每一章内部怎么展开
- 条件项：什么内容只在特定公司、特定证据条件下才写

先想清楚自己不满意的是哪一层，再动模板，会比“到处加规则”更有效。

### 4.4 怎么改模板：先改文章骨架

如果你对整份报告都不满意，先改 high level，也就是整篇文章骨架。

**这里最重要的一点是：**

- 第 1-10 章不是固定编制。
- 你完全可以把普通分析章节改成 3 章、4 章、6 章，或者按你自己的研究框架重排。
- 系统并不要求你必须保留“第 1 章到第 10 章”这种数量和顺序。

你可以把“改文章骨架”理解成：决定整份报告一共要有哪些一级章节，以及这些一级章节按什么顺序出现。

最常见的文章骨架修改有：

- 调整一级章节顺序
- 新增或删除普通一级章节
- 把原来的 1-10 章改成更少或更多章
- 让报告更偏“继续研究 / 暂缓 / 放弃”的筛选框架
- 让报告更偏“重建公司全貌”，而不是“归纳优点”

适合先改文章骨架的场景：

- 报告整体方向不对
- 每一章都在写，但串起来不是你想要的研究路径
- 你希望读者先看到“值不值得继续看”，还是先看到“公司到底是什么”

改文章骨架时，优先问自己三个问题：

1. 这份报告最后要帮我做什么判断？
2. 我希望读者按什么顺序建立判断？
3. 哪些一级章节是真正必要的，哪些只是习惯性保留？

改文章骨架时，一级章节标题可以分成两类看：

- 普通一级章节：可以随便改标题、顺序和数量。你想保留 3 章、4 章、7 章都可以。
- 特殊一级章节：`投资要点概览`、`是否值得继续深研与待验证问题`、`来源清单` 建议保留原名。

其中最需要记住的是：

- `是否值得继续深研与待验证问题` 这个标题如果改掉，就会变成普通章节，不再按“研究决策章”处理。

如果这三个问题没想清楚，直接去改某一章的小节，通常只会把局部修得更复杂，不能真正改善整份报告。

### 4.5 怎么改模板：再改章节骨架

当整篇文章方向没问题，但某一章总是写偏时，再改 detail level，也就是章节骨架。

你可以把“改章节骨架”理解成：一级章节已经定了，现在再决定这一章里面具体怎么展开。

章节骨架通常包括：

- 本章目标
- 固定小节
- 小节标题
- 每个小节想回答的问题

适合先改章节骨架的场景：

- 标题看起来没问题，但模型总是抓错本章主问题
- 你希望模型固定输出某几个关键判断
- 你想删掉长期低价值的小节
- 你想把某一章从“信息罗列”改成“研究判断”

一个简单判断法：

- 如果你不满意的是“整份报告该有哪些章、这些章怎么排”，先改文章骨架。
- 如果你不满意的是“某一章里面该分哪几个小节、每个小节回答什么”，先改章节骨架。

### 4.6 条件项怎么用

条件项适合表达“只对某类公司才有意义”的补充内容。

例如：

- 只有平台公司才适合写网络效应
- 只有跨区域经营的公司才值得写重要 geography
- 只有证据足够精确时，才值得写更细的 segments、份额、客户集中度

经验法则：

- 所有公司都该写的，放进文章骨架或章节骨架
- 只有部分公司才该写的，放进条件项
- 某类行业优先看的判断入口，放进 `preferred_lens`
- 某类行业才值得补充的局部内容，放进 `ITEM_RULE`

`preferred_lens` 和 `ITEM_RULE` 可以这样理解：

- `preferred_lens`：这一章优先从什么视角进入判断
- `ITEM_RULE`：在特定条件下，额外补哪些局部内容

不要把写法技巧、句式要求、修辞规则塞进条件项。条件项更适合管“写不写什么”，不适合管“怎么写得好看”。

### 4.7 实用原则

好的模板，不是让模型“写更多”，而是让模型：

- 更快抓住这章真正要回答的问题
- 更少写偏
- 在证据不够时宁可少写，也不硬写

如果某条模板规则只是让报告更花哨、看起来更专业，但不帮助你更快做“继续研究 / 暂缓 / 放弃”的判断，通常就不值得加。

改模板时，一个很实用的顺序是：

1. 先改文章骨架
2. 再改章节骨架
3. 最后才补条件项

如果报告方向不对，通常先改“结构”和“本章问题”，效果会比一开始就堆很多条件规则更明显。

### 4.8 自动写作会产出什么

自动写作会在输出目录下按章节落盘。常见文件包括：

- `manifest.json`：记录章节状态，以及当前公司的“公司级 facets”等写作上下文
- 每章最终的 `.md`：这是你最该优先看的正文结果
- 对应的 `*_audit.json`：如果你想知道某章为什么没写好，可以看这里
- `run_summary.json`：整次写作的双模型质量、用量、路由与预算凭证；保留原有失败摘要，并记录主写/审计模型职责、章节门禁结果、返修次数、证据确认次数、锚点修复次数，以及按职责和 scene 聚合的请求数、Token、replay、可选成本估算、后备切换和预算阻断原因
- `challenger_comparison.json`：仅在显式 Challenger 运行后生成，记录两次运行的兼容性、模型计划变化、质量退化/改进、路由稳定性、成本差异和保守晋升建议
- `write_model_challenger_promotion_proposal_v1` 导出文件：仅在显式请求且原始比较建议晋升时生成，绑定两份摘要和比较产物，只供人工审查，不属于输出目录中的自动运行产物，也不授权配置变更

`run_summary.json` 中的 `gate_status` 表示本次运行是否满足当前模式的发布门禁。正常模式下，章节必须经过审计；`chapters[].outcome` 会区分首次通过、返修后通过和被阻断。`audit.failed_count` 只统计真正的审计失败；审计已经通过但仍被其他运行条件阻断的章节单独计入 `audit.gate_blocked_count`。`--fast` 模式只生成草稿，因此即使 `gate_status` 为 `passed`，`audit.required` 仍为 `false`，章节会标记为 `passed_without_audit`，不能当作 MiMo 已完成质量复核。

`model_usage.usage_status` 会明确区分完整、部分和不可用的 usage 覆盖；`model_usage.cost` 只有在 `llm_models.json` 为相关模型配置了当前价格时才估算。成本不会使用代码内置价格，也不替代供应商账单。

`model_routing` 是增量兼容的后备路由凭证。`fallback_switch_count` 记录实际发出的后备调用数，`routes[]` 按 scene、主模型、后备模型、触发错误类型和后备调用状态聚合。`fallback_call_status=completed` 只表示后备模型调用没有返回应用错误，不代表章节已通过解析、审计或发布门禁；最终质量仍以 `gate_status` 和 `chapters[]` 为准。旧运行摘要没有该字段时，`write --summary` 会显示“未记录”，不会把未知历史误报为零次切换。

`budget.status` 为 `disabled`、`within_budget` 或 `blocked`。预算阻断时，运行级 `gate_status` 一定为 `blocked`，`publication_status` 为 `blocked_by_budget`；`budget.block` 会保存阻断发生在 Scene 准入还是 usage 结算阶段，以及对应模型、维度、上限和预测值。

历史运行可以按当前模型目录的价格只读重估，无需重新调用模型：

```bash
dayu-cli write --summary --reprice-costs --ticker AAPL
```

该命令只在内存中重算 `model_usage.cost` 并打印结果，不会改写 `run_summary.json`。因此它适合补录价格或统一比较历史运行，但结果代表当前配置价格下的估算，不会篡改当时的运行凭证，也不能代替供应商账单。

如果你只关心结果，优先看：

- 每章最终的 `.md`
- `dayu-cli write --summary --ticker AAPL` 的摘要输出
- `run_summary.json` 中的运行级门禁与逐章质量轨迹
- 需要排查具体违规时，再看对应的 `*_audit.json`

## 5. tool trace 分析

如果你在 `prompt` / `interactive` / `write` 时开启了 trace：

```bash
dayu-cli prompt \
  "总结最新财报风险" \
  --ticker AAPL \
  --enable-tool-trace
```

trace 默认写入 `workspace/output/tool_call_traces`。分析命令：

```bash
python -m utils.analyze_tool_trace \
  --input ./workspace/output/tool_call_traces \
  --ticker AAPL \
  --output ./workspace/trace_analysis_AAPL.md
```

这个脚本会输出：
- 工具级诊断总表（成功率、截断率、载荷大小、错误分布）
- 详细失败签名（例如 URL 拦截、HTTP 状态、超时等），而不只停留在粗粒度 `error_code`
- 单独汇总 `sse_protocol_error`，直接展示 `partial_tool_name`、失败时的 `arguments` 前缀以及对应 `sse_error_*.json` 冷存路径
- 围绕“降低模型认知负担”的信号分析
- 截断续读、重复调用、上下文负担、失败与降级诊断
- 各 run / turn 的工具调用链与 trace 完整性检查
- 面向工具设计的优化建议

### 5.1 网页抓取诊断

当你遇到“浏览器能打开，但 `fetch_web_page` / `requests` / Playwright 访问失败”的 URL 时，可以用下面的脚本把同源证据导出成 JSON：

```bash
python -m utils.diagnose_web_access \
  --url "https://investor.pddholdings.com/news-releases/news-release-details/pdd-holdings-announces-fourth-quarter-2025-and-fiscal-year-2025" \
  --output ./workspace/output/web_diagnostics/pdd-ir.json
```

如需用有界面 Chrome 观察实际打开过程：

```bash
python -m utils.diagnose_web_access \
  --url "https://example.com" \
  --headed \
  --channel chrome
```

如需在人工完成验证后导出可复用的浏览器状态：

```bash
python -m utils.diagnose_web_access \
  --url "https://www.reuters.com/..." \
  --headed \
  --channel chrome \
  --manual-wait-seconds 30 \
  --pause-before-snapshot \
  --storage-state-out ./workspace/output/web_diagnostics/storage_states/www.reuters.com.json
```

仓库内也提供了更省事的包装脚本：

```bash
./utils/diag_web.sh "https://www.reuters.com/..."
```

它默认会用有界面 Chrome 打开页面，并等待 30 秒供你人工操作；30 秒到达后会自动继续采样页面状态并保存诊断结果。

它也会按 host 自动读写 `workspace/output/web_diagnostics/storage_states/<host>.json`：
- 第一次运行时，若状态文件不存在，只会导出新的 state，不会报错
- 后续再运行同一 host 时，会自动把已有 state 喂回诊断脚本

脚本会导出：
- 浏览器主文档 request headers 与导航结果
- 当前仓库 `fetch_web_page` 的调用结果，以及工具层 `extra.internal_diagnostics`
- `requests` 将发送的 headers 与实际 GET 结果
- Playwright 观察到的网络请求摘要
- 浏览器页面的文本/HTML 前缀，便于判断 challenge/access gate

若某些受保护站点只能靠人工浏览器通过验证，可把导出的 state 文件放进 `run.json.web_tools_config.playwright_storage_state_dir` 指向的目录；`fetch_web_page` 会按 host 自动复用对应的 `<host>.json`。

### 5.2 批量诊断与 CI

如果你的目标不是“修一个站点”，而是让 CI 持续产出一批可分析的 `web_diagnostics` 原始证据，再由后续分析去定位 `fetch_web_page` 的 root cause，推荐直接使用 `diagnose_web_access` 的批量模式：

```bash
python -m utils.diagnose_web_access \
  --url-file ./utils/web_ci_urls.jsonl \
  --run-label 20260406-sample \
  --storage-state-dir ./workspace/output/web_diagnostics/storage_states
```

仓库里已经附带了一份 sample corpus：`./utils/web_ci_urls.jsonl`。它覆盖常见新闻网站、财经网站和政府/监管组织，并包含中国与海外站点，可直接作为第一轮诊断样本。

如果你直接使用仓库内的包装脚本：

```bash
./utils/diag_web_batch.sh ./utils/web_ci_urls.jsonl
```

它默认也会开启有界面 Chrome，并为每条 URL 等待 30 秒供你人工操作；30 秒到达后会自动继续采样并保存诊断结果。

它会对每个 URL 逐条导出同源诊断 JSON，单条诊断里默认包含三条访问路径：
- 人工/自动浏览器侧的 Playwright 诊断
- `requests` 侧的实际请求结果
- 当前仓库 `fetch_web_page` 的调用结果

如果你需要人工浏览器先完成验证，再采样页面状态并保存可复用 cookie / local storage，可在批量模式下继续加：

```bash
python -m utils.diagnose_web_access \
  --url-file ./utils/web_ci_urls.jsonl \
  --run-label 20260406-manual \
  --headed \
  --channel chrome \
  --manual-wait-seconds 30 \
  --pause-before-snapshot \
  --storage-state-dir ./workspace/output/web_diagnostics/storage_states
```

只有显式传入 `--pause-before-snapshot` 时，脚本才会在等待结束后继续要求你按回车确认。

默认每条 URL 都会在独立子进程里执行，并在执行前删除 `workspace/.dayu/session`，避免进程内 Session、warmup host 和 Playwright 单例污染下一条 URL。这样 CI 侧只需要稳定地产出 `web_diagnostics`，后续分析和优化可以基于这些原始结果继续进行。

URL 文件支持两种格式：

1. JSONL：适合带元数据的长期基准集

```json
{"url":"https://finance.yahoo.com/quote/AAPL/","label":"Yahoo Finance AAPL","region":"foreign","category":"quote"}
{"url":"https://www.reuters.com/markets/companies/AAPL.OQ/","label":"Reuters AAPL","region":"foreign","category":"company-page"}
{"url":"https://www.stcn.com/article/detail/1568835.html","label":"证券时报示例","region":"china","category":"news"}
```

2. TXT：每行一个 URL，适合快速试跑

```text
https://finance.yahoo.com/quote/AAPL/
https://www.reuters.com/markets/companies/AAPL.OQ/
```

常用参数：
- `--storage-state-dir`：按 host 自动读写 storage state 目录
- `--headed`：启用有界面浏览器，便于人工观察和手工通过验证
- `--manual-wait-seconds`：导航后先额外等待多少秒
- `--pause-before-snapshot`：人工确认完成后，再按回车继续采样和保存 state
- `--skip-playwright`：只跑 `requests` 与 `fetch_web_page`
- `--skip-tool-fetch`：只收集浏览器与 `requests` 诊断，不调用 `fetch_web_page`

输出目录默认写到 `workspace/output/web_diagnostics/<run_label>/`，其中包括：
- `corpus.normalized.jsonl`：本轮归一化后的样本集
- `diagnostics/`：每条 URL 的完整诊断 JSON
- `results.jsonl`：从完整诊断提炼出的批量索引，便于后续程序分析
- `summary.json` / `summary.md`：本轮批量诊断汇总

如果你希望我直接参与 CI 优化流程，那么 CI 侧只需要跑完这一步并保留 `workspace/output/web_diagnostics/<run_label>/`，后续我就可以基于这批 `web_diagnostics` 结果做差异分析、找 root cause，并继续优化 `fetch_web_page`。

## 6. 渲染输出

Markdown 报告渲染入口：

```bash
dayu-render <输入文件.md> [输出文件]
```

常见示例：

```bash
dayu-render workspace/draft/AAPL/AAPL_qual_report.md
dayu-render workspace/draft/AAPL/AAPL_qual_report.md report.pdf
dayu-render workspace/draft/AAPL/AAPL_qual_report.md report.html
```

支持格式：
- `.docx`（默认）
- `.html`
- `.pdf`

说明：
- 生成 **HTML**、**Word（.docx）** 需要 `pandoc`；生成 **PDF** 需要 `pandoc`（先由 Pandoc 生成 HTML）以及 Chrome（Headless 打印为 PDF）
- 若 Chrome 不在标准位置，可设置 `PUPPETEER_EXECUTABLE_PATH`
- 渲染器会保留 Markdown 里的普通换行；例如列表项里单独一行的“标签”与下一行正文，在 `.docx` 中会继续换行显示

## 7. 配置文件从哪里改

大多数用户只需要关注这三个位置：

| 文件/目录 | 用途 |
|-----------|------|
| `workspace/config/llm_models.json` | 模型配置、API Key 占位符 |
| `workspace/config/run.json` | Agent 行为、Host 配置、工具超时、trace、budget、limits；CLI / WeChat 的 chat 与 prompt 默认执行参数也在运行时由 Host 基于这里继续收敛 |
| `workspace/config/prompts/` | prompt 资产 |

建议修改方式：
- 想换模型：改 `llm_models.json`
- 想新增自定义模型：先在 `workspace/config/llm_models.json` 里添加模型配置；再把该模型加入对应 scene manifest 的 `workspace/config/prompts/manifests/*.json -> model.allowed_names`，必要时改 `model.default_name`；如果该模型要长期参与 `interactive` 多轮会话，建议同时给该模型补 `runtime_hints.conversation_memory`
- 想调 Agent 行为：改 `run.json`；其中 `conversation_memory` 控制 `interactive` 多轮会话的历史预算与压缩策略
- 想改系统提示词和任务提示词：改 `prompts/`

配置说明请看：
- [dayu/config/README.md](dayu/config/README.md)

<a id="model-config"></a>

## 8. 模型配置

如果你只是临时切换模型，最简单的办法是在命令里直接传 `--model-name`。  
如果你想长期修改默认模型，或者接入一个新的模型，再改配置文件。

最常用的两个位置是：

- `workspace/config/llm_models.json`：定义“有哪些模型可以用”
- `workspace/config/prompts/manifests/*.json`：定义“每个场景默认用哪个模型”

### 8.1 怎么修改默认模型

每个场景都有自己的默认模型，配置在对应 scene manifest 里。

最常改的几个文件：

- `workspace/config/prompts/manifests/prompt.json`
- `workspace/config/prompts/manifests/interactive.json`
- `workspace/config/prompts/manifests/prompt_mt.json`
- `workspace/config/prompts/manifests/write.json`
- `workspace/config/prompts/manifests/audit.json`
- `workspace/config/prompts/manifests/confirm.json`

你主要看这一段：

```json
"model": {
  "default_name": "mimo-v2.5-pro",
  "allowed_names": [
    "mimo-v2.5-pro",
    "mimo-v2.5-pro",
    "deepseek-v4-flash"
  ],
  "temperature_profile": "write"
}
```

改默认模型时，通常只需要两步：

1. 把 `default_name` 改成你想用的模型名
2. 确认这个模型名已经出现在 `allowed_names` 里

例如：

- 想把 `write` 默认模型从 `mimo-v2.5-pro` 改成 `gpt-5.4`，就改 `workspace/config/prompts/manifests/write.json`
- 想把 `interactive` 默认模型改成 `qwen-plus-thinking`，就改 `workspace/config/prompts/manifests/interactive.json`
- 想把 `audit` / `confirm` 默认模型换掉，就分别改 `audit.json` 和 `confirm.json`

一个简单理解：

- `default_name`：这个场景默认会用谁
- `allowed_names`：这个场景允许切换到哪些模型
- `temperature_profile`：这个场景默认使用哪组温度参数，一般不用改

### 8.2 怎么添加新模型

如果现有模型不够用，你可以自己往 `workspace/config/llm_models.json` 里加一个新条目。

最简单的做法是：

1. 先复制一个最接近的现有模型配置
2. 改模型名、接口地址、鉴权头和能力参数
3. 再把这个模型名加入对应 scene manifest 的 `allowed_names`
4. 如果希望它成为默认模型，再修改 `default_name`

例如，你可以复制一段现有配置，改成这样：

```json
"my-model": {
  "runner_type": "openai_compatible",
  "name": "my-model",
  "endpoint_url": "https://api.example.com/v1/chat/completions",
  "model": "my-model",
  "headers": {
    "Authorization": "Bearer {{MY_API_KEY}}",
    "Content-Type": "application/json"
  },
  "timeout": 3600,
  "supports_stream": true,
  "supports_tool_calling": true,
  "max_context_tokens": 128000,
  "runtime_hints": {
    "temperature_profiles": {
      "write": {
        "temperature": 0.8
      },
      "audit": {
        "temperature": 0.2
      }
    }
  }
}
```

加完之后，再去对应 scene manifest，例如 `workspace/config/prompts/manifests/write.json`，把 `"my-model"` 加进 `allowed_names`。如果你想让它直接成为默认模型，再把 `default_name` 改成 `"my-model"`。

### 8.3 模型参数怎么理解

对最终用户来说，下面这些参数最重要：

- `name`：配置名。你在 `--model-name`、`default_name`、`allowed_names` 里写的就是它。
- `endpoint_url`：模型服务地址。
- `model`：真正发给服务商的模型标识。
- `headers`：鉴权和请求头，通常在这里放 API Key 占位符。
- `timeout`：单次请求超时时间，单位秒。
- `supports_stream`：是否支持流式输出。
- `supports_tool_calling`：是否支持工具调用。用于 `prompt`、`interactive`、`write` 的模型通常需要支持。
- `max_context_tokens`：模型可用上下文上限。

`runtime_hints.temperature_profiles` 里最常看到的是 `temperature`：

- `temperature` 越低，输出通常越稳、更保守
- `temperature` 越高，输出通常越发散、更有变化

通常可以这样理解：

- `write`：正文写作时的参数
- `overview`：第 0 章概览时的参数
- `audit`：审计场景的参数
- `decision`：第 10 章研究决策场景的参数
- `prompt`：单轮问答场景的参数
- `interactive`：交互对话场景的参数
- `infer`：公司类型与关键约束判断场景的参数

如果你只是新增一个模型，最稳的办法不是从零设计全部参数，而是复制一个相近模型，再按你的服务商要求做最小改动。

### 8.4 一个推荐顺序

如果你准备调整模型配置，建议按这个顺序来：

1. 先临时用 `--model-name` 试跑
2. 满意后再改 scene manifest 的 `default_name`
3. 如果现有模型都不合适，再去 `llm_models.json` 新增模型

这样做的好处是：

- 先验证效果，再改默认配置
- 不容易一上来改太多，最后不知道是哪一步导致结果变化

## 9. 文档导航

- 用户手册（当前文档）：[README.md](README.md)
- 开发手册总览：[dayu/README.md](dayu/README.md)
- Engine 包开发手册：[dayu/engine/README.md](dayu/engine/README.md)
- Fins 包开发手册：[dayu/fins/README.md](dayu/fins/README.md)
- 配置说明手册：[dayu/config/README.md](dayu/config/README.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)

## 10. 开源与许可证

本仓库采用 `Apache License 2.0` 开源协议发布。

你在分发或修改本项目时，至少需要注意三件事：

- 保留仓库中的 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)
- 对你修改过的文件添加明确变更说明
- 不要把仓库名称、作者名称或项目商标暗示成对你分发版本的背书

如果你准备贡献代码、文档或测试，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
