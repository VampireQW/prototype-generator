# API 参考 (API Reference)

## PRD 草稿版本 3（2026-10-16）

本节替代旧版草稿内容格式；工作台三文件元数据 schemaVersion 仍为 2。`scope.requirements[]` 必须有 id、text、sourceQuote；原文引用须来自 scope.request，delta 模式另需非空且不同的 before / after。full 模式另以 fullRequest 引用整页 PRD 授权，“重新落库”不自动开启。可选 exclusions 为本期不涉及内容的字符串数组。

targets 使用 `{protoId,requirementIds:[...]}`。document 不再接受字符串，改为 `{background:[{requirementId,text}],goals:[{requirementId,text}]}`，两部分均可省略；纯文档变更通过页面级 requirementIds 指定需求。annotations 不再接受 body，改用 `{protoId,items:[{section,requirementId,markdown}],action?}`；每个 item 是一个顶层列表项或一张状态表，只引用该 target 的需求，工具合成为普通 Markdown。每个 section 仍可独立选择，不要求填写全部五项。

可选 removals 为 `[{annotationId,reason}]`，须通过 scope.cleanupRequest 引用 scope.request 中的清理授权；限定当前页状态和准确 ID，已确认标注保留，不允许同时删除和重建同一目标。正式保存维护 deletedAnnotations，dry-run 不删除。report 新增 scope / contentRefs / removedAnnotations；contentRefs 表示提交内容的引用，实际是否保存结合 skipped 和操作结果判断。其余 revision CAS、元素唯一、confirmed 与删除保护保持。

版本 1 / 2 草稿会返回明确错误并保留原稿；须由 Agent 根据本期实际需求重写，不能仅改版本数字或回放旧正文。工具校验格式与引用，不独立推断自然语言是否属于本期。完整示例见 [PRD 协议](../agent-skills/prototype-flow/references/prd-import.md)。

## 项目改名（2026-10-16）

`POST /api/proto/rename-project`：请求 `{projectId, name, expectedRevision}`，返回 `{ok:true, projectId, name, root, viewerUrl, bundle}`。项目 ID 保持不变，本地文件夹在原父目录内同步改名，页面 file 不变、file URL 更新；PRD、标注、回收站和 GitHub 发布地址保留。AI 项目同时修改 projects 列表、record 中的项目名 / 身份与归属 / 分享，远端发布 ID 保留。

该端点要求本机同源 JSON 及项目访问权限。名称去除首尾空白后为 1–100 字符，不接受路径、保留目录名、已有目标或与其他项目重叠的根目录；拒绝链接目录。400 为非法名称、冲突或文件系统失败（回滚），404 为登记失效，409 为 revision 冲突并返回 current。首页原 `/rename-project` 与工作台使用同一改名逻辑，不再在文件夹名后追加时间戳。

## PRD 导入与页面直达（2026-10-16）

`proto_import.py` 的新草稿标注须为结构化 Markdown：三级标题按页面显示 / 数据流转 / 业务规则 / 交互说明 / 异常情况选择适用小节，每节至少有列表或状态表，不重复或留空。document 为可选背景说明，含“研发实现”等标题的新增草稿拒绝导入。该校验不追溯修改历史 PRD，也不限制工作台手工编辑。

hotspots 缺省为空清单，不再从 targets 推导。runtime 仅匹配 interactionHints.protoIds 中控件自身的稳定 ID，不沿父元素授权后代。完整 PRD 与全页提示仍各自显式授权。

导入报告新增 projectName / viewerUrl / pages，pages 包含 pageId、pageTitle、file、stateId、stateTitle、viewerUrl；接入脚本也返回项目和页面定位。两脚本的 `--viewer-origin` 默认为工具默认来源 http://localhost:8080，可指定实际来源。页面 URL 支持 ext / page / state / mode=annotate，直接打开已登记状态与标注模式；项目仍需已登记。

## 页面层级（2026-10-15）

