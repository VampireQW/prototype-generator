"""PRD 图片边界、序号颜色持久化与实际对比度。"""
import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import proto_meta

SRC = Path(__file__).resolve().parents[1] / 'src'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


@pytest.mark.parametrize('failure', ['old-service', 'network'])
def test_image_upload_gives_restart_guidance_for_old_or_unreachable_service(failure):
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js')
    viewer = (SRC / 'viewer.html').read_text(encoding='utf-8')
    upload = re.search(r'function extImageOptions\(\)[\s\S]+?(?=\n        async function extDeleteNote)', viewer)[0]
    script = "global.extId='p-isolated';" + upload + "\nconst failure=" + json.dumps(failure) + ";\n" + """
global.FileReader=class{readAsDataURL(){this.result='data:image/png;base64,AAAA';queueMicrotask(()=>this.onload());}};
global.fetch=async()=>{if(failure==='network')throw new TypeError('Failed to fetch');return new Response('<!DOCTYPE HTML><p>Not Found</p>',{status:404,headers:{'Content-Type':'text/html;charset=utf-8'}});};
(async()=>{let message='';try{await extImageOptions().uploadImage({});}catch(e){message=e.message;}
if(!message.includes('重启'))throw new Error('未给出服务重启指引：'+message);
global.fetch=async()=>new Response(JSON.stringify({ok:true,path:'prd-assets/image.png'}),{status:200,headers:{'Content-Type':'application/json'}});
if(await extImageOptions().uploadImage({})!=='prd-assets/image.png')throw new Error('正常上传返回路径失败');
})().catch(error=>{console.error(error);process.exit(1)});
"""
    result = subprocess.run([executable, '-'], input=script, text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('data', ['data:image/png;base64,@@@@', 'data:image/png;base64,' + base64.b64encode(b'not an image').decode(), 'data:text/html;base64,PGh0bWw+', 'data:image/jpeg;base64,' + base64.b64encode(PNG).decode(), None])
def test_reject_invalid_image_content(tmp_path, data):
    with pytest.raises(ValueError):
        proto_meta.store_prd_image(tmp_path, data)
    assert not (tmp_path / 'prd-assets').exists()


def test_image_size_limit(tmp_path):
    with pytest.raises(ValueError, match='10 MB'):
        proto_meta.store_prd_image(tmp_path, 'data:image/png;base64,' + base64.b64encode(PNG + bytes(proto_meta.MAX_PRD_IMAGE_SIZE)).decode())


def test_annotation_color_roundtrip_and_validation(tmp_path):
    (tmp_path / 'index.html').write_text('<title>需求</title>', encoding='utf-8')
    bundle = proto_meta.ensure_bundle(tmp_path)
    page = bundle['project']['pages'][0]
    note = {'id': 'n1', 'number': 1, 'pageId': page['id'], 'stateId': page['states'][0]['id'], 'body': '需求', 'color': '#fdd143'}
    bundle['prd']['annotations'].append(note)
    proto_meta.save_bundle(tmp_path, bundle)
    assert proto_meta.load_bundle(tmp_path)['prd']['annotations'][0]['color'] == '#fdd143'
    note['color'] = 'red;background:url(x)'
    with pytest.raises(ValueError, match='颜色'):
        proto_meta.validate_bundle(bundle)


def test_palette_pin_contrast_and_reset():
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js')
    source = (SRC / 'proto-appearance.js').read_text(encoding='utf-8')
    script = "global.window={};" + source + """
const styles={}; const element={style:{setProperty(k,v){styles[k]=v;}}};
const a=window.ProtoAppearance;
const rendered=[];
for(const [color] of a.PIN_COLORS){a.applyPin(element,{color}); if(styles['--pin-fill']!==color)throw Error('颜色未应用');rendered.push({color,ink:styles['--pin-ink'],stroke:styles['--pin-stroke']});}
a.applyPin(element,{});if(styles['--pin-fill']!==a.DEFAULT_PIN)throw Error('默认颜色未恢复');
a.applyPin(element,{color:'#e6e6e6'});if(styles['--pin-fill']!=='#e6e6e6')throw Error('旧浅灰标注颜色被改写');
console.log(JSON.stringify({text:a.TEXT_COLORS,pins:a.PIN_COLORS,rendered}));
"""
    result = subprocess.run([executable, '-'], input=script, text=True, capture_output=True, encoding='utf-8', check=True)
    data = json.loads(result.stdout)
    assert [c for c, _ in data['text']] == ['#191919','#1684fc','#8a38f5','#666666','#fbfbfb','#ec4954','#ff9f29']
    assert len(data['pins']) == 10
    assert data['pins'][0] == ['#2563eb', '默认蓝色']
    assert '#e6e6e6' not in [color for color, _ in data['pins']]
    def lum(hex):
        c = [int(hex[i:i+2], 16) / 255 for i in (1,3,5)]
        return sum((v / 12.92 if v <= .04045 else ((v+.055)/1.055)**2.4) * w for v,w in zip(c,(.2126,.7152,.0722)))
    for rendered in data['rendered']:
        def contrast(a, b):
            values = sorted([lum(a), lum(b)])
            return (values[1] + .05) / (values[0] + .05)
        assert contrast(rendered['color'], rendered['ink']) >= 4.5
        assert contrast(rendered['color'], rendered['stroke']) >= 3


def test_export_image_renderer_keeps_code_literal_and_uses_site_asset_path():
    executable = shutil.which('node')
    if not executable:
        pytest.skip('需要 Node.js')
    shell = (SRC / 'review_shell.html').read_text(encoding='utf-8')
    renderer = re.search(r'function esc\(s\) \{[\s\S]+?(?=\s+function md\(src\))', shell)[0]
    image = 'prd-assets/' + 'a' * 64 + '.png'
    script = "const location={href:'https://example.github.io/repo/projects/p1/index.html'};" + renderer + "\nconst path=" + json.dumps(image) + ";\n" + """
const value=inline('![需求]('+path+')');
if(!value.includes('https://example.github.io/repo/projects/p1/proto/'+path))throw Error(value);
if(inline('`![需求]('+path+')`').includes('<img'))throw Error('代码被渲染成图片');
if(inline('![x](javascript:alert)').includes('<img'))throw Error('危险 URL 被放行');
if(inline('<img src=x onerror=alert(1)>').includes('<img'))throw Error('原始 HTML 被放行');
"""
    subprocess.run([executable, '-'], input=script, text=True, capture_output=True, encoding='utf-8', check=True)
