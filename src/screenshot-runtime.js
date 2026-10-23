/* 截图的便携运行时；编辑能力仅由本机工作台显式开启。 */
(() => {
    'use strict';
    const config = JSON.parse(document.getElementById('screenshot-config').textContent);
    const stage = document.getElementById('screenshot-stage'), image = document.getElementById('screenshot-image'), layer = document.getElementById('screenshot-regions');
    stage.style.width = config.width + 'px';
    let regions = structuredClone(config.regions), editing = false, drawing = false, selected = '', callback = null, gesture = null;
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    function paint() {
        layer.replaceChildren();
        for (const region of regions) {
            const node = document.createElement(region.targetFile ? 'a' : 'button');
            if (region.targetFile) node.href = region.targetFile; else node.type = 'button';
            node.className = 'screenshot-region'; node.dataset.regionId = region.id;
            node.dataset.protoId = 'screenshot-region-' + region.id; node.dataset.protoHotspot = 'true';
            node.setAttribute('aria-label', region.label);
            Object.assign(node.style, {left:region.x*100+'%', top:region.y*100+'%', width:region.width*100+'%', height:region.height*100+'%'});
            if (editing) {
                node.dataset.editor = '';
                if (selected === region.id) {
                    node.dataset.selected = '';
                    for (const corner of ['nw','ne','sw','se']) {
                        const handle = document.createElement('span'); handle.dataset.prototypeOwned = ''; handle.dataset.corner = corner; handle.className = 'screenshot-handle'; node.append(handle);
                    }
                }
            }
            layer.append(node);
        }
    }
    function point(e) {const r=image.getBoundingClientRect();return {x:clamp((e.clientX-r.left)/r.width,0,1), y:clamp((e.clientY-r.top)/r.height,0,1)};}
    function notify(type) {callback?.({type, regions:structuredClone(regions), selected});}
    function end(cancel = false) {
        if (!gesture) return;
        const g = gesture; gesture = null; g.rubber?.remove();
        try {stage.releasePointerCapture(g.pointerId);} catch (_) {}
        if (cancel) {regions=g.before;paint();return;}
        if (g.kind==='draw') {
            const p=g.last || g.start, r=image.getBoundingClientRect();
            if (Math.abs(p.x-g.start.x)*r.width<8 || Math.abs(p.y-g.start.y)*r.height<8) return;
            const region={id:'r-'+crypto.randomUUID(),label:'热区 '+(regions.length+1),x:Math.min(p.x,g.start.x),y:Math.min(p.y,g.start.y),width:Math.abs(p.x-g.start.x),height:Math.abs(p.y-g.start.y),targetPageId:'',targetFile:''};
            regions.push(region);selected=region.id;drawing=false;document.documentElement.removeAttribute('data-screenshot-draw');
        }
        paint();notify('change');
    }
    stage.addEventListener('pointerdown', e => {
        if (!editing || e.button!==0) return;
        const node=e.target.closest('[data-region-id]');
        if (!drawing && !node) return;
        e.preventDefault();e.stopImmediatePropagation();
        const p=point(e), before=structuredClone(regions);
        if (drawing) {
            const rubber=document.createElement('div');rubber.className='screenshot-rubber';rubber.dataset.prototypeOwned='';stage.append(rubber);
            gesture={kind:'draw',start:p,last:p,rubber,before,pointerId:e.pointerId};
        } else {
            selected=node.dataset.regionId;const region=regions.find(r=>r.id===selected);
            gesture={kind:e.target.dataset.corner || 'move',start:p,original:structuredClone(region),before,pointerId:e.pointerId};paint();notify('select');
        }
        stage.setPointerCapture(e.pointerId);
    }, true);
    stage.addEventListener('pointermove', e => {
        if (!gesture) return;
        e.preventDefault();const g=gesture,p=point(e);g.last=p;
        if (g.kind==='draw') {Object.assign(g.rubber.style,{left:Math.min(p.x,g.start.x)*100+'%',top:Math.min(p.y,g.start.y)*100+'%',width:Math.abs(p.x-g.start.x)*100+'%',height:Math.abs(p.y-g.start.y)*100+'%'});return;}
        const r=regions.find(r=>r.id===selected),o=g.original,dx=p.x-g.start.x,dy=p.y-g.start.y;
        if (g.kind==='move') {r.x=clamp(o.x+dx,0,1-o.width);r.y=clamp(o.y+dy,0,1-o.height);}
        else {
            const minX=8/image.getBoundingClientRect().width,minY=8/image.getBoundingClientRect().height;
            const left=g.kind.includes('w')?clamp(o.x+dx,0,o.x+o.width-minX):o.x;
            const top=g.kind.includes('n')?clamp(o.y+dy,0,o.y+o.height-minY):o.y;
            const right=g.kind.includes('e')?clamp(o.x+o.width+dx,o.x+minX,1):o.x+o.width;
            const bottom=g.kind.includes('s')?clamp(o.y+o.height+dy,o.y+minY,1):o.y+o.height;
            Object.assign(r,{x:left,y:top,width:right-left,height:bottom-top});
        }
        paint();
    });
    stage.addEventListener('pointerup',()=>end());stage.addEventListener('pointercancel',()=>end(true));
    stage.addEventListener('click', e => {
        if(editing){e.preventDefault();e.stopImmediatePropagation();return;}
        const region=regions.find(r=>r.id===e.target.closest('[data-region-id]')?.dataset.regionId);
        if(region?.targetFile && region.targetPageId && !e.ctrlKey && !e.metaKey && !e.shiftKey && window.parent!==window && ['workbench','review'].includes(document.documentElement.dataset.protoHost)) {
            e.preventDefault();window.parent.postMessage({__protoScreenshot:1,type:'navigate',pageId:region.targetPageId},'*');
        }
    },true);
    stage.addEventListener('keydown', e => {
        if(!editing || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
        const id=e.target.closest('[data-region-id]')?.dataset.regionId,region=regions.find(r=>r.id===id);if(!region)return;
        e.preventDefault();const step=(e.shiftKey?10:1),bounds=image.getBoundingClientRect();selected=id;
        if(e.key==='ArrowLeft')region.x=clamp(region.x-step/bounds.width,0,1-region.width);
        if(e.key==='ArrowRight')region.x=clamp(region.x+step/bounds.width,0,1-region.width);
        if(e.key==='ArrowUp')region.y=clamp(region.y-step/bounds.height,0,1-region.height);
        if(e.key==='ArrowDown')region.y=clamp(region.y+step/bounds.height,0,1-region.height);
        paint();notify('change');[...layer.children].find(n=>n.dataset.regionId===id)?.focus();
    });
    document.addEventListener('keydown',e=>{if(editing&&e.key==='Escape'){end(true);drawing=false;document.documentElement.removeAttribute('data-screenshot-draw');notify('cancel');}});
    window.ProtoScreenshot={
        image, get regions(){return structuredClone(regions);},
        edit(value,onchange){end(true);editing=!!value;drawing=false;callback=onchange || null;document.documentElement.toggleAttribute('data-screenshot-edit',editing);document.documentElement.removeAttribute('data-screenshot-draw');paint();},
        draw(){drawing=true;document.documentElement.setAttribute('data-screenshot-draw','');},
        select(id){selected=id;paint();const node=[...layer.children].find(n=>n.dataset.regionId===id);node?.scrollIntoView({block:'nearest'});},
        set(next){regions=structuredClone(next);paint();},
        hint(){layer.querySelectorAll('.screenshot-region').forEach(node=>node.animate([{outline:'2px solid #2563eb',background:'#2563eb30'},{outline:'2px solid transparent',background:'transparent'}],{duration:1500}));}
    };
    paint();
})();
