"""精确修改静态文本或持久化有稳定控件键的动态文案，不序列化运行中的 DOM。"""
from __future__ import annotations

import base64
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

import proto_meta

VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
BLOCKED = set('script style template noscript svg math canvas iframe object textarea'.split())
ALLOWED = set('button a label span p h1 h2 h3 h4 h5 h6 td th option legend small strong em b i li dt dd summary div'.split())
DYNAMIC = {'v-for', 'v-text', 'v-html', 'ng-bind', 'ng-repeat', 'data-bind'}
KEYS = {'data-proto-id', 'id', 'data-q', 'data-key', 'data-id', 'data-row-id', 'data-row-key', 'data-item-id', 'data-column-key', 'data-field', 'data-testid', 'name'}
RUNTIME_START = '\n<!-- proto-text-edits:start -->\n'
RUNTIME_END = '\n<!-- proto-text-edits:end -->\n'


class UnsupportedText(ValueError):
    pass


class EditConflict(ValueError):
    pass


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _normal(value):
    return ' '.join(value.split())


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []


class Source(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text, self.root, self.nodes = text, Node('#document'), []
        self.stack = [self.root]
        self.lines = [0] + [m.end() for m in re.finditer('\n', text)]
        self.feed(text); self.close()

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        optional = {'td': {'td', 'th'}, 'th': {'td', 'th'}, 'tr': {'tr'}, 'li': {'li'}, 'option': {'option'}}
        if tag in optional:
            for index in range(len(self.stack)-1, 0, -1):
                if self.stack[index].tag in optional[tag]:
                    self.stack = self.stack[:index]; break
                if self.stack[index].tag in {'table', 'ul', 'ol', 'select'}: break
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node); self.nodes.append(node)
        if tag not in VOID: self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]; break

    def add_text(self, raw):
        start, end = self.position(), self.position() + len(raw)
        children = self.stack[-1].children
        if children and isinstance(children[-1], tuple) and children[-1][1] == start:
            children[-1] = (children[-1][0], end)
        else: children.append((start, end))

    handle_data = add_text

    def handle_entityref(self, name): self.add_text('&' + name + (';' if self.text[self.position()+len(name)+1:self.position()+len(name)+2] == ';' else ''))
    def handle_charref(self, name): self.add_text('&#' + name + (';' if self.text[self.position()+len(name)+2:self.position()+len(name)+3] == ';' else ''))

    def resolve(self, target):
        if not isinstance(target, dict) or not isinstance(target.get('tag'), str) or target['tag'] not in ALLOWED or target.get('reactive'):
            raise UnsupportedText('请选择按钮、文字或单元格；动态内容请使用 AI 修改')
        if target.get('protoId') or target.get('id'):
            key, value = ('data-proto-id', target['protoId']) if target.get('protoId') else ('id', target['id'])
            found = [n for n in self.nodes if n.attrs.get(key) == value]
        else:
            node = self.root
            path = target.get('path')
            if not isinstance(path, list) or not path or len(path) > 80: raise UnsupportedText('无法定位到源文件，请使用 AI 修改')
            for part in path:
                if not isinstance(part, dict): raise UnsupportedText('元素位置无效')
                tag, index = part.get('tag'), part.get('index')
                if not isinstance(tag, str) or type(index) is not int or index < 1: raise UnsupportedText('元素位置无效')
                children = [n for n in node.children if isinstance(n, Node) and n.tag == tag]
                if not children and ((tag in {'html', 'body'} and node.tag in {'#document', 'html'}) or (tag == 'tbody' and node.tag == 'table')):
                    if index != 1: raise UnsupportedText('元素位置无效')
                    continue
                if index > len(children): raise UnsupportedText('当前内容无法在源文件中精确定位，请使用 AI 修改')
                node = children[index-1]
            found = [node]
        if len(found) != 1 or found[0].tag != target['tag']:
            raise UnsupportedText('元素未找到或不唯一，请重新选择，或使用 AI 修改')
        node = found[0]
        ancestor = node
        while ancestor:
            if ancestor.tag in BLOCKED or any(k in DYNAMIC or k.startswith('v-bind:') and k.endswith(('text', 'html')) for k in ancestor.attrs):
                raise UnsupportedText('这个文案由程序生成，请使用 AI 修改')
            ancestor = ancestor.parent
        slots = []
        def visit(current):
            for child in current.children:
                if isinstance(child, tuple):
                    raw = self.text[child[0]:child[1]]; value = html.unescape(raw)
                    if value.strip(): slots.append((child[0], child[1], value.strip()))
                elif child.tag not in BLOCKED: visit(child)
        visit(node)
        expected = target.get('texts')
        if not slots or len(slots) > 8 or any(len(s[2]) > 4096 or '{{' in s[2] or '${' in s[2] for s in slots):
            raise UnsupportedText('请选择具体文案；程序生成的内容请使用 AI 修改')
        if not isinstance(expected, list) or not all(isinstance(t, str) for t in expected) or [_normal(t) for t in expected] != [_normal(s[2]) for s in slots]:
            raise UnsupportedText('页面文案与源文件不一致，可能由程序生成，请使用 AI 修改')
        return slots


