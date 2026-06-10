# 🎨 原型生成器 (Prototype Generator)

> AI 驱动的高保真原型设计工具 - 通过自然语言描述快速生成交互式 HTML 原型

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ 功能特性

- 🤖 **AI 生成原型** - 输入设计需求，AI 自动生成高保真 HTML 原型
- 🖼️ **参考图驱动** - 支持上传参考图，AI 会模仿布局和风格
- 🎞️ **HTML PPT 生成** - 支持导入 PPTX 美化或逐页描述生成，产物自带概览和全屏播放模式
- 🎨 **设计系统增强** - 内置中文化设计系统选择、色卡预览，并参考 OpenDesign 的 skills 及资产组织生成上下文
- 🚀 **外部 AI 生成** - 不调用内置大模型，支持一键复制完整 prompt，或生成 Cursor / Codex 可直接读取的 AI IDE 项目包
- 📋 **剪切板粘贴** - 直接 Ctrl+V 粘贴截图作为参考图
- 🔄 **异步生成** - 点击生成后立即在列表显示，后台完成后自动更新
- 🔀 **多模型切换** - 顶栏模型选择器，支持添加/编辑/删除多个 AI 模型配置
- 📝 **微调模式** - 可视化点选元素进行 AI 微调修改，支持整页面修改
- 📱 **真机外壳预览** - iPhone 写实外壳，含灵动岛、状态栏、物理按键，可开关
- 📄 **PRD 文档** - 内置 Markdown 编辑器撰写需求文档
- 👥 **团队协作** - 支持账号登录、创建/加入团队、邀请码邀请成员，并将个人项目分享给团队查看
- ☁️ **一键发布分享** - 支持发布到 GitHub Pages 并自动生成项目作品集主页，提供纯净预览、研发交付、内嵌等多种模式
- 📦 **项目导出** - 导出为独立 HTML，无需服务器即可运行

新增 HTML PPT 生成、设计系统和外部 AI 生成模式。外部 AI 生成可将结构化原型需求交给 Cursor、Codex 等 AI 编程工具继续生成和精修，减少额外大模型调用成本。

## 📋 系统要求

- **操作系统**: Windows 10/11, macOS, Linux
- **Python**: 3.8 或更高版本
- **浏览器**: Chrome, Edge, Firefox (推荐 Chrome)
- **网络**: 需要能访问 AI API 服务

## 🚀 快速开始

### 1. 安装 Python

