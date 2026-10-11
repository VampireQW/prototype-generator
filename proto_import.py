"""PRD 草稿落库：把 Agent 写出的 .prototype/prd.draft.json 确定性地写进 .prototype 三文件。

为什么要有这一步：Agent 写 PRD 是判断活（哪条该做序号、哪条该进页面说明），落库是结构活
（anchor 字段、编号、三文件同 revision、confirmed 保护）。让 Agent 直接手改 prd.json 会错字段、
撞 revision、漏校验；这里只认草稿，其余全部由代码推导。

草稿格式（schemaVersion 1）：
{
  "schemaVersion": 1,
  "pages": [{
    "file": "index.html",            # 或 "pageId": "home"；file 优先，按登记表 casefold 匹配
    "stateId": "default",            # 可省，默认 default；必须是该页已登记的状态
    "document": "## 一、需求描述\\n...\\n## 二、研发实现\\n...",   # 可省
    "annotations": [{ "protoId": "btn-refresh", "body": "点击后……" }]  # 可省
  }],
  "unknowns": ["……"]                 # 待确认清单，只回显不落库
}

规则：
- protoId 必须在该页 HTML 中恰好出现一次，否则整份草稿不落库（--skip-missing 改为跳过并报告）。
- 同页同状态已有相同 protoId 的标注 → 跳过（重复导入幂等）。
- 页面文档：目标已有非空正文 → 跳过（--replace-doc 才覆盖）；confirmed 的文档永不覆盖。
- 新标注 confirmed:false，落点在元素左侧中点（rx=0, ry=0.5），用户可在工作台拖动。
- 成功后三文件 revision +1，草稿移入 .prototype/imported/ 留档。

用法：
  python proto_import.py <项目根 | p-xxxx 登记ID> [草稿路径] [--dry-run] [--skip-missing] [--replace-doc]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proto_meta  # noqa: E402

DRAFT_VERSION = 1
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

def _page_lookup(bundle: dict[str, Any], entry: dict[str, Any], where: str) -> dict[str, Any]:
    pages = bundle['project']['pages']
    file = entry.get('file')
    if file:
        rel = str(file).replace('\\', '/').casefold()
        page = next((p for p in pages if str(p.get('file', '')).casefold() == rel), None)
        if not page:
            raise ImportError_(f'{where}：文件 {file} 未登记为页面（先在工作台打开一次让它登记，或改用已登记的 pageId）')
        return page
    pid = entry.get('pageId')
    page = next((p for p in pages if p['id'] == pid), None)
    if not page:
        raise ImportError_(f'{where}：pageId {pid!r} 不存在；已登记：{", ".join(p["id"] for p in pages)}')
    return page


def _state_check(page: dict[str, Any], state_id: str, where: str) -> None:
    if not any(s['id'] == state_id for s in page.get('states', [])):
        raise ImportError_(f'{where}：页面 {page["id"]} 没有状态 {state_id!r}；已登记：{", ".join(s["id"] for s in page["states"])}')


def load_draft(path: Path) -> dict[str, Any]:
    try:
        draft = json.loads(path.read_text(encoding='utf-8'))
    except OSError as error:
        raise ImportError_(f'草稿读取失败：{error}') from error
    except ValueError as error:
        raise ImportError_(f'草稿不是合法 JSON：{error}') from error
    if not isinstance(draft, dict) or draft.get('schemaVersion') != DRAFT_VERSION:
        raise ImportError_(f'草稿 schemaVersion 必须为 {DRAFT_VERSION}')
    if not isinstance(draft.get('pages'), list) or not draft['pages']:
        raise ImportError_('草稿 pages 为空')
    for i, entry in enumerate(draft['pages']):
        where = f'pages[{i}]'
        if not isinstance(entry, dict) or not (entry.get('file') or entry.get('pageId')):
            raise ImportError_(f'{where}：缺 file 或 pageId')
        if entry.get('document') is not None and not isinstance(entry['document'], str):
            raise ImportError_(f'{where}：document 必须是 Markdown 字符串')
        notes = entry.get('annotations')
        if notes is None:
            notes = []
        if not isinstance(notes, list):
            raise ImportError_(f'{where}：annotations 必须是数组')
        for j, note in enumerate(notes):
            if not isinstance(note, dict) or not str(note.get('protoId', '')).strip() or not str(note.get('body', '')).strip():
                raise ImportError_(f'{where}.annotations[{j}]：protoId 与 body 都不能为空')
    if draft.get('unknowns') is not None and not isinstance(draft['unknowns'], list):
        raise ImportError_('unknowns 必须是数组')
    return draft


# ---------- 落库 ----------

def import_draft(root: Path, draft: dict[str, Any], *, replace_doc: bool = False,
                 skip_missing: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """把草稿合入 bundle。返回报告；除 dry_run 外成功即落盘（revision +1）。"""
    root = Path(root).resolve()
    bundle = proto_meta.ensure_bundle(root)
    proto_meta.ensure_pages_registered(root, bundle)
    report: dict[str, Any] = {'root': str(root), 'projectId': bundle['project']['id'], 'revisionBefore': bundle['revision'],
                              'documents': [], 'annotations': [], 'skipped': [], 'warnings': [], 'unknowns': list(draft.get('unknowns') or [])}
    problems: list[str] = []
    now = proto_meta.now_iso()

    for i, entry in enumerate(draft['pages']):
        where = f'pages[{i}]'
        page = _page_lookup(bundle, entry, where)
        state_id = str(entry.get('stateId') or 'default')
        _state_check(page, state_id, where)
        scope = f'{page["id"]}/{state_id}'

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
        if not notes:
            continue
        try:
            html = proto_meta.safe_asset(root, page['file']).read_text(encoding='utf-8', errors='replace')
        except (ValueError, FileNotFoundError) as error:
            raise ImportError_(f'{where}：读不到页面文件 {page["file"]}：{error}') from error
        ids = scan_proto_ids(html)
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
                report['skipped'].append(f'{scope} 已有绑定 {pid} 的标注，跳过重复导入')
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

    if problems:
        raise ImportError_('草稿未落库，请先修正：\n  - ' + '\n  - '.join(problems))
    changed = bool(report['documents'] or report['annotations'])
    report['changed'] = changed
    report['dryRun'] = dry_run
    if changed and not dry_run:
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
    lines = [f'项目 {report["projectId"]}  {report["root"]}']
    lines.append(f'revision {report["revisionBefore"]} → {report["revisionAfter"]}' + ('（dry-run，未写入）' if report['dryRun'] else ''))
    for d in report['documents']:
        lines.append(f'  文档  {d["scope"]}  {"覆盖" if d["action"] == "replaced" else "新建"}')
    for a in report['annotations']:
        lines.append(f'  标注  {a["scope"]}  #{a["number"]}  {a["protoId"]}  <{a["tag"]}> {a["text"]}')
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
    args = ap.parse_args(argv)
    try:
        root = resolve_root(args.project)
        draft_path = Path(args.draft).resolve() if args.draft else proto_meta.meta_dir(root) / DRAFT_NAME
        draft = load_draft(draft_path)
        report = import_draft(root, draft, replace_doc=args.replace_doc, skip_missing=args.skip_missing, dry_run=args.dry_run)
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
