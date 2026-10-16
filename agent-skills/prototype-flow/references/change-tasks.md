# 修改任务协议

适用于用户提供工作台复制的修改 Prompt，或明确指定 `.prototype/changes.json` 中的任务。微调模式也能复制元素修改 Prompt；它不一定对应已经登记的任务，不能凭空创建任务 ID。

## 定位与修改

1. 读取原型项目的相关源文件、`.prototype/brief.md`，用工具仓库的 `proto_meta.load_bundle` 读取项目元数据。如果 Prompt 给出了基准 revision，必须与当前值一致；不一致时报告差异并让用户取得当前任务，不用旧 Prompt 覆盖新数据。
2. 以指定文件、pageId / stateId 为范围，依次通过 `protoId`、selector（结合 tag / text 验证）、唯一可见文本定位。找不到或命中不唯一时报告，不修改形似的其他元素。
3. 完成用户要求的源文件修改，保留稳定 `data-proto-id`、页面与状态约定。若本次需求明确新增页面 / 状态，再按接入约定登记。
4. 检查实际受影响的交互。不得把项目的导出目录当作原始源码修改，不覆盖人工确认的 PRD。
5. 需要同步 PRD 或点击提示时读取 `prd-import.md`，默认只提交本次实际变更范围；已有界面的交互不自动变成本期需求，用户删除的标注不补回。位置与样式修改不得扩展成整页功能说明。背景 / 目标也只写本期改造，每条标注逐项核对：撤销本期改造后仍原样成立的规则不提交。重新整理既有 PRD 时使用版本 3 的 items、update 及明确授权的 removals，不用重复 create 冒充改写，不清空历史或重置确认状态。

## 已登记任务的回写

任务在 bundle 的 `changes.items` 中，可能关联 `source: "annotation"`。只有确实存在且属于本次请求的任务，才在完成源文件修改后改为 `status: "applied"`，并用 `proto_meta.now_iso()` 更新 `updatedAt`。

保存前重新读取最新 bundle，核对 revision 与执行时的基准一致。使用 `proto_meta.save_bundle` 写入，bundle 的 revision 增加一次，三份 JSON 的 revision / projectId 由工具统一维护。不要逐个手改文件，也不要声称 `save_bundle` 本身实现了跨进程 CAS；保存期间避免同时在工作台编辑同一项目。

用户验证后由工作台将任务改为 `verified`；Agent 不替用户验证。若只是微调 Prompt 且没有任务 ID，完成源文件修改并回报即可，不伪造任务，也不为此改动 PRD revision。

## 回报

说明实际修改的文件、交互与验证结果；有登记任务时带上对应任务 ID 和新 revision，提示用户在工作台验证。源文件已改但元数据发生冲突时，分别报告两个结果，不宣称整个任务已经同步成功。
