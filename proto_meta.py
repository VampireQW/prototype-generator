"""原型元数据层：.prototype 三文件 + revision CAS。

来源：移植自「原型生成全流程」server.py / preview.py（SCHEMA_VERSION=2），
格式与全流程严格一致——同一项目的 .prototype 元数据两个工具可互开互认。
本模块自包含，不依赖全流程的任何文件。
（全流程已于 2026-09-26 归档至 独立项目\_归档\原型生成全流程\，不再运行。）
"""
from __future__ import annotations

import hashlib
import base64
import json
import math
import os
import re
import tempfile
import threading
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
PROJECT_LOCK = threading.RLock()
MAX_PRD_IMAGE_SIZE = 10 * 1024 * 1024


def store_prd_image(root: Path, data_url: str) -> str:
    """将 PRD 图片按内容哈希存入项目，返回可移植的 Markdown 相对路径。"""
    if not isinstance(data_url, str) or len(data_url) > MAX_PRD_IMAGE_SIZE * 4 // 3 + 128:
        raise ValueError('图片不能超过 10 MB')
    match = re.fullmatch(r'data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\r\n]+)', data_url)
    if not match:
        raise ValueError('仅支持 PNG、JPG、GIF、WebP 图片')
    try:
        raw = base64.b64decode(match[2].replace('\r', '').replace('\n', ''), validate=True)
    except ValueError:
        raise ValueError('图片编码无效') from None
    if not raw or len(raw) > MAX_PRD_IMAGE_SIZE:
        raise ValueError('图片不能为空或超过 10 MB')
    kind = ('png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
            'jpeg' if raw.startswith(b'\xff\xd8\xff') else
            'gif' if raw.startswith((b'GIF87a', b'GIF89a')) else
            'webp' if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP' else None)
    if not kind or kind != match[1]:
        raise ValueError('图片内容与格式不一致')
    root = Path(root).resolve()
    folder = root / 'prd-assets'
    if folder.is_symlink() or (folder.exists() and folder.resolve() != folder):
        raise ValueError('图片目录不能是链接')
    folder.mkdir(exist_ok=True)
    filename = hashlib.sha256(raw).hexdigest() + '.' + ('jpg' if kind == 'jpeg' else kind)
    target = folder / filename
    if target.is_symlink():
        raise ValueError('图片文件不能是链接')
    if not target.exists():
        fd, temp = tempfile.mkstemp(dir=folder, suffix='.upload')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return 'prd-assets/' + filename

ASSET_TYPES = {'.html', '.htm', '.css', '.js', '.mjs', '.json', '.svg', '.png', '.jpg', '.jpeg',
               '.webp', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.mp4', '.webm', '.ogg', '.mp3'}
EXCLUDED = {'.prototype', 'exports', 'dist', 'node_modules', '__pycache__'}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def slugify(text: str) -> str:
    text = re.sub(r"[^\w一-鿿-]+", "-", text.strip(), flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return text[:60] or "prototype"


def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "file":
        # 文件身份以解码后的本机路径为准，查询参数与片段不另建页面。
        path = file_url_to_path(url).resolve()
        return Path(os.path.normcase(str(path))).as_uri()
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def file_url_to_path(url: str) -> Path | None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "file":
        return None
    if parts.netloc and parts.netloc.lower() != "localhost":
        raise ValueError("仅支持本机 file:// 原型，请使用本地磁盘路径")
    path = urllib.request.url2pathname(parts.path)
    if os.name == "nt" and path.startswith("\\") and re.match(r"^\\[A-Za-z]:", path):
        path = path[1:]
    return Path(path)


def project_id_for(root: Path) -> str:
    key = str(root.resolve()).replace("/", "\\").lower()
    return "p-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def meta_dir(root: Path) -> Path:
    return root / ".prototype"


def safe_relative(path: str) -> Path:
    rel = Path(path.replace("\\", "/"))
    if rel.is_absolute() or rel.drive or ':' in path or any(part in ("", ".", "..") or part.startswith('.') or part != part.rstrip(' .') for part in rel.parts):
        raise ValueError("路径必须位于项目内")
    return rel


def page_record(root: Path, url: str, title: str) -> dict[str, Any]:
    file_path = file_url_to_path(url)
    rel = "index.html"
    if file_path:
        try:
            rel = file_path.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            rel = file_path.name or "index.html"
    page_id = slugify(Path(rel).stem)
    if page_id in {"index", "主页"}:
        page_id = "home"
    return {
        "id": page_id,
        "title": title or page_id,
        "file": rel,
        "url": canonical_url(url),
        "states": [{"id": "default", "title": "默认页面", "kind": "default"}],
    }


def default_bundle(root: Path, url: str, title: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "revision": 0,
        "project": {
            "id": project_id_for(root),
            "name": root.name or "原型项目",
            "pages": [page_record(root, url, title)],
        },
        "prd": {"documents": [], "annotations": []},
        "changes": {"items": []},
    }


def validate_size(value, label="视口"):
    if value is None:
        return None
    if not isinstance(value, dict) or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) or not 0 < value[k] <= 10_000_000 for k in ("width", "height")):
        raise ValueError(f"{label}尺寸无效")
    return {k: value[k] for k in ("width", "height")}


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("项目协议版本不支持")
    if not isinstance(bundle.get("revision"), int) or bundle["revision"] < 0:
        raise ValueError("revision 无效")
    project = bundle.get("project") or {}
    pages = project.get("pages")
    if not project.get("id") or not isinstance(pages, list) or not pages:
        raise ValueError("项目页面清单无效")
    scopes: set[str] = set()
    page_ids: set[str] = set()
    for page in pages:
        if not page.get("id") or page["id"] in page_ids:
            raise ValueError("页面 ID 为空或重复")
        page_ids.add(page["id"])
        safe_relative(page.get("file") or "index.html")
        states = page.get("states")
        if not isinstance(states, list) or not states:
            raise ValueError("页面状态清单无效")
        for state in states:
            if not state.get("id") or state.get("kind") not in {"default", "adapter", "manual"}:
                raise ValueError("状态定义无效")
            key = f"{page['id']}\n{state['id']}"
            if key in scopes:
                raise ValueError("状态 ID 重复")
            scopes.add(key)
            validate_size(state.get('viewport'))
    for group in (bundle.get("prd", {}).get("documents"), bundle.get("prd", {}).get("annotations"), bundle.get("changes", {}).get("items")):
        if not isinstance(group, list):
            raise ValueError("PRD 或任务列表无效")
        ids = set()
        for item in group:
            if item.get('id') in ids:
                raise ValueError("元数据条目 ID 重复")
            ids.add(item.get('id'))
            if not item.get("id") or f"{item.get('pageId')}\n{item.get('stateId')}" not in scopes:
                raise ValueError("条目引用了未登记状态")
    numbers = set()
    for note in bundle['prd']['annotations']:
        if note.get('color') is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(note['color'])):
            raise ValueError('标注颜色无效')
        number = note.get('number')
        if type(number) is not int or number < 1:
            raise ValueError('标注编号无效')
        key = (note['pageId'], note['stateId'], number)
        if key in numbers:
            raise ValueError('标注编号重复，请保留草稿并重新分配新增编号')
        numbers.add(key)
        p = note.get('placement')
        if p is not None:
            if not isinstance(p, dict) or p.get('kind') not in {'element', 'document'}:
                raise ValueError('标注落点类型无效')
            if any(type(p.get(k)) not in (int, float) or not math.isfinite(p[k]) for k in ('x', 'y')):
                raise ValueError('标注落点坐标必须为有限数字')
            if p['kind'] == 'document' and (p['x'] < 0 or p['y'] < 0):
                raise ValueError('页面落点坐标不能为负数')
            if p['kind'] == 'element' and not isinstance(note.get('anchor'), dict):
                raise ValueError('元素落点缺少锚点')
    if len(json.dumps(bundle, ensure_ascii=False)) > 8_000_000:
        raise ValueError("项目元数据过大")
    return bundle


