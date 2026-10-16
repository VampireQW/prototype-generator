"""隐藏目标的声明式路径：同步 / 异步多层显现、唯一定位及无副作用。"""
import json
import shutil
import subprocess
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / 'src/proto-anchors.js').read_text(encoding='utf-8')
ENV = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const mapping=new Map(),events=[],clicks=[];
class El {
 constructor(tag,attrs={},parent=null){this.tagName=tag;this.attrs=attrs;this.parentElement=parent;this.nodeType=1;this.isHidden=false;this.disabled=false;this.isConnected=true;this.textContent=attrs.text||'';this.dataset={};this.open=false;}
 get id(){return this.attrs.id||''} getAttribute(k){return this.attrs[k]??null} hasAttribute(k){return k in this.attrs}
 setAttribute(k,v){this.attrs[k]=v} closest(){return null}
 contains(other){for(let n=other;n;n=n.parentElement)if(n===this)return true;return false}
 getClientRects(){for(let n=this;n;n=n.parentElement)if(n.isHidden)return [];return [this.getBoundingClientRect()]}
 getBoundingClientRect(){return {left:50,top:80,right:170,bottom:120,width:120,height:40,x:50,y:80}}
 querySelectorAll(sel){return (mapping.get(sel)||[]).filter(n=>this.contains(n))}
 querySelector(sel){return this.querySelectorAll(sel)[0]||null}
 click(){clicks.push(this.id);this.onClick?.()}
 dispatchEvent(){}
}
const html=new El('HTML'),body=new El('BODY',{},html);
const tab=new El('DIV',{id:'tab-answer',text:'答题区切割'},body);
const pane=new El('DIV',{'data-proto-reveal-by':'#tab-answer','data-proto-reveal-label':'切换到答题区切割'},body);pane.isHidden=true;
const opener=new El('SPAN',{id:'open-group',text:'设置分组'},pane);
const group=new El('DIV',{'data-proto-reveal-by':'#open-group','data-proto-reveal-label':'打开设置分组'},pane);group.isHidden=true;
const target=new El('DIV',{'data-proto-id':'group-footer'},group);
mapping.set('#tab-answer',[tab]);mapping.set('#open-group',[opener]);mapping.set('[data-proto-id="group-footer"]',[target]);
tab.onClick=()=>{pane.isHidden=false};opener.onClick=()=>{group.isHidden=false};
const document={body,documentElement:html,querySelectorAll:sel=>mapping.get(sel)||[],querySelector:sel=>(mapping.get(sel)||[])[0]||null,dispatchEvent:event=>events.push(event)};
const context={document,CSS:{escape:s=>s},getComputedStyle:el=>({display:el.isHidden?'none':'block',visibility:'visible'}),setTimeout,clearTimeout,Date,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail}},Event:class{},innerWidth:800,innerHeight:600,scrollX:0,scrollY:0,console};
vm.createContext(context);vm.runInContext(SOURCE,context);const A=context.ProtoAnchors,anchor={protoId:'group-footer',tag:'div'};
'''


def run_case(code):
    result = subprocess.run([shutil.which('node') or r'D:\software\nodejs\node.exe', '-'], input=ENV.replace('SOURCE', json.dumps(SOURCE)) + code, encoding='utf-8', text=True, capture_output=True, timeout=12)
    assert result.returncode == 0, result.stderr


def test_hidden_imported_anchor_uses_live_outer_then_inner_declaration():
    run_case(r'''
const hint=A.revealHint(anchor);assert.equal(hint?.trigger,tab,'导入的旧锚点没有 conditions 时，也应读取页面显现声明');
tab.click();assert.equal(A.revealHint(anchor)?.trigger,opener,'外层显现后引导接力到设置分组');
opener.click();assert.equal(A.revealHint(anchor),null,'目标显现后移除引导');
''')


def test_reveal_executes_declared_safe_path_without_clicking_confirm():
    run_case(r'''
const result=A.reveal(anchor);assert.equal(result,target);assert.deepEqual(clicks,['tab-answer','open-group']);
assert.equal(A.hidden(target),false);A.reveal(anchor);assert.deepEqual(clicks,['tab-answer','open-group'],'已展开时不能重复打开或重置分组草稿');
''')


def test_async_path_waits_for_render_and_clicks_each_trigger_once():
    run_case(r'''
assert.equal(typeof A.revealAndWait,'function');
tab.onClick=()=>setTimeout(()=>{pane.isHidden=false},35);opener.onClick=()=>setTimeout(()=>{group.isHidden=false},35);
(async()=>{const [one,two]=await Promise.all([A.revealAndWait(anchor),A.revealAndWait(anchor)]);assert.equal(one,target);assert.equal(two,target);assert.deepEqual(clicks,['tab-answer','open-group']);assert.equal(events.length,0);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_ambiguous_or_disabled_declaration_never_clicks_arbitrary_control():
    run_case(r'''
mapping.set('#tab-answer',[tab,new El('DIV',{id:'duplicate'},body)]);assert.equal(A.revealHint(anchor),null);assert.equal(A.reveal(anchor),null);assert.deepEqual(clicks,[]);
mapping.set('#tab-answer',[tab]);tab.disabled=true;assert.equal(A.revealHint(anchor),null);assert.equal(A.reveal(anchor),null);assert.deepEqual(clicks,[]);
''')


def test_native_condition_is_restored_with_change_instead_of_toggle_click():
    run_case(r'''
tab.tagName='INPUT';tab.type='checkbox';tab.checked=false;
tab.dispatchEvent=()=>{pane.isHidden=false};
const result=A.reveal(anchor);assert.equal(result,target);assert.equal(tab.checked,true);assert.deepEqual(clicks,['open-group']);
''')


def test_live_path_precedes_stale_unrelated_captured_conditions():
    run_case(r'''
const unrelated=new El('INPUT',{id:'unrelated'},body);unrelated.type='checkbox';unrelated.checked=false;
mapping.set('#unrelated',[unrelated]);anchor.conditions=[{selector:'#unrelated',kind:'checkbox',value:true}];
assert.equal(A.reveal(anchor),target);assert.equal(unrelated.checked,false);assert.deepEqual(clicks,['tab-answer','open-group']);
''')


def test_failed_async_path_is_bounded_and_does_not_repeat_business_clicks():
    run_case(r'''
opener.onClick=()=>{};
(async()=>{const result=await A.revealAndWait(anchor);assert.equal(result,null);assert.deepEqual(clicks,['tab-answer','open-group']);assert.equal(events.length,1);assert.equal(events[0].type,'proto-anchors:reveal-failed');assert.equal(A.revealHint(anchor),null);})().catch(e=>{console.error(e);process.exitCode=1});
''')
