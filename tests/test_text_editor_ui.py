"""手动微调编辑器：只预览文字节点，保存 / 取消 / 切换保留边界。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'


HARNESS = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
class El {
 constructor(tag,doc){this.tagName=tag.toUpperCase();this.nodeType=1;this.ownerDocument=doc;this.childNodes=[];this.dataset={};this.attrs={};this.style={};this.value='';this.textContent='';this.isConnected=true;this.hidden=false;this.disabled=false;}
 get children(){return this.childNodes.filter(n=>n.nodeType===1);}
 get previousElementSibling(){if(!this.parentElement)return null;const a=this.parentElement.children;return a[a.indexOf(this)-1]||null;}
 getAttribute(k){return this.attrs[k]??null;}setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}
 append(...nodes){for(const n of nodes){n.parentElement=this;this.childNodes.push(n);}}
 appendChild(n){this.append(n);return n;}replaceChildren(...nodes){this.childNodes=[];this.append(...nodes);}
 closest(selector){return selector.split(',').map(s=>s.trim().toUpperCase()).includes(this.tagName)?this:this.parentElement?.closest(selector)||null;}
 focus(){}addEventListener(type,fn){this['on'+type]=fn;}
}
const doc={createElement:tag=>new El(tag,doc)};
const txt=value=>({nodeType:3,nodeValue:value,isConnected:true});
const html=new El('html',doc),body=new El('body',doc);html.append(body);
function button(label,id){const el=new El('button',doc);el.attrs['data-proto-id']=id;const icon=new El('i',doc);const text=txt(' '+label+' ');el.append(icon,text);body.append(el);return {el,icon,text};}
const first=button('保存','save'),second=button('取消','cancel'),container=new El('section',doc);
let scope={projectId:'p',pageId:'home',stateId:'default'},writes=0,undone=0,fail=false,requests=[];
const context={window:{},document:doc,setTimeout,clearTimeout};vm.createContext(context);vm.runInContext(SOURCE,context);
const api=context.window.ProtoTextEdit;assert.ok(api);
const request=async(action,payload)=>{requests.push({action,payload});if(action==='inspect')return {ok:true,file:'index.html',hash:'old',fields:payload.target.texts.map((text,slot)=>({slot,text})),undoId:null};
 if(action==='save'){if(fail)throw Error('源文件已变化');writes++;assert.equal(payload.expectedHash,'old');return {ok:true,hash:'new',undoId:'undo',fields:payload.target.texts.map((text,slot)=>({slot,text:payload.edits.find(e=>e.slot===slot)?.text??text}))};}
 if(action==='undo'){undone++;return {ok:true,hash:'old'};}};
const editor=api.create({container,scope:()=>scope,request,onUndo(){undone++;}});
const all=n=>n.childNodes.flatMap(c=>[c,...(c.nodeType===1?all(c):[])]);
const control=role=>{const n=all(container).find(n=>n.dataset?.role===role);assert.ok(n,'missing '+role);return n;};
const input=value=>{const n=control('text');n.value=value;n.oninput();};
'''


def run_case(code):
    node = shutil.which('node')
    if not node: pytest.skip('需要 Node.js')
    source = (SRC/'proto-text-edit.js').read_text(encoding='utf-8')
    result = subprocess.run([node,'-'],input=HARNESS.replace('SOURCE',json.dumps(source))+code,
                            text=True,encoding='utf-8',capture_output=True)
    assert result.returncode == 0, result.stderr


def test_preview_and_cancel_preserve_icon_and_original_text():
    run_case(r'''
(async()=>{await editor.select([first.el]);input('确认保存');assert.equal(first.text.nodeValue,' 确认保存 ');assert.equal(first.el.children[0],first.icon);assert.equal(writes,0);
control('cancel').onclick();assert.equal(first.text.nodeValue,' 保存 ');assert.equal(writes,0);assert.equal(control('save').disabled,true);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_save_uses_source_snapshot_and_closing_keeps_saved_text():
    run_case(r'''
(async()=>{await editor.select([first.el]);input('确认保存');await control('save').onclick();assert.equal(writes,1);assert.equal(requests.at(-1).payload.target.texts[0],'保存');
editor.close();assert.equal(first.text.nodeValue,' 确认保存 ');assert.equal(first.el.children[0],first.icon);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_failed_save_keeps_preview_and_cancel_restores_it():
    run_case(r'''
(async()=>{await editor.select([first.el]);input('新文案');fail=true;await control('save').onclick();assert.equal(writes,0);assert.equal(first.text.nodeValue,' 新文案 ');assert.ok(control('status').textContent.includes('源文件已变化'));
editor.close();assert.equal(first.text.nodeValue,' 保存 ');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_selection_change_rolls_back_preview_and_rejects_wrong_page_save():
    run_case(r'''
(async()=>{await editor.select([first.el]);input('未保存');await editor.select([second.el]);assert.equal(first.text.nodeValue,' 保存 ');assert.equal(control('text').value,'取消');
input('另一页');scope={...scope,pageId:'other'};await control('save').onclick();assert.equal(writes,0);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_late_inspect_response_does_not_replace_new_selection():
    run_case(r'''
(async()=>{let resolveOld;
const delayed=api.create({container,scope:()=>scope,request:async(action,p)=>p.target.protoId==='save'?await new Promise(r=>resolveOld=r):{ok:true,file:'index.html',hash:'old',fields:[{slot:0,text:'取消'}]}});
const old=delayed.select([first.el]);await delayed.select([second.el]);resolveOld({ok:true,file:'index.html',hash:'old',fields:[{slot:0,text:'保存'}]});await old;
assert.equal(control('text').value,'取消');assert.equal(first.text.nodeValue,' 保存 ');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_reactive_text_offers_no_manual_save_and_undo_is_available_after_save():
    run_case(r'''
(async()=>{first.el.__vueParentComponent={};await editor.select([first.el]);assert.equal(requests.length,0);assert.equal(control('save').disabled,true);assert.ok(control('status').textContent.includes('程序生成'));
delete first.el.__vueParentComponent;await editor.select([first.el]);input('确认');await control('save').onclick();assert.equal(control('undo').disabled,false);
await control('undo').onclick();assert.equal(undone,2);
})().catch(e=>{console.error(e);process.exitCode=1});
''')
