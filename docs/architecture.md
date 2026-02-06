# 架构设计 (Architecture)

## 1. 系统架构

本系统采用 **Python (后端) + 原生 HTML/JS (前端)** 的轻量级架构，零依赖运行。

### 后端 (server.py)
- 基于 `http.server` 的原生实现，无 Flask/Django 依赖。
- 职责：
  - 静态文件服务
  - AI 大模型调用代理
  - 项目/文件管理 (CRUD)
  - PRD/Inspector API 支持
  - HTML 解析与流程图生成
  - **网络层增强**：集成智能代理探测与 `curl` 命令行兜底机制，确保在 SSL 握手失败等极端网络环境下仍能稳定调用 AI 接口。

### 前端 (Viewer)
- **HTML5 + ES6 + Vue3 (Composition API)**
- **viewer.html**：核心预览容器，承载所有交互模式。
- **iframe**：加载生成的原型项目，隔离运行环境。

---

## 2. 核心机制

### 页面导航与状态同步
由于原型运行在 iframe 中，且可能包含 Vue 路由逻辑，系统采用 `postMessage` 实现 Viewer 与 Prototype 的双向通信：

```
Viewer (Parent)                         Prototype (iframe)
      │                                       │
      │   postMessage('navigateTo')           │
      │ ─────────────────────────────────────>│
      │                                       │ window.currentPage.value = pageName
      │                                       │
      │   postMessage('pageChange')           │
      │ <─────────────────────────────────────│
      │ 更新 UI / PRD                         │
```

**实现细节**：
- **注入监听器**：后端在服务 HTML 时（或通过 `inject_listener.py`），会在 `<script>` 中注入消息监听代码，并暴露 `window.currentPage`。
- **状态感知**：Viewer 定时轮询 + 事件监听，确保左侧导航栏与 iframe 内部页面始终同步。

### 跨域与文件协议支持
为了支持 `项目导出` 后在本地 `file://` 协议下运行：
- 所有资源引用使用相对路径。
- 页面跳转依然依赖 `postMessage`，绕过 `file://` 下的跨 iframe 访问限制（同源策略在 file 协议下表现不同）。

---

## 3. 文件结构

详细的文件用途说明：

```
原型生成器/
├── server.py              # 后端核心服务
├── config.json            # AI 配置、端口设置
├── projects.json          # 项目索引（自动同步）
├── data/                  # 运行时数据
├── 
├── src/                   # 前端系统源码
│   ├── viewer.html        # 全能预览器（预览/编辑/研发/微调）
│   ├── index.html         # 系统首页（新建项目）
│   └── style.css          # 全局样式
├── 
├── projects/              # 用户项目存储
│   └── {项目ID}/
│       ├── index.html     # 原型 HTML 文件
│       ├── prd/           # PRD 文档目录 (.md)
│       └── images/        # 资源文件
├── 
├── docs/                  # 开发文档
└── scripts (bat/py)       # 辅助工具脚本
```
