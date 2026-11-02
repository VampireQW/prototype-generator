"""GitHub 共用连接：沿用系统代理与 TLS 校验，区分网络、凭据和访问频率。"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GitHubError(ValueError):
    def __init__(self, message, *, need_github_config=False, status=502):
        super().__init__(message)
        self.need_github_config = need_github_config
        self.status = status


class GitHubSession(requests.Session):
    def send(self, request, **kwargs):
        try:
            response = super().send(request, **kwargs)
        except requests.exceptions.SSLError as error:
            raise GitHubError('GitHub 安全连接的证书校验失败，请检查系统时间和代理证书') from error
        except requests.exceptions.ProxyError as error:
            raise GitHubError('GitHub 代理连接失败，请确认系统代理正在运行且允许访问 api.github.com') from error
        except requests.exceptions.Timeout as error:
            raise GitHubError('连接 GitHub 超时，请检查网络和系统代理后重试') from error
        except requests.exceptions.RetryError as error:
            raise GitHubError('GitHub 服务暂时不可用，自动重试后仍失败，请稍后重试', status=503) from error
        except requests.exceptions.ConnectionError as error:
            raise GitHubError('GitHub 连接中断，自动重试后仍未连接；请检查网络和系统代理后重试') from error
        status = response.status_code
        if status == 401:
            response.close()
            raise GitHubError('GitHub Token 验证失败（HTTP 401），可能已过期或被撤销；请在 GitHub 配置中更新 Token',
                              need_github_config=True, status=400)
        if status == 429 or status == 403 and (response.headers.get('X-RateLimit-Remaining') == '0' or response.headers.get('Retry-After')):
            response.close()
            raise GitHubError(f'GitHub 请求频率受限（HTTP {status}），请稍后重试', status=503)
        if status == 403:
            response.close()
            raise GitHubError('GitHub 拒绝访问（HTTP 403），请检查 Token 的仓库权限及 GitHub Pages 权限',
                              need_github_config=True, status=400)
        return response


def api_session(token):
    session = GitHubSession()
    # 连接建立前的失败允许重试；收到或等待写入结果后不自动重放 POST / PATCH，避免重复操作。
    retry = Retry(total=3, backoff_factor=1, connect=3, read=3,
                  status_forcelist=[500, 502, 503, 504], allowed_methods=['GET', 'HEAD', 'OPTIONS'])
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers.update({'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json',
                            'Content-Type': 'application/json'})
    return session
