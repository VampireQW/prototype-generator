import json

import pytest

import page_lifecycle as lifecycle
import proto_meta
import prototype_manifest as pm
import review_export


@pytest.fixture
def project(tmp_path):
    root=tmp_path/'project';root.mkdir()
    for name in ('index.html','a.html','b.html'):
        (root/name).write_text('<html><body><button data-proto-id="go">'+name+'</button></body></html>',encoding='utf-8')
    (root/'shared.js').write_text('window.shared=true',encoding='utf-8')
    proto_meta.write_json_atomic(root/pm.MANIFEST_NAME,{'schemaVersion':1,'pages':[{'file':'index.html','role':'launcher'},{'file':'a.html'},{'file':'b.html'}],'defaultPage':'a.html'})
    bundle=proto_meta.ensure_bundle(root);proto_meta.ensure_pages_registered(root,bundle)
    for page in bundle['project']['pages']:
        bundle['prd']['documents'].append({'id':'doc-'+page['id'],'pageId':page['id'],'stateId':'default','markdown':'页面要求 '+page['id'],'confirmed':True})
        bundle['prd']['annotations'].append({'id':'note-'+page['id'],'pageId':page['id'],'stateId':'default','number':1,'body':'标注 '+page['id'],'anchor':{'protoId':'go'},'confirmed':True})
        bundle['changes']['items'].append({'id':'task-'+page['id'],'pageId':page['id'],'stateId':'default','text':'修改任务'})
    bundle['revision']+=1;proto_meta.save_bundle(root,bundle)
    return root,bundle


def act(root,page,action,**kwargs):
    return lifecycle.change_page(root,page,action,proto_meta.load_bundle(root)['revision'],**kwargs)


def test_trash_restore_preserves_file_prd_order_and_prevents_rescan(project):
    root,before=project
    result=act(root,'a','trash')
    assert (root/'a.html').exists()
    assert result['prd']==before['prd'] and result['changes']==before['changes']
    assert result['project']['defaultPage']=='b'
    assert not proto_meta.ensure_pages_registered(root,result)
    assert next(p for p in result['project']['pages'] if p['id']=='a')['trashedAt']
    assert all(p['id']!='a' for p in pm.public_navigation(result['project'])['pages'])
    restored=act(root,'a','restore')
    assert restored['project']['pages']==before['project']['pages']
    assert restored['prd']==before['prd'] and restored['changes']==before['changes']


def test_permanent_delete_removes_html_owned_metadata_and_manifest_only(project):
    root,before=project;act(root,'a','trash')
    result=act(root,'a','delete',confirm_file='a.html')
    assert not (root/'a.html').exists() and (root/'b.html').exists() and (root/'shared.js').exists()
    assert all(p['id']!='a' for p in result['project']['pages'])
    assert all(item['pageId']!='a' for key in ('documents','annotations') for item in result['prd'][key])
    assert all(item['pageId']!='a' for item in result['changes']['items'])
    assert all(p['file']!='a.html' for p in pm.load_manifest(root)['pages'])
    assert not proto_meta.ensure_pages_registered(root,result)
    assert all(p['id']!='a' for p in proto_meta.load_bundle(root)['project']['pages'])
    assert not list((root/'.prototype').glob('page-delete-*'))


def test_last_page_can_be_trashed_restored_and_deleted(project):
    root,_=project
    for pid in ('home','a','b'):act(root,pid,'trash')
    b=proto_meta.load_bundle(root)
    assert not lifecycle.active_pages(b['project']) and b['project']['defaultPage']==''
    act(root,'b','restore')
    assert proto_meta.load_bundle(root)['project']['defaultPage']=='b'
    act(root,'b','trash')
    for pid,file in (('home','index.html'),('a','a.html'),('b','b.html')):act(root,pid,'delete',confirm_file=file)
    result=proto_meta.load_bundle(root)
    assert result['project']['pages']==[] and not result['prd']['documents']
    assert pm.load_manifest(root)['allowEmpty'] is True
    assert not proto_meta.ensure_pages_registered(root,result)


@pytest.mark.parametrize('action,confirm', [('delete','a.html'),('restore',None),('unknown',None),('delete','b.html')])
def test_invalid_actions_never_delete_active_files(project,action,confirm):
    root,before=project
    with pytest.raises(ValueError):act(root,'a',action,confirm_file=confirm)
    assert proto_meta.load_bundle(root)==before and (root/'a.html').exists()