`/api/proto/read` 和 `/api/proto/save` 的 bundle 中，`project.pages[]` 支持可选 `parentId`，指向同端业务页面 ID；缺省 / null / 空字符串为顶层。同级顺序沿用 pages 数组。最多三级，端分组和页面状态不计级数；无效父引用、循环、跨端父子或演示入口嵌套返回校验错误。保存仍使用最新 expectedRevision CAS，不改变页面 ID 或 PRD 归属。

跨端移动需要连同整棵子树更新 clientId。回收父页面不回收子页面，读取保留原 parentId，导航 / 导出临时向可见祖先提升；恢复后还原。永久删除父页面将直属子页面接到原父级，不删除子页面文件。

## 页面回收站（2026-10-15）

`POST /api/proto/page-lifecycle`：请求 `{projectId, pageId, action, expectedRevision}`，action 为 `trash`、`restore` 或 `delete`；返回 `{ok:true,bundle}`。仅处理已登记项目，沿用本机、JSON、项目访问权限和 revision CAS 校验。400 表示动作 / 路径 / 文件不符或写入失败，409 表示版本冲突（含 current bundle）。

`trash` 设置该页 `trashedAt`，保留文件和关联数据；`restore` 要求本地文件仍存在，清除回收标记。`delete` 必须先在回收站，额外传 `confirmFile` 为该页准确相对文件名，永久删除该 HTML 及该页 documents / annotations / deletedAnnotations / changes.items；共用资源保留。页面清单同步去掉已删除文件，允许删除最后一页。普通 `/api/proto/save` 不允许移除页面或更改回收标记。

`trashedAt` 是页面对象可选的非空时间字符串，普通读取保持原值。回收站页的 `/ext/` HTML 返回 404；导出排除该文件及关联 PRD，自动补登不恢复已有回收页。删除期间暂存文件并保存事务恢复记录，失败回滚，异常中断后保留现场并停止覆盖元数据。

## 首页升级（2026-10-10）

### 获取项目封面
GET /api/home/thumbnail?source=local|ai&id=<项目ID>

- local 接受已登记 ID，或从 /api/external/list 实际扫描发现的 ID；移除扫描目录后发现 ID 失效。ai 接受原 AI ID，沿用工作台离线个人版及团队访问校验。
- 200：image/png，1280×640，私有缓存 60 秒；202：正在生成；429：队列繁忙；503：渲染不可用；404：目录或页面不可用；403：来源或项目访问被拒绝。
- 同一源文件版本复用缓存，源资源变更后生成新封面。不接受任意路径，不创建 .prototype 元数据。缓存目录不提供静态 GET / HEAD 访问，包括编码和相对路径变体。

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
- Body: `{ projectId, projectName, formData, imageFiles, prompt }`
- Returns: `{ success: true, project: {...}, instruction }`
- 说明：创建不调用AI的占位项目，用于复制Prompt功能
- `instruction` 为后端合成的完整 Prompt，包含预设规范与主动覆盖优先级，保存到项目 `prompt.txt`，前端以此复制。

### 解析 AI 项目的统一工作台
`POST /api/projects/workbench`
- Body: `{ projectId: "旧 AI 项目 ID" }`
- Returns: `{ ok: true, connected: true, projectId: "p-xxx", aiProjectId: "旧 AI 项目 ID", name, viewerUrl: "/src/viewer.html?ext=p-xxx", pages, revision }`。
- 解析项目目录并幂等登记 `.prototype` 元数据，保留原 AI 项目 ID 与首页归属；已有 PRD 合并到共享文档时不覆盖已有需求。Viewer 的 `?project=` 入口与 AI 项目发布 / 导出入口使用此接口，再走 `?ext=` 工作台与 `/api/ext/*` 共享流程。
- 同文件 Vue / Router 页面登记为首页的 adapter 状态：`aiNavigation: "legacy"`，状态含 `legacyPage`、`legacyType: "currentPage" | "router"` 与可选 `routePath`；多 HTML 项目保持真实文件页。同名现代状态按名称 slug 追加 `-2`、`-3`，迁入的页面需求分别保留。项目 `previewType: "mobile" | "web" | "pad"` 用作 Auto 预览元数据；状态、页面和所属端设置优先，其次读取原型根元素的显式 `data-proto-preview` 与项目默认值。
- 沿用本机同源、loopback 与 JSON 约束；非法 ID / 越界路径 400，项目不存在 404，当前用户无项目权限 403，损坏元数据 409。错误格式为 `{ ok: false, error }`。

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
- Returns: `{ success: true, designSystems: [{ id, name, displayName, category, categoryLabel, colors, preset }] }`
- 说明：返回 `design-systems/` 下的中文化设计系统资产，前端用于下拉选择和色卡预览。
- `preset`: `{ primaryColor, secondaryColor, defaultTheme, componentStyle, themes: { light: { background, surface, text, border }, dark: {...} } }`；`colors` 为继承预设时的最终六角色色样。

