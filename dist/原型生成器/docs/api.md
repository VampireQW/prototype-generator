# API 参考 (API Reference)

服务端地址: `http://localhost:8080`

## 1. 项目管理

### 获取项目列表
`GET /api/projects`

### 创建项目
`POST /generate`
- Body: `{ prompt, images }`

### 删除项目
`POST /delete-project`
- Body: `{ id }`

### 复制项目
`POST /copy-project`
- Body: `{ sourceProjectId, newProjectName }`
- Returns: `{ success: true, project: {...} }`

### 创建占位项目
`POST /create-placeholder`
- Body: `{ projectId, projectName, formData, imageFiles }`
- Returns: `{ success: true, project: {...} }`
- 说明：创建不调用AI的占位项目，用于复制Prompt功能

### 查询生成状态
`GET /api/generation-status`
- Query: `?id=xxx`
- Returns: `{ status: 'pending'|'generating'|'completed'|'failed', progress: 0-100, error: 'xxx' }`
- 说明：查询项目异步生成状态

## 2. PRD 文档

### 保存 PRD
`POST /api/prd/save`
- Body: `{ projectId, pageName, content }`

### 加载 PRD
`GET /api/prd/load`
- Query: `?projectId=xxx&pageName=yyy`

## 3. 研发数据

### 获取页面列表
`GET /api/pages`
- Query: `?projectId=xxx`
- Returns: `{ pages: [{name, label}] }`

### 获取流程图数据
`GET /api/flowchart`
- Query: `?projectId=xxx`
- Returns: `{ pages, transitions, modals, mermaid }`

## 4. 微调模式

### 应用 AI 修改
`POST /api/inspector/apply`
- Body: 
  ```json
  {
    "projectId": "xxx",
    "userRequest": "修改背景色为蓝色",
    "elements": [
      { "selector": "#btn", "html": "<button>..." }
    ],
    "prompt": "完整 prompt (可选)"
  }
  ```
- Returns: `{ success: true, message: "...", backupFile: "index.html.bak" }`


### 📝 最近更新 (2026-01-30)
- 测试自动文档更新功能 - SKILL优化测试
