"""实际发布脚本：嵌套滚动、合帧重排与裁切后的序号可见性。"""
import json
import shutil
import subprocess
from pathlib import Path


def test_published_pins_follow_nested_scroll_without_false_stale():
    source = (Path(__file__).resolve().parents[1] / 'src' / 'review-pins.js').read_text(encoding='utf-8')
    script = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const listeners={},frames=[],syncs=[];let y=200,visible=true;
class Element{
 constructor(){this.style={setProperty(){}};this.dataset={};this.children=[];this.classList={add(){},remove(){},toggle(){}};}
 appendChild(n){this.children.push(n)} replaceChildren(){this.children=[]} setAttribute(){} querySelectorAll(){return []} querySelector(){return null}
}
const html=new Element(),head=new Element();html.dataset.protoState='default';html.outerHTML='<html></html>';
const note={id:'one',stateId:'default',number:1,displayNumber:1};
const R={notes:[note],onSync:(order,state,stale)=>syncs.push(stale)};
const context={console,document:{documentElement:html,head,createElement:()=>new Element(),addEventListener:(name,fn)=>listeners['doc:'+name]=fn},
 scrollX:0,scrollY:0,innerWidth:800,innerHeight:600,CSS:{escape:s=>s},setInterval(){},requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},
 ProtoAnchors:{point:()=>({point:{x:100,y,visible}})},ProtoOrder:{project:notes=>notes},__REVIEW__:R,
 addEventListener:(name,fn)=>listeners[name]=fn};context.window=context;
vm.createContext(context);vm.runInContext(SOURCE,context);
const layer=html.children[0];assert.equal(layer.children[0].style.top,'200px');
y=120;listeners.scroll({target:{}});listeners.scroll({target:{}});
assert.equal(frames.length,1);frames.shift()();assert.equal(layer.children[0].style.top,'120px');
visible=false;listeners.scroll({target:{}});frames.shift()();assert.equal(layer.children.length,0);assert.deepEqual(Array.from(syncs.at(-1)),[]);
visible=true;y=240;listeners.scroll({target:{}});frames.shift()();assert.equal(layer.children[0].style.top,'240px');
context.innerWidth=900;y=180;listeners.resize();frames.shift()();assert.equal(layer.children[0].style.top,'180px');
'''.replace('SOURCE', json.dumps(source))
    result = subprocess.run([shutil.which('node') or r'D:\software\nodejs\node.exe', '-'], input=script, text=True, capture_output=True, timeout=20, encoding='utf-8')
    assert result.returncode == 0, result.stderr
