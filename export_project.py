# -*- coding: utf-8 -*-
"""
项目导出工具 - 生成零依赖的预览包
支持三种导出模式：
  1. 研发模式 - 包含页面导航、PRD 文档、流程图
  2. 纯预览模式 - 仅原型本身，可直接打开查看
  3. 内嵌模式 - 原型内嵌到预览框架中，单文件可分享
"""

import os
import re
import json
import shutil
import base64
import urllib.request
from datetime import datetime

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(SCRIPT_DIR, 'projects')
EXPORTS_DIR = os.path.join(SCRIPT_DIR, 'exports')

# CDN 资源缓存目录
CDN_CACHE_DIR = os.path.join(SCRIPT_DIR, '.cdn_cache')

def list_projects():
    """列出所有项目"""
    if not os.path.exists(PROJECTS_DIR):
        return []
    return [d for d in os.listdir(PROJECTS_DIR) 
            if os.path.isdir(os.path.join(PROJECTS_DIR, d))]

def read_file(path, default=''):
    """读取文件内容"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return default

def extract_pages_from_html(html_content):
    """从 HTML 中提取页面列表"""
    patterns = [
        r'v-if=["\']currentPage\s*===?\s*["\']([^"\']+)["\']',
        r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']',
    ]
    
    pages = set()
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        for m in matches:
            if m and len(m) < 50 and not m.startswith('!'):
                pages.add(m)
    
    return list(pages)

def get_page_label(page_name):
    """获取页面中文标签"""
    labels = {
        'home': '首页', 'scan': '扫描页', 'result': '结果页',
        'analysis': '解析页', 'aiTutor': 'AI讲题',
        'wrongBookHome': '错题本首页', 'wrongBookList': '错题列表',
        'wrongBookDetail': '错题详情', 'login': '登录',
        'register': '注册', 'profile': '个人中心', 'settings': '设置',
    }
    return labels.get(page_name, page_name)

def extract_transitions(html_content, pages):
    """提取页面跳转关系"""
    transitions = []
    page_set = set(pages)
    
    # 分析每个页面区块
    blocks = re.split(r'v-if=["\']currentPage\s*===?\s*["\']', html_content)
    
    current_page = None
    for block in blocks:
        # 提取当前页面名
        match = re.match(r'([^"\']+)["\']', block)
        if match:
            current_page = match.group(1)
            if current_page not in page_set:
                current_page = None
                continue
        
        if current_page:
            # 查找跳转目标
            jump_matches = re.findall(r'currentPage(?:\.value)?\s*=\s*["\']([^"\']+)["\']', block[:5000])
            for target in jump_matches:
                if target in page_set and target != current_page:
                    transitions.append({'from': current_page, 'to': target})
    
    # 去重
    seen = set()
    unique = []
    for t in transitions:
        key = f"{t['from']}->{t['to']}"
        if key not in seen:
            seen.add(key)
            unique.append(t)
    
    return unique

def extract_modals(html_content):
    """提取弹窗组件"""
    patterns = [
        r'v-if=["\']show(\w+)["\']',
        r'(\w+Modal)\s*=\s*ref\(',
        r'(\w+Dialog)\s*=\s*ref\(',
    ]
    
    modals = set()
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        for m in matches:
            clean = m.replace('show', '').replace('Modal', '').replace('Dialog', '')
            if clean and len(clean) < 30 and clean.lower() not in ['loading', 'error']:
                modals.add((m, f'{clean}弹窗'))
    
    return [{'name': m[0], 'label': m[1]} for m in modals]

def generate_mermaid_code(pages, transitions):
    """生成 Mermaid 流程图代码"""
    lines = ['flowchart TD']
    
    # 添加节点
    for page in sorted(pages):
        label = get_page_label(page)
        safe_id = re.sub(r'[^a-zA-Z0-9]', '_', page)
        lines.append(f'    {safe_id}["{label}"]')
    
    # 添加连接
    for t in transitions:
        safe_from = re.sub(r'[^a-zA-Z0-9]', '_', t['from'])
        safe_to = re.sub(r'[^a-zA-Z0-9]', '_', t['to'])
        lines.append(f'    {safe_from} --> {safe_to}')
    
    # 添加样式
    if pages:
        ids = ' '.join([re.sub(r'[^a-zA-Z0-9]', '_', p) for p in pages])
        lines.append(f'    classDef pageNode fill:#e0e7ff,stroke:#6366f1,stroke-width:2px')
        lines.append(f'    class {ids} pageNode')
    
    return '\n'.join(lines)

def generate_standalone_html(project_name, pages, prd_data, transitions, modals, mermaid_code):
    """生成独立的 HTML 预览器"""
    
    pages_json = json.dumps([{'name': p, 'label': get_page_label(p)} for p in sorted(pages)], ensure_ascii=False)
    prd_json = json.dumps(prd_data, ensure_ascii=False)
    transitions_json = json.dumps(transitions, ensure_ascii=False)
    modals_json = json.dumps(modals, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - 原型预览</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{ font-family: 'Inter', sans-serif; }}
        .scrollbar-thin::-webkit-scrollbar {{ width: 6px; }}
        .scrollbar-thin::-webkit-scrollbar-track {{ background: transparent; }}
        .scrollbar-thin::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}
        .prd-sidebar {{ transition: width 0.3s ease; position: relative; }}
        .prd-sidebar.collapsed {{ width: 48px; }}
        .prd-sidebar.expanded {{ width: 420px; }}
        .markdown-body h1 {{ font-size: 1.5rem; font-weight: 700; margin: 1rem 0 0.5rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem; }}
        .markdown-body h2 {{ font-size: 1.25rem; font-weight: 600; margin: 1rem 0 0.5rem; }}
        .markdown-body h3 {{ font-size: 1.1rem; font-weight: 600; margin: 0.75rem 0 0.5rem; }}
        .markdown-body p {{ margin: 0.5rem 0; line-height: 1.6; }}
        .markdown-body ul {{ margin: 0.5rem 0; padding-left: 1.5rem; list-style-type: disc; }}
        .markdown-body ol {{ margin: 0.5rem 0; padding-left: 1.5rem; list-style-type: decimal; }}
        .markdown-body li {{ margin: 0.25rem 0; display: list-item; }}
        .markdown-body code {{ background: #f3f4f6; padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.875rem; }}
        .markdown-body pre {{ background: #1f2937; color: #e5e7eb; padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 0.75rem 0; }}
        .markdown-body pre code {{ background: transparent; padding: 0; color: inherit; }}
        .markdown-body blockquote {{ border-left: 4px solid #6366f1; padding-left: 1rem; margin: 0.75rem 0; color: #6b7280; }}
        .markdown-body table {{ width: 100%; border-collapse: collapse; margin: 0.75rem 0; }}
        .markdown-body th, .markdown-body td {{ border: 1px solid #e5e7eb; padding: 0.5rem; text-align: left; }}
        .markdown-body th {{ background: #f9fafb; font-weight: 600; }}
        .page-item {{ transition: all 0.2s ease; }}
        .page-item:hover {{ background: #f3f4f6; }}
        .page-item.active {{ background: #eef2ff; border-left: 3px solid #6366f1; }}
        .preview-frame-mobile {{ width: 390px; height: 844px; border-radius: 40px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); }}
        .preview-frame-web {{ width: 100%; height: 100%; max-width: 1200px; border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1); }}
    </style>
</head>
<body class="bg-gray-100 h-screen flex flex-col overflow-hidden">
    <header class="bg-white border-b border-gray-200 h-14 flex items-center justify-between px-6 flex-none z-20">
        <div class="flex items-center gap-4">
            <h1 class="font-bold text-gray-900 text-lg">{project_name}</h1>
            <span class="text-xs text-gray-400 bg-indigo-50 text-indigo-600 px-2 py-1 rounded">研发预览版</span>
        </div>
        <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm text-gray-500">
                <span>视图:</span>
                <select id="previewType" class="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="auto">自动</option>
                    <option value="mobile">移动端</option>
                    <option value="web">网页端</option>
                </select>
            </div>
        </div>
    </header>

    <div class="flex-1 flex overflow-hidden">
        <aside class="w-64 bg-white border-r border-gray-200 flex flex-col">
            <div class="p-4 border-b border-gray-100">
                <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider">页面导航</h3>
            </div>
            <div id="flowchartEntry" class="p-3 border-b border-gray-100 cursor-pointer hover:bg-indigo-50 transition-colors">
                <div class="flex items-center gap-3 text-indigo-600">
                    <i class="fas fa-project-diagram"></i>
                    <span class="font-medium">页面流程图</span>
                </div>
            </div>
            <div id="pageList" class="flex-1 overflow-y-auto scrollbar-thin"></div>
        </aside>

        <main class="flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-200">
            <div id="flowchartView" class="flex-1 bg-white m-4 rounded-xl shadow-sm overflow-auto hidden">
                <div class="p-6">
                    <h2 class="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
                        <i class="fas fa-project-diagram text-indigo-500"></i>
                        页面流程图
                    </h2>
                    <div id="flowchartContainer" class="min-h-[400px]"></div>
                </div>
            </div>
            <div id="previewContainer" class="flex-1 flex items-center justify-center p-4">
                <div id="previewWrapper" class="bg-white overflow-hidden preview-frame-mobile">
                    <iframe id="previewFrame" class="w-full h-full border-0" src="prototype/index.html"></iframe>
                </div>
            </div>
        </main>

        <aside id="prdSidebar" class="prd-sidebar expanded bg-white border-l border-gray-200 flex flex-col">
            <button id="prdToggle" 
                class="absolute left-0 top-1/2 -translate-y-1/2 w-6 h-20 bg-indigo-600 hover:bg-indigo-700 text-white rounded-l-lg flex items-center justify-center cursor-pointer z-20 shadow-lg"
                style="transform: translateX(-100%) translateY(-50%);">
                <i class="fas fa-chevron-right text-xs"></i>
            </button>
            <div id="prdCollapsedLabel" class="flex-1 items-center justify-center cursor-pointer hover:bg-gray-50 hidden">
                <span class="text-gray-500 text-sm font-medium" style="writing-mode: vertical-lr; transform: rotate(180deg);">PRD 文档</span>
            </div>
            <div id="prdContent" class="flex-1 flex flex-col overflow-hidden">
                <div class="p-4 border-b border-gray-100 flex items-center justify-between flex-none">
                    <div class="flex items-center gap-2">
                        <i class="fas fa-file-alt text-indigo-500"></i>
                        <span class="font-semibold text-gray-800">PRD 文档</span>
                    </div>
                    <div id="prdPageName" class="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">home</div>
                </div>
                <div id="prdPreview" class="flex-1 overflow-y-auto p-4">
                    <div id="prdPreviewContent" class="markdown-body text-sm"></div>
                </div>
            </div>
        </aside>
    </div>

    <script>
        // ========== 内联数据 ==========
        const PAGES = {pages_json};
        const PRD_DATA = {prd_json};
        const TRANSITIONS = {transitions_json};
        const MODALS = {modals_json};
        const MERMAID_CODE = `{mermaid_code}`;

        // ========== 状态 ==========
        let currentPage = PAGES.length > 0 ? PAGES[0].name : 'home';
        let prdExpanded = true;

        const $ = id => document.getElementById(id);
        const previewFrame = $('previewFrame');
        const previewWrapper = $('previewWrapper');

        document.addEventListener('DOMContentLoaded', () => {{
            renderPageList();
            showPrd(currentPage);
            
            previewFrame.onload = () => {{
                detectPreviewType();
                startPageDetection();
            }};
            
            $('prdToggle').onclick = togglePrdSidebar;
            $('prdCollapsedLabel').onclick = togglePrdSidebar;
            $('flowchartEntry').onclick = showFlowchart;
            $('previewType').onchange = (e) => {{
                if (e.target.value === 'mobile') setPreviewMode('mobile');
                else if (e.target.value === 'web') setPreviewMode('web');
                else detectPreviewType();
            }};
            
            mermaid.initialize({{ startOnLoad: false, theme: 'default' }});
        }});

        function detectPreviewType() {{
            try {{
                const doc = previewFrame.contentDocument || previewFrame.contentWindow.document;
                const w = Math.max(doc.body.scrollWidth, doc.body.offsetWidth);
                setPreviewMode(w <= 500 ? 'mobile' : 'web');
            }} catch (e) {{ setPreviewMode('mobile'); }}
        }}

        function setPreviewMode(mode) {{
            previewWrapper.className = mode === 'mobile' 
                ? 'bg-white overflow-hidden preview-frame-mobile' 
                : 'bg-white overflow-hidden preview-frame-web';
        }}

        function togglePrdSidebar() {{
            prdExpanded = !prdExpanded;
            const sidebar = $('prdSidebar');
            const label = $('prdCollapsedLabel');
            const content = $('prdContent');
            const toggle = $('prdToggle');
            
            if (prdExpanded) {{
                sidebar.classList.remove('collapsed'); sidebar.classList.add('expanded');
                label.classList.add('hidden'); content.classList.remove('hidden');
                toggle.innerHTML = '<i class="fas fa-chevron-right text-xs"></i>';
            }} else {{
                sidebar.classList.remove('expanded'); sidebar.classList.add('collapsed');
                label.classList.remove('hidden'); label.classList.add('flex'); content.classList.add('hidden');
                toggle.innerHTML = '<i class="fas fa-chevron-left text-xs"></i>';
            }}
        }}

        function renderPageList() {{
            const list = $('pageList');
            if (PAGES.length === 0) {{
                list.innerHTML = '<div class="p-4 text-center text-gray-400 text-sm">无页面</div>';
                return;
            }}
            list.innerHTML = PAGES.map(p => `
                <div class="page-item px-4 py-3 cursor-pointer ${{p.name === currentPage ? 'active' : ''}}"
                     onclick="navigateToPage('${{p.name}}')">
                    <div class="flex items-center gap-3">
                        <i class="fas fa-file text-gray-400"></i>
                        <div>
                            <div class="font-medium text-gray-800">${{p.label}}</div>
                            <div class="text-xs text-gray-400">${{p.name}}</div>
                        </div>
                        ${{PRD_DATA[p.name] ? '<i class="fas fa-book text-indigo-400 ml-auto" title="有PRD"></i>' : ''}}
                    </div>
                </div>
            `).join('');
        }}

        function navigateToPage(pageName) {{
            console.log('[Viewer] 切换到页面:', pageName);
            $('flowchartView').classList.add('hidden');
            $('previewContainer').classList.remove('hidden');
            
            // 使用 postMessage 发送导航请求 (file:// 协议下唯一可行的方式)
            try {{
                const w = previewFrame.contentWindow;
                w.postMessage({{ type: 'navigateTo', page: pageName }}, '*');
                console.log('[Viewer] 已发送 postMessage');
            }} catch (e) {{
                console.log('[Viewer] postMessage 失败:', e);
            }}
            
            currentPage = pageName;
            renderPageList();
            showPrd(pageName);
        }}

        function showPrd(pageName) {{
            $('prdPageName').textContent = pageName;
            const content = PRD_DATA[pageName];
            $('prdPreviewContent').innerHTML = content 
                ? marked.parse(content) 
                : '<p class="text-gray-400">此页面暂无 PRD 文档</p>';
        }}

        async function showFlowchart() {{
            $('flowchartView').classList.remove('hidden');
            $('previewContainer').classList.add('hidden');
            
            const container = $('flowchartContainer');
            try {{
                const {{ svg }} = await mermaid.render('flowchart-svg', MERMAID_CODE);
                container.innerHTML = svg;
                
                if (MODALS.length > 0) {{
                    container.insertAdjacentHTML('beforeend', `
                        <div class="mt-6 p-4 bg-gray-50 rounded-lg">
                            <h3 class="font-semibold text-gray-700 mb-3">
                                <i class="fas fa-window-restore text-indigo-500 mr-2"></i>弹窗/交互组件
                            </h3>
                            <div class="grid grid-cols-2 gap-2">
                                ${{MODALS.map(m => `<div class="flex items-center gap-2 text-sm text-gray-600">
                                    <span class="w-2 h-2 bg-indigo-400 rounded-full"></span>${{m.label}}
                                </div>`).join('')}}
                            </div>
                        </div>
                    `);
                }}
                
                if (TRANSITIONS.length > 0) {{
                    container.insertAdjacentHTML('beforeend', `
                        <div class="mt-4 p-4 bg-blue-50 rounded-lg">
                            <h3 class="font-semibold text-gray-700 mb-3">
                                <i class="fas fa-exchange-alt text-blue-500 mr-2"></i>页面跳转 (${{TRANSITIONS.length}}个)
                            </h3>
                            <div class="space-y-1 text-sm">
                                ${{TRANSITIONS.map(t => `<div class="flex items-center gap-2 text-gray-600">
                                    <span class="font-medium">${{t.from}}</span>
                                    <i class="fas fa-arrow-right text-gray-400"></i>
                                    <span class="font-medium">${{t.to}}</span>
                                </div>`).join('')}}
                            </div>
                        </div>
                    `);
                }}
            }} catch (e) {{
                container.innerHTML = '<div class="text-red-500">流程图渲染失败</div><pre class="bg-gray-100 p-4 mt-4 rounded text-sm">' + MERMAID_CODE + '</pre>';
            }}
        }}

        function startPageDetection() {{
            setInterval(() => {{
                try {{
                    const w = previewFrame.contentWindow;
                    if (w && w.currentPage) {{
                        const p = w.currentPage.value || w.currentPage;
                        if (p && typeof p === 'string' && p !== currentPage) {{
                            currentPage = p;
                            renderPageList();
                            showPrd(p);
                        }}
                    }}
                }} catch (e) {{}}
            }}, 1000);
            
            window.addEventListener('message', (e) => {{
                if (e.data && e.data.type === 'pageChange' && e.data.page !== currentPage) {{
                    currentPage = e.data.page;
                    renderPageList();
                    showPrd(e.data.page);
                }}
            }});
        }}
    </script>
</body>
</html>'''
    
    return html


# ==================== 纯预览模式导出 ====================

def download_cdn_resource(url, cache_name):
    """下载 CDN 资源并缓存"""
    if not os.path.exists(CDN_CACHE_DIR):
        os.makedirs(CDN_CACHE_DIR)
    
    cache_path = os.path.join(CDN_CACHE_DIR, cache_name)
    
    # 如果缓存存在，直接读取
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # 下载资源
    try:
        print(f"    下载: {url[:60]}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
        
        # 缓存
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return content
    except Exception as e:
        print(f"    [警告] 下载失败: {e}")
        return None


def inline_cdn_resources(html_content):
    """将 CDN 资源内联到 HTML 中"""
    
    # 1. 处理 Vue 3
    vue_url = 'https://unpkg.com/vue@3/dist/vue.global.prod.js'
    vue_content = download_cdn_resource(vue_url, 'vue3.prod.js')
    if vue_content:
        html_content = re.sub(
            r'<script\s+src=["\']https://unpkg\.com/vue@3[^"]*["\']>\s*</script>',
            f'<script>/* Vue 3 Production */\n{vue_content}</script>',
            html_content
        )
    
    # 2. 处理 Tailwind CSS - 使用 Play CDN 的精简方案
    # Tailwind CDN 是运行时编译的，无法完全内联，保留原样
    # 但可以添加备用样式
    
    # 3. 处理 Font Awesome - 使用子集方案
    # 只内联常用的基础样式，图标通过 Unicode 保留
    fa_basic_css = '''
    /* Font Awesome Basic - Inlined */
    .fa, .fas, .far, .fab, .fa-solid, .fa-regular, .fa-brands {
        font-family: 'Font Awesome 6 Free', 'Font Awesome 6 Brands', sans-serif;
        font-style: normal;
        font-weight: 900;
        display: inline-block;
    }
    .fa-regular, .far { font-weight: 400; }
    '''
    
    # 检查是否已经有 Font Awesome
    if 'font-awesome' in html_content.lower() or 'fontawesome' in html_content.lower():
        # 保留 CDN 链接，因为图标字体需要在线加载
        pass
    
    return html_content


def export_preview_only(project_name):
    """纯预览模式导出 - 只导出原型本身"""
    project_dir = os.path.join(PROJECTS_DIR, project_name)
    export_dir = os.path.join(EXPORTS_DIR, project_name + '_预览版')
    
    # 清理并创建导出目录
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
    os.makedirs(export_dir)
    
    print(f"\n[1/4] 复制原型文件...")
    
    # 读取原型 HTML
    html_path = os.path.join(project_dir, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 复制静态资源目录
    for item in os.listdir(project_dir):
        if item in ['index.html', 'prd', 'record.json', 'prompt.txt', 'reference']:
            continue  # 跳过这些文件
        
        src = os.path.join(project_dir, item)
        dst = os.path.join(export_dir, item)
        
        if os.path.isdir(src):
            shutil.copytree(src, dst)
            print(f"    复制目录: {item}/")
        else:
            shutil.copy2(src, dst)
    
    print(f"[2/4] 优化资源引用...")
    
    # 尝试内联一些关键资源（可选）
    # html_content = inline_cdn_resources(html_content)
    
    # 添加离线提示和备用样式
    offline_notice = '''
<!-- 纯预览模式 - 需要网络加载外部资源 -->
<noscript>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; }
        .offline-notice { background: #fef3cd; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
    </style>
    <div class="offline-notice">⚠️ 请启用 JavaScript 以查看此原型</div>
</noscript>
'''
    
    if '<head>' in html_content:
        html_content = html_content.replace('<head>', '<head>\n' + offline_notice)
    
    print(f"[3/4] 保存导出文件...")
    
    # 保存 HTML
    output_path = os.path.join(export_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"[4/4] 生成说明文件...")
    
    # 创建 README
    display_name = project_name.split('_')[0]
    readme = f'''# {display_name} - 原型预览版

## 使用方法

**直接双击 `index.html` 即可在浏览器中查看！**

> ⚠️ 注意：此版本需要联网才能正常显示（依赖在线 CSS/JS 库）
> 如果无法访问外网，请联系发送者获取研发版本。

## 操作说明

- 这是一个交互式原型，可以点击按钮和链接进行页面跳转
- 在手机上查看效果更佳（或使用浏览器的移动端模拟功能）

---
导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
导出模式: 纯预览版
'''
    with open(os.path.join(export_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
    
    return export_dir


# ==================== 内嵌模式导出 ====================

def export_embedded(project_name):
    """内嵌模式导出 - 原型内嵌到预览框架中，单文件可分享"""
    project_dir = os.path.join(PROJECTS_DIR, project_name)
    export_dir = os.path.join(EXPORTS_DIR, project_name + '_内嵌版')
    
    # 清理并创建导出目录
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
    os.makedirs(export_dir)
    
    print(f"\n[1/4] 读取原型文件...")
    
    # 读取原型 HTML
    html_path = os.path.join(project_dir, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        prototype_html = f.read()
    
    print(f"[2/4] 处理图片资源...")
    
    # 收集并内嵌图片资源
    images_dir = os.path.join(project_dir, 'images')
    userimages_dir = os.path.join(project_dir, 'userimages')
    
    def embed_images_base64(html, img_dir, prefix):
        """将图片转为 base64 内嵌到 HTML 中"""
        if not os.path.exists(img_dir):
            return html
        
        for img_file in os.listdir(img_dir):
            img_path = os.path.join(img_dir, img_file)
            if os.path.isfile(img_path):
                try:
                    with open(img_path, 'rb') as f:
                        img_data = base64.b64encode(f.read()).decode('utf-8')
                    
                    # 确定 MIME 类型
                    ext = img_file.lower().split('.')[-1]
                    mime_types = {
                        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                        'gif': 'image/gif', 'svg': 'image/svg+xml', 'webp': 'image/webp'
                    }
                    mime = mime_types.get(ext, 'image/png')
                    
                    # 替换图片引用
                    data_uri = f'data:{mime};base64,{img_data}'
                    html = html.replace(f'{prefix}/{img_file}', data_uri)
                    html = html.replace(f'{prefix}\\{img_file}', data_uri)
                except Exception as e:
                    print(f"    [警告] 无法处理图片 {img_file}: {e}")
        
        return html
    
    prototype_html = embed_images_base64(prototype_html, images_dir, 'images')
    prototype_html = embed_images_base64(prototype_html, userimages_dir, 'userimages')
    
    print(f"[3/4] 生成内嵌预览页面...")
    
    # 将原型 HTML 进行 Base64 编码，通过 JS 解码后用 Blob URL 加载
    prototype_b64 = base64.b64encode(prototype_html.encode('utf-8')).decode('utf-8')
    
    display_name = project_name.split('_')[0]
    
    # 生成带预览框架的 HTML - 使用浮动小图标样式
    embedded_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{display_name} - 原型预览</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
        
        /* 预览框架 */
        .preview-frame-mobile {{
            width: 390px;
            height: 844px;
            border-radius: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }}
        .preview-frame-web {{
            width: 100%;
            height: 100%;
            max-width: 1400px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}
        
        /* 浮动工具栏 */
        .toolbar-wrapper {{
            position: fixed;
            top: 16px;
            right: 16px;
            z-index: 1000;
        }}
        .toolbar-trigger {{
            width: 36px;
            height: 36px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
            transition: all 0.2s ease;
        }}
        .toolbar-trigger:hover {{
            background: #fff;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        }}
        .toolbar-trigger i {{
            color: #6366f1;
            font-size: 14px;
        }}
        .toolbar-panel {{
            position: absolute;
            top: 0;
            right: 0;
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 12px;
            padding: 12px 16px;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
            display: none;
            flex-direction: column;
            gap: 8px;
            min-width: 140px;
        }}
        .toolbar-wrapper.expanded .toolbar-trigger {{ display: none; }}
        .toolbar-wrapper.expanded .toolbar-panel {{ display: flex; }}
        
        /* 视图选择按钮 */
        .view-btn {{
            padding: 6px 10px;
            font-size: 12px;
            border-radius: 6px;
            border: 1px solid #e5e7eb;
            background: #fff;
            color: #6b7280;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .view-btn:hover {{ border-color: #6366f1; color: #6366f1; }}
        .view-btn.active {{ background: #6366f1; border-color: #6366f1; color: #fff; }}
    </style>
</head>
<body class="bg-gray-200 h-screen flex items-center justify-center overflow-hidden">
    <!-- 浮动工具栏 -->
    <div class="toolbar-wrapper" id="toolbar">
        <div class="toolbar-trigger" onclick="toggleToolbar()">
            <i class="fas fa-cog"></i>
        </div>
        <div class="toolbar-panel">
            <div class="text-xs text-gray-400 mb-1">视图切换</div>
            <div class="flex gap-1">
                <button class="view-btn active" data-view="auto" onclick="setView('auto')">Auto</button>
                <button class="view-btn" data-view="web" onclick="setView('web')">Web</button>
                <button class="view-btn" data-view="mobile" onclick="setView('mobile')">App</button>
            </div>
        </div>
    </div>

    <!-- 预览区域 -->
    <div id="previewWrapper" class="bg-white overflow-hidden preview-frame-mobile">
        <iframe id="previewFrame" class="w-full h-full border-0"></iframe>
    </div>

    <script>
        const previewFrame = document.getElementById('previewFrame');
        const previewWrapper = document.getElementById('previewWrapper');
        const toolbar = document.getElementById('toolbar');
        let currentView = 'auto';

        // 原型 HTML (Base64 编码)
        const prototypeB64 = "{prototype_b64}";

        // 解码并加载到 iframe (正确处理 UTF-8)
        function loadPrototype() {{
            try {{
                // atob 返回的是 Latin-1 字符串，需要转换为 UTF-8
                const binaryString = atob(prototypeB64);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {{
                    bytes[i] = binaryString.charCodeAt(i);
                }}
                const html = new TextDecoder('utf-8').decode(bytes);
                const blob = new Blob([html], {{ type: 'text/html; charset=utf-8' }});
                const url = URL.createObjectURL(blob);
                previewFrame.src = url;
            }} catch (e) {{
                console.error('加载原型失败:', e);
            }}
        }}

        // 页面加载完成后自动检测
        previewFrame.onload = function() {{
            if (currentView === 'auto') {{
                detectPreviewType();
            }}
        }};

        function detectPreviewType() {{
            try {{
                const doc = previewFrame.contentDocument || previewFrame.contentWindow.document;
                const htmlContent = doc.documentElement.innerHTML;
                const body = doc.body;

                // 移动端特征检测
                const hasMobileFeatures =
                    htmlContent.includes('max-w-md') ||
                    htmlContent.includes('max-w-sm') ||
                    htmlContent.includes('max-width: 430px') ||
                    htmlContent.includes('max-width: 480px') ||
                    htmlContent.includes('max-w-[480px]') ||
                    htmlContent.includes('user-scalable=no') ||
                    doc.querySelector('[class*="bottom-nav"]') !== null ||
                    doc.querySelector('[class*="safe-area"]') !== null ||
                    htmlContent.includes('router-view');

                // Web 端特征检测
                const hasWebFeatures =
                    doc.querySelector('aside') !== null ||
                    doc.querySelector('[class*="sidebar"]') !== null ||
                    htmlContent.includes('ant-dark') ||
                    htmlContent.includes('ant-table') ||
                    htmlContent.includes('w-64') ||
                    htmlContent.includes('w-72') ||
                    doc.querySelector('table') !== null;

                if (hasMobileFeatures && !hasWebFeatures) {{
                    setPreviewMode('mobile');
                }} else if (hasWebFeatures && !hasMobileFeatures) {{
                    setPreviewMode('web');
                }} else {{
                    const maxWidth = Math.max(body.scrollWidth, body.offsetWidth);
                    setPreviewMode(maxWidth <= 500 ? 'mobile' : 'web');
                }}
            }} catch (e) {{
                console.log('自动检测失败，默认移动端:', e);
                setPreviewMode('mobile');
            }}
        }}

        function setPreviewMode(mode) {{
            if (mode === 'mobile') {{
                previewWrapper.className = 'bg-white overflow-hidden preview-frame-mobile';
            }} else {{
                previewWrapper.className = 'bg-white overflow-hidden preview-frame-web';
            }}
        }}

        function setView(view) {{
            currentView = view;
            document.querySelectorAll('.view-btn').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.view === view);
            }});
            if (view === 'auto') detectPreviewType();
            else if (view === 'mobile') setPreviewMode('mobile');
            else setPreviewMode('web');
            // 收起工具栏
            toolbar.classList.remove('expanded');
        }}

        function toggleToolbar() {{
            toolbar.classList.toggle('expanded');
        }}

        // 点击外部关闭工具栏
        document.addEventListener('click', function(e) {{
            if (!toolbar.contains(e.target)) {{
                toolbar.classList.remove('expanded');
            }}
        }});

        // 初始化
        loadPrototype();
    </script>
</body>
</html>'''
    
    print(f"[4/4] 保存导出文件...")
    
    # 保存 HTML
    output_path = os.path.join(export_dir, f'{display_name}_内嵌版.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(embedded_html)
    
    # 创建 README
    readme = f'''# {display_name} - 内嵌预览版

## 使用方法

**直接双击 `{display_name}_内嵌版.html` 即可在浏览器中查看！**

## 功能说明

点击右上角的齿轮图标可以切换视图：
- **Auto** - 自动检测项目类型
- **Web** - 网页端全宽显示
- **App** - 移动端手机框显示

> ⚠️ 注意：需要联网才能正常显示

---
导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
'''
    with open(os.path.join(export_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
    
    return export_dir


def export_project(project_name, mode='dev'):
    """导出项目
    
    Args:
        project_name: 项目名称
        mode: 导出模式 - 'dev' 研发模式, 'preview' 纯预览模式, 'embedded' 内嵌模式
    """
    if mode == 'preview':
        return export_preview_only(project_name)
    elif mode == 'embedded':
        return export_embedded(project_name)
    
    # 以下是原有的研发模式导出逻辑
    project_dir = os.path.join(PROJECTS_DIR, project_name)
    export_dir = os.path.join(EXPORTS_DIR, project_name)
    
    # 清理并创建导出目录
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
    os.makedirs(export_dir)
    os.makedirs(os.path.join(export_dir, 'prototype'))
    
    print(f"\n[1/6] 复制原型文件...")
    # 复制原型文件（排除 prd 目录，因为会内联）
    src_dir = project_dir
    dst_dir = os.path.join(export_dir, 'prototype')
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dst_dir, item)
        if item == 'prd':
            continue  # PRD 会内联，不需要复制
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    
    print(f"[2/6] 注入页面导航支持...")
    # 为导出的原型 HTML 注入页面导航监听器
    prototype_html_path = os.path.join(dst_dir, 'index.html')
    if os.path.exists(prototype_html_path):
        with open(prototype_html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 注入 window.currentPage 暴露代码
        expose_pattern = r'(return\s*\{\s*\n?\s*currentPage)'
        if re.search(expose_pattern, html_content) and 'window.currentPage = currentPage' not in html_content:
            expose_replacement = r'// 暴露 currentPage 到 window (导出时注入)\n                window.currentPage = currentPage;\n\n                \1'
            html_content = re.sub(expose_pattern, expose_replacement, html_content, count=1)
            print("    已暴露 currentPage 到 window")
        
        # 注入消息监听器
        listener_script = '''
<!-- 页面导航监听器 (导出时注入) -->
<script>
(function() {
    var checkInterval = setInterval(function() {
        if (window.currentPage) {
            clearInterval(checkInterval);
            console.log('[原型] currentPage 已就绪');
        }
    }, 100);
    
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'navigateTo') {
            var pageName = event.data.page;
            console.log('[原型] 收到页面切换请求:', pageName);
            if (window.currentPage && window.currentPage.value !== undefined) {
                window.currentPage.value = pageName;
                console.log('[原型] 已切换到页面:', pageName);
            }
            if (window.parent !== window) {
                window.parent.postMessage({ type: 'pageChange', page: pageName }, '*');
            }
        }
    });
    
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
        
        # 移除旧的监听器（如果有）并注入新的
        if '页面导航监听器' in html_content:
            old_pattern = r'<!-- 页面导航监听器.*?</script>\s*'
            html_content = re.sub(old_pattern, '', html_content, flags=re.DOTALL)
        
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', listener_script + '\n</body>')
        elif '</html>' in html_content:
            html_content = html_content.replace('</html>', listener_script + '\n</html>')
        
        with open(prototype_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("    已注入页面导航监听器")
    
    print(f"[3/6] 解析原型页面...")
    # 读取原型 HTML
    html_path = os.path.join(project_dir, 'index.html')
    html_content = read_file(html_path)
    
    # 提取页面列表
    pages = extract_pages_from_html(html_content)
    print(f"    发现 {len(pages)} 个页面")
    
    print(f"[4/6] 读取 PRD 文档...")
    # 读取 PRD 文件
    prd_dir = os.path.join(project_dir, 'prd')
    prd_data = {}
    if os.path.exists(prd_dir):
        for f in os.listdir(prd_dir):
            if f.endswith('.md'):
                page_name = f[:-3]
                content = read_file(os.path.join(prd_dir, f))
                if content.strip():
                    prd_data[page_name] = content
        print(f"    加载 {len(prd_data)} 个 PRD 文档")
    else:
        print(f"    未找到 PRD 目录")
    
    print(f"[5/6] 生成流程图数据...")
    # 提取跳转关系和弹窗
    transitions = extract_transitions(html_content, pages)
    modals = extract_modals(html_content)
    mermaid_code = generate_mermaid_code(pages, transitions)
    print(f"    {len(transitions)} 个跳转, {len(modals)} 个弹窗")
    
    print(f"[6/6] 生成预览器...")
    # 生成独立 HTML
    display_name = project_name.split('_')[0]
    standalone_html = generate_standalone_html(
        display_name, pages, prd_data, transitions, modals, mermaid_code
    )
    
    # 保存
    output_path = os.path.join(export_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(standalone_html)
    
    # 创建 README
    readme = f'''# {display_name} - 原型预览包

## 使用方法

**直接双击 `index.html` 即可在浏览器中查看！**

无需安装任何软件，无需启动服务器。

## 功能说明

- **左侧**：页面导航列表，点击切换页面
- **中间**：原型预览，支持移动端/网页端视图切换
- **右侧**：PRD 文档查看
- **流程图**：点击"页面流程图"查看页面跳转关系

## 文件说明

- `index.html` - 预览器（双击打开）
- `prototype/` - 原型资源文件

---
导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
'''
    with open(os.path.join(export_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
    
    return export_dir

def main():
    print("\n" + "="*50)
    print("  原型项目导出工具")
    print("  支持研发模式、纯预览模式、内嵌模式")
    print("="*50 + "\n")
    
    projects = list_projects()
    
    if not projects:
        print("[错误] 未找到任何项目！")
        input("\n按回车键退出...")
        return
    
    print("可用项目列表:")
    print("-" * 40)
    for i, p in enumerate(projects, 1):
        print(f"  {i}. {p}")
    print("-" * 40)
    
    try:
        choice = input(f"\n请输入项目编号 (1-{len(projects)}): ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(projects):
            raise ValueError()
        project_name = projects[idx]
    except:
        print("\n[错误] 无效的选择！")
        input("\n按回车键退出...")
        return
    
    print(f"\n选择的项目: {project_name}")
    
    # 选择导出模式
    print("\n" + "-" * 40)
    print("请选择导出模式:")
    print("-" * 40)
    print("  [1] 研发模式  - 包含页面导航、PRD 文档、流程图")
    print("  [2] 纯预览模式 - 仅原型本身，可直接打开查看")
    print("  [3] 内嵌模式  - 原型内嵌到预览框架中，单文件可分享")
    print("-" * 40)
    
    try:
        mode_choice = input("\n请输入模式 (1/2/3): ").strip()
        if mode_choice == '2':
            export_mode = 'preview'
            mode_name = '纯预览模式'
        elif mode_choice == '3':
            export_mode = 'embedded'
            mode_name = '内嵌模式'
        else:
            export_mode = 'dev'
            mode_name = '研发模式'
    except:
        export_mode = 'dev'
        mode_name = '研发模式'
    
    print(f"\n导出模式: {mode_name}")
    print("\n开始导出...\n")
    
    try:
        export_dir = export_project(project_name, mode=export_mode)
        print("\n" + "="*50)
        print("  导出成功！")
        print("="*50)
        print(f"\n导出目录: {export_dir}")
        
        if export_mode == 'preview':
            print(f"\n包含文件:")
            print(f"  ├─ index.html    (双击打开)")
            print(f"  ├─ README.md     (使用说明)")
            print(f"  └─ userimages/   (图片资源)")
            print(f"\n发送给他人:")
            print(f"  1. 将整个文件夹打包成 ZIP")
            print(f"  2. 发送 ZIP 给对方")
            print(f"  3. 对方解压后双击 index.html 即可查看")
            print(f"\n⚠️ 注意: 纯预览模式需要联网才能正常显示")
        elif export_mode == 'embedded':
            display_name = project_name.split('_')[0]
            print(f"\n包含文件:")
            print(f"  ├─ {display_name}_内嵌版.html  (双击打开)")
            print(f"  └─ README.md                    (使用说明)")
            print(f"\n发送给他人:")
            print(f"  直接发送 '{display_name}_内嵌版.html' 单个文件即可！")
            print(f"  对方双击打开即可在预览框架中查看原型")
            print(f"\n功能说明:")
            print(f"  - Auto: 自动检测移动端/Web端")
            print(f"  - Web:  网页端全宽显示")
            print(f"  - App:  移动端手机框显示")
            print(f"\n⚠️ 注意: 内嵌模式需要联网才能正常显示")
        else:
            print(f"\n包含文件:")
            print(f"  ├─ index.html    (双击打开)")
            print(f"  ├─ README.md     (使用说明)")
            print(f"  └─ prototype/    (原型资源)")
            print(f"\n发送给研发:")
            print(f"  1. 将 '{os.path.basename(export_dir)}' 文件夹打包成 ZIP")
            print(f"  2. 发送 ZIP 给研发")
            print(f"  3. 研发解压后双击 index.html 即可查看")
        
        # 询问是否打开目录
        open_dir = input("\n是否打开导出目录? (Y/N): ").strip().upper()
        if open_dir == 'Y':
            os.startfile(export_dir)
            
    except Exception as e:
        print(f"\n[错误] 导出失败: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按回车键退出...")

if __name__ == '__main__':
    main()
