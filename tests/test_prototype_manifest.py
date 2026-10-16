import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import proto_meta
import prototype_manifest as pm
import review_export


@pytest.fixture
def project(tmp_path):
    for name in ('index.html', 'teacher.html', 'app.html'):
        (tmp_path / name).write_text('<!doctype html><html><body><button data-proto-id="btn">业务</button></body></html>', encoding='utf-8')
    manifest = {'schemaVersion': 1, 'clients': [{'id':'teacher','title':'教师 Web','previewType':'web'},
                                               {'id':'student','title':'学生 App','previewType':'mobile'}],
                'defaultPage':'teacher.html','pages':[{'file':'index.html','role':'launcher'},
                {'file':'teacher.html','clientId':'teacher'},{'file':'app.html','clientId':'student','states':[{'id':'detail','title':'详情'}]}]}
    (tmp_path / pm.MANIFEST_NAME).write_text(json.dumps(manifest), encoding='utf-8')
    return tmp_path, manifest


def registered(root):
    bundle=proto_meta.ensure_bundle(root)
    proto_meta.ensure_pages_registered(root,bundle)
    return bundle


def test_no_manifest_never_hides_business_index(tmp_path):
    (tmp_path/'index.html').write_text('<h1>业务首页</h1><aside>菜单</aside>')
    b=registered(tmp_path)
    assert b['project']['pages'][0].get('role','page')=='page'


def test_registration_preserves_ids_and_prd(project):
    root,_=project
    b=proto_meta.ensure_bundle(root)
    before=copy.deepcopy(b['prd'])
    home=b['project']['pages'][0]['id']
    proto_meta.ensure_pages_registered(root,b)
    assert next(p for p in b['project']['pages'] if p['file']=='index.html')['id']==home
    assert b['prd']==before
    app=next(p for p in b['project']['pages'] if p['file']=='app.html')
    assert app['previewType']=='mobile' and any(s['id']=='detail' for s in app['states'])
    assert next(p for p in b['project']['pages'] if p['id']==b['project']['defaultPage'])['file']=='teacher.html'


def test_pad_registration_preserves_prd_and_all_export_display_types(project):
    root, manifest = project
    (root/'pad.html').write_text('<html data-proto-preview="pad"><h1>平板页面</h1></html>', encoding='utf-8')
    manifest['clients'].append({'id':'pad','title':'学生 Pad','previewType':'pad'})
    manifest['pages'].append({'file':'pad.html','clientId':'pad','states':[{'id':'detail','previewType':'pad'}]})
    (root/pm.MANIFEST_NAME).write_text(json.dumps(manifest),encoding='utf-8')
    bundle=proto_meta.ensure_bundle(root)
    before=copy.deepcopy(bundle['prd'])
    proto_meta.ensure_pages_registered(root,bundle)
    proto_meta.validate_bundle(bundle)
    page=next(p for p in bundle['project']['pages'] if p['file']=='pad.html')
    assert page['previewType']=='pad'
    assert next(s for s in page['states'] if s['id']=='detail')['previewType']=='pad'
    assert bundle['prd']==before
    bundle['project']['previewType']='pad'
    data=review_export.review_data(bundle,'2026-10-15')
    assert data['previewType']=='pad'
    assert next(p for p in data['pages'] if p['id']==page['id'])['previewType']=='pad'
    pm.build_launcher(root,bundle)
    source=(root/'index.html').read_text(encoding='utf-8')
    navigation=json.loads(source.split('id="navigationData">',1)[1].split('</script>',1)[0])
    assert next(p for p in navigation['pages'] if p['id']==page['id'])['previewType']=='pad'
    assert 'ppn-pad' in (root/'assets/prototype-navigation/project-navigation.css').read_text(encoding='utf-8')


def test_unchanged_manifest_preserves_manual_correction(project):
    root,_=project;b=registered(root)
    b['project']['pages'][0]['role']='page';b['revision']+=1;proto_meta.save_bundle(root,b)
    r=b['revision'];assert not proto_meta.ensure_pages_registered(root,b)
    assert b['revision']==r and b['project']['pages'][0]['role']=='page'


