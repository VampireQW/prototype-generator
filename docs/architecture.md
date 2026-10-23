# 架构设计 (Architecture)

## 共用展开入口与路径复用（2026-10-23）

`proto-interactions.js` 的点选器在原型文档插入临时自有样式，让 `[data-prototype-owned]` 图层及其子节点穿透，避免已有 `pa-guide` 截获点选；窗口捕获监听继续阻止原型业务动作。选择、取消、页面离开均通过同一 cleanup 移除样式和监听。

编辑器的 commitReveal 对添加、删除、排序和复用立即调用 saveReveal / CAS，保存期间禁止重复操作，显示状态；失败保留当前修改并提供重试 / 放弃，不显示已生效。「展开方式」从当前真实步骤匹配来源，没有采用的来源不会预选。显式复用深拷贝步骤并只保存当前标注，确认保护保留。

编辑器监听原型文档的业务显隐变化，过滤平台自有层并合帧调用被动 refresh。以当前作用域、视图、配置和识别报告的语义快照过滤无变化的刷新，避免连续业务动画反复撤换按钮。pointerdown / 键盘按下到释放后的下一帧之间延后后台刷新，使浏览器 click 完成后才应用状态变化；保存、点选、待确认步骤和表单输入期间同样延后。同一视图重绘恢复滚动位置，iframe 换页断开旧观察者。

`ProtoAnchors.inspectReveal` 是编辑器的只读检查接口，不执行 reveal 或业务点击，不写入元数据。目标可见时也沿祖先检查显式展开声明、原生 details / ARIA 控制关系，按外到内展示步骤；未知的隐藏 / 语义可收起区域报告需补充，直接可见且无已知关系的目标报告当前无需展开。同一区域的唯一手动路径可展示共用来源；多路径冲突、重复定位、缺失 / 禁用入口明确报告需处理。详情展示入口当前隐藏，不把当前隐藏误判为永远失效；原型运行时继续由 revealHint / reveal 按真实显隐条件决定是否操作。

`ProtoAnchors.setRevealNotes` 接收工作台 / 静态评审当前页状态的标注上下文。sharedReveal 在没有自身手动路径、显式容器关系或已记录条件时，按最近实际隐藏的容器筛选其他标注的手动路径，仅有唯一动作序列且入口可操作时提供自动共享；不同容器、路径冲突、失效来源不推断。推断只属于运行时，不产生跨标注持久引用或批量写入。revealHint 和 reveal 使用同一结果，标注层聚合数量；revealAndWait 按容器与步骤签名合并进行中的展开请求，并在完成后清理，避免两个标注连续点同一异步开关。

## 静态评审选中状态（2026-10-23）

评审壳与 `review-pins.js` 分别以 `selectedNoteId` 记录选择，`review-bridge.js` 通过来源受限的 selection / select 消息同步，init 和 reveal 一并传递选择。原型序号使用 `__review_selected` 和 `aria-current`，右栏使用 `selected` 和 `aria-current`；右栏重建从 ID 恢复样式，不依赖短暂 flash。页面 / 状态变化或标注移除时清除选择，PRD 开合与几何重排保留，不落盘。

`review-pins.js` 的 `pinsById` 按标注 ID 复用原型序号按钮，重排仅更新属性、坐标和当前正文回调，不清空图层或重新挂载已存在按钮，避免按下与松开之间断开节点导致 click 丢失。每次布局记录实际可见 ID，只移除隐藏、失效或离开当前状态的按钮并清理映射；重新显现时创建新按钮并恢复会话选择。

## 静态评审标注层的浮窗移动与显隐（2026-10-22）

`review_export.build_review_export` 对注入运行时之后的原型 HTML 字节计算 SHA-256，前 20 位写入产物清单 `prototypeVersions`。`review_shell.html` 的 `prototypeUrl` 为 iframe 和原型直达链接拼接同一个 `?v=<内容版本>`，旧清单无版本时沿用原地址；同文件状态切换继续用桥消息。哈希仅属于导出数据，不改变本地 bundle / revision，运行时代码变化也会生成新 iframe URL，避免 Pages / 浏览器命中旧内嵌脚本。

