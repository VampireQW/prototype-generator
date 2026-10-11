/* 旧单页原型的状态适配；工作台和静态评审壳共用。 */
(() => {
    'use strict';
    if (window.ProtoNavigation) return;
    let active = null;

    function init(config = {}) {
        active?.destroy();
        const states = Array.isArray(config.states) ? config.states : [];
        if (config.aiNavigation !== 'legacy' || !states.some(s => s.legacyPage || s.legacyType)) return null;
        const root = document.documentElement;
        const originalBridge = window.PrototypeBridge;
        if (typeof originalBridge?.enter === 'function') return originalBridge;
        let destroyed = false, timer = null, unwatch = null;
        const hasDefault = states.some(s => s.id === 'default' && !s.legacyPage);
        let defaultSelected = false;
        let defaultTarget = null;

        function vueInstance() {
            const app = document.getElementById('app');
            return app?._vnode?.component || app?.__vue_app__?._instance || app?.firstElementChild?.__vueParentComponent || null;
        }
        function router() {
            const app = document.getElementById('app')?.__vue_app__;
            return window.__vueRouter__ || app?.config?.globalProperties?.$router || vueInstance()?.proxy?.$router || null;
        }
        function pageSource() {
            if (window.currentPage !== undefined) return { owner: window, key: 'currentPage' };
            const instance = vueInstance();
            for (const owner of [instance?.setupState, instance?.proxy, instance?.data, instance?.ctx]) {
                if (owner && owner.currentPage !== undefined) return { owner, key: 'currentPage' };
            }
            return null;
        }
        function valueOf(source) {
            const value = source?.owner[source.key];
            return value && typeof value === 'object' && 'value' in value ? value.value : value;
        }
        function currentState() {
            const route = router()?.currentRoute;
            const routePath = route?.value?.path || route?.path || window.location.hash.replace(/^#/, '') || '/';
            const routed = states.find(s => s.legacyType === 'router' && s.routePath === routePath);
            if (routed) return routed;
            const page = valueOf(pageSource());
            return states.find(s => s.legacyPage === page) || null;
        }
        function sync() {
            if (destroyed) return;
            const state = currentState();
            if (!state) return;
            if (state.id !== defaultTarget?.id) defaultSelected = false;
            if (config.pageId) root.dataset.protoPage = config.pageId;
            const id = defaultSelected ? 'default' : state.id;
            if (root.dataset.protoState !== id) root.dataset.protoState = id;
        }
        async function enter(stateId) {
            const state = stateId === 'default' && hasDefault ? defaultTarget : states.find(s => s.id === stateId);
            if (!state || !(state.legacyPage || state.legacyType)) return originalBridge?.enter?.(stateId);
            if (state.legacyType === 'router' && state.routePath) {
                const r = router();
                if (r?.push) await r.push(state.routePath);
                else window.location.hash = '#' + state.routePath;
            } else {
                const source = pageSource();
                if (!source) return originalBridge?.enter?.(stateId);
                const value = source.owner[source.key];
                if (value && typeof value === 'object' && 'value' in value) value.value = state.legacyPage;
                else source.owner[source.key] = state.legacyPage;
            }
            await Promise.resolve();
            defaultSelected = stateId === 'default' && hasDefault;
            sync();
            return root.dataset.protoState === stateId;
        }
        defaultTarget = currentState() || states.find(s => s.legacyPage || s.legacyType) || null;
        const bridge = { ...originalBridge, enter };
        window.PrototypeBridge = bridge;
        const onRouteChange = () => sync();
        window.addEventListener('hashchange', onRouteChange);
        const r = router();
        if (r?.afterEach) unwatch = r.afterEach(onRouteChange);
        timer = window.setInterval(sync, 100);
        sync();
        active = { enter, sync, destroy() {
            destroyed = true;
            window.clearInterval(timer);
            window.removeEventListener('hashchange', onRouteChange);
            if (typeof unwatch === 'function') unwatch();
            if (window.PrototypeBridge === bridge) {
                if (originalBridge) window.PrototypeBridge = originalBridge;
                else delete window.PrototypeBridge;
            }
        } };
        return active;
    }
    window.ProtoNavigation = { init };
    if (window.__PROTO_NAVIGATION__) init(window.__PROTO_NAVIGATION__);
})();
