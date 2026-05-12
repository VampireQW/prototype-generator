# -*- coding: utf-8 -*-
"""
原型生成器后端服务
- 提供静态文件服务
- 处理图片上传
- 调用AI大模型生成原型
- 管理项目文件
- 下载外部图片到本地
"""

import http.server
import socketserver
import os
import json
import re
import datetime
import urllib.request
import urllib.parse
import base64
import ssl
import hashlib
import requests # Add requests import
import subprocess
import tempfile
import shlex
import threading
import time
import sys
import http.cookies
import zipfile
import xml.etree.ElementTree as ET

import db  # 团队协作数据库

# ==================== PyInstaller 兼容 ====================
def get_base_path():
    """获取应用根目录（兼容 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# 切换工作目录到应用根目录
os.chdir(get_base_path())

# ==================== 异步任务管理 ====================
generating_tasks = {}  # {project_id: {status, progress, error, thread}}
tasks_lock = threading.Lock()  # 线程锁

# 状态常量
STATUS_PENDING = 'pending'
STATUS_GENERATING = 'generating'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'

# ==================== 模型配置 ====================
MODELS_FILE = 'models.json'

def load_models():
    """加载模型配置文件"""
    if not os.path.exists(MODELS_FILE):
        # 创建默认模型配置
        default_models = {
            "models": [{
                "id": "default",
                "name": "Default Model",
                "provider": "",
                "base_url": "",
                "api_key": "YOUR_API_KEY_HERE",
                "model": "gpt-4"
            }],
            "selected_model_id": "default"
        }
        save_models(default_models)
        return default_models
    with open(MODELS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_models(data):
    """保存模型配置文件"""
    with open(MODELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_selected_model():
    """获取当前选中的模型配置"""
    data = load_models()
    selected_id = data.get('selected_model_id', '')
    for m in data.get('models', []):
        if m['id'] == selected_id:
            return m
    # 兜底返回第一个
    models = data.get('models', [])
    return models[0] if models else None

# ==================== 配置加载 ====================
CONFIG_FILE = 'config.json'

def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_FILE):
        print("=" * 60)
        print("❌ 错误: 配置文件 config.json 不存在!")
        print("")
        print("请创建 config.json 文件，内容格式如下:")
        print(json.dumps({
            "server": {
                "port": 8080
            },
            "ai_options": {
                "max_tokens": 100000,
                "temperature": 0.7,
                "timeout": 300,
                "system_prompt": "You are a professional UI/UX Developer."
            }
        }, indent=2, ensure_ascii=False))
        print("")
        print("模型配置请在 models.json 或页面「管理模型」中设置")
        print("=" * 60)
        raise FileNotFoundError("config.json 不存在，请创建配置文件")

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 验证模型配置（从 models.json）
    try:
        selected = get_selected_model()
        if not selected or not selected.get('api_key') or selected.get('api_key') == 'YOUR_API_KEY_HERE':
            print("=" * 60)
            print("⚠️ 警告: 请在 models.json 中配置有效的 API 密钥!")
            print("   或启动后在页面顶栏「管理模型」中配置")
            print("=" * 60)
        else:
            print(f"[INFO] 当前模型: {selected.get('name', '未命名')}")
    except Exception as e:
        print("=" * 60)
        print(f"⚠️ 警告: models.json 加载失败，请检查文件格式 ({e})")
        print("=" * 60)

    return config

# 加载配置
CONFIG = load_config()

# 从配置文件读取设置
PORT = CONFIG.get('server', {}).get('port', 8080)
API_CONFIG = CONFIG.get('api', {})
AI_OPTIONS = CONFIG.get('ai_options', {
    'max_tokens': 100000,
    'temperature': 0.7,
    'timeout': 300,
    'system_prompt': 'You are a professional UI/UX Developer. Generate complete, standalone HTML prototypes with realistic data.'
})


UPLOAD_DIR = 'uploads'
DATA_DIR = 'data'
PROJECTS_DIR = 'projects'
DELETED_DIR = 'deleted'
DESIGN_SYSTEMS_DIR = 'design-systems'
SKILLS_DIR = 'skills'
CRAFT_DIR = 'craft'
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DELETED_PROJECTS_FILE = os.path.join(DATA_DIR, 'deleted_projects.json')

# 创建必要的目录
for dir_path in [UPLOAD_DIR, DATA_DIR, PROJECTS_DIR, DELETED_DIR, DESIGN_SYSTEMS_DIR, SKILLS_DIR, CRAFT_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

if not os.path.exists(PROJECTS_FILE):
    with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

if not os.path.exists(DELETED_PROJECTS_FILE):
    with open(DELETED_PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# 初始化协作数据库
db.init_db()
print("[INFO] 协作数据库已初始化")


# ==================== Open Design 资产层 ====================
MAX_DESIGN_SYSTEM_CHARS = 12000
MAX_SKILL_CONTEXT_CHARS = 12000
MAX_CRAFT_CONTEXT_CHARS = 4000
MAX_PPT_IMAGES_PER_SLIDE = 5
MAX_AI_IMAGES_PER_REQUEST = 16
STALE_GENERATION_SECONDS = 15 * 60
HEAVY_AI_PROMPT_CHARS = 30000
HEAVY_AI_IMAGE_COUNT = 8
HEAVY_AI_TIMEOUT_SECONDS = 120
DEFAULT_MAX_OUTPUT_TOKENS = 100000
GEMINI_MAX_OUTPUT_TOKENS = 65536

DEFAULT_SKILL_ID = 'web-prototype'
DEFAULT_CRAFT_SECTIONS = ['typography', 'color', 'anti-ai-slop']

MINIMAL_CRAFT_RULES = """- 使用清晰的信息层级、真实业务文案和可扫描布局，不要输出模板感占位内容。
- 字体控制在 6-8 个层级内；正文 15-18px，行高 1.5-1.6；按钮/标签文字保持可读。
- 色彩需要有主次、背景、中性色和状态色；避免整页只用单一色系的浅深变化。
- 页面必须响应式，移动端不能文字溢出或元素重叠。
- 组件状态要完整：hover/focus/active/disabled/loading 等按场景补齐。"""

MINIMAL_SKILL_RULES = {
    'web-prototype': """- 生成可交互的 Web 原型页面，优先完成用户描述的页面结构、核心流程和关键状态。
- 用真实示例数据呈现列表、表格、卡片、表单和空状态。
- 不做营销式 landing，除非用户明确要求。""",
    'dashboard': """- 面向高频业务操作，布局要紧凑、清晰、便于扫描。
- 优先呈现筛选、指标、表格、图表、批量操作和状态反馈。
- 避免大面积装饰和过度卡片化。""",
    'mobile-app': """- 按移动端真实使用方式组织导航、列表、详情、表单和反馈。
- 控件尺寸适合触控，底部导航、顶部栏、安全区和滚动区域要自然。
- 避免桌面 Web 布局直接缩放到手机。""",
    'saas-landing': """- 产物是 SaaS 产品页时，首屏直接表达产品/品牌和核心价值。
- 内容包含功能、场景、社会证明、价格或行动入口等必要模块。
- 视觉要有可信产品感，不堆砌空泛装饰。""",
    'html-ppt': """- 生成单文件 HTML 演示稿，不是长网页。
- 默认展示大缩略图概览；点击播放或缩略图进入全屏播放。
- 播放模式每页占满 100vw x 100vh，支持键盘/鼠标/触摸翻页。
- 只能通过 Esc 或右键退出播放模式，不显示明显关闭按钮。
- 每个 PPT 页面对应独立 slide，保留页序、信息层级和配图归属。"""
}

DESIGN_SYSTEM_CN_NAMES = {
    'linear-app': 'Linear 设计系统',
    'apple': 'Apple 设计系统',
    'vercel': 'Vercel 设计系统',
    'notion': 'Notion 设计系统',
    'xiaohongshu': '小红书设计系统',
    'stripe': 'Stripe 设计系统',
    'figma': 'Figma 设计系统',
    'shadcn': 'shadcn/ui 设计系统',
    'github': 'GitHub 设计系统',
    'supabase': 'Supabase 设计系统',
    'openai': 'OpenAI 设计系统',
    'default': '默认设计系统',
}

DESIGN_SYSTEM_CATEGORY_CN = {
    'Productivity & SaaS': '生产力 / SaaS',
    'Media & Consumer': '媒体 / 消费产品',
    'Developer Tools': '开发者工具',
    'Finance & Crypto': '金融 / 加密',
    'E-commerce': '电商',
    'Social & Community': '社交 / 社区',
    'Automotive': '汽车',
    'Gaming & Entertainment': '游戏 / 娱乐',
    'AI & Infrastructure': 'AI / 基础设施',
}


def safe_asset_id(value):
    """限制资产 ID，避免路径穿越。"""
    value = (value or '').strip()
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', value):
        return ''
    return value


def read_text_file(path, limit=None):
    """读取文本文件；limit 用来控制注入 prompt 的上下文大小。"""
    if not os.path.exists(path) or not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    if limit and len(text) > limit:
        return text[:limit] + "\n\n[内容过长，已截断到关键前段]"
    return text


def first_markdown_heading(text, fallback):
    match = re.search(r'^#\s+(.+)$', text or '', re.MULTILINE)
    return match.group(1).strip() if match else fallback


def design_system_display_name(asset_id, heading):
    if asset_id in DESIGN_SYSTEM_CN_NAMES:
        return DESIGN_SYSTEM_CN_NAMES[asset_id]
    name = (heading or asset_id).strip()
    prefix = 'Design System Inspired by '
    if name.startswith(prefix):
        return f"{name[len(prefix):].strip()} 设计系统"
    if name.lower() == asset_id.lower():
        return f"{asset_id.replace('-', ' ').title()} 设计系统"
    return name


def extract_design_system_colors(text, max_count=6):
    """从 DESIGN.md 中抽取可预览的主配色。"""
    colors = []
    seen = set()
    for match in re.finditer(r'#[0-9a-fA-F]{6}\b', text or ''):
        color = match.group(0).lower()
        if color in seen:
            continue
        seen.add(color)
        colors.append(color)
        if len(colors) >= max_count:
            break
    return colors


def extract_frontmatter(text):
    if not text.startswith('---'):
        return ''
    match = re.match(r'^---\s*\n(.*?)\n---\s*', text, re.DOTALL)
    return match.group(1) if match else ''


def extract_yaml_scalar(frontmatter, key, default=''):
    match = re.search(rf'^{re.escape(key)}:\s*(.+)$', frontmatter or '', re.MULTILINE)
    if not match:
        return default
    value = match.group(1).strip().strip('"').strip("'")
    return value if value not in ('|', '>') else default


def extract_yaml_block(frontmatter, key, default=''):
    lines = (frontmatter or '').splitlines()
    for i, line in enumerate(lines):
        if re.match(rf'^{re.escape(key)}:\s*[|>]?\s*$', line):
            block = []
            for next_line in lines[i + 1:]:
                if next_line and not next_line.startswith((' ', '\t', '-')):
                    break
                block.append(next_line.strip())
            return '\n'.join([x for x in block if x]).strip() or default
    return extract_yaml_scalar(frontmatter, key, default)


def design_system_path(design_system_id):
    ds_id = safe_asset_id(design_system_id)
    if not ds_id:
        return ''
    return os.path.join(DESIGN_SYSTEMS_DIR, ds_id, 'DESIGN.md')


def skill_path(skill_id):
    sid = safe_asset_id(skill_id)
    if not sid:
        return ''
    return os.path.join(SKILLS_DIR, sid, 'SKILL.md')


def list_design_system_assets():
    items = []
    if not os.path.exists(DESIGN_SYSTEMS_DIR):
        return items
    for name in sorted(os.listdir(DESIGN_SYSTEMS_DIR)):
        path = os.path.join(DESIGN_SYSTEMS_DIR, name, 'DESIGN.md')
        if not os.path.isfile(path):
            continue
        text = read_text_file(path, 12000)
        category = ''
        category_match = re.search(r'^>\s*Category:\s*(.+)$', text, re.MULTILINE)
        if category_match:
            category = category_match.group(1).strip()
        items.append({
            'id': name,
            'name': first_markdown_heading(text, name),
            'displayName': design_system_display_name(name, first_markdown_heading(text, name)),
            'category': category,
            'categoryLabel': DESIGN_SYSTEM_CATEGORY_CN.get(category, category),
            'colors': extract_design_system_colors(text)
        })
    return items


def list_skill_assets():
    items = []
    if not os.path.exists(SKILLS_DIR):
        return items
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, 'SKILL.md')
        if not os.path.isfile(path):
            continue
        text = read_text_file(path, 12000)
        frontmatter = extract_frontmatter(text)
        mode_match = re.search(r'^\s*mode:\s*([a-zA-Z0-9_-]+)\s*$', frontmatter, re.MULTILINE)
        items.append({
            'id': name,
            'name': extract_yaml_scalar(frontmatter, 'name', name),
            'description': extract_yaml_block(frontmatter, 'description', ''),
            'mode': mode_match.group(1) if mode_match else 'prototype'
        })
    return items


def get_skill_context(skill_id, max_chars=None, include_references=True):
    sid = safe_asset_id(skill_id) or DEFAULT_SKILL_ID
    root = os.path.join(SKILLS_DIR, sid)
    skill_md = os.path.join(root, 'SKILL.md')
    if not os.path.isfile(skill_md):
        return ''

    context_limit = max_chars or MAX_SKILL_CONTEXT_CHARS
    parts = [read_text_file(skill_md, min(26000, context_limit))]

    # 常见 skill 的关键参考资料。API 模型没有文件工具，所以需要把轻量种子注入 prompt。
    if include_references:
        for rel in [
            os.path.join('assets', 'template.html'),
            os.path.join('references', 'layouts.md'),
            os.path.join('references', 'checklist.md'),
            os.path.join('references', 'themes.md'),
            os.path.join('references', 'full-decks.md'),
            os.path.join('references', 'animations.md'),
            os.path.join('references', 'presenter-mode.md'),
        ]:
            ref_path = os.path.join(root, rel)
            if os.path.isfile(ref_path):
                ref_text = read_text_file(ref_path, 12000)
                if ref_text:
                    parts.append(f"\n\n## Skill reference: {rel}\n\n{ref_text}")

    context = '\n'.join([p for p in parts if p]).strip()
    if len(context) > context_limit:
        context = context[:context_limit] + "\n\n[Skill 上下文过长，已截断]"
    return context


def get_craft_context(section_ids=None, max_chars=None):
    section_ids = section_ids or DEFAULT_CRAFT_SECTIONS
    parts = []
    remaining = max_chars or MAX_CRAFT_CONTEXT_CHARS
    for section in section_ids:
        sid = safe_asset_id(section)
        if not sid:
            continue
        path = os.path.join(CRAFT_DIR, f'{sid}.md')
        text = read_text_file(path, remaining)
        if text:
            parts.append(f"## Craft: {sid}\n\n{text}")
            remaining -= len(text)
            if remaining <= 0:
                break
    return '\n\n'.join(parts)


def get_design_system_context(design_system_id, max_chars=None):
    ds_id = safe_asset_id(design_system_id)
    if not ds_id or ds_id in ('default', 'none'):
        return ''
    return read_text_file(design_system_path(ds_id), max_chars or MAX_DESIGN_SYSTEM_CHARS)


def is_default_design_system(design_system_id):
    ds_id = safe_asset_id(design_system_id)
    return not ds_id or ds_id in ('default', 'none')


def get_minimal_skill_rules(skill_id):
    sid = safe_asset_id(skill_id) or DEFAULT_SKILL_ID
    return MINIMAL_SKILL_RULES.get(sid) or MINIMAL_SKILL_RULES[DEFAULT_SKILL_ID]


def compose_generation_prompt(user_prompt, design_system_id='', skill_id='', craft_sections=None):
    """将 Open Design 的资产层按需注入现有生成任务。

    默认风格下只注入必要摘要，避免普通原型生成携带大段 OpenDesign 上下文。
    只有用户选择具体设计系统时，才注入对应 DESIGN.md。
    """
    sid = safe_asset_id(skill_id) or DEFAULT_SKILL_ID
    default_design = is_default_design_system(design_system_id)
    large_ppt_import = (
        sid == 'html-ppt'
        and (len(user_prompt or '') > 8000 or '来源文件：' in (user_prompt or ''))
    )
    design_limit = 8000 if large_ppt_import else MAX_DESIGN_SYSTEM_CHARS
    skill_limit = 10000 if sid == 'html-ppt' else 6000
    craft_limit = 2500 if large_ppt_import else MAX_CRAFT_CONTEXT_CHARS

    parts = [
        "# 生成上下文",
        "下面是本次生成的必要约束。请严格遵守，但不要在页面中解释这些规则。",
        "优先级：用户明确需求 > 选中的设计系统 > 产物类型规则 > 通用设计规则 > 用户表单里的主题色/辅助色/组件风格。",
    ]

    if large_ppt_import:
        parts.append("本次是大体量 PPT 导入任务，已自动精简上下文；请优先保留 PPT 原始信息层级、页序和关键视觉。")

    if default_design:
        parts.append("\n## 通用设计规则（精简）\n\n" + MINIMAL_CRAFT_RULES)
    else:
        design_system = get_design_system_context(design_system_id, design_limit)
        if design_system:
            parts.append(f"\n## Active DESIGN.md ({design_system_id})\n\n{design_system}")
            parts.append("若 DESIGN.md 与用户表单颜色冲突，以 DESIGN.md 的品牌色、字体和组件语言为准。")
        else:
            parts.append("\n## 通用设计规则（精简）\n\n" + MINIMAL_CRAFT_RULES)

    if not default_design and sid != DEFAULT_SKILL_ID:
        skill_context = get_skill_context(sid, skill_limit, include_references=False)
        if skill_context:
            parts.append(f"\n## Active Skill ({sid}, compact)\n\n{skill_context}")
        else:
            parts.append(f"\n## 产物类型规则（{sid}）\n\n{get_minimal_skill_rules(sid)}")
    else:
        parts.append(f"\n## 产物类型规则（{sid}，精简）\n\n{get_minimal_skill_rules(sid)}")

    if sid == 'html-ppt' and default_design and not large_ppt_import:
        skill_context = get_skill_context(sid, skill_limit, include_references=False)
        if skill_context:
            parts.append(f"\n## HTML PPT Skill 补充（compact）\n\n{skill_context}")

    if not default_design and craft_sections:
        craft = get_craft_context(craft_sections, craft_limit)
        if craft:
            parts.append(f"\n## Craft Rules（按需）\n\n{craft}")

    parts.append(f"\n# 用户原始需求\n\n{user_prompt}")
    parts.append(
        "\n# 最终输出约束\n"
        "- 输出一个完整、独立、可直接预览的 HTML 文件。\n"
        "- 如果产物类型要求 deck/PPT，也输出单文件 HTML deck，保存为 index.html。\n"
        "- 不要输出 Markdown 解释，不要输出多个文件名说明，只返回 HTML。"
    )
    return '\n\n'.join(parts)


def get_model_max_tokens(model_name):
    """返回当前模型可接受的 max_tokens，避免兼容网关因上限不同直接 400。"""
    configured = AI_OPTIONS.get('max_tokens', DEFAULT_MAX_OUTPUT_TOKENS)
    try:
        configured = int(configured)
    except (TypeError, ValueError):
        configured = DEFAULT_MAX_OUTPUT_TOKENS

    model_key = (model_name or '').lower()
    caps = []
    if 'gemini' in model_key:
        caps.append(GEMINI_MAX_OUTPUT_TOKENS)

    if caps:
        capped = min(configured, *caps)
        if capped != configured:
            print(f"[AI] max_tokens 从 {configured} 自动调整为 {capped}，以适配模型 {model_name}")
        return capped

    return configured


def get_github_runtime_config():
    """GitHub token 只从环境变量读取，避免把密钥写进 config.json。"""
    config = load_config()
    gh = config.get('github', {})
    token = os.environ.get('PROTOTYPE_GITHUB_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    return {
        'token': token,
        'username': gh.get('username', ''),
        'repo': gh.get('repo', 'my-prototypes')
    }


def chinese_to_pinyin(text):
    """将中文转换为拼音（简化版，只保留英文和数字）"""
    # 简单处理：保留英文字母和数字，去掉中文和特殊字符
    result = re.sub(r'[^\w\s-]', '', text)
    result = re.sub(r'[\s]+', '_', result)

    # 如果结果为空或只有下划线，使用默认名称
    if not result or result == '_':
        return 'project'

    # 如果包含中文，尝试使用简单映射（常用词）
    chinese_map = {
        '首页': 'home', '登录': 'login', '注册': 'register',
        '作业': 'homework', '列表': 'list', '详情': 'detail',
        '用户': 'user', '设置': 'settings', '个人': 'profile',
        '管理': 'manage', '系统': 'system', '数据': 'data',
        '分析': 'analysis', '报告': 'report', '统计': 'stats',
        '订单': 'order', '商品': 'product', '购物': 'shopping',
        '消息': 'message', '通知': 'notice', '搜索': 'search',
        '批改': 'grading', '智能': 'smart', 'AI': 'ai',
        '学生': 'student', '老师': 'teacher', '课程': 'course',
        '考试': 'exam', '成绩': 'score', '答案': 'answer',
    }

    for cn, en in chinese_map.items():
        result = result.replace(cn, en)

    # 移除剩余的非ASCII字符
    result = re.sub(r'[^\x00-\x7F]+', '', result)
    result = re.sub(r'_+', '_', result)  # 合并多个下划线
    result = result.strip('_')

    return result if result else 'project'


def generate_project_id(project_name):
    """生成项目文件夹名称：项目名_年月日_时间"""
    # 时间格式: 20260114_4-15-23pm
    now = datetime.datetime.now()
    hour = now.hour
    am_pm = 'am' if hour < 12 else 'pm'
    hour_12 = hour if hour <= 12 else hour - 12
    if hour_12 == 0:
        hour_12 = 12
    timestamp = now.strftime(f'%Y%m%d_{hour_12}-%M-%S{am_pm}')

    # 保留中文名称，但替换不安全字符
    safe_name = re.sub(r'[\\/:*?"<>|]', '', project_name)  # 移除Windows不允许的字符
    safe_name = safe_name.replace(' ', '_')
    # 限制长度
    if len(safe_name) > 30:
        safe_name = safe_name[:30]

    return f"{safe_name}_{timestamp}"


def extract_title_from_html(html_content):
    """从HTML中提取title标签的内容"""
    match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def download_image(url, save_folder, filename=None):
    """下载图片到本地"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            content_type = response.headers.get('Content-Type', '')
            data = response.read()

            # 确定文件扩展名
            if not filename:
                # 从URL或content-type推断
                ext = '.jpg'
                if 'png' in content_type or url.endswith('.png'):
                    ext = '.png'
                elif 'gif' in content_type or url.endswith('.gif'):
                    ext = '.gif'
                elif 'webp' in content_type or url.endswith('.webp'):
                    ext = '.webp'

                # 用URL的hash作为文件名
                url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
                filename = f"img_{url_hash}{ext}"

            save_path = os.path.join(save_folder, filename)
            with open(save_path, 'wb') as f:
                f.write(data)

            return filename
    except Exception as e:
        print(f"[图片下载失败] {url}: {e}")
        return None