`src/review-pins.js` 随研发导出内嵌到原型副本。使用 MutationObserver 监听业务 DOM 的显隐、内容与状态变化，requestAnimationFrame 合并重排；自有样式、序号层、引导层和正文浮窗带 `data-prototype-owned`，不触发自身重建循环。滚动、尺寸、资源加载及过渡结束补充触发定位，不再序列化整页并比较 HTML 长度。

每次重排记录实际可见标注 ID，浮窗所属目标不再可见时清理浮窗及移动手势。移动握把由 window 指针监听与 pointer capture 共同接管，取消 / 失焦清理监听并恢复位置、光标和选择行为；位置仅属于当前阅读浮窗，不写回标注锚点或项目元数据。导出与发布每次读取最新脚本，服务无需重启，旧产物需重新生成。

## HTML 导入与统一页面入口（2026-10-21）

`proto-screenshot-editor.js` 共享页面设置窗口，统一入口通过原生 popover 菜单选择截图 / HTML，菜单按导航工具行对齐，支持方向键和 Esc。HTML 单文件或文件夹由 FileReader 读取，文件夹保留相对路径，过滤依赖、隐藏文件及非静态资源；多入口通过下拉选择，只有选定 HTML 随资源提交。

`html_import.py` 在 PROJECT_LOCK 内进行 revision、体积、文件路径和层级校验，原字节写入随机独立 `pages/html-<id>/` 后保存三文件元数据。`html-import.pending.json` 记录 before / after 和完整资源清单，失败清理本次文件，中断时阻止后续读取覆盖现场。普通元数据保存禁止修改资源所有权清单。

重新导入由 `/api/proto/replace-html` 调用 `replace_page`，与创建共用包校验和写入过程。复制当前页面记录，仅更新 file / url / htmlImport，保持页面 ID、状态及业务文档；旧登记文件的原字节写入 pending 的 `beforeFiles`，新资源路径与已有未登记文件冲突时提前拒绝。移除旧文件、写入新文件后提交元数据，异常恢复旧字节并移除新文件，只清理已知路径的空父目录，不递归删除页面目录。左侧设置按所选 pageId 打开共享替换窗口，保存成功通过原有导航刷新页面。

`htmlImport.directory/files` 随页面记录保留；通用回收站同时暂存 HTML 和专属资源，恢复保留资源，彻底删除提交后清理。纯净版 / 研发版共用资源复制与回收排除，`.htm` 也可作为唯一活动导出入口。不生成 PRD 或自动扩大交互提示范围。

## 截图页面（2026-10-20）

`screenshot_pages.py` 管理 `pages/shot-<id>.html` 与 `assets/prototype-screenshots/<pageId>/<sha256>.<ext>`。页面 kind:screenshot，元数据保存图片尺寸与归一化矩形。HTML 内嵌 `screenshot-runtime.js/css` 和便携配置，可离线显示、跳转，不依赖工作台，不生成 PRD。

专用写接口在 PROJECT_LOCK 下校验 revision、图片、目录、矩形、目标及层级；写 `screenshot-operation.pending.json` 后原子写入图片 / HTML，再提交三文件元数据。失败恢复原 HTML 并清理新资源；中断日志保留 before / after、原 HTML 与新增资源路径，后续读取拒绝覆盖现场。拒绝链接或目录联接路径。

`proto-screenshot-editor.js/css` 负责上传 / 粘贴、热区列表和草稿，未保存切页拦截，保存时冻结画布。运行时仅由工作台显式开启编辑，手动画出的矩形只在专用容器内放开尺寸限制。`ProtoAnchors.at` 将截图落点绑定图片，placement.rx / ry 保证移动 / 删除热区不影响序号。工作台与研发壳验证当前 iframe 的导航消息并按登记 ID 切页，纯净版 / 独立打开使用相对链接。

通用页面管理与回收站复用；永久删除同时暂存 HTML 与专属图片，提交后清理，清理失败不错误回滚。导出按当前登记重建截图页，失效跳转降为仅提示，回收图片排除。图片不参与静态文字修改，多图状态另行扩展。

## Pages 容量与发布管理（2026-10-20）

