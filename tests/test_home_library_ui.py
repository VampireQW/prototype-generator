"""首页隐藏视图与卡片操作的 DOM 行为回归。"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def run_case(case):
    node = shutil.which('node')
    if not node: pytest.skip('需要 Node.js')
    source = (Path(__file__).resolve().parents[1]/'src/script.js').read_text(encoding='utf-8')
    start = source.index('function renderExternalProjects(')
    end = source.index('const connectingProjects', start)
    script = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const fields={};const element=id=>fields[id]||(fields[id]={value:'',textContent:'',hidden:false,attrs:{},children:[],setAttribute(k,v){this.attrs[k]=v;},append(item){this.children.push(item);}});
element('externalFilter').value='all';
let rendered=[],empty;
const context={console,document:{createElement(){return {className:'',type:'',textContent:''};}},
 $:element,externalProjects:[],externalHiddenProjects:[],externalShowHidden:false,
 HomeUI:{clear(box){box.children=[];rendered=[];},formatDate(){return '';},updateCounts(source,total,visible){context.counts={source,total,visible};},
 card(config){rendered.push(config);config.actions=[];return {article:{config},actions:{append(...actions){config.actions.push(...actions);}}};},
 action(icon,label,handler){return {icon,label,handler};},more(name,items){return {items};},empty(...args){empty=args;},closeMenu(){}},
 connectExternalProject(){},openExternalProject(){},openExtPublishModal(){},hideExternalProject(){},restoreExternalProject(){},deleteExternalProject(){},toggleExternalAddPanel(){}};
vm.createContext(context);vm.runInContext(SOURCE,context);
const connected={projectId:'a',name:'已连接项目',root:'/a',exists:true,pages:1};
const discovered={projectId:'b',name:'新发现项目',root:'/b',exists:true,pages:1,discovered:true};
const hidden={projectId:'c',name:'已隐藏项目',root:'/c',exists:true,pages:1,discovered:true};
'''.replace('SOURCE',json.dumps(source[start:end])) + case
    result = subprocess.run([node,'-'],input=script,text=True,encoding='utf-8',capture_output=True)
    assert result.returncode == 0, result.stderr


def test_hidden_entries_do_not_leak_into_home_and_keep_home_count():
    run_case(r'''
context.renderExternalProjects([connected],[discovered],[hidden]);
assert.deepEqual(rendered.map(item=>item.id).sort(),['a','b']);assert.equal(context.counts.total,2);
assert.equal(element('hiddenProjectCount').textContent,1);
context.externalShowHidden=true;context.renderExternalProjects();
assert.deepEqual(rendered.map(item=>item.id),['c']);assert.equal(context.counts.total,2);
assert.ok(element('localResultCount').textContent.includes('已隐藏'));
assert.equal(element('externalHiddenBack').hidden,false);
''')


def test_connected_and_discovered_cards_both_offer_hide_and_delete():
    run_case(r'''
context.renderExternalProjects([connected],[discovered],[]);
for(const card of rendered){const menu=card.actions.find(item=>item.items);assert.ok(menu);
 assert.ok(menu.items.some(item=>item.label==='隐藏项目'));assert.ok(menu.items.some(item=>item.label==='彻底删除项目及本地文件'));}
''')


def test_hidden_cards_offer_restore_without_connecting_and_delete():
    run_case(r'''
context.externalShowHidden=true;context.renderExternalProjects([],[],[hidden]);
const card=rendered[0];assert.equal(card.disabled,true);
assert.ok(card.actions.some(item=>item.label==='显示到首页'));
assert.ok(card.actions.find(item=>item.items).items.some(item=>item.label==='彻底删除项目及本地文件'));
''')
