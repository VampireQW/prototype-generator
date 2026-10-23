"""截图页：相对图片坐标、可移植 HTML、带 revision 的原子修改。"""
from __future__ import annotations

import base64
import copy
import hashlib
import html
import io
import json
import math
import os
import posixpath
import re
import uuid
import warnings
from pathlib import Path
from urllib.parse import quote

import proto_meta

ASSETS = 'assets/prototype-screenshots'
PENDING = 'screenshot-operation.pending.json'
MAX_BYTES = 10 * 1024 * 1024
ID = re.compile(r'shot-[a-f0-9]{16}')
REGION_ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}')


class RevisionConflict(ValueError):
    def __init__(self, current):
        super().__init__('项目已更新，请刷新后重试；尚未保存的截图和热区仍保留在编辑区')
        self.current = current


def image_data(value):
    from PIL import Image, UnidentifiedImageError
    if not isinstance(value, str) or len(value) > MAX_BYTES * 4 // 3 + 256:
        raise ValueError('截图不能超过 10 MB')
    match = re.fullmatch(r'data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\r\n]+)', value)
    if not match:
        raise ValueError('请选择 PNG、JPG、WebP 或 GIF 截图')
    try:
        raw = base64.b64decode(match[2], validate=True)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('截图不能为空或超过 10 MB')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                kind = image.format.lower()
                size = image.size
                if kind != match[1] or not (1 <= size[0] <= 20000 and 1 <= size[1] <= 40000) or size[0] * size[1] > 40_000_000:
                    raise ValueError('截图格式不匹配或尺寸过大（最多 4000 万像素）')
                if getattr(image, 'n_frames', 1) > 1:
                    raise ValueError('请使用静态截图，不支持动画图片')
                image.verify()
        return raw, ('jpg' if kind == 'jpeg' else kind), size
    except (OSError, UnidentifiedImageError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValueError('无法读取截图，请重新导出为静态 PNG 或 JPG') from error


def safe_path(root, rel):
    target = root / proto_meta.safe_relative(rel)
    if not target.resolve().is_relative_to(root):
        raise ValueError('截图文件必须保存在项目内')
    for part in (target, *target.parents):
        if part == root:
            break
        if proto_meta.is_linked_path(part):
            raise ValueError('截图路径不能包含链接或目录联接')
    return target


def validate_record(page):
    data = page.get('screenshot')
    if not ID.fullmatch(str(page.get('id', ''))) or page.get('file') != 'pages/' + page['id'] + '.html' or not isinstance(data, dict):
        raise ValueError('截图页面登记无效')
    if not re.fullmatch(re.escape(ASSETS + '/' + page['id'] + '/') + r'[a-f0-9]{64}\.(png|jpg|webp|gif)', str(data.get('image', ''))):
        raise ValueError('截图资源路径无效')
    if any(type(data.get(key)) is not int or data[key] < 1 for key in ('width', 'height')):
        raise ValueError('截图尺寸无效')
    validate_regions(data.get('regions', []))


def validate_regions(regions, project=None):
    if not isinstance(regions, list) or len(regions) > 200:
        raise ValueError('每页最多添加 200 个矩形热区')
    seen = set()
    for item in regions:
        if not isinstance(item, dict) or not REGION_ID.fullmatch(str(item.get('id', ''))) or item['id'] in seen:
            raise ValueError('热区 ID 无效或重复')
        seen.add(item['id'])
        if not isinstance(item.get('label'), str) or not item['label'].strip() or len(item['label']) > 120:
            raise ValueError('请填写热区名称（最多 120 字）')
        if any(type(item.get(k)) not in (float, int) or not math.isfinite(item[k]) for k in ('x', 'y', 'width', 'height')):
            raise ValueError('热区坐标必须是有限数字')
        if item['x'] < 0 or item['y'] < 0 or item['width'] <= 0 or item['height'] <= 0 or item['x'] + item['width'] > 1.000001 or item['y'] + item['height'] > 1.000001:
            raise ValueError('热区必须在图片范围内')
        target = item.get('targetPageId', '')
        if not isinstance(target, str):
            raise ValueError('热区目标页面无效')
        if target and project is not None and not any(p['id'] == target and not p.get('trashedAt') for p in project['pages']):
            raise ValueError('热区目标页面不存在或已在回收站中')


def owned_images(page):
    if page.get('kind') != 'screenshot':
        return []
    validate_record(page)
    return [page['screenshot']['image']]


def render_page(page, project):
    validate_record(page)
    base = posixpath.dirname(page['file'])
    active = {p['id']: p for p in project['pages'] if not p.get('trashedAt')}
    regions = []
    for region in page['screenshot']['regions']:
        target = active.get(region.get('targetPageId'))
        regions.append({**region, 'targetFile': quote(posixpath.relpath(target['file'], base), safe='/') if target else ''})
    config = {'pageId': page['id'], 'image': quote(posixpath.relpath(page['screenshot']['image'], base), safe='/'),
              'width': page['screenshot']['width'], 'height': page['screenshot']['height'], 'regions': regions}
    payload = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    runtime = (Path(__file__).parent / 'src' / 'screenshot-runtime.js').read_text(encoding='utf-8')
    style = (Path(__file__).parent / 'src' / 'screenshot-runtime.css').read_text(encoding='utf-8')
    title = html.escape(page['title'], quote=True)
    return (f'<!doctype html><html lang="zh-CN" data-proto-page="{page["id"]}" data-proto-state="default" data-proto-screenshot="true" data-proto-preview="{page.get("previewType", "web")}">'
            f'<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{style}</style></head>'
            f'<body><main id="screenshot-stage"><img id="screenshot-image" data-proto-id="screenshot-image-{page["id"]}" src="{config["image"]}" width="{config["width"]}" height="{config["height"]}" alt="{title}" draggable="false">'
            f'<div id="screenshot-regions"></div></main><script id="screenshot-config" type="application/json">{payload}</script><script>{runtime}</script></body></html>')


def _atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_bytes(raw)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def mutate(root, action, data):
    root = Path(root).resolve()
    if action not in ('create', 'replace', 'regions'):
        raise ValueError('截图操作无效')
    with proto_meta.PROJECT_LOCK:
        before = proto_meta.load_bundle(root)
        if type(data.get('expectedRevision')) is not int or data['expectedRevision'] != before['revision']:
            raise RevisionConflict(before)
        bundle = copy.deepcopy(before); project = bundle['project']; created = []; obsolete = []
        if action == 'create':
            title = data.get('title')
            if not isinstance(title, str) or not title.strip() or len(title) > 100:
                raise ValueError('请填写页面名称（最多 100 字）')
            preview = data.get('previewType', 'web')
            if preview not in ('web', 'mobile', 'pad'):
                raise ValueError('页面外壳无效')
            client = data.get('clientId', '')
            if client and not any(c['id'] == client for c in project.get('clients', [])):
                raise ValueError('端分类不存在')
            page_id = 'shot-' + uuid.uuid4().hex[:16]
            page = {'id':page_id, 'title':title.strip(), 'file':'pages/' + page_id + '.html', 'kind':'screenshot', 'previewType':preview,
                    'clientId':client, 'states':[{'id':'default','title':'默认页面','kind':'default','interactionHints':{'mode':'targets','protoIds':[]}}]}
            page['url'] = (root / page['file']).as_uri()
            if data.get('parentId'):
                parent = next((p for p in project['pages'] if p['id'] == data['parentId'] and not p.get('trashedAt')), None)
                if not parent:
                    raise ValueError('父页面不存在')
                page['parentId'] = parent['id']
            project['pages'].append(page)
            if not project.get('defaultPage'):
                project['defaultPage'] = page_id
        else:
            page = next((p for p in project['pages'] if p['id'] == data.get('pageId') and not p.get('trashedAt')), None)
            if not page or page.get('kind') != 'screenshot':
                raise ValueError('请选择有效的截图页面')
            validate_record(page)
        changed = False
        if action in ('create', 'replace'):
            raw, extension, size = image_data(data.get('dataUrl'))
            image_rel = f'{ASSETS}/{page["id"]}/{hashlib.sha256(raw).hexdigest()}.{extension}'
            old = page.get('screenshot') or {}
            changed = bool(old and (old['width'], old['height']) != size)
            if old.get('image') and old['image'] != image_rel:
                obsolete.append(old['image'])
            page['screenshot'] = {'image':image_rel, 'width':size[0], 'height':size[1], 'regions':old.get('regions', [])}
        if action == 'regions':
            validate_regions(data.get('regions'), project)
            page['screenshot']['regions'] = [{k:r[k] for k in ('id','label','x','y','width','height','targetPageId') if k in r} for r in data['regions']]
        # 截图热区仅授权明确绘制的矩形，不扩大到整张图片。
        page['states'][0]['interactionHints'] = {'mode':'targets', 'protoIds':['screenshot-region-' + r['id'] for r in page['screenshot']['regions']]}
        bundle['revision'] += 1
        proto_meta.validate_bundle(bundle)
        source = safe_path(root, page['file']); previous = source.read_bytes() if source.exists() else None
        marker = proto_meta.meta_dir(root) / PENDING
        if proto_meta.is_linked_path(marker.parent) or proto_meta.is_linked_path(marker):
            raise ValueError('元数据路径不能是链接')
        image_path = safe_path(root, page['screenshot']['image'])
        html_bytes = render_page(page, project).encode('utf-8')
        if action in ('create', 'replace') and not image_path.exists():
            created.append(page['screenshot']['image'])
        proto_meta.write_json_atomic(marker, {'before':before, 'after':bundle, 'file':page['file'],
            'beforeHtml':base64.b64encode(previous).decode() if previous is not None else None, 'createdAssets':created, 'obsoleteAssets':obsolete})
        try:
            if created:
                _atomic(image_path, raw)
            _atomic(source, html_bytes)
            proto_meta.save_bundle(root, bundle)
        except Exception:
            if previous is None: source.unlink(missing_ok=True)
            else: _atomic(source, previous)
            for rel in created: safe_path(root, rel).unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            raise
        # 成功后才清理本页旧图片；不触碰项目的其他资源。
        for rel in obsolete:
            try: safe_path(root, rel).unlink(missing_ok=True)
            except OSError: pass
        marker.unlink(missing_ok=True)
        return {'ok':True, 'bundle':bundle, 'page':page, 'layoutChanged':changed}


def refresh_export(destination, bundle):
    """按当前目标页面状态重建副本，不带上回收站跳转或本地绝对路径。"""
    for page in bundle['project']['pages']:
        if page.get('kind') == 'screenshot' and not page.get('trashedAt'):
            target = destination / page['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_page(page, bundle['project']), encoding='utf-8')


def trashed_assets(bundle):
    return [relative for page in bundle['project']['pages'] if page.get('trashedAt') for relative in owned_images(page)]
