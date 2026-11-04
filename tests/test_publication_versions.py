"""发布快照与事实差异；仅写临时项目，不接触真实发布与凭据。"""
import copy
import importlib
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module():
    return importlib.import_module('publication_versions')


def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'index.html').write_text('<html><head><link rel="stylesheet" href="shared.css"></head><body><button data-proto-id="save">保存</button></body></html>', encoding='utf-8')
    (root / 'details.html').write_text('<html><link rel="stylesheet" href="shared.css"><h1>详情</h1></html>', encoding='utf-8')
    (root / 'shared.css').write_text('button{color:blue}', encoding='utf-8')
    bundle = {'revision': 1, 'project': {'id': 'p-fixture', 'name': '样例', 'pages': [
        {'id':'home','title':'首页','file':'index.html','states':[{'id':'default','title':'默认'}]},
        {'id':'details','title':'详情','file':'details.html','states':[{'id':'default','title':'默认'}]}]},
        'prd': {'documents': [], 'annotations': [{'id':'note-one','pageId':'home','stateId':'default','number':1,
            'body':'保存后展示结果。','anchor':{'protoId':'save'},'placement':{'kind':'element','x':0,'y':0},'updatedAt':'old'}]},
        'changes': {'items': []}}
    return root, bundle


def test_text_change_lists_only_affected_element_and_page(tmp_path):
    root, bundle = project(tmp_path)
    before = module().capture(root, bundle)
    path = root / 'index.html'
    path.write_text(path.read_text(encoding='utf-8').replace('>保存<','>确认保存<'), encoding='utf-8')
    after = module().capture(root, bundle)
    rows = module().compare(before, after)
    assert len(rows) == 1
    assert rows[0]['kind'] == 'text' and rows[0]['before'] == '保存' and rows[0]['after'] == '确认保存'
    assert rows[0]['target']['pageId'] == 'home' and rows[0]['target']['anchor']['protoId'] == 'save'
    assert before['contentVersion'] != after['contentVersion']


def test_revision_timestamp_and_display_number_are_not_content_changes(tmp_path):
    root, bundle = project(tmp_path)
    before = module().capture(root, bundle)
    bundle['revision'] += 1
    bundle['prd']['annotations'][0].update(number=9, updatedAt='new')
    after = module().capture(root, bundle)
    assert after['contentVersion'] == before['contentVersion']
    assert module().compare(before, after) == []


def test_annotation_content_is_documentation_not_implementation(tmp_path):
    root, bundle = project(tmp_path)
    before = module().capture(root, bundle)
    bundle['prd']['annotations'][0]['body'] = '保存后展示结果，并显示操作时间。'
    rows = module().compare(before, module().capture(root,bundle))
    assert len(rows) == 1 and rows[0]['kind'] == 'annotation'
    assert rows[0]['target']['noteId'] == 'note-one'
    assert '标注' in rows[0]['description']


def test_shared_resource_change_is_one_row_with_affected_pages(tmp_path):
    root, bundle = project(tmp_path)
    before = module().capture(root,bundle)
    (root/'shared.css').write_text('button{color:red}', encoding='utf-8')
    rows = module().compare(before,module().capture(root,bundle))
    assert len(rows) == 1 and rows[0]['kind'] == 'style'
    assert set(rows[0]['affectedPages']) == {'home','details'}


def test_initial_baseline_has_one_row_per_page_not_every_element(tmp_path):
    root, bundle = project(tmp_path)
    rows = module().compare(None,module().capture(root,bundle))
    assert len(rows) == 2 and all(row['kind'] == 'page-added' for row in rows)


def test_prepare_does_not_advance_baseline_and_failed_publish_keeps_it(tmp_path):
    root, bundle = project(tmp_path)
    target = {'owner':'fixture','repo':'repo','branch':'main','remoteId':'p-fixture'}
    first = module().prepare(root,bundle,target,published_at='2026-11-03 15:00:00')
    assert module().load_state(root,target) is None
    module().commit(root,target,first)
    saved = module().load_state(root,target)
    assert saved['snapshot']['contentVersion'] == first['snapshot']['contentVersion']
    second = module().prepare(root,bundle,target,published_at='2026-11-03 16:00:00')
    assert second['release']['contentVersion'] == first['release']['contentVersion']
    assert second['changes']['items'] == []
    assert module().load_state(root,target)['release']['releaseId'] == saved['release']['releaseId']
    assert module().load_state(root,{**target,'repo':'another'}) is None


def test_draft_only_edits_descriptions_and_rejects_stale_sources(tmp_path):
    root,bundle=project(tmp_path)
    target={'owner':'o','repo':'r','branch':'main','remoteId':'p'}
    publication=module().prepare(root,bundle,target)
    row=publication['changes']['items'][0]
    module().save_draft(root,target,publication['snapshot']['contentVersion'],{row['id']:'新增首页入口'})
    again=module().prepare(root,bundle,target)
    assert again['changes']['items'][0]['description'] == '新增首页入口'
    assert again['changes']['items'][0]['target'] == row['target']
    with pytest.raises(ValueError):
        module().save_draft(root,target,'stale',{row['id']:'不应保存'})


