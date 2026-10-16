# 多端项目与统一演示导航

## 判断入口角色

用户明确多端混合，或原型包含不同角色 / 设备端时，先分析实际页面结构。只有主要展示演示目录、通过 iframe / 跳转加载其他可独立打开的业务文件的入口，才声明为 `launcher`。

登录、业务首页、后台工作台、包含业务视图的单文件 SPA 都是 `page`；文件名 `index.html`、出现侧栏、出现多个端，本身都不是隐藏入口的依据。判断不明确时保留 `page`，报告疑点。用户明确指定的角色优先。

演示目录必须用本 skill `assets/project-navigation.css` / `project-navigation.js`，不重新设计侧栏。组件提供端筛选、端分组折叠、选中态、页面状态、键盘导航及主题适配。业务侧栏、顶部菜单与 App 底部 Tab 遵循原产品设计。

## 接入清单

在项目根编写 `prototype.manifest.json`，只写公开的相对路径与页面信息，不包含账号、密钥、绝对路径或 PRD 正文：

```json
{
  "schemaVersion": 1,
  "clients": [
    {"id": "teacher-web", "title": "教师 Web", "previewType": "web"},
    {"id": "student-app", "title": "学生 App", "previewType": "mobile"},
    {"id": "student-pad", "title": "学生 Pad", "previewType": "pad"}
  ],
  "defaultPage": "teacher.html",
  "pages": [
    {"file": "index.html", "title": "演示入口", "role": "launcher"},
    {"file": "teacher.html", "title": "教师首页", "role": "page", "clientId": "teacher-web"},
    {"file": "app.html", "title": "学生首页", "role": "page", "clientId": "student-app",
     "states": [{"id": "default", "title": "首页"}, {"id": "detail", "title": "详情"}]}
  ]
}
```

替换为实际端与页面。`defaultPage` 是默认业务文件；每个文件只能登记一次，可放在 `teacher/`、`student/` 等项目内目录，清单使用相对路径。角色省略为 `page`，显示类型优先页面 `previewType`，然后所属端类型。`web` 为桌面、`mobile` 为手机、`pad` 为横向平板。Pad 以 1180 × 820 逻辑画布呈现，外壳随可用空间缩放，页面不要自行缩放业务字号；平台及演示入口可关闭外壳。至少保留一个业务页面。states 可省略；提供时与真实 PrototypeBridge 一致，新增状态会登记，已有状态 / 标注不删除。

## 接入与演示入口生成

先完成业务页面与入口 HTML；新建的演示入口可先复制本 skill `assets/launcher.html` 为 index.html，再执行：

```text
python "<skill目录>/scripts/connect_project.py" "<原型项目>" --tool-root "<工具仓库>" --dry-run
python "<skill目录>/scripts/connect_project.py" "<原型项目>" --tool-root "<工具仓库>" --build-launcher
```

工具仓库需要新版 `prototype_manifest.py`。这里 `--dry-run` 完全不写项目，与 `proto_import.py --dry-run` 的行为不同。正式接入读取清单、校验文件与端引用、登记页面角色 / 状态，保持既有页面和元素 ID。`--build-launcher` 仅重新生成明确声明为 launcher 的根 index.html，复制共用资源到 `assets/prototype-navigation/`，给业务页加入轻量父窗口状态通信脚本，不改业务交互。

单文件业务首页不要声明为 launcher，也不要用生成器覆盖它。清单同样可登记该业务首页与它的状态；演示入口生成参数对它不生效。

工作台默认直接加载业务页；旧壳页及其 PRD 在折叠“演示入口”中保留。页内 `data-proto-preview` 仍应准确填写；既有自带手机或平板边框的原型应在 `html[data-proto-host]` 时移除自身装饰外壳，让工作台 / 演示入口负责设备外观，保留业务内容。平板外壳不附加手机的灵动岛与状态栏，原型自己的平板状态栏可保留。

## 页面回收站

工作台导航只显示未设置 `trashedAt` 的页面，回收站入口支持恢复与彻底删除。移入回收站保留本地 HTML、原有页面位置、状态、PRD 和任务；不要因为文件仍在目录中就清除回收状态或重新登记。恢复需要用户明确要求，PRD 导入不会自动恢复页面。