def save_base64_image(base64_data, save_folder, filename):
    """保存base64图片到本地"""
    try:
        # 移除data:image/xxx;base64,前缀
        if ',' in base64_data:
            header, data = base64_data.split(',', 1)
        else:
            data = base64_data

        raw = base64.b64decode(data)
        mime = detect_supported_image_mime(raw)
        if not mime:
            print(f"[Base64图片跳过] {filename}: 不支持的图片格式")
            return None

        ext = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/gif': '.gif',
            'image/webp': '.webp',
        }.get(mime, '.jpg')

        # 确保文件名有正确扩展名
        if not any(filename.endswith(e) for e in ['.jpg', '.png', '.gif', '.webp']):
            filename = filename + ext

        save_path = os.path.join(save_folder, filename)
        with open(save_path, 'wb') as f:
            f.write(raw)

        return filename
    except Exception as e:
        print(f"[Base64图片保存失败] {filename}: {e}")
        return None


def detect_supported_image_mime(raw):
    """只允许主流 raster 图片进入模型，过滤 SVG/XML 等网关不支持的内容。"""
    if not raw:
        return ''
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if raw.startswith(b'GIF87a') or raw.startswith(b'GIF89a'):
        return 'image/gif'
    if raw.startswith(b'RIFF') and len(raw) > 12 and raw[8:12] == b'WEBP':
        return 'image/webp'
    return ''


def normalize_supported_image_data_url(image_data):
    """校验 data URL 的真实字节格式，并修正 mime，避免 .png 文件里实际是 XML。"""
    try:
        if not image_data:
            return ''
        data = image_data
        if ',' in image_data:
            data = image_data.split(',', 1)[1]
        raw = base64.b64decode(data)
        mime = detect_supported_image_mime(raw)
        if not mime:
            return ''
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return ''


