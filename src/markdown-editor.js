/* 本地 Vditor 原样接入；独立 CSP 限制正文中的资源与脚本。 */
(() => {
    'use strict';
    const bridge = window.frameElement?._markdownBridge;
    if (!bridge) return;
    const config = bridge.config, CDN = new URL('/src/vendor/vditor', location.href).href;
    const $ = id => document.getElementById(id);
    let editor, ready = false, composing = false, baseline = '', destroyed = false, resizeFrame = null;
    document.documentElement.dataset.theme = config.theme;
    /* 回传真实内容高（不加余量）：父层 ceil 后与阅读态差不足 1px，双击接管无可见跳变。 */
    const measure = () => document.body.getBoundingClientRect().height;
    function resize(immediate = false) {
        if (resizeFrame) { cancelAnimationFrame(resizeFrame); resizeFrame = null; }
        /* immediate：输入/回车路径同步量高回传——浏览器绘制前父页 iframe 已是新高度，
           光标（尤其末尾回车的新行）始终落在视口内，不再出现「回车光标不见、打字才在新行」。 */
        if (immediate) { bridge.resize(measure()); return; }
        resizeFrame = requestAnimationFrame(() => {
            resizeFrame = null;
            bridge.resize(measure());
        });
    }
    let stateFrame = null;
    document.addEventListener('selectionchange', () => {
        if (!ready || destroyed) return;
        const sel = document.getSelection();
        if (!sel || !sel.rangeCount) return;
        /* 兜底（selectionchange）：Vditor 异步渲染/重排后 options.input 未必同步触发，此路在 setRange 后必然触发——
           光标越出当前视口（回车/粘贴后高度未回传的窗口期）时同步量高回传，绘制前把新行收进视口。 */
        const rects = sel.getRangeAt(0).getClientRects();
        if (!rects.length) return;
        const caret = rects[rects.length - 1];
        if (caret.bottom > window.innerHeight + 1 || caret.top < -1) resize(true);
    });
    // 光标所在块类型上报（工具条按钮点亮）：按帧去抖
    document.addEventListener('selectionchange', () => {
        if (!ready || destroyed || stateFrame) return;
        stateFrame = requestAnimationFrame(() => { stateFrame = null; reportState(); });
    });
    // 内容高度变化也刷一次状态：表格几何（父页表格角标跟着它摆）随行高 / 行数而变
    const observer = new ResizeObserver(() => { resize(); reportState(); placeImageHandle(); }); observer.observe(document.body);
    /* 上色后把文字删光会留下空壳 <span style="color:…"></span>：存盘时剔掉，阅读态与下次编辑都不再带着它 */
    const EMPTY_COLOR = /<span style="color:(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]+)"><\/span>/g;
    function value() {
        const current = editor.getValue();
        let result = (current === baseline ? config.value : current).replace(EMPTY_COLOR, '');
        if (config.assetBase) {
            const base = new URL(config.assetBase, location.href);
            for (const prefix of [base.href, base.pathname]) {
                const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                result = result.replace(new RegExp(escaped + '(?=prd-assets/[a-f0-9]{64}\\.(?:png|jpg|gif|webp))', 'g'), '');
            }
        }
        return result;
    }
    let statusTimer = null;
    function status(text, error = false, hold = false) {
        const el = $('status');
        el.textContent = text; el.classList.toggle('error', error); el.classList.add('show');
        clearTimeout(statusTimer);
        if (!error && !hold) statusTimer = setTimeout(() => el.classList.remove('show'), 1800);
    }
    document.addEventListener('compositionstart', () => { composing = true; bridge.composition(true); }, true);
    document.addEventListener('compositionend', () => { composing = false; bridge.composition(false); if (decorateQueued) decorate(); }, true);
    document.addEventListener('keydown', e => {
        if (e.isComposing || composing || e.keyCode === 229 || e.repeat) return;
        if (e.key === 'Escape' && imageDrag) { e.preventDefault(); e.stopImmediatePropagation(); imageDrag.end(true); return; }
        if (!imageDrag && e.target !== imageGrip) selectImage(null);
        if (e.key === 'Escape' || ((e.ctrlKey || e.metaKey) && e.key === 'Enter')) {
            e.preventDefault(); e.stopImmediatePropagation();
            if (e.key === 'Escape') bridge.cancel(); else bridge.save();
        }
    }, true);
    document.addEventListener('paste', e => {
        if (!ready) return;
        e.preventDefault(); e.stopImmediatePropagation();
        const images = [...(e.clipboardData?.files || [])].filter(file => file.type.startsWith('image/'));
        if (images.length) { uploadImages(images); return; }
        const text = e.clipboardData?.getData('text/plain');
        if (text) editor.insertMD(text);
    }, true);
    document.addEventListener('dragover', e => { e.preventDefault(); }, true);
    document.addEventListener('drop', e => { e.preventDefault(); e.stopImmediatePropagation(); if (ready) uploadImages([...(e.dataTransfer?.files || [])]); }, true);
    document.addEventListener('click', e => { if (e.target.closest('a')) e.preventDefault(); }, true);

    /* ===== 源码层命令 =====
       Vditor IR 的块命令（标题 / 列表 / 任务）作用于整个 data-block（一次 Enter 没隔开空行的几行算同一块），
       用户要的是「只改光标所在的那一行」。做法：在光标处插入一个不可见标记字符，取 Markdown 源码，
       在源码里改那一行的前缀，再 setValue 写回并按标记把光标放回原处。
       标记用 U+2063（INVISIBLE SEPARATOR）：DOM↔Markdown 往返与表格单元格内都原样保留（零宽空格 / <wbr> 会被剥掉）。 */
    const MARK = '\u2063';
    const BLOCKS = new Set(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'task']);
    const FENCE = /^\s{0,3}(`{3,}|~{3,})/;
    const surface = () => document.querySelector('.vditor-ir [contenteditable="true"]');
    const elementOf = n => n?.nodeType === 3 ? n.parentElement : n;
    function liveRange() {
        const sel = document.getSelection(), root = surface();
        if (!sel || !sel.rangeCount || !root) return null;
        const r = sel.getRangeAt(0);
        return root.contains(r.commonAncestorContainer) ? r : null;
    }
    let uploading = false;
    async function uploadImages(files, at = liveRange()?.cloneRange()) {
        if (uploading || destroyed || !files.length) return;
        uploading = true;
        status('正在插入图片…', false, true);
        try {
            const paths = [];
            for (const file of files) {
                if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) throw new Error('仅支持 PNG、JPG、GIF、WebP 图片');
                if (file.size > 10 * 1024 * 1024) throw new Error('图片不能超过 10 MB');
                const path = await bridge.uploadImage(file);
                if (destroyed) return;
                const alt = file.name.replace(/\.[^.]+$/, '').replace(/[\[\]\\\r\n]/g, '').slice(0, 80) || '图片';
                paths.push(`![${alt}](${path})`);
            }
            editor.focus();
            if (at && surface()?.contains(at.commonAncestorContainer)) {
                const selection = document.getSelection(); selection.removeAllRanges(); selection.addRange(at);
            }
            editor.insertMD('\n\n' + paths.join('\n\n') + '\n\n');
            bridge.change(value()); resize(true); reportState();
            $('status').classList.remove('show');
        } catch (error) { if (!destroyed) status(error.message || '图片插入失败，请重试', true); }
        finally { uploading = false; }
    }
    function pickImage() {
        const at = liveRange()?.cloneRange();
        const input = document.createElement('input'); input.type = 'file'; input.accept = 'image/png,image/jpeg,image/gif,image/webp'; input.multiple = true;
        input.onchange = () => uploadImages([...input.files], at);
        input.click();
    }
    /* 尺寸使用标准 Markdown 的图片 title 后缀保存。只接受项目图片与有限整数，拖动期间不改源码。 */
    const IMAGE_SIZE = /(?:^|\s)proto-width=(\d{1,4})$/;
    let selectedImage = null, imageOverlay = null, imageGrip = null, imageDrag = null;
    const imageNode = img => img?.closest('.vditor-ir__node[data-type="img"]');
    function imageTitle(img) {
        const text = imageNode(img)?.querySelector('.vditor-ir__marker--title')?.textContent || '';
        return text.replace(/^["']|["']$/g, '');
    }
    function decorateImages() {
        for (const img of surface()?.querySelectorAll('img') || []) {
            if (imageDrag?.img === img) continue;
            const size = IMAGE_SIZE.exec(imageTitle(img));
            const width = size && +size[1] >= 48 && +size[1] <= 4096 ? size[1] + 'px' : '';
            if (img.style.width !== width) img.style.width = width;
        }
        placeImageHandle();
    }
    function placeImageHandle() {
        if (!imageOverlay) return;
        if (!selectedImage?.isConnected) { imageOverlay.hidden = true; selectedImage = null; return; }
        const r = selectedImage.getBoundingClientRect();
        imageOverlay.hidden = !r.width || !r.height;
        Object.assign(imageOverlay.style, {left: r.left + scrollX + 'px', top: r.top + scrollY + 'px', width: r.width + 'px', height: r.height + 'px'});
        imageOverlay.querySelector('.proto-md-image-size').textContent = Math.round(r.width) + ' × ' + Math.round(r.height);
    }
    function selectImage(img) {
        selectedImage = img;
        if (img && !imageOverlay) {
            imageOverlay = document.createElement('div'); imageOverlay.className = 'proto-md-image-resize';
            imageOverlay.setAttribute('data-prototype-owned', '');
            const size = document.createElement('span'); size.className = 'proto-md-image-size'; size.setAttribute('aria-hidden', 'true');
            imageGrip = document.createElement('button'); imageGrip.type = 'button'; imageGrip.className = 'proto-md-image-grip';
            imageGrip.title = '拖动调整图片大小'; imageGrip.setAttribute('aria-label', '调整图片大小，左右方向键调节');
            imageGrip.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m5 13 8-8M9 13l4-4M13 13h.01"/></svg>';
            imageGrip.onpointerdown = startImageResize;
            imageGrip.onkeydown = e => {
                if (!['ArrowLeft','ArrowRight','Home'].includes(e.key) || !selectedImage) return;
                e.preventDefault();
                const width = e.key === 'Home' ? null : selectedImage.getBoundingClientRect().width + (e.key === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 40 : 10);
                commitImageSize(selectedImage, width);
                imageGrip.focus({preventScroll: true});
            };
            imageOverlay.append(size, imageGrip); document.body.appendChild(imageOverlay);
        }
        placeImageHandle();
    }
    function commitImageSize(img, requested) {
        const root = surface(), node = imageNode(img);
        if (!root || !node || destroyed) return;
        const recordUndo = () => {
            // Vditor 默认延迟 800ms 入栈；尺寸操作必须一次入栈，立即撤销也能恢复。
            clearTimeout(editor.vditor.ir.processTimeoutId);
            editor.vditor.undo.addToUndoStack(editor.vditor);
        };
        recordUndo();
        const index = [...root.querySelectorAll('img')].indexOf(img);
        const max = Math.max(48, Math.min(4096, root.getBoundingClientRect().right - img.getBoundingClientRect().left));
        const width = requested === null ? null : Math.round(Math.max(Math.min(48, max), Math.min(requested, max)));
        let marker = node.querySelector('.vditor-ir__marker--title');
        const oldText = marker?.textContent || '', originalTitle = imageTitle(img).replace(IMAGE_SIZE, '').trim();
        const title = originalTitle + (width === null ? '' : (originalTitle ? ' ' : '') + 'proto-width=' + width);
        if (!marker && title) {
            marker = document.createElement('span'); marker.className = 'vditor-ir__marker vditor-ir__marker--title';
            node.querySelector('.vditor-ir__marker--paren:last-of-type').before(document.createTextNode(' '), marker);
        }
        if (marker) marker.textContent = title ? '"' + title.replace(/(?<!\\)"/g, '\\"') + '"' : '';
        const next = value();
        if (marker) marker.textContent = oldText;
        editor.setValue(next);
        decorateImages(); recordUndo(); bridge.change(value()); resize(true); reportState();
        selectImage(surface()?.querySelectorAll('img')[index] || null);
    }
    function startImageResize(e) {
        if (e.button !== 0 || !selectedImage || composing || imageDrag) return;
        e.preventDefault(); e.stopPropagation();
        imageGrip.focus({preventScroll: true});
        const img = selectedImage, rect = img.getBoundingClientRect(), original = img.style.width;
        const ratio = rect.height / rect.width, max = Math.max(48, Math.min(4096, surface().getBoundingClientRect().right - rect.left));
        let width = rect.width;
        const move = ev => {
            if (ev.pointerId !== e.pointerId) return;
            const dx = ev.clientX - e.clientX, dy = ev.clientY - e.clientY;
            const delta = (dx + dy * ratio) / (1 + ratio * ratio);
            width = Math.round(Math.max(Math.min(48, max), Math.min(max, rect.width + delta)));
            img.style.width = width + 'px'; placeImageHandle(); resize(true);
        };
        const end = cancel => {
            imageGrip.removeEventListener('pointermove', move); imageGrip.removeEventListener('pointerup', up);
            imageGrip.removeEventListener('pointercancel', cancelDrag); imageGrip.removeEventListener('lostpointercapture', cancelDrag);
            imageDrag = null; document.documentElement.classList.remove('is-image-resizing'); img.style.width = original;
            if (imageGrip.hasPointerCapture(e.pointerId)) imageGrip.releasePointerCapture(e.pointerId);
            if (!cancel && Math.abs(width - rect.width) >= 1) commitImageSize(img, width);
            else { placeImageHandle(); resize(true); }
        };
        const up = ev => { if (ev.pointerId === e.pointerId) end(false); };
        const cancelDrag = ev => { if (ev.pointerId === e.pointerId) end(true); };
        imageDrag = {img, end}; document.documentElement.classList.add('is-image-resizing');
        imageGrip.addEventListener('pointermove', move); imageGrip.addEventListener('pointerup', up);
        imageGrip.addEventListener('pointercancel', cancelDrag); imageGrip.addEventListener('lostpointercapture', cancelDrag);
        imageGrip.setPointerCapture(e.pointerId);
    }
    document.addEventListener('pointerdown', e => {
        if (!ready || imageDrag || imageOverlay?.contains(e.target)) return;
        const img = e.target.closest?.('.vditor-ir img');
        if (img && imageNode(img)) { e.preventDefault(); e.stopImmediatePropagation(); selectImage(img); }
        else selectImage(null);
    }, true);
    window.addEventListener('resize', placeImageHandle);
    /* 在 (container, offset) 插入标记文本节点。光标落在语法标记（`**`、`# `、`- `）里时挪到这一串标记之后，
       否则标记字符会卡进 "#⁣ " 之类的语法里，正则认不出这一行是什么。代码块的标记不挪（本来就要拒绝）。 */
    function placeMark(container, offset) {
        const r = document.createRange(); r.setStart(container, offset); r.collapse(true);
        let marker = elementOf(container)?.closest('.vditor-ir__marker');
        if (marker && !marker.closest('[data-type="code-block"]')) {
            while (marker.nextSibling?.classList?.contains('vditor-ir__marker')) marker = marker.nextSibling;
            r.setStartAfter(marker); r.collapse(true);
        }
        const node = document.createTextNode(MARK); r.insertNode(node); return node;
    }
    /* 把当前选区编码进源码，交给 transform 改写：transform({ lines, idx, line, clean, marks }) 返回新的行数组，
       或返回 null 表示放弃（由 transform 自己给出 status 提示）。withEnd：选区两端都打标记（上色用），否则只标起点。 */
    function rewrite(transform, withEnd = false) {
        if (!ready || destroyed || composing) return false;
        const range = liveRange();
        if (!range) { status('请先把光标放到要调整的内容上'); return false; }
        const sc = range.startContainer, so = range.startOffset, ec = range.endContainer, eo = range.endOffset;
        const nodes = [];
        if (withEnd && !range.collapsed) nodes.push(placeMark(ec, eo));
        nodes.push(placeMark(sc, so));
        let md;
        try { md = editor.getValue(); } finally {
            // 先把标记从 DOM 里拿掉再决定是否改写；放弃时原选区复原（splitText 留下的碎片 normalize 回去）
            for (const n of nodes) n.remove();
            for (const n of new Set([sc, ec])) if (n.nodeType === 3) n.parentNode?.normalize();
        }
        const lines = md.split('\n');
        const hit = lines.findIndex(l => l.includes(MARK));
        if (hit < 0) { status('无法定位光标所在行'); return false; }
        const total = md.split(MARK).length - 1, marks = lines[hit].split(MARK).length - 1;
        const clean = lines[hit].split(MARK).join('');
        let fence = null;
        for (let i = 0; i < hit; i++) { const m = FENCE.exec(lines[i]); if (!m) continue; if (!fence) fence = m[1][0]; else if (m[1][0] === fence) fence = null; }
        const out = transform({ lines, idx: hit, line: lines[hit], clean, marks, total, inCode: !!fence || FENCE.test(clean) });
        if (!out) { restore(sc, so, ec, eo); return false; }
        apply(out.join('\n'));
        return true;
    }
    function restore(sc, so, ec, eo) {
        const root = surface();
        if (!root?.contains(sc) || !root.contains(ec)) return;
        try { document.getSelection()?.setBaseAndExtent(sc, Math.min(so, sc.length ?? so), ec, Math.min(eo, ec.length ?? eo)); } catch (_) { /* 碎片已变 */ }
    }
    /* 写回源码，按标记字符恢复光标（一个标记 = 光标，两个 = 选区），然后上报内容与状态 */
    function apply(md) {
        editor.setValue(md);
        const root = surface(), sel = document.getSelection(), points = [];
        if (root) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), found = [];
            let n; while ((n = walker.nextNode())) if (n.data.includes(MARK)) found.push(n);
            for (const node of found) {
                let i;
                while ((i = node.data.indexOf(MARK)) >= 0) { node.deleteData(i, 1); points.push([node, i]); }
            }
            for (const p of points) {
                if (p[0].data.length) continue;
                const parent = p[0].parentNode;
                if (!parent) continue;
                const at = Array.prototype.indexOf.call(parent.childNodes, p[0]);
                p[0].remove(); p[0] = parent; p[1] = at;
            }
        }
        editor.focus();
        if (points.length && sel) {
            const r = document.createRange(), last = points[points.length - 1];
            try { r.setStart(points[0][0], points[0][1]); r.setEnd(last[0], last[1]); sel.removeAllRanges(); sel.addRange(r); } catch (_) { /* 节点已被 Vditor 重排 */ }
        }
        decorate();
        bridge.change(value()); resize(true); reportState();
    }

    /* ---- 块样式：正文 / 标题 / 无序 / 有序 / 任务，只动光标所在行 ---- */
    const BLOCK_RE = /^((?:\s{0,3}>\s?)*\s*)(?:(#{1,6})\s+|([-*+]|\d{1,9}[.)])\s+(\[[ xX]\]\s+)?)?(.*)$/;
    function parseBlock(line) {
        const [, lead, hashes, bullet, task, rest] = BLOCK_RE.exec(line);
        const type = hashes ? 'h' + hashes.length : bullet ? (task ? 'task' : /^\d/.test(bullet) ? 'ol' : 'ul') : 'p';
        return { lead, type, bullet, rest };
    }
    const isList = t => t === 'ul' || t === 'ol' || t === 'task';
    const isItem = line => isList(parseBlock(line).type);
    const nonblank = line => line.trim() !== '' && line.trim() !== '>';
    function setBlock(target) {
        rewrite(({ lines, idx, line, clean, inCode }) => {
            if (inCode) { status('代码块内不能改块样式'); return null; }
            if (/^\s*\|/.test(clean)) { status('表格内不能改块样式，请用表格按钮增删行列'); return null; }
            const cur = parseBlock(line);
            const next = cur.type === target ? 'p' : target;   // 同一样式再点一次 = 回到正文
            if (next === cur.type) return null;
            let prefix = '';
            if (/^h\d$/.test(next)) prefix = '#'.repeat(+next[1]) + ' ';
            else if (next === 'ul') prefix = '- ';
            else if (next === 'task') prefix = '- [ ] ';
            else if (next === 'ol') {
                // 接着上一行的有序编号；否则从 1 起
                const prev = idx > 0 ? parseBlock(lines[idx - 1]) : null;
                prefix = prev?.type === 'ol' && prev.lead === cur.lead ? `${parseInt(prev.bullet, 10) + 1}. ` : '1. ';
            }
            const out = lines.slice();
            out[idx] = cur.lead + prefix + cur.rest;
            /* 列表 ↔ 非列表切换时与相邻非空行隔开空行：否则 Markdown 会把这行并进相邻列表项 / 段落（懒延续），
               视觉上就成了「把上下几行一起改了」。引用里空行保留 ">"。 */
            if (isList(cur.type) !== isList(next)) {
                const blank = cur.lead.trimEnd();
                const below = out[idx + 1], above = out[idx - 1];
                if (below !== undefined && nonblank(below) && (isList(next) ? !isItem(below) : isItem(below))) out.splice(idx + 1, 0, blank);
                if (above !== undefined && nonblank(above) && (isList(next) ? !isItem(above) : true)) out.splice(idx, 0, blank);
            }
            return out;
        });
    }

    /* ---- 表格：插入 R×C（含表头行）；光标在表内时按光标所在单元格增删行列、删整表 ---- */
    const SEP_RE = /^\s*\|(\s*:?-+:?\s*\|)+\s*$/;
    const isRow = line => /^\s*\|/.test(line);
    const cells = line => line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '').split(/(?<!\\)\|/).map(c => c.trim());
    const row = list => `| ${list.join(' | ')} |`;
    function insertTable(rows, cols) {
        rows = Math.max(1, Math.min(50, rows)); cols = Math.max(1, Math.min(20, cols));
        rewrite(({ lines, idx, clean, inCode }) => {
            if (inCode) { status('代码块内不能插入表格'); return null; }
            if (isRow(clean)) { status('光标已在表格内，请用表格按钮增删行列'); return null; }
            const head = row(Array.from({ length: cols }, (_, i) => `列${i + 1}${i === 0 ? MARK : ''}`));
            const table = [head, row(Array(cols).fill('---')), ...Array.from({ length: rows - 1 }, () => row(Array(cols).fill('')))];
            const out = lines.slice();
            if (clean.trim() === '') out.splice(idx, 1, '', ...table, '');
            else { out[idx] = clean; out.splice(idx + 1, 0, '', ...table, ''); }
            return out;
        });
    }
    function tableOp(name) {
        rewrite(({ lines, idx, line, clean, inCode }) => {
            if (inCode || !isRow(clean)) { status('光标不在表格内'); return null; }
            const src = lines.map(l => l.split(MARK).join(''));
            let top = idx, bottom = idx;
            while (top > 0 && isRow(src[top - 1])) top--;
            while (bottom + 1 < src.length && isRow(src[bottom + 1])) bottom++;
            if (bottom - top < 1 || !SEP_RE.test(src[top + 1])) { status('光标不在表格内'); return null; }
            const grid = []; for (let i = top; i <= bottom; i++) grid.push(cells(src[i]));
            const cols = grid[0].length;
            for (const r of grid) while (r.length < cols) r.push(r === grid[1] ? '---' : '');
            const ri = idx - top;
            const ci = Math.max(0, Math.min(cols - 1, (line.slice(0, line.indexOf(MARK)).match(/(?<!\\)\|/g) || []).length - 1));
            const blank = () => Array(cols).fill('');
            let at = ri, col = ci;
            if (name === 'table-del') {
                // 整表换成一个空段落，光标落在那里；两侧原有的空行保留（它们本来就是与上下文的分隔）
                const out = src.slice();
                out.splice(top, bottom - top + 1, MARK);
                return out;
            }
            if (name === 'row-above') { if (ri <= 1) { status('表头上方不能插行'); return null; } grid.splice(ri, 0, blank()); }
            else if (name === 'row-below') { at = ri <= 1 ? 2 : ri + 1; grid.splice(at, 0, blank()); }
            else if (name === 'row-del') { if (ri <= 1) { status('不能删除表头行'); return null; } grid.splice(ri, 1); at = Math.min(ri, grid.length - 1); if (at === 1) at = 0; }
            else if (name === 'col-left' || name === 'col-right') { col = name === 'col-left' ? ci : ci + 1; grid.forEach((r, i) => r.splice(col, 0, i === 1 ? '---' : '')); }
            else if (name === 'col-del') { if (cols <= 1) { status('只剩一列，不能再删'); return null; } grid.forEach(r => r.splice(ci, 1)); col = Math.min(ci, cols - 2); }
            else return null;
            grid[at][col] += MARK;
            const out = src.slice();
            out.splice(top, bottom - top + 1, ...grid.map(row));
            return out;
        });
    }

    /* ---- 文字颜色：选中文字包成 <span style="color:…">（内联 HTML，阅读态 safeHTML 放行这一种）；'' = 去色 ---- */
    const COLOR_TAG = /^<span style="color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)">$/;
    const COLOR_TOKEN = /<span style="color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)">|<\/span>/g;
    /* 把一行拆成字符序列 [{ ch, color, src }]：颜色标签不算字符、只改后续字符的颜色；没配对的 </span> 当普通文本 */
    function colorRuns(text) {
        const chars = [], stack = [];
        let i = 0, m;
        COLOR_TOKEN.lastIndex = 0;
        const push = (from, to) => { for (let k = from; k < to; k++) chars.push({ ch: text[k], color: stack[stack.length - 1] || '', src: k }); };
        while ((m = COLOR_TOKEN.exec(text))) {
            push(i, m.index);
            if (m[1]) stack.push(m[1].toLowerCase());
            else if (stack.length) stack.pop();
            else { push(m.index, m.index + m[0].length); }
            i = m.index + m[0].length;
        }
        push(i, text.length);
        return chars;
    }
    function setColor(hex) {
        const r0 = liveRange();
        if (r0?.collapsed) {
            // 光标停在已上色的文字里：整段换色 / 去色
            const wrap = elementOf(r0.startContainer)?.closest('.proto-md-color');
            if (!wrap) { status('请先选中要上色的文字'); return; }
            const r = document.createRange(); r.selectNodeContents(wrap);
            const sel = document.getSelection(); sel.removeAllRanges(); sel.addRange(r);
        }
        rewrite(({ lines, idx, line, clean, marks, total, inCode }) => {
            if (inCode) { status('代码块内不能上色'); return null; }
            if (marks < 2) { status(total >= 2 ? '请在同一行内选中要上色的文字' : '请先选中要上色的文字'); return null; }
            const sIdx = line.indexOf(MARK), eIdx = line.indexOf(MARK, sIdx + 1) - 1;
            const chars = colorRuns(clean);
            let a = chars.findIndex(c => c.src >= sIdx), b = chars.findIndex(c => c.src >= eIdx);
            if (a < 0) a = chars.length; if (b < 0) b = chars.length;
            if (a >= b) { status('请先选中要上色的文字'); return null; }
            let out = '', open = '';
            for (let i = 0; i <= chars.length; i++) {
                const c = i < chars.length ? (i >= a && i < b ? hex : chars[i].color) : '';
                if (i === b) out += MARK;
                if (c !== open) { if (open) out += '</span>'; if (c) out += `<span style="color:${c}">`; open = c; }
                if (i === a) out += MARK;
                if (i < chars.length) out += chars[i].ch;
            }
            const next = lines.slice(); next[idx] = out;
            return next;
        }, true);
    }
    /* 编辑面装饰：Vditor IR 把内联 HTML 渲成灰色原文 <code>，看不到颜色效果。这里把成对的颜色开闭标签节点
       标成 .proto-md-color-tag（CSS 隐藏），中间的内容包进 <span class="proto-md-color" style="color:…">（纯展示壳，
       lute 转回 Markdown 时按未知标签剥掉）。Vditor 每次输入都会重渲当前块、冲掉装饰，所以用 MutationObserver 跟着补。 */
    let decorating = false, decorateQueued = false;
    const htmlInline = n => n?.nodeType === 1 && n.matches('.vditor-ir__node[data-type="html-inline"]');
    const isOpen = n => htmlInline(n) && COLOR_TAG.test(n.textContent);
    const isClose = n => htmlInline(n) && n.textContent === '</span>';
    function decorate() {
        const root = surface();
        if (!root || decorating || destroyed) return;
        if (composing) { decorateQueued = true; return; }
        decorateQueued = false; decorating = true;
        try {
            const sel = document.getSelection();
            const saved = sel?.rangeCount ? [sel.anchorNode, sel.anchorOffset, sel.focusNode, sel.focusOffset] : null;
            let changed = false;
            for (const w of root.querySelectorAll('.proto-md-color')) {
                if (isOpen(w.previousSibling) && isClose(w.nextSibling)) continue;
                w.replaceWith(...w.childNodes); changed = true;
            }
            for (const t of root.querySelectorAll('.proto-md-color-tag')) if (!isOpen(t) && !isClose(t)) { t.classList.remove('proto-md-color-tag'); changed = true; }
            for (const node of root.querySelectorAll('.vditor-ir__node[data-type="html-inline"]')) {
                if (!isOpen(node) || node.nextSibling?.classList?.contains('proto-md-color')) continue;
                const between = []; let n = node.nextSibling, closer = null;
                while (n) { if (isClose(n)) { closer = n; break; } if (isOpen(n)) break; between.push(n); n = n.nextSibling; }
                if (!closer) continue;
                const wrap = document.createElement('span'), color = COLOR_TAG.exec(node.textContent)[1].toLowerCase();
                wrap.className = 'proto-md-color'; wrap.dataset.color = color; wrap.style.color = color;
                node.after(wrap); wrap.append(...between);
                node.classList.add('proto-md-color-tag'); closer.classList.add('proto-md-color-tag');
                changed = true;
            }
            if (changed && saved && root.contains(saved[0]) && root.contains(saved[2])) {
                try { sel.setBaseAndExtent(...saved); } catch (_) { /* 节点已移动 */ }
            }
            decorateImages();
        } finally { decorating = false; }
    }
    /* 上报光标所在块类型给父页工具条（按钮点亮、表格按钮切成行列增删） */
    let lastState = '';
    function reportState() {
        if (!ready || destroyed || !bridge.state) return;
        const r = liveRange(), st = { block: 'p', table: false };
        const el = r ? elementOf(r.startContainer) : null;
        if (el) {
            // 注意编辑面本身就是 <pre class="vditor-reset">，不能拿 pre 判代码块
            if (el.closest('[data-type="code-block"], .vditor-ir__marker--pre')) st.block = 'code';
            else if (el.closest('table')) {
                // 表格几何（本文档视口坐标）：父页据此把表格角标钉在表格左上角
                const b = el.closest('table').getBoundingClientRect();
                st.block = 'table'; st.table = true;
                st.rect = { left: Math.round(b.left), top: Math.round(b.top), width: Math.round(b.width), height: Math.round(b.height) };
            }
            else {
                const li = el.closest('li'), h = el.closest('h1,h2,h3,h4,h5,h6');
                if (li) st.block = li.classList.contains('vditor-task') || li.querySelector(':scope > input[type="checkbox"]') ? 'task' : li.parentElement?.tagName === 'OL' ? 'ol' : 'ul';
                else if (h) st.block = h.tagName.toLowerCase();
            }
        }
        const key = st.block + (st.table ? '!' + Object.values(st.rect).join(',') : '');
        st.color = el?.closest('.proto-md-color')?.dataset.color || '';
        if (key + st.color === lastState) return;
        lastState = key + st.color; bridge.state(st);
    }
    /* 全局悬浮工具栏命令：块样式 / 表格 / 颜色走源码层改写；加粗 / 斜体 / 撤销 / 重做仍转发给隐藏的 Vditor 内置按钮。 */
    function command(name) {
        if (!ready || destroyed) return;
        if (name === 'list') name = 'ul'; else if (name === 'check') name = 'task';
        let m;
        if (name === 'image') { pickImage(); return; }
        if (name === 'link') { editor.insertValue('[链接说明](https://)', true); editor.focus(); return; }
        if (BLOCKS.has(name)) { setBlock(name); return; }
        if ((m = /^table(?::(\d+):(\d+))?$/.exec(name))) { insertTable(+(m[1] || 3), +(m[2] || 3)); return; }
        if (/^(row|col)-(above|below|left|right|del)$|^table-del$/.test(name)) { tableOp(name); return; }
        if ((m = /^color:(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)?$/.exec(name))) { setColor((m[1] || '').toLowerCase()); return; }
        document.querySelector(`.vditor-toolbar [data-type="${name}"]`)?.click();
        editor.focus();
    }
    /* 外观就地切换（父页 ProtoMarkdown.theme 调用）：文档变量 + Vditor 自身主题与内容主题，不重建编辑器。 */
    function theme(value) {
        config.theme = value;
        document.documentElement.dataset.theme = value;
        if (editor && ready && !destroyed) editor.setTheme(value === 'dark' ? 'dark' : 'classic', value === 'dark' ? 'dark' : 'light', undefined, `${CDN}/dist/css/content-theme`);
    }
    let mutations = null;
    window.ProtoEditor = { value, focus: () => editor?.focus(), status, command, theme,
        destroy() { imageDrag?.end(true); destroyed = true; imageOverlay?.remove(); window.removeEventListener('resize', placeImageHandle); observer.disconnect(); mutations?.disconnect(); if (resizeFrame) cancelAnimationFrame(resizeFrame); if (stateFrame) cancelAnimationFrame(stateFrame); editor?.destroy(); } };
    try {
        editor = new Vditor($('editor'), {
            cdn: CDN, icon: '', mode: 'ir', lang: 'zh_CN', theme: config.theme === 'dark' ? 'dark' : 'classic',
            cache: { enable: false }, value: config.value, height: 'auto', minHeight: 0,
            placeholder: '直接输入 Markdown…', typewriterMode: false,
            toolbar: ['headings','bold','italic','link','list','check','table','undo','redo'],
            toolbarConfig: { pin: false }, counter: { enable: false }, resize: { enable: false },
            outline: { enable: false }, hint: { emoji: {}, parse: false },
            link: { isOpen: false }, image: { isPreview: false }, upload: { url: '', linkToImgUrl: '' },
            preview: { markdown: { sanitize: true, autoSpace: false, fixTermTypo: false, codeBlockPreview: false, mathBlockPreview: false, linkBase: config.assetBase || '' },
                hljs: { enable: false }, maxWidth: 10000,
                theme: { current: config.theme === 'dark' ? 'dark' : 'light', path: `${CDN}/dist/css/content-theme` },
                render: { media: { enable: false } } },
            input: () => { if (ready && !destroyed) { bridge.change(value()); resize(true); } },
            after: () => {
                if (destroyed) { editor.destroy(); return; }
                baseline = editor.getValue(); editor.clearStack(); ready = true;
                const surfaceEl = surface();
                surfaceEl?.setAttribute('aria-label', config.label);
                editor.focus();
                // 光标落在内容末尾：进入编辑即衔接阅读视图的结尾，无需再滚动定位，直接往下续写。
                // 定位、滚动与首轮高度回传全部在 bridge.ready() 接管前完成：接管帧即最终态，不再先显文首再跳末尾。
                if (surfaceEl) {
                    const range = document.createRange();
                    range.selectNodeContents(surfaceEl);
                    range.collapse(false);
                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                    (surfaceEl.lastElementChild || surfaceEl).scrollIntoView?.({ block: 'nearest' });
                    mutations = new MutationObserver(() => decorate());
                    mutations.observe(surfaceEl, { childList: true, subtree: true, characterData: true });
                    decorate();
                }
                reportState();
                /* 首轮量高同步回传：接管帧即最终高度，内容增高后浏览器自动把根滚动位置钳回 0。 */
                resize(true);
                /* 揭开阅读态遮盖前，先让编辑器内容真正绘制一帧：Vditor 刚在本回调里写入 DOM，
                   若此刻同步回传 ready，父层撤下遮盖时 iframe 内容尚未上屏，会闪一下空白。
                   双 rAF 等内容绘制后再回传；隐藏页签 rAF 挂起时用 setTimeout 兜底（此时本无可见闪烁）。 */
                let revealed = false;
                const fireReady = () => { if (revealed || destroyed) return; revealed = true; bridge.ready(); };
                requestAnimationFrame(() => requestAnimationFrame(fireReady));
                setTimeout(fireReady, 150);
            }
        });
    } catch (e) { status('编辑器加载失败：' + e.message, true); }
})();
