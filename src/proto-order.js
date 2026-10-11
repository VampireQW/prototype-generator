/* 展示编号投影：不改元数据 number，所有定位与编辑始终使用稳定 id。
   排序键是页面逻辑坐标（视口坐标加回各级滚动偏移），从上到下、从左到右。
   目标当前不可见、但能在主页面流里靠「展开 / 选中 / 点击」显现的标注（折叠区、条件行、页签），
   用它的显现触发器位置代位参与主序，编号在展开前后保持一致，而不是被甩到末尾；
   落在弹窗 / 抽屉 / 提示等分支容器里的目标整体排在主页序号之后再自然排序；彻底失锚的排最后。 */
(() => {
    'use strict';
    const stable = (a, b) => String(a.id).localeCompare(String(b.id), 'en');
    function logicalPoint(found, win) {
        if (!found?.point) return null;
        const { element, legacy } = found;
        const point = legacy && element ? element.getBoundingClientRect() : found.point;
        let x = point.x + win.scrollX, y = point.y + win.scrollY;
        for (let node = legacy ? element?.parentElement : element; node && node !== win.document.scrollingElement; node = node.parentElement) {
            x += node.scrollLeft || 0;
            y += node.scrollTop || 0;
        }
        return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    }
    /* 分支容器判定：目标所在的祖先链里有对话框 / 抽屉 / 提示 / 下拉等「离开主页面流」的容器。
       语义属性（<dialog>、role、aria-modal、popover）直接判定；类名只作弱线索，且要求容器本身是 fixed / absolute 定位，
       否则页面主流里的 notification-list、message-item 之类命名会被误判。
       原型可用 data-proto-branch="true|false" 在任意祖先上显式声明，覆盖自动推断。 */
    const BRANCH_ROLE = /^(dialog|alertdialog|tooltip|menu)$/;
    const BRANCH_CLASS = /(^|[^a-z])(modal|dialog|drawer|popover|popup|toast|tooltip|dropdown|sheet|snackbar|notification|message)(?![a-z])/i;
    function inBranch(el, win) {
        const doc = win.document;
        for (let n = el; n && n !== doc.body && n !== doc.documentElement; n = n.parentElement) {
            if (n.hasAttribute('data-proto-branch')) return n.getAttribute('data-proto-branch') !== 'false';
            if (n.tagName === 'DIALOG' || n.hasAttribute('popover') || n.getAttribute('aria-modal') === 'true' || BRANCH_ROLE.test(n.getAttribute('role') || '')) return true;
            if (BRANCH_CLASS.test(n.getAttribute('class') || '') && /^(fixed|absolute)$/.test(win.getComputedStyle(n).position)) return true;
        }
        return false;
    }
    /* 目标不可见时的代位坐标：优先目标自身仍有的几何（visibility:hidden 一类），否则取显现触发器的下缘——
       紧跟触发器所在行之后，在其下方显现的内容也就落在正确的行序里。无触发器（真失锚）返回 null。 */
    function proxyPoint(note, el, win) {
        const PA = win.ProtoAnchors;
        if (el && !PA.hidden?.(el)) return null;                         // 元素可见却定不到落点：落点失效，按失锚置底
        if (el && el.getClientRects().length) return logicalPoint({ element: el, point: el.getBoundingClientRect(), legacy: true }, win);
        let hint = null;
        try {
            hint = PA.revealHint?.(note.anchor, el) ||
                (el && PA.revealTrigger?.(el) ? { trigger: PA.revealTrigger(el) } : null);
        } catch (_) { /* 条件选择器失效等同无触发器 */ }
        const trigger = hint?.trigger;
        if (!trigger || !trigger.getClientRects?.().length) return null;
        const p = logicalPoint({ element: trigger, point: {}, legacy: true }, win);
        return p && { x: p.x, y: p.y + trigger.getBoundingClientRect().height };
    }
    function rows(list) {
        const sorted = list.slice().sort((a, b) => a.point.y - b.point.y || a.point.x - b.point.x || stable(a.note, b.note));
        const result = [];
        for (let i = 0; i < sorted.length;) {
            const top = sorted[i].point.y, row = [];
            while (i < sorted.length && sorted[i].point.y - top <= 12) row.push(sorted[i++]);
            row.sort((a, b) => a.point.x - b.point.x || a.point.y - b.point.y || stable(a.note, b.note));
            result.push(...row);
        }
        return result;
    }
    /* records: { note, point, group }。group 0 = 主页面流，1 = 分支容器；同组内按行序，组间主页面流在前；无 point 的失锚置底。 */
    function arrange(records) {
        const placed = records.filter(r => r.point);
        const result = [
            ...rows(placed.filter(r => !r.group)),
            ...rows(placed.filter(r => r.group)),
            ...records.filter(r => !r.point).sort((a, b) => stable(a.note, b.note)),
        ];
        return result.map((r, i) => ({ ...r.note, displayNumber: i + 1 }));
    }
    function classify(note, win) {
        const PA = win.ProtoAnchors;
        let found = null;
        try { found = PA.point(note); } catch (_) { /* 未就绪或失效锚点 */ }
        let point = logicalPoint(found, win), el = found?.element || null;
        if (!el && note.anchor) { try { el = PA.resolveHidden?.(note.anchor) || null; } catch (_) { /* 旧选择器失效 */ } }
        if (!point && note.anchor) { try { point = proxyPoint(note, el, win); } catch (_) { /* 代位失败按失锚处理 */ } }
        const group = el && inBranch(el, win) ? 1 : 0;
        return { note, point, group };
    }
    function project(notes, win, pending = null) {
        const records = notes.map(note => classify(note, win));
        if (pending?.point) records.push({ note: { id: '~pending' }, point: pending.point, group: pending.group || 0 });
        return arrange(records);
    }
    function previewNumber(notes, win, x, y) {
        const element = win.ProtoAnchors.at(x, y);
        const point = logicalPoint({ element, point: { x, y } }, win);
        const group = element && inBranch(element, win) ? 1 : 0;
        return project(notes, win, { point, group }).find(n => n.id === '~pending')?.displayNumber || notes.length + 1;
    }
    globalThis.ProtoOrder = { arrange, project, previewNumber, logicalPoint, inBranch };
})();
