# 备份与回滚日志 (Backup & Rollback Log)

## 发布更新通知与说明（2026-11-03）

修改前核心文件、共享评审模块、发布 / 导出测试和对应文档保存至 `backups/20261103_release_updates/`，沿用相对路径。`src/proto-text-runtime.js` 的原导出接口另存同目录；PRD skill 随服务副本同步前也已备份，保留本地已确认规则。

回滚恢复相应 server / github_pages / review_export、viewer / 首页、review shell / bridge、文本运行时及文档，移除新增 publication_versions.py、publication-updates.js/css、change-locator.js，再重启服务。真实项目、凭据和远端发布均未为验证改写；浏览器验证使用 tmp/release-updates 下的隔离项目。

上线后产生的 `.prototype/releases/` 为独立版本记录，回滚旧代码可保留而不读取；远端新研发版自包含运行代码，恢复本地代码不会改写已发布内容。需要撤回远端行为应显式重新发布，不删除业务 PRD 或原型。

## 遗留入口与历史产物清理（2026-11-03）

清理前工作树差异及加载 / 发布时间修复快照保存在 `backups/20261103_legacy_cleanup/`。`retired-source.zip` 保存退役的 16 个源码 / 脚本；`historical-exports.zip` 和 `historical-tomodao.zip` 保存历史交付文件，共 176 个文件。每个 zip 均有相对路径、长度与 SHA-256 清单，已逐条回读校验。

需要回滚时，从对应 zip 按归档内相对路径恢复指定文件；当前修改前文档与运行文件另存 working-tree 子目录。`cleanup-result.json` 记录实际清理和权限受限目录，执行与验证详情见 `docs/archive/task_20261103_legacy_cleanup.md`。未改写项目、回收站、模型配置和发布凭据。

## 发布与导出时间统一（2026-11-03）

修改前的 server.py、review_export.py、src/review_shell.html、相关发布 / 导出回归及对应文档保存到 backups/20261103_publication_time/，保留相对路径。恢复对应文件并重启服务可撤回时间统一修复；不涉及原型业务文件、PRD、GitHub 凭据或历史发布记录。

## 预览启动加载过渡（2026-11-03）

修改前的 src/viewer.html 与对应更新日志、功能、架构文档保存到 backups/20261103_preview_loading/，保留相对路径。恢复 viewer 并移除新增 src/preview-loading.js、src/preview-loading.css 及对应回归即可撤回；前端刷新生效，不涉及业务原型、项目配置或 PRD。

## 首页打开项目目录（2026-10-28）

修改前的 server.py、src/script.js、src/index.html、首页菜单回归及对应文档保存到 backups/20261028_open_project_folder/，保留相对路径。恢复对应文件并重启服务可撤回目录入口；新增 tests/test_open_folder.py 可随回滚移除，未修改项目目录与凭据。

## 发布卡显示发布时间（2026-10-28）

修改前的 src/viewer.html、src/workbench.css 及本次对应文档保存到 backups/20261028_publish_time/，保留相对路径。恢复对应文件即可撤回，前端刷新生效；未修改凭据、发布记录和 PRD。

时间独占一行的布局调整前，另存 src/viewer.html、src/workbench.css 到 backups/20261028_publish_time_layout/。

## GitHub 错误分类与通用标注显隐（2026-10-28）

GitHub 修改前的 server.py 与继续验证前的锚点 / 标注 / 交互 / 评审脚本、viewer 已保存到 backups/20261028_github_diagnostics/，保留相对路径。proto-order.js 的修改前基线也保存在同目录。该备份包含此前的通用显隐改动；需要整体恢复至本次修改前时，以 Git 中 2405e3f 为基线逐文件回溯。未备份或修改真实凭据、原型业务文件和 PRD。撤回网络模块时同时恢复 server.py 并移除新增 github_transport.py；完成后重启服务。

## 首页升级（2026-10-10）

修改前备份至 backups/20261010_home_commercial/，保留相对路径：src/index.html、src/home.css、src/home-ui.js、src/script.js、server.py、DESIGN.md、docs/changelog.md、docs/features.md、docs/architecture.md、docs/api.md、docs/backup_log.md、.finesse/log.json。

回滚恢复对应文件并重启服务；新增 home_thumbnails.py、src/vendor/tailwind-runtime.js 与 tests/test_home_thumbnails.py 可随回滚移除。tests/test_external_api.py 仅新增隔离模块导入，回滚删除该行。data/home-thumbnails 是可重建缓存，无需回滚项目数据。本次没有修改凭据、原型源码或 PRD。

> 记录每次关键变更前的备份点，以便快速回滚。

