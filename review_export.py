"""评审壳导出构建：把已登记项目打包成 GitHub Pages 可托管的静态评审站。

产物结构：
    out_dir/
        index.html   评审壳（src/review_shell.html 填充 bundle）
        proto/       项目原型文件副本（排除隐藏项与产物目录），业务脚本前加载热区模块，
                     HTML 尾部内嵌色板 / 锚点 / 顺序 / 桥 / 气泡脚本——壳与 iframe 只走
                     postMessage，file:// 双击打开（每个文件独立源）也能显示序号与引导

纯函数模块，不 import server.py（其模块级起服务）；复制规则与全流程
copy_source 对齐（跳过点开头项与 EXCLUDED 名，拒绝越出项目根的链接目标）。
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SHELL_TEMPLATE = BASE_DIR / "src" / "review_shell.html"
# 顺序即加载顺序：anchors 提供定位 → order 提供页面排序 → bridge 建 __REVIEW__ 并握手 → pins 画气泡
PIN_SCRIPTS = (
    ("appearance", "proto-appearance.js"),
    ("anchors", "proto-anchors.js"),
    ("order", "proto-order.js"),
    ("bridge", "review-bridge.js"),
    ("pins", "review-pins.js"),
)
BUNDLE_MARK = "<!-- proto-review-bundle -->"
HOTSPOT_SCRIPT = ('hotspots', 'proto-hotspots.js')
HTML_SUFFIXES = (".html", ".htm")

IGNORE_NAMES = {".prototype", "exports", "dist", ".git", "node_modules", "__pycache__"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 与 GitHub Contents API 单文件上限一致


def copy_proto(root: Path, dest: Path, *, ai_project: bool = False) -> list[str]:
    """复制项目文件到 dest，返回 POSIX 相对路径清单（已排序，便于断言）。"""
    copied: list[str] = []
    root_resolved = root.resolve()
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root)
        if ai_project and (
            (len(rel.parts) == 1 and rel.name.casefold() in {'record.json', 'prompt.full.md', 'task.md', 'agents.md', 'design.md'})
            or rel.parts[0].casefold() == 'prd'
            or (rel.parts[0].casefold() == 'pages' and rel.suffix.casefold() == '.md')
        ):
            continue
        if any(part in IGNORE_NAMES or (part.startswith(".") and part != ".well-known") for part in rel.parts):
            continue
        try:
            resolved = item.resolve()
            if root_resolved not in resolved.parents or any(
                p.startswith(".") or p.casefold() in IGNORE_NAMES
                for p in resolved.relative_to(root_resolved).parts
            ):
                continue
        except (ValueError, OSError):
            continue
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and item.stat().st_size <= MAX_FILE_SIZE:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied.append(rel.as_posix())
    return copied


def review_data(bundle: dict, published_at: str) -> dict:
    """评审壳嵌入数据：只含展示所需字段（不导出 changes 任务列表）。"""
    project = bundle.get("project") or {}
    prd = bundle.get("prd") or {}
    return {
        "name": project.get("name", "原型项目"),
        "projectId": project.get("id", ""),
        **({'previewType': project['previewType']} if project.get('previewType') in ('mobile', 'web') else {}),
        "revision": bundle.get("revision", 0),
        "publishedAt": published_at,
        "pages": project.get("pages", []),
        "documents": prd.get("documents", []),
        "annotations": prd.get("annotations", []),
    }


def render_shell(template: str, data: dict) -> str:
    """填充模板占位符：数据 JSON 转义 </ 防 </script> 截断。"""
    for placeholder in ("__PROJECT_TITLE__", "__REVIEW_DATA__"):
        if placeholder not in template:
            raise ValueError(f"评审壳模板缺少占位符 {placeholder}")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = template.replace("__PROJECT_TITLE__", html.escape(str(data.get("name", "原型项目")), quote=True))
    return out.replace("__REVIEW_DATA__", payload)


def load_bundle_scripts() -> str:
    """按依赖顺序拼成内嵌 bundle（各自独立 <script>，保持文件内 'use strict' 与 IIFE 边界）。"""
    parts = [BUNDLE_MARK]
    for key, name in PIN_SCRIPTS:
        source = (BASE_DIR / "src" / name).read_text(encoding="utf-8")
        if "</script" in source.lower():
            raise ValueError(f"脚本 {name} 含 </script，无法内嵌")
        parts.append(f"<script data-proto-review=\"{key}\">\n{source}\n</script>")
    return "\n".join(parts) + "\n"


def inject_hotspot_bootstrap(text: str, *, inline: bool = False) -> str:
    """在首个业务脚本前载入热区模块，保留原始字符编码声明；不初始化提示 UI。"""
    marker = 'data-proto-hotspot-bootstrap'
    if marker in text or not re.search(r'<[a-zA-Z][^>]*>', text):
        return text
    if inline:
        key, name = HOTSPOT_SCRIPT
        source = (BASE_DIR / 'src' / name).read_text(encoding='utf-8')
        if '</script' in source.lower():
            raise ValueError(f'脚本 {name} 含 </script，无法内嵌')
        tag = f'<script data-prototype-owned {marker} data-proto-review="{key}">\n{source}\n</script>\n'
    else:
        tag = f'<script data-prototype-owned {marker} src="/src/proto-hotspots.js?v=20261005-real-actions-orange"></script>\n'
    first_script = re.search(r'<script\b', text, re.I)
    head_end = re.search(r'</head\s*>', text, re.I)
    positions = [match.start() for match in (first_script, head_end) if match]
    if positions:
        at = min(positions)
        return text[:at] + tag + text[at:]
    end = re.search(r'</(?:body|html)\s*>', text, re.I)
    if end:
        return text[:end.start()] + tag + text[end.start():]
    return text + '\n' + tag


def inject_bundle(text: str, bundle: str) -> str:
    """把 bundle 插到 </body> 前（大小写不敏感；无 body 则 </html> 前；再兜底追加）。已注入的跳过。"""
    if BUNDLE_MARK in text:
        return text
    lower = text.lower()
    for tag in ("</body>", "</html>"):
        at = lower.rfind(tag)
        if at >= 0:
            return text[:at] + bundle + text[at:]
    return text + "\n" + bundle


def inject_proto_scripts(proto_dir: Path, copied: list[str], project_bundle: dict | None = None) -> list[str]:
    """给 proto/ 下每个 HTML 副本内嵌 bundle；surrogateescape 保留非 UTF-8 字节原样。返回改过的文件。"""
    bundle = load_bundle_scripts()
    touched: list[str] = []
    for rel in copied:
        if not rel.lower().endswith(HTML_SUFFIXES):
            continue
        target = proto_dir / rel
        text = target.read_text(encoding="utf-8", errors="surrogateescape")
        scripts = bundle
        page = next((page for page in (project_bundle or {}).get('project', {}).get('pages', [])
                     if str(page.get('file', '')).replace('\\', '/').casefold() == rel.casefold()), None)
        if page and page.get('aiNavigation') == 'legacy':
            navigation = (BASE_DIR / 'src' / 'proto-navigation.js').read_text(encoding='utf-8')
            if '</script' in navigation.lower():
                raise ValueError('导航桥含 </script，无法内嵌')
            config = json.dumps({'pageId': page['id'], 'aiNavigation': page['aiNavigation'], 'states': page['states']}, ensure_ascii=False).replace('</', '<\\/')
            scripts = (BUNDLE_MARK + '\n<script data-proto-review="navigation-config">window.__PROTO_NAVIGATION__=' + config + ';</script>\n'
                       + '<script data-proto-review="navigation">\n' + navigation + '\n</script>\n' + bundle[len(BUNDLE_MARK):])
        out = inject_bundle(inject_hotspot_bootstrap(text, inline=True), scripts)
        if out != text:
            target.write_text(out, encoding="utf-8", errors="surrogateescape")
            touched.append(rel)
    return touched


def build_review_export(root: Path, bundle: dict, out_dir: Path, published_at: str | None = None) -> dict:
    """构建评审站到 out_dir（调用方保证 out_dir 为空或已清理）。返回产物清单。"""
    root = Path(root)
    out_dir = Path(out_dir)
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{root}")
    template = SHELL_TEMPLATE.read_text(encoding="utf-8")
    published = published_at or datetime.now(timezone.utc).isoformat()
    proto_dir = out_dir / "proto"
    proto_dir.mkdir(parents=True, exist_ok=True)
    copied = copy_proto(root, proto_dir, ai_project=(bundle.get('project') or {}).get('source') == 'ai')
    injected = inject_proto_scripts(proto_dir, copied, bundle)
    (out_dir / "index.html").write_text(
        render_shell(template, review_data(bundle, published)), encoding="utf-8"
    )
    return {
        "files": ["index.html", *(f"proto/{rel}" for rel in copied)],
        "publishedAt": published,
        "injected": [f"proto/{rel}" for rel in injected],
    }


def build_pure_export(root: Path, bundle: dict, out_dir: Path) -> dict:
    """纯净版构建：原型文件原样复制到站点根，并保证 index.html 入口存在。

    根目录已有 index.html 时直接作为入口；缺失时按页面登记（home 页优先，
    否则第一个登记页，再兜底清单里首个 HTML）生成 meta refresh 跳转页，
    保证 GitHub Pages / 任意静态托管打开站点根即可进入原型。
    """
    root = Path(root)
    out_dir = Path(out_dir)
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{root}")
    copied = copy_proto(root, out_dir, ai_project=(bundle.get('project') or {}).get('source') == 'ai')
    html_files = [rel for rel in copied if rel.lower().endswith(".html")]
    if not html_files:
        raise ValueError("项目里没有可发布的 HTML 页面")
    entry = "index.html"
    if not (out_dir / "index.html").is_file():
        pages = (bundle.get("project") or {}).get("pages") or []
        home = next((p for p in pages if p.get("id") == "home"), pages[0] if pages else None)
        target = ((home or {}).get("file") or html_files[0]).replace("\\", "/")
        entry = target
        redirect = (
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">'
            f"<title>原型入口</title></head>"
            f'<body><a href="{html.escape(target, quote=True)}">进入原型</a></body></html>'
        )
        (out_dir / "index.html").write_text(redirect, encoding="utf-8")
        copied.append("index.html")
    return {"files": sorted(copied), "entry": entry, "htmlCount": len(html_files)}
