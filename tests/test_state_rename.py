"""状态改名仅变更显示标题，保持身份、绑定与导出语义。"""
import copy
import shutil
import subprocess

import pytest
import proto_meta
import prototype_manifest as pm
import review_export
from test_prototype_manifest import project,registered
from test_external_api import api,prototype


def test_state_rename_validates_before_mutating_and_preserves_identity():
    node=shutil.which('node')
    if not node:pytest.skip('需要 Node.js')
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');const c={};c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync(process.argv[1]+'/project-navigation.js','utf8'),c);
const rename=c.ProtoProjectNavigation.updateStateTitle;
assert.equal(typeof rename,'function');
const project={pages:[{id:'home',states:[{id:'default',title:'默认页面',kind:'default'},{id:'running',title:'进行中',kind:'adapter',interactionHints:{mode:'targets',protoIds:['save']},previewType:'mobile'}]}]};
const before=JSON.parse(JSON.stringify(project));
for(const title of ['', '   ', 'x'.repeat(101),'a\nb'])assert.throws(()=>rename(project,'home','running',title));
assert.equal(JSON.stringify(project),JSON.stringify(before));
assert.throws(()=>rename(project,'home','missing','新状态'));
assert.equal(rename(project,'home','running','  智批进行中  '),true);
assert.deepEqual(JSON.parse(JSON.stringify(project.pages[0].states[1])),{...before.pages[0].states[1],title:'智批进行中',titleUserSet:true});
assert.equal(rename(project,'home','running','智批进行中'),false);
assert.equal(rename(project,'home','default','已完成'),true);
assert.equal(project.pages[0].states[0].id,'default');
project.pages[0].trashedAt='now';assert.throws(()=>rename(project,'home','running','不应修改'));
'''
    result=subprocess.run([node,'-e',script,str(pm.ASSETS_DIR)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_state_title_survives_manifest_refresh_and_both_exports(project):
    root,data=project;bundle=registered(root)
    page=next(p for p in bundle['project']['pages'] if p['file']=='app.html')
    state=next(s for s in page['states'] if s['id']=='detail')
    state.update(title='设置详情 · 自定义',titleUserSet=True)
    original=copy.deepcopy(state);prd=copy.deepcopy(bundle['prd'])
    proto_meta.save_bundle(root,bundle)
    data['pages'][2]['states'][0].update(title='声明中的旧名称',previewType='pad')
    proto_meta.write_json_atomic(root/pm.MANIFEST_NAME,data)
    assert proto_meta.ensure_pages_registered(root,bundle)
    saved=proto_meta.load_bundle(root)
    renamed=next(p for p in saved['project']['pages'] if p['id']==page['id'])['states'][1]
    assert renamed=={**original,'previewType':'pad'}
    assert saved['prd']==prd
    for flavor,builder in [('pure',review_export.build_pure_export),('review',review_export.build_review_export)]:
        output=root.parent/('state-renamed-'+flavor);builder(root,saved,output)
        html=(output/'index.html').read_text(encoding='utf-8')
        assert '设置详情 · 自定义' in html


def test_saved_state_title_keeps_confirmed_notes_and_rejects_stale_revision(api,tmp_path):
    root=prototype(tmp_path/'project')
    pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    bundle=proto_meta.load_bundle(root);page=bundle['project']['pages'][0]
    page['states'].append({'id':'running','title':'进行中','kind':'adapter'})
    bundle['prd']['annotations']=[{'id':'locked','pageId':page['id'],'stateId':'running','number':1,'confirmed':True,'body':'保留规则','anchor':{'protoId':'save'},'placement':{'kind':'element','rx':0,'ry':0,'x':0,'y':0}}]
    proto_meta.save_bundle(root,bundle)
    before=copy.deepcopy(bundle);page['states'][1].update(title='智批进行中',titleUserSet=True)
    payload={'projectId':pid,'expectedRevision':before['revision'],'bundle':bundle}
    status,result=api.request('/api/proto/save',payload)
    assert status==200,result
    saved=proto_meta.load_bundle(root)
    assert saved['prd']==before['prd'] and saved['changes']==before['changes']
    assert saved['project']['pages'][0]['states'][1]['id']=='running'
    assert saved['project']['pages'][0]['states'][1]['title']=='智批进行中'
    assert api.request('/api/proto/save',payload)[0]==409
