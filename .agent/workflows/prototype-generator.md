---
description: 原型生成器项目的结构说明与修改规范
---

# 原型生成器项目 Workflow

> ⚠️ **每次修改本项目前，必须阅读并遵循本文档的修改规范**

## 项目位置

`d:\ai project\ky_antigravity\原型生成器`

---

## 一、项目概述

这是一个 **AI 驱动的产品原型生成工具**，可以根据用户输入的需求描述和参考图片，自动生成 HTML 原型页面。

### 核心功能

| 功能 | 说明 |
|------|------|
| **AI 生成** | 调用 AI 大模型生成完整 HTML 原型 |
| **项目管理** | 新建、复制、删除、重命名项目，回收站恢复 |
| **预览器** | 支持 PC/Mobile 视图，四种工作模式 |
| **微调模式** | 点选/框选元素，AI 精准修改 |
| **PRD 撰写** | 内置 Markdown 编辑器 |
| **项目导出** | 零依赖导出，可离线运行 |

---

## 二、项目架构

### 核心文件

| 文件 | 说明 | 行数 |
|------|------|------|
| `server.py` | Python 后端服务器 | ~1600 |
| `src/index.html` | 主界面 HTML | ~260 |
| `src/script.js` | 主界面脚本 | ~1000 |
| `src/viewer.html` | 原型预览器 | ~1200 |

### 目录结构

```
原型生成器/
├── server.py              # 后端核心
├── src/
│   ├── index.html         # 主界面
│   ├── script.js          # 主界面逻辑
│   └── viewer.html        # 预览器（预览/编辑/研发/微调模式）
├── projects/              # 生成的原型项目
├── data/
│   ├── projects.json      # 项目列表
│   └── deleted_projects.json
├── docs/                  # 开发文档
├── backups/               # 备份目录
├── templates/             # AI 提示词模板
├── exports/               # 导出的项目
└── 启动项目.bat           # 一键启动
```

### 后端 API 端点

| 端点 | 功能 |
|------|------|
| `POST /generate` | AI 生成原型 |
| `POST /copy-project` | 复制项目 |
| `POST /delete-project` | 删除项目 |
| `POST /rename-project` | 重命名项目 |
| `POST /restore-project` | 恢复项目 |
| `POST /api/prd/save` | 保存 PRD |
| `POST /api/inspector/apply` | 微调模式 AI 修改 |

---

## 三、启动方式

双击 `启动项目.bat`，自动：
1. 启动 Python 后端 (localhost:8080)
2. 打开浏览器访问主界面

---

## 四、修改规范 ⚠️ (已自动化)

> **重要**: 本项目已集成 **auto-documentation skill**，AI 将自动处理备份和文档更新

### 自动化流程

当 AI 修改本项目时，将自动执行以下步骤：

#### Step 1: 修改前 — 自动备份

```bash
# AI 自动调用
python ../.agent/skills/auto-documentation/scripts/auto_backup.py \
    --task "任务描述" \
    --files file1.py file2.js \
    --project-root .
```

✅ **自动完成**:
- 创建备份目录 `backups/YYYYMMDD_HHMMSS_任务名/`
- 复制将被修改的文件
- 更新 `docs/backup_log.md`

#### Step 2: 执行修改

按照用户需求修改代码文件。

#### Step 3: 修改后 — 自动更新文档

```bash
# AI 自动调用
python ../.agent/skills/auto-documentation/scripts/auto_update_docs.py \
    --type [feature|fix|optimize|refactor] \
    --desc "变更描述" \
    --files file1.py file2.js \
    --project-root .
```

✅ **自动完成**:
- 在 `docs/changelog.md` 添加今日条目
- 根据修改文件提示需要更新的其他文档（如 `api.md`, `features.md`）

#### Step 4: 完成提醒

AI 会提醒用户：
- 如修改了 `server.py`：**需要重启服务器**
- 如修改了前端文件：**需要刷新浏览器**

### 修改类型说明

| 类型 | 说明 | auto_update_docs.py 参数 |
|------|------|--------------------------|
| 新增功能 | 添加新功能 | `--type feature` |
| Bug修复 | 修复问题 | `--type fix` |
| 优化改进 | 性能/UI优化 | `--type optimize` |
| 重构 | 代码重构 | `--type refactor` |
| 文档 | 仅文档更新 | `--type docs` |

### 手动流程（备用）

仅在自动化脚本失败时使用：

1. 手动创建备份：`mkdir backups\YYYYMMDD_任务名` 并复制文件
2. 执行修改
3. 手动编辑 `docs/changelog.md` 和 `docs/backup_log.md`


---

## 五、文档结构

| 文档 | 用途 |
|------|------|
| `docs/README.md` | 项目入口，文档索引 |
| `docs/changelog.md` | 更新日志 |
| `docs/backup_log.md` | 备份记录表 |
| `docs/api.md` | 后端 API 文档 |
| `docs/features.md` | 功能详解 |
| `docs/architecture.md` | 系统架构 |
| `docs/best_practices.md` | 开发规范 |

---

## 六、检查清单

修改完成后，确认以下事项：

- [ ] 备份已创建并记录到 `backup_log.md`
- [ ] `changelog.md` 已添加变更记录
- [ ] 如涉及新 API：`api.md` 已更新
- [ ] 如涉及新功能：`features.md` 已更新
- [ ] 已提醒用户重启服务器/刷新浏览器

---

## 七、常见修改场景

### 场景 1: 添加新的项目管理功能
1. 后端：`server.py` 添加 `handle_xxx` 函数 + 路由
2. 前端：`src/script.js` 添加调用函数
3. 更新：`api.md` + `features.md` + `changelog.md`

### 场景 2: 修改预览器 UI
1. 修改：`src/viewer.html`
2. 备份原文件
3. 更新：`changelog.md` + `backup_log.md`

### 场景 3: 修复 Bug
1. 定位并修复代码
2. 更新：`changelog.md`（### 修复 分类）
