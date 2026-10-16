"""PRD 草稿落库：把 Agent 写出的 .prototype/prd.draft.json 确定性地写进 .prototype 三文件。

为什么要有这一步：Agent 写 PRD 是判断活（哪条该做序号、哪条该进页面说明），落库是结构活
（anchor 字段、编号、三文件同 revision、confirmed 保护）。让 Agent 直接手改 prd.json 会错字段、
撞 revision、漏校验；这里只认草稿，其余全部由代码推导。

草稿格式（schemaVersion 3，正文由逐条需求关联生成 Markdown）：
{
  "schemaVersion": 3,
  "baseRevision": 0,
  "scope": {"mode":"delta", "request":"新增刷新入口", "requirements":[{"id":"R1","text":"新增刷新入口","sourceQuote":"新增刷新入口","before":"列表没有刷新入口","after":"提供刷新当前列表的入口"}]},
  "pages": [{
    "file": "index.html",            # 或 "pageId": "home"；file 优先，按登记表 casefold 匹配
    "targets": [{"protoId":"btn-refresh","requirementIds":["R1"]}],
    "stateId": "default",            # 可省，默认 default；必须是该页已登记的状态
    "document": {"goals":[{"requirementId":"R1","text":"便于手动获取当前列表的最新结果。"}]},
    "hotspots": ["btn-refresh"],      # 仅本次改变的真实交互，省略为无提示
    "annotations": [{"protoId":"btn-refresh","items":[{"section":"交互说明","requirementId":"R1","markdown":"1. 点击刷新当前列表。"}]}]
  }],
  "unknowns": ["……"]                 # 待确认清单，只回显不落库
}

规则：
- protoId 必须在该页 HTML 中恰好出现一次，否则整份草稿不落库（--skip-missing 改为跳过并报告）。
- 默认只处理 scope 中本次需求；旧版本或过期草稿拒绝导入。
- 相同 protoId 默认跳过，显式 update 更新未确认正文，手动删除不自动恢复。
- 点击提示只按单独列出的本次 hotspots 保存，缺省不提示；整页提示必须独立明确开启。
- 页面文档：目标已有非空正文 → 跳过（--replace-doc 才覆盖）；confirmed 的文档永不覆盖。
- 新标注 confirmed:false，落点在元素左侧中点（rx=0, ry=0.5），用户可在工作台拖动。
- 成功后三文件 revision +1，草稿移入 .prototype/imported/ 留档。

用法：
  python proto_import.py <项目根 | p-xxxx 登记ID> [草稿路径] [--dry-run] [--skip-missing] [--replace-doc]
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proto_meta  # noqa: E402

DRAFT_VERSION = 3
DRAFT_NAME = 'prd.draft.json'
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


class ImportError_(ValueError):
    """草稿不合格：整份不落库，消息里列出全部问题让 Agent 一次改完。"""


# ---------- HTML 里的 data-proto-id 清单 ----------

class _ProtoIdScanner(HTMLParser):
    """收集每个 data-proto-id 的 tag 与可见文本（用作 anchor.text，与 proto-anchors.serialize 的 text 同义）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: dict[str, list[dict[str, Any]]] = {}
        self._open: list[tuple[str, dict[str, Any] | None]] = []   # (tag, record)；非 protoId 元素 record 为 None
        self._skip = 0                                              # script/style 深度，内文不算文本

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        record = None
        pid = (attrs.get('data-proto-id') or '').strip()
        if pid:
            record = {'tag': tag, 'text': '', 'attrs': attrs}
            self.found.setdefault(pid, []).append(record)
        if tag in VOID_TAGS:
            if record is not None:
                record['text'] = (attrs.get('value') or attrs.get('placeholder') or attrs.get('aria-label') or attrs.get('alt') or '').strip()
            return
        if tag in ('script', 'style'):
            self._skip += 1
        self._open.append((tag, record))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        # 容错：未闭合标签按最近同名开标签收口；找不到同名开标签的孤立闭合忽略
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                del self._open[i:]
                self._skip = sum(1 for t, _ in self._open if t in ('script', 'style'))
                return

    def handle_data(self, data):
        if self._skip or not data.strip():
            return
        piece = re.sub(r'\s+', ' ', data)
        for _tag, rec in self._open:
            if rec is not None:
                rec['text'] += piece


