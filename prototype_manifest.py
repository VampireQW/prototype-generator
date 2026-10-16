"""Portable navigation declarations. No classification by filename or UI heuristics."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from pathlib import Path

MANIFEST_NAME = 'prototype.manifest.json'
ASSETS_DIR = Path(__file__).resolve().parent / 'agent-skills' / 'prototype-flow' / 'assets'
NAV_FILES = ('project-navigation.css', 'project-navigation.js', 'project-page.js')


def load_manifest(root: Path, *, missing_files=()) -> dict | None:
    import proto_meta
    path = root / MANIFEST_NAME
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 256_000:
        raise ValueError('页面清单必须是项目内小于 256 KB 的普通文件')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        raise ValueError(f'页面清单读取失败：{error}') from error
    if not isinstance(data, dict) or data.get('schemaVersion') != 1:
        raise ValueError('页面清单 schemaVersion 必须为 1')
    clients = data.get('clients', [])
    pages = data.get('pages')
    if not isinstance(clients, list) or not isinstance(pages, list) or (not pages and data.get('allowEmpty') is not True):
        raise ValueError('页面清单需要非空 pages 数组和 clients 数组')
    client_ids = set()
    for client in clients:
        if not isinstance(client, dict) or not isinstance(client.get('id'), str) or not client['id'] or client['id'] in client_ids:
            raise ValueError('端 ID 为空或重复')
        if not isinstance(client.get('title'), str) or not client['title'].strip():
            raise ValueError('请填写端名称')
        if client.get('previewType', 'web') not in ('mobile', 'web', 'pad'):
            raise ValueError('端的 previewType 必须为 mobile、web 或 pad')
        client_ids.add(client['id'])
    files = set()
    missing_files = {str(f).replace('\\', '/').casefold() for f in missing_files}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('file'), str):
            raise ValueError('页面清单缺少 file')
        relative = proto_meta.safe_relative(page['file']).as_posix()
        if relative.casefold() in files:
            raise ValueError('页面清单中的文件重复')
        files.add(relative.casefold())
        if Path(relative).suffix.lower() not in ('.html', '.htm'):
            raise ValueError('页面清单只能登记 HTML 页面')
        try:
            proto_meta.safe_asset(root, relative)
        except FileNotFoundError as error:
            if relative.casefold() not in missing_files:
                raise ValueError(f'页面文件不存在或不允许访问：{relative}') from error
        except ValueError as error:
            raise ValueError(f'页面文件不存在或不允许访问：{relative}') from error
        page['file'] = relative
        if page.get('role', 'page') not in ('page', 'launcher'):
            raise ValueError('页面 role 必须为 page 或 launcher')
        if page.get('clientId') and page['clientId'] not in client_ids:
            raise ValueError('页面引用了未登记的端')
        if 'previewType' in page and page['previewType'] not in ('mobile', 'web', 'pad'):
            raise ValueError('页面的 previewType 必须为 mobile、web 或 pad')
        if 'states' in page:
            states = page['states']
            if not isinstance(states, list) or not states:
                raise ValueError('页面 states 必须为非空数组')
            used = set()
            for state in states:
                if not isinstance(state, dict) or not isinstance(state.get('id'), str) or not state['id'] or state['id'] in used:
                    raise ValueError('页面状态 ID 为空或重复')
                used.add(state['id'])
                if state.get('previewType', 'web') not in ('mobile', 'web', 'pad'):
                    raise ValueError('状态 previewType 必须为 mobile、web 或 pad')
    declared_files = {p['file'].casefold(): p for p in pages}
    hierarchy = []
    for item in pages:
        record = {'id': item['file'].casefold(), 'role': item.get('role', 'page'), 'clientId': item.get('clientId', '')}
        if 'parentFile' in item:
            if not isinstance(item['parentFile'], str):
                raise ValueError('parentFile 必须为相对页面文件名或空字符串')
            if item['parentFile']:
                parent = proto_meta.safe_relative(item['parentFile']).as_posix()
                if parent.casefold() not in declared_files:
                    raise ValueError('parentFile 指向的父页面未登记')
                item['parentFile'] = parent
                record['parentId'] = parent.casefold()
        hierarchy.append(record)
    proto_meta.validate_page_hierarchy(hierarchy)
    business = [p for p in pages if p.get('role', 'page') == 'page']
    if not business and data.get('allowEmpty') is not True:
        raise ValueError('至少保留一个可直接打开的业务页面，不能将所有页面标记为演示入口')
    if data.get('defaultPage'):
        data['defaultPage'] = str(data['defaultPage']).replace('\\', '/')
    if data.get('defaultPage') and not any(p['file'].casefold() == data['defaultPage'].casefold() for p in business):
        raise ValueError('defaultPage 必须指向清单中的业务页面')
    return data


def apply_manifest(root: Path, bundle: dict, declaration: dict | None = None) -> bool:
    data = declaration if declaration is not None else load_manifest(root)
    if data is None:
        return False
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    project = bundle['project']
    if project.get('navigationManifestHash') == fingerprint:
        return False
    requested_clients = {c['id']: {k: c[k] for k in ('id', 'title', 'previewType') if k in c} for c in data.get('clients', [])}
    merged_clients = []
    for previous in project.get('clients', []):
        requested = requested_clients.pop(previous['id'], None)
        if requested is not None:
            if previous.get('userCreated'):
                requested['userCreated'] = True
            merged_clients.append(requested)
        elif previous.get('userCreated'):
            merged_clients.append(previous)
    project['clients'] = merged_clients + list(requested_clients.values())
    clients = {c['id']: c for c in project['clients']}
    by_file = {p['file'].casefold(): p for p in project['pages']}
    for item in data['pages']:
        page = by_file.get(item['file'].replace('\\', '/').casefold())
        if page is None:
            raise ValueError(f"页面未登记：{item['file']}")
        page['role'] = item.get('role', 'page')
        page['clientId'] = item.get('clientId', '')
        page['previewType'] = item.get('previewType') or clients.get(page['clientId'], {}).get('previewType', 'web')
        if isinstance(item.get('title'), str) and item['title'].strip():
            page['title'] = item['title'].strip()
        for requested in item.get('states', []):
            existing = next((s for s in page['states'] if s['id'] == requested['id']), None)
            if existing is None:
                existing = {'id': requested['id'], 'title': requested.get('title', requested['id']), 'kind': 'adapter'}
                page['states'].append(existing)
            for key in ('title', 'previewType'):
                if key in requested:
                    existing[key] = requested[key]
    by_id = {p['id']: p for p in project['pages']}
    for page in project['pages']:
        parent = by_id.get(page.get('parentId'))
        if parent and (page.get('role') == 'launcher' or parent.get('role') == 'launcher' or (page.get('clientId') or '') != (parent.get('clientId') or '')):
            page.pop('parentId', None)
    for item in data['pages']:
        if 'parentFile' in item:
            page = by_file[item['file'].casefold()]
            if item['parentFile']:
                page['parentId'] = by_file[item['parentFile'].casefold()]['id']
            else:
                page.pop('parentId', None)
    desired = data.get('defaultPage') or next((p['file'] for p in data['pages'] if p.get('role', 'page') == 'page'), '')
    selected = by_file.get(desired.replace('\\', '/').casefold())
    project['defaultPage'] = selected['id'] if selected and not selected.get('trashedAt') else next((p['id'] for p in project['pages'] if not p.get('trashedAt') and p.get('role') != 'launcher'), '')
    project['navigationManifestHash'] = fingerprint
    return True


def public_navigation(project: dict) -> dict:
    """Whitelist only display fields; never put file:// URLs, task data or root paths in launchers."""
    import proto_meta
    return {
        'name': project.get('name', '原型项目'),
        'clients': [{k: c[k] for k in ('id', 'title', 'previewType') if k in c} for c in project.get('clients', [])],
        'defaultPage': project.get('defaultPage', ''),
        'pages': [{**{k: p[k] for k in ('id', 'title', 'file', 'role', 'clientId', 'previewType', 'priority', 'progress', 'parentId') if k in p},
                   'states': [{k: s[k] for k in ('id', 'title', 'previewType') if k in s} for s in p.get('states', [])]}
                  for p in proto_meta.navigation_pages(project.get('pages', []))],
    }


