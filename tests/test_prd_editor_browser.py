"""真实编辑器与静态导出的隔离验收，不访问用户项目、生成服务或 GitHub。"""
import functools
import io
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image
sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSET = 'prd-assets/' + 'a' * 64 + '.png'
BODY = '**页面要求**\n\n![示例一](' + ASSET + ')\n\n![示例二](' + ASSET + ' "原始说明 proto-width=150")'

HARNESS = '''<!doctype html><html><meta charset="utf-8"><link rel="stylesheet" href="/src/proto-markdown.css">
<script src="/src/vendor/vditor/dist/js/lute/lute.min.js"></script><script src="/src/vendor/vditor/dist/index.min.js"></script>
<script src="/src/vendor/dompurify/dist/purify.min.js"></script><script src="/src/proto-markdown.js"></script>
<style>body{margin:0;background:#e5e7eb}.pa-card{position:absolute;left:16px;top:30px;width:min(420px,calc(100vw - 360px));display:flex;flex-direction:column;background:white;border:1px solid #808790;border-radius:10px;max-height:80vh}
.pa-card-grip{height:14px;flex:none;cursor:grab;touch-action:none}.pa-card-scroll{overflow:auto;min-height:0}.pa-card-body{padding:8px 20px 12px 12px}
.pa-card-resize-e{position:absolute;right:-5px;top:16px;bottom:4px;width:10px;cursor:ew-resize;touch-action:none}
aside{position:absolute;right:0;top:0;width:320px;height:100vh;background:white;overflow:auto;padding:16px;box-sizing:border-box}.section{position:relative;padding-bottom:40px}.section h2{margin:0 0 12px;font:600 16px/1.8 sans-serif}
.fixture-sidebar-grip{position:absolute;left:0;top:0;width:8px;height:100%;cursor:ew-resize;touch-action:none}
#selected-pin{display:none;position:fixed;width:36px;height:36px;background:#2563eb;border-radius:50%;z-index:5}
@media(max-width:650px){.pa-card{width:calc(100vw - 32px);top:16px}aside{width:100%;top:90vh}}</style>
<div class="pa-card"><div class="pa-card-grip"></div><div class="pa-card-scroll"><div class="pa-card-body"><div id="card"></div></div></div><div class="pa-card-resize-e"></div></div>
<aside id="prdSidebar"><div class="fixture-sidebar-grip"></div><div class="section"><h2>标注明细</h2><div id="note"></div></div><div class="section"><h2>页面需求</h2><div id="doc"></div></div></aside>
<div id="selected-pin" data-proto-toolbar-avoid></div>
<script>window.saved=[];window.data={};window.options={};
window.init=async(body,theme)=>{for(const id of ['card','note','doc']){data[id]=body;options[id]={value:body,key:ProtoMarkdown.key('fixture','home','default',id),label:id,theme,assetBase:'/ext/p-fixture/',autosave:true,
save:async(value)=>{saved.push({id,value});data[id]=value;options[id].value=value;return true;},onSaved:()=>ProtoMarkdown.render(document.getElementById(id),options[id])};await ProtoMarkdown.render(document.getElementById(id),options[id]);}};
window.edit=id=>ProtoMarkdown.begin(document.getElementById(id),options[id]);
// 与真实宿主相同：移动卡片通知 relayout，拖宽只变尺寸，依赖编辑器的 ResizeObserver。
function fixtureDrag(selector,target,update){document.querySelector(selector).onpointerdown=e=>{
if(e.button!==0)return;e.preventDefault();const handle=e.currentTarget,box=document.querySelector(target),r=box.getBoundingClientRect();
handle.setPointerCapture(e.pointerId);handle.onpointermove=ev=>{if(ev.pointerId===e.pointerId)update(box,r,ev.clientX-e.clientX,ev.clientY-e.clientY);};
handle.onpointerup=handle.onpointercancel=()=>{handle.onpointermove=null;};};}
fixtureDrag('.pa-card-grip','.pa-card',(box,r,dx,dy)=>{box.style.left=r.left+dx+'px';box.style.top=r.top+dy+'px';ProtoMarkdown.relayout();});
fixtureDrag('.pa-card-resize-e','.pa-card',(box,r,dx)=>{box.style.width=Math.max(280,r.width+dx)+'px';});
fixtureDrag('.fixture-sidebar-grip','aside',(box,r,dx)=>{box.style.width=Math.max(280,r.width-dx)+'px';});
</script></html>'''


