"""Run the actual hotspot module against a small DOM, without a browser or private data."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parents[1] / 'src/proto-hotspots.js').read_text(encoding='utf-8')
HARNESS = r'''
const vm = require('node:vm'), assert = require('node:assert/strict');
class Target { addEventListener(){} removeEventListener(){} }
class El extends Target {
 constructor(tag, id, x=0) { super();this.tagName=tag;this.dataset={};this.attrs={};this.children=[];this.style={};this.isConnected=true;this.rect={left:x,top:80,right:x+80,bottom:110,width:80,height:30};if(id)this.setAttribute('data-proto-id',id); }
 setAttribute(k,v){this.attrs[k]=v;if(k==='data-proto-id')this.dataset.protoId=v;}
 getAttribute(k){return this.attrs[k]??null;}
 appendChild(el){this.children.push(el);el.parentElement=this;return el;}
 contains(el){return el===this||this.children.some(c=>c.contains(el));}
 closest(selector){for(let el=this;el;el=el.parentElement){if(el.matches(selector))return el;}return null;}
 matches(selector){return selector.split(',').some(s=>s===':disabled'?!!this.disabled:s==='input[type="checkbox"]'?this.tagName==='INPUT'&&this.type==='checkbox':s==='button'?this.tagName==='BUTTON':s==='input'?this.tagName==='INPUT':s==='[data-proto-hotspot="false"]'?this.dataset.protoHotspot==='false':s==='[data-prototype-owned]'?this.attrs['data-prototype-owned']!==undefined:false);}
 getBoundingClientRect(){return this.rect;}
 replaceChildren(){this.children=[];}
 remove(){this.isConnected=false;if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);}
}
const doc=new Target(),win=new Target();doc.documentElement=new El('HTML');doc.head=new El('HEAD');doc.body=new El('BODY');doc.documentElement.appendChild(doc.body);
const old=doc.body.appendChild(new El('BUTTON','old-export',20));old.onclick=()=>{};
const changed=doc.body.appendChild(new El('BUTTON','changed',130));changed.onclick=()=>{};
const group=doc.body.appendChild(new El('DIV','changed-group',240));
const check=group.appendChild(new El('INPUT','group-check',240));check.type='checkbox';
const inert=doc.body.appendChild(new El('BUTTON','inert',350));
const explicit=doc.body.appendChild(new El('DIV','old-explicit',460));explicit.dataset.protoHotspot='true';
const elements=[old,changed,group,check,inert,explicit];
doc.createElement=tag=>new El(tag.toUpperCase());doc.querySelectorAll=()=>elements;
doc.elementFromPoint=(x,y)=>[...elements].reverse().find(el=>x>=el.rect.left&&x<=el.rect.right&&y>=el.rect.top&&y<=el.rect.bottom);
const ctx={window:win,document:doc,Element:El,EventTarget:Target,innerWidth:800,innerHeight:600,performance:{now:()=>0},getComputedStyle:()=>({display:'block',visibility:'visible',opacity:'1',overflowX:'visible',overflowY:'visible'}),setTimeout:()=>1,clearTimeout(){},requestAnimationFrame:()=>1,cancelAnimationFrame(){},MutationObserver:class{observe(){}disconnect(){}}};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
const api=win.ProtoHotspots;
const shown=()=>doc.documentElement.children.find(e=>e.className==='ph-layer')?.children.map(e=>e.dataset.hotspotFor).sort()||[];
'''


def run_case(case):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required')
    result = subprocess.run([node, '-e', HARNESS.replace('SOURCE', json.dumps(SOURCE)) + case], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_undeclared_scope_has_no_hints_even_for_explicit_markers():
    run_case("api.init();assert.equal(api.show(),0);assert.deepEqual(shown(),[]);")


def test_targets_do_not_include_other_working_controls_or_inert_targets():
    run_case("api.init({scope:{mode:'targets',protoIds:['changed','inert']}});assert.equal(api.show(),1);assert.deepEqual(shown(),['changed']);")


def test_container_scope_does_not_authorize_children_without_explicit_targets():
    run_case("api.init({scope:{mode:'targets',protoIds:['changed-group']}});assert.equal(api.show(),0);assert.deepEqual(shown(),[]);api.init({scope:{mode:'targets',protoIds:['group-check']}});assert.equal(api.show(),1);assert.deepEqual(shown(),['group-check']);")


def test_state_and_scope_changes_clear_previous_hints():
    run_case("let state='first';api.init({scope:()=>({mode:'targets',protoIds:[state==='first'?'changed':'old-export']})});api.show();assert.deepEqual(shown(),['changed']);state='second';api.hide();api.show();assert.deepEqual(shown(),['old-export']);api.init({scope:{mode:'targets',protoIds:[]}});assert.deepEqual(shown(),[]);assert.equal(api.show(),0);")


def test_full_page_hints_require_explicit_all_mode():
    run_case("api.init({scope:{mode:'all'}});api.show();assert.deepEqual(shown(),['changed','group-check','old-explicit','old-export']);api.init({scope:{mode:'targets',protoIds:['changed']}});api.show();assert.deepEqual(shown(),['changed']);")
