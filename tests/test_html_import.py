"""HTML 导入只使用隔离项目，保持原文和资源相对关系。"""
import base64
import copy
import importlib
from pathlib import Path

import pytest
import proto_meta
import page_lifecycle
import review_export
from test_external_api import api, prototype


def asset(path, raw):
    if isinstance(raw,str):raw=raw.encode('utf-8')
    return {'path':path,'dataUrl':'data:application/octet-stream;base64,'+base64.b64encode(raw).decode()}


@pytest.fixture
def project(tmp_path):
    root=prototype(tmp_path/'project');bundle=proto_meta.ensure_bundle(root)
    return root,bundle,importlib.import_module('html_import')


def payload(bundle, **extra):
    return {'expectedRevision':bundle['revision'],'title':'补充页面','previewType':'pad','entryFile':'index.html',
            'files':[asset('index.html','<!doctype html><title>原始标题</title><link rel="stylesheet" href="assets/style.css"><button onclick="alert(1)">提交</button>'),asset('assets/style.css','button {color: blue}')],**extra}


def test_import_preserves_source_and_assets_without_generating_prd(project):
    root,bundle,mod=project;data=payload(bundle)
    result=mod.import_page(root,data);page=result['page']
    assert page['previewType']=='pad' and len(result['bundle']['project']['pages'])==2
    assert (root/page['file']).read_bytes()==base64.b64decode(data['files'][0]['dataUrl'].split(',')[1])
    assert (root/Path(page['file']).parent/'assets/style.css').read_text()=='button {color: blue}'
    assert result['bundle']['prd']==bundle['prd']
    reread=proto_meta.load_bundle(root);proto_meta.ensure_pages_registered(root,reread)
    assert len(reread['project']['pages'])==2
    with pytest.raises(mod.RevisionConflict):mod.import_page(root,data)


@pytest.mark.parametrize('path',['../escape.js','/absolute.js','C:/outside.js','.prototype/x.json','assets/../x.js','assets/private.py','assets/CON.js','assets/name. /x.js'])
def test_bad_package_paths_never_write(project,path):
    root,bundle,mod=project;before=sorted(str(p) for p in root.rglob('*') if p.is_file())
    data=payload(bundle);data['files'].append(asset(path,'bad'))
    with pytest.raises(ValueError):mod.import_page(root,data)
    assert sorted(str(p) for p in root.rglob('*') if p.is_file())==before


def test_failed_save_rolls_back_only_new_files(project,monkeypatch):
    root,bundle,mod=project;before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(proto_meta,'save_bundle',lambda *a:(_ for _ in ()).throw(OSError('full')))
    with pytest.raises(OSError):mod.import_page(root,payload(bundle))
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}==before


def test_parent_and_duplicate_source_names_are_safe(project):
    root,bundle,mod=project;parent=bundle['project']['pages'][0]['id']
    one=mod.import_page(root,payload(bundle,parentId=parent));two=mod.import_page(root,payload(one['bundle']))
    assert one['page']['parentId']==parent and one['page']['file']!=two['page']['file']
    assert (root/'index.html').read_text(encoding='utf-8').startswith('<title>隔离样例')


def test_empty_resource_is_allowed_and_only_htm_entry_can_export(project,tmp_path):
    root,bundle,mod=project;data=payload(bundle,entryFile='detail.htm',files=[asset('detail.htm','<title>详情</title><h1>详情</h1>'),asset('assets/empty.js',b'')])
    result=mod.import_page(root,data);home=bundle['project']['pages'][0]
    active=page_lifecycle.change_page(root,home['id'],'trash',result['bundle']['revision'])
    out=tmp_path/'only-htm';review_export.build_pure_export(root,active,out)
    assert (out/result['page']['file']).exists() and (out/'index.html').exists()


def test_non_utf8_html_returns_actionable_error_without_writing(project):
    root,bundle,mod=project
    with pytest.raises(ValueError,match='UTF-8'):
        mod.import_page(root,payload(bundle,files=[asset('index.html','<title>中文</title>'.encode('gbk'))]))
    assert proto_meta.load_bundle(root)==bundle


def test_export_trash_restore_and_permanent_delete_include_owned_resources(project,tmp_path):
    root,bundle,mod=project;result=mod.import_page(root,payload(bundle));page=result['page'];image=Path(page['file']).parent/'assets/style.css'
    for mode in ('review','pure'):
        out=tmp_path/mode;getattr(review_export,'build_'+mode+'_export')(root,result['bundle'],out)
        target=out/'proto' if mode=='review' else out
        assert (target/page['file']).exists() and (target/image).exists()
    trashed=page_lifecycle.change_page(root,page['id'],'trash',result['bundle']['revision'])
    out=tmp_path/'trashed';review_export.build_pure_export(root,trashed,out)
    assert not (out/page['file']).exists() and not (out/image).exists()
    restored=page_lifecycle.change_page(root,page['id'],'restore',trashed['revision'])
    trashed=page_lifecycle.change_page(root,page['id'],'trash',restored['revision'])
    page_lifecycle.change_page(root,page['id'],'delete',trashed['revision'],page['file'])
    assert not (root/page['file']).exists() and not (root/image).exists() and (root/'index.html').exists()


def test_api_import_and_generic_save_cannot_change_owned_paths(api,tmp_path):
    root=prototype(tmp_path/'project');_,registered=api.request('/api/external/add',{'path':str(root)})
    bundle=proto_meta.load_bundle(root);pid=registered['projectId']
    status,result=api.request('/api/proto/import-html',{'projectId':pid,**payload(bundle)})
    assert status==200 and result['ok']
    current=result['bundle'];current['project']['pages'][-1]['htmlImport']['files'].append('index.html')
    status,_=api.request('/api/proto/save',{'projectId':pid,'expectedRevision':current['revision'],'bundle':current})
    assert status==400


