"""发布壳与 iframe 必须按导出内容版本配套，不能命中旧 HTML 缓存。"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import review_export


def export_fixture(tmp_path, out_name='out'):
    root = tmp_path / 'project'
    root.mkdir(exist_ok=True)
    (root / 'index.html').write_text('<html data-proto-page="home"><body><button>示例</button></body></html>', encoding='utf-8')
    bundle = {'revision': 1, 'project': {'id': 'example', 'name': '示例', 'pages': [
        {'id': 'home', 'title': '首页', 'file': 'index.html', 'states': [{'id': 'default'}]}]},
        'prd': {'documents': [], 'annotations': []}}
    out = tmp_path / out_name
    review_export.build_review_export(root, bundle, out, published_at='2026-10-22T10:00:00Z')
    shell = (out / 'index.html').read_text(encoding='utf-8')
    payload = shell.split('<script type="application/json" id="review-data">', 1)[1].split('</script>', 1)[0]
    return out, json.loads(payload)


def test_prototype_version_hashes_final_html_including_review_runtime(tmp_path):
    out, data = export_fixture(tmp_path)
    expected = hashlib.sha256((out / 'proto/index.html').read_bytes()).hexdigest()[:20]
    assert data.get('prototypeVersions', {}).get('index.html') == expected
    assert str(tmp_path) not in json.dumps(data)


def test_review_runtime_update_changes_version_without_a_prd_revision_change(tmp_path, monkeypatch):
    _, before = export_fixture(tmp_path, 'before')
    original = review_export.load_bundle_scripts
    monkeypatch.setattr(review_export, 'load_bundle_scripts', lambda: original() + '<script data-proto-review="test-update">/* 更新 */</script>')
    _, after = export_fixture(tmp_path, 'after')
    assert before['revision'] == after['revision']
    assert before.get('prototypeVersions') and before['prototypeVersions'] != after.get('prototypeVersions')
    _, repeat = export_fixture(tmp_path, 'repeat')
    assert after['prototypeVersions'] == repeat['prototypeVersions']


def test_frame_and_open_original_link_use_same_version_but_state_change_keeps_frame():
    source = review_export.SHELL_TEMPLATE.read_text(encoding='utf-8')
    helpers = source[source.index('            const safePath ='):source.index('            /* file:// 下 iframe')]
    navigation = source[source.index('            function selectPage('):source.index('            // ---------- 原型页握手')]
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js 执行发布 URL 回归')
    code = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const page={id:'home',title:'示例',file:'pages/示例 页.html',states:[{id:'default'},{id:'done'}]};
const version='1234567890abcdef1234',data={prototypeVersions:{[page.file]:version}};
const nodes={scope:{},source:{removeAttribute(){}},tree:{querySelectorAll:()=>[]},empty:{}};
const context={data,frame:{src:'',hidden:true},current:{page:null,stateId:null},loadedFile:null,frameReady:false,pendingState:null,orders:{},
 buildTree(){},renderAside(){},ProtoProjectNavigation:{applyPreview(){}},$:id=>nodes[id],history:{replaceState(){}},URLSearchParams,post:msg=>context.messages.push(msg),messages:[]};
vm.createContext(context);vm.runInContext(HELPERS+NAVIGATION,context);
context.selectPage(page,'default');
assert.equal(context.frame.src,'proto/pages/%E7%A4%BA%E4%BE%8B%20%E9%A1%B5.html?v='+version);
assert.equal(nodes.source.href,context.frame.src);
context.frameReady=true;const first=context.frame.src;context.selectPage(page,'done');
assert.equal(context.frame.src,first);assert.equal(context.messages[0].type,'enterState');
// 旧清单无版本时继续可用；版本字段不能注入 URL 查询或片段。
context.loadedFile=null;context.data.prototypeVersions[page.file]='bad#fragment';context.selectPage(page,'default');
assert.equal(context.frame.src,'proto/pages/%E7%A4%BA%E4%BE%8B%20%E9%A1%B5.html');
'''.replace('HELPERS', json.dumps(helpers)).replace('NAVIGATION', json.dumps(navigation))
    result = subprocess.run([executable, '-'], input=code, text=True, encoding='utf-8', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
