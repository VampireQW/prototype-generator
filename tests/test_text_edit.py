"""手动文案修改只操作隔离原型，验证精确写入、冲突和撤销。"""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proto_meta
from test_external_api import api

SOURCE = ('<!doctype html>\r\n<html><body><button id="save" data-proto-id="save" onclick="run()">'
          '<i class="icon"></i> 提交 &amp; 保存 </button><table><tr><td>张三</td><td>张三</td></tr></table>'
          '<script>function run(){alert("提交 & 保存")}</script></body></html>')
TARGET = {'tag': 'button', 'protoId': 'save', 'texts': ['提交 & 保存']}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'prototype'; root.mkdir()
    (root / 'index.html').write_bytes(SOURCE.encode())
    bundle = proto_meta.ensure_bundle(root)
    return root, bundle['project']['pages'][0]['id'], importlib.import_module('proto_text_edit')


def inspect(project, target=None):
    root, page, edit = project
    return edit.inspect_text(root, page, target or TARGET)


def save(project, target=None, edits=None, digest=None):
    root, page, edit = project; target = target or TARGET
    return edit.save_text(root, page, target, digest or inspect(project, target)['hash'], edits or [{'slot': 0, 'text': '保存修改'}])


def test_save_replaces_only_text_and_undo_restores_exact_bytes(project):
    root, page, edit = project; bundle = proto_meta.load_bundle(root)
    info = inspect(project); assert info['fields'] == [{'slot': 0, 'text': '提交 & 保存'}]
    result = save(project)
    assert (root/'index.html').read_bytes() == SOURCE.replace(' 提交 &amp; 保存 </button>', ' 保存修改 </button>').encode()
    assert proto_meta.load_bundle(root) == bundle
    assert inspect(project, {**TARGET, 'texts': ['保存修改']})['undoId'] == result['undoId']
    edit.undo_text(root, page, result['undoId'], result['hash'])
    assert (root/'index.html').read_bytes() == SOURCE.encode()


def test_cell_path_handles_implicit_tbody_and_does_not_replace_identical_text_elsewhere(project):
    root, _, _ = project
    target = {'tag': 'td', 'path': [{'tag':'html','index':1}, {'tag':'body','index':1}, {'tag':'table','index':1},
                                 {'tag':'tbody','index':1}, {'tag':'tr','index':1}, {'tag':'td','index':2}], 'texts':['张三']}
    save(project, target, [{'slot':0, 'text':'李四'}])
    assert '<td>张三</td><td>李四</td>' in (root/'index.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('source,target', [
    ('<div id="app"><span id="dynamic">{{ count }}</span></div>', {'tag':'span','id':'dynamic','texts':['12']}),
    ('<table><tr v-for="row in rows"><td id="dynamic">张三</td></tr></table>', {'tag':'td','id':'dynamic','texts':['张三']}),
    ('<button id="x">原文</button>', {'tag':'button','id':'x','texts':['脚本生成的文案']}),
    ('<button id="x">同名</button><button id="x">同名</button>', {'tag':'button','id':'x','texts':['同名']}),
    ('<script id="x">alert(1)</script>', {'tag':'script','id':'x','texts':['alert(1)']}),
])
def test_unsupported_or_ambiguous_targets_never_write(project, source, target):
    root, _, edit = project; (root/'index.html').write_text(source, encoding='utf-8')
    before=(root/'index.html').read_bytes()
    with pytest.raises(edit.UnsupportedText): inspect(project,target)
    assert (root/'index.html').read_bytes()==before


def test_save_rejects_external_changes_and_escapes_text(project):
    root, _, edit=project; info=inspect(project)
    (root/'index.html').write_bytes((SOURCE+'<!-- Agent 的修改 -->').encode())
    with pytest.raises(edit.EditConflict): save(project,digest=info['hash'])
    assert b'Agent' in (root/'index.html').read_bytes()
    result=save(project,edits=[{'slot':0,'text':'<img src=x onerror=alert(1)>'}])
    source=(root/'index.html').read_text(encoding='utf-8')
    assert '&lt;img src=x onerror=alert(1)&gt;' in source and '<img src=x' not in source
    assert result['hash'] != info['hash']


