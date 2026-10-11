# 安装与使用 prototype-flow

仓库现在提供完整的 [prototype-flow 协作 skill](../agent-skills/prototype-flow/SKILL.md)，供本地 Codex、Claude Code 等 Agent 使用：

- 制作或接入带稳定元素 ID、页面 / 状态协议的 HTML 原型。
- 根据原型与已确认需求整理 Markdown 页面 PRD 和元素标注。
- 调用 `proto_import.py` 校验并导入草稿。
- 执行工作台复制的修改任务，保留标注并回写任务状态。

它不包含个人项目、账号或密钥，也不预设视觉风格。原型生成器的 `skills/` 用于“产物类型”；`agent-skills/` 提供给本地 Agent 安装，两者用途不同。

## 1. 安装 skill

下载或更新本仓库，把 **`agent-skills/prototype-flow/` 整个目录**复制到所用 Agent 的技能目录。不要只复制 `SKILL.md`，三个 `references/` 文件也要保留。

| Agent | 仅在目标项目中使用 | 当前用户的多个项目中使用 |
| --- | --- | --- |
| Codex | `<原型项目>/.agents/skills/prototype-flow/` | `~/.agents/skills/prototype-flow/` |
| Claude Code | `<原型项目>/.claude/skills/prototype-flow/` | `~/.claude/skills/prototype-flow/` |

`~` 是用户主目录。若已有同名 skill，先保留自己的修改，再替换或合并，避免同时加载多个不同版本。Codex 的目录规则见 [OpenAI 官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills)，Claude Code 的目录与调用规则见 [Claude Code 官方 Skills 文档](https://code.claude.com/docs/en/skills)。

启动或重新打开目标项目的 Agent 会话，确认能找到 `prototype-flow`。若暂时未被发现，可以直接让 Agent 读取本仓库 `agent-skills/prototype-flow/SKILL.md` 完成本次任务；直接读取不会自动安装 skill。

## 2. 提供工具与项目位置

告诉 Agent 两个目录：

- **工具仓库**：下载的原型生成器源码目录，包含 `proto_import.py` 和 `proto_meta.py`。
- **原型项目**：需要接入或写 PRD 的 HTML 项目根目录。

可以明确提供工具路径，或在启动 Agent 前设置自己的 `PROTOTYPE_GENERATOR_ROOT` 环境变量。它是本 skill 的路径约定，不需要填入 API Key 或 GitHub Token。只安装 skill 无法替代原型生成器源码和 Python 环境。

## 3. 让 Agent 接入并写 PRD

Codex 可明确引用 `$prototype-flow`；Claude Code 可使用 `/prototype-flow`。也可以直接描述任务，让支持自动匹配的 Agent 选择该 skill。

示例请求（将路径替换为你的目录）：

```text
使用 prototype-flow，把这个 HTML 原型接入原型生成器。
工具仓库：<工具仓库目录>
原型项目：<原型项目目录>
检查并补齐稳定 data-proto-id 和已有业务状态的登记。
根据原型、已确认需求和 .prototype/brief.md 整理页面 PRD 与元素标注，
写入 .prototype/prd.draft.json，然后调用 proto_import.py 正式落库。
不明确的业务规则列为待确认问题。
```

Agent 会读取对应协议，写草稿并执行：

```text
python "<工具仓库>/proto_import.py" "<原型项目>" --dry-run
python "<工具仓库>/proto_import.py" "<原型项目>"
```

`--dry-run` 不写 PRD 正文和标注，但可能创建元数据 / 登记新页面。正式导入有变更后，草稿归档到 `.prototype/imported/`；已有正文、重复标注与已确认内容按导入规则保留。具体格式和选项见 [PRD 协议](../agent-skills/prototype-flow/references/prd-import.md)。

## 4. 在工作台中查看

启动原型生成器，在首页“本地原型”中点击“添加本地项目”，选择这个原型目录。打开后即可查看页面需求与序号标注，继续编辑、微调和导出。

**落库与首页登记是两步**：导入脚本保存项目内 `.prototype/` 元数据，不会自动将目录写入首页列表。已添加过的项目刷新工作台即可。

本地 HTML 接入和 PRD 导入本身不需要第三方 AI API Key 或 GitHub Token；GitHub Pages 发布由用户在工作台另行配置、发起。
