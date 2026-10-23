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


def test_inspection_displays_full_automatic_path_even_when_target_is_visible_without_clicking():
    run_case(r'''
pane.isHidden=false;group.isHidden=false;
const result=A.inspectReveal(anchor);
assert.equal(result.state,'automatic');assert.equal(result.visible,true);
assert.deepEqual(Array.from(result.steps,s=>s.label),['切换到答题区切割','打开设置分组']);
assert.deepEqual(clicks,[],'查看识别结果不能操作业务页面');assert.equal(anchor.revealSteps,undefined);
group.isHidden=true;pane.isHidden=true;
assert.equal(A.inspectReveal(anchor).steps[1].status,'hidden','显示后续入口目前隐藏，而不是漏掉该步');
''')


def test_inspection_distinguishes_visible_static_target_missing_anchor_and_unknown_hidden_entry():
    run_case(r'''
delete pane.attrs['data-proto-reveal-by'];delete group.attrs['data-proto-reveal-by'];
pane.isHidden=false;group.isHidden=false;
assert.equal(A.inspectReveal(anchor).state,'visible');
group.attrs.role='dialog';assert.equal(A.inspectReveal(anchor).state,'needed','已显示的弹窗也需要说明缺少入口');
group.isHidden=true;assert.equal(A.inspectReveal(anchor).state,'needed');
mapping.set('[data-proto-id="group-footer"]',[]);assert.equal(A.inspectReveal(anchor).state,'missing');
assert.deepEqual(clicks,[]);
''')


def test_inspection_shows_shared_path_when_dialog_is_open_and_reports_conflicts():
    run_case(r'''
delete pane.attrs['data-proto-reveal-by'];delete group.attrs['data-proto-reveal-by'];
pane.isHidden=false;group.isHidden=false;group.attrs.role='dialog';
const second=new El('TH',{'data-proto-id':'second'},group);mapping.set('[data-proto-id="second"]',[second]);
const other={protoId:'second',tag:'th'},source={id:'source',anchor:{...anchor,revealSteps:[{selector:'#open-group',kind:'click',value:'true',label:'打开分组'}]}};
A.setRevealNotes([source]);let result=A.inspectReveal(other);
assert.equal(result.state,'automatic');assert.equal(result.sourceNoteIds[0],'source');assert.equal(result.steps[0].label,'打开分组');
A.setRevealNotes([source,{id:'conflict',anchor:{...anchor,revealSteps:[{selector:'#tab-answer',kind:'click',value:'true',label:'另一入口'}]}}]);
result=A.inspectReveal(other);assert.equal(result.state,'needed');assert.ok(result.reason.includes('不同'));
assert.deepEqual(clicks,[]);assert.equal(other.revealSteps,undefined);
''')


def test_inspection_reports_duplicate_disabled_and_missing_automatic_controls():
    run_case(r'''
pane.isHidden=false;group.isHidden=false;
mapping.set('#tab-answer',[tab,new El('BUTTON',{},body)]);
let r=A.inspectReveal(anchor);assert.equal(r.state,'needed');assert.equal(r.steps[0].status,'duplicate');
mapping.set('#tab-answer',[tab]);tab.disabled=true;
r=A.inspectReveal(anchor);assert.equal(r.state,'needed');assert.equal(r.steps[0].status,'disabled');
tab.disabled=false;mapping.set('#open-group',[]);
r=A.inspectReveal(anchor);assert.equal(r.state,'needed');assert.equal(r.steps[1].status,'missing');assert.deepEqual(clicks,[]);
''')


def test_inspection_displays_open_details_and_aria_relationships_without_toggling():
    run_case(r'''
delete pane.attrs['data-proto-reveal-by'];delete group.attrs['data-proto-reveal-by'];
pane.isHidden=false;group.isHidden=false;group.tagName='DETAILS';group.open=true;
const summary=new El('SUMMARY',{id:'summary',text:'高级设置'},group);mapping.set('summary',[summary]);mapping.set('#summary',[summary]);
let r=A.inspectReveal(anchor);assert.equal(r.state,'automatic');assert.equal(r.steps[0].label,'高级设置');assert.equal(group.open,true);
group.tagName='DIV';group.attrs.id='group';opener.attrs['aria-controls']='group';mapping.set('[aria-controls]',[opener]);
r=A.inspectReveal(anchor);assert.equal(r.state,'automatic');assert.equal(r.steps[0].label,'设置分组');assert.deepEqual(clicks,[]);
''')


