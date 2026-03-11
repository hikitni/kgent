# 05 Windows 运行指南

- 项目名称：**Kgent V3**
- 文档版本：v3.1
- 更新日期：2026-03-04

## 1. 安装

```powershell
# 克隆或下载项目后，进入目录
cd D:\AiGithub

# 安装依赖（rich 为必要，watchdog 为可选）
pip install -r requirements.txt
```

> `requirements.txt` 内容：
> ```
> rich>=13.0.0
> watchdog>=4.0.0
> ```

## 2. 配置

```powershell
# 复制配置模板
copy config.example.json config.json
```

用任意文本编辑器打开 `config.json`，修改 `watch_paths` 为你的工作目录：

```json
{
  "watch_paths": ["D:/my-project", "D:/work-docs"],
  "ignore_dirs": [".git", "node_modules", "__pycache__", ".daily_reporter", "reports"],
  "ignore_suffixes": [".log", ".tmp", ".swp", ".pyc"],
  "snapshot_root": ".daily_reporter",
  "output_root": "reports",
  "auto_snapshot_times": ["06:00", "18:00"],
  "max_file_size_kb": 1024
}
```

| 字段 | 说明 |
|---|---|
| `watch_paths` | 监控目录列表，支持多个 |
| `ignore_dirs` | 跳过的目录名（如构建产物、缓存）|
| `ignore_suffixes` | 跳过的文件后缀 |
| `snapshot_root` | 快照存储目录（自动创建）|
| `output_root` | 日报输出目录（自动创建）|
| `auto_snapshot_times` | Watch 模式下每天自动打快照的时间点 |
| `max_file_size_kb` | 大于此大小的文件只存哈希，不读取内容 |
| `ai_provider` | AI 提供商：`disabled`（默认）\| `zhipuai` \| `openai` \| `ollama` |
| `ai_model` | 模型名，如 `glm-4-flash`、`deepseek-chat`、`llama3` |
| `ai_api_key` | API 密钥（Ollama 可不填）|
| `ai_base_url` | 自定义端点，OpenAI 兼容或 Ollama 地址 |

## 3. 启动

### 3.1 交互式菜单（默认）

```powershell
python main.py
```

启动后进入主菜单：

```
  1  📸 打快照
  2  📋 浏览/管理快照
  3  🔍 对比快照
  4  📄 生成日报
  5  📑 日报管理
  6  ⏱  Watch（定时快照）
  7  ⚙️  查看配置
  8  📅 定时任务管理
  0  🚪 退出
```

> 状态栏实时显示快照总数、日报总数、监控目录数和自动快照时间。
> 每次回到主菜单时自动重载 `config.json`，修改配置无需重启。

### 3.2 单次快照（供计划任务调用）

```powershell
# 打一次快照后立即退出，无交互界面
python main.py snapshot

# 自定义标签
python main.py snapshot --label morning

# 指定配置文件
python main.py --config D:\work\config.json snapshot --label evening
```

> 此模式为 Windows 计划任务设计：任务到达时启动进程→打快照→进程退出，无需任何进程持续运行。

## 4. 典型工作流

### 日常使用（上班 → 下班）

```
上班时：主菜单 → 1（打快照）→ 标签填 morning → 确认
下班时：主菜单 → 4（生成日报）→ 选择"打日结快照"→ 生成 → 选择"立即打开"
```

### 查看历史变更

```
主菜单 → 2（浏览快照）→ 输入序号查看任意快照详情
主菜单 → 3（对比快照）→ 选起点 A 和终点 B → 查看变更摘要
```

## 5. 各功能说明

### 5.1 打快照（菜单 1）

手动扫描监控目录，为当前状态创建快照。可自定义标签（如 `morning`、`feature-done`）。

### 5.2 浏览/管理快照（菜单 2）

展示所有快照列表，支持：

| 输入 | 操作 |
|---|---|
| `序号`（如 `2`）| 查看详情：显示快照元数据 + 前 30 个文件（路径/哈希/行数）|
| `d+序号`（如 `d2`）| 删除快照：二次确认后删除文件并移除索引 |
| `0` | 返回主菜单 |

### 5.3 对比快照（菜单 3）

选择任意两个快照作为起点 A 和终点 B，显示：
- 变更文件总数、新增/修改/删除分布
- 行级净变化（+行 / -行）
- 高频变更文件类型 Top5
- 分状态文件明细列表

### 5.4 生成日报（菜单 4）

1. 选择快照区间（默认最后两个快照）
2. 可选：自动打一个"日结快照"作为终点
3. 生成机器版 Markdown（含完整变更数据和 diff 预览）
4. **如果配置了 AI：自动将机器版投送给 AI，用 `ai_report_prompt.md` 模板重写为叙述性日报，覆盖原文件**
5. 可选：用系统默认程序立即打开日报文件

