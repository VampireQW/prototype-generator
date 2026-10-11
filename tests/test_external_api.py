"""目录能力的隔离 HTTP 回归；只加载定义，不运行服务启动或真实配置初始化。"""
import ast
import concurrent.futures
import datetime
import functools
import http.client
import http.server
import ipaddress
import json
import mimetypes
import os
import posixpath
import shutil
import socket
import tempfile
import sys
import threading
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proto_meta
import review_export
import design_settings
import home_thumbnails

SERVER = Path(__file__).resolve().parents[1] / 'server.py'


def isolated_handler(registry):
    tree = ast.parse(SERVER.read_text(encoding='utf-8'))
    names = {'load_external_registry', 'save_external_registry', 'external_root_for', 'normalize_design_form',
             'github_api_session', 'github_ensure_pages', 'github_upload_dir', 'CustomHandler', 'PrototypeHTTPServer'}
    selected = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    ns = {**globals(), 'EXTERNAL_FILE': str(registry), 'EXTERNAL_LOCK': threading.RLock(), 'REQUEST_LOCK': threading.RLock(),
          # 隔离环境不读真实配置：始终无 Token，发布端点走 400 错误路径（真实发布由用户配置后验收）
          'get_github_runtime_config': lambda: {'token': '', 'username': '', 'repo': 'fixture-repo'}}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SERVER), 'exec'), ns)
    return ns


