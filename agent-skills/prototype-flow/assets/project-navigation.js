(function () {
    'use strict';
    const svg = (path) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">' + path + '</svg>';
    const fileIcon = svg('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4"/>');
    const chevron = svg('<path d="m6 9 6 6 6-6"/>');
    const editIcon = svg('<path d="m4 16 12-12 4 4-12 12-5 1zM14 6l4 4"/>');
    const checkIcon = svg('<path d="m5 12 4 4 10-10"/>');
    const dragIcon = svg('<circle cx="9" cy="5" r=".8"/><circle cx="15" cy="5" r=".8"/><circle cx="9" cy="12" r=".8"/><circle cx="15" cy="12" r=".8"/><circle cx="9" cy="19" r=".8"/><circle cx="15" cy="19" r=".8"/>');
    let selectSequence = 0;

    function positionPopup(popup, anchor, {side = 'bottom', gap = 6, onDetach} = {}) {
        function place() {
            if (!anchor.isConnected || !popup.isConnected) {onDetach?.(); return;}
            const r = anchor.getBoundingClientRect(), width = popup.offsetWidth, height = popup.offsetHeight;
            const clipping = anchor.closest('.ppn')?.getBoundingClientRect();
            if (!r.width || !r.height || r.bottom < 0 || r.top > window.innerHeight || (clipping && (r.bottom < clipping.top || r.top > clipping.bottom))) {onDetach?.(); return;}
            const edge = 12, viewWidth = window.innerWidth, viewHeight = window.innerHeight;
            let left, top;
            if (side === 'right') {
                left = r.right + gap;
                if (left + width > viewWidth - edge && r.left - width - gap >= edge) left = r.left - width - gap;
                top = r.top - 16;
                popup.style.transformOrigin = left >= r.right ? 'left top' : 'right top';
            } else {
                left = r.left;
                const below = viewHeight - r.bottom - gap - edge;
                top = below >= height || below >= r.top - gap - edge ? r.bottom + gap : r.top - height - gap;
                popup.style.transformOrigin = top >= r.bottom ? 'top left' : 'bottom left';
            }
            left = Math.max(edge, Math.min(left, viewWidth - width - edge));
            top = Math.max(edge, Math.min(top, viewHeight - height - edge));
            popup.style.left = left + 'px'; popup.style.top = top + 'px';
            popup.style.setProperty('--anchor-y', Math.max(22, Math.min(r.top + r.height / 2 - top, height - 22)) + 'px');
        }
        const controller = new AbortController();
        window.addEventListener('resize', place, {signal: controller.signal});
        window.addEventListener('scroll', place, {capture: true, signal: controller.signal});
        const observer = new ResizeObserver(place); observer.observe(popup); observer.observe(anchor);
        place();
        return () => {controller.abort(); observer.disconnect();};
    }

    function createSelect(host, config) {
        let items = config.items || [], value = config.value || '', menu = null, cleanup = null, busy = false;
        const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'ppn-select';
        trigger.setAttribute('role', 'combobox'); trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-label', config.label || '选择');
        const id = 'ppn-options-' + ++selectSequence; trigger.setAttribute('aria-controls', id);
        const text = document.createElement('span'); text.className = 'ppn-select-label';
        const arrow = document.createElement('span'); arrow.className = 'ppn-select-arrow'; arrow.innerHTML = chevron;
        trigger.append(text, arrow); host.append(trigger);
        function paint() {text.textContent = items.find(i => i.value === value)?.label || config.placeholder || '请选择';}
        function close(restore = false) {
            if (!menu) return;
            cleanup?.(); cleanup = null; menu.remove(); menu = null;
            trigger.setAttribute('aria-expanded', 'false'); trigger.removeAttribute('aria-activedescendant');
            if (restore && trigger.isConnected) trigger.focus({preventScroll: true});
        }
        async function choose(item) {
            close(true);
            const old = value; value = item.value; paint(); busy = true; trigger.disabled = true;
            try {if (await config.onChange?.(value) === false) {value = old; paint();}}
            catch (error) {value = old; paint(); config.onError?.(error);}
            finally {busy = false; trigger.disabled = !!config.disabled;}
        }
        function open(direction = 0) {
            if (menu || busy || trigger.disabled) return;
            document.querySelectorAll('.ppn-menu').forEach(other => other.dispatchEvent(new Event('ppn-close')));
            menu = document.createElement('div'); menu.className = 'ppn ppn-menu';
            menu.dataset.ppnOwner = config.owner?.id || '';
            menu.style.width = Math.min(Math.max(trigger.getBoundingClientRect().width, 208), window.innerWidth - 24) + 'px';
            const list = document.createElement('div'); list.id = id; list.className = 'ppn-options';
            list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', config.label || '选择');
            const enabled = [];
            items.forEach((item, index) => {
                const option = document.createElement('button'); option.type = 'button'; option.className = 'ppn-option';
                option.id = id + '-' + index; option.setAttribute('role', 'option'); option.tabIndex = -1;
                option.setAttribute('aria-selected', String(item.value === value)); option.disabled = !!item.disabled;
                const label = document.createElement('span'); label.className = 'ppn-option-label'; label.textContent = item.label;
                if (item.description) {const detail = document.createElement('small'); detail.textContent = item.description; label.append(detail);}
                option.append(label);
                if (item.hint) {const hint = document.createElement('span'); hint.className = 'ppn-option-hint'; hint.textContent = item.hint; option.append(hint);}
                const check = document.createElement('span'); check.className = 'ppn-option-check'; check.innerHTML = checkIcon; option.append(check);
                option.onclick = () => choose(item); list.append(option);
                if (!item.disabled) enabled.push({node: option, item});
            });
            menu.append(list);
            if (config.onAdd) {
                const add = document.createElement('button'); add.type = 'button'; add.className = 'ppn-option-add';
                add.textContent = '+ 新增端分类'; add.onclick = () => {close(); config.onAdd();}; menu.append(add);
                enabled.push({node:add,item:{label:'新增端分类',action:true}});
            }
            const maxHeight = Math.max(100, Math.min(320, window.innerHeight - 64)); list.style.maxHeight = maxHeight + 'px';
            document.body.append(menu); trigger.setAttribute('aria-expanded', 'true');
            const controller = new AbortController(), unposition = positionPopup(menu, trigger, {onDetach: () => close()});
            if (!menu) {controller.abort(); unposition(); return;}
            let cursor = Math.max(0, enabled.findIndex(i => i.item.value === value));
            if (direction) cursor = Math.max(0, Math.min(enabled.length - 1, cursor + direction));
            function focus(index) {
                cursor = index; const option = enabled[cursor]?.node;
                if (option) {option.focus({preventScroll: true}); option.scrollIntoView({block: 'nearest'}); if(option.getAttribute('role')==='option')trigger.setAttribute('aria-activedescendant', option.id);else trigger.removeAttribute('aria-activedescendant');}
            }
            let typed = '', typedAt = 0;
            document.addEventListener('keydown', event => {
                if (!menu || (!menu.contains(event.target) && event.target !== trigger)) return;
                if (event.key === 'Escape') {event.preventDefault(); event.stopImmediatePropagation(); close(true); return;}
                if (event.key === 'Tab') {close(true); return;}
                if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
                    event.preventDefault(); event.stopPropagation();
                    focus(event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : (cursor + (event.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length);
                } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey && event.key !== ' ') {
                    typed = Date.now() - typedAt < 700 ? typed + event.key.toLocaleLowerCase() : event.key.toLocaleLowerCase(); typedAt = Date.now();
                    const next = enabled.findIndex((_, offset) => enabled[(cursor + 1 + offset) % enabled.length].item.label.toLocaleLowerCase().startsWith(typed));
                    if (next >= 0) {event.preventDefault(); focus((cursor + 1 + next) % enabled.length);}
                }
            }, {capture: true, signal: controller.signal});
            document.addEventListener('pointerdown', event => {if (!menu?.contains(event.target) && !trigger.contains(event.target)) close();}, {signal: controller.signal});
            window.addEventListener('blur', () => {if (document.activeElement?.tagName === 'IFRAME') close();}, {signal: controller.signal});
            menu.addEventListener('ppn-close', () => close());
            cleanup = () => {controller.abort(); unposition();}; focus(cursor);
        }
        trigger.onclick = () => menu ? close(true) : open();
        trigger.onkeydown = event => {if (['ArrowDown', 'ArrowUp'].includes(event.key)) {event.preventDefault(); event.stopPropagation(); open(event.key === 'ArrowDown' ? 0 : -1);}};
        trigger.disabled = !!config.disabled; paint();
        return {button: trigger, get value() {return value;}, setValue(next) {value = next; paint();},
            setItems(next) {close(); items = next; paint();}, close, destroy() {close(); trigger.remove();}};
    }

    function priorityLabel(value) {return '优先级 ' + value + (value === 1 ? '（最高）' : value === 6 ? '（最低）' : '');}
    function priorityBadge(value) {
        const badge = document.createElement('span');badge.className = 'ppn-priority';badge.dataset.priority = value;
        badge.textContent = value;badge.setAttribute('role', 'img');badge.setAttribute('aria-label', priorityLabel(value));badge.title = priorityLabel(value);return badge;
    }
    function progressLabel(value) {return value === 0 ? '未开始' : value === 100 ? '已完成' : value + '%';}
    function progressGlyph(value) {
        const glyph = document.createElement('span');glyph.className = 'ppn-progress-glyph';glyph.setAttribute('aria-hidden', 'true');
        glyph.style.setProperty('--ppn-progress', value + '%');glyph.dataset.complete = String(value === 100);
        if (value === 100) glyph.innerHTML = checkIcon;return glyph;
    }
    function createPageTracking(host, page) {
        const model = {priority: Number.isInteger(page.priority) && page.priority >= 1 && page.priority <= 6 ? page.priority : null,
            progress: Number.isInteger(page.progress) && page.progress >= 0 && page.progress <= 100 ? page.progress : null};
        const painters = [];host.classList.add('ppn-tracking');
        for (const [key, label, values] of [['priority', '优先级', [1,2,3,4,5,6]], ['progress', '完成情况', [0,25,50,75,100]]]) {
            const field = document.createElement('div'), head = document.createElement('div');head.className = 'ppn-mark-heading';
            const heading = document.createElement('span');heading.id = 'ppn-tracking-' + ++selectSequence;heading.textContent = label;
            const current = document.createElement('span');current.className = 'ppn-mark-current';
            const clear = document.createElement('button');clear.type = 'button';clear.className = 'ppn-mark-clear';clear.textContent = '清除';clear.setAttribute('aria-label', '清除' + label);
            head.append(heading, current, clear);field.append(head);
            const row = document.createElement('div');row.className = 'ppn-mark-options ppn-mark-' + key;row.setAttribute('role', 'radiogroup');row.setAttribute('aria-labelledby', heading.id);
            const choices = values.map(value => {
                const option = document.createElement('button');option.type = 'button';option.className = 'ppn-mark-option';option.setAttribute('role', 'radio');
                option.setAttribute('aria-label', key === 'priority' ? priorityLabel(value) : '完成情况：' + progressLabel(value));
                option.title = option.getAttribute('aria-label');option.append(key === 'priority' ? priorityBadge(value) : progressGlyph(value));
                if (key === 'progress') {const caption = document.createElement('small');caption.textContent = value + '%';option.append(caption);}
                option.onclick = () => {model[key] = value;paint();};row.append(option);return option;
            });
            function paint() {
                const selected = values.indexOf(model[key]);clear.disabled = model[key] === null;
                current.textContent = model[key] === null ? '未标记' : key === 'priority' ? model[key] + (model[key] === 1 ? ' · 最高' : model[key] === 6 ? ' · 最低' : '') : progressLabel(model[key]);
                choices.forEach((option, index) => {option.setAttribute('aria-checked', String(index === selected));option.tabIndex = index === Math.max(0, selected) ? 0 : -1;});
            }
            clear.onclick = () => {model[key] = null;paint();choices[0].focus({preventScroll: true});};
            row.onkeydown = event => {
                if (!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
                event.preventDefault();event.stopPropagation();const index = choices.indexOf(event.target);if (index < 0) return;
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1 : (index + (['ArrowRight','ArrowDown'].includes(event.key) ? 1 : -1) + choices.length) % choices.length;
                choices[next].click();choices[next].focus({preventScroll: true});
            };
            field.append(row);host.append(field);painters.push(paint);paint();
        }
        return {get value() {return {...model};}, refresh() {painters.forEach(paint => paint());}, destroy() {host.remove();}};
    }

    function groupKey(page, project) {
        if (page.role === 'launcher') return '__launchers';
        return (project.clients || []).some(c => c.id === page.clientId) ? page.clientId : '__ungrouped';
    }
    function pageTree(project) {
        const all = new Map((project.pages || []).map(p => [p.id, p]));
        const nodes = new Map((project.pages || []).filter(p => !p.trashedAt).map(page => [page.id, {page, parentId: '', children: [], depth: 1}]));
        for (const node of nodes.values()) {
            let parent = all.get(node.page.parentId), seen = new Set([node.page.id]);
            while (parent?.trashedAt && !seen.has(parent.id)) {seen.add(parent.id); parent = all.get(parent.parentId);}
            if (parent && !seen.has(parent.id) && nodes.has(parent.id) && groupKey(parent, project) === groupKey(node.page, project)) node.parentId = parent.id;
        }
        for (const node of nodes.values()) if (node.parentId) nodes.get(node.parentId).children.push(node);
        const roots = [...nodes.values()].filter(n => !n.parentId);
        function walk(node, depth) {node.depth = depth; node.children.forEach(child => walk(child, depth + 1));}
        roots.forEach(n => walk(n, 1));
        return {nodes, roots};
    }
    function subtreePages(project, id) {
        const result = [], seen = new Set();
        function visit(page) {if (!page || seen.has(page.id)) return; seen.add(page.id); result.push(page); (project.pages || []).filter(p => p.parentId === page.id).forEach(visit);}
        visit((project.pages || []).find(p => p.id === id)); return result;
    }
    function reorderError(project, request) {
        if (request.kind === 'client') return '';
        const source = project.pages?.find(p => p.id === request.id), target = project.pages?.find(p => p.id === request.targetId);
        if (!source || source.trashedAt) return '页面已移除';
        if (!['before', 'after', 'inside', 'root'].includes(request.position)) return '无效的移动位置';
        if (request.position === 'root') {
            if (source.role === 'launcher' || (request.targetId !== '__ungrouped' && !project.clients?.some(c => c.id === request.targetId))) return '请选择业务页面所属端';
        } else {
            if (!target || target.trashedAt) return '目标页面已移除';
            if (subtreePages(project, source.id).some(p => p.id === target.id)) return '不能移入自己或自己的子页面';
            if ((source.role === 'launcher') !== (target.role === 'launcher') || (target.role === 'launcher' && request.position === 'inside')) return '演示入口不能作为业务页面的父级';
        }
        const all = new Map((project.pages || []).map(p => [p.id, p]));
        const parentId = request.position === 'root' ? '' : request.position === 'inside' ? target.id : pageTree(project).nodes.get(target.id)?.parentId;
        let depth = 1, parent = all.get(parentId), seen = new Set();
        while (parent && !seen.has(parent.id)) {seen.add(parent.id); depth++; parent = all.get(parent.parentId);}
        function height(page) {const children = (project.pages || []).filter(p => p.parentId === page.id); return 1 + Math.max(0, ...children.map(height));}
        return depth + height(source) - 1 > 3 ? '最多支持三级页面，当前子树会超过三级' : '';
    }
    function reorderProject(project, request) {
        if (!['page', 'client'].includes(request.kind)) return false;
        if (request.kind === 'client') {
            const records = [...(project.clients || [])], source = records.findIndex(p => p.id === request.id), target = records.findIndex(p => p.id === request.targetId);
            if (source < 0 || target < 0 || source === target || !['before', 'after'].includes(request.position)) return false;
            const before = records.map(p => p.id).join('\n'), [record] = records.splice(source, 1);
            records.splice(records.findIndex(p => p.id === request.targetId) + (request.position === 'after' ? 1 : 0), 0, record);
            if (before === records.map(p => p.id).join('\n')) return false;
            project.clients = records; return true;
        }
        if (reorderError(project, request)) return false;
        const tree = pageTree(project), target = tree.nodes.get(request.targetId)?.page;
        const moved = subtreePages(project, request.id).map(p => ({...p})), ids = new Set(moved.map(p => p.id));
        const records = project.pages.filter(p => !ids.has(p.id));
        const parentId = request.position === 'root' ? '' : request.position === 'inside' ? target.id : tree.nodes.get(target.id).parentId;
        const clientId = request.position === 'root' ? (request.targetId === '__ungrouped' ? '' : request.targetId) : target.clientId || '';
        if (parentId) moved[0].parentId = parentId; else delete moved[0].parentId;
        for (const page of moved) {if (clientId) page.clientId = clientId; else if (page.clientId) delete page.clientId;}
        let destination = records.length;
        if (request.position !== 'root') {
            destination = records.findIndex(p => p.id === target.id);
            if (request.position !== 'before') {
                const descendants = new Set(subtreePages({pages: records}, target.id).map(p => p.id));
                destination = Math.max(...records.map((p, i) => descendants.has(p.id) ? i : -1)) + 1;
            }
        }
        records.splice(destination, 0, ...moved);
        if (JSON.stringify(records) === JSON.stringify(project.pages)) return false;
        project.pages = records; return true;
    }
    function defaultPage(project) {
        const pages = (project.pages || []).filter(p=>!p.trashedAt);
        return pages.find(p => p.id === project.defaultPage && p.role !== 'launcher')
            || pages.find(p => p.id === 'home' && p.role !== 'launcher')
            || pages.find(p => p.role !== 'launcher');
    }
    function updatePageNavigation(project, id, values) {
        const page=project.pages.find(p=>p.id===id);if(!page)throw new Error('页面已移除，请重新打开项目');
        const moved=subtreePages(project,id);
        for(const child of moved)child.clientId=values.clientId;
        Object.assign(page,values);
        const parent=project.pages.find(p=>p.id===page.parentId);
        if(page.role==='launcher'||(parent&&(parent.clientId || '')!==(page.clientId || '')))delete page.parentId;
        if(page.role==='launcher')for(const child of project.pages)if(child.parentId===id)delete child.parentId;
    }
    function mount(host, initial) {
        let options = initial, filter = '', closed = new Set(['__launchers']), closedPages = new Set(), filterControl = null, drag = null, saving = false, suppressClick = false;
        host.classList.add('ppn');
        const live = document.createElement('span'); live.className = 'ppn-live'; live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite');
        function button(className, label, action) {
            const node = document.createElement('button');
            node.type = 'button'; node.className = className; node.textContent = label; node.onclick = action;
            return node;
        }
        function render() {
            const focused = document.activeElement?.closest('[data-ppn-key]')?.dataset.ppnKey;
            const { project, currentPage, currentState, onSelect, onEdit, onReorder, annotations = [] } = options;
            const pages = (project.pages || []).filter(p=>!p.trashedAt), clients = project.clients || [], tree = pageTree(project);
            if (filter && !clients.some(c => c.id === filter)) filter = '';
            filterControl?.destroy(); filterControl = null; host.replaceChildren();
            host.setAttribute('aria-busy', String(saving));
            if (clients.length) {
                const wrap = document.createElement('div'); wrap.className = 'ppn-filter';
                host.append(wrap);
                filterControl = createSelect(wrap, {label: '切换端', value: filter,
                    items: [{value: '', label: '全部端', hint: pages.filter(p => p.role !== 'launcher').length + ' 页'},
                        ...clients.map(c => ({value: c.id, label: c.title, hint: pages.filter(p => p.role !== 'launcher' && p.clientId === c.id).length + ' 页'}))],
                    onChange: async value => {
                    const previousFilter = filter;
                    filter = value;
                    closed.delete(filter);
                    const candidates = pages.filter(p => p.role !== 'launcher' && (!filter || p.clientId === filter));
                    if (filter && !candidates.some(p => p.id === currentPage)) {
                        const remembered = memory.get(filter);
                        const next = candidates.find(p => p.id === remembered?.pageId) || candidates[0];
                        if (next && await onSelect(next.id, remembered?.pageId === next.id ? remembered.stateId : next.states?.[0]?.id || 'default') === false) filter = previousFilter;
                    }
                    render();
                }});
                filterControl.button.dataset.ppnKey = 'filter';
            }
            let groups = clients.map(c => ({...c, pages:pages.filter(p => p.role !== 'launcher' && p.clientId === c.id)}));
            const ungrouped = pages.filter(p => p.role !== 'launcher' && !clients.some(c => c.id === p.clientId));
            if (ungrouped.length) groups.push({id:'__ungrouped',title:clients.length?'未分组':'页面',pages:ungrouped});
            groups = groups.filter(g => !filter || g.id === filter);
            const launchers = pages.filter(p => p.role === 'launcher');
            if (launchers.length) groups.push({id:'__launchers',title:'演示入口',pages:launchers});
            for (const group of groups.filter(g => g.pages.length)) {
                const section = document.createElement('section');section.className = 'ppn-group';section.dataset.groupId = group.id;
                const list = document.createElement('div'); list.className = 'ppn-group-list';
                const showHeading = clients.length || group.id === '__launchers';
                if (group.id === '__launchers' && group.pages.some(p => p.id === currentPage)) closed.delete(group.id);
                if (showHeading) {
                    const toggle = button('ppn-group-toggle', '', () => {closed.has(group.id)?closed.delete(group.id):closed.add(group.id);render();});
                    toggle.innerHTML = chevron;
                    const label = document.createElement('span');label.textContent=group.title;toggle.append(label);
                    const count = document.createElement('span'); count.className = 'ppn-group-count'; count.textContent = group.pages.length; count.setAttribute('aria-hidden','true'); toggle.append(count);
                    if (onReorder && clients.some(c => c.id === group.id)) {toggle.dataset.ppnDrag = 'client'; toggle.dataset.dragId = group.id; toggle.setAttribute('aria-keyshortcuts', 'Alt+ArrowUp Alt+ArrowDown'); toggle.title = '按住拖动分组 · Alt + ↑ / ↓';}
                    toggle.dataset.ppnKey='group:'+group.id;toggle.setAttribute('aria-expanded',String(!closed.has(group.id)));if(group.id!=='__launchers')toggle.dataset.ppnRoot=group.id;section.append(toggle);
                    list.hidden=closed.has(group.id);
                }
                function renderPage(branch, container) {
                    const {page, depth, children} = branch;
                    const node = document.createElement('div');node.className='ppn-branch';node.dataset.branchId=page.id;
                    const item = document.createElement('div');item.className='ppn-item-wrap';item.style.setProperty('--ppn-depth', depth - 1);item.dataset.depth=depth;
                    const stateId=page.states?.[0]?.id || 'default';
                    const target = button('ppn-page','',()=>onSelect(page.id,stateId));
                    const icon = document.createElement('span'); icon.className = 'ppn-page-icon'; icon.innerHTML=fileIcon+(onReorder?dragIcon:'');target.append(icon);target.dataset.pageId=page.id;target.dataset.ppnKey='page:'+page.id;
                    if (Number.isInteger(page.priority) && page.priority >= 1 && page.priority <= 6) {icon.classList.add('has-priority');icon.append(priorityBadge(page.priority));}
                    if (onReorder) {target.dataset.ppnDrag='page'; target.dataset.dragId=page.id; target.dataset.dragGroup=group.id; target.dataset.parentId=branch.parentId; target.setAttribute('aria-keyshortcuts','Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight'); target.title='拖动排序或移入页面 · Alt + 方向键调整层级';}
                    target.dataset.scope=page.id+'\n'+stateId;target.setAttribute('aria-current',String(page.id===currentPage));
                    const label=document.createElement('span');label.className='ppn-label';
                    const title=document.createElement('span');title.className='ppn-title';title.textContent=page.title || page.id;title.title=title.textContent;
                    const sub=document.createElement('span');sub.className='ppn-subtitle';
                    const count=annotations.filter(n=>n.pageId===page.id).length;
                    if (Number.isInteger(page.progress) && page.progress >= 0 && page.progress <= 100) {
                        const progress = document.createElement('span');progress.className = 'ppn-page-progress';progress.title = '完成情况：' + progressLabel(page.progress);
                        progress.append(progressGlyph(page.progress), document.createTextNode(progressLabel(page.progress)));sub.append(progress);
                    }
                    const detail = document.createElement('span');detail.className = 'ppn-page-detail';detail.textContent=page.file+(count?' · '+count+' 条标注':'');sub.append(detail);label.append(title,sub);target.append(label);item.append(target);
                    if(onEdit){const edit=button('ppn-edit','',event=>onEdit(page,event.currentTarget));edit.innerHTML=editIcon;edit.setAttribute('aria-label','设置 '+title.textContent);edit.dataset.ppnKey='edit:'+page.id;item.append(edit);}
                    node.append(item);container.append(node);
                    const nested = document.createElement('div');nested.className='ppn-children';nested.id='ppn-children-'+(++selectSequence);nested.setAttribute('role','group');nested.setAttribute('aria-label',title.textContent+'的子页面');nested.hidden=closedPages.has(page.id);
                    if(children.length){
                        item.classList.add('ppn-has-children');
                        const expand=button('ppn-expand','',()=>{closedPages.has(page.id)?closedPages.delete(page.id):closedPages.add(page.id);render();});
                        expand.innerHTML=chevron;expand.setAttribute('aria-label',(nested.hidden?'展开':'收起')+' '+title.textContent+'的子页面');expand.setAttribute('aria-expanded',String(!nested.hidden));expand.setAttribute('aria-controls',nested.id);expand.dataset.ppnKey='expand:'+page.id;item.append(expand);
                    }
                    if ((page.states || []).length>1) for (const state of page.states) {
                        const st=button('ppn-state',state.title || state.id,()=>onSelect(page.id,state.id));
                        st.dataset.pageId=page.id;st.dataset.stateId=state.id;st.dataset.scope=page.id+'\n'+state.id;st.dataset.ppnKey='state:'+page.id+':'+state.id;
                        st.style.setProperty('--ppn-depth',depth-1);st.setAttribute('aria-current',String(page.id===currentPage && state.id===currentState));node.append(st);
                    }
                    children.forEach(child=>renderPage(child,nested));if(children.length)node.append(nested);
                }
                tree.roots.filter(n=>groupKey(n.page,project)===group.id).forEach(n=>renderPage(n,list));
                section.append(list);host.append(section);
            }
            if(!host.querySelector('.ppn-page')){const empty=document.createElement('div');empty.className='ppn-empty';empty.textContent=filter?'该端暂无页面':'暂无页面';host.append(empty);}
            if(options.onTrash){const count=(project.pages || []).filter(p=>p.trashedAt).length;const trash=button('ppn-trash-entry','',event=>options.onTrash(event.currentTarget));trash.innerHTML=svg('<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>');const label=document.createElement('span');label.textContent='回收站';trash.append(label);const badge=document.createElement('span');badge.className='ppn-group-count';badge.textContent=count;trash.append(badge);trash.dataset.ppnKey='trash';trash.setAttribute('aria-label','回收站，'+count+' 个页面');host.append(trash);}
            host.append(live);
            if(focused) Array.from(host.querySelectorAll('[data-ppn-key]')).find(n=>n.dataset.ppnKey===focused)?.focus({preventScroll:true});
        }
        const memory = new Map();
        async function commit(request, focusKey) {
            if (saving || !options.onReorder) return;
            const check = {pages: [...options.project.pages], clients: [...(options.project.clients || [])]};
            const error=reorderError(options.project,request);if(error){live.textContent=error;return;}
            if (!reorderProject(check, request)) {live.textContent='页面位置未改变';return;}
            const previousProject=options.project, save=options.onReorder;
            if(request.position==='inside')closedPages.delete(request.targetId);
            const moved=check.pages.find(p=>p.id===request.id);if(moved)closed.delete(groupKey(moved,check));
            if(filter && moved && groupKey(moved,check)!==filter)filter='';
            saving = true; options={...options,project:check}; live.textContent = '正在保存页面结构'; render();
            try {const ok = await save(request); if(ok===false && options.project===check)options={...options,project:previousProject};live.textContent = ok === false ? '移动未保存，已恢复原结构' : '页面结构已保存';}
            catch (_) {if(options.project===check)options={...options,project:previousProject};live.textContent = '移动未保存，已恢复原结构';}
            finally {saving = false; render(); if(focusKey) Array.from(host.querySelectorAll('[data-ppn-key]')).find(n=>n.dataset.ppnKey===focusKey)?.focus({preventScroll:true});}
        }
        function endDrag(cancel = false) {
            if (!drag) return;
            const last = drag; drag = null; clearTimeout(last.timer); clearTimeout(last.expandTimer); cancelAnimationFrame(last.raf); last.controller.abort();
            last.node.classList.remove('ppn-drag-source'); last.ghost?.remove(); last.line?.remove();
            host.querySelectorAll('.ppn-drop-inside,.ppn-drop-invalid,.ppn-root-active').forEach(n=>n.classList.remove('ppn-drop-inside','ppn-drop-invalid','ppn-root-active'));
            document.body.classList.remove('ppn-dragging');
            if(last.started){suppressClick=true; try{last.node.releasePointerCapture(last.pointerId);}catch(_){} if(!cancel && last.drop) commit(last.drop, last.node.dataset.ppnKey);else live.textContent=last.error || '已取消拖动';}
        }
        function beginDrag(event, node) {
            const controller = new AbortController(), startRect = node.getBoundingClientRect();
            drag = {node, controller, pointerId: event.pointerId, x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY, started:false,drop:null};
            function start() {
                if (!drag || drag.started) return; drag.started = true;
                filterControl?.close(); node.classList.add('ppn-drag-source'); document.body.classList.add('ppn-dragging');
                try{node.setPointerCapture(event.pointerId);}catch(_){}
                drag.ghost = document.createElement('div'); drag.ghost.className='ppn ppn-drag-ghost';drag.ghost.inert=true;drag.ghost.setAttribute('aria-hidden','true');
                const copy=node.cloneNode(true);copy.removeAttribute('id');copy.removeAttribute('aria-current');copy.removeAttribute('data-ppn-drag');drag.ghost.append(copy);
                drag.caption=document.createElement('div');drag.caption.className='ppn-drag-caption';drag.ghost.append(drag.caption);
                drag.ghost.style.width=startRect.width+'px';document.body.append(drag.ghost);
                drag.line=document.createElement('div');drag.line.className='ppn-drop-line';document.body.append(drag.line);
                live.textContent=node.dataset.ppnDrag==='client'?'正在拖动端分组':'拖到中间成为子页面，上下边缘同级排序';tick();
            }
            function tick(schedule=true) {
                if (!drag?.started) return;
                const d=drag, r=host.getBoundingClientRect();
                d.ghost.style.transform=`translate3d(${d.x-(d.startX-startRect.left)+4}px,${d.y-(d.startY-startRect.top)+4}px,0)`;
                const inPanel=d.x>=r.left-18 && d.x<=r.right+18;
                if(inPanel){const edge=38;const delta=d.y<r.top+edge?-Math.min(9,(r.top+edge-d.y)/4):d.y>r.bottom-edge?Math.min(9,(d.y-r.bottom+edge)/4):0;host.scrollTop+=delta;}
                host.querySelectorAll('.ppn-drop-inside,.ppn-drop-invalid,.ppn-root-active').forEach(n=>n.classList.remove('ppn-drop-inside','ppn-drop-invalid','ppn-root-active'));
                const kind=node.dataset.ppnDrag, candidates=Array.from(host.querySelectorAll('[data-ppn-drag]')).filter(n=>n.dataset.ppnDrag===kind && n.getClientRects().length);
                let closest=null, distance=Infinity, request=null, caption='', inside=false;
                const rootTarget=kind==='page'&&inPanel?Array.from(host.querySelectorAll('[data-ppn-root]')).find(n=>{const cr=n.getBoundingClientRect();return cr.height&&d.y>=cr.top&&d.y<=cr.bottom;}):null;
                if(rootTarget){request={kind,id:node.dataset.dragId,targetId:rootTarget.dataset.ppnRoot,position:'root'};closest=rootTarget;caption='移到“'+rootTarget.querySelector('span')?.textContent+'”顶层';}
                else if(inPanel && d.y>=r.top && d.y<=r.bottom)for(const candidate of candidates){const cr=candidate.getBoundingClientRect(),dist=Math.abs(d.y-(cr.top+cr.height/2));if(dist<distance&&d.y>=cr.top-8&&d.y<=cr.bottom+8){distance=dist;closest=candidate;}}
                if(closest&&!rootTarget){const cr=closest.getBoundingClientRect(),part=(d.y-cr.top)/cr.height;inside=kind==='page'&&part>.25&&part<.75&&node.dataset.dragGroup!=='__launchers';
                    const position=inside?'inside':part<.5?'before':'after';request={kind,id:node.dataset.dragId,targetId:closest.dataset.dragId,position};
                    const title=closest.querySelector('.ppn-title')?.textContent || closest.textContent;caption=inside?'移入“'+title+'”':'放在“'+title+'”'+(position==='before'?'之前':'之后');
                }
                const error=request?reorderError(options.project,request):'', valid=request&&!error;
                d.error=error;d.drop=valid?request:null;d.line.hidden=true;
                if(closest&&request){
                    if(inside)closest.classList.add(error?'ppn-drop-invalid':'ppn-drop-inside');
                    else if(rootTarget)rootTarget.classList.add(error?'ppn-drop-invalid':'ppn-root-active');
                    else if(valid){const cr=closest.getBoundingClientRect(),after=request.position==='after';let bottom=cr.bottom;if(after&&kind==='page')bottom=closest.closest('.ppn-branch').getBoundingClientRect().bottom;d.line.hidden=false;d.line.style.cssText=`left:${cr.left+4}px;top:${after?bottom:cr.top}px;width:${cr.width-8}px`;}
                }
                const expandId=valid&&inside?request.targetId:'';
                if(d.expandId!==expandId){clearTimeout(d.expandTimer);d.expandId=expandId;if(expandId&&closedPages.has(expandId))d.expandTimer=setTimeout(()=>{if(!drag||drag.expandId!==expandId)return;closedPages.delete(expandId);const branch=closest.closest('.ppn-branch'),children=branch.querySelector(':scope > .ppn-children'),toggle=branch.querySelector(':scope > .ppn-item-wrap > .ppn-expand');if(children)children.hidden=false;if(toggle){toggle.setAttribute('aria-expanded','true');toggle.setAttribute('aria-label',toggle.getAttribute('aria-label').replace(/^展开/,'收起'));}},650);}
                const message=error || caption || '中间移入 · 边缘排序 · 最多三级';d.caption.textContent=message;if(d.message!==message){live.textContent=message;d.message=message;}
                d.ghost.classList.toggle('ppn-no-drop',!d.drop);if(schedule)d.raf=requestAnimationFrame(tick);
            }
            const touchHandle=event.target.closest('.ppn-page-icon');
            if(event.pointerType==='touch'&&!touchHandle) drag.timer=setTimeout(start,300);
            window.addEventListener('pointermove', e=>{if(!drag||e.pointerId!==drag.pointerId)return;drag.x=e.clientX;drag.y=e.clientY;if(!drag.started&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)>6){if(event.pointerType==='touch'&&!touchHandle){endDrag(true);return;}start();}if(drag?.started)e.preventDefault();},{passive:false,signal:controller.signal});
            window.addEventListener('pointerup',e=>{if(drag&&e.pointerId===drag.pointerId){drag.x=e.clientX;drag.y=e.clientY;if(drag.started)tick(false);endDrag();}},{signal:controller.signal});
            window.addEventListener('pointercancel',()=>endDrag(true),{signal:controller.signal});
            node.addEventListener('lostpointercapture',()=>endDrag(true),{signal:controller.signal});
            window.addEventListener('blur',()=>endDrag(true),{signal:controller.signal});
            document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();endDrag(true);}},{signal:controller.signal});
        }
        host.addEventListener('pointerdown',event=>{suppressClick=false;const node=event.target.closest('[data-ppn-drag]');if(!node||!options.onReorder||saving||drag||event.button!==0||event.isPrimary===false)return;beginDrag(event,node);});
        host.addEventListener('click',event=>{if(suppressClick){suppressClick=false;event.preventDefault();event.stopImmediatePropagation();}},true);
        host.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key))suppressClick=false;},true);
        host.addEventListener('contextmenu',event=>{if(drag?.started)event.preventDefault();});
        host.addEventListener('keydown',event=>{
            if(!event.altKey||!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)||!options.onReorder)return;
            const node=event.target.closest('[data-ppn-drag]');if(!node)return;event.preventDefault();event.stopImmediatePropagation();
            const kind=node.dataset.ppnDrag,id=node.dataset.dragId,tree=pageTree(options.project),branch=tree.nodes.get(id);
            const siblings=Array.from(host.querySelectorAll('[data-ppn-drag]')).filter(n=>n.dataset.ppnDrag===kind && (kind==='client'||(n.dataset.dragGroup===node.dataset.dragGroup&&n.dataset.parentId===node.dataset.parentId)));
            const i=siblings.indexOf(node);let target,position;
            if(event.key==='ArrowLeft'&&kind==='page'){target=branch?.parentId;position='after';}
            else if(event.key==='ArrowRight'&&kind==='page'){target=siblings[i-1]?.dataset.dragId;position='inside';}
            else if(['ArrowUp','ArrowDown'].includes(event.key)){target=siblings[i+(event.key==='ArrowUp'?-1:1)]?.dataset.dragId;position=event.key==='ArrowUp'?'before':'after';}
            if(target)commit({kind,id,targetId:target,position},node.dataset.ppnKey);
        },true);
        function revealAncestors(pageId){const tree=pageTree(options.project);let node=tree.nodes.get(pageId);while(node?.parentId){closedPages.delete(node.parentId);node=tree.nodes.get(node.parentId);}}
        let revealedPage='';
        function update(next){if(drag)endDrag(true);const previous=options.currentPage,previousClient=options.project.pages?.find(p=>p.id===previous)?.clientId;options=next;const p=next.project.pages?.find(p=>p.id===next.currentPage);if(filter && p?.clientId!==filter && (previous!==next.currentPage||previousClient!==p?.clientId))filter=p?.clientId || '';if(p?.clientId)memory.set(p.clientId,{pageId:p.id,stateId:next.currentState});if(revealedPage!==next.currentPage){revealAncestors(next.currentPage);revealedPage=next.currentPage;}render();}
        host.addEventListener('keydown',e=>{if(e.defaultPrevented||!['ArrowDown','ArrowUp','Home','End'].includes(e.key)||e.target.getAttribute('role')==='combobox')return;const buttons=Array.from(host.querySelectorAll('button')).filter(b=>b.getClientRects().length);const i=buttons.indexOf(e.target);if(i<0)return;e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,i+(e.key==='ArrowDown'?1:-1)));buttons[n]?.focus();});
        update(initial);
        return {update, reveal(pageId){const p=options.project.pages.find(p=>p.id===pageId);if(filter && p?.clientId!==filter)filter='';closed.delete(p?.clientId || '__ungrouped');revealAncestors(pageId);render();}};
    }
    function fitDevice(device, canvas, width, height) {
        function fit() {
            const css=getComputedStyle(canvas);
            const availableWidth=canvas.clientWidth-(parseFloat(css.paddingLeft)||0)-(parseFloat(css.paddingRight)||0);
            const availableHeight=canvas.clientHeight-(parseFloat(css.paddingTop)||0)-(parseFloat(css.paddingBottom)||0);
            device.style.zoom=String(Math.max(.05,Math.min(1,availableWidth/width,availableHeight/height)));
        }
        const observer=new ResizeObserver(fit);observer.observe(canvas);
        window.addEventListener('resize',fit);fit();
        return {destroy(){observer.disconnect();window.removeEventListener('resize',fit);device.style.zoom='';}};
    }
    const previewDevices=new WeakMap();
    function applyPreview(frame, type, shell=true) {
        previewDevices.get(frame)?.destroy();previewDevices.delete(frame);
        const canvas=frame.parentElement;
        canvas.classList.add('ppn-canvas');canvas.classList.toggle('ppn-mobile',type==='mobile');canvas.classList.toggle('ppn-pad',type==='pad');canvas.classList.toggle('ppn-shell',['mobile','pad'].includes(type) && shell);
        if(type==='pad')previewDevices.set(frame,fitDevice(frame,canvas,shell?1220:1180,shell?860:820));
    }
    window.ProtoProjectNavigation = {mount, defaultPage, applyPreview, fitDevice, createSelect, positionPopup, reorderProject, reorderError, pageTree, subtreePages, updatePageNavigation, createPageTracking};
})();