def scan_proto_ids(html: str) -> dict[str, list[dict[str, Any]]]:
    parser = _ProtoIdScanner()
    parser.feed(html)
    parser.close()
    for records in parser.found.values():
        for rec in records:
            rec['text'] = rec['text'].strip()[:200]
    return parser.found


# ---------- 草稿解析 ----------

ANNOTATION_SECTIONS = ('页面显示', '数据流转', '业务规则', '交互说明', '异常情况')


def _text_key(value):
    return re.sub(r'\s+', '', value)


def _reference(item, allowed, where):
    if not isinstance(item, dict) or not isinstance(item.get('requirementId'), str) or item['requirementId'] not in allowed:
        raise ImportError_(f'{where}：每条内容必须关联本期 requirementId，不能借容器绑定夹带其他功能')


def render_document(document, allowed, where):
    if document is None:
        return ''
    if not isinstance(document, dict) or not document or set(document) - {'background', 'goals'}:
        raise ImportError_(f'{where}：document 只接受本期 background / goals 分条对象，背景与目标以外的研发规则请写标注，不再接受整页 Markdown 字符串')
    sections = []
    for key, title in (('background', '需求背景'), ('goals', '需求目标')):
        if key not in document:
            continue
        items = document[key]
        if not isinstance(items, list) or not items:
            raise ImportError_(f'{where}.{key}：无内容时省略，不提交空背景或目标')
        lines = []
        for index, item in enumerate(items):
            label = f'{where}.{key}[{index}]'
            _reference(item, allowed, label)
            text = item.get('text')
            if not isinstance(text, str) or not text.strip() or '\n' in text or '\r' in text or re.match(r'\s*(?:#{1,6}\s|[-*+]\s|\d+\.\s|[|>])', text):
                raise ImportError_(f'{label}：背景与目标每条只写一项本期问题或目标，研发实现请拆入标注；不夹带标题、列表或整页概述')
            lines.append('- ' + text.strip())
        sections.append('## ' + title + '\n\n' + '\n'.join(lines))
    return '\n\n'.join(sections)


def render_annotation(note, allowed, where):
    if 'body' in note:
        raise ImportError_(f'{where}：版本 3 不接受整段 body；请将 Markdown 拆成 items，每条选择适用小节并关联本期 requirementId')
    items = note.get('items')
    if not isinstance(items, list) or not items:
        raise ImportError_(f'{where}：protoId 与逐条 items 都不能为空')
    grouped = {}
    for index, item in enumerate(items):
        label = f'{where}.items[{index}]'
        _reference(item, allowed, label)
        section, markdown = item.get('section'), item.get('markdown')
        if section not in ANNOTATION_SECTIONS or not isinstance(markdown, str) or not markdown.strip():
            raise ImportError_(f'{label}：选择适用的 Markdown 小节并填写单条内容，不凑齐五项')
        markdown = markdown.replace('\r\n', '\n').strip()
        if re.search(r'^#{1,6}\s', markdown, re.M):
            raise ImportError_(f'{label}：Markdown 小节由工具生成，单条内容不能再夹带标题')
        bullets = list(re.finditer(r'^(?:[-*+]|\d+\.)[ \t]+\S', markdown, re.M))
        is_table = all(line.startswith('|') and line.endswith('|') for line in markdown.splitlines()) and len(markdown.splitlines()) >= 2
        if not is_table and (len(bullets) != 1 or bullets[0].start() != 0):
            raise ImportError_(f'{label}：每个 Markdown items 条目只写一个顶层列表项或一张状态表；不同规则请分别关联需求')
        if section not in grouped:
            grouped[section] = []
        grouped[section].append(markdown)
    body = '\n\n'.join('### ' + title + '\n\n' + '\n'.join(grouped[title]) for title in ANNOTATION_SECTIONS if title in grouped)
    validate_annotation_markdown(body, where)
    return body


