"""远端发布目录与容量估算；取消发布通过非强制分支更新一次提交完成。"""
from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
import re
import threading
import time
from urllib.parse import quote, urlsplit

import requests

LIMIT = 1_000_000_000
_CACHE, _LOCK, _EPOCH = {}, threading.RLock(), 0


class PagesError(ValueError):
    status = 502


class Conflict(PagesError):
    status = 409


def invalidate():
    global _EPOCH
    with _LOCK:
        _CACHE.clear(); _EPOCH += 1


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', value) or value in {'.', '..'}:
        raise ValueError('项目目录 ID 无效')
    return value


def _path(value):
    if not isinstance(value, str) or value.startswith('/') or '\\' in value or any(part in {'', '.', '..'} for part in value.split('/')):
        raise PagesError('远端文件路径无效，无法安全管理')
    return value


def _call(session, method, url, **kwargs):
    try:
        response = getattr(session, method)(url, timeout=20, **kwargs)
    except requests.RequestException as error:
        raise PagesError('无法连接 GitHub，请检查网络后重试') from error
    if response.status_code not in (200, 201):
        if method == 'patch' and response.status_code in (409, 422):
            raise Conflict('远端分支已变化或不允许更新，请刷新列表后重试')
        raise PagesError(f'GitHub 请求失败（HTTP {response.status_code}），请检查仓库权限及网络后重试')
    try: result = response.json()
    except ValueError as error: raise PagesError('GitHub 返回了无效数据') from error
    if not isinstance(result, dict): raise PagesError('GitHub 返回了无效数据')
    return result


def _tree(session, api, sha):
    initial = _call(session, 'get', api+'/git/trees/'+quote(sha, safe='')+'?recursive=1')
    if not initial.get('truncated'):
        rows = initial.get('tree')
        if not isinstance(rows, list): raise PagesError('无法读取远端文件清单')
        return rows
    rows, pending = [], [('', sha)]
    while pending:
        prefix, tree_sha = pending.pop()
        data = _call(session, 'get', api+'/git/trees/'+quote(tree_sha, safe=''))
        if data.get('truncated') or not isinstance(data.get('tree'), list):
            raise PagesError('远端文件清单不完整，暂时无法统计或清理')
        for item in data['tree']:
            path = prefix+_path(item.get('path'))
            row = {**item, 'path': path}; rows.append(row)
            if item.get('type') == 'tree': pending.append((path+'/', item['sha']))
        if len(rows) > 200_000: raise PagesError('远端文件较多，暂时无法完成完整统计')
    return rows