### 创建表单视觉设置协议（版本 2）

三种创建入口统一接受 `formData.global`：`designSettingsVersion: 2`、`designSystemId`、`colorMode: "preset" | "custom"`、`themeMode: "inherit" | "light" | "dark"`、`primaryColor`、`secondaryColor`、`customColorFields`。最后一项为实际修改的颜色键数组；空数组表示两色仍继承，仅修改主色时辅色仍跟随风格。后端重新解析预设与主动选择，不信任前端传入的派生组件语言或色样。

记录同时保存最终 `backgroundMode`、`componentStyle`、`effectivePalette` 和仅包含主动覆盖的 `designOverrides`，用于回填与一致性检查。`colorMode=preset` 忽略旧颜色输入；`themeMode=inherit` 使用预设主题。旧协议的固定默认色视为继承，非默认历史颜色保留为自定义；旧 dark 主题保留。优先级：用户明确需求 > 主动自定义配色 / 主题模式 > 视觉风格预设 > 产物类型规则 > 通用规则。

### 获取单个设计系统详情
`GET /api/design-systems/{id}`
- Returns: `{ success: true, id, name, body }`
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

## 8. 外部项目与标注（.prototype 元数据）

### 本机访问约束
- `/api/projects/workbench`、`/api/external/*`、`/api/proto/*`、`/api/ext/*`、`/ext/*` 及登记表静态读取仅允许 loopback 客户端；Host 必须是 `localhost`、`127.0.0.1` 或 `[::1]` 且端口与服务一致。
- 浏览器 Origin 必须等于当前 `http://Host`；拒绝 `null`、跨站及 same-site 非同源请求（403）。无 Origin 的本机命令行调用仍可用。
- 上述 API 的 POST 使用 `Content-Type: application/json`，否则返回 415。目录选择在独立子进程执行，不阻塞列表读取；普通请求仍串行调度以保护读改写和 CAS。

### 选择系统文件夹
`POST /api/external/pick-folder`
- Body: `{}`
- Returns: `{ ok: true, path, cancelled }`；取消时 `path` 为空，不写登记表。
- 已有窗口打开时 409；系统选择器不可用、失败或 180 秒超时返回 503，可改用粘贴路径。
- 只选择路径，不自动登记；取得路径后调用 `roots/add`。

### 添加项目或监视根
`POST /api/external/roots/add`
- Body: `{ path: "D:\\prototypes" }`
- 目录本身有 HTML 原型：沿用单项目登记，返回 `{ ok: true, connected: true, projectId, name, pages, revision, viewerUrl }`。
- 否则保存监视根，返回 `{ ok: true, connected: false, roots: ["绝对路径"], candidates: 2, errors: [] }`。
- 仅扫描监视根及直接子目录；项目页面发现范围为根 HTML 与 `pages/` 下 HTML。不扫描隐藏、依赖、交付、工具目录、符号链接及 Windows junction。
- 按规范化路径去重。只读发现不创建 `.prototype`；用户打开候选时才调用 `/api/external/add`。
- 无效或不允许的目录返回 400；空容器可登记，稍后刷新发现新增项目。

### 移除监视根
`POST /api/external/roots/remove`
- Body: `{ path }`
- Returns: `{ ok: true, roots }`；仅停止发现，不移除已登记项目，不删除文件。

