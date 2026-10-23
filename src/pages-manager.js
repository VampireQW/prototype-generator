/* Pages 发布管理与发布菜单快捷入口；凭据只由本地服务持有。 */
(() => {
    'use strict';
    const formatBytes = value => {
        if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—';
        const units = ['B', 'KB', 'MB', 'GB']; let index = 0;
        while (value >= 1000 && index < units.length-1) { value /= 1000; index++; }
        return new Intl.NumberFormat('zh-CN', {maximumFractionDigits: index ? 1 : 0}).format(value)+' '+units[index];
    };
    const projectRows = (data, query = '', sort = 'size') => {
        const word = query.trim().toLocaleLowerCase();
        return (data?.projects || []).filter(row => `${row.name} ${row.id}`.toLocaleLowerCase().includes(word)).slice().sort((a,b) =>
            sort === 'name' ? a.name.localeCompare(b.name,'zh-CN') : sort === 'date' ? (Date.parse(b.publishedAt)||0)-(Date.parse(a.publishedAt)||0) :
            (b.bytes ?? -1)-(a.bytes ?? -1) || a.name.localeCompare(b.name,'zh-CN'));
    };
    function createController(config) {
        const state = {data:null, busy:false, error:'', pendingId:''};
        const emit = () => config.onChange?.({...state});
        async function load(refresh = false) {
            if (state.busy) return;
            state.busy=true; state.error=''; emit();
            try { state.data=await config.request('overview',null,refresh); }
            catch(error) { state.error=error.message || '读取发布信息失败'; }
            finally { state.busy=false; emit(); }
        }
        async function remove(row) {
            if (state.busy || !state.data) return;
            const payload={projectId:row.id,repository:state.data.repository,expectedHead:state.data.head};
            state.busy=true;state.pendingId=row.id;state.error='';emit();
            try {
                if (!await config.confirm(row,state.data)) return;
                const result=await config.request('unpublish',payload);
                state.data=result.overview || await config.request('overview',null,true);
                config.onRemoved?.(result);
            } catch(error) { state.error=error.message || '取消发布失败，请刷新检查后重试'; }
            finally { state.busy=false;state.pendingId='';emit(); }
        }
        return {load,remove};
    }
    const safeUrl = value => {
        try { const url=new URL(value,location.href);return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.href : ''; }
        catch(_) { return ''; }
    };
    async function request(action,payload,refresh=false) {
        const response=await fetch(action === 'overview' ? '/api/pages/overview'+(refresh?'?refresh=1':'') : '/api/pages/unpublish',
            action === 'overview' ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const result=await response.json();
        if (!response.ok || !result.ok) throw Error(result.error || '发布信息暂不可用，请稍后重试');
        return result;
    }
    const hosts=new Set();let summaryValue=null,summaryBusy=false,summaryTime=0;
    function node(tag,cls,text) { const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el; }
    function anchor(text,url,cls='') { const el=node('a',cls,text);const href=safeUrl(url);if(href)el.href=href;else el.hidden=true;el.target='_blank';el.rel='noopener noreferrer';return el; }
    function renderSummary(host) {
        const link=host.querySelector('[data-pages-overview]');
        const url=safeUrl(summaryValue?.overviewUrl || '');link.hidden=!summaryValue?.overviewUrl || !url;if(!link.hidden)link.href=url;
    }
    async function refreshSummaries(force=true) {
        if(summaryBusy || !hosts.size)return;
        if(!force && summaryValue && Date.now()-summaryTime<120000){hosts.forEach(renderSummary);return;}
        summaryBusy=true;hosts.forEach(renderSummary);
        try {summaryValue=await request('overview',null,force);summaryTime=Date.now();}
        catch(_){summaryValue=null;}
        finally{summaryBusy=false;hosts.forEach(renderSummary);}
    }
    function mountSummaries() {
        const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))void refreshSummaries(false);});
        document.querySelectorAll('[data-pages-summary]').forEach(host=>{
            const links=node('div','pages-summary-links'),manager=anchor('发布管理 ↗','/src/publish.html'),overview=anchor('Pages 总览 ↗','');overview.dataset.pagesOverview='';overview.hidden=true;
            links.append(manager,overview);host.replaceChildren(links);hosts.add(host);renderSummary(host);observer.observe(host);
        });
    }
    function publicationChanged() {
        summaryTime=0;void refreshSummaries();
        try{localStorage.setItem('prototype-pages-updated',String(Date.now()));}catch(_){}
        window.dispatchEvent(new CustomEvent('pages-publication-changed'));
    }
    function initPage() {
        const root=document.getElementById('pagesManager');if(!root)return;
        const $=id=>document.getElementById(id);let current=null;
        const date=value=>{const time=new Date(value);return Number.isNaN(time.getTime())?'时间未记录':time.toLocaleString('zh-CN',{hour12:false});};
        const dialog=$('pagesConfirm');
        const controller=createController({request,onChange:render,onRemoved:()=>{publicationChanged();$('pagesMessage').textContent='已提交取消发布，Pages 重新部署后生效。本地文件与 PRD 已保留。';},
            confirm:(row,data)=>new Promise(resolve=>{
                $('pagesConfirmName').textContent=row.name;
                $('pagesConfirmPath').textContent=data.repository+'/'+data.sourcePath.replace(/^\//,'')+(data.sourcePath==='/'?'':'/')+'projects/'+row.id+'/';
                const finish=answer=>{dialog.close();dialog.oncancel=null;$('pagesConfirmCancel').onclick=null;$('pagesConfirmAccept').onclick=null;resolve(answer);};
                $('pagesConfirmCancel').onclick=()=>finish(false);$('pagesConfirmAccept').onclick=()=>finish(true);
                dialog.oncancel=event=>{event.preventDefault();finish(false);};dialog.showModal();$('pagesConfirmCancel').focus();
            })});
        function render(state) {
            current=state;$('pagesRefresh').disabled=state.busy;$('pagesSearch').disabled=$('pagesSort').disabled=!state.data;
            $('pagesError').textContent=state.error;$('pagesError').hidden=!state.error;
            $('pagesList').setAttribute('aria-busy',String(state.busy));
            if(!state.data){$('pagesCount').textContent=state.busy?'正在读取远端项目…':'未读取到发布信息';$('pagesList').replaceChildren(node('p','pages-empty',state.busy?'正在读取发布信息…':'无法读取远端项目，请检查配置后点击刷新远端。'));return;}
            const data=state.data,usage=data.usage;
            $('pagesRepo').textContent=data.repository;$('pagesRepo').href=safeUrl(data.repositoryUrl);
            $('pagesSource').textContent=`${data.branch} · ${data.sourcePath}`;
            $('pagesUsed').textContent=formatBytes(usage.usedBytes);$('pagesRemaining').textContent=formatBytes(usage.remainingBytes);$('pagesTotal').textContent=data.projects.length;
            $('pagesUsageReason').textContent=usage.reason || '按当前发布源文件估算；参考上限 1 GB，实际构建产物可能不同。';
            $('pagesChecked').textContent='最近统计：'+date(data.checkedAt);
            const total=usage.usedBytes == null?0:Math.min(100,usage.usedBytes/usage.limitBytes*100);$('pagesUsageBar').style.width=total+'%';$('pagesUsageTrack').hidden=usage.usedBytes==null;
            $('pagesUsageTrack').setAttribute('aria-label',`估算使用 ${total.toFixed(1)}%`);
            const url=safeUrl(data.overviewUrl);$('pagesOverview').hidden=!data.overviewUrl || !url;if(url)$('pagesOverview').href=url;
            const rows=projectRows(data,$('pagesSearch').value,$('pagesSort').value);$('pagesCount').textContent=`${rows.length} 个远端项目`;
            const list=$('pagesList');list.replaceChildren();
            if(!rows.length){list.append(node('p','pages-empty',data.projects.length?'没有匹配的项目':'当前仓库没有可管理的原型项目'));return;}
            for(const row of rows){
                const article=node('article','pages-project'),info=node('div','pages-project-info');
                info.append(node('h2','',row.name));const meta=node('div','pages-project-meta');
                if(!row.listed)meta.append(node('span','pages-tag','未列入总览'));else if(!row.hasFiles)meta.append(node('span','pages-tag','待清理记录'));
                else if(row.mode)meta.append(node('span','pages-tag',/review|dev/.test(row.mode)?'研发版':'纯净版'));
                meta.append(node('span','',date(row.publishedAt)));info.append(meta,node('p','pages-project-path',row.id));
                const size=node('div','pages-project-size',formatBytes(row.bytes)),actions=node('div','pages-project-actions');
                actions.append(anchor('打开原型 ↗',row.url),anchor('查看目录 ↗',row.directoryUrl));
                const remove=node('button','pages-remove',state.pendingId===row.id?'处理中…':'取消发布');remove.type='button';remove.disabled=state.busy || !row.canUnpublish;
                remove.setAttribute('aria-label','取消发布 '+row.name);remove.onclick=()=>controller.remove(row);actions.append(remove);article.append(info,size,actions);list.append(article);
            }
        }
        $('pagesRefresh').onclick=()=>{$('pagesMessage').textContent='';void controller.load(true);};
        $('pagesSearch').oninput=$('pagesSort').onchange=()=>{if(current)render(current);};
        window.addEventListener('storage',event=>{if(event.key==='prototype-pages-updated')void controller.load(true);});
        void controller.load();
    }
    window.PagesManager={formatBytes,projectRows,createController,refreshSummaries,publicationChanged};
    document.addEventListener('DOMContentLoaded',()=>{mountSummaries();initPage();});
})();
