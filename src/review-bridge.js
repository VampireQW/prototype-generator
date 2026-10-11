/* 评审壳 ↔ 原型页桥：随导出内嵌进每个原型 HTML，跑在 iframe 内。
   壳与原型改用 postMessage 通信，不再由壳跨文档注入脚本——ZIP 解压后 file:// 直接打开时
   每个 file 都是独立源，壳拿不到 iframe 的 document，旧注入方式静默失效（无序号、无引导、右栏乱序）。
   加载顺序：proto-hotspots.js（先于业务脚本）→ proto-appearance.js → proto-anchors.js → proto-order.js → 本文件 → review-pins.js。
   独立打开原型（不在壳内）时本文件不做任何事。 */
(() => {
    'use strict';
    if (window.__reviewBridgeBoot) return;
    window.__reviewBridgeBoot = true;
    if (window.parent === window || !window.ProtoAnchors) return;

    const post = (msg) => { try { window.parent.postMessage(Object.assign({ __review: 1 }, msg), '*'); } catch (_) { /* 壳未就绪 */ } };
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let asideOpen = true;

    // review-pins.js 启动时读取的宿主对象：标注在 init 消息到达后填充，正文 HTML 由壳预渲染（气泡层无 Markdown 渲染器）。
    window.__REVIEW__ = {
        notes: [],
        asideOpen: () => asideOpen,
        onSync: (map, state, stale) => post({ type: 'sync', map, state, stale }),
        onFocus: (noteId) => post({ type: 'focus', noteId }),
        renderBody: (note) => note.bodyHtml || '<p>' + esc(note.body || '') + '</p>',
    };
    window.ProtoHotspots?.init();

    // 气泡层在本文件之后加载；init 早到时等它就位再重排（最多等 5s）。
    function relayout(tries) {
        if (window.__reviewRelayout) { window.__reviewRelayout(); return; }
        if ((tries || 0) < 50) setTimeout(() => relayout((tries || 0) + 1), 100);
    }

    function reveal(note) {
        const A = window.ProtoAnchors;
        let found = null;
        try { found = A.point(note); } catch (_) { /* 锚定异常 */ }
        if (!found?.element && !found?.point) {
            // 目标被折叠/隐藏：先联动展开对应折叠区，再重新定位与重排气泡
            try { A.reveal?.(note.anchor); } catch (_) { /* ignore */ }
            try { window.__reviewRelayout?.(); } catch (_) { /* ignore */ }
            try { found = A.point(note); } catch (_) { /* ignore */ }
        }
        if (found?.element) found.element.scrollIntoView({ block: 'center', behavior: 'smooth' });
        else if (found?.point) window.scrollTo({ top: Math.max(0, found.point.y + window.scrollY - window.innerHeight / 2), behavior: 'smooth' });
    }

    window.addEventListener('message', (e) => {
        if (e.source !== window.parent || !e.data || e.data.__review !== 1) return;
        const m = e.data;
        switch (m.type) {
            case 'init':
                window.__REVIEW__.notes = Array.isArray(m.notes) ? m.notes : [];
                asideOpen = m.asideOpen !== false;
                if (m.enterState) { try { window.ProtoAnchors.enterState?.(m.enterState)?.catch?.(() => {}); } catch (_) { /* ignore */ } }
                relayout();
                break;
            case 'aside':
                asideOpen = !!m.open;
                try { window.__reviewHidePop?.(); } catch (_) { /* ignore */ }
                break;
            case 'enterState':
                try { window.ProtoAnchors.enterState?.(m.stateId)?.catch?.(() => {}); } catch (_) { /* ignore */ }
                break;
            case 'reveal':
                if (m.note) reveal(m.note);
                break;
            case 'hidePop':
                try { window.__reviewHidePop?.(); } catch (_) { /* ignore */ }
                break;
            case 'showHotspots':
                window.ProtoHotspots?.show();
                break;
            default:
                break;
        }
    });

    let ids = {};
    try { ids = window.ProtoAnchors.currentIds?.() || {}; } catch (_) { /* ignore */ }
    post({ type: 'ready', ids });
})();