### 登记外部项目
`POST /api/external/add`
- Body: `{ path: "D:\\path\\to\\prototype-folder" }`
- Returns: `{ ok: true, connected: true, projectId, name, pages, revision, viewerUrl }`
- 说明：登记磁盘上任意原型文件夹（根目录或 `pages/` 下需含 HTML），登记表存于 `data/external.json`；登记时初始化 `.prototype` 元数据（幂等），并对齐 projectId、补登新发现页面。

### 外部项目列表
`GET /api/external/list`
- Returns: `{ ok: true, items: [{ projectId, name, root, createdAt, addedAt, pages, revision, exists }], discovered: [{ projectId, name, root, createdAt, pages, discovered: true, exists: true }], roots: ["绝对路径"], errors: [{ root, error }] }`
- `items` 是已连接项目，失效路径保留且 `exists: false`；`discovered` 是尚未登记的候选。页面数 `pages` 为数字，无法读取元数据时 `revision` 为 null。
- `createdAt` 为目录创建时间（UTC ISO 8601），优先文件系统 birth time，未提供时取 ctime；失效路径回退已存创建时间或 `addedAt`，无法取得时为空字符串。两组分别按创建时间倒序返回，首页合并两组整体倒序；搜索在前端按名称 / 绝对路径过滤，不改变扫描范围与登记数据。
- 每次读取重新扫描；扫描错误单独返回，不静默删除登记。`data/external.json` 向后兼容扩展为 `{ projects: {...}, roots: [...] }`，旧登记表不会自动增加监视根。

### 移除登记
`POST /api/external/remove`
- Body: `{ projectId }`
- Returns: `{ ok: true }`
- 说明：只移除登记，不删除磁盘上的项目与 `.prototype` 元数据；仍在监视根内的项目，下次列表读取可再次作为候选出现。

### 删除项目（连同本地文件夹）
`POST /api/external/delete`
- Body: `{ projectId }`
- Returns: `{ ok: true, folderDeleted, root, publishedUrl }`；未登记 404。
- 说明：在 `remove` 之上连带删除本地项目文件夹（含 `.prototype` 元数据与全部页面），前端两级确认后调用。服务端再做路径安全校验：拒绝磁盘根目录、包含本工具的目录、工具目录内部、仍包含其他已登记项目或监视根目录的文件夹（400），符号链接/junction 同样拒绝；文件夹删除失败保留登记（500）。目录本就不存在时只移除登记并返回 `folderDeleted: false`；项目根同为监视根时一并从 `roots` 清理。`publishedUrl` 为已发布评审站地址（若有），远端不自动下线。

### 读取项目元数据
`GET /api/proto/read?projectId=p-xxx`
- Returns: `{ ok: true, root, bundle, discovered }`
- 说明：`bundle` 为 SCHEMA_VERSION=2 的完整元数据（project / prd / changes + revision），与「原型生成全流程」格式互认；读取时自动对齐 projectId、补登新页面（各 revision+1）。

### 保存项目元数据（CAS）
`POST /api/proto/save`
- Body: `{ projectId, expectedRevision, bundle }`
- Returns: `{ ok: true, bundle }`（服务端将 revision 置为 current+1）
- 冲突：HTTP 409 `{ ok: false, conflict: true, current, error }`；校验失败：HTTP 400 `{ ok: false, error }`（编号重复、引用未登记页面/状态、落点非法等）。
- 服务端拒绝修改、取消确认或删除既有 `confirmed: true` 标注；页面需求文档仍可编辑。未修改的确认标注可随 bundle 原样提交。
- 标注可选字段 `color: "#fdd143"` 保存序号颜色（P2 色板），删除该字段恢复默认蓝色；换色与正文共用 CAS，已确认标注仍只读。
- 工作台按位置产生的 `displayNumber` 仅用于前端展示，不写入 bundle、不改 metadata `number` 或 schema v2。其他工具仍可能显示原始 `number`。
- 客户端保存失败保留草稿；409 不再自动重新加载覆盖正文。

