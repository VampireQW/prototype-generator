/* 按稳定控件键重放手动文案；只改文字节点，保留原型事件和结构。 */
(() => {
    'use strict';
    const blocked = new Set('SCRIPT STYLE TEMPLATE NOSCRIPT SVG MATH CANVAS IFRAME OBJECT TEXTAREA'.split(' '));
    const keyed = ['data-proto-id', 'id', 'data-q', 'data-key', 'data-id', 'data-row-id', 'data-row-key', 'data-item-id', 'data-column-key', 'data-field', 'data-testid', 'name'];
    const states = new WeakMap();
    const normal = text => text.trim().replace(/\s+/g, ' ');
    function nodes(element) {
        const out = [];
        const visit = node => {
            if (node.nodeType === 3) { if (node.nodeValue.trim()) out.push(node); return; }
            if (blocked.has(node.tagName)) return;
            for (const child of node.childNodes || []) visit(child);
        };
        visit(element); return out;
    }
    function reactive(element) {
        for (let node = element; node; node = node.parentElement) {
            if (blocked.has(node.tagName) || node.hasAttribute?.('data-prototype-owned') ||
                node.__vue__ || node.__vueParentComponent || Object.keys(node).some(k => k.startsWith('__reactFiber$')) ||
                [...(node.attributes || [])].some(a => /^(v-for|v-text|v-html|ng-bind|ng-repeat|data-bind)$/.test(a.name))) return true;
        }
        return false;
    }
    const within = (parent, child) => { for (let n = child; n; n = n.parentElement) if (n === parent) return true; return false; };
    const baseText = node => states.get(node.ownerDocument || node.parentElement?.ownerDocument)?.originals.get(node) ?? node.nodeValue;
    const text = (element, own = false) => normal((own ? [...element.childNodes].filter(n => n.nodeType === 3) : nodes(element)).map(baseText).join(' '));
    function ordinal(element) {
        let index = 1;
        for (let prev = element.previousElementSibling; prev; prev = prev.previousElementSibling) if (prev.tagName === element.tagName) index++;
        return { tag: element.tagName.toLowerCase(), index };
    }
    function follow(element, path) {
        for (const step of path) {
            element = [...(element?.children || [])].filter(n => n.tagName.toLowerCase() === step.tag)[step.index - 1];
            if (!element) return null;
        }
        return element;
    }
    function matches(element, criteria) {
        return criteria.every(c => { const found = follow(element, c.path); return found && text(found, c.own) === c.text; });
    }
    function headerPaths(cell) {
        let table = cell.parentElement;
        while (table && table.tagName !== 'TABLE') table = table.parentElement;
        if (!table) return [];
        const head = [...table.children].find(n => n.tagName === 'THEAD'), grid = [];
        const rows = [...(head?.children || [])].filter(n => n.tagName === 'TR');
        rows.forEach((row, r) => {
            grid[r] ||= []; let column = 0;
            for (const th of row.children) {
                if (!['TH', 'TD'].includes(th.tagName)) continue;
                while (grid[r][column]) column++;
                const width = Math.min(100, Math.max(1, Number(th.getAttribute('colspan')) || 1));
                const height = Math.min(100, Math.max(1, th.getAttribute('rowspan') === '0' ? rows.length - r : Number(th.getAttribute('rowspan')) || 1));
                for (let y = r; y < r + height; y++) {
                    grid[y] ||= [];
                    for (let x = column; x < column + width; x++) grid[y][x] = { node: th, label: text(th) };
                }
                column += width;
            }
        });
        const paths = [];
        for (let x = 0; x < (grid[0]?.length || 0); x++) {
            const path = [], seen = new Set();
            for (const row of grid) {
                const h = row?.[x];
                if (h?.label && !seen.has(h.node)) { path.push(h.label); seen.add(h.node); }
            }
            paths.push(path);
        }
        return paths;
    }
    function columnOf(cell, paths) {
        if (!['TD', 'TH'].includes(cell.tagName) || Number(cell.getAttribute('colspan') || 1) !== 1) return null;
        let index = 0;
        for (const prev of cell.parentElement.children) {
            if (prev === cell) break;
            if (['TD', 'TH'].includes(prev.tagName)) index += Number(prev.getAttribute('colspan')) || 1;
        }
        const column = paths[index];
        return column?.length ? column : null;
    }
    function landmarks(element, selected, siblings) {
        if (element === selected) return null;
        const candidates = [], own = text(element, true);
        if (own && own.length <= 160) candidates.push({ path: [], own: true, text: own });
        function visit(node, path) {
            if (path.length >= 3 || candidates.length >= 24) return;
            for (const child of node.children) {
                if (blocked.has(child.tagName) || within(child, selected) || within(selected, child)) continue;
                const childPath = [...path, ordinal(child)], value = text(child);
                if (value && value.length <= 160) candidates.push({ path: childPath, text: value });
                else visit(child, childPath);
            }
        }
        visit(element, []);
        const chosen = [];
        for (const candidate of candidates) {
            chosen.push(candidate);
            if (siblings.filter(n => matches(n, chosen)).length === 1) return chosen;
            if (chosen.length >= 3) break;
        }
        return null;
    }
    function part(element, selected) {
        const tag = element.tagName.toLowerCase();
        for (const key of keyed) {
            const value = element.getAttribute(key);
            if (value && value.length <= 256) return { tag, key, value };
        }
        if (['TD', 'TH'].includes(element.tagName)) {
            const paths = headerPaths(element), column = columnOf(element, paths);
            if (column && paths.filter(p => JSON.stringify(p) === JSON.stringify(column)).length === 1) return { tag, column };
        }
        const siblings = [...(element.parentElement?.children || [])].filter(n => n.tagName === element.tagName);
        if (element === selected) {
            const label = text(element);
            if (label && label.length <= 160 && siblings.filter(n => text(n) === label).length === 1) return { tag, text: label };
        }
        if (['TR', 'LI', 'ARTICLE'].includes(element.tagName) || siblings.length > 1) {
            const match = landmarks(element, selected, siblings);
            if (match) return { tag, match };
        }
        return ordinal(element);
    }
    function locate(doc, binding) {
        const a = binding.anchor;
        const anchors = [...doc.getElementsByTagName(a.tag)].filter(n => !a.key || n.getAttribute(a.key) === a.value);
        if (anchors.length !== 1) return null;
        if (!a.key) {
            // A body fallback must stay unique across equivalent unkeyed containers;
            // inserting or moving another table/list must not retarget an old edit.
            let candidates = anchors, identified = false;
            for (const step of binding.path) {
                candidates = candidates.flatMap(parent => {
                    const children = [...parent.children].filter(n => n.tagName.toLowerCase() === step.tag);
                    if (step.key) return children.filter(n => n.getAttribute(step.key) === step.value);
                    if (step.match) return children.filter(n => matches(n, step.match));
                    if (step.text) return children.filter(n => text(n) === step.text);
                    if (step.column) {
                        const paths = headerPaths(children[0] || parent);
                        return children.filter(n => JSON.stringify(columnOf(n, paths)) === JSON.stringify(step.column));
                    }
                    return identified ? children.slice(step.index - 1, step.index) : children;
                });
                identified ||= !!(step.key || step.match || step.text || step.column);
                if (!candidates.length || candidates.length > 2000) return null;
            }
            return candidates.length === 1 && !reactive(candidates[0]) ? candidates[0] : null;
        }
        let node = anchors[0];
        for (const step of binding.path) {
            const children = [...node.children].filter(n => n.tagName.toLowerCase() === step.tag);
            if (step.key) {
                const found = children.filter(n => n.getAttribute(step.key) === step.value);
                if (found.length !== 1) return null;
                node = found[0];
            } else if (step.match || step.column || step.text) {
                const paths = step.column ? headerPaths(children[0] || node) : null;
                const found = children.filter(n => step.match ? matches(n, step.match) : step.text ? text(n) === step.text : JSON.stringify(columnOf(n, paths)) === JSON.stringify(step.column));
                if (found.length !== 1) return null;
                node = found[0];
            } else node = children[step.index - 1];
            if (!node) return null;
        }
        return reactive(node) ? null : node;
    }
    function bindings(element) {
        const result = [], path = [];
        for (const rule of states.get(element.ownerDocument)?.rules || []) {
            if (locate(element.ownerDocument, rule.binding) === element) result.push(rule.binding);
        }
        for (let node = element; node && path.length <= 16; node = node.parentElement) {
            for (const key of ['data-proto-id', 'id']) {
                const value = node.getAttribute(key);
                if (value && value.length <= 256) {
                    const binding = { anchor: { tag: node.tagName.toLowerCase(), key, value }, path: [...path] };
                    if (locate(element.ownerDocument, binding) === element && !result.some(b => JSON.stringify(b) === JSON.stringify(binding))) result.push(binding);
                    if (result.length >= 12) return result;
                }
            }
            if (node.tagName === 'BODY' && path.length) {
                const binding = { anchor: { tag: 'body' }, path: [...path] };
                if (locate(element.ownerDocument, binding) === element) result.push(binding);
                break;
            }
            path.unshift(part(node, element));
        }
        return result;
    }
    function install(doc, rules) {
        let state = states.get(doc);
        if (state) { state.rules = rules; state.apply(); return; }
        const Observer = doc.defaultView?.MutationObserver;
        if (!Observer || !doc.documentElement) return;
        state = { rules, observer: null, apply: null, originals: new WeakMap() };
        state.apply = () => {
            // Disconnect during our own writes so text changes do not feed back forever.
            state.observer.disconnect();
            try {
                for (const rule of state.rules) {
                    const element = locate(doc, rule.binding);
                    if (!element) continue;
                    const texts = nodes(element), current = texts.map(n => normal(n.nodeValue));
                    if (texts.length !== rule.before.length ||
                        ![rule.before, rule.after].some(expected => expected.every((t, i) => normal(t) === current[i]))) continue;
                    texts.forEach((node, i) => {
                        if (!state.originals.has(node)) state.originals.set(node, rule.before[i]);
                        if (node.nodeValue.trim() === rule.after[i]) return;
                        const prefix = node.nodeValue.match(/^\s*/)[0], suffix = node.nodeValue.match(/\s*$/)[0];
                        node.nodeValue = prefix + rule.after[i] + suffix;
                    });
                }
            } finally { state.observer.observe(doc.documentElement, { childList: true, characterData: true, subtree: true }); }
        };
        state.observer = new Observer(state.apply); states.set(doc, state); state.apply();
        doc.addEventListener('DOMContentLoaded', state.apply, { once: true });
    }
    window.ProtoTextRuntime = { bindings, install };
    const data = document.getElementById('proto-text-edits-data');
    if (data) { try { install(document, JSON.parse(data.textContent)); } catch (_) { /* Keep the original prototype usable if an override was edited externally. */ } }
})();
