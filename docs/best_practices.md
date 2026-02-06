# 开发规范 (Development Rules & Best Practices)

> ⚠️ **所有 AI Agent 开发前必读**
> 为了保证系统的稳定性，减少 Bug，请严格遵守以下规范。

## 1. 核心原则

1. **增量修改，严禁重写**：除非得到明确指令，否则禁止重写整个文件（尤其是 `viewer.html` 和 `server.py`）。
2. **保护 iframe 通信**：`postMessage` 是系统的神经中枢。修改 `viewer.html` 或注入脚本时，**绝对不能破坏**现有的消息监听逻辑 (navigateTo, pageChange)。
3. **兼容性第一**：
   - CSS 使用原生或 Tailwind (如果已引入)。
   - JS 尽量使用 ES6+，但要注意不要引入需编译的语法（如 JSX）。
   - **必须兼容 `file://` 协议**：导出后的项目会在本地运行，严禁使用 `/` 开头的绝对路径引用资源。

## 2. 文件操作规范

- **修改前备份 (必选)**：核心逻辑修改前，必须将原文件复制到 `backups/YYYYMMDD_TaskName/`，并在 `docs/backup_log.md` 登记。这是回滚的唯一救命稻草。
- **路径处理**：在 Python 中使用 `os.path.join`，不要硬编码路径分隔符。

## 3. UI/UX 规范

- **Aesthetics First**：保持界面美观，使用半透明、圆角、阴影等现代 UI 元素。
- **统一交互**：新功能入口尽量融合到现有的「悬浮工具栏」中，不要随意增加顶部/侧边栏。

## 4. 调试指南

- **服务端日志**：`server.py` 的控制台输出是排查后端问题的关键。
- **前端日志**：`viewer.html` 中保留了 `console.log('[Viewer] ...')` 格式的日志，调试时请延续此格式。

## 5. 任务记录

每次进行较大的开发任务时：
1. 在 `docs/archive/` 下创建一个新的任务记录文件（如 `task_20260123_inspector.md`）。
2. 记录 `Implementation Plan` 和 `Verification Report`。
3. 更新 `docs/changelog.md`。
