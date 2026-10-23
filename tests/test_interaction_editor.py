"""Exercise the real editor's button and picker lifecycle against isolated DOM fixtures."""
import json
import shutil
import subprocess
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / 'src/proto-interactions.js').read_text(encoding='utf-8')
HARNESS = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
class Events {
 constructor(){this.handlers=new Map()}
 addEventListener(name,fn){if(!this.handlers.has(name))this.handlers.set(name,new Set());this.handlers.get(name).add(fn)}
 removeEventListener(name,fn){this.handlers.get(name)?.delete(fn)}
 async fire(name,event={}){for(const fn of [...(this.handlers.get(name)||[])])await fn(event)}
}
class El extends Events {
 constructor(tag,doc,text=''){super();this.tagName=tag.toUpperCase();this.ownerDocument=doc;this.children=[];this.textContent=text;this.attrs={};this.dataset={};this.style={};this.className='';this.hidden=false;this.value=''}
 append(...nodes){for(const n of nodes){this.children.push(n);n.parentElement=this}}
 replaceChildren(...nodes){this.children=[];this.append(...nodes)}
 contains(other){for(let n=other;n;n=n.parentElement)if(n===this)return true;return false}
 setAttribute(k,v){this.attrs[k]=String(v)} getAttribute(k){return this.attrs[k]??null}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(x=>x!==this)}
 closest(){return this} scrollIntoView(){} getBoundingClientRect(){return {left:20,top:30,width:120,height:36}}
}
const doc=new Events();doc.createElement=tag=>new El(tag,doc);doc.documentElement=new El('html',doc);
const child=new Events();child.createElement=tag=>new El(tag,child);child.documentElement=new El('html',child);
let scope={mode:'targets',protoIds:[]},key='["project","page","default"]',notes=[{id:'n',number:3,body:'原有 PRD',anchor:{protoId:'hidden'}}],savedKeys=[],notice=[];
const w=new Events();w.document=child;w.Element=El;
w.ProtoAnchors={owned:el=>el?.dataset.prototypeOwned!==undefined,serialize:el=>({protoId:el.getAttribute('data-proto-id')||'',selector:'#'+el.attrs.id,tag:el.tagName.toLowerCase(),text:el.textContent,parentText:''}),resolveHidden:()=>null};
w.ProtoHotspots={candidate:el=>({status:'ready',label:el.textContent}),hide(){},show(){},inspect:()=>({items:(scope.manualTargets||[]).map(t=>({...t,key:'manual:'+t.id,source:'manual',protoId:t.anchor.protoId,status:'ready'}))})};
const frame=new El('iframe',doc);frame.contentWindow=w;frame.contentDocument=child;
const container=new El('section',doc),trigger=new El('button',doc);
const observers=[],frames=[];
const context={window:{},crypto:{randomUUID:()=> 'manual-id'},setTimeout:()=>1,clearTimeout(){},
 MutationObserver:class{constructor(fn){this.fn=fn;observers.push(this)}observe(){}disconnect(){}},
 requestAnimationFrame:fn=>{frames.push(fn);return frames.length},cancelAnimationFrame(){}};
vm.createContext(context);vm.runInContext(SOURCE,context);
const editorConfig={container,trigger,frame,scopeKey:()=>key,scope:()=>scope,notes:()=>notes,
 saveScope:async(next,k)=>{scope=next;savedKeys.push(k);return true},saveReveal:async(id,steps,k)=>{notes[0]=context.window.ProtoInteractions.model.setReveal(notes[0],steps);savedKeys.push(k);return true},notice:(text)=>notice.push(text),preparePick(){},picking(){},focusNote(){}};
const editor=context.window.ProtoInteractions.create(editorConfig);
const descendants=node=>node.children.flatMap(c=>[c,...descendants(c)]);
const button=label=>{const el=descendants(container).find(n=>n.tagName==='BUTTON'&&n.textContent===label);assert.ok(el,'missing button: '+label);return el};
const target=new El('button',child,'设置分组');target.attrs={id:'open', 'data-proto-id':'open'};
const clickEvent=()=>({target,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}});
const flush=()=>{while(frames.length)frames.shift()()};
const mutate=()=>{observers.at(-1).fn([{target:{closest:()=>null}}]);flush()};
'''


def run_case(code):
    result = subprocess.run([shutil.which('node'), '-'], input=HARNESS.replace('SOURCE', json.dumps(SOURCE)) + code,
                            text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


def test_add_delete_and_cancel_use_the_correct_scope_and_release_picker():
    run_case(r'''
