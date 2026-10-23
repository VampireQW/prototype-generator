/* 本地工作台添加页面入口、HTML 导入与截图热区编辑。 */
(() => {
    'use strict';
    const clone = value => structuredClone(value);
    const htmlType = path => /\.html?$/i.test(path);
    const resourceType = path => /\.(css|js|mjs|json|svg|png|jpe?g|webp|gif|ico|woff2?|ttf|otf|mp4|webm|ogg|mp3)$/i.test(path);
    function collectHtmlFiles(files, folder = false) {
        const records = [], seen = new Set();
        for (const file of files) {
            const parts = (folder ? file.webkitRelativePath : file.name).split('/');
            if (folder) parts.shift();
            if (!parts.length || parts.some(part => !part || part.startsWith('.') || ['node_modules','__pycache__','exports','dist','agent-skills'].includes(part.toLowerCase()))) continue;
            const path = parts.join('/');
            if (!htmlType(path) && !resourceType(path)) continue;
            if (seen.has(path.toLowerCase())) throw new Error('文件路径重复，请检查大小写');
            seen.add(path.toLowerCase()); records.push({path,file});
        }
        if (!records.some(record => htmlType(record.path))) throw new Error('请选择 HTML 文件或包含 HTML 的页面文件夹');
        return records;
    }
    function create(config) {
        const {frame} = config;
        let pageId='', draft=[], original=[], dirty=false, busy=false, active=false, selected='', drawing=false, host=null, dialog=null, menu=null;
        const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
        const button=(text,fn,cls='')=>{const b=el('button',cls,text);b.type='button';b.onclick=fn;b.disabled=busy;return b;};
        const runtime=()=>{try{return frame.contentWindow.ProtoScreenshot;}catch(_){return null;}};
        const current=()=>config.page()?.kind==='screenshot'?config.page():null;
        const notice=(message,tone='info')=>config.notice?.(message,tone);
        const portable=regions=>regions.map(region=>{
            const target=config.project().pages.find(p=>p.id===region.targetPageId&&!p.trashedAt);
            return {...region,targetFile:target?'../'+target.file.split('/').map(encodeURIComponent).join('/'):''};
        });
        function sync() {
            const page=current();
            if(page?.id!==pageId) {pageId=page?.id||'';draft=clone(page?.screenshot.regions||[]);original=clone(draft);dirty=false;selected='';drawing=false;}
            else if(!dirty&&!busy&&JSON.stringify(page?.screenshot.regions||[])!==JSON.stringify(original)) {draft=clone(page?.screenshot.regions||[]);original=clone(draft);}
        }
        function changed(regions) {
            draft=regions.map(({targetFile,...region})=>region);dirty=JSON.stringify(draft)!==JSON.stringify(original);runtime()?.set(portable(draft));
            updateStatus();
        }
        function update(id, patch) {changed(draft.map(region=>region.id===id?{...region,...patch}:region));}
        function updateStatus() {
            if(!host)return;
            const save=host.querySelector('[data-shot-save]'),cancel=host.querySelector('[data-shot-cancel]'),status=host.querySelector('[data-shot-status]');
            if(save)save.disabled=busy||!dirty;if(cancel)cancel.disabled=busy||!dirty;if(status)status.hidden=!dirty;
            for(const label of host.querySelectorAll('[data-shot-label]')){const region=draft.find(r=>r.id===label.dataset.shotLabel);if(region)label.textContent=region.label;}
        }
        function attach() {
            const api=runtime();if(!api)return;
            api.set(portable(draft));api.edit(active&&!busy,event=>{
                if(event.type==='change')changed(event.regions);
                selected=event.selected;
                if(event.type==='change'||event.type==='cancel')drawing=false;
                paint();
            });
        }
        function setActive(value) {
            sync();const next=!!value&&!!current();
            if(next!==active){active=next;drawing=false;if(next)config.prepare?.();attach();}
        }
        function canLeave() {
            if(busy){notice('正在保存截图，请稍候','warning');return false;}
            if(dirty){notice('热区有未保存修改，请先保存或放弃修改','warning');return false;}
            return true;
        }
        async function save() {
            if(!dirty||busy)return;busy=true;attach();paint();
            try {
                const result=await config.save('regions',{pageId,regions:clone(draft)});
                original=clone(result.page.screenshot.regions);draft=clone(original);dirty=false;attach();notice('热区已保存');
            } catch(error) {notice(error.message||'保存失败','warning');}
            finally{busy=false;attach();paint();}
        }
        function paint() {
            if(!host?.isConnected)return;
            sync();host.replaceChildren();
            const actions=el('div','ei-actions');
            const add=button(drawing?'取消绘制 · Esc':'＋ 添加热区',()=>{
                config.prepare?.();attach();drawing=!drawing;
                if(drawing)runtime()?.draw();else attach();paint();
            },'ei-pick-action');
            add.disabled=busy||draft.length>=200;
            actions.append(add,button('预览提示',()=>runtime()?.hint()),button('更换截图',()=>openDialog(true),'ps-shot-replace'));host.append(actions);
            host.append(el('p','ei-description',drawing?'在截图中拖动，框选一个操作控件。':'拖动画框添加热区；选中后可移动或拖动角点调整大小。'));
            if(!draft.length)host.append(el('div','ei-empty','暂无矩形热区'));
            for(const region of draft) {
                const row=el('div','ei-row ps-shot-row');row.dataset.selected=String(region.id===selected);
                const title=button(region.label,()=>{selected=region.id;runtime()?.select(selected);paint();},'ps-shot-label');
                title.dataset.shotLabel=region.id;
                const caption=el('span','ei-status',region.targetPageId?'跳转页面':'仅点击提示');
                if(region.targetPageId&&!config.project().pages.some(p=>p.id===region.targetPageId&&!p.trashedAt))caption.textContent='目标已移除 · 仅点击提示';
                const text=el('div','ei-row-text');text.append(title,caption);row.append(text,
                    button('编辑',()=>{selected=region.id;runtime()?.select(selected);paint();}),
                    button('删除',()=>{changed(draft.filter(r=>r.id!==region.id));if(selected===region.id)selected='';paint();},'ei-danger'));
                host.append(row);
                if(selected===region.id)renderFields(region);
            }
            const footer=el('div','ei-actions ei-footer');
            const saveButton=button(busy?'保存中…':'保存热区',save,'ei-primary');saveButton.disabled=busy||!dirty;
            const cancel=button('放弃修改',()=>{draft=clone(original);dirty=false;selected='';drawing=false;attach();paint();});cancel.disabled=busy||!dirty;
            saveButton.dataset.shotSave='';cancel.dataset.shotCancel='';const status=el('span','ei-description','有未保存修改');status.dataset.shotStatus='';status.hidden=!dirty;
            footer.append(saveButton,cancel,status);host.append(footer);
        }
        function renderFields(region) {
            const fields=el('div','ps-shot-fields');
            const label=el('label','','热区名称'),input=el('input');input.value=region.label;input.maxLength=120;input.disabled=busy;input.setAttribute('aria-label','热区名称');
            input.oninput=()=>{const text=input.value.trim();if(text)update(region.id,{label:text});};
            input.onchange=()=>{if(!input.value.trim())input.value=draft.find(r=>r.id===region.id)?.label||region.label;updateStatus();};label.append(input);fields.append(label);
            const targetLabel=el('label','','点击后'),target=el('select');target.disabled=busy;target.setAttribute('aria-label','热区跳转页面');
            const hint=el('option','','仅显示点击提示');hint.value='';target.append(hint);
            for(const page of config.project().pages.filter(p=>!p.trashedAt)) {const option=el('option','',page.title);option.value=page.id;target.append(option);}
            if(region.targetPageId&&!config.project().pages.some(p=>p.id===region.targetPageId&&!p.trashedAt)){const option=el('option','','目标已移除');option.value=region.targetPageId;target.append(option);}
            target.value=region.targetPageId||'';target.onchange=()=>{update(region.id,{targetPageId:target.value});paint();};targetLabel.append(target);fields.append(targetLabel);
            const details=el('details','ps-shot-geometry'),summary=el('summary','','位置与尺寸');details.append(summary);
            const grid=el('div','ps-shot-grid');
            for(const [key,title] of [['x','横向位置 %'],['y','纵向位置 %'],['width','宽度 %'],['height','高度 %']]) {
                const label=el('label','',title),number=el('input');number.disabled=busy;number.type='number';number.min=key==='x'||key==='y'?'0':'0.1';number.max='100';number.step='0.1';number.value=(region[key]*100).toFixed(1);number.setAttribute('aria-label',title);
                const change=final=>{if(number.value==='')return;const value=Number(number.value)/100,next={...draft.find(r=>r.id===region.id),[key]:value};
                    if(!Number.isFinite(value)||value<0||next.width<=0||next.height<=0||next.x+next.width>1||next.y+next.height>1){if(final){notice('热区必须位于截图内','warning');number.value=(draft.find(r=>r.id===region.id)[key]*100).toFixed(1);}return;}
                    update(region.id,next);
                };number.oninput=()=>change(false);number.onchange=()=>change(true);label.append(number);grid.append(label);
            }details.append(grid);fields.append(details);host.append(fields);
        }
        function render(container) {host=container;sync();attach();paint();}
        function readFile(file) {
            if(!file||!/^image\/(png|jpeg|webp|gif)$/.test(file.type))throw new Error('请选择 PNG、JPG、WebP 或 GIF 截图');
            if(file.size>10*1024*1024)throw new Error('截图不能超过 10 MB');
            return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('截图读取失败'));reader.readAsDataURL(file);});
        }
        function openMenu() {
            if(menu){menu.hidePopover();return;}
            if(dialog || !canLeave())return;
            const popup=el('div','ps-page-menu');popup.id='addPageMenu';popup.setAttribute('popover','auto');popup.setAttribute('role','menu');popup.setAttribute('aria-label','添加页面方式');
            menu=popup;let unposition=()=>{};
            const entries=[['screenshot','截图页面','上传或粘贴截图','<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m4 17 5-5 4 4 3-3 5 5"/><circle cx="16" cy="8" r="1"/>'],['html','导入 HTML','导入文件或页面文件夹','<path d="M6 3h8l4 4v14H6zM14 3v5h4m-8 5-2 2 2 2m4-4 2 2-2 2"/>']];
            for(const [kind,title,detail,path]of entries){
                const option=button('',()=>{popup.hidePopover();openDialog(false,kind);},'ps-page-option');option.setAttribute('role','menuitem');
                const icon=el('span','ps-page-option-icon');icon.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'+path+'</svg>';
                const text=el('span');text.append(el('strong','',title),el('small','',detail));option.append(icon,text);popup.append(option);
            }
            popup.addEventListener('toggle',event=>{if(event.newState==='closed'){unposition();popup.remove();if(menu===popup)menu=null;config.trigger.setAttribute('aria-expanded','false');}});
            popup.addEventListener('keydown',event=>{
                const items=[...popup.querySelectorAll('button')],index=items.indexOf(document.activeElement);
                if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();items[event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}
                if(event.key==='Escape'){event.preventDefault();popup.hidePopover();config.trigger.focus();}
                if(event.key==='Tab')popup.hidePopover();
            });
            document.body.append(popup);popup.showPopover();config.trigger.setAttribute('aria-expanded','true');
            unposition=ProtoProjectNavigation.positionPopup(popup,config.trigger.closest('.ps-page-actions')||config.trigger,{onDetach:()=>popup.hidePopover()});popup.querySelector('button').focus();
        }
        function openDialog(replace=false, kind='screenshot', replacementPage=null, onClose=null) {
            if(dialog||!canLeave())return;
            const isHtml=kind==='html';
            const page=replace?(replacementPage||current()):null;if(replace&&!page)return;
            const modal=el('dialog','ps-shot-dialog');dialog=modal;
            modal.setAttribute('aria-labelledby','psShotTitle');
            const form=el('form'),header=el('header');header.append(el('h2','',''));header.firstChild.id='psShotTitle';header.firstChild.textContent=replace?(isHtml?'重新导入 HTML':'替换截图'):isHtml?'导入 HTML':'添加截图页面';
            const close=button('×',()=>modal.close(),'ps-shot-close');close.setAttribute('aria-label','关闭');header.append(close);form.append(header);
            const upload=el('div','ps-shot-upload');upload.tabIndex=0;upload.setAttribute('role','group');upload.setAttribute('aria-label',isHtml?'导入或粘贴 HTML':'上传或粘贴截图');
            const preview=el('img');preview.alt='截图预览';preview.hidden=true;
            const file=el('input');file.type='file';file.accept=isHtml?'.html,.htm':'image/png,image/jpeg,image/webp,image/gif';file.id='psShotFile';file.setAttribute('aria-label',isHtml?'选择 HTML':'选择截图');
            const choose=el('label','ps-shot-file',isHtml?'选择 HTML':'选择截图');choose.htmlFor=file.id;
            const fileActions=el('div','ps-page-file-actions');fileActions.append(choose);
            const directory=el('input');directory.type='file';directory.multiple=true;directory.setAttribute('webkitdirectory','');directory.id='psHtmlDirectory';directory.setAttribute('aria-label','选择页面文件夹');
            if(isHtml){const selectFolder=el('label','ps-shot-file','导入文件夹');selectFolder.htmlFor=directory.id;fileActions.append(selectFolder);}
            const tip=el('span','ps-page-upload-tip',isHtml?'也可在此粘贴 HTML 源码':'也可在此粘贴或拖入截图 · 最大 10 MB');upload.append(preview,fileActions,tip,file);if(isHtml)upload.append(directory);form.append(upload);
            const entryLabel=el('label','ps-page-entry','入口 HTML'),entrySelect=el('select');entrySelect.setAttribute('aria-label','入口 HTML');entryLabel.append(entrySelect);entryLabel.hidden=true;form.append(entryLabel);
            if(isHtml)form.append(el('p','ps-shot-hint','包含本地图片、CSS 或脚本时，请导入页面文件夹。仅导入选定的 HTML 及静态资源。'));
            const fields=el('div','ps-shot-dialog-fields');
            const title=el('input');title.required=true;title.maxLength=100;title.setAttribute('aria-label','页面名称');
            const shell=el('select');shell.setAttribute('aria-label','页面外壳');
            for(const [value,label]of[['web','Web'],['mobile','App'],['pad','Pad']]){const option=el('option','',label);option.value=value;shell.append(option);}
            shell.value=config.page()?.previewType||'web';
            const client=el('select');client.setAttribute('aria-label','端分类');
            const none=el('option','','未分组');none.value='';client.append(none);
            for(const item of config.project().clients||[]){const option=el('option','',item.title);option.value=item.id;client.append(option);}
            client.value=config.page()?.clientId||'';
            const parent=el('select');parent.setAttribute('aria-label','父页面');
            function parents(){const last=parent.value;parent.replaceChildren();const option=el('option','','顶层页面');option.value='';parent.append(option);
                const pages=config.project().pages;
                for(const item of pages.filter(p=>!p.trashedAt&&p.role!=='launcher'&&(p.clientId||'')===client.value)) {
                    let depth=1,node=item;while(node.parentId&&depth<4){depth++;node=pages.find(p=>p.id===node.parentId)||{};}
                    if(depth>=3)continue;const option=el('option','',item.title);option.value=item.id;parent.append(option);
                }parent.value=[...parent.options].some(o=>o.value===last)?last:'';
            }client.onchange=()=>{parents();const c=config.project().clients?.find(c=>c.id===client.value);if(c)shell.value=c.previewType||'web';};parents();
            if(!replace)for(const [text,control]of[['页面名称',title],['页面外壳',shell],['端分类',client],['父页面',parent]]){const label=el('label','',text);label.append(control);fields.append(label);}
            form.append(fields);
            if(replace){form.append(el('p','ps-shot-hint','替换页面：'+page.title));form.append(el('p','ps-shot-hint',isHtml?'保留页面设置、PRD、标注与热区。新 HTML 的结构或控件变化后，请检查原有定位。':'保留页面设置、PRD、标注与热区。原有位置按图片比例保留，布局变化后请检查定位。'));}
            const error=el('p','ps-shot-error');error.setAttribute('role','alert');error.hidden=true;form.append(error);
            const submitText=replace?(isHtml?'替换页面':'替换截图'):isHtml?'导入页面':'添加页面';
            const footer=el('footer'),cancel=button('取消',()=>modal.close()),submit=el('button','ei-primary',submitText);submit.type='submit';submit.disabled=true;footer.append(cancel,submit);form.append(footer);modal.append(form);
            let dataUrl='',saving=false,reading=0,htmlRecords=[],htmlPayload=null,suggestedTitle='';
            async function accept(image){const version=++reading;submit.disabled=true;dataUrl='';try{const value=await readFile(image);if(version!==reading)return;dataUrl=value;preview.src=value;preview.hidden=false;tip.textContent=image.name||'已粘贴截图';if(!title.value)title.value=(image.name||'截图页面').replace(/\.[^.]+$/,'').slice(0,100);error.hidden=true;submit.disabled=false;}catch(reason){if(version!==reading)return;error.textContent=reason.message;error.hidden=false;}}
            const readData=source=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(source);});
            async function prepareHtml() {
                const version=++reading;submit.disabled=true;htmlPayload=null;error.hidden=true;
                try{
                    const entry=entrySelect.value,records=htmlRecords.filter(r=>r.path===entry||!htmlType(r.path));
                    if(!records.some(r=>r.path===entry))throw new Error('请选择入口 HTML');
                    if(records.length>300)throw new Error('每次最多导入 300 个文件');
                    if(records.reduce((total,r)=>total+r.file.size,0)>30*1024*1024)throw new Error('文件合计不能超过 30 MB');
                    if(records.some(r=>r.file.size>(r.path===entry?5:10)*1024*1024))throw new Error('HTML 最大 5 MB，单个资源最大 10 MB');
                    const files=await Promise.all(records.map(async r=>({path:r.path,dataUrl:await readData(r.file)})));
                    const selected=records.find(r=>r.path===entry);const text=await selected.file.text();
                    if(version!==reading)return;
                    const doc=new DOMParser().parseFromString(text,'text/html'),nextTitle=(doc.title||selected.file.name.replace(/\.html?$/i,'')).trim().slice(0,100);
                    if(!title.value||title.value===suggestedTitle)title.value=nextTitle;suggestedTitle=nextTitle;
                    htmlPayload={entryFile:entry,files};tip.textContent=entry+' · '+records.length+' 个文件';submit.disabled=false;
                }catch(reason){if(version!==reading)return;error.textContent=reason.message;error.hidden=false;}
            }
            async function acceptHtml(files,folder=false){
                try{htmlRecords=collectHtmlFiles([...files],folder);const entries=htmlRecords.filter(r=>htmlType(r.path));entrySelect.replaceChildren();
                    for(const record of entries){const option=el('option','',record.path);option.value=record.path;entrySelect.append(option);}
                    entrySelect.value=(entries.find(r=>r.path.toLowerCase()==='index.html')||entries[0]).path;entryLabel.hidden=entries.length<2;await prepareHtml();
                }catch(reason){reading++;htmlPayload=null;submit.disabled=true;error.textContent=reason.message;error.hidden=false;}
            }
            file.onchange=()=>{if(file.files[0])void(isHtml?acceptHtml(file.files):accept(file.files[0]));};
            directory.onchange=()=>{if(directory.files.length)void acceptHtml(directory.files,true);};entrySelect.onchange=()=>void prepareHtml();
            modal.addEventListener('paste',e=>{
                if(saving)return;
                if(isHtml){if(e.target!==upload&&!upload.contains(e.target))return;const text=e.clipboardData.getData('text/plain');
                    if(text&&/<[a-z][^>]*>/i.test(text)){e.preventDefault();void acceptHtml([new File([text.replace(/^```(?:html)?\s*\n|\n```\s*$/g,'')],'index.html',{type:'text/html'})]);}return;}
                const item=[...e.clipboardData.items].find(i=>i.type.startsWith('image/'));if(item){e.preventDefault();void accept(item.getAsFile());}
            });
            upload.ondragover=e=>{e.preventDefault();};upload.ondrop=e=>{e.preventDefault();if(saving||!e.dataTransfer.files.length)return;void(isHtml?acceptHtml(e.dataTransfer.files):accept(e.dataTransfer.files[0]));};
            modal.addEventListener('cancel',e=>{if(saving)e.preventDefault();});
            modal.addEventListener('close',()=>{reading++;modal.remove();dialog=null;if(onClose)onClose();else config.trigger?.focus();},{once:true});
            form.onsubmit=async e=>{e.preventDefault();if(saving||(isHtml?!htmlPayload:!dataUrl))return;saving=true;submit.disabled=cancel.disabled=close.disabled=true;submit.textContent='保存中…';error.hidden=true;
                form.querySelectorAll('input,select').forEach(control=>control.disabled=true);
                try{const result=await config.save(isHtml?(replace?'replace-html':'import-html'):replace?'replace':'create',{...(replace?{pageId:page.id}:{title:title.value.trim(),previewType:shell.value,clientId:client.value,parentId:parent.value}),...(isHtml?htmlPayload:{dataUrl})});
                    modal.close();pageId='';dirty=false;config.openPage(result.page.id);notice(replace?(isHtml?'HTML 已替换，请检查标注与热区定位':'截图已替换，请检查标注与热区定位'):isHtml?'HTML 页面已导入':'截图页面已添加');
                }catch(reason){error.textContent=reason.message||'保存失败';error.hidden=false;}
                finally{saving=false;submit.disabled=cancel.disabled=close.disabled=false;submit.textContent=submitText;form.querySelectorAll('input,select').forEach(control=>control.disabled=false);}
            };
            document.body.append(modal);modal.showModal();upload.focus();
            return true;
        }
        function openReplace(id, onClose=null) {
            const page=config.project().pages.find(p=>p.id===id&&!p.trashedAt);
            if(!page||(page.kind!=='screenshot'&&!page.htmlImport))return false;
            return !!openDialog(true,page.kind==='screenshot'?'screenshot':'html',page,onClose);
        }
        frame.addEventListener('load',()=>{menu?.hidePopover();active=false;host=null;sync();});
        return {enabled:()=>!!current(),render,setActive,canLeave,isEditing:()=>active,isDrawing:()=>drawing,openCreate:()=>openDialog(false),openMenu,openReplace};
    }
    window.ProtoScreenshotEditor={create,collectHtmlFiles};
})();