def docs_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    common = {"schemaVersion": SCHEMA_VERSION, "projectId": bundle["project"]["id"], "revision": bundle["revision"]}
    return {
        "project.json": {**common, **bundle["project"]},
        "prd.json": {**common, **bundle["prd"]},
        "changes.json": {**common, **bundle["changes"]},
    }


def bundle_from_docs(docs: dict[str, Any]) -> dict[str, Any]:
    p, prd, changes = docs["project.json"], docs["prd.json"], docs["changes.json"]
    revision = p.get("revision", 0)
    for doc in (p, prd, changes):
        if doc.get("schemaVersion") != SCHEMA_VERSION or doc.get("projectId") != p.get("id") or doc.get("revision") != revision:
            raise ValueError("项目元数据版本不一致")
    return validate_bundle({
        "schemaVersion": SCHEMA_VERSION,
        "revision": revision,
        "project": {"id": p["id"], "name": p.get("name", "原型项目"), "pages": p.get("pages", []),
                    **{key: p[key] for key in ('source', 'aiProjectId', 'previewType') if key in p}},
        "prd": {"documents": prd.get("documents", []), "annotations": prd.get("annotations", [])},
        "changes": {"items": changes.get("items", [])},
    })


def load_bundle(root: Path) -> dict[str, Any]:
    md = meta_dir(root)
    if (md / ".pending-write.json").exists():
        raise ValueError("上次元数据保存中断，已保留 .pending-write.json 恢复备份；请先恢复，不会重建项目")
    docs = {}
    for name in ("project.json", "prd.json", "changes.json"):
        try:
            docs[name] = json.loads((md / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"项目元数据读取失败（{name}），已保留原文件：{error}") from error
    return bundle_from_docs(docs)


def save_bundle(root: Path, bundle: dict[str, Any]) -> None:
    validate_bundle(bundle)
    with PROJECT_LOCK:
        md = meta_dir(root)
        marker = md / ".pending-write.json"
        if marker.exists():
            raise ValueError("元数据有未完成写入，请保留恢复备份")
        docs = docs_from_bundle(bundle)
        old = {name: json.loads((md / name).read_text(encoding="utf-8")) for name in docs if (md / name).exists()}
        write_json_atomic(marker, {"before": old, "after": docs})
        try:
            for name, doc in docs.items():
                write_json_atomic(md / name, doc)
        except OSError:
            for name, doc in old.items():
                write_json_atomic(md / name, doc)
            if len(old) == 3:
                marker.unlink()
            raise
        marker.unlink()


def page_for_url(bundle: dict[str, Any], url: str) -> dict[str, Any] | None:
    key = canonical_url(url)
    return next((page for page in bundle["project"]["pages"]
                 if canonical_url(page.get("url", "")) == key), None)


def page_for_source(bundle, root, url):
    page = page_for_url(bundle, url)
    if page:
        return page
    source = file_url_to_path(url)
    if source:
        rel = source.resolve().relative_to(root.resolve()).as_posix()
        return next((p for p in bundle['project']['pages'] if p['file'].casefold() == rel.casefold()), None)
    return None


def ensure_bundle(root: Path, url: str = "", title: str = "") -> dict[str, Any]:
    md = meta_dir(root)
    if not any((md / name).exists() for name in ("project.json", "prd.json", "changes.json")):
        if not url:
            pages = discover_pages(root)
            if not pages:
                raise ValueError("项目目录中没有 HTML 原型")
            url, title = pages[0]["url"], pages[0]["title"]
        bundle = default_bundle(root, url, title)
        save_bundle(root, bundle)
        return bundle
    # 已有元数据不能因读取、校验失败被默认空项目覆盖。
    bundle = load_bundle(root)
    if url and page_for_source(bundle, root, url) is None:
        page = page_record(root, url, title)
        used_ids = {item["id"] for item in bundle["project"]["pages"]}
        base_id = page["id"]
        suffix = 2
        while page["id"] in used_ids:
            page["id"] = f"{base_id}-{suffix}"
            suffix += 1
        bundle["project"]["pages"].append(page)
        bundle["revision"] += 1
        save_bundle(root, bundle)
    return bundle


def ensure_project_id(root: Path, bundle: dict[str, Any], pid: str) -> bool:
    """项目目录被复制/移动后，bundle 内 project.id 与登记 pid 不一致时对齐（三份文件 projectId 随 save_bundle 同步）。"""
    if bundle['project'].get('id') == pid:
        return False
    bundle['project']['id'] = pid
    bundle['revision'] += 1
    save_bundle(root, bundle)
    return True


def ensure_pages_registered(root: Path, bundle: dict[str, Any]) -> bool:
    """把目录里新发现但未登记的页面补进 bundle；有变更则 revision+1 并落盘。返回是否有变更。"""
    pages = bundle['project']['pages']
    known_files = {str(p.get('file', '')).casefold() for p in pages}
    known_ids = {p['id'] for p in pages}
    changed = False
    for rec in discover_pages(root):
        if rec['file'].casefold() in known_files:
            continue
        page = page_record(root, rec['url'], rec['title'])
        base_id = page['id']
        suffix = 2
        while page['id'] in known_ids:
            page['id'] = f'{base_id}-{suffix}'
            suffix += 1
        known_ids.add(page['id'])
        known_files.add(page['file'].casefold())
        pages.append(page)
        changed = True
    if changed:
        bundle['revision'] += 1
        save_bundle(root, bundle)
    return changed


def ensure_ai_project_bundle(root: Path, record: dict, detected_pages: list[dict], name: str = '') -> dict:
    """把旧 AI 项目接入同一工作台，首次补登状态与页面需求，已有内容保持原样。"""
    with PROJECT_LOCK:
        bundle = ensure_bundle(root)
        ensure_project_id(root, bundle, project_id_for(root))
        ensure_pages_registered(root, bundle)
        project = bundle['project']
        before = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
        project.update(source='ai', aiProjectId=root.name)
        if name:
            project['name'] = name
        global_data = record.get('global') if isinstance(record.get('global'), dict) else {}
        skill_id = record.get('skillId') or global_data.get('skillId') or ''
        inputs = [item for item in (record.get('pages') or []) if isinstance(item, dict)]
        pages = project['pages']
        home = next((page for page in pages if str(page.get('file', '')).casefold() == 'index.html'), pages[0])
        source = safe_asset(root, home['file']).read_text(encoding='utf-8', errors='replace')
        hint = global_data.get('previewType') or record.get('previewType')
        if hint not in ('mobile', 'web'):
            hint = 'mobile' if skill_id == 'mobile-app' else 'web' if skill_id in ('web-prototype', 'dashboard', 'saas-landing', 'html-ppt') else ''
        if not hint:
            declaration = re.search(r'data-proto-preview\s*=\s*["\'](mobile|web)["\']', source)
            hint = declaration.group(1) if declaration else ''
        if hint:
            project['previewType'] = hint
        scopes = []
        if len(pages) == 1:
            modern_ids = []
            for value in re.findall(r'data-proto-state\s*=\s*["\']([^"\']+)["\']', source):
                if value not in modern_ids:
                    modern_ids.append(value)
            for values in re.findall(r'data-state-visible\s*=\s*["\']([^"\']+)["\']', source):
                for value in values.split(','):
                    if value.strip() and value.strip() not in modern_ids:
                        modern_ids.append(value.strip())
            has_modern_bridge = 'PrototypeBridge' in source
            candidates = []
            if has_modern_bridge:
                home.pop('aiNavigation', None)
                candidates = [{'name': value, 'label': value, 'type': 'bridge'} for value in modern_ids]
                # 新外部单文件协议明确要求每个需求页按名称 slug 登记为状态。
                input_ids = set()
                for item in inputs:
                    base_id = slugify(str(item.get('name') or ''))
                    if not base_id:
                        continue
                    state_id, suffix = base_id, 2
                    while state_id in input_ids:
                        state_id = f'{base_id}-{suffix}'
                        suffix += 1
                    input_ids.add(state_id)
                    candidate = next((candidate for candidate in candidates if candidate['name'] == state_id), None)
                    if candidate is None:
                        candidate = {'name': state_id, 'label': str(item.get('name') or state_id), 'type': 'bridge'}
                        candidates.append(candidate)
                    candidate['input'] = item
            elif detected_pages:
                candidates = detected_pages
                home['aiNavigation'] = 'legacy'
            # 只有已检测到实际单页切换能力，才把 record 页数解释为状态。
            for index, candidate in enumerate(candidates):
                legacy_name = str(candidate.get('name') or '').strip()
                if not legacy_name:
                    continue
                state_id = legacy_name if candidate.get('type') == 'bridge' else slugify(legacy_name)
                state = next((item for item in home['states'] if item['id'] == state_id), None)
                matching = candidate.get('input') or next((item for item in inputs if slugify(str(item.get('name') or '')) == slugify(legacy_name)), None)
                if matching is None and len(inputs) == len(candidates):
                    matching = inputs[index]
                title = str((matching or {}).get('name') or candidate.get('label') or legacy_name)
                if state is None:
                    state = {'id': state_id, 'title': title, 'kind': 'adapter'}
                    home['states'].append(state)
                if candidate.get('type') in ('currentPage', 'router'):
                    state.update(legacyPage=legacy_name, legacyType=candidate['type'])
                    if candidate.get('routePath'):
                        state['routePath'] = candidate['routePath']
                scopes.append((home, state, matching, [legacy_name, title]))
        if not scopes:
            for index, page in enumerate(pages):
                stem = Path(page['file']).stem
                aliases = [page['id'], page.get('title', ''), stem]
                matching = next((item for item in inputs if slugify(str(item.get('name') or '')) in {slugify(alias) for alias in aliases}), None)
                if matching is None and len(pages) == len(inputs):
                    matching = inputs[index]
                elif matching is None and page is home and len(pages) == 1 and len(inputs) == 1:
                    matching = inputs[0]
                if matching:
                    aliases.append(str(matching.get('name') or ''))
                scopes.append((page, page['states'][0], matching, aliases))
        prd_dir = root / 'prd'
        old_docs = {}
        if prd_dir.is_dir() and not is_linked_path(prd_dir):
            for path in sorted(prd_dir.glob('*.md')):
                if not is_linked_path(path) and path.is_file():
                    old_docs[path.stem] = path.read_text(encoding='utf-8')
        used_legacy = set()
        for page, state, matching, aliases in scopes:
            keys = {re.sub(r'[^\w\u4e00-\u9fff-]', '_', str(alias)) for alias in aliases if alias}
            legacy = next((key for key in old_docs if key in keys), None)
            markdown = old_docs[legacy] if legacy else ''
            if legacy:
                used_legacy.add(legacy)
            if not markdown.strip() and matching:
                parts = []
                for key, title in (('layout', '布局描述'), ('features', '功能说明'), ('content', '页面内容'), ('interaction', '交互说明'), ('description', '页面说明')):
                    text = str(matching.get(key) or '').strip()
                    if text:
                        parts.append(f'## {title}\n\n{text}')
                markdown = '\n\n'.join(parts)
            existing = next((doc for doc in bundle['prd']['documents'] if doc['pageId'] == page['id'] and doc['stateId'] == state['id']), None)
            if markdown.strip() and existing is None:
                identity = f"{page['id']}\n{state['id']}"
                bundle['prd']['documents'].append({'id': 'ai-doc-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16],
                    'pageId': page['id'], 'stateId': state['id'], 'markdown': markdown,
                    'confirmed': False, 'updatedAt': now_iso(), 'source': 'ai-import'})
        # 旧界面可能还有未匹配的 PRD。汇总到未占用的默认需求；原文件始终保留。
        unmatched = [(key, text) for key, text in old_docs.items() if key not in used_legacy and text.strip()]
        if unmatched and not any(doc['pageId'] == home['id'] and doc['stateId'] == 'default' for doc in bundle['prd']['documents']):
            bundle['prd']['documents'].append({'id': 'ai-legacy-docs', 'pageId': home['id'], 'stateId': 'default',
                'markdown': '\n\n'.join(f'## {key}\n\n{text}' for key, text in unmatched),
                'confirmed': False, 'updatedAt': now_iso(), 'source': 'ai-import'})
        if json.dumps(bundle, ensure_ascii=False, sort_keys=True) != before:
            bundle['revision'] += 1
            save_bundle(root, bundle)
        return bundle


# ---------- 文件发现与安全读取（移植自全流程 preview.py） ----------

def safe_asset(root: Path, relative: str) -> Path:
    parts = relative.replace('\\', '/').split('/')
    if not parts or any(not p or p.startswith('.') or ':' in p or p.casefold() in EXCLUDED or p != p.rstrip(' .') for p in parts):
        raise ValueError('预览路径不允许')
    target = root.joinpath(*parts).resolve()
    if root.resolve() not in target.parents or target.suffix.lower() not in ASSET_TYPES:
        raise ValueError('只能读取项目中的原型与静态资源')
    resolved_parts = target.relative_to(root.resolve()).parts
    if any(p.startswith('.') or p.casefold() in EXCLUDED for p in resolved_parts):
        raise ValueError('预览目标位于受保护目录')
    if not target.is_file():
        raise FileNotFoundError('原型文件不存在')
    return target


def is_directory_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def is_linked_path(path: Path) -> bool:
    return any(is_directory_link(p) for p in (path, *path.parents))


def discover_pages(root: Path, errors: list | None = None) -> list[dict]:
    def report(error):
        if errors is not None:
            errors.append({'root': str(getattr(error, 'filename', None) or root), 'error': str(error)})

    try:
        files = [p for p in root.iterdir() if p.suffix.lower() == '.html' and p.is_file() and not p.is_symlink()]
    except OSError as error:
        report(error)
        return []
    page_dir = root / 'pages'
    if page_dir.is_dir() and not is_directory_link(page_dir):
        for current, dirs, names in os.walk(page_dir, followlinks=False, onerror=report):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d.casefold() not in EXCLUDED
                             and not is_directory_link(Path(current) / d))
            files.extend(Path(current) / n for n in names if n.lower().endswith('.html'))
    result = []
    for file in sorted(files, key=lambda p: (p.name != 'index.html', p.as_posix())):
        rel = file.relative_to(root).as_posix()
        try:
            if file.is_symlink():
                continue
            safe_asset(root, rel)
            with file.open(encoding='utf-8', errors='replace') as stream:
                head = stream.read(32000)
            title = re.search(r'<title[^>]*>(.*?)</title>', head, re.I | re.S)
            result.append({'file': rel, 'url': file.as_uri(), 'title': title.group(1).strip() if title else file.stem})
        except ValueError:
            continue
        except OSError as error:
            report(error)
    return result


