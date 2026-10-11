"""Local, read-only project cover rendering. No account state or business requests."""
from pathlib import Path
import hashlib
import mimetypes
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse

BASE = Path(__file__).resolve().parent
CACHE = BASE / 'data' / 'home-thumbnails'
discovered = {}
_jobs = {}
_lock = threading.Lock()
_queue = queue.Queue(maxsize=64)
_started = False


def fingerprint(root, entry):
    import proto_meta
    root = Path(root).resolve()
    digest = hashlib.sha256(('home-cover-v1:' + str(root) + ':' + entry).encode())
    count = 0
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in
                         {'node_modules', 'exports', 'dist', 'build', 'venv', '__pycache__'}
                         and not proto_meta.is_directory_link(Path(current) / d))
        for name in sorted(names):
            file = Path(current) / name
            if file.is_symlink() or file.suffix.lower() not in {'.html', '.css', '.js', '.json', '.png', '.jpg', '.svg', '.webp'}:
                continue
            try:
                stat = file.stat()
                digest.update(f'{file.relative_to(root)}:{stat.st_mtime_ns}:{stat.st_size}'.encode())
                count += 1
                if count >= 1500:
                    return digest.hexdigest()
            except OSError:
                continue
    return digest.hexdigest()


def _worker():
    while True:
        key, root, entry = _queue.get()
        output = CACHE / (key + '.png')
        temp = CACHE / (key + '.working.png')
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--capture',
                                     str(root), entry, str(temp)], cwd=str(BASE), timeout=28,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode != 0 or not temp.is_file():
                raise RuntimeError('cover rendering unavailable')
            temp.replace(output)
            with _lock:
                _jobs[key] = ('ready', time.monotonic())
        except Exception:
            with _lock:
                _jobs[key] = ('unavailable', time.monotonic())
        finally:
            if temp.exists():
                temp.unlink()
            _queue.task_done()


def request(root, entry):
    global _started
    key = fingerprint(root, entry)
    target = CACHE / (key + '.png')
    if target.is_file():
        return 'ready', target
    with _lock:
        state, stamp = _jobs.get(key, ('missing', 0))
        if state == 'unavailable' and time.monotonic() - stamp < 120:
            return state, None
        if state == 'pending':
            return state, None
        if not _started:
            for _ in range(2):
                threading.Thread(target=_worker, daemon=True).start()
            _started = True
        try:
            _queue.put_nowait((key, Path(root).resolve(), entry))
        except queue.Full:
            return 'busy', None
        _jobs[key] = ('pending', time.monotonic())
    return 'pending', None


def capture(root, entry, output):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    import proto_meta

    root = Path(root).resolve()
    source = proto_meta.safe_asset(root, entry).read_text(encoding='utf-8', errors='replace')
    mobile = bool(re.search(r'data-proto-preview=[\"\']mobile|(?:max-width|width)\s*:\s*(?:390|375|414|430)px', source, re.I))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 390 if mobile else 1280, 'height': 780 if mobile else 720},
                                      reduced_motion='reduce', service_workers='block')
        context.add_init_script("window.WebSocket = class { constructor() { throw new Error('Offline cover'); } }; window.EventSource = window.WebSocket;")

        def serve(route):
            req = route.request
            url = urllib.parse.urlsplit(req.url)
            if req.method != 'GET':
                route.abort(); return
            try:
                if url.hostname == 'prototype.invalid':
                    relative = urllib.parse.unquote(url.path).lstrip('/') or entry
                    asset = proto_meta.safe_asset(root, relative)
                    if asset.suffix.lower() not in {'.html', '.css', '.js', '.mjs', '.json', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.woff', '.woff2', '.ttf'}:
                        route.abort(); return
                    route.fulfill(content_type=mimetypes.guess_type(str(asset))[0] or 'application/octet-stream', body=asset.read_bytes())
                elif url.hostname == 'cdn.tailwindcss.com':
                    route.fulfill(content_type='application/javascript', body=(BASE / 'src/vendor/tailwind-runtime.js').read_bytes())
                elif url.hostname == 'cdnjs.cloudflare.com' and '/font-awesome/' in url.path:
                    name = url.path.rsplit('/', 1)[-1]
                    asset = BASE / 'src/vendor/fontawesome' / ('css' if name == 'all.min.css' else 'webfonts') / name
                    if name not in {'all.min.css', 'fa-solid-900.woff2', 'fa-regular-400.woff2', 'fa-brands-400.woff2'}:
                        route.abort(); return
                    route.fulfill(content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream', body=asset.read_bytes())
                else:
                    route.abort()
            except (OSError, ValueError):
                route.abort()

        context.route('**/*', serve)
        page = context.new_page()
        page.goto('http://prototype.invalid/' + urllib.parse.quote(entry, safe='/'), wait_until='networkidle', timeout=18000)
        page.evaluate('() => document.fonts.ready')
        page.wait_for_timeout(350)
        if not page.locator('body').inner_text().strip() and not page.locator('body img, body canvas, body svg').count():
            raise RuntimeError('No rendered content')
        page.screenshot(path=output, animations='disabled')
        context.close(); browser.close()
    with Image.open(output) as image:
        if mobile:
            cover = Image.new('RGB', (1280, 640), '#eaf0f4')
            image = image.convert('RGB'); image.thumbnail((330, 608), Image.Resampling.LANCZOS)
            cover.paste(image, ((1280 - image.width) // 2, (640 - image.height) // 2))
        else:
            cover = image.convert('RGB').crop((0, 0, 1280, 640))
        cover.save(output, optimize=True)


if __name__ == '__main__' and len(sys.argv) == 5 and sys.argv[1] == '--capture':
    capture(*sys.argv[2:])
