"""项目隐藏 / 恢复 / 彻底删除，只操作隔离临时目录。"""
from pathlib import Path
import shutil

import proto_meta

from test_external_api import api, prototype


def listing(api):
    return api.request('/api/external/list')[1]


def test_connected_hide_keeps_registration_prd_and_does_not_rediscover(api, tmp_path):
    root = prototype(tmp_path/'collection'/'connected')
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    before = (root/'.prototype/prd.json').read_bytes()
    status, result = api.request('/api/external/hide', {'projectId': pid})
    assert status == 200 and result['ok']
    for _ in range(2):
        current = listing(api)
        assert current['items'] == [] and current['discovered'] == []
        assert current['hidden'][0]['projectId'] == pid
        assert not current['hidden'][0].get('discovered')
    assert pid in api.namespace['load_external_registry']()['projects']
    assert (root/'.prototype/prd.json').read_bytes() == before
    assert api.request('/api/proto/read?projectId='+pid)[0] == 200
    assert api.request('/api/external/restore', {'projectId': pid})[0] == 200
    assert listing(api)['items'][0]['projectId'] == pid and listing(api)['hidden'] == []


def test_discovered_hide_and_restore_do_not_initialize_or_connect(api, tmp_path):
    root = prototype(tmp_path/'collection'/'new')
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    pid = listing(api)['discovered'][0]['projectId']
    assert api.request('/api/external/hide', {'projectId': pid})[0] == 200
    assert listing(api)['discovered'] == [] and listing(api)['hidden'][0]['discovered']
    assert pid not in api.namespace['load_external_registry']()['projects']
    assert not (root/'.prototype').exists()
    # 停止监视后仍可从已隐藏找回；恢复只重新发现该目录，不连接。
    api.request('/api/external/roots/remove', {'path': str(root.parent)})
    assert listing(api)['hidden'][0]['projectId'] == pid
    assert api.request('/api/external/restore', {'projectId': pid})[0] == 200
    assert listing(api)['discovered'][0]['projectId'] == pid
    assert not (root/'.prototype').exists()


def test_legacy_remove_is_hide_and_delete_clears_hidden_record(api, tmp_path):
    root = prototype(tmp_path/'victim')
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    assert api.request('/api/external/remove', {'projectId': pid})[0] == 200
    assert listing(api)['items'] == [] and len(listing(api)['hidden']) == 1
    assert api.request('/api/external/delete', {'projectId': pid, 'expectedRoot': str(root)})[0] == 200
    assert not root.exists() and listing(api)['hidden'] == []


def test_discovered_can_delete_directly_or_while_hidden(api, tmp_path):
    base = tmp_path/'collection'
    first = prototype(base/'first'); second = prototype(base/'second')
    api.request('/api/external/roots/add', {'path': str(base)})
    entries = {item['name']: item['projectId'] for item in listing(api)['discovered']}
    assert api.request('/api/external/delete', {'projectId': entries['first']})[0] == 200
    assert not first.exists() and second.exists()
    assert api.request('/api/external/hide', {'projectId': entries['second']})[0] == 200
    assert api.request('/api/external/delete', {'projectId': entries['second']})[0] == 200
    assert not second.exists() and listing(api)['hidden'] == []
    assert not (base/'.prototype').exists()


def test_visibility_and_deletion_only_accept_known_projects_and_current_path(api, tmp_path):
    root = prototype(tmp_path/'safe')
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    for route in ('hide', 'restore', 'delete'):
        assert api.request('/api/external/'+route, {'projectId': 'unknown', 'path': str(root)})[0] == 404
        assert api.request('/api/external/'+route, {'projectId': pid}, {'Origin': 'https://evil.example'})[0] == 403
    assert api.request('/api/external/delete', {'projectId': pid, 'expectedRoot': str(tmp_path/'other')})[0] == 409
    assert (root/'index.html').exists()


def test_delete_parent_protects_other_discovered_and_hidden_children(api, tmp_path):
    base = tmp_path/'collection'
    parent = prototype(base/'parent')
    child = prototype(parent/'child')
    api.request('/api/external/roots/add', {'path': str(base)})
    registry = api.namespace['load_external_registry']()
    registry['roots'].append(str(parent))
    api.namespace['save_external_registry'](registry)
    entries = {Path(item['root']): item['projectId'] for item in listing(api)['discovered']}
    assert api.request('/api/external/hide', {'projectId': entries[child]})[0] == 200
    code, result = api.request('/api/external/delete', {'projectId': entries[parent]})
    assert code == 400 and '项目' in result['error']
    assert (child/'index.html').exists()


def test_missing_hidden_candidate_stays_recoverable_until_folder_returns(api, tmp_path):
    root = prototype(tmp_path/'collection'/'new')
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    pid = listing(api)['discovered'][0]['projectId']
    api.request('/api/external/hide', {'projectId': pid})
    moved = root.with_name('temporarily-moved'); root.rename(moved)
    assert listing(api)['hidden'][0]['exists'] is False
    assert api.request('/api/external/restore', {'projectId': pid})[0] == 400
    moved.rename(root)
    assert api.request('/api/external/restore', {'projectId': pid})[0] == 200


def test_copy_with_existing_metadata_stays_hidden_when_connected(api, tmp_path):
    original = prototype(tmp_path/'original')
    original_bundle = proto_meta.ensure_bundle(original)
    root = tmp_path/'collection'/'copied'
    shutil.copytree(original, root)
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    discovered_id = listing(api)['discovered'][0]['projectId']
    assert api.request('/api/external/hide', {'projectId': discovered_id})[0] == 200
    connected_id = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    assert connected_id == original_bundle['project']['id'] and connected_id != discovered_id
    current = listing(api)
    assert current['items'] == [] and current['discovered'] == []
    assert len(current['hidden']) == 1 and current['hidden'][0]['projectId'] == connected_id
    assert not current['hidden'][0].get('discovered')


def test_delete_failure_keeps_hidden_item_and_files(api, tmp_path, monkeypatch):
    root = prototype(tmp_path/'collection'/'new')
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    pid = listing(api)['discovered'][0]['projectId']
    api.request('/api/external/hide', {'projectId': pid})
    def fail(*args, **kwargs): raise OSError('模拟文件占用')
    monkeypatch.setattr(shutil, 'rmtree', fail)
    assert api.request('/api/external/delete', {'projectId': pid})[0] == 500
    assert (root/'index.html').exists() and listing(api)['hidden'][0]['projectId'] == pid
