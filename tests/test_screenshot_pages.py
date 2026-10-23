"""截图页只在隔离目录创建；验证位置、跳转、冲突、删除与离线发布。"""
import base64
import copy
import importlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

import proto_meta
import page_lifecycle
import review_export
from test_external_api import api, prototype


def image_url(size=(900, 1200)):
    stream = io.BytesIO()
    Image.new('RGB', size, '#fafafa').save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


@pytest.fixture
def shot(tmp_path):
    root = prototype(tmp_path / 'project')
    bundle = proto_meta.ensure_bundle(root)
    module = importlib.import_module('screenshot_pages')
    result = module.mutate(root, 'create', {'expectedRevision': bundle['revision'], 'title': '补充截图', 'dataUrl': image_url(), 'previewType': 'pad'})
    return root, module, result


def test_create_portable_page_without_prd(shot):
    root, _, result = shot
    page = result['page']; bundle = proto_meta.load_bundle(root)
    assert page['kind'] == 'screenshot' and page['previewType'] == 'pad'
    assert page['screenshot']['width'] == 900 and page['screenshot']['height'] == 1200
    assert (root / page['screenshot']['image']).is_file()
    text = (root / page['file']).read_text(encoding='utf-8')
    assert 'data-proto-screenshot' in text and 'localhost' not in text
    assert bundle['prd'] == {'documents': [], 'annotations': []}
    proto_meta.ensure_pages_registered(root, bundle)
    assert len(bundle['project']['pages']) == 2


def test_regions_validate_geometry_and_link_and_keep_annotations(shot):
    root, mod, result = shot; page = result['page']; before = result['bundle']
    note = {'id': 'n', 'pageId': page['id'], 'stateId': 'default', 'number': 1, 'body': '说明',
            'anchor': {'protoId': 'screenshot-image-' + page['id']},
            'placement': {'kind':'element','x':90,'y':120,'rx':.1,'ry':.1}}
    before['prd']['annotations'].append(note); proto_meta.save_bundle(root, before)
    regions = [{'id': 'r-one', 'label': '打开首页', 'x': .1, 'y': .2, 'width': .15, 'height': .04, 'targetPageId': before['project']['pages'][0]['id']}]
    saved = mod.mutate(root, 'regions', {'pageId':page['id'], 'expectedRevision':before['revision'], 'regions':regions})
    assert saved['page']['screenshot']['regions'] == regions
    assert saved['bundle']['prd']['annotations'] == [note]
    text = (root / page['file']).read_text(encoding='utf-8')
    assert '../index.html' in text
    with pytest.raises(mod.RevisionConflict):
        mod.mutate(root, 'regions', {'pageId':page['id'], 'expectedRevision':before['revision'], 'regions':[]})
    stable = (root / page['file']).read_bytes()
    for bad in [{**regions[0], 'width': 2}, {**regions[0], 'x': float('nan')}, {**regions[0], 'targetPageId':'missing'}, {**regions[0], 'id':'../escape'}]:
        with pytest.raises(ValueError):
            mod.mutate(root, 'regions', {'pageId':page['id'], 'expectedRevision':saved['bundle']['revision'], 'regions':[bad]})
        assert (root / page['file']).read_bytes() == stable


def test_replace_retains_positions_and_uses_new_asset(shot):
    root, mod, result = shot; page = result['page']; old_image = page['screenshot']['image']
    regions=[{'id':'keep-region','label':'保留热区','x':.1,'y':.2,'width':.2,'height':.1}]
    before=mod.mutate(root,'regions',{'pageId':page['id'],'expectedRevision':result['bundle']['revision'],'regions':regions})['bundle']
    before['prd']['annotations']=[{'id':'keep-note','pageId':page['id'],'stateId':'default','number':1,'body':'保留正文',
        'anchor':{'protoId':'screenshot-image-'+page['id']},'placement':{'kind':'element','x':90,'y':120,'rx':.1,'ry':.1}}]
    proto_meta.save_bundle(root,before)
    saved = mod.mutate(root, 'replace', {'pageId':page['id'], 'expectedRevision':before['revision'], 'dataUrl':image_url((1000, 1400))})
    assert saved['layoutChanged'] is True and saved['page']['id'] == page['id']
    assert saved['page']['screenshot']['image'] != old_image
    assert not (root / old_image).exists()
    assert saved['page']['screenshot']['regions']==regions
    assert saved['bundle']['prd']==before['prd']


def test_failed_commit_restores_source_and_assets(shot, monkeypatch):
    root, mod, result = shot; before = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    source = (root/result['page']['file']).read_bytes()
    monkeypatch.setattr(proto_meta, 'save_bundle', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        mod.mutate(root, 'replace', {'pageId':result['page']['id'], 'expectedRevision':result['bundle']['revision'], 'dataUrl':image_url((800, 1000))})
    assert (root/result['page']['file']).read_bytes() == source
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()) == before


