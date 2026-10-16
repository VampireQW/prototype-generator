"""本期 PRD 的内容粒度：背景、目标与每条规则都要追溯需求。"""
import copy
import json

import pytest

import proto_import
import proto_meta


@pytest.fixture
def pad(tmp_path):
    (tmp_path / 'pad.html').write_text('<html><title>作业详情</title><button data-proto-id="old-tab">学案/作业</button><section data-proto-id="cards"><input type="checkbox" data-proto-id="explain-toggle"><button data-proto-id="sort">按题号正序</button></section></html>', encoding='utf-8')
    return tmp_path


def current_change():
    return {'schemaVersion': 3, 'baseRevision': 0, 'scope': {
        'mode': 'delta', 'request': '原按钮不便直观看出是否需讲解。本期将我不需讲解按钮改为需讲解开关，开启显示需要讲解、关闭显示不需讲解，切换后即时更新并反馈。',
        'requirements': [{'id': 'R1', 'text': '以开关表达是否需要讲解', 'sourceQuote': '将我不需讲解按钮改为需讲解开关', 'before': '题卡使用我不需讲解按钮', 'after': '题卡使用常驻的需讲解开关'}],
        'exclusions': ['原有学案/作业 Tab 切换', '原有题卡答案展示', '原有排序和题干折叠']},
        'pages': [{'file': 'pad.html', 'requirementIds': ['R1'],
            'document': {'background': [{'requirementId': 'R1', 'text': '原按钮不便直观看出当前是否需要讲解。'}], 'goals': [{'requirementId': 'R1', 'text': '以开关状态明确表达讲解意愿。'}]},
            'targets': [{'protoId': 'explain-toggle', 'requirementIds': ['R1']}],
            'hotspots': ['explain-toggle'], 'annotations': [{'protoId': 'explain-toggle', 'items': [
                {'section': '页面显示', 'requirementId': 'R1', 'markdown': '- 开启显示“需要讲解”，关闭显示“不需讲解”。'},
                {'section': '交互说明', 'requirementId': 'R1', 'markdown': '1. 切换后即时更新讲解意愿，并显示原型已实现的反馈。'}]}]}]}


def test_only_current_toggle_rules_are_rendered_and_auditable(pad):
    data = current_change()
    original = copy.deepcopy(data)
    report = proto_import.import_draft(pad, data)
    saved = proto_meta.load_bundle(pad)
    assert data == original, '渲染正文不得修改 Agent 的原始草稿，便于复核留档'
    assert saved['schemaVersion'] == 2, '草稿升级不改变工作台元数据版本'
    assert len(saved['prd']['annotations']) == 1
    text = saved['prd']['annotations'][0]['body']
    assert text.startswith('### 页面显示\n\n- ')
    assert all(word not in text for word in ('学案', '排序', '题干折叠', '正确答案'))
    background = saved['prd']['documents'][0]['markdown']
    assert '需求背景' in background and '需求目标' in background and '横屏双栏' not in background
    assert len(report['contentRefs']) == 4 and {item['requirementId'] for item in report['contentRefs']} == {'R1'}
    hints = saved['project']['pages'][0]['states'][0]['interactionHints']
    assert hints == {'mode': 'targets', 'protoIds': ['explain-toggle']}
    assert '本期不涉及' in proto_import.format_report(report)


@pytest.mark.parametrize('place', ['background', 'goals', 'annotation'])
def test_unrelated_rule_without_requirement_is_rejected_before_writing(pad, place):
    data = current_change()
    item = {'text': '旧有排序规则'} if place != 'annotation' else {'section': '交互说明', 'markdown': '1. 按题号正序可切换为倒序。'}
    if place == 'annotation':
        data['pages'][0]['annotations'][0]['items'].append(item)
    else:
        data['pages'][0]['document'][place].append(item)
    with pytest.raises(proto_import.ImportError_, match='每条内容必须关联本期'):
        proto_import.import_draft(pad, data)
    assert not (pad / '.prototype').exists()


def test_unchanged_tab_cannot_be_declared_as_delta_requirement(pad):
    data = current_change()
    data['scope']['requirements'].append({'id': 'R2', 'text': '学案/作业 Tab 切换', 'sourceQuote': '本期', 'before': 'Tab 切换', 'after': 'Tab 切换'})
    with pytest.raises(proto_import.ImportError_, match='before / after'):
        proto_import.import_draft(pad, data)
    assert not (pad / '.prototype').exists()


def test_requirement_must_quote_current_request(pad):
    data = current_change()
    data['scope']['requirements'][0]['sourceQuote'] = '增加学案/作业 Tab 切换'
    with pytest.raises(proto_import.ImportError_, match='sourceQuote'):
        proto_import.import_draft(pad, data)


def test_container_does_not_authorize_rules_for_other_requirement(pad):
    data = current_change()
    data['scope']['requirements'].append({'id': 'R2', 'text': '另一个改动', 'sourceQuote': '本期', 'before': '旧状态', 'after': '新状态'})
    data['pages'][0]['annotations'][0]['items'].append({'section': '交互说明', 'requirementId': 'R2', 'markdown': '2. 切换题卡排序。'})
    with pytest.raises(proto_import.ImportError_, match='每条内容必须关联本期'):
        proto_import.import_draft(pad, data)


