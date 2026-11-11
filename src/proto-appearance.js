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
    function pinStyle(value) {
        const style = value && typeof value === 'object' ? value : {};
        return { size: Number.isInteger(style.size) && style.size >= 24 && style.size <= 56 ? style.size : 36,
            ...(/^#[0-9a-f]{6}$/i.test(style.color || '') ? { color: style.color.toLowerCase() } : {}) };
    }
    function applyPin(element, note, value) {
        const global = pinStyle(value), color = global.color || pinColor(note), custom = color !== DEFAULT_PIN;
        let ink = custom ? INK : ON_BLUE, stroke = custom ? STROKE : ON_BLUE;
        if (global.color) {
            const rgb = [1,3,5].map(i => parseInt(color.slice(i,i+2),16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4);
            const lum = rgb[0]*.2126 + rgb[1]*.7152 + rgb[2]*.0722;
            ink = lum > .179 ? '#000000' : '#ffffff'; stroke = ink;
        }
        element.style.setProperty('--pin-fill', color);
        element.style.setProperty('--pin-ink', ink);
        element.style.setProperty('--pin-stroke', stroke);
    }
    function applyPinSize(element, value) {
        const {size} = pinStyle(value);
        element.style.setProperty('--pin-size', size + 'px');
        element.style.setProperty('--pin-font', Math.round(size*13/36) + 'px');
        element.style.setProperty('--pin-padding', Math.round(size*8/36) + 'px');
    }
    window.ProtoAppearance = { TEXT_COLORS, PIN_COLORS, DEFAULT_PIN, pinColor, pinStyle, applyPin, applyPinSize };
})();
