"""独立发布快照、事实差异与说明草稿。不会改写项目 PRD。"""
from __future__ import annotations

import copy
import difflib
import gzip
import hashlib
from html.parser import HTMLParser
import json
import os
import posixpath
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import uuid

import proto_meta

SCHEMA = 1
MANIFEST = 'prototype-release.json'
NOTES_DIR = 'prototype-changes'
VERSIONS_DIR = 'prototype-versions'
LIMIT = 10
IGNORED = {'.prototype','.git','node_modules','__pycache__','exports','dist','backups','agent-skills'}
PRIVATE = {'config.json','models.json','record.json','prompt.full.md','task.md','agents.md','design.md'}
VOLATILE = {'revision','updatedAt','createdAt','publishedAt','addedAt','url','navigationManifestHash'}
KINDS = {'.css':'style','.js':'logic','.mjs':'logic','.json':'resource'}
ASSETS = {'.png','.jpg','.jpeg','.gif','.webp','.svg','.ico','.avif','.woff','.woff2','.ttf','.mp4','.webm','.pdf'}
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
TEXT_TAGS = {'button','a','label','th','td','h1','h2','h3','h4','h5','h6','p','span','div','li','option','input','textarea'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def blob_hash(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items() if k not in VOLATILE}
    if isinstance(value,list):
        return [clean(v) for v in value]
    return value


def _short(value, limit=180):
    text = re.sub(r'\s+',' ',str(value or '')).strip()
    return text if len(text) <= limit else text[:limit]+'…'


def changed_text(old,new,limit=70):
    """跳过未变化的正文，说明只引用实际变化的行。"""
    a=str(old or '').splitlines();b=str(new or '').splitlines();left=[];right=[]
    for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if op!='equal': left.extend(a[i:j]);right.extend(b[k:l])
    return _short(' '.join(left),limit),_short(' '.join(right),limit)


def text_description(label,old,new):
    a,b=changed_text(old,new)
    return label+'：'+('“'+a+'” → “'+b+'”' if a and b else '新增“'+b+'”' if b else '移除“'+a+'”')


class Content(HTMLParser):
    """只记录展示文字、相对资源及业务脚本 hash，过滤评审注入。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]; self.nodes={}; self.structure=[]; self.scripts=[]; self.styles=[]; self.refs=[]; self.text_rules=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); parent=self.stack[-1] if self.stack else None
        counts=parent['counts'] if parent else {}
        counts[tag]=counts.get(tag,0)+1
        selector=(parent['selector']+' > ' if parent else '')+tag+':nth-of-type('+str(counts[tag])+')'
        stable=False
        if attrs.get('data-proto-id'):
            selector='[data-proto-id='+json.dumps(attrs['data-proto-id'],ensure_ascii=False)+']'; stable=True
        elif attrs.get('id'):
            selector='[id='+json.dumps(attrs['id'],ensure_ascii=False)+']'; stable=True
        scope=attrs.get('data-proto-page') or (parent or {}).get('scope','')
        condition=attrs.get('v-if','')+' '+attrs.get('v-show','')
        found=re.search(r'currentPage\s*={2,3}\s*[\'\"]([^\'\"]+)',condition)
        if found: scope=found.group(1)
        owned=bool((parent or {}).get('owned')) or any(k in attrs for k in ('data-proto-review','data-prototype-owned','data-proto-hotspot-bootstrap'))
        owned=owned or (tag=='script' and 'data-proto-text-runtime' in attrs)
        node={'tag':tag,'attrs':attrs,'selector':selector,'stable':stable,'scope':scope,
              'state':attrs.get('data-proto-state') or (parent or {}).get('state',''),'text':[],'counts':{},'children':False,'owned':owned}
        if parent: parent['children']=True
        if not owned:
            safe={k:v for k,v in attrs.items() if k not in {'nonce','integrity'} and not k.startswith('data-proto-review')}
            if tag=='input' and attrs.get('type') in {'password','hidden'}: safe.pop('value',None)
            if tag not in {'script','style','meta','link'}: self.structure.append([tag,safe])
            for key in ('src','href','poster'):
                if attrs.get(key): self.refs.append(attrs[key])
        self.stack.append(node)
        if tag in VOID: self.handle_endtag(tag)

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID: self.handle_endtag(tag)

    def handle_data(self,data):
        if self.stack: self.stack[-1]['text'].append(data)

    def handle_endtag(self,tag):
        index=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i]['tag']==tag),None)
        if index is None: return
        while len(self.stack)>index:
            node=self.stack.pop(); text=''.join(node['text']); tag=node['tag']; attrs=node['attrs']
            if self.stack and tag not in {'script','style'}: self.stack[-1]['text'].append(text)
            if node['owned']: continue
            if tag=='script':
                if attrs.get('id')=='proto-text-edits-data':
                    try: self.text_rules=json.loads(text)
                    except ValueError: pass
                else: self.scripts.append([attrs.get('src',''),text.strip()])
                continue
            if tag=='style': self.styles.append(text.strip()); continue
            if tag=='title': self.structure.append(['title',text.strip()]);continue
            if tag not in TEXT_TAGS and (node['children'] or tag in {'head','html','body','meta','link','noscript','template'}): continue
            if any(n['tag'] in TEXT_TAGS-{'div','span','li','input','textarea','option'} for n in self.stack): continue
            if tag in {'div','span','li'} and node['children']: continue
            text=_short(attrs.get('placeholder') or attrs.get('aria-label') or text,800)
            if tag=='input' and attrs.get('type') in {'password','hidden'}: continue
            if not text: continue
            key='proto:'+attrs['data-proto-id'] if attrs.get('data-proto-id') else 'id:'+attrs['id'] if attrs.get('id') else node['selector']
            anchor={'selector':node['selector'],'tag':tag}
            if attrs.get('data-proto-id'): anchor['protoId']=attrs['data-proto-id']
            if len(text)<150: anchor['text']=text
            self.nodes[key]={'text':text,'anchor':anchor,'scope':node['scope'],'state':node['state'],'stable':node['stable']}

    def result(self):
        while self.stack: self.handle_endtag(self.stack[-1]['tag'])
        return {'nodes':self.nodes,'logicHash':digest(self.scripts),'styleHash':digest(self.styles),
                'structureHash':digest(self.structure),'refs':self.refs,'textRules':self.text_rules}


def html_content(text):
    parser=Content(); parser.feed(text); return parser.result()


def source_files(root):
    root=Path(root).resolve()
    if proto_meta.is_linked_path(root): raise ValueError('不能读取链接目录中的发布快照')
    paths=[]
    for folder,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[n for n in dirs if not n.startswith('.') and n not in IGNORED and not proto_meta.is_linked_path(Path(folder)/n)]
        paths.extend(Path(folder)/name for name in names)
    for path in sorted(paths):
        rel=path.relative_to(root)
        if any(part.startswith('.') or part in IGNORED for part in rel.parts): continue
        if rel.parts[0].casefold() in PRIVATE: continue
        if rel.as_posix() in {MANIFEST,'prototype.manifest.json'} or rel.parts[0] in {NOTES_DIR,VERSIONS_DIR}: continue
        if path.suffix.lower() not in {'.html','.htm',*KINDS,*ASSETS}: continue
        if proto_meta.is_linked_path(path) or not path.is_file(): continue
        if path.stat().st_size > 25*1024*1024: continue
        yield rel.as_posix(),path


def runtime_version():
    base=Path(__file__).parent
    names=['review_shell.html','proto-anchors.js','proto-order.js','proto-navigation.js','review-bridge.js','review-pins.js',
           'proto-hotspots.js','proto-appearance.js','publication-updates.js','publication-updates.css','change-locator.js']
    return digest({name:hashlib.sha256((base/'src'/name).read_bytes()).hexdigest() for name in names if (base/'src'/name).is_file()})


def capture(root,bundle,mode='review'):
    for name in (MANIFEST,NOTES_DIR,VERSIONS_DIR):
        if (Path(root)/name).exists(): raise ValueError('项目文件与发布保留名称冲突：'+name+'，请先改名后再发布')
    pages=[clean(p) for p in proto_meta.navigation_pages(bundle['project'].get('pages',[]))]
    # 显示序号由运行时计算；不作为版本变化依据。
    notes=[clean({k:v for k,v in n.items() if k not in {'number','confirmed'}}) for n in bundle.get('prd',{}).get('annotations',[]) if n.get('pageId') in {p['id'] for p in pages}]
    docs=[clean({k:v for k,v in d.items() if k!='confirmed'}) for d in bundle.get('prd',{}).get('documents',[]) if d.get('pageId') in {p['id'] for p in pages}]
    files={}
    import screenshot_pages, html_import
    excluded={p['file'] for p in bundle['project'].get('pages',[]) if p.get('trashedAt')}
    excluded.update(screenshot_pages.trashed_assets(bundle)); excluded.update(html_import.trashed_assets(bundle))
    for rel,path in source_files(root):
        if rel in excluded or (bundle['project'].get('source')=='ai' and rel.split('/')[0].casefold()=='prd'): continue
        raw=path.read_bytes(); kind=KINDS.get(path.suffix.lower(),'asset')
        row={'hash':blob_hash(raw),'bytes':len(raw),'kind':kind}
        if path.suffix.lower() in {'.html','.htm'}:
            try:
                row.update(html_content(raw.decode('utf-8-sig'))); row['kind']='html'
                row['hash']=digest({k:v for k,v in row.items() if k not in {'hash','bytes','refs'}})
            except (UnicodeError,ValueError): row['kind']='content'
        elif path.suffix.lower()=='.css':
            try: row['refs']=re.findall(r'(?:url\(|@import\s+)[\s\'\"]*([^\s\)\'\";]+)',raw.decode('utf-8-sig'))
            except UnicodeError: pass
        files[rel]=row
    snap={'schemaVersion':SCHEMA,'projectId':bundle['project']['id'],'name':bundle['project'].get('name','原型项目'),
          'mode':mode,'pages':pages,'navigation':clean({k:bundle['project'][k] for k in ('previewType','clients','defaultPage') if k in bundle['project']}),'documents':sorted(docs,key=lambda d:d.get('id','')),
          'annotations':sorted(notes,key=lambda n:n['id']),'files':files,'runtime':runtime_version() if mode=='review' else '',
          **({'pinStyle':clean(bundle['project']['pinStyle'])} if mode=='review' and 'pinStyle' in bundle['project'] else {})}
    snap['contentVersion']=digest(snap)
    return snap


def _owners(snapshot):
    files=snapshot.get('files',{}); owners={name:set() for name in files}
    def visit(name,pid,seen):
        if name not in files or name in seen: return
        seen.add(name); owners[name].add(pid)
        for ref in files[name].get('refs',[]):
            parsed=urlsplit(ref)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'): continue
            child=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(parsed.path)))
            if not child.startswith('../'): visit(child,pid,seen)
    for page in snapshot.get('pages',[]): visit(page.get('file',''),page['id'],set())
    for item in snapshot.get('documents',[])+snapshot.get('annotations',[]):
        for ref in re.findall(r'!\[[^\]]*\]\(([^\s\)]+)',item.get('markdown',item.get('body',''))):
            if ref in owners: owners[ref].add(item.get('pageId',''))
    for page in snapshot.get('pages',[]):
        def refs(value):
            if isinstance(value,str) and value in owners: owners[value].add(page['id'])
            elif isinstance(value,dict):
                for v in value.values(): refs(v)
            elif isinstance(value,list):
                for v in value: refs(v)
        refs(page)
    return owners


def compare(before,after):
    pages={p['id']:p for p in after.get('pages',[])}
    old_pages={p['id']:p for p in (before or {}).get('pages',[])}
    rows=[]
    def add(kind,description,pid='',state='default',old='',new='',anchor=None,note_id=None,deleted=False,affected=None,doc_id=None):
        page=pages.get(pid) or old_pages.get(pid) or {}
        target={'pageId':pid,'stateId':state or 'default'}
        if anchor: target['anchor']=anchor
        if note_id: target['noteId']=note_id
        if doc_id: target['documentId']=doc_id
        if deleted: target['deleted']=True
        row={'kind':kind,'description':description,'pageTitle':'公共资源' if affected and len(affected)>1 else page.get('title') or ('公共资源' if not pid else pid),
             'stateTitle':next((s.get('title',s['id']) for s in page.get('states',[]) if s['id']==state),state or '默认'),
             'target':target,'before':_short(old,800),'after':_short(new,800),'affectedPages':sorted(affected or ([pid] if pid else []))}
        row['affectedPageTitles']=[(pages.get(p) or old_pages.get(p) or {}).get('title',p) for p in row['affectedPages']]
        row['id']='change-'+digest({k:v for k,v in row.items() if k!='description'})[:20]
        rows.append(row)
    for pid,page in pages.items():
        if pid not in old_pages: add('page-added','新增页面：'+page['title'],pid)
        elif page!=old_pages[pid]:
            old=old_pages[pid]
            if page.get('title')!=old.get('title'): add('page','页面名称调整',pid,old=old.get('title'),new=page.get('title'))
            if {k:v for k,v in page.items() if k!='title'}!={k:v for k,v in old.items() if k!='title'}:
                add('page','页面结构、状态或交互配置更新',pid)
    for pid,page in old_pages.items():
        if pid not in pages: add('page-removed','删除页面：'+page.get('title',pid),pid,deleted=True,old=page.get('title'))
    if before is None: return rows
    if before.get('name')!=after.get('name'):
        add('page','项目名称调整',next(iter(pages),''),old=before.get('name'),new=after.get('name'))
    if 'navigation' in before and before.get('navigation')!=after.get('navigation'):
        add('page','导航分组或默认预览设置更新',next(iter(pages),''))
    if before.get('pinStyle',{}) != after.get('pinStyle',{}):
        add('page','页面标注序号颜色或大小调整',next(iter(pages),''),affected=set(pages))
    for key,kind,field,label in [('annotations','annotation','body','标注'),('documents','document','markdown','页面需求')]:
        old={n['id']:n for n in before.get(key,[])}; new={n['id']:n for n in after.get(key,[])}
        for nid in sorted(set(old)|set(new)):
            a=old.get(nid); b=new.get(nid); n=b or a
            if n['pageId'] not in pages or n['pageId'] not in old_pages: continue
            if a==b: continue
            if kind=='annotation' and a and b and a.get('title','') != b.get('title',''):
                add('annotation','标注标题更新',n['pageId'],n.get('stateId'),old=a.get('title',''),new=b.get('title',''),note_id=nid)
            if a and b and a.get(field)==b.get(field):
                if kind=='annotation' and {k:v for k,v in a.items() if k!='title'} != {k:v for k,v in b.items() if k!='title'}: add('annotation-position','标注位置或展开入口调整',n['pageId'],n.get('stateId'),note_id=nid)
                continue
            action='新增' if not a else '删除' if not b else '更新'
            old_text=(a or {}).get(field,'');new_text=(b or {}).get(field,'')
            old_excerpt,new_excerpt=changed_text(old_text,new_text,800)
            add(kind,text_description(label+'内容'+action,old_text,new_text),n['pageId'],n.get('stateId'),old=old_excerpt,new=new_excerpt,
                note_id=nid if kind=='annotation' else None,doc_id=nid if kind=='document' else None,deleted=not b)
    owners=_owners(after); old_owners=_owners(before)
    for name in sorted(set(before.get('files',{}))|set(after.get('files',{}))):
        a=before.get('files',{}).get(name); b=after.get('files',{}).get(name)
        if a and b and a['hash']==b['hash']: continue
        affected=(owners.get(name,set())|old_owners.get(name,set())) & set(pages) & set(old_pages)
        if not affected:
            # 未能静态归属的运行资源只列一条共享变化。
            if (b or a).get('kind')=='html': continue
            affected=set(pages)&set(old_pages)
        pid=next(iter(sorted(affected)),'')
        if not pid: continue
        kind=(b or a).get('kind','resource')
        if kind=='html' and a and b:
            an=a.get('nodes',{}); bn=b.get('nodes',{}); count=len(rows)
            for key in sorted(set(an)|set(bn)):
                na=an.get(key); nb=bn.get(key); node=nb or na
                if na and nb and na['text']==nb['text']: continue
                scope=node.get('scope'); target_pid=scope if scope in affected else pid
                state=node.get('state') or 'default'
                if state not in {s['id'] for s in pages.get(target_pid,{}).get('states',[])}:state='default'
                if len(affected)>1 and scope not in affected: continue
                if not na or not nb:
                    if not node.get('stable'): continue
                    add('element-added' if nb else 'element-removed','新增页面内容' if nb else '移除页面内容',target_pid,state,
                        old=(na or {}).get('text',''),new=(nb or {}).get('text',''),anchor=node['anchor'],deleted=not nb)
                else: add('text',text_description('文案',na['text'],nb['text']),target_pid,state,old=na['text'],new=nb['text'],anchor=node['anchor'])
            ar={canonical(r['binding']):r for r in a.get('textRules',[]) if isinstance(r,dict) and isinstance(r.get('binding'),dict)}
            br={canonical(r['binding']):r for r in b.get('textRules',[]) if isinstance(r,dict) and isinstance(r.get('binding'),dict)}
            for key in sorted(set(ar)|set(br)):
                ra=ar.get(key); rb=br.get(key)
                old=(ra or rb).get('after' if ra else 'before',[])
                new=(rb or ra).get('after' if rb else 'before',[])
                if old!=new:
                    add('text',text_description('文案',' / '.join(old),' / '.join(new)),pid,old=' / '.join(old),new=' / '.join(new),
                        anchor={'textRule':key},affected=affected)
            if a.get('logicHash')!=b.get('logicHash'):
                add('logic','页面交互代码或动态文案有更新，请核对',pid,affected=affected)
            if a.get('styleHash')!=b.get('styleHash'):
                add('style','页面样式更新',pid,affected=affected)
            if a.get('structureHash')!=b.get('structureHash') and len(rows)==count:
                add('layout','页面结构或样式属性更新',pid,affected=affected)
        else:
            label={'style':'样式资源','logic':'交互资源','asset':'图片或媒体资源','resource':'页面资源'}.get(kind,'页面内容')
            add(kind,label+('新增：' if not a else '移除：' if not b else '更新：')+name,pid,affected=affected,deleted=not b,old=name if not b else '')
    if before.get('runtime') and before.get('runtime')!=after.get('runtime'):
        add('runtime','评审组件更新',next(iter(pages),''),affected=pages)
    if before.get('mode')!=after.get('mode'):
        add('publication','发布版本类型调整',next(iter(pages),''),old=before.get('mode'),new=after.get('mode'))
    return rows


def target_key(target):
    return digest({k:str(target.get(k,'')) for k in ('owner','repo','branch','remoteId')})[:24]


def _folder(root,target,create=False):
    path=Path(root)/'.prototype'/'releases'/target_key(target)
    if proto_meta.is_linked_path(path): raise ValueError('版本记录不能使用链接目录')
    if create: path.mkdir(parents=True,exist_ok=True)
    return path


def load_state(root,target):
    path=_folder(root,target)
    state=proto_meta.read_json(path/'state.json',None)
    if not isinstance(state,dict): return None
    rid=(state.get('release') or {}).get('releaseId','')
    if not re.fullmatch(r'rel-[a-f0-9]{16}',rid): return None
    snap_path=path/'snapshots'/(rid+'.json.gz')
    if proto_meta.is_linked_path(snap_path): raise ValueError('版本快照不能使用链接文件')
    try:
        with gzip.open(snap_path,'rt',encoding='utf-8') as stream: state['snapshot']=json.load(stream)
    except (OSError,ValueError): return None
    return state


def prepare(root,bundle,target,published_at=None,*,snapshot=None,baseline=None,mode='review',unavailable=False):
    import review_export
    snap=snapshot or capture(root,bundle,mode)
    previous=baseline if baseline is not None else load_state(root,target)
    old=(previous or {}).get('snapshot')
    items=[] if unavailable and old is None else compare(old,snap)
    draft=proto_meta.read_json(_folder(root,target)/'draft.json',{})
    if draft.get('sourceVersion')==snap['contentVersion']:
        for item in items:
            if item['id'] in draft.get('descriptions',{}): item['description']=draft['descriptions'][item['id']]
    rid='rel-'+uuid.uuid4().hex[:16]
    release={'schemaVersion':SCHEMA,'projectId':snap['projectId'],'releaseId':rid,'sequence':int(((previous or {}).get('release') or {}).get('sequence',0))+1,
             'contentVersion':snap['contentVersion'],'publishedAt':review_export.publication_time(published_at),'mode':mode,
             'baseReleaseId':((previous or {}).get('release') or {}).get('releaseId',''),
             'summary':{'pages':len({r['target']['pageId'] for r in items}),'changes':len(items)},
             'changesUrl':NOTES_DIR+'/'+rid+'.json','snapshotUrl':NOTES_DIR+'/'+rid+'.snapshot.json',
             'prototypeBase':VERSIONS_DIR+'/'+snap['contentVersion'][:24]+'/' if mode=='review' else '',
             'baselineStatus':'previous' if old else 'unavailable' if unavailable else 'initial'}
    changes={'schemaVersion':SCHEMA,'releaseId':rid,'sequence':release['sequence'],'publishedAt':release['publishedAt'],
             'contentVersion':snap['contentVersion'],'baselineStatus':release['baselineStatus'],'items':items}
    publication={'release':release,'changes':changes,'snapshot':snap,'target':dict(target),
                 'history':(previous or {}).get('history',[])}
    remember_preview(root,target,publication)
    return publication


def save_draft(root,target,source_version,descriptions):
    path=_folder(root,target,True)
    preview=proto_meta.read_json(path/'preview.json',{})
    if preview.get('sourceVersion')!=source_version: raise ValueError('项目内容已变化，请重新生成更新说明')
    if not isinstance(descriptions,dict) or len(descriptions)>1000: raise ValueError('更新说明格式无效')
    allowed=set(preview.get('changeIds',[])); values={}
    for key,value in descriptions.items():
        if key not in allowed or not isinstance(value,str) or len(value)>1000: raise ValueError('更新说明内容无效')
        values[key]=value.strip()
    proto_meta.write_json_atomic(path/'draft.json',{'sourceVersion':source_version,'descriptions':values})


def remember_preview(root,target,publication):
    path=_folder(root,target,True)
    proto_meta.write_json_atomic(path/'preview.json',{'sourceVersion':publication['snapshot']['contentVersion'],
        'changeIds':[r['id'] for r in publication['changes']['items']]})


def commit(root,target,publication):
    folder=_folder(root,target,True); snapshots=folder/'snapshots'
    if proto_meta.is_linked_path(snapshots): raise ValueError('快照目录不能使用链接')
    snapshots.mkdir(exist_ok=True)
    release=publication['release']; rid=release['releaseId']
    if not re.fullmatch(r'rel-[a-f0-9]{16}',rid): raise ValueError('发布版本 ID 无效')
    raw=gzip.compress(canonical(publication['snapshot']).encode('utf-8'),mtime=0)
    dest=snapshots/(rid+'.json.gz'); temp=dest.with_suffix('.tmp')
    if proto_meta.is_linked_path(dest) or proto_meta.is_linked_path(temp): raise ValueError('快照路径不能使用链接')
    temp.write_bytes(raw); temp.replace(dest)
    entry={**release,'items':publication['changes']['items']}
    previous=load_state(root,target)
    unchanged=previous and previous['release'].get('contentVersion')==release.get('contentVersion')
    history=publication.get('history',[])[:LIMIT] if unchanged else [entry,*publication.get('history',[])][:LIMIT]
    state={'schemaVersion':SCHEMA,'target':dict(target),'release':release,'history':history,'deployment':'pending'}
    proto_meta.write_json_atomic(folder/'state.json',state)
    keep={h['releaseId'] for h in history}|{rid}
    for old in snapshots.glob('rel-*.json.gz'):
        if old.name[:-8] not in keep and not old.is_symlink(): old.unlink()
    return state


def remote_baseline(session,target):
    """优先读取本协议的公开语义快照；旧研发产物只读迁移，不改远端。"""
    import github_pages as G
    current=G.repository_tree(session,target['owner'],target['repo'],target['branch'])
    prefix='projects/'+G._id(target['remoteId'])+'/'
    raw=G.read_file(session,current,prefix+MANIFEST)
    if raw:
        release=json.loads(raw)
        if not isinstance(release,dict) or release.get('schemaVersion')!=SCHEMA: raise ValueError('远端版本协议不兼容')
        rel=release.get('snapshotUrl','')
        if not re.fullmatch(r'prototype-changes/rel-[a-f0-9]{16}\.snapshot\.json',rel):
            return {'release':release,'snapshot':None,'history':release.get('history',[])}
        snapshot=json.loads(G.read_file(session,current,prefix+rel) or b'null')
        if not isinstance(snapshot,dict) or not isinstance(snapshot.get('pages'),list) or not isinstance(snapshot.get('files'),dict):
            raise ValueError('远端比较快照不完整')
        return {'release':release,'snapshot':snapshot,'history':release.get('history',[])}
    shell=G.read_file(session,current,prefix+'index.html')
    if not shell: return None
    match=re.search(r'<script type="application/json" id="review-data">(.*?)</script>',shell.decode('utf-8-sig'),re.S)
    if not match: return None
    data=json.loads(match.group(1))
    if not isinstance(data.get('pages'),list): return None
    files={}
    for row in current['files']:
        if row.get('type')!='blob' or not row['path'].startswith(prefix+'proto/'): continue
        name=row['path'][len(prefix+'proto/'):]
        suffix=Path(name).suffix.lower()
        if suffix not in {'.html','.htm',*KINDS,*ASSETS}: continue
        record={'hash':row['sha'],'bytes':row.get('size',0),'kind':KINDS.get(suffix,'asset')}
        if suffix in {'.html','.htm'}:
            text=(G.read_file(session,current,row['path']) or b'').decode('utf-8-sig')
            record.update(html_content(text)); record['kind']='html'
            record['hash']=digest({k:v for k,v in record.items() if k not in {'hash','bytes','refs'}})
        files[name]=record
    snapshot={'schemaVersion':SCHEMA,'projectId':data.get('projectId',''),'name':data.get('name','原型项目'),
        'mode':'review','pages':[clean(p) for p in data['pages']],
        'documents':[clean({k:v for k,v in d.items() if k!='confirmed'}) for d in data.get('documents',[])],
        'annotations':[clean({k:v for k,v in n.items() if k not in {'number','confirmed'}}) for n in data.get('annotations',[])],
        'files':files,'runtime':None,**({'pinStyle':clean(data['pinStyle'])} if 'pinStyle' in data else {})}
    snapshot['contentVersion']=digest(snapshot)
    return {'snapshot':snapshot,'release':{'sequence':0,'releaseId':'','publishedAt':data.get('publishedAt',''),'prototypeBase':'proto/'},'history':[]}


def write_publication(directory,publication):
    """只把原本可交付的内容写入静态站；纯净版不携带 PRD 或语义快照。"""
    directory=Path(directory); release=copy.deepcopy(publication['release'])
    if release['mode']=='review':
        notes=directory/NOTES_DIR; notes.mkdir(exist_ok=True)
        (directory/release['changesUrl']).write_text(canonical(publication['changes']),encoding='utf-8')
        (directory/release['snapshotUrl']).write_text(canonical(publication['snapshot']),encoding='utf-8')
    else:
        release.update(changesUrl='',snapshotUrl='',summary={'pages':0,'changes':0})
    (directory/MANIFEST).write_text(canonical(release),encoding='utf-8')
    return [MANIFEST]+([release['changesUrl'],release['snapshotUrl']] if release['mode']=='review' else [])


def probe_deployment(target,release):
    import requests
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,99}',str(target.get('owner',''))): return False
    from urllib.parse import quote
    url='https://'+target['owner']+'.github.io/'+quote(target['repo'],safe='')+'/projects/'+quote(target['remoteId'],safe='')+'/'+MANIFEST
    try:
        response=requests.get(url,params={'v':release['releaseId']},headers={'Cache-Control':'no-cache'},timeout=5)
        if response.status_code!=200 or len(response.content)>1024*1024:return False
        value=response.json()
        return value.get('releaseId')==release['releaseId'] and value.get('contentVersion')==release['contentVersion']
    except (requests.RequestException,ValueError,AttributeError): return False
