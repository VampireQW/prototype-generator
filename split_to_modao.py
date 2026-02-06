"""
split_to_modao.py - Vue SPA Splitter for Modao Import
Splits a Vue single-page application into multiple standalone HTML files.
Supports both legacy v-if pages and Vue Router pages.
Extracts Modals, Transitions, and States as separate pages for Modao interaction.
"""

import os
import re
import sys
import shutil

# Configuration for State/Modal Pages
# These are "sub-states" that exist ON TOP of a base page.
STATE_PAGES = [
    {
        "name": "cameraModal",
        "description": "拍照上传弹窗",
        "base_page": "scan", # Matches route path or page name
        "set_true": ["showPhotoModal"] 
    },
    {
        "name": "loadingState",
        "description": "智批 Loading 状态",
        "base_page": "scan",
        "set_true": ["isSubmitting"]
    },
    {
        "name": "scanAnimation",
        "description": "扫描动态效果",
        "base_page": "english-translation", # Updated to match where isScanning is used
        "set_true": ["isScanning"]
    },
    {
        "name": "writingAnalyzing",
        "description": "作文分析中",
        "base_page": "writing-guidance",
        "set_true": ["isAnalyzing"]
    },
     {
        "name": "correctionAnalyzing",
        "description": "批改分析中",
        "base_page": "photo-correction",
        "set_true": ["isAnalyzing"]
    },
    {
        "name": "aiTyping",
        "description": "AI正在输入",
        "base_page": "ai-explain",
        "set_true": ["isTyping"]
    }
]

def convert_to_modao(project_path_arg):
    """
    Splits a Vue SPA index.html into multiple HTML files for Modao import.
    """
    
    project_path = os.path.abspath(project_path_arg)
    index_path = os.path.join(project_path, 'index.html')
    
    if not os.path.exists(index_path):
        print(f"错误: 未找到 index.html 于 {project_path}")
        return

    project_name = os.path.basename(os.path.normpath(project_path))
    parent_dir = os.path.dirname(project_path)
    root_generator_dir = os.path.dirname(parent_dir)
    tomodao_root = os.path.join(root_generator_dir, 'tomodao')
    output_dir = os.path.join(tomodao_root, project_name)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    
    print(f"项目名称: {project_name}")
    print(f"源文件: {index_path}")
    print(f"输出目录: {output_dir}")

    with open(index_path, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Copy assets first
    for item in os.listdir(project_path):
        s = os.path.join(project_path, item)
        if 'tomodao' in s: 
            continue
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(output_dir, item), dirs_exist_ok=True)
        elif os.path.isfile(s) and item != 'index.html':
            shutil.copy2(s, os.path.join(output_dir, item))

    # Detect Mode: Router vs Legacy
    if "createRouter" in original_content and "const routes =" in original_content:
        print("检测到 Vue Router 项目，使用路由模式拆分...")
        generate_router_pages(original_content, output_dir)
    else:
        print("未检测到路由，尝试使用 v-if 模式拆分...")
        convert_legacy_vif(original_content, output_dir)

    print(f"\n成功! 所有文件已生成到: {output_dir}")
    print("现在可以将这些HTML文件导入墨刀了。")


def convert_legacy_vif(original_content, output_dir):
    """Legacy v-if splitting logic"""
    page_pattern = r"v-if\s*=\s*[\"']currentPage\s*===?\s*['\"]([^'\"]+)['\"]"
    found_pages = set(re.findall(page_pattern, original_content))
    
    if not found_pages:
        print("未找到页面 (v-if=\"currentPage === '...')")
        return

    print(f"找到 {len(found_pages)} 个普通页面: {', '.join(sorted(found_pages))}")

    # Generate Standard Pages
    for page_name in found_pages:
        content = prepare_html_legacy(original_content, page_name, found_pages)
        write_file(output_dir, f"{page_name}.html", content)
        print(f"  ✓ {page_name}.html")
            
    # Generate State/Modal Pages (Legacy)
    # ... (Simplified for brevity, assuming new projects use Router) ...