def test_cas_and_confirmation_protect_delete(project):
    root,before=project;act(root,'a','trash')
    with pytest.raises(lifecycle.RevisionConflict):lifecycle.change_page(root,'a','delete',before['revision'],'a.html')
    with pytest.raises(ValueError,match='确认'):act(root,'a','delete',confirm_file='b.html')
    assert (root/'a.html').exists()


def test_delete_missing_local_file_can_clean_up_metadata(project):
    root,_=project;act(root,'a','trash');(root/'a.html').unlink()
    with pytest.raises(ValueError,match='不存在'):act(root,'a','restore')
    result=act(root,'a','delete',confirm_file='a.html')
    assert all(p['id']!='a' for p in result['project']['pages'])


def test_failed_delete_restores_file_manifest_and_all_metadata(project,monkeypatch):
    root,_=project;act(root,'a','trash')
    before=proto_meta.load_bundle(root);manifest=(root/pm.MANIFEST_NAME).read_bytes();source=(root/'a.html').read_bytes()
    original=proto_meta.save_bundle;failed=False
    def fail_once(target,bundle):
        nonlocal failed
        if not failed:failed=True;raise OSError('模拟保存失败')
        return original(target,bundle)
    monkeypatch.setattr(proto_meta,'save_bundle',fail_once)
    with pytest.raises(OSError):act(root,'a','delete',confirm_file='a.html')
    assert proto_meta.load_bundle(root)==before
    assert (root/pm.MANIFEST_NAME).read_bytes()==manifest and (root/'a.html').read_bytes()==source
    assert not (root/'.prototype'/lifecycle.PENDING).exists()


def test_exports_omit_trashed_files_documents_and_navigation(project,tmp_path):
    root,before=project;bundle=act(root,'a','trash')
    for kind in ('review','pure'):
        output=tmp_path/kind
        build=review_export.build_review_export if kind=='review' else review_export.build_pure_export
        build(root,bundle,output)
        page_root=output/'proto' if kind=='review' else output
        assert not (page_root/'a.html').exists() and (page_root/'b.html').exists()
        source=(page_root/'index.html').read_text(encoding='utf-8')
        navigation=json.loads(source.split('id="navigationData">',1)[1].split('</script>',1)[0])
        assert all(p['id']!='a' for p in navigation['pages'])
    data=review_export.review_data(bundle,'now')
    assert all(p['id']!='a' for p in data['pages']) and all(n['pageId']!='a' for n in data['annotations'])


def test_symlink_page_never_deletes_target(project,tmp_path):
    root,_=project;act(root,'a','trash');(root/'a.html').unlink();outside=tmp_path/'outside.html';outside.write_text('保留',encoding='utf-8')
    try:(root/'a.html').symlink_to(outside)
    except OSError:pytest.skip('当前环境不支持符号链接')
    with pytest.raises(ValueError):act(root,'a','delete',confirm_file='a.html')
    assert outside.read_text(encoding='utf-8')=='保留'


def test_lifecycle_never_deletes_shared_script_as_page(project):
    root,bundle=project
    page=next(p for p in bundle['project']['pages'] if p['id']=='a')
    page['file']='shared.js';page['trashedAt']=proto_meta.now_iso()
    bundle['revision']+=1;proto_meta.save_bundle(root,bundle)
    with pytest.raises(ValueError,match='HTML'):
        act(root,'a','delete',confirm_file='shared.js')
    assert (root/'shared.js').read_text(encoding='utf-8')=='window.shared=true'


def test_trashed_index_never_reappears_as_old_exported_home(project,tmp_path):
    root,_=project;bundle=act(root,'home','trash')
    pure=tmp_path/'pure';review=tmp_path/'review'
    review_export.build_pure_export(root,bundle,pure)
    review_export.build_review_export(root,bundle,review)
    assert not (review/'proto/index.html').exists()
    assert 'http-equiv="refresh"' in (pure/'index.html').read_text(encoding='utf-8')
    assert 'data-proto-id="go"' not in (pure/'index.html').read_text(encoding='utf-8')


def test_all_trashed_pages_cannot_be_exported(project,tmp_path):
    root,_=project
    for pid in ('home','a','b'):bundle=act(root,pid,'trash')
    for kind,build in [('pure',review_export.build_pure_export),('review',review_export.build_review_export)]:
        with pytest.raises(ValueError,match='恢复'):
            build(root,bundle,tmp_path/kind)
