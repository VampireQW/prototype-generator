"""真实文案编辑器、HTTP 接口与原型重载；只写隔离项目，不调用 AI/GitHub。"""
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import proto_meta
import review_export
from test_external_api import api

sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright
ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''<!doctype html><html><meta charset="utf-8"><body>
<div id="classes"></div><button id="rerender" onclick="render()">重新绘制</button>
<output id="clicked">0</output><script>
const labels=[['c1','高三31班'],['c2','高三35班']];
function render(){document.getElementById('classes').innerHTML=labels.map(([key,label])=>
'<button data-key="'+key+'">'+label+'</button>').join('');
document.querySelectorAll('#classes button').forEach(button=>button.onclick=()=>document.getElementById('clicked').textContent++)}
render();</script></body></html>'''


def test_manual_agent_reload_recover_and_export_end_to_end(api, tmp_path):
    root = tmp_path / 'prototype'
    root.mkdir()
    path = root / 'index.html'
    path.write_bytes(SOURCE.encode('utf-8'))
    status, registered = api.request('/api/external/add', {'path': str(root)})
    assert status == 200
    project_id = registered['projectId']
    bundle = proto_meta.load_bundle(root)
    page_id = bundle['project']['pages'][0]['id']
    origin = f'http://127.0.0.1:{api.port}'
    harness = '''<!doctype html><html><meta charset="utf-8">
<style>body{font:14px sans-serif;background:#f3f4f6}iframe{width:95%;height:150px}
#editor{background:white;padding:20px;max-width:420px}textarea{display:block;width:360px}
button{margin:6px;padding:8px} [hidden]{display:none!important}</style>
<iframe id="prototype"></iframe><button id="select">选择第二个班级</button><div id="editor"></div>
<script src="/src/proto-text-runtime.js"></script><script src="/src/proto-text-edit.js"></script>
<script>const scope=SCOPE;const frame=document.getElementById('prototype');frame.src=FRAME;
const editor=ProtoTextEdit.create({container:document.getElementById('editor'),scope:()=>scope,
request:async(action,payload)=>{const response=await fetch('/api/proto/text/'+action,{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});return response.json();}});
document.getElementById('select').onclick=()=>editor.select([frame.contentDocument.querySelector('[data-key="c2"]')]);
</script></html>'''
    import json
    harness = harness.replace('SCOPE', json.dumps({'projectId': project_id, 'pageId': page_id}))
    harness = harness.replace('FRAME', json.dumps('/ext/' + project_id + '/index.html'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        context.route('**/harness', lambda route: route.fulfill(content_type='text/html', body=harness))
        context.route('**/src/*.js*', lambda route: route.fulfill(
            content_type='application/javascript', path=str(ROOT / 'src' / urlsplit(route.request.url).path.rsplit('/', 1)[-1])))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(origin + '/harness')
        frame = page.frame_locator('#prototype')
        selected = frame.locator('[data-key="c2"]')
        field = page.locator('[data-role="text"]')
        save = page.locator('[data-role="save"]')

        def reopen(expected):
            page.reload()
            selected.wait_for()
            page.wait_for_function("text=>document.querySelector('iframe').contentDocument.querySelector('[data-key=c2]')?.textContent===text", arg=expected)
            page.locator('#select').click()
            page.wait_for_function("text=>document.querySelector('[data-role=text]').value===text", arg=expected)
            assert field.input_value() == expected
            assert field.is_enabled()

        reopen('高三35班')
        field.fill('手动班级名称')
        save.click()
        page.locator('[data-role="status"]').filter(has_text='已保存到').wait_for()
        path.write_bytes(path.read_bytes() + b'<!-- unrelated Agent change -->')
        reopen('手动班级名称')
        assert page.locator('[data-role="recover"]').is_hidden()
        path.write_bytes(path.read_bytes().replace('高三35班'.encode(), 'Agent 新班级名称'.encode(), 1))
        reopen('Agent 新班级名称')
        assert '上次手动修改未应用' in page.locator('[data-role="status"]').inner_text()
        recover = page.locator('[data-role="recover"]')
        recover.click()
        assert selected.inner_text() == '手动班级名称'
        page.locator('[data-role="cancel"]').click()
        assert selected.inner_text() == 'Agent 新班级名称'
        recover.click()
        save.click()
        page.locator('[data-role="status"]').filter(has_text='已保存到').wait_for()
        reopen('手动班级名称')
        field.fill('再次修改成功')
        save.click()
        page.locator('[data-role="status"]').filter(has_text='已保存到').wait_for()
        reopen('再次修改成功')
        frame.locator('#rerender').click()
        assert selected.inner_text() == '再次修改成功'
        assert frame.locator('[data-key="c1"]').inner_text() == '高三31班'
        selected.click()
        assert frame.locator('#clicked').inner_text() == '1'
        page.screenshot(path=str(tmp_path / 'text-rebase-recovered.png'), full_page=True)
        for name, builder, entry in [('pure', review_export.build_pure_export, 'index.html'),
                                     ('review', review_export.build_review_export, 'proto/index.html')]:
            out = tmp_path / name
            builder(root, proto_meta.load_bundle(root), out)
            exported = context.new_page()
            exported.goto((out / entry).as_uri())
            exported.wait_for_function("document.querySelector('[data-key=c2]')?.textContent==='再次修改成功'")
            assert exported.locator('[data-key="c1"]').inner_text() == '高三31班'
            exported.close()
        assert not errors, errors
        context.close()
        browser.close()