def compile_draft(draft):
    """只生成有逐条需求依据的正文；不从 HTML / 历史 PRD 补充内容。"""
    result = copy.deepcopy(draft)
    ids = {r['id'] for r in result['scope']['requirements']}
    for entry in result['pages']:
        allowed = {t['protoId']: set(t['requirementIds']) for t in entry.get('targets', [])}
        refs = set(entry.get('requirementIds', [])) or {rid for refs in allowed.values() for rid in refs}
        document = entry.get('document')
        entry['_contentRefs'] = [{'kind': 'document', 'section': key, 'requirementId': item['requirementId'], 'text': item['text']} for key in ('background', 'goals') for item in (document or {}).get(key, [])]
        entry['document'] = render_document(document, refs, 'document')
        for note in entry.get('annotations', []):
            note['body'] = render_annotation(note, ids if result['scope']['mode'] == 'full' else allowed[note['protoId']], 'annotations')
            entry['_contentRefs'].extend({'kind': 'annotation', 'protoId': note['protoId'], 'section': item['section'], 'requirementId': item['requirementId'], 'markdown': item['markdown']} for item in note['items'])
    return result


def validate_annotation_markdown(body, where):
    """Require organized Markdown without inventing missing business requirements."""
    body = body.replace('\r\n', '\n')
    headings = list(re.finditer(r'^### +([^\n]+?)[ \t]*$', body, re.M))
    names = [h.group(1).strip() for h in headings]
    if not headings or body[:headings[0].start()].strip() or any(name not in ANNOTATION_SECTIONS for name in names):
        raise ImportError_(f'{where}：body 须用结构化 Markdown，自行选择 ### 页面显示 / 数据流转 / 业务规则 / 交互说明 / 异常情况 中适用的小节，不要求全部填写，不写成一整段')
    indexes = [ANNOTATION_SECTIONS.index(name) for name in names]
    if indexes != sorted(set(indexes)):
        raise ImportError_(f'{where}：Markdown 小节应按页面显示、数据流转、业务规则、交互说明、异常情况排序且不重复')
    for i, heading in enumerate(headings):
        content = body[heading.end():headings[i + 1].start() if i + 1 < len(headings) else len(body)].strip()
        if not content or not re.match(r'(?:\d+\.\s+\S|[-*+]\s+\S|\|.+\|[ \t]*(?:\n|$))', content):
            raise ImportError_(f'{where}：{names[i]} 须分条列出内容（1. 或 -），状态对照可用 Markdown 表格；无内容的小节请省略')
        if not re.match(r'\n[ \t]*\n', body[heading.end():]):
            raise ImportError_(f'{where}：Markdown 小节标题与内容之间须空一行')

def _page_lookup(bundle: dict[str, Any], entry: dict[str, Any], where: str) -> dict[str, Any]:
    pages = bundle['project']['pages']
    file = entry.get('file')
    if file:
        rel = str(file).replace('\\', '/').casefold()
        page = next((p for p in pages if str(p.get('file', '')).casefold() == rel), None)
        if not page:
            raise ImportError_(f'{where}：文件 {file} 未登记为页面（先在工作台打开一次让它登记，或改用已登记的 pageId）')
        if page.get('trashedAt'):
            raise ImportError_(f'{where}：页面在回收站中，请经用户明确要求恢复后再导入')
        return page
    pid = entry.get('pageId')
    page = next((p for p in pages if p['id'] == pid), None)
    if not page:
        raise ImportError_(f'{where}：pageId {pid!r} 不存在；已登记：{", ".join(p["id"] for p in pages)}')
    if page.get('trashedAt'):
        raise ImportError_(f'{where}：页面在回收站中，请经用户明确要求恢复后再导入')
    return page


def _state_check(page: dict[str, Any], state_id: str, where: str) -> None:
    if not any(s['id'] == state_id for s in page.get('states', [])):
        raise ImportError_(f'{where}：页面 {page["id"]} 没有状态 {state_id!r}；已登记：{", ".join(s["id"] for s in page["states"])}')


