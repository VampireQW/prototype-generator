/* 工作台和独立评审壳共用页面列表宽度交互。 */
(() => {
    'use strict';
    function attach(handle, options) {
        const min = 200, defaultWidth = 256;
        let preferred = defaultWidth, width, drag = null;
        const max = () => Math.max(min, Math.min(480, options.getMax()));
        try {
            const saved = Number(localStorage.getItem(options.storageKey));
            if (Number.isFinite(saved) && saved >= min) preferred = Math.min(480, saved);
        } catch (_) { /* 存储不可用时仍可调整 */ }
        function render(value) {
            width = Math.round(Math.max(min, Math.min(max(), value)));
            options.setWidth(width);
            handle.setAttribute('aria-valuemin', min);
            handle.setAttribute('aria-valuemax', Math.floor(max()));
            handle.setAttribute('aria-valuenow', width);
            handle.setAttribute('aria-valuetext', `${width} 像素`);
        }
        function save() {
            preferred = width;
            try { localStorage.setItem(options.storageKey, String(width)); } catch (_) { /* 本次页面保留宽度 */ }
        }
        function finish(commit) {
            if (!drag) return;
            const previous = drag; drag = null;
            previous.overlay.remove();
            handle.classList.remove('resizing'); document.body.classList.remove('page-nav-resizing');
            if (handle.hasPointerCapture(previous.pointerId)) handle.releasePointerCapture(previous.pointerId);
            if (commit) save(); else render(preferred);
        }
        function refresh() {
            if (drag) finish(false);
            handle.hidden = !options.isOpen();
            render(preferred);
        }
        handle.addEventListener('pointerdown', event => {
            if (drag || event.button !== 0 || event.isPrimary === false || !options.isOpen()) return;
            event.preventDefault();
            const overlay = document.createElement('div'); overlay.className = 'page-nav-resize-overlay';
            overlay.setAttribute('aria-hidden', 'true'); document.body.append(overlay);
            drag = {pointerId: event.pointerId, x: event.clientX, width, overlay};
            handle.classList.add('resizing'); document.body.classList.add('page-nav-resizing');
            handle.focus({preventScroll: true});
            handle.setPointerCapture(event.pointerId);
        });
        handle.addEventListener('pointermove', event => {
            if (drag && drag.pointerId === event.pointerId) render(drag.width + event.clientX - drag.x);
        });
        handle.addEventListener('pointerup', event => { if (drag?.pointerId === event.pointerId) finish(true); });
        handle.addEventListener('pointercancel', () => finish(false));
        handle.addEventListener('lostpointercapture', () => finish(false));
        handle.addEventListener('dblclick', () => { if (options.isOpen()) { render(defaultWidth); save(); } });
        handle.addEventListener('keydown', event => {
            if (drag || !options.isOpen()) return;
            const step = event.shiftKey ? 40 : 10;
            const next = {ArrowLeft: width - step, ArrowRight: width + step, Home: min, End: max()}[event.key];
            if (next == null) return;
            event.preventDefault(); render(next); save();
        });
        window.addEventListener('keydown', event => {
            if (drag && event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); finish(false); }
        }, true);
        window.addEventListener('blur', () => finish(false));
        window.addEventListener('resize', refresh);
        refresh();
        return {refresh};
    }
    window.ProtoSidebarResize = {attach};
})();