def test_reimport_replaces_owned_files_and_preserves_page_identity_prd_and_hotspots(project,tmp_path):
    root,bundle,mod=project
    initial=mod.import_page(root,payload(bundle));bundle=initial['bundle'];page=bundle['project']['pages'][-1]
    page.update(title='用户改过的名称',parentId=bundle['project']['pages'][0]['id'],priority=1,progress=60)
    page['states'][0]['interactionHints']={'mode':'targets','protoIds':['save-button']}
    bundle['prd']['annotations']=[{'id':'keep','pageId':page['id'],'stateId':'default','number':1,'body':'保留正文',
        'anchor':{'protoId':'save-button'},'placement':{'kind':'element','x':1,'y':2}}]
    proto_meta.save_bundle(root,bundle);previous=copy.deepcopy(page)
    result=mod.replace_page(root,payload(bundle,pageId=page['id'],title='忽略导入标题',entryFile='detail.htm',files=[
        asset('detail.htm','<title>新标题</title><button data-proto-id="save-button">新版按钮</button>'),asset('new.css','button {color:red}')]))
    assert len(result['bundle']['project']['pages'])==len(bundle['project']['pages'])
    for key in previous.keys()-{'file','url','htmlImport'}:assert result['page'][key]==previous[key]
    assert result['bundle']['prd']==bundle['prd'] and result['bundle']['changes']==bundle['changes']
    assert result['page']['file'].endswith('/detail.htm')
    assert not (root/previous['file']).exists()
    assert not (root/previous['htmlImport']['directory']/'assets/style.css').exists()
    reread=proto_meta.load_bundle(root);proto_meta.ensure_pages_registered(root,reread)
    assert len(reread['project']['pages'])==len(bundle['project']['pages'])
    out=tmp_path/'replaced-export';review_export.build_review_export(root,reread,out)
    assert '新版按钮' in (out/'proto'/result['page']['file']).read_text(encoding='utf-8')
    assert not (out/'proto'/previous['file']).exists()


@pytest.mark.parametrize('failure',['save','write'])
def test_failed_reimport_restores_overwritten_obsolete_and_new_files(project,monkeypatch,failure):
    root,bundle,mod=project;initial=mod.import_page(root,payload(bundle));bundle=initial['bundle']
    before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    if failure=='save':
        monkeypatch.setattr(proto_meta,'save_bundle',lambda *a:(_ for _ in ()).throw(OSError('disk full')))
    else:
        atomic=mod._atomic;calls=0
        def fail_second_write(path,raw):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('disk full')
            atomic(path,raw)
        monkeypatch.setattr(mod,'_atomic',fail_second_write)
    with pytest.raises(OSError):mod.replace_page(root,payload(bundle,pageId=initial['page']['id'],files=[
        asset('index.html','<title>会回滚</title>'),asset('new.css','new')]))
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}==before
    assert proto_meta.load_bundle(root)==bundle


def test_reimport_rejects_wrong_page_conflict_and_unowned_file_collision(project):
    root,bundle,mod=project;initial=mod.import_page(root,payload(bundle));current=initial['bundle']
    with pytest.raises(mod.RevisionConflict):mod.replace_page(root,payload(bundle,pageId=initial['page']['id']))
    with pytest.raises(ValueError,match='HTML'):mod.replace_page(root,payload(current,pageId=bundle['project']['pages'][0]['id']))
    unowned=root/initial['page']['htmlImport']['directory']/'manual.css';unowned.write_text('不能覆盖')
    with pytest.raises(ValueError,match='未登记'):mod.replace_page(root,payload(current,pageId=initial['page']['id'],files=[
        asset('index.html','<title>替换</title>'),asset('manual.css','bad')]))
    assert unowned.read_text()=='不能覆盖' and proto_meta.load_bundle(root)==current


def test_interrupted_reimport_leaves_original_bytes_in_recovery_record(project,monkeypatch):
    root,bundle,mod=project;initial=mod.import_page(root,payload(bundle))
    old={f:(root/f).read_bytes() for f in initial['page']['htmlImport']['files']}
    monkeypatch.setattr(proto_meta,'save_bundle',lambda *a:(_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):mod.replace_page(root,payload(initial['bundle'],pageId=initial['page']['id'],files=[asset('new.htm','<h1>新页</h1>')],entryFile='new.htm'))
    pending=proto_meta.read_json(proto_meta.meta_dir(root)/mod.PENDING,{})
    assert {f:base64.b64decode(raw) for f,raw in pending['beforeFiles'].items()}==old
    with pytest.raises(ValueError,match='导入中断'):proto_meta.load_bundle(root)


def test_reimport_api_keeps_id_and_checks_origin_and_revision(api,tmp_path):
    root=prototype(tmp_path/'replace-api');pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    created=api.request('/api/proto/import-html',{'projectId':pid,**payload(proto_meta.load_bundle(root))})[1]
    data={'projectId':pid,**payload(created['bundle'],pageId=created['page']['id'],files=[asset('index.html','<h1>替换完成</h1>')])}
    assert api.request('/api/proto/replace-html',data,{'Origin':'https://untrusted.invalid'})[0]==403
    status,result=api.request('/api/proto/replace-html',data)
    assert status==200 and result['page']['id']==created['page']['id']
    assert len(result['bundle']['project']['pages'])==2
    assert api.request('/api/proto/replace-html',data)[0]==409
