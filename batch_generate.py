# -*- coding: utf-8 -*-
"""
分批生成原型脚本
将大型项目拆分为多个批次生成，然后整合为完整项目
"""

import json
import os
import base64
import urllib.request
import urllib.parse
import ssl
import datetime
import shutil
import re
import time

# ==================== 配置 ====================
SOURCE_PROJECT = r"D:\ai project\ky_antigravity\原型生成器\projects\首页_+_扫码作答页_+_扫码结果页_+_题目详情页_+_A_20260125_5-41-16pm"
PROJECTS_DIR = r"D:\ai project\ky_antigravity\原型生成器\projects"
CONFIG_FILE = r"D:\ai project\ky_antigravity\原型生成器\config.json"

# 批次定义：每批包含的页面索引
BATCHES = [
    {
        "name": "批次1_核心流程",
        "pages": [0, 1, 2, 3, 4],  # 首页、扫码作答页、扫码结果页、题目详情页、AI讲解页
        "is_first": True
    },
    {
        "name": "批次2_作业模块", 
        "pages": [5, 6, 7, 8],  # 作业列表页、在线作答页、在线作答结果页、作业详情页
        "is_first": False
    },
    {
        "name": "批次3_错题本和我的",
        "pages": [9, 10, 11, 12, 13],  # 错题本页、错题列表页、AI答疑页、我的、学情报告页
        "is_first": False
    }
]

# ==================== 工具函数 ====================