@pytest.fixture
def api(tmp_path):
    registry = tmp_path / 'data' / 'external.json'
    ns = isolated_handler(registry)
    handler = functools.partial(ns['CustomHandler'], directory=str(tmp_path))
    server_type = ns.get('PrototypeHTTPServer', http.server.ThreadingHTTPServer)
    server = server_type(('127.0.0.1', 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port
    def request(path, data=None, headers=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        supplied = {'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        supplied.update(headers or {})
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method or ('POST' if data is not None else 'GET'), path, body, supplied)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader('Content-Type', '')
        result = (response.status, (json.loads(raw) if 'application/json' in content_type else raw if content_type.startswith('image/') else raw.decode('utf-8')) if raw else {})
        connection.close()
        return result
    yield SimpleNamespace(request=request, namespace=ns, registry=registry, port=port)
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def prototype(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'index.html').write_text('<title>隔离样例</title><button>开始</button>', encoding='utf-8')
    return path


@pytest.mark.skipif(os.name != 'nt', reason='Windows 重复监听端口回归')
def test_server_rejects_duplicate_listener(api):
    server_type = api.namespace.get('PrototypeHTTPServer', http.server.ThreadingHTTPServer)
    with pytest.raises(OSError):
        duplicate = server_type(('127.0.0.1', api.port), api.namespace['CustomHandler'])
        duplicate.server_close()
    assert api.request('/api/external/list')[0] == 200


def test_prd_image_upload_serving_and_export(api, tmp_path):
    image_data = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
    import base64
    root = prototype(tmp_path / 'media')
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    before = proto_meta.load_bundle(root)['revision']
    code, image = api.request('/api/proto/upload-image', {'projectId': pid, 'dataUrl': 'data:image/png;base64,' + image_data})
    assert code == 200 and image['path'].startswith('prd-assets/')
    assert proto_meta.load_bundle(root)['revision'] == before
    assert api.request(image['url'])[1] == base64.b64decode(image_data)
    assert api.request('/api/proto/upload-image', {'projectId': pid, 'dataUrl': 'data:image/png;base64,' + image_data})[1]['path'] == image['path']
    bundle = proto_meta.load_bundle(root)
    page = bundle['project']['pages'][0]
    bundle['prd']['documents'].append({'id': 'media-doc', 'pageId': page['id'], 'stateId': page['states'][0]['id'], 'markdown': '![需求截图](' + image['path'] + ')'})
    assert api.request('/api/proto/save', {'projectId': pid, 'expectedRevision': before, 'bundle': bundle})[0] == 200
    output = tmp_path / 'review'
    result = review_export.build_review_export(root, proto_meta.load_bundle(root), output)
    assert 'proto/' + image['path'] in result['files']
    assert (output / 'proto' / image['path']).read_bytes() == base64.b64decode(image_data)
    assert image['path'] in (output / 'index.html').read_text(encoding='utf-8')
    assert api.request('/api/proto/upload-image', {'projectId': 'missing', 'dataUrl': 'data:image/png;base64,' + image_data})[0] == 404
    assert api.request('/api/proto/upload-image', {'projectId': pid, 'dataUrl': 'data:image/svg+xml;base64,PHN2Zz4='})[0] == 400
    assert api.request('/api/proto/upload-image', {'projectId': pid, 'dataUrl': 'data:image/png;base64,' + image_data}, {'Origin': 'https://evil.example'})[0] == 403


def test_registry_upgrade_and_roots_lifecycle(api, tmp_path):
    api.registry.parent.mkdir()
    api.registry.write_text('{"projects":{}}', encoding='utf-8')
    assert api.namespace['load_external_registry']()['roots'] == []
    root = tmp_path / 'collection'
    child = prototype(root / 'project')
    assert api.request('/api/external/roots/add', {'path': str(root)})[0] == 200
    assert api.request('/api/external/roots/add', {'path': str(root / '.')})[0] == 200
    listing = api.request('/api/external/list')[1]
    assert len(listing['roots']) == 1 and len(listing['discovered']) == 1
    assert not (child / '.prototype').exists()
    connected = api.request('/api/external/add', {'path': str(child)})[1]
    assert connected['ok'] and (child / '.prototype' / 'prd.json').exists()
    pid = connected['projectId']
    listing = api.request('/api/external/list')[1]
    assert len(listing['items']) == 1 and listing['discovered'] == []
    api.request('/api/external/roots/remove', {'path': str(root)})
    listing = api.request('/api/external/list')[1]
    assert listing['roots'] == [] and len(listing['items']) == 1
    assert (child / 'index.html').exists()
    api.request('/api/external/roots/add', {'path': str(root)})
    api.request('/api/external/remove', {'projectId': pid})
    assert len(api.request('/api/external/list')[1]['discovered']) == 1
    assert (child / '.prototype' / 'prd.json').exists()


def test_external_list_uses_creation_time_instead_of_connection_order(api, tmp_path, monkeypatch):
    collection = tmp_path / 'creation-order'
    old = prototype(collection / 'old')
    recent = prototype(collection / 'recent')
    newest = prototype(collection / 'newest')
    dates = {old: '2026-09-01T00:00:00.000000+00:00',
             recent: '2026-09-15T00:00:00.000000+00:00',
             newest: '2026-10-03T00:00:00.000000+00:00'}
    actual = proto_meta.directory_created_at
    monkeypatch.setattr(proto_meta, 'directory_created_at', lambda root, fallback='': dates.get(root, actual(root, fallback)))
    api.request('/api/external/roots/add', {'path': str(collection)})
    api.request('/api/external/add', {'path': str(recent)})
    old_pid = api.request('/api/external/add', {'path': str(old)})[1]['projectId']
    listing = api.request('/api/external/list')[1]
    assert [item['name'] for item in listing['items']] == ['recent', 'old']
    assert listing['discovered'][0]['name'] == 'newest'
    assert listing['discovered'][0]['createdAt'] == dates[newest]
    assert not (newest / '.prototype').exists()
    assert api.namespace['load_external_registry']()['projects'][old_pid]['createdAt'] == dates[old]


def test_root_itself_connects_and_invalid_paths_are_not_registered(api, tmp_path):
    child = prototype(tmp_path / 'direct')
    code, result = api.request('/api/external/roots/add', {'path': str(child)})
    assert code == 200 and result['connected']
    assert api.namespace['load_external_registry']()['roots'] == []
    assert api.request('/api/external/roots/add', {'path': str(tmp_path / 'missing')})[0] == 400
    protected = prototype(tmp_path / 'dist')
    assert api.request('/api/external/roots/add', {'path': str(protected)})[0] == 400
    assert api.request('/api/external/add', {'path': str(protected)})[0] == 400
    assert not (protected / '.prototype').exists()


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Host': 'evil.example'},
    {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}, {'Host': 'localhost:1'},
])
def test_local_origin_rejects_untrusted_requests(api, headers):
    for route, body in [('/api/external/list', None), ('/api/external/pick-folder', {}),
                        ('/api/external/roots/add', {'path': '.'}),
                        ('/api/external/delete', {'projectId': 'p-x'})]:
        assert api.request(route, body, headers)[0] == 403
    assert not api.registry.exists()


def test_picker_requires_json_and_has_no_cancel_side_effect(api, monkeypatch):
    monkeypatch.setattr(proto_meta, 'pick_folder', lambda: '')
    assert api.request('/api/external/pick-folder', {}, {'Content-Type': 'text/plain'})[0] == 415
    code, result = api.request('/api/external/pick-folder', {})
    assert code == 200 and result['cancelled'] and result['path'] == ''
    assert not api.registry.exists()
    def unavailable():
        raise RuntimeError('请粘贴路径')
    monkeypatch.setattr(proto_meta, 'pick_folder', unavailable)
    assert api.request('/api/external/pick-folder', {})[0] == 503


def test_picker_does_not_block_list_or_repeat_requests(api, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def picker_process(*args, **kwargs):
        started.set()
        assert release.wait(4)
        return SimpleNamespace(returncode=0, stdout='{"path":""}')
    monkeypatch.setattr(proto_meta.subprocess, 'run', picker_process)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        first = executor.submit(api.request, '/api/external/pick-folder', {})
        assert started.wait(2)
        try:
            assert api.request('/api/external/pick-folder', {})[0] == 409
            assert api.request('/api/external/list')[0] == 200
        finally:
            release.set()
        assert first.result()[1]['cancelled']


def test_parallel_cas_and_confirmed_protection(api, tmp_path):
    child = prototype(tmp_path / 'project')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    bundle = api.request(f'/api/proto/read?projectId={pid}')[1]['bundle']
    data = {'projectId': pid, 'expectedRevision': bundle['revision'], 'bundle': bundle}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(api.request, '/api/proto/save', data) for _ in range(2)]
        assert sorted(f.result()[0] for f in futures) == [200, 409]
    bundle = proto_meta.load_bundle(child)
    bundle['prd']['annotations'] = [{'id': 'confirmed', 'pageId': 'home', 'stateId': 'default', 'number': 7,
                                    'body': '不可修改', 'confirmed': True, 'placement': {'kind': 'document', 'x': 20, 'y': 30}}]
    proto_meta.save_bundle(child, bundle)
    bundle['prd']['annotations'][0]['body'] = '试图覆盖'
    assert api.request('/api/proto/save', {'projectId': pid, 'expectedRevision': bundle['revision'], 'bundle': bundle})[0] == 400
    assert proto_meta.load_bundle(child)['prd']['annotations'][0]['body'] == '不可修改'


def test_external_delete_removes_folder_registration_and_scan_root(api, tmp_path):
    child = prototype(tmp_path / 'victim')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    # 项目根同时也是监视根时，删除要一并清理
    reg = api.namespace['load_external_registry']()
    reg['roots'].append(str(child))
    api.namespace['save_external_registry'](reg)
    assert (child / 'index.html').exists()
    code, result = api.request('/api/external/delete', {'projectId': pid})
    assert code == 200 and result['ok'] and result['folderDeleted'] and result['publishedUrl'] == ''
    assert not child.exists()
    listing = api.request('/api/external/list')[1]
    assert listing['items'] == [] and listing['roots'] == []


def test_external_delete_rejects_unregistered_and_dangerous_roots(api, tmp_path):
    assert api.request('/api/external/delete', {'projectId': 'p-unknown'})[0] == 404
    api.registry.parent.mkdir(parents=True, exist_ok=True)
    api.registry.write_text(json.dumps({'projects': {
        'p-disk': {'root': str(Path(tmp_path.anchor)), 'name': 'disk-root'},
        'p-tool': {'root': str(SERVER.parent), 'name': 'tool'},
    }, 'roots': []}), encoding='utf-8')
    code, result = api.request('/api/external/delete', {'projectId': 'p-disk'})
    assert code == 400 and '根目录' in result['error']
    code, result = api.request('/api/external/delete', {'projectId': 'p-tool'})
    assert code == 400 and '工具' in result['error']
    assert SERVER.parent.is_dir()
    # 被拒绝的危险登记保留，等待人工处理
    assert set(api.namespace['load_external_registry']()['projects']) == {'p-disk', 'p-tool'}


def test_external_delete_guards_nested_projects_and_missing_folder(api, tmp_path):
    parent = prototype(tmp_path / 'parent')
    child = prototype(parent / 'child')
    parent_pid = api.request('/api/external/add', {'path': str(parent)})[1]['projectId']
    child_pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    code, result = api.request('/api/external/delete', {'projectId': parent_pid})
    assert code == 400 and '已登记' in result['error']
    assert (child / 'index.html').exists()
    code, result = api.request('/api/external/delete', {'projectId': child_pid})
    assert code == 200 and result['folderDeleted']
    assert not child.exists() and (parent / 'index.html').exists()
    # 目录本就不存在：只移除登记
    shutil.rmtree(parent)
    code, result = api.request('/api/external/delete', {'projectId': parent_pid})
    assert code == 200 and result['ok'] and result['folderDeleted'] is False
    assert api.request('/api/external/list')[1]['items'] == []


def test_static_registry_aliases_are_origin_guarded(api):
    for path in ('/data/external.json', '/data/%65xternal.json', '/src/../data/external.json',
                 '/DATA/EXTERNAL.JSON', '/data/external.json.', '/data/external.json::$DATA'):
        for method in ('GET', 'HEAD'):
            assert api.request(path, headers={'Origin': 'https://evil.example'}, method=method)[0] == 403


def test_external_asset_path_is_decoded_once(api, tmp_path):
    child = prototype(tmp_path / 'project')
    (child / '%41.html').write_text('literal-percent', encoding='utf-8')
    (child / 'A.html').write_text('different-file', encoding='utf-8')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    assert api.request(f'/ext/{pid}/%2541.html') == (200, 'literal-percent')
    assert api.request(f'/ext/{pid}/pages/%2e%2e/A.html')[0] == 403


@pytest.mark.parametrize('change', ['remove', 'unconfirm', 'body', 'number'])
def test_confirmed_annotations_are_immutable(api, tmp_path, change):
    child = prototype(tmp_path / 'project')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    bundle = proto_meta.load_bundle(child)
    item = {'id': 'locked', 'pageId': 'home', 'stateId': 'default', 'confirmed': True,
            'number': 9, 'body': '已确认'}
    bundle['prd']['annotations'] = [item]
    proto_meta.save_bundle(child, bundle)
    before = proto_meta.load_bundle(child)
    if change == 'remove':
        bundle['prd']['annotations'] = []
    elif change == 'unconfirm':
        item['confirmed'] = False
    elif change == 'number':
        item['number'] = 1
    else:
        item['body'] = '禁止覆盖'
    data = {'projectId': pid, 'expectedRevision': bundle['revision'], 'bundle': bundle}
    assert api.request('/api/proto/save', data)[0] == 400
    assert proto_meta.load_bundle(child) == before
    data['bundle'] = before
    assert api.request('/api/proto/save', data)[0] == 200


@pytest.mark.parametrize('change', ['body', 'unconfirm', 'remove'])
def test_confirmed_documents_are_editable(api, tmp_path, change):
    """页面需求文档永远可双击编辑（用户裁定 2026-09-28）：confirmed 只锁标注，不锁文档。"""
    child = prototype(tmp_path / 'project')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    bundle = proto_meta.load_bundle(child)
    item = {'id': 'doc1', 'pageId': 'home', 'stateId': 'default', 'confirmed': True, 'markdown': '已确认文档'}
    bundle['prd']['documents'] = [item]
    proto_meta.save_bundle(child, bundle)
    if change == 'remove':
        bundle['prd']['documents'] = []
    elif change == 'unconfirm':
        item['confirmed'] = False
    else:
        item['markdown'] = '改后的需求'
    data = {'projectId': pid, 'expectedRevision': bundle['revision'], 'bundle': bundle}
    assert api.request('/api/proto/save', data)[0] == 200
    saved = proto_meta.load_bundle(child)['prd']['documents']
    if change == 'remove':
        assert saved == []
    elif change == 'unconfirm':
        assert saved[0]['confirmed'] is False
    else:
        assert saved[0]['markdown'] == '改后的需求'


def test_pure_export_build_guarantees_entry(tmp_path):
    """纯净版构建：原样复制 + 保证 index.html 入口（缺失时生成跳转页指向登记页）。"""
    child = prototype(tmp_path / 'multi')
    (child / 'pages').mkdir()
    (child / 'pages' / 'detail.html').write_text('<title>详情</title>', encoding='utf-8')
    bundle = proto_meta.ensure_bundle(child)
    proto_meta.ensure_pages_registered(child, bundle)
    built = review_export.build_pure_export(child, bundle, tmp_path / 'out-multi')
    assert built['entry'] == 'index.html' and built['htmlCount'] == 2
    assert 'pages/detail.html' in built['files'] and 'index.html' in built['files']
    single = tmp_path / 'single'
    single.mkdir()
    (single / 'board.html').write_text('<title>看板</title>', encoding='utf-8')
    bundle2 = proto_meta.ensure_bundle(single)
    proto_meta.ensure_pages_registered(single, bundle2)
    out2 = tmp_path / 'out-single'
    built2 = review_export.build_pure_export(single, bundle2, out2)
    assert built2['htmlCount'] == 1 and built2['entry'] == 'board.html'
    redirect = (out2 / 'index.html').read_text(encoding='utf-8')
    assert 'board.html' in redirect and 'refresh' in redirect


def test_ext_export_download_single_page_html(api, tmp_path):
    """单页面纯净版：GET /api/ext/export 直接回 HTML 附件流。"""
    child = prototype(tmp_path / 'solo')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']
    connection = http.client.HTTPConnection('127.0.0.1', api.port, timeout=5)
    connection.request('GET', f'/api/ext/export?extId={pid}&mode=pure', None,
                       {'Origin': f'http://127.0.0.1:{api.port}'})
    response = connection.getresponse()
    body = response.read()
    disposition = response.getheader('Content-Disposition') or ''
    connection.close()
    assert response.status == 200
    assert 'text/html' in (response.getheader('Content-Type') or '')
    assert 'attachment' in disposition and '.html' in disposition
    assert '隔离样例'.encode('utf-8') in body


def test_ext_export_download_zip_and_review_shell(api, tmp_path):
    """多页面纯净版回 ZIP；研发版 ZIP 含评审壳 index.html 与 proto/ 副本；错误路径 404/400。"""
    import io
    import zipfile
    child = prototype(tmp_path / 'multi2')
    (child / 'detail.html').write_text('<title>详情页</title><p>第二页</p>', encoding='utf-8')
    pid = api.request('/api/external/add', {'path': str(child)})[1]['projectId']

    def download(mode):
        connection = http.client.HTTPConnection('127.0.0.1', api.port, timeout=5)
        connection.request('GET', f'/api/ext/export?extId={pid}&mode={mode}', None,
                           {'Origin': f'http://127.0.0.1:{api.port}'})
        response = connection.getresponse()
        payload = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, payload

    code, headers, payload = download('pure')
    assert code == 200 and headers['Content-Type'] == 'application/zip'
    assert '.zip' in headers['Content-Disposition']
    names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
    assert 'index.html' in names and 'detail.html' in names
    code, headers, payload = download('review')
    assert code == 200 and headers['Content-Type'] == 'application/zip'
    names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
    assert 'index.html' in names and 'proto/index.html' in names and 'proto/detail.html' in names
    connection = http.client.HTTPConnection('127.0.0.1', api.port, timeout=5)
    connection.request('GET', '/api/ext/export?extId=missing&mode=pure', None,
                       {'Origin': f'http://127.0.0.1:{api.port}'})
    assert connection.getresponse().status == 404
    connection.close()
    assert api.request(f'/api/ext/export?extId={pid}&mode=bogus')[0] == 400


def test_ext_publish_supports_pure_mode_and_export_route():
    """server.py 静态断言：发布接受 pure/review 双版本，导出路由与纯净版构建接入。"""
    source = SERVER.read_text(encoding='utf-8')
    assert "mode not in ('review', 'pure')" in source
    assert "elif path == '/api/ext/export':" in source
    assert 'def handle_ext_export' in source
    assert 'build_pure_export' in source
    # 发布版本落登记：发布时记录、状态查询返回、取消发布清理
    assert "item['github_publish_mode'] = mode" in source
    assert "'mode': item.get('github_publish_mode', '')" in source
    assert "item.pop('github_publish_mode', None)" in source


def test_github_token_persisted_locally_encrypted(tmp_path):
    """GitHub Token 本地持久化：往返一致（模拟重启后读取）；Windows 走 DPAPI 不明文落盘；传空清除。"""
    tree = ast.parse(SERVER.read_text(encoding='utf-8'))
    names = {'_dpapi_transform', 'save_github_token', 'load_github_token'}
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in selected} == names, '缺少 token 持久化函数'
    data_dir = tmp_path / 'data'
    ns = {'os': os, 'sys': sys, 'tempfile': tempfile,
          'DATA_DIR': str(data_dir), 'GITHUB_TOKEN_FILE': str(data_dir / 'github_token.bin')}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SERVER), 'exec'), ns)
    save, load = ns['save_github_token'], ns['load_github_token']
    token_file = Path(ns['GITHUB_TOKEN_FILE'])
    tok = 'fixture-token-for-dpapi-persistence'
    assert save(tok) is True and token_file.exists()
    blob = token_file.read_bytes()
    assert blob[:1] in (b'D', b'P')          # Windows=DPAPI(D)；其他平台退化明文(P)
    if blob[:1] == b'D':
        assert tok.encode() not in blob      # DPAPI 加密后原文不出现
    assert load() == tok                     # 往返一致 = 重启后仍可用
    assert save('') is True                  # 传空清除
    assert not token_file.exists() and load() == ''


