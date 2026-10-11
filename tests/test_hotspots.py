"""真实浏览器验证热区发现、业务点击透传和 HTTP / file:// 研发导出。"""
import functools
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(ROOT))
import review_export

HTML = '''<!doctype html><html lang="zh-CN" data-proto-page="home" data-proto-state="default">
<meta charset="utf-8"><style>
body{margin:0;padding:24px;background:white;font:16px/1.7 "Microsoft YaHei"}
.controls{display:flex;gap:16px;flex-wrap:wrap;max-width:650px;align-items:center}
button,a,.action{padding:8px 12px} .action{border:1px solid gray}
#cursor{cursor:pointer} #offscreen{position:absolute;top:1500px}
#cursor-only{cursor:pointer}
#covered{position:absolute;left:30px;top:230px;width:110px;height:45px}
#cover{position:absolute;left:24px;top:224px;width:122px;height:57px;background:white}
#blank{position:fixed;bottom:20px;left:20px;width:180px;height:60px}
#clip{position:absolute;top:320px;left:24px;width:150px;height:30px;overflow:hidden}
#clipped{height:60px} #dark{position:absolute;top:380px;left:250px;background:rgb(18,21,25);padding:12px}
#darkbutton{color:white;background:transparent;border:1px solid gray}
</style><body><main class="controls">
<button id="button" data-proto-id="save">保存</button><a id="link" href="#details">详情</a>
<div id="cursor" class="action"><span>自定义按钮</span></div>
<div id="role" class="action" role="button">菜单</div>
<button id="export" style="cursor:pointer">导出</button><div id="cursor-only" class="action">静态卡片</div>
<a id="empty-link" href="#">静态链接</a><a id="void-link" href="javascript:void(0)">空链接</a>
<div id="explicit" class="action" data-proto-hotspot="true">区域操作</div>
<select id="select"><option>全部</option></select><input id="check" type="checkbox">
<input id="text" value="待填写"><button id="disabled" disabled>不可用</button>
<button id="aria" aria-disabled="true">禁用</button><button id="ignored" data-proto-hotspot="false">忽略</button>
<div inert><button id="inert">禁用区域</button></div><button id="hidden" hidden>隐藏</button>
<div data-prototype-owned><button id="owned">标注控件</button></div>
</main><button id="offscreen">屏幕外</button><button id="covered">遮挡</button><div id="cover"></div>
<div id="clip"><button id="clipped">局部可见</button></div>
<div id="dark"><button id="darkbutton">深色操作</button></div><div id="blank"></div><span id="details">订单详情</span>
<script>window.clicks=0;document.querySelector('#button').onclick=()=>clicks++;
document.querySelector('#cursor').addEventListener('click',()=>clicks++);
document.querySelector('#clipped').onclick=()=>clicks++;
document.querySelector('#darkbutton').onclick=()=>clicks++;</script></body></html>'''


@pytest.fixture(scope='module')
def browser():
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as p:
        try:
            instance = p.chromium.launch(headless=True)
        except api.Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip('需要 Playwright Chromium')
            raise
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width': 800, 'height': 600})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_content(review_export.inject_hotspot_bootstrap(HTML, inline=True))
    page.evaluate('ProtoHotspots.init()')
    yield page
    context.close()
    assert not errors, errors


def targets(page):
    return set(page.locator('.ph-box').evaluate_all('els=>els.map(e=>e.dataset.hotspotFor)'))


def test_hotspots_and_timed_disappearance(page):
    before = page.locator('body').inner_html()
    assert not targets(page)
    page.locator('#blank').click()
    expected = {'save', 'link', 'cursor', 'explicit', 'select', 'check', 'clipped', 'darkbutton'}
    assert targets(page) == expected
    assert page.locator('body').inner_html() == before, '提示不能修改业务元素'
    assert page.locator('.ph-box').all_text_contents() == [''] * len(expected), '热区不能带编号或展开标签'
    assert page.locator('.ph-layer').get_attribute('aria-hidden') == 'true'
    assert page.locator('.ph-box').first.evaluate("e=>getComputedStyle(e).pointerEvents") == 'none'
    first = page.locator('.ph-box').first.element_handle()
    page.wait_for_timeout(600)
    page.locator('#blank').click()
    assert first.evaluate('e=>e.isConnected'), '重复点击不重建或叠加提示'
    page.wait_for_function("!document.querySelector('.ph-box')", timeout=1800)


