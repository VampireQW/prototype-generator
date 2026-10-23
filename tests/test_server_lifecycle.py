"""重复启动只替换同目录实例；隔离端口，不读取真实配置。"""
import functools
import http.client
import importlib.util
import json
from pathlib import Path
import queue
import threading
import time

import pytest
from test_external_api import isolated_handler


def lifecycle():
    assert importlib.util.find_spec('server_lifecycle'), '缺少新实例接替旧服务的生命周期机制'
    import server_lifecycle
    return server_lifecycle


def request(server,path='/api/server-info',body=None,headers=None):
    port=server.server_port; conn=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
    supplied={'Origin':f'http://127.0.0.1:{port}','Content-Type':'application/json'}; supplied.update(headers or {})
    conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,supplied)
    response=conn.getresponse(); raw=response.read(); status=response.status; conn.close()
    return status,json.loads(raw) if 'json' in response.getheader('Content-Type','') else raw.decode()


@pytest.fixture
def service(tmp_path):
    module=lifecycle(); root=tmp_path/'app';root.mkdir()
    ns=isolated_handler(root/'external.json');ns.update(generating_tasks={},tasks_lock=threading.Lock(),PROJECTS_DIR=str(root/'projects'))
    factory=lambda address: ns['PrototypeHTTPServer'](address,functools.partial(ns['CustomHandler'],directory=str(root)))
    ready=queue.Queue(); failures=[]
    def run():
        try:
            with module.running_server(factory,('127.0.0.1',0),root,wait_timeout=3) as server:
                ready.put(server);server.serve_forever(poll_interval=.02)
        except Exception as error: failures.append(error);ready.put(None)
    worker=threading.Thread(target=run,daemon=True);worker.start();server=ready.get(timeout=4)
    assert server is not None,failures
    yield server,worker,module,factory,root,ns
    if worker.is_alive(): server.shutdown();worker.join(timeout=3)
    assert not failures,failures


def test_new_start_replaces_old_instance_and_cleanup_preserves_new_record(service):
    old,worker,module,factory,root,_=service
    with module.running_server(factory,('127.0.0.1',old.server_port),root,wait_timeout=3) as new:
        worker.join(timeout=2);assert not worker.is_alive()
        assert new.lifecycle.instance_id!=old.lifecycle.instance_id
        record=json.loads(new.lifecycle.record_path.read_text())
        assert record['instanceId']==new.lifecycle.instance_id
    assert not new.lifecycle.record_path.exists()


def test_foreign_service_or_other_project_is_never_stopped(service,tmp_path):
    old,worker,module,factory,_,_=service
    other=tmp_path/'other';other.mkdir()
    with pytest.raises(module.PortInUse):
        with module.running_server(factory,('127.0.0.1',old.server_port),other,wait_timeout=.2): pass
    assert worker.is_alive() and request(old)[0]==200


def test_stop_requires_local_origin_secret_and_exact_instance(service):
    old,worker,_,_,_,_=service
    assert 'token' not in json.dumps(request(old)[1]).lower()
    stop={'instanceId':old.lifecycle.instance_id,'token':old.lifecycle.token}
    for body,headers in [({**stop,'token':'wrong'},{}),({**stop,'token':'非法凭据'},{}),({**stop,'instanceId':'stale'},{}),(stop,{'Origin':'https://evil.example'})]:
        assert request(old,'/api/server/stop',body,headers)[0]==403
    assert worker.is_alive()
    for path in ('/data/server-instance-'+str(old.server_port)+'.json', '/DATA/server-instance-'+str(old.server_port)+'.json.'):
        assert request(old,path)[0]==403


@pytest.mark.parametrize('busy_kind',['write','generation'])
def test_takeover_waits_for_active_work_instead_of_interrupting_it(service,busy_kind):
    old,worker,module,factory,root,ns=service
    if busy_kind=='write':ns['REQUEST_LOCK'].acquire()
    else:ns['generating_tasks']['test']={'status':'generating'}
    ready=threading.Event(); errors=[]
    def replace():
        try:
            with module.running_server(factory,('127.0.0.1',old.server_port),root,wait_timeout=3): ready.set()
        except Exception as error: errors.append(error)
    replacement=threading.Thread(target=replace,daemon=True);replacement.start()
    try:
        time.sleep(.2);assert worker.is_alive() and not ready.is_set()
    finally:
        if busy_kind=='write':ns['REQUEST_LOCK'].release()
        else:ns['generating_tasks'].clear()
    replacement.join(timeout=4)
    assert not errors and ready.is_set()


def test_rapid_startups_are_serialized_by_project_port_lock(tmp_path):
    module=lifecycle(); entered=threading.Event();order=[]
    with module.startup_lock(tmp_path,8080,timeout=2):
        def contender():
            with module.startup_lock(tmp_path,8080,timeout=2):order.append('next');entered.set()
        worker=threading.Thread(target=contender);worker.start()
        time.sleep(.1);assert not entered.is_set();order.append('first')
    worker.join(timeout=2);assert order==['first','next']


def test_timeout_keeps_busy_old_service_running(service):
    old,worker,module,factory,root,ns=service
    ns['generating_tasks']['pending']={'status':'pending'}
    with pytest.raises(module.PortInUse,match='尚未完成'):
        with module.running_server(factory,('127.0.0.1',old.server_port),root,wait_timeout=.15):pass
    assert worker.is_alive() and request(old)[0]==200
