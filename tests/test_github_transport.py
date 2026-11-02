"""GitHub 网络与凭据错误必须分开，失败时不泄露凭据或误报发布成功。"""
import json
import io

import pytest
import requests
from requests.adapters import BaseAdapter

import github_transport


class Transport(BaseAdapter):
    def __init__(self, status=200, headers=None, error=None):
        self.status, self.headers, self.error = status, headers or {}, error

    def send(self, request, **kwargs):
        if self.error:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response.headers.update(self.headers)
        response._content = json.dumps({'message': 'fixture'}).encode()
        response.request = request
        return response

    def close(self):
        pass


@pytest.mark.parametrize('status,headers,words,configure', [
    (401, {}, 'Token', True),
    (403, {}, '权限', True),
    (403, {'X-RateLimit-Remaining': '0'}, '频率', False),
    (429, {'Retry-After': '60'}, '频率', False),
])
def test_http_errors_have_actionable_categories(status, headers, words, configure):
    with github_transport.api_session('fixture-secret') as session:
        session.mount('https://', Transport(status, headers))
        with pytest.raises(github_transport.GitHubError) as caught:
            session.get('https://api.github.com/user', timeout=1)
        assert words in str(caught.value)
        assert str(status) in str(caught.value)
        assert caught.value.need_github_config is configure
        assert 'fixture-secret' not in str(caught.value)


@pytest.mark.parametrize('error,words', [
    (requests.exceptions.ConnectionError('10054 fixture-secret'), '连接中断'),
    (requests.exceptions.ProxyError('http://user:fixture-secret@proxy'), '代理'),
    (requests.exceptions.Timeout('fixture-secret'), '超时'),
    (requests.exceptions.RetryError('fixture-secret'), '服务暂时不可用'),
    (requests.exceptions.SSLError('fixture-secret'), '证书'),
])
def test_network_errors_do_not_invalidate_token_or_expose_connection_details(error, words):
    with github_transport.api_session('fixture-secret') as session:
        session.mount('https://', Transport(error=error))
        with pytest.raises(github_transport.GitHubError) as caught:
            session.get('https://api.github.com/user', timeout=1)
        assert words in str(caught.value)
        assert caught.value.need_github_config is False
        assert 'fixture-secret' not in str(caught.value)


def test_success_and_not_found_are_left_to_callers_and_writes_are_not_replayed():
    with github_transport.api_session('fixture-secret') as session:
        retry = session.get_adapter('https://').max_retries
        assert retry.total == 3 and retry.connect == 3
        assert 'GET' in retry.allowed_methods and 'POST' not in retry.allowed_methods
        assert session.trust_env is True and session.verify is True
        for status in (200, 201, 404, 409, 422):
            session.mount('https://', Transport(status))
            response = session.get('https://api.github.com/repos/fixture/fixture', timeout=1)
            assert response.status_code == status


@pytest.mark.parametrize('status,headers,configure', [
    (401, {}, True), (403, {}, True), (429, {'Retry-After': '60'}, False), (503, {}, False),
])
def test_connection_check_uses_shared_session_and_classifies_failures(tmp_path, status, headers, configure):
    from test_external_api import isolated_handler
    namespace = isolated_handler(tmp_path / 'isolated-registry.json')
    session = github_transport.api_session('fixture-secret')
    session.mount('https://', Transport(status, headers))
    namespace['github_api_session'] = lambda token: session
    namespace['get_github_runtime_config'] = lambda: {'token': 'fixture-secret'}
    handler = namespace['CustomHandler'].__new__(namespace['CustomHandler'])
    handler.headers = {'Content-Length': '2'}
    handler.rfile = io.BytesIO(b'{}')
    results = []
    handler.send_json_response = results.append
    handler.handle_github_test()
    assert len(results) == 1 and results[0]['success'] is False
    assert results[0].get('needGithubConfig', False) is configure
    assert str(status) in results[0]['message']
    assert 'fixture-secret' not in json.dumps(results)