def test_updated_manifest_preserves_saved_client_order_and_new_categories(project):
    root, data = project
    bundle = registered(root)
    bundle['project']['clients'].reverse()
    bundle['project']['clients'].append({'id': 'manual', 'title': '管理 Web', 'previewType': 'web', 'userCreated': True})
    bundle['revision'] += 1
    proto_meta.save_bundle(root, bundle)
    data['clients'][0]['title'] = '教师工作台'
    (root / pm.MANIFEST_NAME).write_text(json.dumps(data), encoding='utf-8')
    assert proto_meta.ensure_pages_registered(root, bundle)
    saved = proto_meta.load_bundle(root)
    assert [c['id'] for c in saved['project']['clients']] == ['student', 'teacher', 'manual']
    assert saved['project']['clients'][1]['title'] == '教师工作台'
    assert saved['project']['clients'][2]['userCreated'] is True
    assert 'userCreated' not in pm.public_navigation(saved['project'])['clients'][2]


@pytest.mark.parametrize('bad',[{'defaultPage':'index.html'}, {'pages':[{'file':'../outside.html'}]},
 {'pages':[{'file':'index.html','role':'launcher'}]}, {'pages':[{'file':'teacher.html','clientId':'unknown'}]},
 {'pages':[{'file':'missing.html'}]}, {'pages':[{'file':'teacher.html','role':'unknown'}]}])
def test_invalid_manifest_rejected_without_prd_loss(project,bad):
    root,data=project;b=registered(root);snap=proto_meta.load_bundle(root)
    data.update(bad);(root/pm.MANIFEST_NAME).write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):proto_meta.ensure_pages_registered(root,b)
    assert proto_meta.load_bundle(root)==snap


def test_launcher_and_exports_use_public_navigation(project):
    root,_=project;b=registered(root)
    files=pm.build_launcher(root,b)
    assert 'index.html' in files and 'data-proto-page-helper' in (root/'app.html').read_text()
    assert {'teacher.html', 'app.html'} <= set(files)
    assert not {'teacher.html', 'app.html'} & set(pm.build_launcher(root, b))
    source=(root/'index.html').read_text()
    assert 'project-navigation.js' in source and 'file:///' not in source and str(root) not in source
    review=root.parent/'review';review.mkdir();review_export.build_review_export(root,b,review)
    shell=(review/'index.html').read_text()
    assert 'ProtoProjectNavigation.mount' in shell and 'file:///' not in shell
    pure=root.parent/'pure';pure.mkdir();review_export.build_pure_export(root,b,pure)
    assert 'navigationData' in (pure/'index.html').read_text()
    assert not (pure/pm.MANIFEST_NAME).exists()


def test_business_index_not_overwritten_and_cli_dry_run_readonly(project):
    root,data=project;data['pages'][0]['role']='page';data['defaultPage']='index.html'
    (root/pm.MANIFEST_NAME).write_text(json.dumps(data))
    script=pm.ASSETS_DIR.parent/'scripts/connect_project.py'
    run=subprocess.run([sys.executable,str(script),str(root),'--tool-root',str(Path(proto_meta.__file__).parent),'--dry-run'],capture_output=True)
    assert run.returncode==0 and not (root/'.prototype').exists()
    b=registered(root);before=(root/'index.html').read_bytes();assert pm.build_launcher(root,b)==[]
    assert (root/'index.html').read_bytes()==before


