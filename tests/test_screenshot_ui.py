"""截图标注聚焦、运行时与编辑器的前端回归。"""
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'


def node(code):
    binary = shutil.which('node') or 'D:/software/nodejs/node.exe'
    result = subprocess.run([binary, '-'], input=code, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_focus_long_screenshot_uses_annotation_point_instead_of_whole_image_center():
    source=(SRC/'proto-annotate.js').read_text(encoding='utf-8')
    focus=source[source.index('let focusGeneration = 0;'):source.index('async function testReveal(anchor)')]
    node("""
const assert=require('node:assert/strict');let scrolled=null;
const document={documentElement:{dataset:{protoScreenshot:'true'}}};
const image={id:'screenshot-image',matches:s=>s==='#screenshot-image',scrollIntoView(){throw Error('must focus annotation point');}};
const window={scrollY:700,innerHeight:800,scrollTo:value=>scrolled=value};
const notes=[{id:'one'}],ProtoAnchors={point:()=>({element:image,point:{x:90,y:-500}})};
const motion=()=> 'instant',selectNote=()=>{},layoutPins=()=>{},setTimeout=()=>{};
""" + focus + "\nflashNote('one').then(ok=>{assert.equal(ok,true);assert.equal(scrolled.top,0);});")


@pytest.mark.parametrize('name',['proto-screenshot-editor.js','screenshot-runtime.js'])
def test_script_syntax(name):
    binary=shutil.which('node') or 'D:/software/nodejs/node.exe'
    result=subprocess.run([binary,'--check',str(SRC/name)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0,result.stderr