> **AI 重写失败时**（网络超时、Key 错误等），自动保留机器版，不会丢失数据。

### 5.5 日报管理（菜单 5）

列出所有已生成的日报文件，支持：

| 输入 | 操作 |
|---|---|
| `序号`（如 `1`）| 用系统默认程序打开日报 |
| `d+序号`（如 `d1`）| 删除日报文件（二次确认）|
| `s+序号`（如 `s1`）| 用 AI 全文重写该日报，覆盖原文件 |
| `0` | 返回主菜单 |

### 5.6 Watch 定时快照（菜单 6）

按 `config.json` 中的 `auto_snapshot_times` 每天定时自动打快照，无需人工干预。按 `Ctrl+C` 退出。

### 5.7 查看配置（菜单 7）

分组展示当前 `config.json` 全字段（监控目录、存储设置、定时时间、忽略规则）。
输入 `o` 可直接用系统编辑器打开配置文件。

## 6. Windows 计划任务（推荐：替代 Watch 模式）

计划任务方案将“定时触发”的责任转移给操作系统，程序本身无需持续运行。

### 6.1 通过菜单 8 一键注册（推荐）

```
python main.py  →  菜单 8（📅 定时任务管理） →  [r] 注册/更新全部任务
```

程序会自动读取 `auto_snapshot_times`，为每个时间点创建一条 `DailyReporter-HHMM` 计划任务，每天在对应时间自动运行：

```powershell
python "D:\AiGithub\main.py" --config "D:\AiGithub\config.json" snapshot --label morning
```

### 6.2 菜单 8 操作说明

| 输入 | 操作 |
|---|---|
| `[r]` | 注册/更新全部任务（以 config.json 为准、删除期旧任务）|
| `d+序号`（如 `d1`）| 删除单条任务 |
| `[D]` | 删除全部已注册任务 |
| `t+序号`（如 `t1`）| 立即触发该时间点快照 |
| `[0]` | 返回主菜单 |

### 6.3 时间点变更后更新任务

在 `config.json` 中修改 `auto_snapshot_times` 后，重新进菜单 8 → `[r]` 即可同步，程序会自动增加新任务、删除建除旧任务。

### 6.4 手动注册示例（备用）

若无法使用菜单 8，也可手动运行：

```powershell
schtasks /Create /F /SC DAILY /ST 06:00 /TN "DailyReporter-0600" `
  /TR "\"C:\Python311\python.exe\" \"D:\AiGithub\main.py\" --config \"D:\AiGithub\config.json\" snapshot --label morning"
```

## 7. 指定配置文件启动

```powershell
# 使用默认 config.json（进入交互菜单）
python main.py

# 指定其他配置文件进入交互菜单
python main.py --config D:\other-project\config.json

# 指定配置文件打单次快照
python main.py --config D:\other-project\config.json snapshot --label morning
```

## 8. AI 总结配置

AI 总结为**可选功能**，默认禁用（`ai_provider: "disabled"`）。配置后，在生成日报或日报管理页面可调用 AI 对日报进行智能总结。

### 8.1 配置流程

1. 按需安装 AI SDK（见下方）
2. 在 `config.json` 中配置 `ai_provider`、`ai_model`、`ai_api_key`等字段
3. （可选）编辑 `ai_report_prompt.md` 自定义日报格式
4. 下次生成日报时将自动调用 AI

**模板文件管理**：`ai_report_prompt.md` 位于项目根目录，可直接用文本编辑器修改。`{{report_data}}` 占位符会被替换为实际变更数据。模板路径通过 `config.json` 的 `ai_prompt_template` 字段指定。

### 8.2 智谱 AI（GLM 系列）

```powershell
# 安装 SDK
pip install zhipuai
```

`config.json` 配置：

```json
"ai_provider": "zhipuai",
"ai_model":    "glm-4-flash",
"ai_api_key":  "你的智谱APIKey",
"ai_base_url": ""
```

> API Key 在 [https://open.bigmodel.cn](https://open.bigmodel.cn) 账号中心申请。

### 8.3 OpenAI / DeepSeek / Moonshot

```powershell
# 安装 SDK
pip install openai
```

**OpenAI**：
```json
"ai_provider": "openai",
"ai_model":    "gpt-4o-mini",
"ai_api_key":  "你的OpenAI_APIKey",
"ai_base_url": ""
```

**DeepSeek**：
```json
"ai_provider": "openai",
"ai_model":    "deepseek-chat",
"ai_api_key":  "你的DeepSeek_APIKey",
"ai_base_url": "https://api.deepseek.com/v1"
```

**Moonshot**：
```json
"ai_provider": "openai",
"ai_model":    "moonshot-v1-8k",
"ai_api_key":  "你的Moonshot_APIKey",
"ai_base_url": "https://api.moonshot.cn/v1"
```

### 8.4 Ollama（本地大模型，无需 API Key）

1. 安装 Ollama：[https://ollama.com](https://ollama.com)
2. 拉取模型：
   ```powershell
   ollama pull llama3
   ```
3. 确认本地服务运行（默认 `http://localhost:11434`）：
   ```powershell
   ollama serve
   ```
