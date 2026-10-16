/* 首页界面组件；业务操作与保存继续由 script.js 负责。 */
(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const paths = {
        folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3V7Z"/>',
        open: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="3"/>',
        publish: '<path d="M12 16V3m-4 4 4-4 4 4M4 14v6h16v-6"/>',
        remove: '<path d="m4 4 16 16M8 8l-2 2a4 4 0 0 0 6 6l2-2M16 16l2-2a4 4 0 0 0-6-6l-2 2"/>',
        delete: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
        edit: '<path d="m15 4 5 5M4 20l5-1L20 8a3.5 3.5 0 0 0-5-5L4 14v6Z"/>',
        copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
        history: '<path d="M3 11a9 9 0 1 1 3 7M3 4v7h7M12 7v5l3 2"/>',
        refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5"/>',
        share: '<circle cx="5" cy="12" r="3"/><circle cx="19" cy="5" r="3"/><circle cx="19" cy="19" r="3"/><path d="m8 10 8-4M8 14l8 4"/>',
        connect: '<path d="m8 16 8-8M8 11l-2 2a4 4 0 0 0 6 6l2-2M16 13l2-2a4 4 0 0 0-6-6l-2 2"/>',
        check: '<path d="m5 12 4 4L19 6"/>',
        clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
        error: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16h.01"/>',
        spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
        model: '<rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/>',
        sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
        moon: '<path d="M20 14a8.5 8.5 0 0 1-10-10A9 9 0 1 0 20 14Z"/>',
        more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
        user: '<circle cx="12" cy="8" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>'
    };
    function icon(name) { return `<svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.folder}</svg>`; }
    function node(tag, cls, text) { const el = document.createElement(tag); if (cls) el.className = cls; if (text != null) el.textContent = text; return el; }
    function action(iconName, label, handler, options = {}) {
        const button = node('button', 'project-action');
        button.type = 'button'; button.title = label; button.setAttribute('aria-label', label);
        button.innerHTML = icon(iconName);
        button.disabled = !!options.disabled; if (options.danger) button.dataset.danger = 'true';
        button.onclick = event => { event.stopPropagation(); handler?.(); };
        return button;
    }
    function formatDate(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
    }
    let activeMenu = null;
    function closeMenu(restore = false) {
        if (!activeMenu) return;
        const { menu, trigger } = activeMenu; activeMenu = null;
        menu.remove(); trigger.setAttribute('aria-expanded', 'false');
        if (restore && trigger.isConnected) trigger.focus({ preventScroll: true });
    }
    function more(name, items) {
        const trigger = action('more', `更多操作 ${name}`, () => {
            if (activeMenu?.trigger === trigger) { closeMenu(true); return; }
            closeMenu();
            const menu = node('div', 'project-menu'); menu.setAttribute('role', 'menu');
            menu.setAttribute('aria-label', `${name}的操作`);
            items.forEach(item => {
                const button = node('button', 'project-menu-item'); button.type = 'button';
                button.setAttribute('role', 'menuitem'); button.disabled = !!item.disabled;
                button.innerHTML = icon(item.icon); button.append(node('span', '', item.label));
                if (item.danger) button.dataset.danger = 'true';
                button.onclick = () => { closeMenu(true); item.handler?.(); };
                menu.append(button);
            });
            document.body.append(menu); trigger.setAttribute('aria-expanded', 'true');
            activeMenu = { menu, trigger };
            const r = trigger.getBoundingClientRect(), m = menu.getBoundingClientRect();
            menu.style.left = Math.max(8, Math.min(r.right - m.width, innerWidth - m.width - 8)) + 'px';
            menu.style.top = (r.bottom + m.height + 8 < innerHeight ? r.bottom + 6 : Math.max(8, r.top - m.height - 6)) + 'px';
            menu.querySelector('button:not(:disabled)')?.focus({ preventScroll: true });
            menu.onkeydown = e => {
                const buttons = [...menu.querySelectorAll('button:not(:disabled)')];
                const i = buttons.indexOf(document.activeElement);
                if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
                    e.preventDefault(); buttons[e.key === 'Home' ? 0 : e.key === 'End' ? buttons.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
                } else if (e.key === 'Escape') { e.preventDefault(); closeMenu(true); }
                else if (e.key === 'Tab') closeMenu(true);
            };
        });
        trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
        return trigger;
    }
    const previewObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            previewObserver.unobserve(entry.target);
            loadPreview(entry.target);
        });
    }, { rootMargin: '120px' });
    async function loadPreview(cover) {
        const url = cover.dataset.preview;
        for (let attempt = 0; attempt < 10 && cover.isConnected; attempt++) {
            try {
                const response = await fetch(url, { cache: 'no-cache' });
                if (response.status === 202 || response.status === 429) {
                    await new Promise(r => setTimeout(r, Math.min(800 + attempt * 500, 4000))); continue;
                }
                if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/')) return;
                const objectURL = URL.createObjectURL(await response.blob());
                const img = node('img', 'project-thumbnail'); img.alt = ''; img.decoding = 'async';
                img.onload = () => { cover.classList.add('has-thumbnail'); URL.revokeObjectURL(objectURL); };
                img.onerror = () => { img.remove(); URL.revokeObjectURL(objectURL); };
                img.src = objectURL;
                if (cover.isConnected) cover.append(img); else URL.revokeObjectURL(objectURL);
                return;
            } catch (_) { return; }
        }
    }
    function card({ name, kind, badge, tone, badgeIcon, meta, detail, open, disabled, id, preview }) {
        const article = node('article', 'project-card' + (disabled ? ' is-unavailable' : ''));
        article.dataset.kind = kind; article.dataset.projectId = id || '';
        const button = node('button', 'project-card-open'); button.type = 'button'; button.disabled = !!disabled;
        button.setAttribute('aria-label', `${kind === 'ai' ? '预览' : '打开'} ${name}`); button.onclick = open;
        const cover = node('div', 'project-card-cover');
        const identity = node('div', 'project-identity');
        identity.append(node('span', 'project-monogram', [...(name || '原型').replace(/[^\p{L}\p{N}]/gu, '')][0] || '原'));
        const label = node('span', 'project-cover-kind'); label.innerHTML = icon(kind === 'ai' ? 'spark' : 'folder');
        label.append(document.createTextNode(kind === 'ai' ? 'AI 原型' : '本地原型')); identity.append(label); cover.append(identity);
        if (preview && !disabled) { cover.dataset.preview = '/api/home/thumbnail?' + new URLSearchParams(preview); previewObserver.observe(cover); }
        const status = node('span', 'project-badge'); status.dataset.tone = tone;
        status.innerHTML = icon(badgeIcon); status.append(document.createTextNode(badge));
        cover.append(status);
        const body = node('div', 'project-card-body');
        const title = node('h3', 'project-card-title', name); title.title = name; body.append(title);
        body.append(node('div', 'project-card-meta', meta));
        const path = node('div', 'project-card-path'); path.title = detail || ''; path.innerHTML = icon(kind === 'ai' ? 'model' : 'folder');
        path.append(node('span', '', detail || '')); body.append(path);
        button.append(cover, body); article.append(button);
        const actions = node('div', 'project-card-actions'); article.append(actions);
        return { article, actions };
    }
    function empty(container, title, description, buttonText, handler, iconName = 'folder') {
        clear(container); const el = node('div', 'library-empty');
        const image = node('div', 'library-empty-icon'); image.innerHTML = icon(iconName); el.append(image);
        el.append(node('h3', '', title), node('p', '', description));
        if (buttonText) { const button = node('button', 'app-button app-secondary', buttonText); button.type = 'button'; button.onclick = handler; el.append(button); }
        container.append(el);
    }
    const counts = { local: null, ai: null };
    let localFilter = null;
    function updateCounts(source, total, visible = total) {
        if (source === 'local' && localFilter) localFilter.setValue($('externalFilter').value);
        if (total != null) counts[source] = total;
        const badge = $(source === 'local' ? 'localProjectCount' : 'aiProjectCount');
        badge.hidden = counts[source] == null; badge.textContent = counts[source] ?? '';
        $(source === 'local' ? 'localResultCount' : 'aiResultCount').textContent = counts[source] == null ? '正在读取项目…' : `${visible ?? counts[source]} 个项目`;
    }
    let currentView = null, libraryScroll = 0;
    function clear(container) {
        closeMenu();
        container.querySelectorAll('.project-card-cover').forEach(cover => previewObserver.unobserve(cover));
        container.replaceChildren();
    }
    function loading(container) {
        if (container.querySelector('.project-card:not(.project-skeleton)')) return;
        container.replaceChildren();
        for (let i = 0; i < 8; i++) {
            const el = node('div', 'project-card project-skeleton'); el.setAttribute('aria-hidden', 'true');
            el.innerHTML = '<div class="project-card-cover"></div><div class="project-card-body"><i></i><i></i><i></i></div>';
            container.append(el);
        }
    }
    function route() {
        const next = location.hash === '#new' ? 'new' : 'projects';
        if (next === currentView) return;
        closeMenu();
        if (next === 'new') libraryScroll = scrollY;
        $('projectsView').hidden = next === 'new'; $('createView').hidden = next !== 'new';
        currentView = next; document.title = next === 'new' ? '新建项目 · 原型生成器' : '项目 · 原型生成器';
        summary();
        requestAnimationFrame(() => { window.scrollTo(0, next === 'new' ? 0 : libraryScroll); if (next === 'new') $('headerTitle').focus({ preventScroll: true }); });
    }
    function show(view) { const hash = view === 'new' ? '#new' : '#projects'; if (location.hash !== hash) location.hash = hash; route(); }
    function goHome(event) { event?.preventDefault(); show('projects'); }
    function setTheme(theme) {
        document.documentElement.dataset.homeTheme = theme;
        const button = $('homeThemeButton');
        button.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon');
        button.title = theme === 'dark' ? '切换浅色外观' : '切换深色外观'; button.setAttribute('aria-label', button.title);
    }
    function toggleTheme() {
        const theme = document.documentElement.dataset.homeTheme === 'dark' ? 'light' : 'dark';
        setTheme(theme); try { localStorage.setItem('prototype-home-theme', theme); } catch (_) { /* 外观仅保留在本次页面 */ }
    }
    function summary() {
        if (!$('summarySkill') || typeof pages === 'undefined') return;
        if ($('summaryProjectName')) {
            const name = getProjectNameFromForm();
            $('summaryProjectName').textContent = name;
            $('summaryProjectName').title = name;
        }
        $('summarySkill').textContent = $('skillSelect')?.selectedOptions[0]?.textContent || 'Web 原型';
        $('summaryDesign').textContent = $('designSystemPickerLabel')?.textContent || '默认风格';
        $('summaryPageCount').textContent = `${pages.length} ${$('skillSelect')?.value === 'html-ppt' ? '页 / 章节' : '页'}`;
        $('summaryImageCount').textContent = `${pages.reduce((sum, id) => sum + (pageFiles[id]?.length || 0) + (pagePptImages[id]?.length || 0), 0)} 张`;
        $('summaryModel').textContent = $('currentModelName')?.textContent || '未选择模型';
        const list = $('summaryPages'); list.replaceChildren();
        pages.forEach((id, i) => { const li = node('li'); li.append(node('span', '', i + 1), document.createTextNode($('pageName_' + id)?.value.trim() || `页面 ${i + 1}`)); list.append(li); });
    }
    function init() {
        const nativeFilter = $('externalFilter');
        if (nativeFilter && window.ProtoProjectNavigation?.createSelect) {
            const host = node('div', 'ppn library-filter-host');
            nativeFilter.after(host); nativeFilter.hidden = true;
            nativeFilter.parentElement.classList.add('is-enhanced');
            localFilter = ProtoProjectNavigation.createSelect(host, {
                label: nativeFilter.getAttribute('aria-label'), value: nativeFilter.value,
                items: [...nativeFilter.options].map(option => ({value: option.value, label: option.textContent})),
                onChange: value => { nativeFilter.value = value; nativeFilter.dispatchEvent(new Event('change', {bubbles: true})); }
            });
        }
        document.querySelectorAll('i[class*="fa"]').forEach(icon => icon.setAttribute('aria-hidden', 'true'));
        $('userMenuBtn').innerHTML = icon('user');
        updateCounts('local'); updateCounts('ai');
        const openDialogs = new Map();
        document.querySelectorAll('[id$="Modal"]').forEach(dialog => {
            const heading = dialog.querySelector('h2, h3');
            const close = dialog.querySelector('button[onclick^="close"]');
            if (!heading || !close) return;
            dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true');
            heading.id ||= dialog.id + 'Title'; dialog.setAttribute('aria-labelledby', heading.id);
            if (!close.getAttribute('aria-label')) close.setAttribute('aria-label', '关闭' + heading.textContent.trim());
            new MutationObserver(() => {
                const visible = !dialog.classList.contains('hidden');
                if (visible && !openDialogs.has(dialog)) {
                    openDialogs.set(dialog, document.activeElement);
                    close.focus({preventScroll: true});
                } else if (!visible && openDialogs.has(dialog)) {
                    const previous = openDialogs.get(dialog); openDialogs.delete(dialog);
                    if (previous?.isConnected) previous.focus({preventScroll: true});
                }
            }).observe(dialog, {attributes: true, attributeFilter: ['class']});
        });
        document.addEventListener('keydown', event => {
            const dialog = [...openDialogs.keys()].at(-1);
            if (!dialog) return;
            if (event.key === 'Escape') {
                event.preventDefault(); event.stopPropagation();
                dialog.querySelector('button[onclick^="close"]')?.click();
            } else if (event.key === 'Tab') {
                const controls = [...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(el => el.getClientRects().length);
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
            }
        });
        loading($('externalList')); loading($('projectList'));
        document.addEventListener('pointerdown', event => { if (activeMenu && !activeMenu.menu.contains(event.target) && !activeMenu.trigger.contains(event.target)) closeMenu(); });
        document.addEventListener('focusin', event => { if (activeMenu && !activeMenu.menu.contains(event.target) && event.target !== activeMenu.trigger) closeMenu(); });
        window.addEventListener('scroll', () => closeMenu(), true);
        window.addEventListener('resize', () => closeMenu());
        document.querySelector('.workspace-tabs').addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const tabs = [$('tabSourceLocal'), $('tabSourceAi')];
            const target = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[1] : tabs[1 - tabs.indexOf(document.activeElement)];
            target?.click(); target?.focus();
        });
        document.querySelectorAll('[data-home-icon]').forEach(element => { element.innerHTML = icon(element.dataset.homeIcon); });
        document.documentElement.dataset.homeInput = 'pointer';
        document.addEventListener('pointerdown', () => { document.documentElement.dataset.homeInput = 'pointer'; }, true);
        document.addEventListener('keydown', event => { if (event.key === 'Tab') document.documentElement.dataset.homeInput = 'keyboard'; }, true);
        let theme = 'light'; try { theme = localStorage.getItem('prototype-home-theme') || theme; } catch (_) { /* 使用浅色 */ }
        setTheme(theme === 'dark' ? 'dark' : 'light');
        route(); window.addEventListener('hashchange', route);
        document.addEventListener('input', summary); document.addEventListener('change', () => queueMicrotask(summary));
        new MutationObserver(summary).observe($('pageCardsContainer'), { childList: true, subtree: true });
        new MutationObserver(summary).observe($('currentModelName'), { childList: true, subtree: true });
        new MutationObserver(summary).observe($('designSystemPickerLabel'), { childList: true, subtree: true });
        document.addEventListener('keydown', event => {
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.isComposing || $('projectsView').hidden) return;
            if (event.target.closest('input, textarea, select, [contenteditable="true"]') || document.querySelector('[id$="Modal"].flex')) return;
            event.preventDefault(); document.documentElement.dataset.homeInput = 'keyboard'; ($('tabSourceLocal').getAttribute('aria-selected') === 'true' ? $('externalSearch') : $('projectSearch')).focus();
        });
    }
    window.HomeUI = { icon, action, more, closeMenu, clear, loading, card, empty, formatDate, updateCounts, show, goHome, toggleTheme, summary, init };
})();
