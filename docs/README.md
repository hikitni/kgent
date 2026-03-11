# Kgent V3 - 本地文件变更监控  AI 日报生成

> **Kgent V3** 是一个轻量级、纯本地、可长期运行在 Windows 的文件变更跟踪与 AI 日报生成工具。
> 通过快照对比采集文件变更，结合大模型生成口语化工作日报，帮助开发者快速完成每日工作总结。

## 文档导航

| 章节 | 文件 | 内容 |
|---|---|---|
| 01 | [01-概述与目标.md](01-概述与目标.md) | 背景、核心目标、范围、典型流程 |
| 02 | [02-功能与非功能需求.md](02-功能与非功能需求.md) | FR / NFR 完整需求清单 |
| 03 | [03-系统架构与模块设计.md](03-系统架构与模块设计.md) | 架构分层、各模块职责与数据流 |
| 04 | [04-数据规范.md](04-数据规范.md) | 快照格式、索引格式、日报结构、配置规范 |
| 05 | [05-Windows运行指南.md](05-Windows运行指南.md) | 安装、使用命令、计划任务配置 |
| 06 | [06-验收标准与风险.md](06-验收标准与风险.md) | UAT 清单、验证方案、风险与迭代建议 |
| 07 | [07-Web管理界面设计.md](07-Web管理界面设计.md) | FastAPI + Vue3 构成的 Web 界面端架构与 API 设计 |
| 08 | [08-代码复核与评价报告.md](08-代码复核与评价报告.md) | 项目代码质量复盘、性能评估与演进建议 |
| 09 | [09-打包与分发方案.md](09-打包与分发方案.md) | PyInstaller 打包流程、发行包结构与分发方式 |
| 10 | [10-准出指标与质量基线.md](10-准出指标与质量基线.md) | 5 类 28 项准出指标、当前达标状态与 CI 集成建议 |

## 快速开始

```powershell
# 安装依赖
pip install -r requirements.txt

# 复制配置文件并编辑 watch_paths 等参数
copy config.example.json config.json

# 方式一：启动 Web 页面管理系统（推荐）
python main.py --web

# 方式二：上/下班时后台命令行直接打快照
python main.py snapshot --label morning

# 方式三：进入命令行交互式菜单生成日报
python main.py
```

详细说明见 [05-Windows运行指南.md](05-Windows运行指南.md)。

**Kgent V3 核心能力：**

1. 监控指定目录下的本地文件变更（新增、修改、删除）
2. 记录每次变更对应的行级变化摘要（+/- 行数）
3. 按天生成 Markdown 日报，快速复盘当日工作
4. 可选接入大模型（DeepSeek / ZhipuAI / OpenAI / Ollama），一键生成口语化异步 AI 日报
5. 现代化 Web 管理视图 (FastAPI + Vue 3)，支持可视化操作快照、列表对比生成、异步 AI 报告与轮询反馈
6. Windows 计划任务集成，自动定时打快照

## 1. 安装

```powershell
pip install -r requirements.txt
```

## 2. 配置

复制配置模板：

```powershell
copy config.example.json config.json
```

编辑 `config.json`：

- `watch_paths`：要监控的目录列表
- `ignore_dirs`：忽略目录名
- `ignore_suffixes`：忽略文件后缀
- `snapshot_root`：中间数据目录（默认 `.daily_reporter`）
- `output_root`：日报输出目录（默认 `reports`）
- `ai_provider`：AI 提供商（`zhipuai` / `openai` / `ollama`，留空则不启用 AI）

## 3. 启动 Web 管理界面 (推荐)

> 最新支持 FastAPI + Vue 3 的浏览器化管理系统！

```powershell
python main.py --web
```
启动后自动弹出浏览器打开管理界面，支持**可视化操作快照、列表对比直接生成、以及非阻塞的异步 AI 报告**流式等待操作。
您也可以使用附加参数设定端口和阻止默认浏览行为：
```powershell
python main.py --web --port 8080 --no-browser
```

## 4. 启动交互式终端菜单

```powershell
python main.py
```

进入全功能终端菜单，也可执行打快照、对比、生成日报、管理计划任务等操作（Web 端已涵盖该入口的核心功能）。

## 5. 命令行快速后台打快照

```powershell
python main.py snapshot                    # 打一次快照
python main.py snapshot --label morning   # 带标签
python main.py -c my.json snapshot        # 指定配置文件
```

## 6. 建议工作流

- 上班时：计划任务自动打早快照（06:00），或在控制台使用 `python main.py snapshot` 打下初始化点。
- 工作中：通过 Web 页面/控制台手动打里程碑快照，标注功能分支。
- 下班前：在 Web 快照列表中选中最早与最晚快照一键提取合并，并通过异步交互界面获取带 AI 风格渲染的生成报告。
- 最终在生成的日报里核对增量，补充业务风险后提交。

## 7. Windows 持续运行建议

1. 使用菜单 **8 - 定时任务管理** 注册 Windows 计划任务。
2. 也可手动创建任务，命令：`python main.py snapshot`。
3. 建议在 `config.json` 配置 `ai_provider` 以启用 AI 日报功能。