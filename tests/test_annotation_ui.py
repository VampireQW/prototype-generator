"""标注交互回归：语法、对比度、键盘边界、视口定位及串行保存。"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'
VIEWER = (SRC / 'viewer.html').read_text(encoding='utf-8')
ANNOTATE = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
ORDER = (SRC / 'proto-order.js').read_text(encoding='utf-8')
MARKDOWN = (SRC / 'proto-markdown.js').read_text(encoding='utf-8')
MARKDOWN_EDITOR = (SRC / 'markdown-editor.js').read_text(encoding='utf-8')
MARKDOWN_CSS = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
DEMO = SRC.parents[1] / '独立项目' / '原型Markdown编辑演示'


def node(code, check=False):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行前端回归')
    result = subprocess.run([executable, '--check' if check else '-'], input=code,
                            text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize('source', [
    ANNOTATE, (SRC / 'proto-anchors.js').read_text(encoding='utf-8'), ORDER, (SRC / 'script.js').read_text(encoding='utf-8'),
    '\n'.join(re.findall(r'<script>([\s\S]*?)</script>', VIEWER)),
    MARKDOWN, MARKDOWN_EDITOR, (DEMO / 'assets/demo.js').read_text(encoding='utf-8'),
    (SRC / 'localize-markdown.cjs').read_text(encoding='utf-8')
], ids=['annotate', 'anchors', 'order', 'home', 'viewer', 'markdown-adapter', 'markdown-editor', 'markdown-demo', 'localize-script'])
def test_javascript_syntax(source):
    node(source, check=True)


def test_workbench_deep_links_select_registered_page_state_and_keep_url_current():
    loader=VIEWER[VIEWER.index('async function loadProto()'):VIEWER.index('function extPageRecord()')]+VIEWER[VIEWER.index('function renderProjectName()'):VIEWER.index('function openProjectRename()')]
    sync=VIEWER[VIEWER.index('function syncExtLocation()'):VIEWER.index('function renderExtPageList()')]
    node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const bundle={project:{name:'示例项目',pages:[{id:'home',states:[{id:'default'}]},{id:'detail',states:[{id:'default'},{id:'done'}]},{id:'old',trashedAt:'now',states:[{id:'default'}]}]}};
const opened=[],warnings=[],element={};
const context={URL,URLSearchParams,extId:'p-example',extBundle:null,extPage:'',extStateId:'done',extInitialLocation:null,currentMode:'annotate',location:new URL('http://localhost:8080/src/viewer.html?ext=p-example&page=detail&state=done&mode=annotate'),
document:{},console,fetch:async()=>({json:async()=>({ok:true,bundle})}),$:()=>element,
ProtoProjectNavigation:{defaultPage:project=>project.pages[0]},showAppAlert:e=>{throw new Error(JSON.stringify(e));},showToast:message=>warnings.push(message),showExtEmptyPages(){},applyPreviewType(){},openExtPage:id=>opened.push(id)};
context.history={replaceState:(_,__,url)=>context.location=new URL(url)};
vm.createContext(context);vm.runInContext(LOADER+SYNC,context);
(async()=>{
await context.loadProto();assert.equal(context.extPage,'detail');assert.equal(opened.at(-1),'detail');assert.equal(context.extInitialLocation.stateId,'done');
context.extInitialLocation=null;context.extPage='home';context.extStateId='default';context.syncExtLocation();
assert.equal(context.location.searchParams.get('page'),'home');assert.equal(context.location.searchParams.get('state'),'default');assert.equal(context.location.searchParams.get('mode'),'annotate');
context.location=new URL('http://localhost:8080/src/viewer.html?ext=p-example&page=old');await context.loadProto();assert.equal(context.extPage,'home');assert.equal(warnings.length,1);
context.extInitialLocation=null;context.location=new URL('http://localhost:8080/src/viewer.html?ext=p-example&page=detail&state=missing');await context.loadProto();assert.equal(context.extInitialLocation.stateId,'default');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('LOADER',repr(loader)).replace('SYNC',repr(sync)))


def test_pad_scaled_coordinates_match_inspector_and_annotation_card():
    geometry=VIEWER[VIEWER.index('function previewFrameGeometry()'):VIEWER.index('function onOverlayMouseMove(e)')]
    click=VIEWER[VIEWER.index('function handleInspectorClick(e)'):VIEWER.index('function selectElementsInBox(boxRect)')]
    to_card=ANNOTATE[ANNOTATE.index('function toCard(x, y)'):ANNOTATE.index('const editable =')]
    node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const picked={tagName:'BUTTON',classList:{add(){}}},points=[];
const frame={offsetWidth:1200,offsetHeight:840,clientLeft:10,clientTop:10,getBoundingClientRect:()=>({left:200,top:50,width:600,height:420}),contentDocument:{elementFromPoint:(x,y)=>{points.push({x,y});return picked;}}};
const document={},parentDocument={};
const context={console,previewFrame:frame,selectedElements:[],clearAllSelections(){},showInspectorModal(){},document,window:{frameElement:frame},cardDoc:()=>parentDocument};
vm.createContext(context);vm.runInContext(GEOMETRY+CLICK+TO_CARD,context);
context.handleInspectorClick({clientX:355,clientY:155});
assert.deepEqual(points,[{x:300,y:200}]);
assert.equal(context.selectedElements[0],picked);
assert.deepEqual(JSON.parse(JSON.stringify(context.toCard(300,200))),{x:355,y:155});
context.cardDoc=()=>document;assert.deepEqual(JSON.parse(JSON.stringify(context.toCard(300,200))),{x:300,y:200});
'''.replace('GEOMETRY',repr(geometry)).replace('CLICK',repr(click)).replace('TO_CARD',repr(to_card)))


def test_prd_toggle_preserves_width_and_moves_focus_out_of_collapsed_panel():
    source = VIEWER[VIEWER.index('function syncPrdControls()'):VIEWER.index("const prdResizer = $('prdResizer');")]
    node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
function element(initial=[]){const classes=new Set(initial);return {style:{},attributes:{},classList:{add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v),toggle(v,on){if(on===undefined)on=!classes.has(v);if(on)classes.add(v);else classes.delete(v);}},setAttribute(k,v){this.attributes[k]=v;},focus(){this.focused=true;},contains(){return true;}};}
const sidebar=element(['expanded']),floating=element(),toggle=element(),content=element(['flex']);
let refreshes=0;
const context={prdSidebar:sidebar,prdFloatingToggle:floating,prdToggle:toggle,prdContentEl:content,prdExpanded:true,
localStorage:{getItem:()=> '512'},document:{activeElement:{}},extId:'fixture',extRefreshSidebar:()=>refreshes++,previewFrame:null};
vm.createContext(context);vm.runInContext(SOURCE,context);
context.togglePrdSidebar();
assert.equal(context.prdExpanded,false);assert.equal(sidebar.classList.contains('collapsed'),true);
assert.equal(sidebar.style.width,'');assert.equal(content.classList.contains('hidden'),true);
assert.equal(floating.focused,true);assert.equal(floating.attributes['aria-expanded'],'false');
assert.equal(floating.attributes['aria-label'],'展开 PRD 面板');assert.equal(floating.classList.contains('hidden'),false);
context.togglePrdSidebar();
assert.equal(sidebar.style.width,'512px');assert.equal(refreshes,1);assert.equal(sidebar.attributes['aria-hidden'],'false');
assert.equal(floating.attributes['aria-expanded'],'true');assert.equal(toggle.attributes['aria-expanded'],'true');
sidebar.classList.add('hidden-mode');context.syncPrdControls();
assert.equal(floating.classList.contains('hidden'),true);assert.equal(sidebar.attributes['aria-hidden'],'true');
sidebar.classList.remove('hidden-mode');context.syncPrdControls();
assert.equal(floating.classList.contains('hidden'),false);assert.equal(sidebar.style.width,'512px');
'''.replace('SOURCE', repr(source)))


def contrast(a, b):
    def luminance(color):
        c = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted([luminance(a), luminance(b)], reverse=True)
    return (light + .05) / (dark + .05)


def _tokens(source, marker):
    """取 marker 所在规则块内的 --token: #hex 字典（块 = marker 之后的第一对花括号）。"""
    rest = source.split(marker, 1)[1]
    block = (rest if marker.endswith('{') else rest.split('{', 1)[1]).split('}', 1)[0]
    return dict(re.findall(r'--([\w-]+):\s*(#[\da-fA-F]{6})', block))


def theme_tokens(theme):
    """标注层（.pa-*，暗色为基础、浅色覆盖）与右栏（--ext-*，浅色为基础、暗色覆盖）两套 token 合并后的实际取值。"""
    pa = _tokens(ANNOTATE, '\n.pa-layer{')
    ext_block = re.search(r':root\s*\{(?=[^{}]*--ext-accent:)([^{}]*)\}', VIEWER).group(1)
    ext = dict(re.findall(r'--([\w-]+):\s*(#[\da-fA-F]{6})', ext_block))
    if theme == 'light':
        pa.update(_tokens(ANNOTATE, '.pa-layer[data-theme="light"]'))
    else:
        ext.update(_tokens(VIEWER, ':root[data-ext-theme="dark"] #prdSidebar'))
    return {**pa, **ext}


@pytest.mark.parametrize('theme', ['dark', 'light'])
@pytest.mark.parametrize('foreground,background,minimum', [
    ('pa-on-accent', 'pa-accent', 4.5), ('pa-text', 'pa-surface', 4.5),
    ('pa-muted', 'pa-surface', 4.5), ('pa-border', 'pa-surface', 3),
    ('pa-ring', 'pa-surface', 3), ('pa-error', 'pa-surface', 4.5), ('pa-scroll', 'pa-surface', 3),
    ('ext-text', 'ext-surface', 4.5), ('ext-muted', 'ext-surface', 4.5), ('ext-control', 'ext-surface', 3),
    ('ext-accent-text', 'ext-soft', 4.5), ('ext-accent-text', 'ext-surface', 4.5),
    ('ext-on-accent', 'ext-accent', 4.5), ('ext-danger', 'ext-surface', 4.5),
])
def test_annotation_token_contrast(theme, foreground, background, minimum):
    colors = theme_tokens(theme)
    ratio = contrast(colors[foreground], colors[background])
    assert ratio >= minimum, f'{theme} {foreground}/{background}: {ratio:.2f}'


def test_workbench_appearance_setting():
    """外观设置（跟随系统 / 浅色 / 暗色）：一个偏好管右栏、iframe 内标注卡、Markdown 阅读与编辑三处；新建标注不再闪白。"""
    # 设置入口与三选一，偏好落 localStorage，跟随系统听 prefers-color-scheme 变化
    assert 'id="extThemeBtn"' in VIEWER and 'fa-circle-half-stroke' in VIEWER
    assert VIEWER.count('<input type="radio" name="extTheme"') == 3 and all(f'name="extTheme" value="{v}"' in VIEWER for v in ('system', 'light', 'dark'))
    assert "const EXT_THEME_KEY = 'prototype-theme';" in VIEWER
    assert "matchMedia('(prefers-color-scheme: dark)')" in VIEWER
    assert "extSystemDark.addEventListener('change'" in VIEWER
    # 三处下发：右栏 data-ext-theme、标注层 setTheme、Markdown 会话 theme()；原来写死的 'dark' / 'light' 全部改走 extTheme()
    assert 'document.documentElement.dataset.extTheme = theme;' in VIEWER
    assert 'w.ProtoAnnotate.setTheme?.(extTheme());' in VIEWER
    assert 'ProtoMarkdown.theme?.(theme);' in VIEWER
    assert 'function extNoteOptions(note, theme = extTheme())' in VIEWER
    assert 'async function extEditNote(noteId, region, theme = extTheme())' in VIEWER
    assert "extNoteOptions(note, 'dark')" not in VIEWER and "theme: 'dark'" not in VIEWER
    assert 'readonly: false, theme: extTheme(),' in VIEWER
    # 暗色 token 只作用于右栏与其弹出菜单；蓝底白字与面上蓝字拆开，不再写裸 #fff
    assert ':root[data-ext-theme="dark"] #prdSidebar, :root[data-ext-theme="dark"] .ext-note-menu {' in VIEWER
    ext_start = re.search(r':root\s*\{(?=[^{}]*--ext-accent:)', VIEWER).start()
    ext_css = VIEWER[ext_start:].split('.ext-publish-links {', 1)[0]
    assert 'color: #fff' not in ext_css
    # 标注层：浅色变量组 + setTheme 导出（阅读卡开着时重渲染）
    assert '.pa-layer[data-theme="light"]{' in ANNOTATE and 'function setTheme(theme)' in ANNOTATE
    assert re.search(r'window\.ProtoAnnotate = \{[^}]*\bsetTheme\b', ANNOTATE)
    # 闪白根因：begin() 不经 render 时 region 没有 data-theme，按浅色铺白底；现在 begin 也设一次
    begin = MARKDOWN.split('function begin(', 1)[1].split('\n    function ', 1)[0]
    assert "region.dataset.theme = options.theme || 'light';" in begin
    # 编辑中的会话就地换皮：适配层 theme() → 编辑器 ProtoEditor.theme() → Vditor setTheme(theme, contentTheme, codeTheme, contentThemePath)
    assert re.search(r'\n\s*theme\(theme\) \{', MARKDOWN) and 'ProtoEditor?.theme?.(theme)' in MARKDOWN
    assert 'function theme(value)' in MARKDOWN_EDITOR
    assert "editor.setTheme(value === 'dark' ? 'dark' : 'classic', value === 'dark' ? 'dark' : 'light', undefined, `${CDN}/dist/css/content-theme`)" in MARKDOWN_EDITOR
    vditor = (SRC / 'vendor/vditor/dist/index.min.js').read_text(encoding='utf-8')
    assert 'setTheme=function(e,t,n,r){this.vditor.options.theme=e' in vditor


@pytest.mark.parametrize('foreground,background,minimum', [
    ('text', 'surface', 4.5), ('muted', 'surface', 4.5), ('accent', 'surface', 4.5),
    ('error', 'surface', 4.5), ('control', 'surface', 3), ('dark-text', 'dark', 4.5),
    ('dark-muted', 'dark', 4.5), ('dark-accent', 'dark', 4.5), ('dark-error', 'dark', 4.5),
])
def test_markdown_demo_token_contrast(foreground, background, minimum):
    css = (DEMO / 'assets/demo.css').read_text(encoding='utf-8')
    colors = dict(re.findall(r'--([\w-]+):\s*(#[\da-fA-F]{6})', css))
    assert contrast(colors[foreground], colors[background]) >= minimum


