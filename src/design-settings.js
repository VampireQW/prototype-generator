(function (root) {
    'use strict';
    const tokens = {
        primary: '#1d4ed8', secondary: '#046c4e',
        light: { background: '#f7f8f8', surface: '#ffffff', text: '#1a1d23', border: '#808790' },
        dark: { background: '#0b0d10', surface: '#121519', text: '#f2f4f7', border: '#7e8795' }
    };
    const priority = '用户明确需求 > 主动自定义配色 / 主题模式 > 视觉风格预设 > 产物类型规则 > 通用设计规则';
    const color = (value, fallback) => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : fallback;
    const fallback = { primaryColor: tokens.primary, secondaryColor: tokens.secondary, defaultTheme: 'light', themes: { light: tokens.light, dark: tokens.dark }, componentStyle: '中性现代组件' };
    function resolve(raw = {}, preset = fallback) {
        preset = { ...fallback, ...preset, themes: { ...fallback.themes, ...preset.themes } };
        const modern = raw.designSettingsVersion === 2;
        const legacyCustom = [['primaryColor', '#004fff'], ['secondaryColor', '#10b981']].some(([key, old]) => raw[key] && String(raw[key]).toLowerCase() !== old);
        const colorMode = modern ? (raw.colorMode === 'custom' ? 'custom' : 'preset') : (legacyCustom ? 'custom' : 'preset');
        let themeMode = modern ? raw.themeMode : (raw.backgroundMode === 'dark' ? 'dark' : 'inherit');
        if (!['light', 'dark'].includes(themeMode)) themeMode = 'inherit';
        const mode = themeMode === 'inherit' ? preset.defaultTheme : themeMode;
        const theme = preset.themes[mode];
        const keys = ['primaryColor', 'secondaryColor'];
        const customColorFields = colorMode !== 'custom' ? [] : modern ? keys.filter(key => (raw.customColorFields || keys).includes(key)) : [['primaryColor', '#004fff'], ['secondaryColor', '#10b981']].filter(([key, old]) => raw[key] && String(raw[key]).toLowerCase() !== old).map(([key]) => key);
        const primaryColor = customColorFields.includes('primaryColor') ? color(raw.primaryColor, preset.primaryColor) : preset.primaryColor;
        const secondaryColor = customColorFields.includes('secondaryColor') ? color(raw.secondaryColor, preset.secondaryColor) : preset.secondaryColor;
        const designOverrides = {};
        if (themeMode !== 'inherit') designOverrides.themeMode = themeMode;
        if (customColorFields.includes('primaryColor')) designOverrides.primaryColor = primaryColor;
        if (customColorFields.includes('secondaryColor')) designOverrides.secondaryColor = secondaryColor;
        return { ...raw, designSettingsVersion: 2, colorMode, themeMode, customColorFields, primaryColor, secondaryColor,
            backgroundMode: mode, componentStyle: preset.componentStyle, designOverrides,
            effectivePalette: [primaryColor, secondaryColor, theme.background, theme.surface, theme.text, theme.border] };
    }
    function promptRules(settings) {
        const lines = [`- 约束优先级：${priority}`, '- 配色、字体与组件语言默认继承视觉风格，不额外指定另一套组件库。'];
        const fields = settings.customColorFields || (settings.colorMode === 'custom' ? ['primaryColor', 'secondaryColor'] : []);
        if (fields.includes('primaryColor')) lines.push(`- 用户主动自定义主色：${settings.primaryColor}`);
        if (fields.includes('secondaryColor')) lines.push(`- 用户主动自定义辅色：${settings.secondaryColor}`);
        if (fields.length) lines.push('- 自定义配色覆盖风格原始规范中的同名颜色；保留该风格的字体、排版与组件语言。');
        if (settings.themeMode !== 'inherit') lines.push(`- 用户主动指定主题模式：${settings.themeMode === 'dark' ? '深色' : '浅色'}；覆盖风格默认主题。`);
        lines.push('- 中文优先字体栈："PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif。', '- 颜色使用语义 token；正文对比度 ≥ 4.5:1、控件边界 ≥ 3:1。品牌填色保留，必要时单独修正文字态色值。');
        return lines.join('\n');
    }
    root.DesignSettings = { resolve, promptRules, fallback, priority };
})(globalThis);
