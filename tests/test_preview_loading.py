"""首屏与切页的加载状态：真实完成、并发竞态、失败和空项目清理。"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def case(body):
    node = shutil.which('node')
    if not node:
        pytest.skip('需要 Node.js')
    source = (ROOT/'src/preview-loading.js').read_text(encoding='utf-8')
    script = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const element=()=>({dataset:{},attrs:{},hidden:false,inert:false,textContent:'',setAttribute(k,v){this.attrs[k]=v;}});
const container=element(),overlay=element(),frame=element(),title=element(),detail=element(),button=element();
let retry=0,sequence=0;const timers=new Map(),paints=new Map();
button.addEventListener=(_,fn)=>button.click=fn;
overlay.querySelector=key=>key==='[data-loading-title]'?title:key==='[data-loading-detail]'?detail:button;
const context={window:{},setTimeout:(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
 requestAnimationFrame:fn=>{const id=++sequence;paints.set(id,fn);return id;},cancelAnimationFrame:id=>paints.delete(id)};
vm.createContext(context);vm.runInContext(SOURCE,context);
const loader=context.window.ProtoPreviewLoading.create(container,overlay,frame,()=>retry++);
const paint=()=>{const current=[...paints.values()];paints.clear();current.forEach(fn=>fn());};
'''.replace('SOURCE', json.dumps(source)) + body
    result = subprocess.run([node, '-'], input=script, text=True, encoding='utf-8', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_ready_waits_for_committed_layout_without_an_artificial_loading_delay():
    case(r'''
const ticket=loader.begin('工作台');assert.equal(container.dataset.previewState,'loading');assert.equal(frame.inert,true);
assert.equal(container.attrs['aria-busy'],'true');assert.equal(button.hidden,true);
loader.ready(ticket);assert.equal(container.dataset.previewState,'loading');assert.equal(timers.size,0);
paint();assert.equal(container.dataset.previewState,'loading');paint();
assert.equal(container.dataset.previewState,'ready');assert.equal(frame.inert,false);assert.equal(overlay.inert,true);
assert.equal(overlay.attrs['aria-hidden'],'true');assert.equal(container.attrs['aria-busy'],'false');
''')


def test_late_previous_page_completion_and_timer_cannot_uncover_the_next_page():
    case(r'''
const first=loader.begin('第一页'),late=[...timers.values()][0].fn;
loader.ready(first);paint();const second=loader.begin('第二页');
loader.ready(first);loader.fail(first,'旧错误');late();paint();paint();
assert.equal(container.dataset.previewState,'loading');assert.equal(detail.textContent,'正在打开「第二页」');assert.equal(button.hidden,true);
loader.ready(second);paint();paint();assert.equal(container.dataset.previewState,'ready');
''')


def test_slow_loading_offers_retry_and_does_not_pretend_to_be_complete():
    case(r'''
loader.begin();const timer=[...timers.values()][0];assert.equal(timer.ms,12000);timer.fn();
assert.equal(container.dataset.previewState,'loading');assert.equal(button.hidden,false);assert.match(detail.textContent,/加载时间较长/);
button.click();assert.equal(retry,1);assert.equal(frame.inert,true);
''')


def test_failure_and_empty_project_clear_pending_work_without_stuck_spinner():
    case(r'''
const first=loader.begin();loader.fail(first,'目录已移除');
assert.equal(container.dataset.previewState,'error');assert.equal(container.attrs['aria-busy'],'false');
assert.equal(detail.textContent,'目录已移除');assert.equal(button.hidden,false);assert.equal(timers.size,0);
loader.ready(first);paint();paint();assert.equal(container.dataset.previewState,'error');
const next=loader.begin();loader.ready(next);loader.dismiss();paint();paint();
assert.equal(container.dataset.previewState,'ready');assert.equal(timers.size,0);assert.equal(paints.size,0);
assert.equal(frame.inert,false);loader.fail(next,'已过期');assert.equal(container.dataset.previewState,'ready');
''')


def test_first_paint_has_local_loading_feedback_and_keeps_iframe_measurable():
    from html.parser import HTMLParser

    class Elements(HTMLParser):
        def __init__(self): super().__init__(); self.items = {}
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('id'): self.items[attrs['id']] = attrs

    page = Elements(); page.feed((ROOT/'src/viewer.html').read_text(encoding='utf-8'))
    assert page.items['previewContainer']['data-preview-state'] == 'loading'
    assert page.items['previewContainer']['aria-busy'] == 'true'
    assert 'inert' in page.items['deviceFrameWrapper']
    assert page.items['previewLoading']['role'] == 'status'
    css = (ROOT/'src/preview-loading.css').read_text(encoding='utf-8')
    rule = css.split(':not([data-preview-state="ready"]) > #deviceFrameWrapper {', 1)[1].split('}', 1)[0]
    assert 'opacity: 0' in rule and 'display: none' not in rule and 'visibility: hidden' not in rule
    assert '@media(prefers-reduced-motion:reduce)' in css
