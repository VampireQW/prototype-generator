# 手动文案与 Agent 后续修改冲突

## 复现及原因

用户提供截图：手动文案保存后，Agent 再改原型，重新打开时文案失效，选取控件报“页面文案与已保存的修改不一致，请重新加载后选择”。朋友的原项目文件未提供，复现在隔离动态控件中完成。

运行时为防止误覆盖，跳过既非原值、也非上次手改值的文案；后端却将同一情况永久拒绝。重载不会改变文件内的旧规则，所以不能解除阻塞。另外，动态控件静态化后，静态写入没有移除对应重放规则，将文案改回旧原值时可能被再次覆盖。

## 实现

- inspect 返回当前文案和新文件 hash；旧手动记录冲突时只提示，结构相同则提供 previousFields 供用户恢复预览。检查不写文件。
- 用户确认保存后以当前文案重建重放基线。expectedHash 校验、原子替换及撤销的 afterHash 保护继续生效。
- 静态保存只移除能按键、条目特征、表头唯一对应到该控件的重放规则。body 回退存在歧义时不清理。其他控件的规则保留。
- 编辑器提供“恢复上次手动文案”，只更改预览，保存后生效；取消和切换仍还原未保存内容。更新 viewer 的资源版本。

## 验证与对抗性自审

新增测试先复现旧错误，再修复；补充动态控件静态化后旧规则覆盖新保存的失败用例并修复。自审重点检查误删其他控件规则、同名条目、分组表头、文字片段数变化、旧 hash 保存及撤销覆盖后续 Agent 改动。

最终命令：`python -m pytest -q --tb=short --basetemp=<仓库内隔离目录> tests/test_text_edit.py tests/test_text_editor_ui.py tests/test_text_runtime.py tests/test_text_edit_browser.py tests/test_review_export.py tests/test_publication_versions.py`，结果 **85 passed**。

真实 Chromium 使用编辑器及 HTTP 接口完成手动保存、无关 Agent 改动后重载、同处文案变动后恢复 / 取消、继续修改、重绘、原点击事件及同名控件核对；纯净版和研发版均通过 file:// 加载。截图在 `tmp/text-rebase-final-cccce532a2b8415d88b54f7956d6637d/test_manual_agent_reload_recov0/text-rebase-recovered.png`。

验证未调用 AI 或 GitHub，未改写用户项目。朋友的原项目仍需使用新版复测；若外部工具删除了控件身份或整段手动记录，无法凭现有规则自动恢复。后端改动需重启生成器加载。