def load_config():
    """加载配置文件"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_record():
    """加载项目记录"""
    record_path = os.path.join(SOURCE_PROJECT, 'record.json')
    with open(record_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def image_to_base64(image_path):
    """将图片转换为base64"""
    with open(image_path, 'rb') as f:
        data = f.read()
    
    ext = os.path.splitext(image_path)[1].lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    mime = mime_types.get(ext, 'image/png')
    
    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"

def build_prompt(record, page_indices, is_first_batch, all_pages):
    """构建AI prompt"""
    global_config = record['global']
    pages = record['pages']
    
    prompt_parts = []
    
    # 系统指令
    prompt_parts.append("你是专业的前端工程师和UI/UX设计师。")
    prompt_parts.append("请生成一个高保真的HTML原型页面。")
    prompt_parts.append("")
    
    # 技术栈
    prompt_parts.append("# 技术栈")
    prompt_parts.append("- Tailwind CSS (CDN)")
    prompt_parts.append("- Vue 3 (CDN)")
    prompt_parts.append("- FontAwesome (CDN)")
    prompt_parts.append("- ECharts (如需图表)")
    prompt_parts.append("- Google Fonts (Inter)")
    prompt_parts.append("")
    
    # 全局设计规范
    prompt_parts.append("# 全局设计规范")
    prompt_parts.append(f"- 主色: {global_config.get('primaryColor', '#004fff')}")
    prompt_parts.append(f"- 强调色: {global_config.get('secondaryColor', '#10b981')}")
    prompt_parts.append(f"- 背景模式: {'浅色' if global_config.get('backgroundMode') == 'light' else '深色'}")
    prompt_parts.append(f"- 组件风格: {global_config.get('componentStyle', 'Ant Design')}")
    prompt_parts.append("- 圆角: 0.5rem")
    prompt_parts.append("- 阴影: 使用柔和现代的阴影")
    prompt_parts.append("")
    
    # 页面需求
    prompt_parts.append("# 页面需求")
    prompt_parts.append("")
    
    # 如果是第一批，说明这是完整应用的入口
    if is_first_batch:
        prompt_parts.append("## 重要说明")
        prompt_parts.append("这是一个完整的移动端学生学习App原型，需要包含：")
        prompt_parts.append("1. 底部导航栏（首页、错题本、AI答疑、我的）")
        prompt_parts.append("2. 使用Vue 3的createApp实现页面路由切换")
        prompt_parts.append("3. 所有页面共享相同的UI风格和导航组件")
        all_page_names = [p['name'] for p in all_pages]
        prompt_parts.append(f"4. 应用包含以下所有页面（本批次生成部分页面）: {', '.join(all_page_names)}")
        prompt_parts.append("")
    else:
        prompt_parts.append("## 重要说明")
        prompt_parts.append("这是学生学习App的部分页面，需要：")
        prompt_parts.append("1. 保持与首页相同的UI风格")
        prompt_parts.append("2. 生成完整的Vue组件代码")
        prompt_parts.append("3. 每个页面作为独立的Vue组件")
        prompt_parts.append("")
    
    # 添加当前批次的页面需求
    for i, page_idx in enumerate(page_indices):
        page = pages[page_idx]
        page_num = i + 1
        
        prompt_parts.append(f"## 页面{page_num}: {page['name']}")
        
        if page.get('layout'):
            prompt_parts.append(f"**布局描述**: {page['layout']}")
        
        if page.get('features'):
            prompt_parts.append(f"**核心功能**: {page['features']}")
        
        if page.get('interaction'):
            prompt_parts.append(f"**交互说明**: {page['interaction']}")
        
        if page.get('images'):
            prompt_parts.append(f"**参考图**: 已附加{len(page['images'])}张参考图。请参考其布局结构。")
        
        prompt_parts.append("")
    
    # 输出要求
    prompt_parts.append("# 输出要求（重要！）")
    prompt_parts.append("")
    prompt_parts.append("请输出一个**完整的、独立的HTML文件**。")
    prompt_parts.append("")
    prompt_parts.append("要求：")
    prompt_parts.append("1. 所有CSS放在<style>标签中")
    prompt_parts.append("2. 所有JS放在<script>标签中")
    prompt_parts.append("3. 使用真实的示例数据（不要Lorem ipsum）")
    prompt_parts.append("4. 响应式设计")
    prompt_parts.append("5. 直接可在浏览器中打开使用")
    
    if is_first_batch:
        prompt_parts.append("6. 包含完整的Vue路由系统，支持页面切换")
        prompt_parts.append("7. 预留其他页面的路由占位（后续批次会生成）")
    else:
        prompt_parts.append("6. 输出可以直接复制到Vue应用中的组件代码")
    
    prompt_parts.append("")
    prompt_parts.append("输出格式：")
    prompt_parts.append("```html")
    prompt_parts.append("<!DOCTYPE html>")
    prompt_parts.append('<html lang="zh-CN">')
    prompt_parts.append("...完整代码...")
    prompt_parts.append("</html>")
    prompt_parts.append("```")
    
    return "\n".join(prompt_parts)

def call_ai_api(prompt, images, config):
    """调用AI API"""
    api_config = config['api']
    ai_options = config.get('ai_options', {})
    
    # 构建消息内容
    user_content = [{"type": "text", "text": prompt}]
    
    # 添加图片
    for img_base64 in images:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": img_base64}
        })
    
    messages = [
        {
            "role": "system", 
            "content": ai_options.get('system_prompt', 
                'You are a professional UI/UX Developer. Generate complete, standalone HTML prototypes with realistic data.')
        },
        {"role": "user", "content": user_content}
    ]
    
    request_body = json.dumps({
        "model": api_config.get('model', 'gpt-4'),
        "messages": messages,
        "max_tokens": ai_options.get('max_tokens', 100000),
        "temperature": ai_options.get('temperature', 0.7)
    }).encode('utf-8')
    
    url = f"{api_config.get('base_url', '')}/chat/completions"
    req = urllib.request.Request(url, data=request_body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f"Bearer {api_config.get('api_key', '')}")
    
    # 忽略SSL验证
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    timeout = ai_options.get('timeout', 300)
    print(f"[AI] 正在调用大模型... (超时: {timeout}s)")
    
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
        result = json.loads(response.read().decode('utf-8'))
    
    content = result['choices'][0]['message']['content']
    finish_reason = result['choices'][0].get('finish_reason', '')
    
    print(f"[AI] 响应长度: {len(content)} 字符, finish_reason: {finish_reason}")
    
    if finish_reason == 'length':
        print("[警告] AI响应可能被截断!")
    
    return content

def extract_html(content):
    """从AI响应中提取HTML"""
    # 尝试提取 ```html ... ``` 代码块
    pattern = r'```html\s*([\s\S]*?)```'
    matches = re.findall(pattern, content, re.IGNORECASE)
    
    if matches:
        # 返回最长的匹配（通常是完整的HTML）
        return max(matches, key=len).strip()
    
    # 如果没有代码块，尝试直接查找HTML
    if '<!DOCTYPE html>' in content or '<html' in content:
        start = content.find('<!DOCTYPE html>')
        if start == -1:
            start = content.find('<html')
        end = content.rfind('</html>') + len('</html>')
        if start >= 0 and end > start:
            return content[start:end]
    
    return content

def generate_batch(batch_info, record, config, all_pages):
    """生成单个批次"""
    print(f"\n{'='*60}")
    print(f"开始生成: {batch_info['name']}")
    print(f"包含页面: {[all_pages[i]['name'] for i in batch_info['pages']]}")
    print(f"{'='*60}")
    
    # 构建prompt
    prompt = build_prompt(record, batch_info['pages'], batch_info['is_first'], all_pages)
    
    # 收集图片
    images = []
    ref_folder = os.path.join(SOURCE_PROJECT, 'reference')
    
    for page_idx in batch_info['pages']:
        page = all_pages[page_idx]
        for img_name in page.get('images', []):
            img_path = os.path.join(ref_folder, img_name)
            if os.path.exists(img_path):
                try:
                    img_base64 = image_to_base64(img_path)
                    images.append(img_base64)
                    print(f"[图片] 加载: {img_name}")
                except Exception as e:
                    print(f"[警告] 无法加载图片 {img_name}: {e}")
    
    print(f"[信息] 共加载 {len(images)} 张图片")
    
    # 调用AI
    try:
        response = call_ai_api(prompt, images, config)
        html_content = extract_html(response)
        print(f"[成功] 生成HTML: {len(html_content)} 字符")
        return html_content
    except Exception as e:
        print(f"[错误] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def merge_batches(batch_results, record):
    """合并多个批次的生成结果"""
    print("\n" + "="*60)
    print("开始合并批次...")
    print("="*60)
    
    # 第一批应该是完整的应用框架
    if batch_results[0]:
        base_html = batch_results[0]
        print(f"[合并] 使用批次1作为基础框架: {len(base_html)} 字符")
        
        # TODO: 这里可以添加更复杂的合并逻辑
        # 目前简单返回第一批的结果，因为它应该包含完整的路由框架
        
        # 记录其他批次的页面，可以手动添加
        for i, html in enumerate(batch_results[1:], 2):
            if html:
                print(f"[信息] 批次{i}生成完成: {len(html)} 字符")
        
        return base_html
    
    return None

def create_output_project(html_content, record):
    """创建输出项目目录"""
    # 生成项目名称
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H-%M-%S')
    project_name = f"AI智学_学生端_完整版_{timestamp}"
    project_path = os.path.join(PROJECTS_DIR, project_name)
    
    print(f"\n[创建] 项目目录: {project_path}")
    os.makedirs(project_path, exist_ok=True)
    
    # 保存HTML
    html_path = os.path.join(project_path, 'index.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[保存] index.html: {len(html_content)} 字符")
    
    # 复制参考图片
    src_ref = os.path.join(SOURCE_PROJECT, 'reference')
    dst_ref = os.path.join(project_path, 'reference')
    if os.path.exists(src_ref):
        shutil.copytree(src_ref, dst_ref)
        print(f"[复制] reference 文件夹")
    
    # 创建images目录
    os.makedirs(os.path.join(project_path, 'images'), exist_ok=True)
    
    # 更新并保存record.json
    record['createdAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    record_path = os.path.join(project_path, 'record.json')
    with open(record_path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"[保存] record.json")
    
    # 生成并保存prompt.txt
    prompt_text = generate_full_prompt(record)
    prompt_path = os.path.join(project_path, 'prompt.txt')
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(prompt_text)
    print(f"[保存] prompt.txt")
    
    return project_path

def generate_full_prompt(record):
    """生成完整的prompt.txt内容"""
    global_config = record['global']
    pages = record['pages']
    
    lines = []
    lines.append("你是专业的前端工程师和UI/UX设计师。")
    lines.append("请生成一个高保真的HTML原型页面。")
    lines.append("")
    lines.append("# 技术栈")
    lines.append("- Tailwind CSS (CDN)")
    lines.append("- Vue 3 (CDN)")
    lines.append("- FontAwesome (CDN)")
    lines.append("- ECharts (如需图表)")
    lines.append("- Google Fonts (Inter)")
    lines.append("")
    lines.append("# 全局设计规范")
    lines.append(f"- 主色: {global_config.get('primaryColor', '#004fff')}")
    lines.append(f"- 强调色: {global_config.get('secondaryColor', '#10b981')}")
    lines.append(f"- 背景模式: {'浅色' if global_config.get('backgroundMode') == 'light' else '深色'}")
    lines.append(f"- 组件风格: {global_config.get('componentStyle', 'Ant Design')}")
    lines.append("- 圆角: 0.5rem")
    lines.append("- 阴影: 使用柔和现代的阴影")
    lines.append("")
    lines.append("# 页面需求")
    lines.append("")
    
    for i, page in enumerate(pages, 1):
        lines.append(f"## 页面{i}: {page['name']}")
        if page.get('layout'):
            lines.append(f"**布局**: {page['layout']}")
        if page.get('features'):
            lines.append(f"**核心功能**: {page['features']}")
        if page.get('interaction'):
            lines.append(f"**交互说明**: {page['interaction']}")
        if page.get('images'):
            lines.append(f"**参考图**: 已附加{len(page['images'])}张参考图。")
        lines.append("")
    
    lines.append("# 输出要求（重要！）")
    lines.append("")
    lines.append("请输出一个**完整的、独立的HTML文件**。")
    lines.append("")
    lines.append("要求：")
    lines.append("1. 所有CSS放在<style>标签中")
    lines.append("2. 所有JS放在<script>标签中")
    lines.append("3. 使用真实的示例数据（不要Lorem ipsum）")
    lines.append("4. 响应式设计")
    lines.append("5. 直接可在浏览器中打开使用")
    lines.append("")
    lines.append("输出格式：")
    lines.append("```html")
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="zh-CN">')
    lines.append("...完整代码...")
    lines.append("</html>")
    lines.append("```")
    
    return "\n".join(lines)

# ==================== 主函数 ====================

def main():
    print("="*60)
    print("AI智学 学生端原型 - 分批生成脚本")
    print("="*60)
    
    # 加载配置
    print("\n[加载] 配置文件...")
    config = load_config()
    print(f"[配置] API: {config['api']['base_url']}")
    print(f"[配置] 模型: {config['api']['model']}")
    
    # 加载项目记录
    print("\n[加载] 项目记录...")
    record = load_record()
    all_pages = record['pages']
    print(f"[信息] 共 {len(all_pages)} 个页面")
    
    # 分批生成
    batch_results = []
    for batch in BATCHES:
        html = generate_batch(batch, record, config, all_pages)
        batch_results.append(html)
        
        if html is None:
            print(f"\n[错误] {batch['name']} 生成失败，终止流程")
            return
        
        # 批次之间等待一下，避免API限流
        if batch != BATCHES[-1]:
            print("\n[等待] 3秒后继续下一批次...")
            time.sleep(3)
    
    # 合并结果
    final_html = merge_batches(batch_results, record)
    
    if final_html:
        # 创建输出项目
        output_path = create_output_project(final_html, record)
        
        print("\n" + "="*60)
        print("生成完成！")
        print(f"项目位置: {output_path}")
        print("="*60)
    else:
        print("\n[错误] 合并失败，未生成最终项目")

if __name__ == "__main__":
    main()