def _page(root, page_id):
    root = Path(root).resolve()
    if proto_meta.is_linked_path(root): raise ValueError('不能修改链接目录中的原型')
    bundle = proto_meta.load_bundle(root)
    page = next((p for p in bundle['project']['pages'] if p['id'] == page_id and not p.get('trashedAt')), None)
    if page is None: raise ValueError('页面不存在或已在回收站')
    path = proto_meta.safe_asset(root, page['file'])
    if path.suffix.lower() not in {'.html', '.htm'} or proto_meta.is_linked_path(root / page['file']): raise ValueError('只能修改项目内的真实 HTML 文件')
    data = path.read_bytes()
    if len(data) > 4 * 1024 * 1024: raise UnsupportedText('页面较大，请使用 AI 修改')
    try: source = Source(data.decode('utf-8'))
    except UnicodeError as error: raise UnsupportedText('当前文件编码不支持手动修改，请使用 AI 修改') from error
    return path, page['file'], data, source


def _history(root, create=False):
    folder = Path(root) / '.prototype' / 'text-edits'
    if proto_meta.is_linked_path(folder): raise ValueError('文案修改记录不能存放在链接目录')
    if create: folder.mkdir(parents=True, exist_ok=True)
    return folder


def _last_undo(root, file, digest):
    folder = _history(root)
    if not folder.exists(): return None
    for path in sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        if path.is_symlink(): continue
        record = proto_meta.read_json(path, {})
        if record.get('file') == file and record.get('afterHash') == digest: return path.stem
    return None


def _runtime_block(source):
    text = source.text
    if RUNTIME_START not in text and RUNTIME_END not in text: return None, []
    if text.count(RUNTIME_START) != 1 or text.count(RUNTIME_END) != 1:
        raise UnsupportedText('手动文案记录有冲突，请使用 AI 检查后再修改')
    start = text.index(RUNTIME_START); end = text.index(RUNTIME_END) + len(RUNTIME_END)
    block = text[start:end]
    match = re.search(r'<script type="application/json" id="proto-text-edits-data">(.*?)</script>', block, re.S)
    try:
        rules = json.loads(match[1]) if match else None
        if not isinstance(rules, list) or len(rules) > 200: raise ValueError()
        for rule in rules:
            if not isinstance(rule, dict): raise ValueError()
            _binding(rule.get('binding'))
            if not all(isinstance(rule.get(k), list) and 1 <= len(rule[k]) <= 8 and
                       all(isinstance(t, str) and len(t) <= 4096 for t in rule[k]) for k in ('before', 'after')):
                raise ValueError()
            if len(rule['before']) != len(rule['after']): raise ValueError()
    except (ValueError, TypeError, KeyError) as error:
        raise UnsupportedText('手动文案记录无法读取，请使用 AI 检查后再修改') from error
    return (start, end), rules