(async()=>{
 trigger.onclick();button('＋ 添加热区').onclick();assert.equal(editor.isPicking(),true);
 const e=clickEvent();await w.fire('click',e);assert.ok(e.prevented&&e.stopped);
 assert.equal(editor.isPicking(),false);assert.equal(w.handlers.get('click').size,0);
 assert.equal(scope.manualTargets[0].anchor.protoId,'open');assert.equal(target.dataset.protoHotspot,undefined);
 assert.equal(savedKeys[0],'["project","page","default"]');
 await button('删除').onclick();assert.equal(scope.manualTargets.length,0);assert.equal(scope.excludedTargets[0].anchor.protoId,'open');
 button('＋ 添加热区').onclick();await w.fire('keydown',{key:'Escape',preventDefault(){},stopImmediatePropagation(){}});
 assert.equal(editor.isPicking(),false);assert.equal(w.handlers.get('click').size,0);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_background_mutations_and_refresh_keep_settings_back_and_delete_click_targets():
    run_case(r'''
(async()=>{
 trigger.onclick();button('展开联动').onclick();
 let settings=button('设置');mutate();editor.refresh();
 assert.equal(button('设置'),settings,'无关原型变化不能替换设置按钮');
 await settings.onclick();let back=button('←');mutate();editor.refresh();
 assert.equal(button('←'),back,'无关原型变化不能替换返回按钮');
 await back.onclick();assert.ok(button('设置'));
 notes[0].anchor.revealSteps=[{selector:'#open',kind:'click',value:'true',label:'打开弹窗'}];
 editor.openReveal('n');let remove=button('删除');mutate();editor.refresh();
 assert.equal(button('删除'),remove,'后台刷新不能吞掉删除点击');
 await remove.onclick();assert.equal(notes[0].anchor.revealSteps,undefined);assert.equal(savedKeys.length,1);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_real_status_change_during_pointer_press_waits_until_click_finishes():
    run_case(r'''
(async()=>{
 let state='needed';w.ProtoAnchors.inspectReveal=()=>({state,text:state,steps:[]});
 trigger.onclick();button('展开联动').onclick();const settings=button('设置');
 await doc.fire('pointerdown',{target:settings});state='automatic';mutate();editor.refresh();
 assert.equal(button('设置'),settings,'按住设置时状态变化也不能撤掉按钮');
 await doc.fire('pointerup',{target:settings});editor.refresh();
 assert.equal(button('设置'),settings,'松开与浏览器派发click之间仍保留按钮');await settings.onclick();flush();
 assert.ok(button('←'),'第一次点击就进入详情');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_overview_explains_which_annotations_need_entries_and_displays_automatic_steps():
    run_case(r'''
notes=[
 {id:'a',number:1,anchor:{protoId:'static'}},
 {id:'b',number:2,anchor:{protoId:'auto'}},
 {id:'c',number:3,anchor:{protoId:'unknown'}},
 {id:'d',number:4,anchor:{protoId:'manual',revealSteps:[{selector:'#open',label:'手动打开',kind:'click'}]}}
];
w.ProtoAnchors.inspectReveal=anchor=>({state:({static:'visible',auto:'automatic',unknown:'needed',manual:'manual'})[anchor.protoId],reason:'识别说明',steps:anchor.protoId==='auto'?[{label:'自动切换页签',status:'ready'}]:anchor.revealSteps||[]});
trigger.onclick();button('展开联动').onclick();
const all=()=>descendants(container).map(n=>n.textContent).join('|');
assert.ok(all().includes('需处理 1'));assert.ok(all().includes('当前无需展开'));assert.ok(all().includes('需补充入口'));
assert.ok(all().includes('自动切换页签'));assert.ok(all().includes('手动打开'));
const autoView=descendants(container).find(n=>n.attrs['aria-label']==='查看标注 2 的展开路径');autoView.onclick();
assert.ok(all().includes('自动识别结果'));assert.ok(all().includes('1. 自动切换页签'));assert.equal(savedKeys.length,0,'查看自动结果不落库');
''')


def test_confirmed_paths_can_be_inspected_but_not_mutated():
    run_case(r'''
notes[0].confirmed=true;notes[0].anchor.revealSteps=[{selector:'#open',label:'打开弹窗',kind:'click'}];
trigger.onclick();button('展开联动').onclick();assert.equal(button('编辑').disabled,false);button('编辑').onclick();
assert.equal(button('删除').disabled,true);assert.equal(button('＋ 点选展开入口').disabled,true);
assert.equal(button('←').disabled,false);assert.equal(savedKeys.length,0);
''')


def test_manual_reveal_form_saves_path_without_rewriting_body_or_number():
    run_case(r'''
(async()=>{
 editor.openReveal('n');button('＋ 点选展开入口').onclick();await w.fire('click',clickEvent());
 const form=descendants(container).find(n=>n.tagName==='FORM');assert.ok(form);
 await form.onsubmit({preventDefault(){}});
 assert.equal(descendants(container).some(n=>n.textContent==='保存关联'),false);
 assert.equal(notes[0].body,'原有 PRD');assert.equal(notes[0].number,3);
 assert.equal(notes[0].anchor.revealSteps[0].selector,'#open');assert.equal(notes[0].anchor.revealSteps[0].label,'设置分组');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_picker_makes_existing_guides_transparent_and_restores_them_when_cancelled():
    run_case(r'''
(async()=>{
 editor.openReveal('n');button('＋ 点选展开入口').onclick();
 const passthrough=child.documentElement.children.find(n=>n.tagName==='STYLE');
 assert.ok(passthrough,'已有引导遮住共享入口时，需要让原型控件接收点选');
 assert.ok(passthrough.textContent.includes('pointer-events:none!important'));
 await w.fire('keydown',{key:'Escape',preventDefault(){},stopImmediatePropagation(){}});
 assert.equal(child.documentElement.children.includes(passthrough),false,'取消点选恢复引导交互');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_reuse_selection_is_truthful_and_immediately_saved_without_apply_or_save_buttons():
    run_case(r'''
(async()=>{
 const source={id:'source',number:1,body:'来源 PRD',anchor:{protoId:'other',revealSteps:[{selector:'#open',kind:'click',value:'true',label:'设置分组'}]}};
 notes.push(source);
 editorConfig.saveReveal=async(id,steps,k)=>{notes=notes.map(n=>n.id===id?context.window.ProtoInteractions.model.setReveal(n,steps):n);savedKeys.push(k);return true};
 editor.openReveal('n');
 const choices=descendants(container).filter(n=>n.tagName==='INPUT'&&n.type==='radio');
 assert.ok(choices.find(n=>n.value===''&&n.checked),'尚未采用来源时不能假装选中标注1');
 const sourceChoice=choices.find(n=>n.value==='source');
 assert.equal(savedKeys.length,0);sourceChoice.checked=true;await sourceChoice.onchange();
 assert.equal(savedKeys.length,1);assert.equal(descendants(container).some(n=>['使用此路径','保存关联'].includes(n.textContent)),false);
 assert.equal(notes[0].anchor.revealSteps[0].selector,'#open');assert.equal(notes[0].anchor.protoId,'hidden');
 assert.equal(notes[0].body,'原有 PRD');assert.equal(notes[0].number,3);
 assert.equal(notes[1],source,'不改写来源标注');assert.equal(source.body,'来源 PRD');
 assert.notEqual(notes[0].anchor.revealSteps,source.anchor.revealSteps,'两条标注独立保存同一入口');
 const autoChoice=descendants(container).find(n=>n.tagName==='INPUT'&&n.type==='radio'&&n.value==='');
 autoChoice.checked=true;await autoChoice.onchange();
 assert.equal(notes[0].anchor.revealSteps,undefined,'选择自动识别立即清除当前手动覆盖');assert.equal(savedKeys.length,2);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_manual_radio_prepares_empty_path_without_persisting_until_a_step_is_added():
    run_case(r'''
(async()=>{
 editor.openReveal('n');const manual=descendants(container).find(n=>n.tagName==='INPUT'&&n.type==='radio'&&n.value==='manual');
 manual.checked=true;await manual.onchange();assert.equal(savedKeys.length,0);assert.equal(notes[0].anchor.revealSteps,undefined);
 assert.ok(descendants(container).some(n=>n.textContent==='添加后生效'));
 button('＋ 点选展开入口').onclick();await w.fire('click',clickEvent());
 await descendants(container).find(n=>n.tagName==='FORM').onsubmit({preventDefault(){}});
 assert.equal(savedKeys.length,1);assert.equal(notes[0].anchor.revealSteps[0].selector,'#open');
 await button('删除').onclick();assert.equal(notes[0].anchor.revealSteps,undefined);
 assert.ok(descendants(container).some(n=>n.tagName==='INPUT'&&n.type==='radio'&&n.value===''&&n.checked));
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_page_change_during_pick_never_saves_into_new_page():
    run_case(r'''
(async()=>{trigger.onclick();button('＋ 添加热区').onclick();key='["project","other","default"]';
await w.fire('click',clickEvent());assert.equal(savedKeys.length,0);assert.equal(editor.isPicking(),false);
editor.refresh();assert.equal(w.handlers.get('click').size,0);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_added_path_is_saved_before_testing_without_focusing_the_sidebar():
    run_case(r'''
(async()=>{
 let tests=0;editorConfig.focusNote=()=>{throw Error('sidebar focus must not stand in for reveal')};
 editorConfig.testReveal=async(id,steps,k)=>{tests++;assert.equal(id,'n');assert.equal(steps[0].selector,'#open');assert.equal(k,key);return {ok:true}};
 editor.openReveal('n');button('＋ 点选展开入口').onclick();await w.fire('click',clickEvent());
 await descendants(container).find(n=>n.tagName==='FORM').onsubmit({preventDefault(){}});
 assert.equal(button('测试展开').disabled,false);await button('测试展开').onclick();
 assert.equal(tests,1);assert.equal(savedKeys.length,1);assert.equal(notes[0].anchor.revealSteps[0].selector,'#open');
 assert.ok(descendants(container).some(n=>n.textContent==='已展开并定位标注'));
 assert.equal(descendants(container).some(n=>n.textContent==='保存关联'),false);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_autosave_failure_is_visible_and_retry_preserves_the_same_note():
    run_case(r'''
(async()=>{
 let attempts=0;editorConfig.saveReveal=async(id,steps,k)=>{assert.equal(id,'n');attempts++;if(attempts===1)return false;
 notes[0]=context.window.ProtoInteractions.model.setReveal(notes[0],steps);savedKeys.push(k);return true};
 editor.openReveal('n');button('＋ 点选展开入口').onclick();await w.fire('click',clickEvent());
 await descendants(container).find(n=>n.tagName==='FORM').onsubmit({preventDefault(){}});
 assert.equal(notes[0].anchor.revealSteps,undefined);assert.ok(descendants(container).some(n=>n.textContent.includes('尚未生效')));
 assert.equal(button('测试展开').disabled,true);await button('重试').onclick();
 assert.equal(attempts,2);assert.equal(notes[0].anchor.revealSteps[0].selector,'#open');assert.equal(notes[0].body,'原有 PRD');
 await button('删除').onclick();assert.equal(notes[0].anchor.revealSteps,undefined,'删除最后一步立即恢复自动识别');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_reordering_and_deleting_steps_autosave_with_no_extra_confirmation():
    run_case(r'''
(async()=>{
 notes[0].anchor.revealSteps=[{selector:'#first',kind:'click',value:'true',label:'先开外层'},{selector:'#second',kind:'click',value:'true',label:'再开内层'}];
 editor.openReveal('n');
 await descendants(container).find(n=>n.attrs['aria-label']==='下移步骤'&&!n.disabled).onclick();
 assert.equal(notes[0].anchor.revealSteps[0].selector,'#second');assert.equal(savedKeys.length,1);
 await button('删除').onclick();assert.equal(notes[0].anchor.revealSteps.length,1);assert.equal(savedKeys.length,2);
 assert.equal(notes[0].anchor.revealSteps[0].selector,'#first');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_failed_test_reports_a_visible_reason_and_keeps_the_draft():
    run_case(r'''
(async()=>{
 editorConfig.testReveal=async()=>({ok:false,message:'第二步入口被遮挡'});
 editor.openReveal('n');await button('测试展开').onclick();
 assert.ok(descendants(container).some(n=>n.textContent==='第二步入口被遮挡'));
 assert.equal(savedKeys.length,0);assert.equal(button('测试展开').disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_viewer_test_route_sends_draft_anchor_to_the_prototype_without_saving():
    viewer = (Path(__file__).resolve().parents[1] / 'src/viewer.html').read_text(encoding='utf-8')
    route = viewer[viewer.index('        async function extTestReveal('):viewer.index('        function extCanChange(')]
    code = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
let received=null,selected=null;
const note={id:'note',number:4,body:'保持现有 PRD',anchor:{selector:'#mask > div > header',revealSteps:[{selector:'#old',kind:'click',value:'true'}]}};
const ctx={extScopeKey:()=> 'scope',extPageNotes:()=>[note],extAnnotateDeactivate(){},extSuspendNoteEdit(){},currentMode:'annotate',
 previewFrame:{contentWindow:{ProtoAnnotate:{async testReveal(anchor){received=anchor;return {ok:true}}}}},extSelectNote:id=>selected=id};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
(async()=>{
const steps=[{selector:'#need',kind:'click',value:'true'}];assert.equal((await ctx.extTestReveal('note',steps,'scope')).ok,true);
assert.equal(received.revealSteps[0].selector,'#need');assert.equal(note.anchor.revealSteps[0].selector,'#old');assert.equal(selected,'note');
assert.equal(note.body,'保持现有 PRD');received=null;assert.equal((await ctx.extTestReveal('note',steps,'other')).ok,false);assert.equal(received,null);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([shutil.which('node'), '-'], input=code.replace('SOURCE', json.dumps(route)), text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
