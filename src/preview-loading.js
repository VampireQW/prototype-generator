/* 预览准备期间保留 iframe 布局；只在当前页面及视图准备完成后揭开占位。 */
(() => {
    'use strict';
    function create(container, overlay, frame, retry) {
        const title = overlay.querySelector('[data-loading-title]');
        const detail = overlay.querySelector('[data-loading-detail]');
        const button = overlay.querySelector('button');
        let generation = 0, timer = null, paint = null;
        function clear() {
            clearTimeout(timer); timer = null;
            if (paint !== null) cancelAnimationFrame(paint);
            paint = null;
        }
        function state(value) {
            container.dataset.previewState = value;
            container.setAttribute('aria-busy', String(value === 'loading'));
            frame.inert = value !== 'ready';
            overlay.inert = value === 'ready';
            overlay.setAttribute('aria-hidden', String(value === 'ready'));
        }
        function begin(page = '') {
            clear();
            const token = ++generation;
            state('loading');
            title.textContent = '正在加载原型';
            detail.textContent = page ? `正在打开「${page}」` : '正在准备页面与预览视图';
            button.hidden = true;
            timer = setTimeout(() => {
                if (generation !== token || container.dataset.previewState !== 'loading') return;
                detail.textContent = '加载时间较长，可以稍候或重新加载';
                button.hidden = false;
            }, 12000);
            return token;
        }
        function ready(token) {
            if (token !== generation || container.dataset.previewState !== 'loading') return;
            clear();
            // 视图尺寸及初始状态完成后，再留一帧提交布局；不人为延长快速加载。
            paint = requestAnimationFrame(() => {
                paint = requestAnimationFrame(() => {
                    paint = null;
                    if (token === generation && container.dataset.previewState === 'loading') state('ready');
                });
            });
        }
        function fail(token, message) {
            if (token !== generation) return;
            clear(); state('error');
            title.textContent = '暂时无法加载原型';
            detail.textContent = message || '请检查项目后重新加载';
            button.hidden = false;
        }
        function dismiss() { clear(); ++generation; state('ready'); }
        button.addEventListener('click', () => retry());
        return { begin, ready, fail, dismiss, isLoading: () => container.dataset.previewState === 'loading' };
    }
    window.ProtoPreviewLoading = { create };
})();
