"""评审壳发布端点（/api/ext/publish|unpublish|publish-status）的隔离 HTTP 回归。
GitHub 网络层全部替换为假实现，断言导出调用、记录写入与错误路径；不加载真实配置、不起真实服务。"""
import ast
import datetime
import functools
import http.client
import http.server
import ipaddress
import json
import os
import posixpath
import tempfile
import threading
import urllib.parse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proto_meta
import review_export

SERVER = Path(__file__).resolve().parents[1] / 'server.py'


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


class FakeSession:
    """最小 GitHub API 替身：repo 查询 + contents 树形列举 + 删除记录。"""

    def __init__(self, tree=None):
        self.tree = tree or {}
        self.deleted = []

    def get(self, url, timeout=15, headers=None):
        if url.endswith('/repos/u/r'):
            return FakeResponse(200, {'default_branch': 'main'})
        if url in self.tree:
            return FakeResponse(200, self.tree[url])
        return FakeResponse(404, {})

    def delete(self, url, json=None, timeout=20):
        self.deleted.append((url, json))
        return FakeResponse(200, {})


def isolated_handler(registry, extra_globals):
    tree = ast.parse(SERVER.read_text(encoding='utf-8'))
    names = {'load_external_registry', 'save_external_registry', 'external_root_for', 'CustomHandler'}
    selected = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    ns = {**globals(), 'EXTERNAL_FILE': str(registry), 'EXTERNAL_LOCK': threading.RLock(), 'REQUEST_LOCK': threading.RLock()}
    ns.update(extra_globals)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SERVER), 'exec'), ns)
    return ns


