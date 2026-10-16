import copy
import json
import shutil
import subprocess

import pytest

import page_lifecycle
import proto_meta
import prototype_manifest as pm
import review_export


@pytest.fixture
def hierarchy(tmp_path):
    for name in ('index', 'a', 'b', 'c', 'd'):
        (tmp_path / (name + '.html')).write_text('<html><body>' + name + '</body></html>', encoding='utf-8')
    declaration = {'schemaVersion': 1, 'clients': [{'id': 'web', 'title': 'Web', 'previewType': 'web'}],
                   'pages': [{'file': 'index.html', 'role': 'launcher'},
                             {'file': 'a.html', 'clientId': 'web'},
                             {'file': 'b.html', 'clientId': 'web', 'parentFile': 'a.html'},
                             {'file': 'c.html', 'clientId': 'web', 'parentFile': 'b.html'},
                             {'file': 'd.html', 'clientId': 'web'}]}
    proto_meta.write_json_atomic(tmp_path / pm.MANIFEST_NAME, declaration)
    bundle = proto_meta.ensure_bundle(tmp_path)
    proto_meta.ensure_pages_registered(tmp_path, bundle)
    return tmp_path, bundle


def test_manifest_registers_three_levels_and_preserves_prd_and_manual_structure(hierarchy):
    root, bundle = hierarchy
    pages = {p['id']: p for p in bundle['project']['pages']}
    assert pages['b']['parentId'] == 'a' and pages['c']['parentId'] == 'b'
    before = copy.deepcopy(bundle['prd'])
    assert proto_meta.validate_bundle(bundle) is bundle
    # An unrelated declaration change does not erase manually created hierarchy.
    declaration = pm.load_manifest(root)
    declaration['pages'] = [{k: v for k, v in p.items() if k != 'parentFile'} for p in declaration['pages']]
    pages['d']['parentId'] = 'a'
    pm.apply_manifest(root, bundle, declaration)
    assert pages['d']['parentId'] == 'a' and pages['c']['parentId'] == 'b'
    assert bundle['prd'] == before


@pytest.mark.parametrize('mutation, message', [
    ({'a': 'c'}, '循环'), ({'d': 'c'}, '三级'), ({'b': 'missing'}, '不存在'),
    ({'a': 'home'}, '演示'), ({'b': ['a']}, '无效'),
])
def test_invalid_parentage_is_rejected(hierarchy, mutation, message):
    _, bundle = hierarchy
    for page in bundle['project']['pages']:
        if page['id'] in mutation:
            page['parentId'] = mutation[page['id']]
    with pytest.raises(ValueError, match=message):
        proto_meta.validate_bundle(bundle)


def test_cross_client_parentage_is_rejected(hierarchy):
    _, bundle = hierarchy
    bundle['project']['clients'].append({'id': 'app', 'title': 'App', 'previewType': 'mobile'})
    next(p for p in bundle['project']['pages'] if p['id'] == 'c')['clientId'] = 'app'
    with pytest.raises(ValueError, match='同一个端'):
        proto_meta.validate_bundle(bundle)


def test_portable_manifest_rejects_four_levels_and_cycles(hierarchy):
    root, _ = hierarchy
    declaration = pm.load_manifest(root)
    declaration['pages'][-1]['parentFile'] = 'c.html'
    proto_meta.write_json_atomic(root / pm.MANIFEST_NAME, declaration)
    with pytest.raises(ValueError, match='三级'):
        pm.load_manifest(root)
    declaration['pages'][-1].pop('parentFile')
    declaration['pages'][1]['parentFile'] = 'c.html'
    proto_meta.write_json_atomic(root / pm.MANIFEST_NAME, declaration)
    with pytest.raises(ValueError, match='循环'):
        pm.load_manifest(root)


