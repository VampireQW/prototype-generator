"""页面回收站：软删除保留文件与关联数据，永久删除只移除该页 HTML。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from pathlib import Path

import proto_meta
import prototype_manifest


PENDING = 'page-operation.pending.json'


class RevisionConflict(ValueError):
    def __init__(self, current):
        super().__init__('项目已更新，请刷新后重试')
        self.current = current


def active_pages(project):
    return [p for p in project.get('pages', []) if not p.get('trashedAt')]


def _regular_path(root, relative):
    path = root / proto_meta.safe_relative(relative)
    if not path.resolve().is_relative_to(root):
        raise ValueError('页面路径必须位于项目目录内')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('不能删除或恢复链接路径中的页面')
    if path.suffix.casefold() not in ('.html', '.htm') or (path.exists() and not path.is_file()):
        raise ValueError('只能操作本项目的 HTML 页面文件')
    return path


def change_page(root, page_id, action, expected_revision, confirm_file=None):
    root = Path(root).resolve()
    if action not in ('trash', 'restore', 'delete'):
        raise ValueError('页面操作只支持 trash / restore / delete')
    if type(expected_revision) is not int:
        raise ValueError('缺少有效 expectedRevision')
    with proto_meta.PROJECT_LOCK:
        before = proto_meta.load_bundle(root)
        if before['revision'] != expected_revision:
            raise RevisionConflict(before)
        bundle = copy.deepcopy(before)
        project = bundle['project']
        page = next((p for p in project['pages'] if p['id'] == page_id), None)
        if page is None:
            raise ValueError('页面不存在，可能已被彻底删除')
        path = _regular_path(root, page['file'])
        if action == 'trash':
            if page.get('trashedAt'):
                raise ValueError('页面已在回收站中')
            page['trashedAt'] = proto_meta.now_iso()
        elif action == 'restore':
            if not page.get('trashedAt'):
                raise ValueError('页面不在回收站中')
            if not path.is_file():
                raise ValueError('本地页面文件已不存在，无法恢复')
            page.pop('trashedAt', None)
        else:
            if not page.get('trashedAt'):
                raise ValueError('请先将页面移入回收站，再彻底删除')
            if confirm_file != page['file']:
                raise ValueError('请确认要永久删除的本地页面文件名')
            if any(p['id'] != page_id and p['file'].casefold() == page['file'].casefold() for p in project['pages']):
                raise ValueError('该文件仍被其他页面登记使用，不能删除')
            project['pages'] = [p for p in project['pages'] if p['id'] != page_id]
            for child in project['pages']:
                if child.get('parentId') == page_id:
                    if page.get('parentId'):
                        child['parentId'] = page['parentId']
                    else:
                        child.pop('parentId', None)
            for key in ('documents', 'annotations', 'deletedAnnotations'):
                if key in bundle['prd']:
                    bundle['prd'][key] = [item for item in bundle['prd'][key] if item.get('pageId') != page_id]
            bundle['changes']['items'] = [item for item in bundle['changes']['items'] if item.get('pageId') != page_id]
        available = active_pages(project)
        if not any(p['id'] == project.get('defaultPage') and p.get('role') != 'launcher' for p in available):
            project['defaultPage'] = next((p['id'] for p in available if p.get('role') != 'launcher'), '')
        bundle['revision'] += 1
        proto_meta.validate_bundle(bundle)
        if action != 'delete':
            proto_meta.save_bundle(root, bundle)
            return bundle

        manifest_path = root / prototype_manifest.MANIFEST_NAME
        manifest_before = None
        manifest_after = None
        if manifest_path.exists():
            if manifest_path.is_symlink():
                raise ValueError('页面清单不能是链接')
            manifest_before = manifest_path.read_bytes()
            declaration = prototype_manifest.load_manifest(root, missing_files=[page['file']])
            deleted_declaration = next((p for p in declaration['pages'] if p['file'].casefold() == page['file'].casefold()), {})
            declaration['pages'] = [p for p in declaration['pages'] if p['file'].casefold() != page['file'].casefold()]
            for child in declaration['pages']:
                if child.get('parentFile', '').replace('\\', '/').casefold() == page['file'].casefold():
                    child['parentFile'] = deleted_declaration.get('parentFile', '')
            if declaration.get('defaultPage', '').casefold() == page['file'].casefold():
                declaration.pop('defaultPage', None)
                replacement = next((p['file'] for p in available if p.get('role') != 'launcher'), '')
                if replacement:
                    declaration['defaultPage'] = replacement
            if not any(p.get('role', 'page') == 'page' for p in declaration['pages']):
                declaration['allowEmpty'] = True
            manifest_after = declaration
            project['navigationManifestHash'] = hashlib.sha256(json.dumps(declaration, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

        folder = proto_meta.meta_dir(root)
        if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
            raise ValueError('元数据目录不能是链接')
        pending = folder / PENDING
        staged = folder / ('page-delete-' + uuid.uuid4().hex + '.html')
        import screenshot_pages
        import html_import
        owned = []
        for relative in screenshot_pages.owned_images(page) + html_import.owned_assets(page):
            if any(p['id'] != page_id and p.get('screenshot', {}).get('image') == relative for p in before['project']['pages']):
                raise ValueError('截图资源仍被其他页面使用，不能删除')
            asset = screenshot_pages.safe_path(root, relative)
            if asset.is_file():
                owned.append((asset, folder / ('page-delete-' + uuid.uuid4().hex + asset.suffix)))
        proto_meta.write_json_atomic(pending, {'before': before, 'after': bundle, 'file': page['file'], 'staged': staged.name,
                                             'assets': [{'file':a.relative_to(root).as_posix(), 'staged':b.name} for a,b in owned],
                                             'manifestBefore': manifest_before.decode('utf-8-sig') if manifest_before else None})
        moved = False
        moved_assets = []
        try:
            if path.exists():
                os.replace(path, staged)
                moved = True
            for asset, backup in owned:
                os.replace(asset, backup)
                moved_assets.append((asset, backup))
            if manifest_after is not None:
                proto_meta.write_json_atomic(manifest_path, manifest_after)
            proto_meta.save_bundle(root, bundle)
        except Exception:
            if manifest_before is not None:
                manifest_path.write_bytes(manifest_before)
            proto_meta.save_bundle(root, before)
            if moved and staged.exists():
                os.replace(staged, path)
            for asset, backup in moved_assets:
                if backup.exists(): os.replace(backup, asset)
            pending.unlink()
            raise
        # 提交后临时文件清理失败不能回滚到已删除的备份。
        for backup in ([staged] if moved else []) + [b for _,b in moved_assets]:
            try: backup.unlink(missing_ok=True)
            except OSError: pass
        pending.unlink()
        return bundle