### 上传 PRD 图片
`POST /api/proto/upload-image`
- Body: `{ projectId, dataUrl: "data:image/png;base64,..." }`
- Returns: `{ ok: true, path: "prd-assets/<sha256>.png", url: "/ext/<projectId>/prd-assets/<sha256>.png" }`。
- 仅已登记本地项目可上传；沿用本机同源与 JSON 约束。支持 PNG/JPG/GIF/WebP，单张最多 10 MB，校验真实文件签名与声明 MIME；不接收 SVG/HTML，不信任客户端文件名。
- 图片按内容哈希去重，原子写入项目根 `prd-assets/`。上传不修改 revision；正文中的 `![图片说明](prd-assets/<sha256>.png)` 再通过 `/api/proto/save` 保存。
- 图片自定义宽度使用标准 Markdown 的 title 后缀保存：`![图片说明](prd-assets/<sha256>.png "proto-width=240")`；已有 title 保留为 `"图片标题 proto-width=240"`。宽度为 48–4096 的整数 CSS px，拖拽时额外受容器宽度限制。阅读 / 静态评审只解析有效后缀并移除元信息提示，旧图片不指定宽度时自适应。不增加 API 字段或修改 revision 协议。
- 未登记 404；格式、内容或大小无效 400；JSON 请求体超过 14 MB 返回 413；写文件失败 500。
- 研发版导出 / GitHub Pages 发布会把图片复制到 `proto/prd-assets/`。壳以站点入口为基准生成图片 URL，再通过 postMessage 将渲染正文送入气泡，兼容项目子目录、HTTP 与 file://；不写本机 localhost 地址进 Markdown。

### 查询评审壳发布状态
`GET /api/ext/publish-status?projectId=p-xxx`
- Returns: `{ ok: true, published, url, publishedAt }`；未登记 404。
- 读登记表 `data/external.json` 中的 `github_url` / `github_published_at`，供 viewer 悬浮工具栏「发布」区展示。

### 发布原型或研发版到 GitHub Pages
`POST /api/ext/publish`
- Body: `{ extId: "p-xxx", mode: "pure" | "review" }`；省略 mode 默认 `review`。
- Returns: `{ ok: true, url, publishedAt, message }`；未登记 404、缺 Token/用户名 400（含 `needGithubConfig: true`，viewer 据此自动弹配置引导）、元数据读取失败 409、构建或上传失败 500（错误均 `{ ok: false, error }`，失败不写本地发布记录）。
- 流程：登记校验 → 读取 bundle（自动对齐 projectId、补登新发现页面）→ 按 mode 构建纯原型或评审站 → 复用 GitHub 建仓 / Pages / 上传管线推送至 `projects/<extId>/` → 登记表写入发布地址、时间与版本 → 更新作品集列表页。`review` 使用 `review_export.build_review_export` 构建 `index.html` 评审壳与 `proto/` 原型副本；导出副本排除 `.prototype` / 隐藏项 / `exports` / `dist` / `node_modules` / `__pycache__`，单文件 >25MB 跳过。
- 发布地址形态 `https://<用户名>.github.io/<仓库>/projects/<extId>/`；Token 优先读取环境变量 `PROTOTYPE_GITHUB_TOKEN` / `GITHUB_TOKEN`，其次读取既有本机加密持久化配置，不写入项目或导出物。
- 评审壳为只读单文件应用：左页面树（多状态页可切换状态，经 PrototypeBridge 同步）、中间真原型 iframe（注入锚点脚本渲染编号气泡）、右栏页面需求与标注明细（壳内置零依赖 Markdown 渲染器，失锚标注灰显）；点气泡右栏滚动定位、点标注行原型滚动定位；支持 `#p=<pageId>&s=<stateId>` 深链。

### 下载原型或研发版
`GET /api/ext/export?extId=p-xxx&mode=pure|review`
- 本地与已解析的 AI 项目共用。`pure` 为纯原型，单 HTML 页面且无需附带资源时直接下载 HTML，其他情况 ZIP；`review` 为原型副本、只读评审壳、PRD 与图片，始终 ZIP。省略 mode 默认 `pure`，无效 mode 返回 400；没有内嵌版本。
- 沿用登记、路径白名单与本机同源约束，响应带附件下载头；只在临时目录构建导出物，不修改原型源文件。

