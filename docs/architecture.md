# 架构设计 (Architecture)

## 首页升级（2026-10-10）

src/home-ui.js 管理共用卡片、视口观察、封面请求、更多菜单、弹窗焦点与首页主题；业务仍由 src/script.js 调用已有接口。DOM 文本用 textContent 写入；路径和名称不作为 HTML 片段。

home_thumbnails.py 使用两个后台线程分发独立渲染进程，队列上限 64；每个任务限时 28 秒。源文件路径、大小和修改时间参与指纹，缓存写入 data/home-thumbnails，固定卡片窗口不产生布局跳动。没有逐卡片的实时 iframe。

封面使用可选的 Playwright Chromium 和 Pillow。新上下文不携带浏览器账号状态，禁止业务 POST、外部请求、Service Worker、WebSocket 和 EventSource；只提供经 safe_asset 校验的本地资源与已归档的 Tailwind / Font Awesome。无法离线呈现的页面回退名称卡片。截图不会点击项目控件，也不写用户原型或 PRD。缓存只能经项目授权接口访问，静态服务拒绝缓存路径。

新增依赖缺失时保持项目文字卡片与原业务可用；当前 C:\python.exe 环境已完成离线渲染验证。首页自身继续使用本地预编译 CSS。

## 视觉配置解析（2026-10-05）

`design_settings.py` 是无服务副作用的视觉配置模块，读取风格资产的 Color 章节，按颜色角色解析主辅色、主题和组件语言，按文件修改时间缓存预设。语义文字与控件边界通过对比度选择；缺失主题角色继承 home 基线。`/api/design-systems` 返回预设和六角色色样。

`src/design-settings.js` 按同一版本 2 协议解析表单，色样、Prompt、请求和历史回填共用 `getEffectiveDesignSettings()`。Python / JS 的解析结果及覆盖规则文本由回归用例直接比对。后端在 AI 同步 / 异步生成、复制 Prompt 占位、外部项目包入口再次规范化配置。

`compose_generation_prompt()` 在风格资产后声明继承与主动覆盖；默认风格也注入默认规范。复制 Prompt 采用后端返回 `instruction`，保存同一 `prompt.txt`。项目包 `DESIGN.md` 将主动覆盖置于风格原始规范之上，字体、排版和组件语言继续继承；记录存最终值与显式覆盖，未改默认值不作为用户指令。

## 1. 系统架构

### PRD 工具栏与图片尺寸（2026-10-07 更新）

`proto-markdown.js` 负责会话和外侧悬浮工具栏：工具栏始终以 `position: fixed` 挂在所属文档根节点，不创建占位 slot，也不使用 `is-docked` 状态。浮窗定位以整个 `.pa-card` 外框计算上、下、左、右候选位置，间隔 12px；右侧 PRD 优先使用侧栏左外侧空间。`ResizeObserver` 跟踪卡片、编辑区和侧栏尺寸，触发重新摆位；编辑器 `resize` 桥接同步更新高度与工具栏坐标，覆盖图片载入和正文重排。手动拖动只改变悬浮坐标，不保留原位置高度；双击握把或按 Enter 恢复自动摆位，结束编辑清理工具栏和观察器。分组布局通过 CSS 适配可用宽度，三处编辑共用。

`markdown-editor.js` 在 Vditor IR 文档的编辑面之外建立图片选择框，不把控制柄写入正文。pointer capture 跟踪等比拖动，预览只改图片展示宽度；松手才将有效 `proto-width=N` 后缀写入图片 title，并显式记录固定版本 Vditor 的撤销栈，避免 800ms 原生延迟导致立即撤销无效。取消、销毁与编辑面重建清理拖拽状态。

会话保存和草稿仍走原 Markdown / CAS 协议。工作台安全渲染继续限制 `prd-assets/<hash>.<extension>` 与 DOMPurify；静态评审壳先转义文本，再解析相同整数尺寸并通过已有 postMessage 将正文送到只读气泡。没有外部图片、任意样式或新增服务端接口。导出每次读取 `review_shell.html`，本次静态资源和模板更新无需重启服务。

本系统采用 **Python (后端) + 原生 HTML/JS (前端)** 的轻量级架构，零依赖运行。

