/* 工作台共用的 Markdown 阅读、持久草稿与单编辑会话。 */
(() => {
    'use strict';
    const CDN = new URL('/src/vendor/vditor', location.href).href;
    const PREFIX = 'prototype-markdown-draft-v1:';
    const drafts = new Map(), regions = new WeakMap();
    let session = null;
    const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const key = (projectId, pageId, stateId, itemId) => JSON.stringify([projectId, pageId, stateId, itemId]);
    function getDraft(id) {
        if (drafts.has(id)) return drafts.get(id);
        try {
            const value = JSON.parse(localStorage.getItem(PREFIX + id) || 'null');
            if (value && typeof value.value === 'string' && typeof value.base === 'string') { drafts.set(id, value); return value; }
        } catch (_) { /* 存储不可读时使用本页内存。 */ }
        return null;
    }
    function putDraft(id, value) {
        if (value) drafts.set(id, value); else drafts.delete(id);
        try {
            if (value) localStorage.setItem(PREFIX + id, JSON.stringify(value));
            else localStorage.removeItem(PREFIX + id);
            return true;
        } catch (_) { return false; }
    }
    /* 文字颜色：正文里存为内联 <span style="color:#hex">…</span>（标准 Markdown 没有颜色语法，这是各家渲染器都认的写法）。
       安全策略对原始 HTML 一律当代码文本显示，唯一放行这两个形态；进 DOMPurify 后只保留 span 上的 color。 */
    const COLOR_OPEN = /^<span style="color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)">$/, COLOR_CLOSE = /^<\/span>$/;
    const COLOR_STYLE = /^\s*color\s*:\s*(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\s*;?\s*$/;
    async function safeHTML(markdown, assetBase = '') {
        const raw = (node, entering) => [entering ? `<code>${escape(node.TokensStr())}</code>` : '', Lute.WalkContinue];
        const inline = (node, entering) => {
            if (!entering) return ['', Lute.WalkContinue];
            const t = node.TokensStr();
            return [COLOR_OPEN.test(t) || COLOR_CLOSE.test(t) ? t : `<code>${escape(t)}</code>`, Lute.WalkContinue];
        };
        const html = await Vditor.md2html(markdown, {
            cdn: CDN, markdown: { sanitize: true, autoSpace: false, fixTermTypo: false, codeBlockPreview: false, mathBlockPreview: false },
            renderers: { renderHTML: raw, renderInlineHTML: inline }
        });
        const fragment = DOMPurify.sanitize(html, {
            RETURN_DOM_FRAGMENT: true,
            ALLOWED_TAGS: ['p','br','h1','h2','h3','h4','h5','h6','strong','em','s','del','a','blockquote','ul','ol','li','input','table','thead','tbody','tr','th','td','pre','code','hr','span','img'],
            ALLOWED_ATTR: ['href','title','type','checked','disabled','start','style','src','alt'], ALLOW_DATA_ATTR: false
        });
        fragment.querySelectorAll('[style]').forEach(el => {
            const m = el.tagName === 'SPAN' && COLOR_STYLE.exec(el.getAttribute('style') || '');
            if (m) el.setAttribute('style', `color:${m[1].toLowerCase()}`); else el.removeAttribute('style');
        });
        fragment.querySelectorAll('a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!/^(https?:\/\/|mailto:|#)/i.test(href.trim())) a.removeAttribute('href');
            else { a.rel = 'noopener noreferrer'; if (!href.startsWith('#')) a.target = '_blank'; }
        });
        fragment.querySelectorAll('input').forEach(el => { el.type = 'checkbox'; el.disabled = true; });
        fragment.querySelectorAll('img').forEach(img => {
            const src = img.getAttribute('src') || '';
            if (!assetBase || !/^prd-assets\/[a-f0-9]{64}\.(png|jpg|gif|webp)$/.test(src)) { img.remove(); return; }
            img.src = new URL(src, new URL(assetBase, location.href)).href;
            const title = img.getAttribute('title') || '', size = /(?:^|\s)proto-width=(\d{1,4})$/.exec(title);
            if (size && +size[1] >= 48 && +size[1] <= 4096) {
                img.width = +size[1];
                img.title = title.slice(0, size.index).trim();
            }
            img.loading = 'lazy'; img.decoding = 'async';
        });
        return fragment;
    }
    function owns(region) { return !!session && (session.region === region || region?.contains?.(session.region)); }
    function focus() { session?.frame.contentWindow?.ProtoEditor?.focus(); }
    async function render(region, options) {
        let entry = regions.get(region);
        if (!entry) {
            entry = {}; regions.set(region, entry);
            // 双击（多击）不触发原生整段选中：.proto-md 是 role=button 的双击编辑区，双击会选中其全部文本，
            // 一旦焦点离开（编辑器接管 / 未进编辑）整段就以灰色失活选区显示（用户所说的“灰底”）；
            // 仅拦第二击及以后（detail>1），不影响单击拖选复制与 dblclick 进编辑。
            region.addEventListener('mousedown', e => { if (e.detail > 1 && !e.target.closest('a,button,input,iframe')) e.preventDefault(); });
            region.addEventListener('dblclick', e => { if (!e.target.closest('a,button,input,iframe')) begin(region, entry.options); });
            region.addEventListener('keydown', e => {
                if (e.target === region && e.key === 'Enter' && !e.isComposing && !e.repeat) { e.preventDefault(); begin(region, entry.options); }
            });
        }
        entry.options = options;
        region.classList.add('proto-md');
        region.dataset.theme = options.theme || 'light';
        if (owns(region)) return;
        region.tabIndex = options.readonly ? -1 : 0;
        region.setAttribute('role', options.readonly ? 'article' : 'button');
        region.setAttribute('aria-label', options.label + (options.readonly ? '，已确认，只读' : '，双击或按回车编辑'));
        const draft = options.key && getDraft(options.key);
        const signature = JSON.stringify([options.value, !!draft, options.readonly]);
        if (entry.signature === signature) return;
        entry.signature = signature;
        const generation = entry.generation = {};
        const doc = region.ownerDocument, body = doc.createElement('div');
        body.className = 'proto-md-body';
        try { if (options.value) body.appendChild(await safeHTML(options.value, options.assetBase)); else body.textContent = options.empty || '双击添加说明'; }
        catch (_) { body.textContent = options.value || '本地编辑资源不可用，请刷新重试。'; }
        if (owns(region) || entry.generation !== generation) return;
        region.replaceChildren(body);
        if (draft && !options.readonly) {
            const badge = doc.createElement('div'); badge.className = 'proto-md-draft';
            badge.textContent = '有未提交草稿 · 双击恢复'; region.appendChild(badge);
        }
    }
    function capture(s) {
        const api = s.frame.contentWindow?.ProtoEditor;
        if (s.ready && api) s.value = api.value();
        if (s.value !== s.saved || s.options.extra) {
            const durable = putDraft(s.key, { value: s.value, base: s.saved, extra: s.options.extra || null });
            if (!durable) s.notice = '草稿暂存于本页，刷新前请复制正文。';
        } else putDraft(s.key, null);
    }
    function schedule(s) {
        clearTimeout(s.timer);
        if (s.options.autosave && !s.composing && !s.conflict && s.value !== s.saved) s.timer = setTimeout(() => save(false, s), 1200);
    }
    function finish(s, saved = false) {
        clearTimeout(s.timer); clearTimeout(s.loading);
        if (session === s) session = null;
        closePop(s);
        s.unfollow?.(); s.toolbar?.remove(); s.handle?.remove(); s.handle = null;
        try { s.frame.contentWindow?.ProtoEditor?.destroy(); } catch (_) { /* 载入中也可关闭。 */ }
        s.frame._markdownBridge = null; s.frame.remove();
        s.region.classList.remove('is-editing');
        const entry = regions.get(s.region);
        if (entry) { entry.signature = null; render(s.region, { ...entry.options, value: saved ? s.saved : entry.options.value }); }
        s.options.onEnd?.(saved);
    }
    const ICON = body => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
    /* 工具条命令（由编辑器 markdown-editor.js 执行）：
       块样式 p / h1-h3 / ul / ol / task 只改光标所在的那一行（源码层改写，Enter 换出的新行不联动上一行）；
       color / table 是弹层入口（色板 / 行列选择器，光标在表格内时换成行列增删）。 */
    const COMMANDS = [
        ['p', '正文', ICON('<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>')],
        ['h1', '一级标题', ICON('<path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="m17 12 3-2v8"/>')],
        ['h2', '二级标题', ICON('<path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="M21 18h-4c0-4 4-3 4-6 0-1.5-2-2.5-4-1"/>')],
        ['h3', '三级标题', ICON('<path d="M4 12h8"/><path d="M4 18V6"/><path d="M12 18V6"/><path d="M17.5 10.5c1.7-1 3.5 0 3.5 1.5a2 2 0 0 1-2 2"/><path d="M17 17.5c2 1.5 4 .3 4-1.5a2 2 0 0 0-2-2"/>')],
        '|',
        ['bold', '加粗', ICON('<path d="M6 12h9a4 4 0 0 1 0 8H6z"/><path d="M6 4h8a4 4 0 0 1 0 8H6z"/>')],
        ['italic', '斜体', ICON('<path d="M19 4h-9"/><path d="M14 20H5"/><path d="M15 4 9 20"/>')],
        ['color', '文字颜色', ICON('<path d="M4 20h16"/><path d="m6 16 6-12 6 12"/><path d="M8 12h8"/>')],
        '|',
        ['link', '链接', ICON('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>')],
        ['image', '插入图片', ICON('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/>')],
        ['ul', '无序列表', ICON('<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>')],
        ['ol', '有序列表', ICON('<path d="M10 12h11"/><path d="M10 18h11"/><path d="M10 6h11"/><path d="M4 10h2"/><path d="M4 6h1v4"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>')],
        ['task', '任务列表', ICON('<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>')],
        ['table', '表格', ICON('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M12 3v18"/>')],
        '|',
        ['undo', '撤销', ICON('<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>')],
        ['redo', '重做', ICON('<path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/>')],
    ];
    const BLOCKS = ['p', 'h1', 'h2', 'h3', 'ul', 'ol', 'task'];
    /* 色板：DESIGN_MASTER 浅色 token（白底均 ≥ 4.5:1）；正文里存浅色值，暗色主题由 proto-markdown.css 按值映射成暗色对应色 */
    const COLORS = window.ProtoAppearance?.TEXT_COLORS || [];
    const TABLE_OPS = [['row-above', '上方插行'], ['row-below', '下方插行'], ['row-del', '删除本行'], ['col-left', '左侧插列'], ['col-right', '右侧插列'], ['col-del', '删除本列'], ['table-del', '删除整个表格']];
    const GRID_COLS = 8, GRID_ROWS = 6;
    const run = (s, name) => s.frame.contentWindow?.ProtoEditor?.command?.(name);
    function closePop(s) {
        if (!s.pop) return;
        s.pop.el.remove(); s.pop.off(); s.pop = null;
        for (const host of [s.toolbar, s.handle]) host?.querySelectorAll('button[aria-expanded]').forEach(b => b.setAttribute('aria-expanded', 'false'));
    }
    /* 工具条弹层：挂在按钮所在容器（工具条 / 表格角标）下方、与按钮左对齐；底部放不下翻到上方，右侧超出往左挑。
       关闭：弹层外 pointerdown（捕获）、Esc、窗口失焦（点进编辑器 iframe）、再点同一按钮。 */
    function openPop(s, btn, kind, fill) {
        if (s.pop?.kind === kind && s.pop.anchor === btn) { closePop(s); return; }
        closePop(s);
        const host = btn.closest('.proto-md-toolbar, .proto-md-handle') || s.toolbar;
        const doc = host.ownerDocument, win = doc.defaultView, pop = doc.createElement('div');
        pop.className = `proto-md-pop proto-md-pop-${kind}`; pop.setAttribute('role', 'dialog');
        pop.setAttribute('data-prototype-owned', '');
        fill(pop);
        host.appendChild(pop);
        btn.setAttribute('aria-expanded', 'true');
        // 表格角标在表格右上角：弹层右对齐往左展开（落在表格上方），左侧放不下再改左对齐；工具条上的弹层与按钮左对齐
        const fromHandle = host.classList.contains('proto-md-handle');
        if (fromHandle) { pop.style.left = 'auto'; pop.style.right = '0'; } else pop.style.left = btn.offsetLeft + 'px';
        const r = pop.getBoundingClientRect?.();
        if (r) {
            if (r.bottom > win.innerHeight - 4) pop.classList.add('is-above');
            if (fromHandle) { if (r.left < 4) { pop.style.right = 'auto'; pop.style.left = '0'; } }
            else if (r.right > win.innerWidth - 4) pop.style.left = Math.max(0, btn.offsetLeft - (r.right - win.innerWidth + 4)) + 'px';
        }
        const down = e => { if (!pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) closePop(s); };
        // Esc 只关弹层：工具条按钮不夺焦点，按键落在编辑器 iframe 里，那边 document 捕获的 Esc 会取消整次编辑；
        // 挂到它的 window 捕获阶段（先于 document）并截断，父页同理（避免工作台的 Esc 连带关卡）
        const key = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); closePop(s); } };
        const blur = () => { if (doc.activeElement?.matches('input[type="color"]')) return; closePop(s); };
        // 点回编辑器：父文档收不到 iframe 内的 pointerdown，同源编辑器文档也挂一份
        let fdoc = null; try { fdoc = s.frame.contentDocument; } catch (_) { /* 载入中 */ }
        const fwin = fdoc?.defaultView || null;
        win.addEventListener('pointerdown', down, true); win.addEventListener('keydown', key, true); win.addEventListener('blur', blur);
        fdoc?.addEventListener('pointerdown', down, true); fwin?.addEventListener('keydown', key, true);
        s.pop = { kind, anchor: btn, el: pop, off() {
            win.removeEventListener('pointerdown', down, true); win.removeEventListener('keydown', key, true); win.removeEventListener('blur', blur);
            fdoc?.removeEventListener('pointerdown', down, true); fwin?.removeEventListener('keydown', key, true);
        } };
    }
    function popButton(doc, label, onClick) {
        const b = doc.createElement('button'); b.type = 'button'; b.textContent = label; b.setAttribute('aria-label', label); b.title = label;
        b.onclick = onClick; return b;
    }
    function colorPop(s, btn) {
        openPop(s, btn, 'color', pop => {
            const doc = pop.ownerDocument, row = doc.createElement('div'); row.className = 'proto-md-swatches';
            for (const [hex, label] of COLORS) {
                const b = popButton(doc, label, () => { closePop(s); run(s, `color:${hex}`); });
                b.textContent = ''; b.className = 'proto-md-swatch'; b.dataset.color = hex;
                b.setAttribute('aria-pressed', String((s.state?.color || COLORS[0][0]) === hex));
                if (hex) b.style.setProperty('--swatch', hex);
                row.appendChild(b);
            }
            const custom = doc.createElement('label'); custom.className = 'proto-md-swatch proto-md-custom'; custom.title = '自定义颜色';
            const input = doc.createElement('input'); input.type = 'color'; input.value = s.state?.color || COLORS[0][0]; input.setAttribute('aria-label', '自定义文字颜色');
            input.onchange = () => { const hex = input.value; closePop(s); run(s, `color:${hex}`); };
            custom.appendChild(input); row.appendChild(custom);
            pop.appendChild(row);
            const reset = popButton(doc, '恢复默认颜色', () => { closePop(s); run(s, 'color:'); });
            reset.className = 'proto-md-color-reset'; pop.appendChild(reset);
        });
    }
    /* 表内行列操作弹层：工具条表格按钮与表格左上角角标共用。增删都相对光标所在单元格（上 / 下插行、左 / 右插列），最后一项删整表 */
    function tableOpsPop(s, btn) {
        openPop(s, btn, 'table-ops', pop => {
            const doc = pop.ownerDocument, box = doc.createElement('div'); box.className = 'proto-md-ops';
            for (const [name, label] of TABLE_OPS) { const b = popButton(doc, label, () => { closePop(s); run(s, name); }); b.dataset.op = name; box.appendChild(b); }
            pop.appendChild(box);
        });
    }
    function tablePop(s, btn) {
        if (s.state?.table) { tableOpsPop(s, btn); return; }
        openPop(s, btn, 'table-grid', pop => {
            const doc = pop.ownerDocument, grid = doc.createElement('div'), hint = doc.createElement('div');
            grid.className = 'proto-md-grid'; grid.style.setProperty('--cols', GRID_COLS);
            hint.className = 'proto-md-grid-hint'; hint.textContent = '选择行 × 列（含表头行）';
            const cells = [];
            const mark = (r, c) => { for (const cell of cells) cell.classList.toggle('is-on', cell.r <= r && cell.c <= c); hint.textContent = r && c ? `${r} 行 × ${c} 列` : '选择行 × 列（含表头行）'; };
            for (let r = 1; r <= GRID_ROWS; r++) for (let c = 1; c <= GRID_COLS; c++) {
                const cell = popButton(doc, `${r} 行 ${c} 列`, () => { closePop(s); run(s, `table:${r}:${c}`); });
                cell.textContent = ''; cell.r = r; cell.c = c;
                cell.onpointerenter = () => mark(r, c); cell.onfocus = () => mark(r, c);
                cells.push(cell); grid.appendChild(cell);
            }
            grid.onpointerleave = () => mark(0, 0);
            pop.append(grid, hint);
        });
    }
    /* 按编辑器上报的光标所在块类型点亮对应按钮；光标在表格内时表格按钮变为“表格行列” */
    function syncToolbar(s) {
        const bar = s.toolbar; if (!bar?.querySelectorAll) return;
        const st = s.state || {};
        bar.querySelectorAll('button[data-command]').forEach(b => {
            const name = b.dataset.command;
            if (BLOCKS.includes(name)) b.setAttribute('aria-pressed', String(st.block === name));
            if (name === 'table') { b.setAttribute('aria-pressed', String(!!st.table)); b.title = st.table ? '表格行列' : '表格'; b.setAttribute('aria-label', b.title); }
        });
    }
    /* 表格角标：光标进入表格后在表格右上角（父页文档，不被编辑器 iframe 裁掉）钉一个小图标，点开行列操作弹层；
       位置 = 编辑器 iframe 在父页的坐标 + 编辑器上报的表格坐标，跟随滚动 / 卡片拖动 / 内容重排；光标离开表格即收。
       放右上角（用户择定）：左上角会压住表头首列的文字起笔处。 */
    function placeHandle(s) {
        const st = s.state;
        if (!st?.table || !st.rect || !s.ready || session !== s) {
            if (s.handle) { if (s.pop && s.handle.contains(s.pop.el)) closePop(s); s.handle.remove(); s.handle = null; }
            return;
        }
        if (!s.handle) {
            const doc = s.region.ownerDocument, box = doc.createElement('div'), b = doc.createElement('button');
            box.className = 'proto-md-handle'; box.dataset.theme = s.options.theme || 'light';
            box.setAttribute('data-prototype-owned', '');
            box.addEventListener('pointerdown', e => { if (e.target.closest?.('button')) e.preventDefault(); });
            b.type = 'button'; b.dataset.command = 'table-handle';
            b.title = '表格操作'; b.setAttribute('aria-label', '表格操作：增删行列、删除表格');
            b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false');
            b.innerHTML = ICON('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>');
            b.onclick = () => tableOpsPop(s, b);
            box.appendChild(b); doc.documentElement.appendChild(box); s.handle = box;
        }
        const fr = s.frame.getBoundingClientRect(), size = s.handle.offsetWidth || 22;
        s.handle.style.left = Math.round(fr.left + st.rect.left + st.rect.width - size / 2) + 'px';
        s.handle.style.top = Math.round(fr.top + st.rect.top - size / 2) + 'px';
    }
    function makeToolbar(s) {
        const doc = s.region.ownerDocument, bar = doc.createElement('div');
        bar.className = 'proto-md-toolbar'; bar.dataset.theme = s.options.theme || 'light';
        if (!s.region.closest('.pa-card') && s.region.closest('#prdSidebar, aside')) bar.classList.add('is-single-row');
        bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', 'Markdown 格式工具栏');
        bar.setAttribute('data-prototype-owned', '');
        // 按下按钮不夺焦点：编辑器 iframe 里的选区与光标原地保留，命令直接作用在当前行 / 选中文字上
        bar.addEventListener('pointerdown', e => { if (e.target.closest?.('button')) e.preventDefault(); });
        const grip = doc.createElement('span');
        grip.className = 'proto-md-grip'; grip.textContent = '⋮⋮'; grip.title = '拖动移动工具栏，双击归位';
        grip.tabIndex = 0; grip.setAttribute('role', 'button'); grip.setAttribute('aria-label', '移动工具栏，回车归位');
        const reset = () => { s.toolbarManual = false; closePop(s); placeToolbar(s); };
        grip.ondblclick = reset;
        grip.onkeydown = e => { if (e.key === 'Enter' || e.key === 'Escape') { e.preventDefault(); reset(); } };
        grip.onpointerdown = e => {
            if (e.button !== 0) return;
            e.preventDefault(); e.stopPropagation();
            closePop(s);
            const rect = bar.getBoundingClientRect(), dx = e.clientX - rect.left, dy = e.clientY - rect.top;
            s.toolbarManual = true; bar.style.width = rect.width + 'px';
            grip.setPointerCapture(e.pointerId);
            const move = ev => {
                if (ev.pointerId !== e.pointerId) return;
                placeToolbar(s, ev.clientX - dx, ev.clientY - dy);
            };
            const up = ev => {
                if (ev.pointerId !== e.pointerId) return;
                grip.removeEventListener('pointermove', move); grip.removeEventListener('pointerup', up);
                grip.removeEventListener('pointercancel', up); grip.removeEventListener('lostpointercapture', up);
            };
            grip.addEventListener('pointermove', move); grip.addEventListener('pointerup', up);
            grip.addEventListener('pointercancel', up); grip.addEventListener('lostpointercapture', up);
        };
        bar.appendChild(grip);
        let group = doc.createElement('div'); group.className = 'proto-md-tools-group'; bar.appendChild(group);
        for (const item of COMMANDS) {
            if (item === '|') {
                group = doc.createElement('div'); group.className = 'proto-md-tools-group'; bar.appendChild(group);
                const sep = doc.createElement('i'); sep.className = 'proto-md-sep'; group.appendChild(sep); continue;
            }
            const [name, label, icon] = item, b = doc.createElement('button');
            b.type = 'button'; b.dataset.command = name;
            b.setAttribute('aria-label', label); b.title = label;
            b.innerHTML = icon;
            if (name === 'color') { b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false'); b.onclick = () => colorPop(s, b); }
            else if (name === 'table') { b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false'); b.onclick = () => tablePop(s, b); }
            else b.onclick = () => { closePop(s); run(s, name); };
            group.appendChild(b);
        }
        doc.documentElement.appendChild(bar);
        return bar;
    }
    const TOOLBAR_GAP = 12;
    /* 工具条脱离正文布局；右栏在当前正文 / 标注序号上方，浮卡仍按外框避让。 */
    function placeToolbar(s, x, y) {
        const bar = s.toolbar; if (!bar) return;
        const doc = s.region.ownerDocument, win = doc.defaultView, EDGE = 4;
        const W = win.innerWidth, H = win.innerHeight;
        const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));
        const set = (left, top) => { bar.style.left = left + 'px'; bar.style.top = top + 'px'; };
        if (s.toolbarManual || x !== undefined) {
            const r = bar.getBoundingClientRect();
            set(clamp(x ?? r.left, EDGE, W - r.width - EDGE), clamp(y ?? r.top, EDGE, H - r.height - EDGE));
            return;
        }
        const card = s.region.closest('.pa-card'), panel = !card && s.region.closest('#prdSidebar, aside');
        const anchor = card || (panel && s.region.closest('.ext-note')?.querySelector('.ext-note-head')) || s.region;
        let rect = anchor.getBoundingClientRect();
        const avoid = [];
        const collect = (d, ox = 0, oy = 0, clip, sx = 1, sy = 1) => {
            for (const node of d.querySelectorAll('[data-proto-toolbar-avoid]')) {
                const r = node.getBoundingClientRect();
                if (!r.width || !r.height) continue;
                const box = { left: r.left * sx + ox, top: r.top * sy + oy, right: r.right * sx + ox, bottom: r.bottom * sy + oy };
                if (clip) {
                    box.left = Math.max(box.left, clip.left); box.top = Math.max(box.top, clip.top);
                    box.right = Math.min(box.right, clip.right); box.bottom = Math.min(box.bottom, clip.bottom);
                }
                if (box.right > box.left && box.bottom > box.top) avoid.push(box);
            }
        };
        collect(doc);
        for (const frame of doc.querySelectorAll('iframe')) {
            if (frame === s.frame) continue;
            try { if (frame.contentDocument) { const r = frame.getBoundingClientRect(), sx=r.width/(frame.offsetWidth || r.width) || 1, sy=r.height/(frame.offsetHeight || r.height) || 1; collect(frame.contentDocument,r.left+(frame.clientLeft || 0)*sx,r.top+(frame.clientTop || 0)*sy,r,sx,sy); } }
            catch (_) { /* 跨源原型不读取内部序号。 */ }
        }
        // 气泡工具条同时避开右侧 PRD 面板，避免跨到另一处正文上。
        if (card) {
            const sidebar = doc.getElementById('prdSidebar');
            if (sidebar?.getClientRects().length) avoid.push(sidebar.getBoundingClientRect());
        }
        const area = (c, r) => Math.max(0, Math.min(c.left + c.width, r.right) - Math.max(c.left, r.left)) *
            Math.max(0, Math.min(c.top + c.height, r.bottom) - Math.max(c.top, r.top));
        const measure = width => {
            bar.style.width = width ? width + 'px' : '';
            const bounds = bar.getBoundingClientRect();
            return { width: bounds.width, height: bounds.height };
        };
        const normal = measure();
        if (panel) {
            const size = normal;
            if (s.toolbarOpening) {
                s.toolbarOpening = false;
                const scroller = s.region.closest('#extReadingScroll') || panel;
                const minTop = Math.max(EDGE, scroller.getBoundingClientRect().top) + size.height + TOOLBAR_GAP;
                if (rect.top < minTop) {
                    scroller.scrollTop = Math.max(0, scroller.scrollTop - (minTop - rect.top));
                    rect = anchor.getBoundingClientRect();
                }
            }
            set(Math.min(rect.right, W - EDGE) - size.width, rect.top - size.height - TOOLBAR_GAP);
            return;
        }
        const candidates = [];
        const add = (left, top, size) => candidates.push({ left, top, ...size });
        const beside = (leftEdge, rightEdge, side) => {
            const space = side === 'left' ? leftEdge - TOOLBAR_GAP - EDGE : W - rightEdge - TOOLBAR_GAP - EDGE;
            if (space < 160) return;
            const size = measure(Math.min(normal.width, space));
            add(side === 'left' ? leftEdge - TOOLBAR_GAP - size.width : rightEdge + TOOLBAR_GAP,
                clamp(rect.top, EDGE, H - size.height - EDGE), size);
        };
        for (const top of [rect.top - normal.height - TOOLBAR_GAP, rect.bottom + TOOLBAR_GAP]) {
            for (const left of [rect.left, rect.right - normal.width]) add(clamp(left, EDGE, W - normal.width - EDGE), top, normal);
        }
        beside(rect.left, rect.right, 'right'); beside(rect.left, rect.right, 'left');
        const external = candidates.filter(c => area(c, rect) === 0);
        const inView = c => c.left >= EDGE && c.top >= EDGE && c.left + c.width <= W - EDGE + .5 && c.top + c.height <= H - EDGE + .5;
        const visible = external.filter(inView);
        const score = c => avoid.reduce((sum, r) => sum + area(c, r), 0);
        // 不再把屏内钳制后的工具条压回编辑框；极端满屏时仍保留外侧位置。
        const pool = visible.length ? visible : external;
        const chosen = pool.find(c => score(c) === 0) || pool.reduce((best, c) => !best || score(c) < score(best) ? c : best, null);
        if (chosen) { measure(chosen.width); set(chosen.left, chosen.top); }
    }
    function suspend(region) {
        const s = session;
        if (!s || (region && !owns(region))) return;
        capture(s);
        if (s.options.autosave && s.ready && !s.busy && !s.composing && !s.conflict &&
            s.value !== s.saved && (s.options.allowEmpty || s.value.trim())) {
            save(true, s).then(ok => { if (!ok && session === s) finish(s); });
            return;
        }
        finish(s);
    }
    async function save(close = true, s = session) {
        if (!s || !s.ready || s.composing) return false;
        clearTimeout(s.timer);
        if (s.busy) { if (close) s.closeRequested = true; return false; }
        capture(s);
        if (!s.options.allowEmpty && !s.value.trim()) { s.frame.contentWindow.ProtoEditor.status('正文不能为空。', true); return false; }
        if (!close && (s.conflict || s.value === s.saved)) return true;
        const snapshot = s.value;
        s.busy = true;
        if (close) s.frame.contentWindow.ProtoEditor.status('保存中…', false, true);
        let result = false;
        try { result = await s.options.save(snapshot); }
        catch (e) { s.notice = e.message || '保存失败'; }
        if (result && typeof result === 'object') {
            if (result.key && result.key !== s.key) {
                const d = getDraft(s.key); putDraft(s.key, null);
                s.key = result.key; s.options.extra = null;
                if (d) putDraft(s.key, { value: d.value, base: snapshot, extra: null });
            }
            result = result.ok !== false;
        }
        s.busy = false;
        if (result) {
            const stored = getDraft(s.key);
            if (stored?.value === snapshot) putDraft(s.key, null);
            else if (stored) putDraft(s.key, { ...stored, base: snapshot });
            s.saved = snapshot; s.conflict = false;
        }
        if (session !== s) return result;
        capture(s);
        if (!result) {
            s.closeRequested = false;
            s.frame.contentWindow.ProtoEditor.status('未保存，正文与草稿已保留。请重试或复制正文。' + (s.notice || ''), true);
            return false;
        }
        if ((close || s.closeRequested) && s.value === snapshot) {
            putDraft(s.key, null); finish(s, true); s.options.onSaved?.(result);
        } else if (close || s.closeRequested) { s.closeRequested = false; return save(true, s); }
        else { s.options.onAutosaved?.(result); schedule(s); }
        return result;
    }
    function begin(region, options) {
        if (!options || options.readonly) return false;
        if (session) {
            if (session.region === region) { focus(); return false; }
            suspend(); // 换一条编辑：原会话自动保存并回到阅读态，全程只保留一个编辑器
        }
        const draft = getDraft(options.key), doc = region.ownerDocument;
        const frame = doc.createElement('iframe');
        frame.className = 'proto-md-frame'; frame.title = options.label;
        frame.style.opacity = '0';
        frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
        frame.setAttribute('data-prototype-owned', '');
        const s = session = { region, frame, key: options.key, options, saved: options.value,
            value: draft?.value ?? options.value, ready: false, composing: false, busy: false,
            conflict: !!draft && draft.base !== options.value, cover: false, kept: null,
            /* 编辑器高度下限：编辑既有标注时贴合内容（与阅读态等高、双击零跳变）；
               新增标注（无内容）时给一个舒适的初始输入区。 */
            minH: options.minHeight ?? 28, toolbarOpening: true };
        region.classList.add('proto-md', 'is-editing'); region.removeAttribute('role');
        /* 主题必须在这里也设一次：新建标注不经 render 直接 begin，region 没有 data-theme 就按浅色变量铺白底，
           编辑器 iframe 加载期间（opacity 0）深色卡里就露出一块白——即“插入序号后浮窗闪一下白”。 */
        region.dataset.theme = options.theme || 'light';
        const h0 = region.getBoundingClientRect?.().height || 0;
        if (h0 > 24) {
            // 所见即所得：编辑器加载期间透明盖在阅读态上，ready 后才接管，内容与高度都不跳变
            s.cover = true; s.kept = [...region.children];
            // 已有内容时高度下限不得超过阅读态实高：否则单行标注接管时会被下限撑高几像素
            s.minH = Math.min(s.minH, Math.ceil(h0));
            frame.classList.add('proto-md-cover'); frame.style.height = Math.round(h0) + 'px';
            region.appendChild(frame);
        } else region.replaceChildren(frame);
        s.toolbar = makeToolbar(s);
        const follow = () => { if (!s.toolbarManual) placeToolbar(s); placeHandle(s); };
        const win = doc.defaultView;
        win.addEventListener('scroll', follow, { capture: true, passive: true });
        win.addEventListener('resize', follow, { passive: true });
        const observer = win.ResizeObserver && new win.ResizeObserver(follow);
        for (const target of new Set([region, region.closest('.pa-card'), region.closest('#prdSidebar, aside')])) {
            if (target) observer?.observe(target);
        }
        s.unfollow = () => { observer?.disconnect(); win.removeEventListener('scroll', follow, { capture: true }); win.removeEventListener('resize', follow); };
        placeToolbar(s); // 同步定位：不依赖 rAF（隐藏页签不触发），接管帧工具条即最终位置
        frame._markdownBridge = {
            config: { value: s.value, theme: options.theme || 'light', label: options.label, assetBase: options.assetBase || '' },
            uploadImage: file => options.uploadImage ? options.uploadImage(file) : Promise.reject(new Error('当前项目不支持图片上传')),
            ready() {
                if (session !== s) return;
                clearTimeout(s.loading); s.ready = true;
                if (s.cover) {
                    /* 此刻编辑器已就绪，才撤下阅读态完成接管。必须逐个移除阅读节点而不能 replaceChildren(frame)：
                       后者会先把 iframe 从文档摘下再插回，浏览器会销毁它的文档并重新加载——编辑器被初始化两次，
                       中间就是那一下空白闪烁，且二次加载无焦点、编辑面灰底直到再点一次。 */
                    s.cover = false;
                    for (const node of s.kept) if (node !== frame) node.remove();
                    s.kept = null;
                    frame.classList.remove('proto-md-cover');
                }
                frame.style.opacity = '1'; placeToolbar(s); placeHandle(s);
                // 接管帧同步把系统焦点送进编辑面：光标直接可用，不用再点一下
                try { frame.focus(); frame.contentWindow?.ProtoEditor?.focus(); } catch (_) { /* 隐藏页签无焦点可给 */ }
                // 只保留「草稿与正文冲突」的必要警示；不再弹自动保存 / 草稿恢复的提示气泡（用户反馈打扰）。
                if (s.conflict) frame.contentWindow.ProtoEditor.status('草稿对应的正文已变化，请核对后手动保存。', true);
            },
            change(value) { if (session !== s) return; s.value = value; capture(s); schedule(s); },
            composition(value) { s.composing = value; if (value) clearTimeout(s.timer); else { capture(s); schedule(s); } },
            /* 编辑器上报光标所在块类型（p / h1 / ul / ol / task / table / code）：工具条按钮点亮，表格按钮在表内切成行列增删，表格角标跟到表格左上角 */
            state(st) { if (session !== s) return; s.state = st; syncToolbar(s); placeHandle(s); },
            save: () => save(true, s), cancel: () => { if (!s.composing) suspend(region); },
            resize(height) {
                if (session !== s) return;
                frame.style.height = Math.max(s.minH, Math.ceil(height)) + 'px';
                if (!s.toolbarManual) placeToolbar(s);
                placeHandle(s);
            }
        };
        s.loading = setTimeout(() => {
            if (s.ready || session !== s) return;
            const m = doc.createElement('div'); m.className = 'proto-md-draft';
            m.textContent = '本地编辑器加载失败，请刷新重试。'; region.appendChild(m);
        }, 8000);
        frame.src = '/src/markdown-editor.html';
        return true;
    }
    window.addEventListener('beforeunload', e => {
        if (session) { capture(session); if (session.value !== session.saved || session.busy) { e.preventDefault(); e.returnValue = ''; } }
    });
    /* 预热编辑器文档：页面空闲时静默加载一次 markdown-editor.html（无 bridge，脚本即退），
       让 Vditor / Lute 这几 MB 脚本进入浏览器代码缓存——首次双击从约 1s 降到几十毫秒，光标随双击即到。 */
    function warm() {
        try {
            const f = document.createElement('iframe');
            f.hidden = true; f.setAttribute('aria-hidden', 'true'); f.tabIndex = -1;
            f.setAttribute('sandbox', 'allow-scripts allow-same-origin'); f.setAttribute('data-prototype-owned', '');
            f.addEventListener('load', () => setTimeout(() => f.remove(), 500));
            f.src = '/src/markdown-editor.html';
            document.documentElement.appendChild(f);
        } catch (_) { /* 预热失败不影响功能 */ }
    }
    if (typeof document !== 'undefined') {
        if (document.readyState === 'complete') setTimeout(warm, 800);
        else window.addEventListener('load', () => setTimeout(warm, 800), { once: true });
    }
    window.ProtoMarkdown = { key, getDraft, putDraft, render, begin, owns, suspend, save, focus,
        isBusy: () => !!session?.busy, current: () => session,
        /* 编辑区几何变化（如气泡卡拖宽）后重定位工具条；用户手动拖过的手动位不打扰 */
        relayout: () => { if (session) { if (!session.toolbarManual) placeToolbar(session); placeHandle(session); } },
        /* 外观切换：正在进行的编辑会话就地换主题（编辑区、工具条、编辑器文档），不重建、不丢光标；阅读态由调用方重新 render 即可 */
        theme(theme) {
            const s = session; if (!s) return;
            s.options.theme = theme;
            const entry = regions.get(s.region); if (entry?.options) entry.options.theme = theme;
            s.region.dataset.theme = theme;
            if (s.toolbar) s.toolbar.dataset.theme = theme;
            if (s.handle) s.handle.dataset.theme = theme;
            if (s.frame._markdownBridge) s.frame._markdownBridge.config.theme = theme;
            try { s.frame.contentWindow?.ProtoEditor?.theme?.(theme); } catch (_) { /* 载入中：编辑器就绪时从 config 读新主题 */ }
        } };
})();