@pytest.fixture(scope='module')
def local_static_server():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


@pytest.fixture
def browser_page(local_static_server, request):
    image = io.BytesIO()
    Image.new('RGB', (640, 320), '#dbeafe').save(image, format='PNG')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        touch = getattr(request.node, 'callspec', None) and request.node.callspec.params.get('width') == 375
        context = browser.new_context(viewport={'width': 1440, 'height': 900}, has_touch=bool(touch))
        context.route('**/harness', lambda r: r.fulfill(content_type='text/html', body=HARNESS))
        context.route('**/prd-assets/*.png', lambda r: r.fulfill(content_type='image/png', body=image.getvalue()))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(local_static_server + '/harness')
        yield page, errors
        assert not errors, errors
        context.close()
        browser.close()


def edit(page, region):
    page.evaluate('id=>edit(id)', region)
    page.wait_for_function('() => ProtoMarkdown.current()?.ready')
    return page.frame_locator('.proto-md-frame')


def overlap(a, b):
    return max(0, min(a['x'] + a['width'], b['x'] + b['width']) - max(a['x'], b['x'])) * max(0, min(a['y'] + a['height'], b['y'] + b['height']) - max(a['y'], b['y']))


def settle_layout(page):
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')


def drag(page, locator, dx, dy):
    box = locator.bounding_box()
    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=8)
    page.mouse.up()
    settle_layout(page)


def assert_floating_outside(page, host):
    toolbar = page.locator('.proto-md-toolbar')
    assert toolbar.evaluate("e => e.parentElement === document.documentElement && getComputedStyle(e).position === 'fixed'")
    box = toolbar.bounding_box()
    assert overlap(box, host.bounding_box()) == 0
    assert box['x'] >= 0 and box['y'] >= 0
    assert box['x'] + box['width'] <= page.viewport_size['width'] + 1
    assert box['y'] + box['height'] <= page.viewport_size['height'] + 1
    return box