def parse_pptx_bytes(file_data):
    """用标准库解析 PPTX 的文字和图片引用，供 HTML PPT 美化模式使用。"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        slides = []
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            slide_names = [
                name for name in zf.namelist()
                if re.match(r'ppt/slides/slide\d+\.xml$', name)
            ]
            slide_names.sort(key=lambda n: int(re.search(r'slide(\d+)\.xml$', n).group(1)))

            media_cache = {}
            for slide_index, slide_name in enumerate(slide_names, start=1):
                root = ET.fromstring(zf.read(slide_name))
                texts = []
                for node in root.iter():
                    if node.tag.endswith('}t') and node.text:
                        text = node.text.strip()
                        if text:
                            texts.append(text)

                rels_name = f"ppt/slides/_rels/slide{slide_index}.xml.rels"
                image_targets = []
                if rels_name in zf.namelist():
                    rel_root = ET.fromstring(zf.read(rels_name))
                    for rel in rel_root:
                        rel_type = rel.attrib.get('Type', '')
                        target = rel.attrib.get('Target', '')
                        if 'image' not in rel_type or not target:
                            continue
                        media_path = target.replace('../', 'ppt/')
                        if media_path.startswith('/'):
                            media_path = media_path.lstrip('/')
                        if media_path in zf.namelist():
                            image_targets.append(media_path)

                images = []
                for media_path in image_targets[:MAX_PPT_IMAGES_PER_SLIDE]:
                    if media_path in media_cache:
                        images.append(media_cache[media_path])
                        continue
                    raw = zf.read(media_path)
                    if len(raw) > 2_500_000:
                        continue
                    mime = detect_supported_image_mime(raw)
                    if not mime:
                        print(f"[PPTX解析] 跳过不支持的图片格式: {media_path}")
                        continue
                    item = {
                        'name': os.path.basename(media_path),
                        'base64': f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                    }
                    media_cache[media_path] = item
                    images.append(item)

                slides.append({
                    'index': slide_index,
                    'title': texts[0] if texts else f'第 {slide_index} 页',
                    'texts': texts,
                    'images': images,
                    'imageCount': len(images),
                    'sourceImageCount': len(image_targets),
                })

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return {
            'slides': slides,
            'slideCount': len(slides),
            'imageCount': sum(len(slide.get('images', [])) for slide in slides),
            'sourceImageCount': sum(slide.get('sourceImageCount', 0) for slide in slides),
            'maxImagesPerSlide': MAX_PPT_IMAGES_PER_SLIDE
        }
    except zipfile.BadZipFile:
        raise ValueError('无法解析该文件。当前仅支持 .pptx，请先将 .ppt 另存为 .pptx 后再上传。')


def extract_ai_error_message(result, max_chars=1500):
    """从非标准 AI 响应里提取可读错误，避免只暴露 KeyError: choices。"""
    if isinstance(result, dict):
        error = result.get('error')
        if isinstance(error, dict):
            parts = []
            for key in ('message', 'code', 'type', 'param'):
                value = error.get(key)
                if value:
                    parts.append(f"{key}: {value}")
            if parts:
                return '; '.join(parts)[:max_chars]
        if error:
            return str(error)[:max_chars]

        for key in ('message', 'msg', 'detail', 'error_description'):
            if result.get(key):
                return str(result[key])[:max_chars]

        return json.dumps(result, ensure_ascii=False)[:max_chars]

    return str(result)[:max_chars]


def parse_project_timestamp(value):
    try:
        return datetime.datetime.strptime(value or '', '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def mark_project_failed(project_id, error_message):
    """统一把生成中项目置为失败，避免列表和 record.json 状态漂移。"""
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    projects_path = PROJECTS_FILE
    if os.path.exists(projects_path):
        try:
            with open(projects_path, 'r', encoding='utf-8') as f:
                projects = json.load(f)
            for p in projects:
                if p.get('id') == project_id:
                    p['status'] = STATUS_FAILED
                    break
            with open(projects_path, 'w', encoding='utf-8') as f:
                json.dump(projects, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[状态] 更新项目失败状态失败: {e}")

    record_path = os.path.join(PROJECTS_DIR, project_id, 'record.json')
    if os.path.exists(record_path):
        try:
            with open(record_path, 'r', encoding='utf-8') as f:
                record = json.load(f)
            record['status'] = STATUS_FAILED
            record['error'] = error_message
            record['failedAt'] = now
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[状态] 更新 record 失败状态失败: {e}")


def assign_saved_images_to_pages(pages_data, saved_image_names, skill_id=None):
    """将扁平图片列表按页面元数据分回 PPT 配图和参考图，并生成给 AI 的路径说明。"""
    page_records = []
    manifest_lines = []
    img_index = 0
    is_ppt = skill_id == 'html-ppt'

    for page_idx, page in enumerate(pages_data, start=1):
        page_record = {
            'name': page.get('name', ''),
            'layout': page.get('layout', ''),
            'features': page.get('features', ''),
            'interaction': page.get('interaction', ''),
            'similarity': page.get('similarity', 'layout'),
            'images': [],
            'referenceImages': [],
            'pptImages': []
        }

        ppt_meta = page.get('pptImages') or []
        ppt_count = int(page.get('pptImageCount') or 0)
        reference_count = int(page.get('referenceImageCount') or max(int(page.get('imageCount') or 0) - ppt_count, 0))

        if ppt_count:
            manifest_lines.append(f"页面 {page_idx} 的 PPT 原始配图（必须放回对应原始页，不是参考图）:")
        for i in range(ppt_count):
            if img_index >= len(saved_image_names):
                break
            filename = saved_image_names[img_index]
            meta = ppt_meta[i] if i < len(ppt_meta) and isinstance(ppt_meta[i], dict) else {}
            slide_index = meta.get('slideIndex') or page_idx
            slide_title = meta.get('slideTitle') or ''
            item = {
                'file': filename,
                'slideIndex': slide_index,
                'slideTitle': slide_title
            }
            page_record['pptImages'].append(item)
            page_record['images'].append(filename)
            manifest_lines.append(f"- 第 {slide_index} 页配图: reference/{filename}" + (f"（{slide_title}）" if slide_title else ""))
            img_index += 1

        if reference_count:
            similarity = page_record.get('similarity', 'layout')
            if is_ppt:
                manifest_lines.append(f"页面 {page_idx} 的额外参考图（只用于辅助视觉风格判断）:")
            elif similarity == 'pixel':
                manifest_lines.append(
                    f"页面 {page_idx} 的参考图模式：像素级还原。"
                    "必须严格还原参考图的页面类型、布局、比例、颜色、字体层级、组件样式、内容密度、图标/图片位置和可读文字；"
                    "不得主动改动参考图中的主要结构、视觉风格、模块顺序和关键文案。用户文字需求只用于补充缺失信息，不要改成无关主题。"
                )
            elif similarity == 'style':
                manifest_lines.append(
                    f"页面 {page_idx} 的参考图模式：仅参考风格。"
                    "只提取色彩、字体气质、圆角/阴影、图标语言、留白、质感和整体视觉调性；"
                    "不要照抄参考图的布局结构、模块顺序或具体内容，页面结构以用户文字需求为准。"
                )
            else:
                manifest_lines.append(
                    f"页面 {page_idx} 的参考图模式：仅参考布局。"
                    "只提取页面类型、区域划分、模块层级、组件关系、排列方向、信息密度和交互入口位置；"
                    "不要照抄参考图的配色、品牌视觉、字体风格或装饰质感，视觉风格以用户选择的设计系统/表单设置为准。"
                )
        for _ in range(reference_count):
            if img_index >= len(saved_image_names):
                break
            filename = saved_image_names[img_index]
            page_record['referenceImages'].append(filename)
            page_record['images'].append(filename)
            manifest_lines.append(f"- 参考图: reference/{filename}")
            img_index += 1

        page_records.append(page_record)

    manifest = ''
    if manifest_lines:
        reference_rule = (
            "PPT 原始配图必须放回对应原始页；额外参考图只作为风格/质感参考，不要当成 PPT 内容图片。\n"
            if is_ppt else
            "非 PPT 参考图是页面生成的重要依据，但必须严格按每页的参考图模式执行：仅参考布局、仅参考风格、像素级还原三者互斥。请先识别参考图，再按指定模式取舍；不要忽略参考图，也不要替换成无关业务页面。\n"
        )
        manifest = (
            "\n\n# 图片资源路径与用途\n"
            "所有图片已保存到项目文件夹的 `reference/` 目录。生成 HTML 时请使用这些相对路径作为 `<img src=\"reference/...\">`。\n"
            + reference_rule
            + "\n".join(manifest_lines)
        )
    return page_records, manifest


def download_html_images(html_content, save_folder):
    """下载HTML中的所有外部图片并替换URL"""
    # 创建images子目录
    images_folder = os.path.join(save_folder, 'images')
    os.makedirs(images_folder, exist_ok=True)

    # 匹配图片URL（src="https://..."）
    img_pattern = r'src=["\']?(https?://[^"\'>\s]+\.(jpg|jpeg|png|gif|webp|svg)[^"\'>\s]*)["\']?'
    matches = re.findall(img_pattern, html_content, re.IGNORECASE)

    url_map = {}
    for url, ext in matches:
        if url not in url_map:
            filename = download_image(url, images_folder)
            if filename:
                url_map[url] = f"images/{filename}"
                print(f"[下载] {url} -> {filename}")

    # 替换URL
    for old_url, new_path in url_map.items():
        html_content = html_content.replace(old_url, new_path)

    return html_content


class CustomHandler(http.server.SimpleHTTPRequestHandler):

    def end_headers(self):
        """添加禁用缓存的响应头"""
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    # ==================== 认证辅助方法 ====================

    def get_current_user(self):
        """从 Cookie 读取 session，返回 user dict 或 None"""
        cookie_header = self.headers.get('Cookie', '')
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(cookie_header)
        except Exception:
            return None
        token_morsel = cookies.get('session_token')
        if not token_morsel:
            return None
        return db.get_session_user(token_morsel.value)

    def require_auth(self):
        """要求登录，返回 user dict，未登录则发送 401 并返回 None"""
        user = self.get_current_user()
        if not user:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': '请先登录'}).encode('utf-8'))
            return None
        return user

    def set_session_cookie(self, token):
        """设置 session cookie"""
        cookie = http.cookies.SimpleCookie()
        cookie['session_token'] = token
        cookie['session_token']['path'] = '/'
        cookie['session_token']['httponly'] = True
        cookie['session_token']['samesite'] = 'Lax'
        cookie['session_token']['max-age'] = 3 * 24 * 3600  # 3天
        self.send_header('Set-Cookie', cookie['session_token'].OutputString())

    def clear_session_cookie(self):
        """清除 session cookie"""
        cookie = http.cookies.SimpleCookie()
        cookie['session_token'] = ''
        cookie['session_token']['path'] = '/'
        cookie['session_token']['max-age'] = 0
        self.send_header('Set-Cookie', cookie['session_token'].OutputString())

    def read_json_body(self):
        """读取并解析 JSON 请求体"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))

    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        # ---- 认证 & 团队 路由 ----
        if path == '/api/auth/me':
            self.handle_auth_me()
        elif path == '/api/teams':
            self.handle_get_teams()
        elif path.startswith('/api/teams/') and path.endswith('/members'):
            team_id = path.split('/')[3]
            self.handle_get_team_members(team_id)
        elif path == '/api/projects/my':
            self.handle_get_my_projects(query)
        elif path == '/api/projects/team':
            self.handle_get_team_projects(query)
        # ---- 项目文件访问控制 ----
        elif path.startswith('/projects/'):
            self.handle_project_file_access(path)
        # ---- 原有路由 ----
        elif path == '/api/prd/load':
            self.handle_prd_load(query)
        elif path == '/api/pages':
            self.handle_get_pages(query)
        elif path == '/api/flowchart':
            self.handle_get_flowchart(query)
        elif path == '/api/generation-status':
            self.handle_generation_status(query)
        elif path == '/api/models':
            self.handle_get_models()
        elif path == '/api/design-systems':
            self.handle_get_design_systems()
        elif path.startswith('/api/design-systems/'):
            design_system_id = urllib.parse.unquote(path.split('/api/design-systems/', 1)[1])
            self.handle_get_design_system(design_system_id)
        elif path == '/api/skills':
            self.handle_get_skills()
        elif path.startswith('/api/skills/'):
            skill_id = urllib.parse.unquote(path.split('/api/skills/', 1)[1])
            self.handle_get_skill(skill_id)
        elif path == '/api/server-info':
            self.handle_server_info()
        elif path == '/api/github/config':
            self.handle_github_config_get()
        elif path == '/data/projects.json':
            # 拦截项目列表请求，确保返回最新数据
            self.load_projects()
            super().do_GET()
        else:
            # 默认静态文件服务
            super().do_GET()

    def do_POST(self):
        path = self.path.split('?')[0]  # 去掉查询参数
        # ---- 认证路由 ----
        if path == '/api/auth/register':
            self.handle_auth_register()
        elif path == '/api/auth/login':
            self.handle_auth_login()
        elif path == '/api/auth/logout':
            self.handle_auth_logout()
        # ---- 团队路由 ----
        elif path == '/api/teams/create':
            self.handle_create_team()
        elif path == '/api/teams/join':
            self.handle_join_team()
        elif path.startswith('/api/teams/') and path.endswith('/leave'):
            team_id = path.split('/')[3]
            self.handle_leave_team(team_id)
        elif path.startswith('/api/teams/') and path.endswith('/remove-member'):
            team_id = path.split('/')[3]
            self.handle_remove_member(team_id)
        # ---- 项目分享路由 ----
        elif path.startswith('/api/projects/') and path.endswith('/share'):
            project_id = urllib.parse.unquote(path.split('/api/projects/')[1].rsplit('/share', 1)[0])
            self.handle_share_project(project_id)
        elif path.startswith('/api/projects/') and path.endswith('/unshare'):
            project_id = urllib.parse.unquote(path.split('/api/projects/')[1].rsplit('/unshare', 1)[0])
            self.handle_unshare_project(project_id)
        elif path.startswith('/api/projects/') and path.endswith('/shared-teams'):
            project_id = urllib.parse.unquote(path.split('/api/projects/')[1].rsplit('/shared-teams', 1)[0])
            self.handle_get_project_shared_teams(project_id)
        # ---- 原有路由 ----
        elif self.path == '/upload':
            self.handle_upload()
        elif self.path == '/generate':
            self.handle_generate()
        elif self.path == '/generate-async':
            self.handle_generate_async()
        elif self.path == '/save-project':
            self.handle_save_project()
        elif self.path == '/delete-project':
            self.handle_delete_project()
        elif self.path == '/rename-project':
            self.handle_rename_project()
        elif self.path == '/restore-project':
            self.handle_restore_project()
        elif self.path == '/deleted-projects':
            self.handle_get_deleted_projects()
        elif self.path == '/copy-project':
            self.handle_copy_project()
        elif self.path == '/create-placeholder':
            self.handle_create_placeholder()
        elif self.path == '/api/prd/save':
            self.handle_prd_save()
        elif self.path == '/api/inspector/apply':
            self.handle_inspector_apply()
        elif self.path == '/api/pptx/parse':
            self.handle_pptx_parse()
        elif self.path == '/api/models/select':
            self.handle_model_select()
        elif self.path == '/api/models/save':
            self.handle_model_save()
        elif self.path == '/api/models/delete':
            self.handle_model_delete()
        elif self.path == '/api/export':
            self.handle_export()
        elif self.path == '/api/github/config':
            self.handle_github_config_save()
        elif self.path == '/api/github/test':
            self.handle_github_test()
        elif self.path == '/api/github/publish':
            self.handle_github_publish()
        elif self.path == '/api/github/unpublish':
            self.handle_github_unpublish()
        else:
            self.send_error(404, "Not Found")

    def handle_upload(self):
        """处理图片上传"""
        try:
            content_type = self.headers['Content-Type']
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400, "Expected multipart/form-data")
                return

            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                self.send_error(400, "Missing boundary")
                return
            boundary = boundary_match.group(1).encode()

            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)

            saved_paths = []
            parts = body.split(b'--' + boundary)

            for part in parts:
                if not part or part == b'--\r\n' or part == b'--':
                    continue
                if part.startswith(b'\r\n'):
                    part = part[2:]
                if part.endswith(b'\r\n'):
                    part = part[:-2]

                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue

                headers = part[:header_end].decode('utf-8', errors='ignore')
                file_data = part[header_end+4:]

                filename_match = re.search(r'filename="([^"]+)"', headers)
                if filename_match:
                    filename = filename_match.group(1)
                    filename = os.path.basename(filename)

                    save_path = os.path.join(UPLOAD_DIR, filename)
                    with open(save_path, 'wb') as f:
                        f.write(file_data)

                    saved_paths.append({
                        'name': filename,
                        'path': os.path.abspath(save_path),
                        'url': f'/{UPLOAD_DIR}/{filename}'
                    })

            self.send_json_response({'files': saved_paths})

        except Exception as e:
            self.send_error_response(str(e))

    def handle_generate(self):
        """处理AI生成请求（支持增量更新）"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            prompt = data.get('prompt', '')
            images = data.get('images', [])  # base64 images
            project_name = data.get('projectName', '未命名项目')
            form_data = data.get('formData', {})  # 用户输入的表单数据
            global_data = form_data.get('global', {}) if isinstance(form_data, dict) else {}
            design_system_id = data.get('designSystemId') or global_data.get('designSystemId') or ''
            skill_id = data.get('skillId') or global_data.get('skillId') or DEFAULT_SKILL_ID

            # 增量更新参数
            is_incremental = data.get('incremental', False)
            source_project_id = data.get('sourceProjectId', None)
            changes = data.get('changes', None)

            if not prompt:
                self.send_error_response("缺少 prompt")
                return

            print(f"[生成] 项目: {project_name}, 图片数: {len(images)}, 增量模式: {is_incremental}")

            # 生成项目ID（日期时间_英文名）
            project_id = generate_project_id(project_name)
            project_folder = os.path.join(PROJECTS_DIR, project_id)
            os.makedirs(project_folder, exist_ok=True)

            # 保存用户上传的参考图片
            ref_images_folder = os.path.join(project_folder, 'reference')
            os.makedirs(ref_images_folder, exist_ok=True)

            reused_pages = 0
            source_html_content = None

            # ==================== 增量更新处理 ====================
            if is_incremental and source_project_id and changes:
                source_folder = os.path.join(PROJECTS_DIR, source_project_id)

                # 检查是否完全无变化
                if not changes.get('hasChanges', True):
                    print(f"[增量] 无变化，复制原项目")
                    return self.copy_project(source_project_id, project_name)

                # 复制原项目的reference图片（未变化的页面）
                source_ref_folder = os.path.join(source_folder, 'reference')
                if os.path.exists(source_ref_folder):
                    import shutil
                    for f in os.listdir(source_ref_folder):
                        src = os.path.join(source_ref_folder, f)
                        dst = os.path.join(ref_images_folder, f)
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    print(f"[增量] 复制原项目参考图片")

                # 读取原项目的HTML
                source_html_path = os.path.join(source_folder, 'index.html')
                if os.path.exists(source_html_path):
                    with open(source_html_path, 'r', encoding='utf-8') as f:
                        source_html_content = f.read()
                    print(f"[增量] 读取原项目HTML: {len(source_html_content)} 字符")

                # 复制原项目的images文件夹
                source_images_folder = os.path.join(source_folder, 'images')
                dest_images_folder = os.path.join(project_folder, 'images')
                if os.path.exists(source_images_folder):
                    import shutil
                    shutil.copytree(source_images_folder, dest_images_folder)
                    print(f"[增量] 复制原项目images文件夹")

                reused_pages = len(changes.get('pagesUnchanged', []))
                print(f"[增量] 未变化页面数: {reused_pages}, 变化页面数: {len(changes.get('pagesChanged', []))}")

            # 保存新上传的图片并记录文件名
            saved_image_names = []
            for i, img_base64 in enumerate(images):
                filename = f"ref_{i+1}"
                saved = save_base64_image(img_base64, ref_images_folder, filename)
                if saved:
                    saved_image_names.append(saved)
                    print(f"[保存参考图] {saved}")

            # 构建并保存record.json（用户输入记录）
            record = {
                'global': form_data.get('global', {}),
                'pages': [],
                'designSystemId': design_system_id,
                'skillId': skill_id,
                'createdAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'sourceProjectId': source_project_id if is_incremental else None
            }

            pages_data = form_data.get('pages', [])
            page_records, image_manifest = assign_saved_images_to_pages(pages_data, saved_image_names, skill_id)
            record['pages'] = page_records

            # 保存record.json
            record_path = os.path.join(project_folder, 'record.json')
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            print(f"[保存] record.json")

            # ==================== 决定是否调用AI ====================
            html_content = None

            if is_incremental and source_html_content and reused_pages > 0:
                # 部分页面可复用，但仍需要调用AI（因为有变化的页面）
                # 在prompt中提示AI参考原有内容
                enhanced_prompt = prompt + image_manifest + f"\n\n# 重要提示\n这是一个增量更新任务。原项目中有{reused_pages}个页面内容未变化。请保持整体风格一致，重点关注变化的部分。"
                print(f"[增量] 使用增强prompt调用AI")
                composed_prompt = compose_generation_prompt(enhanced_prompt, design_system_id, skill_id)
                html_content = self.call_ai_model(composed_prompt, images)
            else:
                # 正常调用AI
                composed_prompt = compose_generation_prompt(prompt + image_manifest, design_system_id, skill_id)
                html_content = self.call_ai_model(composed_prompt, images)

            if not html_content:
                self.send_error_response("AI未返回有效内容")
                return

            # 下载HTML中的外部图片并替换URL
            print("[处理] 下载HTML中的外部图片...")
            html_content = download_html_images(html_content, project_folder)

            # 注入页面切换消息监听器（用于 viewer.html 的页面导航）
            html_content = self.inject_page_navigation_listener(html_content)

            # 保存 HTML
            html_path = os.path.join(project_folder, 'index.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 从HTML中提取title作为项目名称
            html_title = extract_title_from_html(html_content)
            if html_title and html_title != project_name:
                print(f"[提取] HTML title: {html_title}")
                # 使用HTML中的title重新生成项目ID
                new_project_id = generate_project_id(html_title)
                new_project_folder = os.path.join(PROJECTS_DIR, new_project_id)

                # 重命名文件夹
                if not os.path.exists(new_project_folder):
                    import shutil
                    shutil.move(project_folder, new_project_folder)
                    project_folder = new_project_folder
                    project_id = new_project_id
                    project_name = html_title
                    print(f"[重命名] 项目文件夹: {project_id}")

            # 保存 prompt (用于调试)
            prompt_path = os.path.join(project_folder, 'prompt.txt')
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(composed_prompt)

            # 获取当前选中的模型名称
            current_model = get_selected_model()
            current_model_name = current_model.get('name', '') if current_model else ''

            # 更新项目列表
            projects = self.load_projects()
            new_project = {
                'id': project_id,
                'name': project_name,
                'model_name': current_model_name,
                'url': f'/projects/{project_id}/index.html',
                'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            # 检查是否已存在（避免重复）
            existing_idx = next((i for i, p in enumerate(projects) if p['id'] == project_id), None)
            if existing_idx is not None:
                projects[existing_idx] = new_project
            else:
                projects.insert(0, new_project)
            self.save_projects(projects)

            # 记录项目归属
            cur_user = self.get_current_user()
            if cur_user:
                db.set_project_owner(project_id, cur_user['id'])

            print(f"[完成] 项目已保存: {project_folder}")

            # 返回结果，包含增量信息
            response_data = {
                'success': True,
                'project': new_project,
                'incremental': is_incremental,
                'reusedPages': reused_pages
            }
            self.send_json_response(response_data)

        except Exception as e:
            print(f"[错误] 生成失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def handle_generate_async(self):
        """异步处理AI生成请求：立即返回项目信息，后台线程完成生成"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            prompt = data.get('prompt', '')
            images = data.get('images', [])
            project_name = data.get('projectName', '未命名项目')
            form_data = data.get('formData', {})
            global_data = form_data.get('global', {}) if isinstance(form_data, dict) else {}
            design_system_id = data.get('designSystemId') or global_data.get('designSystemId') or ''
            skill_id = data.get('skillId') or global_data.get('skillId') or DEFAULT_SKILL_ID
            is_incremental = data.get('incremental', False)
            source_project_id = data.get('sourceProjectId', None)
            changes = data.get('changes', None)

            if not prompt:
                self.send_error_response("缺少 prompt")
                return

            # 生成项目ID
            project_id = generate_project_id(project_name)
            project_folder = os.path.join(PROJECTS_DIR, project_id)
            os.makedirs(project_folder, exist_ok=True)

            # 保存参考图片
            ref_images_folder = os.path.join(project_folder, 'reference')
            os.makedirs(ref_images_folder, exist_ok=True)

            saved_image_names = []
            for i, img_base64 in enumerate(images):
                filename = f"ref_{i+1}"
                saved = save_base64_image(img_base64, ref_images_folder, filename)
                if saved:
                    saved_image_names.append(saved)

            # 创建初始 record.json
            record = {
                'global': form_data.get('global', {}),
                'pages': [],
                'designSystemId': design_system_id,
                'skillId': skill_id,
                'status': STATUS_GENERATING,
                'createdAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'sourceProjectId': source_project_id if is_incremental else None
            }

            pages_data = form_data.get('pages', [])
            page_records, image_manifest = assign_saved_images_to_pages(pages_data, saved_image_names, skill_id)
            record['pages'] = page_records

            record_path = os.path.join(project_folder, 'record.json')
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            # 保存 prompt
            prompt_path = os.path.join(project_folder, 'prompt.txt')
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(compose_generation_prompt(prompt + image_manifest, design_system_id, skill_id))

            # 获取当前选中的模型名称
            current_model = get_selected_model()
            current_model_name = current_model.get('name', '') if current_model else ''

            # 更新项目列表（带 generating 状态）
            projects = self.load_projects()
            new_project = {
                'id': project_id,
                'name': project_name,
                'model_name': current_model_name,
                'status': STATUS_GENERATING,
                'url': f'/projects/{project_id}/index.html',
                'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            existing_idx = next((i for i, p in enumerate(projects) if p.get('id') == project_id), None)
            if existing_idx is not None:
                projects[existing_idx] = new_project
            else:
                projects.insert(0, new_project)
            self.save_projects(projects)

            # 记录项目归属
            cur_user = self.get_current_user()
            if cur_user:
                db.set_project_owner(project_id, cur_user['id'])

            # 注册异步任务
            with tasks_lock:
                generating_tasks[project_id] = {
                    'status': STATUS_GENERATING,
                    'progress': 0,
                    'error': '',
                    'startedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

            # 启动后台线程
            def generate_in_background():
                try:
                    print(f"[异步] 开始后台生成: {project_id}")

                    # 更新进度
                    with tasks_lock:
                        generating_tasks[project_id]['progress'] = 10

                    # 增量处理
                    source_html_content = None
                    reused_pages = 0
                    if is_incremental and source_project_id and changes:
                        source_folder = os.path.join(PROJECTS_DIR, source_project_id)
                        source_html_path = os.path.join(source_folder, 'index.html')
                        if os.path.exists(source_html_path):
                            with open(source_html_path, 'r', encoding='utf-8') as f:
                                source_html_content = f.read()

                        # 复制原项目图片
                        source_images_folder = os.path.join(source_folder, 'images')
                        dest_images_folder = os.path.join(project_folder, 'images')
                        if os.path.exists(source_images_folder):
                            import shutil
                            if not os.path.exists(dest_images_folder):
                                shutil.copytree(source_images_folder, dest_images_folder)

                        reused_pages = len(changes.get('pagesUnchanged', []))

                    with tasks_lock:
                        generating_tasks[project_id]['progress'] = 20

                    # 调用AI（这里复用现有逻辑）
                    enhanced_prompt = prompt
                    if is_incremental and source_html_content and reused_pages > 0:
                        enhanced_prompt += f"\n\n# 重要提示\n这是一个增量更新任务。原项目中有{reused_pages}个页面内容未变化。请保持整体风格一致。"
                    composed_prompt = compose_generation_prompt(enhanced_prompt + image_manifest, design_system_id, skill_id)

                    # 使用类似 call_ai_model 的逻辑
                    html_content = self._call_ai_for_async(composed_prompt, images)

                    with tasks_lock:
                        generating_tasks[project_id]['progress'] = 80

                    if not html_content:
                        raise Exception("AI未返回有效内容")

                    # 下载图片
                    html_content = download_html_images(html_content, project_folder)

                    # 注入导航监听器
                    html_content = self.inject_page_navigation_listener(html_content)

                    # 保存HTML
                    html_path = os.path.join(project_folder, 'index.html')
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)

                    # 更新项目状态
                    projects = self.load_projects()
                    for p in projects:
                        if p['id'] == project_id:
                            p['status'] = None  # 清除 generating 状态
                            break
                    self.save_projects(projects)

                    # 更新record.json状态
                    if os.path.exists(record_path):
                        with open(record_path, 'r', encoding='utf-8') as f:
                            record = json.load(f)
                        record['status'] = STATUS_COMPLETED
                        with open(record_path, 'w', encoding='utf-8') as f:
                            json.dump(record, f, ensure_ascii=False, indent=2)

                    with tasks_lock:
                        generating_tasks[project_id]['status'] = STATUS_COMPLETED
                        generating_tasks[project_id]['progress'] = 100

                    print(f"[异步] 生成完成: {project_id}")

                except Exception as e:
                    print(f"[异步错误] {project_id}: {e}")
                    import traceback
                    traceback.print_exc()

                    # 更新失败状态
                    with tasks_lock:
                        generating_tasks[project_id]['status'] = STATUS_FAILED
                        generating_tasks[project_id]['error'] = str(e)

                    mark_project_failed(project_id, str(e))

            # 启动线程
            thread = threading.Thread(target=generate_in_background, daemon=True)
            thread.start()

            print(f"[异步] 项目已创建，后台生成中: {project_id}")
            self.send_json_response({
                'success': True,
                'project': new_project,
                'async': True
            })

        except Exception as e:
            print(f"[错误] 异步生成启动失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def _call_ai_for_async(self, prompt, images):
        """异步生成专用的AI调用（复用现有逻辑）"""
        return self.call_ai_model(prompt, images)

    def copy_project(self, source_project_id, new_project_name):
        """复制项目（当内容完全无变化时）"""
        try:
            import shutil

            source_folder = os.path.join(PROJECTS_DIR, source_project_id)
            if not os.path.exists(source_folder):
                self.send_error_response(f"源项目不存在: {source_project_id}")
                return

            # 生成新项目ID
            project_id = generate_project_id(new_project_name)
            project_folder = os.path.join(PROJECTS_DIR, project_id)

            # 如果目标目录已存在，先删除
            if os.path.exists(project_folder):
                shutil.rmtree(project_folder)

            # 复制整个文件夹
            shutil.copytree(source_folder, project_folder)
            print(f"[复制] {source_folder} -> {project_folder}")

            # 更新record.json的时间戳
            record_path = os.path.join(project_folder, 'record.json')
            if os.path.exists(record_path):
                with open(record_path, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                record['createdAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                record['copiedFrom'] = source_project_id
                with open(record_path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)

            # 更新项目列表
            projects = self.load_projects()
            new_project = {
                'id': project_id,
                'name': new_project_name,
                'url': f'/projects/{project_id}/index.html',
                'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            # 检查是否已存在（避免重复）
            existing_idx = next((i for i, p in enumerate(projects) if p['id'] == project_id), None)
            if existing_idx is not None:
                projects[existing_idx] = new_project
            else:
                projects.insert(0, new_project)
            self.save_projects(projects)

            # 记录项目归属
            cur_user = self.get_current_user()
            if cur_user:
                db.set_project_owner(project_id, cur_user['id'])

            print(f"[完成] 项目已复制: {project_folder} (0 API调用)")
            self.send_json_response({
                'success': True,
                'project': new_project,
                'incremental': True,
                'reusedPages': 'all',
                'message': '内容无变化，已复制原项目'
            })

        except Exception as e:
            print(f"[错误] 复制失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def call_ai_model(self, prompt, images):
        """调用AI大模型 (使用 requests 库)"""
        try:
            # 添加图片。历史记录里可能有扩展名是 png、实际内容却是 XML/SVG 的文件，这里统一过滤。
            valid_images = []
            skipped_images = 0
            for img_base64 in images:
                normalized = normalize_supported_image_data_url(img_base64)
                if normalized:
                    valid_images.append(normalized)
                else:
                    skipped_images += 1

            if skipped_images:
                print(f"[AI] 已跳过 {skipped_images} 张不支持的参考图")

            if len(valid_images) > MAX_AI_IMAGES_PER_REQUEST:
                skipped_extra = len(valid_images) - MAX_AI_IMAGES_PER_REQUEST
                valid_images = valid_images[:MAX_AI_IMAGES_PER_REQUEST]
                print(f"[AI] 参考图超过网关上限，已仅发送前 {MAX_AI_IMAGES_PER_REQUEST} 张，跳过 {skipped_extra} 张")
            print(f"[AI] 有效参考图: {len(valid_images)}/{len(images)}")

            image_content = []
            for img_base64 in valid_images:
                image_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_base64}
                })
            text_content = [{
                "type": "text",
                "text": prompt
            }]

            # 豆包/火山兼容接口的视觉示例通常把 image_url 放在 text 前；
            # 其他模型保留原来的 text-first 顺序。
            selected_model = get_selected_model()
            model_name = selected_model.get('model', API_CONFIG.get('model', 'gpt-4'))
            model_name_lower = model_name.lower()
            if 'doubao' in model_name_lower or 'seed' in model_name_lower:
                user_content = image_content + text_content
            else:
                user_content = text_content + image_content

            # 从配置读取 system prompt
            system_prompt = AI_OPTIONS.get('system_prompt',
                'You are a professional UI/UX Developer. Generate complete, standalone HTML prototypes with realistic data.')

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]

            # 动态获取当前选中模型配置
            base_url = selected_model.get('base_url', API_CONFIG.get('base_url', ''))
            api_key = selected_model.get('api_key', API_CONFIG.get('api_key', ''))
            print(f"[AI] 使用模型: {selected_model.get('name', model_name)} ({model_name})")

            # 准备请求数据
            payload = {
                "model": model_name,
                "messages": messages,
                "max_tokens": get_model_max_tokens(model_name),
                "temperature": AI_OPTIONS.get('temperature', 0.7)
            }

            url = f"{base_url}/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {api_key}"
            }

            timeout = AI_OPTIONS.get('timeout', 300)
            heavy_request = len(prompt) > HEAVY_AI_PROMPT_CHARS or len(valid_images) > HEAVY_AI_IMAGE_COUNT
            if heavy_request:
                timeout = min(timeout, HEAVY_AI_TIMEOUT_SECONDS)
                print(f"[AI] 检测到重型请求：prompt={len(prompt)}字符, images={len(valid_images)}，超时收紧到 {timeout}s，仅尝试1次")
            print(f"[AI] 正在调用大模型... (超时: {timeout}s)")

            result = None
            max_retries = 1 if heavy_request else 3
            last_error = None

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"[AI] 重试第 {attempt+1} 次...")

                    # 每次重试创建新 Session，确保无状态污染
                    session = requests.Session()
                    session.trust_env = False # 强制直连，不使用系统代理 (针对国内 API 域名优化)

                    # 伪装浏览器，并禁用长连接
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Connection': 'close'
                    })

                    # 使用 session 发送请求，verify=False 忽略 SSL 验证
                    response = session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=timeout,
                        verify=False
                    )

                    response.raise_for_status() # 检查 HTTP 错误
                    result = response.json()
                    break # 成功则跳出循环
                except requests.HTTPError as e:
                    status_code = e.response.status_code if e.response is not None else 'unknown'
                    body = e.response.text if e.response is not None else ''
                    body = body[:1500]
                    message = f"AI接口HTTP {status_code}: {body}"
                    print(f"[AI] 调用失败 (第 {attempt+1}/{max_retries} 次): {message}")
                    last_error = Exception(message)
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)
                except Exception as e:
                    print(f"[AI] 调用失败 (第 {attempt+1}/{max_retries} 次): {e}")
                    last_error = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)

            # 如果 requests 全部失败，尝试使用 curl 命令行兜底。重型请求不兜底，避免后台长时间假死。
            if not result:
                if heavy_request:
                    raise last_error or Exception("AI重型请求超时或失败")
                print("[AI] 尝试使用 curl 命令行兜底...")
                result = self.call_ai_model_via_curl(url, headers, payload, timeout)

            if not result:
                raise last_error

            choices = result.get('choices') if isinstance(result, dict) else None
            if not choices:
                error_message = extract_ai_error_message(result)
                print(f"[AI错误] 返回缺少 choices: {error_message}")
                raise Exception(f"AI返回异常：{error_message}")

            content = choices[0].get('message', {}).get('content', '')
            finish_reason = choices[0].get('finish_reason', '')
            if not content:
                raise Exception("AI返回异常：choices 中没有可用内容")

            print(f"[AI] 响应长度: {len(content)} 字符, finish_reason: {finish_reason}")

            if finish_reason == 'length':
                print("[警告] AI响应可能被截断!")

            # 提取HTML代码
            return self.extract_html(content)

        except Exception as e:
            print(f"[AI错误] {e}")
            import traceback
            traceback.print_exc()
            raise

    def call_ai_model_via_curl(self, url, headers, payload, timeout):
        """使用系统 curl 命令调用 AI (解决 SSL 问题)"""
        try:
            # 将 payload 写入临时文件以避免命令行长度限制和转义问题
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix='.json') as f:
                json.dump(payload, f, ensure_ascii=False)
                temp_payload_path = f.name

            # 构建 curl 命令
            # -k: 忽略 SSL 验证
            # -s: 静默模式
            cmd = ['curl', '-k', '-s', '-X', 'POST', url]

            # 添加 header
            for k, v in headers.items():
                cmd.extend(['-H', f'{k}: {v}'])

            # 添加 body 文件
            cmd.extend(['-d', f'@{temp_payload_path}'])

            print(f"[AI] 执行 curl 命令: {' '.join(cmd[:6])} ...")

            # 执行命令
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )

            # 清理临时文件
            try:
                os.remove(temp_payload_path)
            except:
                pass

            if process.returncode != 0:
                print(f"[curl错误] returncode: {process.returncode}, stderr: {process.stderr}")
                return None

            # 解析结果
            try:
                return json.loads(process.stdout)
            except json.JSONDecodeError:
                print(f"[curl错误] 响应不是JSON: {process.stdout[:1500]}")
                return {
                    'error': {
                        'message': process.stdout[:1500] or process.stderr[:1500] or 'curl 返回空响应'
                    }
                }

        except Exception as e:
            print(f"[curl异常] {e}")
            return None

    def extract_html(self, content):
        """从AI响应中提取HTML代码"""
        # 尝试匹配 ```html 代码块
        html_match = re.search(r'```(?:html|HTML)?\s*\n([\s\S]*?)```', content)
        if html_match:
            html = html_match.group(1).strip()
            if '<!DOCTYPE html>' in html or '<html' in html:
                return html

        # 直接查找HTML文档
        doctype_idx = content.find('<!DOCTYPE html>')
        if doctype_idx != -1:
            end_idx = content.rfind('</html>')
            if end_idx != -1:
                return content[doctype_idx:end_idx + 7]

        # 返回原始内容作为预览
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>生成结果</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 p-8">
    <div class="bg-white rounded-lg shadow p-6 max-w-4xl mx-auto">
        <h1 class="text-xl font-bold text-red-600 mb-4">⚠️ HTML提取失败</h1>
        <p class="text-gray-600 mb-4">AI返回内容格式不符合预期：</p>
        <pre class="bg-gray-50 p-4 rounded text-sm overflow-auto">{content[:5000]}</pre>
    </div>