def validate_draft_scope(draft):
    if not isinstance(draft, dict) or draft.get('schemaVersion') != DRAFT_VERSION:
        raise ImportError_(f'草稿 schemaVersion 必须为 {DRAFT_VERSION}；旧草稿需按本次需求重写 scope，不能直接重放历史标注')
    if type(draft.get('baseRevision')) is not int or draft['baseRevision'] < 0:
        raise ImportError_('缺少有效 baseRevision，请读取当前元数据 revision 后生成草稿')
    scope = draft.get('scope')
    if not isinstance(scope, dict) or scope.get('mode') not in ('delta', 'full') or not isinstance(scope.get('request'), str) or not scope['request'].strip():
        raise ImportError_('scope 必须包含 delta/full 模式与本次用户 request；默认使用 delta')
    requirements = scope.get('requirements')
    if not isinstance(requirements, list) or not requirements or any(not isinstance(r, dict) or not isinstance(r.get('text'), str) or not r['text'].strip() for r in requirements):
        raise ImportError_('scope.requirements 必须列出本次需求 id 与 text')
    ids = [r.get('id') for r in requirements]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ImportError_('需求 id 必须是不重复的字符串')
    request = _text_key(scope['request'])
    for requirement in requirements:
        quote = requirement.get('sourceQuote')
        if not isinstance(quote, str) or not _text_key(quote) or _text_key(quote) not in request:
            raise ImportError_(f'需求 {requirement["id"]} 须以 sourceQuote 引用 scope.request 中的本期需求原文，不能从旧页面功能反推本期需求')
        if scope['mode'] == 'delta':
            before, after = requirement.get('before'), requirement.get('after')
            if not isinstance(before, str) or not before.strip() or not isinstance(after, str) or not after.strip() or _text_key(before) == _text_key(after):
                raise ImportError_(f'需求 {requirement["id"]} 须说明本期实际 before / after 差异；保持不变的功能不属于增量需求')
    if scope['mode'] == 'full':
        full_request = scope.get('fullRequest')
        if not isinstance(full_request, str) or not _text_key(full_request) or _text_key(full_request) not in request:
            raise ImportError_('完整 PRD 须通过 fullRequest 引用用户明确要求的原文；重新整理 / 重新落库不等于整页补全')
    if not isinstance(scope.get('exclusions', []), list) or any(not isinstance(value, str) or not value.strip() for value in scope.get('exclusions', [])):
        raise ImportError_('scope.exclusions 需为本期不涉及内容的字符串数组')
    hint_mode = scope.get('hotspotMode', 'delta')
    if hint_mode not in ('delta', 'full', 'off') or hint_mode == 'full' and (not isinstance(scope.get('hotspotRequest'), str) or not scope['hotspotRequest'].strip()):
        raise ImportError_('hotspotMode 只支持 delta/full/off；整页提示必须填写用户明确要求的 hotspotRequest')
    pages = draft.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ImportError_('草稿 pages 为空')
    for i, entry in enumerate(pages):
        where = f'pages[{i}]'
        if not isinstance(entry, dict):
            raise ImportError_(f'{where} 必须为对象')
        if not (entry.get('file') or entry.get('pageId')):
            raise ImportError_(f'{where}：缺 file 或 pageId')
        removals = entry.get('removals', [])
        if not isinstance(removals, list) or any(not isinstance(item, dict) or not isinstance(item.get('annotationId'), str) or not item['annotationId'].strip() or not isinstance(item.get('reason'), str) or not item['reason'].strip() for item in removals):
            raise ImportError_(f'{where}.removals 必须点名现存 annotationId 并说明误写原因，不能整页清空')
        if len({item['annotationId'] for item in removals}) != len(removals):
            raise ImportError_(f'{where}.removals 重复指定了标注')
        if removals:
            cleanup = scope.get('cleanupRequest')
            if not isinstance(cleanup, str) or not _text_key(cleanup) or _text_key(cleanup) not in request:
                raise ImportError_('清理既有误写标注须以 cleanupRequest 引用用户本次整理 / 清理授权原文；默认不删除历史内容')
        targets = entry.get('targets', [])
        if not isinstance(targets, list) or any(not isinstance(t, dict) or not isinstance(t.get('protoId'), str) or not t['protoId'].strip() or not isinstance(t.get('requirementIds'), list) or not t['requirementIds'] or any(rid not in ids for rid in t['requirementIds']) for t in targets):
            raise ImportError_(f'{where}.targets 必须绑定存在的需求 requirementIds 和 protoId')
        allowed = [t['protoId'] for t in targets]
        if len(set(allowed)) != len(allowed):
            raise ImportError_(f'{where}.targets 的 protoId 重复')
        refs = entry.get('requirementIds', [rid for t in targets for rid in t['requirementIds']])
        if not isinstance(refs, list) or any(ref not in ids for ref in refs):
            raise ImportError_(f'{where}.requirementIds 引用了不存在的需求')
        if scope['mode'] == 'delta' and entry.get('document') and not refs:
            raise ImportError_(f'{where} 页面文档必须关联本次 requirementIds')
        render_document(entry.get('document'), refs, f'{where}.document')
        notes = entry.get('annotations')
        if notes is None:
            notes = []
        if not isinstance(notes, list) or any(not isinstance(n, dict) for n in notes):
            raise ImportError_(f'{where}.annotations 必须是数组')
        for note in notes:
            if not isinstance(note.get('protoId'), str) or not note['protoId'].strip():
                raise ImportError_(f'{where}：protoId 与逐条 items 都不能为空')
            if scope['mode'] == 'delta' and note.get('protoId') not in allowed:
                raise ImportError_(f'{where} 标注 {note.get("protoId")} 超出本次 targets 范围')
            if note.get('action', 'create') not in ('create', 'update', 'restore'):
                raise ImportError_(f'{where} 标注 action 只支持 create/update/restore')
            item_refs = ids if scope['mode'] == 'full' else next(t['requirementIds'] for t in targets if t['protoId'] == note['protoId'])
            render_annotation(note, item_refs, f'{where} 标注 {note["protoId"]}')
        hints = entry.get('hotspots', [])
        if not isinstance(hints, list) or any(not isinstance(pid, str) or pid not in allowed for pid in hints) or len(set(hints)) != len(hints):
            raise ImportError_(f'{where}.hotspots 超出本次 targets 范围或存在重复')
    if draft.get('unknowns') is not None and not isinstance(draft['unknowns'], list):
        raise ImportError_('unknowns 必须是数组')


