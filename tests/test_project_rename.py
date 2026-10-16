"""改名只使用隔离目录，验证 PRD、身份和磁盘的一致性。"""
import copy
import json
from pathlib import Path

import pytest

import proto_meta
import project_rename
from test_external_api import api, prototype


def connect(api, root):
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    bundle = api.request('/api/proto/read?projectId=' + pid)[1]['bundle']
    bundle['prd']['annotations'] = [{'id': 'keep', 'pageId': bundle['project']['pages'][0]['id'], 'stateId': 'default', 'number': 1, 'body': '手工保留的标注', 'placement': {'kind': 'document', 'x': 20, 'y': 80}}]
    bundle['prd']['deletedAnnotations'] = [{'pageId': bundle['project']['pages'][0]['id'], 'stateId': 'default', 'protoId': 'deleted-by-user'}]
    bundle['revision'] += 1
    proto_meta.save_bundle(root, bundle)
    return pid, bundle


def test_rename_reconnect_scan_export_preserves_identity_and_prd(api, tmp_path):
    parent = tmp_path / 'collection'
    root = prototype(parent / 'old')
    pid, before = connect(api, root)
    api.request('/api/external/roots/add', {'path': str(parent)})
    payload = {'projectId': pid, 'name': '新的项目名称', 'expectedRevision': before['revision']}
    assert api.request('/api/proto/rename-project', payload, {'Origin': 'https://evil.example'})[0] == 403
    status, data = api.request('/api/proto/rename-project', payload)
    assert status == 200, data
    destination = parent / payload['name']
    assert destination.is_dir() and not root.exists()
    assert data['bundle']['project']['id'] == pid
    assert data['bundle']['prd'] == before['prd']
    assert data['bundle']['project']['pages'][0]['url'] == (destination / 'index.html').as_uri()
    assert api.request('/ext/' + pid + '/index.html')[0] == 200
    assert api.request('/api/proto/read?projectId=' + pid)[1]['bundle'] == data['bundle']
    assert api.request('/api/external/add', {'path': str(destination)})[1]['projectId'] == pid
    assert api.request('/api/external/list')[1]['discovered'] == []
    assert api.request('/api/proto/rename-project', {**payload, 'name': '再次改名'})[0] == 409
    api.request('/api/external/remove', {'projectId': pid})
    assert api.request('/api/external/add', {'path': str(destination)})[1]['projectId'] == pid


@pytest.mark.parametrize('name', ['', '../outside', 'nested/name', 'bad:name', 'CON', 'name.', '.hidden', 'dist', 'a' * 101])
def test_invalid_names_leave_everything_untouched(api, tmp_path, name):
    root = prototype(tmp_path / 'safe')
    pid, bundle = connect(api, root)
    status, data = api.request('/api/proto/rename-project', {'projectId': pid, 'name': name, 'expectedRevision': bundle['revision']})
    assert status == 400, data
    assert root.exists() and proto_meta.load_bundle(root) == bundle


def test_collision_and_overlapping_projects_are_rejected(api, tmp_path):
    root = prototype(tmp_path / 'source')
    occupied = prototype(tmp_path / 'occupied')
    pid, bundle = connect(api, root)
    payload = {'projectId': pid, 'expectedRevision': bundle['revision']}
    assert api.request('/api/proto/rename-project', {**payload, 'name': 'occupied'})[0] == 400
    assert occupied.exists() and root.exists()
    nested = prototype(root / 'nested')
    api.request('/api/external/add', {'path': str(nested)})
    assert api.request('/api/proto/rename-project', {**payload, 'name': 'renamed'})[0] == 400
    assert nested.exists() and root.exists()


def test_write_failure_restores_folder_metadata_and_registry(api, tmp_path, monkeypatch):
    root = prototype(tmp_path / 'rollback')
    pid, before = connect(api, root)
    registry_before = api.registry.read_bytes()
    def fail(*args):
        raise OSError('模拟磁盘写入失败')
    monkeypatch.setattr(proto_meta, 'save_bundle', fail)
    status, _ = api.request('/api/proto/rename-project', {'projectId': pid, 'name': 'should-not-remain', 'expectedRevision': before['revision']})
    assert status == 400
    assert root.exists() and not (tmp_path / 'should-not-remain').exists()
    assert proto_meta.load_bundle(root) == before
    assert json.loads(api.registry.read_bytes()) == json.loads(registry_before)


