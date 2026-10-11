"""视觉预设与主动覆盖；不启动服务，不读取凭据或项目资料。"""
import copy
import re
from functools import lru_cache
from pathlib import Path


TOKENS = {
    'primary': '#1d4ed8', 'secondary': '#046c4e',
    'light': {'background': '#f7f8f8', 'surface': '#ffffff', 'text': '#1a1d23', 'border': '#808790'},
    'dark': {'background': '#0b0d10', 'surface': '#121519', 'text': '#f2f4f7', 'border': '#7e8795'},
}
PRIORITY = '用户明确需求 > 主动自定义配色 / 主题模式 > 视觉风格预设 > 产物类型规则 > 通用设计规则'


def color(value, fallback):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback


def luminance(value):
    channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in channels]
    return sum(x * w for x, w in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def preset_from_markdown(text, asset_id=''):
    """只提取 Color 章节的语义色角色，不把文中第一个十六进制值当主色。"""
    match = re.search(r'^##\s+(?:\d+\.\s*)?Color[^\n]*\n(.*?)(?=^##\s|\Z)', text, re.M | re.S | re.I)
    section = match.group(1) if match else ''
    rows = []
    group = ''
    for line in section.splitlines():
        if line.startswith('### '):
            group = line.lower()
        found = re.findall(r'#[0-9a-fA-F]{6}\b', line)
        if found and (line.lstrip().startswith(('-', '|'))):
            for index, hex_value in enumerate(found):
                rows.append((hex_value.lower(), line.lower(), group, index))

    def accent_score(row, secondary=False):
        value, line, group, index = row
        role = line.split(':', 1)[0]
        if re.search(r'\b(text|heading|foreground|fg|ink|border|shadow|surface|canvas|background|neutral|success|warning|danger|error)\b', role):
            return -1
        if re.search(r'text|neutral|border|shadow', group) and not re.search(r'\*\*(primary|secondary|accent)\s*:', line):
            return -1
        score = 0
        if secondary:
            if re.search(r'\*\*secondary(?:\s*(?:&|/).*?)?\s*:', line): score = 120
            elif 'accent' in group or 'secondary' in group: score = 70
            elif 'accent' in line: score = 40
        else:
            if re.search(r'primary (?:action|brand|fill|cta)|cta background|cta emphasis', line): score = 130
            elif re.search(r'\*\*primary\s*:', line): score = 120
            elif re.search(r'\*\*accent\s*:', line): score = 110
            elif 'primary' in group and luminance(value) > .04 and luminance(value) < .8: score = 85
            elif 'brand' in line or 'action' in line: score = 80
            elif 'accent' in line or 'interactive' in group: score = 60
        return score - index

    primary_row = max(rows, key=lambda r: accent_score(r), default=None)
    primary = primary_row[0] if primary_row and accent_score(primary_row) > 0 else TOKENS['primary']
    secondary_rows = [r for r in rows if r[0] != primary]
    secondary_row = max(secondary_rows, key=lambda r: accent_score(r, True), default=None)
    secondary = secondary_row[0] if secondary_row and accent_score(secondary_row, True) > 0 else primary
    first_background = next((r[0] for r in rows if re.search(r'\*\*background\s*:', r[1])), None)
    intro = text.split('## 2.', 1)[0][:3500].lower()
    default_mode = 'dark' if (first_background and luminance(first_background) < .15) or re.search(r'dark[- ]mode[- ](?:first|native)|dark[- ]first|dark (?:canvas|background|interface)|near-black canvas', intro) else 'light'
    themes = copy.deepcopy({k: TOKENS[k] for k in ('light', 'dark')})
    for mode, theme in themes.items():
        eligible = [r for r in rows if (luminance(r[0]) >= .65 if mode == 'light' else luminance(r[0]) < .08)]
        backgrounds = [r for r in eligible if re.search(r'background|canvas', r[1]) and not re.search(r'text|button|link|accent|brand|purple|green', r[1])]
        surfaces = [r for r in eligible if re.search(r'surface|panel|card', r[1]) and not re.search(r'text|border', r[1].split(':', 1)[0])]
        if backgrounds: theme['background'] = backgrounds[0][0]
        if surfaces: theme['surface'] = surfaces[0][0]
        # 色样展示可读的最终文字与控件边界；保留品牌填色，文字另按对比度使用。
        text_rows = [r for r in rows if re.search(r'foreground|text|heading|ink|\bfg\b', r[1].split(':', 1)[0]) and contrast(r[0], theme['background']) >= 4.5 and contrast(r[0], theme['surface']) >= 4.5]
        if text_rows: theme['text'] = text_rows[0][0]
        border_rows = [r for r in rows if 'border' in r[1].split(':', 1)[0] and contrast(r[0], theme['background']) >= 3 and contrast(r[0], theme['surface']) >= 3]
        if border_rows: theme['border'] = border_rows[0][0]
        if min(contrast(theme['border'], theme[k]) for k in ('background', 'surface')) < 3:
            theme['border'] = theme['text']
    component = {'ant': 'Ant Design', 'material': 'Material Design', 'default': '中性现代组件'}.get(asset_id, f'{asset_id or "默认风格"} 组件语言')
    return {'primaryColor': primary, 'secondaryColor': secondary, 'defaultTheme': default_mode, 'themes': themes, 'componentStyle': component}


@lru_cache(maxsize=160)
def _read_preset(path, stamp):
    return preset_from_markdown(Path(path).read_text(encoding='utf-8'), Path(path).parent.name)


def load_preset(asset_id='', directory='design-systems'):
    safe_id = asset_id if isinstance(asset_id, str) and re.fullmatch(r'[a-zA-Z0-9_-]+', asset_id) else 'default'
    if safe_id == 'none': safe_id = 'default'
    path = Path(directory) / safe_id / 'DESIGN.md'
    if path.is_file():
        return copy.deepcopy(_read_preset(str(path.resolve()), path.stat().st_mtime_ns))
    return {'primaryColor': TOKENS['primary'], 'secondaryColor': TOKENS['secondary'], 'defaultTheme': 'light', 'themes': copy.deepcopy({k: TOKENS[k] for k in ('light', 'dark')}), 'componentStyle': '中性现代组件'}


def resolve_settings(raw=None, preset=None):
    raw = raw if isinstance(raw, dict) else {}
    preset = preset or load_preset(raw.get('designSystemId', ''))
    modern = raw.get('designSettingsVersion') == 2
    # 旧表单默认色不是主动覆盖；非默认历史颜色保留。旧组件选择不再独立生效。
    legacy_custom = any(raw.get(k) and str(raw[k]).lower() != old for k, old in [('primaryColor', '#004fff'), ('secondaryColor', '#10b981')])
    color_mode = ('custom' if raw.get('colorMode') == 'custom' else 'preset') if modern else ('custom' if legacy_custom else 'preset')
    theme_mode = raw.get('themeMode') if modern else ('dark' if raw.get('backgroundMode') == 'dark' else 'inherit')
    if theme_mode not in ('light', 'dark'): theme_mode = 'inherit'
    mode = preset['defaultTheme'] if theme_mode == 'inherit' else theme_mode
    theme = preset['themes'][mode]
    keys = ('primaryColor', 'secondaryColor')
    if color_mode != 'custom': fields = []
    elif modern: fields = [k for k in keys if k in raw.get('customColorFields', keys)]
    else: fields = [k for k, old in [('primaryColor', '#004fff'), ('secondaryColor', '#10b981')] if raw.get(k) and str(raw[k]).lower() != old]
    primary = color(raw.get('primaryColor'), preset['primaryColor']) if 'primaryColor' in fields else preset['primaryColor']
    secondary = color(raw.get('secondaryColor'), preset['secondaryColor']) if 'secondaryColor' in fields else preset['secondaryColor']
    overrides = {}
    if theme_mode != 'inherit': overrides['themeMode'] = theme_mode
    for key, value in [('primaryColor', primary), ('secondaryColor', secondary)]:
        if key in fields: overrides[key] = value
    return {**raw, 'designSettingsVersion': 2, 'colorMode': color_mode, 'themeMode': theme_mode,
            'customColorFields': fields,
            'primaryColor': primary, 'secondaryColor': secondary, 'backgroundMode': mode,
            'componentStyle': preset['componentStyle'], 'designOverrides': overrides,
            'effectivePalette': [primary, secondary, theme['background'], theme['surface'], theme['text'], theme['border']]}


def prompt_rules(settings):
    if settings.get('designSettingsVersion') != 2:
        settings = resolve_settings(settings)
    lines = [f'- 约束优先级：{PRIORITY}', '- 配色、字体与组件语言默认继承视觉风格，不额外指定另一套组件库。']
    fields = settings.get('customColorFields', ('primaryColor', 'secondaryColor') if settings['colorMode'] == 'custom' else ())
    if 'primaryColor' in fields: lines.append(f'- 用户主动自定义主色：{settings["primaryColor"]}')
    if 'secondaryColor' in fields: lines.append(f'- 用户主动自定义辅色：{settings["secondaryColor"]}')
    if fields: lines.append('- 自定义配色覆盖风格原始规范中的同名颜色；保留该风格的字体、排版与组件语言。')
    if settings['themeMode'] != 'inherit':
        lines.append(f'- 用户主动指定主题模式：{"深色" if settings["themeMode"] == "dark" else "浅色"}；覆盖风格默认主题。')
    lines += ['- 中文优先字体栈："PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif。', '- 颜色使用语义 token；正文对比度 ≥ 4.5:1、控件边界 ≥ 3:1。品牌填色保留，必要时单独修正文字态色值。']
    return '\n'.join(lines)
