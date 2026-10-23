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
