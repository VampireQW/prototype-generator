"""页面列表宽度：范围、存储与拖动取消的行为回归。"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_sidebar_resize_interactions():
    node = shutil.which('node')
    if not node:
        pytest.skip('需要 Node.js')
    source = (Path(__file__).resolve().parents[1] / 'src/sidebar-resize.js').read_text(encoding='utf-8')
    script = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
function element(){return {listeners:{},attrs:{},hidden:false,
    classList:{values:new Set(),add(v){this.values.add(v);},remove(v){this.values.delete(v);}},
    addEventListener(k,f){this.listeners[k]=f;},setAttribute(k,v){this.attrs[k]=String(v);},
    setPointerCapture(id){this.capture=id;},hasPointerCapture(id){return this.capture===id;},
    releasePointerCapture(){this.capture=null;},focus(){},remove(){this.removed=true;},
    fire(type,extra={}){this.listeners[type]?.({button:0,pointerId:1,clientX:100,preventDefault(){},stopImmediatePropagation(){},...extra});}};}
function setup(saved,blocked=false){
    const handle=element(),body=element(),events={},values={width:saved};let width,open=true,max=480,overlay;
    body.append=el=>overlay=el;
    const context={window:{addEventListener(type,fn){events[type]=fn;}},document:{body,createElement(){return element();}},
        localStorage:{getItem(k){if(blocked)throw Error('blocked');return values[k]??null;},setItem(k,v){if(blocked)throw Error('blocked');values[k]=v;}}};
    vm.runInNewContext(SOURCE,context);
    const control=context.window.ProtoSidebarResize.attach(handle,{storageKey:'width',isOpen:()=>open,getMax:()=>max,setWidth:value=>width=value});
    return {handle,body,values,control,get width(){return width;},get overlay(){return overlay;},
        close(){open=false;control.refresh();},open(){open=true;control.refresh();},
        max(value){max=value;events.resize();},event(type,extra={}){events[type]?.({key:'Escape',preventDefault(){},stopImmediatePropagation(){},...extra});}};
}
const page=setup('300');assert.equal(page.width,300);
page.handle.fire('pointerdown');page.handle.fire('pointermove',{clientX:250});assert.equal(page.width,450);
assert.ok(page.body.classList.values.has('page-nav-resizing'));
page.handle.fire('pointerup');assert.equal(page.values.width,'450');assert.ok(page.overlay.removed);
assert.equal(page.body.classList.values.has('page-nav-resizing'),false);
page.close();assert.equal(page.handle.hidden,true);page.open();assert.equal(page.width,450);
page.max(330);assert.equal(page.width,330);page.max(480);assert.equal(page.width,450);
page.handle.fire('pointerdown');page.handle.fire('pointermove',{clientX:0});assert.equal(page.width,350);
page.event('keydown');assert.equal(page.width,450);assert.equal(page.values.width,'450');
for(const cancel of ['pointercancel','lostpointercapture']){
    page.handle.fire('pointerdown');page.handle.fire('pointermove',{clientX:110});page.handle.fire(cancel);
    assert.equal(page.width,450);assert.ok(page.overlay.removed);
}
page.handle.fire('keydown',{key:'End'});assert.equal(page.width,480);
page.handle.fire('keydown',{key:'Home'});assert.equal(page.width,200);
page.handle.fire('keydown',{key:'ArrowRight',shiftKey:true});assert.equal(page.width,240);
page.handle.fire('dblclick');assert.equal(page.width,256);assert.equal(page.values.width,'256');
const local=setup(null,true);local.handle.fire('keydown',{key:'ArrowRight'});assert.equal(local.width,266);
local.handle.fire('pointerdown',{button:2});assert.equal(local.overlay,undefined);
assert.equal(local.handle.attrs['aria-valuenow'],'266');
'''.replace('SOURCE', json.dumps(source))
    result = subprocess.run([node, '-'], input=script, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
