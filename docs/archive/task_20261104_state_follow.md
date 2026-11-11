# 页内交互自动跟随左侧状态

日期：2026-11-04。用户要求通用支持，并指定 p-0f9a831e16df569b（电子作业本-左侧目录）直接调整后验收。

## 原因与实现

指定项目的 setDir 只改变目录显隐，data-proto-state 只在外部桥 enter 中更新；初始化还把恢复的实际收起状态强制标为 default。修改前两页在真实浏览器均复现：目录已收起但状态仍为 default。

工作台原有属性观察可更新导航和 PRD。本轮完善为通用接入：proto-navigation 支持可选的同步 getState()，读取已登记的真实状态，保持原桥与 enter，不猜测业务。交互事件及 100ms 读取处理异步变化；异常 / 未登记 / Promise 忽略，重初始化清理旧监听。工作台与研发导出共同接入，宿主观察额外校验登记 ID；发布运行时指纹覆盖该组件。

项目两页在统一 setDir 中同步属性，新增真实 getter，初始化尊重已有记忆，enter 拒绝未知 ID。页面 / 状态身份、布局、PRD、标注和人工删除记录未迁移；brief 与两份 skill 接入协议同步。

## 验证

- 新增三个回归先失败，再通过：getter 同步与已知状态限制 / 清理、现代多状态页研发注入、运行时发布指纹。
- 强化现有宿主观察用例：旧范围草稿先保留，导航随状态更新，同状态不重绘，未知状态不切换。
- 相关回归 175 passed、1 deselected；完整非专用浏览器回归 762 passed、1 skipped、1 deselected，276.28 秒。沿用 tests/test_hotspots.py、tests/test_prd_editor_browser.py 专用浏览器范围及一个既有几何用例排除，本轮所需浏览器场景另行实际验证。
- 隔离副本：班级 / 学生两页的收起展开、快捷键、左侧主动进入、PRD / 链接同步通过；另设 getter-only 异步页面验证不依赖原型主动写属性。研发 HTTP 和 file:// 同样跟随，无浏览器脚本错误。
- 直接访问真实 localhost 服务及实际项目，两页原生按钮激活后均自动同步选中态 / PRD / URL，实际三份元数据 SHA-256 不变。班级页在标注模式验证，学生页在预览模式避开原有序号对按钮的覆盖；独立页面另验证两页的鼠标开关、恢复记忆与刷新。
- 用户 Chrome 的自动化标签未完成预览加载，原因未确认，未将该尝试计为通过；最终实际服务验收使用独立浏览器正常完成，临时标签关闭。实际服务按身份验证机制从旧实例交接到新代码，未按端口查杀或发布远端测试内容。

JUnit 与结构化报告：tmp/state-follow/results.xml、acceptance-result.json、live-result.json。真实项目效果图：live-home-collapsed.png、live-student-collapsed.png。备份与回滚见 docs/backup_log.md。