@pytest.mark.parametrize('theme,width', [('light',1440), ('dark',900), ('light',375)])
def test_toolbar_and_image_resize_save_undo(browser_page, theme, width):
    page, _ = browser_page
    page.set_viewport_size({'width':width,'height':900})
    page.evaluate('args=>init(...args)', [BODY,theme])
    for region in ['card','note','doc']:
        frame = edit(page, region)
        toolbar = page.locator('.proto-md-toolbar')
        toolbar.scroll_into_view_if_needed()
        box = toolbar.bounding_box()
        input_box = page.locator('.proto-md-frame').bounding_box()
        assert overlap(box,input_box) == 0
        assert 0 <= box['x'] and box['x'] + box['width'] <= width + 1
        assert toolbar.locator('button').count() == 15
        first = frame.locator('.vditor-ir img').first
        first.wait_for()
        first.evaluate('img=>img.decode()')
        original = first.bounding_box()
        first.click()
        grip = frame.get_by_role('button',name='调整图片大小，左右方向键调节')
        if width == 375:
            assert grip.bounding_box()['width'] >= 44
        grip.scroll_into_view_if_needed()
        handle = grip.bounding_box()
        page.mouse.move(handle['x']+handle['width']/2,handle['y']+handle['height']/2)
        page.mouse.down()
        page.mouse.move(handle['x']+handle['width']/2-70,handle['y']+handle['height']/2-35,steps=8)
        live = first.bounding_box()
        assert live['width'] < original['width'] - 40
        assert abs(live['height']/live['width'] - .5) < .02
        assert 'proto-width=' not in frame.locator('.vditor-ir__node[data-type="img"]').first.inner_text()
        page.mouse.up()
        page.wait_for_function("() => /proto-width=/.test(ProtoMarkdown.current().frame.contentWindow.ProtoEditor.value().split('示例二')[0])")
        resized = frame.locator('.vditor-ir img').first.bounding_box()['width']
        assert abs(resized-live['width']) <= 1
        assert frame.locator('.vditor-ir img').nth(1).evaluate("img=>img.style.width") == '150px'
        page.locator('.proto-md-toolbar button[data-command="undo"]').click()
        page.wait_for_function("() => !/proto-width=/.test(ProtoMarkdown.current().frame.contentWindow.ProtoEditor.value().split('示例二')[0])")
        page.locator('.proto-md-toolbar button[data-command="redo"]').click()
        page.wait_for_function("() => /proto-width=/.test(ProtoMarkdown.current().frame.contentWindow.ProtoEditor.value().split('示例二')[0])")
        # 第二次拖动取消：源码与尺寸均恢复。
        image = frame.locator('.vditor-ir img').first
        image.click()
        before = page.evaluate('ProtoMarkdown.current().frame.contentWindow.ProtoEditor.value()')
        grip.scroll_into_view_if_needed()
        handle = grip.bounding_box()
        page.mouse.move(handle['x']+handle['width']/2,handle['y']+handle['height']/2)
        page.mouse.down()
        assert frame.locator('html').evaluate("e=>e.classList.contains('is-image-resizing')")
        page.mouse.move(handle['x']-20,handle['y']-10,steps=3)
        page.keyboard.press('Escape'); page.mouse.up()
        assert page.evaluate('ProtoMarkdown.current().frame.contentWindow.ProtoEditor.value()') == before
        page.evaluate('ProtoMarkdown.save(true)')
        page.wait_for_function('() => !ProtoMarkdown.current()')
        reader = page.locator('#'+region+' .proto-md-body img').first
        assert abs(reader.bounding_box()['width'] - resized) <= 1
        assert 'proto-width=' in page.evaluate('id=>data[id]', region)
        # 从保存后的 Markdown 重新建立编辑器；不依赖旧 DOM。
        frame = edit(page, region)
        assert abs(frame.locator('.vditor-ir img').first.bounding_box()['width'] - resized) <= 1
        page.evaluate('ProtoMarkdown.save(true)')
        page.wait_for_function('() => !ProtoMarkdown.current()')
    # 工具条手动拖动不销毁编辑器，双击握把归位。
    edit(page,'card')
    toolbar=page.locator('.proto-md-toolbar')
    toolbar.scroll_into_view_if_needed()
    grip=toolbar.locator('.proto-md-grip')
    r=grip.bounding_box(); page.mouse.move(r['x']+4,r['y']+4);page.mouse.down()
    page.mouse.move(r['x']+64,r['y']+44,steps=6);page.mouse.up()
    assert page.evaluate('ProtoMarkdown.current().toolbarManual')
    assert toolbar.evaluate("e=>getComputedStyle(e).position==='fixed'")
    grip.dblclick()
    assert not page.evaluate('ProtoMarkdown.current().toolbarManual')
    assert overlap(toolbar.bounding_box(),page.locator('.proto-md-frame').bounding_box()) == 0


def test_toolbar_has_no_layout_slot_before_after_drag_and_reset(browser_page):
    page, _ = browser_page
    page.evaluate('args=>init(...args)', ['编辑正文保持原位。', 'light'])
    card = page.locator('.pa-card')
    for region in ['card', 'note', 'doc']:
        body = page.locator('#' + region)
        before_body, before_card = body.bounding_box(), card.bounding_box()
        body.dblclick()
        page.wait_for_function('() => ProtoMarkdown.current()?.ready')
        settle_layout(page)
        host = card if region == 'card' else page.locator('aside')
        assert_floating_outside(page, host)

        def assert_no_space_added():
            # 允许 iframe 对自然行高向上取整的亚像素差，不允许出现一行工具条高度。
            after_body, after_card = body.bounding_box(), card.bounding_box()
            assert abs(after_body['y'] - before_body['y']) <= 1
            assert abs(after_body['height'] - before_body['height']) <= 2
            assert abs(after_card['height'] - before_card['height']) <= 2

        assert_no_space_added()
        grip = page.locator('.proto-md-grip')
        drag(page, grip, 60, 45)
        assert page.evaluate('ProtoMarkdown.current().toolbarManual')
        assert_no_space_added()
        grip.focus()
        page.keyboard.press('Enter')
        settle_layout(page)
        assert not page.evaluate('ProtoMarkdown.current().toolbarManual')
        assert_floating_outside(page, host)
        assert_no_space_added()
        page.evaluate('ProtoMarkdown.save(true)')
        page.wait_for_function('() => !ProtoMarkdown.current()')
        assert not page.locator('.proto-md-toolbar').count()