def test_business_click_and_input_do_not_trigger(page):
    page.locator('#blank').click()
    page.locator('#button').click()
    assert page.evaluate('clicks') == 1 and not targets(page)
    page.locator('#cursor span').click()
    assert page.evaluate('clicks') == 2 and not targets(page)
    page.locator('#link').click()
    assert page.evaluate('location.hash') == '#details' and not targets(page)
    page.locator('#text').click()
    page.locator('#text').fill('输入仍正常')
    page.locator('#check').check()
    assert page.locator('#text').input_value() == '输入仍正常' and not targets(page)
    page.locator('#button').focus()
    page.keyboard.press('Enter')
    assert page.evaluate('clicks') == 3 and not targets(page)
    page.locator('#blank').evaluate('e=>e.click()')
    assert not targets(page), '脚本和键盘事件不能触发空白点击提示'
    rect = page.locator('#blank').bounding_box()
    page.mouse.move(rect['x'] + 10, rect['y'] + 10)
    page.mouse.down()
    page.mouse.move(rect['x'] + 60, rect['y'] + 10)
    page.mouse.up()
    assert not targets(page), '拖动不能触发提示'
    page.evaluate("const r=document.createRange();r.selectNodeContents(document.querySelector('#cursor'));getSelection().removeAllRanges();getSelection().addRange(r)")
    page.dispatch_event('#blank', 'click', {'button': 0, 'detail': 1})
    assert not targets(page), '选择文本时不能触发提示'


def test_dynamic_controls_clip_and_lifecycle(page):
    page.evaluate("const b=document.createElement('button');b.id='new';b.textContent='新按钮';b.onclick=()=>clicks++;document.querySelector('main').append(b)")
    page.locator('#blank').click()
    assert 'new' in targets(page)
    clipped = page.locator('.ph-box[data-hotspot-for="clipped"]').bounding_box()
    clip = page.locator('#clip').bounding_box()
    assert clipped['y'] + clipped['height'] <= clip['y'] + clip['height'] + 3
    page.locator('#new').evaluate("e=>e.disabled=true")
    page.wait_for_function("!document.querySelector('.ph-box[data-hotspot-for=new]')")
    page.evaluate("document.documentElement.dataset.protoState='details'")
    page.wait_for_function("!document.querySelector('.ph-box')")
    page.evaluate('ProtoHotspots.init({enabled:false})')
    page.locator('#blank').click()
    assert not targets(page)
    page.evaluate('ProtoHotspots.init();ProtoHotspots.init()')
    assert page.locator('.ph-layer').count() == 1
    page.locator('#blank').click()
    assert targets(page)
    page.evaluate('ProtoHotspots.destroy()')
    page.locator('#blank').click()
    assert page.locator('.ph-layer').count() == 0


def test_reduced_motion_and_theme(page):
    page.emulate_media(reduced_motion='reduce')
    page.locator('#blank').click()
    assert page.locator('.ph-box').first.evaluate('e=>getComputedStyle(e).animationName') == 'none'
    for target in ['save', 'darkbutton']:
        assert page.locator(f'.ph-box[data-hotspot-for={target}]').evaluate('e=>getComputedStyle(e).backgroundColor') == 'rgb(255, 159, 41)'
        assert page.locator(f'.ph-box[data-hotspot-for={target}]').evaluate('e=>getComputedStyle(e).opacity') == '0.3'
    page.wait_for_function("!document.querySelector('.ph-box')", timeout=2800)


@pytest.mark.parametrize('background', [(255, 255, 255), (18, 21, 25), (37, 99, 235), (128, 128, 128)])
def test_transparent_orange_fill_without_border(page, background):
    page.locator('#button').evaluate('(el,rgb)=>el.parentElement.style.backgroundColor=`rgb(${rgb.join(",")})`', background)
    page.locator('#blank').click()
    box = page.locator('.ph-box[data-hotspot-for=save]')
    box.evaluate('e=>{const a=e.getAnimations()[0];a.pause();a.currentTime=400}')
    metrics = box.evaluate('''e=>{const s=getComputedStyle(e);return {
        fill:s.backgroundColor,opacity:s.opacity,border:s.borderTopWidth,outline:s.outlineWidth,shadow:s.boxShadow,pointer:s.pointerEvents};}''')
    assert metrics == {'fill':'rgb(255, 159, 41)','opacity':'0.42','border':'0px','outline':'0px','shadow':'none','pointer':'none'}
    box.evaluate('e=>e.getAnimations()[0].currentTime=900')
    assert float(box.evaluate('e=>getComputedStyle(e).opacity')) == pytest.approx(.18)