### 取消发布评审壳
`POST /api/ext/unpublish`
- Body: `{ extId: "p-xxx" }`
- Returns: `{ ok: true, message }`；未登记 404、缺 Token/用户名 400（含 `needGithubConfig: true`）、远端操作失败 500。
- 递归删除远端 `projects/<extId>/` 全部文件（含嵌套目录），作品集列表页移除该项目，登记表清除 `github_url` / `github_published_at`。

### 白名单文件服务
`GET /ext/<projectId>/<相对路径>`
- 只伺服登记项目内的原型与静态资源（html/css/js/json/svg/图片/字体/媒体后缀）；拒绝路径穿越、`.prototype`/`exports`/`dist`/`node_modules` 与未登记项目（403）。
- HTML 响应在业务脚本前载入热区事件记账模块，不修改源文件；只初始化后才出现提示 UI。字符编码声明、doctype 及非 HTML 资源保持原样，响应 Content-Length 按处理后字节计算。

## 9. GitHub 发布配置

### 读取配置
`GET /api/github/config`
- Returns: `{ success: true, username, repo, tokenMasked, hasToken, tokenSource, tokenState }`；Token 仅返回打码值。
- `tokenSource` 为 `env`、`stored` 或空字符串；`tokenState` 为 `ready`、`missing` 或 `unreadable`。存在持久化文件但无法读取 / 解密时返回 `unreadable`，与未配置区分。
- Windows DPAPI 凭据绑定保存时的用户账户，服务必须由同一账户运行。

### 保存配置
`POST /api/github/config`
- Body: `{ token, username, repo }`；空 Token 不清除已有凭据。
- Returns: `{ success: true, message, tokenStored }`。提交新 Token 时先持久化，失败返回 `{ success: false, error, tokenStored: false }`，不替换进程中的旧 Token 或更新配置；成功后才启用新 Token。

## 10. 多端接入与导航元数据（2026-10-14）

现有 `/api/proto/read` 在补登记页面时读取项目根 `prototype.manifest.json`，校验并登记端、页面角色、预览类型、默认业务页和状态。角色由明确声明决定，没有清单的旧项目沿用原行为。

bundle 的 `project` 增加可选 `clients[{id,title,previewType}]`、`defaultPage`（页面 ID）及清单指纹；pages 增加 `clientId`、`role`（page / launcher）、`previewType`（web / mobile / pad）。端、页面及状态的 previewType 都支持 pad，代表横向平板画布与可关闭的外壳。`POST /api/proto/save` 沿用原 expectedRevision CAS，可通过工作台页面设置纠正字段；校验端引用和至少一个业务页，保存与读回保持这些字段。

页面还支持可选 `priority`（整数 1–6，1 最高）与 `progress`（整数 0–100，100 已完成）。缺省或 null 表示未标记，0% 表示明确未开始；UI 提供 0 / 25 / 50 / 75 / 100% 快捷选择。清除时删除对应字段即可。读取后应保留这些字段，通过原 CAS 保存，不修改页面 ID、排序或 PRD；不符合类型和范围的值返回校验错误。

导入清单不等于首页登记，CLI 入口与格式见 [多端接入与迁移](multi-client.md)。独立入口与两种导出复用共用导航；发布 / 导出 API 仍使用原端点和版本选择。

### 📝 最近更新 (2026-01-30)
- 测试自动文档更新功能 - SKILL优化测试

## 本地原型的需求范围元数据（2026-10-15）

`project.pages[].states[].interactionHints` 可选：`{mode:"targets",protoIds:[...]}` 仅提示清单中具体控件自身的真实交互，不继承容器范围，缺省 / 空数组不提示；`{mode:"all"}` 仅用于明确要求的整页提示。`GET /api/proto/read` 和研发导出保留此配置。

`POST /api/proto/save` 在原有 expectedRevision 与已确认保护之后，将被删除标注的 pageId / stateId / protoId 追加到 `prd.deletedAnnotations`，不存正文；以后保存不能移除已有删除定位。PRD 导入版本 3 使用此记录和历史导入定位防止补回，旧草稿不能通过省略范围绕过校验。
