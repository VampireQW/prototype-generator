"""AI 项目接入本地工作台的隔离回归；仅写临时项目，不调用 AI / GitHub。"""
import functools
import http.client
import http.server
import json
import re
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_external_api import isolated_handler
import proto_meta
import review_export


@pytest.fixture
def api(tmp_path, monkeypatch):
    registry = tmp_path / 'data' / 'external.json'
    ns = isolated_handler(registry)
    project_dir = tmp_path / 'projects'
    project_dir.mkdir()
    listing = tmp_path / 'data' / 'projects.json'
    listing.parent.mkdir()
    listing.write_text('[]', encoding='utf-8')
    owners = {}
    ns.update(PROJECTS_DIR=str(project_dir), PROJECTS_FILE=str(listing), USER=None, ACCESS=True, re=re,
              get_base_path=lambda: str(tmp_path),
              db=SimpleNamespace(get_project_owner=lambda pid: owners.get(pid),
                                 set_project_owner=lambda pid, uid: owners.update({pid: uid}),
                                 can_user_access_project=lambda pid, uid: ns['ACCESS']))
    ns['CustomHandler'].get_current_user = lambda self: ns['USER']
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: None)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(ns['CustomHandler'], directory=str(tmp_path)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port

    def request(path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        supplied = {'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        supplied.update(headers or {})
        connection.request('POST' if data is not None else 'GET', path,
                           json.dumps(data).encode('utf-8') if data is not None else None, supplied)
        response = connection.getresponse()
        raw = response.read()
        ctype = response.getheader('Content-Type', '')
        value = json.loads(raw) if 'application/json' in ctype else raw
        result = (response.status, value, dict(response.getheaders()))
        connection.close()
        return result

    yield SimpleNamespace(request=request, namespace=ns, registry=registry, projects=project_dir, listing=listing, owners=owners)
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def make_ai(api, name='ai-20261004', record=None, html=None):
    root = api.projects / name
    root.mkdir()
    (root / 'index.html').write_text(html or '<html><title>AI 首页</title><body><button>查看</button></body></html>', encoding='utf-8')
    (root / 'record.json').write_text(json.dumps(record or {}, ensure_ascii=False), encoding='utf-8')
    api.listing.write_text(json.dumps([{'id': name, 'name': 'AI 验收项目', 'url': f'/projects/{name}/index.html'}], ensure_ascii=False), encoding='utf-8')
    return root


def connect(api, root):
    code, data, _ = api.request('/api/projects/workbench', {'projectId': root.name})
    assert code == 200, data
    return data


def test_workbench_rename_keeps_identity_access_and_published_target(api):
    root = make_ai(api, record={'projectName': 'AI 验收项目'})
    result = connect(api, root)
    pid = result['projectId']
    api.owners[root.name] = 42
    def migrate(old, new):
        if old in api.owners:
            api.owners[new] = api.owners.pop(old)
    api.namespace['db'].rename_project_identity = migrate
    api.namespace['USER'] = {'id': 42}
    code, renamed, _ = api.request('/api/proto/rename-project', {'projectId': pid, 'name': '团队原型', 'expectedRevision': result['revision']})
    assert code == 200, renamed
    assert not root.exists() and (api.projects / '团队原型').is_dir()
    assert api.owners == {'团队原型': 42}
    assert api.request('/api/proto/read?projectId=' + pid)[0] == 200
    connected = api.request('/api/projects/workbench', {'projectId': '团队原型'})[1]
    assert connected['projectId'] == pid
    item = json.loads(api.registry.read_text(encoding='utf-8'))['projects'][pid]
    assert item['github_remote_id'] == root.name
    assert connected['name'] == '团队原型'
    api.namespace['ACCESS'] = False
    api.namespace['USER'] = {'id': 99}
    assert api.request('/api/proto/rename-project', {'projectId': pid, 'name': '无权更名', 'expectedRevision': connected['revision']})[0] == 403


def test_pending_ai_project_can_rename_without_placeholder_html(api):
    root = make_ai(api)
    (root / 'index.html').unlink()
    api.namespace['db'].rename_project_identity = lambda *args: None
    status, result, _ = api.request('/rename-project', {'id': root.name, 'newName': '尚未生成'})
    assert status == 200, result
    assert result['success'] and result['project']['id'] == '尚未生成'
    assert not root.exists() and (api.projects / '尚未生成' / 'record.json').exists()
    assert not (api.projects / '尚未生成' / 'index.html').exists()


def test_contract_idempotent_migration_and_local_list(api, tmp_path):
    root = make_ai(api, record={'global': {'skillId': 'mobile-app'}, 'pages': [
        {'name': 'home', 'layout': '首页布局', 'features': '首页功能'},
        {'name': 'detail', 'layout': '详情布局', 'features': '详情功能'}]},
        html='<html><body><section v-if="currentPage === \'home\'">首页</section><section v-if="currentPage === \'detail\'">详情</section></body></html>')
    (root / 'prd').mkdir()
    (root / 'prd' / 'home.md').write_text('# 旧首页需求\n\n保留旧文档', encoding='utf-8')
    result = connect(api, root)
    assert result['aiProjectId'] == root.name
    assert result['projectId'] == proto_meta.project_id_for(root)
    assert result['viewerUrl'] == '/src/viewer.html?ext=' + result['projectId']
    bundle = proto_meta.load_bundle(root)
    assert bundle['project']['previewType'] == 'mobile'
    assert bundle['project']['source'] == 'ai'
    page = bundle['project']['pages'][0]
    assert page['aiNavigation'] == 'legacy'
    assert {s['legacyPage'] for s in page['states'] if 'legacyPage' in s} == {'home', 'detail'}
    docs = {d['stateId']: d['markdown'] for d in bundle['prd']['documents']}
    assert docs['home'] == '# 旧首页需求\n\n保留旧文档'
    assert 'detail' not in docs  # 未明确提供背景 / 目标的页面不自动补写 PRD。
    assert api.request('/api/external/list')[1]['items'] == []
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'index.html').write_text('<button>本地</button>', encoding='utf-8')
    assert api.request('/api/external/add', {'path': str(local)})[0] == 200
    assert len(api.request('/api/external/list')[1]['items']) == 1
    assert connect(api, root)['revision'] == bundle['revision']
    # 用户保存过的标注、任务和文档不可被二次转换重置。
    bundle['prd']['annotations'].append({'id': 'note', 'pageId': page['id'], 'stateId': 'home', 'number': 1,
        'body': '用户标注', 'confirmed': True, 'placement': {'kind': 'document', 'x': 0, 'y': 100}})
    bundle['prd']['documents'][0]['markdown'] = '用户修改过的需求'
    bundle['revision'] += 1
    proto_meta.save_bundle(root, bundle)
    (root / 'prd' / 'home.md').write_text('后来旧文档', encoding='utf-8')
    connect(api, root)
    assert proto_meta.load_bundle(root) == bundle


def test_modern_bridge_states_without_layout_and_unknown_preview(api):
    root = make_ai(api, record={'pages': [{'name': '首页', 'features': '查看课程'}, {'name': '练习详情', 'interaction': '提交练习'}]},
        html='<html data-proto-state="首页"><script>window.PrototypeBridge={enter(stateId){}};</script></html>')
    connect(api, root)
    bundle = proto_meta.load_bundle(root)
    page = bundle['project']['pages'][0]
    assert {state['id'] for state in page['states']} >= {'首页', '练习详情'}
    assert 'aiNavigation' not in page
    assert 'previewType' not in bundle['project']
    assert bundle['prd']['documents'] == []
    assert api.request('/api/proto/save', {'projectId': bundle['project']['id'], 'expectedRevision': bundle['revision'], 'bundle': bundle})[0] == 200


def test_multiple_real_files_remain_pages(api):
    root = make_ai(api, record={'pageLayout': 'split', 'pages': [{'name': '课程列表', 'features': '列出课程'}, {'name': '课程详情', 'features': '查看详情'}]})
    (root / 'pages').mkdir()
    for name in ('课程列表', '课程详情'):
        (root / 'pages' / (name + '.html')).write_text(f'<title>{name}</title>', encoding='utf-8')
    connect(api, root)
    bundle = proto_meta.load_bundle(root)
    assert {page['file'] for page in bundle['project']['pages']} == {'index.html', 'pages/课程列表.html', 'pages/课程详情.html'}
    assert all(len(page['states']) == 1 for page in bundle['project']['pages'])
    assert bundle['prd']['documents'] == []


def test_duplicate_modern_view_names_get_independent_states(api):
    root = make_ai(api, record={'pages': [{'name': '课程', 'features': '课程入口'}, {'name': '课程', 'features': '课程详情'}]},
                   html='<html data-proto-state="default"><script>window.PrototypeBridge={enter(stateId){}};</script></html>')
    connect(api, root)
    bundle = proto_meta.load_bundle(root)
    assert {state['id'] for state in bundle['project']['pages'][0]['states']} >= {'课程', '课程-2'}
    docs = {doc['stateId']: doc['markdown'] for doc in bundle['prd']['documents']}
    assert docs == {}


@pytest.mark.parametrize('layout,count,expected', [('single', 2, 'single'), ('split', 2, 'split'), ('auto', 4, 'split')])
def test_external_ai_package_uses_workbench_contract(api, layout, count, expected):
    api.namespace.update(DEFAULT_SKILL_ID='web-prototype', get_design_system_context=lambda *args: '', get_skill_context=lambda *args, **kwargs: '')
    body = {'projectId': 'external-contract', 'projectName': '课程管理', 'pageLayout': layout, 'prompt': '用户生成要求',
            'formData': {'global': {'skillId': 'mobile-app', 'previewType': 'mobile'}, 'pages': [{'name': f'页面{i + 1}'} for i in range(count)]}}
    code, result, _ = api.request('/create-ai-ide-package', body)
    assert code == 200 and result['success'], result
    root = api.projects / body['projectId']
    rules = (root / 'AGENTS.md').read_text(encoding='utf-8')
    task = (root / 'TASK.md').read_text(encoding='utf-8')
    assert 'data-proto-id' in rules and 'data-proto-preview="mobile"' in rules
    assert '导航、Tab、路由和弹层切换' in rules and 'PrototypeBridge.enter(stateId)' in task
    assert json.loads((root / 'record.json').read_text(encoding='utf-8'))['pageLayout'] == expected
    assert ('pages/` 下独立 HTML' in rules) == (expected == 'split')


def test_legacy_upgraded_to_author_bridge_keeps_prd_and_annotations(api):
    root = make_ai(api, record={'pages': [{'name': 'home', 'features': '首页功能'}, {'name': 'detail', 'features': '详情功能'}]},
                   html='<div v-if="currentPage === \'home\'">首页</div><div v-if="currentPage === \'detail\'">详情</div>')
    connect(api, root)
    old = proto_meta.load_bundle(root)
    old['prd']['annotations'].append({'id': 'keep', 'pageId': old['project']['pages'][0]['id'], 'stateId': 'home',
                                      'number': 1, 'body': '已确认标注', 'confirmed': True})
    old['revision'] += 1
    proto_meta.save_bundle(root, old)
    (root / 'index.html').write_text('<html data-proto-state="home"><script>window.PrototypeBridge={enter(id){}};</script></html>', encoding='utf-8')
    connect(api, root)
    upgraded = proto_meta.load_bundle(root)
    assert 'aiNavigation' not in upgraded['project']['pages'][0]
    assert upgraded['prd'] == old['prd']
    assert connect(api, root)['revision'] == upgraded['revision']


def test_safe_ids_origin_pending_and_corrupt_metadata(api):
    root = make_ai(api)
    for unsafe in ('../ai', '/absolute', 'C:folder', 'x\\y', 'x/y', 'x.', '..', None):
        assert api.request('/api/projects/workbench', {'projectId': unsafe})[0] == 400
    assert api.request('/api/projects/workbench', {'projectId': 'missing'})[0] == 404
    assert api.request('/api/projects/workbench', {'projectId': root.name}, {'Origin': 'https://evil.example'})[0] == 403
    assert api.request('/api/projects/workbench', {'projectId': root.name}, {'Content-Type': 'text/plain'})[0] == 415
    pending = api.projects / 'pending'
    pending.mkdir()
    (pending / 'record.json').write_text('{}', encoding='utf-8')
    assert api.request('/api/projects/workbench', {'projectId': 'pending'})[0] == 404
    (root / '.prototype').mkdir()
    (root / '.prototype' / 'project.json').write_text('{broken', encoding='utf-8')
    assert api.request('/api/projects/workbench', {'projectId': root.name})[0] == 409
    assert (root / '.prototype' / 'project.json').read_text(encoding='utf-8') == '{broken'


def test_permissions_apply_to_workbench_and_all_unified_paths(api):
    root = make_ai(api)
    api.namespace['USER'] = {'id': 1}
    result = connect(api, root)
    assert api.owners[root.name] == 1
    pid = result['projectId']
    api.namespace['USER'] = {'id': 2}
    api.namespace['ACCESS'] = False
    requests = [('/api/projects/workbench', {'projectId': root.name}),
                ('/api/proto/read?projectId=' + pid, None), ('/ext/' + pid + '/index.html', None),
                ('/api/proto/save', {'projectId': pid}), ('/api/proto/upload-image', {'projectId': pid}),
                ('/api/ext/publish-status?projectId=' + pid, None), ('/api/ext/export?extId=' + pid, None),
                ('/api/ext/publish', {'extId': pid}), ('/api/ext/unpublish', {'extId': pid})]
    for path, data in requests:
        assert api.request(path, data)[0] == 403, path


def test_embedded_rejected_before_any_export_or_github_call(api):
    root = make_ai(api)
    for path in ('/api/export', '/api/github/publish'):
        code, body, _ = api.request(path, {'projectId': root.name, 'mode': 'embedded'})
        assert code == 400 and '内嵌版已移除' in body['error']
    assert not (root / '.prototype').exists()


def test_legacy_export_aliases_use_same_builders(api):
    root = make_ai(api, record={'pages': [{'name': '首页', 'features': '课程'}]})
    for mode in ('preview', 'dev'):
        code, data, _ = api.request('/api/export', {'projectId': root.name, 'mode': mode})
        assert code == 200, data
        output = Path(data['exportPath'])
        assert (output / 'index.html').is_file()
        assert (output / 'proto' / 'index.html').exists() == (mode == 'dev')
    pure = api.request('/api/ext/export?extId=' + proto_meta.project_id_for(root) + '&mode=pure')
    assert pure[0] == 200 and pure[1] == (root / 'index.html').read_bytes()
    review = api.request('/api/ext/export?extId=' + proto_meta.project_id_for(root) + '&mode=review')
    assert review[0] == 200 and review[1].startswith(b'PK')


def test_old_publication_identity_and_new_publish_sync(api, monkeypatch):
    original_url = 'https://fixture.github.io/fixture/projects/ai-20261004/'
    root = make_ai(api, record={'github_url': original_url, 'github_published_at': '2026-10-01', 'github_mode': 'dev'})
    result = connect(api, root)
    pid = result['projectId']
    status = api.request('/api/ext/publish-status?projectId=' + pid)[1]
    assert status['published'] and status['url'] == original_url and status['mode'] == 'review'
    uploads, listing, unpublishes = [], [], []

    class Session:
        def get(self, url, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {'default_branch': 'main'} if url.endswith('/repos/fixture/fixture') else [])

    import github_pages
    def unpublish(session, owner, repo, remote_id, head, render_index, **kwargs):
        unpublishes.append((owner, repo, remote_id, kwargs.get('expected_url')))
        return {'ok': True, 'overview': {'pagesUrl': 'https://fixture.github.io/fixture/'}}
    monkeypatch.setattr(github_pages, 'unpublish', unpublish)

    api.namespace.update(get_github_runtime_config=lambda: {'token': 'isolated-test', 'username': 'fixture', 'repo': 'fixture'},
                         github_api_session=lambda token: Session(), github_ensure_pages=lambda *a: 'main',
                         github_upload_dir=lambda *a: uploads.append(a[-1]))
    api.namespace['CustomHandler'].update_github_listing = lambda self, *a, **kwargs: listing.append(kwargs)
    code, published, _ = api.request('/api/ext/publish', {'extId': pid, 'mode': 'review'})
    assert code == 200, published
    assert uploads == ['projects/' + root.name]
    assert published['url'].endswith('/projects/' + root.name + '/')
    assert json.loads((root / 'record.json').read_text(encoding='utf-8'))['github_url'] == published['url']
    assert json.loads(api.listing.read_text(encoding='utf-8'))[0]['github_url'] == published['url']
    assert listing[-1]['project_id'] == root.name
    assert api.request('/api/ext/unpublish', {'extId': pid})[0] == 200
    assert unpublishes == [('fixture', 'fixture', root.name, published['url'])]
    assert 'github_url' not in json.loads((root / 'record.json').read_text(encoding='utf-8'))
    assert 'github_url' not in json.loads(api.listing.read_text(encoding='utf-8'))[0]
    assert not api.request('/api/ext/publish-status?projectId=' + pid)[1]['published']


def test_review_export_includes_legacy_bridge_configuration(api, tmp_path):
    root = make_ai(api, html='<div v-if="currentPage === \'home\'">首页</div><div v-if="currentPage === \'detail\'">详情</div>')
    connect(api, root)
    bundle = proto_meta.load_bundle(root)
    output = tmp_path / 'review'
    review_export.build_review_export(root, bundle, output)
    html = (output / 'proto' / 'index.html').read_text(encoding='utf-8')
    assert 'window.__PROTO_NAVIGATION__=' in html
    assert '"legacyPage": "detail"' in html
    assert html.index('data-proto-review="navigation"') < html.index('data-proto-review="anchors"')
    pure = tmp_path / 'pure'
    review_export.build_pure_export(root, bundle, pure)
    assert (pure / 'index.html').read_bytes() == (root / 'index.html').read_bytes()


def test_ai_exports_only_deliver_prototype_and_review_data(api, tmp_path):
    root = make_ai(api)
    for filename in ('AGENTS.md', 'TASK.md', 'DESIGN.md', 'prompt.full.md'):
        (root / filename).write_text('项目生成资料', encoding='utf-8')
    for directory in ('pages', 'prd', 'assets'):
        (root / directory).mkdir()
    (root / 'pages' / '需求.md').write_text('原始需求', encoding='utf-8')
    (root / 'prd' / '首页.md').write_text('页面需求', encoding='utf-8')
    (root / 'assets' / 'record.json').write_text('{"runtime":true}', encoding='utf-8')
    connect(api, root)
    bundle = proto_meta.load_bundle(root)
    for mode, builder in (('pure', review_export.build_pure_export), ('review', review_export.build_review_export)):
        out = tmp_path / mode
        result = builder(root, bundle, out)
        proto = out / 'proto' if mode == 'review' else out
        assert (proto / 'assets' / 'record.json').is_file()
        assert (proto / 'index.html').is_file()
        for filename in ('record.json', 'AGENTS.md', 'TASK.md', 'DESIGN.md', 'prompt.full.md', 'pages/需求.md', 'prd/首页.md'):
            assert not (proto / filename).exists(), (mode, filename)
        if mode == 'review':
            assert '页面需求' in (out / 'index.html').read_text(encoding='utf-8')
        assert result['files']
