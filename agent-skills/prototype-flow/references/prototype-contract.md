# 原型接入约定

多端混合或需要演示目录时，先读 [多端与共用导航](multi-client.md)，明确入口角色，使用接入清单与配套组件；不要仅凭 index 文件名或左侧菜单猜测演示壳。

## 页面与稳定身份

新建静态 HTML 原型时提供 `index.html` 入口，子页面和资源按项目约定组织；修改已有原型时沿用其入口与目录。供本地预览和交付使用的资源优先放在项目内。

页面声明示例：

```html
<html lang="zh-CN" data-proto-page="home" data-proto-state="default" data-proto-preview="mobile">
```

`data-proto-preview` 使用 `mobile`（手机）、`web`（桌面）或 `pad`（平板），与实际端类型一致。工作台登记时按 HTML 文件名推导页面 ID：去扩展名、转小写、保留中文、连续符号合并为 `-`；`index.html` / `主页.html` 对应 `home`。不同文件重名时追加后缀。已有 `.prototype/project.json` 时，以它的 `pages[].id` / `file` 为准，不以预览 URL 或猜测的文件名作为身份。

在需要标注或点名修改的按钮、导航、表单、卡片、表格等元素添加稳定 `data-proto-id`，例如 `btn-create`。同一 HTML 文件内唯一，跨文件可以重复；同文件不同状态的不同元素仍不能使用重复 ID。已有 ID 在修改时保留，避免标注失锚。

稳定 ID 与真实交互只用于定位，不代表它属于本轮需求。PRD 与可点击提示按 `prd-import.md` 的本次范围落库；没有声明的旧项目不会全页提示。若只还原旧系统页面，不为每个已有交互自动生成标注。容器可承载整体显示的标注，点击提示必须在 hotspots 中单独列出具体控件 ID，不会扩散到容器内部旧功能。

## 同文件的多个业务状态

底部 Tab、分段或详情视图若共用一个 HTML，分别使用明确的 stateId。提供 `window.PrototypeBridge.enter(stateId)`，让工作台能主动切入目标状态；原型自己的导航也调用同一切换方法，并同步 `document.documentElement.dataset.protoState`。

简化示例（`default` 为初始列表，`detail` 为详情）：

```html
<button data-proto-id="btn-detail" data-enter-state="detail">查看详情</button>
<section data-state-visible="default">列表</section>
<section data-state-visible="detail" hidden>详情</section>
<script>
  const states = new Set(['default', 'detail']);
  function enter(stateId) {
    if (!states.has(stateId)) throw new Error('未知页面状态');
    document.querySelectorAll('[data-state-visible]').forEach(element => {
      element.hidden = !element.dataset.stateVisible.split(',').includes(stateId);
    });
    document.documentElement.dataset.protoState = stateId;
  }
  window.PrototypeBridge = { enter };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-enter-state]');
    if (trigger) enter(trigger.dataset.enterState);
  });
  enter('default');
</script>
```

`enter` 应可重复调用；异步切换返回 Promise，在界面完成后更新 `data-proto-state`。工作台按该属性决定当前 PRD 范围，只改变 DOM 可见性会导致标注存入错误状态。

### 登记页面与状态

本地项目不会仅凭 DOM 中的新 stateId 自动登记状态。保存该状态的标注前，先通过 `proto_meta` 登记；以实际已实现的状态为准。

以下 Python 示例在**工具仓库目录**执行，把示例路径、文件和状态替换为项目实际值：

```python
from pathlib import Path
import proto_meta

root = Path("<原型项目>").resolve()
bundle = proto_meta.ensure_bundle(root)
proto_meta.ensure_pages_registered(root, bundle)
base_revision = bundle["revision"]
page = next(p for p in bundle["project"]["pages"] if p["file"] == "index.html")

if not any(s["id"] == "detail" for s in page["states"]):
    page["states"].append({"id": "detail", "title": "详情", "kind": "adapter"})
    if proto_meta.load_bundle(root)["revision"] != base_revision:
        raise RuntimeError("元数据已更新，请重新读取后再登记")
    bundle["revision"] += 1
    proto_meta.save_bundle(root, bundle)
```

`save_bundle` 负责校验和三文件保存。它不是跨进程的版本锁；执行这类脚本期间避免同时在工作台编辑同一项目。版本变化、读取失败或 `.pending-write.json` 出现时停下并报告，不删除恢复备份。

## 条件显现元素

原生 / ARIA 下拉、勾选、Tab、开关和折叠控件尽量使用相应语义。自定义控件的目标若需某项操作才能显现，可在目标或祖先声明：

```html
<section data-proto-id="detail-panel"
         data-proto-reveal-by="#detail-toggle"
         data-proto-reveal-value="detail"
         data-proto-reveal-label="查看详情">
```

触发器须实际存在、可重复执行；显现条件不能依赖提交、删除或支付等业务动作。导入时隐藏的元素可能暂时失锚，应先切入相应状态，必要时在工作台重新绑定。

隐藏标注必须具备可验证的显现路径。自定义 Tab、分组子视图等不能只写一句“默认隐藏，点击设置打开”；应在隐藏区域及必要的外层区域分别声明 `data-proto-reveal-by`，选择器准确指向执行展开的控件自身，不能指向同时包含开关、清空或提交功能的整块工具栏。例如：

```html
<div data-proto-id="tab-config" onclick="showConfig()">配置</div>
<section data-proto-id="config-pane"
         data-proto-reveal-by='[data-proto-id="tab-config"]'
         data-proto-reveal-label="切换到配置">
  <span data-proto-id="open-group" onclick="openGroup()">设置分组</span>
  <div data-proto-id="group-panel" data-proto-branch="true"
       data-proto-reveal-by='[data-proto-id="open-group"]'
       data-proto-reveal-label="打开设置分组">分组子视图</div>
</section>
```

平台在目标仍存在于 DOM 时直接读取自身和祖先的声明，旧锚点没有 conditions 也能显示引导；先指向当前可见的外层入口，再接力内层。点击右侧序号会自动完成整条路径，等待异步渲染后滚动定位，不重复点击触发器。分组子视图等独立分支可声明 `data-proto-branch="true"`，使其序号与主页面分开排序。入口必须唯一、可用，只执行显示 / 切换，不代用户确认、保存或清空业务数据。目标被条件卸载时仍需锚点记录的条件路径，不能靠按钮文案猜测；先展开核对并重新绑定。完成后验收默认隐藏时有引导、点右侧序号可显现、收起后引导恢复，PRD 正文保持本期范围。

## 加入首页

启动原型生成器，在首页“本地原型”中点击“添加本地项目”，选择原型目录。打开后核对页面 / 状态、预览类型与元素定位。`.prototype/` 元数据的建立不等于首页目录登记；不要自行改写账号数据库或 `data/external.json`。