def test_inspection_uses_actual_condition_before_shared_path_and_reports_unreachable_entries():
    run_case(r'''
delete pane.attrs['data-proto-reveal-by'];delete group.attrs['data-proto-reveal-by'];pane.isHidden=false;
const select=new El('SELECT',{id:'mode',text:'视图'},body);select.value='old';mapping.set('#mode',[select]);
anchor.conditions=[{selector:'#mode',kind:'select',value:'answer',label:'视图',option:'答案'}];
const second=new El('TH',{'data-proto-id':'second'},group);mapping.set('[data-proto-id="second"]',[second]);
A.setRevealNotes([{id:'peer',anchor:{protoId:'second',revealSteps:[{selector:'#open-group',kind:'click',value:'true',label:'打开分组'}]}}]);
let r=A.inspectReveal(anchor);assert.equal(r.steps[0].selector,'#mode');assert.equal(r.steps[0].kind,'select');assert.equal(r.steps[0].value,'answer');
delete anchor.conditions;opener.isHidden=true;
r=A.inspectReveal(anchor);assert.equal(r.state,'needed','没有可操作入口时不能声称自动路径已可用');assert.deepEqual(clicks,[]);
''')


def test_manual_path_stays_inspectable_when_target_is_temporarily_unmounted():
    run_case(r'''
anchor.revealSteps=[{selector:'#tab-answer',kind:'click',value:'true',label:'进入答案页'}];
mapping.set('[data-proto-id="group-footer"]',[]);
const r=A.inspectReveal(anchor);assert.equal(r.state,'manual');assert.equal(r.rendered,false);assert.equal(r.steps[0].label,'进入答案页');assert.deepEqual(clicks,[]);
''')


def test_reveal_executes_declared_safe_path_without_clicking_confirm():
    run_case(r'''
const result=A.reveal(anchor);assert.equal(result,target);assert.deepEqual(clicks,['tab-answer','open-group']);
assert.equal(A.hidden(target),false);A.reveal(anchor);assert.deepEqual(clicks,['tab-answer','open-group'],'已展开时不能重复打开或重置分组草稿');
''')


def test_shared_container_declaration_reveals_all_child_annotations_without_retoggling():
    run_case(r'''
const second=new El('TH',{'data-proto-id':'second'},group),other={protoId:'second',tag:'th'};
mapping.set('[data-proto-id="second"]',[second]);
assert.equal(A.revealHint(anchor)?.trigger,tab);assert.equal(A.revealHint(other)?.trigger,tab);
assert.equal(A.reveal(anchor),target);assert.equal(A.reveal(other),second);
assert.deepEqual(clicks,['tab-answer','open-group'],'同一容器内第二条标注不重复开关');
group.isHidden=true;assert.equal(A.revealHint(anchor)?.trigger,opener);assert.equal(A.revealHint(other)?.trigger,opener);
assert.equal(A.reveal(other),second);assert.equal(A.revealHint(anchor),null);
''')


def test_undeclared_hidden_container_can_share_one_unambiguous_manual_path_without_writing_notes():
    run_case(r'''
pane.isHidden=false;delete group.attrs['data-proto-reveal-by'];
const second=new El('TH',{'data-proto-id':'second'},group),other={protoId:'second',tag:'th'};
mapping.set('[data-proto-id="second"]',[second]);
const source={id:'source',anchor:{...anchor,revealSteps:[{selector:'#open-group',kind:'click',value:'true',label:'打开分组'}]}},note={id:'other',anchor:other};
A.setRevealNotes([source,note]);
assert.equal(A.sharedReveal(other).sourceNoteIds[0],'source');
assert.equal(A.revealHint(other)?.trigger,opener);assert.equal(A.reveal(other),second);
assert.equal(other.revealSteps,undefined,'自动识别不改写标注');assert.deepEqual(clicks,['open-group']);
A.reveal(source.anchor);assert.deepEqual(clicks,['open-group'],'已显示不重复切换');
''')


