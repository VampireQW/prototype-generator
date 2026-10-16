"""Register a portable manifest and optionally build its declared index launcher."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode, urlsplit


def main():
    parser = argparse.ArgumentParser(description='登记多端页面清单，可生成共用导航演示入口')
    parser.add_argument('project', help='原型项目根目录')
    parser.add_argument('--tool-root', default=os.environ.get('PROTOTYPE_GENERATOR_ROOT', ''), help='原型生成器工具仓库目录')
    parser.add_argument('--dry-run', action='store_true', help='只校验清单，不建立元数据或修改文件')
    parser.add_argument('--build-launcher', action='store_true', help='更新明确声明为 launcher 的 index.html 和导航资源')
    parser.add_argument('--viewer-origin', default='http://localhost:8080', help='工作台实际来源，用于生成页面直达链接')
    args = parser.parse_args()
    tool = Path(args.tool_root).expanduser().resolve() if args.tool_root else None
    if not tool or not (tool / 'prototype_manifest.py').is_file():
        parser.error('请提供新版原型生成器的 --tool-root，或设置 PROTOTYPE_GENERATOR_ROOT')
    sys.path.insert(0, str(tool))
    import proto_meta
    import prototype_manifest
    root = Path(args.project).expanduser().resolve()
    try:
        origin = urlsplit(args.viewer_origin)
        if origin.scheme not in ('http', 'https') or not origin.netloc or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
            raise ValueError('viewer-origin 须为工作台实际 HTTP(S) 来源')
        declaration = prototype_manifest.load_manifest(root)
        if not declaration:
            raise ValueError('项目根缺少 prototype.manifest.json；先根据实际页面填写清单')
        if args.dry_run:
            print(json.dumps({'ok': True, 'dryRun': True, 'pages': len(declaration['pages']), 'clients': len(declaration.get('clients', []))}, ensure_ascii=False))
            return 0
        bundle = proto_meta.ensure_bundle(root)
        proto_meta.ensure_pages_registered(root, bundle)
        files = prototype_manifest.build_launcher(root, bundle) if args.build_launcher else []
        viewer = args.viewer_origin.rstrip('/') + '/src/viewer.html'
        print(json.dumps({'ok': True, 'projectId': bundle['project']['id'], 'projectName': bundle['project'].get('name') or root.name, 'revision': bundle['revision'],
                          'viewerUrl': viewer + '?' + urlencode({'ext': bundle['project']['id']}),
                          'pages': [{'pageId': page['id'], 'pageTitle': page.get('title') or page['id'], 'file': page['file'],
                                     'viewerUrl': viewer + '?' + urlencode({'ext': bundle['project']['id'], 'page': page['id'], 'state': page['states'][0]['id'], 'mode': 'annotate'})}
                                    for page in bundle['project']['pages'] if not page.get('trashedAt') and page.get('role') != 'launcher'],
                          'defaultPage': bundle['project'].get('defaultPage'), 'modifiedFiles': files,
                          'registeredInHomepage': '首页添加本地项目后可见'}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
