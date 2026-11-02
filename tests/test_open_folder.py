"""打开项目目录：只允许本机同源、由服务端解析目录；不实际启动资源管理器。"""
from types import SimpleNamespace

import pytest
import proto_meta
from test_external_api import api, prototype
from test_ai_workbench import api as ai_api, make_ai


@pytest.fixture
def launched(monkeypatch):
    import os
    calls = []
    monkeypatch.setattr(os, 'startfile', lambda path, operation: calls.append((path, operation)), raising=False)
    return calls


def windows(api):
    api.namespace['sys'] = SimpleNamespace(platform='win32')


@pytest.mark.parametrize('kind', ['registered', 'discovered', 'hidden'])
def test_opens_known_local_folder_without_connecting_or_writing(api, tmp_path, launched, kind):
    windows(api)
    root = prototype(tmp_path / '课件 项目')
    pid = proto_meta.project_id_for(root)
    registry = {'projects': {}, 'roots': [], 'hiddenProjects': {}}
    if kind == 'registered': registry['projects'][pid] = {'root': str(root), 'name': root.name}
    elif kind == 'discovered': registry['roots'] = [str(root.parent)]
    else: registry['hiddenProjects'][pid] = {'root': str(root), 'name': root.name}
    api.namespace['save_external_registry'](registry)
    before = api.registry.read_bytes()
    files = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    status, result = api.request('/api/home/open-folder', {'source': 'local', 'projectId': pid})
    assert status == 200 and result['ok'], result
    assert launched == [(str(root.resolve()), 'explore')]
    assert api.registry.read_bytes() == before
    assert {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()} == files
    assert not (root / '.prototype').exists()


def test_rejects_cross_site_and_client_supplied_unknown_path(api, tmp_path, launched):
    windows(api)
    root = prototype(tmp_path / 'arbitrary')
    body = {'source': 'local', 'projectId': 'unknown', 'path': str(root)}
    assert api.request('/api/home/open-folder', body, {'Origin': 'https://evil.example'})[0] == 403
    assert api.request('/api/home/open-folder', body, {'Content-Type': 'text/plain'})[0] == 415
    assert api.request('/api/home/open-folder', body)[0] == 404
    for body in ({'projectId': []}, {'source': 'other', 'projectId': 'unknown'}, {}):
        assert api.request('/api/home/open-folder', body)[0] == 400
    assert launched == []


@pytest.mark.parametrize('failure,status', [('missing', 404), ('linked', 400), ('launch', 503)])
def test_missing_linked_or_failed_launch_reports_error(api, tmp_path, launched, monkeypatch, failure, status):
    windows(api)
    root = tmp_path / 'folder'
    if failure != 'missing': root.mkdir()
    pid = proto_meta.project_id_for(root)
    api.namespace['save_external_registry']({'projects': {pid: {'root': str(root)}}, 'roots': []})
    if failure == 'linked': monkeypatch.setattr(proto_meta, 'is_linked_path', lambda path: True)
    if failure == 'launch':
        def unavailable(*args): raise OSError('fixture launch failure')
        monkeypatch.setattr(__import__('os'), 'startfile', unavailable)
    actual, result = api.request('/api/home/open-folder', {'projectId': pid})
    assert actual == status and not result['ok']
    assert launched == []


def test_ai_folder_supports_pending_project_and_keeps_access_control(ai_api, launched):
    windows(ai_api)
    root = make_ai(ai_api)
    body = {'source': 'ai', 'projectId': root.name}
    status, result, _ = ai_api.request('/api/home/open-folder', body)
    assert status == 200 and result['ok']
    assert launched == [(str(root.resolve()), 'explore')]
    assert not (root / '.prototype').exists()
    ai_api.namespace['USER'] = {'id': 42}
    ai_api.owners[root.name] = 77
    ai_api.namespace['ACCESS'] = False
    assert ai_api.request('/api/home/open-folder', body)[0] == 403
    assert ai_api.request('/api/home/open-folder', {**body, 'projectId': '../outside'})[0] == 400
    assert len(launched) == 1


@pytest.mark.parametrize('platform,command', [('darwin', 'open'), ('linux', 'xdg-open')])
def test_other_platforms_launch_folder_with_an_argument_list(api, tmp_path, platform, command):
    root = prototype(tmp_path / 'folder with spaces')
    pid = proto_meta.project_id_for(root)
    api.namespace['save_external_registry']({'projects': {pid: {'root': str(root)}}, 'roots': []})
    calls = []
    api.namespace.update(sys=SimpleNamespace(platform=platform),
                         subprocess=SimpleNamespace(DEVNULL=-3, Popen=lambda args, **kwargs: calls.append((args, kwargs))))
    assert api.request('/api/home/open-folder', {'projectId': pid})[0] == 200
    assert calls == [([command, str(root.resolve())], {'stdout': -3, 'stderr': -3, 'start_new_session': True})]
