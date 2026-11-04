# 遗留入口清理与整体功能验证

日期：2026-11-03。依据：用户确认按本地审计建议执行清理，并要求验证整体功能。

## 实施范围

- 归档并移除 16 个旧源码 / 入口：墨刀拆分、旧 CLI 导出、手动恢复、失效导航注入、旧 standalone、两个定制批处理、重复 PowerShell 启动、两个旧模板、旧工作流及两种旧打包脚本。
- 清理旧根 dist、分享版目录 / zip、过期 pytest 与探针文件、Python 缓存。保留根 tmp 下历史证明图片与日志，避免删除仍在使用的输出句柄及已交付图片。
- exports 的 83 个文件、tomodao 的 93 个文件先归档、逐条回读验证长度和 SHA-256 后再移出原目录。exports 空目录继续保留供兼容导出 API 使用。
- 保留源项目、项目回收站、data、模型与凭据、历史备份、Codex 辅助程序、现代运行模块和 vendor dist。

## 归档与回滚

本地归档目录：`backups/20261103_legacy_cleanup/`。

- `retired-source.zip`：16 个退役文件，原始相对路径保留。
- `historical-exports.zip`、`historical-tomodao.zip`：176 个历史交付文件；对应 manifest 保存校验信息。
- `working-tree/`、`pre-cleanup-working-tree.patch`：清理前已有修复和本次将更新文档的快照。
- `protected-files.json`：原项目、回收站、配置、登记与凭据的只读指纹，用于验证清理没有改动用户数据。
- `plan.json`、`cleanup-result.json`：范围及实际处理明细。

## 执行与验证

初次执行移除了 336 个文件 / 目录目标；16 个退役文件均已验证不再位于原路径，旧根 dist、分享目录 / zip 和 tomodao 均已移出，exports 保留空目录。39 个旧 pytest 目录的读取、删除、移动及针对单目录的权限修复均被 Windows 拒绝，保留原状，未扩大权限操作范围。

本轮生成的完整 pytest 数据与隔离应用副本已清理，临时服务已通过身份验证后正常关闭；真实 8080 服务继续运行。按可读文件统计，扣除新增归档与验证资料后，净释放约 **441.61 MiB**；受限目录未计入占用，数据为近似统计。

### 自动回归

```text
python -m pytest tests -q
  --ignore=tests/test_hotspots.py
  --ignore=tests/test_prd_editor_browser.py
  -k "not point_clamps_into_clip_when_cut_side_unreachable_by_scroll"
  --basetemp=tmp/cleanup-20261103/pytest
  --junitxml=tmp/cleanup-20261103/pytest-results.xml --tb=short
```

结果：**699 passed、1 skipped、1 deselected**，耗时 202.90 秒。跳过项为当前环境不支持符号链接的页面生命周期用例。两个直接启动 Playwright 的浏览器测试模块及一个浏览器裁剪用例未通过 pytest 执行，浏览器交互改用当前受控 Chrome 单独核对，因此不将结果描述为全部浏览器测试通过。

覆盖包含：本地 / AI 工作台、页面与层级管理、HTML / 截图导入及替换、标注 / 锚点 / 展开路径、Markdown 与媒体、手动文案修改、项目改名 / 隐藏 / 回收、生成资料和视觉设置、纯净 / 研发导出、发布与取消发布、GitHub 连接与配置、首页主题、启动实例交接等。AI 和 GitHub 请求使用隔离测试，不触发真实生成或远端发布。

### 浏览器与真实接口

使用清理后的源码及静态资产创建独立本地测试站，未复制真实模型、凭据或用户项目。实际核对：

- 首页卡片打开工作台；设备无关加载状态完成后展示原型。
- 原型按钮点击正常；弹窗显示时出现相应标注，关闭后标注恢复正确显隐。
- 右栏 Markdown 正文实际编辑、保存，并在重新读取元数据和导出包时确认内容已落盘。
- 使用界面支持的源码粘贴导入 HTML，新增页面出现在导航和实际研发导出中。
- 实际纯净 / 研发下载接口均返回可校验的 ZIP；研发包包含 3 个页面与修改后的 PRD，纯净包排除评审壳和内部元数据。
- 实际打开研发导出页面，序号单击后对应 PRD 行呈 `selected` 高亮，导入页面可以在研发版导航中打开。
- 真实 8080 服务的编辑器 vendor dist、标注、导航、生成 skill 等关键资源均返回有效内容。

Chrome 扩展未启用本地文件 URL 访问权限，文件选择器设置文件被阻止；该条浏览器上传路径未完成，改用产品支持的 HTML 源码粘贴路径验证。文件上传 / 截图导入的隔离接口回归通过，未为测试更改用户扩展权限。

证明截图：`tmp/cleanup-20261103/review-smoke.png`。结构化结果和 JUnit 保留于本轮 tmp 目录；关键验证摘要另存 `backups/20261103_legacy_cleanup/verification-result.json`。

### 完整性与最终状态

- 768 个原项目、回收站、配置、登记及凭据文件在清理前后 SHA-256 一致。
- 此前加载过渡、发布时间修复及对应回归的 10 个运行 / 测试文件与清理前快照逐字节一致。
- 旧运行入口引用搜索无残留；`git diff --check` 通过。
- 当前未发现由本次清理造成的功能回归；39 个权限受限历史临时目录为已知未清理项。