def _binding(value):
    if not isinstance(value, dict) or not isinstance(value.get('anchor'), dict): raise ValueError('控件位置无效')
    def part(raw, anchor=False):
        if not isinstance(raw, dict) or not isinstance(raw.get('tag'), str) or not re.fullmatch('[a-z][a-z0-9-]{0,39}', raw['tag']) or raw['tag'] in BLOCKED:
            raise ValueError('控件位置无效')
        if anchor and raw == {'tag': 'body'}: return {'tag': 'body'}
        key, value = raw.get('key'), raw.get('value')
        if key:
            if not isinstance(key, str) or key not in ({'id', 'data-proto-id'} if anchor else KEYS) or not isinstance(value, str) or not 1 <= len(value) <= 256 or '\0' in value:
                raise ValueError('控件标识无效')
            return {'tag': raw['tag'], 'key': key, 'value': value}
        if not anchor and 'column' in raw:
            column = raw['column']
            if raw['tag'] not in {'td', 'th'} or not isinstance(column, list) or not 1 <= len(column) <= 8 or not all(isinstance(t, str) and 0 < len(t) <= 256 and '\0' not in t for t in column):
                raise ValueError('列标题无效')
            return {'tag': raw['tag'], 'column': column}
        if not anchor and 'text' in raw:
            text = raw['text']
            if not isinstance(text, str) or not 0 < len(text) <= 160 or '\0' in text: raise ValueError('控件文案特征无效')
            return {'tag': raw['tag'], 'text': text}
        if not anchor and 'match' in raw:
            criteria = raw['match']
            if not isinstance(criteria, list) or not 1 <= len(criteria) <= 3: raise ValueError('条目特征无效')
            clean = []
            for criterion in criteria:
                if not isinstance(criterion, dict) or not isinstance(criterion.get('text'), str) or not 0 < len(criterion['text']) <= 160 or '\0' in criterion['text']:
                    raise ValueError('条目特征无效')
                path = criterion.get('path')
                if not isinstance(path, list) or len(path) > 3 or not path and criterion.get('own') is not True: raise ValueError('条目特征位置无效')
                if any(not isinstance(p, dict) or set(p) != {'tag', 'index'} for p in path): raise ValueError('条目特征位置无效')
                steps = [part(p) for p in path]
                clean.append({'path': steps, **({'own': True} if criterion.get('own') is True else {}), 'text': criterion['text']})
            return {'tag': raw['tag'], 'match': clean}
        if anchor or type(raw.get('index')) is not int or not 1 <= raw['index'] <= 10000: raise ValueError('控件位置无效')
        return {'tag': raw['tag'], 'index': raw['index']}
    path = value.get('path')
    if not isinstance(path, list) or not 1 <= len(path) <= 16: raise ValueError('控件位置无效')
    return {'anchor': part(value['anchor'], True), 'path': [part(p) for p in path]}


def _source_text(source, node, own=False):
    texts = []
    for child in node.children:
        if isinstance(child, tuple): texts.append(html.unescape(source.text[child[0]:child[1]]))
        elif not own and child.tag not in BLOCKED: texts.append(_source_text(source, child))
    return _normal(' '.join(texts))


def _source_matches(source, node, criteria):
    for criterion in criteria:
        selected = node
        for step in criterion['path']:
            found = [n for n in selected.children if isinstance(n, Node) and n.tag == step['tag']]
            if step['index'] > len(found): return False
            selected = found[step['index']-1]
        if _source_text(source, selected, criterion.get('own', False)) != criterion['text']: return False
    return True


