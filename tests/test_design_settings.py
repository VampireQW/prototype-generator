"""预设继承、主动覆盖、旧记录与三个生成入口的隔离回归。"""
import ast
import copy
import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from test_ai_workbench import api
import design_settings as ds

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'design-systems'


def test_semantic_presets_and_theme():
    assert ds.load_preset('apple', ASSETS)['primaryColor'] == '#0071e3'
    assert ds.load_preset('stripe', ASSETS)['primaryColor'] == '#533afd'
    assert ds.load_preset('github', ASSETS)['primaryColor'] == '#0969da'
    assert ds.load_preset('linear-app', ASSETS)['defaultTheme'] == 'dark'
    assert ds.load_preset('default', ASSETS)['primaryColor'] == '#2f6feb'
    for path in ASSETS.glob('*/DESIGN.md'):
        preset = ds.load_preset(path.parent.name, ASSETS)
        for theme in preset['themes'].values():
            for key in ('background', 'surface'):
                assert ds.contrast(theme['text'], theme[key]) >= 4.5, path.parent.name
                assert ds.contrast(theme['border'], theme[key]) >= 3, path.parent.name


@pytest.mark.parametrize('raw', [
    {}, {'designSettingsVersion': 2, 'colorMode': 'preset', 'primaryColor': '#ff0000'},
    {'designSettingsVersion': 2, 'colorMode': 'custom', 'primaryColor': '#C2410C', 'secondaryColor': '#047857', 'themeMode': 'light'},
    {'designSettingsVersion': 2, 'colorMode': 'custom', 'primaryColor': 'url(evil)', 'secondaryColor': '#bad'},
    {'primaryColor': '#004fff', 'secondaryColor': '#10B981', 'backgroundMode': 'light', 'componentStyle': 'Material Design'},
    {'primaryColor': '#C2410C', 'secondaryColor': '#047857', 'backgroundMode': 'dark'},
    {'designSettingsVersion': 2, 'colorMode': 'preset', 'themeMode': 'dark'},
    {'designSettingsVersion': 2, 'colorMode': 'custom', 'customColorFields': [], 'primaryColor': '#c2410c'},
    {'designSettingsVersion': 2, 'colorMode': 'custom', 'customColorFields': ['primaryColor'], 'primaryColor': '#c2410c', 'secondaryColor': '#ff0000'},
])
def test_frontend_backend_same_resolution(raw):
    preset = ds.load_preset('linear-app', ASSETS)
    expected = ds.resolve_settings(raw, preset)
    payload = {'raw': raw, 'preset': preset}
    node = 'D:/software/nodejs/node.EXE'
    js = "require('./src/design-settings.js');const fs=require('fs');const p=JSON.parse(fs.readFileSync(0,'utf8'));const resolved=DesignSettings.resolve(p.raw,p.preset);process.stdout.write(JSON.stringify({resolved,rules:DesignSettings.promptRules(resolved)}));"
    result = subprocess.run([node, '-e', js], input=json.dumps(payload), text=True, capture_output=True, cwd=ROOT, check=True)
    actual = json.loads(result.stdout)
    assert actual['resolved'] == expected
    assert actual['rules'] == ds.prompt_rules(expected)
    assert expected['componentStyle'] == preset['componentStyle']


def test_only_explicit_overrides_are_instructions():
    preset = ds.load_preset('apple', ASSETS)
    inherited = ds.resolve_settings({'designSettingsVersion': 2, 'colorMode': 'preset', 'themeMode': 'inherit'}, preset)
    assert inherited['designOverrides'] == {}
    rules = ds.prompt_rules(inherited)
    assert inherited['primaryColor'] not in rules and inherited['secondaryColor'] not in rules
    custom = ds.resolve_settings({**inherited, 'colorMode': 'custom', 'customColorFields': ['primaryColor', 'secondaryColor'], 'themeMode': 'dark', 'primaryColor': '#c2410c', 'secondaryColor': '#047857'}, preset)
    assert custom['designOverrides'] == {'themeMode': 'dark', 'primaryColor': '#c2410c', 'secondaryColor': '#047857'}
    assert '#c2410c' in ds.prompt_rules(custom) and '覆盖风格默认主题' in ds.prompt_rules(custom)
    restored = ds.resolve_settings({**custom, 'colorMode': 'preset', 'themeMode': 'inherit'}, preset)
    assert restored == inherited
    partial = ds.resolve_settings({**custom, 'customColorFields': ['primaryColor']}, preset)
    assert partial['secondaryColor'] == preset['secondaryColor']
    assert '用户主动自定义辅色' not in ds.prompt_rules(partial)


