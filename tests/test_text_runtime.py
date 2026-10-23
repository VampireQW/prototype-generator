"""动态文案按稳定键重放，重排 / 重新渲染不串控件。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def run_case(case):
    node = shutil.which('node')
    if not node: pytest.skip('需要 Node.js')
    source = (Path(__file__).resolve().parents[1]/'src/proto-text-runtime.js').read_text(encoding='utf-8')
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
class El{
 constructor(tag,attrs={}){this.tagName=tag.toUpperCase();this.nodeType=1;this.attrs=attrs;this.childNodes=[];this.ownerDocument=doc;}
 get children(){return this.childNodes.filter(n=>n.nodeType===1)}
 get previousElementSibling(){const a=this.parentElement?.children||[];return a[a.indexOf(this)-1]||null}
 get attributes(){return Object.entries(this.attrs).map(([name,value])=>({name,value}))}
 getAttribute(key){return this.attrs[key]??null}hasAttribute(key){return key in this.attrs}
 append(...nodes){for(const n of nodes){n.parentElement=this;this.childNodes.push(n)}}
}
const observers=[],walk=n=>[n,...(n.children||[]).flatMap(walk)];
const doc={getElementById:id=>walk(root).find(n=>n.attrs?.id===id),getElementsByTagName:tag=>walk(root).filter(n=>n.tagName.toLowerCase()===tag),addEventListener(){},
 defaultView:{MutationObserver:class{constructor(fn){this.fn=fn;observers.push(this)}observe(){}disconnect(){}}}};
const root=new El('html'),body=new El('body'),track=new El('div',{id:'pillTrack'});root.append(body);body.append(track);doc.documentElement=root;
const pill=(id,text)=>{const e=new El('span',{'data-q':id}),t={nodeType:3,nodeValue:text};e.append(t);return e};
const a=pill('q1',' 同名 '),b=pill('q2',' 同名 ');track.append(a,b);
const context={window:{},document:doc};vm.createContext(context);vm.runInContext(SOURCE,context);
const api=context.window.ProtoTextRuntime;
const rule={binding:{anchor:{tag:'div',key:'id',value:'pillTrack'},path:[{tag:'span',key:'data-q',value:'q2'}]},before:['同名'],after:['新名称']};
'''
    result = subprocess.run([node,'-'], input=harness.replace('SOURCE',json.dumps(source))+case,text=True,encoding='utf-8',capture_output=True)
    assert result.returncode == 0, result.stderr


def test_keyed_label_survives_rerender_reordering_and_does_not_change_peer():
    run_case(r'''
assert.deepEqual(JSON.parse(JSON.stringify(api.bindings(b)))[0],rule.binding);
api.install(doc,[rule]);assert.equal(a.childNodes[0].nodeValue,' 同名 ');assert.equal(b.childNodes[0].nodeValue,' 新名称 ');
const replacement=pill('q2','同名');track.childNodes=[];track.append(replacement,pill('q1','同名'));observers[0].fn();
assert.equal(replacement.childNodes[0].nodeValue,'新名称');assert.equal(track.children[1].childNodes[0].nodeValue,'同名');
''')


def test_external_new_text_and_ambiguous_keys_are_not_overwritten():
    run_case(r'''
b.childNodes[0].nodeValue='AI 的后续修改';api.install(doc,[rule]);assert.equal(b.childNodes[0].nodeValue,'AI 的后续修改');
b.childNodes[0].nodeValue='同名';track.append(pill('q2','同名'));observers[0].fn();assert.equal(b.childNodes[0].nodeValue,'同名');
''')


def test_live_saved_rule_replaces_old_one_and_preserves_unsaved_preview():
    run_case(r'''
api.install(doc,[rule]);b.childNodes[0].nodeValue='输入中的文案';observers[0].fn();assert.equal(b.childNodes[0].nodeValue,'输入中的文案');
api.install(doc,[{...rule,after:['输入中的文案']}]);assert.equal(observers.length,1);
b.childNodes[0].nodeValue='同名';observers[0].fn();assert.equal(b.childNodes[0].nodeValue,'输入中的文案');
''')


def test_runtime_keeps_markup_literal_and_leaves_framework_text_alone():
    run_case(r'''
rule.after=['<img src=x onerror=run()>'];api.install(doc,[rule]);assert.equal(b.children.length,0);assert.equal(b.childNodes[0].nodeValue.trim(),rule.after[0]);
b.__vueParentComponent={};b.childNodes[0].nodeValue='同名';observers[0].fn();assert.equal(b.childNodes[0].nodeValue,'同名');
''')


TABLE_SETUP=r'''
const table=new El('table'),head=new El('thead'),hr1=new El('tr'),hr2=new El('tr'),rows=new El('tbody',{id:'rows'});
const textEl=(tag,text,attrs={})=>{const e=new El(tag,attrs);e.append({nodeType:3,nodeValue:text});return e};
hr1.append(textEl('th','班级',{rowspan:'2'}),textEl('th','人数',{colspan:'2'}));hr2.append(textEl('th','已交'),textEl('th','良好'));
head.append(hr1,hr2);table.append(head,rows);body.append(table);
const row=(name,sub,good)=>{const e=new El('tr');e.append(textEl('td',name),textEl('td',sub),textEl('td',good));return e};
const six=row('6','65','16'),eight=row('8','57','16');rows.append(six,eight);
const cell=six.children[2],binding=api.bindings(cell)[0];
'''


def test_unkeyed_table_rows_and_grouped_headers_survive_filter_sort_and_column_reordering():
    run_case(TABLE_SETUP+r'''
assert.deepEqual(JSON.parse(JSON.stringify(binding.path[0].match)),[{path:[{tag:'td',index:1}],text:'6'}]);
assert.deepEqual(JSON.parse(JSON.stringify(binding.path[1].column)),['人数','良好']);
const edit={binding,before:['16'],after:['18']};api.install(doc,[edit]);assert.equal(cell.childNodes[0].nodeValue,'18');
assert.equal(eight.children[2].childNodes[0].nodeValue,'16');
rows.childNodes=[];rows.append(row('8','57','16'));observers[0].fn();assert.equal(rows.children[0].children[2].childNodes[0].nodeValue,'16');
const again=row('6','65','16');rows.append(again);observers[0].fn();assert.equal(again.children[2].childNodes[0].nodeValue,'18');
const old=again.childNodes;again.childNodes=[old[0],old[2],old[1]];
hr2.childNodes.reverse();again.children[1].childNodes[0].nodeValue='16';observers[0].fn();
assert.equal(again.children[1].childNodes[0].nodeValue,'18');assert.equal(again.children[2].childNodes[0].nodeValue,'65');
''')


def test_no_id_list_uses_unchanged_heading_and_never_matches_another_item_after_filtering():
    run_case(r'''
const list=new El('ul');body.append(list);
const item=name=>{const e=new El('li'),h=new El('h3'),button=new El('button');h.append({nodeType:3,nodeValue:name});button.append({nodeType:3,nodeValue:'查看'});e.append(h,button);return e};
const one=item('作业A'),two=item('作业B');list.append(one,two);
const binding=api.bindings(one.children[1]).at(-1);assert.equal(binding.anchor.tag,'body');
api.install(doc,[{binding,before:['查看'],after:['查看详情']}]);assert.equal(one.children[1].childNodes[0].nodeValue,'查看详情');
list.childNodes=[];list.append(item('作业B'));observers[0].fn();assert.equal(list.children[0].children[1].childNodes[0].nodeValue,'查看');
list.append(item('作业A'));observers[0].fn();assert.equal(list.children[1].children[1].childNodes[0].nodeValue,'查看详情');
''')


def test_unkeyed_unique_label_keeps_its_binding_after_rename_and_rerender():
    run_case(r'''
const panel=new El('section',{id:'actions'}),button=new El('button');button.append({nodeType:3,nodeValue:'提交'});panel.append(button);body.append(panel);
const binding=api.bindings(button)[0];assert.equal(binding.path[0].text,'提交');
const edit={binding,before:['提交'],after:['保存']};api.install(doc,[edit]);
assert.equal(button.childNodes[0].nodeValue,'保存');assert.equal(JSON.stringify(api.bindings(button)[0]),JSON.stringify(binding));
panel.childNodes=[];const again=new El('button');again.append({nodeType:3,nodeValue:'提交'});panel.append(again);observers[0].fn();assert.equal(again.childNodes[0].nodeValue,'保存');
''')


def test_editing_row_identity_does_not_detach_an_existing_cell_override():
    run_case(TABLE_SETUP+r'''
const firstBinding=api.bindings(six.children[0])[0];
const good={binding,before:['16'],after:['18']},name={binding:firstBinding,before:['6'],after:['六班']};
api.install(doc,[good,name]);observers[0].fn();assert.equal(cell.childNodes[0].nodeValue,'18');
assert.equal(six.children[0].childNodes[0].nodeValue,'六班');
assert.equal(JSON.stringify(api.bindings(cell)[0]),JSON.stringify(binding));
''')


def test_body_fallback_does_not_guess_between_indistinguishable_lists():
    run_case(r'''
const make=()=>{const list=new El('ul'),li=new El('li'),h=new El('h3'),b=new El('button');h.append({nodeType:3,nodeValue:'同一标题'});b.append({nodeType:3,nodeValue:'查看'});li.append(h,b);list.append(li);return {list,b}};
const first=make();body.append(first.list);
const binding=api.bindings(first.b).at(-1);api.install(doc,[{binding,before:['查看'],after:['查看详情']}]);
const second=make();body.childNodes.unshift(second.list);second.list.parentElement=body;observers[0].fn();
assert.equal(second.b.childNodes[0].nodeValue,'查看');
''')
