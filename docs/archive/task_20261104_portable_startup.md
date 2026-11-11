# 全新拉取、首次启动与 Windows 编码兼容

日期：2026-11-04。用户反馈同事拉取 GitHub 代码后需要手动修复 UTF-8 相关问题，无原始报错，无法确认其具体触发点。

## 问题核查

- 扫描当时 Git 跟踪的 493 个文本文件，均为合法 UTF-8，75 个 Python 文件通过 AST 解析，没有发现源码整体编码损坏。
- 旧入口含 UTF-8 中文但没有统一 CMD / Python 输出编码；旧配置读取仅允许无 BOM UTF-8，UTF-8 BOM 与 UTF-16 均可复现失败。
- config.json / models.json 为应当忽略的个人文件；旧服务缺 config.json 就退出，启动脚本也不安装依赖。Docker 仅安装 requests，遗漏必须导入的 Pillow。

## 实现

Windows 入口改为 ASCII / CRLF，设置 UTF-8 并发现本机 Python。标准库 launcher 将依赖限制在项目 .venv，要求 Python 3.10+；首次 / requirements 变化执行 pip，正常复启跳过，失败可重试。--check 只检查并准备，--no-install 不创建环境或安装依赖。

app_runtime 初始化缺失的公开示例配置，保留已有文件；读取支持 UTF-8 / BOM、UTF-16 / UTF-32，配置错误不输出内容、不覆盖原文件。服务日志先于其他导入设置 UTF-8，GitHub 配置保存复用同一读取规则。增加 Git / EditorConfig 换行与编码约定、虚拟环境排除；Docker 使用完整 requirements。README、功能、架构、变更和回滚文档同步。

## 验证

- 新增启动 / 编码及 GitHub 配置回归：24 passed。覆盖缺失 / 已有配置、Unicode 编码、损坏 JSON 不覆盖、不泄露配置内容、ASCII 重定向、安装缓存、失败重试、离线、系统解释器不安装依赖。
- 整体隔离回归：759 passed、1 skipped、1 deselected（261.15 秒）。命令：`python -m pytest tests -q --ignore=tests/test_hotspots.py --ignore=tests/test_prd_editor_browser.py -k 'not point_clamps_into_clip_when_cut_side_unreachable_by_scroll'`。未重新执行依赖专用浏览器环境的两份脚本；保留原有一项已知几何用例排除。
- 两个含中文 / 空格的无配置、无 .venv 副本实际创建环境并安装 requests 2.32.5 / Pillow 12.2.0；首次 Windows BAT → py → launcher → venv 准备成功。从其他工作目录再次调用 BAT 成功，不重复运行 pip，不改既有配置。
- 干净副本 launcher 正常启动及直接 server 启动均通过；后者强制 ASCII 输出环境，使用 UTF-16 config / UTF-8 BOM models。首页、viewer、模型、GitHub 配置与本地项目列表五个接口均 200，无 Traceback / Unicode 编码错误；验证后按测试实例身份正常停止。
- 独立 Git 仓库设置 core.autocrlf=true 后实际 checkout-index，BAT 为 ASCII / CRLF，Python 与 shell 为 UTF-8 / LF。git diff --check 通过。实际运行系统为 Windows / Python 3.14；Pillow 安装元数据要求 >=3.10，但未在每个 Python / OS 上实际运行；本机没有 Docker，因此只校验其依赖配置，未构建镜像。
- 本机 config、models、项目索引、数据库、Token 五个文件哈希保持一致。运行中的真实服务于 11:40:59 收到既有页面的 publish-status 探测，刷新 external.json 发布状态；不是隔离用例改写，没有将旧登记表回滚覆盖。

测试日志、JUnit 与结构化证据在 tmp/portable-startup，临时复制的应用 / 虚拟环境验证后清理。真实项目、PRD 和远端仓库未因验证而改写或发布。备份位于 backups/20261104_portable_startup。
