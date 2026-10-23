"""研发版原型与 PRD 选中状态同步，不能依赖短暂 flash 或 DOM 节点身份。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'
SHELL = (SRC / 'review_shell.html').read_text(encoding='utf-8')
BRIDGE = (SRC / 'review-bridge.js').read_text(encoding='utf-8')


def run_node(code):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行选择同步回归')
    result = subprocess.run([executable, '-'], input=code, text=True, encoding='utf-8', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_right_panel_selection_is_persistent_and_posts_matching_pin_selection():
    callbacks = SHELL[SHELL.index('            function onPinFocus('):SHELL.index('            // ---------- 右栏 PRD')]
    run_node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const rows=['n1','n2'].map(id=>{const classes=new Set();return {dataset:{noteId:id},attrs:{},offsetWidth:100,
 classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),toggle:(c,on)=>on?classes.add(c):classes.delete(c),contains:c=>classes.has(c)},
 setAttribute(k,v){this.attrs[k]=v},getBoundingClientRect:()=>({top:20}),closest:()=>({getBoundingClientRect:()=>({top:0}),clientHeight:600})}});
const host={querySelector:selector=>rows.find(r=>selector.includes(r.dataset.noteId)),querySelectorAll:()=>rows};
const context={selectedNoteId:null,current:{page:{id:'home'},stateId:'default'},data:{annotations:rows.map(r=>({id:r.dataset.noteId,pageId:'home',stateId:'default'}))},
 $:()=>host,CSS:{escape:x=>x},post:m=>context.messages.push(m),messages:[],matchMedia:()=>({matches:true})};
vm.createContext(context);vm.runInContext(CALLBACKS,context);
context.onPinFocus('n1');assert.equal(rows[0].classList.contains('selected'),true);assert.equal(rows[0].attrs['aria-current'],'true');
context.reveal(context.data.annotations[1]);assert.equal(rows[0].classList.contains('selected'),false);assert.equal(rows[1].classList.contains('selected'),true);
assert.equal(context.selectedNoteId,'n2');assert.ok(context.messages.some(m=>m.type==='select'&&m.noteId==='n1'));
context.onPinFocus('gone');assert.equal(context.selectedNoteId,null);
'''.replace('CALLBACKS', json.dumps(callbacks)))


def test_bridge_applies_selection_without_reloading_or_scrolling_for_select_message():
    run_node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm');const listeners={},selected=[],scrolls=[];
const parent={postMessage(){}},document={documentElement:{dataset:{}}};
const window={parent,ProtoAnchors:{point:()=>({element:{scrollIntoView:v=>scrolls.push(v)}}),currentIds:()=>({stateId:'default'})},
 __reviewRelayout(){},__reviewSelectNote:id=>selected.push(id),addEventListener:(t,fn)=>listeners[t]=fn};
const context={window,document,setTimeout};vm.createContext(context);vm.runInContext(BRIDGE,context);
listeners.message({source:parent,data:{__review:1,type:'select',noteId:'n1'}});assert.deepEqual(selected,['n1']);assert.equal(scrolls.length,0);
listeners.message({source:{},data:{__review:1,type:'select',noteId:'n2'}});assert.deepEqual(selected,['n1']);
listeners.message({source:parent,data:{__review:1,type:'reveal',note:{id:'n2'}}});assert.deepEqual(selected,['n1','n2']);assert.equal(scrolls.length,1);
'''.replace('BRIDGE', json.dumps(BRIDGE)))