def test_multi_rule_payload_cannot_hide_in_one_traced_item(pad):
    data = current_change()
    data['pages'][0]['annotations'][0]['items'][-1]['markdown'] += '\n2. 点击排序按钮重排题卡。'
    with pytest.raises(proto_import.ImportError_, match='一个顶层列表项'):
        proto_import.import_draft(pad, data)


def test_old_draft_or_untraced_body_cannot_bypass_new_contract(pad):
    data = current_change()
    data['schemaVersion'] = 2
    with pytest.raises(proto_import.ImportError_, match='schemaVersion 必须为 3'):
        proto_import.import_draft(pad, data)
    data['schemaVersion'] = 3
    data['pages'][0]['annotations'][0]['body'] = '### 交互说明\n\n1. 旧有 Tab 切换。'
    with pytest.raises(proto_import.ImportError_, match='不接受整段 body'):
        proto_import.import_draft(pad, data)


def test_reimport_request_does_not_enable_whole_page_prd(pad):
    data = current_change()
    data['scope']['request'] += '请按新标准重新落库。'
    data['scope']['mode'] = 'full'
    with pytest.raises(proto_import.ImportError_, match='fullRequest'):
        proto_import.import_draft(pad, data)


def test_bad_draft_preserves_existing_prd(pad):
    proto_import.import_draft(pad, current_change())
    before = {path.name: path.read_bytes() for path in (pad / '.prototype').glob('*.json')}
    data = current_change()
    data['baseRevision'] = proto_meta.load_bundle(pad)['revision']
    data['pages'][0]['document'] = '横屏双栏，支持原有 Tab、排序和答案显示。'
    with pytest.raises(proto_import.ImportError_):
        proto_import.import_draft(pad, data, replace_doc=True)
    assert before == {path.name: path.read_bytes() for path in (pad / '.prototype').glob('*.json')}


def test_cli_rejects_old_draft_and_preserves_it(pad, capsys):
    data = current_change(); data['schemaVersion'] = 2
    directory = pad / '.prototype'; directory.mkdir()
    path = directory / 'prd.draft.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    original = path.read_bytes()
    assert proto_import.main([str(pad)]) != 0
    assert path.read_bytes() == original and 'schemaVersion 必须为 3' in capsys.readouterr().err


def with_old_misannotations(pad):
    proto_import.import_draft(pad, current_change())
    bundle = proto_meta.load_bundle(pad)
    page = bundle['project']['pages'][0]
    for number, (pid, confirmed) in enumerate([('old-tab', False), ('sort', True)], 2):
        bundle['prd']['annotations'].append({'id': pid + '-note', 'pageId': page['id'], 'stateId': 'default', 'number': number, 'confirmed': confirmed, 'body': '原有功能说明', 'anchor': {'protoId': pid}, 'placement': {'kind': 'element', 'x': 0, 'y': 0}})
    bundle['revision'] += 1
    proto_meta.save_bundle(pad, bundle)
    data = current_change(); data['baseRevision'] = bundle['revision']
    data['scope']['request'] += '请按新标准清理本期误写的无关标注。'
    data['scope']['cleanupRequest'] = '按新标准清理本期误写的无关标注'
    data['pages'][0]['removals'] = [{'annotationId': 'old-tab-note', 'reason': '本期只改讲解开关，Tab 行为保持不变。'}, {'annotationId': 'sort-note', 'reason': '排序不属于本期需求。'}]
    return data


def test_cleanup_is_targeted_preserves_confirmed_and_remembers_deletion(pad):
    data = with_old_misannotations(pad)
    report = proto_import.import_draft(pad, data)
    saved = proto_meta.load_bundle(pad)
    ids = {n['id'] for n in saved['prd']['annotations']}
    assert 'old-tab-note' not in ids and 'sort-note' in ids
    assert len(report['removedAnnotations']) == 1 and any('已确认' in line for line in report['skipped'])
    assert any(item['protoId'] == 'old-tab' for item in saved['prd']['deletedAnnotations'])


@pytest.mark.parametrize('failure', ['no-authorization', 'wrong-state', 'remove-and-recreate'])
def test_bad_cleanup_leaves_existing_annotations_unchanged(pad, failure):
    data = with_old_misannotations(pad)
    before = proto_meta.load_bundle(pad)
    if failure == 'no-authorization':
        del data['scope']['cleanupRequest']
    elif failure == 'wrong-state':
        data['pages'][0]['removals'][0]['annotationId'] = 'not-here'
    else:
        data['pages'][0]['removals'][0]['annotationId'] = before['prd']['annotations'][0]['id']
    with pytest.raises(proto_import.ImportError_):
        proto_import.import_draft(pad, data)
    assert proto_meta.load_bundle(pad) == before


def test_cleanup_dry_run_does_not_delete_or_add_tombstones(pad):
    data = with_old_misannotations(pad)
    before = proto_meta.load_bundle(pad)
    report = proto_import.import_draft(pad, data, dry_run=True)
    assert report['removedAnnotations'] and proto_meta.load_bundle(pad) == before


def test_published_skill_example_runs_and_qoder_copy_matches(pad):
    import re
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    reference = repo / 'agent-skills/prototype-flow/references/prd-import.md'
    installed = repo.parent / '.qoder/skills/prototype-flow/references/prd-import.md'
    assert reference.read_bytes() == installed.read_bytes()
    example = json.loads(re.search(r'```json\n([\s\S]*?)\n```', reference.read_text(encoding='utf-8')).group(1))
    report = proto_import.import_draft(pad, example)
    assert report['changed'] and len(report['annotations']) == 1
