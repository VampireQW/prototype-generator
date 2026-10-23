"""导出浮窗移动及业务弹窗隐藏时的序号生命周期。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PINS = (Path(__file__).resolve().parents[1] / 'src/review-pins.js').read_text(encoding='utf-8')


ENV = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
class Events {
 constructor(){this.events=new Map()}
 addEventListener(type,fn){if(!this.events.has(type))this.events.set(type,new Set());this.events.get(type).add(fn)}
 removeEventListener(type,fn){this.events.get(type)?.delete(fn)}
 emit(type,props={}){const event={button:0,pointerId:1,preventDefault(){this.prevented=true},stopPropagation(){},stopImmediatePropagation(){},...props};for(const fn of [...(this.events.get(type)||[])])fn(event);return event}
}
class El extends Events {
 constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.style={};this.dataset={};this.parentElement=null;this.className='';this.offsetWidth=360;this.offsetHeight=200;
 this.classList={add:c=>{if(!this.className.split(' ').includes(c))this.className+=' '+c},remove:c=>this.className=this.className.split(' ').filter(x=>x!==c).join(' '),toggle(c,on){on?this.add(c):this.remove(c)}};}
 appendChild(el){el.parentElement=this;this.children.push(el);return el}
 replaceChildren(){for(const el of this.children)el.parentElement=null;this.children=[]}
 setAttribute(k,v){this.attrs[k]=String(v)}
 getAttribute(k){return this.attrs[k]??null}
 closest(sel){for(let el=this;el;el=el.parentElement)if(sel==='[data-prototype-owned]'&&'data-prototype-owned' in el.attrs||sel[0]==='.'&&el.className.split(' ').includes(sel.slice(1)))return el;return null}
 contains(el){return el===this||this.children.some(child=>child.contains(el))}
 matches(sel){return sel[0]==='.'&&this.className.split(' ').includes(sel.slice(1).split('[')[0])}
 querySelectorAll(sel){return this.children.flatMap(child=>[...(child.matches(sel)?[child]:[]),...child.querySelectorAll(sel)])}
 querySelector(sel){const id=sel.match(/data-note-id="([^"]+)"/);return this.querySelectorAll(sel).find(el=>!id||el.dataset.noteId===id[1])||null}
 getBoundingClientRect(){const left=parseFloat(this.style.left)||0,top=parseFloat(this.style.top)||0;return {left,top,width:this.offsetWidth,height:this.offsetHeight,right:left+this.offsetWidth,bottom:top+this.offsetHeight}}
 setPointerCapture(){this.capture=true}hasPointerCapture(){return !!this.capture}releasePointerCapture(){this.capture=false}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(el=>el!==this)}
}
const document=new Events();document.documentElement=new El('html');document.documentElement.dataset.protoState='default';document.documentElement.outerHTML='same length';document.head=new El('head');document.createElement=tag=>new El(tag);
const window=new Events(),frames=[],observers=[];let targetVisible=true;
const target=new El('th'),note={id:'n1',stateId:'default',body:'正文'};
window.__REVIEW__={notes:[note],asideOpen:()=>false,renderBody:()=>'<p>正文</p>',onSync(){}};
window.ProtoOrder={project:notes=>notes.map((n,i)=>({...n,displayNumber:i+1}))};
window.ProtoAnchors={point:()=>targetVisible?{point:{x:300,y:320,visible:true}}:{point:null},resolveHidden:()=>target,revealHint:()=>null,hidden:()=>!targetVisible,revealTrigger:()=>null};
const context={window,document,CSS:{escape:s=>s},innerWidth:800,innerHeight:600,scrollX:0,scrollY:0,
 requestAnimationFrame:fn=>{frames.push(fn);return frames.length},setInterval(){},setTimeout,
 MutationObserver:class {constructor(fn){this.fn=fn;observers.push(this)}observe(target,options){this.target=target;this.options=options}}};
vm.createContext(context);vm.runInContext(SOURCE,context);
const all=selector=>document.documentElement.querySelectorAll(selector),pins=()=>all('.__review_pin'),popup=()=>all('.__review_pop')[0];
const flush=()=>{let tries=0;while(frames.length){assert.ok(++tries<10,'不能被自有图层变动触发无限重排');frames.shift()()}};
const notify=records=>{for(const observer of observers)observer.fn(records);flush()};
pins()[0].onclick({preventDefault(){},stopPropagation(){}});
'''


def case(code):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行浮窗回归')
    result = subprocess.run([executable, '-'], input=ENV.replace('SOURCE', json.dumps(PINS)) + code,
                            text=True, encoding='utf-8', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_same_length_visibility_change_hides_pin_and_open_popup_then_restores_pin():
    case(r'''
assert.equal(pins().length,1);assert.equal(popup().style.display,'block');
assert.ok(observers.length,'应监听 DOM 显隐，而不是只比较 HTML 字符数');
targetVisible=false;notify([{target:new El(),attributeName:'hidden'}]);
assert.equal(pins().length,0);assert.equal(popup().style.display,'none');
targetVisible=true;notify([{target:new El(),attributeName:'hidden'}]);assert.equal(pins().length,1);
// 标注图层自身变化不能触发重建，避免拖动浮窗不断重排。
for(const observer of observers)observer.fn([{target:pins()[0],attributeName:'style'}]);assert.equal(frames.length,0);
assert.equal(window.__REVIEW__.notes[0],note);
''')


def test_popover_drag_keeps_identity_clamps_to_viewport_and_releases_listeners():
    case(r'''
const pop=popup(),grip=all('.__review_pop_grip')[0];assert.ok(grip,'浮窗需要可拖动握把');
const start=pop.getBoundingClientRect();grip.onpointerdown({button:0,pointerId:1,clientX:350,clientY:330,preventDefault(){},stopPropagation(){}});
window.emit('pointermove',{clientX:400,clientY:370});
assert.equal(parseFloat(pop.style.left),start.left+50);assert.equal(parseFloat(pop.style.top),start.top+40);
window.emit('pointermove',{clientX:2000,clientY:2000});
assert.equal(parseFloat(pop.style.left),432);assert.equal(parseFloat(pop.style.top),392);
window.emit('pointerup');assert.equal(window.events.get('pointermove').size,0);assert.equal(grip.capture,false);
assert.equal(window.__reviewPopNoteId(),'n1');assert.equal(pop.style.display,'block');assert.equal(pins().length,1);
const settled=pop.style.left;window.__reviewRelayout();assert.equal(pop.style.left,settled);
''')


@pytest.mark.parametrize('cancel', ['pointercancel', 'blur', 'escape'])
def test_cancelled_popover_move_restores_position_and_page_selection(cancel):
    case(r'''
const pop=popup(),grip=all('.__review_pop_grip')[0];assert.ok(grip);
document.documentElement.style.cursor='crosshair';document.documentElement.style.userSelect='text';
const left=pop.style.left,top=pop.style.top;
grip.onpointerdown({button:0,pointerId:1,clientX:350,clientY:330,preventDefault(){},stopPropagation(){}});
window.emit('pointermove',{clientX:400,clientY:370});
if(CANCEL==='escape')window.emit('keydown',{key:'Escape'});else window.emit(CANCEL);
assert.equal(pop.style.left,left);assert.equal(pop.style.top,top);
assert.equal(document.documentElement.style.cursor,'crosshair');assert.equal(document.documentElement.style.userSelect,'text');
assert.equal(window.events.get('pointermove').size,0);
'''.replace('CANCEL', json.dumps(cancel)))


def test_popover_grip_keyboard_moves_and_escape_closes():
    case(r'''
const pop=popup(),grip=all('.__review_pop_grip')[0];assert.ok(grip);const start=pop.getBoundingClientRect();
grip.emit('keydown',{key:'ArrowRight'});assert.equal(parseFloat(pop.style.left),start.left+10);
grip.emit('keydown',{key:'ArrowDown',shiftKey:true});assert.equal(parseFloat(pop.style.top),start.top+40);
grip.emit('keydown',{key:'Escape'});assert.equal(pop.style.display,'none');
''')


def test_selected_pin_persists_through_relayout_and_switches_by_annotation_id():
    case(r'''
const selected=()=>pins().filter(p=>p.className.split(' ').includes('__review_selected')).map(p=>p.dataset.noteId);
assert.deepEqual(selected(),['n1']);assert.equal(pins()[0].getAttribute('aria-current'),'true');
window.__REVIEW__.notes.push({id:'n2',stateId:'default',body:'第二条'});window.__reviewRelayout();
assert.deepEqual(selected(),['n1']);pins()[1].onclick({preventDefault(){},stopPropagation(){}});
assert.deepEqual(selected(),['n2']);window.__reviewRelayout();assert.deepEqual(selected(),['n2']);
assert.equal(pins()[0].getAttribute('aria-current'),'false');
// 右栏发来的选择按稳定 ID 应用；不把编号当身份。
window.__reviewSelectNote('n1');assert.deepEqual(selected(),['n1']);
window.__REVIEW__.notes=window.__REVIEW__.notes.filter(n=>n.id!=='n1');window.__reviewRelayout();assert.deepEqual(selected(),[]);
''')


def test_layout_between_pointer_press_and_release_keeps_pin_click_target():
    case(r'''
window.__reviewSelectNote(null);
window.__REVIEW__.asideOpen=()=>true;
const focused=[];window.__REVIEW__.onFocus=id=>focused.push(id);
const pressed=pins()[0],parent=pressed.parentElement;
// 鼠标按下后，业务 DOM 更新、滚动和尺寸变化都可能在松开前触发定位。
for(let i=0;i<3;i++)notify([{target:new El(),attributeName:'style'}]);
assert.equal(pressed.parentElement,parent,'按下期间不能移除序号，否则浏览器不会把松开合成为 click');
assert.equal(pins()[0],pressed,'定位只更新已有序号，不替换点击目标');
pressed.onclick({preventDefault(){},stopPropagation(){}});
assert.equal(pressed.getAttribute('aria-current'),'true');assert.deepEqual(focused,['n1']);
''')


def test_retained_pin_uses_updated_note_and_hidden_targets_are_removed():
    case(r'''
const retained=pins()[0];
window.__REVIEW__.notes=[{id:'n2',stateId:'default',body:'另一条'},{...note,body:'修改后的正文'}];
window.__reviewRelayout();
assert.equal(pins().find(p=>p.dataset.noteId==='n1'),retained);
assert.equal(retained.textContent,2,'保留节点仍须更新展示编号');
window.__REVIEW__.renderBody=n=>n.body;
// 初始浮窗已打开：先关闭，再单击同一节点查看最新正文。
retained.onclick({preventDefault(){},stopPropagation(){}});
retained.onclick({preventDefault(){},stopPropagation(){}});
assert.equal(all('.__review_pop_body')[0].innerHTML,'修改后的正文');
window.__REVIEW__.notes=window.__REVIEW__.notes.filter(n=>n.id==='n1');window.__reviewRelayout();
assert.equal(pins().length,1);assert.equal(pins()[0],retained);assert.equal(retained.textContent,1);
targetVisible=false;notify([{target:new El(),attributeName:'hidden'}]);
assert.equal(pins().length,0);assert.equal(popup().style.display,'none');
''')