def test_ai_rename_moves_listing_record_and_keeps_remote_id(tmp_path):
    root = prototype(tmp_path / 'old-ai')
    bundle = proto_meta.ensure_bundle(root)
    pid = bundle['project']['id']
    record = {'projectName': 'Old', 'projectId': root.name, 'github_url': 'https://example.test/old-published/'}
    (root / 'record.json').write_text(json.dumps(record), encoding='utf-8')
    listing = tmp_path / 'projects.json'
    listing.write_text(json.dumps([{'id': root.name, 'name': 'Old', 'url': '/projects/old-ai/index.html'}]), encoding='utf-8')
    registry = {'roots': [], 'projects': {pid: {'root': str(root), 'source': 'ai', 'aiProjectId': root.name, 'github_url': record['github_url']}}}
    identities = []
    result = project_rename.rename(root, bundle, registry, pid, '新 AI 项目', bundle['revision'], lambda value: None, projects_file=listing, migrate_ai=lambda old, new: identities.append((old, new)))
    destination = tmp_path / '新 AI 项目'
    assert destination.is_dir() and not root.exists()
    assert identities == [('old-ai', '新 AI 项目')]
    assert json.loads(listing.read_text(encoding='utf-8'))[0]['id'] == '新 AI 项目'
    assert json.loads((destination / 'record.json').read_text(encoding='utf-8'))['projectName'] == '新 AI 项目'
    assert registry['projects'][pid]['github_remote_id'] == 'old-ai'
    assert registry['projects'][pid]['github_url'] == record['github_url']
    again = proto_meta.ensure_ai_project_bundle(destination, {}, [], '新 AI 项目')
    assert again['project']['id'] == pid and again['prd'] == bundle['prd']


def test_ai_registry_failure_rolls_back_migrated_identity_and_files(tmp_path):
    root = prototype(tmp_path / 'old-ai')
    bundle = proto_meta.ensure_bundle(root)
    pid = bundle['project']['id']
    listing = tmp_path / 'projects.json'
    listing.write_text('[]', encoding='utf-8')
    registry = {'roots': [], 'projects': {pid: {'root': str(root), 'source': 'ai', 'aiProjectId': root.name}}}
    before = copy.deepcopy(registry)
    identities = []
    calls = []
    def save(value):
        calls.append(copy.deepcopy(value))
        if len(calls) == 1:
            raise OSError('registry failed')
    with pytest.raises(OSError):
        project_rename.rename(root, bundle, registry, pid, 'new', bundle['revision'], save, projects_file=listing, migrate_ai=lambda a, b: identities.append((a, b)))
    assert identities == [('old-ai', 'new'), ('new', 'old-ai')]
    assert root.exists() and not (tmp_path / 'new').exists()
    assert registry == before and listing.read_text(encoding='utf-8') == '[]'
    assert proto_meta.load_bundle(root) == bundle


def test_database_ownership_and_shares_move_together(monkeypatch):
    import sqlite3
    import db
    conn = sqlite3.connect(':memory:')
    conn.executescript('CREATE TABLE project_ownership(project_id TEXT PRIMARY KEY,owner_id INTEGER); CREATE TABLE project_shares(project_id TEXT,team_id INTEGER,PRIMARY KEY(project_id,team_id)); INSERT INTO project_ownership VALUES("old",7); INSERT INTO project_shares VALUES("old",3);')
    monkeypatch.setattr(db, 'get_conn', lambda: conn)
    db.rename_project_identity('old', 'new')
    assert conn.execute('SELECT * FROM project_ownership').fetchall() == [('new', 7)]
    assert conn.execute('SELECT * FROM project_shares').fetchall() == [('new', 3)]
    conn.execute('INSERT INTO project_shares VALUES("occupied",4)'); conn.commit()
    with pytest.raises(ValueError):
        db.rename_project_identity('new', 'occupied')
    assert conn.execute('SELECT * FROM project_ownership').fetchall() == [('new', 7)]
    conn.close()


def test_case_only_directory_rename(api, tmp_path):
    root = prototype(tmp_path / 'CamelProject')
    pid, bundle = connect(api, root)
    status, data = api.request('/api/proto/rename-project', {'projectId': pid, 'name': 'camelproject', 'expectedRevision': bundle['revision']})
    assert status == 200, data
    assert 'camelproject' in [p.name for p in tmp_path.iterdir()]
    assert data['bundle']['prd'] == bundle['prd']
