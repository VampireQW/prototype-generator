"""导入 HTML 页面，或在保留页面身份与 PRD 的前提下重新导入本页资源。"""
from __future__ import annotations

import base64
import copy
import re
import uuid
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

import proto_meta
from screenshot_pages import safe_path, _atomic

PENDING = 'html-import.pending.json'
MAX_TOTAL = 30 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
MAX_HTML = 5 * 1024 * 1024
MAX_FILES = 300
PREFIX = re.compile(r'pages/html-[a-f0-9]{16}')
RESERVED = re.compile(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',re.I)


class RevisionConflict(ValueError):
    def __init__(self,current):
        super().__init__('项目已更新，请重试导入；本次选择的文件已保留')
        self.current=current


def relative_path(value):
    if not isinstance(value,str) or not value or '\\' in value or any(ord(c)<32 for c in value) or any(c in value for c in '<>"|?*'):
        raise ValueError('导入文件路径无效')
    path=proto_meta.safe_relative(value).as_posix()
    if path!=value or any(RESERVED.fullmatch(p) or p.casefold() in {'node_modules','__pycache__','exports','dist','agent-skills'} for p in path.split('/')):
        raise ValueError('导入路径包含保留名称或依赖目录')
    return path


def validate_record(page):
    record=page.get('htmlImport')
    if not isinstance(record,dict) or not PREFIX.fullmatch(str(record.get('directory',''))) or page.get('id')!=record['directory'].split('/')[1]:
        raise ValueError('HTML 导入登记无效')
    files=record.get('files')
    if not isinstance(files,list) or not files or len(files)>MAX_FILES or page.get('file') not in files:
        raise ValueError('HTML 导入资源清单无效')
    prefix=record['directory']+'/'
    seen=set()
    for value in files:
        path=relative_path(value)
        if not path.startswith(prefix) or path.casefold() in seen or Path(path).suffix.lower() not in proto_meta.ASSET_TYPES:
            raise ValueError('HTML 导入资源超出本页目录或重复')
        seen.add(path.casefold())
    if Path(page['file']).suffix.lower() not in ('.html','.htm'):
        raise ValueError('导入入口必须是 HTML')


def owned_assets(page):
    if 'htmlImport' not in page:return []
    validate_record(page)
    return [f for f in page['htmlImport']['files'] if f!=page['file']]


def trashed_assets(bundle):
    return [f for p in bundle['project']['pages'] if p.get('trashedAt') for f in owned_assets(p)]


class HTMLInfo(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tags=0;self.in_title=False;self.title=''
    def handle_starttag(self,tag,attrs):
        self.tags+=1
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,text):
        if self.in_title:self.title+=text


def decode_files(data):
    entry=relative_path(data.get('entryFile'))
    if Path(entry).suffix.lower() not in ('.html','.htm'):
        raise ValueError('请选择 .html 或 .htm 入口文件')
    items=data.get('files')
    if not isinstance(items,list) or not 1<=len(items)<=MAX_FILES:
        raise ValueError('每次导入 1–300 个文件')
    files={};seen=set();total=0
    for item in items:
        if not isinstance(item,dict):raise ValueError('导入文件数据无效')
        path=relative_path(item.get('path'));suffix=Path(path).suffix.lower()
        if suffix not in proto_meta.ASSET_TYPES or (suffix in ('.html','.htm') and path!=entry):
            raise ValueError('只支持选定入口 HTML 和配套静态资源')
        if path.casefold() in seen:raise ValueError('文件路径重复（不区分大小写）')
        seen.add(path.casefold())
        value=item.get('dataUrl')
        if not isinstance(value,str) or len(value)>MAX_FILE*4//3+256:
            raise ValueError('单个资源不能超过 10 MB')
        match=re.fullmatch(r'data:[^,;]*(?:;charset=[^,;]+)?;base64,([A-Za-z0-9+/=]*)',value)
        if not match:raise ValueError('导入文件编码无效')
        raw=base64.b64decode(match[1],validate=True);total+=len(raw)
        if len(raw)>MAX_FILE or total>MAX_TOTAL:raise ValueError('单个资源最大 10 MB，合计最大 30 MB')
        if path==entry and (not raw or len(raw)>MAX_HTML):raise ValueError('入口 HTML 不能为空或超过 5 MB')
        files[path]=raw
    if entry not in files:raise ValueError('入口 HTML 未包含在文件清单中')
    raw=files[entry]
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('HTML 请另存为 UTF-8 编码后导入') from None
    info=HTMLInfo();info.feed(text)
    if not info.tags:raise ValueError('文件中没有 HTML 内容')
    return entry,files,re.sub(r'\s+',' ',info.title).strip()[:100]


def import_page(root,data):
    return _write_page(root,data,replace=False)


def replace_page(root,data):
    return _write_page(root,data,replace=True)


def _prune_empty_parents(path, boundary):
    parent=path.parent
    while parent!=boundary and boundary in parent.parents:
        try:parent.rmdir()
        except OSError:break
        parent=parent.parent


def _write_page(root,data,replace):
    if not isinstance(data,dict):raise ValueError('导入参数必须为对象')
    root=Path(root).resolve()
    with proto_meta.PROJECT_LOCK:
        before=proto_meta.load_bundle(root)
        if type(data.get('expectedRevision')) is not int or data['expectedRevision']!=before['revision']:
            raise RevisionConflict(before)
        entry,files,source_title=decode_files(data)
        bundle=copy.deepcopy(before);project=bundle['project']
        old_files=[]
        if replace:
            page=next((p for p in project['pages'] if p['id']==data.get('pageId') and not p.get('trashedAt')),None)
            if not page or 'htmlImport' not in page:raise ValueError('请选择有效的已导入 HTML 页面')
            validate_record(page);directory=page['htmlImport']['directory'];old_files=page['htmlImport']['files'][:]
        else:
            title=data.get('title') or source_title or PurePosixPath(entry).stem
            if not isinstance(title,str) or not title.strip() or len(title)>100:raise ValueError('请填写页面名称（最多 100 字）')
            preview=data.get('previewType','web');client=data.get('clientId','')
            if preview not in ('web','mobile','pad'):raise ValueError('页面外壳无效')
            if client and not any(c['id']==client for c in project.get('clients',[])):raise ValueError('端分类不存在')
            page_id='html-'+uuid.uuid4().hex[:16];directory='pages/'+page_id
            page={'id':page_id,'title':title.strip(),'previewType':preview,'clientId':client,
                  'states':[{'id':'default','title':'默认页面','kind':'default','interactionHints':{'mode':'targets','protoIds':[]}}]}
            if data.get('parentId'):
                parent=next((p for p in project['pages'] if p['id']==data['parentId'] and not p.get('trashedAt')),None)
                if not parent:raise ValueError('父页面不存在')
                page['parentId']=parent['id']
            project['pages'].append(page)
            if not project.get('defaultPage'):project['defaultPage']=page_id
        page['file']=directory+'/'+entry;page['url']=(root/page['file']).as_uri()
        page['htmlImport']={'directory':directory,'files':[directory+'/'+p for p in files]}
        bundle['revision']+=1;proto_meta.validate_bundle(bundle)
        target=safe_path(root,directory)
        if not replace and target.exists():raise ValueError('导入目录已存在，请重试')
        paths={relative:safe_path(root,directory+'/'+relative) for relative in files}
        old_keys={p.casefold() for p in old_files}
        new_keys={p.casefold() for p in page['htmlImport']['files']}
        for relative,path in paths.items():
            if path.exists() and (not path.is_file() or (directory+'/'+relative).casefold() not in old_keys):
                raise ValueError('替换路径包含未登记文件或目录，已保留原文件')
        previous={relative:safe_path(root,relative).read_bytes() for relative in old_files if safe_path(root,relative).exists()}
        obsolete=[p for p in old_files if p.casefold() not in new_keys]
        marker=proto_meta.meta_dir(root)/PENDING
        if proto_meta.is_linked_path(marker.parent) or proto_meta.is_linked_path(marker):raise ValueError('元数据目录不能是链接')
        proto_meta.write_json_atomic(marker,{'before':before,'after':bundle,'directory':directory,'files':page['htmlImport']['files'],
            'beforeFiles':{p:base64.b64encode(raw).decode('ascii') for p,raw in previous.items()}})
        created=[]
        try:
            for relative in obsolete:
                path=safe_path(root,relative);path.unlink(missing_ok=True);_prune_empty_parents(path,target)
            for relative,path in paths.items():
                if not path.exists():created.append(directory+'/'+relative)
                _atomic(path,files[relative])
            proto_meta.save_bundle(root,bundle)
        except Exception:
            for relative in reversed(created):
                path=safe_path(root,relative);path.unlink(missing_ok=True);_prune_empty_parents(path,target)
            for relative,raw in previous.items():_atomic(safe_path(root,relative),raw)
            if not replace:
                try:target.rmdir()
                except OSError:pass
            marker.unlink(missing_ok=True)
            raise
        marker.unlink()
        return {'ok':True,'bundle':bundle,'page':page,'fileCount':len(files)}