### 后端 (server.py)
- 基于 `http.server` 的原生实现，无 Flask/Django 依赖。
- 职责：
  - 静态文件服务
  - AI 大模型调用代理
  - 项目/文件管理 (CRUD)
  - 设计系统、skills、craft 资产读取与 Prompt 组装
  - PPTX 解析、原始配图提取与 HTML PPT 生成辅助
  - PRD/Inspector API 支持
  - HTML 解析与流程图生成
  - **网络层增强**：集成智能代理探测与 `curl` 命令行兜底机制，确保在 SSL 握手失败等极端网络环境下仍能稳定调用 AI 接口。

### 前端 (Viewer)
- **HTML5 + ES6**；原型 iframe 可独立使用 Vue 等前端框架。
- **viewer.html**：AI 与本地原型共用预览 / 微调 / 标注工作台。
- **iframe**：加载生成的原型项目，隔离运行环境。

---

## 2. 核心机制

### AI 与本地原型统一接入（2026-10-04）

AI 项目仍保留首页旧 ID、生成记录与协作归属。`POST /api/projects/workbench` 安全解析真实项目目录，幂等初始化或读取 `.prototype`，将旧 AI ID 映射到 `p-xxx` 登记 ID；旧 PRD 迁入页面需求时保留人工已有内容。`viewer.html?project=旧ID` 先解析，再复用 `initExternalMode`；本地 `?ext=p-xxx` 直接进入相同工作台。两者共用 iframe 锚点、PRD CAS 保存、元素修改 Prompt 与发布 / 导出管线。

多 HTML 项目以 `project.pages[].file` 导航；同一 HTML 中的旧 Vue / Router 页面映射为首页 adapter 状态，记录 `legacyPage`、`legacyType` 与可选路由路径。`src/proto-navigation.js` 连接现代 `PrototypeBridge` 与旧框架导航，在原型业务导航和 `data-proto-state` 之间同步状态，Viewer 与研发版评审壳共用适配模块，切换同文件状态不重载 iframe。

创建页三种生成入口统一提供稳定 `data-proto-id`、根元素页面 / 状态 / 预览类型与 `PrototypeBridge.enter(stateId)` 协议；`record.json` 中保存 `global.previewType`。App / Web 自动预览依次读取原型根元素 `data-proto-preview`、页面 / 项目元数据与 DOM 特征。真机外壳开关只切换容器样式与装饰显示，保留 iframe 文档、表单内容和业务状态，并跨工作台模式与页面沿用所选外壳状态。

AI「导出与分享」解析工作台 ID 后复用本地弹窗和 `/api/ext/export`、`/api/ext/publish`：`pure` 构建纯原型，`review` 构建只读评审壳与原型副本；共享版本选择，删除旧 AI 专属导出弹窗与内嵌入口。团队协作分享仍使用原归属与团队接口。

AI 导出复制成品与资源，排除根目录的生成记录、完整 Prompt、TASK / AGENTS / DESIGN 以及 `prd/`、`pages/*.md`；研发需求从共享元数据打包进评审壳。业务资源目录内的同名文件继续保留。AI 发布沿用原 AI 项目远端目录，发布 / 取消发布同步原生成记录；本地项目沿用原复制规则。

### 页面导航与状态同步
本机工作台与原型 iframe 同源，Viewer 通过 `PrototypeBridge.enter(stateId)` 切换同文件状态，并观察根元素 `data-proto-state`，同步导航和当前 PRD。已有作者 Bridge 保持原对象和实现，系统只为旧项目增加适配器。

`proto-navigation.js` 为旧项目连接 Vue 的全局 ref、Options data、Composition setup、组件 proxy 或 Router。启动时读取当前业务视图，避免把首页 PRD 错误归到 default；显式 default 恢复初始视图。同名业务页面按 slug 追加 `-2`、`-3`，分别保留需求。业务导航变化通过 Router 监听、hash 监听与适配器检查同步到根元素；跨 HTML 导航才加载新文档。

研发版导出将状态配置、导航适配器与锚点 / 评审脚本注入原型副本。评审壳通过 `postMessage` 与 iframe 通信，在 HTTP 与 `file://` 下使用相同的导航、标注和 PRD。

### 点击热区发现

`src/proto-hotspots.js` 提供 `ProtoHotspots.init / show / hide / destroy`，自身不自动启动提示 UI。文件服务只在 HTML 响应副本中提前载入模块，源文件保持原样；模块记录交互事件的实际绑定及移除，保留回调身份、this、去重、capture、once 和 AbortSignal，避免仅凭按钮标签、role 或 cursor 误判。React 根代理由元素 props 的实际业务回调识别；任意自定义祖先代理的区域使用显式热点声明。无实际行为的普通按钮、空链接和占位链接排除。

