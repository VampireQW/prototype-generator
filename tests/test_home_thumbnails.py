"""首页封面的缓存、权限和离线渲染回归，只使用隔离项目。"""
import queue
from types import SimpleNamespace

from PIL import Image

import home_thumbnails
from test_external_api import api, prototype


def test_fingerprint_tracks_source_without_touching_project(tmp_path):
    root = prototype(tmp_path / 'sample')
    css = root / 'style.css'
    css.write_text('body { color: red }')
    first = home_thumbnails.fingerprint(root, 'index.html')
    css.write_text('body { color: orange }')
    assert home_thumbnails.fingerprint(root, 'index.html') != first
    assert not (root / '.prototype').exists()
    cache = root / '.cache'
    cache.mkdir(); (cache / 'ignored.js').write_text('ignored')
    second = home_thumbnails.fingerprint(root, 'index.html')
    (cache / 'ignored.js').write_text('changed')
    assert home_thumbnails.fingerprint(root, 'index.html') == second


def test_request_deduplicates_and_reuses_cache(tmp_path, monkeypatch):
    root = prototype(tmp_path / 'sample')
    cache = tmp_path / 'covers'; cache.mkdir()
    pending = queue.Queue(maxsize=1)
    monkeypatch.setattr(home_thumbnails, 'CACHE', cache)
    monkeypatch.setattr(home_thumbnails, '_queue', pending)
    monkeypatch.setattr(home_thumbnails, '_jobs', {})
    monkeypatch.setattr(home_thumbnails, '_started', True)
    assert home_thumbnails.request(root, 'index.html') == ('pending', None)
    assert home_thumbnails.request(root, 'index.html') == ('pending', None)
    assert pending.qsize() == 1
    second = prototype(tmp_path / 'second')
    assert home_thumbnails.request(second, 'index.html') == ('busy', None)
    target = cache / (home_thumbnails.fingerprint(root, 'index.html') + '.png')
    target.write_bytes(b'cached')
    assert home_thumbnails.request(root, 'index.html') == ('ready', target)


def test_local_cover_permissions_pending_and_cache_guard(api, tmp_path, monkeypatch):
    root = prototype(tmp_path / 'registered')
    pid = api.request('/api/external/add', {'path': str(root)})[1]['projectId']
    monkeypatch.setattr(home_thumbnails, 'request', lambda *args: ('pending', None))
    query = '/api/home/thumbnail?source=local&id=' + pid
    assert api.request(query) == (202, {'status': 'pending'})
    assert api.request(query, headers={'Origin': 'https://other.example'})[0] == 403
    assert api.request('/api/home/thumbnail?source=local&id=missing')[0] == 404
    image = tmp_path / 'cached.png'; Image.new('RGB', (1280, 640), 'orange').save(image)
    monkeypatch.setattr(home_thumbnails, 'request', lambda *args: ('ready', image))
    assert api.request(query) == (200, image.read_bytes())
    private = tmp_path / 'data' / 'home-thumbnails'; private.mkdir(parents=True)
    (private / 'test.png').write_bytes(image.read_bytes())
    for path in ['/data/home-thumbnails/test.png', '/data/%68ome-thumbnails/test.png', '/src/../data/home-thumbnails/test.png']:
        assert api.request(path)[0] == 403
        assert api.request(path, method='HEAD')[0] == 403


def test_discovered_cover_revoked_after_root_removed(api, tmp_path, monkeypatch):
    root = prototype(tmp_path / 'collection' / 'watched')
    api.request('/api/external/roots/add', {'path': str(root.parent)})
    listing = api.request('/api/external/list')[1]
    pid = listing['discovered'][0]['projectId']
    monkeypatch.setattr(home_thumbnails, 'request', lambda *args: ('pending', None))
    query = '/api/home/thumbnail?source=local&id=' + pid
    assert api.request(query)[0] == 202
    assert not (root / '.prototype').exists()
    api.request('/api/external/roots/remove', {'path': str(root.parent)})
    assert api.request(query)[0] == 404


def test_ai_cover_uses_owner_access(api, tmp_path, monkeypatch):
    projects = tmp_path / 'projects'; root = prototype(projects / 'ai-sample')
    ns = api.namespace
    ns.update(PROJECTS_DIR=str(projects), USER=None, ACCESS=True,
              db=SimpleNamespace(get_project_owner=lambda pid: 7, can_user_access_project=lambda pid, uid: ns['ACCESS']))
    ns['CustomHandler'].get_current_user = lambda self: ns['USER']
    monkeypatch.setattr(home_thumbnails, 'request', lambda *args: ('pending', None))
    query = '/api/home/thumbnail?source=ai&id=ai-sample'
    assert api.request(query)[0] == 202  # 保留现有离线个人版访问规则。
    ns['USER'] = {'id': 8}; ns['ACCESS'] = False
    assert api.request(query)[0] == 403
    ns['ACCESS'] = True
    assert api.request(query)[0] == 202


def test_capture_renders_local_content_without_network_or_metadata(tmp_path):
    root = prototype(tmp_path / 'capture')
    (root / 'index.html').write_text('''<html><body style="margin:0;background:#17212c;color:white;font:40px sans-serif">
        <h1>Local cover</h1><script>fetch('http://127.0.0.1:1/never', {method:'POST', body:'blocked'}).catch(()=>{});</script>
        </body></html>''', encoding='utf-8')
    output = tmp_path / 'cover.png'
    home_thumbnails.capture(root, 'index.html', str(output))
    with Image.open(output) as image:
        assert image.size == (1280, 640)
        assert image.getpixel((1100, 400)) == (23, 33, 44)
    assert sorted(p.name for p in root.iterdir()) == ['index.html']
