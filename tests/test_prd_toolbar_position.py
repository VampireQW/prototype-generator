"""Run the real toolbar placement function against panel and floating-card geometry."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/proto-markdown.js').read_text(encoding='utf-8')
PLACEMENT = SOURCE[SOURCE.index('    const TOOLBAR_GAP ='):SOURCE.index('    function suspend(')]
HARNESS = r'''
const assert = require('node:assert/strict');
const box = (left, top, width, height) => ({left, top, right:left+width, bottom:top+height, width, height});
const scroll = {scrollTop:200, getBoundingClientRect:()=>box(860,93,420,627)};
let headerTop=380, bodyTop=422, panelMode=true, hasHeader=true;
const rect = top => box(880,top+(200-scroll.scrollTop),380,30);
const header={getBoundingClientRect:()=>rect(headerTop)};
const note={querySelector:selector=>selector==='.ext-note-head'&&hasHeader?header:null};
const panel={getBoundingClientRect:()=>box(860,0,420,720), querySelector:()=>scroll};
const card={getBoundingClientRect:()=>box(240,240,420,260)};
const doc={defaultView:{innerWidth:1280,innerHeight:720},querySelectorAll:()=>[],getElementById:()=>null};
const region={ownerDocument:doc,getBoundingClientRect:()=>({...rect(bodyTop),height:180,bottom:rect(bodyTop).top+180}),
 closest:selector=>selector==='.pa-card'?(panelMode?null:card):selector==='.ext-note'?(hasHeader?note:null):selector==='#extReadingScroll'?scroll:panelMode?panel:null};
const bar={style:{},getBoundingClientRect(){const width=Number.parseFloat(this.style.width)||512;return box(Number.parseFloat(this.style.left)||0,Number.parseFloat(this.style.top)||0,width,width<500?68:38);}};
const s={region,toolbar:bar,toolbarOpening:true};
const placed=()=>bar.getBoundingClientRect();
'''


def run_case(case):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required')
    result = subprocess.run([node, '-e', HARNESS + PLACEMENT + case], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_annotation_toolbar_is_single_row_and_extends_left_from_number_header():
    run_case("""
placeToolbar(s); const r=placed(), h=header.getBoundingClientRect();
assert.equal(r.right,h.right); assert.ok(r.left<h.left);
assert.equal(r.height,38); assert.equal(r.width,512);
assert.ok(r.bottom<=h.top-12, 'toolbar must clear the annotation number');
assert.equal(scroll.scrollTop,200); assert.equal(region.style,undefined);
""")


def test_page_document_toolbar_starts_above_its_editor():
    run_case("""
hasHeader=false; bodyTop=230; placeToolbar(s);
const r=placed(), body=region.getBoundingClientRect();
assert.equal(r.right,body.right); assert.ok(r.left<body.left);
assert.equal(r.height,38);
assert.ok(r.bottom<=body.top-12);
""")


def test_opening_near_panel_header_reveals_space_by_scrolling_without_layout_slot():
    run_case("""
headerTop=110; bodyTop=152; placeToolbar(s);
const r=placed(), h=header.getBoundingClientRect();
assert.ok(scroll.scrollTop<200, 'scroll the current item down to expose its toolbar');
assert.ok(r.top>=93); assert.ok(r.bottom<=h.top-12);
const top=scroll.scrollTop; placeToolbar(s); assert.equal(scroll.scrollTop,top);
""")


def test_manual_toolbar_placement_is_preserved():
    run_case("""
s.toolbarManual=true; placeToolbar(s,20,30);
assert.equal(placed().left,20); assert.equal(placed().top,30);
assert.equal(scroll.scrollTop,200);
""")


def test_prototype_floating_card_keeps_its_external_toolbar():
    run_case("""
panelMode=false; placeToolbar(s); const r=placed(), c=card.getBoundingClientRect();
assert.ok(r.bottom<=c.top-12 || r.top>=c.bottom+12 || r.right<=c.left-12 || r.left>=c.right+12);
assert.equal(scroll.scrollTop,200);
""")