SCAN_SKIP = EXCLUDED | {'assets', 'backups', 'backup', 'venv', 'env', '原型生成器', '原型生成全流程'}
PICKER_LOCK = threading.Lock()


def skip_scan_directory(path: Path) -> bool:
    return (path.name.startswith('.') or path.name.casefold() in SCAN_SKIP
            or path.resolve() == Path(__file__).resolve().parent or is_directory_link(path))


def directory_created_at(root: Path, fallback: str = '') -> str:
    """读取目录创建时间；失效路径使用已有记录，不写入扫描目录。"""
    try:
        info = root.stat()
        created = getattr(info, 'st_birthtime', info.st_ctime)
        value = datetime.fromtimestamp(created, timezone.utc)
    except (OSError, ValueError, OverflowError):
        try:
            value = datetime.fromisoformat(fallback).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return ''
    return value.isoformat(timespec='microseconds')


def scan_roots(roots: list[str], registered: dict) -> tuple[list[dict], list[dict]]:
    """与全流程一致：根及直接子目录，只读发现，绝不初始化元数据。"""
    candidates, errors, seen = [], [], set()
    for text in roots:
        try:
            base = Path(text).expanduser()
            if is_linked_path(base):
                raise ValueError('不扫描符号链接或目录联接')
            base = base.resolve()
            if not base.is_dir():
                raise ValueError('目录不存在')
            if skip_scan_directory(base):
                raise ValueError('不扫描工具、依赖、交付或隐藏目录')
            children = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
            for folder in [base, *children]:
                if skip_scan_directory(folder):
                    continue
                pid = project_id_for(folder)
                if pid in seen or pid in registered:
                    continue
                seen.add(pid)
                try:
                    pages = discover_pages(folder, errors)
                    if pages:
                        candidates.append({'projectId': pid, 'root': str(folder), 'name': folder.name,
                                           'createdAt': directory_created_at(folder),
                                           'pages': len(pages), 'discovered': True, 'exists': True})
                except OSError as error:
                    errors.append({'root': str(folder), 'error': str(error)})
        except (OSError, ValueError) as error:
            errors.append({'root': text, 'error': str(error)})
    candidates.sort(key=lambda item: item['createdAt'], reverse=True)
    return candidates, errors


def pick_folder() -> str:
    """目录对话框在独立进程主线程运行；不占用服务进程的 GUI 线程。"""
    if not PICKER_LOCK.acquire(blocking=False):
        raise BlockingIOError('文件夹选择窗口已打开')
    try:
        if getattr(sys, 'frozen', False):
            raise RuntimeError('当前打包环境不支持目录选择，请粘贴路径')
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--pick-folder'],
                                capture_output=True, text=True, encoding='utf-8', timeout=180)
        if result.returncode:
            raise RuntimeError('无法打开系统文件夹选择器，请粘贴路径')
        return str(json.loads(result.stdout).get('path', ''))
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('选择窗口已超时关闭，请重试或粘贴路径') from error
    finally:
        PICKER_LOCK.release()


if __name__ == '__main__' and sys.argv[1:] == ['--pick-folder']:
    import tkinter as tk
    from tkinter import filedialog
    sys.stdout.reconfigure(encoding='utf-8')
    app = tk.Tk()
    app.withdraw()
    app.attributes('-topmost', True)
    try:
        selected = filedialog.askdirectory(parent=app, title='选择原型项目或项目集合文件夹', mustexist=True)
        print(json.dumps({'path': selected}, ensure_ascii=False))
    finally:
        app.destroy()
