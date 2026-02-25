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
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DELETED_PROJECTS_FILE = os.path.join(DATA_DIR, 'deleted_projects.json')

# 创建必要的目录
for dir_path in [UPLOAD_DIR, DATA_DIR, PROJECTS_DIR, DELETED_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

if not os.path.exists(PROJECTS_FILE):
    with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

if not os.path.exists(DELETED_PROJECTS_FILE):
    with open(DELETED_PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)


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
            # 从header推断扩展名
            if 'png' in header:
                ext = '.png'
            elif 'gif' in header:
                ext = '.gif'
            elif 'webp' in header:
                ext = '.webp'
            else:
                ext = '.jpg'
        else:
            data = base64_data
            ext = '.jpg'
        
        # 确保文件名有正确扩展名
        if not any(filename.endswith(e) for e in ['.jpg', '.png', '.gif', '.webp']):
            filename = filename + ext
        
        save_path = os.path.join(save_folder, filename)
        with open(save_path, 'wb') as f:
            f.write(base64.b64decode(data))
        
        return filename
    except Exception as e:
        print(f"[Base64图片保存失败] {filename}: {e}")
        return None


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
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)
        
        if path == '/api/prd/load':
            self.handle_prd_load(query)
        elif path == '/api/pages':
            self.handle_get_pages(query)
        elif path == '/api/flowchart':
            self.handle_get_flowchart(query)
        elif path == '/api/generation-status':
            self.handle_generation_status(query)
        elif path == '/api/models':
            self.handle_get_models()
        elif path == '/data/projects.json':
            # 拦截项目列表请求，确保返回最新数据
            self.load_projects()
            super().do_GET()
        else:
            # 默认静态文件服务
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/upload':
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
        elif self.path == '/api/models/select':
            self.handle_model_select()
        elif self.path == '/api/models/save':
            self.handle_model_save()
        elif self.path == '/api/models/delete':
            self.handle_model_delete()
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
                'createdAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'sourceProjectId': source_project_id if is_incremental else None
            }
            
            # 为每个页面分配图片文件名
            pages_data = form_data.get('pages', [])
            img_index = 0
            for page in pages_data:
                page_record = {
                    'name': page.get('name', ''),
                    'layout': page.get('layout', ''),
                    'features': page.get('features', ''),
                    'interaction': page.get('interaction', ''),
                    'similarity': page.get('similarity', 'layout'),
                    'images': []
                }
                # 分配图片
                img_count = page.get('imageCount', 0)
                for _ in range(img_count):
                    if img_index < len(saved_image_names):
                        page_record['images'].append(saved_image_names[img_index])
                        img_index += 1
                record['pages'].append(page_record)
            
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
                enhanced_prompt = prompt + f"\n\n# 重要提示\n这是一个增量更新任务。原项目中有{reused_pages}个页面内容未变化。请保持整体风格一致，重点关注变化的部分。"
                print(f"[增量] 使用增强prompt调用AI")
                html_content = self.call_ai_model(enhanced_prompt, images)
            else:
                # 正常调用AI
                html_content = self.call_ai_model(prompt, images)
            
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
                f.write(prompt)
            
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
                'status': STATUS_GENERATING,
                'createdAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'sourceProjectId': source_project_id if is_incremental else None
            }
            
            pages_data = form_data.get('pages', [])
            img_index = 0
            for page in pages_data:
                page_record = {
                    'name': page.get('name', ''),
                    'layout': page.get('layout', ''),
                    'features': page.get('features', ''),
                    'interaction': page.get('interaction', ''),
                    'similarity': page.get('similarity', 'layout'),
                    'images': []
                }
                img_count = page.get('imageCount', 0)
                for _ in range(img_count):
                    if img_index < len(saved_image_names):
                        page_record['images'].append(saved_image_names[img_index])
                        img_index += 1
                record['pages'].append(page_record)
            
            record_path = os.path.join(project_folder, 'record.json')
            with open(record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            
            # 保存 prompt
            prompt_path = os.path.join(project_folder, 'prompt.txt')
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
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
            projects.insert(0, new_project)
            self.save_projects(projects)
            
            # 注册异步任务
            with tasks_lock:
                generating_tasks[project_id] = {
                    'status': STATUS_GENERATING,
                    'progress': 0,
                    'error': ''
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
                    
                    # 使用类似 call_ai_model 的逻辑
                    html_content = self._call_ai_for_async(enhanced_prompt, images)
                    
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
                    
                    # 更新项目列表状态
                    projects = self.load_projects()
                    for p in projects:
                        if p['id'] == project_id:
                            p['status'] = STATUS_FAILED
                            break
                    self.save_projects(projects)
            
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
            # 构建消息
            user_content = []
            user_content.append({
                "type": "text",
                "text": prompt
            })
            
            # 添加图片
            for img_base64 in images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_base64}
                })
            
            # 从配置读取 system prompt
            system_prompt = AI_OPTIONS.get('system_prompt', 
                'You are a professional UI/UX Developer. Generate complete, standalone HTML prototypes with realistic data.')
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            # 动态获取当前选中模型配置
            selected_model = get_selected_model()
            model_name = selected_model.get('model', API_CONFIG.get('model', 'gpt-4'))
            base_url = selected_model.get('base_url', API_CONFIG.get('base_url', ''))
            api_key = selected_model.get('api_key', API_CONFIG.get('api_key', ''))
            print(f"[AI] 使用模型: {selected_model.get('name', model_name)} ({model_name})")
            
            # 准备请求数据
            payload = {
                "model": model_name,
                "messages": messages,
                "max_tokens": AI_OPTIONS.get('max_tokens', 100000),
                "temperature": AI_OPTIONS.get('temperature', 0.7)
            }
            
            url = f"{base_url}/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {api_key}"
            }
            
            timeout = AI_OPTIONS.get('timeout', 300)
            print(f"[AI] 正在调用大模型... (超时: {timeout}s)")
            
            result = None
            max_retries = 3
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
                except Exception as e:
                    print(f"[AI] 调用失败 (第 {attempt+1}/{max_retries} 次): {e}")
                    last_error = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)
            
            # 如果 requests 全部失败，尝试使用 curl 命令行兜底
            if not result:
                print("[AI] 尝试使用 curl 命令行兜底...")
                result = self.call_ai_model_via_curl(url, headers, payload, timeout)
            
            if not result:
                raise last_error
            
            content = result['choices'][0]['message']['content']
            finish_reason = result['choices'][0].get('finish_reason', '')
            
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
            return json.loads(process.stdout)
            
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
        with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)

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
        
        # 匹配 Vue currentPage 相关的页面定义
        # 模式1: v-if="currentPage === 'xxx'"
        pattern1 = r'v-if=["\']currentPage\s*===?\s*["\']([^"\']+)["\']'
        matches1 = re.findall(pattern1, html_content)
        
        # 模式2: currentPage = 'xxx' 或 currentPage.value = 'xxx'
        pattern2 = r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']'
        matches2 = re.findall(pattern2, html_content)
        
        # 合并并去重
        all_pages = list(set(matches1 + matches2))
        
        # 过滤掉非页面名称
        for page in all_pages:
            if page and len(page) < 50 and not page.startswith('!'):
                pages.append({
                    'name': page,
                    'label': self.get_page_label(page)
                })
        
        # 按名称排序
        pages.sort(key=lambda x: x['name'])
        
        return pages
    
    def get_page_label(self, page_name):
        """获取页面的中文标签"""
        label_map = {
            'home': '首页',
            'scan': '扫描页',
            'result': '结果页',
            'analysis': '解析页',
            'aiTutor': 'AI讲题',
            'wrongBookHome': '错题本首页',
            'wrongBookList': '错题列表',
            'wrongBookDetail': '错题详情',
            'login': '登录',
            'register': '注册',
            'profile': '个人中心',
            'settings': '设置',
            'detail': '详情页',
            'list': '列表页',
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

    def send_json_response(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, message):
        """发送错误响应"""
        self.send_response(500)
        self.send_header('Content-Type', 'application/json')
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
            
            print(f"[完成] 占位项目已创建: {project_folder}")
            self.send_json_response({'success': True, 'project': new_project})
            
        except Exception as e:
            print(f"[错误] 创建占位项目失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_response(str(e))


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
