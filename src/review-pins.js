/* 评审壳只读气泡层：随导出内嵌进每个原型 HTML（review_export.inject_bundle），跑在被评审原型页面内。
   依赖同页先加载的 proto-anchors.js / proto-order.js / review-bridge.js；通过 window.__REVIEW__（由 bridge 建立，内部走 postMessage）与壳父页通信。
   只读：无编辑、无拖动、无删除。 */
(() => {
    'use strict';
    if (window.__reviewPinsBoot) return;
    window.__reviewPinsBoot = true;
    const R = window.__REVIEW__;
    if (!R || !window.ProtoAnchors || !window.ProtoOrder) return;

    const style = document.createElement('style');
    style.textContent = `
.__review_pin{position:absolute;display:grid;place-items:center;min-width:36px;height:36px;padding:0 8px;border:3px solid #fff;border-radius:50% 50% 50% 2px;background:#2563eb;color:#fff;font:600 13px/1 "PingFang SC","Microsoft YaHei UI",system-ui,sans-serif;font-variant-numeric:tabular-nums;box-shadow:0 8px 24px rgba(16,24,40,.24);transform:translateY(-100%);cursor:pointer;pointer-events:auto;}
.__review_pin:hover{background:#1d4ed8;}
.__review_pin:not(.__stale){background:var(--pin-fill);color:var(--pin-ink);border-color:var(--pin-stroke);}
.__review_pin:not(.__stale):hover{background:var(--pin-fill);filter:brightness(.96);}
.__review_pin.__stale{background:#626b78;cursor:default;}
@media(prefers-color-scheme:dark){.__review_pin{border-color:#121519;}}
.__review_pop{position:fixed;z-index:2147482001;width:min(360px,calc(100vw - 16px));max-width:calc(100vw - 16px);overflow:visible;border:1px solid #d8dee3;border-radius:10px;background:#fff;color:#1a1d23;font:14px/1.7 "PingFang SC","Microsoft YaHei UI",system-ui,sans-serif;letter-spacing:.02em;box-shadow:0 8px 24px rgba(16,24,40,.24);display:none;}
.__review_pop_body{max-height:calc(100vh - 16px);overflow:auto;overscroll-behavior:contain;padding:12px 14px;border-radius:inherit;}
.__review_pop_resize{position:absolute;top:0;bottom:0;width:12px;cursor:ew-resize;touch-action:none;z-index:3;background:transparent;}
/* 热区以浮窗真实边框为中心，不画独立蓝细条；视觉仍是浮窗自身边缘，命中区向内外各扩 6px。 */
.__review_pop_resize_w{left:0;transform:translateX(-50%);}.__review_pop_resize_e{right:0;transform:translateX(50%);}
.__review_pop.pop-resizing{user-select:none;}
.__review_pop.pop-resizing,.__review_pop.pop-resizing *{cursor:ew-resize!important;}
@media(prefers-color-scheme:dark){.__review_pop{background:#121519;color:#f2f4f7;border-color:#363c44;}}
.__review_pop_body>:first-child{margin-top:0;}.__review_pop_body>:last-child{margin-bottom:0;}
.__review_pop p{margin:0 0 10px;overflow-wrap:anywhere;}
.__review_pop img{display:block;max-width:100%;height:auto;margin:8px 0;border-radius:6px;}
.__review_pop h1{font-size:18px;}.__review_pop h2{font-size:16px;}.__review_pop h3,.__review_pop h4{font-size:14px;}
.__review_pop ul,.__review_pop ol{padding-left:20px;margin:6px 0 10px;}.__review_pop li.task{list-style:none;margin-left:-18px;}
.__review_pop code{font-family:ui-monospace,Consolas,monospace;font-size:13px;background:rgba(127,127,127,.16);padding:1px 5px;border-radius:4px;}
.__review_pop pre{background:rgba(127,127,127,.14);padding:10px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere;}.__review_pop pre code{background:none;padding:0;}
.__review_pop table{border-collapse:collapse;width:100%;}.__review_pop th,.__review_pop td{border:1px solid #d8dee3;padding:6px;text-align:left;}
@media(prefers-color-scheme:dark){.__review_pop th,.__review_pop td{border-color:#363c44;}}
.__review_pop blockquote{border-left:3px solid #d8dee3;margin:8px 0;padding:2px 12px;color:#4e5560;}.__review_pop a{color:#2563eb;}.__review_pop hr{border:0;border-top:1px solid #d8dee3;}
/* 点击引导：与操作界面 .pa-guide 同式——亮黄色系，与蓝色水滴序号在 色相 / 形状 / 动效 三方面区分。
   框 = 透明可点区：虚线、静态不呼吸；悬停转实线 + 加深底色 + 外环。标签 = 与框左上角拼成一体的选区式标签，只有标签呼吸。
   偏离 DESIGN_MASTER --accent-amber #b45309（实看发褐）：框线 #d97706（白底 3.19:1），标签 #fbbf24 配深棕字 #5c3300（6.52:1）。
   固定浅色、不随 prefers-color-scheme 切换：引导叠在原型页面上，颜色跟随页面而非系统。 */
.__review_guide{--g-line:#d97706;--g-fill:#fbbf24;--g-ink:#5c3300;position:absolute;box-sizing:border-box;margin:0;padding:0;border:2px dashed var(--g-line);border-radius:0 8px 8px 8px;background:rgba(251,191,36,.10);cursor:pointer;pointer-events:auto;transition:background-color 150ms ease-out,box-shadow 150ms ease-out;}
.__review_guide:hover{border-style:solid;background:rgba(251,191,36,.30);box-shadow:0 0 0 3px rgba(251,191,36,.38);}
.__review_guide:active{background:rgba(251,191,36,.45);}
.__review_guide:focus-visible{outline:2px solid var(--g-line);outline-offset:2px;}
.__review_guide_tag{position:absolute;box-sizing:border-box;left:-2px;top:-2px;transform:translateY(-100%);display:inline-flex;align-items:center;gap:3px;height:18px;padding:0 7px 0 5px;border:1px solid var(--g-line);border-radius:6px 6px 6px 0;background:var(--g-fill);color:var(--g-ink);font:600 11px/1 "PingFang SC","Microsoft YaHei UI",system-ui,sans-serif;white-space:nowrap;pointer-events:none;animation:__rvGuideTag 1.8s ease-in-out infinite;animation-delay:var(--g-delay,0s);}
.__review_guide_tag svg{width:10px;height:10px;animation:__rvGuideBob 1.8s ease-in-out infinite;animation-delay:var(--g-delay,0s);}
.__review_guide:hover .__review_guide_tag{animation:none;box-shadow:0 0 0 3px rgba(251,191,36,.38);}
.__review_guide.__review_guide_below{border-radius:8px 8px 8px 0;}
.__review_guide.__review_guide_below .__review_guide_tag{top:auto;bottom:-2px;transform:translateY(100%);border-radius:0 6px 6px 6px;}
.__review_guide.__review_guide_end{border-radius:8px 0 8px 8px;}
.__review_guide.__review_guide_end .__review_guide_tag{left:auto;right:-2px;border-radius:6px 6px 0 6px;}
.__review_guide.__review_guide_below.__review_guide_end{border-radius:8px 8px 0 8px;}
.__review_guide.__review_guide_below.__review_guide_end .__review_guide_tag{border-radius:6px 0 6px 6px;}
@keyframes __rvGuideTag{0%,100%{box-shadow:0 0 0 0 rgba(251,191,36,0),0 1px 2px rgba(92,51,0,.18);}50%{box-shadow:0 0 0 4px rgba(251,191,36,.42),0 1px 2px rgba(92,51,0,.18);}}
@keyframes __rvGuideBob{0%,100%{transform:translateY(-1px);}50%{transform:translateY(1px);}}
@media(prefers-reduced-motion:reduce){.__review_guide_tag,.__review_guide_tag svg{animation:none;}}
`;
    (document.head || document.documentElement).appendChild(style);

    const layer = document.createElement('div');
    layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147482000;';
    document.documentElement.appendChild(layer);
    // 引导框独立图层：序号层每次重排 replaceChildren 整体重建，引导框要按触发器复用（保住悬停态、呼吸相位与点击）
    const glayer = document.createElement('div');
    glayer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147481999;';
    glayer.setAttribute('data-prototype-owned', '');   // 引导框是 <button>，标记自有以免 revealTrigger 兜底搜索把它当成原型触发器
    document.documentElement.appendChild(glayer);

    // 收起态气泡：PRD 侧栏收起时，点序号在序号旁展示正文；正文独立滚动，左右边缘可拖宽。
    let pop = null, popBody = null, popResizing = null, popNoteId = null;
    function setPinExpanded(noteId, expanded) {
        if (!noteId) return;
        layer.querySelector(`.__review_pin[data-note-id="${CSS.escape(noteId)}"]`)?.setAttribute('aria-expanded', String(expanded));
    }
    function hidePop() {
        if (pop) pop.style.display = 'none';
        setPinExpanded(popNoteId, false);
        popNoteId = null;
    }
    function startPopResize(e, handle, side) {
        if (!pop || e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        const rect = pop.getBoundingClientRect(), startX = e.clientX, startW = rect.width, fixedRight = rect.right;
        popResizing = { handle, side, pointerId: e.pointerId };
        pop.classList.add('pop-resizing');
        document.documentElement.style.cursor = 'ew-resize';
        document.documentElement.style.userSelect = 'none';
        // 指针按下后由 window 兜住整段拖动；不依赖鼠标始终停留在 12px 边缘热区，也不依赖 pointer capture 是否成功。
        try { handle.setPointerCapture(e.pointerId); } catch (_) { /* 浏览器不支持时 window 监听仍可工作 */ }
        const move = ev => {
            if (!popResizing || ev.pointerId !== e.pointerId) return;
            ev.preventDefault();
            const raw = side === 'e' ? startW + (ev.clientX - startX) : startW - (ev.clientX - startX);
            const minW = Math.min(280, innerWidth - 16), maxW = Math.max(minW, Math.min(720, innerWidth - 16));
            const edgeMax = side === 'e' ? innerWidth - rect.left - 8 : fixedRight - 8;
            const width = Math.max(minW, Math.min(Math.round(raw), maxW, edgeMax));
            pop.style.width = width + 'px';
            if (side === 'w') pop.style.left = Math.max(8, fixedRight - width) + 'px';
        };
        const up = ev => {
            if (!popResizing || ev.pointerId !== e.pointerId) return;
            popResizing = null; pop.classList.remove('pop-resizing');
            document.documentElement.style.cursor = '';
            document.documentElement.style.userSelect = '';
            window.removeEventListener('pointermove', move, true); window.removeEventListener('pointerup', up, true); window.removeEventListener('pointercancel', up, true);
            try { if (handle.hasPointerCapture(e.pointerId)) handle.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
        };
        window.addEventListener('pointermove', move, { capture: true, passive: false });
        window.addEventListener('pointerup', up, true);
        window.addEventListener('pointercancel', up, true);
    }
    function ensurePop() {
        if (pop) return;
        pop = document.createElement('div');
        pop.id = '__review_popover'; pop.className = '__review_pop';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('data-prototype-owned', '');
        pop.addEventListener('click', e => e.stopPropagation());
        popBody = document.createElement('div'); popBody.className = '__review_pop_body';
        pop.appendChild(popBody);
        for (const side of ['w', 'e']) {
            const handle = document.createElement('span');
            handle.className = `__review_pop_resize __review_pop_resize_${side}`;
            handle.setAttribute('aria-hidden', 'true'); handle.title = '拖动调节宽度';
            handle.onpointerdown = e => startPopResize(e, handle, side);
            pop.appendChild(handle);
        }
        document.documentElement.appendChild(pop);
    }
    function showPop(note, pin) {
        ensurePop();
        setPinExpanded(popNoteId, false);
        popNoteId = note.id;
        pin.setAttribute('aria-expanded', 'true');
        popBody.innerHTML = R.renderBody ? R.renderBody(note) : (note.body || '');
        popBody.scrollTop = 0;
        pop.style.display = 'block';
        pop.style.visibility = 'hidden';
        pop.style.left = '0px'; pop.style.top = '0px';
        const pw = pop.offsetWidth, ph = pop.offsetHeight;
        const px = parseFloat(pin.style.left) || 0, py = parseFloat(pin.style.top) || 0;
        const W = innerWidth, H = innerHeight;
        let left = px + 16, top = py - ph - 8;
        if (left + pw > W - 8) left = px - pw - 16;
        left = Math.max(8, Math.min(left, W - pw - 8));
        if (top < 8) top = py + 8;
        top = Math.max(8, Math.min(top, H - ph - 8));
        pop.style.left = left + 'px'; pop.style.top = top + 'px';
        pop.style.visibility = 'visible';
    }
    function togglePop(note, pin) {
        if (pop && pop.style.display === 'block' && popNoteId === note.id) { hidePop(); return; }
        showPop(note, pin);
    }
    window.__reviewHidePop = hidePop;
    window.__reviewPopNoteId = () => (pop && pop.style.display === 'block' ? popNoteId : null);
    window.__reviewRelayout = () => { try { layout(); } catch (_) { /* ignore */ } };
    document.addEventListener('click', e => {
        if (pop && pop.style.display === 'block' && !pop.contains(e.target) && !e.target.closest?.('.__review_pin')) hidePop();
    }, true);
    // scroll 监听用了 capture，气泡自身 overflow:auto 的滚动也会冒到 window；旧逻辑因此鼠标一滚正文就关气泡。
    // 只在气泡外部（原型页面 / 其他滚动容器）发生滚动时关闭；气泡内部滚动保持打开。
    window.addEventListener('scroll', e => {
        if (pop && pop.style.display === 'block' && pop.contains(e.target)) return;
        hidePop();
        scheduleLayout();
    }, { passive: true, capture: true });
    window.addEventListener('resize', () => { hidePop(); scheduleLayout(); }, { passive: true });

    let layoutFrame = 0;
    function scheduleLayout() {
        if (layoutFrame) return;
        layoutFrame = requestAnimationFrame(() => { layoutFrame = 0; layout(); });
    }

    const stateOf = () => document.documentElement.dataset.protoState || 'default';
    let lastState = '', lastX = -1, lastY = -1, lastW = 0, lastH = 0, lastHtml = '';
    let lastOrder = '', lastStale = '';

    function layout() {
        const state = stateOf();
        if (state !== lastState) hidePop(); // 只在原型状态切换时关气泡；纯几何重排不关（避免侧栏收起引发的 reflow 误关刚弹出的气泡）
        const notes = (R.notes || []).filter(n => n.stateId === state);
        const arranged = window.ProtoOrder.project(notes, window);
        const stale = [], noPoint = [];
        layer.replaceChildren();
        for (const n of arranged) {
            let found = null;
            try { found = window.ProtoAnchors.point(n); } catch (_) { /* 锚定异常按失效处理 */ }
            if (!found?.point) { noPoint.push(n); continue; }
            if (found.point.visible === false) continue; // 滚出嵌套容器的序号随锚点隐藏，不算失锚。
            const pin = document.createElement('button');
            pin.type = 'button';
            pin.className = '__review_pin';
            window.ProtoAppearance?.applyPin(pin, n);
            pin.dataset.noteId = n.id;
            pin.textContent = n.displayNumber;
            pin.setAttribute('aria-label', `标注 ${n.displayNumber}`);
            pin.setAttribute('aria-haspopup', 'dialog');
            pin.setAttribute('aria-controls', '__review_popover');
            pin.setAttribute('aria-expanded', String(popNoteId === n.id && pop?.style.display === 'block'));
            pin.style.left = found.point.x + 'px';
            pin.style.top = found.point.y + 'px';
            pin.onclick = e => {
                e.preventDefault(); e.stopPropagation();
                // PRD 侧栏展开：定位到右栏对应内容；收起：就地弹气泡展示内容。
                if (R.asideOpen && R.asideOpen()) { hidePop(); R.onFocus?.(n.id); }
                else togglePop(n, pin);
            };
            layer.appendChild(pin);
        }
        // 无落点分流（Feature 1 引导 + 失锚判定）：元素还在且被折叠/隐藏 → 正常颜色，可展开的盖透明脉冲描边框引导；
        // 元素真找不到、或可见但落点失效（目标变化）才算失锚（右栏灰显、置底、不可点）。
        const groups = new Map();
        for (const n of noPoint) {
            let el = null; try { el = window.ProtoAnchors.resolveHidden(n.anchor); } catch (_) { /* ignore */ }
            let hint = null;
            try { hint = window.ProtoAnchors.revealHint?.(n.anchor, el); } catch (_) { /* ignore */ }
            if (!hint && el && window.ProtoAnchors.hidden(el)) {
                let trigger = null; try { trigger = window.ProtoAnchors.revealTrigger(el); } catch (_) { /* ignore */ }
                if (trigger) hint = { trigger, target: el, label: '展开', kind: 'disclosure' };
            }
            if (!hint?.trigger) {
                if (!el || !window.ProtoAnchors.hidden(el)) stale.push(n.id); // 元素仍在但隐藏、只是暂无可操作引导时也不算失锚
                continue;
            }
            let g = groups.get(hint.trigger);
            const actionKey = `${hint.kind}\n${hint.label}`;
            if (!g) groups.set(hint.trigger, (g = { target: hint.target, label: hint.label, actionKey, notes: [] }));
            if (g.actionKey === actionKey) g.notes.push(n);
        }
        const GICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
        const existing = [...glayer.querySelectorAll('.__review_guide')];
        const alive = new Set();
        let gi = existing.length;   // 新建引导错峰呼吸（与 proto-annotate.js 一致）：负 delay 立处不同相位
        groups.forEach((g, trig) => {
            const r = trig.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;
            // 描边框套在触发器外 4px，小图标至少 22px 保证可点；裁到视口内，完全出视口就不画（与 proto-annotate.js layoutGuides 同算法）
            const pad = 4, w = Math.max(r.width + pad * 2, 22), h = Math.max(r.height + pad * 2, 22);
            let left = r.left + r.width / 2 - w / 2, top = r.top + r.height / 2 - h / 2;
            const right = Math.min(innerWidth - 2, left + w), bottom = Math.min(innerHeight - 2, top + h);
            left = Math.max(2, left); top = Math.max(2, top);
            if (right - left < 8 || bottom - top < 8) return;
            let guide = existing.find(x => x.__rvTrig === trig);
            if (!guide) {
                guide = document.createElement('button');
                guide.type = 'button'; guide.className = '__review_guide';
                guide.__rvTrig = trig;
                guide.style.setProperty('--g-delay', (-(gi++ % 4) * 0.45) + 's');
                guide.onclick = async e => { e.preventDefault(); e.stopPropagation(); try { await window.ProtoAnchors.revealAndWait(guide.__rvTarget); } catch (_) { /* ignore */ } layout(); };
                glayer.appendChild(guide);
            }
            guide.__rvTarget = g.target;
            const html = '<span class="__review_guide_tag">' + GICON + '<span>' + g.label + ' · ' + g.notes.length + '</span></span>';
            if (guide.__rvHtml !== html) { guide.innerHTML = html; guide.__rvHtml = html; }
            guide.title = '点击“' + g.label + '”以显示 ' + g.notes.length + ' 处标注（' + g.notes.map(n => n.displayNumber).join(' ') + '）';
            guide.setAttribute('aria-label', guide.title);
            guide.style.left = left + 'px'; guide.style.top = top + 'px';
            guide.style.width = (right - left) + 'px'; guide.style.height = (bottom - top) + 'px';
            guide.classList.toggle('__review_guide_below', top < 24);            // 贴顶时标签改挂底边，不被视口切掉
            guide.classList.toggle('__review_guide_end', left + 84 > innerWidth); // 贴右时标签改挂右角
            alive.add(guide);
        });
        existing.forEach(x => { if (!alive.has(x)) x.remove(); });
        const orderKey = JSON.stringify(arranged.map(n => [n.id, n.displayNumber]));
        const staleKey = JSON.stringify(stale);
        if (orderKey !== lastOrder || staleKey !== lastStale || state !== lastState) {
            lastOrder = orderKey; lastStale = staleKey; lastState = state;
            R.onSync?.(Object.fromEntries(arranged.map(n => [n.id, n.displayNumber])), state, stale);
        }
    }

    document.addEventListener('proto-anchors:reveal-failed', layout);

    setInterval(() => {
        const html = document.documentElement.outerHTML.length;
        if (stateOf() !== lastState || scrollX !== lastX || scrollY !== lastY ||
            innerWidth !== lastW || innerHeight !== lastH || html !== lastHtml) {
            lastX = scrollX; lastY = scrollY; lastW = innerWidth; lastH = innerHeight; lastHtml = html;
            layout();
        }
    }, 350);

    layout();
})();