def test_saved_page_name_survives_registration_and_exports(project):
    root, _ = project
    bundle = registered(root)
    page = next(p for p in bundle['project']['pages'] if p['file'] == 'teacher.html')
    original_page = copy.deepcopy(page)
    original_prd, original_changes = copy.deepcopy(bundle['prd']), copy.deepcopy(bundle['changes'])
    page['title'] = '教师工作台 · 新名称'
    bundle['revision'] += 1
    proto_meta.save_bundle(root, bundle)
    assert not proto_meta.ensure_pages_registered(root, bundle)
    saved = proto_meta.load_bundle(root)
    renamed = next(p for p in saved['project']['pages'] if p['id'] == original_page['id'])
    assert renamed == dict(original_page, title=page['title'])
    assert saved['prd'] == original_prd and saved['changes'] == original_changes
    assert next(p for p in pm.public_navigation(saved['project'])['pages'] if p['id'] == page['id'])['title'] == page['title']
    for flavor, builder in [('pure', review_export.build_pure_export), ('review', review_export.build_review_export)]:
        out = root.parent / ('renamed-' + flavor)
        out.mkdir()
        builder(root, saved, out)
        assert page['title'] in (out / 'index.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('progress', [0, 100])
def test_tracking_preserved_on_manifest_update_and_export(project, progress):
    root, data = project
    bundle = registered(root)
    page = next(p for p in bundle['project']['pages'] if p['file'] == 'teacher.html')
    page.update(priority=1, progress=progress)
    proto_meta.save_bundle(root, bundle)
    data['pages'][1]['title'] = '教师工作台'
    (root / pm.MANIFEST_NAME).write_text(json.dumps(data), encoding='utf-8')
    assert proto_meta.ensure_pages_registered(root, bundle)
    saved = proto_meta.load_bundle(root)
    nav_page = next(p for p in pm.public_navigation(saved['project'])['pages'] if p['id'] == page['id'])
    assert nav_page['priority'] == 1 and nav_page['progress'] == progress
    for flavor, builder in [('pure', review_export.build_pure_export), ('review', review_export.build_review_export)]:
        out = root.parent / (root.name + '-tracking-' + flavor)
        out.mkdir()
        builder(root, saved, out)
        source = (out / 'index.html').read_text(encoding='utf-8')
        assert '"priority": 1' in source and '"progress": ' + str(progress) in source
        assert 'ppn-page-progress' in source or 'project-navigation.js' in source


@pytest.mark.parametrize('with_index', [True, False])
def test_manifest_registers_client_directories_and_preserves_data(tmp_path, with_index):
    pages = []
    if with_index:
        (tmp_path / 'index.html').write_text('<h1>演示入口</h1>', encoding='utf-8')
        pages.append({'file': 'index.html', 'role': 'launcher'})
    for relative, client in [('teacher/home.html', 'teacher'), ('student/app/home.html', 'student')]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True)
        target.write_text('<html><body>业务页面</body></html>', encoding='utf-8')
        pages.append({'file': relative, 'clientId': client})
    declaration = {'schemaVersion': 1, 'clients': [{'id': 'teacher', 'title': '教师 Web'},
                    {'id': 'student', 'title': '学生 App', 'previewType': 'mobile'}],
                   'defaultPage': 'student/app/home.html', 'pages': pages}
    (tmp_path / pm.MANIFEST_NAME).write_text(json.dumps(declaration), encoding='utf-8')
    bundle = registered(tmp_path)
    assert {p['file'] for p in bundle['project']['pages']} == {p['file'] for p in pages}
    current = next(p for p in bundle['project']['pages'] if p['id'] == bundle['project']['defaultPage'])
    assert current['file'] == 'student/app/home.html' and current['previewType'] == 'mobile'
    snapshot = copy.deepcopy(bundle)
    assert not proto_meta.ensure_pages_registered(tmp_path, bundle)
    assert proto_meta.load_bundle(tmp_path) == snapshot
    if with_index:
        modified = pm.build_launcher(tmp_path, bundle)
        assert {'teacher/home.html', 'student/app/home.html'} <= set(modified)
        assert '../../assets/prototype-navigation/project-page.js' in (tmp_path / current['file']).read_text()
        pure = tmp_path.parent / 'pure-nested'
        pure.mkdir()
        review_export.build_pure_export(tmp_path, bundle, pure)
        assert (pure / current['file']).is_file()


def test_launcher_preflight_keeps_original_files_on_missing_page(project):
    root, _ = project
    bundle = registered(root)
    before = {name: (root / name).read_bytes() for name in ('index.html', 'teacher.html')}
    (root / 'app.html').unlink()
    with pytest.raises(FileNotFoundError):
        pm.build_launcher(root, bundle)
    assert not (root / 'assets').exists()
    assert all((root / name).read_bytes() == data for name, data in before.items())


def test_launcher_rejects_external_asset_directory_before_writing(project):
    root, _ = project
    bundle = registered(root)
    external = root.parent / 'external-assets'
    external.mkdir()
    link = root / 'assets'
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(external)], capture_output=True)
        if result.returncode:
            pytest.skip('当前系统无法创建目录链接')
    before = {name: (root / name).read_bytes() for name in ('index.html', 'teacher.html', 'app.html')}
    with pytest.raises(ValueError, match='导航输出路径必须位于项目内'):
        pm.build_launcher(root, bundle)
    assert not list(external.iterdir())
    assert all((root / name).read_bytes() == data for name, data in before.items())