页面生命周期统一调用 `POST /api/proto/page-lifecycle`，请求包含 `projectId`、`pageId`、最新 `expectedRevision` 和 `action: "trash" | "restore" | "delete"`。`delete` 仅允许回收站内的页面，还必须传 `confirmFile` 为该页当前相对文件名；只有用户明确要求彻底删除时才执行。永久删除移除该 HTML 文件及该页的 PRD、标注和任务，保留其他页面与共用资源，同时维护导航清单；不能通过普通 `/api/proto/save` 删除页面或修改 `trashedAt` 来替代。

回收站页面及其 PRD 不进入研发 / 纯净导出、Pages 或生成的演示导航。全部页面移除时项目允许为空；工具会为已经没有业务页面的导航清单设置 `allowEmpty: true`，这不是 Agent 将所有正常业务页归为 launcher 的依据。保留这类空项目及回收记录，不重建默认页面。

## 后续更新

增加页面或改变端划分后更新清单，再执行接入命令。工作台页面设置可修改名称、角色、所属端和 Web / App / Pad；名称只改变登记的 `page.title`，不改文件名、页面 ID 或 PRD 归属。同一清单不会反复覆盖手工纠正，清单内容变更时重新应用，Agent 更新清单前应读取并保留用户修改的名称。独立入口内容在再次运行 `--build-launcher` 后同步；下载纯净版会按当前登记结果重建明确声明的演示入口，研发版 / Pages 使用相同登记结果生成共用导航。

工作台允许新增端分类、整体排序端分组，并将页面组织为最多三级的树。端分组和页面状态不计入这三级。拖到页面中部成为子页面，拖到上 / 下边缘同级排序，拖到端标题或顶层页面边缘解除父级；整棵子树一起移动，跨端时所属端一起改变，页面自己的显示类型不变。禁止循环引用、将演示入口作为业务父级或超过三级。Alt + ↑ / ↓ 同级排序，Alt + → 移入前一个同级页面，Alt + ← 提升一级。

登记数据使用可选 `page.parentId` 指向父页面 ID，省略 / null / 空字符串表示顶层。同级顺序取 `project.pages` 数组顺序；父子页面必须在同一端，演示入口不嵌套。清单可用 `parentFile` 指向同一清单内的父页面相对文件名，支持向后引用；`parentFile: ""` 显式移回顶层。省略该字段会保留平台手动建立的结构；清单变更前应读取最新登记结果，避免旧 parentFile 覆盖用户整理。示例：`{"file":"detail.html","clientId":"web","parentFile":"orders.html"}`。

增量接入保留已有顺序和层级，将新页面和新端追加。平台新增分类带有 `userCreated: true`，清单暂未列出时仍保留。Agent 保留分类 ID、页面 ID、状态 ID、parentId、优先级与进度，不用重新生成 ID 的方式排序。工作台改变所属端时子树一起跟随；改为演示入口则解除自身与直属子页面的父子关系。回收父页面不连带回收子页面，子页面临时提升显示，恢复后还原；永久删除父页面将直属子页面接到原父级，保留子页面文件和数据。演示入口需重新生成才能反映最新整理结果，导出 / Pages 按当前树结构生成。

PRD 草稿继续用 `proto_import.py` 导入，不把它混入导航清单。导入会同时读取清单；没有清单的旧项目沿用原导航，不能仅凭猜测跳过 index.html。

页面管理标记保存在 `.prototype/project.json` 的页面对象中：可选 `priority` 为 1–6（1 最高），`progress` 为 0–100 的整数（100 已完成）。缺省 / null 是未标记，0 是明确未开始。平台可分别设置或清除；Agent 读写元数据和更新清单时保留既有值，不凭 PRD 内容自动改成已完成，也不以这些值重新排序。标记不属于导航清单的声明字段；需要由 Agent 修改时，先读取最新 bundle，再通过 `/api/proto/save` 的 expectedRevision CAS 保存。独立演示入口重新生成后和两种导出会显示这些标记。