def test_markdown_demo_local_dependencies_and_csp():
    import json
    html = (DEMO / 'index.html').read_text(encoding='utf-8')
    for resource in re.findall(r'(?:src|href)="(assets/[^\"]+)"', html):
        assert (DEMO / resource).is_file(), resource
    vendor = DEMO / 'assets/vendor'
    lock = json.loads((vendor / 'package-lock.json').read_text(encoding='utf-8'))
    for package, version in [('vditor', '3.11.2'), ('dompurify', '3.3.1')]:
        assert lock['packages']['node_modules/' + package]['version'] == version
        assert (vendor / package / 'LICENSE').stat().st_size > 100
    for resource in ['dist/js/lute/lute.min.js', 'dist/js/i18n/zh_CN.js', 'dist/js/icons/ant.js', 'dist/css/content-theme/light.css', 'dist/css/content-theme/dark.css']:
        assert (vendor / 'vditor' / resource).is_file()
    assert "connect-src 'none'" in html and "img-src 'none'" in html
    assert 'https://' not in html and 'http://' not in html


def test_workbench_markdown_local_dependencies_and_csp():
    import json
    html = (SRC / 'markdown-editor.html').read_text(encoding='utf-8')
    assert "connect-src 'none'" in html and "img-src 'self'" in html
    assert 'https://' not in html and 'http://' not in html
    for resource in re.findall(r'(?:src|href)="(/src/[^\"]+)"', html):
        assert (SRC.parent / resource.split('?', 1)[0].lstrip('/')).is_file(), resource
    vendor = SRC / 'vendor'
    lock = json.loads((vendor / 'package-lock.json').read_text(encoding='utf-8'))
    for package, version in [('vditor', '3.11.2'), ('dompurify', '3.3.1')]:
        assert lock['packages']['node_modules/' + package]['version'] == version
        assert (vendor / package / 'LICENSE').stat().st_size > 100
    for resource in ['dist/index.min.js', 'dist/index.css', 'dist/js/lute/lute.min.js', 'dist/js/i18n/zh_CN.js', 'dist/js/icons/ant.js', 'dist/css/content-theme/light.css', 'dist/css/content-theme/dark.css']:
        assert (vendor / 'vditor' / resource).is_file()
    assert (vendor / 'dompurify' / 'dist/purify.min.js').is_file()
    assert 'new Vditor' in MARKDOWN_EDITOR and 'clearStack()' in MARKDOWN_EDITOR


@pytest.mark.parametrize('scope,foreground,background,minimum', [
    ('light', 'md-text', 'md-surface', 4.5), ('light', 'md-muted', 'md-surface', 4.5),
    ('light', 'md-accent', 'md-surface', 4.5), ('light', 'md-error', 'md-surface', 4.5),
    ('light', 'md-control', 'md-surface', 3), ('dark', 'md-text', 'md-surface', 4.5),
    ('dark', 'md-muted', 'md-surface', 4.5), ('dark', 'md-accent', 'md-surface', 4.5),
    ('dark', 'md-error', 'md-surface', 4.5),
])
def test_workbench_markdown_token_contrast(scope, foreground, background, minimum):
    light, _, dark = MARKDOWN_CSS.partition('[data-theme="dark"]')
    source = light if scope == 'light' else dark
    colors = dict(re.findall(r'--([\w-]+):\s*(#[\da-fA-F]{6})', source))
    assert contrast(colors[foreground], colors[background]) >= minimum


def test_markdown_drafts_are_durable_and_scoped():
    node("""
const assert=require('node:assert/strict');
const store=new Map();
global.window={addEventListener(){}};
global.location={href:'http://127.0.0.1/src/viewer.html'};
global.localStorage={getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,String(value)),removeItem:key=>store.delete(key)};
""" + MARKDOWN + """
const md=window.ProtoMarkdown;
const first=md.key('p-a','home','default','note 1');
const second=md.key('p-a','home','done','note 1');
assert.notEqual(first,second);
md.putDraft(first,{value:'未提交正文',base:'旧正文',extra:{x:5}});
assert.deepEqual(md.getDraft(first),{value:'未提交正文',base:'旧正文',extra:{x:5}});
assert.equal(md.getDraft(second),null);
assert.equal(store.size,1);
md.putDraft(first,null); assert.equal(md.getDraft(first),null); assert.equal(store.size,0);
md.suspend(); assert.equal(md.current(),null);
""")


def markdown_session_harness(test):
    return node("""
const assert=require('node:assert/strict');
const store=new Map(), timers=[], statuses=[], saves=[];
global.window={addEventListener(){}};
global.location={href:'http://127.0.0.1/src/viewer.html'};
global.localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
global.setTimeout=(fn,ms)=>{const t={fn,ms,cleared:false};timers.push(t);return t;};
global.clearTimeout=t=>{if(t)t.cleared=true;};
function el(tag){return {tag,style:{},dataset:{},children:[],className:'',title:'',textContent:'',
    classList:{add(){},remove(){}},setAttribute(){},removeAttribute(){},closest(){return null;},before(){},
    replaceChildren(...k){this.children=k;k.forEach(c=>c.parentNode=this);},appendChild(k){this.children.push(k);k.parentNode=this;},
    remove(){this.removed=true;if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.parentNode=null;}},addEventListener(){},
    offsetWidth:300,offsetHeight:36,
    getBoundingClientRect(){return {left:0,top:0,right:300,bottom:100,width:300,height:100};}};}
const doc={createElement:el,documentElement:el('html'),querySelectorAll(){return [];},getElementById(){return null;},
    defaultView:{addEventListener(){},removeEventListener(){},innerWidth:1024,innerHeight:768}};
global.requestAnimationFrame=fn=>fn();
""" + MARKDOWN + """
const md=window.ProtoMarkdown;
const pendingSave=b=>new Promise(r=>saves.push({body:b,resolve:r}));
const flush=()=>new Promise(r=>setImmediate(r));
const tick=ms=>timers.filter(t=>!t.cleared&&t.ms===ms).forEach(t=>{t.cleared=true;t.fn();});
function makeRegion(){const r=el('div');r.ownerDocument=doc;return r;}
function start(value,extra={}) {
    const region=makeRegion();
    const options={key:md.key('p','home','default',extra.item||'n1'),value,label:'标注 1',save:pendingSave,...extra};
    assert.equal(md.begin(region,options),true);
    const s=md.current();
    s.frame.contentWindow={ProtoEditor:{text:s.value,value(){return this.text;},status:(...a)=>statuses.push(a),focus(){},destroy(){}}};
    s.frame._markdownBridge.ready();
    return {region,s,api:s.frame.contentWindow.ProtoEditor};
}
""" + test)


