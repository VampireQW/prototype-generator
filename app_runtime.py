"""Only standard-library helpers needed before the service can start."""
import json
import sys
from pathlib import Path


def configure_utf8_output():
    """Keep Chinese paths and logs usable in Windows consoles and redirected output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure:
            reconfigure(encoding='utf-8', errors='backslashreplace')


def _read_json_object(path):
    try:
        # json.loads(bytes) detects UTF-8 (including BOM), UTF-16 and UTF-32.
        data = json.loads(path.read_bytes())
    except (UnicodeError, json.JSONDecodeError) as error:
        # Do not echo source lines: local settings may contain credentials.
        raise ValueError(f'{path.name} 格式或编码无效，请保存为 UTF-8 JSON；原文件未修改。') from error
    if not isinstance(data, dict):
        raise ValueError(f'{path.name} 顶层必须是 JSON 对象；原文件未修改。')
    return data


def load_local_json(path, *, template=None):
    """Create absent local settings; read existing Unicode JSON without rewriting it."""
    path = Path(path)
    if template is not None and not path.exists():
        data = _read_json_object(Path(template))
        try:
            # Exclusive create also protects against concurrent first launches.
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        except FileExistsError:
            pass
    return _read_json_object(path)
