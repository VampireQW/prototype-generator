"""Behavioral checks for the actual exported launcher's frame and URL sync."""
import shutil
import subprocess

import pytest
import prototype_manifest


def test_launcher_syncs_frame_state_preview_and_history():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js 未安装')
    script = r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const assets = process.argv[1], listeners = {}, previews = [], messages = [], enters = [];
const frame = {contentWindow:{PrototypeBridge:{enter:state=>enters.push(state)},postMessage:msg=>messages.push(msg)},contentDocument:{documentElement:{dataset:{}}}};
const project = {pages:[{id:'business',file:'business.html',title:'业务',previewType:'web',states:[{id:'default'},{id:'app',previewType:'mobile'},{id:'tablet',previewType:'pad'}]}],defaultPage:'business'};
const nodes = {navigationData:{textContent:JSON.stringify(project)},pageFrame:frame,scope:{},shellToggle:{setAttribute(){}} ,navList:{},toggleNav:{}};
const context = {URLSearchParams,history:{replaceState:(_,__,value)=>context.hash=value},location:{hash:''},document:{getElementById:id=>nodes[id]}};
context.window = context;
context.addEventListener = (type,fn)=>listeners[type]=fn;
vm.createContext(context);
vm.runInContext(fs.readFileSync(assets+'/project-navigation.js','utf8'),context);
let navConfig;
context.ProtoProjectNavigation.mount = (_,config)=>{navConfig=config;return{update:config=>navConfig=config}};
context.ProtoProjectNavigation.applyPreview = (_,type,shell)=>previews.push({type,shell});
const template = fs.readFileSync(assets+'/launcher.html','utf8');
vm.runInContext(template.match(/<script>\s*([\s\S]*?)<\/script>/)[1],context);
assert.equal(frame.src,'business.html');
assert.equal(previews.at(-1).type,'web');
frame.onload();
assert.deepEqual(enters,['default']);
assert.equal(messages.filter(m=>m.type==='enterState').length,0);
listeners.message({source:frame.contentWindow,data:{__protoProject:1,type:'state',stateId:'app'}});
assert.equal(context.hash,'#p=business&s=app');
assert.equal(navConfig.currentState,'app');
assert.equal(previews.at(-1).type,'mobile');
assert.equal(nodes.shellToggle.hidden,false);
nodes.shellToggle.onclick({currentTarget:nodes.shellToggle});
assert.deepEqual(previews.at(-1),{type:'mobile',shell:false});
listeners.message({source:{},data:{__protoProject:1,type:'state',stateId:'default'}});
listeners.message({source:frame.contentWindow,data:{__protoProject:1,type:'state',stateId:'unregistered'}});
assert.equal(context.hash,'#p=business&s=app');
context.location.hash='#p=business&s=default';listeners.hashchange();
assert.equal(previews.at(-1).type,'web');
assert.equal(nodes.shellToggle.hidden,true);
assert.deepEqual(enters,['default','default']);
navConfig.onSelect('business','tablet');
assert.equal(previews.at(-1).type,'pad');
assert.equal(nodes.shellToggle.hidden,false);
nodes.shellToggle.onclick({currentTarget:nodes.shellToggle});
assert.deepEqual(previews.at(-1),{type:'pad',shell:true});
delete frame.contentWindow.PrototypeBridge;
navConfig.onSelect('business','app');
assert.equal(messages.filter(m=>m.type==='enterState').length,1);
assert.equal(context.hash,'#p=business&s=app');
'''
    result = subprocess.run([node, '-e', script, str(prototype_manifest.ASSETS_DIR)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_pad_preview_scales_without_replacing_iframe_and_cleans_up_on_switch():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node.js 未安装')
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const observers=[],events=new Map();
const context={getComputedStyle:()=>({paddingLeft:'20px',paddingRight:'20px',paddingTop:'20px',paddingBottom:'20px'}),ResizeObserver:class{constructor(fn){this.fn=fn;observers.push(this);}observe(){}disconnect(){this.closed=true;}}};
context.window=context;context.addEventListener=(type,fn)=>events.set(fn,type);context.removeEventListener=(type,fn)=>events.delete(fn);vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1]+'/project-navigation.js','utf8'),context);
const classes=new Set(),canvas={clientWidth:1260,clientHeight:900,classList:{add:n=>classes.add(n),toggle:(n,on)=>on?classes.add(n):classes.delete(n)}};
const frame={parentElement:canvas,style:{}};
const apply=context.ProtoProjectNavigation.applyPreview;
apply(frame,'pad');assert.equal(Number(frame.style.zoom),1);assert.ok(classes.has('ppn-pad'));assert.ok(classes.has('ppn-shell'));
canvas.clientWidth=650;observers.at(-1).fn();assert.equal(Number(frame.style.zoom),.5);
apply(frame,'pad',false);assert.equal(observers[0].closed,true);assert.equal(Number(frame.style.zoom),610/1180);assert.equal(classes.has('ppn-shell'),false);
assert.equal(frame.parentElement,canvas);
apply(frame,'web');assert.equal(frame.style.zoom,'');assert.equal(classes.has('ppn-pad'),false);assert.equal(events.size,0);assert.equal(observers.at(-1).closed,true);
apply(frame,'mobile');assert.ok(classes.has('ppn-mobile'));assert.equal(frame.style.zoom,'');
'''
    result=subprocess.run([node,'-e',script,str(prototype_manifest.ASSETS_DIR)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_navigation_reorder_preserves_membership_ids_and_state_data():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js 未安装')
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1]+'/project-navigation.js','utf8'),context);
const project={clients:[{id:'teacher',title:'教师'},{id:'student',title:'学生'}],pages:[
{id:'a',file:'a.html',clientId:'teacher',states:[{id:'default'}]},
{id:'s',file:'s.html',clientId:'student',states:[{id:'default'}]},
{id:'b',file:'b.html',clientId:'teacher',states:[{id:'default'},{id:'detail'}]},
{id:'launch',file:'index.html',role:'launcher',states:[{id:'default'}]}]};
const original=JSON.stringify(Object.fromEntries(project.pages.map(p=>[p.id,p])));
const reorder=context.ProtoProjectNavigation.reorderProject;
assert.equal(reorder(project,{kind:'page',id:'b',targetId:'a',position:'before'}),true);
assert.deepEqual(project.pages.map(p=>p.id),['b','a','s','launch']);
assert.equal(reorder(project,{kind:'page',id:'b',targetId:'a',position:'before'}),false);
assert.equal(reorder(project,{kind:'page',id:'a',targetId:'launch',position:'before'}),false);
assert.equal(reorder(project,{kind:'unknown',id:'a',targetId:'b',position:'before'}),false);
assert.equal(reorder(project,{kind:'client',id:'student',targetId:'teacher',position:'before'}),true);
assert.deepEqual(Array.from(project.clients,c=>c.id),['student','teacher']);
assert.equal(JSON.stringify(Object.fromEntries(['a','s','b','launch'].map(id=>[id,project.pages.find(p=>p.id===id)]))),original);
'''
    result = subprocess.run([node, '-e', script, str(prototype_manifest.ASSETS_DIR)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
