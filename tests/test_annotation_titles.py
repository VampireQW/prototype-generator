"""标注标题和页面序号样式：持久化、输入边界、导出与发布差异。"""
import json
from pathlib import Path
import subprocess
import sys
import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proto_meta
import publication_versions
import review_export


def fixture(tmp_path):
    (tmp_path / 'index.html').write_text('<html><button data-proto-id="save">保存</button></html>', encoding='utf-8')
    bundle = proto_meta.default_bundle(tmp_path, (tmp_path / 'index.html').as_uri(), '样例')
    page = bundle['project']['pages'][0]
    bundle['prd']['annotations'] = [{'id': 'n1', 'pageId': page['id'], 'stateId': 'default', 'number': 1,
        'body': '1. 一级\n    1. 二级\n        1. 三级', 'anchor': {'protoId': 'save'}, 'color': '#ff9e47'}]
    return bundle


def test_new_fields_roundtrip_and_old_notes_are_preserved(tmp_path):
    bundle = fixture(tmp_path)
    bundle['project']['pinStyle'] = {'color': '#123456', 'size': 48}
    bundle['prd']['annotations'][0]['title'] = '<img src=x onerror=alert(1)> 标题'
    proto_meta.save_bundle(tmp_path, bundle)
    saved = proto_meta.load_bundle(tmp_path)
    assert saved['project']['pinStyle'] == bundle['project']['pinStyle']
    assert saved['prd']['annotations'] == bundle['prd']['annotations']
    del saved['project']['pinStyle']
    del saved['prd']['annotations'][0]['title']
    proto_meta.save_bundle(tmp_path, saved)
    old = proto_meta.load_bundle(tmp_path)
    assert 'pinStyle' not in old['project'] and 'title' not in old['prd']['annotations'][0]
    assert old['prd']['annotations'][0]['color'] == '#ff9e47'


@pytest.mark.parametrize('title', [None, 123, [], 'x'*121, 'a\nb', 'a\x00b'])
def test_bad_titles_rejected(tmp_path, title):
    bundle = fixture(tmp_path)
    bundle['prd']['annotations'][0]['title'] = title
    with pytest.raises(ValueError, match='标题'):
        proto_meta.validate_bundle(bundle)


@pytest.mark.parametrize('style', [None, 'red', {'color': 'red'}, {'color': '#fff;display:none'}, {'size': True}, {'size': 23}, {'size': 57}, {'size': 36.1}, {'size': None}, {'css': 'x'}])
def test_bad_global_styles_rejected(tmp_path, style):
    bundle = fixture(tmp_path)
    bundle['project']['pinStyle'] = style
    with pytest.raises(ValueError, match='序号'):
        proto_meta.validate_bundle(bundle)


def test_export_carries_title_and_global_style(tmp_path):
    bundle = fixture(tmp_path)
    bundle['prd']['annotations'][0]['title'] = '班级范围'
    bundle['project']['pinStyle'] = {'color': '#123456', 'size': 24}
    data = review_export.review_data(bundle, '2026-11-05 16:00:00')
    assert data['pinStyle'] == bundle['project']['pinStyle']
    assert data['annotations'][0]['title'] == '班级范围'
    shell = review_export.render_shell(review_export.SHELL_TEMPLATE.read_text(encoding='utf-8'), data)
    assert 'pinStyle: data.pinStyle' in shell and 'title.textContent = note.title' in shell


def test_publication_fingerprint_and_title_changes_are_not_position_changes(tmp_path):
    bundle = fixture(tmp_path)
    before = publication_versions.capture(tmp_path, bundle)
    bundle['prd']['annotations'][0]['title'] = '班级范围'
    after = publication_versions.capture(tmp_path, bundle)
    changes = publication_versions.compare(before, after)
    assert after['contentVersion'] != before['contentVersion']
    assert len(changes) == 1 and changes[0]['description'] == '标注标题更新'
    assert changes[0]['target']['noteId'] == 'n1' and changes[0]['after'] == '班级范围'
    pure = publication_versions.capture(tmp_path, bundle, mode='clean')
    bundle['project']['pinStyle'] = {'size': 56, 'color': '#ff0000'}
    styled = publication_versions.capture(tmp_path, bundle)
    assert styled['contentVersion'] != after['contentVersion']
    assert publication_versions.compare(after, styled)[0]['description'] == '页面标注序号颜色或大小调整'
    assert pure['contentVersion'] == publication_versions.capture(tmp_path, bundle, mode='clean')['contentVersion']


def test_pin_size_reset_and_global_color_do_not_mutate_individual_colors():
    source = (Path(__file__).resolve().parents[1] / 'src/proto-appearance.js').read_text(encoding='utf-8')
    script = 'global.window={};' + source + '''
const a=window.ProtoAppearance, values={}, element={style:{setProperty(k,v){values[k]=v;}}};
const note={color:'#ff9e47'};
a.applyPin(element,note,{color:'#123456'});a.applyPinSize(element,{size:56});
if(values['--pin-fill']!=='#123456'||values['--pin-size']!=='56px')throw Error('统一设置未应用');
a.applyPin(element,note);a.applyPinSize(element,{});
if(values['--pin-fill']!=='#ff9e47'||values['--pin-size']!=='36px'||note.color!=='#ff9e47')throw Error('单独配色或默认大小丢失');
if(a.pinStyle({size:Infinity,color:'red'}).size!==36)throw Error('无效大小未降级');
console.log('passed');
'''
    result = subprocess.run(['node', '-'], input=script, text=True, encoding='utf-8', capture_output=True, check=True)
    assert result.stdout.strip() == 'passed'


def test_export_lists_keep_nested_mixed_types_continuations_and_start_number():
    shell = (Path(__file__).resolve().parents[1] / 'src/review_shell.html').read_text(encoding='utf-8')
    renderer = re.search(r'function esc\(s\) \{[\s\S]+?(?=\s+// ---------- 数据与状态)', shell)[0]
    source = '3. 一级\n    1. 二级\n        1. 三级\n    2. 二级第二条\n4. 一级第二条\n    - 子项\n      续行\n\n后续段落'
    script = "const data={};const location={href:'https://example.test/'};" + renderer + '\nconst html=md(' + json.dumps(source) + ');\n' + '''
if(!html.includes('<ol start="3"><li>一级<ol><li>二级<ol><li>三级</li></ol></li><li>二级第二条</li></ol></li><li>一级第二条<ul><li>子项<br>续行</li></ul></li></ol>'))throw Error(html);
if(!html.includes('<p>后续段落</p>'))throw Error(html);
if(md('1. <script>alert(1)</script>').includes('<script>'))throw Error('原始 HTML 被执行');
console.log('passed');
'''
    result = subprocess.run(['node','-'],input=script,text=True,encoding='utf-8',capture_output=True,check=True)
    assert result.stdout.strip() == 'passed'