def test_toolbar_follows_card_move_and_host_resizes(browser_page):
    page, _ = browser_page
    page.evaluate('args=>init(...args)', ['调整卡片宽度后，工具条需要保持在编辑框外侧。' * 5, 'dark'])
    card = page.locator('.pa-card')
    card.evaluate("e=>Object.assign(e.style,{left:'260px',top:'260px',width:'420px'})")
    edit(page, 'card')
    settle_layout(page)
    before = assert_floating_outside(page, card)
    drag(page, page.locator('.pa-card-grip'), 90, 60)
    moved = assert_floating_outside(page, card)
    assert abs(moved['x'] - before['x'] - 90) <= 2
    assert abs(moved['y'] - before['y'] - 60) <= 2

    # 顶部无空间时工具条放下方；缩窄卡片使正文折行增高，必须同步跟随。
    drag(page, page.locator('.pa-card-grip'), 0, 12 - card.bounding_box()['y'])
    before_resize = assert_floating_outside(page, card)
    before_card = card.bounding_box()
    assert before_resize['y'] >= before_card['y'] + before_card['height']
    drag(page, page.locator('.pa-card-resize-e'), -130, 0)
    assert card.bounding_box()['width'] < before_card['width'] - 100
    page.wait_for_function('old => document.querySelector(".pa-card").getBoundingClientRect().height > old + 20', arg=before_card['height'])
    settle_layout(page)
    resized = assert_floating_outside(page, card)
    assert resized['y'] > before_resize['y'] + 20
    assert not page.evaluate('ProtoMarkdown.current().toolbarManual')

    # 手动移动后的工具条保持位置，卡片继续移动也不把它拉回。
    grip = page.locator('.proto-md-grip')
    drag(page, grip, -80, -80)
    manual = page.locator('.proto-md-toolbar').bounding_box()
    drag(page, page.locator('.pa-card-grip'), 40, 30)
    held = page.locator('.proto-md-toolbar').bounding_box()
    assert abs(held['x'] - manual['x']) <= 1 and abs(held['y'] - manual['y']) <= 1
    grip.dblclick()
    assert_floating_outside(page, card)
    assert not page.evaluate('ProtoMarkdown.current().toolbarManual')

    edit(page, 'note')
    settle_layout(page)
    sidebar = page.locator('aside')
    before = assert_floating_outside(page, sidebar)
    assert before['x'] + before['width'] <= sidebar.bounding_box()['x']
    drag(page, page.locator('.fixture-sidebar-grip'), -160, 0)
    after = assert_floating_outside(page, sidebar)
    assert sidebar.bounding_box()['width'] == 480
    assert abs(after['x'] - before['x'] + 160) <= 2


@pytest.mark.parametrize('width', [1440, 375])
def test_toolbar_avoids_card_viewport_edges_and_selected_pin(browser_page, width):
    page, _ = browser_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.evaluate('args=>init(...args)', ['边缘编辑仍能看到全部格式工具。', 'light'])
    card = page.locator('.pa-card')
    edit(page, 'card')
    for left, top in [(12, 12), (max(12, width - 440), 790)]:
        card.evaluate('(e,p)=>{e.style.left=p[0]+"px";e.style.top=p[1]+"px";ProtoMarkdown.relayout();}', [left, top])
        settle_layout(page)
        bar = assert_floating_outside(page, card)
        assert page.locator('.proto-md-toolbar button').count() == 15
        if width == 375:
            assert bar['height'] > 60  # 触屏按钮折行，完整工具条仍须在卡片外侧。

    # 在原来的首选摆位放入选中序号，下一次重排必须换到不压住序号的位置。
    card.evaluate("e=>{e.style.left='12px';e.style.top='260px';ProtoMarkdown.relayout();}")
    settle_layout(page)
    preferred = assert_floating_outside(page, card)
    pin = page.locator('#selected-pin')
    pin.evaluate('(e,r)=>Object.assign(e.style,{display:"block",left:r.x+"px",top:r.y+"px"})', preferred)
    page.evaluate('ProtoMarkdown.relayout()')
    settle_layout(page)
    relocated = assert_floating_outside(page, card)
    assert overlap(relocated, pin.bounding_box()) == 0