`github_pages.py` 通过注入 Session 读取仓库、Pages 源配置、固定 commit 的 tree 和 manifest，完整汇总发布源字节，并合并实际目录与清单。递归 tree 截断时逐层读取；Actions 最终产物未知时返回 null 余量，1 GB 只作参考，见 [Pages 限制](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)。

取消发布核对确认时的仓库与 expectedHead，基于 base_tree 创建删除目标文件及更新 manifest / index 的新 tree，提交以原 head 为 parent，再 force:false 更新分支并重新读取确认。依据 [Git trees API](https://docs.github.com/en/rest/git/trees) 与 [Git refs API](https://docs.github.com/en/rest/git/refs)。旧 ext / AI 入口共用，远端失败不清除本地发布状态，不重写历史或修改本地原型 / PRD。

目录 ID 限制单层，服务端构造目录 URL，浏览器再次校验协议；清单名称用 textContent 展示，公开总览转义文本与 URL。Token 不进入响应或导出。120 秒缓存按仓库及凭据摘要隔离，变更失效；overview 不持全局写锁，缓存使用独立锁。

`src/pages-manager.js` 复用菜单快捷入口与管理页控制器；菜单只渲染“发布管理 / Pages 总览”链接，不渲染容量、余量或刷新控件，工作台将入口挂在发布区标题右侧（2026-10-21）。管理页确认绑定仓库 / head，失败保留列表，成功使用服务端验证后的新数据；storage 通知其他窗口更新状态。`publish.html` 沿用首页浅深主题，确认框使用原生 dialog。

## 本地项目隐藏（2026-10-20）

`data/external.json.hiddenProjects` 独立保存首页隐藏状态，保留 projects 连接映射。`handle_external_list` 先按原协议读取登记项目与发现候选，再分为 items / discovered / hidden；隐藏记录不因停止监视或目录失效自动清除，新发现项目不初始化元数据。首页使用同一卡片和菜单渲染普通 / 隐藏视图，搜索和筛选共用，首页徽标只统计普通项目。

hide / restore 以及旧 remove 别名沿用本机来源和 JSON 校验。`external_library_entry` 只从登记、已保存的隐藏定位或实时监视扫描中解析项目，拒绝客户端任意路径。恢复已断开监视的新发现项只重新监视该项目根，保持未连接；隐藏候选的缩略图权限限于其已记录目录。

删除共用现有目录边界保护，扩展至发现与隐藏项目，核对可选 expectedRoot 并阻止父目录包含其他候选 / 隐藏项目时递归删除。成功后清理三类记录，失败保留登记与隐藏状态；不操作远端发布。

## 页面三级树（2026-10-15）

页面关系保存在 `project.pages[].parentId`，数组决定同级顺序；共用导航递归渲染和折叠子树，拖动提交完整移动请求，由工作台沿用 CAS 保存。跨端移动连同子树更新所属端，服务端 `validate_page_hierarchy` 校验父引用、端一致性、循环和三级上限。页面身份与 PRD 不随排序变化。

可移植清单以 `parentFile` 引用父文件，接入后转换为稳定 parentId。省略 parentFile 保留用户层级，空字符串显式解除；公共导航和评审导出通过 `navigation_pages` 跳过回收父级，保持可见后代。永久删除将直属子页面提升并同步清单，不连带删除子页面文件。

## 页面回收站（2026-10-15）

`page_lifecycle.py` 负责页面生命周期。软删除以页面 `trashedAt` 保存，不移动源文件或清除 PRD；导航、预览和导出使用活动页面集合。恢复清除标记并保留数组位置。永久删除在专用 CAS API 中确认文件名、校验目录边界与链接，清除该页关联数据并更新清单指纹，保留其他页面与共享资源。

永久删除先将 HTML 临时改名到 `.prototype/`，以 `page-operation.pending.json` 记录前后元数据、原文件定位与清单备份，再保存清单及三份元数据，成功后删除暂存文件。失败恢复源文件、清单和元数据；异常中断保留记录，后续读取拒绝静默重建。回收站文件及 PRD 不进入导出，生成的演示导航只含活动页；没有业务页时阻止导出，工作台空项目仍可进入回收站。

## 多端清单与共用导航（2026-10-14）

`prototype_manifest.py` 校验项目根 `prototype.manifest.json` 并将端、角色、预览类型和默认业务页合入已登记元数据；保留页面身份和 PRD。清单指纹避免重复应用，角色纠正通过现有 CAS 保存。

`agent-skills/prototype-flow/assets/project-navigation.css/js` 是导航组件的唯一维护来源：viewer 直接加载，研发导出内嵌，独立演示入口由模板生成并复制资源。页内 project-page.js 使用父窗口来源校验处理演示入口的状态切换；研发评审仍由 review-bridge 完成握手。

接入脚本读取清单与工具仓库，不依赖固定个人路径。外部复制 Prompt 和 AI IDE 项目包包含完整 skill；业务侧栏沿用产品设计。演示入口声明与多端分组属于项目结构，不参与视觉风格预设。

## 页面列表宽度（2026-10-21）

页面列表宽度由 `src/sidebar-resize.js` 与配套 CSS 管理，宿主提供展开状态、可用宽度和 CSS 变量写入。指针捕获和临时覆盖层处理 iframe 跨区拖动，取消恢复、键盘调整与 localStorage 共用；viewer 直接加载，review_export 将脚本和样式内嵌到独立评审壳。

## 首页升级（2026-10-10）

src/home-ui.js 管理共用卡片、视口观察、封面请求、操作 / 外观菜单与弹窗焦点；业务仍由 src/script.js 调用已有接口。src/home-theme.js 在首页与发布管理页的样式前加载，使用 prototype-home-theme 保存 system / light / dark 偏好，解析为 data-home-theme 的实际浅深色；监听 matchMedia 与 storage，事件通知菜单更新。DOM 文本用 textContent 写入；路径和名称不作为 HTML 片段。

home_thumbnails.py 使用两个后台线程分发独立渲染进程，队列上限 64；每个任务限时 28 秒。源文件路径、大小和修改时间参与指纹，缓存写入 data/home-thumbnails，固定卡片窗口不产生布局跳动。没有逐卡片的实时 iframe。

封面使用可选的 Playwright Chromium 和 Pillow。新上下文不携带浏览器账号状态，禁止业务 POST、外部请求、Service Worker、WebSocket 和 EventSource；只提供经 safe_asset 校验的本地资源与已归档的 Tailwind / Font Awesome。无法离线呈现的页面回退名称卡片。截图不会点击项目控件，也不写用户原型或 PRD。缓存只能经项目授权接口访问，静态服务拒绝缓存路径。

新增依赖缺失时保持项目文字卡片与原业务可用；当前 C:\python.exe 环境已完成离线渲染验证。首页自身继续使用本地预编译 CSS。

## 视觉配置解析（2026-10-05）

`design_settings.py` 是无服务副作用的视觉配置模块，读取风格资产的 Color 章节，按颜色角色解析主辅色、主题和组件语言，按文件修改时间缓存预设。语义文字与控件边界通过对比度选择；缺失主题角色继承 home 基线。`/api/design-systems` 返回预设和六角色色样。

`src/design-settings.js` 按同一版本 2 协议解析表单，色样、Prompt、请求和历史回填共用 `getEffectiveDesignSettings()`。Python / JS 的解析结果及覆盖规则文本由回归用例直接比对。后端在 AI 同步 / 异步生成、复制 Prompt 占位、外部项目包入口再次规范化配置。

`compose_generation_prompt()` 在风格资产后声明继承与主动覆盖；默认风格也注入默认规范。复制 Prompt 采用后端返回 `instruction`，保存同一 `prompt.txt`。项目包 `DESIGN.md` 将主动覆盖置于风格原始规范之上，字体、排版和组件语言继续继承；记录存最终值与显式覆盖，未改默认值不作为用户指令。

## 1. 系统架构

### PRD 工具栏与图片尺寸（2026-10-07 更新）

`proto-markdown.js` 负责会话和外侧悬浮工具栏：工具栏始终以 `position: fixed` 挂在所属文档根节点，不创建占位 slot，也不使用 `is-docked` 状态。浮窗定位以整个 `.pa-card` 外框计算上、下、左、右候选位置，间隔 12px。右侧 PRD 工具条以自然宽度保持单行，右端对齐当前正文或当前标注的 `.ext-note-head`，默认位于正文 / 序号栏上方，空间不足时向左延伸，不使用横向滚动；进入编辑时若靠近顶部，减少阅读区 scrollTop 露出工具条，不插入空白占位。`ResizeObserver` 跟踪卡片、编辑区和侧栏尺寸，触发重新摆位；编辑器 `resize` 桥接同步更新高度与工具栏坐标，覆盖图片载入和正文重排。手动拖动只改变悬浮坐标，不保留原位置高度；双击握把或按 Enter 恢复自动摆位，结束编辑清理工具栏和观察器。分组布局通过 CSS 适配可用宽度，三处编辑共用。

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

### 服务实例交接（2026-10-21）

`server_lifecycle.running_server` 对应用目录 + 端口持有短期系统文件锁，先尝试原独占绑定；占用时使用私有 `data/server-instance-<port>.json` 与 `/api/server-info` 的 service / root / instanceId 核对身份，再用每次启动随机生成的密钥调用本机交接接口。控制请求直接使用 loopback HTTP，不经过代理、不跟随重定向，不按 PID 或端口杀进程。无法识别、跨目录或旧版实例保持运行并报明原因。

交接接口尝试非阻塞获取 `REQUEST_LOCK`，检查异步生成任务；忙碌时返回 409，新实例轮询等候（最多 330 秒）。可退出时在锁内设置 restarting，再启动独立线程调用 HTTPServer.shutdown，后续业务请求返回 503。先关闭旧监听，再在启动锁内核对身份并清理记录，避免与新实例登记竞态。正常退出 / Ctrl+C 清理私有记录，系统锁随进程退出释放；失效记录不阻止空闲端口启动。私有记录和锁路径由 GET / HEAD 拦截，JSON 不输出密钥。

`启动项目.bat` 运行 `python server.py --open-browser`，服务绑定成功并登记后才打开当前端口的首页；正常交接退出不 pause，失败才保留窗口。直接运行 Python 复用相同生命周期，不依赖批处理脚本。

### 文案的手动微调（2026-10-20，10-21 补充动态标签）

`src/proto-text-edit.js` 由 Viewer 微调面板加载，收集选中元素的有意义文字节点、稳定 ID 与结构路径；通过独立 Text.nodeValue 实时预览，保存前不修改源文件。关闭、切换元素或切换到 AI 修改时还原未保存内容，异步检查使用会话序号和项目 / 页面 / 状态快照，避免旧结果写入新选择。

`server.py` 的三个 `/api/proto/text/*` 接口委托 `proto_text_edit.py`。标准库 HTMLParser 记录源代码文字区间，以唯一 data-proto-id / id 或严格结构路径匹配，核对运行时文字后从后向前替换区间，不把运行中的 DOM 序列化回源文件。图标、属性、脚本、原换行及 PRD 保留，框架指令 / 插值、歧义及运行时不一致直接拒绝。

`src/proto-text-runtime.js` 收集容器 + 控件稳定键或语义特征的绑定候选。静态匹配失败时，服务端对具备键 / 语义特征的动态节点开放修改，拒绝只有序号且缺少身份特征的动态节点。动态文案以 `before / after / binding` JSON 与独立内嵌脚本保存到 HTML 的 `proto-text-edits` 区块，避免解析 / 替换 JavaScript 共享数据而误改其他控件。当前 iframe 同步安装规则，MutationObserver 在脚本重建节点后按唯一绑定重新应用；只在文本仍等于原文或已保存文案时改 Text.nodeValue，保留原事件 / 图标，框架节点和新外部文案跳过。观察器自身写入期间断开，避免递归回调；导出携带内嵌运行代码，无本机依赖。

无显式键时使用语义绑定（10-21）：条目路径 `match` 由未包含所选文字的相邻内容组成（最多 3 个特征、每个最多 3 层路径），要求在同类兄弟中唯一；表格单元格 `column` 保存完整分组表头，布局网格处理 rowspan / colspan，按表头路径定位列。唯一短控件可用 `text` 原文匹配，无容器 ID 时使用唯一 body 锚点。源码缺失处必须具备键或语义特征，纯序号仍不作为动态对象身份；动态匹配歧义、目标被筛走或原文不匹配时跳过，不迁移到下一项。运行时 WeakMap 保存已改文字的原文，用于保持既有行 / 标题绑定；再次编辑优先复用已有规则的规范绑定。

`proto_text_edit.upgrade_runtime_html` 仅在 `/ext/` HTML 响应副本内替换合法手动文案区块的旧运行代码，使用当前工具的语义定位实现；源文件和 JSON 记录保持原样，解决既有页面继续调用旧脚本的问题。后续保存重建整个区块，使本地与导出运行代码一致。

手动修改使用独立源文件 SHA256 CAS，与 PRD revision 分离；在项目锁内检查，临时文件 fsync 后再次核对并原子替换。原字节及前后 hash 写入 `.prototype/text-edits/<ticket>.json`，撤销同时校验页面文件、票据及当前 hash；后续 Agent 编辑后不覆盖。记录沿用 `.prototype` 的发布排除规则。前端保留原 AI Prompt 路径，无法唯一识别、框架绑定 / 复杂内容使用 AI 修改。

### AI 与本地原型统一接入（2026-10-04）

AI 项目仍保留首页旧 ID、生成记录与协作归属。`POST /api/projects/workbench` 安全解析真实项目目录，幂等初始化或读取 `.prototype`，将旧 AI ID 映射到 `p-xxx` 登记 ID；旧 PRD 迁入页面需求时保留人工已有内容。`viewer.html?project=旧ID` 先解析，再复用 `initExternalMode`；本地 `?ext=p-xxx` 直接进入相同工作台。两者共用 iframe 锚点、PRD CAS 保存、元素修改 Prompt 与发布 / 导出管线。

多 HTML 项目以 `project.pages[].file` 导航；同一 HTML 中的旧 Vue / Router 页面映射为首页 adapter 状态，记录 `legacyPage`、`legacyType` 与可选路由路径。`src/proto-navigation.js` 连接现代 `PrototypeBridge` 与旧框架导航，在原型业务导航和 `data-proto-state` 之间同步状态，Viewer 与研发版评审壳共用适配模块，切换同文件状态不重载 iframe。

创建页三种生成入口统一提供稳定 `data-proto-id`、根元素页面 / 状态 / 预览类型与 `PrototypeBridge.enter(stateId)` 协议；`record.json` 中保存 `global.previewType`。Web / App / Pad 自动预览依次读取状态、页面、所属端、原型根元素 `data-proto-preview` 与项目元数据，最后用 DOM 特征兜底。Pad 使用固定逻辑画布与 ResizeObserver 适配缩放。真机外壳开关只切换容器样式与装饰显示，保留 iframe 文档、表单内容和业务状态，并跨工作台模式与页面沿用所选外壳状态。

AI「导出与分享」解析工作台 ID 后复用本地弹窗和 `/api/ext/export`、`/api/ext/publish`：`pure` 构建纯原型，`review` 构建只读评审壳与原型副本；共享版本选择，删除旧 AI 专属导出弹窗与内嵌入口。团队协作分享仍使用原归属与团队接口。

AI 导出复制成品与资源，排除根目录的生成记录、完整 Prompt、TASK / AGENTS / DESIGN 以及 `prd/`、`pages/*.md`；研发需求从共享元数据打包进评审壳。业务资源目录内的同名文件继续保留。AI 发布沿用原 AI 项目远端目录，发布 / 取消发布同步原生成记录；本地项目沿用原复制规则。

### 页面导航与状态同步
本机工作台与原型 iframe 同源，Viewer 通过 `PrototypeBridge.enter(stateId)` 切换同文件状态，并观察根元素 `data-proto-state`，同步导航和当前 PRD。已有作者 Bridge 保持原对象和实现，系统只为旧项目增加适配器。

`proto-navigation.js` 为旧项目连接 Vue 的全局 ref、Options data、Composition setup、组件 proxy 或 Router。启动时读取当前业务视图，避免把首页 PRD 错误归到 default；显式 default 恢复初始视图。同名业务页面按 slug 追加 `-2`、`-3`，分别保留需求。业务导航变化通过 Router 监听、hash 监听与适配器检查同步到根元素；跨 HTML 导航才加载新文档。

研发版导出将状态配置、导航适配器与锚点 / 评审脚本注入原型副本。评审壳通过 `postMessage` 与 iframe 通信，在 HTTP 与 `file://` 下使用相同的导航、标注和 PRD。

### 点击热区发现

提示范围来自页面状态 `interactionHints: {mode: "targets", protoIds: [...]}`，元数据空数组或缺省代表不提示，只有明确要求时使用 `{mode: "all"}`。PRD 草稿不从所有标注、可点击元素或稳定 ID 反推授权。导入省略热点字段表示保留既有范围，显式清单替换、[] / clear 清空，preserve 不制造 revision 变化；新一轮交互改造必须显式提交本期清单。静态导入检查节点唯一性、排除声明和后代控件，动态绑定只标记待验收；hintActions / hotspotChecks 形成更新与校验报告。评审壳通过 init 消息传递各状态配置，切状态读取对应范围。

`src/proto-hotspots.js` 提供 `ProtoHotspots.init / show / hide / destroy / inspect`，自身不自动启动提示 UI。文件服务只在 HTML 响应副本中提前载入模块，源文件保持原样；模块记录交互事件的实际绑定及移除，保留回调身份、this、去重、capture、once 和 AbortSignal，避免仅凭按钮标签、role 或 cursor 误判。React 根代理由元素 props 的实际业务回调识别；自定义祖先代理在实际操作节点显式声明 true，不猜测委托规则、不运行操作探测。无实际行为的普通按钮、空链接和占位链接排除。

逐次扫描以精确 ID 建立唯一目标表；重复 ID 不绘制。非原生控件若包含其他操作节点，判为容器而拒绝整块提示，不自动授权其后代。节点高度超过 96px 且原始面积超过 min(64000px², 视口面积的 12%) 时判为 oversized，避免用可见裁切把大容器伪装成按钮；低矮的整行控件仍可提示。inspect 复用绘制的判断，返回逐 ID 的原因与有效矩形，不点击、不改变配置、不创建高亮层。提示期间监听 stable ID、尺寸、可见性与类型变化，刷新已绘制目标。

Viewer 在同源 iframe 完成载入时幂等初始化，启用回调读取预览 / 标注、微调、点选与正文编辑状态；模式切换、新建标注和原型页面 / 状态变化清理提示。外部画布点击调用 iframe 的 show，拖动与控件操作排除。模块不修改业务元素，用 `data-prototype-owned` 的独立、无点击事件的层绘制半透明橙色热区；提示不带边框 / 外圈 / 阴影，透明度呼吸并按时清理。遮挡检测、祖先裁切及滚动 / 尺寸变化定位均在 iframe 内完成。

`proto-interactions.js / .css` 在父 viewer 提供手动编辑面板，纯 model 负责配置更新，点选器在 iframe window capture 阶段拦截点击，橙色选框为独立 owned 层。取消、pagehide、页面 / 状态和模式变化清理事件。保存捕获原始 scopeKey，通过 protoSave 的 CAS 修改对应状态；管理面板的 Backspace 不触发 PRD 删除。manualTargets 使用精确锚点，可授权事件代理控件；excludedTargets 作为持久排除覆盖基础清单，Agent replace 保留手动层。

手动展开路径写入标注 anchor.revealSteps，不与普通点击热点合并。ProtoAnchors.revealHint / revealAndWait 优先读取手动步骤，原生 select / 勾选赋目标值后派发 input / change，其他步骤点击真实入口；每个入口每次展开操作只执行一次，多级异步渲染共用既有等待机制。目标已可见时不再点击入口；已确认正文不修改，重新绑定锚点保留手动路径。评审壳直接携带相同 anchor 与状态配置，无需额外编辑器脚本。

编辑器的测试使用独立 extTestReveal → ProtoAnnotate.testReveal → revealThrough 路径，不经过 fromCanvas 的右栏定位分支。当前草稿步骤只以临时 anchor 传入，保留原始 PRD 与已保存路径；ProtoAnnotate 的 revealing 计数放行显现所需的合成点击。测试返回 ok / alreadyVisible / message，管理面板显示异步结果。仅有明确的 aria-controls 或 data-proto-reveal-by 祖先关联时，后续入口可见才代表外层已经展开；同级独立按钮可见不作为跳过依据。

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
