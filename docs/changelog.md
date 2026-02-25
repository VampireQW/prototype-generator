# 更新日志 (Changelog)

## 2026-02-25
### 新增功能
- **模型管理弹窗左右布局**：弹窗改为左右分栏（左侧模型列表可滚动 + 右侧编辑/添加表单），解决模型多时保存按钮被挤出视口的问题。
- **模型复制功能**：模型列表新增复制按钮，可一键复制模型配置（名称自动加"(副本)"后缀），避免重复粘贴相同的 API 信息。
- **多模态标签**：模型新增"多模态"勾选项，勾选后在模型列表和下拉菜单中显示紫色"多模态"标签，方便快速识别模型是否支持图片识别。
- **项目列表显示模型名称**：左侧项目卡片新增模型名称展示（蓝色小标签），方便查看每个项目使用的 AI 模型。
- **Web 预览去圆角**：Web 端预览模式去掉四角圆角（`border-radius: 8px` → `0`），预览区域填满矩形边界，更符合网页实际展示效果。
- **Web 预览去间距**：Web 模式下移除预览容器内边距和阴影，页面内容贴边占满整个预览区域，无缝显示。
- **修复 Web/App 检测误判**：优化自动检测逻辑——移除 `router-view` 误判（Vue Web 应用也用）、表格检测改为需 3 行以上才算 Web 特征、新增宽容器检测（`max-w-5xl/6xl/7xl`）、调整优先级为 Web 特征优先（误判率更低）。
- **悬浮工具栏贴边**：预览模式右上角设置按钮位置从 `16px` 缩至 `6px`，更贴近角落，减少页面内容遮挡。
- **参考图选项平铺**：参考图的"仅参考布局 / 仅参考风格 / 像素级还原"从下拉菜单改为平铺标签按钮，选中态 indigo 高亮，操作更直观。

### 文件修改
- `src/index.html`: 模型管理弹窗重构为 `max-w-3xl` 左右布局 + 多模态 checkbox + `.similarity-btn` 样式
- `src/script.js`: 新增 `duplicateModel`；`editModel`/`saveModelForm`/`resetModelForm` 支持 `multimodal` 字段；`renderModelManagerList` 增加编辑高亮和复制按钮；`renderModelDropdown` 显示多模态标签；`renderProjectList` 显示 `model_name`；参考图选项改为 radio 按钮组
- `src/viewer.html`: Web 预览去圆角/去间距/去阴影 + `device-screen` 圆角重置 + 检测逻辑优化 + 悬浮工具栏位置调整
- `server.py`: `handle_generate`/`handle_generate_async`/`handle_create_placeholder` 存储 `model_name` 到项目记录


## 2026-02-14
### 前端优化
- **外壳按钮写实化**：iPhone 真机外壳的电源键、静音键、音量键改为凸出的黑色金属质感，增加 3D 阴影和高光反射效果。
- **状态栏不透明**：iOS 状态栏（时间、信号、电池）增加白色不透明背景，页面上滑时不再与内容重叠。
- **外壳开关联动**：关闭「显示真机外壳」开关时，同步隐藏灵动岛、状态栏和底部横条，纯显示页面内容；重新开启时恢复。

### 文件修改
- `src/viewer.html`: 外壳按钮 CSS 样式优化 + 状态栏 `background: #fff` + `setPreviewMode` 逻辑增强

## 2026-02-13
### 新增功能
- **AI 模型切换器**：顶栏新增模型选择器，支持快速切换 AI 模型；点击「管理模型」可添加/编辑/删除模型配置。
- **模型配置存储**：新增 `models.json` 文件，集中管理多个 AI 模型的连接信息（base_url、api_key、model）。
- **统一模型调用**：`call_ai_model()` 改为动态读取 `models.json` 中选中的模型，主页生成和微调模式「AI 直接修改」均使用同一模型。

