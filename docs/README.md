# 原型生成器 (Prototype Generator)

> 简单、高效的 AI 原型生成与管理工具

---

## 简介

本项目是一个结合了 AI 大模型的 Web 原型生成工具。它不仅能让 AI 生成代码，还提供了完整的**预览、编辑、PRD 撰写、研发交付**全流程支持。

当前版本新增 **HTML PPT 生成** 和 **设计系统资产层**：HTML PPT 可通过导入 PPTX 美化或逐页描述生成；设计系统、skills 和 craft 资产参考 OpenDesign 的组织方式，为不同产物类型注入更稳定的设计约束。

## 快速入门

### 启动项目
双击根目录下的 `启动项目.bat` 即可启动服务器，默认地址 `http://localhost:8080/src/`。

### 核心功能
*   **AI 生成**：输入描述，生成 HTML 原型。
*   **HTML PPT**：支持 PPTX 解析、原始配图回填、参考图辅助、概览小图和全屏播放。
*   **设计系统**：支持中文化设计系统选择、色卡预览，并按产物类型联动生成 skill。
*   **预览器**：支持 PC/Mobile 视图切换，实时预览。
*   **PRD 撰写**：内置 Markdown 编辑器，实时编写文档。
*   **微调模式**：所见即所得的元素选择与 AI 修改。
*   **团队协作**：支持账号登录、团队创建 / 加入、项目分享到团队。
*   **研发交付**：一键导出包含导航、流程图、PRD 的完整交付包。

## 文档导航

所有开发与维护文档均位于本目录 (`docs/`) 下：

| 文档 | 说明 |
|------|------|
| [架构设计 (architecture.md)](architecture.md) | 系统架构、文件结构、核心技术原理（导航、通信等） |
| [功能详解 (features.md)](features.md) | 核心功能（微调模式、PRD 系统、导出）的详细说明 |
| [API 参考 (api.md)](api.md) | 后端 API 接口定义 |
| [开发规范 (best_practices.md)](best_practices.md) | **开发必读**：各种规约、注意事项、防 Bug 指南 |
| [更新日志 (changelog.md)](changelog.md) | 版本迭代记录 |
| [任务归档 (archive/)](archive/) | 历史开发任务记录 |

## 目录结构速览

```
原型生成器/
├── server.py              # 后端服务（核心）
├── db.py                  # 团队协作数据库层
├── migrate.py             # 旧项目归属迁移脚本
├── docs/                  # 开发文档（本目录）
├── design-systems/        # 设计系统 DESIGN.md 资产
├── skills/                # 原型、Dashboard、Mobile、SaaS、HTML PPT 等生成 skills
├── craft/                 # 通用设计工艺与反 AI 味规范
├── projects/              # 项目数据存储
├── src/                   # 前端源码 (index.html / login.html / viewer.html)
└── templates/             # 模板文件
```