</body>
</html>'''

    def handle_save_project(self):
        """保存项目（用于手动保存）"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            html_content = data.get('htmlContent')
            project_meta = data.get('projectData')

            if not html_content or not project_meta:
                self.send_error_response("Missing htmlContent or projectData")
                return

            project_id = project_meta.get('id', generate_project_id(project_meta.get('name', 'project')))
            project_folder = os.path.join(PROJECTS_DIR, project_id)
            os.makedirs(project_folder, exist_ok=True)

            file_path = os.path.join(project_folder, 'index.html')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            projects = self.load_projects()
            existing_idx = next((i for i, p in enumerate(projects) if p['id'] == project_id), None)

            new_record = {
                "id": project_id,
                "name": project_meta['name'],
                "url": f"/projects/{project_id}/index.html",
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            if existing_idx is not None:
                projects[existing_idx] = new_record
            else:
                projects.insert(0, new_record)

            self.save_projects(projects)
            self.send_json_response({'success': True, 'project': new_record})

        except Exception as e:
            self.send_error_response(str(e))

    def handle_delete_project(self):
        """删除项目（移动到回收站）"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('id')
            if not project_id:
                self.send_error_response("Missing project ID")
                return

            projects = self.load_projects()
            project = next((p for p in projects if p['id'] == project_id), None)

            if project:
                # 移动文件夹到deleted目录
                project_folder = os.path.join(PROJECTS_DIR, project_id)
                deleted_folder = os.path.join(DELETED_DIR, project_id)
                if os.path.exists(project_folder):
                    import shutil
                    # 如果目标已存在，先删除
                    if os.path.exists(deleted_folder):
                        shutil.rmtree(deleted_folder)
                    shutil.move(project_folder, deleted_folder)
                    print(f"[删除] 项目移动到回收站: {project_id}")

                # 从项目列表移除
                projects = [p for p in projects if p['id'] != project_id]
                self.save_projects(projects)

                # 添加到已删除列表
                deleted_projects = self.load_deleted_projects()
                project['deletedAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                project['url'] = f'/deleted/{project_id}/index.html'
                deleted_projects.insert(0, project)
                self.save_deleted_projects(deleted_projects)

                # 清理项目归属和分享记录
                db.delete_project_ownership(project_id)

            self.send_json_response({'success': True})

        except Exception as e:
            self.send_error_response(str(e))

    def handle_rename_project(self):
        """重命名项目（同时重命名文件夹）"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('id')
            new_name = data.get('newName', '').strip()

            if not project_id:
                self.send_error_response("Missing project ID")
                return
            if not new_name:
                self.send_error_response("Missing new name")
                return

            projects = self.load_projects()
            project = next((p for p in projects if p['id'] == project_id), None)

            if not project:
                self.send_error_response("Project not found")
                return

            old_name = project['name']
            old_folder = os.path.join(PROJECTS_DIR, project_id)

            # 生成新的文件夹名称（新名称 + 原时间戳）
            # 从原ID中提取时间戳部分
            parts = project_id.rsplit('_', 2)
            if len(parts) >= 3:
                timestamp = '_'.join(parts[-2:])  # 例如 "20260114_11-20-20"
            else:
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H-%M-%S')

            # 处理新名称，移除不安全字符
            safe_new_name = re.sub(r'[\\/:*?"<>|]', '', new_name)
            safe_new_name = safe_new_name.replace(' ', '_')
            if len(safe_new_name) > 30:
                safe_new_name = safe_new_name[:30]

            new_project_id = f"{safe_new_name}_{timestamp}"
            new_folder = os.path.join(PROJECTS_DIR, new_project_id)

            # 重命名文件夹
            if os.path.exists(old_folder) and old_folder != new_folder:
                import shutil
                if os.path.exists(new_folder):
                    # 如果目标已存在，添加随机后缀
                    new_project_id = f"{safe_new_name}_{timestamp}_{datetime.datetime.now().strftime('%S')}"
                    new_folder = os.path.join(PROJECTS_DIR, new_project_id)
                shutil.move(old_folder, new_folder)
                print(f"[重命名文件夹] {project_id} -> {new_project_id}")

            # 更新项目信息
            project['id'] = new_project_id
            project['name'] = new_name
            project['url'] = f'/projects/{new_project_id}/index.html'
            self.save_projects(projects)

            print(f"[重命名] {old_name} -> {new_name}")
            self.send_json_response({'success': True, 'project': project})

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def handle_restore_project(self):
        """恢复已删除的项目"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('id')
            if not project_id:
                self.send_error_response("Missing project ID")
                return

            deleted_projects = self.load_deleted_projects()
            project = next((p for p in deleted_projects if p['id'] == project_id), None)

            if not project:
                self.send_error_response("Deleted project not found")
                return

            # 移动文件夹回projects目录
            deleted_folder = os.path.join(DELETED_DIR, project_id)
            project_folder = os.path.join(PROJECTS_DIR, project_id)

            if os.path.exists(deleted_folder):
                import shutil
                # 如果目标已存在，先删除
                if os.path.exists(project_folder):
                    shutil.rmtree(project_folder)
                shutil.move(deleted_folder, project_folder)
                print(f"[恢复] 项目从回收站恢复: {project_id}")

            # 从已删除列表移除
            deleted_projects = [p for p in deleted_projects if p['id'] != project_id]
            self.save_deleted_projects(deleted_projects)

            # 添加回项目列表
            projects = self.load_projects()
            # 移除deletedAt字段，更新url
            if 'deletedAt' in project:
                del project['deletedAt']
            project['url'] = f'/projects/{project_id}/index.html'
            # 检查是否已存在（避免重复）
            existing_idx = next((i for i, p in enumerate(projects) if p['id'] == project_id), None)
            if existing_idx is not None:
                projects[existing_idx] = project
            else:
                projects.insert(0, project)
            self.save_projects(projects)

            self.send_json_response({'success': True, 'project': project})

        except Exception as e:
            self.send_error_response(str(e))

    def handle_copy_project(self):
        """复制项目"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            source_project_id = data.get('sourceProjectId')
            new_project_name = data.get('newProjectName', '').strip()

            if not source_project_id:
                self.send_error_response("缺少源项目ID")
                return
            if not new_project_name:
                self.send_error_response("缺少新项目名称")
                return

            source_folder = os.path.join(PROJECTS_DIR, source_project_id)
            if not os.path.exists(source_folder):
                self.send_error_response("源项目不存在")
                return

            # 生成新项目ID
            new_project_id = generate_project_id(new_project_name)
            new_folder = os.path.join(PROJECTS_DIR, new_project_id)

            # 复制整个文件夹
            import shutil
            shutil.copytree(source_folder, new_folder)
            print(f"[复制项目] {source_project_id} -> {new_project_id}")

            # 更新项目列表 (load_projects会自动同步新文件夹)
            projects = self.load_projects()
            new_project = {
                'id': new_project_id,
                'name': new_project_name,
                'url': f'/projects/{new_project_id}/index.html',
                'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            # 检查是否已被load_projects自动添加，避免重复
            existing_idx = next((i for i, p in enumerate(projects) if p['id'] == new_project_id), None)
            if existing_idx is not None:
                # 更新名称为用户指定的名称
                projects[existing_idx] = new_project
            else:
                projects.insert(0, new_project)
            self.save_projects(projects)

            # 记录项目归属
            cur_user = self.get_current_user()
            if cur_user:
                db.set_project_owner(new_project_id, cur_user['id'])

            self.send_json_response({'success': True, 'project': new_project})

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def handle_get_deleted_projects(self):
        """获取已删除项目列表"""
        try:
            deleted_projects = self.load_deleted_projects()
            self.send_json_response({'success': True, 'projects': deleted_projects})
        except Exception as e:
            self.send_error_response(str(e))

    def load_projects(self):
        """加载项目列表（自动与文件夹同步）"""
        projects = []
        if os.path.exists(PROJECTS_FILE):
            try:
                with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
                    projects = json.load(f)
            except:
                pass

        # 扫描projects文件夹获取实际存在的项目
        # 包含有 index.html 的项目 和 有 record.json 的占位项目
        existing_folders = set()
        folders_with_html = set()  # 有 index.html 的文件夹
        if os.path.exists(PROJECTS_DIR):
            for folder_name in os.listdir(PROJECTS_DIR):
                folder_path = os.path.join(PROJECTS_DIR, folder_name)
                if os.path.isdir(folder_path):
                    has_html = os.path.exists(os.path.join(folder_path, 'index.html'))
                    has_record = os.path.exists(os.path.join(folder_path, 'record.json'))
                    if has_html or has_record:
                        existing_folders.add(folder_name)
                    if has_html:
                        folders_with_html.add(folder_name)

        original_count = len(projects)
        original_ids = [p['id'] for p in projects]
        status_updated = False

        # 1. 移除不存在的项目
        projects = [p for p in projects if p['id'] in existing_folders]

        # 2. 去重：确保每个ID只出现一次（保留第一个）
        seen_ids = set()
        unique_projects = []
        for p in projects:
            if p['id'] not in seen_ids:
                seen_ids.add(p['id'])
                unique_projects.append(p)
        projects = unique_projects

        # 3. 检查并更新占位项目状态（pending_external -> 正常）
        for p in projects:
            if p.get('status') == 'pending_external' and p['id'] in folders_with_html:
                # 占位项目现在有 index.html 了，更新状态
                print(f"[状态更新] 项目 {p['id']} 已完成外部生成")
                p['status'] = None  # 清除 pending 状态
                p['name'] = p['name'].replace(' (待外部生成)', '')  # 移除后缀
                p['url'] = f"/projects/{p['id']}/index.html"  # 更新URL
                status_updated = True

        # 4. 添加新发现的项目（不在列表中的文件夹）
        existing_ids = {p['id'] for p in projects}
        new_added = False
        for folder_name in existing_folders:
            if folder_name not in existing_ids:
                # 从文件夹名称提取项目名和日期
                parts = folder_name.rsplit('_', 2)
                if len(parts) >= 3:
                    name = parts[0]
                    date_part = parts[1]
                    time_part = parts[2]

                    # 解析日期
                    try:
                        year = date_part[:4]
                        month = date_part[4:6]
                        day = date_part[6:8]
                        date_str = f"{year}-{month}-{day}"
                    except:
                        date_str = datetime.datetime.now().strftime('%Y-%m-%d')

                    # 解析时间 (format: 4-15-23pm)
                    try:
                        # 移除am/pm后缀
                        is_pm = time_part.lower().endswith('pm')
                        time_pure = time_part[:-2] if (time_part.lower().endswith('am') or time_part.lower().endswith('pm')) else time_part

                        t_parts = time_pure.split('-')
                        if len(t_parts) >= 3:
                            h = int(t_parts[0])
                            m = int(t_parts[1])
                            s = int(t_parts[2])

                            # 转换12小时制到24小时制
                            if is_pm and h < 12:
                                h += 12
                            elif not is_pm and h == 12:  # 12am is 00:00
                                h = 0

                            time_str = f"{h:02d}:{m:02d}:{s:02d}"
                        else:
                            time_str = "00:00:00"
                    except:
                        time_str = "00:00:00"

                    date = f"{date_str} {time_str}"
                else:
                    name = folder_name
                    date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                new_project = {
                    'id': folder_name,
                    'name': name,
                    'url': f'/projects/{folder_name}/index.html',
                    'date': date
                }
                projects.append(new_project)
                new_added = True
                print(f"[同步] 发现新项目: {folder_name}")

        # 按日期排序（新的在前）
        projects.sort(key=lambda p: p.get('date', ''), reverse=True)

        # 只在有变化时保存
        new_ids = [p['id'] for p in projects]
        if len(projects) != original_count or new_ids != original_ids or new_added or status_updated:
            self.save_projects(projects)
            print(f"[同步] 项目列表已更新: {len(projects)}个项目")

        return projects

    def save_projects(self, projects):
        """保存项目列表"""
        deduped = []
        seen = set()
        for project in projects:
            project_id = project.get('id') if isinstance(project, dict) else None
            if project_id and project_id in seen:
                continue
            if project_id:
                seen.add(project_id)
            deduped.append(project)
        with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(deduped, f, ensure_ascii=False, indent=2)

    def load_deleted_projects(self):
        """加载已删除项目列表"""
        if os.path.exists(DELETED_PROJECTS_FILE):
            try:
                with open(DELETED_PROJECTS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_deleted_projects(self, projects):
        """保存已删除项目列表"""
        with open(DELETED_PROJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)

    def inject_page_navigation_listener(self, html_content):
        """在 HTML 中注入页面切换消息监听器"""

        # 1. 首先在 Vue 的 return 语句前注入暴露代码
        # 查找模式: "return {" 前插入 "window.currentPage = currentPage;"
        expose_pattern = r'(return\s*\{\s*\n?\s*currentPage)'
        expose_replacement = r'// 暴露 currentPage 到 window (由原型生成器注入)\n                window.currentPage = currentPage;\n\n                \1'

        if re.search(expose_pattern, html_content):
            html_content = re.sub(expose_pattern, expose_replacement, html_content, count=1)
            print("[注入] currentPage 已暴露到 window")

        # 2. 注入消息监听器
        listener_script = '''