def read_catalog(session, owner, repo, *, cache_key='', refresh=False):
    if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,99}', owner): raise ValueError('GitHub 用户或组织名称无效')
    _id(repo)
    key = (owner.casefold(), repo.casefold(), hashlib.sha256(cache_key.encode()).hexdigest())
    with _LOCK:
        epoch = _EPOCH
        hit = _CACHE.get(key) if cache_key and not refresh else None
        if hit and time.monotonic()-hit[0] < 120: return copy.deepcopy(hit[1])
    api = f'https://api.github.com/repos/{owner}/{repo}'
    repository = _call(session, 'get', api)
    try: response = session.get(api+'/pages', timeout=20)
    except requests.RequestException as error: raise PagesError('无法读取 GitHub Pages 配置') from error
    if response.status_code == 404: pages = {}
    elif response.status_code == 200: pages = response.json()
    else: raise PagesError(f'无法读取 Pages 配置（HTTP {response.status_code}），请检查 Pages 读取权限')
    source = pages.get('source') or {}
    known_source = bool(source.get('branch')) and pages.get('build_type') != 'workflow'
    branch = source.get('branch') if known_source else repository.get('default_branch')
    if not isinstance(branch, str) or not branch or len(branch) > 255: raise PagesError('仓库没有可管理的发布分支')
    source_path = str(source.get('path') or '/').strip('/') if known_source else ''
    if source_path: _path(source_path)
    prefix = source_path+'/' if source_path else ''
    ref = _call(session, 'get', api+'/git/ref/heads/'+quote(branch, safe=''))
    head = ref['object']['sha']
    commit = _call(session, 'get', api+'/git/commits/'+quote(head, safe=''))
    root_tree = commit['tree']['sha']; entries = _tree(session, api, root_tree)
    for item in entries: _path(item.get('path'))
    files = [item for item in entries if item.get('type') in {'blob', 'commit'} and item['path'].startswith(prefix)]
    manifest_path = prefix+'projects/manifest.json'
    manifest_file = next((item for item in files if item['path'] == manifest_path), None)
    manifest = []
    if manifest_file:
        if manifest_file.get('size', 0) > 2*1024*1024: raise PagesError('远端发布清单过大，暂时无法安全更新')
        data = _call(session, 'get', api+'/git/blobs/'+quote(manifest_file['sha'], safe=''))
        try:
            raw = base64.b64decode(data['content'], validate=False)
            if len(raw) > 2*1024*1024: raise ValueError('too large')
            manifest = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(manifest, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in manifest): raise ValueError('invalid manifest')
        except (ValueError, KeyError, UnicodeError) as error:
            raise PagesError('远端发布清单格式错误，请检查仓库；不会覆盖原清单') from error
    meta = {row['id']: row for row in manifest}
    grouped = {}
    project_prefix = prefix+'projects/'
    for item in files:
        path = item['path'][len(project_prefix):] if item['path'].startswith(project_prefix) else ''
        if '/' in path: grouped.setdefault(path.split('/')[0], []).append(item)
    for project_id in meta: grouped.setdefault(project_id, [])
    pages_url = pages.get('html_url', '')
    if not isinstance(pages_url, str) or urlsplit(pages_url).scheme not in {'http', 'https'}: pages_url = ''
    projects = []
    for project_id, assets in grouped.items():
        row = meta.get(project_id, {})
        valid = bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', project_id))
        sizes_known = all(type(item.get('size')) is int and item['size'] >= 0 for item in assets)
        projects.append({'id':project_id, 'name':str(row.get('name') or project_id), 'mode':str(row.get('mode') or ''),
                         'publishedAt':str(row.get('publishedAt') or ''), 'listed':project_id in meta, 'hasFiles':bool(assets),
                         'bytes':sum(item['size'] for item in assets) if sizes_known else None, 'canUnpublish':valid,
                         'url':pages_url.rstrip('/')+'/projects/'+quote(project_id,safe='')+'/' if pages_url else '',
                         'directoryUrl':f'https://github.com/{owner}/{repo}/tree/{quote(branch,safe="")}/{quote(project_prefix+project_id,safe="/")}'})
    reason = ''
    if not known_source: reason = '当前使用 Actions 构建或尚未启用 Pages，无法可靠估算最终站点大小。'
    elif not all(type(item.get('size')) is int and item['size'] >= 0 for item in files): reason = '部分文件大小不可用，暂时无法完整统计。'
    used = sum(item['size'] for item in files) if not reason else None
    public = {'ok':True, 'repository':owner+'/'+repo, 'repositoryUrl':f'https://github.com/{owner}/{repo}',
              'branch':branch, 'sourcePath':'/'+source_path, 'head':head, 'pagesUrl':pages_url,
              'overviewUrl':pages_url.rstrip('/')+'/projects/' if pages_url else '',
              'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'projects':projects,
              'usage':{'estimated':True,'limitBytes':LIMIT,'usedBytes':used,'remainingBytes':max(0,LIMIT-used) if used is not None else None,'reason':reason}}
    result = {'public':public,'files':files,'manifest':manifest,'prefix':prefix,'tree':root_tree,'api':api}
    with _LOCK:
        if cache_key and epoch == _EPOCH: _CACHE[key] = (time.monotonic(), copy.deepcopy(result))
    return result


def unpublish(session, owner, repo, project_id, expected_head, render_index, *, expected_url=''):
    _id(project_id)
    current = read_catalog(session, owner, repo)
    public = current['public']
    if expected_url:
        allowed = {f'https://{owner}.github.io/{repo}/projects/{project_id}'}
        if public['pagesUrl']: allowed.add(public['pagesUrl'].rstrip('/')+'/projects/'+project_id)
        if expected_url.rstrip('/') not in allowed:
            raise Conflict('原发布地址与当前 GitHub 仓库不一致，请核对配置后重试')
    if expected_head is not None and expected_head != public['head']:
        raise Conflict('远端内容已变化，请刷新列表后重新确认')
    folder = current['prefix']+'projects/'+project_id+'/'
    assets = [item for item in current['files'] if item['path'].startswith(folder)]
    manifest = [row for row in current['manifest'] if row['id'] != project_id]
    if not assets and len(manifest) == len(current['manifest']):
        return {'ok':True,'alreadyAbsent':True,'overview':public}
    changes = [{'path':item['path'],'mode':item['mode'],'type':item['type'],'sha':None} for item in assets]
    # 清单和总览与项目目录变更进入同一棵树，同一次非强制分支更新生效。
    changes += [{'path':current['prefix']+'projects/manifest.json','mode':'100644','type':'blob','content':json.dumps(manifest,ensure_ascii=False,indent=2)},
                {'path':current['prefix']+'projects/index.html','mode':'100644','type':'blob','content':render_index(manifest,owner,repo)}]
    api = current['api']
    tree = _call(session,'post',api+'/git/trees',json={'base_tree':current['tree'],'tree':changes})
    commit = _call(session,'post',api+'/git/commits',json={'message':'Unpublish prototype: '+project_id,'tree':tree['sha'],'parents':[public['head']]})
    _call(session,'patch',api+'/git/refs/heads/'+quote(public['branch'],safe=''),json={'sha':commit['sha'],'force':False})
    invalidate()
    after = read_catalog(session,owner,repo)['public']
    if any(row['id'] == project_id for row in after['projects']):
        raise Conflict('远端仍有该项目或已重新发布，请刷新后检查；本地发布记录已保留')
    return {'ok':True,'overview':after}