def generate_router_pages(original_content, output_dir):
    """Generates pages based on Vue Router definitions"""
    
    # 1. Parse Routes
    # Simple regex to find path and component names in `const routes = [...]`
    # This is a bit rough but works for standard list definitions
    routes_block_match = re.search(r"const\s+routes\s*=\s*\[(.*?)\];", original_content, re.DOTALL)
    if not routes_block_match:
        print("无法解析 const routes = [...]")
        return

    routes_block = routes_block_match.group(1)
    
    # Find individual route objects: { path: '...', component: ... }
    # path: '(/[\w-]*)',?\s*component:\s*(\w+)
    route_pattern = r"path:\s*['\"]([^'\"]+)['\"]\s*,?\s*component:\s*(\w+)"
    found_routes = re.findall(route_pattern, routes_block)
    
    print(f"找到 {len(found_routes)} 个路由页面。")
    
    route_map = {} # path -> component_name
    
    for path, component in found_routes:
        # Determine filename
        if path == '/':
            filename = 'home'
        else:
            filename = path.strip('/').replace('/', '-')
        
        route_map[filename] = {'path': path, 'component': component}
        
        # Generate HTML
        content = prepare_html_router(original_content, path)
        write_file(output_dir, f"{filename}.html", content)
        print(f"  ✓ {filename}.html (Path: {path})")

    # 2. Generate State Pages for Router
    print(f"正在生成状态页面 (弹窗/Loading)...")
    for state in STATE_PAGES:
        # Find which router page this state belongs to
        
        # Match base_page to a filename key
        base_filename = state['base_page']
        
        # Check if this base file exists in our map (fuzzy match?)
        # For simplicity, assume base_page in config MATCHES one of the generated filenames (e.g. 'scan', 'home')
        # OR matches the route path directly.
        
        target_route = None
        target_filename = None
        
        if base_filename in route_map:
            target_route = route_map[base_filename]['path']
            target_filename = base_filename
        else:
            # Try to find by route path
            found = False
            for fname, val in route_map.items():
                if val['path'] == '/' + base_filename or val['path'] == base_filename:
                    target_route = val['path']
                    target_filename = fname
                    found = True
                    break
            if not found:
                # If checking for 'english-translation' but filename is 'english-translation' OK.
                pass

        if not target_route: 
             # Fallback: maybe the user configured a base_page that DOESNT correspond to a route (unlikely in this project structure)
             # But let's assume valid config.
             # Actually, let's just use the filename directly if we can't map it, but we need the route path for router.replace
             pass

        if target_route:
            content = prepare_html_router(original_content, target_route)
            
            # Now Inject State
            # We need to find the setup() of the COMPONENT used by this route.
            comp_name = route_map[target_filename]['component']
            
            # Locate component definition: `const CompName = { ... setup() { ... } }`
            # This is tricky with regex. 
            # Alternative: Global Injection via Mixin or just append to end of script if variables are global?
            # In this project, variables are inside `setup()`.
            
            # Strategy: Inject a Global Mixin or Plugin that forces these values? 
            # No, variables are local to components.
            # We must modify the Component code.
            
            # Find `const CompName = {`
            comp_idx = content.find(f"const {comp_name} = {{")
            if comp_idx != -1:
                # Find the `setup() {` inside this component
                setup_idx = content.find("setup()", comp_idx)
                if setup_idx != -1:
                    # Find the start of setup body `{`
                    setup_body_start = content.find("{", setup_idx) + 1
                    
                    # Inject code
                    injections = []
                    for var in state['set_true']:
                         injections.append(f"try {{ {var}.value = true; }} catch(e) {{ console.log('State injection failed for {var}'); }}")
                    
                    injection_code = "\n                onMounted(() => {\n                    " + "\n                    ".join(injections) + "\n                });\n"
                    
                    # Insert
                    content = content[:setup_body_start] + injection_code + content[setup_body_start:]
                    
                    write_file(output_dir, f"{state['name']}.html", content)
                    print(f"  ✓ {state['name']}.html (State: {state['description']})")
                else:
                    print(f"  [Error] Cannot find setup() for {comp_name}")
            else:
                 print(f"  [Error] Cannot find definition for {comp_name}")
        else:
            print(f"  [Skip] Base page '{base_filename}' not found in routes.")