def test_shared_inference_rejects_conflicting_paths_other_containers_and_removed_sources():
    run_case(r'''
pane.isHidden=false;delete group.attrs['data-proto-reveal-by'];
const second=new El('TH',{'data-proto-id':'second'},group),other={protoId:'second',tag:'th'};
mapping.set('[data-proto-id="second"]',[second]);
const source={id:'source',anchor:{...anchor,revealSteps:[{selector:'#open-group',kind:'click',value:'true',label:'打开分组'}]}};
const competing={id:'competing',anchor:{...anchor,revealSteps:[{selector:'#tab-answer',kind:'click',value:'true',label:'其他入口'}]}};
A.setRevealNotes([source,competing]);assert.equal(A.sharedReveal(other),null,'同容器路径冲突不能猜测');
const separate=new El('DIV',{},body);separate.isHidden=true;second.parentElement=separate;
A.setRevealNotes([source]);assert.equal(A.sharedReveal(other),null,'不同隐藏容器不继承');
second.parentElement=group;A.setRevealNotes([]);assert.equal(A.revealHint(other),null,'来源移除后不能残留共享路径');
''')


def test_shared_async_container_open_is_coalesced_for_different_annotations():
    run_case(r'''
pane.isHidden=false;delete group.attrs['data-proto-reveal-by'];
const second=new El('TH',{'data-proto-id':'second'},group),other={protoId:'second',tag:'th'};
mapping.set('[data-proto-id="second"]',[second]);
const source={id:'source',anchor:{...anchor,revealSteps:[{selector:'#open-group',kind:'click',value:'true',label:'打开分组'}]}};
A.setRevealNotes([source,{id:'other',anchor:other}]);
opener.onClick=()=>setTimeout(()=>{group.isHidden=false},35);
(async()=>{const [one,two]=await Promise.all([A.revealAndWait(source.anchor),A.revealAndWait(other)]);
assert.equal(one,target);assert.equal(two,second);assert.deepEqual(clicks,['open-group'],'同一弹窗等待渲染时也只点击一次');
})().catch(e=>{console.error(e);process.exitCode=1});
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


def test_manual_path_overrides_automatic_conditions_and_chains_safe_clicks():
    run_case(r'''
anchor.revealSteps=[{selector:'#tab-answer',kind:'click',value:'true',label:'切换答题区'}, {selector:'#open-group',kind:'click',value:'true',label:'打开分组'}];
assert.equal(A.revealHint(anchor)?.trigger,tab);
tab.click();assert.equal(A.revealHint(anchor)?.trigger,opener);
clicks.length=0;assert.equal(A.reveal(anchor),target);assert.deepEqual(clicks,['open-group']);
A.reveal(anchor);assert.deepEqual(clicks,['open-group']);
''')


def test_manual_async_path_clicks_each_step_once_and_waits_for_render():
    run_case(r'''
delete pane.attrs['data-proto-reveal-by'];delete group.attrs['data-proto-reveal-by'];
anchor.revealSteps=[{selector:'#tab-answer',kind:'click',value:'true',label:'外层'}, {selector:'#open-group',kind:'click',value:'true',label:'内层'}];
tab.onClick=()=>setTimeout(()=>{pane.isHidden=false},30);opener.onClick=()=>setTimeout(()=>{group.isHidden=false},30);
(async()=>{assert.equal(await A.revealAndWait(anchor),target);assert.deepEqual(clicks,['tab-answer','open-group']);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_visible_unrelated_later_button_does_not_skip_the_real_opener():
    run_case(r'''
const sibling=new El('SPAN',{id:'analytics',text:'数据分析'},body);mapping.set('#analytics',[sibling]);
sibling.onClick=()=>{throw Error('unrelated later action must not replace first step')};
group.isHidden=false;
anchor.revealSteps=[{selector:'#tab-answer',kind:'click',value:'true',label:'需讲解人数'}, {selector:'#analytics',kind:'click',value:'true',label:'数据分析'}];
assert.equal(A.reveal(anchor),target);assert.deepEqual(clicks,['tab-answer']);
''')