def build_launcher(root: Path, bundle: dict) -> list[str]:
    """Regenerate only an explicitly declared index launcher. Existing business indexes stay intact."""
    project = bundle['project']
    entry = next((p for p in project['pages'] if p['file'].casefold() == 'index.html'), None)
    if not entry or entry.get('role') != 'launcher' or entry.get('trashedAt'):
        return []
    import proto_meta
    root = root.resolve()
    def output_path(relative: str) -> Path:
        path = root / proto_meta.safe_relative(relative)
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'导航输出路径必须位于项目内：{relative}')
        return path
    target = output_path('assets/prototype-navigation')
    outputs = [(ASSETS_DIR / name, output_path(f'assets/prototype-navigation/{name}')) for name in NAV_FILES]
    entry_file = proto_meta.safe_asset(root, entry['file'])
    pending_pages = []
    for page in project['pages']:
        if page.get('role') == 'launcher' or page.get('trashedAt'):
            continue
        page_file = proto_meta.safe_asset(root, page['file'])
        source = page_file.read_text(encoding='utf-8')
        if 'data-proto-page-helper' not in source:
            helper = Path(os.path.relpath(target / 'project-page.js', page_file.parent)).as_posix()
            tag = f'<script data-proto-page-helper data-prototype-owned src="{html.escape(helper, quote=True)}"></script>'
            source = source.replace('</body>', tag + '\n</body>') if '</body>' in source else source + '\n' + tag
            pending_pages.append((page['file'], page_file, source))
    payload = json.dumps(public_navigation(project), ensure_ascii=False).replace('</', '<\\/')
    source = (ASSETS_DIR / 'launcher.html').read_text(encoding='utf-8')
    source = source.replace('data-proto-page="home"', f'data-proto-page="{html.escape(entry["id"], quote=True)}"')
    source = source.replace('__PROJECT_TITLE__', html.escape(project.get('name', '原型项目'), quote=True))
    source = source.replace('__NAVIGATION_DATA__', payload)
    # Finish path and source checks before making any navigation or page changes.
    for resource, _ in outputs:
        if not resource.is_file():
            raise FileNotFoundError(f'缺少导航资源：{resource.name}')
    target.mkdir(parents=True, exist_ok=True)
    for resource, destination in outputs:
        shutil.copy2(resource, destination)
    for _, page_file, page_source in pending_pages:
        page_file.write_text(page_source, encoding='utf-8')
    entry_file.write_text(source, encoding='utf-8')
    return [entry['file'], *(f'assets/prototype-navigation/{name}' for name in NAV_FILES),
            *(relative for relative, _, _ in pending_pages)]
