"""Click-hint updates preserve unrelated PRD and reject container-sized targets."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proto_import
import proto_meta


HTML = '''<!doctype html><html><body>
<button data-proto-id="old" onclick="oldAction()">原操作</button>
<div data-proto-id="toolbar" onclick="delegate(event)">
  <button data-proto-id="new" data-proto-hotspot="true">本次操作</button>
  <button data-proto-id="unrelated">无关操作</button>
</div>
<button data-proto-id="dynamic">动态绑定</button>
<div data-proto-hotspot="false"><button data-proto-id="blocked">不提示</button></div>
</body></html>'''


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'index.html').write_text(HTML, encoding='utf-8')
    bundle = proto_meta.ensure_bundle(tmp_path)
    proto_meta.ensure_pages_registered(tmp_path, bundle)
    bundle['project']['pages'][0]['states'][0]['interactionHints'] = {'mode': 'targets', 'protoIds': ['old']}
    proto_meta.save_bundle(tmp_path, bundle)
    return tmp_path


def draft(root, **hint_fields):
    return {'schemaVersion': 3, 'baseRevision': proto_meta.load_bundle(root)['revision'],
            'scope': {'mode': 'delta', 'request': '调整新操作', 'requirements': [
                {'id': 'R1', 'text': '调整新操作', 'sourceQuote': '调整新操作', 'before': '旧操作表现', 'after': '新的操作表现'}]},
            'pages': [{'file': 'index.html', 'targets': [
                {'protoId': key, 'requirementIds': ['R1']} for key in ('new', 'toolbar', 'dynamic', 'blocked')],
                **hint_fields}]}


def hints(root):
    return proto_meta.load_bundle(root)['project']['pages'][0]['states'][0]['interactionHints']


@pytest.mark.parametrize('fields', [{}, {'hotspotAction': 'preserve'}])
def test_prd_only_import_preserves_existing_hints_and_revision(project, fields):
    before = proto_meta.load_bundle(project)
    report = proto_import.import_draft(project, draft(project, **fields))
    assert hints(project) == {'mode': 'targets', 'protoIds': ['old']}
    assert proto_meta.load_bundle(project) == before
    assert not report['changed']
    assert report['hintActions'][0]['action'] == 'preserve'
    assert '保留' in proto_import.format_report(report)


@pytest.mark.parametrize('fields', [{'hotspots': []}, {'hotspotAction': 'clear'}])
def test_explicit_clear_is_distinct_from_omission(project, fields):
    report = proto_import.import_draft(project, draft(project, **fields))
    assert hints(project) == {'mode': 'targets', 'protoIds': []}
    assert report['changed']


def test_replacement_uses_only_new_control_and_reports_binding(project):
    report = proto_import.import_draft(project, draft(project, hotspotAction='replace', hotspots=['new']))
    assert hints(project) == {'mode': 'targets', 'protoIds': ['new']}
    assert report['hotspotChecks'] == [{'scope': 'home/default', 'protoId': 'new', 'status': 'declared'}]


@pytest.mark.parametrize('fields', [
    {'hotspotAction': 'preserve', 'hotspots': ['new']},
    {'hotspotAction': 'replace'},
    {'hotspotAction': 'clear', 'hotspots': ['new']},
    {'hotspotAction': 'merge', 'hotspots': ['new']},
])
def test_ambiguous_hint_updates_are_rejected_before_writing(project, fields):
    before = proto_meta.load_bundle(project)
    with pytest.raises(proto_import.ImportError_, match='hotspot'):
        proto_import.import_draft(project, draft(project, **fields))
    assert proto_meta.load_bundle(project) == before


@pytest.mark.parametrize('target, reason', [('toolbar', '容器'), ('blocked', 'false')])
def test_invalid_hotspot_does_not_overwrite_old_scope_or_prd(project, target, reason):
    before = proto_meta.load_bundle(project)
    with pytest.raises(proto_import.ImportError_, match=reason):
        proto_import.import_draft(project, draft(project, hotspots=[target]))
    assert proto_meta.load_bundle(project) == before


def test_dynamic_listener_is_reported_for_runtime_verification(project):
    report = proto_import.import_draft(project, draft(project, hotspots=['dynamic']))
    assert hints(project)['protoIds'] == ['dynamic']
    assert report['hotspotChecks'][0]['status'] == 'runtime-check'
    assert any('dynamic' in warning and 'inspect' in warning for warning in report['warnings'])


@pytest.mark.parametrize('fields,keep_manual', [({'hotspots': ['new']}, True), ({'hotspotAction': 'clear'}, False)])
def test_import_keeps_user_exclusions_and_manual_mapping_unless_cleared(project, fields, keep_manual):
    before = proto_meta.load_bundle(project)
    state = before['project']['pages'][0]['states'][0]
    manual = [{'id': 'manual', 'label': '手动添加', 'anchor': {'protoId': 'dynamic'}}]
    excluded = [{'id': 'excluded', 'anchor': {'protoId': 'old'}}]
    state['interactionHints'].update(manualTargets=manual, excludedTargets=excluded)
    proto_meta.save_bundle(project, before)
    proto_import.import_draft(project, draft(project, **fields))
    saved = hints(project)
    assert saved['excludedTargets'] == excluded
    assert (saved.get('manualTargets') == manual) == keep_manual
