"""添加页面的文件夹选择保留路径，并隔离无关依赖与隐藏文件。"""
import json
from pathlib import Path
import pytest
from test_screenshot_ui import node

SRC=Path(__file__).resolve().parents[1]/'src'


def test_folder_selection_preserves_paths_and_does_not_read_ignored_files():
    source=(SRC/'proto-screenshot-editor.js').read_text(encoding='utf-8')
    node("""
const assert=require('node:assert/strict');global.window={};
"""+source+"""
const choose=window.ProtoScreenshotEditor.collectHtmlFiles;
const fixture=path=>({name:path.split('/').pop(),webkitRelativePath:'project/'+path});
const records=choose(['pages/detail.html','assets/a.css','assets/a.js','assets/photo.png','.env','node_modules/x.js','.git/config.json','notes.md'].map(fixture),true);
assert.deepEqual(records.map(r=>r.path),['pages/detail.html','assets/a.css','assets/a.js','assets/photo.png']);
assert.throws(()=>choose([fixture('data/a.css')],true),/HTML/);
assert.throws(()=>choose([fixture('index.html'),fixture('INDEX.html')],true),/重复/);
assert.equal(choose([{name:'single.htm'}])[0].path,'single.htm');
""")


@pytest.mark.parametrize('kind',['screenshot','html'])
def test_edit_imported_page_replaces_selected_page_and_retains_files_after_save_failure(kind):
    source=(SRC/'proto-screenshot-editor.js').read_text(encoding='utf-8')
    node(r'''
const assert=require('node:assert/strict');global.window={};
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.events={};this.attrs={};this.value='';this.dataset={};this.files=[];this.hidden=false;this.className='';this.isConnected=true;}
 append(...nodes){this.children.push(...nodes)}
 replaceChildren(){this.children=[]}
 get firstChild(){return this.children[0]}
 get options(){return this.children}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(k,fn){this.events[k]=fn}
 showModal(){this.open=true}
 close(){this.open=false;this.events.close?.()}
 remove(){this.isConnected=false}
 focus(){}
 querySelectorAll(selector){return this.children.flatMap(c=>[...(selector.split(',').includes(c.tagName)?[c]:[]),...c.querySelectorAll(selector)])}
}
global.document={body:new Element('body'),createElement:tag=>new Element(tag)};
global.FileReader=class {readAsDataURL(file){this.result=file.data;this.onload()}};
global.DOMParser=class {parseFromString(){return {title:'导入文件标题'}}};
''' + source + r'''
(async()=>{
const kind=KIND,page={id:'imported',title:'原页面名称',...(kind==='screenshot'?{kind:'screenshot',screenshot:{regions:[]}}:{htmlImport:{directory:'pages/html-test'}})},home={id:'home'};
const saves=[],opened=[],notices=[];let fail=true,focusCount=0;
const editor=window.ProtoScreenshotEditor.create({frame:{addEventListener(){}},page:()=>home,project:()=>({pages:[home,page]}),
 trigger:{focus(){}},notice:m=>notices.push(m),openPage:id=>opened.push(id),
 save:async(action,payload)=>{saves.push({action,payload});if(fail)throw Error('保存失败，重试');return {page}}});
assert.equal(editor.openReplace('home'),false);assert.equal(editor.openReplace('missing'),false);
assert.equal(editor.openReplace(page.id,()=>focusCount++),true,'能替换左侧选择的非当前页面');
const modal=document.body.children.at(-1),form=modal.children[0],fields=form.querySelectorAll('input');
assert.equal(fields.some(f=>f.attrs['aria-label']==='页面名称'),false,'替换不重新创建页面设置');
const file=fields.find(f=>f.attrs['aria-label']===(kind==='html'?'选择 HTML':'选择截图'));
file.files=[{name:kind==='html'?'index.html':'new.png',type:kind==='html'?'text/html':'image/png',size:100,data:'data:application/octet-stream;base64,PGgxPuaWsOmhtTwvaDE+',text:async()=>'<h1>新页</h1>'}];
file.onchange();await new Promise(setImmediate);
await form.onsubmit({preventDefault(){}});
assert.equal(modal.open,true,'失败保留替换窗口和文件');assert.equal(opened.length,0);
fail=false;await form.onsubmit({preventDefault(){}});
assert.equal(modal.open,false);assert.deepEqual(opened,['imported']);assert.equal(focusCount,1);
assert.equal(saves.length,2);assert.equal(saves[1].action,kind==='html'?'replace-html':'replace');
assert.equal(saves[1].payload.pageId,'imported');assert.equal('title' in saves[1].payload,false);
assert.ok(kind==='html'?saves[1].payload.files.length:saves[1].payload.dataUrl);
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('KIND',json.dumps(kind)))
