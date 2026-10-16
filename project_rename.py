"""项目改名：同目录移动，保留工作台身份及 PRD，失败恢复原名和元数据。"""
from __future__ import annotations

import copy
import json
import re
import uuid
from pathlib import Path

import proto_meta


class RevisionConflict(ValueError):
    def __init__(self, current):
        super().__init__('项目已更新，请刷新后重试')
        self.current = current


def validate_name(value):
    if not isinstance(value, str):
        raise ValueError('请填写项目名称')
    name = value.strip()
    if not name or len(name) > 100 or name != name.rstrip(' .') or name.startswith('.'):
        raise ValueError('名称需为 1–100 个字符，不能以点开头或以点、空格结尾')
    if re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
        raise ValueError('名称包含本地文件夹不支持的字符或保留名称')
    return name


def rename(root, bundle, registry, pid, name, expected_revision, save_registry, *, projects_file=None, migrate_ai=None):
    name = validate_name(name)
    if type(expected_revision) is not int or expected_revision != bundle['revision']:
        raise RevisionConflict(bundle)
    source = Path(root)
    if proto_meta.is_linked_path(source):
        raise ValueError('不支持重命名符号链接或目录联接项目')
    source = source.resolve(strict=True)
    parent = source.parent.resolve(strict=True)
    destination = parent / name
    # 必须是原父目录的直属目录，移动前再次检查解析结果，禁止覆盖现有文件。
    if source == parent or destination.resolve().parent != parent or proto_meta.is_linked_path(destination):
        raise ValueError('项目目录必须在原父目录内重命名')
    same_path = destination.resolve() == source
    if destination.exists() and not same_path:
        raise ValueError('同目录下已有这个名称，请换一个名称')
    for key, item in registry['projects'].items():
        other = Path(item.get('root', '')).resolve()
        if key != pid and (other == source or source.is_relative_to(other) or other.is_relative_to(source)):
            raise ValueError('项目目录与另一个已连接项目重叠，请先调整连接关系')
    if proto_meta.skip_scan_directory(destination):
        raise ValueError('不能使用工具、依赖或交付目录的名称')
    if source.name == name and bundle['project']['name'] == name:
        return {'ok': True, 'bundle': bundle, 'root': str(source), 'name': name, 'projectId': pid}

    before = copy.deepcopy(registry)
    updated = copy.deepcopy(bundle)
    updated['project']['name'] = name
    updated['revision'] += 1
    for page in updated['project']['pages']:
        page['url'] = (destination / proto_meta.safe_relative(page['file'])).as_uri()
    item = registry['projects'][pid]
    ai_id = item.get('aiProjectId') if item.get('source') == 'ai' else None
    listing = None
    legacy_project = None
    record_path = source / 'record.json'
    record = None
    files = [source / '.prototype' / f for f in ('project.json', 'prd.json', 'changes.json')]
    if ai_id:
        if not projects_file or not migrate_ai:
            raise ValueError('AI 项目重命名服务不可用')
        listing = json.loads(projects_file.read_text(encoding='utf-8')) if projects_file.exists() else []
        if not isinstance(listing, list):
            raise ValueError('AI 项目列表格式无效')
        if any(p.get('id') == name and p.get('id') != ai_id for p in listing):
            raise ValueError('已有同名 AI 项目')
        legacy_project = next((p for p in listing if p.get('id') == ai_id), None)
        if legacy_project is None:
            legacy_project = {'id': ai_id}
            listing.append(legacy_project)
        legacy_project.update(id=name, name=name, url='/projects/' + name + '/index.html')
        updated['project']['aiProjectId'] = name
        if record_path.exists():
            record = json.loads(record_path.read_text(encoding='utf-8'))
            if not isinstance(record, dict):
                raise ValueError('AI 项目记录格式无效')
            record['projectName'] = name
            if record.get('projectId') == ai_id:
                record['projectId'] = name
            files.append(record_path)
    snapshots = {p.relative_to(source): p.read_bytes() if p.exists() else None for p in files}
    listing_snapshot = projects_file.read_bytes() if ai_id and projects_file.exists() else None
    item.update(root=str(destination), name=name)
    if ai_id:
        item.setdefault('github_remote_id', ai_id)
        item['aiProjectId'] = name
    registry['roots'] = [str(destination / Path(r).resolve().relative_to(source)) if Path(r).resolve().is_relative_to(source) else r for r in registry.get('roots', [])]
    # Windows 大小写改名需要经临时同级目录；每一步都不覆盖目标。
    intermediate = parent / ('.rename-' + uuid.uuid4().hex)
    moved = False
    migrated = False
    try:
        if source.name != name:
            if same_path:
                source.rename(intermediate)
                try:
                    intermediate.rename(destination)
                except Exception:
                    intermediate.rename(source)
                    raise
            else:
                source.rename(destination)
            moved = True
        proto_meta.save_bundle(destination, updated)
        if ai_id:
            if record is not None:
                _atomic_json(destination / 'record.json', record)
            _atomic_json(projects_file, listing)
            if ai_id != name:
                migrate_ai(ai_id, name)
                migrated = True
        save_registry(registry)
    except Exception:
        if migrated:
            migrate_ai(name, ai_id)
        if ai_id:
            _restore(projects_file, listing_snapshot)
        current = destination if moved else source
        for relative, content in snapshots.items():
            _restore(current / relative, content)
        marker = current / '.prototype' / '.pending-write.json'
        marker.unlink(missing_ok=True)
        if moved:
            if same_path:
                destination.rename(intermediate)
                intermediate.rename(source)
            else:
                destination.rename(source)
        registry.clear()
        registry.update(before)
        save_registry(before)
        raise
    return {'ok': True, 'projectId': pid, 'name': name, 'root': str(destination), 'bundle': updated,
            'viewerUrl': '/src/viewer.html?ext=' + pid, **({'project': legacy_project} if ai_id else {})}


def _atomic_json(path, data):
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _restore(path, content):
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(content)