def _plan(source, target):
    # Keep static matching strict; runtime overrides require a key or semantic landmark
    # absent from the source, never hide mismatched static text or framework bindings.
    try: return source.resolve(target), None, []
    except UnsupportedText as original:
        if not isinstance(target, dict) or not isinstance(target.get('tag'), str) or target['tag'] not in ALLOWED or target.get('reactive'): raise original
        expected, candidates = target.get('texts'), target.get('bindings')
        if not isinstance(expected, list) or not 1 <= len(expected) <= 8 or not all(isinstance(t, str) and t.strip() and len(t) <= 4096 for t in expected): raise original
        if not isinstance(candidates, list) or len(candidates) > 12: raise original
        _, rules = _runtime_block(source)
        for raw in candidates:
            try: binding = _binding(raw)
            except ValueError: continue
            if binding['path'][-1]['tag'] != target['tag']: continue
            anchor = binding['anchor']
            found = [n for n in source.nodes if n.tag == anchor['tag'] and (not anchor.get('key') or n.attrs.get(anchor['key']) == anchor['value'])]
            if len(found) != 1: continue
            node = found[0]; generated = False
            ancestor = node
            while ancestor:
                if ancestor.tag in BLOCKED or any(k in DYNAMIC for k in ancestor.attrs): break
                ancestor = ancestor.parent
            if ancestor: continue
            for step in binding['path']:
                children = [n for n in node.children if isinstance(n, Node) and n.tag == step['tag']]
                if step.get('key'):
                    children = [n for n in children if n.attrs.get(step['key']) == step['value']]
                    if not children: generated = True; break
                    if len(children) != 1: break
                    node = children[0]
                elif step.get('match'):
                    found = [n for n in children if _source_matches(source, n, step['match'])]
                    if not found: generated = True; break
                    if len(found) != 1: break
                    node = found[0]
                elif step.get('text'):
                    found = [n for n in children if _source_text(source, n) == step['text']]
                    if not found: generated = True; break
                    if len(found) != 1: break
                    node = found[0]
                elif step.get('column'): break
                elif step['index'] <= len(children): node = children[step['index']-1]
                else: break  # Ordinal-only generated nodes are not stable enough.
                if node.tag in BLOCKED or any(k in DYNAMIC for k in node.attrs): break
            if not generated: continue
            existing = next((r for r in rules if r['binding'] == binding), None)
            if existing and [_normal(t) for t in expected] != [_normal(t) for t in existing['after']]:
                raise UnsupportedText('页面文案与已保存的修改不一致，请重新加载后选择')
            return [(None, None, t) for t in expected], binding, rules
        raise original