#### Windows
1. 访问 [Python 官网](https://www.python.org/downloads/)
2. 下载 Python 3.8+ 安装包
3. 运行安装程序，**务必勾选 "Add Python to PATH"**
4. 打开命令提示符，验证安装：
   ```bash
   python --version
   ```

#### macOS
```bash
# 使用 Homebrew
brew install python@3.11
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip
```

---

### 2. 下载项目

```bash
git clone https://github.com/VampireQW/prototype-generator.git
cd prototype-generator
```

或直接下载 ZIP 并解压。

---

### 3. 安装依赖

```bash
pip install requests
```

> 💡 如果提示权限问题，可以使用 `pip install --user requests`

---

### 4. 启动项目

#### Windows
双击 `启动项目.bat`

#### macOS/Linux
```bash
python server.py
```

启动成功后，浏览器会自动打开 `http://localhost:8080`

---

### 5. 登录与团队协作

项目支持个人模式和团队协作模式：

1. 打开 `http://localhost:8080/src/login.html`
2. 注册或登录账号
3. 在右上角用户菜单中创建团队，或通过邀请码加入团队
4. 在「我的项目」中点击分享按钮，将项目分享给指定团队
5. 切换到「团队项目」即可查看团队成员共享的原型

> 首次启用团队协作时，会自动在 `data/collab.db` 初始化 SQLite 数据库。已有本地项目可通过 `python migrate.py <username>` 分配给指定账号。

---

### 6. 配置 AI 模型

启动项目后，直接在界面中完成模型配置，**无需手动编辑任何文件**：

1. 点击页面顶栏的 **模型选择器**
2. 点击 **「管理模型」** 按钮
3. 点击 **「添加模型」**，填写以下信息：
   - **模型名称**：自定义名称（如 "GPT-4o"）
   - **服务商**：选择或输入服务商名称
   - **模型标识**：填写模型 ID（如 `gpt-4o`）
   - **API 地址**：填写 base_url（参见下方服务商列表）
   - **API Key**：填写你的密钥
4. 保存后即可在顶栏下拉框中选择使用

> 💡 支持配置多个模型，随时在界面中切换、编辑或删除。

---

## 🔑 支持的 API 服务

本项目支持任何 **OpenAI 兼容** 的 API 服务。在界面的「管理模型」中填写对应的 API 地址和密钥即可。

### 服务商参考

| 服务商 | API 地址 (base_url) | 获取 API Key |
|--------|---------------------|--------------|
| OpenAI | `https://api.openai.com/v1` | [platform.openai.com](https://platform.openai.com/api-keys) |
| Claude | `https://api.anthropic.com/v1` | [console.anthropic.com](https://console.anthropic.com/) |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | [ai.google.dev](https://ai.google.dev/) |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | [阿里云控制台](https://dashscope.console.aliyun.com/) |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3` | [火山引擎控制台](https://console.volcengine.com/ark) |
| Kimi | `https://api.moonshot.cn/v1` | [platform.moonshot.cn](https://platform.moonshot.cn/) |
| 中转服务 | 按服务商提供的 URL | 按服务商说明 |

### 推荐模型

| 厂商 | 推荐模型 | 说明 |
|------|----------|------|
| OpenAI | `gpt-5.2`, `gpt-5.3-codex` | 最强综合能力，5.3-codex 专精代码 |
| Anthropic | `claude-opus-4.6`, `claude-sonnet-4.5` | Opus 旗舰推理，Sonnet 性价比高 |
| Google | `gemini-3-pro`, `gemini-3-flash` | 多模态最强，Flash 速度极快 |
| 字节豆包 | `doubao-2.0-pro`, `doubao-2.0-lite` | 万亿参数，多模态能力强 |
| 阿里千问 | `qwen3-max`, `qwen3-vl-max` | 旗舰推理模型，VL 多模态优秀 |
| Moonshot | `kimi-k2.5`, `kimi-k2.5-vision` | 原生多模态，视觉编程能力强 |

---

## 📁 目录结构

```
原型生成器/
├── server.py              # 后端服务 (Python)
├── db.py                  # 团队协作数据库层 (SQLite)
├── migrate.py             # 旧项目归属迁移脚本
├── config.json            # 服务器和 AI 参数配置
├── src/
│   ├── index.html         # 主界面（含模型管理）
│   ├── login.html         # 登录 / 注册页面
│   ├── script.js          # 前端逻辑
│   └── viewer.html        # 预览器/微调模式/真机外壳
├── projects/              # 生成的项目存放目录
├── docs/                  # 项目文档
├── design-systems/        # 中文化设计系统资产（DESIGN.md）
├── skills/                # 按产物类型拆分的生成 skills
├── craft/                 # 色彩、字体、反 AI 味等通用设计规范
├── templates/             # 页面模板
└── 启动项目.bat           # Windows 启动脚本
```

---

## 🎯 使用指南

### 生成原型

1. 先选择**产物类型**，再选择设计系统、背景模式、组件风格和主题色
2. 填写**页面名称**（如：登录页、首页）
3. 描述**布局结构**（如：顶部导航栏、左侧菜单、右侧内容区）
4. 上传**参考图**（可选，支持拖拽或 Ctrl+V 粘贴）
5. 点击 **AI 生成**（异步模式，项目立即出现在列表，后台完成后自动更新）

### 外部 AI 生成

当你希望用 Cursor、Codex、Claude Code 等 AI 编程工具直接生成或精修原型时，点击顶部 **外部 AI 生成**：

1. **仅复制完整prompt（1-2页面）**：适合少量页面，系统会创建待外部生成项目并复制完整 prompt，可直接粘贴到聊天式 AI 或 AI IDE。
2. **AI IDE 项目包（多页面）**：适合多页面、多参考图、需要持续迭代的原型，系统会生成 `AGENTS.md`、`TASK.md`、`DESIGN.md`、`pages/` 和 `reference/manifest.json`，并复制启动指令。

AI IDE 项目包会保留当前选择的设计系统、组件风格、背景模式、主题色、页面描述和参考图信息，方便外部 AI 工具按同一套设计约束生成 `index.html`。

### 生成 HTML PPT

切换产物类型为 **HTML PPT** 后支持两种方式：

1. **导入 PPT 美化**：上传 `.pptx` 后解析文字、页序和原始配图，配图会绑定回对应页面并参与生成。
2. **逐页描述生成**：为每一页分别填写布局/内容描述、动画要求，并可额外添加参考图。

HTML PPT 产物要求默认进入可概览的小图模式，点击页面或播放按钮后进入全屏播放；播放模式支持键盘、鼠标切页，并通过 `Esc` 或右键返回概览。

### 切换 AI 模型

1. 点击顶栏的**模型选择器**下拉框
2. 选择已配置的模型
3. 点击「管理模型」可**添加 / 编辑 / 删除**模型配置

### 微调模式

1. 在预览器中点击 **微调模式** 按钮
2. 点选或框选要修改的元素
3. 输入修改需求（如："把按钮改成蓝色"）
4. 点击 **应用修改**
5. 也可点击底部**「整页面」**按钮对整个页面提修改需求

### 团队协作

1. 进入登录页完成注册 / 登录
2. 在用户菜单中打开**团队管理**
3. 创建团队后复制邀请码给成员，或输入邀请码加入已有团队
4. 在「我的项目」列表点击**分享到团队**
5. 团队成员在「团队项目」中选择团队即可查看共享项目

### 部署到 Fly.io / Docker

项目新增 `Dockerfile`、`fly.toml` 和 `start.sh`，可直接部署到 Fly.io。部署时会将 `data`、`projects`、`deleted`、`uploads`、`backups` 链接到持久化卷，避免团队、项目和上传数据随容器重启丢失。

### GitHub Token 安全配置

GitHub 发布功能不再把 Token 写入 `config.json`。推荐在启动前设置环境变量：

```bash
PROTOTYPE_GITHUB_TOKEN=你的_GitHub_Token python server.py
```

也可以在界面里临时填写 Token；它只会保存到当前服务进程的环境变量中，重启后需要重新设置。

---

## ❓ 常见问题

### Q: 提示 "python 不是内部或外部命令"
**A:** Python 未添加到系统 PATH。请重新安装 Python，勾选 "Add Python to PATH"。

### Q: 提示 "No module named 'requests'"
**A:** 运行 `pip install requests` 安装依赖。

### Q: API 调用失败 / 超时
**A:** 
1. 点击顶栏模型选择器 → 管理模型，检查 API Key 和 API 地址是否正确
2. 检查网络是否能访问 API 服务
3. 尝试使用代理或中转服务

### Q: 端口 8080 被占用
**A:** 修改 `config.json` 中的 `port` 为其他端口（如 8888）。

---

## 📝 更新日志

查看 [docs/changelog.md](docs/changelog.md)

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)
