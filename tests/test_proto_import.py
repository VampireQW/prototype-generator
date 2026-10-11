"""proto_import 单元测试：草稿校验、protoId 扫描、落库幂等、confirmed 保护、revision 推进、留档与登记 ID 解析。

运行：python -m pytest tests/test_proto_import.py -v
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import proto_import  # noqa: E402
import proto_meta  # noqa: E402

INDEX_HTML = """<html lang="zh-CN" data-proto-page="home" data-proto-state="default"><head><title>首页</title>
<style>.x{color:red}</style></head><body>
<nav data-proto-id="nav"><a data-proto-id="nav-home">首页</a><a>关于</a></nav>
<div data-proto-id="card"><h3>标题   文字</h3><p>正文<br>换行</p>
<input data-proto-id="kw" placeholder="搜索关键词"><li>未闭合一<li data-proto-id="li2">未闭合二</div>
<button data-proto-id="dup">A</button><button data-proto-id="dup">B</button>
<script>document.write("<b data-proto-id='fake'>x</b>")</script>
<img data-proto-id="logo" alt="LOGO" />
</body></html>"""

DETAIL_HTML = """<html lang="zh-CN" data-proto-page="detail"><head><title>详情</title></head><body>
<button data-proto-id="btn-save">保存</button></body></html>"""


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'index.html').write_text(INDEX_HTML, encoding='utf-8')
    (tmp_path / 'pages').mkdir()
    (tmp_path / 'pages' / 'detail.html').write_text(DETAIL_HTML, encoding='utf-8')
    return tmp_path


def draft(*pages, unknowns=None):
    d = {'schemaVersion': 1, 'pages': list(pages)}
    if unknowns is not None:
        d['unknowns'] = unknowns
    return d


def write_draft(root, data, name=proto_import.DRAFT_NAME):
    md = proto_meta.meta_dir(root)
    md.mkdir(parents=True, exist_ok=True)
    path = md / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def notes_for(bundle, page_id, state_id='default'):
    return sorted((n for n in bundle['prd']['annotations'] if n['pageId'] == page_id and n['stateId'] == state_id),
                  key=lambda n: n['number'])


# ---------- HTML 扫描 ----------

def test_scan_collects_tag_text_and_counts_duplicates():
    found = proto_import.scan_proto_ids(INDEX_HTML)
    assert found['nav'][0]['tag'] == 'nav' and found['nav'][0]['text'] == '首页关于'
    assert found['card'][0]['text'] == '标题 文字正文换行未闭合一未闭合二', '空白折叠、<br> 不截断、未闭合 li 归属父级'
    assert found['kw'][0] == {'tag': 'input', 'text': '搜索关键词', 'attrs': found['kw'][0]['attrs']}, 'void 元素取 placeholder'
    assert found['li2'][0]['text'] == '未闭合二', '第二个未闭合 li 收口第一个'
    assert [r['text'] for r in found['dup']] == ['A', 'B'], '重复 protoId 计两次供上层拒绝'
    assert 'fake' not in found, 'script 内文不算元素'
    assert found['logo'][0]['text'] == 'LOGO', 'img 取 alt'


def test_scan_truncates_long_text():
    found = proto_import.scan_proto_ids('<p data-proto-id="p">' + 'x' * 500 + '</p>')
    assert len(found['p'][0]['text']) == 200


# ---------- 草稿校验 ----------

@pytest.mark.parametrize('bad, msg', [
    ({'schemaVersion': 2, 'pages': [{'file': 'index.html'}]}, 'schemaVersion'),
    ({'schemaVersion': 1, 'pages': []}, 'pages 为空'),
    ({'schemaVersion': 1, 'pages': [{'document': 'x'}]}, '缺 file 或 pageId'),
    ({'schemaVersion': 1, 'pages': [{'file': 'index.html', 'document': ['x']}]}, 'Markdown 字符串'),
    ({'schemaVersion': 1, 'pages': [{'file': 'index.html', 'annotations': {}}]}, '必须是数组'),
    ({'schemaVersion': 1, 'pages': [{'file': 'index.html', 'annotations': [{'protoId': 'a', 'body': ' '}]}]}, '都不能为空'),
    ({'schemaVersion': 1, 'pages': [{'file': 'index.html'}], 'unknowns': 'x'}, 'unknowns 必须是数组'),
])
def test_load_draft_rejects_bad_shapes(tmp_path, bad, msg):
    path = tmp_path / 'd.json'
    path.write_text(json.dumps(bad), encoding='utf-8')
    with pytest.raises(proto_import.ImportError_, match=msg):
        proto_import.load_draft(path)


def test_load_draft_rejects_invalid_json_and_missing_file(tmp_path):
    path = tmp_path / 'd.json'
    path.write_text('{oops', encoding='utf-8')
    with pytest.raises(proto_import.ImportError_, match='合法 JSON'):
        proto_import.load_draft(path)
    with pytest.raises(proto_import.ImportError_, match='读取失败'):
        proto_import.load_draft(tmp_path / 'nope.json')


# ---------- 落库 ----------

def test_import_creates_document_and_annotations_and_bumps_revision(proj):
    report = proto_import.import_draft(proj, draft(
        {'file': 'index.html', 'document': '## 一、需求描述\n首页\n## 二、研发实现\n无',
         'annotations': [{'protoId': 'nav-home', 'body': '点击回首页'}, {'protoId': 'kw', 'body': '回车搜索'}]},
        {'file': 'pages/detail.html', 'annotations': [{'protoId': 'btn-save', 'body': '保存后回列表'}]},
        unknowns=['分页每页多少条？'],
    ))
    bundle = proto_meta.load_bundle(proj)
    assert report['revisionAfter'] == report['revisionBefore'] + 1 == bundle['revision']
    assert report['changed'] and not report['dryRun']
    assert report['unknowns'] == ['分页每页多少条？']
    # 三文件 revision 一致
    md = proto_meta.meta_dir(proj)
    revs = {json.loads((md / n).read_text(encoding='utf-8'))['revision'] for n in ('project.json', 'prd.json', 'changes.json')}
    assert revs == {bundle['revision']}
    doc = next(d for d in bundle['prd']['documents'] if d['pageId'] == 'home')
    assert doc['markdown'].startswith('## 一、需求描述') and doc['confirmed'] is False
    home = notes_for(bundle, 'home')
    assert [(n['number'], n['anchor']['protoId']) for n in home] == [(1, 'nav-home'), (2, 'kw')]
    n1 = home[0]
    assert n1['anchor'] == {'protoId': 'nav-home', 'selector': '[data-proto-id="nav-home"]', 'tag': 'a', 'text': '首页'}
    assert n1['placement'] == {'kind': 'element', 'x': 0, 'y': 0, 'rx': 0, 'ry': 0.5}
    assert n1['offset'] == {'x': 20, 'y': 0} and n1['confirmed'] is False and n1['collapsed'] is False
    assert n1['body'] == '点击回首页' and n1['id'] and n1['updatedAt']
    detail = notes_for(bundle, 'detail')
    assert [(n['number'], n['anchor']['tag']) for n in detail] == [(1, 'button')], '编号按页面/状态各自从 1 起'
    # 落库结果必须通过工作台同一套校验
    proto_meta.validate_bundle(bundle)


def test_import_by_page_id_and_file_casefold(proj):
    report = proto_import.import_draft(proj, draft(
        {'pageId': 'detail', 'annotations': [{'protoId': 'btn-save', 'body': 'a'}]},
        {'file': 'INDEX.HTML', 'annotations': [{'protoId': 'logo', 'body': 'b'}]},
    ))
    assert {a['scope'] for a in report['annotations']} == {'detail/default', 'home/default'}


def test_import_rejects_missing_or_duplicate_proto_id_as_a_whole(proj):
    before = proto_meta.ensure_bundle(proj)
    proto_meta.ensure_pages_registered(proj, before)
    rev = proto_meta.load_bundle(proj)['revision']
    with pytest.raises(proto_import.ImportError_) as err:
        proto_import.import_draft(proj, draft({'file': 'index.html', 'annotations': [
            {'protoId': 'nav-home', 'body': 'ok'}, {'protoId': 'ghost', 'body': 'x'}, {'protoId': 'dup', 'body': 'y'}]}))
    text = str(err.value)
    assert 'ghost' in text and '不存在' in text
    assert 'dup' in text and '出现 2 次' in text
    after = proto_meta.load_bundle(proj)
    assert after['revision'] == rev and not after['prd']['annotations'], '整份不落库，合格的那条也不写'


def test_skip_missing_writes_valid_ones_and_reports_rest(proj):
    report = proto_import.import_draft(proj, draft({'file': 'index.html', 'annotations': [
        {'protoId': 'ghost', 'body': 'x'}, {'protoId': 'nav-home', 'body': 'ok'}]}), skip_missing=True)
    assert [a['protoId'] for a in report['annotations']] == ['nav-home']
    assert any('ghost' in s for s in report['skipped'])
    assert [n['number'] for n in notes_for(proto_meta.load_bundle(proj), 'home')] == [1], '跳过的不占编号'


def test_reimport_is_idempotent_and_appends_new_numbers(proj):
    d = draft({'file': 'index.html', 'annotations': [{'protoId': 'nav-home', 'body': 'a'}]})
    proto_import.import_draft(proj, d)
    rev = proto_meta.load_bundle(proj)['revision']
    again = proto_import.import_draft(proj, d)
    assert not again['changed'] and again['revisionAfter'] == rev, '重复导入不写盘、不推进 revision'
    assert any('重复导入' in s for s in again['skipped'])
    more = proto_import.import_draft(proj, draft({'file': 'index.html', 'annotations': [
        {'protoId': 'nav-home', 'body': 'a'}, {'protoId': 'kw', 'body': 'b'}]}))
    assert [(a['protoId'], a['number']) for a in more['annotations']] == [('kw', 2)], '新条目接着已有最大编号'


def test_number_continues_after_workbench_notes(proj):
    bundle = proto_meta.ensure_bundle(proj)
    proto_meta.ensure_pages_registered(proj, bundle)
    bundle['prd']['annotations'].append({
        'id': 'n-7', 'pageId': 'home', 'stateId': 'default', 'number': 7, 'body': '工作台手点的',
        'anchor': {'protoId': 'card', 'selector': '[data-proto-id="card"]'},
        'placement': {'kind': 'element', 'x': 3, 'y': 4}, 'offset': {'x': 20, 'y': 0},
        'collapsed': False, 'confirmed': True, 'updatedAt': proto_meta.now_iso()})
    proto_meta.save_bundle(proj, bundle)
    report = proto_import.import_draft(proj, draft({'file': 'index.html', 'annotations': [
        {'protoId': 'card', 'body': '重复绑定'}, {'protoId': 'kw', 'body': '新'}]}))
    assert [(a['protoId'], a['number']) for a in report['annotations']] == [('kw', 8)]
    assert any('card' in s for s in report['skipped'])
    saved = notes_for(proto_meta.load_bundle(proj), 'home')
    assert saved[0]['confirmed'] is True and saved[0]['body'] == '工作台手点的', '已有标注原样保留'


def test_document_protection_and_replace_flag(proj):
    proto_import.import_draft(proj, draft({'file': 'index.html', 'document': '第一版'}))
    r2 = proto_import.import_draft(proj, draft({'file': 'index.html', 'document': '第二版'}))
    assert not r2['changed'] and any('--replace-doc' in s for s in r2['skipped'])
    r3 = proto_import.import_draft(proj, draft({'file': 'index.html', 'document': '第二版'}), replace_doc=True)
    assert r3['documents'] == [{'scope': 'home/default', 'action': 'replaced'}]
    bundle = proto_meta.load_bundle(proj)
    doc = next(d for d in bundle['prd']['documents'] if d['pageId'] == 'home')
    assert doc['markdown'] == '第二版'
    doc['confirmed'] = True
    proto_meta.save_bundle(proj, bundle)
    r4 = proto_import.import_draft(proj, draft({'file': 'index.html', 'document': '第三版'}), replace_doc=True)
    assert not r4['changed'] and any('已确认' in s for s in r4['skipped'])
    assert next(d for d in proto_meta.load_bundle(proj)['prd']['documents'] if d['pageId'] == 'home')['markdown'] == '第二版'


def test_empty_document_fills_existing_blank_record(proj):
    """工作台点开页面会先建一条空 markdown 文档；导入应填进这条而不是再新建一条。"""
    bundle = proto_meta.ensure_bundle(proj)
    proto_meta.ensure_pages_registered(proj, bundle)
    bundle['prd']['documents'].append({'id': 'd-blank', 'pageId': 'home', 'stateId': 'default', 'markdown': '',
                                       'confirmed': False, 'updatedAt': proto_meta.now_iso()})
    proto_meta.save_bundle(proj, bundle)
    report = proto_import.import_draft(proj, draft({'file': 'index.html', 'document': '填进来'}))
    assert report['documents'] == [{'scope': 'home/default', 'action': 'replaced'}]
    docs = [d for d in proto_meta.load_bundle(proj)['prd']['documents'] if d['pageId'] == 'home']
    assert len(docs) == 1 and docs[0]['id'] == 'd-blank' and docs[0]['markdown'] == '填进来'


def test_hidden_element_is_imported_with_warning(proj):
    (proj / 'index.html').write_text(INDEX_HTML.replace(
        '<img data-proto-id="logo"', '<div data-proto-id="empty" hidden>空</div><img data-proto-id="logo"'), encoding='utf-8')
    report = proto_import.import_draft(proj, draft({'file': 'index.html', 'annotations': [
        {'protoId': 'empty', 'body': 'x'}, {'protoId': 'kw', 'body': 'y'}]}))
    assert [a['protoId'] for a in report['annotations']] == ['empty', 'kw'], 'hidden 元素照常落库'
    assert len(report['warnings']) == 1 and 'empty' in report['warnings'][0] and 'hidden' in report['warnings'][0]
    assert '提醒' in proto_import.format_report(report)


def test_dry_run_does_not_write(proj):
    bundle = proto_meta.ensure_bundle(proj)
    proto_meta.ensure_pages_registered(proj, bundle)
    rev = proto_meta.load_bundle(proj)['revision']
    report = proto_import.import_draft(proj, draft({'file': 'index.html', 'document': 'x',
                                                    'annotations': [{'protoId': 'kw', 'body': 'y'}]}), dry_run=True)
    assert report['changed'] and report['dryRun'] and report['revisionAfter'] == rev
    after = proto_meta.load_bundle(proj)
    assert after['revision'] == rev and not after['prd']['annotations'] and not after['prd']['documents']


def test_unknown_page_state_or_file_is_reported(proj):
    with pytest.raises(proto_import.ImportError_, match='未登记为页面'):
        proto_import.import_draft(proj, draft({'file': 'pages/nope.html', 'document': 'x'}))
    with pytest.raises(proto_import.ImportError_, match="pageId 'zzz' 不存在"):
        proto_import.import_draft(proj, draft({'pageId': 'zzz', 'document': 'x'}))
    with pytest.raises(proto_import.ImportError_, match="没有状态 'empty'"):
        proto_import.import_draft(proj, draft({'file': 'index.html', 'stateId': 'empty', 'document': 'x'}))


# ---------- 留档 / 登记 ID / CLI ----------

def test_archive_draft_moves_into_imported_with_revision(proj):
    path = write_draft(proj, draft({'file': 'index.html', 'document': 'x'}))
    target = proto_import.archive_draft(proj, path, 5)
    assert not path.exists() and target.exists()
    assert target.parent == proto_meta.meta_dir(proj) / 'imported'
    assert target.name.startswith('prd.draft.r5.') and target.suffix == '.json'


def test_resolve_root_accepts_path_and_registry_id(proj, tmp_path, monkeypatch):
    assert proto_import.resolve_root(str(proj)) == proj.resolve()
    with pytest.raises(proto_import.ImportError_, match='不存在'):
        proto_import.resolve_root(str(tmp_path / 'missing'))
    fake_home = tmp_path / 'tool'
    (fake_home / 'data').mkdir(parents=True)
    (fake_home / 'data' / 'external.json').write_text(json.dumps(
        {'projects': {'p-0123456789abcdef': {'root': str(proj), 'name': 'x'}}, 'roots': []}), encoding='utf-8')
    monkeypatch.setattr(proto_import, '__file__', str(fake_home / 'proto_import.py'))
    assert proto_import.resolve_root('p-0123456789abcdef') == proj.resolve()
    with pytest.raises(proto_import.ImportError_, match='登记表里没有'):
        proto_import.resolve_root('p-ffffffffffffffff')


def test_cli_default_draft_path_imports_and_archives(proj, capsys):
    write_draft(proj, draft({'file': 'index.html', 'document': '## 一、需求描述\nx',
                             'annotations': [{'protoId': 'kw', 'body': '搜索'}]}, ))
    assert proto_import.main([str(proj)]) == 0
    out = capsys.readouterr().out
    assert '文档  home/default  新建' in out and '#1  kw  <input> 搜索关键词' in out
    assert '草稿已留档' in out and '请刷新页面' in out
    assert not (proto_meta.meta_dir(proj) / proto_import.DRAFT_NAME).exists()
    assert list((proto_meta.meta_dir(proj) / 'imported').glob('prd.draft.r*.json'))


def test_cli_dry_run_keeps_draft_and_reports_failure_to_stderr(proj, capsys):
    path = write_draft(proj, draft({'file': 'index.html', 'annotations': [{'protoId': 'ghost', 'body': 'x'}]}))
    assert proto_import.main([str(proj), '--dry-run']) == 1
    err = capsys.readouterr().err
    assert 'ghost' in err and '草稿未落库' in err
    assert path.exists()
    (proj / '.prototype' / 'prd.draft.json').write_text(json.dumps(draft({'file': 'index.html', 'document': 'x'})), encoding='utf-8')
    assert proto_import.main([str(proj), '--dry-run']) == 0
    assert 'dry-run，未写入' in capsys.readouterr().out and path.exists(), 'dry-run 不留档不移动'