def _save_runtime(source, binding, rules, before_fields, fields):
    span, _ = _runtime_block(source)
    existing = next((r for r in rules if r['binding'] == binding), None)
    rule = {'binding': binding, 'before': existing['before'] if existing else before_fields, 'after': [f['text'] for f in fields]}
    updated = [r for r in rules if r['binding'] != binding]
    if rule['before'] != rule['after']: updated.append(rule)
    if len(updated) > 200: raise UnsupportedText('手动修改较多，请使用 AI 整理页面源码')
    block = ''
    if updated:
        # JSON text is data, never executable markup; the runtime itself is bundled
        # inline so local files, pure exports and GitHub Pages behave identically.
        data = json.dumps(updated, ensure_ascii=False, separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
        runtime = (Path(__file__).parent / 'src' / 'proto-text-runtime.js').read_text(encoding='utf-8')
        block = RUNTIME_START + '<script type="application/json" id="proto-text-edits-data">' + data + '</script>\n<script data-proto-text-runtime>\n' + runtime + '\n</script>' + RUNTIME_END
    if span: return source.text[:span[0]] + block + source.text[span[1]:], updated
    closing = list(re.finditer(r'</body\s*>', source.text, re.I))
    index = closing[-1].start() if closing else len(source.text)
    return source.text[:index] + block + source.text[index:], updated


def upgrade_runtime_html(text):
    """在工作台响应中升级旧内嵌运行代码，不改项目源码和修改记录。"""
    if RUNTIME_START not in text: return text
    try: span, _ = _runtime_block(Source(text))
    except UnsupportedText: return text
    if span is None: return text
    runtime = (Path(__file__).parent / 'src' / 'proto-text-runtime.js').read_text(encoding='utf-8')
    block = re.sub(r'<script data-proto-text-runtime>.*?</script>', lambda _: '<script data-proto-text-runtime>\n' + runtime + '\n</script>', text[span[0]:span[1]], count=1, flags=re.S)
    return text[:span[0]] + block + text[span[1]:]


def inspect_text(root, page_id, target):
    with proto_meta.PROJECT_LOCK:
        _, file, data, source = _page(root, page_id)
        slots, _, _ = _plan(source, target); digest = _hash(data)
        return {'ok': True, 'file': file, 'hash': digest, 'fields': [{'slot': i, 'text': slot[2]} for i, slot in enumerate(slots)], 'undoId': _last_undo(root, file, digest)}


def _write(path, data, expected_hash):
    fd, temporary = tempfile.mkstemp(prefix='.text-edit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode)
        if _hash(path.read_bytes()) != expected_hash: raise EditConflict('源文件已被其他工具修改，请重新选择后再保存')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def save_text(root, page_id, target, expected_hash, edits):
    with proto_meta.PROJECT_LOCK:
        path, file, before, source = _page(root, page_id)
        if _hash(before) != expected_hash: raise EditConflict('源文件已变化，请重新选择后再保存')
        slots, binding, rules = _plan(source, target)
        if not isinstance(edits, list) or not 1 <= len(edits) <= len(slots): raise ValueError('修改内容无效')
        replacements, used = [], set()
        fields = [{'slot': i, 'text': slot[2]} for i, slot in enumerate(slots)]
        for edit in edits:
            if not isinstance(edit, dict): raise ValueError('修改内容无效')
            index, value = edit.get('slot'), edit.get('text')
            if type(index) is not int or index not in range(len(slots)) or index in used or not isinstance(value, str) or len(value) > 4096 or '\0' in value: raise ValueError('修改内容无效')
            used.add(index); start, end, _ = slots[index]
            if binding is None:
                raw = source.text[start:end]; leading = re.match(r'\s*', raw).group(); trailing = re.search(r'\s*$', raw).group()
                replacements.append((start, end, leading + html.escape(value, quote=False) + trailing))
            fields[index]['text'] = value
        after = source.text
        for start, end, value in sorted(replacements, reverse=True): after = after[:start] + value + after[end:]
        extra = {}
        if binding:
            after, updated = _save_runtime(source, binding, rules, [s[2] for s in slots], fields)
            extra['runtimeEdits'] = updated
        data = after.encode('utf-8'); digest = _hash(data)
        if data == before: return {'ok': True, 'file': file, 'hash': digest, 'fields': fields, 'undoId': _last_undo(root, file, digest), **extra}
        ticket = uuid.uuid4().hex
        proto_meta.write_json_atomic(_history(root, True) / (ticket + '.json'), {'file': file, 'beforeHash': _hash(before), 'afterHash': digest, 'before': base64.b64encode(before).decode('ascii')})
        _write(path, data, expected_hash)
        return {'ok': True, 'file': file, 'hash': digest, 'fields': fields, 'undoId': ticket, **extra}


def undo_text(root, page_id, undo_id, expected_hash):
    with proto_meta.PROJECT_LOCK:
        if not isinstance(undo_id, str) or not re.fullmatch('[0-9a-f]{32}', undo_id): raise ValueError('撤销记录无效')
        path, file, current, _ = _page(root, page_id)
        record = proto_meta.read_json(_history(root) / (undo_id + '.json'), {})
        if record.get('file') != file or _hash(current) != expected_hash or record.get('afterHash') != expected_hash:
            raise EditConflict('文件已变化，不能覆盖后续修改；请重新选择')
        try: before = base64.b64decode(record['before'], validate=True)
        except (KeyError, ValueError) as error: raise ValueError('撤销记录损坏') from error
        if _hash(before) != record.get('beforeHash'): raise ValueError('撤销记录校验失败')
        _write(path, before, expected_hash)
        return {'ok': True, 'file': file, 'hash': _hash(before)}