def test_trash_restore_and_delete_parent_keep_children_files_and_export_tree(hierarchy):
    root, bundle = hierarchy
    before = copy.deepcopy(bundle['project']['pages'])
    trashed = page_lifecycle.change_page(root, 'b', 'trash', bundle['revision'])
    for pages in (pm.public_navigation(trashed['project'])['pages'], review_export.review_data(trashed, '')['pages']):
        assert not any(p['id'] == 'b' for p in pages)
        assert next(p for p in pages if p['id'] == 'c')['parentId'] == 'a'
    restored = page_lifecycle.change_page(root, 'b', 'restore', trashed['revision'])
    assert restored['project']['pages'] == before
    trashed = page_lifecycle.change_page(root, 'b', 'trash', restored['revision'])
    deleted = page_lifecycle.change_page(root, 'b', 'delete', trashed['revision'], 'b.html')
    assert next(p for p in deleted['project']['pages'] if p['id'] == 'c')['parentId'] == 'a'
    assert (root / 'c.html').is_file() and (root / 'a.html').is_file() and not (root / 'b.html').exists()
    declaration = pm.load_manifest(root)
    assert next(p for p in declaration['pages'] if p['file'] == 'c.html')['parentFile'] == 'a.html'
    pm.build_launcher(root, deleted)
    source = (root / 'index.html').read_text(encoding='utf-8')
    navigation = json.loads(source.split('id="navigationData">', 1)[1].split('</script>', 1)[0])
    assert next(p for p in navigation['pages'] if p['id'] == 'c')['parentId'] == 'a'


def test_navigation_moves_whole_subtrees_with_atomic_depth_and_cycle_guards():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js 未安装')
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1]+'/project-navigation.js','utf8'),context);
const nav=context.ProtoProjectNavigation;
const page=(id,parentId='',clientId='web')=>({id,file:id+'.html',clientId,...(parentId?{parentId}:{}),states:[{id:'default',interactionHints:{mode:'none'}}]});
const project={clients:[{id:'web'},{id:'app'}],pages:[page('a'),page('b','a'),page('c','b'),page('d'),page('e','','app'),{...page('launcher'),role:'launcher'}]};
let before=JSON.stringify(project);
assert.equal(nav.reorderProject(project,{kind:'page',id:'a',targetId:'c',position:'inside'}),false);
assert.equal(nav.reorderProject(project,{kind:'page',id:'d',targetId:'c',position:'inside'}),false);
assert.equal(nav.reorderProject(project,{kind:'page',id:'a',targetId:'d',position:'inside'}),false);
assert.equal(JSON.stringify(project),before);
assert.match(nav.reorderError(project,{kind:'page',id:'a',targetId:'d',position:'inside'}),/三级/);
const states=JSON.stringify(project.pages.find(p=>p.id==='b').states);
assert.equal(nav.reorderProject(project,{kind:'page',id:'b',targetId:'e',position:'inside'}),true);
assert.equal(project.pages.find(p=>p.id==='b').parentId,'e');
assert.equal(project.pages.find(p=>p.id==='c').parentId,'b');
assert.equal(project.pages.find(p=>p.id==='c').clientId,'app');
assert.equal(nav.pageTree(project).nodes.get('c').depth,3);
assert.equal(JSON.stringify(project.pages.find(p=>p.id==='b').states),states);
assert.equal(nav.reorderProject(project,{kind:'page',id:'b',targetId:'e',position:'after'}),true);
assert.equal(project.pages.find(p=>p.id==='b').parentId,undefined);
assert.deepEqual(Array.from(project.pages.filter(p=>['e','b','c'].includes(p.id)),p=>p.id),['e','b','c']);
assert.equal(nav.reorderProject(project,{kind:'page',id:'b',targetId:'web',position:'root'}),true);
assert.equal(project.pages.find(p=>p.id==='c').clientId,'web');
project.pages.find(p=>p.id==='b').trashedAt='now';
assert.equal(nav.pageTree(project).nodes.get('c').parentId,'');
delete project.pages.find(p=>p.id==='b').trashedAt;
nav.updatePageNavigation(project,'b',{clientId:'app',role:'page',previewType:'pad'});
assert.equal(project.pages.find(p=>p.id==='c').clientId,'app');
nav.updatePageNavigation(project,'b',{clientId:'app',role:'launcher',previewType:'web'});
assert.equal(project.pages.find(p=>p.id==='c').parentId,undefined);
before=JSON.stringify(project);
assert.equal(nav.reorderProject(project,{kind:'page',id:'a',targetId:'launcher',position:'inside'}),false);
assert.equal(JSON.stringify(project),before);
'''
    result = subprocess.run([node, '-e', script, str(pm.ASSETS_DIR)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