def test_github_token_not_in_config_and_runtime_fallback():
    """静态断言：token 不写 config.json；runtime 回退到本地持久化；保存时落盘。"""
    source = SERVER.read_text(encoding='utf-8')
    assert "config['github'].pop('token', None)" in source          # 仍不入 config.json
    assert 'or load_github_token()' in source                      # runtime 回退持久化 token
    assert 'token_saved = save_github_token(' in source            # 保存时持久化
    assert "GITHUB_TOKEN_FILE = os.path.join(DATA_DIR, 'github_token.bin')" in source


def serve_preview_fixture(port=8092):
    """仅供浏览器回归：静态资源取源码，全部登记及元数据写在临时目录。"""
    with tempfile.TemporaryDirectory(prefix='prototype-ui-') as folder:
        root = Path(folder)
        child = root / 'fixture'
        child.mkdir()
        sample = '''<!doctype html><html lang="zh-CN" data-proto-page="home" data-proto-state="default">
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>隔离标注回归</title>
<style>body{font:16px sans-serif;padding:30px;min-height:1400px}button,input,a{margin:12px;padding:12px}#nested{height:180px;overflow:auto;margin:20px;border:1px solid}#inside{height:650px;padding:30px}</style>
<h1>临时项目，不含业务数据</h1><button id="action" data-proto-id="action" onclick="this.textContent='已操作'">开始</button>
<input id="input" aria-label="业务输入"><a href="detail.html" data-proto-id="next">下一页</a>
<button id="state" data-proto-id="state" onclick="PrototypeBridge.enter('done')">切换状态</button>
<div id="nested"><div id="inside" data-proto-id="inside">嵌套滚动内容</div></div>
<script>window.PrototypeBridge={enter(id){document.documentElement.dataset.protoState=id;}};</script></html>'''
        (child / 'index.html').write_text(sample, encoding='utf-8')
        (child / 'detail.html').write_text(sample.replace('data-proto-page="home"', 'data-proto-page="detail"').replace('href="detail.html"', 'href="index.html"'), encoding='utf-8')
        bundle = proto_meta.ensure_bundle(child)
        proto_meta.ensure_pages_registered(child, bundle)
        for page in bundle['project']['pages']:
            page['states'].append({'id': 'done', 'title': '已完成', 'kind': 'adapter'})
        proto_meta.save_bundle(child, bundle)
        pid = bundle['project']['id']
        registry = root / 'data/external.json'
        proto_meta.write_json_atomic(registry, {'projects': {pid: {'root': str(child), 'name': '隔离标注回归'}}, 'roots': []})
        ns = isolated_handler(registry)
        class FixtureHandler(ns['CustomHandler']):
            def translate_path(self, path):
                urlpath = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
                if urlpath.startswith('/src/vendor/'):
                    vendor = (SERVER.parent / 'src/vendor').resolve()
                    target = (vendor / urlpath[len('/src/vendor/'):]).resolve()
                    if vendor in target.parents and target.suffix in {'.js', '.css'} and target.is_file():
                        return str(target)
                    return str(root / 'missing')
                if urlpath.startswith('/src/'):
                    try:
                        return str(proto_meta.safe_asset(SERVER.parent / 'src', urlpath[5:]))
                    except (ValueError, FileNotFoundError):
                        return str(root / 'missing')
                return super().translate_path(path)
        handler = functools.partial(FixtureHandler, directory=str(root))
        with http.server.ThreadingHTTPServer(('127.0.0.1', port), handler) as server:
            print(f'http://127.0.0.1:{port}/src/viewer.html?ext={pid}', flush=True)
            server.serve_forever()


if __name__ == '__main__' and sys.argv[1:2] == ['--serve-preview']:
    serve_preview_fixture(int(sys.argv[2]) if len(sys.argv) > 2 else 8092)
