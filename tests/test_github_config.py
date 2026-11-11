"""GitHub 凭据状态与持久化失败回归；隔离配置，不触碰真实 Token。"""
import json
import os

import pytest

from test_external_api import api


@pytest.mark.parametrize('saved,token,state', [
    (False, '', 'missing'),
    (True, '', 'unreadable'),
    (True, 'isolated-fixture-token', 'ready'),
])
def test_config_distinguishes_missing_and_unreadable(api, tmp_path, monkeypatch, saved, token, state):
    token_file = tmp_path / 'token-fixture.bin'
    if saved:
        token_file.write_bytes(b'Dfixture-not-real-ciphertext')
    monkeypatch.delenv('PROTOTYPE_GITHUB_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    api.namespace.update(GITHUB_TOKEN_FILE=str(token_file), load_config=lambda: {},
        get_github_runtime_config=lambda: {'token': token, 'username': 'fixture', 'repo': 'fixture'})
    status, result = api.request('/api/github/config')
    assert status == 200 and result['success']
    assert result['tokenState'] == state
    assert result['hasToken'] is bool(token)
    assert 'token' not in result


def test_failed_token_storage_preserves_previous_config_and_environment(api, tmp_path, monkeypatch):
    config_file = tmp_path / 'fixture-config.json'
    original = {'github': {'username': 'before', 'repo': 'before'}}
    config_file.write_text(json.dumps(original), encoding='utf-8')
    monkeypatch.setenv('PROTOTYPE_GITHUB_TOKEN', 'previous-fixture-token')
    api.namespace.update(CONFIG_FILE=str(config_file), save_github_token=lambda token: False)
    status, result = api.request('/api/github/config',
        {'token': 'new-fixture-token', 'username': 'after', 'repo': 'after'})
    assert status == 200 and result['success'] is False and result['tokenStored'] is False
    assert os.environ['PROTOTYPE_GITHUB_TOKEN'] == 'previous-fixture-token'
    assert json.loads(config_file.read_text(encoding='utf-8')) == original


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16'])
def test_github_config_save_accepts_windows_unicode_settings(api, tmp_path, encoding):
    config_file = tmp_path / 'fixture-config.json'
    original = {'server': {'port': 8098}, 'custom': '保留同事的配置'}
    config_file.write_bytes(json.dumps(original, ensure_ascii=False).encode(encoding))
    api.namespace.update(CONFIG_FILE=str(config_file))
    status, result = api.request('/api/github/config', {'username': 'fixture', 'repo': 'fixture'})
    assert status == 200 and result['success']
    saved = json.loads(config_file.read_bytes())
    assert saved['server'] == original['server'] and saved['custom'] == original['custom']
    assert saved['github'] == {'username': 'fixture', 'repo': 'fixture'}