def test_undo_will_not_overwrite_later_agent_changes(project):
    root, page, edit=project; result=save(project)
    (root/'index.html').write_bytes((root/'index.html').read_bytes()+b'<!-- later -->')
    with pytest.raises(edit.EditConflict): edit.undo_text(root,page,result['undoId'],result['hash'])
    assert (root/'index.html').read_bytes().endswith(b'<!-- later -->')


def test_multiple_text_parts_update_atomically_and_keep_nested_tags(project):
    root, _, _=project
    source='<button id="multi">保存 <strong>草稿</strong><svg><title>图标</title><path/></svg></button>'
    (root/'index.html').write_text(source,encoding='utf-8')
    target={'tag':'button','id':'multi','texts':['保存','草稿']}
    save(project,target,[{'slot':0,'text':'提交'},{'slot':1,'text':'审核'}])
    assert (root/'index.html').read_text(encoding='utf-8')=='<button id="multi">提交 <strong>审核</strong><svg><title>图标</title><path/></svg></button>'


def test_failed_atomic_write_leaves_html_and_prd_unchanged(project,monkeypatch):
    root, _, edit=project; before=proto_meta.load_bundle(root)
    def fail_replace(*args): raise OSError('模拟写入失败')
    monkeypatch.setattr(edit.os,'replace',fail_replace)
    with pytest.raises(OSError):save(project)
    assert (root/'index.html').read_bytes()==SOURCE.encode() and proto_meta.load_bundle(root)==before


def test_invalid_page_and_traversal_cannot_edit_other_files(project):
    root, page, edit=project
    with pytest.raises(ValueError): edit.inspect_text(root,'../index.html',TARGET)
    with pytest.raises(ValueError): edit.undo_text(root,page,'../outside','anything')
    bundle=proto_meta.load_bundle(root);bundle['project']['pages'][0]['trashedAt']='2026-10-20';bundle['revision']+=1;proto_meta.save_bundle(root,bundle)
    with pytest.raises(ValueError): edit.inspect_text(root,page,TARGET)


@pytest.mark.parametrize('target', [
    {'tag': [], 'texts': ['提交 & 保存']},
    {'tag': 'button', 'path': [None], 'texts': ['提交 & 保存']},
])
def test_malformed_locator_is_rejected_without_writing(project, target):
    root, _, edit = project
    with pytest.raises(edit.UnsupportedText): inspect(project, target)
    assert (root/'index.html').read_bytes() == SOURCE.encode()


def test_malformed_edit_is_rejected_without_writing(project):
    root, _, _ = project
    with pytest.raises(ValueError): save(project, edits=['not an edit object'])
    assert (root/'index.html').read_bytes() == SOURCE.encode()


def test_http_manual_text_routes_are_local_and_persist_to_registered_page(api,tmp_path):
    root=tmp_path/'registered';root.mkdir();(root/'index.html').write_bytes(SOURCE.encode())
    pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    bundle=api.request('/api/proto/read?projectId='+pid)[1]['bundle'];page=bundle['project']['pages'][0]['id']
    payload={'projectId':pid,'pageId':page,'target':TARGET}
    assert api.request('/api/proto/text/inspect',payload,{'Origin':'https://evil.example'})[0]==403
    status,info=api.request('/api/proto/text/inspect',payload);assert status==200,info
    status,result=api.request('/api/proto/text/save',{**payload,'expectedHash':info['hash'],'edits':[{'slot':0,'text':'确定'}]})
    assert status==200,result
    assert api.request('/api/proto/text/undo',{**payload,'expectedHash':result['hash'],'undoId':result['undoId']})[0]==200
    assert (root/'index.html').read_bytes()==SOURCE.encode()


