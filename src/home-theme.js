/* 在样式加载前解析首页外观；发布管理页共用同一偏好。 */
(() => {
    'use strict';
    const key = 'prototype-home-theme';
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const normalize = value => ['system', 'light', 'dark'].includes(value) ? value : 'light';
    let mode = 'light';
    try { mode = normalize(localStorage.getItem(key)); } catch (_) { /* 存储不可用时使用本次偏好 */ }
    function apply() {
        document.documentElement.dataset.homeTheme = mode === 'system' ? (media.matches ? 'dark' : 'light') : mode;
        window.dispatchEvent(new Event('home-theme-change'));
    }
    function setMode(value) {
        mode = normalize(value);
        try { localStorage.setItem(key, mode); } catch (_) { /* 存储不可用时仍可切换 */ }
        apply();
    }
    const followSystem = () => { if (mode === 'system') apply(); };
    if (media.addEventListener) media.addEventListener('change', followSystem);
    else media.addListener(followSystem);
    window.addEventListener('storage', event => {
        if (event.key !== key && event.key !== null) return;
        mode = normalize(event.newValue); apply();
    });
    window.HomeTheme = { getMode: () => mode, setMode };
    apply();
})();