4. `config.json` 配置：
   ```json
   "ai_provider": "ollama",
   "ai_model":    "llama3",
   "ai_api_key":  "",
   "ai_base_url": "http://localhost:11434"
   ```

> `ai_base_url` 留空时 Ollama 提供商自动使用 `http://localhost:11434`。

### 8.5 失败处理

| 懅景 | 表现 |
|---|---|
| SDK 未安装 | 红色错误提示，建议安装命令 |
| API Key 错误 | 显示具体错误信息 |
| 网络超时 | 显示超时提示，日报本身不受影响 |
| 模型不存在 | AI 提供商返回具体错误信息 |


## 1. 安装

```powershell
# 仅需一个依赖（watch 模式可选，report/snapshot 无需安装）
pip install watchdog
```

> `snapshot`、`list`、`report` 命令无任何第三方依赖，可直接运行。

## 2. 快速开始

```powershell
# 1. 复制配置文件
copy config.example.json config.json

# 2. 编辑 config.json，设置你的监控目录
# "watch_paths": ["D:/my-project", "D:/work-docs"]

# 3. 打一个初始快照（上班时）
python daily_change_reporter.py snapshot --label morning

# 4. 下班时生成日报（自动打终点快照）
python daily_change_reporter.py report

# 5. 查看所有快照
python daily_change_reporter.py list
```

## 3. 手动操作参考

```powershell
# 打快照（自定义标签）
python daily_change_reporter.py snapshot --label "feature-done"

# 查看所有快照
python daily_change_reporter.py list

# 生成日报（默认：最近两个快照）
python daily_change_reporter.py report

# 指定快照区间生成日报
python daily_change_reporter.py report --from 20260304-090000 --to 20260304-180000
```

## 4. watch 自动打快照模式

在 `config.json` 中配置：

```json
"auto_snapshot_times": ["06:00", "18:00"]
```

启动 watch：

```powershell
python daily_change_reporter.py watch --config config.json
```

watch 模式会在后台每 30 秒检查时钟，到达配置时间时自动打快照，按 Ctrl+C 退出。

## 5. Windows 计划任务配置（推荐）

通过计划任务实现**开机自动打快照 + watch 持续运行**，彻底解决漏打快照问题。

### 5.1 创建计划任务

打开"任务计划程序" → 创建基本任务，或使用 PowerShell 脚本：

```powershell
$action = New-ScheduledTaskAction `
  -Execute "python.exe" `
  -Argument "D:\AiGithub\daily_change_reporter.py watch --config D:\AiGithub\config.json" `
  -WorkingDirectory "D:\AiGithub"

$trigger = New-ScheduledTaskTrigger -AtLogOn -Delay "00:00:30"

$settings = New-ScheduledTaskSettingsSet `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit (New-TimeSpan -Hours 16)

Register-ScheduledTask `
  -TaskName "DailyChangeReporter" `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -RunLevel Highest
```

### 5.2 推荐参数说明

| 参数 | 建议值 | 说明 |
|---|---|---|
| 触发器 | 用户登录后延迟 30 秒 | 等待磁盘与 Python 环境就绪 |
| 失败重试 | 每 1 分钟，最多 3 次 | 应对偶发启动失败 |
| 执行时限 | 16 小时 | 覆盖一天工作时长 |

### 5.3 解决重启空窗问题

快照机制天然应对重启场景：

- 快照是独立文件，与进程是否存活无关。
- 计划任务在登录时自动启动 watch，watch 在 `auto_snapshot_times` 时刻自动打快照。
- 若当天 06:00 前未开机，开机后 watch 会等到下一个配置时间点自动打快照；也可手动补打：

```powershell
python daily_change_reporter.py snapshot --label morning
```

## 6. 近period变更查询

通过 `list` 命令查看所有历史快照，再用 `--from` / `--to` 跨天对比：

```powershell
# 查看所有快照
python daily_change_reporter.py list

# 对比昨天早上到今天下班的变更
python daily_change_reporter.py report --from 20260303-060000 --to 20260304-180000
```

也可以在 PowerShell 中批量为近 7 天每天生成日报：

```powershell
1..7 | ForEach-Object {
    $day = (Get-Date).AddDays(-$_).ToString("yyyyMMdd")
    # 找到当天第一个和最后一个快照 ID 后生成日报（需配合 list 筛选）
}
```
