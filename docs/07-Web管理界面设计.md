# 07 · Web 管理界面设计

> 版本：v1.1 · 2026-03-04  
> 状态：已实现（M1~M6）

---

## 一、目标与范围

在现有 CLI 终端 UI 不变的前提下，新增一个 **浏览器 Web 管理后台**。用户通过
`python main.py --web` 启动后，程序自动在后台运行 HTTP 服务，并打开默认浏览器。

功能范围：

| 功能 | 终端 CLI | Web UI |
|------|---------|--------|
| 打快照 | ✅ | ✅ |
| 浏览/删除快照 | ✅（分页） | ✅（分页+搜索） |
| 查看快照文件列表 | ✅（前30条） | ✅（分页+搜索） |
| 对比快照 diff | ✅ | ✅（可视化） |
| 生成日报 | ✅ | ✅ |
| 日报列表/预览 | ✅（文件管理器） | ✅（Markdown 渲染） |
| AI 生成日报 | ✅ | ✅ |
| Watch 状态 | ✅（阻塞模式） | ✅（后台 + SSE 推送） |
| 配置查看 | ✅ | ✅ |
| 批量删除 | ❌ | ✅ |
| 暗色模式 | ❌ | ✅ |

---

## 二、启动方式

```bash
# 默认端口 7421，自动打开浏览器
python main.py --web

# 指定端口
python main.py --web --port 8080

# 不自动打开浏览器（适合服务器部署）
python main.py --web --no-browser

# 组合配置文件
python main.py -c my_config.json --web --port 9000
```

---

## 三、技术栈

| 层次 | 选型 | 版本要求 | 说明 |
|------|------|---------|------|
| Web 框架 | FastAPI | ≥0.111 | 异步、自带 OpenAPI |
| ASGI 服务器 | uvicorn | ≥0.29 | 标准安装（带 websockets） |
| 模板引擎 | Jinja2 | ≥3.0 | 仅渲染 `index.html` 入口 |
| 前端框架 | Vue 3 CDN | 3.x | SPA，无需构建工具 |
| 路由 | Vue Router 4 CDN | 4.x | 前端路由，SPA 无刷新 |
| CSS | Tailwind CDN + DaisyUI CDN | 4.x | 零构建，丰富组件 |
| 图标 | Lucide CDN | latest | 线性图标 |
| Markdown 渲染 | marked.js CDN | 9.x | 客户端渲染 |
| 代码高亮 | highlight.js CDN | 11.x | diff/代码高亮 |
| 实时推送 | SSE（Server-Sent Events） | — | Watch 日志流 |

> **无需 Node.js / npm**。所有前端依赖均通过 CDN 引入。

---

## 四、文件结构

```
daily_reporter/
  web/
    __init__.py          # 导出 create_app(), run_server()
    app.py               # FastAPI app 工厂，路由注册，SPA 入口
    routes/
      __init__.py
      snapshots.py       # /api/snapshots 相关路由
      reports.py         # /api/reports 相关路由
      compare.py         # /api/compare 路由（diff）
      watch.py           # /api/watch 路由（SSE）
      config_route.py    # /api/config 路由
    templates/
      index.html         # SPA 唯一入口
    static/
      app.js             # Vue 3 SPA 主逻辑（路由+页面+组件）
      utils.js           # fetch 封装、格式化工具

tests/
  test_web_snapshots.py  # Web 快照接口单元测试
  test_web_reports.py    # Web 日报接口单元测试
  test_web_compare.py    # Web 对比接口单元测试
```

---

## 五、REST API 规范

### 5.1 通用约定

- Base URL：`http://127.0.0.1:{port}/api`
- 所有响应为 JSON
- 成功：HTTP 2xx + `{ "ok": true, ...data }`
- 失败：HTTP 4xx/5xx + `{ "ok": false, "error": "描述" }`
- 分页参数：`?page=1&size=20`（默认 page=1, size=20）

### 5.2 快照接口

| Method | 路径 | 请求体 / 查询参数 | 响应 |
|--------|------|-----------------|------|
| `GET` | `/api/snapshots` | `?page&size&q` | 分页快照列表 |
| `POST` | `/api/snapshots` | `{ "label": "manual" }` | 新快照元数据 |
| `GET` | `/api/snapshots/{id}` | — | 快照详情（含文件列表，分页） |
| `DELETE` | `/api/snapshots/{id}` | — | `{ "ok": true }` |
| `DELETE` | `/api/snapshots` | `{ "ids": ["id1","id2"] }` | 批量删除 |

**GET /api/snapshots 响应示例：**
```json
{
  "ok": true,
  "total": 87,
  "page": 1,
  "size": 20,
  "items": [
    {
      "id": "20260304-123700",
      "timestamp": "2026-03-04T12:37:00",
      "label": "manual",
      "trigger": "manual",
      "file_count": 156
    }
  ]
}
```