DYNAMIC_SOURCE = '''<!doctype html><html><body><div id="pillTrack"></div>
<script>const rows=[{id:'q1',label:'同名标签'},{id:'q2',label:'同名标签'}];
function render(){document.getElementById('pillTrack').innerHTML=rows.map(q=>
'<span data-q="'+q.id+'" onclick="render()">'+q.label+'</span>').join('')}render();</script></body></html>'''
DYNAMIC_TARGET = {'tag': 'span', 'texts': ['同名标签'], 'path': [
    {'tag':'html','index':1}, {'tag':'body','index':1}, {'tag':'div','index':1}, {'tag':'span','index':2}],
    'bindings': [{'anchor': {'tag':'div','key':'id','value':'pillTrack'},
                  'path': [{'tag':'span','key':'data-q','value':'q2'}]}]}


def test_script_rendered_label_saves_per_control_and_undo_restores_source(project):
    root, page, edit = project
    (root/'index.html').write_bytes(DYNAMIC_SOURCE.encode())
    bundle = proto_meta.load_bundle(root)
    info = inspect(project, DYNAMIC_TARGET)
    assert info['fields'] == [{'slot':0, 'text':'同名标签'}]
    result = save(project, DYNAMIC_TARGET, [{'slot':0,'text':'新标签 </script><img onerror="run()">'}])
    after = (root/'index.html').read_text(encoding='utf-8')
    assert "label:'同名标签'" in after and "onclick=\"render()\"" in after
    assert len(result['runtimeEdits']) == 1
    assert result['runtimeEdits'][0]['binding']['path'][0]['value'] == 'q2'
    assert '</script><img' not in after
    assert proto_meta.load_bundle(root) == bundle
    updated = {**DYNAMIC_TARGET, 'texts': [result['fields'][0]['text']]}
    assert inspect(project, updated)['undoId'] == result['undoId']
    edit.undo_text(root, page, result['undoId'], result['hash'])
    assert (root/'index.html').read_bytes() == DYNAMIC_SOURCE.encode()


def test_dynamic_label_can_be_edited_twice_without_stacking_runtime(project):
    root, _, _ = project; (root/'index.html').write_text(DYNAMIC_SOURCE,encoding='utf-8')
    first = save(project,DYNAMIC_TARGET,[{'slot':0,'text':'第一次'}])
    second = save(project,{**DYNAMIC_TARGET,'texts':['第一次']},[{'slot':0,'text':'第二次'}])
    assert len(second['runtimeEdits']) == 1
    assert second['runtimeEdits'][0]['before'] == ['同名标签']
    assert second['runtimeEdits'][0]['after'] == ['第二次']
    assert (root/'index.html').read_text(encoding='utf-8').count('<!-- proto-text-edits:start -->') == 1
    assert second['hash'] != first['hash']


@pytest.mark.parametrize('source,binding', [
    (DYNAMIC_SOURCE, {'anchor':{'tag':'div','key':'id','value':'missing'}, 'path':[{'tag':'span','key':'data-q','value':'q2'}]}),
    (DYNAMIC_SOURCE, {'anchor':{'tag':'div','key':'id','value':'pillTrack'}, 'path':[{'tag':'span','index':2}]}),
    (DYNAMIC_SOURCE.replace('<div id="pillTrack"></div>', '<div id="pillTrack"><span data-q="q2">已被 AI 改动</span></div>'), DYNAMIC_TARGET['bindings'][0]),
    (DYNAMIC_SOURCE.replace('id="pillTrack"','id="pillTrack" v-for="item in items"'), DYNAMIC_TARGET['bindings'][0]),
    (DYNAMIC_SOURCE.replace('<div id="pillTrack"></div>','<div id="pillTrack"></div><div id="pillTrack"></div>'), DYNAMIC_TARGET['bindings'][0]),
])
def test_dynamic_fallback_requires_stable_unique_binding_and_never_masks_source_conflicts(project,source,binding):
    root, _, edit = project; (root/'index.html').write_bytes(source.encode())
    with pytest.raises(edit.UnsupportedText): inspect(project,{**DYNAMIC_TARGET,'bindings':[binding]})
    assert (root/'index.html').read_bytes() == source.encode()