Viewer 在同源 iframe 完成载入时幂等初始化，启用回调读取预览 / 标注、微调、点选与正文编辑状态；模式切换、新建标注和原型页面 / 状态变化清理提示。外部画布点击调用 iframe 的 show，拖动与控件操作排除。模块不修改业务元素，用 `data-prototype-owned` 的独立、无点击事件的层绘制半透明橙色热区；提示不带边框 / 外圈 / 阴影，透明度呼吸并按时清理。遮挡检测、祖先裁切及滚动 / 尺寸变化定位均在 iframe 内完成。

研发版在业务脚本前内嵌热点模块，之后在页面尾部内嵌 appearance → anchors → order → bridge → pins；原来的 charset 与 doctype 保留在前，加载器防重复。`review-bridge.js` 在评审 iframe 中初始化热区，并接受经过父窗口 source 校验的 `showHotspots` 消息；评审壳画布通过 postMessage 触发，无需读取子页 DOM，兼容 file://。原型副本单独打开时 bridge 退出，纯净版构建不注入此模块。现有隐藏标注引导及 PRD 编号机制保持独立。

### 跨域与文件协议支持
为了支持 `项目导出` 后在本地 `file://` 协议下运行：
- 所有资源引用使用相对路径。
- 页面跳转依然依赖 `postMessage`，绕过 `file://` 下的跨 iframe 访问限制（同源策略在 file 协议下表现不同）。

### GitHub 凭据与服务启动账户

Windows Token 由 DPAPI 加密至 `data/github_token.bin`，绑定保存时的 Windows 用户。服务重启应使用该用户账户；自动化沙箱账户启动的 Python 即使能读文件，也无法解密，不能据此判断 Token 已丢失。用户双击 `启动项目.bat` 沿用当前账户；Agent 后台启动时同样使用用户账户执行环境，隐藏窗口。

配置 GET 通过 `tokenState` 区分可用、未保存与无法读取。保存新 Token 必须先成功落盘，随后更新进程环境与配置；失败返回错误并保留原设置。诊断仅输出可读状态，恢复服务不修改原凭据文件。

---

### 设计资产注入

生成 Prompt 不再只依赖首页表单，而是由后端统一组合多层设计上下文：

```
用户输入
  ↓
design-systems/{id}/DESIGN.md
  ↓
skills/{productType}/SKILL.md
  ↓
craft/*.md
  ↓
主题色 / 辅助色等表单偏好
```

优先级为用户明确输入最高，其次是设计系统、产物 skill、craft 通用规范，最后才是表单颜色偏好。这样可以让同一产物类型稳定复用 OpenDesign 风格资产，同时保留用户对具体页面的控制。

### HTML PPT 生成链路

导入 PPT 美化模式会先调用 `/api/pptx/parse` 解析 `.pptx`：

1. 服务端用标准库读取 PPTX 压缩包结构，提取 slide 顺序、文字和媒体引用。
2. 图片按真实二进制签名过滤，只保留浏览器和多模态模型可处理的图片类型。
3. 每页最多保留 5 张 PPT 原始配图，前端允许删除超额或不需要的图片。
4. 生成时后端把 PPT 配图和额外参考图区分写入 `record.json`，并在 Prompt 中要求配图回到对应页面。

HTML PPT 产物应是单文件演示稿：默认概览模式，播放时每页占满 `100vw x 100vh`，通过键盘/鼠标翻页，并用 `Esc` 或右键退出播放。

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
│   ├── viewer.html        # 统一工作台（预览/微调/标注）
│   ├── proto-navigation.js # Bridge / Vue / Router 状态导航适配
│   ├── proto-hotspots.js   # 点击空白时短暂提示可见交互热区
│   ├── index.html         # 项目列表与独立创建页
│   └── style.css          # 全局样式
├──
├── design-systems/        # 设计系统资产（DESIGN.md）
├── skills/                # 产物类型生成 skills
├── craft/                 # 通用设计工艺规范
├──
├── projects/              # 用户项目存储
│   └── {项目ID}/
│       ├── index.html     # 原型 HTML 文件
│       ├── .prototype/    # 项目、PRD、修改任务元数据
│       ├── prd/           # PRD 文档目录 (.md)
│       └── images/        # 资源文件
├──
├── docs/                  # 开发文档
└── scripts (bat/py)       # 辅助工具脚本
```