def load_draft(path: Path) -> dict[str, Any]:
    try:
        draft = json.loads(path.read_text(encoding='utf-8'))
    except OSError as error:
        raise ImportError_(f'草稿读取失败：{error}') from error
    except ValueError as error:
        raise ImportError_(f'草稿不是合法 JSON：{error}') from error
    validate_draft_scope(draft)
    if draft.get('unknowns') is not None and not isinstance(draft['unknowns'], list):
        raise ImportError_('unknowns 必须是数组')
    return draft


# ---------- 落库 ----------

def historical_annotation_targets(root, bundle):
    """归档仅用于识别曾导入而现已删除的定位，不回放任何旧正文。"""
    files = {p['id']: p['file'].casefold() for p in bundle['project']['pages']}
    found = {(files.get(n['pageId'], n['pageId']), n['stateId'], n['protoId'])
             for n in bundle['prd'].get('deletedAnnotations', [])}
    for path in sorted((proto_meta.meta_dir(root) / 'imported').glob('prd.draft.*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ImportError_(f'历史草稿无法读取，不能确认删除保护：{path.name}：{error}') from error
        for entry in data.get('pages', []):
            file = str(entry.get('file') or files.get(entry.get('pageId'), '')).replace('\\', '/').casefold()
            found.update((file, entry.get('stateId') or 'default', n['protoId']) for n in entry.get('annotations', []))
    return found


def import_draft(root: Path, draft: dict[str, Any], *, replace_doc: bool = False,
                 skip_missing: bool = False, dry_run: bool = False, viewer_origin: str = 'http://localhost:8080') -> dict[str, Any]:
    """把草稿合入 bundle。返回报告；除 dry_run 外成功即落盘（revision +1）。"""
    validate_draft_scope(draft)
    raw_scope = copy.deepcopy(draft['scope'])
    draft = compile_draft(draft)
    root = Path(root).resolve()
    bundle = proto_meta.ensure_bundle(root)
    if bundle['revision'] != draft['baseRevision']:
        raise ImportError_(f'baseRevision 已过期（草稿 {draft["baseRevision"]}，当前 {bundle["revision"]}）；请重新读取当前需求与删除结果，不重放旧草稿')
    proto_meta.ensure_pages_registered(root, bundle)
    from urllib.parse import urlencode, urlsplit
    origin = urlsplit(viewer_origin)
    if origin.scheme not in ('http', 'https') or not origin.netloc or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
        raise ImportError_('viewer-origin 须为工作台实际 HTTP(S) 来源，如 http://localhost:8080')
    viewer = viewer_origin.rstrip('/') + '/src/viewer.html'
    report: dict[str, Any] = {'root': str(root), 'projectId': bundle['project']['id'], 'projectName': bundle['project'].get('name') or root.name,
                              'viewerUrl': viewer + '?' + urlencode({'ext': bundle['project']['id']}), 'pages': [], 'revisionBefore': bundle['revision'],
                              'scope': raw_scope, 'contentRefs': [], 'documents': [], 'annotations': [], 'removedAnnotations': [], 'hints': [], 'skipped': [], 'warnings': [], 'unknowns': list(draft.get('unknowns') or [])}
    before_import = copy.deepcopy(bundle)
    problems: list[str] = []
    now = proto_meta.now_iso()
    history = historical_annotation_targets(root, bundle)
    seen = set()

    for i, entry in enumerate(draft['pages']):
        where = f'pages[{i}]'
        page = _page_lookup(bundle, entry, where)
        state_id = str(entry.get('stateId') or 'default')
        _state_check(page, state_id, where)
        scope = f'{page["id"]}/{state_id}'
        if scope in seen:
            raise ImportError_(f'{scope} 在草稿中重复，请合并本次需求后导入')
        seen.add(scope)
        report['contentRefs'].extend({'scope': scope, **item} for item in entry['_contentRefs'])
        for item in entry.get('removals', []):
            current = next((n for n in bundle['prd']['annotations'] if n['id'] == item['annotationId'] and n['pageId'] == page['id'] and n['stateId'] == state_id), None)
            if current is None:
                problems.append(f'{scope} 要清理的标注 {item["annotationId"]} 不存在于本页状态')
                continue
            if current.get('confirmed'):
                report['skipped'].append(f'{scope} 标注 {item["annotationId"]} 已确认，不删除')
                continue
            pid = (current.get('anchor') or {}).get('protoId')
            if any(note['protoId'] == pid for note in entry.get('annotations', [])):
                problems.append(f'{scope} {pid} 同时清理和重建，请使用 action=update 保留身份与序号')
                continue
            bundle['prd']['annotations'].remove(current)
            report['removedAnnotations'].append({'scope': scope, 'annotationId': current['id'], 'protoId': pid, 'reason': item['reason']})
        state = next(s for s in page['states'] if s['id'] == state_id)
        report['pages'].append({'pageId': page['id'], 'pageTitle': page.get('title') or page['id'], 'file': page['file'],
                                'stateId': state_id, 'stateTitle': state.get('title') or state_id,
                                'viewerUrl': viewer + '?' + urlencode({'ext': bundle['project']['id'], 'page': page['id'], 'state': state_id, 'mode': 'annotate'})})

        # 页面文档
        markdown = entry.get('document')
        if markdown is not None and markdown.strip():
            current = next((d for d in bundle['prd']['documents'] if d['pageId'] == page['id'] and d['stateId'] == state_id), None)
            if current and current.get('confirmed'):
                report['skipped'].append(f'{scope} 文档已确认，不覆盖')
            elif current and (current.get('markdown') or '').strip() and not replace_doc:
                report['skipped'].append(f'{scope} 文档已有正文，未覆盖（--replace-doc 才覆盖）')
            elif current:
                current['markdown'] = markdown
                current['updatedAt'] = now
                report['documents'].append({'scope': scope, 'action': 'replaced'})
            else:
                bundle['prd']['documents'].append({'id': str(uuid.uuid4()), 'pageId': page['id'], 'stateId': state_id,
                                                   'markdown': markdown, 'confirmed': False, 'updatedAt': now})
                report['documents'].append({'scope': scope, 'action': 'created'})

        # 元素标注
        notes = entry.get('annotations') or []
        targets = [t['protoId'] for t in entry.get('targets', [])]
        ids = {}
        if notes or targets:
            try:
                html = proto_meta.safe_asset(root, page['file']).read_text(encoding='utf-8', errors='replace')
            except (ValueError, FileNotFoundError) as error:
                raise ImportError_(f'{where}：读不到页面文件 {page["file"]}：{error}') from error
            ids = scan_proto_ids(html)
        valid_targets = []
        for pid in targets:
            if len(ids.get(pid, [])) == 1:
                valid_targets.append(pid)
            elif not skip_missing:
                problems.append(f'{where}.targets：{pid} 不存在或不唯一')
        existing = [n for n in bundle['prd']['annotations'] if n['pageId'] == page['id'] and n['stateId'] == state_id]
        number = max((n.get('number') or 0 for n in existing), default=0)
        taken = {(n.get('anchor') or {}).get('protoId') for n in existing}
        for j, note in enumerate(notes):
            pid = str(note['protoId']).strip()
            hits = ids.get(pid, [])
            if len(hits) != 1:
                msg = (f'{where}.annotations[{j}]：{page["file"]} 里 data-proto-id="{pid}" '
                       + ('不存在' if not hits else f'出现 {len(hits)} 次，页面内必须唯一'))
                if skip_missing:
                    report['skipped'].append(msg)
                    continue
                problems.append(msg)
                continue
            if pid in taken:
                current = next((n for n in existing if (n.get('anchor') or {}).get('protoId') == pid), None)
                if current and note.get('action') == 'update' and not current.get('confirmed') and current['body'] != str(note['body']).strip():
                    current['body'] = str(note['body']).strip()
                    current['updatedAt'] = now
                    report['annotations'].append({'scope': scope, 'number': current['number'], 'protoId': pid, 'tag': ids[pid][0]['tag'], 'text': ids[pid][0]['text'][:40], 'action': 'updated'})
                    continue
                report['skipped'].append(f'{scope} 已有绑定 {pid} 的标注，跳过重复导入')
                continue
            if (page['file'].casefold(), state_id, pid) in history and note.get('action') != 'restore':
                report['skipped'].append(f'{scope} {pid} 曾存在但已被删除，保留删除结果；明确要求恢复时才使用 action=restore')
                continue
            if note.get('action') == 'update':
                problems.append(f'{scope} {pid} 没有可更新的标注，不能自动新增')
                continue
            taken.add(pid)
            number += 1
            hit = hits[0]
            if 'hidden' in hit['attrs']:
                report['warnings'].append(f'{scope} #{number} {pid} 带 hidden 属性：工作台会显示为失锚，直到页面让它显现（需要时在工作台重新绑定以记下显现条件）')
            bundle['prd']['annotations'].append({
                'id': str(uuid.uuid4()), 'pageId': page['id'], 'stateId': state_id, 'number': number,
                'body': str(note['body']).strip(),
                # 与 proto-anchors.serialize 的字段同名；resolve 以 protoId 为第一优先级，tag 作校验，不需要 rect
                'anchor': {'protoId': pid, 'selector': f'[data-proto-id="{pid}"]', 'tag': hit['tag'], 'text': hit['text']},
                # 落点：元素左侧中点。rx/ry 优先于 x/y（proto-anchors.point），x/y 只是占位满足校验
                'placement': {'kind': 'element', 'x': 0, 'y': 0, 'rx': 0, 'ry': 0.5},
                'offset': {'x': 20, 'y': 0}, 'collapsed': False, 'confirmed': False, 'updatedAt': now,
            })
            report['annotations'].append({'scope': scope, 'number': number, 'protoId': pid, 'tag': hit['tag'], 'text': hit['text'][:40]})

        hint_mode = draft['scope'].get('hotspotMode', 'delta')
        hints = {'mode': 'all'} if hint_mode == 'full' else {'mode': 'targets', 'protoIds': [] if hint_mode == 'off' else [pid for pid in entry.get('hotspots', []) if pid in valid_targets]}
        state = next(s for s in page['states'] if s['id'] == state_id)
        if state.get('interactionHints') != hints:
            state['interactionHints'] = hints
            report['hints'].append({'scope': scope, **hints})

    if problems:
        raise ImportError_('草稿未落库，请先修正：\n  - ' + '\n  - '.join(problems))
    changed = bool(report['documents'] or report['annotations'] or report['removedAnnotations'] or report['hints'])
    report['changed'] = changed
    report['dryRun'] = dry_run
    if changed and not dry_run:
        if proto_meta.load_bundle(root)['revision'] != report['revisionBefore']:
            raise ImportError_('导入期间元数据已更新，保留现场，请重新读取后生成草稿')
        if report['removedAnnotations']:
            proto_meta.remember_annotation_deletions(before_import, bundle)
        bundle['revision'] += 1
        proto_meta.save_bundle(root, bundle)
    report['revisionAfter'] = bundle['revision']
    return report


def archive_draft(root: Path, draft_path: Path, revision: int) -> Path:
    """落库后草稿留档：不删（用户红线），移到 .prototype/imported/ 并带上 revision 便于回溯。"""
    target_dir = proto_meta.meta_dir(root) / 'imported'
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = proto_meta.now_iso().replace(':', '').replace('-', '')[:15]
    target = target_dir / f'prd.draft.r{revision}.{stamp}.json'
    draft_path.replace(target)
    return target


def resolve_root(text: str) -> Path:
    """接受项目根路径或登记 ID（p-xxxx，查 data/external.json）。"""
    if re.fullmatch(r'p-[0-9a-f]{16}', text):
        registry = proto_meta.read_json(Path(__file__).resolve().parent / 'data' / 'external.json', {})
        item = (registry.get('projects') or {}).get(text)
        if not item or not item.get('root'):
            raise ImportError_(f'登记表里没有 {text}')
        return Path(item['root']).resolve()
    root = Path(text).expanduser().resolve()
    if not root.is_dir():
        raise ImportError_(f'项目目录不存在：{root}')
    return root


def format_report(report: dict[str, Any]) -> str:
    lines = [f'项目 {report.get("projectName", report["projectId"])}（{report["projectId"]}）  {report["root"]}']
    lines.append(f'revision {report["revisionBefore"]} → {report["revisionAfter"]}' + ('（dry-run，未写入）' if report['dryRun'] else ''))
    for requirement in report.get('scope', {}).get('requirements', []):
        lines.append(f'  本期需求  {requirement["id"]}  {requirement["text"]}')
        if requirement.get('before') and requirement.get('after'):
            lines.append(f'  改造差异  {requirement["before"]} → {requirement["after"]}')
    for excluded in report.get('scope', {}).get('exclusions', []):
        lines.append(f'  本期不涉及  {excluded}')
    for page in report.get('pages', []):
        lines.append(f'  页面  {page["pageTitle"]} · {page["file"]} · {page["stateTitle"]}')
        lines.append(f'  定位  {page["viewerUrl"]}')
    for d in report['documents']:
        lines.append(f'  文档  {d["scope"]}  {"覆盖" if d["action"] == "replaced" else "新建"}')
    for a in report['annotations']:
        lines.append(f'  标注  {a["scope"]}  #{a["number"]}  {a["protoId"]}  <{a["tag"]}> {a["text"]}')
    for item in report.get('removedAnnotations', []):
        lines.append(f'  清理误注  {item["scope"]}  {item["annotationId"]}  {item["reason"]}')
    for hints in report['hints']:
        label = '整页（明确要求）' if hints['mode'] == 'all' else '、'.join(hints['protoIds']) or '无'
        lines.append(f'  点击提示  {hints["scope"]}  {label}')
    for s in report['skipped']:
        lines.append(f'  跳过  {s}')
    for w in report['warnings']:
        lines.append(f'  提醒  {w}')
    if report['unknowns']:
        lines.append('待确认（未落库，需你拍板后补进文档或标注）：')
        lines.extend(f'  ? {u}' for u in report['unknowns'])
    if not report['changed']:
        lines.append('没有可落库的新内容。')
    elif not report['dryRun']:
        lines.append('工作台若已打开该项目，请刷新页面（否则下一次保存会因 revision 过期报 409）。')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='把 Agent 写的 PRD 草稿落进 .prototype 元数据')
    ap.add_argument('project', help='项目根路径，或登记 ID（p-xxxxxxxxxxxxxxxx）')
    ap.add_argument('draft', nargs='?', help=f'草稿路径，默认 <项目根>/.prototype/{DRAFT_NAME}')
    ap.add_argument('--dry-run', action='store_true', help='只报告，不写入')
    ap.add_argument('--skip-missing', action='store_true', help='protoId 找不到 / 不唯一时跳过该条而不是整份拒绝')
    ap.add_argument('--replace-doc', action='store_true', help='目标页面文档已有正文时覆盖（confirmed 的仍不覆盖）')
    ap.add_argument('--viewer-origin', default='http://localhost:8080', help='工作台实际来源，用于生成定位链接')
    args = ap.parse_args(argv)
    try:
        root = resolve_root(args.project)
        draft_path = Path(args.draft).resolve() if args.draft else proto_meta.meta_dir(root) / DRAFT_NAME
        draft = load_draft(draft_path)
        report = import_draft(root, draft, replace_doc=args.replace_doc, skip_missing=args.skip_missing, dry_run=args.dry_run, viewer_origin=args.viewer_origin)
        print(format_report(report))
        if report['changed'] and not args.dry_run:
            print(f'草稿已留档：{archive_draft(root, draft_path, report["revisionAfter"])}')
        return 0
    except (ImportError_, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
