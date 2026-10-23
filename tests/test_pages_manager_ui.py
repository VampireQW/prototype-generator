"""发布管理的筛选、状态与取消发布确认快照。"""
import json
from pathlib import Path
import shutil
import subprocess
import pytest


def run_case(case):
    node=shutil.which('node')
    if not node: pytest.skip('需要 Node.js')
    path=Path(__file__).resolve().parents[1]/'src/pages-manager.js'
    assert path.exists(), '发布管理前端模块尚未实现'
    source=path.read_text(encoding='utf-8')
    harness=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const context={window:{},document:{addEventListener(){}},URL,location:{href:'http://localhost:8080/src/publish.html'},console};
vm.createContext(context);vm.runInContext(SOURCE,context);const api=context.window.PagesManager;
const overview={repository:'owner/repo',head:'v1',usage:{usedBytes:42},projects:[{id:'a',name:'作业',bytes:20,publishedAt:'2026-10-01'},{id:'b',name:'学案',bytes:100,publishedAt:'2026-10-03'},{id:'c',name:'其他',bytes:null}]};
let posts=[],confirmResult=true,fail=false,view;
const controller=api.createController({request:async(action,payload)=>{if(action==='overview')return overview;posts.push(payload);if(fail)throw Error('远端发生变化');return {ok:true,overview:{...overview,head:'v2',projects:overview.projects.filter(row=>row.id!==payload.projectId),usage:{usedBytes:22}}};},confirm:async()=>confirmResult,onChange:value=>view=value});
'''.replace('SOURCE',json.dumps(source))
    result=subprocess.run([node,'-'],input=harness+case,text=True,encoding='utf-8',capture_output=True)
    assert result.returncode==0,result.stderr


def test_filter_sort_and_unavailable_capacity_format():
    run_case(r'''
assert.equal(api.formatBytes(null),'—');assert.equal(api.formatBytes(0),'0 B');
assert.equal(api.formatBytes(1_000_000_000),'1 GB');
assert.deepEqual(Array.from(api.projectRows(overview,'','size'),row=>row.id),['b','a','c']);
assert.deepEqual(Array.from(api.projectRows(overview,'学案','date'),row=>row.id),['b']);
''')


def test_cancelled_confirmation_does_not_send_unpublish():
    run_case(r'''
(async()=>{await controller.load();confirmResult=false;await controller.remove(overview.projects[0]);assert.equal(posts.length,0);assert.equal(view.data.projects.length,3);assert.equal(view.busy,false);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_success_uses_snapshot_and_updates_capacity_and_rows():
    run_case(r'''
(async()=>{await controller.load();await controller.remove(overview.projects[0]);assert.equal(posts[0].repository,'owner/repo');assert.equal(posts[0].expectedHead,'v1');assert.equal(view.data.head,'v2');assert.equal(view.data.usage.usedBytes,22);assert.equal(view.data.projects.length,2);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_failure_preserves_rows_and_reports_error_without_retry():
    run_case(r'''
(async()=>{await controller.load();fail=true;await controller.remove(overview.projects[0]);assert.equal(posts.length,1);assert.equal(view.data.projects.length,3);assert.equal(view.busy,false);assert.ok(view.error.includes('远端发生变化'));})().catch(e=>{console.error(e);process.exitCode=1});
''')
