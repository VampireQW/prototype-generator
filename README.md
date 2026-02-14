# 🎨 原型生成器 (Prototype Generator)

> AI 驱动的高保真原型设计工具 - 通过自然语言描述快速生成交互式 HTML 原型

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ 功能特性

- 🤖 **AI 生成原型** - 输入设计需求，AI 自动生成高保真 HTML 原型
- 🖼️ **参考图驱动** - 支持上传参考图，AI 会模仿布局和风格
- 📋 **剪切板粘贴** - 直接 Ctrl+V 粘贴截图作为参考图
- 🔄 **异步生成** - 点击生成后立即在列表显示，后台完成后自动更新
- 🔀 **多模型切换** - 顶栏模型选择器，支持添加/编辑/删除多个 AI 模型配置
- 📝 **微调模式** - 可视化点选元素进行 AI 微调修改，支持整页面修改
- 📱 **真机外壳预览** - iPhone 写实外壳，含灵动岛、状态栏、物理按键，可开关
- 📄 **PRD 文档** - 内置 Markdown 编辑器撰写需求文档
- 📦 **项目导出** - 导出为独立 HTML，无需服务器即可运行

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

### 5. 配置 AI 模型

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
├── config.json            # 服务器和 AI 参数配置
├── src/
│   ├── index.html         # 主界面（含模型管理）
│   ├── script.js          # 前端逻辑
│   └── viewer.html        # 预览器/微调模式/真机外壳
├── projects/              # 生成的项目存放目录
├── docs/                  # 项目文档
├── templates/             # 页面模板
└── 启动项目.bat           # Windows 启动脚本
```

---

## 🎯 使用指南

### 生成原型

1. 填写**页面名称**（如：登录页、首页）
2. 描述**布局结构**（如：顶部导航栏、左侧菜单、右侧内容区）
3. 上传**参考图**（可选，支持拖拽或 Ctrl+V 粘贴）
4. 点击 **AI 生成**（异步模式，项目立即出现在列表，后台完成后自动更新）

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