### 后端改进
- **新增 API**：`GET /api/models` - 获取模型列表和当前选中模型
- **新增 API**：`POST /api/models/select` - 切换选中模型
- **新增 API**：`POST /api/models/save` - 添加或编辑模型
- **新增 API**：`POST /api/models/delete` - 删除模型（至少保留一个）
- **配置拆分**：`config.json` 仅保留 `server` 和 `ai_options`，模型连接信息迁移至 `models.json`

### 前端优化
- **App 预览隐藏滚动条**：App 模式（手机框）下隐藏 iframe 内的原生滚动条，页面仍可正常滑动。

### 文件修改
- `server.py`: 新增 `load_models`/`save_models`/`get_selected_model` + 4 个模型管理 API + `call_ai_model` 重构
- `src/script.js`: 新增模型管理全套函数（loadModels、selectModel、saveModelForm 等）
- `src/index.html`: 顶栏模型选择器 + 模型管理弹窗
- `src/viewer.html`: App 模式注入隐藏滚动条样式
- `models.json`: 新增文件
- `models.example.json`: 新增分享版模板
- `config.json`: 移除 api 节点
- `.gitignore`: 新增 `models.json`
- `打包分享版.bat`: 增加 `models.json` 模板复制，更新 README

## 2026-02-09
### 新增功能
- **异步生成模式**：点击"AI 生成"后，项目立即出现在左侧列表并显示🔵"生成中..."状态，后台线程完成生成后自动更新状态并打开预览。
- **剪切板粘贴图片**：参考图上传区域支持直接粘贴剪切板中的图片（Ctrl+V），鼠标悬停即可粘贴，无需点击。
- **前端状态轮询**：新增 `pollGenerationStatus` 函数，每3秒轮询后端状态，实时更新项目列表。

### 后端改进
- **新增 API**：`POST /generate-async` - 异步生成项目，立即返回带 `generating` 状态的项目信息，后台线程完成 AI 调用。
- **线程管理**：`handle_generate_async` 函数使用 `threading.Thread` 实现后台生成，避免阻塞前端请求。

### 前端优化
- **上传区焦点样式**：dropzone 添加 `tabindex="0"` 和焦点样式，支持键盘粘贴。
- **提示文字更新**：上传区提示更新为"点击、拖拽或粘贴上传"。

### 文件修改
- `server.py`: 新增 `handle_generate_async` 和 `_call_ai_for_async` 方法
- `src/script.js`: 修改 `generateWithAI`、新增 `pollGenerationStatus`、增强 `setupPageListeners`

## 2026-02-06
### 新增功能
- 优化微调模式提示词（新增目标文件路径、页面信息、元素详情）；新增整页面修改功能；复制提示改为Toast通知

## 2026-02-05
### 修复
- **复制 Prompt 项目ID不一致**：修复了前端 `generateProjectIdFromName()` 与后端 `generate_project_id()` 时间戳格式不一致的问题。现在前端也使用12小时制（含am/pm和秒数），确保外部AI工具能正确定位到占位项目文件夹。
- **Prompt内容优化**：复制的Prompt中现在包含完整的项目文件夹ID，而不仅是项目名称，方便外部AI工具精确定位。
- **整页面弹窗输入框**：修复输入框样式（宽度、高度、边框）并支持弹窗拖动。

### 新增功能
- **占位项目状态自动更新**：当外部AI工具生成 `index.html` 后，刷新页面会自动检测并将「待外部生成」状态更新为正常项目。
- **微调提示词优化**：元素微调提示词新增目标文件路径、当前页面/路由、元素ID/class/文本内容等信息，帮助AI IDE工具精确定位。
- **整页面修改功能**：微调模式底部提示条新增紫色「整页面」按钮，支持针对整个页面的修改需求。