## 2026-10-07 PRD 格式工具条移至编辑框外侧

修改前备份 `src/proto-markdown.js`、`src/proto-markdown.css`、`src/viewer.html`、`src/markdown-editor.html`、`tests/test_annotation_ui.py`、`DESIGN.md`、`docs/features.md`、`docs/architecture.md`、`docs/changelog.md`、`docs/backup_log.md` 至 `backups/20261007_toolbar_outside/`，保留相对目录。回滚时将备份恢复至各自原位置。2026-10-08 完成高度同步定位与浏览器验收；`tests/test_prd_editor_browser.py` 同步更新断言和交互覆盖，其修改前版本未包含在此备份中。

## 2026-10-06 PRD 工具条布局与图片缩放

修改前备份 `src/proto-markdown.js`、`src/proto-markdown.css`、`src/markdown-editor.js`、`src/markdown-editor.html`、`src/viewer.html`、`src/review_shell.html`、`tests/test_annotation_ui.py` 至 `backups/20261006_prd_layout_image_resize/`，保留相对目录。新增真实浏览器回归 `tests/test_prd_editor_browser.py`，回滚时恢复备份并移除新增测试。本次没有修改服务配置、凭据、用户原型文件或现有 PRD。

## 2026-10-05 视觉风格预设与按需自定义

修改前备份 `server.py`、`src/index.html`、`src/script.js`、`src/home.css` 与隔离接口测试至 `backups/20261005_style_presets/`，路径中的 `/` 以 `__` 编码。新增 `design_settings.py`、`src/design-settings.js` 与视觉配置回归；回滚时恢复旧文件并移除新增模块引用。没有备份或修改凭据文件、用户原型源文件与现有项目资料。

## 备份策略

1. **执行时机**：每次开始新任务 (`docs/templates/task_template.md`) 的 "准备阶段"。
2. **备份内容**：仅备份将被修改的核心文件（如 `server.py`, `src/viewer.html`）。不要备份整个 `projects/` 目录（太占空间）。
3. **命名规范**：`backups/YYYYMMDD_{任务名}/`

## 备份记录