def test_dynamic_text_override_is_portable_in_both_export_versions(project,tmp_path):
    import review_export
    root, _, _ = project; (root/'index.html').write_text(DYNAMIC_SOURCE,encoding='utf-8')
    save(project,DYNAMIC_TARGET,[{'slot':0,'text':'导出后的标签'}])
    bundle = proto_meta.load_bundle(root)
    for name,builder,file in [('pure',review_export.build_pure_export,'index.html'),
                              ('review',review_export.build_review_export,'proto/index.html')]:
        out=tmp_path/name; builder(root,bundle,out)
        content=(out/file).read_text(encoding='utf-8')
        assert '导出后的标签' in content and 'data-proto-text-runtime' in content
        assert 'window.ProtoTextRuntime = { bindings, install }' in content
        assert not (out/'.prototype/text-edits').exists()


def test_dynamic_table_cell_without_row_ids_uses_row_text_and_column_header(project):
    root,page,edit=project
    source='<html><body><table><thead><tr><th>班级</th><th>良好人数</th></tr></thead><tbody id="rows"></tbody></table><script>/* rows rendered by JS */</script></body></html>'
    (root/'index.html').write_bytes(source.encode())
    target={'tag':'td','texts':['16'],'bindings':[{'anchor':{'tag':'tbody','key':'id','value':'rows'},'path':[
        {'tag':'tr','match':[{'path':[{'tag':'td','index':1}],'text':'6'}]},
        {'tag':'td','column':['良好人数']}]}]}
    result=save(project,target,[{'slot':0,'text':'18'}])
    assert result['runtimeEdits'][0]['binding']==target['bindings'][0]
    assert inspect(project,{**target,'texts':['18']})['fields']==[{'slot':0,'text':'18'}]
    edit.undo_text(root,page,result['undoId'],result['hash'])
    assert (root/'index.html').read_bytes()==source.encode()


def test_dynamic_list_without_ids_uses_body_and_unedited_item_heading(project):
    root,_,_=project
    (root/'index.html').write_text('<html><body><ul></ul><script>/* list rendered by JS */</script></body></html>',encoding='utf-8')
    target={'tag':'button','texts':['查看'],'bindings':[{'anchor':{'tag':'body'},'path':[
        {'tag':'ul','index':1},{'tag':'li','match':[{'path':[{'tag':'h3','index':1}],'text':'作业A'}]},{'tag':'button','index':1}]}]}
    assert save(project,target,[{'slot':0,'text':'查看详情'}])['fields']==[{'slot':0,'text':'查看详情'}]


def test_workbench_upgrades_old_runtime_in_response_without_rewriting_source(api,tmp_path):
    import proto_text_edit as edit
    root=tmp_path/'old-runtime';root.mkdir()
    (root/'index.html').write_text(DYNAMIC_SOURCE,encoding='utf-8')
    bundle=proto_meta.ensure_bundle(root);page=bundle['project']['pages'][0]['id']
    result=edit.save_text(root,page,DYNAMIC_TARGET,edit.inspect_text(root,page,DYNAMIC_TARGET)['hash'],[{'slot':0,'text':'保留文案'}])
    text=(root/'index.html').read_text(encoding='utf-8')
    import re
    old=re.sub(r'<script data-proto-text-runtime>.*?</script>','<script data-proto-text-runtime>/* old runtime */</script>',text,flags=re.S)
    (root/'index.html').write_bytes(old.encode())
    pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    code,response=api.request('/ext/'+pid+'/index.html')
    assert code==200 and 'function headerPaths' in response and '保留文案' in response
    assert '/* old runtime */' not in response
    assert (root/'index.html').read_bytes()==old.encode()
