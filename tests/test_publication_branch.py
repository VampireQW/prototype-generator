import ast
import base64
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def ensure():
    source=Path(__file__).resolve().parents[1]/'server.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='github_ensure_pages')
    import requests
    ns={'requests':requests,'base64':base64}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
    return ns[fn.name]


class Session:
    def __init__(self,source=None,build_type='legacy'):
        self.source=source or {'branch':'gh-pages','path':'/'};self.build_type=build_type;self.writes=[]
    def get(self,url,**kwargs):
        data={'source':self.source,'build_type':self.build_type} if url.endswith('/pages') else {'default_branch':'main'}
        return SimpleNamespace(status_code=404 if '/contents/' in url else 200,json=lambda:data)
    def put(self,url,**kwargs):
        self.writes.append(kwargs['json']);return SimpleNamespace(status_code=201)


def test_publisher_uses_pages_branch_instead_of_repository_default():
    session=Session()
    assert ensure()(session,'https://api.github.com','fixture','repo')=='gh-pages'
    assert session.writes[0]['branch']=='gh-pages'


@pytest.mark.parametrize('source,build_type',[
    ({'branch':'main','path':'/docs'},'legacy'),({'branch':'main','path':'/'},'workflow')])
def test_unsupported_source_is_reported_before_any_write(source,build_type):
    session=Session(source,build_type)
    with pytest.raises(ValueError):ensure()(session,'https://api.github.com','fixture','repo')
    assert not session.writes
