"""全新检出、Windows 编码与重复启动的隔离回归。"""
import ast
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_runtime
import launcher


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-be', 'utf-32'])
def test_local_json_accepts_unicode_encodings_without_rewriting(tmp_path, encoding):
    path = tmp_path / '配置.json'
    data = {'server': {'port': 8080}, 'name': '同事的模型'}
    original = json.dumps(data, ensure_ascii=False).encode(encoding)
    path.write_bytes(original)
    assert app_runtime.load_local_json(path) == data
    assert path.read_bytes() == original


def test_missing_local_config_is_created_from_public_template(tmp_path):
    template = tmp_path / 'config.example.json'
    template.write_text('{"server":{"port":8080}}', encoding='utf-8')
    path = tmp_path / 'config.json'
    assert app_runtime.load_local_json(path, template=template) == {'server': {'port': 8080}}
    assert json.loads(path.read_bytes()) == {'server': {'port': 8080}}
    path.write_text('{"server":{"port":8097}}', encoding='utf-8')
    assert app_runtime.load_local_json(path, template=template)['server']['port'] == 8097


@pytest.mark.parametrize('raw', [b'{broken', b'[]', b'{"api_key":"private-value",bad}'])
def test_invalid_config_is_not_replaced_and_error_does_not_leak_values(tmp_path, raw):
    path = tmp_path / 'config.json'
    template = tmp_path / 'example.json'
    path.write_bytes(raw)
    template.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError) as error:
        app_runtime.load_local_json(path, template=template)
    assert 'config.json' in str(error.value)
    assert 'private-value' not in str(error.value)
    assert path.read_bytes() == raw


def test_utf8_output_works_when_windows_redirect_uses_ascii(monkeypatch):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding='ascii')
    monkeypatch.setattr(sys, 'stdout', stream)
    monkeypatch.setattr(sys, 'stderr', io.StringIO())
    app_runtime.configure_utf8_output()
    print('中文路径 / 已启动 ✓', flush=True)
    assert buffer.getvalue().decode('utf-8').strip() == '中文路径 / 已启动 ✓'


def test_server_config_and_models_can_boot_without_private_files(tmp_path, monkeypatch):
    import os
    for name in ('config', 'models'):
        (tmp_path / (name + '.example.json')).write_bytes((ROOT / (name + '.example.json')).read_bytes())
    tree = ast.parse((ROOT / 'server.py').read_text(encoding='utf-8'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'load_config', 'load_models', 'save_models', 'get_selected_model'}]
    namespace = {'os': os, 'json': json, 'app_runtime': app_runtime,
                 'CONFIG_FILE': 'config.json', 'MODELS_FILE': 'models.json'}
    monkeypatch.chdir(tmp_path)
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'server.py', 'exec'), namespace)
    assert namespace['load_config']()['server']['port'] == 8080
    assert namespace['load_models']()['models']
    for name in ('config.json', 'models.json'):
        raw = (tmp_path / name).read_bytes()
        (tmp_path / name).write_bytes(raw.decode('utf-8').encode('utf-16'))
    assert namespace['load_config']()['server']['port'] == 8080
    assert namespace['get_selected_model']()


def test_dependency_install_runs_once_and_repeats_on_requirements_change(tmp_path, monkeypatch):
    (tmp_path / '.venv').mkdir()
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text('requests==2.32.5\nPillow==12.2.0\n', encoding='utf-8')
    calls = []
    monkeypatch.setattr(launcher, 'dependencies_ready', lambda root: True)
    monkeypatch.setattr(launcher.subprocess, 'run', lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0))
    launcher.install_dependencies(tmp_path)
    launcher.install_dependencies(tmp_path)
    assert len(calls) == 1
    assert '-r' in calls[0]
    requirements.write_text(requirements.read_text() + '# update\n', encoding='utf-8')
    launcher.install_dependencies(tmp_path)
    assert len(calls) == 2


def test_failed_pip_install_is_retryable_and_does_not_create_success_stamp(tmp_path, monkeypatch):
    (tmp_path / '.venv').mkdir()
    (tmp_path / 'requirements.txt').write_text('requests==2.32.5\n', encoding='utf-8')
    monkeypatch.setattr(launcher, 'dependencies_ready', lambda root: False)
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **kw: calls.append(a) or SimpleNamespace(returncode=1))
    for _ in range(2):
        with pytest.raises(RuntimeError, match='依赖安装失败'):
            launcher.install_dependencies(tmp_path)
    assert len(calls) == 2
    assert not (tmp_path / '.venv' / '.requirements.sha256').exists()


def test_offline_check_never_installs_dependencies(tmp_path, monkeypatch):
    (tmp_path / '.venv').mkdir()
    (tmp_path / 'requirements.txt').write_text('requests==2.32.5\n', encoding='utf-8')
    monkeypatch.setattr(launcher, 'dependencies_ready', lambda root: False)
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **kw: pytest.fail('offline must not run pip'))
    with pytest.raises(RuntimeError, match='依赖'):
        launcher.install_dependencies(tmp_path, allow_install=False)
    monkeypatch.setattr(launcher, 'dependencies_ready', lambda root: True)
    launcher.install_dependencies(tmp_path, allow_install=False)


def test_changed_or_removed_dependency_is_repaired_even_with_stamp(tmp_path, monkeypatch):
    (tmp_path / '.venv').mkdir()
    (tmp_path / 'requirements.txt').write_text('requests==2.32.5\n', encoding='utf-8')
    ready = [True]
    monkeypatch.setattr(launcher, 'dependencies_ready', lambda root: ready[0])
    calls = []
    def install(*a, **kw):
        calls.append(a)
        ready[0] = True
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(launcher.subprocess, 'run', install)
    launcher.install_dependencies(tmp_path)
    ready[0] = False
    launcher.install_dependencies(tmp_path)
    assert len(calls) == 2


def test_launcher_does_not_install_into_system_python(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher.venv.EnvBuilder, 'create', lambda self, path: None)
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'run', lambda args, **kw: calls.append((args, kw)) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(launcher, 'install_dependencies', lambda *a, **kw: pytest.fail('base Python must not run pip'))
    assert launcher.main(['--check']) == 0
    args, options = calls[0]
    assert str(tmp_path / '.venv') in args[0]
    assert args[1:3] == ['-X', 'utf8']
    assert options['cwd'] == tmp_path
    assert options['env']['PYTHONUTF8'] == '1'


def test_windows_entry_is_ascii_crlf_and_uses_utf8_launcher():
    raw = (ROOT / '启动项目.bat').read_bytes()
    source = raw.decode('ascii')
    assert b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b'')
    assert 'launcher.py' in source and '-X utf8' in source
    assert 'PYTHONUTF8=1' in source and 'PYTHONIOENCODING=utf-8' in source


def test_docker_uses_the_same_core_dependencies_and_excludes_local_venv():
    docker = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    assert 'requirements.txt' in docker and 'pip install' in docker
    assert '-r requirements.txt' in docker
    assert '.venv' in (ROOT / '.dockerignore').read_text(encoding='utf-8')
