/* 稳定锚点与可见元素选择；不向业务 DOM 注入高亮 class。
   基线复用自「原型生成全流程」extension/content/anchors.js；标注工作台增补折叠引导、条件显现路径与响应式落点。
   全流程已于 2026-09-26 归档至 独立项目\_归档\原型生成全流程\。 */
(() => {
    'use strict';
    if (globalThis.ProtoAnchors) return;
    const owned = (el) => !!el?.closest?.('[data-prototype-owned]');
    const text = (el) => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 400);
    const loose = (s) => (s || '').replace(/\s+/g, '');
    const grams = (s) => { const set = new Set(); for (let i = 0; i + 1 < s.length; i++) set.add(s.slice(i, i + 2)); return set; };
    /* 文本身份校验：短文本（按钮、标签、单元格）必须逐字相同；长文本（面板、表格、整个筛选区）只要求字符二元组包含率 ≥ .75。
       容器的 innerText 会随条件行显隐、计数、日期等动态内容变化，逐字比对会把整块面板判成「目标变化」，序号全部消失。
       隐藏子树的 innerText 退化为 textContent 丢掉 span 间空格，故两侧先去掉全部空白再比。 */
    function sameText(el, expected) {
        if (!expected) return true;
        const a = loose(text(el)), b = loose(expected);
        if (a === b) return true;
        if (Math.min(a.length, b.length) < 24) return false;
        const ga = grams(a), gb = grams(b);
        let hit = 0;
        for (const g of ga) if (gb.has(g)) hit++;
        return hit / Math.min(ga.size, gb.size) >= 0.75;
    }
    // 选择器就是页面唯一 id：id 本身即身份，文本变化（占位符→已选值、计数刷新）不视为目标变化。
    const idBound = (anchor) => /^#[^\s>+~]+$/.test(anchor?.selector || '');
    const visible = (el) =>
        !!el &&
        !owned(el) &&
        el.getClientRects().length > 0 &&
        getComputedStyle(el).display !== 'none' &&
        getComputedStyle(el).visibility !== 'hidden';
    function selector(el) {
        if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1)
            return '#' + CSS.escape(el.id);
        const path = [];
        for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
            let part = n.tagName.toLowerCase();
            if (n.id && document.querySelectorAll('#' + CSS.escape(n.id)).length === 1) {
                path.unshift('#' + CSS.escape(n.id));
                break;
            }
            const same = n.parentElement
                ? [...n.parentElement.children].filter((x) => x.tagName === n.tagName)
                : [];
            if (same.length > 1) part += `:nth-of-type(${same.indexOf(n) + 1})`;
            path.unshift(part);
        }
        return path.join(' > ');
    }
    function controlLabel(el) {
        const byFor = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
        const label = el.labels?.[0] || byFor || el.closest('label') || el.closest('.f-item,.form-item,.form-group,.field')?.querySelector('label');
        return text(label).replace(/[：:]$/, '').slice(0, 80);
    }
    function conditionRow(el, kind, value, option, targetRect, explicit = false, label = '') {
        if (!el || owned(el) || !visible(el) || el.disabled || el.getAttribute?.('aria-disabled') === 'true') return null;
        const r = el.getBoundingClientRect();
        const dx = r.left + r.width / 2 - (targetRect.left + targetRect.width / 2);
        const dy = r.top + r.height / 2 - (targetRect.top + targetRect.height / 2);
        return { selector: selector(el), kind, value, option: String(option || '').slice(0, 80),
            label: String(label || controlLabel(el)).slice(0, 80), explicit, distance: explicit ? -1 : Math.hypot(dx, dy) };
    }
    function captureConditions(target, targetRect) {
        /* 通用“显现路径”：记录创建标注时使目标可见的状态控件，目标日后 display:none 或被动态移出 DOM，
           仍能把引导挂回条件控件并恢复当时状态。自动覆盖 native select/checkbox/radio 与常见 ARIA 控件；
           任意自定义 JS 控件用祖先 data-proto-reveal-by/value/label 显式声明，避免靠文案猜业务动作。 */
        const rows = [], seen = new Set();
        const add = row => {
            if (!row) return;
            const key = `${row.selector}\n${row.kind}\n${row.value}`;
            if (!seen.has(key)) { seen.add(key); rows.push(row); }
        };
        for (let n = target; n && n !== document.documentElement; n = n.parentElement) {
            const by = n.getAttribute?.('data-proto-reveal-by');
            if (!by) continue;
            let control = null;
            try { control = document.querySelector(by); } catch (_) { /* 声明选择器失效 */ }
            if (!control) continue;
            const raw = n.getAttribute('data-proto-reveal-value') ?? '';
            const kind = control.tagName === 'SELECT' ? 'select' : /^(checkbox|radio)$/.test(control.type) ? control.type : 'click';
            const value = kind === 'select' ? raw : kind === 'click' ? raw || 'true' : raw === 'true';
            add(conditionRow(control, kind, value, raw || text(control), targetRect, true, n.getAttribute('data-proto-reveal-label') || ''));
        }
        for (const el of document.querySelectorAll('select,input[type="checkbox"],input[type="radio"]')) {
            if (!visible(el)) continue;
            let kind, value, initial, option = '';
            if (el.tagName === 'SELECT') {
                kind = 'select'; value = el.value;
                const def = [...el.options].find(o => o.defaultSelected) || el.options[0];
                initial = def?.value ?? '';
                option = el.selectedOptions?.[0]?.textContent?.trim() || value;
                if (value === initial) continue;
            } else {
                kind = el.type; value = !!el.checked; initial = !!el.defaultChecked;
                if (value === initial || (kind === 'radio' && !value)) continue;
                // checkbox 同时记录「由默认勾选切为未勾选」；radio 只记录当前选中的新项，避免同组旧项制造反向条件。
                option = el.value || controlLabel(el);
            }
            add(conditionRow(el, kind, value, option, targetRect));
        }
        const aria = '[role="tab"][aria-selected="true"],[aria-pressed="true"],[aria-expanded="true"][aria-controls],[role="radio"][aria-checked="true"],[role="checkbox"][aria-checked="true"]';
        for (const el of document.querySelectorAll(aria)) {
            const kind = el.matches('[role="tab"]') ? 'aria-selected' : el.hasAttribute('aria-pressed') ? 'aria-pressed' :
                el.hasAttribute('aria-expanded') ? 'aria-expanded' : 'aria-checked';
            add(conditionRow(el, kind, 'true', text(el) || controlLabel(el), targetRect));
        }
        return rows.sort((a, b) => a.distance - b.distance).slice(0, 12).map(({ distance, ...row }) => row);
    }
    function serialize(el) {
        const r = el.getBoundingClientRect();
        const clean = el.cloneNode(true);
        clean.querySelectorAll('[data-prototype-owned],script').forEach((n) => n.remove());
        const conditions = captureConditions(el, r);
        const anchor = {
            protoId: el.getAttribute('data-proto-id') || '',
            selector: selector(el),
            tag: el.tagName.toLowerCase(),
            text: text(el),
            parentText: text(el.parentElement),
            htmlSnippet: clean.outerHTML.slice(0, 1800),
            rect: {
                x: Math.round(r.x + scrollX),
                y: Math.round(r.y + scrollY),
                width: Math.round(r.width),
                height: Math.round(r.height),
            },
        };
        if (conditions.length) anchor.conditions = conditions;
        return anchor;
    }
    function resolve(anchor) {
        if (!anchor) return { element: null, reason: '尚未绑定元素' };
        if (anchor.protoId) {
            const list = [
                ...document.querySelectorAll(`[data-proto-id="${CSS.escape(anchor.protoId)}"]`),
            ].filter(visible);
            if (list.length === 1 && (!anchor.tag || list[0].tagName.toLowerCase() === anchor.tag))
                return { element: list[0] };
            return {
                element: null,
                reason: list.length > 1 ? '稳定 ID 重复，请重新绑定' : '目标已移除或当前状态不可见',
            };
        }
        try {
            const list = [...document.querySelectorAll(anchor.selector || ':not(*)')].filter(visible);
            if (
                list.length === 1 &&
                (!anchor.tag || list[0].tagName.toLowerCase() === anchor.tag) &&
                (idBound(anchor) || sameText(list[0], anchor.text))
            )
                return { element: list[0] };
        } catch (_) {
            /* 旧选择器可能失效，继续尝试唯一文本。 */
        }
        if (anchor.text && /^[a-z][a-z0-9-]*$/i.test(anchor.tag || '')) {
            const candidates = [...document.querySelectorAll(anchor.tag)].filter(
                (el) =>
                    visible(el) &&
                    sameText(el, anchor.text) &&
                    sameText(el.parentElement, anchor.parentText),
            );
            if (candidates.length === 1) return { element: candidates[0] };
            if (candidates.length > 1) return { element: null, reason: '存在多个同名目标，请重新绑定' };
        }
        return { element: null, reason: '目标变化，等待重新定位' };
    }
    function at(x, y) {
        return (
            document
                .elementsFromPoint(x, y)
                .find((el) => !owned(el) && !['HTML', 'BODY'].includes(el.tagName)) || null
        );
    }
    /* 元素的可见矩形：被视口与各级 overflow 祖先裁剪后的区域。
       reach 记录被裁掉的每一侧「用户滚动能否把它露出来」：裁剪者是滚动容器 / 视口且尚未滚到尽头 → 能；
       overflow:hidden|clip、滚到尽头、或视口比元素窄导致的负向溢出（flex 居中的手机壳左缘在 x<0）→ 不能。 */
    function rect(el, fullDocument = false) {
        const r = el.getBoundingClientRect(), doc = document.documentElement;
        const vp = fullDocument
            ? { left: -scrollX, top: -scrollY, right: doc.scrollWidth - scrollX, bottom: doc.scrollHeight - scrollY }
            : { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
        const clip = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
        const by = {};   // 每侧由谁裁掉（裁到同一坐标的全部记下）：null = 视口 / 文档边界，否则为滚动容器节点；未被裁为 undefined
        const cut = (k, v, node, tighter) => {
            if (tighter(v, clip[k])) { clip[k] = v; by[k] = [node]; }
            else if (by[k] && Math.abs(v - clip[k]) < 0.5) by[k].push(node);   // 视口与滚动容器边缘重合：任一能滚即算滚得出来
        };
        const gt = (a, b) => a > b, lt = (a, b) => a < b;
        cut('left', vp.left, null, gt); cut('top', vp.top, null, gt);
        cut('right', vp.right, null, lt); cut('bottom', vp.bottom, null, lt);
        for (let n = el.parentElement; n; n = n.parentElement) {
            if (fullDocument && n === document.scrollingElement) continue;
            const s = getComputedStyle(n), p = n.getBoundingClientRect();
            if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) {
                cut('left', p.left + n.clientLeft, n, gt);
                cut('right', p.left + n.clientLeft + n.clientWidth, n, lt);
            }
            if (/(auto|scroll|hidden|clip)/.test(s.overflowY)) {
                cut('top', p.top + n.clientTop, n, gt);
                cut('bottom', p.top + n.clientTop + n.clientHeight, n, lt);
            }
        }
        const scrollable = (n, axis) => n === null ? !fullDocument : /(auto|scroll)/.test(getComputedStyle(n)['overflow' + axis]);
        const canScroll = (n, axis, before) => {
            if (!scrollable(n, axis)) return false;
            const pos = n ? (axis === 'X' ? n.scrollLeft : n.scrollTop) : (axis === 'X' ? scrollX : scrollY);
            if (before) return pos > 0.5;
            const size = n ? (axis === 'X' ? n.clientWidth : n.clientHeight) : (axis === 'X' ? innerWidth : innerHeight);
            const total = n ? (axis === 'X' ? n.scrollWidth : n.scrollHeight) : (axis === 'X' ? doc.scrollWidth : doc.scrollHeight);
            return pos + size < total - 0.5;
        };
        const reachable = (k, axis, before) => !by[k] || by[k].some((n) => canScroll(n, axis, before));
        const reach = { left: reachable('left', 'X', true), right: reachable('right', 'X', false),
            top: reachable('top', 'Y', true), bottom: reachable('bottom', 'Y', false) };
        return { x: clip.left, y: clip.top, width: Math.max(0, clip.right - clip.left), height: Math.max(0, clip.bottom - clip.top),
            visible: clip.right > clip.left && clip.bottom > clip.top, reach };
    }
    function placement(el, x, y) {
        if (!el) return { kind: 'document', x: x + scrollX, y: y + scrollY };
        const r = el.getBoundingClientRect(), px = x - r.left + el.scrollLeft, py = y - r.top + el.scrollTop;
        // 同存绝对偏移与比例：绝对值保持旧行为，rx/ry 让响应式控件变窄/变高后仍能落在同一相对位置。
        return { kind: 'element', x: px, y: py,
            rx: r.width > 0 ? Math.max(0, Math.min(1, px / r.width)) : 0,
            ry: r.height > 0 ? Math.max(0, Math.min(1, py / r.height)) : 0 };
    }
    function point(note, fullDocument = false) {
        const p = note.placement;
        if (p?.kind === 'document') {
            const x = p.x - scrollX, y = p.y - scrollY;
            if (p.x > document.documentElement.scrollWidth || p.y > document.documentElement.scrollHeight)
                return { reason: '页面尺寸已变化，请重新定位', point: null, rect: null };
            const visible = fullDocument || (x >= 0 && y >= 0 && x < innerWidth && y < innerHeight);
            return { point: { x, y, visible }, rect: { x, y, width: 0, height: 0, visible } };
        }
        const found = resolve(note.anchor);
        if (!found.element) return { reason: found.reason, point: null, rect: null };
        const element = found.element, r = element.getBoundingClientRect(), clip = rect(element, fullDocument);
        if (!p) return { element, rect: clip, point: { x: clip.x, y: clip.y, visible: clip.visible }, legacy: true };
        const ew = Math.max(r.width, element.scrollWidth), eh = Math.max(r.height, element.scrollHeight);
        let px = p.x, py = p.y;
        if (Number.isFinite(p.rx) && Number.isFinite(p.ry)) {
            px = p.rx * ew; py = p.ry * eh;
        } else {
            // 旧锚点无 rx/ry：仅当当前响应式尺寸缩小导致绝对偏移越界、且偏移在创建时 rect 内时，按原尺寸比例回退。
            const base = note.anchor?.rect;
            if (px > ew && base?.width > 0 && px <= base.width) px = px / base.width * ew;
            if (py > eh && base?.height > 0 && py <= base.height) py = py / base.height * eh;
        }
        if (px > ew || py > eh)
            return { element, reason: '落点超出目标范围，请重新定位', rect: clip, point: null };
        let x = r.left + px - element.scrollLeft, y = r.top + py - element.scrollTop;
        // 元素本身可见、落点却落在被裁掉的那一侧，且那一侧再怎么滚也露不出来（视口比元素窄、overflow:hidden、已滚到尽头）：
        // 把落点夹回可见区边缘，否则整宽元素左缘的序号在窄视口里永远不出现。还能滚出来的照旧隐藏，等用户滚过来。
        if (clip.visible && clip.reach) {
            const right = clip.x + clip.width, bottom = clip.y + clip.height;
            if (x < clip.x && !clip.reach.left) x = clip.x;
            if (x > right && !clip.reach.right) x = right;
            if (y < clip.y && !clip.reach.top) y = clip.y;
            if (y > bottom && !clip.reach.bottom) y = bottom;
        }
        const visible = clip.visible && x >= clip.x && x <= clip.x + clip.width && y >= clip.y && y <= clip.y + clip.height;
        return { element, rect: clip, point: { x, y, visible } };
    }
    function inBox(box) {
        const nodes = [
            ...document.querySelectorAll(
                'button,input,img,a,p,h1,h2,h3,h4,li,label,select,textarea,[data-proto-id]',
            ),
        ].filter((el) => {
            if (!visible(el)) return false;
            const r = el.getBoundingClientRect();
            return (
                r.width &&
                r.height &&
                r.left < box.right &&
                r.right > box.left &&
                r.top < box.bottom &&
                r.bottom > box.top &&
                [[.5,.5],[.1,.1],[.9,.1],[.1,.9],[.9,.9]].some(([u,v]) => {
                    const hit = at(r.left + r.width * u, r.top + r.height * v);
                    return hit === el || (hit && el.contains(hit));
                })
            );
        });
        return nodes.filter((el) => !nodes.some((other) => other !== el && other.contains(el))).slice(0, 100);
    }
    function currentIds() {
        return {
            pageId: document.documentElement.dataset.protoPage || 'main',
            stateId: document.documentElement.dataset.protoState || 'default',
        };
    }
    async function enterState(stateId) {
        if (typeof window.PrototypeBridge?.enter === 'function') await window.PrototypeBridge.enter(stateId);
        return currentIds();
    }
    // ---------- 折叠区展开 / 引导（标注工作台“点序号联动展开”与“点击引导”复用；全流程已归档，此为标注侧增补） ----------
    function hidden(el) {
        if (!el) return true;
        const cs = getComputedStyle(el);
        return cs.display === 'none' || cs.visibility === 'hidden' || el.getClientRects().length === 0;
    }
    function resolveHidden(anchor) {
        // 与 resolve 同规则但不过滤可见性：定位被折叠/隐藏的目标元素
        if (!anchor) return null;
        const all = (sel) => { try { return [...document.querySelectorAll(sel)].filter((el) => !owned(el)); } catch (_) { return []; } };
        if (anchor.protoId) {
            const list = all(`[data-proto-id="${CSS.escape(anchor.protoId)}"]`);
            return list.length === 1 && (!anchor.tag || list[0].tagName.toLowerCase() === anchor.tag) ? list[0] : null;
        }
        const list = all(anchor.selector || ':not(*)');
        if (list.length === 1 && (!anchor.tag || list[0].tagName.toLowerCase() === anchor.tag) && (idBound(anchor) || sameText(list[0], anchor.text))) return list[0];
        if (anchor.text && /^[a-z][a-z0-9-]*$/i.test(anchor.tag || '')) {
            const c = all(anchor.tag).filter((el) => sameText(el, anchor.text) && sameText(el.parentElement, anchor.parentText));
            if (c.length === 1) return c[0];
        }
        return null;
    }
    function conditionValue(el, condition) {
        if (condition.kind === 'select') return el.value;
        if (condition.kind === 'checkbox' || condition.kind === 'radio') return !!el.checked;
        if (condition.kind.startsWith('aria-')) return el.getAttribute(condition.kind);
        return null;
    }
    function conditionGuideLabel(condition) {
        const value = condition.option || condition.value || condition.label || '条件';
        if (condition.kind === 'select') return `选择 ${value}`;
        if (condition.kind === 'aria-selected') return `切换到 ${value}`;
        if (condition.kind === 'aria-expanded') return `展开 ${condition.label || value}`;
        return `开启 ${condition.label || value}`;
    }
    function conditionTrigger(anchor) {
        const rows = Array.isArray(anchor?.conditions) ? anchor.conditions : [];
        let fallback = null;
        for (const condition of rows) {
            let el = null;
            try { el = document.querySelector(condition.selector || ':not(*)'); } catch (_) { /* 旧条件选择器失效 */ }
            if (!el || owned(el) || !visible(el)) continue;
            const hit = { element: el, condition, label: conditionGuideLabel(condition) };
            if (conditionValue(el, condition) !== condition.value) return hit;
            // 条件已满足却仍不可见：原生 change 与显式声明允许重放同值事件兜底（satisfied 标记，排在折叠触发器之后）；
            // ARIA 同值点击可能反向关闭，不作为 fallback。
            if (!fallback && (condition.explicit || ['select', 'checkbox', 'radio'].includes(condition.kind))) fallback = { ...hit, satisfied: true };
        }
        return fallback;
    }
    function applyCondition(hit) {
        if (!hit?.element) return false;
        const { element, condition } = hit;
        if (condition.kind === 'select') element.value = condition.value;
        else if (condition.kind === 'checkbox' || condition.kind === 'radio') element.checked = !!condition.value;
        else { element.click(); return true; }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }
    const failedRevealTriggers = new WeakMap();
    const DISCLOSURE_WORDS = /(?:展开|更多|显示|查看|收起|高级|筛选|折叠|expand|more|show|toggle)/i;
    function revealFailed(el, trigger) {
        return !!el && !!trigger && !!failedRevealTriggers.get(el)?.has(trigger);
    }
    function markRevealFailed(el, trigger) {
        if (!el || !trigger) return;
        let failed = failedRevealTriggers.get(el);
        if (!failed) failedRevealTriggers.set(el, (failed = new WeakSet()));
        failed.add(trigger);
    }
    function neighboringBranch(hiddenNode, trigger) {
        const parent = hiddenNode?.parentElement;
        if (!parent || !trigger) return false;
        let branch = trigger;
        while (branch && branch.parentElement !== parent) branch = branch.parentElement;
        return !!branch && (branch === hiddenNode.previousElementSibling || branch === hiddenNode.nextElementSibling);
    }
    function weakRevealCandidate(target, hiddenNode, trigger) {
        if (!trigger || owned(trigger) || hiddenNode.contains(trigger) || !visible(trigger) || revealFailed(target, trigger)) return false;
        // 旧锚点没有 aria-controls 时，只接受隐藏分支相邻区域中的明确展开语义；不能把同容器内任意“导出/新建”按钮猜成触发器。
        if (!neighboringBranch(hiddenNode, trigger)) return false;
        if (trigger.tagName === 'SUMMARY' || trigger.getAttribute?.('aria-expanded') === 'false') return true;
        const role = trigger.getAttribute?.('role');
        if (trigger.tagName !== 'BUTTON' && role !== 'button') return false;
        const label = `${text(trigger)} ${trigger.getAttribute?.('aria-label') || ''} ${trigger.getAttribute?.('title') || ''}`;
        return DISCLOSURE_WORDS.test(label);
    }
    function revealTrigger(el, strongOnly = false) {
        // 找到能让 el 显现的折叠触发器：原生 details / aria-controls 是强关联；相邻且有展开语义的按钮仅作旧锚点退路
        for (let n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
            if (n.tagName === 'DETAILS' && !n.open && !revealFailed(el, n)) return n;
            if (n.id) {
                const ctrls = [...document.querySelectorAll('[aria-controls]')].filter((c) =>
                    !owned(c) && !revealFailed(el, c) && (c.getAttribute('aria-controls') || '').split(/\s+/).includes(n.id));
                const hit = ctrls.find((c) => c.getAttribute('aria-expanded') === 'false') || ctrls.find((c) => visible(c));
                if (hit && visible(hit)) return hit;
            }
        }
        if (strongOnly) return null;
        for (let n = el; n && n !== document.body; n = n.parentElement) {
            if (!hidden(n)) continue;
            const scope = n.parentElement || document;
            const cand = [...scope.querySelectorAll('[aria-expanded="false"], summary, button, [role="button"]')]
                .find((t) => weakRevealCandidate(el, n, t));
            if (cand) return cand;
        }
        return null;
    }
    function declaredCondition(el) {
        // 从外向内找当前可用的入口；导入标注没有 conditions 时也读取页面上的显现声明。
        const chain = [];
        for (let n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) chain.unshift(n);
        for (const node of chain) {
            const by = node.getAttribute?.('data-proto-reveal-by');
            if (!by || !hidden(node)) continue;
            let controls = [];
            try { controls = [...document.querySelectorAll(by)]; } catch (_) { continue; }
            if (controls.length !== 1) continue;
            const control = controls[0];
            if (owned(control) || !visible(control) || control.disabled || control.getAttribute('aria-disabled') === 'true' || revealFailed(el, control)) continue;
            const raw = node.getAttribute('data-proto-reveal-value') ?? 'true';
            const kind = control.tagName === 'SELECT' ? 'select' : /^(checkbox|radio)$/.test(control.type) ? control.type : 'click';
            const condition = { selector: by, kind, value: kind === 'select' ? raw : kind === 'click' ? raw : raw === 'true', explicit: true,
                label: node.getAttribute('data-proto-reveal-label') || controlLabel(control), option: raw };
            return { element: control, condition, label: node.getAttribute('data-proto-reveal-label') || conditionGuideLabel(condition) };
        }
        return null;
    }
    function revealHint(anchor, el = resolveHidden(anchor)) {
        if (el && !hidden(el)) return null; // 目标已显现；若落点异常应走失锚/响应式回退，不能继续显示条件引导
        const declared = el ? declaredCondition(el) : null;
        if (declared) return { trigger: declared.element, target: anchor || el, label: declared.label, kind: 'condition' };
        // 优先语义明确的 details / aria-controls；其次用创建标注时记录的、当前值确实不同的状态条件；
        // 再用邻近按钮弱推断；条件值已满足却仍隐藏的同值重放排最后（否则弹层折叠时会误显「选择 智能体」）。
        const direct = el ? revealTrigger(el, true) : null;
        if (direct) return { trigger: direct, target: el, label: '展开', kind: 'disclosure' };
        const condition = conditionTrigger(anchor);
        const conditionHint = condition ? { trigger: condition.element, target: anchor, label: condition.label, kind: 'condition' } : null;
        if (conditionHint && !condition.satisfied) return conditionHint;
        const fallback = el ? revealTrigger(el) : null;
        if (fallback) return { trigger: fallback, target: el, label: '展开', kind: 'disclosure' };
        return conditionHint;
    }
    function reveal(target, attempted = new Set(), notify = true) {
        const anchor = target && target.nodeType === 1 ? null : target;
        let el = target && target.nodeType === 1 ? target : resolveHidden(target);
        // 条件控件先恢复到创建标注时的值；change/click 处理器可同步显现，也可由 MutationObserver 在异步渲染后接力。
        const condition = (el ? declaredCondition(el) : null) || (anchor ? conditionTrigger(anchor) : null);
        if (condition && !condition.satisfied && !attempted.has(condition.element)) {
            attempted.add(condition.element);
            if (applyCondition(condition)) el = resolveHidden(anchor) || el;
        }
        // 同一触发器只点一次：Vue/React 类原型点击后 DOM 在 nextTick 才更新，同步判定仍为隐藏，
        // 循环里重复点同一个按钮会把刚展开的区域再折回去（偶数次 = 没展开）。多层折叠靠后续重排接力。
        const clicked = attempted;
        let lastAttempt = null;
        for (let g = 0; el && g < 10 && hidden(el); g++) {
            const declared = declaredCondition(el);
            const trig = declared?.element || revealTrigger(el);
            if (!trig || clicked.has(trig)) break;
            clicked.add(trig);
            lastAttempt = { element: el, trigger: trig };
            if (declared) applyCondition(declared);
            else if (trig.tagName === 'DETAILS') trig.open = true; else trig.click();
            if (anchor) el = resolveHidden(anchor) || el;
        }
        // 折叠触发器都试过仍不可见：最后才重放已满足的同值条件（select 的 change 处理器可能负责重建区域）。
        if ((!el || hidden(el)) && condition?.satisfied && !attempted.has(condition.element)) {
            attempted.add(condition.element);
            if (applyCondition(condition)) el = resolveHidden(anchor) || el;
        }
        if ((!el || hidden(el)) && lastAttempt && notify) {
            // 给 Vue/React 等异步渲染留出时间；仍未显现就记住这组无效关联，并通知两种标注层移除假引导。
            setTimeout(() => {
                const current = anchor ? resolveHidden(anchor) : lastAttempt.element;
                if (current && hidden(current)) {
                    markRevealFailed(current, lastAttempt.trigger);
                    document.dispatchEvent(new CustomEvent('proto-anchors:reveal-failed', { detail: { target: current, trigger: lastAttempt.trigger } }));
                }
            }, 450);
        }
        return !el || hidden(el) ? null : el;
    }
    const pendingReveals = new Map();
    function revealAndWait(target) {
        const key = target?.nodeType === 1 ? target : `${target?.protoId || ''}\n${target?.selector || ''}`;
        if (pendingReveals.has(key)) return pendingReveals.get(key);
        const operation = (async () => {
            const attempted = new Set(), deadline = Date.now() + 1800;
            do {
                const el = reveal(target, attempted, false);
                if (el) return el;
                if (!attempted.size) return null;
                await new Promise(resolve => setTimeout(resolve, 32));
            } while (Date.now() < deadline);
            const current = target?.nodeType === 1 ? target : resolveHidden(target);
            if (current && !hidden(current)) return current;
            if (current) for (const trigger of attempted) markRevealFailed(current, trigger);
            document.dispatchEvent(new CustomEvent('proto-anchors:reveal-failed', { detail: { target: current } }));
            return null;
        })();
        pendingReveals.set(key, operation);
        operation.finally(() => { if (pendingReveals.get(key) === operation) pendingReveals.delete(key); }).catch(() => {});
        return operation;
    }
    globalThis.ProtoAnchors = {
        owned,
        text,
        visible,
        hidden,
        selector,
        serialize,
        resolve,
        resolveHidden,
        revealTrigger,
        revealHint,
        reveal,
        revealAndWait,
        rect,
        placement,
        point,
        at,
        inBox,
        currentIds,
        enterState,
    };
})();
