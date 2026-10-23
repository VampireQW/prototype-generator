"""首页外观偏好的持久化与系统跟随行为。"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_home_theme_preference_and_live_system_changes():
    node = shutil.which('node')
    if not node:
        pytest.skip('需要 Node.js')
    source = Path(__file__).resolve().parents[1] / 'src/home-theme.js'
    script = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
function boot(saved, dark, blocked = false, legacy = false) {
    const listeners = {}, media = {matches: dark}, values = {'prototype-home-theme': saved};
    let mediaChange, changes = 0;
    media[legacy ? 'addListener' : 'addEventListener'] = (...args) => {mediaChange = args.at(-1);};
    const context = {document: {documentElement: {dataset: {}}}, Event: class {constructor(type){this.type = type;}},
        localStorage: {getItem(key){if(blocked) throw Error('blocked'); return values[key] ?? null;},
            setItem(key, value){if(blocked) throw Error('blocked'); values[key] = value;}},
        matchMedia: () => media, addEventListener(type, fn){listeners[type] = fn;},
        dispatchEvent(event){changes++; listeners[event.type]?.(event);}};
    context.window = context; vm.runInNewContext(SOURCE, context);
    return {api: context.HomeTheme, values, dataset: context.document.documentElement.dataset,
        system(dark){media.matches = dark; mediaChange();},
        storage(key, value){values[key] = value; listeners.storage({key, newValue: value});},
        get changes(){return changes;}};
}
for (const selected of ['light', 'dark']) {
    const page = boot(selected, selected !== 'dark');
    assert.equal(page.api.getMode(), selected); assert.equal(page.dataset.homeTheme, selected);
    page.system(selected === 'dark'); assert.equal(page.dataset.homeTheme, selected);
}
const page = boot('system', true);
assert.equal(page.dataset.homeTheme, 'dark');
page.system(false); assert.equal(page.dataset.homeTheme, 'light');
page.api.setMode('dark'); assert.equal(page.values['prototype-home-theme'], 'dark');
page.system(false); assert.equal(page.dataset.homeTheme, 'dark');
page.api.setMode('system'); assert.equal(page.dataset.homeTheme, 'light');
assert.equal(page.values['prototype-home-theme'], 'system');
page.system(true); assert.equal(page.dataset.homeTheme, 'dark');
page.storage('unrelated', 'light'); assert.equal(page.api.getMode(), 'system');
page.storage('prototype-home-theme', 'light'); assert.equal(page.dataset.homeTheme, 'light');
assert.equal(page.api.getMode(), 'light');
page.storage('prototype-home-theme', 'system'); assert.equal(page.dataset.homeTheme, 'dark');
assert.equal(boot('unknown', true).api.getMode(), 'light');
assert.equal(boot(null, true).dataset.homeTheme, 'light');
const blocked = boot(null, true, true);
blocked.api.setMode('system'); assert.equal(blocked.dataset.homeTheme, 'dark');
blocked.system(false); assert.equal(blocked.dataset.homeTheme, 'light');
const legacy = boot('system', false, false, true);
legacy.system(true); assert.equal(legacy.dataset.homeTheme, 'dark');
assert.ok(page.changes > 1);
'''.replace('SOURCE', json.dumps(source.read_text(encoding='utf-8')))
    result = subprocess.run([node, '-'], input=script, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
