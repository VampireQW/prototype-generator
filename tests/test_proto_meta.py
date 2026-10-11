# -*- coding: utf-8 -*-
"""proto_meta 单元测试：round-trip、校验拒绝、资产白名单、页面补登与 id 对齐。

运行：python -m pytest tests/test_proto_meta.py -v

对账说明（四期 F1，2026-09-26）：已移植「原型生成全流程」tests/connector.py 中仍有独特价值的
schema 互认/连接器行为用例（同名页唯一 ID、中文页登记、部分写回滚、异常元数据不重建）。
不移植项及原因：
- tests/browser.py（Playwright E2E）：面向已删除的扩展工作台 UI（任务面板/多选），工作台已由
  viewer 取代并由 test_annotation_ui.py + 浏览器走查覆盖，随归档退役。
- tests/store.cjs：测扩展端 project-store.js 三方合并/离线草稿，原型生成器无此模块（冲突策略为
  409 人工处理；串行保存与草稿恢复行为已由 test_annotation_ui.py 覆盖）。
- connector.py 连接器专属用例：/api/health previewOrigin、/api/export/state 指纹交付、
  /api/share/build ZIP、/api/project/snapshot、扩展 core.js canonical——全流程交付管线与
  双服务架构在原型生成器中无对应功能。其余用例（CAS 并发、来源守卫、白名单、监视根、confirmed
  保护、落点/编号校验）两侧已有等价覆盖，不重复移植。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import proto_meta


@pytest.fixture
def proj(tmp_path):
    """最小原型项目：index.html + pages/detail.html + 一份 CSS"""
    (tmp_path / 'index.html').write_text(
        '<html><head><title>首页</title></head><body>hi</body></html>', encoding='utf-8')
    (tmp_path / 'pages').mkdir()
    (tmp_path / 'pages' / 'detail.html').write_text(
        '<html><head><title>详情</title></head><body>d</body></html>', encoding='utf-8')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app.css').write_text('body{}', encoding='utf-8')
    return tmp_path


def fresh_bundle(root):
    pages = proto_meta.discover_pages(root)
    assert pages, 'fixture 应至少发现一页'
    return proto_meta.default_bundle(root, pages[0]['url'], pages[0]['title'])


def make_note(page_id, number, **over):
    note = {
        'id': f'n-{number}', 'pageId': page_id, 'stateId': 'default', 'number': number,
        'body': 'x', 'anchor': {'kind': 'protoId', 'protoId': 'btn'},
        'placement': {'kind': 'element', 'x': 0.5, 'y': 0.5},
        'offset': {'x': 20, 'y': 0}, 'collapsed': False, 'confirmed': False,
        'updatedAt': '2026-09-24T00:00:00Z',
    }
    note.update(over)
    return note


# ---------- 持久化 round-trip ----------

class TestPersistence:
    def test_round_trip(self, proj):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        loaded = proto_meta.load_bundle(proj)
        assert loaded['project'] == bundle['project']
        assert loaded['prd'] == bundle['prd']
        assert loaded['revision'] == bundle['revision']
        # 三文件 revision/projectId 一致
        md = proto_meta.meta_dir(proj)
        docs = {n: json.loads((md / n).read_text(encoding='utf-8'))
                for n in ('project.json', 'prd.json', 'changes.json')}
        assert len({d['revision'] for d in docs.values()}) == 1
        assert len({d['projectId'] for d in docs.values()}) == 1

    def test_load_rejects_pending_write(self, proj):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        (proto_meta.meta_dir(proj) / '.pending-write.json').write_text('{}', encoding='utf-8')
        with pytest.raises(ValueError, match='中断'):
            proto_meta.load_bundle(proj)

    def test_load_rejects_revision_mismatch(self, proj):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        md = proto_meta.meta_dir(proj)
        p = json.loads((md / 'project.json').read_text(encoding='utf-8'))
        p['revision'] += 1
        (md / 'project.json').write_text(json.dumps(p, ensure_ascii=False), encoding='utf-8')
        with pytest.raises(ValueError, match='版本不一致'):
            proto_meta.load_bundle(proj)


# ---------- validate_bundle 校验 ----------

class TestValidate:
    def test_rejects_bad_schema_version(self, proj):
        bundle = fresh_bundle(proj)
        bundle['schemaVersion'] = 1
        with pytest.raises(ValueError, match='协议版本'):
            proto_meta.validate_bundle(bundle)

    def test_rejects_dup_number(self, proj):
        bundle = fresh_bundle(proj)
        page_id = bundle['project']['pages'][0]['id']
        bundle['prd']['annotations'] = [make_note(page_id, 1), make_note(page_id, 1, id='n-dup')]
        with pytest.raises(ValueError, match='编号重复'):
            proto_meta.validate_bundle(bundle)

    def test_rejects_ghost_scope(self, proj):
        bundle = fresh_bundle(proj)
        bundle['prd']['annotations'] = [make_note('ghost-page', 1)]
        with pytest.raises(ValueError, match='未登记状态'):
            proto_meta.validate_bundle(bundle)

    def test_rejects_bad_placement_kind(self, proj):
        bundle = fresh_bundle(proj)
        page_id = bundle['project']['pages'][0]['id']
        note = make_note(page_id, 1)
        note['placement'] = {'kind': 'weird', 'x': 1, 'y': 2}
        bundle['prd']['annotations'] = [note]
        with pytest.raises(ValueError, match='落点类型'):
            proto_meta.validate_bundle(bundle)

    def test_rejects_element_placement_without_anchor(self, proj):
        bundle = fresh_bundle(proj)
        page_id = bundle['project']['pages'][0]['id']
        note = make_note(page_id, 1)
        del note['anchor']
        bundle['prd']['annotations'] = [note]
        with pytest.raises(ValueError, match='缺少锚点'):
            proto_meta.validate_bundle(bundle)

    def test_accepts_document_placement(self, proj):
        bundle = fresh_bundle(proj)
        page_id = bundle['project']['pages'][0]['id']
        note = make_note(page_id, 1)
        del note['anchor']
        note['placement'] = {'kind': 'document', 'x': 100, 'y': 200}
        bundle['prd']['annotations'] = [note]
        assert proto_meta.validate_bundle(bundle) is bundle


# ---------- safe_asset 白名单 ----------

class TestSafeAsset:
    def test_allows_normal_assets(self, proj):
        assert proto_meta.safe_asset(proj, 'index.html').name == 'index.html'
        assert proto_meta.safe_asset(proj, 'pages/detail.html').name == 'detail.html'
        assert proto_meta.safe_asset(proj, 'assets\\app.css').name == 'app.css'

    def test_rejects_traversal(self, proj):
        with pytest.raises(ValueError):
            proto_meta.safe_asset(proj, '../outside.html')
        with pytest.raises(ValueError):
            proto_meta.safe_asset(proj, 'pages/../../outside.html')

    def test_rejects_protected_dirs(self, proj):
        for rel in ('.prototype/prd.json', 'node_modules/pkg/index.js', 'exports/x.html', '.git/config'):
            with pytest.raises(ValueError):
                proto_meta.safe_asset(proj, rel)

    def test_rejects_bad_suffix(self, proj):
        (proj / 'evil.exe').write_text('x')
        with pytest.raises(ValueError):
            proto_meta.safe_asset(proj, 'evil.exe')

    def test_missing_file(self, proj):
        with pytest.raises(FileNotFoundError):
            proto_meta.safe_asset(proj, 'ghost.html')


# ---------- 派生与补登 ----------

class TestDerive:
    def test_slugify_keeps_chinese(self):
        assert proto_meta.slugify('作业详情') == '作业详情'
        assert proto_meta.slugify('Hello World!') == 'hello-world'
        assert proto_meta.slugify('  ') == 'prototype'
        assert proto_meta.slugify('a/b\\c:d') == 'a-b-c-d'

    def test_page_record_home(self, proj):
        pages = {p['file']: p for p in proto_meta.discover_pages(proj)}
        idx = proto_meta.page_record(proj, pages['index.html']['url'], '首页')
        det = proto_meta.page_record(proj, pages['pages/detail.html']['url'], '详情')
        assert idx['id'] == 'home'
        assert det['id'] == 'detail'
        assert det['file'] == 'pages/detail.html'

    def test_project_id_stable(self, proj):
        assert proto_meta.project_id_for(proj).startswith('p-')

    def test_ensure_pages_registered(self, proj):
        bundle = fresh_bundle(proj)  # 只登记首页
        assert len(bundle['project']['pages']) == 1
        proto_meta.save_bundle(proj, bundle)
        rev0 = bundle['revision']

        changed = proto_meta.ensure_pages_registered(proj, bundle)
        assert changed is True
        assert bundle['revision'] == rev0 + 1
        ids = {p['id'] for p in bundle['project']['pages']}
        assert ids == {'home', 'detail'}
        # 幂等：第二次无变更
        assert proto_meta.ensure_pages_registered(proj, bundle) is False
        # 落盘可重读
        assert len(proto_meta.load_bundle(proj)['project']['pages']) == 2

    def test_ensure_project_id(self, proj):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        real_pid = proto_meta.project_id_for(proj)
        rev0 = bundle['revision']

        assert proto_meta.ensure_project_id(proj, bundle, real_pid) is False  # 一致不动

        bundle['project']['id'] = 'p-legacy0000000000'
        proto_meta.save_bundle(proj, bundle)  # save_bundle 本身不升 revision，递增是调用方责任
        assert proto_meta.ensure_project_id(proj, bundle, real_pid) is True
        assert bundle['revision'] == rev0 + 1
        md = proto_meta.meta_dir(proj)
        for name in ('project.json', 'prd.json', 'changes.json'):
            doc = json.loads((md / name).read_text(encoding='utf-8'))
            assert doc['projectId'] == real_pid, f'{name} 未同步'


def test_directory_created_at_uses_birth_time_and_preserves_missing_path_fallback(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(Path, 'stat', lambda path: SimpleNamespace(st_birthtime=1000, st_ctime=2000, st_mtime=3000))
    assert proto_meta.directory_created_at(tmp_path) == '1970-01-01T00:16:40.000000+00:00'
    def missing(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(Path, 'stat', missing)
    assert proto_meta.directory_created_at(tmp_path, '2026-10-03T08:00:00+08:00') == '2026-10-03T00:00:00.000000+00:00'
    assert proto_meta.directory_created_at(tmp_path, 'invalid') == ''


def test_scan_roots_is_shallow_deduplicated_and_readonly(tmp_path):
    for name in ('index.html', 'child/index.html', 'only-pages/pages/detail.html',
                 'container/deep/index.html', '.hidden/index.html', 'node_modules/index.html',
                 'exports/index.html', 'dist/index.html', '原型生成器/index.html'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('<title>样例</title>', encoding='utf-8')
    before = sorted(str(p) for p in tmp_path.rglob('*'))
    found, errors = proto_meta.scan_roots([str(tmp_path), str(tmp_path / 'child')], {})
    assert not errors
    assert {Path(p['root']).name for p in found} == {tmp_path.name, 'child', 'only-pages'}
    assert len(found) == 3
    assert sorted(str(p) for p in tmp_path.rglob('*')) == before
    assert not list(tmp_path.rglob('.prototype'))
    registered = {proto_meta.project_id_for(tmp_path / 'child'): {}}
    found, _ = proto_meta.scan_roots([str(tmp_path)], registered)
    assert 'child' not in {Path(p['root']).name for p in found}
    (tmp_path / 'new').mkdir()
    (tmp_path / 'new' / 'index.html').write_text('new')
    found, _ = proto_meta.scan_roots([str(tmp_path)], registered)
    assert 'new' in {Path(p['root']).name for p in found}


@pytest.mark.parametrize('name', ['dist', 'node_modules', '.hidden', '原型生成器'])
def test_scan_rejects_protected_root_including_its_children(tmp_path, name):
    base = tmp_path / name
    child = base / 'project'
    child.mkdir(parents=True)
    (child / 'index.html').write_text('禁止扫描', encoding='utf-8')
    found, errors = proto_meta.scan_roots([str(base)], {})
    assert not found and errors
    assert not (child / '.prototype').exists()


def test_scan_reports_invalid_and_unreadable_roots(tmp_path, monkeypatch):
    found, errors = proto_meta.scan_roots([str(tmp_path / 'gone')], {})
    assert not found and errors
    original = Path.iterdir
    def denied(path):
        if path == tmp_path:
            raise PermissionError('无权访问')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', denied)
    assert proto_meta.scan_roots([str(tmp_path)], {})[1]


def test_scan_skips_directory_links_without_following(tmp_path, monkeypatch):
    linked = tmp_path / 'linked'
    linked.mkdir()
    (linked / 'index.html').write_text('ignored')
    monkeypatch.setattr(proto_meta, 'is_directory_link', lambda p: p == linked)
    assert proto_meta.scan_roots([str(tmp_path)], {}) == ([], [])
    assert proto_meta.scan_roots([str(linked)], {})[1]


def test_discover_pages_skips_nested_protected_and_links(proj, monkeypatch):
    hidden = proj / 'pages' / '.cache'
    hidden.mkdir()
    (hidden / 'secret.html').write_text('ignored')
    linked = proj / 'pages' / 'linked'
    linked.mkdir()
    (linked / 'secret.html').write_text('ignored')
    monkeypatch.setattr(proto_meta, 'is_directory_link', lambda p: p == linked)
    assert len(proto_meta.discover_pages(proj)) == 2


# ---------- 移植自全流程 connector.py：schema 互认与连接器行为 ----------

class TestConnectorParity:
    def test_duplicate_stem_gets_unique_id_and_chinese_page(self, proj):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        (proj / 'pages' / 'index.html').write_text('<title>重名页</title>', encoding='utf-8')
        proto_meta.ensure_pages_registered(proj, bundle)
        by_id = {p['id']: p['file'] for p in bundle['project']['pages']}
        assert by_id['home'] == 'index.html'
        assert by_id['home-2'] == 'pages/index.html', '同名不同文件应分配唯一 ID'
        (proj / 'pages' / '创建作业.html').write_text('<title>创建作业</title>', encoding='utf-8')
        proto_meta.ensure_pages_registered(proj, bundle)
        by_id = {p['id']: p['file'] for p in bundle['project']['pages']}
        assert by_id['创建作业'] == 'pages/创建作业.html', '中文页面登记保留中文 ID'
        assert len(proto_meta.load_bundle(proj)['project']['pages']) == 4

    def test_partial_write_failure_rolls_back(self, proj, monkeypatch):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        md = proto_meta.meta_dir(proj)
        names = ('project.json', 'prd.json', 'changes.json')
        before = {n: (md / n).read_bytes() for n in names}
        original = proto_meta.write_json_atomic
        written = []
        def fail_second(path, data):
            if path.name != '.pending-write.json':
                written.append(path.name)
                if len(written) == 2:
                    raise OSError('模拟第二文件写入失败')
            original(path, data)
        monkeypatch.setattr(proto_meta, 'write_json_atomic', fail_second)
        bundle['revision'] += 1
        with pytest.raises(OSError, match='模拟'):
            proto_meta.save_bundle(proj, bundle)
        assert {n: (md / n).read_bytes() for n in names} == before, '部分写失败应回滚三文件'
        assert not (md / '.pending-write.json').exists(), '完整回滚后恢复标记应清除'

    @pytest.mark.parametrize('case', ['broken-json', 'partial', 'duplicate'])
    def test_broken_metadata_never_rebuilt(self, proj, case):
        bundle = fresh_bundle(proj)
        proto_meta.save_bundle(proj, bundle)
        md = proto_meta.meta_dir(proj)
        names = ('project.json', 'prd.json', 'changes.json')
        if case == 'broken-json':
            (md / 'prd.json').write_text('{', encoding='utf-8')
            match = '读取失败'
        elif case == 'partial':
            (md / 'prd.json').unlink()
            match = '读取失败'
        else:
            doc = json.loads((md / 'project.json').read_text(encoding='utf-8'))
            doc['pages'].append(dict(doc['pages'][0]))
            (md / 'project.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
            match = '页面 ID 为空或重复'
        before = {n: (md / n).read_bytes() for n in names if (md / n).exists()}
        with pytest.raises(ValueError, match=match):
            proto_meta.ensure_bundle(proj)
        after = {n: (md / n).read_bytes() for n in names if (md / n).exists()}
        assert after == before, '异常元数据不得被重建或覆盖'
        if case == 'partial':
            assert not (md / 'prd.json').exists(), '缺失文件不得被悄悄补建'


def test_picker_cancel_success_busy_failure_and_timeout(monkeypatch):
    from types import SimpleNamespace
    import subprocess
    outputs = iter(['', 'D:/原型'])
    def run(args, **kwargs):
        assert args[-1] == '--pick-folder' and kwargs['timeout'] == 180
        return SimpleNamespace(returncode=0, stdout=json.dumps({'path': next(outputs)}))
    monkeypatch.setattr(proto_meta.subprocess, 'run', run)
    assert proto_meta.pick_folder() == ''
    assert proto_meta.pick_folder() == 'D:/原型'
    proto_meta.PICKER_LOCK.acquire()
    try:
        with pytest.raises(BlockingIOError):
            proto_meta.pick_folder()
    finally:
        proto_meta.PICKER_LOCK.release()
    monkeypatch.setattr(proto_meta.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match='粘贴'):
        proto_meta.pick_folder()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('picker', 180)
    monkeypatch.setattr(proto_meta.subprocess, 'run', timeout)
    with pytest.raises(RuntimeError, match='超时'):
        proto_meta.pick_folder()
    assert proto_meta.PICKER_LOCK.acquire(blocking=False)
    proto_meta.PICKER_LOCK.release()
