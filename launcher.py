"""Prepare a project-local Python environment and launch the workbench."""
import argparse
import hashlib
import importlib
import importlib.metadata
import os
import re
import subprocess
import sys
import venv
from pathlib import Path

import app_runtime


ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)


def utf8_environment():
    return {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8:backslashreplace'}


def dependencies_ready(root):
    """Verify the pinned runtime packages, even when an old success stamp exists."""
    try:
        for line in (root / 'requirements.txt').read_text(encoding='utf-8-sig').splitlines():
            line = line.partition('#')[0].strip()
            if not line:
                continue
            match = re.fullmatch(r'([\w.-]+)==([\w.+-]+)', line)
            if not match or importlib.metadata.version(match[1]) != match[2]:
                return False
        importlib.import_module('requests')
        importlib.import_module('PIL.Image')
    except (ImportError, importlib.metadata.PackageNotFoundError, OSError):
        return False
    return True


def install_dependencies(root, *, allow_install=True):
    requirements = root / 'requirements.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = root / '.venv' / '.requirements.sha256'
    ready = dependencies_ready(root)
    if not allow_install:
        if not ready:
            raise RuntimeError('核心依赖未安装或版本不符，请联网运行 launcher.py 后再使用 --no-install。')
        return
    if ready and stamp.is_file() and stamp.read_text(encoding='ascii').strip() == digest:
        return
    print('[SETUP] 正在安装核心依赖（首次启动或依赖更新时需要联网）...', flush=True)
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pip', 'install',
                             '--disable-pip-version-check', '-r', str(requirements)],
                            cwd=root, env=utf8_environment())
    if result.returncode != 0 or not dependencies_ready(root):
        raise RuntimeError('依赖安装失败；请检查上方 pip 报错、网络或代理，恢复后再次启动即可重试。')
    stamp.write_text(digest + '\n', encoding='ascii')


def main(argv=None):
    app_runtime.configure_utf8_output()
    parser = argparse.ArgumentParser(description='准备本地依赖并启动原型工作台')
    parser.add_argument('--open-browser', action='store_true', help='服务启动成功后打开浏览器')
    parser.add_argument('--check', action='store_true', help='只检查并准备运行环境，不启动服务')
    parser.add_argument('--no-install', action='store_true', help='离线检查已有环境，不创建环境或安装依赖')
    args = parser.parse_args(argv)
    if sys.version_info < MIN_PYTHON:
        print('[ERROR] 需要 Python 3.10 或更高版本，请安装后重新启动。', file=sys.stderr)
        return 1
    try:
        environment = ROOT / '.venv'
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if Path(sys.prefix).resolve() != environment.resolve():
            if not python.is_file():
                if args.no_install:
                    raise RuntimeError('尚无 .venv 运行环境，请先联网运行 launcher.py。')
                print('[SETUP] 正在创建项目独立 Python 环境 .venv ...', flush=True)
                venv.EnvBuilder(with_pip=True).create(environment)
            forwarded = list(argv) if argv is not None else sys.argv[1:]
            return subprocess.run([str(python), '-X', 'utf8', str(ROOT / 'launcher.py'), *forwarded],
                                  cwd=ROOT, env=utf8_environment()).returncode
        install_dependencies(ROOT, allow_install=not args.no_install)
        for name in ('config', 'models'):
            app_runtime.load_local_json(ROOT / (name + '.json'), template=ROOT / (name + '.example.json'))
        if args.check:
            print('[OK] 运行环境和本机配置已就绪。')
            return 0
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'server.py')]
        if args.open_browser:
            command.append('--open-browser')
        return subprocess.run(command, cwd=ROOT, env=utf8_environment()).returncode
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'[ERROR] {error}', file=sys.stderr)
        print('可在命令行运行 python -X utf8 launcher.py --check 查看并重试；已有配置不会被覆盖。', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
