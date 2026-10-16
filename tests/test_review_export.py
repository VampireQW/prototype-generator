"""评审壳导出构建（review_export.py）的纯函数回归。"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_export


def make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / 'index.html').write_text(
        '<html lang="zh-CN" data-proto-page="home" data-proto-state="default"><title>首页</title>', encoding='utf-8')
    (root / 'pages').mkdir()
    (root / 'pages' / '作业详情.html').write_text('<title>作业详情</title>', encoding='utf-8')
    (root / 'assets').mkdir()
    (root / 'assets' / 'common.js').write_text('window.PrototypeBridge={enter(){}}', encoding='utf-8')
    return root


def make_bundle() -> dict:
    return {
        'schemaVersion': 2,
        'revision': 7,
        'project': {
            'id': 'p1',
            'name': '测试项目</script><b>',
            'pages': [
                {'id': 'home', 'title': '首页', 'file': 'index.html', 'url': 'file:///',
                 'states': [{'id': 'default', 'title': '默认页面', 'kind': 'default'}]},
                {'id': '作业详情', 'title': '作业详情', 'file': 'pages/作业详情.html', 'url': 'file:///',
                 'states': [{'id': 'default', 'title': '默认页面', 'kind': 'default'},
                            {'id': 'empty', 'title': '空态', 'kind': 'dynamic'}]},
            ],
        },
        'prd': {
            'documents': [{'id': 'd1', 'pageId': 'home', 'stateId': 'default',
                           'markdown': '## 一、需求描述\n正文', 'confirmed': True, 'updatedAt': '2026-01-01T00:00:00Z'}],
            'annotations': [{'id': 'n1', 'pageId': 'home', 'stateId': 'default', 'number': 1,
                             'body': '按钮</button>逻辑不对，参考</script>', 'anchor': {'protoId': 'btn'},
                             'placement': {'kind': 'element', 'x': 1, 'y': 2},
                             'confirmed': False, 'updatedAt': '2026-01-01T00:00:00Z'}],
        },
        'changes': {'items': [{'id': 'task-1', 'status': 'pending'}]},
    }


def build(tmp_path: Path):
    root = make_project(tmp_path / 'proj')
    out = tmp_path / 'out'
    out.mkdir()
    result = review_export.build_review_export(root, make_bundle(), out, published_at='2026-02-03T04:05:06+00:00')
    return root, out, result


def payload_of(out: Path) -> tuple[str, dict]:
    html_text = (out / 'index.html').read_text(encoding='utf-8')
    match = re.search(r'<script type="application/json" id="review-data">(.*?)</script>', html_text, re.S)
    assert match, '评审壳缺少嵌入数据块'
    return match.group(1), json.loads(match.group(1))


def test_copy_completeness_and_exclusions(tmp_path):
    root, out, _ = build(tmp_path)
    (root / '.prototype').mkdir()
    (root / '.prototype' / 'prd.json').write_text('{}', encoding='utf-8')
    (root / '.git').mkdir()
    (root / '.git' / 'config').write_text('x', encoding='utf-8')
    (root / '.env').write_text('SECRET=1', encoding='utf-8')
    for name in ('exports', 'dist', 'node_modules', '__pycache__'):
        (root / name).mkdir(exist_ok=True)
        (root / name / 'junk.txt').write_text('x', encoding='utf-8')
    out2 = tmp_path / 'out2'
    out2.mkdir()
    result = review_export.build_review_export(root, make_bundle(), out2)
    files = set(result['files'])
    assert {'index.html', 'proto/index.html', 'proto/pages/作业详情.html', 'proto/assets/common.js'} <= files
    copied_parts = [part for p in out2.rglob('*') for part in p.parts]
    for banned in ('.prototype', '.git', '.env', 'exports', 'dist', 'node_modules', '__pycache__'):
        assert banned not in copied_parts, f'{banned} 泄漏进评审产物'


def test_shell_contains_embedded_data(tmp_path):
    _, out, result = build(tmp_path)
    assert (out / 'index.html').is_file()
    raw, data = payload_of(out)
    assert data['name'] == '测试项目</script><b>'
    assert data['projectId'] == 'p1' and data['revision'] == 7
    assert data['publishedAt'] == '2026-02-03T04:05:06+00:00'
    assert len(data['pages']) == 2 and len(data['documents']) == 1 and len(data['annotations']) == 1
    assert 'changes' not in data and 'task-1' not in raw, '任务列表不应进入评审数据'
    assert result['publishedAt'] == '2026-02-03T04:05:06+00:00'


def test_script_close_tag_escaped(tmp_path):
    _, out, _ = build(tmp_path)
    raw, data = payload_of(out)
    assert '</' not in raw, '嵌入数据中的 </ 必须转义，防止 </script> 截断'
    assert data['annotations'][0]['body'] == '按钮</button>逻辑不对，参考</script>'
    html_text = (out / 'index.html').read_text(encoding='utf-8')
    assert '测试项目</script>' not in html_text
    assert '测试项目&lt;/script&gt;&lt;b&gt;' in html_text, '标题占位符必须 HTML 转义'


def test_chinese_filenames_preserved(tmp_path):
    _, out, result = build(tmp_path)
    assert 'proto/pages/作业详情.html' in result['files']
    assert (out / 'proto' / 'pages' / '作业详情.html').is_file()


def test_scripts_inlined_into_each_proto_page(tmp_path):
    """六段脚本按顺序内嵌进原型 HTML，兼容 file://。"""
    _, out, result = build(tmp_path)
    html_text = (out / 'index.html').read_text(encoding='utf-8')
    assert '__SRC_' not in html_text and '__REVIEW_DATA__' not in html_text and '__PROJECT_TITLE__' not in html_text
    src_dir = Path(review_export.__file__).resolve().parent / 'src'
    order = ('proto-hotspots.js', 'proto-appearance.js', 'proto-anchors.js', 'proto-order.js', 'review-bridge.js', 'review-pins.js')
    for name in order:
        assert json.dumps(src_dir.joinpath(name).read_text(encoding='utf-8')) not in html_text, f'{name} 不应再进壳'
    assert sorted(result['injected']) == ['proto/index.html', 'proto/pages/作业详情.html']
    for rel in ('index.html', 'pages/作业详情.html'):
        page = (out / 'proto' / rel).read_text(encoding='utf-8')
        assert page.count(review_export.BUNDLE_MARK) == 1
        positions = [page.find(src_dir.joinpath(name).read_text(encoding='utf-8')) for name in order]
        assert all(p >= 0 for p in positions), f'{rel} 缺脚本'
        assert positions == sorted(positions), '加载顺序必须 hotspots → 业务脚本 → appearance → anchors → order → bridge → pins'
        for key in ('appearance', 'anchors', 'hotspots', 'order', 'bridge', 'pins'):
            assert re.search(r'<script\b[^>]*data-proto-review="' + key + r'"[^>]*>', page)
    # 非 HTML 文件不动
    assert (out / 'proto' / 'assets' / 'common.js').read_text(encoding='utf-8') == 'window.PrototypeBridge={enter(){}}'


