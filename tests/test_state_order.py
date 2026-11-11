"""状态显示排序不改变状态定义、入口或业务绑定。"""
import copy
import json
import shutil
import subprocess

import pytest
import proto_meta
import prototype_manifest as pm
import review_export
from test_prototype_manifest import project,registered
from test_external_api import api,prototype


def test_reorder_states_is_page_scoped_preserves_definitions_and_rollbacks():
    node=shutil.which('node')
    if not node:pytest.skip('需要 Node.js')
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),c={};c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync(process.argv[1]+'/project-navigation.js','utf8'),c);const nav=c.ProtoProjectNavigation;
assert.equal(typeof nav.orderedStates,'function');
const states=[{id:'default',kind:'default',title:'默认',titleUserSet:true},{id:'pending',kind:'adapter',interactionHints:{mode:'targets',protoIds:['save']}},{id:'done',kind:'adapter'}];
const project={pages:[{id:'home',states},{id:'other',states:[{id:'default'},{id:'other-only'}]}]};
const before=JSON.stringify(project),base={kind:'state',pageId:'home',id:'done',targetId:'default',position:'before'};
const check={pages:[...project.pages]};assert.equal(nav.reorderProject(check,base),true);
assert.equal(JSON.stringify(project),before,'optimistic preview must not mutate rollback source');
assert.equal(JSON.stringify(check.pages[0].states),JSON.stringify(states),'state definitions and default entry must stay in original order');
assert.deepEqual(Array.from(nav.orderedStates(check.pages[0]),s=>s.id),['done','default','pending']);
assert.deepEqual(Array.from(check.pages[0].stateOrder),['done','default','pending']);
assert.equal(nav.reorderProject(check,base),false,'same placement is a no-op');
const valid=JSON.stringify(check);
for(const invalid of [{...base,pageId:'missing'},{...base,targetId:'other-only'},{...base,position:'inside'},{...base,id:'done',targetId:'done'}])assert.equal(nav.reorderProject(check,invalid),false);
assert.equal(JSON.stringify(check),valid);
assert.equal(nav.reorderProject(check,{...base,id:'default',targetId:'pending',position:'after'}),true);
assert.deepEqual(Array.from(nav.orderedStates(check.pages[0]),s=>s.id),['done','pending','default']);
check.pages[0].stateOrder=['gone','pending'];
assert.deepEqual(Array.from(nav.orderedStates(check.pages[0]),s=>s.id),['pending','default','done']);
assert.equal(nav.reorderProject(check,{...base,pageId:'other',id:'default',targetId:'pending'}),false);
'''
    result=subprocess.run([node,'-e',script,str(pm.ASSETS_DIR)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_state_display_order_survives_scan_and_both_exports(project):
    root,declaration=project;bundle=registered(root)
    page=next(p for p in bundle['project']['pages'] if p['file']=='app.html')
    page['stateOrder']=['detail','default'];definitions=copy.deepcopy(page['states'])
    proto_meta.save_bundle(root,bundle)
    declaration['pages'][2]['states'].append({'id':'pending','title':'处理中'})
    proto_meta.write_json_atomic(root/pm.MANIFEST_NAME,declaration)
    proto_meta.ensure_pages_registered(root,bundle)
    saved=proto_meta.load_bundle(root);new=next(p for p in saved['project']['pages'] if p['id']==page['id'])
    assert new['stateOrder']==['detail','default'] and new['states'][:2]==definitions
    assert next(p for p in pm.public_navigation(saved['project'])['pages'] if p['id']==page['id'])['stateOrder']==['detail','default']
    for flavor,builder in [('pure',review_export.build_pure_export),('review',review_export.build_review_export)]:
        out=root.parent/('state-ordered-'+flavor);builder(root,saved,out)
        html=(out/'index.html').read_text(encoding='utf-8')
        marker='id="navigationData">' if flavor=='pure' else 'id="review-data">'
        data=json.loads(html.split(marker,1)[1].split('</script>',1)[0])
        exported=next(p for p in data['pages'] if p['id']==page['id'])
        assert exported['stateOrder']==['detail','default']
        assert exported['states'][0]['id']=='default'


@pytest.mark.parametrize('value',['default',['default','default'],[None]])
def test_invalid_state_order_is_rejected(project,value):
    root,_=project;bundle=registered(root);bundle['project']['pages'][0]['stateOrder']=value
    with pytest.raises(ValueError,match='状态排序'):proto_meta.validate_bundle(bundle)


def test_saved_order_preserves_current_identity_and_confirmed_notes(api,tmp_path):
    root=prototype(tmp_path/'project');pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    bundle=proto_meta.load_bundle(root);page=bundle['project']['pages'][0]
    page['states'].append({'id':'pending','title':'处理中','kind':'adapter'})
    bundle['prd']['annotations']=[{'id':'locked','pageId':page['id'],'stateId':'pending','number':1,'confirmed':True,'body':'保留状态绑定','placement':{'kind':'document','x':0,'y':0}}]
    proto_meta.save_bundle(root,bundle);before=copy.deepcopy(bundle)
    page['stateOrder']=['pending','default']
    payload={'projectId':pid,'expectedRevision':before['revision'],'bundle':bundle}
    status,response=api.request('/api/proto/save',payload);assert status==200,response
    saved=proto_meta.load_bundle(root)
    assert saved['prd']==before['prd'] and saved['changes']==before['changes']
    assert saved['project']['pages'][0]['states']==before['project']['pages'][0]['states']
    assert saved['project']['pages'][0]['stateOrder']==['pending','default']
    assert api.request('/api/proto/save',payload)[0]==409
