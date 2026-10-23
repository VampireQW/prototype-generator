/* 点击空白时短暂提示本次需求范围内的真实交互；未声明范围时不扫描整页。 */
(() => {
    'use strict';
    if (window.ProtoHotspots) return;
    const DURATION = 2000, MAX_HINTS = 80;
    const COLORS = { fill: '#ff9f29' };
    const EVENTS = new Set(['click', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchend']);
    const EDITABLE = 'input,textarea,select,[contenteditable]:not([contenteditable="false"])';
    const BLOCKED = '[hidden],[inert],[aria-hidden="true"],[aria-disabled="true"],[data-proto-hotspot="false"]';
    const CONTROL_TAGS = new Set(['BUTTON', 'A', 'AREA', 'INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY']);
    const CONTROL_ROLES = new Set(['button', 'link', 'checkbox', 'radio', 'switch', 'tab', 'menuitem', 'option', 'combobox', 'slider', 'textbox']);
    const owned = el => !!el?.closest?.('[data-prototype-owned],.__review_pin,.__review_pop,.__review_guide');
    let options = {}, layer, style, observer, timer = 0, frame = 0, started = 0, down = null;
    const boxes = new Map();

    // 先于业务脚本载入：只记录实际绑定，不运行任何按钮来试探功能。
    const listeners = new WeakMap();
    const nativeAdd = EventTarget.prototype.addEventListener, nativeRemove = EventTarget.prototype.removeEventListener;
    const captureOf = config => typeof config === 'boolean' ? config : !!config?.capture;
    EventTarget.prototype.addEventListener = function (type, listener, config) {
        if (!EVENTS.has(type) || !listener || typeof listener !== 'function' && typeof listener.handleEvent !== 'function')
            return nativeAdd.call(this, type, listener, config);
        let entries = listeners.get(this);
        if (!entries) { entries = new Set(); listeners.set(this, entries); }
        const capture = captureOf(config);
        const existing = [...entries].find(entry => entry.type === type && entry.listener === listener && entry.capture === capture && !entry.signal?.aborted);
        if (existing) return nativeAdd.call(this, type, existing.wrapper, config);
        const entry = { type, listener, capture, once: !!config?.once, signal: config?.signal };
        entry.wrapper = function (event) {
            if (entry.once) { entries.delete(entry); schedule(); }
            return typeof listener === 'function' ? listener.call(this, event) : listener.handleEvent.call(listener, event);
        };
        const result = nativeAdd.call(this, type, entry.wrapper, config);
        if (!entry.signal?.aborted) {
            entries.add(entry);
            if (entry.signal) nativeAdd.call(entry.signal, 'abort', () => { entries.delete(entry); schedule(); }, { once: true });
            schedule();
        }
        return result;
    };
    EventTarget.prototype.removeEventListener = function (type, listener, config) {
        const entries = listeners.get(this), capture = captureOf(config);
        const entry = entries && [...entries].find(item => item.type === type && item.listener === listener && item.capture === capture);
        if (!entry) return nativeRemove.call(this, type, listener, config);
        const result = nativeRemove.call(this, type, entry.wrapper, config);
        entries.delete(entry); schedule(); return result;
    };

    function binding(el) {
        if ([...EVENTS].some(type => typeof el['on' + type] === 'function')) return true;
        const reactRoot = Object.keys(el).some(key => key.startsWith('__reactContainer$'));
        if (!reactRoot && [...(listeners.get(el) || [])].some(entry => !entry.signal?.aborted)) return true;
        // React 的点击监听由根节点代理，真实业务回调在元素 props 上。
        const props = Object.keys(el).find(key => key.startsWith('__reactProps$'));
        return !!props && Object.entries(el[props] || {}).some(([key, value]) =>
            /^on(Click|PointerDown|PointerUp|MouseDown|MouseUp|TouchEnd)(Capture)?$/.test(key) && typeof value === 'function');
    }
    function navigation(el) {
        if (!el.matches('a[href],area[href]')) return false;
        const href = el.getAttribute('href').trim();
        if (!href || href === '#' || /^javascript:/i.test(href)) return false;
        if (href.startsWith('#')) {
            let id; try { id = decodeURIComponent(href.slice(1)); } catch (_) { return false; }
            return !!document.getElementById(id) || !!document.getElementsByName(id).length;
        }
        return true;
    }
    function nativeAction(el) {
        if (el.matches('select,input[type="checkbox"],input[type="radio"],input[type="file"],input[type="color"],input[type="range"]')) return true;
        if (el.tagName === 'SUMMARY') return el.parentElement?.tagName === 'DETAILS' && el.parentElement.querySelector('summary') === el;
        if (el.matches('button,input') && el.form) return el.type === 'submit' || el.type === 'reset';
        return false;
    }

    function enabled() {
        try { return typeof options.isEnabled === 'function' ? !!options.isEnabled() : options.enabled !== false; }
        catch (_) { return false; }
    }
    function action(el) {
        if (!(el instanceof Element) || el === document.body || el === document.documentElement || owned(el) || el.closest(BLOCKED) || el.matches(':disabled')) return false;
        return el.dataset.protoHotspot === 'true' || binding(el) || navigation(el) || nativeAction(el);
    }
    function controlLike(el) {
        return CONTROL_TAGS.has(el.tagName) && !(el.tagName === 'INPUT' && el.type === 'hidden')
            || CONTROL_ROLES.has(el.getAttribute('role')) || el.dataset.protoHotspot === 'true';
    }
    function controlIssue(el) {
        // 仅截图专用运行时中用户手动画出的矩形可使用自定尺寸。
        if (window.ProtoScreenshot && el.parentElement?.id === 'screenshot-regions' && el.classList.contains('screenshot-region')) return null;
        // 事件代理容器不能替代实际操作节点，未授权的子控件也不能让父容器整块高亮。
        if (!CONTROL_TAGS.has(el.tagName) && [...el.querySelectorAll('*')].some(child =>
            !owned(child) && (controlLike(child) || action(child)))) return 'container';
        const rect = el.getBoundingClientRect();
        // 长而矮的整行按钮可保留；高且大面积的卡片 / 面板需拆到具体控件。
        if (rect.height > 96 && rect.width * rect.height > Math.min(64000, innerWidth * innerHeight * .12)) return 'oversized';
        return null;
    }
    function currentScope() {
        try { return typeof options.scope === 'function' ? options.scope() : options.scope; }
        catch (_) { return null; }
    }
    function inScope(el, scope = currentScope()) {
        if (scope?.mode === 'all') return true;
        if (scope?.mode !== 'targets' || !Array.isArray(scope.protoIds)) return false;
        // 范围只授权该控件自身；容器标注不授权内部的历史交互。
        return scope.protoIds.includes(el.getAttribute('data-proto-id'));
    }
    function hitAction(target) {
        if (currentScope()?.manualTargets?.length && scan().some(item => item.source === 'manual' && item.status === 'ready' && item.el.contains(target))) return true;
        for (let el = target instanceof Element ? target : target?.parentElement; el && el !== document.documentElement; el = el.parentElement)
            if ((controlLike(el) || action(el)) && !controlIssue(el) && rectFor(el)) return true;
        return false;
    }
    function rectFor(el) {
        if (!el?.isConnected || owned(el) || el.closest(BLOCKED) || el.matches(':disabled')) return null;
        const original = el.getBoundingClientRect();
        let left = Math.max(0, original.left), top = Math.max(0, original.top);
        let right = Math.min(innerWidth, original.right), bottom = Math.min(innerHeight, original.bottom);
        for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
            const css = getComputedStyle(node);
            if (css.display === 'none' || css.visibility === 'hidden' || Number(css.opacity) === 0) return null;
            if (node === el) continue;
            const clip = node.getBoundingClientRect();
            if (/hidden|clip|auto|scroll/.test(css.overflowX)) { left = Math.max(left, clip.left); right = Math.min(right, clip.right); }
            if (/hidden|clip|auto|scroll/.test(css.overflowY)) { top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom); }
        }
        if (right - left < 4 || bottom - top < 4) return null;
        if ((right - left) * (bottom - top) > innerWidth * innerHeight * .65 && !(window.ProtoScreenshot && el.parentElement?.id === 'screenshot-regions')) return null;
        const points = [[.5, .5], [.2, .2], [.8, .8]];
        if (!points.some(([x, y]) => {
            const hit = document.elementFromPoint(left + (right - left) * x, top + (bottom - top) * y);
            return hit === el || !!hit && el.contains(hit);
        })) return null;
        return { left, top, right, bottom };
    }
    function examine(el, manual = false) {
        if (owned(el) || el.closest('[data-proto-hotspot="false"]')) return { status: 'excluded' };
        if (el.matches(':disabled') || el.closest('[inert],[aria-disabled="true"]')) return { status: 'disabled' };
        for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
            const css = getComputedStyle(node);
            if (node.matches('[hidden],[aria-hidden="true"]') || css.display === 'none' || css.visibility === 'hidden' || Number(css.opacity) === 0)
                return { status: 'hidden' };
        }
        if (/^(SCRIPT|STYLE|LINK|META|OPTION|OPTGROUP|PATH|SVG)$/.test(el.tagName)) return { status: 'unsupported' };
        const issue = controlIssue(el);
        if (issue) return { status: issue };
        if (!manual && !action(el)) return { status: 'no-action' };
        const bounds = el.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return { status: 'hidden' };
        if (bounds.bottom <= 0 || bounds.top >= innerHeight || bounds.right <= 0 || bounds.left >= innerWidth) return { status: 'offscreen' };
        const rect = rectFor(el);
        return rect ? { status: 'ready', rect } : { status: 'occluded' };
    }
    function scan(scope = currentScope()) {
        const elements = [...document.querySelectorAll('body *')], byId = new Map();
        for (const el of elements) {
            const id = el.getAttribute('data-proto-id');
            if (id) { if (!byId.has(id)) byId.set(id, []); byId.get(id).push(el); }
        }
        const anchorFor = el => {
            if (window.ProtoAnchors) {
                const A = window.ProtoAnchors;
                return { protoId: el.getAttribute('data-proto-id') || '', selector: A.selector(el), tag: el.tagName.toLowerCase(), text: A.text(el), parentText: A.text(el.parentElement) };
            }
            return { protoId: el.getAttribute('data-proto-id') || '', selector: el.id ? '#' + CSS.escape(el.id) : '', tag: el.tagName.toLowerCase() };
        };
        const resolve = anchor => {
            if (anchor?.protoId) { const hits = byId.get(anchor.protoId) || []; return hits.length === 1 ? hits[0] : null; }
            if (window.ProtoAnchors) return window.ProtoAnchors.resolveHidden(anchor);
            try { const hits = [...document.querySelectorAll(anchor?.selector || ':not(*)')]; return hits.length === 1 ? hits[0] : null; } catch (_) { return null; }
        };
        let entries = [];
        if (scope?.mode === 'targets' && Array.isArray(scope.protoIds)) {
            entries = scope.protoIds.map(protoId => {
                const hits = byId.get(protoId) || [];
                const base = { protoId, key: 'proto:' + protoId, source: 'declared', anchor: { protoId } };
                if (hits.length !== 1) return { ...base, status: hits.length ? 'duplicate' : 'missing' };
                return { ...base, el: hits[0], label: labelFor(hits[0]), anchor: anchorFor(hits[0]), ...examine(hits[0]) };
            });
        } else if (scope?.mode === 'all') {
            entries = elements.filter(el => action(el)).map(el => ({
                protoId: el.getAttribute('data-proto-id') || el.id || el.tagName.toLowerCase(), source: 'automatic',
                anchor: anchorFor(el), label: labelFor(el), key: 'all:' + (el.getAttribute('data-proto-id') || el.id || anchorFor(el).selector), el, ...examine(el)
            }));
        }
        for (const target of scope?.manualTargets || []) {
            const el = resolve(target.anchor);
            const existing = el && entries.find(item => item.el === el);
            if (existing) entries = entries.filter(item => item !== existing);
            entries.push({ ...target, key: 'manual:' + target.id, source: 'manual', protoId: target.anchor.protoId || target.id, el,
                ...(el ? examine(el, true) : { status: target.anchor.protoId && (byId.get(target.anchor.protoId)?.length || 0) > 1 ? 'duplicate' : 'missing' }) });
        }
        const excluded = (scope?.excludedTargets || []).map(target => resolve(target.anchor)).filter(Boolean);
        for (const item of entries) if (item.el && excluded.includes(item.el)) item.status = 'excluded';
        const ready = entries.filter(item => item.status === 'ready');
        let count = 0;
        for (const item of ready) {
            if (ready.some(other => other.el !== item.el && item.el.contains(other.el))) item.status = 'contains-target';
            else if (++count > MAX_HINTS) item.status = 'limit';
        }
        return entries;
    }
    function labelFor(el) { return (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || el.value || el.tagName).replace(/\s+/g, ' ').trim().slice(0, 120); }
    function candidate(el) { return el instanceof Element ? { ...examine(el, true), label: labelFor(el) } : { status: 'missing' }; }
    // 只读诊断，不执行点击、不展开页面，也不修改 PRD / 提示配置。
    function inspect() {
        const scope = currentScope();
        return { mode: scope?.mode || 'off', enabled: enabled(), items: scan(scope).map(({ el, ...item }) => item) };
    }
    function position(box, rect) {
        box.style.left = Math.max(0, rect.left - 3) + 'px';
        box.style.top = Math.max(0, rect.top - 3) + 'px';
        box.style.width = Math.min(innerWidth, rect.right + 3) - Math.max(0, rect.left - 3) + 'px';
        box.style.height = Math.min(innerHeight, rect.bottom + 3) - Math.max(0, rect.top - 3) + 'px';
    }
    function hide() {
        clearTimeout(timer); timer = 0;
        cancelAnimationFrame(frame); frame = 0;
        boxes.clear(); layer?.replaceChildren();
    }
    function refresh() {
        frame = 0;
        if (!enabled()) { hide(); return; }
        const ready = new Map(scan().filter(item => item.status === 'ready').map(item => [item.el, item.rect]));
        for (const [el, box] of boxes) {
            const rect = ready.get(el);
            if (!rect) { box.remove(); boxes.delete(el); }
            else position(box, rect);
        }
    }
    function schedule() {
        if (boxes.size && !frame) frame = requestAnimationFrame(refresh);
    }
    function show() {
        if (!layer || !enabled()) { hide(); return 0; }
        const scope = currentScope();
        if (scope?.mode !== 'all' && (scope?.mode !== 'targets' || !scope.protoIds?.length && !scope.manualTargets?.length)) { hide(); return 0; }
        if (boxes.size && performance.now() - started < DURATION) { refresh(); return boxes.size; }
        hide();
        for (const { el, rect } of scan(scope).filter(item => item.status === 'ready')) {
            const box = document.createElement('div');
            box.className = 'ph-box'; box.setAttribute('data-prototype-owned', '');
            box.dataset.hotspotFor = el.getAttribute('data-proto-id') || el.id || el.tagName.toLowerCase();
            position(box, rect); layer.appendChild(box); boxes.set(el, box);
        }
        if (boxes.size) { started = performance.now(); timer = setTimeout(hide, DURATION); }
        return boxes.size;
    }
    function pointerDown(event) { down = { x: event.clientX, y: event.clientY, moved: false }; }
    function pointerMove(event) {
        if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 8) down.moved = true;
    }
    function click(event) {
        const drag = down?.moved; down = null;
        const target = event.target instanceof Element ? event.target : event.target?.parentElement;
        if (!enabled() || owned(target) || hitAction(target)) { hide(); return; }
        if (event.defaultPrevented || event.button !== 0 || event.detail === 0 || drag || target?.closest(EDITABLE) || String(getSelection()).trim()) return;
        show();
    }
    function mutations(records) {
        if (!boxes.size) return;
        for (const record of records) {
            if (owned(record.target)) continue;
            if (record.type === 'attributes' && /data-proto-(page|state)/.test(record.attributeName)) { hide(); return; }
            if (record.type === 'childList' && [...record.addedNodes, ...record.removedNodes].every(node => node instanceof Element && owned(node))) continue;
            schedule(); break;
        }
    }
    function init(config = {}) {
        options = config;
        if (layer) { hide(); return window.ProtoHotspots; }
        style = document.createElement('style'); style.setAttribute('data-prototype-owned', '');
        style.textContent = `
.ph-layer{--ph-fill:${COLORS.fill};--ph-opacity-low:.18;--ph-opacity-high:.42;--ph-opacity-still:.3;position:fixed;inset:0;z-index:2147481000;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;pointer-events:none!important;overflow:hidden;}
.ph-layer .ph-box{position:absolute;box-sizing:border-box;margin:0;padding:0;border:0!important;outline:0!important;border-radius:6px;background:var(--ph-fill);box-shadow:none!important;pointer-events:none!important;opacity:var(--ph-opacity-still);animation:ph-discover ${DURATION}ms cubic-bezier(.4,0,.2,1) 1 forwards;}
@keyframes ph-discover{0%{opacity:var(--ph-opacity-low)}20%{opacity:var(--ph-opacity-high)}45%{opacity:var(--ph-opacity-low)}70%{opacity:var(--ph-opacity-high)}100%{opacity:0}}
@media(prefers-reduced-motion:reduce){.ph-layer .ph-box{animation:none;opacity:var(--ph-opacity-still)}}
`;
        layer = document.createElement('div'); layer.className = 'ph-layer';
        layer.setAttribute('data-prototype-owned', ''); layer.setAttribute('aria-hidden', 'true');
        (document.head || document.documentElement).appendChild(style); document.documentElement.appendChild(layer);
        document.addEventListener('pointerdown', pointerDown, true);
        document.addEventListener('pointermove', pointerMove, true);
        document.addEventListener('pointercancel', hide, true);
        document.addEventListener('click', click);
        document.addEventListener('scroll', schedule, true);
        window.addEventListener('resize', schedule);
        window.addEventListener('pagehide', hide);
        observer = new MutationObserver(mutations);
        observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['style', 'class', 'hidden', 'inert', 'disabled', 'aria-hidden', 'aria-disabled', 'role', 'onclick', 'href', 'type', 'data-proto-id', 'data-proto-hotspot', 'data-proto-state', 'data-proto-page'] });
        return window.ProtoHotspots;
    }
    function destroy() {
        hide(); observer?.disconnect(); observer = null;
        document.removeEventListener('pointerdown', pointerDown, true);
        document.removeEventListener('pointermove', pointerMove, true);
        document.removeEventListener('pointercancel', hide, true);
        document.removeEventListener('click', click);
        document.removeEventListener('scroll', schedule, true);
        window.removeEventListener('resize', schedule); window.removeEventListener('pagehide', hide);
        layer?.remove(); style?.remove(); layer = null; style = null; down = null;
    }
    window.ProtoHotspots = { init, show, hide, destroy, inspect, candidate };
})();
