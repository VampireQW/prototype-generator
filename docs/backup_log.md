# 备份与回滚日志 (Backup & Rollback Log)

> 记录每次关键变更前的备份点，以便快速回滚。

## 备份策略

1. **执行时机**：每次开始新任务 (`docs/templates/task_template.md`) 的 "准备阶段"。
2. **备份内容**：仅备份将被修改的核心文件（如 `server.py`, `src/viewer.html`）。不要备份整个 `projects/` 目录（太占空间）。
3. **命名规范**：`backups/YYYYMMDD_{任务名}/`

## 备份记录

| 日期 | 任务名称 | 备份路径 | 包含文件 | 备注 |
|------|----------|----------|----------|------|
| 2026-01-23 | 微调模式开发 | `backups/20260123_inspector/` | `src/viewer.html`, `server.py` | (补录) |
| 2026-01-23 | 按钮颜色修改 | `backups/20260123_red_buttons/` | `index.html` | 修改按钮为红色 |
| 2026-01-24 | 微调模式优化 | `backups/20260124_inspector_refine/` | `src/viewer.html` | 弹窗UI修改+修复点选 |
| 2026-01-24 | 修改表格表头 | `backups/20260124_change_table_header/` | `index.html` | "模板ID" -> "模板" |
| 2026-01-24 | 弹窗拖拽优化 | `backups/20260124_inspector_drag/` | `src/viewer.html` | 弹窗缩小 + 支持拖拽 |
| 2026-01-24 | 全局设置按钮优化 | `backups/20260124_settings_drag/` | `src/viewer.html` | 缩小按钮 + 支持拖拽 |
| 2026-01-24 | 复制项目功能 | - | `server.py`, `src/script.js` | 新增复制按钮和后端 API |
| 2026-01-30 | 13:56 | 测试自动备份 | `backups\20260130_135643_测试自动备份` | server.py |  |
| 2026-01-30 | 14:51 | 异步生成和复制Prompt功能 | `backups\20260130_145123_异步生成和复制Prompt功能` | server.py, src/script.js, src/index.html |  |
| 2026-01-30 | 15:40 | 添加输入验证功能 | `backups\20260130_154009_添加输入验证功能` | src/script.js |  |