def configure_generation(api):
    ns = api.namespace
    tree = ast.parse((ROOT / 'server.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compose_generation_prompt')
    ns.update(DEFAULT_SKILL_ID='web-prototype', DESIGN_SYSTEMS_DIR=str(ASSETS),
              safe_asset_id=lambda value: value or '', is_default_design_system=lambda value: value in ('', 'default', 'none'), MAX_DESIGN_SYSTEM_CHARS=20000, MAX_CRAFT_CONTEXT_CHARS=1000,
              MINIMAL_CRAFT_RULES='通用设计规则', get_minimal_skill_rules=lambda sid: '产物规则',
              get_design_system_context=lambda sid, *args: (ASSETS / (sid or 'default') / 'DESIGN.md').read_text(encoding='utf-8'),
              get_skill_context=lambda *args, **kwargs: '', get_craft_context=lambda *args: '',
              get_selected_model=lambda: None, generate_project_id=lambda name: name,
              assign_saved_images_to_pages=lambda pages, *args: (pages, ''), download_html_images=lambda html, *args: html,
              STATUS_GENERATING='generating', STATUS_COMPLETED='completed', STATUS_FAILED='failed',
              generating_tasks={}, tasks_lock=threading.Lock())
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<isolated-compose>', 'exec'), ns)
    ns['CustomHandler'].load_projects = lambda self: json.loads(api.listing.read_text(encoding='utf-8'))
    calls = []
    ns['CustomHandler']._call_ai_for_async = lambda self, prompt, images: (calls.append(prompt) or '<html lang="zh-CN"><title>隔离原型</title><body>内容</body></html>')
    return calls


@pytest.mark.parametrize('custom', [False, True])
def test_three_paths_store_same_settings_and_priority(api, custom):
    calls = configure_generation(api)
    raw = {'designSettingsVersion': 2, 'designSystemId': 'apple', 'designSystemName': 'Apple', 'skillId': 'mobile-app',
           'colorMode': 'custom' if custom else 'preset', 'themeMode': 'dark' if custom else 'inherit',
           'primaryColor': '#c2410c', 'secondaryColor': '#047857', 'componentStyle': 'Material Design'}
    expected = ds.resolve_settings(raw, ds.load_preset('apple', ASSETS))
    requests = ['/generate-async', '/create-placeholder', '/create-ai-ide-package']
    for i, path in enumerate(requests):
        pid = f'style-path-{i}'
        body = {'projectId': pid, 'projectName': pid, 'prompt': '用户明确要求：橙色按钮；页面首页。',
                'formData': {'global': copy.deepcopy(raw), 'pages': [{'name': '首页', 'features': '课程管理'}]}}
        code, result, _ = api.request(path, body)
        assert code == 200 and result['success'], result
        root = api.projects / pid
        if path == '/generate-async':
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and api.namespace['generating_tasks'][pid]['status'] == 'generating':
                time.sleep(.02)
            assert api.namespace['generating_tasks'][pid]['status'] == 'completed', api.namespace['generating_tasks'][pid]
            assert calls and ds.PRIORITY in calls[0]
        record = json.loads((root / 'record.json').read_text(encoding='utf-8'))
        assert record['global'] == expected
        text = (root / ('DESIGN.md' if path.endswith('package') else 'prompt.txt')).read_text(encoding='utf-8')
        assert ds.PRIORITY in text
        assert '只作为微调偏好' not in text and '组件风格：Material' not in text
        assert ('用户主动自定义主色：#c2410c' in text) == custom
        if path == '/create-placeholder': assert result['instruction'] == text