## 2026-01-30
### 修复
- 修复hasAnyInput函数中getElementById的ID参数错误（多余的#符号导致null错误）
### 新增功能
- 添加输入验证：AI生成和复制Prompt按钮在无输入时显示提示
- 测试自动文档更新功能 - SKILL优化测试
- 测试自动文档更新功能 - 新增复制Prompt按钮
- **复制 Prompt 功能**：新增「复制 Prompt」按钮，支持将设计需求复制到剪贴板，可用于 Antigravity、Cursor、Claude 等外部 AI 工具。
- **占位项目**：点击复制 Prompt 后自动创建占位项目，参考图片保存到项目文件夹，标记为「待外部生成」状态。
- **状态可视化**：项目列表支持显示项目状态（生成中🔵、失败🔴、待外部生成🟡），带动画效果。

### 后端改进
- **新增 API**：`GET /api/generation-status` - 查询项目生成状态。
- **新增 API**：`POST /create-placeholder` - 创建不调用 AI 的占位项目。
- **异步基础设施**：添加线程管理和任务队列系统（`generating_tasks`），为未来异步生成做准备。

### 前端优化
- **UI 增强**：复制 Prompt 按钮采用绿色渐变配色，与 AI 生成按钮并列显示。
- **CSS 兼容性**：修复 `line-clamp` 属性的浏览器兼容性警告。

### 文件修改
- `server.py`: 添加异步任务管理、generation-status 和 create-placeholder 端点
- `src/script.js`: 实现 copyPromptToClipboard 函数和状态显示逻辑
- `src/index.html`: 新增复制 Prompt 按钮，修复 CSS 兼容性

### 备份
- 备份路径: `backups/20260130_145123_异步生成和复制Prompt功能/`
- 备份文件: `server.py`, `src/script.js`, `src/index.html`

## 2026-01-29
### 修复与优化
- **网络层增强**：彻底解决了 AI 接口调用时的 `SSLEOFError` 连接中断问题。
- **Curl 智能兜底**：实现了双层请求机制。当 Python `requests` 库因网络环境（如 VPN/代理干扰）遭遇 SSL 握手失败时，系统会自动降级调用系统原生 `curl` 命令进行重试，大幅提升了在复杂网络环境下的稳定性。
- **环境诊断**：优化了网络连接检测逻辑。

## 2026-01-26
### 维护 (Maintenance)
- **项目清理**：执行了深度清理，删除了 26 个开发过程中用于修补和更新生成项目的临时 Python 脚本及辅助工具，保持生成器项目目录整洁。

## 2026-01-24
### 新增功能
- **复制项目**：左侧项目列表新增复制按钮，支持一键复制项目到新名称。

### 修复
- **项目同步**：修复手动复制项目文件夹后未同步到列表的问题。
- **去重逻辑**：修复复制项目时可能产生重复条目的 Bug。

## 2026-01-23
### 修复
- **微调模式**：修复了弹窗因 CSS 权重问题无法关闭（一直显示）的 Bug。
- **微调模式**：优化弹窗 UI 为跟随式（非全屏遮罩），允许操作底层元素。
- **微调模式**：修复了点选和 Ctrl+多选在某些情况下失效的问题（重构为 Overlay 统一接管事件）。
- **微调模式**：弹窗尺寸优化（更紧凑），并支持按住标题栏拖拽移动。
- **全局设置**：右上角设置按钮尺寸缩小（32px），并支持自由拖拽移动（防遮挡）。

### 新增功能
- **微调模式 (Inspector Mode)**：
  - 支持点选/框选元素
  - 自动生成上下文 Prompt
  - 后端 AI 接口直接修改 HTML

## 2026-01-22
### 修复与优化
- **页面同步修复**：修复预览模式下 JS 错误，优化 iframe 同步机制。
- **UI 统一**：所有模式统一使用悬浮工具栏。
- **界面优化**：移除顶部 Header，增加返回按钮。

## 2026-01-21
### 新增功能
- **纯预览导出**：只导出原型本身，不含研发数据。
- **预览模式**：新增默认的沉浸式预览模式。

## 2026-01-19
### 新增功能
- **PRD 撰写系统**：Markdown 编辑与存储。
- **研发模式**：集成流程图与页面导航。
- **零依赖导出**：支持 `file://` 协议运行。