<!-- 页面导航监听器 (由原型生成器自动注入) -->
<script>
(function() {
    // 等待 Vue 应用挂载完成
    var checkInterval = setInterval(function() {
        if (window.currentPage) {
            clearInterval(checkInterval);
            console.log('[原型] currentPage 已就绪');
        }
    }, 100);

    // 监听来自 viewer 的页面切换消息
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'navigateTo') {
            var pageName = event.data.page;
            console.log('[原型] 收到页面切换请求:', pageName);

            // 使用 window.currentPage (Vue ref)
            if (window.currentPage && window.currentPage.value !== undefined) {
                window.currentPage.value = pageName;
                console.log('[原型] 已切换到页面:', pageName);
            }

            // 通知父窗口页面已切换
            if (window.parent !== window) {
                window.parent.postMessage({ type: 'pageChange', page: pageName }, '*');
            }
        }
    });

    // 定期向父窗口报告当前页面
    if (window.parent !== window) {
        setInterval(function() {
            if (window.currentPage && window.currentPage.value) {
                window.parent.postMessage({ type: 'pageChange', page: window.currentPage.value }, '*');
            }
        }, 500);
    }
})();
</script>
'''

        # 在 </body> 标签前注入
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', listener_script + '\n</body>')
        elif '</html>' in html_content:
            html_content = html_content.replace('</html>', listener_script + '\n</html>')
        else:
            html_content += listener_script

        print("[注入] 页面导航监听器已添加")
        return html_content

    # ==================== PRD 相关 API ====================

    def handle_prd_save(self):
        """保存 PRD 文档"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId')
            page_name = data.get('pageName', 'default')
            content = data.get('content', '')

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            # 创建 PRD 目录
            prd_dir = os.path.join(PROJECTS_DIR, project_id, 'prd')
            os.makedirs(prd_dir, exist_ok=True)

            # 保存 PRD 文件
            # 清理页面名称，防止路径注入
            safe_page_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', page_name)
            prd_file = os.path.join(prd_dir, f'{safe_page_name}.md')

            with open(prd_file, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"[PRD] 保存: {project_id}/{safe_page_name}.md")
            self.send_json_response({'success': True, 'file': f'{safe_page_name}.md'})

        except Exception as e:
            print(f"[PRD错误] 保存失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    # ==================== 模型管理 API ====================

    def handle_get_models(self):
        """获取模型列表和当前选中模型"""
        try:
            data = load_models()
            self.send_json_response(data)
        except Exception as e:
            self.send_error_response(str(e))

    def handle_model_select(self):
        """切换选中的模型"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            req = json.loads(body.decode('utf-8'))
            model_id = req.get('id', '')

            data = load_models()
            # 验证模型存在
            found = any(m['id'] == model_id for m in data.get('models', []))
            if not found:
                self.send_error_response("模型不存在")
                return

            data['selected_model_id'] = model_id
            save_models(data)

            selected = next(m for m in data['models'] if m['id'] == model_id)
            print(f"[模型] 切换到: {selected.get('name', model_id)}")
            self.send_json_response({'success': True, 'selected': selected})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_model_save(self):
        """添加或编辑模型"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            model_info = json.loads(body.decode('utf-8'))

            if not model_info.get('id'):
                self.send_error_response("缺少模型 ID")
                return

            data = load_models()
            models = data.get('models', [])

            # 查找是否已存在
            existing_idx = next((i for i, m in enumerate(models) if m['id'] == model_info['id']), None)
            if existing_idx is not None:
                models[existing_idx] = model_info
                print(f"[模型] 更新: {model_info.get('name', model_info['id'])}")
            else:
                models.append(model_info)
                print(f"[模型] 新增: {model_info.get('name', model_info['id'])}")

            data['models'] = models
            save_models(data)
            self.send_json_response({'success': True, 'model': model_info})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_model_delete(self):
        """删除模型"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            req = json.loads(body.decode('utf-8'))
            model_id = req.get('id', '')

            data = load_models()
            models = data.get('models', [])

            if len(models) <= 1:
                self.send_error_response("至少保留一个模型")
                return

            data['models'] = [m for m in models if m['id'] != model_id]

            # 如果删除的是当前选中的，自动选第一个
            if data.get('selected_model_id') == model_id and data['models']:
                data['selected_model_id'] = data['models'][0]['id']

            save_models(data)
            print(f"[模型] 删除: {model_id}")
            self.send_json_response({'success': True})
        except Exception as e:
            self.send_error_response(str(e))

    # ==================== Inspector 微调 API ====================

    def handle_inspector_apply(self):
        """处理微调模式的 AI 修改请求"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId')
            user_request = data.get('userRequest', '')
            elements = data.get('elements', [])
            prompt = data.get('prompt', '')

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            if not user_request:
                self.send_error_response("缺少修改需求")
                return

            if not elements:
                self.send_error_response("未选中任何元素")
                return

            # 读取当前 HTML
            html_file = os.path.join(PROJECTS_DIR, project_id, 'index.html')
            if not os.path.exists(html_file):
                self.send_error_response("项目不存在")
                return

            with open(html_file, 'r', encoding='utf-8') as f:
                current_html = f.read()

            print(f"[Inspector] 收到微调请求: {project_id}")
            print(f"[Inspector] 选中元素数: {len(elements)}")
            print(f"[Inspector] 用户需求: {user_request}")

            # 构建 AI Prompt
            elements_desc = "\n".join([
                f"元素 {i+1}:\n- 选择器: {el.get('selector', 'unknown')}\n- HTML:\n```html\n{el.get('html', '')}\n```"
                for i, el in enumerate(elements)
            ])

            ai_prompt = f"""你是一个精准的 HTML 修改专家。请根据用户的需求，精确修改指定的 HTML 元素。

## 当前完整 HTML
```html
{current_html}
```

## 需要修改的元素
{elements_desc}

## 用户修改需求
{user_request}

## 修改规则
1. 只修改上述指定的元素，不要修改其他任何代码
2. 保持页面整体风格和结构不变
3. 如果涉及样式修改，优先使用内联 style 或 Tailwind CSS 类
4. 返回修改后的完整 HTML 文档

请直接返回修改后的完整 HTML 代码（从 <!DOCTYPE html> 开始到 </html> 结束），不要有任何额外说明。"""

            # 调用 AI
            try:
                modified_html = self.call_ai_model(ai_prompt, [])

                if not modified_html or len(modified_html) < 100:
                    self.send_error_response("AI 返回内容无效")
                    return

                # 备份原文件
                backup_file = os.path.join(PROJECTS_DIR, project_id, 'index.html.bak')
                with open(backup_file, 'w', encoding='utf-8') as f:
                    f.write(current_html)
                print(f"[Inspector] 备份已创建: {backup_file}")

                # 保存修改后的 HTML
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(modified_html)

                print(f"[Inspector] HTML 已更新: {html_file}")
                self.send_json_response({
                    'success': True,
                    'message': '修改成功',
                    'backupFile': 'index.html.bak'
                })

            except Exception as ai_error:
                print(f"[Inspector] AI 调用失败: {ai_error}")
                import traceback
                traceback.print_exc()
                self.send_error_response(f"AI 调用失败: {str(ai_error)}")

        except Exception as e:
            print(f"[Inspector错误] {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def handle_server_info(self):
        """返回服务器运行时的基础目录信息，供前端动态构建文件路径"""
        try:
            projects_abs_path = os.path.abspath(PROJECTS_DIR)
            self.send_json_response({
                'projectsDir': projects_abs_path
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_pptx_parse(self):
        """解析上传的 PPTX，提取文字、图片和基础页面顺序。"""
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error_response("请上传 multipart/form-data 格式的 PPTX 文件")
                return

            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                self.send_error_response("缺少 multipart boundary")
                return

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            boundary = boundary_match.group(1).encode()
            parts = body.split(b'--' + boundary)

            filename = ''
            file_data = None
            for part in parts:
                if not part or part in (b'--\r\n', b'--'):
                    continue
                if part.startswith(b'\r\n'):
                    part = part[2:]
                if part.endswith(b'\r\n'):
                    part = part[:-2]

                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue

                headers = part[:header_end].decode('utf-8', errors='ignore')
                payload = part[header_end + 4:]
                filename_match = re.search(r'filename="([^"]+)"', headers)
                if filename_match:
                    filename = os.path.basename(filename_match.group(1))
                    file_data = payload
                    break

            if not file_data:
                self.send_error_response("没有收到 PPT 文件")
                return

            if not filename.lower().endswith('.pptx'):
                self.send_error_response("当前仅支持 .pptx。请先将 .ppt 另存为 .pptx 后上传。")
                return

            parsed = parse_pptx_bytes(file_data)
            parsed['success'] = True
            parsed['filename'] = filename
            self.send_json_response(parsed)
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_design_systems(self):
        """返回可选的 Open Design 设计系统列表"""
        try:
            self.send_json_response({
                'success': True,
                'designSystems': list_design_system_assets()
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_design_system(self, design_system_id):
        """返回单个 DESIGN.md 内容"""
        try:
            ds_id = safe_asset_id(design_system_id)
            if not ds_id:
                self.send_error_response("无效的 design system ID")
                return
            path = design_system_path(ds_id)
            body = read_text_file(path)
            if not body:
                self.send_error_response("Design system 不存在")
                return
            self.send_json_response({
                'success': True,
                'id': ds_id,
                'name': first_markdown_heading(body, ds_id),
                'body': body
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_skills(self):
        """返回可选的 Open Design skills 列表"""
        try:
            self.send_json_response({
                'success': True,
                'skills': list_skill_assets()
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_skill(self, skill_id):
        """返回单个 skill 的 SKILL.md 内容"""
        try:
            sid = safe_asset_id(skill_id)
            if not sid:
                self.send_error_response("无效的 skill ID")
                return
            path = skill_path(sid)
            body = read_text_file(path)
            if not body:
                self.send_error_response("Skill 不存在")
                return
            frontmatter = extract_frontmatter(body)
            self.send_json_response({
                'success': True,
                'id': sid,
                'name': extract_yaml_scalar(frontmatter, 'name', sid),
                'description': extract_yaml_block(frontmatter, 'description', ''),
                'body': body
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_prd_load(self, query):
        """加载 PRD 文档"""
        try:
            project_id = query.get('projectId', [''])[0]
            page_name = query.get('pageName', ['default'])[0]

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            # 清理页面名称
            safe_page_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', page_name)
            prd_file = os.path.join(PROJECTS_DIR, project_id, 'prd', f'{safe_page_name}.md')

            content = ''
            if os.path.exists(prd_file):
                with open(prd_file, 'r', encoding='utf-8') as f:
                    content = f.read()

            self.send_json_response({'content': content, 'pageName': safe_page_name})

        except Exception as e:
            print(f"[PRD错误] 加载失败: {e}")
            self.send_error_response(str(e))

    def handle_get_pages(self, query):
        """获取项目的页面列表（解析 HTML）"""
        try:
            project_id = query.get('projectId', [''])[0]

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            html_file = os.path.join(PROJECTS_DIR, project_id, 'index.html')
            if not os.path.exists(html_file):
                self.send_error_response("项目不存在")
                return

            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()

            pages = self.extract_pages_from_html(html_content)
            self.send_json_response({'pages': pages})

        except Exception as e:
            print(f"[Pages错误] {e}")
            self.send_error_response(str(e))

    def handle_get_flowchart(self, query):
        """生成流程图（解析 HTML 中的页面跳转关系）"""
        try:
            project_id = query.get('projectId', [''])[0]

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            html_file = os.path.join(PROJECTS_DIR, project_id, 'index.html')
            if not os.path.exists(html_file):
                self.send_error_response("项目不存在")
                return

            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()

            flowchart = self.generate_flowchart_from_html(html_content)
            self.send_json_response(flowchart)

        except Exception as e:
            print(f"[Flowchart错误] {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    def extract_pages_from_html(self, html_content):
        """从 HTML 中提取页面列表"""
        pages = []
        seen_names = set()

        # ===== 模式A: Vue currentPage 相关的页面定义 =====
        # 模式1: v-if="currentPage === 'xxx'"
        pattern1 = r'v-if=["\']currentPage\s*===?\s*["\']([^"\']+)["\']'
        matches1 = re.findall(pattern1, html_content)

        # 模式2: currentPage = 'xxx' 或 currentPage.value = 'xxx'
        pattern2 = r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']'
        matches2 = re.findall(pattern2, html_content)

        for page in set(matches1 + matches2):
            if page and len(page) < 50 and not page.startswith('!') and page not in seen_names:
                seen_names.add(page)
                pages.append({
                    'name': page,
                    'label': self.get_page_label(page),
                    'type': 'currentPage'
                })

        # ===== 模式B: Vue Router 路由定义 =====
        # 匹配 { path: '/xxx', component: YyyPage } 模式
        router_pattern = r'\{\s*path:\s*["\'](/[^"\']*)["\']'
        router_matches = re.findall(router_pattern, html_content)

        if router_matches and not pages:
            # 仅当没有 currentPage 模式时才使用 Router 模式（避免重复）
            for route_path in router_matches:
                # 将路径转换为页面名称: '/scan-result' -> 'scan-result', '/' -> 'home'
                page_name = route_path.strip('/')
                if not page_name:
                    page_name = 'home'

                if page_name and len(page_name) < 50 and page_name not in seen_names:
                    seen_names.add(page_name)
                    pages.append({
                        'name': page_name,
                        'label': self.get_page_label(page_name),
                        'type': 'router',
                        'routePath': route_path
                    })

        # 按名称排序（home 排在最前面）
        pages.sort(key=lambda x: (0 if x['name'] == 'home' else 1, x['name']))

        return pages

    def get_page_label(self, page_name):
        """获取页面的中文标签"""
        label_map = {
            'home': '首页',
            'scan': '扫描页',
            'scan-result': '扫描结果',
            'result': '结果页',
            'analysis': '解析页',
            'aiTutor': 'AI讲题',
            'ai-explain': 'AI讲解',
            'ai-qa': 'AI答疑',
            'wrongBookHome': '错题本首页',
            'wrongBookList': '错题列表',
            'wrongBookDetail': '错题详情',
            'mistakes': '错题本',
            'mistakes-list': '错题列表',
            'login': '登录',
            'register': '注册',
            'profile': '个人中心',
            'settings': '设置',
            'detail': '详情页',
            'list': '列表页',
            'learning-report': '学情报告',
            'homework-list': '作业列表',
            'homework-report': '作业报告',
            'online-answer': '在线作答',
            'photo-correction': '拍照批改',
            'writing-guidance': '写作指导',
            'english-translation': '英文翻译',
            'speaking-practice': '口语练习',
        }
        return label_map.get(page_name, page_name)

    def generate_flowchart_from_html(self, html_content):
        """从 HTML 生成 Mermaid 流程图"""
        pages = []
        transitions = []
        modals = []

        # 1. 提取所有页面
        page_patterns = [
            r'v-if=["\']currentPage\s*===?\s*["\']([^"\']+)["\']',
            r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']',
            r':class="[^"]*currentPage\s*===?\s*["\']([^"\']+)["\']',
        ]

        all_pages = set()
        for pattern in page_patterns:
            matches = re.findall(pattern, html_content)
            for m in matches:
                if m and len(m) < 50 and not m.startswith('!'):
                    all_pages.add(m)

        pages = list(all_pages)

        # 2. 提取页面跳转关系 - 改进算法
        # 分割成页面区块来分析
        page_block_pattern = r'(v-if=["\']currentPage\s*===?\s*["\'][^"\']+["\'])'
        blocks = re.split(page_block_pattern, html_content)

        current_page = None
        for i, block in enumerate(blocks):
            # 检查是否是页面标识块
            page_match = re.search(r'v-if=["\']currentPage\s*===?\s*["\']([^"\']+)["\']', block)
            if page_match:
                current_page = page_match.group(1)
                continue

            # 如果有当前页面，分析这个块中的跳转
            if current_page and current_page in pages:
                # 模式1: currentPage = 'xxx' 或 currentPage.value = 'xxx'
                jump_matches = re.findall(r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']', block)
                for target in jump_matches:
                    if target in pages and target != current_page:
                        transitions.append({
                            'from': current_page,
                            'to': target,
                            'type': 'direct'
                        })

                # 模式2: goToXxx 或 goTo('xxx')
                method_matches = re.findall(r'@click=["\'][^"\']*go(?:To)?([A-Z][a-zA-Z]*)', block)
                for target in method_matches:
                    target_lower = target[0].lower() + target[1:] if target else ''
                    if target_lower in pages and target_lower != current_page:
                        transitions.append({
                            'from': current_page,
                            'to': target_lower,
                            'type': 'method'
                        })

                # 模式3: navigateTo('xxx')
                nav_matches = re.findall(r'navigateTo\(["\']([^"\']+)["\']\)', block)
                for target in nav_matches:
                    if target in pages and target != current_page:
                        transitions.append({
                            'from': current_page,
                            'to': target,
                            'type': 'navigate'
                        })

        # 3. 提取弹窗/模态框/交互组件
        modal_patterns = [
            (r'v-if=["\']show(\w+)["\']', 'show'),
            (r'(\w+Modal)\s*=\s*ref\(', 'modal'),
            (r'(\w+Dialog)\s*=\s*ref\(', 'dialog'),
            (r'(\w+Popup)\s*=\s*ref\(', 'popup'),
            (r'const\s+(show\w+)\s*=\s*ref\(', 'ref'),
        ]

        modal_set = set()
        for pattern, ptype in modal_patterns:
            matches = re.findall(pattern, html_content)
            for modal in matches:
                # 清理名称
                clean_name = modal.replace('show', '').replace('Show', '')
                clean_name = clean_name.replace('Modal', '').replace('Dialog', '').replace('Popup', '')
                if clean_name and len(clean_name) < 30 and clean_name.lower() not in ['loading', 'error', 'success']:
                    modal_set.add((modal, f'{clean_name}弹窗'))

        modals = [{'name': m[0], 'label': m[1]} for m in modal_set]

        # 4. 去重转换
        unique_transitions = {}
        for t in transitions:
            key = f"{t['from']}->{t['to']}"
            if key not in unique_transitions:
                unique_transitions[key] = t
        transitions = list(unique_transitions.values())

        # 5. 确保没有孤立页面 - 如果页面没有入边和出边，尝试推断
        connected_pages = set()
        for t in transitions:
            connected_pages.add(t['from'])
            connected_pages.add(t['to'])

        isolated_pages = set(pages) - connected_pages

        # 如果有 home 页面，将孤立页面连接到 home
        if 'home' in pages and isolated_pages:
            for page in isolated_pages:
                if page != 'home':
                    transitions.append({
                        'from': 'home',
                        'to': page,
                        'type': 'inferred'
                    })

        # 6. 生成 Mermaid 代码
        mermaid_lines = ['flowchart TD']

        # 添加页面节点
        for page in sorted(pages):
            label = self.get_page_label(page)
            # 使用安全的节点ID (移除特殊字符)
            safe_id = re.sub(r'[^a-zA-Z0-9]', '_', page)
            mermaid_lines.append(f'    {safe_id}["{label}"]')

        # 添加弹窗节点（圆角矩形）
        for modal in modals[:8]:  # 限制数量
            safe_id = re.sub(r'[^a-zA-Z0-9]', '_', modal['name'])
            mermaid_lines.append(f'    {safe_id}("{modal["label"]}")')

        # 添加跳转连接
        added_transitions = set()
        for t in transitions:
            safe_from = re.sub(r'[^a-zA-Z0-9]', '_', t['from'])
            safe_to = re.sub(r'[^a-zA-Z0-9]', '_', t['to'])
            key = f"{safe_from}->{safe_to}"
            if key not in added_transitions:
                if t.get('type') == 'inferred':
                    mermaid_lines.append(f'    {safe_from} -.-> {safe_to}')
                else:
                    mermaid_lines.append(f'    {safe_from} --> {safe_to}')
                added_transitions.add(key)

        # 添加样式类定义（必须在节点和边之后）
        mermaid_lines.append('    classDef pageNode fill:#e0e7ff,stroke:#6366f1,stroke-width:2px')
        mermaid_lines.append('    classDef modalNode fill:#fef3c7,stroke:#f59e0b,stroke-width:1px,stroke-dasharray:5 5')

        # 应用样式（必须在 classDef 之后，节点名用逗号分隔）
        if pages:
            page_ids = ','.join([re.sub(r'[^a-zA-Z0-9]', '_', p) for p in pages])
            mermaid_lines.append(f'    class {page_ids} pageNode')
        if modals:
            modal_ids = ','.join([re.sub(r'[^a-zA-Z0-9]', '_', m['name']) for m in modals[:8]])
            mermaid_lines.append(f'    class {modal_ids} modalNode')

        mermaid_code = '\n'.join(mermaid_lines)

        return {
            'pages': [{'name': p, 'label': self.get_page_label(p)} for p in sorted(pages)],
            'transitions': transitions,
            'modals': modals,
            'mermaid': mermaid_code,
            'stats': {
                'pageCount': len(pages),
                'transitionCount': len(transitions),
                'modalCount': len(modals)
            }
        }

    # ==================== 认证处理 ====================

    def handle_auth_register(self):
        """注册新用户"""
        try:
            data = self.read_json_body()
            username = data.get('username', '').strip()
            password = data.get('password', '')
            display_name = data.get('displayName', '').strip() or username

            if not username or not password:
                self.send_error_response("用户名和密码不能为空")
                return
            if len(username) < 2 or len(username) > 30:
                self.send_error_response("用户名长度 2-30 个字符")
                return
            if len(password) < 6:
                self.send_error_response("密码至少 6 个字符")
                return

            user = db.create_user(username, password, display_name)
            if not user:
                self.send_error_response("用户名已被占用")
                return

            token = db.create_session(user['id'])
            imported_count = self.sync_local_projects_to_user(user['id'], claim_all=True)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.set_session_cookie(token)
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'user': {'id': user['id'], 'username': user['username'], 'displayName': user['display_name']},
                'importedProjects': imported_count
            }, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error_response(str(e))

    def handle_auth_login(self):
        """用户登录"""
        try:
            data = self.read_json_body()
            username = data.get('username', '').strip()
            password = data.get('password', '')

            user = db.get_user_by_username(username)
            if not user or not db.verify_password(password, user['password_hash']):
                self.send_error_response("用户名或密码错误")
                return

            token = db.create_session(user['id'])
            imported_count = self.sync_local_projects_to_user(user['id'], claim_all=True)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.set_session_cookie(token)
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'user': {'id': user['id'], 'username': user['username'], 'displayName': user['display_name']},
                'importedProjects': imported_count
            }, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error_response(str(e))

    def handle_auth_logout(self):
        """退出登录"""
        try:
            cookie_header = self.headers.get('Cookie', '')
            cookies = http.cookies.SimpleCookie()
            cookies.load(cookie_header)
            token_morsel = cookies.get('session_token')
            if token_morsel:
                db.delete_session(token_morsel.value)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.clear_session_cookie()
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
        except Exception as e:
            self.send_error_response(str(e))

    def handle_auth_me(self):
        """获取当前登录用户信息"""
        user = self.get_current_user()
        if not user:
            self.send_json_response({'user': None})
            return
        self.sync_local_projects_to_user(user['id'], claim_all=False)
        teams = db.get_user_teams(user['id'])
        self.send_json_response({
            'user': {
                'id': user['id'],
                'username': user['username'],
                'displayName': user['display_name']
            },
            'teams': [{'id': t['id'], 'name': t['name'], 'role': t['role'], 'inviteCode': t['invite_code']} for t in teams]
        })

    # ==================== 团队处理 ====================

    def handle_get_teams(self):
        """获取当前用户的团队列表"""
        user = self.require_auth()
        if not user:
            return
        teams = db.get_user_teams(user['id'])
        self.send_json_response({
            'teams': [{'id': t['id'], 'name': t['name'], 'role': t['role'], 'inviteCode': t['invite_code']} for t in teams]
        })

    def handle_create_team(self):
        """创建团队"""
        user = self.require_auth()
        if not user:
            return
        try:
            data = self.read_json_body()
            name = data.get('name', '').strip()
            if not name:
                self.send_error_response("团队名称不能为空")
                return
            team = db.create_team(name, user['id'])
            self.send_json_response({
                'success': True,
                'team': {'id': team['id'], 'name': team['name'], 'inviteCode': team['invite_code']}
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_join_team(self):
        """通过邀请码加入团队"""
        user = self.require_auth()
        if not user:
            return
        try:
            data = self.read_json_body()
            invite_code = data.get('inviteCode', '').strip()
            if not invite_code:
                self.send_error_response("请输入邀请码")
                return
            team = db.join_team_by_code(invite_code, user['id'])
            if not team:
                self.send_error_response("邀请码无效")
                return
            self.send_json_response({
                'success': True,
                'team': {'id': team['id'], 'name': team['name'], 'inviteCode': team['invite_code']}
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_team_members(self, team_id):
        """获取团队成员列表"""
        user = self.require_auth()
        if not user:
            return
        try:
            team_id = int(team_id)
            if not db.is_team_member(team_id, user['id']):
                self.send_error_response("你不是该团队成员")
                return
            members = db.get_team_members(team_id)
            self.send_json_response({'members': members})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_leave_team(self, team_id):
        """退出团队"""
        user = self.require_auth()
        if not user:
            return
        try:
            team_id = int(team_id)
            db.leave_team(team_id, user['id'])
            self.send_json_response({'success': True})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_remove_member(self, team_id):
        """管理员移除团队成员"""
        user = self.require_auth()
        if not user:
            return
        try:
            team_id = int(team_id)
            data = self.read_json_body()
            target_user_id = data.get('userId')

            role = db.get_team_member_role(team_id, user['id'])
            if role != 'admin':
                self.send_error_response("只有管理员可以移除成员")
                return
            if target_user_id == user['id']:
                self.send_error_response("不能移除自己")
                return
            db.remove_team_member(team_id, target_user_id)
            self.send_json_response({'success': True})
        except Exception as e:
            self.send_error_response(str(e))

    # ==================== 项目分享处理 ====================

    def handle_share_project(self, project_id):
        """分享项目到团队"""
        user = self.require_auth()
        if not user:
            return
        try:
            data = self.read_json_body()
            team_id = data.get('teamId')
            if not team_id:
                self.send_error_response("缺少 teamId")
                return
            # 验证：是项目拥有者
            owner_id = db.get_project_owner(project_id)
            if owner_id != user['id']:
                self.send_error_response("只有项目拥有者可以分享")
                return
            # 验证：是团队成员
            if not db.is_team_member(team_id, user['id']):
                self.send_error_response("你不是该团队成员")
                return
            db.share_project(project_id, team_id, user['id'])
            self.send_json_response({'success': True})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_unshare_project(self, project_id):
        """取消分享"""
        user = self.require_auth()
        if not user:
            return
        try:
            data = self.read_json_body()
            team_id = data.get('teamId')
            owner_id = db.get_project_owner(project_id)
            if owner_id != user['id']:
                self.send_error_response("只有项目拥有者可以取消分享")
                return
            db.unshare_project(project_id, team_id)
            self.send_json_response({'success': True})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_get_project_shared_teams(self, project_id):
        """获取项目分享到的团队列表"""
        user = self.require_auth()
        if not user:
            return
        try:
            teams = db.get_project_shared_teams(project_id)
            self.send_json_response({'teams': teams})
        except Exception as e:
            self.send_error_response(str(e))

    # ==================== 项目列表（按用户/团队过滤）====================

    def handle_get_my_projects(self, query):
        """获取当前用户的个人项目"""
        user = self.require_auth()
        if not user:
            return
        self.sync_local_projects_to_user(user['id'], claim_all=False)
        all_projects = self.load_projects()
        my_ids = set(db.get_user_project_ids(user['id']))
        my_projects = [p for p in all_projects if p['id'] in my_ids]
        self.send_json_response({'projects': my_projects})

    def handle_get_team_projects(self, query):
        """获取团队内的共享项目"""
        user = self.require_auth()
        if not user:
            return
        team_id = query.get('teamId', [''])[0]
        if not team_id:
            self.send_error_response("缺少 teamId")
            return
        try:
            team_id = int(team_id)
        except ValueError:
            self.send_error_response("teamId 无效")
            return
        if not db.is_team_member(team_id, user['id']):
            self.send_error_response("你不是该团队成员")
            return
        all_projects = self.load_projects()
        team_ids = set(db.get_team_project_ids(team_id))
        team_projects = [p for p in all_projects if p['id'] in team_ids]
        # 附加拥有者信息
        for p in team_projects:
            owner_id = db.get_project_owner(p['id'])
            if owner_id:
                owner = db.get_user_by_id(owner_id)
                p['ownerName'] = owner['display_name'] if owner else '未知'
        self.send_json_response({'projects': team_projects})

    # ==================== 项目文件访问控制 ====================

    def handle_project_file_access(self, path):
        """控制 /projects/<id>/ 下的文件访问"""
        user = self.get_current_user()
        # 从路径提取 project_id（/projects/{id}/...）
        parts = path.split('/')
        if len(parts) < 3:
            super().do_GET()
            return
        project_id = urllib.parse.unquote(parts[2])

        # 离线个人版默认不需要登录，允许直接访问本地项目文件
        if not user:
            super().do_GET()
            return

        owner_id = db.get_project_owner(project_id)
        if owner_id is None:
            db.set_project_owner(project_id, user['id'])
            super().do_GET()
            return

        # 检查权限
        if not db.can_user_access_project(project_id, user['id']):
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': '无权访问此项目'}).encode('utf-8'))
            return

        # 有权限，正常服务静态文件
        super().do_GET()

    def sync_local_projects_to_user(self, user_id, claim_all=False):
        """将本地个人版项目同步到登录用户的个人项目列表。

        claim_all=True 用于登录/注册后的首次导入，确保离线个人版项目进入当前账号。
        claim_all=False 只接管未归属项目，避免普通刷新覆盖已有团队归属。
        """
        imported = 0
        try:
            projects = self.load_projects()
            for project in projects:
                project_id = project.get('id')
                if not project_id:
                    continue
                owner_id = db.get_project_owner(project_id)
                if claim_all or owner_id is None:
                    if owner_id != user_id:
                        db.set_project_owner(project_id, user_id)
                        imported += 1
            if imported:
                print(f"[协作] 已同步 {imported} 个本地项目到用户 {user_id}")
        except Exception as e:
            print(f"[协作] 同步本地项目失败: {e}")
        return imported

    def send_json_response(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, message):
        """发送错误响应"""
        self.send_response(500)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}, ensure_ascii=False).encode('utf-8'))

    def handle_generation_status(self, query):
        """查询项目生成状态"""
        try:
            project_id = query.get('id', [''])[0]
            if not project_id:
                self.send_error_response("缺少project_id")
                return

            # 检查任务状态
            with tasks_lock:
                if project_id in generating_tasks:
                    task_info = generating_tasks[project_id]
                    if task_info.get('status') == STATUS_GENERATING:
                        started_at = parse_project_timestamp(task_info.get('startedAt'))
                        record_path = os.path.join(PROJECTS_DIR, project_id, 'record.json')
                        if not started_at and os.path.exists(record_path):
                            try:
                                with open(record_path, 'r', encoding='utf-8') as f:
                                    record = json.load(f)
                                started_at = parse_project_timestamp(record.get('createdAt'))
                            except Exception:
                                started_at = None
                        if started_at and (datetime.datetime.now() - started_at).total_seconds() > STALE_GENERATION_SECONDS:
                            error = f"生成超时：超过 {STALE_GENERATION_SECONDS // 60} 分钟仍未完成，已自动标记失败。建议减少参考图/切换更稳定模型后重试。"
                            task_info['status'] = STATUS_FAILED
                            task_info['error'] = error
                            mark_project_failed(project_id, error)
                    self.send_json_response({
                        'status': task_info['status'],
                        'progress': task_info.get('progress', 0),
                        'error': task_info.get('error', '')
                    })
                    return

            # 检查是否已完成
            html_path = os.path.join(PROJECTS_DIR, project_id, 'index.html')
            if os.path.exists(html_path):
                self.send_json_response({'status': STATUS_COMPLETED, 'progress': 100})
            else:
                record_path = os.path.join(PROJECTS_DIR, project_id, 'record.json')
                if os.path.exists(record_path):
                    with open(record_path, 'r', encoding='utf-8') as f:
                        record = json.load(f)
                    status = record.get('status') or STATUS_GENERATING
                    if status == STATUS_GENERATING:
                        created_at = parse_project_timestamp(record.get('createdAt'))
                        if created_at and (datetime.datetime.now() - created_at).total_seconds() > STALE_GENERATION_SECONDS:
                            error = f"生成超时：超过 {STALE_GENERATION_SECONDS // 60} 分钟仍未完成，已自动标记失败。建议减少参考图/切换更稳定模型后重试。"
                            mark_project_failed(project_id, error)
                            self.send_json_response({'status': STATUS_FAILED, 'progress': 20, 'error': error})
                            return
                    self.send_json_response({
                        'status': status,
                        'progress': 20 if status == STATUS_GENERATING else 0,
                        'error': record.get('error', '')
                    })
                else:
                    self.send_json_response({'status': 'not_found', 'progress': 0})

        except Exception as e:
            print(f"[错误] 查询状态失败: {e}")
            self.send_error_response(str(e))

    def handle_create_placeholder(self):
        """创建占位项目（不调用AI，用于复制Prompt功能）"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId', '')
            project_name = data.get('projectName', '未命名项目')
            form_data = data.get('formData', {})
            image_files = data.get('imageFiles', {})  # {pageIndex: [base64...]}

            if not project_id:
                self.send_error_response("缺少projectId")
                return

            print(f"[占位] 创建项目: {project_name} ({project_id})")

            # 创建项目文件夹
            project_folder = os.path.join(PROJECTS_DIR, project_id)
            os.makedirs(project_folder, exist_ok=True)

            # 保存参考图片
            ref_images_folder = os.path.join(project_folder, 'reference')
            os.makedirs(ref_images_folder, exist_ok=True)

            saved_image_names = []
            for page_index_str, images in image_files.items():
                for i, img_base64 in enumerate(images):
                    filename = f"ref_{page_index_str}_{i+1}"
                    saved = save_base64_image(img_base64, ref_images_folder, filename)
                    if saved:
                        saved_image_names.append(saved)

            # 构建record.json
            record = {
                'global': form_data.get('global', {}),
                'pages': form_data.get('pages', []),
                'status': 'pending_external',
                'createdAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            record_path = os.path.join(project_folder, 'record.json')
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            # 获取当前选中的模型名称
            current_model = get_selected_model()
            current_model_name = current_model.get('name', '') if current_model else ''

            # 更新项目列表
            projects = self.load_projects()
            new_project = {
                'id': project_id,
                'name': project_name + ' (待外部生成)',
                'model_name': current_model_name,
                'status': 'pending_external',
                'url': f'/projects/{project_id}/record.json',  # 暂无HTML
                'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            projects.insert(0, new_project)
            self.save_projects(projects)

            # 记录项目归属
            cur_user = self.get_current_user()
            if cur_user:
                db.set_project_owner(project_id, cur_user['id'])

            print(f"[完成] 占位项目已创建: {project_folder}")
            self.send_json_response({'success': True, 'project': new_project})

        except Exception as e:
            print(f"[错误] 创建占位项目失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    # ==================== GitHub 列表页生成 ====================

    def generate_index_html(self, manifest, username, repo):
        """生成 projects/index.html 列表页 HTML"""
        mode_labels = {'preview': '纯净版', 'dev': '研发版', 'embedded': '内嵌版'}
        mode_colors = {'preview': '#3b82f6', 'dev': '#8b5cf6', 'embedded': '#f59e0b'}

        cards_html = ''
        sorted_items = sorted(manifest, key=lambda x: x.get('publishedAt', ''), reverse=True)
        for item in sorted_items:
            name = item.get('name', '未命名项目')
            url = item.get('url', '#')
            published_at = item.get('publishedAt', '')[:10]
            mode = item.get('mode', 'preview')
            mode_label = mode_labels.get(mode, mode)
            mode_color = mode_colors.get(mode, '#6b7280')
            cards_html += f'''
            <div class="card" onclick="window.open('{url}','_blank')">
                <div class="card-header">
                    <div class="project-icon">🎨</div>
                </div>
                <div class="card-body">
                    <h3 class="project-name" title="{name}">{name}</h3>
                    <div class="project-meta">
                        <span class="mode-badge" style="background:{mode_color}20;color:{mode_color};border-color:{mode_color}40">{mode_label}</span>
                        <span class="published-date">{published_at}</span>
                    </div>
                </div>
                <div class="card-footer">
                    <button class="btn-open" onclick="event.stopPropagation();window.open('{url}','_blank')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        打开
                    </button>
                    <button class="btn-copy" onclick="event.stopPropagation();copyLink('{url}',this)">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                        复制链接
                    </button>
                </div>
            </div>'''

        count = len(manifest)
        pages_root = f'https://{username}.github.io/{repo}'
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>原型作品库 · {username}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f13;color:#e2e8f0;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1e1b4b 0%,#312e81 50%,#1e1b4b 100%);padding:48px 24px 40px;text-align:center;border-bottom:1px solid #ffffff12}}
  .header-icon{{font-size:40px;margin-bottom:12px}}
  .header h1{{font-size:28px;font-weight:700;color:#fff;margin-bottom:6px;letter-spacing:-0.5px}}
  .header p{{color:#a5b4fc;font-size:14px}}
  .header .count{{display:inline-block;background:#4f46e5;color:#fff;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;margin-top:10px}}
  .container{{max-width:1100px;margin:0 auto;padding:32px 24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}}
  .card{{background:#1a1a24;border:1px solid #ffffff0f;border-radius:16px;overflow:hidden;cursor:pointer;transition:all .2s;display:flex;flex-direction:column}}
  .card:hover{{border-color:#6366f140;transform:translateY(-3px);box-shadow:0 12px 40px #6366f120}}
  .card-header{{background:linear-gradient(135deg,#1e1b4b,#312e81);padding:28px 20px;display:flex;align-items:center;justify-content:center}}
  .project-icon{{font-size:36px;filter:drop-shadow(0 4px 8px rgba(0,0,0,.3))}}
  .card-body{{padding:16px 18px;flex:1}}
  .project-name{{font-size:15px;font-weight:600;color:#f1f5f9;margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .project-meta{{display:flex;align-items:center;gap:8px}}
  .mode-badge{{font-size:11px;font-weight:500;padding:2px 8px;border-radius:6px;border:1px solid;flex-shrink:0}}
  .published-date{{font-size:12px;color:#64748b}}
  .card-footer{{padding:12px 18px;border-top:1px solid #ffffff08;display:flex;gap:8px}}
  .btn-open,.btn-copy{{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:8px;border-radius:8px;font-size:12px;font-weight:500;border:none;cursor:pointer;transition:all .15s}}
  .btn-open{{background:#4f46e5;color:#fff}}.btn-open:hover{{background:#4338ca}}
  .btn-copy{{background:#ffffff0a;color:#94a3b8;border:1px solid #ffffff12}}.btn-copy:hover{{background:#ffffff14;color:#fff}}
  .btn-copy.copied{{background:#059669;color:#fff;border-color:#059669}}
  .empty{{text-align:center;padding:80px 24px;color:#475569}}
  .empty-icon{{font-size:48px;margin-bottom:16px}}
  .footer{{text-align:center;padding:32px;color:#334155;font-size:12px;border-top:1px solid #ffffff08;margin-top:32px}}
  .footer a{{color:#6366f1;text-decoration:none}}
</style>
</head>
<body>
<div class="header">
  <div class="header-icon">🎨</div>
  <h1>原型作品库</h1>
  <p>{username} · {repo}</p>
  <span class="count">共 {count} 个原型</span>
</div>
<div class="container">
  {'<div class="grid">' + cards_html + '</div>' if manifest else '<div class="empty"><div class="empty-icon">📭</div><p>暂无已发布的原型</p></div>'}
</div>
<div class="footer">由 <a href="{pages_root}" target="_blank">AI 原型生成器</a> 发布 · GitHub Pages 托管</div>
<script>
function copyLink(url, btn) {{
  navigator.clipboard.writeText(url).then(() => {{
    const orig = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 12 4 10"/></svg> 已复制';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.innerHTML = orig; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
</body>
</html>'''

    def update_github_listing(self, session, api_base, username, repo, default_branch,
                              project_id, project_name, project_url, mode, remove=False):
        """更新 GitHub 上的 projects/manifest.json 和 projects/index.html"""
        manifest_api_url = f"{api_base}/repos/{username}/{repo}/contents/projects/manifest.json"

        # 读取现有 manifest
        existing = session.get(manifest_api_url, timeout=15)
        manifest = []
        manifest_sha = None
        if existing.status_code == 200:
            import base64 as b64
            raw = b64.b64decode(existing.json().get('content', '')).decode('utf-8')
            try:
                manifest = json.loads(raw)
            except Exception:
                manifest = []
            manifest_sha = existing.json().get('sha', '')

        if remove:
            # 移除项目
            manifest = [m for m in manifest if m.get('id') != project_id]
        else:
            # 更新或添加项目
            found = False
            for m in manifest:
                if m.get('id') == project_id:
                    m['name'] = project_name
                    m['url'] = project_url
                    m['mode'] = mode
                    m['publishedAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    found = True
                    break
            if not found:
                manifest.append({
                    'id': project_id,
                    'name': project_name,
                    'url': project_url,
                    'mode': mode,
                    'publishedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

        # 上传 manifest.json
        manifest_b64 = base64.b64encode(json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')).decode()
        manifest_payload = {
            'message': 'Update projects manifest',
            'content': manifest_b64,
            'branch': default_branch
        }
        if manifest_sha:
            manifest_payload['sha'] = manifest_sha
        session.put(manifest_api_url, json=manifest_payload, timeout=20)
        print(f"[GitHub] manifest.json 已更新 ({len(manifest)} 个项目)")

        # 生成并上传 projects/index.html
        index_html = self.generate_index_html(manifest, username, repo)
        index_api_url = f"{api_base}/repos/{username}/{repo}/contents/projects/index.html"
        existing_index = session.get(index_api_url, timeout=10)
        index_payload = {
            'message': 'Update projects listing page',
            'content': base64.b64encode(index_html.encode('utf-8')).decode(),
            'branch': default_branch
        }
        if existing_index.status_code == 200:
            index_payload['sha'] = existing_index.json().get('sha', '')
        session.put(index_api_url, json=index_payload, timeout=30)
        print(f"[GitHub] projects/index.html 已更新")

    # ==================== 取消发布 API ====================

    def handle_github_unpublish(self):
        """取消发布：删除 GitHub 上的项目文件，更新列表页"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId', '')
            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            gh = get_github_runtime_config()
            token = gh.get('token', '')
            username = gh.get('username', '')
            repo = gh.get('repo', 'my-prototypes')

            if not token or not username:
                self.send_error_response("请先配置 GitHub Token")
                return

            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retry_strategy = Retry(total=3, backoff_factor=1, connect=3, read=3,
                                   status_forcelist=[500, 502, 503, 504],
                                   allowed_methods=["GET", "PUT", "POST", "DELETE"])
            session = requests.Session()
            session.mount('https://', HTTPAdapter(max_retries=retry_strategy))
            session.headers.update({
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            })

            api_base = 'https://api.github.com'

            # 获取默认分支
            repo_info = session.get(f"{api_base}/repos/{username}/{repo}", timeout=15).json()
            default_branch = repo_info.get('default_branch', 'main')

            # 列出 projects/{id}/ 下的所有文件并逐一删除
            print(f"[GitHub] 取消发布: {project_id}")
            folder_url = f"{api_base}/repos/{username}/{repo}/contents/projects/{project_id}"
            files_resp = session.get(folder_url, timeout=15)
            if files_resp.status_code == 200:
                files = files_resp.json()
                # 如果有子目录（如 images/），需要递归列出
                all_files = []
                for f in files:
                    if f.get('type') == 'file':
                        all_files.append(f)
                    elif f.get('type') == 'dir':
                        sub_resp = session.get(f['url'], timeout=15)
                        if sub_resp.status_code == 200:
                            all_files.extend([sf for sf in sub_resp.json() if sf.get('type') == 'file'])

                for f in all_files:
                    del_resp = session.delete(f['url'], json={
                        'message': f'Remove prototype: {project_id}',
                        'sha': f['sha'],
                        'branch': default_branch
                    }, timeout=20)
                    if del_resp.status_code in (200, 201):
                        print(f"[GitHub] 已删除: {f['path']}")
                    else:
                        print(f"[GitHub] 删除失败: {f['path']} ({del_resp.status_code})")

            # 更新列表页（传 remove=True）
            self.update_github_listing(
                session, api_base, username, repo, default_branch,
                project_id=project_id, project_name='', project_url='', mode='', remove=True
            )

            # 清除本地 record.json 中的 github_url
            project_dir = os.path.join(PROJECTS_DIR, project_id)
            record_path = os.path.join(project_dir, 'record.json')
            if os.path.exists(record_path):
                with open(record_path, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                record.pop('github_url', None)
                record.pop('github_published_at', None)
                record.pop('github_mode', None)
                with open(record_path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
                print(f"[GitHub] 本地 record.json 已清除 github_url")

            self.send_json_response({'success': True, 'message': '已取消发布，GitHub 文件已删除'})

        except Exception as e:
            print(f"[错误] 取消发布失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(f"取消发布失败: {str(e)}")

    # ==================== 导出 API ====================

    def handle_export(self):
        """触发本地导出，支持三种模式: preview / embedded / dev"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId', '')
            mode = data.get('mode', 'preview')  # preview | embedded | dev

            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            project_dir = os.path.join(PROJECTS_DIR, project_id)
            if not os.path.exists(project_dir):
                self.send_error_response(f"项目不存在: {project_id}")
                return

            print(f"[导出] 项目: {project_id}, 模式: {mode}")

            # 动态导入 export_project 模块
            import importlib.util
            ep_path = os.path.join(get_base_path(), 'export_project.py')
            spec = importlib.util.spec_from_file_location("export_project", ep_path)
            ep = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ep)

            export_dir = ep.export_project(project_id, mode=mode)

            # 自动打开导出目录（Windows）
            try:
                import subprocess
                subprocess.Popen(f'explorer "{os.path.abspath(export_dir)}"')
            except Exception:
                pass

            self.send_json_response({
                'success': True,
                'exportPath': export_dir,
                'message': f'已导出到: {export_dir}'
            })

        except Exception as e:
            print(f"[错误] 导出失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))

    # ==================== GitHub 配置 API ====================

    def handle_github_config_get(self):
        """读取 GitHub 配置（Token 打码）"""
        try:
            config = load_config()
            gh = get_github_runtime_config()
            token = gh.get('token', '')
            # 打码显示
            masked_token = (token[:6] + '****' + token[-4:]) if len(token) > 10 else ('****' if token else '')
            self.send_json_response({
                'success': True,
                'username': gh.get('username', ''),
                'repo': gh.get('repo', 'my-prototypes'),
                'tokenMasked': masked_token,
                'hasToken': bool(token),
                'tokenSource': 'env' if token else ''
            })
        except Exception as e:
            self.send_error_response(str(e))

    def handle_github_config_save(self):
        """保存 GitHub 配置到 config.json"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if 'github' not in config:
                config['github'] = {}

            # Token 不再写入 config.json，避免密钥落盘；仅在当前进程中临时可用。
            if data.get('token'):
                os.environ['PROTOTYPE_GITHUB_TOKEN'] = data['token']
            if 'username' in data:
                config['github']['username'] = data['username']
            if 'repo' in data:
                config['github']['repo'] = data['repo'] or 'my-prototypes'
            config['github'].pop('token', None)

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            print(f"[GitHub] 配置已保存: {config['github']['username']}/{config['github']['repo']}")
            self.send_json_response({'success': True, 'message': '配置已保存，Token 仅保存在当前进程环境变量中'})

        except Exception as e:
            self.send_error_response(str(e))

    def handle_github_test(self):
        """验证 GitHub Token 有效性"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            token = data.get('token', '')
            if not token:
                token = get_github_runtime_config().get('token', '')

            if not token:
                self.send_error_response("请先填写 Personal Access Token")
                return

            resp = requests.get(
                'https://api.github.com/user',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                timeout=15
            )

            if resp.status_code == 200:
                user = resp.json()
                self.send_json_response({
                    'success': True,
                    'username': user.get('login', ''),
                    'name': user.get('name', ''),
                    'message': f"✅ 验证通过，用户：{user.get('login', '')}"
                })
            else:
                self.send_json_response({
                    'success': False,
                    'message': f"Token 无效（HTTP {resp.status_code}）"
                })

        except Exception as e:
            self.send_error_response(f"连接失败：{str(e)}")

    # ==================== GitHub 发布 API ====================

    def handle_github_publish(self):
        """将项目发布到 GitHub Pages"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            project_id = data.get('projectId', '')
            mode = data.get('mode', 'preview')  # 导出模式: dev / preview / embedded
            if not project_id:
                self.send_error_response("缺少 projectId")
                return

            gh = get_github_runtime_config()
            token = gh.get('token', '')
            username = gh.get('username', '')
            repo = gh.get('repo', 'my-prototypes')

            if not token or not username:
                self.send_error_response("请先在设置中配置 GitHub Token 和用户名")
                return

            project_dir = os.path.join(PROJECTS_DIR, project_id)
            if not os.path.exists(project_dir):
                self.send_error_response(f"项目不存在: {project_id}")
                return

            api_base = 'https://api.github.com'

            # 用带自动重试的 Session，解决连接池里的"僵尸连接"被 GitHub 关闭后引发的 ConnectionResetError
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retry_strategy = Retry(
                total=3,          # 最多重试 3 次
                backoff_factor=1, # 重试间隔: 0s, 1s, 2s
                connect=3,        # 连接失败（ConnectionResetError）也重试
                read=3,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "PUT", "POST", "DELETE"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session = requests.Session()
            session.mount('https://', adapter)
            session.headers.update({
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            })

            print(f"[GitHub] 开始发布项目 '{project_id}' 到仓库 '{username}/{repo}'")

            # ---- 1. 检查/创建仓库 ----
            print(f"[GitHub] 步骤 1/7: 检查或创建 GitHub 仓库 '{username}/{repo}'...")
            repo_url = f"{api_base}/repos/{username}/{repo}"
            try:
                r = session.get(repo_url, timeout=15)
                if r.status_code == 404:
                    print(f"[GitHub] 仓库 '{repo}' 不存在，尝试创建...")
                    create_resp = session.post(
                        f"{api_base}/user/repos",
                        json={'name': repo, 'private': False, 'auto_init': True},
                        timeout=20
                    )
                    if create_resp.status_code not in (200, 201):
                        raise Exception(f"创建仓库失败: {create_resp.json().get('message', create_resp.text)}")
                    print(f"[GitHub] 仓库 '{repo}' 已成功创建。")
                    import time
                    time.sleep(2)  # 等待仓库初始化
                elif r.status_code != 200:
                    raise Exception(f"访问仓库失败（HTTP {r.status_code}）: {r.json().get('message', r.text)}")
                else:
                    print(f"[GitHub] 仓库 '{repo}' 已存在。")
            except requests.exceptions.RequestException as req_e:
                raise Exception(f"连接 GitHub API 失败（检查网络或Token）: {req_e}")

            # ---- 2. 获取默认分支 ----
            print(f"[GitHub] 步骤 2/7: 获取仓库默认分支...")
            repo_info = session.get(repo_url, timeout=15).json()
            default_branch = repo_info.get('default_branch', 'main')
            print(f"[GitHub] 默认分支为: '{default_branch}'。")

            # ---- 3. 确保 index.html 根文件存在（GitHub Pages 需要） ----
            print(f"[GitHub] 步骤 3/7: 检查并创建根目录重定向文件 'index.html'...")
            root_index_path = f"{api_base}/repos/{username}/{repo}/contents/index.html"
            r_root = session.get(root_index_path, timeout=10)
            if r_root.status_code == 404:
                root_content = base64.b64encode(b'<meta http-equiv="refresh" content="0;url=projects/">').decode()
                put_resp = session.put(root_index_path, json={
                    'message': 'Add root redirect for GitHub Pages',
                    'content': root_content,
                    'branch': default_branch
                }, timeout=15)
                if put_resp.status_code not in (200, 201):
                    raise Exception(f"创建根目录 'index.html' 失败: {put_resp.json().get('message', put_resp.text)}")
                print(f"[GitHub] 根目录 'index.html' 已创建。")
            else:
                print(f"[GitHub] 根目录 'index.html' 已存在。")

            # ---- 4. 启用 GitHub Pages ----
            print(f"[GitHub] 步骤 4/7: 检查并启用 GitHub Pages...")
            pages_api_url = f"{api_base}/repos/{username}/{repo}/pages"
            # Pages API 需要特殊的 Accept header，临时覆盖
            pages_headers = {'Accept': 'application/vnd.github+json'}
            pages_resp = session.get(pages_api_url, headers=pages_headers, timeout=10)
            if pages_resp.status_code == 404:
                post_resp = session.post(pages_api_url, headers=pages_headers, json={
                    'source': {'branch': default_branch, 'path': '/'}
                }, timeout=15)
                if post_resp.status_code not in (200, 201):
                    raise Exception(f"启用 GitHub Pages 失败: {post_resp.json().get('message', post_resp.text)}")
                print(f"[GitHub] GitHub Pages 已成功启用。")
            elif pages_resp.status_code == 200:
                print(f"[GitHub] GitHub Pages 已存在，跳过。")
            else:
                raise Exception(f"检查 GitHub Pages 状态失败（HTTP {pages_resp.status_code}）: {pages_resp.json().get('message', pages_resp.text)}")

            # ---- 4.5. 执行本地导出 ----
            print(f"[GitHub] 步骤 4.5/7: 按模式 '{mode}' 执行本地导出...")
            import importlib.util
            ep_path = os.path.join(get_base_path(), 'export_project.py')
            spec = importlib.util.spec_from_file_location("export_project", ep_path)
            ep = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ep)

            export_dir = ep.export_project(project_id, mode=mode)
            print(f"[GitHub] 导出目录: {export_dir}")

            # ---- 5. 上传项目文件 ----
            print(f"[GitHub] 步骤 5/7: 上传项目文件到 'projects/{project_id}/' 目录...")
            def upload_file(local_path, remote_path):
                with open(local_path, 'rb') as f:
                    content_b64 = base64.b64encode(f.read()).decode()

                file_api_url = f"{api_base}/repos/{username}/{repo}/contents/{remote_path}"

                # Check if file exists to get SHA for update
                existing = session.get(file_api_url, timeout=10)
                payload = {
                    'message': f'Update prototype: {project_id}',
                    'content': content_b64,
                    'branch': default_branch
                }
                if existing.status_code == 200:
                    payload['sha'] = existing.json().get('sha', '')
                    print(f"[GitHub] 更新文件: {remote_path}")
                else:
                    print(f"[GitHub] 创建文件: {remote_path}")

                put_resp = session.put(file_api_url, json=payload, timeout=30)
                if put_resp.status_code not in (200, 201):
                    raise Exception(f"上传文件失败 {remote_path}: {put_resp.json().get('message', put_resp.text)}")
                print(f"[GitHub] 文件 '{remote_path}' 上传成功。")

            # 遍历 export_dir 下的所有文件并上传
            if os.path.exists(export_dir):
                for root_dir, _, files in os.walk(export_dir):
                    for file_name in files:
                        local_path = os.path.join(root_dir, file_name)
                        rel_path = os.path.relpath(local_path, export_dir).replace('\\', '/')
                        remote_path = f"projects/{project_id}/{rel_path}"
                        upload_file(local_path, remote_path)
            else:
                raise Exception(f"导出目录不存在: {export_dir}")

            print(f"[GitHub] 项目文件上传完成。")

            # ---- 6. 生成 Pages URL ----
            print(f"[GitHub] 步骤 6/7: 生成 GitHub Pages URL...")
            pages_url_result = f"https://{username}.github.io/{repo}/projects/{project_id}/"
            print(f"[GitHub] 预计发布链接: {pages_url_result}")

            # ---- 7. 更新 record.json + 列表页 ----
            print(f"[GitHub] 步骤 7/7: 更新本地记录 + GitHub 列表页...")
            record_path = os.path.join(project_dir, 'record.json')
            project_name = project_id  # 默认用 ID
            try:
                record = {}
                if os.path.exists(record_path):
                    with open(record_path, 'r', encoding='utf-8') as f:
                        record = json.load(f)
                project_name = record.get('title', record.get('name', project_id))
                record['github_url'] = pages_url_result
                record['github_published_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                record['github_mode'] = mode
                with open(record_path, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
                print(f"[GitHub] 'record.json' 已更新。")
            except Exception as e:
                print(f"[GitHub] 警告: 更新 'record.json' 失败（非致命错误）: {e}")

            # 更新 GitHub 列表页
            try:
                self.update_github_listing(
                    session, api_base, username, repo, default_branch,
                    project_id=project_id,
                    project_name=project_name,
                    project_url=pages_url_result,
                    mode=mode,
                    remove=False
                )
            except Exception as e:
                print(f"[GitHub] 警告: 更新列表页失败（非致命错误）: {e}")

            print(f"[GitHub] 项目 '{project_id}' 发布流程完成。")
            self.send_json_response({
                'success': True,
                'url': pages_url_result,
                'mode': mode,
                'message': f'发布成功！约 1-3 分钟后链接生效: {pages_url_result}'
            })

        except Exception as e:
            print(f"[错误] GitHub 发布失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(f"GitHub 发布失败: {str(e)}")


print(f"=" * 50)
print(f"原型生成器服务启动")
print(f"地址: http://localhost:{PORT}/src/")
print(f"项目目录: {os.path.abspath(PROJECTS_DIR)}")
print(f"=" * 50)

socketserver.TCPServer.allow_reuse_address = True

try:
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\n服务已停止")
except Exception as e:
    print(f"\n服务错误: {e}")
