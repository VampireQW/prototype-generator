"""拖动 / 重绑保存的相对落点必须使用控件边框尺寸，不能被溢出文案放大。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'
ANCHORS = (SRC / 'proto-anchors.js').read_text(encoding='utf-8')
VIEWER = (SRC / 'viewer.html').read_text(encoding='utf-8')


def run_node(code):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行坐标回归')
    result = subprocess.run([executable, '-'], input=code, text=True,
                            encoding='utf-8', capture_output=True, timeout=12)
    assert result.returncode == 0, result.stderr


ENV = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const root={scrollWidth:800,scrollHeight:600},body={parentElement:root,scrollLeft:0,scrollTop:0};
root.getBoundingClientRect=body.getBoundingClientRect=()=>({left:0,top:0,right:800,bottom:600,width:800,height:600});
let bounds={left:100,top:120,width:118,height:36};
const el={tagName:'TH',id:'column',parentElement:body,scrollLeft:0,scrollTop:0,scrollWidth:217,scrollHeight:80,
 innerText:'允许不填?',textContent:'允许不填?',closest:()=>null,
 getAttribute:key=>key==='data-proto-id'?'column':null,
 getClientRects:()=>[el.getBoundingClientRect()],
 getBoundingClientRect:()=>({...bounds,x:bounds.left,y:bounds.top,right:bounds.left+bounds.width,bottom:bounds.top+bounds.height}),
 cloneNode:()=>({querySelectorAll:()=>[],outerHTML:'<th data-proto-id="column">允许不填?</th>'})};
const document={documentElement:root,body,scrollingElement:root,
 querySelectorAll:selector=>['[data-proto-id="column"]','#column'].includes(selector)?[el]:[],querySelector:()=>null};
const context={document,CSS:{escape:s=>s},getComputedStyle:()=>({display:'block',visibility:'visible',overflowX:'visible',overflowY:'visible'}),
 innerWidth:800,innerHeight:600,scrollX:0,scrollY:0};
vm.createContext(context);vm.runInContext(SOURCE,context);const A=context.ProtoAnchors;
const note={id:'note-1',number:10,body:'保留正文',anchor:A.serialize(el),placement:A.placement(el,190,130)};
const check=(note,x,y)=>{const found=A.point(note);assert.ok(found.point);assert.equal(found.point.visible,true);
 assert.ok(Math.abs(found.point.x-x)<.001,JSON.stringify(found));assert.ok(Math.abs(found.point.y-y)<.001,JSON.stringify(found));};
'''


def case(code):
    run_node(ENV.replace('SOURCE', json.dumps(ANCHORS)) + code)


def test_saved_relative_point_ignores_tooltip_and_visible_content_overflow():
    case(r'''
check(note,190,130);
el.scrollWidth=500;el.scrollHeight=400;check(note,190,130);
// 序列化再加载也应停在原处；无需迁移已有 placement。
check(JSON.parse(JSON.stringify(note)),190,130);
''')


def test_relative_point_follows_resizing_and_parent_scrolling():
    case(r'''
bounds={left:100,top:120,width:59,height:72};check(note,145,140);
bounds.top=40;check(note,145,60);
// Agent 导入的左侧中点仍使用控件的实际尺寸。
check({...note,placement:{kind:'element',x:0,y:0,rx:0,ry:.5}},100,76);
// 没有比例的旧数据仍保留绝对落点。
bounds={left:100,top:120,width:118,height:36};
check({...note,placement:{kind:'element',x:90,y:10}},190,130);
''')


def test_hidden_screen_ancestor_suppresses_pins_without_losing_anchor_or_placement():
    case(r'''
let screenHidden='true';body.getAttribute=key=>key==='aria-hidden'?screenHidden:null;
const saved=JSON.stringify(note);
assert.equal(el.getClientRects().length,1,'后台屏幕仍保留布局矩形');
assert.equal(A.visible(el),false,'aria-hidden 祖先中的目标不属于当前可见页面');
assert.equal(A.hidden(el),true);assert.equal(A.resolveHidden(note.anchor),el,'隐藏页面不是失锚');
assert.equal(A.point(note).point,null,'首页序号不能穿透覆盖在详情页上');
const attributes=el.getAttribute;el.getAttribute=key=>key==='aria-hidden'?'false':attributes(key);
assert.equal(A.visible(el),false,'子节点 aria-hidden=false 不可覆盖祖先的隐藏状态');
screenHidden='false';check(note,190,130);
assert.equal(JSON.stringify(note),saved,'切回首页无需改写已有标注或落点');
''')


def test_hidden_target_itself_is_suppressed_even_if_css_still_draws_it():
    case(r'''
const attributes=el.getAttribute;let aria='true';el.getAttribute=key=>key==='aria-hidden'?aria:attributes(key);
assert.equal(A.hidden(el),true);assert.equal(A.visible(el),false);assert.equal(A.point(note).point,null);
aria='false';check(note,190,130);
''')


def test_logical_projection_keeps_saved_relative_point_when_page_is_hidden():
    case(r'''
const saved=JSON.stringify(note);let aria='false';
body.getAttribute=key=>key==='aria-hidden'?aria:null;
const before=A.point(note,true).point;aria='true';
assert.equal(A.point(note).point,null,'显示层隐藏');
const logical=A.point(note,true).point;
assert.ok(logical,'排序仍使用保留布局的隐藏目标');
assert.equal(logical.x,before.x);assert.equal(logical.y,before.y,'不能退回容器左上角导致换号');
assert.equal(JSON.stringify(note),saved);
''')


@pytest.mark.parametrize('kind', ['hidden', 'inert', 'aria', 'display', 'opacity', 'content', 'visibility', 'collapse', 'dialog'])
def test_generic_hidden_page_states_preserve_and_restore_the_same_anchor(kind):
    case(r'''
const kind=KIND,attrs={},page={tagName:kind==='dialog'?'DIALOG':'SECTION',parentElement:body,scrollTop:0,scrollLeft:0,
 getAttribute:k=>attrs[k]??null,hasAttribute:k=>k in attrs,getBoundingClientRect:body.getBoundingClientRect,open:kind!=='dialog'};
el.parentElement=page;let active=false;
context.getComputedStyle=n=>({display:!active&&kind==='display'&&n===page?'none':'block',
 visibility:!active&&['visibility','collapse'].includes(kind)&&[page,el].includes(n)?kind==='collapse'?'collapse':'hidden':'visible',
 opacity:!active&&kind==='opacity'&&n===page?'0':'1',contentVisibility:!active&&kind==='content'&&n===page?'hidden':'visible',overflowX:'visible',overflowY:'visible'});
if(kind==='aria')attrs['aria-hidden']='true';
if(kind==='hidden'||kind==='inert')attrs[kind]='';
assert.equal(A.visible(el),false,kind+' 页面不应显示序号');assert.equal(A.hidden(el),true);
assert.equal(A.point(note).point,null);assert.equal(A.resolveHidden(note.anchor),el);
delete attrs.hidden;delete attrs.inert;delete attrs['aria-hidden'];page.open=true;active=true;
check(note,190,130);
'''.replace('KIND', json.dumps(kind)))


def test_visible_disabled_controls_and_css_visibility_override_remain_annotatable():
    case(r'''
el.disabled=true;
context.getComputedStyle=n=>({display:'block',visibility:n===body?'hidden':'visible',opacity:'.35',pointerEvents:'none',overflowX:'visible',overflowY:'visible'});
check(note,190,130,'禁用、半透明和 pointer-events:none 不能被猜成后台页面');
''')


def test_business_overlay_suppresses_covered_pin_but_owned_layers_do_not():
    case(r'''
el.contains=n=>n===el||n===child;
const child={parentElement:el,closest:()=>null,getClientRects:()=>[bounds],contains:()=>false};
const cover={parentElement:body,closest:()=>null,getClientRects:()=>[bounds],contains:()=>false};
const owned={closest:()=>({}),getClientRects:()=>[bounds],contains:()=>false};
document.elementsFromPoint=()=>[owned,cover,el];
let found=A.point(note);assert.ok(found.point,'被遮挡不等于失锚');assert.equal(found.point.visible,false,'底层序号不能浮到覆盖页面上');
assert.equal(A.hidden(el),false);assert.equal(A.point(note,true).point.visible,true,'逻辑坐标仍可用于编号排序');
document.elementsFromPoint=()=>[owned,child,el];check(note,190,130);
document.elementsFromPoint=()=>[];check(note,190,130,'非交互元素不能仅因无命中节点而消失');
''')


def test_nearby_visible_markers_are_separated_without_changing_saved_positions():
    case(r'''
const saved=JSON.stringify(note),occupied=[];
const points=[[100,150],[105,154],[103,149]];
const positions=points.map(([x,y])=>A.pinPosition(x,y,36,36,occupied,800,600));
assert.equal(positions[0].x,100);assert.equal(positions[0].y,150,'未冲突的落点保持原位');
for(let i=0;i<positions.length;i++)for(let j=i+1;j<positions.length;j++){
 const a=positions[i],b=positions[j];
 assert.ok(a.x+36<=b.x||b.x+36<=a.x||a.y<=b.y-36||b.y<=a.y-36,'相近序号不可互相遮挡');
}
assert.equal(JSON.stringify(note),saved);
const again=[];assert.deepEqual(points.map(([x,y])=>A.pinPosition(x,y,36,36,again,800,600)),positions,'重复重排不抖动');
''')


def test_marker_spacing_keeps_touch_targets_inside_narrow_viewport():
    case(r'''
const occupied=[];
for(let i=0;i<4;i++){
 const pos=A.pinPosition(370,20,44,44,occupied,375,600);
 assert.ok(pos.x>=4&&pos.x+44<=371);assert.ok(pos.y-44>=4&&pos.y<=596);
}
for(let i=0;i<occupied.length;i++)for(let j=i+1;j<occupied.length;j++){
 const a=occupied[i],b=occupied[j];assert.ok(a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top);
}
''')


def test_move_and_rebind_preserve_annotation_identity_body_and_count():
    methods = VIEWER[VIEWER.index('            rebindDone('):VIEWER.index('            deleteNote(')]
    case(r'''
const original=JSON.parse(JSON.stringify(note));original.color='#2563eb';original.anchor.revealSteps=[{selector:'#open',kind:'click',value:'true'}];
let stored={prd:{annotations:[original]}};
const hostContext={extCanChange:()=>true,protoSave:async update=>{const draft=JSON.parse(JSON.stringify(stored));update(draft);stored=draft;return true;}};
vm.createContext(hostContext);vm.runInContext('globalThis.host={'+METHODS+'}',hostContext);
(async()=>{
 for(const method of ['moveNote','rebindDone']){
  assert.equal(await hostContext.host[method](original.id,A.serialize(el),A.placement(el,190,130)),true);
  assert.equal(stored.prd.annotations.length,1);
  const saved=stored.prd.annotations[0];
  assert.equal(saved.id,original.id);assert.equal(saved.body,original.body);assert.equal(saved.number,10);assert.equal(saved.color,original.color);
  assert.equal(saved.anchor.revealSteps.length,1);check(saved,190,130);
 }
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('METHODS', json.dumps(methods)))