def test_inject_bundle_position_and_idempotent():
    """插入点：</body> 前（大小写不敏感）→ </html> 前 → 末尾追加；已含标记的不重复注入。"""
    bundle = review_export.BUNDLE_MARK + '<script>1</script>\n'
    inject = review_export.inject_bundle
    assert inject('<html><BODY>x</BODY></html>', bundle) == '<html><BODY>x' + bundle + '</BODY></html>'
    assert inject('<html>x</html>', bundle) == '<html>x' + bundle + '</html>'
    assert inject('<title>t</title>', bundle) == '<title>t</title>\n' + bundle
    once = inject('<body></body>', bundle)
    assert inject(once, bundle) == once
    # 保留非 UTF-8 字节：surrogateescape 往返不丢字节
    raw = b'<html><body>\xff\xfe</body></html>'
    text = raw.decode('utf-8', errors='surrogateescape')
    assert inject(text, bundle).encode('utf-8', errors='surrogateescape').startswith(b'<html><body>\xff\xfe')


def test_review_data_keeps_hint_scope_but_excludes_deletion_history():
    bundle = make_bundle()
    bundle['project']['pages'][0]['states'][0]['interactionHints'] = {'mode': 'targets', 'protoIds': ['new-filter']}
    bundle['prd']['deletedAnnotations'] = [{'pageId': 'home', 'stateId': 'default', 'protoId': 'old-filter'}]
    data = review_export.review_data(bundle, '2026-10-15')
    assert data['pages'][0]['states'][0]['interactionHints'] == {'mode': 'targets', 'protoIds': ['new-filter']}
    assert 'deletedAnnotations' not in data and 'old-filter' not in json.dumps(data)


def test_hotspot_bootstrap_before_business_scripts():
    original = '<!doctype html><html><head><meta charset="utf-8"><title>订单</title><script>window.business=1</script></head><body>内容</body></html>'
    result = review_export.inject_hotspot_bootstrap(original)
    assert result.startswith('<!doctype html>')
    assert result.index('<meta charset') < result.index('data-proto-hotspot-bootstrap') < result.index('window.business=1')
    assert review_export.inject_hotspot_bootstrap(result) == result
    assert review_export.inject_hotspot_bootstrap('literal-percent') == 'literal-percent'
    no_head = '<!doctype html><html><body><button>静态</button></body></html>'
    assert review_export.inject_hotspot_bootstrap(no_head).startswith('<!doctype html>')


def test_hotspot_inline_refuses_script_close_tag(monkeypatch, tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/proto-hotspots.js').write_text('"</SCRIPT>"', encoding='utf-8')
    monkeypatch.setattr(review_export, 'BASE_DIR', tmp_path)
    with pytest.raises(ValueError, match='proto-hotspots.js'):
        review_export.inject_hotspot_bootstrap('<html></html>', inline=True)


def test_bundle_scripts_refuse_script_close_tag(monkeypatch, tmp_path):
    """内嵌源码若含 </script 会截断宿主页，必须拒绝。"""
    (tmp_path / 'src').mkdir()
    for _, name in review_export.PIN_SCRIPTS:
        (tmp_path / 'src' / name).write_text('ok', encoding='utf-8')
    (tmp_path / 'src' / 'review-pins.js').write_text('x = "</SCRIPT>"', encoding='utf-8')
    monkeypatch.setattr(review_export, 'BASE_DIR', tmp_path)
    with pytest.raises(ValueError, match='review-pins.js'):
        review_export.load_bundle_scripts()


def test_missing_root_raises(tmp_path):
    with pytest.raises(ValueError, match='项目目录不存在'):
        review_export.build_review_export(tmp_path / 'nope', make_bundle(), tmp_path / 'out')


def test_render_shell_missing_placeholder():
    with pytest.raises(ValueError, match='__REVIEW_DATA__'):
        review_export.render_shell('<html>__PROJECT_TITLE__</html>', {})
