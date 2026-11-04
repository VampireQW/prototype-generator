/* 更新说明的位置定位；复用锚点与展开，不生成序号或改写 PRD。 */
(() => {
    'use strict';
    let overlay=null, stop=null, generation=0;
    async function locate(target, notes=[]) {
        const token=++generation;
        const A=window.ProtoAnchors;
        if (!A || !target || target.deleted) return {ok:false,message:target?.deleted?'该内容已删除，请查看变更详情':'当前页面尚未准备好'};
        try {
            if (target.stateId) await A.enterState(target.stateId);
            const note=target.noteId && notes.find(n=>n.id===target.noteId);
            const anchor=note?.anchor || target.anchor;
            if (!anchor) return {ok:true,level:'page',message:'已打开对应页面'};
            let element;
            if (anchor.textRule) {
                const canonical=value=>JSON.stringify(value && typeof value==='object' ? Array.isArray(value)?value.map(v=>JSON.parse(canonical(v))):Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(canonical(value[k]))])):value);
                const rules=JSON.parse(document.getElementById('proto-text-edits-data')?.textContent || '[]');
                const rule=rules.find(r=>canonical(r.binding)===anchor.textRule);
                if(rule)element=window.ProtoTextRuntime?.locate(document,rule.binding);
            } else {
                element=A.resolve(anchor)?.element;
                if (!element || A.hidden(element)) element=await A.revealAndWait(anchor);
            }
            if(token!==generation)return {ok:false,cancelled:true};
            if (!element || A.hidden(element)) return {ok:false,message:'目标暂时无法定位，已打开所属页面'};
            element.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
            if (stop) stop();
            overlay=document.createElement('div'); overlay.setAttribute('data-prototype-owned','');
            Object.assign(overlay.style,{position:'fixed',pointerEvents:'none',zIndex:'2147483630',border:'3px solid #2563eb',
                borderRadius:'5px',boxShadow:'0 0 0 4px #2563eb25',boxSizing:'border-box'});
            document.documentElement.append(overlay);
            const paint=()=>{const r=element.getBoundingClientRect(); Object.assign(overlay.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});};
            paint(); window.addEventListener('scroll',paint,true); window.addEventListener('resize',paint);
            const observer=new ResizeObserver(paint); observer.observe(element);
            let timer;
            stop=()=>{clearTimeout(timer); observer.disconnect();window.removeEventListener('scroll',paint,true);window.removeEventListener('resize',paint);overlay?.remove();overlay=null;stop=null;};
            timer=setTimeout(stop,3000);
            return {ok:true,level:'element',message:'已定位更新位置'};
        } catch (_) { return {ok:false,message:'目标已变化，已打开所属页面'}; }
    }
    window.ProtoChangeLocator={locate};
})();
