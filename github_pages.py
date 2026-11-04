"""远端发布目录与容量估算；取消发布通过非强制分支更新一次提交完成。"""
from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
from pathlib import Path
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


def repository_tree(session, owner, repo, branch):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,99}',str(owner)): raise ValueError('GitHub 用户无效')
    _id(repo)
    if not isinstance(branch,str) or not branch or len(branch)>255: raise ValueError('发布分支无效')
    api=f'https://api.github.com/repos/{owner}/{repo}'
    ref=_call(session,'get',api+'/git/ref/heads/'+quote(branch,safe=''))
    head=ref['object']['sha']
    commit=_call(session,'get',api+'/git/commits/'+quote(head,safe=''))
    tree=commit['tree']['sha']; rows=_tree(session,api,tree)
    for row in rows: _path(row.get('path'))
    return {'api':api,'head':head,'tree':tree,'files':rows,'branch':branch}


def read_file(session,current,path,max_bytes=8*1024*1024):
    _path(path)
    row=next((r for r in current['files'] if r.get('path')==path and r.get('type')=='blob'),None)
    if not row: return None
    if row.get('size',0)>max_bytes: raise PagesError('发布版本数据过大，不能安全读取')
    data=_call(session,'get',current['api']+'/git/blobs/'+quote(row['sha'],safe=''))
    try: raw=base64.b64decode(data['content'])
    except (ValueError,KeyError) as error: raise PagesError('发布版本数据无效') from error
    if len(raw)>max_bytes: raise PagesError('发布版本数据过大')
    return raw


def publish_directory(session, owner, repo, branch, directory, remote_prefix):
    """所有文件与发布清单同一 commit；仅清理发布器登记的本项目文件。"""
    import publication_versions as V
    remote_prefix=_path(remote_prefix).rstrip('/')+'/'
    if not re.fullmatch(r'projects/[A-Za-z0-9][A-Za-z0-9_.-]{0,199}/',remote_prefix): raise ValueError('发布目录无效')
    current=repository_tree(session,owner,repo,branch)
    previous_raw=read_file(session,current,remote_prefix+V.MANIFEST)
    try: previous=json.loads(previous_raw) if previous_raw else {}
    except ValueError: raise PagesError('远端版本清单损坏，未覆盖原发布')
    if not isinstance(previous,dict): raise PagesError('远端版本清单无效')
    folder=Path(directory).resolve(); local={}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink(): raise ValueError('发布产物不能含链接')
        if path.is_file(): local[path.relative_to(folder).as_posix()]=path.read_bytes()
    if not local: raise ValueError('没有可发布文件')
    manifest=json.loads(local[V.MANIFEST]) if V.MANIFEST in local else None
    retained=set()
    if manifest is not None:
        if manifest.get('baseReleaseId','')!=previous.get('releaseId',''):
            raise Conflict('该项目已有另一版本发布，请重新生成更新说明后重试')
        bases=[manifest.get('prototypeBase','')]
        if manifest.get('mode')=='review':
            old_base=previous.get('prototypeBase') or ('proto/' if any(r['path'].startswith(remote_prefix+'proto/') for r in current['files']) else '')
            if old_base and old_base!=bases[0]: bases.append(old_base)
        bases=[p for p in bases if p and (p=='proto/' or re.fullmatch(r'prototype-versions/[a-f0-9]{24}/',p))]
        history=previous.get('history',[])
        history=[h for h in history if isinstance(h,dict) and re.fullmatch(r'rel-[a-f0-9]{16}',str(h.get('releaseId','')))]
        if manifest.get('contentVersion')!=previous.get('contentVersion'):
            history=[{k:manifest[k] for k in ('releaseId','sequence','contentVersion','publishedAt','changesUrl','summary','mode') if k in manifest},*history][:V.LIMIT]
        if manifest.get('mode')!='review': history=[]
        keep_notes={h.get('changesUrl','') for h in history}
        keep_notes|={p.replace('.json','.snapshot.json') for p in keep_notes if p.endswith('.json')}
        for row in current['files']:
            path=row['path']
            if row.get('type')!='blob' or not path.startswith(remote_prefix): continue
            rel=path[len(remote_prefix):]
            if any(rel.startswith(base) for base in bases) or rel in keep_notes: retained.add(rel)
        manifest['history']=history
        manifest['managedFiles']=sorted(set(local)|retained)
        local[V.MANIFEST]=json.dumps(manifest,ensure_ascii=False,separators=(',',':')).encode()
    owned=previous.get('managedFiles',[])
    if not isinstance(owned,list): raise PagesError('远端文件归属清单无效')
    remote={r['path']:r for r in current['files'] if r.get('type')=='blob'}
    changes=[]
    for rel,raw in local.items():
        _path(rel); path=remote_prefix+rel
        sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if path in remote and remote[path].get('sha')==sha: continue
        created=_call(session,'post',current['api']+'/git/blobs',json={'content':base64.b64encode(raw).decode(),'encoding':'base64'})
        changes.append({'path':path,'mode':'100644','type':'blob','sha':created['sha']})
    for rel in owned:
        _path(rel)
        if rel not in local and rel not in retained and remote_prefix+rel in remote:
            changes.append({'path':remote_prefix+rel,'mode':'100644','type':'blob','sha':None})
    if not changes: return {'head':current['head'],'release':manifest}
    tree=_call(session,'post',current['api']+'/git/trees',json={'base_tree':current['tree'],'tree':changes})
    commit=_call(session,'post',current['api']+'/git/commits',json={'message':'Publish prototype: '+remote_prefix.split('/')[-2],
        'tree':tree['sha'],'parents':[current['head']]})
    _call(session,'patch',current['api']+'/git/refs/heads/'+quote(branch,safe=''),json={'sha':commit['sha'],'force':False})
    invalidate()
    return {'head':commit['sha'],'release':manifest}