**GET /api/snapshots/{id} 响应示例：**
```json
{
  "ok": true,
  "id": "20260304-123700",
  "timestamp": "2026-03-04T12:37:00",
  "label": "manual",
  "trigger": "manual",
  "file_count": 156,
  "files": {
    "total": 156,
    "page": 1,
    "size": 50,
    "items": [
      { "path": "src/main.py", "hash": "abc123", "lines": 120 }
    ]
  }
}
```

### 5.3 日报接口

| Method | 路径 | 请求体 / 查询参数 | 响应 |
|--------|------|-----------------|------|
| `GET` | `/api/reports` | `?page&size&type=all\|ai\|raw` | 分页日报列表 |
| `GET` | `/api/reports/{name}/content` | — | `{ "content": "markdown文本" }` |
| `POST` | `/api/reports/generate` | `{ "snap_a": "id", "snap_b": "id" }` | 新日报元数据 |
| `POST` | `/api/reports/{name}/ai` | — | 提交 AI 生成任务（异步，立即返回 202） |
| `GET` | `/api/reports/ai-tasks` | — | 查询所有 AI 生成任务状态 |
| `DELETE` | `/api/reports/{name}` | — | `{ "ok": true }` |

**POST /api/reports/{name}/ai 响应（202 Accepted）：**
```json
{
  "ok": true,
  "task_id": "report-20260304-123700-to-20260304-125403.md",
  "status": "running"
}
```

**GET /api/reports/ai-tasks 响应示例：**
```json
{
  "ok": true,
  "tasks": [
    {
      "name": "report-20260304-123700-to-20260304-125403.md",
      "status": "running",
      "filename": null,
      "error": null,
      "elapsed_sec": 12.3
    },
    {
      "name": "report-20260304-125403-to-20260304-132800.md",
      "status": "done",
      "filename": "report-20260304-125403-to-20260304-132800-ai.md",
      "error": null,
      "elapsed_sec": 45.1
    }
  ]
}
```

**GET /api/reports 响应示例：**
```json
{
  "ok": true,
  "total": 8,
  "page": 1,
  "size": 20,
  "items": [
    {
      "filename": "report-20260304-123700-to-20260304-125403-ai.md",
      "size_kb": 1.2,
      "mtime": "2026-03-04 13:28",
      "snap_a": "20260304-123700",
      "snap_b": "20260304-125403",
      "is_ai": true
    }
  ]
}
```

### 5.4 对比接口

| Method | 路径 | 响应 |
|--------|------|------|
| `GET` | `/api/compare/{snap_a}/{snap_b}` | diff 汇总 + 明细列表 |

**响应示例：**
```json
{
  "ok": true,
  "snap_a": { "id": "...", "timestamp": "..." },
  "snap_b": { "id": "...", "timestamp": "..." },
  "summary": {
    "total": 5,
    "created": 1,
    "modified": 3,
    "deleted": 1,
    "total_add": 42,
    "total_remove": 10,
    "net": 32,
    "top_ext": [[".py", 3], [".md", 2]]
  },
  "diffs": [
    {
      "path": "src/main.py",
      "status": "modified",
      "added_lines": 20,
      "removed_lines": 5
    }
  ]
}
```

### 5.5 Watch 接口

| Method | 路径 | 响应 |
|--------|------|------|
| `GET` | `/api/watch/status` | Watch 状态 + 配置时间点 |
| `POST` | `/api/watch/start` | 启动 Watch |
| `POST` | `/api/watch/stop` | 停止 Watch |
| `GET` | `/api/watch/stream` | SSE 事件流（text/event-stream） |

**SSE 事件格式：**
```
event: snapshot
data: {"id": "20260304-180000", "file_count": 158, "label": "afternoon"}

event: log
data: {"time": "18:00:01", "message": "定时触发快照"}

event: ping
data: {}
```

### 5.6 配置接口

| Method | 路径 | 响应 |
|--------|------|------|
| `GET` | `/api/config` | 完整配置（ai_api_key 脱敏） |

---

## 六、前端页面结构

```
/ → /dashboard       仪表盘（重定向）
/dashboard           首页统计卡片 + 最近快照/日报
/snapshots           快照列表（分页、搜索、批量删除）
/snapshots/:id       快照详情（文件列表分页）
/reports             日报列表（分页、类型筛选）
/reports/:name       日报 Markdown 预览（目录导航、下载）
/compare             快照对比选择页
/compare/:a/:b       对比结果（diff 汇总 + 明细）
/watch               Watch 状态 + SSE 实时日志
/settings            配置查看
```

---

## 七、UI 设计规范

### 配色（支持暗色模式）

