"""现代原型读取真实状态，保持桥接口及评审导出的一致性。"""
import shutil
import subprocess
from pathlib import Path

import pytest
import proto_meta
import publication_versions
import review_export


ROOT = Path(__file__).resolve().parents[1]


def test_modern_state_getter_syncs_only_registered_states_and_cleans_up():
    node = shutil.which('node')
    if not node:
        pytest.skip('需要 Node.js')
    script = r'''
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const timers=new Map(),events=new Map(),docEvents=new Map();let seq=0,actual='collapsed',fail=false,enters=0;
const root={dataset:{protoPage:'original-html-id',protoState:'default'}};
const original={enter(id){enters++;actual=id;return true;},getState(){if(fail)throw Error('not ready');return actual;}};
const context={document:{documentElement:root,addEventListener:(n,f)=>docEvents.set(n,f),removeEventListener:(n,f)=>{if(docEvents.get(n)===f)docEvents.delete(n);}},
 setInterval:f=>{timers.set(++seq,f);return seq;},clearInterval:id=>timers.delete(id),
 addEventListener:(n,f)=>events.set(n,f),removeEventListener:(n,f)=>{if(events.get(n)===f)events.delete(n);},PrototypeBridge:original};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const config={pageId:'home',states:[{id:'default'},{id:'collapsed'}]}, nav=context.ProtoNavigation;
const observer=nav.init(config);
assert.equal(root.dataset.protoState,'collapsed','initial state must reflect actual UI instead of a forced default');
assert.equal(root.dataset.protoPage,'home');assert.equal(context.PrototypeBridge,original);assert.equal(enters,0);
assert.equal(timers.size,1);const oldTick=[...timers.values()][0];
actual='default';oldTick();assert.equal(root.dataset.protoState,'default');
actual='unknown';oldTick();assert.equal(root.dataset.protoState,'default','do not create undeclared state scopes');
fail=true;oldTick();assert.equal(root.dataset.protoState,'default');fail=false;
actual=Promise.resolve('collapsed');oldTick();assert.equal(root.dataset.protoState,'default','getState is synchronous');
actual='collapsed';oldTick();assert.equal(root.dataset.protoState,'collapsed');
nav.init(config);assert.equal(timers.size,1,'reinit must replace old subscription');
actual='default';oldTick();assert.equal(root.dataset.protoState,'collapsed','destroyed observer cannot affect a new page');
const active=nav.init(config);assert.equal(root.dataset.protoState,'default');active.destroy();assert.equal(timers.size,0);
assert.equal(context.PrototypeBridge,original);assert.equal(events.size,0);assert.equal(docEvents.size,0);
delete context.PrototypeBridge;root.dataset.protoState='collapsed';assert.equal(nav.init(config),null);
assert.equal(root.dataset.protoState,'collapsed');assert.equal(timers.size,0);
'''
    result = subprocess.run([node, '-e', script, str(ROOT/'src/proto-navigation.js')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_review_export_includes_state_reader_for_modern_multi_state_page(tmp_path):
    root = tmp_path/'project'
    root.mkdir()
    (root/'index.html').write_text('<html data-proto-state="default"><button>切换</button><script>window.PrototypeBridge={enter(){},getState(){return "collapsed";}};</script></html>', encoding='utf-8')
    bundle = proto_meta.ensure_bundle(root)
    proto_meta.ensure_pages_registered(root,bundle)
    bundle['project']['pages'][0]['states'].append({'id':'collapsed','title':'已收起','kind':'adapter'})
    out = tmp_path/'review'
    review_export.build_review_export(root,bundle,out)
    html=(out/'proto/index.html').read_text(encoding='utf-8')
    assert 'data-proto-review="navigation-config"' in html
    assert 'window.__PROTO_NAVIGATION__=' in html
    assert 'getState' in html and 'proto-navigation' in (ROOT/'src/viewer.html').read_text(encoding='utf-8')


def test_state_runtime_changes_count_as_publication_content(tmp_path,monkeypatch):
    monkeypatch.setattr(publication_versions,'__file__',str(tmp_path/'publication_versions.py'))
    (tmp_path/'src').mkdir()
    runtime=tmp_path/'src/proto-navigation.js'
    runtime.write_text('/* state reader v1 */',encoding='utf-8')
    before=publication_versions.runtime_version()
    runtime.write_text('/* state reader v2 */',encoding='utf-8')
    assert publication_versions.runtime_version()!=before