def test_actual_event_binding_and_removal(page):
    page.evaluate('''window.handler=function(){window.bindingThis=this;window.clicks++};
      const el=document.querySelector('#export');el.addEventListener('click',handler);el.addEventListener('click',handler);
      document.querySelector('#role').__reactProps$fixture={onClick:()=>clicks++};''')
    page.locator('#blank').click()
    assert {'export', 'role'} <= targets(page)
    page.locator('#export').click()
    assert page.evaluate('clicks===1 && bindingThis===document.querySelector("#export")')
    page.evaluate('document.querySelector("#export").removeEventListener("click",handler)')
    page.locator('#blank').click()
    assert 'export' not in targets(page)
    page.evaluate('''window.once=()=>clicks++;document.querySelector('#export').addEventListener('click',once,{once:true});''')
    page.evaluate('ProtoHotspots.hide();ProtoHotspots.show()')
    assert 'export' in targets(page)
    page.locator('#export').click()
    page.locator('#blank').click()
    assert 'export' not in targets(page)
    page.evaluate('''window.abort=new AbortController();document.querySelector('#export').addEventListener('click',handler,{signal:abort.signal});''')
    page.evaluate('ProtoHotspots.hide();ProtoHotspots.show()')
    assert 'export' in targets(page)
    page.evaluate('abort.abort()')
    page.wait_for_function('!document.querySelector(".ph-box[data-hotspot-for=export]")')
    page.locator('#export').click()
    assert page.evaluate('clicks') == 2


def test_export_over_http_and_file(browser, tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'index.html').write_text(HTML, encoding='utf-8')
    bundle = {'revision': 1, 'project': {'id': 'fixture', 'name': '热区验收', 'pages': [
        {'id': 'home', 'title': '首页', 'file': 'index.html', 'states': [{'id': 'default', 'title': '默认'}]}]},
        'prd': {'documents': [], 'annotations': []}}
    review_export.build_review_export(project, bundle, tmp_path / 'review')
    review_export.build_pure_export(project, bundle, tmp_path / 'pure')
    assert (tmp_path / 'pure/index.html').read_text(encoding='utf-8') == HTML

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for url in [(tmp_path / 'review/index.html').as_uri(), f'http://127.0.0.1:{server.server_port}/review/index.html']:
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            frame = page.frame_locator('#frame')
            frame.locator('.ph-layer').wait_for(state='attached')
            frame.locator('#blank').click()
            assert frame.locator('.ph-box[data-hotspot-for=link]').count() == 1
            assert frame.locator('.ph-box').all_text_contents() == [''] * frame.locator('.ph-box').count()
            frame.locator('#button').click()
            child = page.frames[1]
            assert child.evaluate('clicks') == 1 and frame.locator('.ph-box').count() == 0
            page.goto(url.rsplit('/', 1)[0] + '/proto/index.html')
            page.locator('#blank').click()
            assert page.locator('.ph-layer').count() == 0, '独立原型不启用评审提示'
            assert not errors, errors
            context.close()
    finally:
        server.shutdown()
        server.server_close()


def test_javascript_syntax():
    node = shutil.which('node')
    if not node:
        pytest.skip('需要 Node.js')
    for source in [(SRC / 'proto-hotspots.js').read_text(encoding='utf-8'),
                   (SRC / 'review-bridge.js').read_text(encoding='utf-8'),
                   '\n'.join(re.findall(r'<script>([\s\S]*?)</script>', (SRC / 'review_shell.html').read_text(encoding='utf-8')))]:
        result = subprocess.run([node, '--check'], input=source, text=True, encoding='utf-8', capture_output=True)
        assert result.returncode == 0, result.stderr