```
主色调：indigo-500  (#6366f1)
成功色：green-500   (#22c55e)
警告色：amber-500   (#f59e0b)
危险色：red-500     (#ef4444)
中性背景：slate-50  (#f8fafc)
卡片背景：white
主文字：slate-800
辅文字：slate-400
```

### 布局

```
┌─ 侧栏 (w-64, 可折叠) ─┬─ 主内容区 ─────────────────┐
│  Logo                  │  面包屑 / 页头               │
│  ─────────────────    │  ┌── 卡片 (rounded-xl) ───┐  │
│  📊 仪表盘              │  │  内容区域               │  │
│  📸 快照管理            │  └────────────────────────┘  │
│  📄 日报管理            │                              │
│  🔍 对比分析            │                              │
│  ⏱  Watch              │                              │
│  ⚙️  设置               │                              │
│                        │                              │
└────────────────────────┴──────────────────────────────┘
顶栏：项目名称 + 暗色切换按钮（fixed，h-16）
```

### 关键组件规范

| 组件 | 样式规范 |
|------|---------|
| 按钮-主要 | `btn btn-primary btn-sm rounded-lg` |
| 按钮-危险 | `btn btn-error btn-sm rounded-lg` |
| 按钮-幽灵 | `btn btn-ghost btn-sm` |
| 表格 | 无竖线，横线分割，hover 行高亮 |
| 徽章-AI | `badge badge-primary text-xs` |
| 徽章-原始 | `badge badge-ghost text-xs` |
| 卡片 | `card bg-base-100 shadow-sm border border-base-200` |
| 统计卡片 | 数字 `text-3xl font-bold`，标签 `text-sm text-base-content/60` |
| 分页 | `join` 组，显示页码，首/末快捷 |
| 搜索框 | 内嵌图标，实时过滤（防抖 300ms） |
| Modal 确认删除 | DaisyUI dialog，红色按钮，文字重述目标 |
| Toast | `alert` 固定右上角，3s 自动消失 |
| 骨架屏 | DaisyUI skeleton，替代 spinner |
| 空状态 | 居中图标 + 灰色文字 + 引导按钮 |

---

## 八、安全边界

| 风险 | 措施 |
|------|------|
| 公网暴露 | 默认 bind `127.0.0.1`，不对外 |
| API Key 泄露 | `/api/config` 返回时 `ai_api_key` 替换为 `***` |
| 路径穿越 | 快照 ID / 报告名称通过正则白名单校验 |
| 误删操作 | 前端 Modal 二次确认，不使用 `window.confirm` |

---

## 九、里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 | FastAPI 骨架 + 首页 + 快照列表/详情/删除 | ✅ 已实现 |
| M2 | 日报列表 + Markdown 预览 + 生成日报 | ✅ 已实现 |
| M3 | 快照对比 + AI 生成 | ✅ 已实现 |
| M4 | Watch SSE 实时日志 | ✅ 已实现 |
| M5 | 批量删除 + 配置页 | ✅ 已实现 |
| M6 | 快照页生成日报 + AI 异步任务 + 状态轮询 | ✅ 已实现 |

---

## 十、M6 详细设计：快照生成日报 + AI 异步任务

### 10.1 快照管理页面——选中两个快照生成日报

- 操作栏在选中恰好 **2 个快照**时显示「📄 生成日报」按钮
- 按快照 ID（即时间字符串）排序，较早为 snap_a，较晚为 snap_b
- 复用已有 `POST /api/reports/generate` 接口
- 成功后 toast 提示，可跳转日报预览页

### 10.2 AI 日报异步生成

**动机**：AI 接口耗时 10~60s，同步等待会阻塞 UI 交互并导致超时。

**后端实现**：
- 内存任务池 `_ai_tasks: dict[str, dict]`，key=原始日报文件名
- `POST /{name}/ai` 改为非阻塞：检查参数 → 将任务放入池 → `asyncio.create_task()` 后台执行 → 立即返回 **202 Accepted**
- 新增 `GET /api/reports/ai-tasks` 端点：返回所有任务的 status / filename / error / elapsed_sec
- 任务完成后更新 status=`"done"` 或 `"error"`，保留记录供轮询
- 重复提交同一日报返回 **409 Conflict**

**前端实现**：
- **日报列表页**（PageReports）：
  - 新增 `aiTasks` ref，`onMounted` + 每 3s 轮询 `GET /api/reports/ai-tasks`
  - 表格中原始日报行：若有 running 任务，显示 spinning badge + "AI生成中…"
  - 任务 done 时自动 `load()` 刷新列表 + toast 提示
  - 任务 error 时显示红色 badge  
- **日报预览页**（PageReportView）：
  - `genAI()` 改为 fire-and-forget：发请求后立即 toast "已提交"，不等待结果
  - 跳转到日报列表页查看进度

**任务状态机**：
```
idle → running → done
                → error
```