def test_markdown_save_lifecycle_protects_drafts():
    markdown_session_harness("""
(async()=>{
// 页面文档：停输入 1200ms 自动保存，编辑器保持打开，草稿清理
const docKey=md.key('p','home','default','$document');
const h=start('旧',{item:'$document',allowEmpty:true,autosave:true});
h.api.text='新正文'; h.s.frame._markdownBridge.change('新正文');
assert.ok(!saves.some(x=>x.body==='新正文'));
tick(1200); await flush();
assert.equal(saves.length,1); assert.equal(saves[0].body,'新正文');
saves[0].resolve(true); await flush(); await flush();
assert.equal(md.current(),h.s);
assert.equal(md.getDraft(docKey),null);
assert.ok(!statuses.some(a=>String(a[0]).includes('未保存')));
md.suspend();

// 显式保存期间继续输入：旧回包不清新草稿，继续保存最新正文后再关闭
const n1=md.key('p','home','default','n1');
const h1=start('旧',{item:'n1'});
h1.api.text='v1'; h1.s.frame._markdownBridge.change('v1');
const first=md.save(true,h1.s); await flush();
assert.equal(saves.length,2); assert.equal(saves[1].body,'v1');
h1.api.text='v2'; h1.s.frame._markdownBridge.change('v2');
assert.equal(md.getDraft(n1).value,'v2');
saves[1].resolve(true);
for(let i=0;i<10&&saves.length<3;i++) await flush();
assert.equal(saves.length,3); assert.equal(saves[2].body,'v2');
saves[2].resolve(true); await first; await flush();
assert.equal(md.getDraft(n1),null);
assert.equal(md.current(),null);

// 500/409 失败：编辑不销毁、草稿保留、状态提示，不自动重载
const n2=md.key('p','home','default','n2');
const h2=start('旧',{item:'n2'});
h2.api.text='正文'; h2.s.frame._markdownBridge.change('正文');
const attempt=md.save(true,h2.s); await flush();
assert.equal(saves.length,4); saves[3].resolve(false);
assert.equal(await attempt,false); await flush();
assert.equal(md.current(),h2.s);
assert.equal(md.getDraft(n2).value,'正文');
assert.ok(statuses.at(-1)[0].includes('未保存'));
md.suspend();

// 挂起后失败回包：不触碰已关闭的编辑器，草稿仍可恢复
const n3=md.key('p','home','default','n3');
const h3=start('旧',{item:'n3'});
h3.api.text='未提交'; h3.s.frame._markdownBridge.change('未提交');
const pending=md.save(true,h3.s); await flush();
assert.equal(saves.length,5);
md.suspend();
assert.equal(md.current(),null);
saves[4].resolve(false);
assert.equal(await pending,false); await flush();
assert.equal(md.getDraft(n3).value,'未提交');

// 冲突草稿：提示并禁止自动保存，显式保存仍可用
const n5=md.key('p','home','default','n5');
md.putDraft(n5,{value:'草稿正文',base:'旧版本',extra:null});
const h5=start('新版本',{item:'n5',autosave:true});
assert.equal(h5.s.conflict,true);
assert.ok(statuses.some(a=>String(a[0]).includes('已变化')));
h5.api.text='x'; h5.s.frame._markdownBridge.change('x');
assert.ok(!timers.some(t=>!t.cleared&&t.ms===1200));
assert.equal(await md.save(false,h5.s),true);
assert.equal(saves.length,5);
const manual=md.save(true,h5.s); await flush();
assert.equal(saves.length,6); assert.equal(saves[5].body,'x');
saves[5].resolve(true); await manual; await flush();
assert.equal(md.getDraft(n5),null);
assert.equal(md.current(),null);

// 已确认只读不可编辑；换一条编辑时旧会话自动交接关闭，仍只保留一个编辑器
assert.equal(md.begin(makeRegion(),{key:'k',value:'v',label:'x',readonly:true,save:pendingSave}),false);
const h6=start('a',{item:'n6'});
const region7=makeRegion();
assert.equal(md.begin(region7,{key:'k2',value:'b',label:'y',save:pendingSave}),true);
assert.notEqual(md.current(),h6.s);
assert.equal(md.current().region,region7);
md.suspend();
assert.equal(md.current(),null);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_markdown_suspend_saves_and_rekeys_created_note():
    markdown_session_harness("""
(async()=>{
// 挂起即保存：自动保存会话退出时先落库再关闭
const n4=md.key('p','home','default','n4');
const h4=start('旧',{item:'n4',autosave:true});
h4.api.text='新'; h4.s.frame._markdownBridge.change('新');
md.suspend(); await flush();
assert.equal(saves.length,1); assert.equal(saves[0].body,'新');
saves[0].resolve(true); await flush(); await flush();
assert.equal(md.current(),null);
assert.equal(md.getDraft(n4),null);

// 浮窗落点：首次保存返回新 key 后会话改挂新落点，后续自动保存打同一落点
const n9=md.key('p','home','default','n9'), newK=md.key('p','home','default','$new');
const created=[];
const h9=start('',{item:'$new',autosave:true,
    save:body=>{created.push(body);return Promise.resolve(created.length===1?{ok:true,key:n9}:true);}});
h9.api.text='第一段'; h9.s.frame._markdownBridge.change('第一段');
tick(1200);
for(let i=0;i<10&&created.length<1;i++) await flush();
assert.equal(created.length,1); assert.equal(created[0],'第一段');
await flush(); await flush();
assert.equal(md.current().key,n9);
assert.equal(md.getDraft(newK),null);
assert.equal(md.getDraft(n9),null);
h9.api.text='第一段 追加'; h9.s.frame._markdownBridge.change('第一段 追加');
tick(1200);
for(let i=0;i<10&&created.length<2;i++) await flush();
assert.equal(created.length,2); assert.equal(created[1],'第一段 追加');
assert.equal(md.current().key,n9);
await flush(); await flush();
md.suspend(); await flush(); await flush();
assert.equal(md.current(),null);
assert.equal(md.getDraft(n9),null);

// 挂起时保存失败：编辑器仍关闭，草稿保留在落点上
const n7=md.key('p','home','default','n7');
const h7=start('旧',{item:'n7',autosave:true});
h7.api.text='未落库'; h7.s.frame._markdownBridge.change('未落库');
md.suspend(); await flush();
assert.equal(saves.length,2); assert.equal(saves[1].body,'未落库');
saves[1].resolve(false);
for(let i=0;i<10&&md.current();i++) await flush();
assert.equal(md.current(),null);
assert.equal(md.getDraft(n7).value,'未落库');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_markdown_begin_covers_reading_view_until_ready():
    """所见即所得：编辑器加载期透明盖在阅读态上，ready 才接管，内容与高度不跳变。"""
    assert "frame.classList.add('proto-md-cover')" in MARKDOWN
    assert 'region.appendChild(frame)' in MARKDOWN
    assert 's.cover = true' in MARKDOWN and 's.kept = [...region.children]' in MARKDOWN
    ready = MARKDOWN.split('ready() {', 1)[1].split('resize(height)', 1)[0]
    # 接管必须逐个移除阅读节点：replaceChildren(frame) 会把已在文档里的 iframe 摘下再插回，浏览器销毁并重载其文档——
    # 编辑器初始化两次，中间一帧空白就是双击时的闪烁，且二次加载无焦点。
    assert 's.cover = false' in ready and 'for (const node of s.kept) if (node !== frame) node.remove();' in ready
    assert 'region.replaceChildren(frame)' not in ready
    # 接管即把焦点送进编辑器：Vditor 未聚焦时编辑面是灰底，否则要再点一下才变白
    assert 'frame.focus(); frame.contentWindow?.ProtoEditor?.focus();' in ready
    assert '.proto-md-frame.proto-md-cover' in MARKDOWN_CSS
    proto_md_rule = MARKDOWN_CSS.split('.proto-md {', 1)[1].split('}', 1)[0]
    assert 'position: relative' in proto_md_rule
    # 光标落在内容末尾并滚入可视区，进入编辑即可往下续写
    assert 'selectNodeContents' in MARKDOWN_EDITOR and 'collapse(false)' in MARKDOWN_EDITOR
    assert 'scrollIntoView' in MARKDOWN_EDITOR
    # 工作台入口先铺阅读态再进编辑，气泡卡首开也不从 120px 空窗起跳
    assert 'async function extEditNote' in VIEWER
    assert 'await ProtoMarkdown.render(region, extNoteOptions(note, theme))' in VIEWER
    # 换一条编辑/点其他序号/点空白：原会话自动保存并回到阅读态
    assert 'if (session.region === region) { focus(); return false; }' in MARKDOWN
    assert 'suspend(); // 换一条编辑' in MARKDOWN
    assert 'extSuspendNoteEdit(); // 选中其他序号' in VIEWER
    assert "e.target.closest('.proto-md.is-editing, .proto-md-toolbar, .proto-md-handle, .ext-note-menu, .pa-card')" in VIEWER


def test_markdown_cover_lifecycle_keeps_reading_view():
    markdown_session_harness("""
// 有阅读态时：编辑器透明盖顶，ready 后才撤下阅读态完成接管
const region=makeRegion();
const body=el('div'); body.className='proto-md-body'; region.appendChild(body);
assert.equal(md.begin(region,{key:md.key('p','home','default','cover-1'),value:'正文',label:'标注 1',save:pendingSave}),true);
const s=md.current();
assert.equal(s.cover,true);
assert.equal(region.children.length,2);
assert.equal(region.children[0],body);
assert.equal(s.frame.style.height,'100px');
s.frame.contentWindow={ProtoEditor:{text:s.value,value(){return this.text;},status(){},focus(){},destroy(){}}};
s.frame._markdownBridge.ready();
assert.equal(s.cover,false);
assert.equal(region.children.length,1);
assert.equal(region.children[0],s.frame);
// iframe 自身未被摘下重挂（否则文档重载、编辑器初始化两次）
assert.notEqual(s.frame.removed,true);
assert.equal(body.removed,true);
// 挂起清理无残留
md.suspend();
assert.equal(md.current(),null);
""")


def test_state_navigation_observer_resets_pick_and_preserves_scope():
    start = VIEWER.index('        function extWatchState()')
    end = VIEWER.index('        function extPageNotes()', start)
    node("""
const assert=require('node:assert/strict');
let extStateWatcher=null,extStateId='default',extSelectedNoteId='a',calls=[];
const doc={documentElement:{dataset:{protoState:'default'}}};
const previewFrame={contentWindow:{document:doc,ProtoAnnotate:{closeInputCard:()=>calls.push('close')}}};
const extSuspendNoteEdit=()=>calls.push(['draft',extStateId]);
const extAnnotateDeactivate=()=>calls.push(['exit',extStateId]),closeExtNoteMenu=()=>{};
const extRenderPins=()=>calls.push('pins'),renderExtAnnotList=()=>{},renderExtDoc=()=>{};
class MutationObserver {constructor(callback){this.callback=callback;} observe(el,opts){assert.deepEqual(opts.attributeFilter,['data-proto-state']);} disconnect(){this.disconnected=true;}}
""" + VIEWER[start:end] + """
extWatchState(); assert.equal(calls.length,0);
doc.documentElement.dataset.protoState='done'; extStateWatcher.callback();
assert.equal(extStateId,'done'); assert.equal(extSelectedNoteId,null);
assert.deepEqual(calls.slice(0,3),[['draft','default'],['exit','default'],'close']);
const old=extStateWatcher; extWatchState(); assert.ok(old.disconnected);
""")


def test_display_order_rows_deletion_pending_and_metadata_unchanged():
    node("""
const assert=require('node:assert/strict');
""" + ORDER + """
const n=(id,x,y,number)=>({note:{id,number,confirmed:true},point:x===null?null:{x,y}});
const records=[n('bottom',5,150,1),n('right',100,10,2),n('left',10,20,9),n('next',0,33,4),n('stale',null,0,8)];
const original=JSON.stringify(records);
let result=ProtoOrder.arrange(records);
assert.deepEqual(result.map(n=>n.id),['left','right','next','bottom','stale']);
assert.deepEqual(result.map(n=>n.displayNumber),[1,2,3,4,5]);
assert.equal(JSON.stringify(records),original);
assert.equal(result[0].number,9); assert.equal(result[0].confirmed,true);
assert.deepEqual(ProtoOrder.arrange(records.filter(r=>r.note.id!=='right')).map(n=>n.displayNumber),[1,2,3,4]);
assert.deepEqual(ProtoOrder.arrange([n('b',4,5,1),n('a',4,5,2)]).map(n=>n.id),['a','b']);
// 行起点容差不会通过链式 12px 比较跨行合并。
assert.deepEqual(ProtoOrder.arrange([n('a',90,0,1),n('b',80,10,2),n('c',0,20,3)]).map(n=>n.id),['b','a','c']);
const win={scrollX:5,scrollY:100,document:{scrollingElement:{}},ProtoAnchors:{at:()=>null,point:n=>({point:n.p})}};
assert.equal(ProtoOrder.previewNumber([{id:'a',p:{x:20,y:10}},{id:'b',p:{x:20,y:100}}],win,10,50),2);
const parent={scrollLeft:3,scrollTop:50,parentElement:win.document.scrollingElement};
const element={scrollLeft:7,scrollTop:20,parentElement:parent,getBoundingClientRect:()=>({x:-10,y:-40})};
assert.deepEqual(ProtoOrder.logicalPoint({element,point:{x:10,y:-30}},win),{x:25,y:140});
assert.deepEqual(ProtoOrder.logicalPoint({element,point:{x:0,y:0},legacy:true},win),{x:-2,y:110});
""")


def test_display_order_hidden_targets_proxy_and_branch_containers_follow_main_flow():
    """收起 / 条件显现的目标用触发器下缘代位参与主序（编号不因收起被甩到末尾）；
    弹窗 / 抽屉 / 提示等分支容器里的目标整体排主页序号之后；彻底失锚置底。"""
    node("""
const assert=require('node:assert/strict');
""" + ORDER + """
const n=(id,x,y,group)=>({note:{id},point:x===null?null:{x,y},group});
// arrange：主流(0) 行序 → 分支(1) 行序 → 无 point 置底；旧记录无 group 字段按主流处理。
assert.deepEqual(ProtoOrder.arrange([n('dlg',0,0,1),n('main2',0,50,0),n('main1',0,10),n('stale',null,0,0),n('dlg0',0,-5,1)]).map(r=>r.id),
    ['main1','main2','dlg0','dlg','stale']);
// DOM 桩：body > [row1(设备编号), select(智批题卡筛选), hiddenRow(选择智批题型, display:none), row3(列表展示项), dialog > inDlg]
const root={parentElement:null,scrollLeft:0,scrollTop:0};
const body={parentElement:root,scrollLeft:0,scrollTop:0};
const mk=(tag,rect,attrs={},parent=body)=>({tagName:tag,parentElement:parent,scrollLeft:0,scrollTop:0,
    getBoundingClientRect:()=>({x:0,y:0,width:100,height:0,...rect}),getClientRects:()=>rect?[rect]:[],
    hasAttribute:k=>k in attrs,getAttribute:k=>attrs[k]??null});
const row1=mk('DIV',{x:10,y:100,height:30}), select=mk('SELECT',{x:10,y:150,height:30});
const hiddenRow=mk('DIV',null), row3=mk('DIV',{x:10,y:200,height:30});
const dialog=mk('DIV',{x:300,y:0,height:400},{class:'ant-modal-wrap',role:'dialog'});
const inDlg=mk('BUTTON',{x:320,y:20,height:30},{},dialog);
const toastList=mk('UL',{x:0,y:400,height:100},{class:'notification-list'});   // 主流里的命名弱线索：static 定位不算分支
const inList=mk('LI',{x:0,y:410,height:20},{},toastList);
const win={scrollX:0,scrollY:0,document:{scrollingElement:root,body,documentElement:root},
    getComputedStyle:el=>({position:el===dialog?'fixed':'static'}),
    ProtoAnchors:{
        hidden:el=>el===hiddenRow,
        point:note=>note.el&&note.el!==hiddenRow?{element:note.el,point:note.el.getBoundingClientRect()}:null,
        resolveHidden:anchor=>anchor==='hidden'?hiddenRow:null,
        revealHint:(anchor,el)=>el===hiddenRow?{trigger:select,kind:'condition'}:null,
    }};
assert.equal(ProtoOrder.inBranch(inDlg,win),true);
assert.equal(ProtoOrder.inBranch(inList,win),false);
assert.equal(ProtoOrder.inBranch(row1,win),false);
const notes=[{id:'row3',el:row3,anchor:'a'},{id:'dlg',el:inDlg,anchor:'b'},{id:'hidden',anchor:'hidden'},{id:'row1',el:row1,anchor:'c'},{id:'lost',anchor:'gone'}];
const out=ProtoOrder.project(notes,win);
// 隐藏行代位到 select 下缘 y=180：在 设备编号(100) 之后、列表展示项(200) 之前 → 编号 2；弹窗内目标排主页之后；失锚最后。
assert.deepEqual(out.map(r=>[r.id,r.displayNumber]),[['row1',1],['hidden',2],['row3',3],['dlg',4],['lost',5]]);
// 预览序号：落在弹窗内的候选点算分支组，排到主页序号之后。
win.ProtoAnchors.at=(x,y)=>x>=300?inDlg:row1;
assert.equal(ProtoOrder.previewNumber(notes,win,330,10),5);
assert.equal(ProtoOrder.previewNumber(notes,win,10,90),1);
// data-proto-branch 显式声明覆盖自动推断。
const forced=mk('DIV',{x:0,y:0,height:10},{'data-proto-branch':'true'}); assert.equal(ProtoOrder.inBranch(forced,win),true);
const denied=mk('DIV',{x:0,y:0,height:10},{'data-proto-branch':'false',role:'dialog'}); assert.equal(ProtoOrder.inBranch(denied,win),false);
""")


def annotation_harness(test):
    hook = """
    globalThis.testState = values => {
        if ('active' in values) active = values.active;
        if ('selectedId' in values) selectedId = values.selectedId;
        if ('saving' in values) saving = values.saving;
        if ('composing' in values) composing = values.composing;
        if ('inputCard' in values) inputCard = values.inputCard;
        if ('pending' in values) pending = values.pending;
        if ('notes' in values) notes = values.notes;
        if ('hoverBox' in values) hoverBox = values.hoverBox;
        if ('pinLayer' in values) pinLayer = values.pinLayer;
    };
    globalThis.testAPI = { onKeyDown, onClick, placeCard, startDrag, moveDrag, endDrag, cancelDrag, closeInputCard, hideHover, setVisible, layoutPins };
"""
    instrumented = ANNOTATE.replace('    window.ProtoAnnotate = {', hook + '\n    window.ProtoAnnotate = {')
    return node("""
const assert = require('node:assert/strict');
const calls = [];
global.window = { addEventListener() {}, parent: { ProtoExtHost: {
    deleteNote: id => calls.push(['delete', id]),
    exitAnnotate: () => calls.push(['exit']),
    togglePick: () => calls.push(['toggle']),
    storePickDraft: (draft, key) => calls.push(['draft', draft, key]),
    clearSelection: () => calls.push(['clear']),
    moveNote: (id, anchor, placement) => calls.push(['move', id, anchor, placement]),
    markdown: { isBusy: () => false, current: () => null, focus: () => calls.push(['focus']), suspend: card => calls.push(['suspend', card]) }
} } };
global.document = { documentElement: { clientWidth: 276, clientHeight: 600 }, addEventListener() {}, removeEventListener() {} };
global.matchMedia = () => ({ matches: true });
""" + instrumented + '\n' + test)


def test_frozen_preview_number_survives_mouseleave_until_card_closes():
    """点击落点后序号冻结（pending）：鼠标移出 iframe 触发的 mouseleave 不得藏掉它；关卡清掉 pending 后才隐藏。"""
    annotation_harness("""
const box={style:{display:''}};
testState({active:true, hoverBox:box, pending:{anchor:null,x:10,y:10}, inputCard:{remove(){}}});
testAPI.hideHover(); assert.equal(box.style.display,'');
testAPI.closeInputCard(true); assert.equal(box.style.display,'none');
box.style.display=''; testState({pending:null}); testAPI.hideHover(); assert.equal(box.style.display,'none');
""")


def test_pins_hidden_in_preview_and_inspector_modes():
    """预览 / 微调模式收起整个序号层（序号 + 引导徽标 + 气泡卡）；编辑 / 研发 / 标注显示。
    显隐跟着 extRenderPins 下发（iframe 重载后不回默认可见），switchMode 末尾立即同步。"""
    assert "function extPinsVisible() { return !['preview', 'inspector'].includes(currentMode); }" in VIEWER
    assert 'w.ProtoAnnotate.setVisible?.(extPinsVisible());' in VIEWER
    switch_mode = VIEWER.split('function switchMode(mode) {', 1)[1].split('\n        }\n', 1)[0]
    assert switch_mode.rstrip().endswith('extRenderPins();')
    assert '.pa-layer[data-hidden]{display:none;}' in ANNOTATE
    assert re.search(r'window\.ProtoAnnotate = \{[^}]*\bsetVisible\b', ANNOTATE)
    annotation_harness("""
document.getElementById = () => ({});
const attrs = new Set(); let layouts = 0;
const layer = { hasAttribute: k => attrs.has(k), toggleAttribute(k, on) { on ? attrs.add(k) : attrs.delete(k); }, querySelectorAll: () => { layouts++; return []; } };
testState({ pinLayer: layer, notes: [] });
testAPI.setVisible(false); assert.ok(attrs.has('data-hidden'));
testAPI.setVisible(false); assert.ok(attrs.has('data-hidden'));
const before = layouts;
testAPI.setVisible(true); assert.ok(!attrs.has('data-hidden')); assert.ok(layouts > before);   // 重新可见立即重排（display:none 期间量不到宽度）
""")


def test_backspace_guards_and_escape_layers():
    annotation_harness("""
const event = overrides => ({ key:'Backspace', target: {closest:()=>false},
    preventDefault(){}, stopPropagation(){}, ...overrides });
testState({active:true, selectedId:'note-1'});
for (const guard of [ {repeat:true}, {ctrlKey:true}, {metaKey:true}, {altKey:true},
    {isComposing:true}, {target:{closest:()=>({})}} ]) testAPI.onKeyDown(event(guard));
assert.equal(calls.length,0);
testState({saving:true}); testAPI.onKeyDown(event()); assert.equal(calls.length,0);
testState({saving:false}); testAPI.onKeyDown(event()); assert.deepEqual(calls,[['delete','note-1']]);
let removed=false;
testState({inputCard:{remove(){removed=true;}}});
testAPI.onKeyDown(event({key:'Escape'})); assert.ok(removed); assert.deepEqual(calls.at(-1),['exit']);
let prevented = false;
testAPI.onKeyDown(event({key:'Escape',preventDefault(){prevented=true;}}));
assert.equal(prevented,false);
// 关闭添加后，明确选中的标注仍可删除。
testAPI.onKeyDown(event()); assert.deepEqual(calls.at(-1),['delete','note-1']);
""")


def test_pin_click_readonly_dblclick_edits_and_flicker_free_takeover():
    """序号单击只读 / 双击编辑；编辑器接管在定位完成后瞬时切换，无闪烁。"""
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    editor = (SRC / 'markdown-editor.js').read_text(encoding='utf-8')
    css = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    # 单击开阅读卡（不加载编辑器），双击才进编辑
    assert 'function openNote(id, edit = false)' in annotate
    assert 'pin.ondblclick' in annotate and 'openNote(note.id, true)' in annotate
    assert 'note.confirmed || !edit' in annotate
    # 已打开的阅读卡双击就地转编辑，不重建卡
    assert 'if (inputCard?.dataset.noteId === id)' in annotate
    # 编辑器在 bridge.ready() 接管前完成光标定位与滚动（接管帧即最终态；注释含同名字符串，取代码处的最后出现）
    after = editor.split('after: () => {', 1)[1]
    takeover = after.rindex('bridge.ready()')
    assert after.index('scrollIntoView') < takeover
    assert after.index('editor.focus()') < takeover
    # 接管瞬时化：frame 不再有 opacity 淡入
    frame_rule = css.split('.proto-md-frame {', 1)[1].split('}', 1)[0]
    assert 'transition' not in frame_rule


def test_dblclick_does_not_native_select_whole_note():
    """双击笔记不得选中其全部文本：.proto-md 是 role=button 的双击编辑区，
    原生双击会选中整段，焦点离开后整段以灰色失活选区显示（“灰底”）。
    拦第二击及以后（detail>1）的默认选中，保留单击拖选与 dblclick 进编辑。"""
    md = (SRC / 'proto-markdown.js').read_text(encoding='utf-8')
    assert "region.addEventListener('mousedown', e => { if (e.detail > 1 && !e.target.closest('a,button,input,iframe')) e.preventDefault(); });" in md
    # mousedown 守卫必须注册在 dblclick 之前（同一 region），且不影响 dblclick 进编辑
    md_at = md.index("region.addEventListener('mousedown'")
    db_at = md.index("region.addEventListener('dblclick'")
    assert md_at < db_at


def test_markdown_editor_enter_caret_and_table_overflow():
    """编辑区回车光标可见 + 表格单元格不溢出：同步量高、selectionchange 兜底、margin 不逸出量算、td 可换行。"""
    editor = (SRC / 'markdown-editor.js').read_text(encoding='utf-8')
    css = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    # 表格：覆盖 Vditor reset 的 td nowrap，编辑态内容在单元格内换行不溢出
    td_rule = css.split('.proto-md-body :is(th,td)', 1)[1].split('}', 1)[0]
    assert 'white-space: normal' in td_rule and 'overflow-wrap: anywhere' in td_rule
    # 回车：量高支持同步回传（immediate），输入回调走同步路径
    assert 'function resize(immediate = false)' in editor
    assert 'if (immediate) { bridge.resize(' in editor
    input_cb = editor.split('input: () => {', 1)[1].split('}', 1)[0]
    assert 'resize(true)' in input_cb
    # 回车兜底：selectionchange 在光标越出视口时同步量高（Vditor input 回调本身异步）
    sel = editor.split("document.addEventListener('selectionchange'", 1)[1].split('});', 1)[0]
    assert 'caret.bottom > window.innerHeight + 1' in sel and 'resize(true)' in sel
    # 首轮量高同步：在 bridge.ready() 接管前完成
    after = editor.split('after: () => {', 1)[1]
    assert after.index('resize(true)') < after.rindex('bridge.ready()')
    # 揭盖前双 rAF 等编辑器内容绘制一帧，避免 iframe 未上屏时揭盖闪空白；隐藏页签 setTimeout 兜底且幂等
    assert 'requestAnimationFrame(() => requestAnimationFrame(fireReady))' in editor
    assert 'setTimeout(fireReady, 150)' in editor
    assert 'if (revealed || destroyed) return; revealed = true;' in editor
    # 高度量算：编辑面内边距归零（与阅读态对齐、双击无缝）；margin 逸出由 pre margin:0 阻断（非靠 ir 的 padding-top）
    assert '.markdown-editor .vditor-ir { padding: 0; }' in css
    pre_rule = css.split('.vditor-ir pre.vditor-reset:focus {', 1)[1].split('}', 1)[0]
    assert 'margin: 0' in pre_rule and 'margin-top' not in pre_rule
    # 末元素 margin 穿透改由 flow-root 包容（阅读态与编辑态同口径），body 不再留 1px、量高不再 +3——否则单行标注接管时多出 4~5px
    body_rule = css.split('.markdown-editor body {', 1)[1].split('}', 1)[0]
    assert 'padding: 0;' in body_rule and '1px' not in body_rule
    assert '.proto-md-body, .markdown-editor .vditor-ir pre.vditor-reset { display: flow-root; }' in css
    assert 'getBoundingClientRect().height + 3' not in editor
    assert 'const measure = () => document.body.getBoundingClientRect().height;' in editor
    # 竖向 overflow hidden：高度由父层跟随内容，亚像素取整差不再冒出内部滚动条
    root_rule = css.split('.markdown-editor {', 1)[1].split('}', 1)[0]
    assert 'overflow-y: hidden' in root_rule


def test_sidebar_note_layout_content_first():
    """右栏标注行：序号与「更多」同处首行，正文另起一行（双击编辑时序号不消失）。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    # 行结构：首行 head（序号 + 更多）在前，内容 content 在后
    assert '<div class="ext-note-head"><button type="button" class="ext-note-no">' in viewer
    assert '</button></div><div class="ext-note-content">' in viewer
    # head 行：flex 两端对齐（序号左 / 更多右）
    head_rule = viewer.split('\n        .ext-note-head {', 1)[1].split('}', 1)[0]
    assert 'display: flex' in head_rule and 'justify-content: space-between' in head_rule
    # 序号不再 float，仍为 20px 水滴小圆
    no_rule = viewer.split('\n        .ext-note-no {', 1)[1].split('}', 1)[0]
    assert 'float' not in no_rule and 'height: 20px' in no_rule and 'font-size: 11px' in no_rule
    # 「更多」首行内静态定位（不再 absolute），常态透明悬停显现
    more_rule = viewer.split('.ext-note-more {', 1)[1].split('}', 1)[0]
    assert 'position: absolute' not in more_rule and 'opacity: 0' in more_rule
    assert '.ext-note:hover .ext-note-more' in viewer and '.ext-note-more[aria-expanded="true"]' in viewer
    # 正文全宽，不再为悬浮按钮预留 26px 右内边距
    body_rule = viewer.split('.ext-note-body {', 1)[1].split('}', 1)[0]
    assert 'padding: 4px 26px 4px 0' not in body_rule


def test_viewer_publish_block_has_two_modes_and_download():
    """viewer 右上角发布区：研发版/纯净版二选一，发布与下载共用版本，状态显示版本。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    # 版本 segmented：研发版默认选中 + 纯净版
    assert 'name="extPubMode" value="review" checked' in viewer
    assert 'name="extPubMode" value="pure"' in viewer
    # 发布按所选版本提交；本地下载共用版本
    assert 'JSON.stringify({ extId, mode: extPubMode() })' in viewer
    assert 'function extDownloadLocal()' in viewer and '/api/ext/export?extId=' in viewer
    # 已发布状态显示版本（旧记录无 mode 时回落不显示）
    assert "{ review: '研发版', pure: '纯净版' }[data.mode] || ''" in viewer


def test_card_toolbar_placement_resize_and_grip_bugfix():
    """气泡卡拖宽与 grip 一按消失修复；工具条位置由浏览器几何用例验证。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    markdown = (SRC / 'proto-markdown.js').read_text(encoding='utf-8')
    # grip 修复：iframe 内 pointerdown 只挂起右栏（顶层文档）会话，气泡卡会话不被误销毁
    assert 's.region.ownerDocument === document' in viewer
    assert "hoverBox.setAttribute('data-proto-toolbar-avoid', '');" in annotate
    assert "pin.toggleAttribute('data-proto-toolbar-avoid', selected);" in annotate
    assert "pin.toggleAttribute('data-proto-toolbar-avoid', note.id === selectedId);" in annotate
    open_card = annotate.split('function openInputCard(', 1)[1].split('function makeCard(', 1)[0]
    assert open_card.index('showPreviewNumber(x, y);') < open_card.index('host()?.markdown?.relayout?.();')
    # 工具条重定位接口（卡拖宽后跟随）；初始定位同步不依赖 rAF
    assert 'relayout: () => { if (session) { if (!session.toolbarManual) placeToolbar(session); placeHandle(session); } },' in markdown
    assert 'placeToolbar(s); // 同步定位' in markdown
    # 气泡卡边缘拖拽调尺寸：外壳不裁剪 + 内部滚动区，热区骑在真实边框上（外 6px）不随内容滚走；只用光标表达，不再画那条蓝线（用户反馈）
    card_rule = re.search(r'\n\.pa-card\{([^}]*)\}', annotate).group(1)
    assert 'overflow:visible' in card_rule and 'display:flex;flex-direction:column' in card_rule
    assert 'width:420px' in card_rule and 'max-height:min(60vh,calc(100% - 24px))' in card_rule, '默认加宽、高度不再撑满整屏'
    assert '.pa-card.pa-sized{max-height:calc(100% - 24px);}' in annotate
    assert '.pa-layer .pa-card-scroll{flex:1 1 auto;min-height:0;' in annotate
    assert '.pa-card-resize-e{right:-6px;}' in annotate and '.pa-card-resize-w{left:-6px;}' in annotate
    assert '.pa-card-resize-s{left:0;right:0;bottom:-6px;height:10px;cursor:ns-resize;}' in annotate
    assert '.pa-card-resize-se{right:-6px;cursor:nwse-resize;}' in annotate and '.pa-card-resize-sw{left:-6px;cursor:nesw-resize;}' in annotate
    assert '.pa-card-resize::after' not in annotate and '.pa-card-resize:hover' not in annotate
    # 靠边缘输入留间距（用户反馈）：卡与视口边缘最小 12px（CSS 对应 calc(100% - 24px)）；正文右侧 20px 不贴滚动条；
    # 落点不可见（折叠 / 过渡动画量到屏外坐标）时不挪卡，避免开着的卡被甩到边角
    assert 'const CARD_EDGE = 12;' in annotate
    assert 'padding:8px 20px 12px 12px' in annotate
    assert 'Math.max(CARD_EDGE, Math.min(left, width - w - CARD_EDGE))' in annotate
    assert 'cardHeight() - startT - CARD_EDGE' in annotate
    assert 'if (inputCard?.dataset.noteId === note.id && found.point.visible) placeCard(x, y);' in annotate
    assert "for (const side of ['w', 'e', 's', 'se', 'sw'])" in annotate
    assert 'function startCardResize(e, card, handle, side)' in annotate
    assert 'Math.min(760, cardWidth() - CARD_EDGE * 2)' in annotate and 'Math.min(280, hi)' in annotate
    assert 'Math.min(160, hi)' in annotate and "card.classList.add('pa-sized');" in annotate
    assert "const RESIZE_CURSOR = { e: 'ew-resize', w: 'ew-resize', s: 'ns-resize', se: 'nwse-resize', sw: 'nesw-resize' };" in annotate
    assert 'cardResizing' in annotate and 'cardManual' in annotate
    assert "host()?.markdown?.relayout?.()" in annotate
    # 拖宽 / 拖动全程由卡所在文档的 window 接管（指针越过编辑器 iframe 不丢事件），按 pointerId 过滤，结束还原光标与选区
    assert 'function trackPointer(e, target, onMove, onEnd, cursor)' in annotate
    assert "const win = target.ownerDocument?.defaultView || window;" in annotate
    assert "win.addEventListener('pointermove', move, true)" in annotate
    assert 'ev.pointerId !== e.pointerId' in annotate
    # 按住卡面拖动：排除正文 / 底栏 / 控件 / 拖宽把手；5px 阈值后才算拖；拖过的卡记下相对锚点偏移，重排时跟随而不回默认位
    assert 'function startCardMove(e, card)' in annotate
    assert "e.target.closest('.pa-card-resize, .pa-card-text, .pa-card-foot, button, a, input, iframe')" in annotate
    assert 'let cardOffset = null;' in annotate
    assert 'cardOffset = cardPoint ? { x: left - cardPoint.x, y: top - cardPoint.y } : null;' in annotate
    assert 'if (cardOffset) { left = x + cardOffset.x; top = y + cardOffset.y; }' in annotate
    assert '.pa-card-grip{position:relative;flex:0 0 auto;' in annotate
    # 序号单击开卡、再击同一序号关卡；双击的第二击（detail>1）不走 toggle，dblclick 仍就地转编辑
    assert 'if (e.detail > 1) return;' in annotate
    open_note = annotate.split('function openNote(', 1)[1].split('\n    function ', 1)[0]
    assert 'closeInputCard();' in open_note and "'dark'" not in open_note
    # 卡内容重写只动滚动区：三处正文填充走 setCardBody，不再 innerHTML 整体冲掉拖柄 / 热区
    assert 'function setCardBody(card, html)' in annotate and annotate.count('setCardBody(') >= 4
    assert "card.querySelector(':scope > .pa-card-scroll').innerHTML = html;" in annotate
    assert "card.innerHTML = '<div class=\"pa-card-body" not in annotate
    # 窄视口兜底：工具条可折行且宽不超过视口，四方向避让重新可行
    css = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    bar_rule = css.split('.proto-md-toolbar { position: fixed', 1)[1].split('}', 1)[0]
    assert 'flex-wrap: wrap' in bar_rule and 'max-width: calc(100vw - 8px)' in bar_rule
    # 抗原型页 CSS 污染：按钮/握把显式 margin: 0（原型全局 button{margin} 会套上来）；按钮基础规则与表格角标共用
    btn_rule = css.split(':is(.proto-md-toolbar, .proto-md-handle) button {', 1)[1].split('}', 1)[0]
    assert 'margin: 0' in btn_rule
    grip_rule = css.split('.proto-md-grip {', 1)[1].split('}', 1)[0]
    assert 'margin: 0' in grip_rule


def test_review_shell_note_number_matches_workbench_style():
    """研发版导出（评审壳）右栏序号与操作界面同式：序号单独首行、正文另起一行，蓝色与预览一致。"""
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 行结构 block + 序号 head 行（与操作台新版布局一致），序号不再 float
    note_rule = shell.split('.note {', 1)[1].split('}', 1)[0]
    assert 'flow-root' not in note_rule and 'display: block' in note_rule
    assert '.note-head {' in shell and "head.append(no)" in shell and 'row.append(head, body)' in shell
    no_rule = shell.split('.note-no {', 1)[1].split('}', 1)[0]
    assert 'float' not in no_rule and 'height: 20px' in no_rule and 'font-size: 11px' in no_rule
    # 评审壳主色与预览（viewer 的 --ext-accent #2563eb）统一
    assert '--accent: #2563eb;' in shell
    # 失锚灰圆与操作界面一致
    assert '.note.stale .note-no' in shell and 'background: var(--muted)' in shell
    assert "createElement('strong')" not in shell and 'stale-badge' not in shell


def test_review_pin_matches_workbench_pin_style():
    """研发版页面序号气泡与预览同式：水滴 36px、白描边、#2563eb、锚点在尖部。"""
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    # 与 .pa-pin 同式：水滴形、尺寸、描边、主色、向上锤点
    assert 'border-radius:50% 50% 50% 2px' in pins and 'min-width:36px;height:36px' in pins
    assert 'border:3px solid #fff' in pins and 'background:#2563eb' in pins
    assert 'transform:translateY(-100%)' in pins
    # 不再是旧的圆形小标（居中定位 + 22px + 圆角 999px）
    assert 'translate(-50%,-50%)' not in pins and 'border-radius:999px' not in pins


def test_editor_enter_visible_and_seamless_swap_and_no_autosave_toast():
    """编辑器三修：回车空行可见、双击无缝接管（零内边距对齐）、去掉自动保存提示气泡。"""
    css = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    md = (SRC / 'proto-markdown.js').read_text(encoding='utf-8')
    # #1 回车：空块补零宽字符行盒，光标可见
    assert 'p:empty::before' in css and 'content: "\\200b"' in css
    assert 'li:empty::before' in css and 'blockquote:empty::before' in css
    # #3 无缝接管：编辑面内边距归零与阅读态对齐；pre 强制零内边距（Vditor 内联 10px）
    assert '.markdown-editor .vditor-ir { padding: 0; }' in css
    # 编辑面白底同时覆盖 :focus（Vditor 未聚焦灰底）；white-space 保持 pre-wrap 与阅读态 <br> 软换行等高
    assert '.markdown-editor .vditor-ir pre.vditor-reset, .markdown-editor .vditor-ir pre.vditor-reset:focus { background: var(--md-surface); margin: 0; padding: 0 !important; }' in css
    assert 'white-space: normal; margin: 0' not in css
    # 阅读态悬停不再画虚线描边（用户要求去掉；选中态由右栏蓝框承担）
    assert 'dashed' not in css and ':hover { outline' not in css
    # 逐块等高：li 间距归零、空单元格撑行盒、hr 两边同口径
    assert '.markdown-editor .vditor-reset li + li { margin-top: 0; }' in css
    assert '.proto-md-body :is(th,td):empty::before { content: "\\200b"; }' in css
    assert '.proto-md-body hr, .markdown-editor .vditor-reset hr {' in css
    # 工作台空闲时预热一次编辑器文档（命中缓存，首次双击不再冷加载）；Node 测试环境无 document 需守卫
    assert 'function warm()' in md and "typeof document !== 'undefined'" in md
    # #3 高度下限改为每会话 min（编辑既有标注贴合内容、不再固定 80 造成跳变）
    assert 'minH: options.minHeight ?? 28' in md
    assert 'Math.max(s.minH, Math.ceil(height))' in md
    # #4 不再弹「输入即自动保存 / 已恢复草稿」提示（保留冲突警示）
    assert '输入即自动保存' not in md and '已恢复未提交草稿' not in md
    assert '草稿对应的正文已变化' in md


def test_pin_click_routes_by_prd_state_viewer_and_export():
    """点序号按 PRD 展开/收起分流：收起→序号旁弹内容，展开→定位右栏（编辑/发布/导出一致）。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 编辑态（viewer + proto-annotate）：host 暴露 prdExpanded；序号点击按展开态分流
    assert 'prdExpanded: () => prdExpanded' in viewer
    assert 'if (host()?.prdExpanded?.()) { closeInputCard(true); host()?.focusNote?.(note.id); return; }' in annotate
    # 收起态弹气泡不再回调 focusNote（否则会把 PRD 自动展开，破坏意图）
    assert '不再回调 focusNote' in annotate
    # 导出/发布态：侧栏状态与正文渲染由 review-bridge 在 iframe 内暴露（壳只通过 postMessage 同步 asideOpen / 预渲染 bodyHtml），点击同样分流
    bridge = (SRC / 'review-bridge.js').read_text(encoding='utf-8')
    assert 'asideOpen: () => asideOpen' in bridge and "case 'aside':" in bridge
    assert "renderBody: (note) => note.bodyHtml ||" in bridge
    assert "post({ type: 'aside', open: !closed })" in shell
    assert "const prdAsideOpen = () => !$('layout').classList.contains('right-closed') && !$('layout').classList.contains('prd-empty')" in shell
    assert 'asideOpen: prdAsideOpen()' in shell
    assert "bodyHtml: md(" in shell
    assert 'function showPop(note, pin)' in pins and '.__review_pop{position:fixed' in pins
    assert 'if (R.asideOpen && R.asideOpen()) { hidePop(); R.onFocus?.(n.id); }' in pins
    assert 'else togglePop(n, pin);' in pins
    assert 'window.__reviewHidePop = hidePop;' in pins
    # 同一序号是显式开关：首击显示、再次点击隐藏；切换其他序号直接换正文
    assert 'function togglePop(note, pin)' in pins
    assert "pop.style.display === 'block' && popNoteId === note.id" in pins
    assert 'showPop(note, pin);' in pins
    assert 'popNoteId = note.id;' in pins and 'popNoteId = null;' in pins
    assert "pin.dataset.noteId = n.id;" in pins
    assert "pin.setAttribute('aria-expanded', String(popNoteId === n.id && pop?.style.display === 'block'))" in pins
    assert "pin.setAttribute('aria-haspopup', 'dialog')" in pins and "pop.setAttribute('role', 'dialog')" in pins
    # 气泡只在状态切换时关，几何重排不误关（避免收起引发的 reflow 秒关刚弹出的气泡）
    assert 'if (state !== lastState) hidePop()' in pins
    # 气泡正文可独立滚动：capture scroll 必须排除 pop 内部目标，滚动到边界也不串到原型页面
    assert 'overflow:auto;overscroll-behavior:contain' in pins
    assert "if (pop && pop.style.display === 'block' && pop.contains(e.target)) return;" in pins
    assert "window.addEventListener('scroll', hidePop" not in pins
    # 定位右栏的滚动语义：保证行首（序号）进视口。scrollIntoView({block:'nearest'}) 对「比滚动容器高且正覆盖视口」的
    # 长标注是规范 no-op（box 两端都超出滚动口不滚动）——长文标注停在视口中部时点序号不滚动（2026-09-30 用户报障）；两侧同源修复。
    assert 'function extScrollNoteIntoView(row)' in viewer
    assert "const pad = parseFloat(getComputedStyle(sc).scrollPaddingTop) || 16;" in viewer
    assert 'if (top >= pad && top < sc.clientHeight) return;' in viewer
    assert 'extScrollNoteIntoView(row);' in viewer
    assert "row?.scrollIntoView({ block: 'nearest'" not in viewer
    assert "row.closest('aside')" in shell and 'if (top < 0 || top >= sc.clientHeight) sc.scrollTo({' in shell
    assert "row.scrollIntoView({ block: 'nearest'" not in shell
    # PRD 展开时，收起态开的序号浮窗自动迁移为右栏定位（2026-09-30 用户裁定）：关卡 + 行首定位 + 高亮；编辑 / 发布 / 导出三态同源
    assert 'openNoteId: () => inputCard?.dataset.noteId || null' in annotate
    assert 'const openId = pa?.openNoteId?.();' in viewer
    assert 'if (openId) { pa.closeInputCard(true); extFocusNote(openId, true); }' in viewer
    assert 'window.__reviewPopNoteId' in pins
    assert 'frame.contentWindow?.__reviewPopNoteId?.()' in shell and 'onPinFocus(openPopId);' in shell


def test_export_pin_popover_resizable_from_both_edges():
    """发布/导出页序号 PRD 浮窗：正文独立滚动，左右边缘均可按住横向拖宽，280–720px 钳制。"""
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    assert 'function startPopResize(e, handle, side)' in pins
    assert "for (const side of ['w', 'e'])" in pins
    assert '__review_pop_resize_w{left:0;transform:translateX(-50%);}' in pins
    assert '__review_pop_resize_e{right:0;transform:translateX(50%);}' in pins
    assert 'cursor:ew-resize' in pins and 'touch-action:none' in pins
    # 不再绘制独立蓝细条；命中的是浮窗真实边框，按下后由 window 兜住拖动
    assert '.__review_pop_resize::after' not in pins
    assert "window.addEventListener('pointermove', move, { capture: true, passive: false })" in pins
    assert "window.addEventListener('pointerup', up, true)" in pins
    assert "window.removeEventListener('pointermove', move, true)" in pins
    assert "try { handle.setPointerCapture(e.pointerId); } catch (_)" in pins
    assert "try { if (handle.hasPointerCapture(e.pointerId)) handle.releasePointerCapture(e.pointerId); } catch (_)" in pins
    assert "document.documentElement.style.cursor = 'ew-resize'" in pins and "document.documentElement.style.userSelect = 'none'" in pins
    assert "const raw = side === 'e' ? startW + (ev.clientX - startX) : startW - (ev.clientX - startX);" in pins
    assert 'Math.min(280, innerWidth - 16)' in pins and 'Math.min(720, innerWidth - 16)' in pins
    assert "pop.style.width = width + 'px'" in pins
    assert "if (side === 'w') pop.style.left = Math.max(8, fixedRight - width) + 'px';" in pins
    # 外壳负责定位/拖边，body 负责滚动；showPop 只替换正文，不能冲掉拖拽把手
    assert 'popBody = document.createElement(\'div\'); popBody.className = \'__review_pop_body\'' in pins
    assert 'popBody.innerHTML = R.renderBody' in pins
    show = pins.split('function showPop(note, pin)', 1)[1].split('window.__reviewHidePop', 1)[0]
    assert 'pop.innerHTML' not in show


def test_export_prd_area_resizable():
    """导出原型右栏 PRD 区可拖拽放大缩小（与编辑态一致）：拖拽条 + 宽度记忆 + 收起归 0。"""
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 拖拽条元素与样式
    assert 'id="prd-resizer"' in shell and '#prd-resizer {' in shell
    assert 'cursor: ew-resize' in shell and '.right-closed #prd-resizer, .prd-empty #prd-resizer { display: none; }' in shell
    # 拖拽逻辑：pointerdown 拖动改 --right，钳制 280-720，存 localStorage
    assert "prdResizer.addEventListener('pointerdown'" in shell
    assert 'Math.max(280, Math.min(startWidth + (startX - ev.clientX), 720))' in shell
    assert "const PRD_KEY = 'proto-review-prd-width'" in shell
    # 宽度记忆回放 + 收起时清除内联宽度让 --right 归 0
    assert 'const applyPrdWidth' in shell
    assert "$('layout').style.removeProperty('--right')" in shell
    # 拖拉条常显握把（中部 4×40 圆角条），不再只靠 hover 才能发现；悬停/拖动时整条亮主色
    resizer_after = shell.split('#prd-resizer::after {', 1)[1].split('}', 1)[0]
    assert 'width: 4px' in resizer_after and 'height: 40px' in resizer_after and 'background: var(--control)' in resizer_after
    assert '#prd-resizer:hover::before { background: var(--accent); }' in shell
    assert '#prd-resizer.resizing::before' in shell


def test_review_shell_prd_compact_spacing_and_empty_sections_hidden():
    """发布/导出评审壳：PRD 纵向留白紧凑；页面需求/标注明细为空分别隐藏，两者都空时收掉整栏。"""
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 间距：右栏外边距、标题、区块、summary 与 Markdown 段落均收紧
    aside_rule = shell.split('\n            aside {', 1)[1].split('}', 1)[0]
    assert 'padding: 12px 16px 16px' in aside_rule
    assert 'aside h2 { font-size: 17px; margin: 0 0 4px; }' in shell
    assert 'details { border-bottom: 1px solid var(--border); padding: 7px 0; }' in shell
    assert 'details[open] > summary { margin-bottom: 6px; }' in shell
    assert '.markdown :is(h1,h2,h3,h4) { margin: 12px 0 6px;' in shell
    # 段落间距 0：Enter 换段与自然折行间距一致，工作台与评审壳同口径
    assert '.markdown p { margin: 0; }' in shell
    assert '.proto-md-body p, .markdown-editor .vditor-reset p { margin: 0; }' in (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    # 区块有稳定 id；空文档/空标注明细分别 hidden，不再渲染“暂无…”占位
    assert 'id="document-section"' in shell and 'id="notes-section"' in shell
    assert "$('document-section').hidden = !docHasContent;" in shell
    assert "$('notes-section').hidden = !notesHasContent;" in shell
    assert "'*暂无页面需求*'" not in shell and '本状态暂无标注。' not in shell
    # 两块都空：第三列归 0、aside/拖拽条/开关隐藏；iframe 收到 aside=false，点序号走就地气泡
    assert "const prdEmpty = !docHasContent && !notesHasContent;" in shell
    assert "$('layout').classList.toggle('prd-empty', prdEmpty);" in shell
    assert "$('toggle-prd').hidden = prdEmpty;" in shell
    assert ".layout.prd-empty { grid-template-columns: var(--left) minmax(0, 1fr) 0; }" in shell
    assert "post({ type: 'aside', open: !prdEmpty && !$('layout').classList.contains('right-closed') })" in shell


def test_review_shell_talks_to_iframe_via_postmessage_only():
    """评审壳不再跨文档向 iframe 注入脚本（file:// 下每个文件独立源会静默失效），只走 postMessage 握手。"""
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    bridge = (SRC / 'review-bridge.js').read_text(encoding='utf-8')
    # 壳：无脚本占位、无 contentDocument 访问、无 inject
    assert '__SRC_' not in shell and 'contentDocument' not in shell and 'function inject(' not in shell
    assert "frame.contentWindow?.postMessage(Object.assign({ __review: 1 }, msg), '*')" in shell
    # 壳：校验消息来源为当前 iframe；ready 握手后才接受 sync/focus
    assert 'if (e.source !== frame.contentWindow || !e.data || e.data.__review !== 1) return;' in shell
    assert "if (m.type === 'ready') { onFrameReady(m.ids || {}); return; }" in shell
    assert 'if (!frameReady) return;' in shell
    assert "post({ type: 'init', notes: pageNotes()" in shell
    assert "post({ type: 'enterState', stateId })" in shell
    # 桥：只信父页消息；独立打开（非 iframe）时不动
    assert 'if (e.source !== window.parent || !e.data || e.data.__review !== 1) return;' in bridge
    assert 'if (window.parent === window || !window.ProtoAnchors) return;' in bridge
    assert "post({ type: 'ready', ids })" in bridge and "onSync: (map, state, stale) => post({ type: 'sync'" in bridge


def test_inspector_finetune_available_for_external_projects():
    """微调（Inspector）在外部项目也可用：不再隐藏入口；Prompt 走 .prototype 约定交 Agent；AI 直改仅内部。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    # 入口：外部模式只隐编辑/研发，不再隐藏微调（inspector）
    assert '.compact-mode-btn[data-mode="edit"], .compact-mode-btn[data-mode="dev"]\').forEach(el => el.style.display = \'none\')' in viewer
    assert '.compact-mode-btn[data-mode="dev"], .compact-mode-btn[data-mode="inspector"]\').forEach' not in viewer
    # 外部项目专用的微调 Prompt：沿用 .prototype 修改任务约定，捕获 data-proto-id
    assert 'function extInspectorPrompt(' in viewer
    assert 'if (extId) return extInspectorPrompt(userInput, selectedElements);' in viewer
    assert "el.getAttribute('data-proto-id')" in viewer
    assert '# 原型微调任务' in viewer and '# 原型整页面微调任务' in viewer
    # 选元 HTML 剔除 inspector 高亮类（克隆后取 outerHTML）
    assert "clone.classList.remove('inspector-selected', 'inspector-highlight')" in viewer
    # AI 直接修改：外部模式隐藏 + 函数内兜底拦截
    assert 'inspector-ai-btn' in viewer
    assert 'body.ext-mode .inspector-ai-btn { display: none; }' in viewer
    assert viewer.count("if (extId) { showToast('外部项目请用「复制 Prompt」交给 Agent 修改真实源文件', 'warning'); return; }") >= 2


def test_selected_prd_block_white_with_blue_border_and_task_status_tooltip():
    """右栏选中态收进首行：head 行淡蓝底条 + 序号光环，整块不再画蓝框；任务状态徽章有自解释悬停提示。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    # 整块不再有选中样式（旧：白底 + inset 2px 蓝框 + 圆角 + 隐分隔线）
    assert '.ext-note.flash {' not in viewer and 'inset 0 0 0 2px var(--ext-accent)' not in viewer
    # 选中信号在 head 行：淡蓝底条 + 序号白隙蓝环（与页面气泡 .pa-selected 光环同款）
    assert '.ext-note.flash .ext-note-head { background: var(--ext-soft); }' in viewer
    assert '.ext-note.flash .ext-note-no { box-shadow: 0 0 0 2px var(--ext-surface), 0 0 0 4px var(--ext-accent); }' in viewer
    # head 负 margin 与 padding 等量，选中/未选中盒子不变（正文不跳）
    head_rule = viewer.split('\n        .ext-note-head {', 1)[1].split('}', 1)[0]
    assert 'margin: -5px -8px 8px' in head_rule and 'padding: 5px 8px' in head_rule and 'border-radius: 6px' in head_rule
    assert '.ext-note.flash:has(.ext-note-body.is-editing)' not in viewer
    assert '#f4f7fe' not in viewer
    # 任务状态徽章：悬停提示解释含义（不再只显内部 task.id）
    assert 'const statusTip = {' in viewer
    assert '已把这条标注生成为一条修改任务' in viewer
    assert 'title="${statusTip}"' in viewer
    assert 'title="修改任务 ${task.id}"' not in viewer


def test_collapse_reveal_and_click_guidance_across_contexts():
    """折叠标注的点击引导 + 点序号联动展开：编辑/导出/发布三态共用 ProtoAnchors 展开能力。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 共享展开能力：resolveHidden / revealTrigger / reveal，且识别 aria-controls 折叠按钮
    assert 'function resolveHidden(' in anchors and 'function revealTrigger(' in anchors and 'function reveal(' in anchors
    assert 'aria-controls' in anchors and "getAttribute('aria-expanded') === 'false'" in anchors
    assert 'resolveHidden,' in anchors and 'revealTrigger,' in anchors and 'reveal,' in anchors  # 已导出
    # 编辑态：引导徽标（Feature 1）+ 点序号先展开再定位（Feature 2）
    assert 'function layoutGuides()' in annotate and "className = 'pa-guide'" in annotate
    assert 'ProtoAnchors.reveal?.(target)' in annotate and 'revealThrough(note.anchor)' in annotate
    # 导出/发布态（评审壳，GitHub Pages 同一套）：引导徽标 + reveal 前置展开（壳发 reveal 消息，iframe 内 bridge 执行）
    bridge = (SRC / 'review-bridge.js').read_text(encoding='utf-8')
    assert "className = '__review_guide'" in pins and 'window.__reviewRelayout' in pins
    assert "post({ type: 'reveal', note })" in shell
    assert 'A.reveal?.(note.anchor)' in bridge and "case 'reveal':" in bridge


def test_hidden_pins_stay_hidden_and_guide_is_transparent_overlay():
    """三修：隐藏序号不再摆成左上角灰网格；引导多点不丢；引导改成透明描边框盖在触发器上（保留呼吸）。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    # #1 定不到落点的序号一律 visibility:hidden，删掉旧的左上角 48px 网格；评审壳页面上不渲染无落点 pin
    assert "if (!found.point) { pin.style.visibility = 'hidden'; return; }" in annotate
    assert '16 + (index % 6) * 48' not in annotate and 'Math.floor(index / 6) * 48' not in annotate
    assert 'if (!found?.point) { noPoint.push(n); continue; }' in pins
    # #2a reveal 同一触发器只点一次（Vue/React 原型 nextTick 才更新 DOM，重复点会把展开的区域再折回）
    reveal = anchors.split('function reveal(', 1)[1].split('\n    }', 1)[0]
    assert 'const clicked = attempted;' in reveal and 'clicked.has(trig)' in reveal and 'clicked.add(trig);' in reveal
    # #2c 隐藏子树 innerText 退化为 textContent（span 间空格消失），文本比对必须忽略空白；共享 sameText 已上提到文件顶部，resolve / resolveHidden 同规则
    resolve_hidden = anchors.split('function resolveHidden(', 1)[1].split('function revealTrigger(', 1)[0]
    assert "const loose = (s) => (s || '').replace(/\\s+/g, '');" in anchors
    assert '(idBound(anchor) || sameText(list[0], anchor.text))' in resolve_hidden
    assert 'sameText(el, anchor.text) && sameText(el.parentElement, anchor.parentText)' in resolve_hidden
    assert 'text(list[0]) === anchor.text' not in anchors and 'text(el) === anchor.text' not in anchors
    # #2b 编辑态原型自身交互（展开/折叠/切页签）后也要重排，不能只靠 scroll/resize；自有节点变动过滤掉防死循环
    assert 'new MutationObserver((records) => { if (records.some((r) => !owned(r.target))) scheduleLayout(); })' in annotate
    assert "attributeFilter: ['class', 'style', 'hidden', 'open', 'aria-expanded', 'aria-hidden']" in annotate
    assert "document.addEventListener('transitionend'" in annotate and "document.addEventListener('animationend'" in annotate
    # #3 透明可点虚线框 + 拼接式呼吸标签，两侧同源；亮黄色系（框线 #d97706 / 标签 #fbbf24 深棕字 #5c3300）与蓝色序号区分
    for src, cls, tag, below, end, kf in ((annotate, '.pa-guide', '.pa-guide-tag', 'pa-guide-below', 'pa-guide-end', 'paGuideTag'),
                                          (pins, '.__review_guide', '.__review_guide_tag', '__review_guide_below', '__review_guide_end', '__rvGuideTag')):
        rule = src.split(cls + '{', 1)[1].split('}', 1)[0]
        assert '--g-line:#d97706;--g-fill:#fbbf24;--g-ink:#5c3300;' in rule
        assert 'border:2px dashed var(--g-line)' in rule and 'border-radius:0 8px 8px 8px' in rule   # 左上直角与标签拼接
        assert 'cursor:pointer' in rule and 'pointer-events:auto' in rule   # 整块透明区域可点
        assert 'animation' not in rule.replace('transition', '')          # 框不呼吸
        hover = src.split(cls + ':hover{', 1)[1].split('}', 1)[0]
        assert 'border-style:solid' in hover and 'background:rgba(251,191,36,.30)' in hover and 'box-shadow:0 0 0 3px' in hover
        tag_rule = src.split(tag + '{', 1)[1].split('}', 1)[0]
        assert 'left:-2px;top:-2px;transform:translateY(-100%)' in tag_rule and 'border-radius:6px 6px 6px 0' in tag_rule
        assert 'background:var(--g-fill)' in tag_rule and 'color:var(--g-ink)' in tag_rule and 'pointer-events:none' in tag_rule
        assert 'animation:' + kf + ' 1.8s ease-in-out infinite' in tag_rule and 'animation-delay:var(--g-delay,0s)' in tag_rule   # 只有标签呼吸
        assert '@keyframes ' + kf + '{' in src
        # 固定浅色：引导是页面内容叠加层，颜色跟随（浅色的）原型页面而非系统深色；废弃色不再出现
        assert src.count('prefers-color-scheme:dark') == (3 if '.__review_pop' in src else 0)
        assert '#f0a35e' not in src and 'rgba(180,83,9' not in src
        assert '#b45309' not in rule and '#b45309' not in tag_rule   # 废弃色只允许出现在注释里说明偏离理由
        assert 'rgba(37,99,235' not in rule and 'rgba(29,78,216' not in tag_rule   # 不是蓝色系
        assert "classList.toggle('" + below + "', top < 24)" in src and "classList.toggle('" + end + "', left + 84 > " in src
        # 几何同算法：外扩 4px、最小 22px、裁视口
        assert 'const pad = 4, w = Math.max(r.width + pad * 2, 22), h = Math.max(r.height + pad * 2, 22);' in src
        assert 'if (right - left < 8 || bottom - top < 8) return;' in src
        # 多个引导错峰呼吸：新建时写负 --g-delay
        assert "style.setProperty('--g-delay', (-(gi++ % 4) * 0.45) + 's')" in src
    # 按触发器复用节点（不再每次重排整体重建：重建会打断悬停态与呼吸，按下/抬起落在新旧节点上 click 丢失）
    guides = annotate.split('function layoutGuides()', 1)[1].split('function startDrag(', 1)[0]
    assert ".forEach((g) => g.remove())" not in guides
    assert 'existing.find((m) => m.__paTrig === trig)' in guides and 'existing.forEach((m) => { if (!alive.has(m)) m.remove(); });' in guides
    assert 'existing.find(x => x.__rvTrig === trig)' in pins and 'existing.forEach(x => { if (!alive.has(x)) x.remove(); });' in pins
    assert "glayer.setAttribute('data-prototype-owned', '')" in pins and 'glayer.appendChild(guide)' in pins
    # 点击绑在整个 <button> 框上（不只标签），透明区域同样可点；标签由 revealHint 动态给出（展开 / 选择值 / 切换 Tab 等）
    assert 'marker.onclick = async (e) => { e.stopPropagation(); await revealThrough(marker.__paTarget); scheduleLayout(); }' in annotate
    assert 'await window.ProtoAnchors.revealAndWait(guide.__rvTarget)' in pins
    assert '<span class="pa-guide-tag">${ICON}<span>${g.label} · ${g.notes.length}</span></span>' in annotate
    assert '<span class="__review_guide_tag">\' + GICON + \'<span>\' + g.label + \' · \' + g.notes.length + \'</span></span>' in pins


def test_reveal_click_passes_through_annotate_capture():
    """标注模式下 onClick 捕获拦截所有非自有点击：reveal 合成的 trig.click() 必须放行，
    否则点引导框 / 序号定位展不开折叠，反而弹出新建标注输入卡。"""
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    assert 'let revealing = 0;' in annotate
    assert 'revealing++;' in annotate and 'return await (ProtoAnchors.revealAndWait?.(target) ?? ProtoAnchors.reveal?.(target))' in annotate and 'finally { revealing--; }' in annotate
    on_click = annotate.split('function onClick(e) {', 1)[1].split('\n    }', 1)[0]
    assert on_click.lstrip().startswith('if (revealing || owned(e.target)) return;')
    # 所有 reveal 调用都走 revealThrough（引导框点击 + flashNote 定位）
    assert 'ProtoAnchors.reveal(' not in annotate and annotate.count('ProtoAnchors.reveal?.(') == 1
    assert 'await revealThrough(note.anchor);' in annotate


def test_pick_preview_number_stays_visible_before_and_after_click():
    """添加标注的预览序号必须稳定：DOM 重排不隐藏；点击后即使输入卡打开、鼠标移入卡内也冻结在落点旁。"""
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    assert 'function ensureHoverBox()' in annotate and 'function showPreviewNumber(x, y)' in annotate
    # 点击前：普通 mousemove 更新序号；点击后：pending/inputCard 分支直接 return，不能执行 hideHover
    on_move = annotate.split('function onMouseMove(e) {', 1)[1].split('\n    }', 1)[0]
    assert 'if (!active || drag || saving) { hideHover(); return; }' in on_move
    assert 'if (pending || inputCard) return;' in on_move
    assert 'if (pending || inputCard) { hideHover(); return; }' not in on_move
    assert 'showPreviewNumber(e.clientX, e.clientY);' in on_move
    # 点击后即便此前没有 hoverBox，也主动创建并显示；关闭输入卡才隐藏
    open_card = annotate.split('function openInputCard(x, y) {', 1)[1].split('function makeCard()', 1)[0]
    assert 'showPreviewNumber(x, y);' in open_card
    assert 'if (hoverBox)' not in open_card
    close_card = annotate.split('function closeInputCard(', 1)[1].split('function selectNote(', 1)[0]
    assert 'hideHover();' in close_card
    # DOM mutation / hover 动画重排不得无条件隐藏预览序号
    schedule = annotate.split('function scheduleLayout() {', 1)[1].split('\n    }', 1)[0]
    assert 'hideHover();' not in schedule


def test_conditional_visibility_guidance_is_generic():
    """条件显现引导不是项目特判：锚点保存通用状态路径，工作台/评审壳共用 revealHint 与 reveal。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    # 自动采集原生条件控件 + 常见 ARIA 状态；自定义控件有显式 data-proto-reveal-* 协议兜底
    assert 'function captureConditions(target, targetRect)' in anchors
    assert 'select,input[type="checkbox"],input[type="radio"]' in anchors
    assert '[role="tab"][aria-selected="true"]' in anchors
    assert '[aria-pressed="true"]' in anchors and '[aria-expanded="true"][aria-controls]' in anchors
    assert "getAttribute?.('data-proto-reveal-by')" in anchors
    assert "getAttribute('data-proto-reveal-value')" in anchors and "getAttribute('data-proto-reveal-label')" in anchors
    assert 'if (conditions.length) anchor.conditions = conditions;' in anchors
    # 解析为统一 hint（触发器 / 目标 / 动作文案），点击恢复状态并派发标准 input/change；ARIA 走 click
    assert 'function revealHint(anchor, el = resolveHidden(anchor))' in anchors
    assert "label: condition.label, kind: 'condition'" in anchors
    assert "element.dispatchEvent(new Event('input', { bubbles: true }))" in anchors
    assert "element.dispatchEvent(new Event('change', { bubbles: true }))" in anchors
    assert 'else { element.click(); return true; }' in anchors
    # 编辑态 / 导出态均消费同一 revealHint 与动态 label；条件目标被移出 DOM 也不要求先有 el
    assert 'ProtoAnchors.revealHint?.(note.anchor, el)' in annotate
    assert 'window.ProtoAnchors.revealHint?.(n.anchor, el)' in pins
    assert "label: '展开', kind: 'disclosure'" in annotate and "label: '展开', kind: 'disclosure'" in pins
    assert '${g.label} · ${g.notes.length}' in annotate
    assert "g.label + ' · ' + g.notes.length" in pins
    # 新落点保存 rx/ry；旧落点在控件响应式缩小时用 anchor.rect 比例回退，不因绝对 x 越界误判失锚
    placement = anchors.split('function placement(', 1)[1].split('function point(', 1)[0]
    point = anchors.split('function point(', 1)[1].split('function inBox(', 1)[0]
    assert 'rx:' in placement and 'ry:' in placement
    assert 'if (Number.isFinite(p.rx) && Number.isFinite(p.ry))' in point
    assert 'px / base.width * ew' in point and 'py / base.height * eh' in point
    # 目标已经显现时不再继续显示条件引导
    reveal_hint = anchors.split('function revealHint(', 1)[1].split('function reveal(', 1)[0]
    assert 'if (el && !hidden(el)) return null;' in reveal_hint


def test_sidebar_number_grey_only_when_anchor_truly_lost():
    """右栏序号灰显收窄为「真失锚」：页面上被折叠/隐藏（元素还在、可联动展开）的正常颜色，可点击定位。"""
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 工作台：隐藏元素、或目标当前被动态移出 DOM 但有显现路径的都按存活处理；可见但落点失效才灰
    alive = viewer.split('function extAnchorAlive(note) {', 1)[1].split('\n        }', 1)[0]
    assert 'A.point(note).point) return true' in alive and 'A.resolveHidden?.(note.anchor)' in alive
    assert 'if (el && A.hidden?.(el)) return true;' in alive
    assert 'return !el && !!A.revealHint?.(note.anchor, null);' in alive
    # 评审壳页面：无落点分流——隐藏/条件目标不进 stale；只有元素真找不到且无显现路径、或可见但落点失效才灰
    assert 'for (const n of noPoint) {' in pins
    assert 'window.ProtoAnchors.revealHint?.(n.anchor, el)' in pins
    assert "if (!el || !window.ProtoAnchors.hidden(el)) stale.push(n.id);" in pins
    # 灰显样式仍只为真失锚服务（未删除）
    assert '.note.stale .note-no { background: var(--muted); }' in shell
    assert '.ext-note-no.stale { background: var(--ext-muted); }' in viewer


def test_external_publish_entry_and_modal_markup():
    """本地原型卡片有发布入口；发布弹窗含纯净版/研发版双选与导出/发布两区。"""
    index = (SRC / 'index.html').read_text(encoding='utf-8')
    script = (SRC / 'script.js').read_text(encoding='utf-8')
    # 卡片操作条发布按钮（位于预览与移出列表之间）
    assert "HomeUI.action('publish'," in script and 'openExtPublishModal(item)' in script
    # 弹窗：两版 radio + 本地导出区 + GitHub 发布区 + 取消发布
    modal = index.split('id="extPublishModal"', 1)[1]
    assert 'name="extPubMode"' in modal and 'value="pure"' in modal and 'value="review"' in modal
    assert 'id="extLocalExportBtn"' in modal and 'id="extPubPublishBtn"' in modal
    assert 'id="extPubPublishedUrl"' in modal and 'id="extPubUnpublishBtn"' in modal
    # 导出下载按版本发起；发布携带版本；两类项目取消发布共用确认弹窗与同一实现
    assert '/api/ext/export?extId=' in script
    assert 'body: JSON.stringify({ extId: currentExtPubId, mode: currentExtPubMode })' in script
    assert re.search(r'async function executeGitHubUnpublish\(\)\s*\{\s*await executeExtGithubUnpublish\(\);', script)
    assert "body: JSON.stringify({ extId: currentExtPubId })" in script and '/api/ext/unpublish' in script


def test_local_add_panel_collapsed_behind_header_button():
    """本地原型操作区默认收起为 header 右上角小按钮，成功添加后自动收起。"""
    index = (SRC / 'index.html').read_text(encoding='utf-8')
    script = (SRC / 'script.js').read_text(encoding='utf-8')
    # header 右上角小按钮 + 操作区整体包进默认隐藏的 panel
    assert 'id="extAddPanelToggle"' in index and 'aria-controls="externalAddPanel"' in index
    assert 'id="externalAddPanel" class="hidden"' in index
    panel = index.split('id="externalAddPanel"', 1)[1]
    assert 'id="externalPickBtn"' in panel and 'id="extAddToggleBtn"' in panel
    # 开合/收起辅助与成功添加后自动收起
    assert 'function toggleExternalAddPanel' in script and 'function collapseExternalAddPanel' in script
    assert 'collapseExternalAddPanel();' in script
    # 选择文件夹失败回退手动输入时级联展开 panel
    assert "externalAddPanel').classList.remove('hidden')" in script


def test_shortcut_card_two_rows_with_persistent_actions():
    """快捷键设置卡：查看态显当前键+修改/恢复默认；录制态三按钮常驻+实时回显。"""
    # 卡片在导航行下方独占展开区，不再是行内 inline 串
    assert 'id="extShortcutCard" class="ext-shortcut-card hidden"' in VIEWER
    assert 'extShortcutCluster' not in VIEWER
    # 查看态：当前快捷键 + 修改 + 恢复默认
    view = VIEWER.split('id="extShortcutView"', 1)[1].split('</div>', 1)[0]
    assert 'id="extShortcutNow"' in view and 'id="extShortcutModify"' in view and 'id="extShortcutReset"' in view
    # 录制态：确定/恢复默认/取消三按钮常驻 markup（无 hidden），确定初始仅 disabled
    edit = VIEWER.split('id="extShortcutEdit"', 1)[1].split('</div>', 1)[0]
    assert 'id="extShortcutApply"' in edit and 'id="extShortcutResetEdit"' in edit and 'id="extShortcutCancel"' in edit
    assert '<button id="extShortcutApply" type="button" class="ext-shortcut-primary" disabled>确定</button>' in VIEWER
    # 实时回显：纯修饰键回显进行中组合，无修饰键组合给出提示
    assert "parts.join('+') + '+…'" in VIEWER and 'is-invalid' in VIEWER
    # 取消/关闭卡片/两个恢复默认统一走 exitRecording/doReset
    assert 'cancel.onclick = () => exitRecording();' in VIEWER
    assert 'extExitShortcutRecording?.()' in VIEWER
    assert 'resetEdit.onclick = doReset;' in VIEWER


def test_shortcut_and_draft_escape_do_not_intercept_business_input():
    annotation_harness("""
const event=over=>({key:'A',code:'KeyA',altKey:true,shiftKey:true,target:{closest:()=>false},preventDefault(){},stopPropagation(){},...over});
testAPI.onKeyDown(event()); assert.deepEqual(calls,[['toggle']]);
for(const guard of [{repeat:true},{isComposing:true},{keyCode:229},{ctrlKey:true},{target:{closest:()=>true}}]) testAPI.onKeyDown(event(guard));
assert.equal(calls.length,1);
const target={closest:selector=>selector==='[data-prototype-owned]'?{}:{}};
const card={remove(){calls.push(['remove'])}};
testState({active:true,pending:{x:5,y:10,scopeKey:'page-a'},inputCard:card});
testAPI.onKeyDown(event({key:'Escape',code:'Escape',target}));
assert.deepEqual(calls.slice(-2),[['suspend',card],['remove']]);
assert.ok(window.ProtoAnnotate.isActive());
testAPI.onKeyDown(event({key:'Escape',code:'Escape'})); assert.ok(!window.ProtoAnnotate.isActive());
let intercepted=false;
testState({active:false,selectedId:'note-1'});
testAPI.onClick({target:{closest:()=>false},preventDefault(){intercepted=true;}});
assert.equal(intercepted,false); assert.deepEqual(calls.at(-1),['clear']);
""")


def test_card_uses_visible_viewport_and_avoids_pin():
    annotation_harness("""
// 276 宽视口下卡被 CSS max-width:calc(100% - 24px) 钳到 252，fake 卡无 CSS，直接写死钳后宽
const card={offsetWidth:252,offsetHeight:166,style:{}};
testState({inputCard:card}); testAPI.placeCard(156,246);
assert.equal(parseFloat(card.style.left),12);
assert.ok(parseFloat(card.style.left)+card.offsetWidth <= document.documentElement.clientWidth-12);
assert.ok(parseFloat(card.style.top)>246);
testAPI.placeCard(268,592);
assert.ok(parseFloat(card.style.top)+card.offsetHeight<=592);
document.documentElement.clientWidth=390;
card.offsetWidth=340; testAPI.placeCard(384,300);
assert.ok(parseFloat(card.style.left)+card.offsetWidth<=378);
""")


def test_drag_threshold_cancel_and_drop_persistence():
    annotation_harness("""
(async()=>{
global.ProtoAnchors={at:()=>({}),serialize:()=>({protoId:'drop'}),placement:(_,x,y)=>({kind:'element',x,y})};
const pin={style:{left:'80px',top:'160px'},offsetWidth:36,focus(){},
    classList:{add(){},remove(){}},setPointerCapture(){},hasPointerCapture(){return false;},
    setAttribute(){},removeAttribute(){}};
const event=(x,y)=>({button:0,pointerId:1,clientX:x,clientY:y,stopPropagation(){},preventDefault(){}});
testState({active:false});
testAPI.startDrag(event(90,145),'note-1',pin);
testAPI.moveDrag(event(92,147)); await testAPI.endDrag(event(92,147));
assert.equal(calls.length,0);
testAPI.startDrag(event(90,145),'note-1',pin);
testAPI.moveDrag(event(140,185)); await testAPI.endDrag(event(140,185));
assert.deepEqual(calls,[['move','note-1',{protoId:'drop'},{kind:'element',x:130,y:200}]]);
testAPI.startDrag(event(140,185),'note-1',pin);
testAPI.moveDrag(event(170,200)); testAPI.cancelDrag();
await testAPI.endDrag(event(170,200)); assert.equal(calls.length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_document_and_note_saves_are_serialized():
    start = VIEWER.index('        function protoSave(')
    end = VIEWER.index('        // ---------- iframe', start)
    node("""
const assert=require('node:assert/strict');
let extSaveQueue=Promise.resolve(), extBundle={revision:4,prd:{annotations:[]}}, extId='fixture';
let extSelectedNoteId=null, requests=[], persisted=4;
const extRenderPins=()=>{},extRefreshSidebar=()=>{},showToast=()=>{};
const showAppAlert=()=>Promise.resolve(),loadProto=()=>{};
const fetch=async(_,options)=>{
    const request=JSON.parse(options.body); requests.push(request.expectedRevision);
    assert.equal(request.expectedRevision,persisted);
    await new Promise(r=>setTimeout(r,5));
    request.bundle.revision=++persisted;
    return {status:200,json:async()=>({ok:true,bundle:request.bundle})};
};
""" + VIEWER[start:end] + """
(async()=>{
const outcomes=await Promise.all([
    protoSave(d=>d.prd.annotations.push({id:'a'})),
    protoSave(d=>d.prd.document='draft'),
    protoSave(d=>d.prd.annotations.push({id:'b'}))
]);
assert.deepEqual(outcomes,[true,true,true]); assert.deepEqual(requests,[4,5,6]);
assert.equal(extBundle.revision,7); assert.equal(extBundle.prd.annotations.length,2);
assert.equal(extBundle.prd.document,'draft');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_annotation_card_dark_scrollbar_no_horizontal():
    scroll = re.search(r'\.pa-card-scroll\{[^}]*\}', ANNOTATE).group(0)
    assert 'overflow:auto' not in scroll and 'overflow-x:hidden' in scroll, '卡片不得再开横向滚动'
    assert 'overflow-y:auto' in scroll, '纵向滚动保留（内容超高时在滚动区内滚）'
    for token in ['scrollbar-width:thin', 'scrollbar-color:var(--pa-scroll) transparent',
                  '.pa-card::-webkit-scrollbar', '.pa-card *::-webkit-scrollbar',
                  '::-webkit-scrollbar-thumb{background:var(--pa-scroll)',
                  '.pa-card-text img']:
        assert token in ANNOTATE, token


def test_ext_publish_setup_modal_markup_present():
    for token in ['id="extGithubSetupModal"', 'id="extSetupUsername"', 'id="extSetupRepo"',
                  'id="extSetupToken"', 'id="extGithubTestResult"', 'id="extPublishSetupBtn"',
                  'id="extTestConnBtn"', 'id="extSaveGithubBtn"',
                  'onclick="extOpenGithubSetup()"', 'onclick="extPublishEntry()"']:
        assert token in VIEWER, token
    assert 'needGithubConfig' in VIEWER, '发布/取消失败须识别 needGithubConfig 转配置引导'


def test_compact_mode_btn_no_wrap_publish_label():
    """悬浮工具栏按钮（含「发布到 GitHub Pages」）禁折行：面板宽度随内容自适应，文案必须一行。"""
    rule = VIEWER.split('.compact-mode-btn {', 1)[1].split('}', 1)[0]
    assert 'white-space: nowrap' in rule
    assert '<span>发布到 GitHub Pages</span>' in VIEWER


def test_ext_publish_gate_routes_entry_and_toggles_panel():
    start = VIEWER.index("        let extPublishUrl = '';")
    end = VIEWER.index('        async function extRefreshPublishStatus()', start)
    node("""
const assert=require('node:assert/strict');
const els={}, calls=[];
const $=(id)=>els[id]||(els[id]={value:'',placeholder:'',textContent:'',style:{},
    classList:{_s:new Set(),add(c){this._s.add(c);},remove(c){this._s.delete(c);},contains(c){return this._s.has(c);}}});
let configResponse={success:true,hasToken:true,username:'u',repo:'r'};
const fetch=async()=>({json:async()=>configResponse});
const showToast=()=>{};
function extPublish(){calls.push('publish');}
""" + VIEWER[start:end] + """
(async()=>{
    await extRefreshGithubGate();
    assert.equal(extGithubReady,true);
    assert.deepEqual([els.extPublishBtn.style.display,els.extPublishRepo.style.display],['','']);
    assert.equal(els.extPublishRepo.textContent,'u/r');
    assert.deepEqual([els.extPublishHint.style.display,els.extPublishSetupBtn.style.display],['none','none']);
    extPublishEntry();
    assert.deepEqual(calls,['publish'],'已配置时点入口必须直接发布');
    configResponse={success:true,hasToken:false,username:'',repo:'r'};
    await extRefreshGithubGate();
    assert.equal(extGithubReady,false);
    assert.deepEqual([els.extPublishBtn.style.display,els.extPublishRepo.style.display],['none','none']);
    assert.deepEqual([els.extPublishHint.style.display,els.extPublishSetupBtn.style.display],['','']);
    calls.length=0; extPublishEntry();
    assert.deepEqual(calls,[],'未配置时不得触发发布');
    await new Promise(r=>setTimeout(r,0));
    assert.ok(els.extGithubSetupModal.classList.contains('flex'),'未配置时必须打开配置引导弹窗');
    configResponse={success:true,hasToken:false,tokenState:'unreadable',username:'u',repo:'r'};
    await extRefreshGithubGate();
    assert.match(els.extPublishHintText.textContent,/已保存的 Token 无法读取/,'解密失败不能误报 Token 消失');
    configResponse={success:true,hasToken:true,username:'',repo:'r'};
    await extRefreshGithubGate();
    assert.equal(els.extPublishHintText.textContent,'请补充 GitHub 用户名');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_hidden_reveal_guidance_rejects_unrelated_buttons_and_remembers_failures():
    """隐藏元素不能把同容器内的“导出/新建”误认成展开入口；弱推断须同时满足结构相邻与展开语义，失败后两层都收起假引导。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    pins = (SRC / 'review-pins.js').read_text(encoding='utf-8')
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    start = anchors.index('    const failedRevealTriggers = ')
    end = anchors.index('    function revealHint(', start)
    trigger_logic = anchors[start:end]
    out = node("""
const assert = require('assert');
const owned = () => false;
const visible = () => true;
const hidden = (el) => !!el?.isHidden;
const text = (el) => el?.label || '';
const body = { tagName: 'BODY' }, root = { tagName: 'HTML' };
const document = { body, documentElement: root, querySelectorAll: () => [] };
function el(tag, label = '', attrs = {}) {
  return {
    tagName: tag, label, attrs, parentElement: null, previousElementSibling: null, nextElementSibling: null,
    id: '', isHidden: false, open: false,
    getAttribute(name) { return this.attrs[name] ?? null; },
    contains(other) { for (let n = other; n; n = n.parentElement) if (n === this) return true; return false; },
    querySelectorAll() { return this.candidates || []; }
  };
}
function wire(parent, children) {
  children.forEach((child, i) => {
    child.parentElement = parent;
    child.previousElementSibling = children[i - 1] || null;
    child.nextElementSibling = children[i + 1] || null;
  });
}
""" + trigger_logic + """
const main = el('MAIN'); main.parentElement = body;
const toolbar = el('DIV'), table = el('TABLE'), target = el('DIV'); target.isHidden = true;
const exportBtn = el('BUTTON', '导出'); exportBtn.parentElement = toolbar;
wire(main, [toolbar, table, target]); main.candidates = [exportBtn];
assert.equal(revealTrigger(target), null, '不得把 demo 中不相邻且无展开语义的导出按钮当触发器');

const bar = el('DIV'), expandBtn = el('BUTTON', '展开详情'); expandBtn.parentElement = bar;
wire(main, [bar, target]); main.candidates = [expandBtn];
assert.equal(revealTrigger(target), expandBtn, '相邻分支内有明确展开语义的旧按钮仍兼容');
markRevealFailed(target, expandBtn);
assert.equal(revealTrigger(target), null, '点击后仍未显现的关联必须被记为无效');

const ariaBar = el('DIV'), ariaBtn = el('BUTTON', ''); ariaBtn.attrs['aria-expanded'] = 'false'; ariaBtn.parentElement = ariaBar;
wire(main, [ariaBar, target]); main.candidates = [ariaBtn];
assert.equal(revealTrigger(target), ariaBtn, '相邻 aria-expanded 折叠控件保持可用');
console.log('ok');
""")
    assert out.strip() == 'ok'
    assert "new CustomEvent('proto-anchors:reveal-failed'" in anchors
    assert "document.addEventListener('proto-anchors:reveal-failed'" in annotate
    assert "document.addEventListener('proto-anchors:reveal-failed', layout)" in pins
    assert 'pendingReveal = !!ProtoAnchors.revealHint?.(note.anchor, hiddenEl);' in annotate
    assert 'return !!found.point;' in annotate
    assert 'const focused = await pa?.flashNote(noteId);' in viewer and 'if (focused === false && note)' in viewer
    assert "revealFailed() { showToast('该标注对应元素当前隐藏，页面没有可用的展开入口'" in viewer


def test_anchor_text_identity_tolerates_dynamic_container_text():
    """容器锚点（整块筛选区 / 面板）innerText 随条件行显隐而变，逐字比对会把全部序号判成「目标变化」并隐藏；
    短文本仍逐字，长文本按字符二元组包含率容错；裸 id 选择器跳过文本校验；同值条件只作兜底不抢引导。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    head = anchors.split('const text = ', 1)[1].split('const visible = ', 1)[0]
    out = node("""
const assert = require('assert');
const text = """ + head + """
const el = (t) => ({ innerText: t });
const long = '筛选 智批来源： 全部 智能体 状态： 全部 已完成 处理中 关键词： 请输入试卷名称 年级： 学科： 本页共 120 条记录 最近扫描时间 2026-09-24';
const changed = long + ' 选择智批题型： 请选择智批题型 小学 3 项';
assert.equal(sameText(el(long), changed), true, '长文本追加条件行仍视为同一目标');
assert.equal(sameText(el(long + ' 本页共 121 条记录'), long), true, '计数刷新不算目标变化');
assert.equal(sameText(el('保存'), '保存'), true);
assert.equal(sameText(el('保 存'), '保存'), true, '空白差异忽略');
assert.equal(sameText(el('保存'), '取消'), false, '短文本必须逐字相同');
assert.equal(sameText(el('导出本页数据到表格'), '导出全部数据到表格'), false, '短文本一字之差即不同');
assert.equal(sameText(el('完全不同的一段很长很长的文本内容用于对照测试用途'), long), false, '长文本内容不同不容错');
assert.equal(sameText(el('x'), ''), true, '锚点无文本时不校验');
assert.equal(idBound({ selector: '#zpControl' }), true);
assert.equal(idBound({ selector: '#a > div' }), false);
assert.equal(idBound({ selector: 'body > section:nth-of-type(1)' }), false);
console.log('ok');
""")
    assert out.strip() == 'ok'
    # 同值条件 fallback 带 satisfied 标记；revealHint 顺序：直接折叠触发器 → 未满足条件 → 弱触发器 → 已满足条件兜底
    assert 'fallback = { ...hit, satisfied: true };' in anchors
    hint = anchors.split('function revealHint(', 1)[1].split('function reveal(', 1)[0]
    assert hint.index('if (conditionHint && !condition.satisfied) return conditionHint;') < hint.index('revealTrigger(el)')
    reveal = anchors.split('function reveal(', 1)[1].split('\n    }', 1)[0]
    assert 'if (condition && !condition.satisfied && !attempted.has(condition.element))' in reveal
    assert "condition?.satisfied && !attempted.has(condition.element)" in reveal
    assert 'return !el || hidden(el) ? null : el;' in reveal


def test_point_clamps_into_clip_when_cut_side_unreachable_by_scroll():
    """落点落在元素被裁掉的一侧时按「能否滚出来」分流：视口比元素窄（flex 居中的手机壳左缘 x<0）、overflow:hidden、
    滚到尽头 → 滚不出来，落点夹回可见区边缘仍显示；滚动容器里被滚出去的 → 滚得出来，照旧隐藏等用户滚回来。
    否则整宽元素 rx=0 的序号（proto_import 默认左侧中点）在窄视口里永远不出现。"""
    anchors = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
    rect_fn = anchors.split('function rect(', 1)[1].split('function placement(', 1)[0]
    point_fn = anchors.split('function point(', 1)[1].split('function inBox(', 1)[0]
    assert 'reach' in rect_fn and "scrollable(n, axis)" in rect_fn
    assert 'if (x < clip.x && !clip.reach.left) x = clip.x;' in point_fn
    assert 'if (y < clip.y && !clip.reach.top) y = clip.y;' in point_fn
    sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright
    html = """<!doctype html><html><head><style>
      body{margin:0;display:flex;justify-content:center;padding:0}
      .phone{width:400px;flex-shrink:0;overflow:hidden}
      .content{height:200px;overflow-y:auto;overflow-x:hidden}
      .block{height:150px}
    </style></head><body><div class="phone"><div class="content">
      <div class="block" data-proto-id="a">A</div><div class="block" data-proto-id="b">B</div><div class="block" data-proto-id="c">C</div>
    </div></div></body></html>"""
    note = lambda pid, ry: {'anchor': {'protoId': pid, 'tag': 'div'}, 'placement': {'kind': 'element', 'x': 0, 'y': 0, 'rx': 0, 'ry': ry}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 360, 'height': 600})   # 视口 360 < 手机壳 400：左缘在 x=-20
        page.set_content(html)
        page.add_script_tag(content=anchors)
        res = page.evaluate("""([a, b]) => {
            const r1 = ProtoAnchors.point(a);                       // 左缘被视口裁掉且 scrollX=0 滚不出来 → 夹到 0 仍可见
            document.querySelector('.content').scrollTop = 120;      // A 的中点(75)滚到容器顶之上，往回滚得出来 → 隐藏
            const r2 = ProtoAnchors.point(a);
            const r3 = ProtoAnchors.point(b);                        // B 可见部分：左缘仍夹回 0
            return [r1.point, r2.point, r3.point, r1.rect.reach];
        }""", [note('a', 0.5), note('b', 0.5)])
        browser.close()
    r1, r2, r3, reach = res
    assert r1['visible'] is True and r1['x'] == 0, r1
    assert reach['left'] is False and reach['top'] is True
    assert r2['visible'] is False, r2
    assert r3['visible'] is True and r3['x'] == 0, r3


def test_markdown_block_commands_color_table_and_card_in_parent():
    """第四轮：卡与工具条挂父页（手机壳外可拖）、块命令只改光标行、正文/色板/表格网格与行列操作、Esc 只关弹层、重开保位。"""
    annotate = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
    md = (SRC / 'proto-markdown.js').read_text(encoding='utf-8')
    editor = (SRC / 'markdown-editor.js').read_text(encoding='utf-8')
    css = (SRC / 'proto-markdown.css').read_text(encoding='utf-8')
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    # 气泡卡挂父页图层：小屏壳内不再折行 / 挤压，拖柄可把卡拖到壳外
    assert 'function cardDoc()' in annotate and 'function toCard(x, y)' in annotate
    assert "cardLayer.id = 'proto-annotate-cards'" in annotate
    # 双击转编辑会关卡再开：按标注 id 记住拖动偏移，重开沿用（拖出壳外的卡不被塞回默认位）
    assert 'let keptOffset = null;' in annotate
    assert 'if (card?.dataset?.noteId && cardOffset) keptOffset = { id: card.dataset.noteId, offset: cardOffset };' in annotate
    assert 'if (keptOffset?.id === id) cardOffset = keptOffset.offset;' in annotate
    # 工具条：正文 + 三级标题 + 文字颜色 + 无序/有序/任务列表 + 表格
    for name, label in [('p', '正文'), ('h1', '一级标题'), ('color', '文字颜色'), ('ul', '无序列表'), ('ol', '有序列表'), ('task', '任务列表'), ('table', '表格')]:
        assert f"['{name}', '{label}'" in md, name
    assert "const BLOCKS = ['p', 'h1', 'h2', 'h3', 'ul', 'ol', 'task'];" in md
    assert 'ProtoAppearance?.TEXT_COLORS' in md
    assert "const TABLE_OPS = [['row-above', '上方插行'], ['row-below', '下方插行'], ['row-del', '删除本行'], ['col-left', '左侧插列'], ['col-right', '右侧插列'], ['col-del', '删除本列'], ['table-del', '删除整个表格']];" in md
    assert 'const GRID_COLS = 8, GRID_ROWS = 6;' in md
    # 光标在表格内时表格按钮切为行列操作弹层；表格左上角角标共用同一弹层，弹层挂在按钮所在容器
    assert "if (s.state?.table) { tableOpsPop(s, btn); return; }" in md and "openPop(s, btn, 'table-ops'" in md and "openPop(s, btn, 'table-grid'" in md
    assert "const host = btn.closest('.proto-md-toolbar, .proto-md-handle') || s.toolbar;" in md
    assert 'function placeHandle(s)' in md and "box.className = 'proto-md-handle'" in md and "b.dataset.command = 'table-handle'" in md
    # 角标钉表格右上角（用户择定，左上角会压住表头首列起笔）；弹层从角标弹出时右对齐往左展开
    assert 's.handle.style.left = Math.round(fr.left + st.rect.left + st.rect.width - size / 2) + ' in md
    assert "if (fromHandle) { pop.style.left = 'auto'; pop.style.right = '0'; }" in md
    # 编辑器上报光标块类型（表内附表格几何）→ 点亮对应按钮、摆角标
    assert 'state(st) { if (session !== s) return; s.state = st; syncToolbar(s); placeHandle(s); }' in md
    assert "b.setAttribute('aria-pressed', String(st.block === name))" in md
    # 弹层 Esc：挂父页与编辑器 window 捕获并截断，只关弹层不取消整次编辑
    assert "fwin?.addEventListener('keydown', key, true)" in md
    assert 'e.stopImmediatePropagation(); closePop(s);' in md
    # 按钮按下不夺焦点：命令作用在编辑器当前行 / 选区
    assert "bar.addEventListener('pointerdown', e => { if (e.target.closest?.('button')) e.preventDefault(); });" in md
    # 渲染：只放行 <span style="color:…"> 一种内联 HTML
    assert 'COLOR_OPEN.test(t) || COLOR_CLOSE.test(t) ? t : `<code>${escape(t)}</code>`' in md
    assert "el.setAttribute('style', `color:${m[1].toLowerCase()}`)" in md
    # 编辑器：源码层按行改写（Enter 换出的新行不联动前一行），光标用零宽标记找回
    assert "const MARK = '\\u2063';" in editor
    for fn in ['function rewrite(', 'function setBlock(', 'function insertTable(', 'function tableOp(', 'function setColor(', 'function decorate()']:
        assert fn in editor, fn
    assert 'bridge.state(st)' in editor
    assert "st.rect = { left: Math.round(b.left), top: Math.round(b.top), width: Math.round(b.width), height: Math.round(b.height) };" in editor
    assert "if (name === 'table-del') {" in editor and 'out.splice(top, bottom - top + 1, MARK);' in editor
    assert "/^(row|col)-(above|below|left|right|del)$|^table-del$/" in editor
    assert '[data-type="code-block"], .vditor-ir__marker--pre' in editor
    # 样式：色标 HTML 节点隐藏、弹层 / 色板 / 网格存在
    assert '.proto-md-color-tag { display: none !important; }' in css
    assert '.proto-md-pop {' in css and '.proto-md-swatch {' in css and '.proto-md-grid {' in css
    assert '.proto-md-handle { position: fixed;' in css and '.proto-md-pop .proto-md-ops button[data-op="table-del"] { grid-column: 1 / -1; color: var(--md-error);' in css
    # 弹层挂在 22px 角标里：绝对定位收缩宽度受包含块限制，必须 max-content（实测不加会被压成一条、按钮叠成一团）；行 / 列操作各占一行
    pop_rule = css.split('.proto-md-pop {', 1)[1].split('}', 1)[0]
    assert 'width: max-content' in pop_rule
    assert '.proto-md-ops { display: grid; grid-template-columns: repeat(3, auto);' in css
    # 工作台“点空白收编辑”的白名单含表格角标（实测漏了会在点角标的 pointerdown 上直接收掉整次编辑）
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    assert ".proto-md-toolbar, .proto-md-handle, .ext-note-menu, .pa-card')" in viewer
    # 评审站：同口径放行颜色 span，暗色主题按值映射
    assert '&lt;span style=&quot;color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)&quot;&gt;' in shell
    assert '[style="color:#b42318"] { color: #ff8a8a !important; }' in shell
