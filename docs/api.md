# API 参考 (API Reference)

服务端地址: `http://localhost:8080`

## 1. 项目管理

### 获取项目列表
`GET /api/projects`

### 获取我的项目
`GET /api/projects/my`
- 需登录
- Returns: `{ projects: [...] }`

### 获取团队项目
`GET /api/projects/team`
- 需登录
- Query: `?teamId=1`
- Returns: `{ projects: [...] }`

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

## 2. 认证与团队协作

### 注册
`POST /api/auth/register`
- Body: `{ username, password, displayName }`
- Returns: `{ success: true, user: {...} }`
- 说明：注册成功后会自动写入登录 Cookie。

### 登录
`POST /api/auth/login`
- Body: `{ username, password }`
- Returns: `{ success: true, user: {...} }`

### 获取当前用户
`GET /api/auth/me`
- Returns: `{ user: null }` 或 `{ user: {...}, teams: [...] }`

### 退出登录
`POST /api/auth/logout`
- Returns: `{ success: true }`

### 创建团队
`POST /api/teams/create`
- 需登录
- Body: `{ name }`
- Returns: `{ success: true, team: { id, name, inviteCode } }`

### 加入团队
`POST /api/teams/join`
- 需登录
- Body: `{ inviteCode }`
- Returns: `{ success: true, team: {...} }`

### 获取我的团队
`GET /api/teams`
- 需登录
- Returns: `{ teams: [{ id, name, role, inviteCode }] }`

### 获取团队成员
`GET /api/teams/{teamId}/members`
- 需登录且是团队成员
- Returns: `{ members: [{ id, username, display_name, role, joined_at }] }`

### 退出团队
`POST /api/teams/{teamId}/leave`
- 需登录
- Returns: `{ success: true }`

### 分享项目到团队
`POST /api/projects/{projectId}/share`
- 需登录且是项目拥有者
- Body: `{ teamId }`
- Returns: `{ success: true }`

### 取消项目分享
`POST /api/projects/{projectId}/unshare`
- 需登录且是项目拥有者
- Body: `{ teamId }`
- Returns: `{ success: true }`

### 获取项目已分享团队
`POST /api/projects/{projectId}/shared-teams`
- 需登录
- Returns: `{ teams: [{ id, name }] }`

## 3. PRD 文档

### 保存 PRD
`POST /api/prd/save`
- Body: `{ projectId, pageName, content }`

### 加载 PRD
`GET /api/prd/load`
- Query: `?projectId=xxx&pageName=yyy`

## 4. 研发数据

### 获取页面列表
`GET /api/pages`
- Query: `?projectId=xxx`
- Returns: `{ pages: [{name, label}] }`

### 获取流程图数据
`GET /api/flowchart`
- Query: `?projectId=xxx`
- Returns: `{ pages, transitions, modals, mermaid }`

## 5. 设计系统与 Skills

### 获取设计系统列表
`GET /api/design-systems`
- Returns: `{ designSystems: [{ id, name, category, colors, summary }] }`
- 说明：返回 `design-systems/` 下的中文化设计系统资产，前端用于下拉选择和色卡预览。

### 获取单个设计系统详情
`GET /api/design-systems/{id}`
- Returns: `{ designSystem: {...} }`
- 说明：返回对应 `DESIGN.md` 内容，生成 Prompt 时由后端注入。

### 获取产物 Skills 列表
`GET /api/skills`
- Returns: `{ skills: [{ id, name, description }] }`
- 说明：返回 `skills/` 下的产物工作流资产，用于按产物类型联动生成约束。

### 获取单个 Skill 详情
`GET /api/skills/{id}`
- Returns: `{ skill: {...} }`

## 6. PPTX 解析

### 解析 PPTX
`POST /api/pptx/parse`
- Content-Type: `multipart/form-data`
- Form 字段：`file`
- Returns:
  ```json
  {
    "success": true,
    "slides": [
      {
        "slideIndex": 1,
        "title": "页面标题",
        "text": "页面文字",
        "images": [
          { "name": "slide1_image1.png", "mime": "image/png", "base64": "..." }
        ]
      }
    ],
    "maxImagesPerSlide": 5
  }
  ```
- 说明：当前仅支持 `.pptx`。服务端会提取文字、页序和可用图片；PPT 原始配图会作为页面配图参与生成，不作为普通参考图。

## 7. 微调模式

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

### 获取服务器路径信息
`GET /api/server-info`
- Returns: `{ projectsDir }`
- 说明：供预览器生成微调提示词时动态定位项目文件路径。


### 📝 最近更新 (2026-01-30)
- 测试自动文档更新功能 - SKILL优化测试