def test_reader_image_width_security(browser_page):
    page,_=browser_page
    markdown='\n\n'.join(['![正常]('+ASSET+' "说明 proto-width=192")',
        '![越界]('+ASSET+' "proto-width=9999")', '![普通]('+ASSET+')',
        '![外部](https://fixture.invalid/image.png "proto-width=200")', '<img src="'+ASSET+'" onerror="window.compromised=true">'])
    page.evaluate('args=>init(...args)',[markdown,'light'])
    images=page.locator('#doc .proto-md-body img')
    assert images.count()==4  # 原始 HTML 仍须经过净化与同一项目资源校验。
    assert images.nth(0).get_attribute('width')=='192'
    assert images.nth(0).get_attribute('title')=='说明'
    assert images.nth(1).get_attribute('width') is None
    assert images.nth(2).get_attribute('width') is None
    assert images.nth(3).get_attribute('onerror') is None
    assert page.evaluate('window.compromised') is None


def test_exported_image_sizes_http_and_file(browser_page, local_static_server, tmp_path):
    sys.path.insert(0,str(ROOT))
    import review_export
    page,_=browser_page
    project=tmp_path/'project';project.mkdir()
    (project/'index.html').write_text('<html lang="zh-CN" data-proto-page="home" data-proto-state="default"><meta charset="utf-8"><body style="padding:70px"><button data-proto-id="save-button">保存</button></body></html>',encoding='utf-8')
    image=io.BytesIO();Image.new('RGB',(640,320),'#dbeafe').save(image,format='PNG')
    (project/'prd-assets').mkdir();(project/ASSET).write_bytes(image.getvalue())
    bundle={'revision':1,'project':{'id':'p-fixture','name':'图片尺寸验收','previewType':'web','pages':[{'id':'home','title':'首页','file':'index.html','states':[{'id':'default','title':'默认','kind':'default'}]}]},
        'prd':{'documents':[{'id':'doc','pageId':'home','stateId':'default','markdown':'![页需求]('+ASSET+' "proto-width=192")'}],
        'annotations':[{'id':'note-1','pageId':'home','stateId':'default','number':1,'body':'![标注]('+ASSET+' "图片说明 proto-width=144")',
        'anchor':{'protoId':'save-button','selector':'[data-proto-id="save-button"]','tag':'button','text':'保存'},'placement':{'kind':'element','rx':.5,'ry':.5}}]},'changes':{'items':[]}}
    out=tmp_path/'export';out.mkdir()
    review_export.build_review_export(project,bundle,out)
    assert (out/'proto'/ASSET).read_bytes()==image.getvalue()
    page.context.unroute('**/prd-assets/*.png')
    def exported(route):
        from urllib.parse import urlsplit,unquote
        relative=unquote(urlsplit(route.request.url).path.split('/export-fixture/',1)[1])
        target=out/relative
        route.fulfill(path=str(target))
    page.context.route('**/export-fixture/**',exported)
    for url in [local_static_server+'/export-fixture/index.html',(out/'index.html').as_uri()]:
        page.goto(url)
        image=page.locator('#document img');image.wait_for();image.evaluate('img=>img.decode()')
        assert image.bounding_box()['width']==192
        note=page.locator('#notes img');note.wait_for();note.evaluate('img=>img.decode()')
        assert note.bounding_box()['width']==144
        assert note.get_attribute('title')=='图片说明'
        page.locator('#toggle-prd').click()
        pin=page.frame_locator('#frame').locator('.__review_pin')
        pin.wait_for();pin.click()
        popup=page.frame_locator('#frame').locator('.__review_pop img');popup.wait_for();popup.evaluate('img=>img.decode()')
        assert popup.bounding_box()['width']==144
        assert not page.locator('.proto-md-image-grip').count()  # 导出是只读展示。