| 日期 | 任务名称 | 备份路径 | 包含文件 | 备注 |
|------|----------|----------|----------|------|
| 2026-10-05 | 热区透明橙色覆盖 | `backups/20261005_hotspot_orange_fill/` | src/proto-hotspots.js、tests/test_hotspots.py | 保留橙色描边与分离线版本；回滚还原原位置，不含原型业务资料或凭据 |
| 2026-10-05 | 热区识别纠错与橙色呼吸 | `backups/20261005_hotspots_accuracy_orange/` | src/proto-hotspots.js、src/viewer.html、src/review-bridge.js、review_export.py、server.py、tests/test_hotspots.py、tests/test_review_export.py | 七个文件按 basename 保存，回滚还原原位置；不包含用户原型业务资料或凭据 |
| 2026-10-05 | 原型点击热区短暂提示 | `backups/20261005_click_hotspots/` | src/viewer.html、src/review-bridge.js、src/review_shell.html、review_export.py | 四个核心文件按 basename 保存；回滚还原原位置并移除新增 proto-hotspots.js。备份不含原型业务资料或凭据 |
| 2026-10-05 | 首页顶部留白收紧 | `backups/20261005_tighten_home_gap/` | src/home.css、src/index.html | 保留 24px 工作区上边距与样式缓存版本，备份按 basename 存放，回滚到原位置 |
| 2026-10-05 | 发布菜单与 GitHub Token 读取修复 | `backups/20261005_publish_panel_token/` | src/viewer.html、server.py | 保存发布菜单、配置状态与 Token 保存流程；备份文件按 basename 存放，回滚到原位置。凭据文件未改动 |
| 2026-10-05 | 统一工作台收尾、刷新图标与名称对齐 | `backups/20261005_finish_workbench_ui/` | src/index.html、src/home.css、src/home-ui.js、src/proto-navigation.js、server.py、proto_meta.py、review_export.py | 保存 10-04 工作台改造后的代码；备份文件按 basename 存放，回滚时还原到各自原位置 |
| 2026-10-04 | AI 与本地统一工作台、App 外壳及共享导出 | `backups/20261004_unify_ai_workbench/` | server.py、proto_meta.py、review_export.py、index.html、script.js、src/viewer.html | 保留改造前 AI / 本地入口、旧 AI 导出弹窗、元数据 / 发布导出与外壳逻辑；回滚按原位置还原六个文件，并移除本轮新增 proto-navigation.js 引用 |
| 2026-10-04 | 新建项目顶部工具栏压缩 | `backups/20261004_compact_creation_toolbar/` | src/home.css、src/index.html | 保留工具栏 12px 上下内边距、40px 桌面控件与旧样式缓存版本；回滚还原这两个文件 |
| 2026-10-04 | 首页来源页签与新建入口合行 | `backups/20261004_merge_project_tabs/` | src/index.html、src/home.css、src/home-ui.js、tests/home_ui_probe.py | 保留标题 / 总数 / 副文案及新建按钮独立一行的旧结构、计数逻辑、资源缓存版本与浏览器探针；回滚还原这四个文件 |
| 2026-10-04 | 新建项目名称与自动命名 | `backups/20261004_project_name/` | src/index.html、src/home.css、src/script.js、src/home-ui.js | 保留添加项目名称输入、自动命名、概览与历史回填前的行为及缓存版本；回滚还原这四个文件 |
| 2026-10-04 | 新建项目紧凑设计设置 | `backups/20261004_compact_creation_settings/` | src/index.html、src/home.css、src/script.js、src/home-ui.js | 保留创建工具栏、三列设置与概览装饰图旧布局；回滚还原前三个文件，home-ui.js 仅预防备份、本轮未修改 |
| 2026-10-04 | 项目搜索工具条与本地添加面板精修 | `backups/20261004_polish_project_toolbar/` | src/home-ui.js、src/home.css、src/script.js、src/index.html | 保留搜索留白、下拉箭头、焦点与目录 / 粘贴路径面板旧样式及资源缓存版本；回滚还原这四个文件 |
| 2026-10-04 | 本地原型与 AI 项目卡片图标统一 | `backups/20261004_unify_project_icons/` | src/home-ui.js、src/home.css、src/script.js、src/index.html | 保留本地独立封面图形、图文操作按钮与静态资源缓存版本；回滚还原这四个文件 |
| 2026-10-04 | AI 项目列表恢复多列卡片布局 | `backups/20261004_fix_ai_project_grid/` | src/script.js、src/index.html、tests/home_ui_probe.py | 保留修复前来源切换布局、脚本缓存版本与浏览器探针；回滚还原这三个文件 |
| 2026-10-04 | 首页头部与列表间距压缩 | `backups/20261004_compact_home_header/` | src/home.css、src/index.html | 保留压缩前的顶栏、首页间距与样式缓存版本；回滚还原这两个文件 |
| 2026-10-04 | 首页全屏项目工作台与独立创建页 | `backups/20261004_fullscreen_project_home/` | src/index.html、src/script.js、tests/test_annotation_ui.py | 保留原列表 / 创建并排界面及已有未提交改动；回滚还原备份并移除本轮新增 home.css / home-ui.js 引用，新增 vendor 资源不影响旧入口 |
| 2026-10-04 | PRD 虚线颜色调淡 | `backups/20261004_soften_prd_dividers/` | src/viewer.html、src/review_shell.html | 保留原来虚线使用通用边框颜色的样式 |
| 2026-10-04 | 序号色板与底部操作精修 | `backups/20261004_refine_pin_palette/` | src/viewer.html、src/proto-appearance.js、tests/test_prd_media.py | 保留十种浅色色板与恢复默认文字按钮的旧实现 |
| 2026-10-04 | 左右悬浮按钮位置尺寸对齐 | `backups/20261004_align_floating_controls/` | src/viewer.html | 保留调整前的展开按钮与模式切换悬浮按钮样式 |
| 2026-10-04 | PRD 标注分隔线改为虚线 | `backups/20261004_dashed_prd_separators/` | src/viewer.html、src/review_shell.html | 保留调整前的标注条目分隔线样式 |
| 2026-10-03 | 图片上传旧服务与重复监听修复 | `backups/20261003_upload_service_fix/` | server.py、src/viewer.html | 保留修复前的启动方式与上传回调 |
| 2026-10-03 | 色板弹层缩小 | `backups/20261003_compact_color_palettes/` | src/proto-markdown.css、src/viewer.html | 保留调整前的色样与弹层尺寸 |
| 2026-10-03 | 本地项目搜索与创建时间排序 | `backups/20261003_local_project_search/` | server.py、proto_meta.py、src/index.html、src/script.js | 保留此前色板 / 图片功能及已有未提交内容 |
| 2026-10-03 | PRD 文字/序号色板与图片 | `backups/20261003_prd_palette_images/` | server.py、proto_meta.py、review_export.py、viewer / Markdown / 标注 / 评审源文件 | 保留本轮修改前已有未提交内容 |
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
| 2026-03-04 | 16:05 | 增强 GitHub 发布功能 | Git Repo | server.py, src/index.html, src/script.js | 使用 Git 提交作为备份 |
