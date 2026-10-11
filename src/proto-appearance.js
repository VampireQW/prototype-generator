/* PRD 内容色板与序号外观；编辑、导出和发布共用。 */
(() => {
    'use strict';
    const TEXT_COLORS = [
        ['#191919', '黑色'], ['#1684fc', '蓝色'], ['#8a38f5', '紫色'], ['#666666', '灰色'],
        ['#fbfbfb', '白色'], ['#ec4954', '红色'], ['#ff9f29', '橙色']
    ];
    const DEFAULT_PIN = '#2563eb', INK = '#191919', STROKE = '#4e5560', ON_BLUE = '#ffffff';
    const PIN_COLORS = [
        [DEFAULT_PIN, '默认蓝色'],
        ['#acbcd1', '灰蓝'], ['#ff9e93', '珊瑚'], ['#ff9e47', '橙色'], ['#fdd143', '黄色'], ['#9dc4ff', '浅蓝'],
        ['#38cde7', '青色'], ['#54d691', '绿色'], ['#daa3ff', '紫色'], ['#ff94e4', '粉色']
    ];
    const LEGACY_PIN_COLORS = ['#e6e6e6'];
    function pinColor(note) {
        const color = String(note?.color || '').toLowerCase();
        return PIN_COLORS.some(([hex]) => hex === color) || LEGACY_PIN_COLORS.includes(color) ? color : DEFAULT_PIN;
    }
    function applyPin(element, note) {
        const color = pinColor(note), custom = color !== DEFAULT_PIN;
        element.style.setProperty('--pin-fill', color);
        element.style.setProperty('--pin-ink', custom ? INK : ON_BLUE);
        element.style.setProperty('--pin-stroke', custom ? STROKE : ON_BLUE);
    }
    window.ProtoAppearance = { TEXT_COLORS, PIN_COLORS, DEFAULT_PIN, pinColor, applyPin };
})();
