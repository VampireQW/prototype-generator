"""同目录、同端口的服务实例交接；不按端口查杀进程。"""
from contextlib import contextmanager
import hmac
import http.client
import json
import os
from pathlib import Path
import secrets
import tempfile
import time


class PortInUse(RuntimeError):
    pass


def _read(path):
    try:
        if path.is_symlink(): return {}
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError): return {}


def _folder(root):
    folder=Path(root).resolve()/'data'
    if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():
        raise PortInUse('服务运行记录不能放在链接目录中')
    folder.mkdir(parents=True,exist_ok=True)
    return folder


@contextmanager
def startup_lock(root,port,timeout=360):
    path=_folder(root)/f'server-startup-{port}.lock'
    if path.is_symlink(): raise PortInUse('启动锁文件不能是链接')
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if not stream.tell():stream.write(b'0');stream.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline: raise PortInUse('另一次启动仍在进行，请稍后重试')
                time.sleep(.1)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


class Instance:
    def __init__(self,root,port):
        self.root=Path(root).resolve();self.port=port
        self.instance_id=secrets.token_hex(16);self.token=secrets.token_hex(32)
        self.record_path=_folder(root)/f'server-instance-{port}.json'

    def public_info(self):
        return {'service':'prototype-generator','instanceId':self.instance_id,
                'root':str(self.root),'pid':os.getpid(),'port':self.port}

    def authorized(self,body):
        return (isinstance(body,dict) and body.get('instanceId')==self.instance_id and
                isinstance(body.get('token'),str) and hmac.compare_digest(body['token'].encode('utf-8'),self.token.encode('ascii')))

    def register(self):
        fd,name=tempfile.mkstemp(prefix='.server-instance-',dir=self.record_path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump({**self.public_info(),'token':self.token},stream);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.record_path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def cleanup(self):
        if _read(self.record_path).get('instanceId')==self.instance_id:
            self.record_path.unlink(missing_ok=True)


def _request(port,path,body=None):
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
    headers={'Origin':f'http://127.0.0.1:{port}','Content-Type':'application/json'}
    try:
        connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse();raw=response.read(65536)
        return response.status,json.loads(raw)
    finally:connection.close()


def _known_instance(root,port):
    record=_read(_folder(root)/f'server-instance-{port}.json')
    try:
        status,info=_request(port,'/api/server-info')
        if (status!=200 or not isinstance(info,dict) or info.get('service')!='prototype-generator' or
            info.get('instanceId')!=record.get('instanceId') or
            Path(info.get('root','')).resolve()!=Path(root).resolve() or
            not isinstance(record.get('root'),str) or Path(record['root']).resolve()!=Path(root).resolve() or
            not isinstance(record.get('token'),str) or len(record['token'])!=64):raise ValueError()
    except (OSError,ValueError,TypeError,http.client.HTTPException):
        raise PortInUse(f'端口 {port} 被其他程序或不支持自动交接的旧版服务占用，未关闭任何进程') from None
    return record


@contextmanager
def running_server(factory,address,root,wait_timeout=330):
    """先绑定；占用时验证身份、请求退出，再重新绑定。"""
    server=None;instance=None;port=address[1]
    try:
        with startup_lock(root,port,timeout=wait_timeout+5):
            try:server=factory(address)
            except OSError as error:
                if error.errno not in (48,98,10013,10048):raise
                record=_known_instance(root,port)
                print('[INFO] 检测到旧实例，正在自动关闭并重新启动…',flush=True)
                deadline=time.monotonic()+wait_timeout;accepted=False;waiting=False
                while server is None:
                    if time.monotonic()>=deadline:
                        raise PortInUse('旧实例尚未完成当前任务，请稍后重新启动；未强制终止任务')
                    if not accepted:
                        try:
                            status,reply=_request(port,'/api/server/stop',{'instanceId':record['instanceId'],'token':record['token']})
                            if status==202:accepted=True
                            elif status==409 and reply.get('busy'):
                                if not waiting:print('[INFO] 旧实例正在处理任务，等待完成后自动接替…',flush=True);waiting=True
                                time.sleep(.1);continue
                            else:raise PortInUse('旧实例拒绝交接，请检查服务状态；未关闭任何其他进程')
                        except (OSError,http.client.HTTPException):
                            # It may have exited between identity verification and the request.
                            accepted=True
                    try:server=factory(address)
                    except OSError as bind_error:
                        if bind_error.errno not in (48,98,10013,10048):raise
                        time.sleep(.1)
            instance=Instance(root,server.server_port);server.lifecycle=instance;server.restarting=False
            instance.register()
        yield server
    finally:
        if server is not None:server.server_close()
        # Release the port first: the successor is holding the startup lock while
        # waiting for it. Then serialize cleanup so an old exit cannot unlink a
        # newly registered instance between the identity check and unlink.
        if instance is not None:
            with startup_lock(root,instance.port):instance.cleanup()
