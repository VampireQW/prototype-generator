# 多端项目与 AI 工具迁移

## 本次能力

一个项目可登记多个端，每页携带所属端、Web / App / Pad 类型和 `page` / `launcher` 角色。工作台默认直开业务页，以平台左侧导航切换；明确声明的演示入口及已有标注保留在折叠分组。Pad 使用 `previewType: "pad"` 和 `data-proto-preview="pad"`，以横向平板画布呈现；外壳可关闭，预览、独立入口与导出都按可用空间缩放。

`index.html` 不会因文件名、多端或出现侧栏被自动隐藏。只有 Agent 判断它主要是演示目录并加载独立业务页面后，才在清单中声明 `launcher`；真实业务首页声明 `page`，模糊情况保留业务页并报告疑点。

## 需要迁移的文件

### 提供给其他 AI 工具

复制 **`agent-skills/prototype-flow/` 整个目录**，包含：

| 目录 / 文件 | 用途 |
| --- | --- |
| `SKILL.md` | 触发与工作流程 |
| `references/multi-client.md` | 判断条件、清单格式、接入命令和兼容约定 |
| 其他 `references/` | 页面状态、PRD 草稿、修改任务协议 |
| `assets/` | 与工作台共用的导航 CSS / JS、入口模板、页内状态通信 |
| `scripts/connect_project.py` | 校验清单、登记元数据、生成明确声明的演示入口 |

不要只复制 SKILL.md。Codex / Claude Code 技能目录见 [安装指南](agent-skill.md)；Qoder 等工具按自身技能发现规则安装，或直接让工具读取这个 SKILL.md。文件存在并不代表当前工具已经自动加载。

### 原型生成器本身也要更新

接入脚本需要新版工具仓库，其中包括 `prototype_manifest.py`、更新后的 `proto_meta.py`、viewer、导出构建与配套导航资源。只更新 AI 工具中的 skill，旧平台不会识别新清单。

两条“外部 AI 生成”路径已提供新版 skill：复制 Prompt 的占位项目和 AI IDE 项目包都包含 `agent-skills/prototype-flow/`；工程包 AGENTS.md 指向新版约定。内置 API 的单文件输出保留业务入口，混合端 / 演示导航请求提供共用组件源码。

## 新项目流程

1. Agent 制作业务页面，保持稳定 `data-proto-id` 和真实状态桥。
2. 根据实际功能判断入口角色，在项目根写 `prototype.manifest.json`。
3. 运行 skill 脚本，明确提供原型目录和工具仓库；需要独立演示目录时生成入口：

   ```text
   python "<skill目录>/scripts/connect_project.py" "<原型项目>" --tool-root "<工具仓库>" --dry-run
   python "<skill目录>/scripts/connect_project.py" "<原型项目>" --tool-root "<工具仓库>" --build-launcher
   ```

4. Agent 写 `.prototype/prd.draft.json`，调用 `proto_import.py` 导入 PRD。
5. 在首页添加本地项目。登记清单或导入 PRD 不会自动新增首页目录。

清单格式见 [多端协议](../agent-skills/prototype-flow/references/multi-client.md)。`connect_project.py --dry-run` 完全只校验；`proto_import.py --dry-run` 可能建立元数据 / 补登记页面，两者行为不同。

页面可以按端放在 `teacher/`、`student/` 等目录，清单使用项目内相对路径；平台会登记清单中明确列出的文件。生成入口前检查输出路径和业务文件，执行结果中的 `modifiedFiles` 列出入口、导航资源以及补充同步脚本的业务页面。

## 旧项目迁移

先备份入口、页面和三份元数据。保留现有页面 ID、状态 ID、元素 ID 以及 PRD，新增清单后接入；不要为端分组重命名页面 ID，也不要把旧壳标注自动搬到业务页。

有自带手机外观的页面，应通过 `html[data-proto-host]` 样式移除嵌入场景中的装饰外壳。独立打开保留其原外观，工作台 / 演示入口提供设备框。

工作台每页的设置按钮支持纠正角色、所属端和显示类型。相同清单重复读取不会覆盖手工纠正；清单变更后重新应用。独立入口在再次生成后同步；纯净版导出会按当前登记结果重建已声明的演示壳，研发版 / Pages 用共用组件呈现同一份登记导航。

页面设置在编辑按钮右侧展开，可新增端分类后一起保存。页面可在所属端内拖拽排序，端标题可整体排序，支持 Alt + ↑ / ↓；取消拖动或保存失败不改变登记顺序。顺序保存在 `project.pages` 与 `project.clients` 数组中，端增量接入会保留既有顺序及平台新增的 `userCreated` 分类。Agent 增量维护时保持这些数组顺序，不为排序重建 ID。

## 调用示例

```text
请读取 prototype-flow/SKILL.md，尤其是 references/multi-client.md。
工具仓库：<新版原型生成器目录>
原型项目：<当前原型目录>
判断哪些是业务页面、哪些是演示入口，整理端与页面清单。
演示导航使用 skill 配套组件，业务菜单保持原设计。
保留既有页面与元素 ID，校验并接入，必要时生成独立演示入口。
随后整理 PRD 草稿并导入，缺少依据的业务规则列为待确认。
```
