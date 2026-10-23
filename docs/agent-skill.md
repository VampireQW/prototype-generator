# 安装与使用 prototype-flow

仓库现在提供完整的 [prototype-flow 协作 skill](../agent-skills/prototype-flow/SKILL.md)，供本地 Codex、Claude Code 等 Agent 使用：

- 制作或接入带稳定元素 ID、页面 / 状态协议的 HTML 原型。
- 根据原型与已确认需求整理 Markdown 页面 PRD 和元素标注。
- 调用 `proto_import.py` 校验并导入草稿。
- 执行工作台复制的修改任务，保留标注并回写任务状态。

它不包含个人项目、账号或密钥，也不预设视觉风格。原型生成器的 `skills/` 用于“产物类型”；`agent-skills/` 提供给本地 Agent 安装，两者用途不同。

## 1. 安装 skill

下载或更新本仓库，把 **`agent-skills/prototype-flow/` 整个目录**复制到所用 Agent 的技能目录。保留全部 `references/`、`assets/` 和 `scripts/`，不要只复制 `SKILL.md`。多端项目的新清单和迁移流程见 [多端接入与迁移](multi-client.md)。

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
仅整理本期实际改造，背景、目标和每条标注都关联本期需求，
引用需求原文并说明改造前后差异，用版本 3 的分条对象生成 Markdown，
写入 .prototype/prd.draft.json，然后调用 proto_import.py 正式落库。
可点击提示单独列出本次变化的具体控件，不提示原有重批、导出等功能。
完成后告诉我项目名称、页面名称，并给出可直接打开该页标注的链接。
不明确的业务规则列为待确认问题。
```

Agent 会先确认具体撰写清单，再按协议写草稿并执行。尚无已确认清单时，会展示“仅本次改动（推荐）／当前页面完整业务需求／自定义范围”，前两个选项分别简列实际业务项，同时说明排除项、背景目标及点击提示范围。用户已明确同一具体范围并要求落库时直接执行；范围扩大时仅补问变化部分。

```text
python "<工具仓库>/proto_import.py" "<原型项目>" --dry-run
python "<工具仓库>/proto_import.py" "<原型项目>"
```

`--dry-run` 不写 PRD 正文和标注，但可能创建元数据 / 登记新页面。正式导入有变更后，草稿归档到 `.prototype/imported/`；已有正文、重复标注与已确认内容按导入规则保留。具体格式和选项见 [PRD 协议](../agent-skills/prototype-flow/references/prd-import.md)。

## 4. 在工作台中查看

启动原型生成器，在首页“本地原型”中点击“添加本地项目”，选择这个原型目录。打开后即可查看页面需求与序号标注，继续编辑、微调和导出。

**落库与首页登记是两步**：导入脚本保存项目内 `.prototype/` 元数据，不会自动将目录写入首页列表。已添加过的项目刷新工作台即可。

本地 HTML 接入和 PRD 导入本身不需要第三方 AI API Key 或 GitHub Token；GitHub Pages 发布由用户在工作台另行配置、发起。

## 增量 PRD 与点击提示（2026-10-15）

更新工具仓库和完整 `prototype-flow` 文件夹，并让 Agent 在新会话读取新版入口。草稿已升级为版本 3，基于最新 revision 逐条关联本期需求，引用需求原文并说明 before / after；背景 / 目标用分条对象，标注用 items，由工具生成 Markdown，不接受旧版整段 body；复刻原有界面不自动生成整页标注。完整 PRD 与整页点击提示分别需要用户明确要求。

旧项目没有提示范围时默认不提示；新导入把本次范围写入状态 `interactionHints`。用户删除的标注保持删除，不重放旧草稿；范围、update / restore 与完整格式见 [PRD 协议](../agent-skills/prototype-flow/references/prd-import.md)。

## 结构化标注与完成回复（2026-10-16）

更新完整 skill 后，让 Agent 重新读取入口和 PRD 协议。页面需求默认省略，确有新增背景或目标再写；实现规则放到元素标注。标注由 AI 选择“页面显示 / 数据流转 / 业务规则 / 交互说明 / 异常情况”中适用的 Markdown 小节和列表，可仅写一项，不凑齐五项。导入工具会拒绝无结构正文；历史内容不会自动重排或覆盖。

hotspots 必须单独填写本次改变的具体交互 ID。只整理 PRD 时省略以保留原值，新页无提示；新一轮交互改造显式替换本期清单，无提示用 []。页面支持 hotspotAction: preserve / replace / clear。事件代理须在具体控件加 data-proto-hotspot="true"，不能把整张卡片或工具栏标 true；导入报告及运行时 ProtoHotspots.inspect() 用于验证控件粒度与漏项。落库成功后使用报告的 projectName、pages[].pageTitle 和 viewerUrl 回复项目 / 页面位置与点击链接。默认来源为 http://localhost:8080，工具运行在其他来源时传入 `--viewer-origin`。

## 本期内容逐条关联（2026-10-16）

更新后的草稿使用 schemaVersion 3；工作台元数据仍为 2。旧草稿须重新按本期范围组织，不能仅修改版本数字。每条需求以 sourceQuote 引用用户原文，增量需求填写 before / after；document.background / goals 的每条及 annotations.items 的每条分别绑定 requirementId。工具生成 Markdown 标题、空行和列表，页面外观与原有手工编辑方式不变。

“重新整理 / 重新落库”仍只针对本期，不补全整页。Agent 应先逐条排除旧功能：撤销本期改造后仍原样成立的描述不提交；容器标注不能夹带内部旧规则。明确要求清理已误写内容时，以 cleanupRequest 引用授权原文，使用 removals 点名未确认误注；修订用 update，背景 / 目标修订用 --replace-doc。确认保护、人工删除结果及无关历史内容保留。

当前仓库的 Qoder 技能副本与发布目录同步。让正在运行的 Agent 重新读取新版 SKILL.md 和 references/prd-import.md；只在对话中说“按新标准”不能保证它已读取最新文件。导入报告附本期需求、前后差异、contentRefs 和 removedAnnotations，Agent 复核后回复项目 / 页面直达链接。工具能验证格式与关联，语义范围仍由 Agent 根据真实本期需求判断。

## 落库前确认业务清单（2026-10-22）

范围确认是 Agent 的执行约束：等待真实用户选择，将清单与真实答复记入项目 brief；不使用自行填写的 confirmed 字段冒充用户确认。当前导入工具仍执行版本 3 的结构、引用、定位和历史保护校验，Agent 负责把 dry-run 的新增 / 更新 / 保留 / 拟删除项与清单逐条对照。完整业务需求按已选页面 / 状态和业务功能组织，不逐元素写标注，也不自动开启整页点击提示或删除历史 PRD。

功能改造涉及历史业务数据时，同一轮说明受影响记录、缺省值 / 旧状态 / 统计口径等变化，提供可行处理选项、推荐方案及依据，由用户选择；无影响或已有明确决定时不重复追问。确认后将有关规则写入适用标注小节并记入 brief，未决策略放 unknowns。历史业务数据与平台 PRD 历史分别处理，记录规则不代表授权实际迁移或修改业务库。