@pytest.fixture
def api(tmp_path):
    calls = {'ensure': [], 'upload': [], 'listing': []}
    hooks = {'fail_upload': False}
    session = FakeSession()
    gh = {'token': 't', 'username': 'u', 'repo': 'r'}

    def fake_upload(sess, api_base, username, repo, branch, export_dir, remote_prefix):
        if hooks['fail_upload']:
            raise Exception('网络不可达')
        export = Path(export_dir)
        calls['upload'].append({
            'remote_prefix': remote_prefix,
            'branch': branch,
            'has_shell': (export / 'index.html').is_file(),
            'has_proto': (export / 'proto' / 'index.html').is_file(),
        })

    extra = {
        'proto_meta': proto_meta,
        'review_export': review_export,
        'get_github_runtime_config': lambda: dict(gh),
        'github_api_session': lambda token: session,
        'github_ensure_pages': lambda sess, api_base, username, repo: (calls['ensure'].append((username, repo)), 'main')[1],
        'github_upload_dir': fake_upload,
    }
    registry = tmp_path / 'data' / 'external.json'
    ns = isolated_handler(registry, extra)
    ns['CustomHandler'].update_github_listing = lambda self, *a, **k: calls['listing'].append(k)
    handler = functools.partial(ns['CustomHandler'], directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port

    def request(path, data=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        headers = {'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method or ('POST' if data is not None else 'GET'), path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, json.loads(raw) if raw else {})
        connection.close()
        return result

    yield SimpleNamespace(request=request, registry=registry, calls=calls, hooks=hooks, session=session, gh=gh, tmp_path=tmp_path, namespace=ns)
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def register_project(api, name='样例项目'):
    root = api.tmp_path / 'proj'
    root.mkdir()
    (root / 'index.html').write_text('<html lang="zh-CN" data-proto-page="home"><title>首页</title>', encoding='utf-8')
    pid = proto_meta.project_id_for(root)
    api.registry.parent.mkdir(parents=True, exist_ok=True)
    api.registry.write_text(json.dumps({'projects': {pid: {'root': str(root), 'title': name}}, 'roots': []}), encoding='utf-8')
    return pid, root


def test_publish_happy_path(api):
    pid, _ = register_project(api)
    status, res = api.request('/api/ext/publish', {'extId': pid})
    assert status == 200 and res['ok']
    assert res['url'] == f'https://u.github.io/r/projects/{pid}/'
    assert res['publishedAt']
    assert api.calls['ensure'] == [('u', 'r')], '建仓/Pages 管线应被复用'
    assert api.calls['upload'] == [{
        'remote_prefix': f'projects/{pid}', 'branch': 'main', 'has_shell': True, 'has_proto': True,
    }], '评审壳导出应完整上传'
    assert api.calls['listing'] and api.calls['listing'][0]['mode'] == 'review'
    saved = json.loads(api.registry.read_text(encoding='utf-8'))['projects'][pid]
    assert saved['github_url'] == res['url'] and saved['github_published_at']
    status, res = api.request(f'/api/ext/publish-status?projectId={urllib.parse.quote(pid)}')
    assert status == 200 and res['ok'] and res['published'] and res['url'] == saved['github_url']


def test_publish_without_token_writes_nothing(api):
    pid, _ = register_project(api)
    api.gh['token'] = ''
    status, res = api.request('/api/ext/publish', {'extId': pid})
    assert status == 400 and not res['ok'] and 'Token' in res['error']
    assert res.get('needGithubConfig') is True, '未配置必须带标记，viewer 据此弹配置引导'
    assert not api.calls['upload'], '无 Token 不应触发上传'
    saved = json.loads(api.registry.read_text(encoding='utf-8'))['projects'][pid]
    assert 'github_url' not in saved, '失败路径不得写本地发布记录'


def test_publish_upload_failure_writes_nothing(api):
    pid, _ = register_project(api)
    api.hooks['fail_upload'] = True
    status, res = api.request('/api/ext/publish', {'extId': pid})
    assert status == 500 and not res['ok'] and '网络不可达' in res['error']
    saved = json.loads(api.registry.read_text(encoding='utf-8'))['projects'][pid]
    assert 'github_url' not in saved, '上传失败不得写本地发布记录'


def test_publish_unregistered(api):
    status, res = api.request('/api/ext/publish', {'extId': 'p-0000000000000000'})
    assert status == 404 and not res['ok']


def test_unpublish_recurses_and_cleans(api):
    from test_pages_manager import Remote
    pid, _ = register_project(api)
    remote = Remote()
    remote.files = {'index.html': b'root', 'projects/index.html': b'listing', 'projects/other/index.html': b'keep',
                    f'projects/{pid}/index.html': b'shell', f'projects/{pid}/proto/index.html': b'prototype',
                    f'projects/{pid}/proto/pages/a.html': b'nested',
                    'projects/manifest.json': json.dumps([{'id': pid}, {'id': 'other'}]).encode()}
    api.gh.update(username='test-owner', repo='fixture-repo')
    api.namespace['github_api_session'] = lambda token: remote
    status, res = api.request('/api/ext/publish', {'extId': pid})
    assert res['ok']
    status, res = api.request('/api/ext/unpublish', {'extId': pid})
    assert status == 200 and res['ok']
    assert not any(path.startswith(f'projects/{pid}/') for path in remote.files), '嵌套目录必须完整删除'
    assert remote.files['projects/other/index.html'] == b'keep', '保留其他项目'
    assert [item['id'] for item in json.loads(remote.files['projects/manifest.json'])] == ['other']
    assert any(method == 'PATCH' and args['json']['force'] is False for method, _, args in remote.calls)
    saved = json.loads(api.registry.read_text(encoding='utf-8'))['projects'][pid]
    assert 'github_url' not in saved and 'github_published_at' not in saved
    status, res = api.request(f'/api/ext/publish-status?projectId={urllib.parse.quote(pid)}')
    assert res['ok'] and not res['published']


def test_unpublish_unregistered(api):
    status, res = api.request('/api/ext/unpublish', {'extId': 'p-0000000000000000'})
    assert status == 404 and not res['ok']


def test_unpublish_without_token_marks_need_config(api):
    pid, _ = register_project(api)
    api.gh['token'] = ''
    status, res = api.request('/api/ext/unpublish', {'extId': pid})
    assert status == 400 and not res['ok'] and res.get('needGithubConfig') is True


def test_publish_status_unregistered(api):
    status, res = api.request('/api/ext/publish-status?projectId=p-0000000000000000')
    assert status == 404 and not res['ok']
