"""新增标注在右栏编辑时，保存、重绘与空草稿的生命周期。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'
VIEWER = (SRC / 'viewer.html').read_text(encoding='utf-8')
ANNOTATE = (SRC / 'proto-annotate.js').read_text(encoding='utf-8')
METHODS = VIEWER[VIEWER.index('            beginSidebarPick('):VIEWER.index('            storePickDraft(')]
RENDER = VIEWER[VIEWER.index('        function renderExtAnnotList()'):VIEWER.index('        function extSelectNote(')]
PINS = VIEWER[VIEWER.index('        function extRenderPins()'):VIEWER.index('        // ---------- 外观：')]
ORDER = (SRC / 'proto-order.js').read_text(encoding='utf-8')


def run_node(code):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行前端回归')
    result = subprocess.run([executable, '-'], input=code, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


HARNESS = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
class El {
 constructor(classes='') { this.classes=new Set(classes.split(' ').filter(Boolean));this.children=[];this.dataset={};this.style={};this.attrs={};this.hidden=false;
  this.classList={add:(...v)=>v.forEach(c=>this.classes.add(c)),remove:(...v)=>v.forEach(c=>this.classes.delete(c)),contains:c=>this.classes.has(c),toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)}; }
 appendChild(el){el.remove();el.parent=this;this.children.push(el);return el;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(el=>el!==this);this.parent=null;}
 setAttribute(k,v){this.attrs[k]=String(v);}
 contains(el){return el===this||this.children.some(c=>c.contains(el));}
 matches(q){if(q==='[data-empty]')return 'empty' in this.dataset;if(q.includes(':not('))return this.matches('.ext-note')&&!this.matches('.ext-pick-draft');return q[0]==='.'&&this.classes.has(q.slice(1));}
 closest(q){return this.matches(q)?this:this.parent?.closest(q)||null;}
 querySelectorAll(q){return this.children.flatMap(el=>[...(el.matches(q)?[el]:[]),...el.querySelectorAll(q)]);}
 querySelector(q){return this.querySelectorAll(q)[0]||null;}
}
const list=new El(),count=new El();let scope='["project","page","default"]',expanded=true,session=null,failSave=false,sequence=0,reserved=0,savedScopes=[];
const bundle={prd:{annotations:[]},changes:{items:[]}};
function createRow(id){const row=new El('ext-note');row.dataset.noteId=id;
 const head=row.appendChild(new El('ext-note-head'));head.appendChild(new El('ext-note-no'));head.appendChild(new El('ext-note-more'));
 const content=row.appendChild(new El('ext-note-content'));content.appendChild(new El('ext-note-body'));return row;}
const md={key:(...v)=>JSON.stringify(v),begin(region,options){session={region,options};return true;},
 render(region,options){if(session?.region!==region)region.textContent=options.value;},
 suspend(region){if(!session||!region.contains(session.region))return;const s=session;session=null;s.options.onEnd(false);}};
const context={ProtoMarkdown:md,ProtoAppearance:{applyPin(){}},get prdExpanded(){return expanded;},extScopeKey:()=>scope,
 extBundle:bundle,extDisplayNotes:[],extSelectedNoteId:null,extPickPreview:null,crypto:{randomUUID:()=> 'new-'+(++reserved)},
 $:id=>id==='extAnnotList'?list:count,document:{createElement:()=>new El()},extCreateNoteRow:createRow,
 extPageNotes:()=>bundle.prd.annotations.filter(n=>JSON.stringify(['project',n.pageId,n.stateId])===scope),
 extAnchorAlive:()=>true,extNoteOptions:n=>({value:n.body}),extShortcutText:()=> 'Alt+Shift+A',
 closeExtNoteMenu(){},extScrollNoteIntoView(){},extImageOptions:()=>({}),extTheme:()=> 'light',
 extPinsVisible:()=>true,extSaveNoteBody:async(id,body)=>{const note=bundle.prd.annotations.find(n=>n.id===id);note.body=body;return true;}};
const win={scrollX:0,scrollY:0,document:{},ProtoAnchors:{point:n=>({point:{x:n.placement?.x??0,y:n.placement?.y??0}})},
 ProtoAnnotate:{setTheme(){},setVisible(){},renderPins(notes){context.renderedPins=notes;}}};
context.previewFrame={contentWindow:win};
vm.createContext(context);vm.runInContext(ORDER,context);vm.runInContext(PINS,context);vm.runInContext(RENDER,context);
vm.runInContext('globalThis.host={'+METHODS+'};',context);
context.host.previewNumber=()=>1;
context.host.submitPick=async pick=>{if(failSave)return false;savedScopes.push(pick.scopeKey);const [project,pageId,stateId]=JSON.parse(pick.scopeKey);
 const id=pick.id||'new-'+(++sequence);bundle.prd.annotations.push({id,pageId,stateId,number:sequence,body:pick.body,anchor:pick.anchor,placement:pick.placement});context.extRenderPins();context.renderExtAnnotList();return id;};
const pick={x:20,y:90,scopeKey:scope,anchor:{protoId:'control'},placement:{kind:'document',x:20,y:90}};
'''


def sidebar_case(code):
    run_node(HARNESS.replace('RENDER', json.dumps(RENDER)).replace('METHODS', json.dumps(METHODS)).replace('PINS', json.dumps(PINS)).replace('ORDER', json.dumps(ORDER)) + code)


def test_pending_annotation_reserves_its_number_immediately_and_cancel_restores_order():
    sidebar_case(r'''
const original={id:'existing',pageId:'page',stateId:'default',number:17,body:'历史正文',placement:{kind:'document',x:20,y:160}};
bundle.prd.annotations.push(original);context.extRenderPins();context.renderExtAnnotList();
const cleanup=context.host.beginSidebarPick(pick,()=>{},()=>{}),draft=list.querySelector('.ext-pick-draft');
const numbers=()=>list.querySelectorAll('.ext-note').sort((a,b)=>Number(a.style.order)-Number(b.style.order)).map(row=>Number(row.querySelector('.ext-note-no').textContent));
assert.deepEqual(numbers(),[1,2]);assert.ok(list.querySelectorAll('.ext-note').every(row=>Number.isInteger(Number(row.style.order))));
assert.equal(context.renderedPins.find(n=>n.id==='existing').displayNumber,2);assert.equal(count.textContent,'2 条');
assert.equal(bundle.prd.annotations.length,1);assert.equal(original.number,17);
context.extRenderPins();context.renderExtAnnotList();assert.deepEqual(numbers(),[1,2]);assert.equal(list.querySelector('.ext-pick-draft'),draft);
cleanup();assert.deepEqual(numbers(),[1]);assert.equal(context.renderedPins[0].displayNumber,1);assert.equal(count.textContent,'1 条');assert.equal(original.number,17);
''')


@pytest.mark.parametrize('existing_y', [90, 160])
def test_first_save_keeps_the_pending_number_order_and_editor_region(existing_y):
    sidebar_case(r'''
(async()=>{
 bundle.prd.annotations.push({id:'existing',pageId:'page',stateId:'default',number:9,body:'历史正文',placement:{kind:'document',x:20,y:EXISTING_Y}});
 context.extRenderPins();context.renderExtAnnotList();context.host.beginSidebarPick(pick,()=>{},()=>{});
 const row=list.querySelector('.ext-pick-draft'),region=session.region,options=session.options;
 const labels=()=>list.querySelectorAll('.ext-note').sort((a,b)=>Number(a.style.order)-Number(b.style.order)).map(r=>Number(r.querySelector('.ext-note-no').textContent));
 const orderBefore=row.style.order,numberBefore=row.querySelector('.ext-note-no').textContent;
 assert.deepEqual(labels(),[1,2]);await options.save('首次输入');options.onAutosaved();
 assert.deepEqual(labels(),[1,2]);assert.equal(row.dataset.noteId,'new-1');assert.equal(session.region,region);assert.equal(row.classList.contains('ext-pick-draft'),false);
 assert.equal(row.style.order,orderBefore);assert.equal(row.querySelector('.ext-note-no').textContent,numberBefore);
 const s=session;session=null;s.options.onEnd(true);assert.deepEqual(labels(),[1,2]);assert.equal(bundle.prd.annotations.find(n=>n.id==='existing').number,9);
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('EXISTING_Y', str(existing_y)))


def test_autosaved_sidebar_row_is_reused_without_duplicate_or_editor_teardown():
    sidebar_case(r'''
(async()=>{
 const cleanup=context.host.beginSidebarPick(pick,()=>{},()=>{});assert.equal(typeof cleanup,'function');
 const row=list.querySelector('.ext-pick-draft'),region=session.region;assert.ok(row.contains(region));
 context.renderExtAnnotList();assert.equal(list.querySelector('.ext-pick-draft'),row);assert.equal(list.querySelector('[data-empty]'),null);
 const options=session.options,result=await options.save('新增正文');assert.equal(result.key,md.key('project','page','default','new-1'));
 options.onAutosaved();assert.equal(list.querySelectorAll('.ext-note').length,1);assert.equal(list.children[0],row);
 assert.equal(row.dataset.noteId,'new-1');assert.equal(row.classList.contains('ext-pick-draft'),false);assert.equal(row.querySelector('.ext-note-more').hidden,false);
 assert.equal(session.region,region);await options.save('继续修改');assert.equal(bundle.prd.annotations.length,1);assert.equal(bundle.prd.annotations[0].body,'继续修改');
 cleanup();assert.equal(session,null);assert.equal(list.querySelectorAll('.ext-note').length,1);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_empty_or_failed_sidebar_draft_does_not_create_an_annotation():
    sidebar_case(r'''
(async()=>{
 let cancelled=0;let cleanup=context.host.beginSidebarPick(pick,()=>{},()=>cancelled++);
 cleanup();assert.equal(cancelled,1);assert.equal(bundle.prd.annotations.length,0);assert.equal(list.querySelector('.ext-pick-draft'),null);
 cleanup=context.host.beginSidebarPick(pick,()=>{},()=>cancelled++);failSave=true;
 assert.equal(await session.options.save('尚未保存'),false);assert.ok(list.querySelector('.ext-pick-draft'));assert.equal(bundle.prd.annotations.length,0);
 cleanup();assert.equal(cancelled,2);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_sidebar_creation_respects_collapsed_state_and_original_scope():
    sidebar_case(r'''
(async()=>{
 expanded=false;assert.equal(context.host.beginSidebarPick(pick,()=>{},()=>{}),null);assert.equal(session,null);
 expanded=true;context.host.beginSidebarPick(pick,()=>{},()=>{});const options=session.options;
 scope='["project","other-page","default"]';await options.save('旧页面正文');options.onAutosaved();
 assert.deepEqual(savedScopes,[pick.scopeKey]);assert.equal(bundle.prd.annotations[0].pageId,'page');assert.equal(list.querySelectorAll('.ext-note').length,0);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_collapsed_creation_still_uses_floating_editor_without_expanding_sidebar():
    source = ANNOTATE[ANNOTATE.index('    function openInputCard('):ANNOTATE.index('    function makeCard(')]
    run_node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');let made=0,closed=0,done;
const region={},card={setAttribute(){},querySelector:()=>region};
const h={prdExpanded:()=>false,scopeKey:()=> 'scope',beginSidebarPick(){throw Error('must not use sidebar');},
 beginPick:(r,p,onDone)=>{assert.equal(r,region);done=onDone;return true;},focusNote(){throw Error('must not expand sidebar');},markdown:{relayout(){}}};
const context={inputCard:null,pending:{x:20,y:90,scopeKey:'scope'},host:()=>h,makeCard:()=>{made++;return card;},
 closeInputCard(){closed++;context.inputCard=null;context.pending=null;},setCardBody(){},placeCard(){},showPreviewNumber(){},selectNote(){}};
vm.createContext(context);vm.runInContext(SOURCE,context);context.openInputCard(20,90);assert.equal(made,1);assert.equal(context.inputCard,card);
done('n');assert.equal(closed,1);
'''.replace('SOURCE', json.dumps(source)))