def test_trash_restore_and_delete_owned_image(shot):
    root, _, result = shot; page = result['page']; rev = result['bundle']['revision']
    trashed = page_lifecycle.change_page(root, page['id'], 'trash', rev)
    assert (root / page['screenshot']['image']).exists()
    restored = page_lifecycle.change_page(root, page['id'], 'restore', trashed['revision'])
    trashed = page_lifecycle.change_page(root, page['id'], 'trash', restored['revision'])
    page_lifecycle.change_page(root, page['id'], 'delete', trashed['revision'], page['file'])
    assert not (root / page['file']).exists() and not (root / page['screenshot']['image']).exists()
    assert (root/'index.html').exists()


def test_both_exports_include_image_and_disable_trashed_destination(shot, tmp_path):
    root, mod, result = shot; page = result['page']; bundle = result['bundle']; home = bundle['project']['pages'][0]
    saved = mod.mutate(root, 'regions', {'pageId':page['id'], 'expectedRevision':bundle['revision'], 'regions':[
        {'id':'r-link','label':'首页','x':.1,'y':.1,'width':.1,'height':.04,'targetPageId':home['id']}]})
    bundle = page_lifecycle.change_page(root, home['id'], 'trash', saved['bundle']['revision'])
    for mode in ('review', 'pure'):
        out = tmp_path/mode
        getattr(review_export, 'build_' + mode + '_export')(root, bundle, out)
        proto = out/'proto' if mode == 'review' else out
        assert (proto/page['screenshot']['image']).is_file()
        text = (proto/page['file']).read_text(encoding='utf-8')
        assert '"targetFile": "../index.html"' not in text
        assert 'localhost' not in text


def test_image_rejects_svg_fake_and_unsafe_folders(tmp_path):
    mod = importlib.import_module('screenshot_pages'); root=prototype(tmp_path/'project'); bundle=proto_meta.ensure_bundle(root)
    for value in ('data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,YmFk'):
        with pytest.raises(ValueError): mod.mutate(root, 'create', {'expectedRevision':bundle['revision'], 'title':'截图', 'dataUrl':value})
    assert len(proto_meta.load_bundle(root)['project']['pages']) == 1


def test_trashed_screenshot_image_is_not_exported(shot, tmp_path):
    root, _, result=shot;page=result['page']
    bundle=page_lifecycle.change_page(root,page['id'],'trash',result['bundle']['revision'])
    for mode in ('review','pure'):
        out=tmp_path/mode;getattr(review_export,'build_'+mode+'_export')(root,bundle,out)
        target=out/'proto' if mode=='review' else out
        assert not (target/page['file']).exists()
        assert not (target/page['screenshot']['image']).exists()


def test_html_and_image_links_are_escaped(shot):
    root, mod, result=shot;page=result['page'];bundle=result['bundle']
    page['title']='说明 <script>alert(1)</script>'
    page['screenshot']['regions']=[{'id':'r-safe','label':'</script><img src=x onerror=alert(1)>','x':0,'y':0,'width':.1,'height':.1}]
    text=mod.render_page(page,bundle['project'])
    assert '<title>说明 &lt;script&gt;' in text
    assert '</script><img src=x' not in text


def test_linked_image_directory_is_rejected_without_metadata_write(shot):
    root, mod, result=shot;folder=root/'assets'
    original=mod.proto_meta.is_linked_path
    from unittest.mock import patch
    with patch.object(mod.proto_meta,'is_linked_path',lambda p:p==folder or original(p)):
        with pytest.raises(ValueError,match='链接'):
            mod.mutate(root,'replace',{'pageId':result['page']['id'],'expectedRevision':result['bundle']['revision'],'dataUrl':image_url((800,1000))})
    assert proto_meta.load_bundle(root)==result['bundle']


def test_api_create_and_cas_and_origin(api, tmp_path):
    root=prototype(tmp_path/'project'); _, registered=api.request('/api/external/add', {'path':str(root)})
    pid=registered['projectId']; bundle=proto_meta.load_bundle(root)
    payload={'projectId':pid, 'expectedRevision':bundle['revision'], 'title':'截图', 'dataUrl':image_url()}
    status, created=api.request('/api/proto/screenshot/create', payload)
    assert status == 200 and created['ok']
    status, conflict=api.request('/api/proto/screenshot/create', payload)
    assert status == 409 and conflict['conflict']
    status, _=api.request('/api/proto/screenshot/create', payload, {'Origin':'https://untrusted.invalid'})
    assert status == 403
