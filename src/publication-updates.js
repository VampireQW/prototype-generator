/* 发布说明、本地草稿与静态站更新检测。只读取同站点版本文件。 */
(function(global){
    'use strict';
    const KINDS={text:'文案',annotation:'标注',document:'页面需求','annotation-position':'标注位置',page:'页面配置',
        'page-added':'新增页面','page-removed':'删除页面','element-added':'新增内容','element-removed':'删除内容',
        style:'样式',logic:'交互代码',asset:'图片 / 资源',resource:'公共资源',layout:'结构',runtime:'评审组件',publication:'发布版本'};
    function validRelease(value) {
        return !!value && value.schemaVersion===1 && /^rel-[a-f0-9]{16}$/.test(value.releaseId || '') &&
            /^[a-f0-9]{64}$/.test(value.contentVersion || '') && Number.isSafeInteger(value.sequence) && value.sequence>0 &&
            ['review','pure'].includes(value.mode);
    }
    function safeRelative(value) {
        return typeof value==='string' && value.length<300 && !value.includes('\\') && !/[?#:%]/.test(value) &&
            value.split('/').every(p=>p && p!=='.' && p!=='..');
    }
    function createWatcher(options) {
        const current=options.current, fetcher=options.fetch || global.fetch.bind(global);
        const visible=options.visible || (()=>!global.document?.hidden);
        const schedule=options.setTimeout || global.setTimeout.bind(global), cancel=options.clearTimeout || global.clearTimeout.bind(global);
        let timer=null, stopped=true, inFlight=null, delay=30000, seen=current?.sequence || 0;
        const protocol=options.protocol || global.location?.protocol;
        function next(){ cancel(timer); if(!stopped && visible()) timer=schedule(check,delay); }
        function check(){
            if(stopped || !visible() || !validRelease(current) || !['http:','https:'].includes(protocol)) return Promise.resolve();
            if(inFlight) return inFlight;
            cancel(timer);
            const abort=global.AbortController ? new global.AbortController():null;
            const timeout=abort && schedule(()=>abort.abort(),5000);
            inFlight=(async()=>{
                try {
                    const url=new URL('prototype-release.json',options.baseUrl || global.location.href);
                    url.searchParams.set('_check',String(Date.now()));
                    const response=await fetcher(url.href,{cache:'no-store',credentials:'omit',signal:abort?.signal});
                    if(!response.ok) throw Error('版本暂不可读');
                    const latest=await response.json();
                    if(!validRelease(latest) || (current.projectId && latest.projectId!==current.projectId)) return;
                    delay=30000;
                    if(latest.sequence>seen){
                        seen=latest.sequence;
                        if(latest.contentVersion!==current.contentVersion) options.onUpdate(latest);
                    }
                } catch(_){ delay=Math.min(delay*2,300000); }
                finally { if(timeout)cancel(timeout); inFlight=null;next(); }
            })();
            return inFlight;
        }
        const resume=()=>{if(visible())check();else cancel(timer);};
        return {start(){if(!stopped)return;stopped=false;global.addEventListener?.('focus',resume);global.document?.addEventListener('visibilitychange',resume);check();},
            check,stop(){stopped=true;cancel(timer);global.removeEventListener?.('focus',resume);global.document?.removeEventListener('visibilitychange',resume);}};
    }
    function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
    function notify(text){
        let n=document.querySelector('.pu-toast');if(!n){n=node('div',undefined,'pu-toast');n.setAttribute('role','status');document.body.append(n);}
        n.textContent=text;n.hidden=false;clearTimeout(n._timer);n._timer=setTimeout(()=>n.hidden=true,4500);
    }
    function targetHash(target){return new URLSearchParams({p:target.pageId || '',s:target.stateId || 'default',changeTarget:JSON.stringify(target)}).toString();}
    function readTarget(hash){try{const raw=new URLSearchParams(hash.slice(1)).get('changeTarget');if(!raw || raw.length>6000)return null;const t=JSON.parse(raw);
        if(!t || typeof t.pageId!=='string' || t.pageId.length>256 || typeof t.stateId!=='string' || t.stateId.length>256)return null;
        const out={pageId:t.pageId,stateId:t.stateId};for(const k of ['noteId','documentId'])if(typeof t[k]==='string' && t[k].length<256)out[k]=t[k];
        if(t.anchor && typeof t.anchor==='object'){out.anchor={};for(const k of ['selector','protoId','tag','text','parentText','textRule'])if(typeof t.anchor[k]==='string' && t.anchor[k].length<3000)out.anchor[k]=t.anchor[k];}
        return out;
    }catch(_){return null;}}
    let currentDialog=null;
    const previewCache=new Map();
    function previewLocal(projectId,force=false){
        const hit=previewCache.get(projectId);if(!force && hit && Date.now()-hit.time<5000)return hit.promise;
        const promise=fetch('/api/ext/release-preview?projectId='+encodeURIComponent(projectId)).then(r=>r.json());
        previewCache.set(projectId,{promise,time:Date.now()});return promise;
    }
    async function summarizeLocal(button,projectId,force=false){
        if(!button)return;button.dataset.project=projectId;button.textContent='更新说明 · 正在对比…';
        try{const result=await previewLocal(projectId,force);if(button.dataset.project!==projectId)return;
            const s=result.release?.summary;button.textContent=result.ok?`更新说明 · ${s?.pages || 0} 页 / ${s?.changes || 0} 项`:'更新说明 · 点击重试';
        }catch(_){if(button.dataset.project===projectId)button.textContent='更新说明 · 点击重试';}
    }
    function dialog(title){
        currentDialog?.close();currentDialog?.remove();
        const d=node('dialog',undefined,'pu-dialog');currentDialog=d;
        const head=node('div',undefined,'pu-dialog-head');const heading=node('h2',title);heading.id='pu-title';d.setAttribute('aria-labelledby','pu-title');head.append(heading);
        const close=node('button','关闭','pu-btn');close.type='button';close.onclick=()=>d.close();head.append(close);
        const body=node('div',undefined,'pu-dialog-body');d.append(head,body);document.body.append(d);
        d.addEventListener('close',()=>{d._flush?.();d.remove();if(currentDialog===d)currentDialog=null;},{once:true});
        d.showModal();return {d,body};
    }
    function showItems(host,payload,options={}){
        host.replaceChildren();
        const items=Array.isArray(payload?.items)?payload.items:[];
        const status=node('p',undefined,'pu-muted');host.append(status);
        status.textContent=payload?.baselineStatus==='unavailable'?'首次建立版本基线，历史差异暂不可完整比较':
            payload?.baselineStatus==='initial'?'首次发布摘要':items.length?`${new Set(items.map(i=>i.target?.pageId)).size} 个页面 · ${items.length} 项更新`:'与上次版本相比没有内容变化';
        if(payload?.publishedAt)host.append(node('p',payload.publishedAt,'pu-muted'));
        if(!items.length)return;
        const wrap=node('div',undefined,'pu-table-wrap'), table=node('table',undefined,'pu-table');
        const tr=node('tr');for(const label of ['页面 / 状态','类型','更新内容','操作'])tr.append(node('th',label));
        const thead=node('thead');thead.append(tr);table.append(thead);
        const tbody=node('tbody');table.append(tbody);wrap.append(table);host.append(wrap);
        for(const item of items){
            const row=node('tr'), page=node('td'), kind=node('td'), description=node('td'), action=node('td');
            page.append(node('strong',item.pageTitle || '公共资源'),node('div',item.stateTitle || '默认','pu-muted'));
            if(item.affectedPages?.length>1)page.append(node('small',(item.affectedPageTitles || item.affectedPages).join('、'),'pu-muted'));
            kind.append(node('span',KINDS[item.kind] || '内容','pu-kind'));
            if(options.edit){
                const input=node('textarea');input.value=item.description || '';input.rows=2;input.maxLength=1000;
                input.setAttribute('aria-label','修改更新说明：'+(item.pageTitle || '公共资源'));
                input.oninput=()=>{item.description=input.value;options.onEdit?.(items);};description.append(input);
            }else description.append(node('div',item.description || '内容有更新'));
            if(item.before || item.after){
                const details=node('details');details.append(node('summary',item.target?.deleted?'查看删除内容':'前后内容'));
                if(item.before)details.append(node('p','原：'+item.before,'pu-before'));
                if(item.after)details.append(node('p','新：'+item.after,'pu-after'));description.append(details);
            }
            const button=node('button',item.target?.deleted?'查看详情':options.refresh?'刷新并定位':'定位','pu-btn');button.type='button';
            button.onclick=()=>{
                if(item.target?.deleted){description.querySelector('details')?.setAttribute('open','');return;}
                if(!item.target?.pageId){notify('此项为公共更新，请查看涉及页面');return;}
                options.close?.();Promise.resolve(options.onLocate?.(item.target)).catch(e=>notify(e.message || '定位失败'));
            };
            action.append(button);row.append(page,kind,description,action);tbody.append(row);
        }
    }
    async function openLocal({projectId,onLocate}){
        const {d,body}=dialog('更新说明');body.append(node('p','正在对比上次发布…','pu-muted'));
        let result,saveTimer=null,pending=null,saving=false;
        const status=node('p','修改说明自动保存','pu-muted');
        async function save(){
            clearTimeout(saveTimer);if(saving || !pending)return;
            saving=true;const descriptions=pending;pending=null;
            try{
                const response=await fetch('/api/ext/release-notes',{method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({projectId,branch:result.target.branch,sourceVersion:result.sourceVersion,descriptions})});
                const data=await response.json();if(!data.ok)throw Error(data.error || '说明保存失败');status.textContent='说明已保存';
            }catch(e){status.textContent=e.message;notify(e.message);}finally{saving=false;if(pending)save();}
        }
        d._flush=()=>{clearTimeout(saveTimer);save();};
        try{
            result=await previewLocal(projectId,true);
            if(!result.ok)throw Error(result.error || '无法生成更新说明');if(!d.open)return;
            const content=node('div');showItems(content,result.changes,{edit:true,close:()=>d.close(),onLocate:target=>{
                if(onLocate)return onLocate(target);
                const url=new URL('/src/viewer.html',location.href);url.searchParams.set('ext',projectId);url.searchParams.set('page',target.pageId);url.searchParams.set('state',target.stateId || 'default');url.searchParams.set('mode','annotate');url.hash=targetHash(target);global.open(url.href,'_blank','noopener');
            },onEdit:items=>{pending=Object.fromEntries(items.map(i=>[i.id,i.description]));status.textContent='正在保存…';clearTimeout(saveTimer);saveTimer=setTimeout(save,600);}});
            body.replaceChildren(content,status);
        }catch(e){body.replaceChildren(node('p',e.message,'pu-error'));}
    }
    function mountPublished({data,onLocate}){
        const header=document.querySelector('header.topbar');if(!header)return;
        let latest=null;
        const banner=node('section',undefined,'pu-update-banner');banner.hidden=true;banner.setAttribute('aria-label','页面更新通知');banner.setAttribute('role','status');
        const label=node('div'),title=node('strong','页面有更新，请刷新查看最新版本。'),detail=node('div',undefined,'pu-banner-detail');label.append(title,detail);
        const controls=node('div',undefined,'pu-banner-actions');
        const refresh=node('button','刷新页面','pu-btn primary'),view=node('button','查看更新','pu-btn'),later=node('button','稍后','pu-btn');
        controls.append(refresh,view,later);banner.append(label,controls);header.after(banner);
        const badge=node('button','有更新','pu-btn pu-update-badge');badge.hidden=true;badge.onclick=()=>{badge.hidden=true;banner.hidden=false;};header.append(badge);
        function refreshTo(target){const url=new URL(location.href);url.searchParams.set('v',latest.contentVersion);if(target)url.hash=targetHash(target);location.replace(url.href);}
        refresh.onclick=()=>refreshTo();later.onclick=()=>{banner.hidden=true;badge.hidden=false;};
        async function show(latestOnly=false){
            const {d,body}=dialog(latestOnly?'最新更新说明':'更新说明');
            if(!latestOnly){showItems(body,data.changeLog || {items:[]},{close:()=>d.close(),onLocate});}
            else body.append(node('p','正在读取更新说明…','pu-muted'));
            let release=latestOnly?latest:data.release;
            if(!validRelease(release))return;
            if(release.mode==='pure'){body.replaceChildren(node('p','最新发布已切换为纯净版，请刷新后查看原型。'));return;}
            if(!latestOnly && ['http:','https:'].includes(location.protocol)){
                try{
                    const response=await fetch(new URL('prototype-release.json',location.href),{cache:'no-store',credentials:'omit'});
                    const remote=await response.json();
                    if(validRelease(remote) && remote.projectId===data.release.projectId && Array.isArray(remote.history))
                        release={...release,history:remote.history.filter(h=>h.sequence<=data.release.sequence)};
                }catch(_){/* 离线时保留随包携带的当前更新说明。 */}
            }
            const history=(Array.isArray(release.history)?release.history:[]).filter(h=>!latestOnly || h.sequence>data.release.sequence);
            const paths=[...history.map(h=>h.changesUrl),release.changesUrl].filter((v,i,a)=>v && a.indexOf(v)===i && safeRelative(v));
            if(!latestOnly){
                if(!paths.length)return;
                const more=node('button','查看保留的历史更新','pu-btn');body.append(more);more.onclick=()=>load();
            }else await load();
            async function load(){
                const output=node('div');let count=0;
                if(latestOnly && history.length && Math.min(...history.map(h=>h.sequence))>data.release.sequence+1)
                    output.append(node('p','当前页面落后较多，以下仅包含保留范围内的更新；更早变化已归档。','pu-muted'));
                for(const path of paths){
                    try{
                        const response=await fetch(new URL(path,location.href),{cache:'no-store',credentials:'omit'});if(!response.ok)continue;
                        const payload=await response.json();if(payload.schemaVersion!==1 || !Array.isArray(payload.items) || path!=='prototype-changes/'+payload.releaseId+'.json')continue;
                        const section=node('section',undefined,'pu-release-section');showItems(section,payload,{refresh:latestOnly,close:()=>d.close(),onLocate:latestOnly?refreshTo:onLocate});output.append(section);count++;
                    }catch(_){/* 部分历史可能已归档 */}
                }
                if(!d.open)return;
                if(count)body.replaceChildren(output);else if(latestOnly)body.replaceChildren(node('p','更新说明暂不可读，请稍后重试；可先刷新查看最新页面。'));
            }
        }
        const notes=node('button','更新说明','pu-btn');notes.onclick=()=>show();header.append(notes);view.onclick=()=>show(true);
        if(validRelease(data.release)){
            const watcher=createWatcher({current:data.release,onUpdate:value=>{latest=value;const s=value.summary || {};detail.textContent=`${value.publishedAt || ''} · 涉及 ${s.pages || 0} 个页面、${s.changes || 0} 项变化`;banner.hidden=false;badge.hidden=true;}});
            watcher.start();global.addEventListener('pagehide',()=>watcher.stop(),{once:true});
        }
        return {notify};
    }
    global.PublicationUpdates={createWatcher,validRelease,safeRelative,openLocal,summarizeLocal,mountPublished,notify,readTarget,targetHash};
})(typeof window!=='undefined'?window:globalThis);
