"""预编译首页既有 Tailwind 工具类；运行时不依赖 CDN 或构建服务。"""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'src/vendor/tailwind-runtime.js'
if not RUNTIME.exists():
    raise FileNotFoundError('缺少 src/vendor/tailwind-runtime.js，请使用完整的仓库源码。')

source = '\n'.join((ROOT / f'src/{file}').read_text(encoding='utf-8') for file in ['index.html', 'script.js', 'home-ui.js'])
candidates = sorted(set(re.findall(r'[a-zA-Z0-9_!:/#.%\-\[\]()]+', source)))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.route('https://**/*', lambda route: route.abort())
    page.set_content('<div class="' + ' '.join(candidates) + '"></div>')
    page.add_script_tag(path=str(RUNTIME))
    page.evaluate("document.body.appendChild(document.createElement('span'))")
    page.wait_for_function("[...document.querySelectorAll('style')].some(s=>s.textContent.includes('.hidden'))")
    css = '\n'.join(page.locator('style').all_text_contents())
    assert '.hidden' in css and '.grid-cols-6' in css and '.fixed' in css
    target = ROOT / 'src/vendor/home-utilities.css'
    target.write_text('/*! Tailwind CSS v3.4.17 | MIT License | https://tailwindcss.com */\n' + css, encoding='utf-8')
    browser.close()
print(f'Compiled {len(css):,} bytes: {target}')
