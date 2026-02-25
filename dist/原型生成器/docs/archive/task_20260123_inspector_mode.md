# 开发任务归档：微调模式 (Inspector Mode)

> 日期：2026-01-23
> 任务：实现可视化的"指哪改哪"微调模式

## 1. 需求分析
借鉴 Agentation 思想，为原型生成器增加可视化微调能力。用户可以通过点选/框选元素，生成包含精确上下文（CSS Selector, HTML）的 Prompt，或直接调用 AI 完成修改。

## 2. 实现方案 (Implementation Plan)
### 前端 (viewer.html)
- **UI**: 新增粉色微调按钮、悬浮工具栏入口、Inspector 覆盖层、Prompt 弹窗。
- **Core Logic**:
  - `enableInspector()`: 激活覆盖层，注入 CSS 高亮样式。
  - `click`: 单击选中元素，计算唯一 CSS Selector。
  - `box-select`: 拖拽框选，计算矩形相交选出多个元素。
  - `prompt`: 组合 `projectId` + `selector` + `html` + `userRequest`。
- **AI Integration**: 调用后端 `/api/inspector/apply`。

### 后端 (server.py)
- 新增 API: `POST /api/inspector/apply`
- 逻辑：读取 HTML -> 备份 -> 调用 LLM -> 写入新 HTML -> 返回成功。

## 3. 验证报告 (Walkthrough)
### 功能验证
- [x] 点选高亮
- [x] 框选多选
- [x] Ctrl+Click 追加选择
- [x] Prompt 生成准确性
- [x] AI 接口调用成功

### 测试截图
![Inspector Active](C:/Users/qky/.gemini/antigravity/brain/537ad22a-816f-4e13-a5a7-48e6a3ffb464/inspector_mode_active_1769178604594.png)

## 4. 修改文件列表
- `src/viewer.html`
- `server.py`
