# 🎨 原型生成器 (Prototype Generator)

> AI 驱动的高保真原型设计工具 - 通过自然语言描述快速生成交互式 HTML 原型

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ 功能特性

- 🤖 **AI 生成原型** - 输入设计需求，AI 自动生成高保真 HTML 原型
- 🖼️ **参考图驱动** - 支持上传参考图，AI 会模仿布局和风格
- 📋 **剪切板粘贴** - 直接 Ctrl+V 粘贴截图作为参考图
- 🔄 **异步生成** - 点击生成后立即在列表显示，后台完成后自动更新
- 📝 **微调模式** - 可视化点选元素进行 AI 微调修改
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

### 4. 配置 API Key

复制配置模板并编辑：

```bash
# Windows
copy config.example.json config.json

# macOS/Linux
cp config.example.json config.json
```

编辑 `config.json`，填入您的 API 配置：

```json
{
    "api": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-xxxxxxxxxxxxxxxx",
        "model": "gpt-4o"
    },
    "server": {
        "port": 8080
    },
    "ai_options": {
        "max_tokens": 100000,
        "temperature": 0.7,
        "timeout": 300
    }
}
```

---

### 5. 启动项目

#### Windows
双击 `启动项目.bat`

#### macOS/Linux
```bash
python server.py
```

启动成功后，浏览器会自动打开 `http://localhost:8080`

---

## 🔑 API 配置说明

本项目支持任何 **OpenAI 兼容** 的 API 服务。

### 支持的 API 服务

| 服务商 | base_url | 获取 API Key |
|--------|----------|--------------|
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
| OpenAI | `gpt-5.2`, `gpt-5.3` | 最新一代模型，能力最强 |
| Anthropic | `claude-4.5-sonnet`, `claude-4.6-sonnet` | 代码质量高，理解力强 |
| Google | `gemini-3-pro`, `gemini-3-flash` | 多模态能力强，速度快 |
| 字节豆包 | `doubao-vision-pro`, `doubao-vision-lite` | 国产多模态模型 |
| 阿里千问 | `qwen-vl-max`, `qwen-vl-plus` | 多模态理解能力优秀 |
| Moonshot | `kimi-vision`, `moonshot-v1-128k` | 长上下文支持好 |

---

## 📁 目录结构

```
原型生成器/
├── server.py              # 后端服务 (Python)
├── config.json            # 配置文件 (包含 API Key)
├── config.example.json    # 配置模板
├── src/
│   ├── index.html         # 主界面
│   ├── script.js          # 前端逻辑
│   ├── style.css          # 样式
│   └── viewer.html        # 预览器/微调模式
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
4. 点击 **AI 生成**
5. 等待生成完成，自动打开预览

### 微调模式

1. 在预览器中点击 **微调模式** 按钮
2. 点选或框选要修改的元素
3. 输入修改需求（如："把按钮改成蓝色"）
4. 点击 **应用修改**

---

## ❓ 常见问题

### Q: 提示 "python 不是内部或外部命令"
**A:** Python 未添加到系统 PATH。请重新安装 Python，勾选 "Add Python to PATH"。

### Q: 提示 "No module named 'requests'"
**A:** 运行 `pip install requests` 安装依赖。

### Q: API 调用失败 / 超时
**A:** 
1. 检查 `config.json` 中的 API Key 是否正确
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