def test_removed_element_produces_deleted_target_not_fake_locator(tmp_path):
    root,bundle=project(tmp_path)
    before=module().capture(root,bundle)
    (root/'index.html').write_text('<html><body></body></html>',encoding='utf-8')
    rows=module().compare(before,module().capture(root,bundle))
    assert any(row['kind']=='element-removed' and row['target']['deleted'] for row in rows)


def test_snapshot_never_reads_private_or_own_history_as_content(tmp_path):
    root,bundle=project(tmp_path)
    before=module().capture(root,bundle)
    (root/'.env').write_text('SECRET=private',encoding='utf-8')
    (root/'models.json').write_text('{"api_key":"private"}',encoding='utf-8')
    (root/'.prototype/releases').mkdir(parents=True)
    (root/'.prototype/releases/old.json').write_text('history',encoding='utf-8')
    after=module().capture(root,bundle)
    assert after['contentVersion']==before['contentVersion']
    assert 'private' not in json.dumps(after)


def test_dynamic_manual_text_rules_have_real_before_after_and_stable_target(tmp_path):
    root,bundle=project(tmp_path)
    before=module().capture(root,bundle)
    rule={'binding':{'anchor':{'tag':'table','key':'id','value':'results'},'path':[{'tag':'td','column':['优秀人数']}]},
          'before':['16'],'after':['18']}
    path=root/'index.html'
    path.write_text(path.read_text(encoding='utf-8')+'<script type="application/json" id="proto-text-edits-data">'+json.dumps([rule])+'</script><script data-proto-text-runtime>ignored runtime</script>',encoding='utf-8')
    rows=module().compare(before,module().capture(root,bundle))
    assert len(rows)==1 and rows[0]['kind']=='text'
    assert (rows[0]['before'],rows[0]['after'])==('16','18')
    assert json.loads(rows[0]['target']['anchor']['textRule'])==rule['binding']


def test_reserved_publication_names_are_not_silently_overwritten(tmp_path):
    root,bundle=project(tmp_path)
    (root/module().MANIFEST).write_text('user file',encoding='utf-8')
    with pytest.raises(ValueError,match='名称冲突'): module().capture(root,bundle)


def test_local_snapshots_retain_ten_and_pure_has_no_public_prd(tmp_path):
    root,bundle=project(tmp_path); target={'owner':'o','repo':'r','branch':'main','remoteId':'p'}
    for i in range(12):
        bundle['prd']['annotations'][0]['body']='规则'+str(i)
        pub=module().prepare(root,bundle,target)
        module().commit(root,target,pub)
    state=module().load_state(root,target)
    assert len(state['history'])==10
    assert len(list(module()._folder(root,target).glob('snapshots/*.json.gz')))==10
    pure=module().prepare(root,bundle,target,mode='pure')
    out=tmp_path/'pure';out.mkdir();files=module().write_publication(out,pure)
    assert files==[module().MANIFEST]
    assert '规则' not in (out/module().MANIFEST).read_text(encoding='utf-8')


def test_remote_protocol_baseline_can_restore_after_local_state_lost(tmp_path):
    from test_release_publish import PublishingRemote,write
    import github_pages
    root,bundle=project(tmp_path); target={'owner':'test-owner','repo':'fixture-repo','branch':'main','remoteId':'a'}
    pub=module().prepare(root,bundle,target)
    out=tmp_path/'site';out.mkdir();module().write_publication(out,pub)
    write(out,'index.html','shell')
    remote=PublishingRemote();github_pages.publish_directory(remote,target['owner'],target['repo'],'main',out,'projects/a')
    recovered=module().remote_baseline(remote,target)
    assert recovered['snapshot']['contentVersion']==pub['snapshot']['contentVersion']
    assert module().compare(recovered['snapshot'],module().capture(root,bundle))==[]


def test_nested_leaf_text_is_not_missed_or_reported_twice(tmp_path):
    root,bundle=project(tmp_path);file=root/'index.html'
    file.write_text('<body><div><strong>说明正文</strong></div><p><strong>段落正文</strong></p></body>',encoding='utf-8')
    before=module().capture(root,bundle)
    file.write_text(file.read_text(encoding='utf-8').replace('正文','更新'),encoding='utf-8')
    rows=module().compare(before,module().capture(root,bundle))
    assert len(rows)==2 and all(r['kind']=='text' for r in rows)


def test_no_change_republish_does_not_fill_change_history(tmp_path):
    root,bundle=project(tmp_path);target={'owner':'o','repo':'r','branch':'main','remoteId':'p'}
    first=module().prepare(root,bundle,target);module().commit(root,target,first)
    for _ in range(3):module().commit(root,target,module().prepare(root,bundle,target))
    state=module().load_state(root,target)
    assert len(state['history'])==1
    assert state['release']['sequence']==4


def test_text_target_keeps_declared_state(tmp_path):
    root,bundle=project(tmp_path);bundle['project']['pages'][0]['states'].append({'id':'expanded','title':'展开'})
    path=root/'index.html';path.write_text('<section data-proto-state="expanded"><button id="confirm">确认</button></section>',encoding='utf-8')
    before=module().capture(root,bundle)
    path.write_text(path.read_text(encoding='utf-8').replace('>确认<','>确定<'),encoding='utf-8')
    rows=module().compare(before,module().capture(root,bundle))
    assert len(rows)==1 and rows[0]['target']['stateId']=='expanded'