def prepare_html_router(content, target_path):
    """
    Prepares HTML for a Router project.
    1. Injects `router.replace(...)` to force initial navigation.
    2. Updates `router.push` calls to be harmless or point to .html files?
       Actually, standard `router.push` works fine for SPA, but if we want *MPA* feel in Modao, 
       we might want to replace `router.push('/foo')` with `window.location.href='foo.html'`.
       
       Let's try to do the `router.push` replacement to keep Modao links working as external links.
    """
    
    modified_content = content
    
    # 1. Force Route on Mount
    # Look for `app.mount('#app')`
    mount_point = "app.mount('#app');"
    if mount_point in modified_content:
        injection = f"\n        router.replace('{target_path}');\n        "
        modified_content = modified_content.replace(mount_point, injection + mount_point)
        
    # 2. Transform router.push to window.location (Optional but good for Modao)
    # This regex matches `router.push('/path')` or `router.push("path")`
    # We want to change it to `window.location.href = 'path.html'`
    
    def replacer(match):
        raw_path = match.group(1) # e.g. /scan
        if raw_path == '/': return "window.location.href = 'home.html'"
        
        # Clean path
        clean_name = raw_path.strip('/').replace('/', '-')
        return f"window.location.href = '{clean_name}.html'"

    # Simple router.push string args
    modified_content = re.sub(r"router\.push\(['\"]([^'\"]+)['\"]\)", replacer, modified_content)
    
    # Also handle <button @click="$router.push('/skks')"> in templates?
    # The regex above mostly handles JS calls. Template calls are often `$router.push`.
    modified_content = re.sub(r"\$router\.push\(['\"]([^'\"]+)['\"]\)", replacer, modified_content)
    
    return modified_content


def prepare_html_legacy(content, page_name, all_pages):
    """Original legacy preparation logic"""
    modified_content = content
    
    # 1. Set currentPage
    modified_content = re.sub(
        r"const\s+currentPage\s*=\s*ref\(\s*['\"][^'\"]*['\"]\s*\)",
        f"const currentPage = ref('{page_name}')",
        modified_content,
        count=1
    )
    
    # 2. Replace Navigation
    def replace_navigation(match):
        target = match.group(1)
        if target in all_pages:
            return f"window.location.href = '{target}.html'"
        return match.group(0)
    
    modified_content = re.sub(
        r"currentPage\.value\s*=\s*['\"]([^'\"]+)['\"]",
        replace_navigation,
        modified_content
    )
    
    # 3. Inject Watcher
    if "const { createApp" in modified_content and ", watch" not in modified_content.split("const { createApp")[1].split("}")[0]:
        modified_content = modified_content.replace(
            "const { createApp",
            "const { createApp, watch"
        )
    
    watcher_code = f'''
                // Navigation watcher
                watch(currentPage, (newVal) => {{
                    if (newVal !== '{page_name}') {{
                        const knownPages = {str(list(all_pages))};
                        if (knownPages.includes(newVal)) {{
                             window.location.href = newVal + '.html';
                        }}
                    }}
                }});

                return {{'''
    
    modified_content = re.sub(
        r"return\s*\{",
        watcher_code,
        modified_content,
        count=1
    )
    
    return modified_content

def write_file(output_dir, filename, content):
    with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
        f.write(content)

def interactive_mode():
    """Interactive CLI"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    
    def scan_dir(dirname, label):
        path = os.path.join(base_dir, dirname)
        if os.path.exists(path):
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    candidates.append({"path": full_path, "name": item, "type": label})

    scan_dir("exports", "导出")
    scan_dir("projects", "项目")

    if not candidates:
        print("未在 exports 或 projects 目录下找到任何项目文件夹。")
        input("按回车键退出...")
        return

    print("\n[可用项目列表]:")
    for i, p in enumerate(candidates):
        print(f"  {i+1}. [{p['type']}] {p['name']}")
        
    print("\n--------------------------------------------------------")
    
    while True:
        choice = input("请输入要转换的项目编号 (输入 0 退出): ").strip()
        if choice == '0':
            return
            
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                target = candidates[idx]
                print(f"\n正在处理: {target['name']}")
                print("-" * 50)
                try:
                    convert_to_modao(target['path'])
                except Exception as e:
                    print(f"处理出错: {e}")
                    import traceback
                    traceback.print_exc()
                input("\n按回车键结束...")
                break
            else:
                print("无效的编号。")
        else:
            print("请输入数字。")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        convert_to_modao(sys.argv[1])
        # input("\n完成。按回车键退出...") # Commented out for batch usage
    else:
        interactive_mode()
