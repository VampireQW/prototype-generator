"""Pages 管理使用内存 GitHub 仓库；绝不访问或修改真实远端。"""
import base64
import copy
import hashlib
import importlib
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_external_api import api, prototype


class Response:
    def __init__(self, data, status=200): self.data, self.status_code = data, status
    def json(self): return copy.deepcopy(self.data)


class Remote:
    def __init__(self):
        self.head = 'head-old'; self.branch = 'main'; self.pages = True; self.actions = False
        self.fail = ''; self.truncated = False; self.calls = []; self.pending = None
        self.files = {'index.html': b'root', 'projects/a/index.html': b'alpha',
                      'projects/a/assets/x.png': b'image', 'projects/b/deep/index.html': b'beta',
                      'projects/manifest.json': json.dumps([{'id':'a','name':'项目 A','mode':'review','publishedAt':'2026-10-01'}]).encode(),
                      'projects/index.html': b'listing', 'other.txt': b'keep'}
        self.trees = {}
    def sha(self, data): return hashlib.sha256(data).hexdigest()
    def get(self, url, **kwargs):
        route = urlsplit(url).path.split('/repos/test-owner/fixture-repo')[-1]
        self.calls.append(('GET',route,kwargs))
        if self.fail and self.fail == route: return Response({},403)
        if not route: return Response({'default_branch':self.branch,'size':500})
        if route == '/pages':
            return Response({'html_url':'https://test-owner.github.io/fixture-repo/','build_type':'workflow' if self.actions else 'legacy',
                             'source':{} if self.actions else {'branch':self.branch,'path':'/'}},200 if self.pages else 404)
        if route.startswith('/git/ref/heads/'): return Response({'object':{'sha':self.head}})
        if route.startswith('/git/commits/'): return Response({'tree':{'sha':'tree-'+self.head}})
        if route.startswith('/git/blobs/'):
            sha=route.rsplit('/',1)[-1]; data=next(value for value in self.files.values() if self.sha(value)==sha)
            return Response({'encoding':'base64','content':base64.b64encode(data).decode()})
        if route.startswith('/git/trees/'):
            sha=route.rsplit('/',1)[-1]; prefix=self.trees.get(sha,'')
            recursive='recursive=1' in url
            result=[]; seen=set()
            for path,data in self.files.items():
                if not path.startswith(prefix): continue
                relative=path[len(prefix):]
                if not recursive and '/' in relative:
                    folder=relative.split('/')[0]; key=prefix+folder+'/'
                    if key in seen: continue
                    seen.add(key); tree_sha=self.sha(key.encode()); self.trees[tree_sha]=key
                    result.append({'path':folder,'type':'tree','mode':'040000','sha':tree_sha}); continue
                result.append({'path':relative,'type':'blob','mode':'100644','size':len(data),'sha':self.sha(data)})
            return Response({'tree':result[:1] if recursive and self.truncated else result,'truncated':recursive and self.truncated})
        raise AssertionError(('unexpected GET',route))
    def post(self,url,**kwargs):
        route=urlsplit(url).path.split('/repos/test-owner/fixture-repo')[-1]; self.calls.append(('POST',route,kwargs))
        if self.fail == route: return Response({},403)
        if route == '/git/trees':
            assert kwargs['json']['base_tree']=='tree-'+self.head
            self.pending=copy.deepcopy(self.files)
            for change in kwargs['json']['tree']:
                if 'content' in change: self.pending[change['path']]=change['content'].encode()
                elif change.get('sha') is None: self.pending.pop(change['path'])
            return Response({'sha':'tree-new'},201)
        if route == '/git/commits':
            assert kwargs['json']['parents']==[self.head]
            return Response({'sha':'head-new'},201)
        raise AssertionError(route)
    def patch(self,url,**kwargs):
        route=urlsplit(url).path.split('/repos/test-owner/fixture-repo')[-1]; self.calls.append(('PATCH',route,kwargs))
        assert kwargs['json']['force'] is False
        if self.fail == 'race': return Response({},409)
        if self.fail == route: return Response({},403)
        self.files=self.pending; self.head='head-new'
        return Response({'object':{'sha':self.head}})


def module(): return importlib.import_module('github_pages')
def catalog(remote): return module().read_catalog(remote,'test-owner','fixture-repo')
def remove(remote, project='a', head='head-old'):
    return module().unpublish(remote,'test-owner','fixture-repo',project,head,
                              lambda items,owner,repo: '<html>'+','.join(row['id'] for row in items)+'</html>')


def test_remote_catalog_includes_unlisted_projects_and_estimates_source_bytes():
    remote=Remote(); result=catalog(remote)['public']
    assert {row['id'] for row in result['projects']}=={'a','b'}
    assert next(row for row in result['projects'] if row['id']=='b')['listed'] is False
    assert result['usage']['usedBytes']==sum(map(len,remote.files.values()))
    assert result['usage']['remainingBytes']==1_000_000_000-result['usage']['usedBytes']
    assert result['usage']['estimated'] and result['head']=='head-old'
    assert all(call[0]=='GET' for call in remote.calls)


def test_truncated_tree_is_fully_walked_instead_of_reporting_partial_capacity():
    remote=Remote(); remote.truncated=True
    assert catalog(remote)['public']['usage']['usedBytes']==sum(map(len,remote.files.values()))
    assert len(catalog(remote)['public']['projects'])==2


def test_unknown_actions_output_does_not_report_zero_or_exact_remaining():
    remote=Remote(); remote.actions=True
    usage=catalog(remote)['public']['usage']
    assert usage['usedBytes'] is None and usage['remainingBytes'] is None
    assert usage['reason']


def test_upstream_failure_is_an_error_instead_of_an_empty_catalog():
    remote=Remote(); remote.fail='/git/ref/heads/main'
    with pytest.raises(module().PagesError): catalog(remote)


def test_atomic_unpublish_updates_files_manifest_and_index_and_keeps_other_projects():
    remote=Remote(); before=remote.files['projects/b/deep/index.html']
    result=remove(remote)
    assert result['ok'] and not any(path.startswith('projects/a/') for path in remote.files)
    assert json.loads(remote.files['projects/manifest.json'])==[]
    assert remote.files['projects/b/deep/index.html']==before and remote.files['other.txt']==b'keep'
    assert len([call for call in remote.calls if call[0]=='PATCH'])==1
    assert all(call[0]!='DELETE' for call in remote.calls)
    assert result['overview']['head']=='head-new'


@pytest.mark.parametrize('failure',['/git/trees','/git/commits','race','/git/refs/heads/main'])
def test_remote_write_failure_does_not_change_published_branch(failure):
    remote=Remote(); before=copy.deepcopy(remote.files); remote.fail=failure
    with pytest.raises(module().PagesError): remove(remote)
    assert remote.files==before and remote.head=='head-old'


@pytest.mark.parametrize('project,head',[('../other','head-old'),('a','stale')])
def test_invalid_project_and_stale_head_never_write(project,head):
    remote=Remote()
    with pytest.raises((module().PagesError,ValueError)): remove(remote,project,head)
    assert all(call[0]=='GET' for call in remote.calls)


def configure(api,remote):
    api.namespace['get_github_runtime_config']=lambda:{'username':'test-owner','repo':'fixture-repo','token':'fixture-key-'+str(id(remote))}
    api.namespace['github_api_session']=lambda token:remote


def test_overview_is_local_only_and_has_no_credentials(api):
    remote=Remote(); configure(api,remote)
    assert api.request('/api/pages/overview',headers={'Origin':'https://evil.example'})[0]==403
    code,result=api.request('/api/pages/overview?refresh=1')
    assert code==200 and len(result['projects'])==2
    assert 'fixture-key' not in json.dumps(result) and 'token' not in result


def test_manager_removes_remote_only_project_without_registering_local_data(api):
    remote=Remote(); configure(api,remote)
    assert api.request('/api/pages/unpublish',{'projectId':'b','repository':'test-owner/fixture-repo','expectedHead':'head-old'})[0]==200
    assert api.namespace['load_external_registry']()['projects']=={}
    assert not any(path.startswith('projects/b/') for path in remote.files)


def test_failed_existing_unpublish_preserves_local_published_state(api,tmp_path):
    remote=Remote(); remote.fail='/git/trees'; configure(api,remote)
    root=prototype(tmp_path/'local'); pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    registry=api.namespace['load_external_registry']()
    registry['projects'][pid].update(github_remote_id='a',github_url='https://test-owner.github.io/fixture-repo/projects/a/')
    api.namespace['save_external_registry'](registry)
    code,result=api.request('/api/ext/unpublish',{'extId':pid})
    assert code>=400 and not result.get('ok')
    assert api.namespace['load_external_registry']()['projects'][pid]['github_url']
    assert 'projects/a/index.html' in remote.files


def test_manager_requires_current_repository_and_snapshot(api):
    remote=Remote(); configure(api,remote)
    for payload in ({'projectId':'a','repository':'other/repo','expectedHead':'head-old'},
                    {'projectId':'a','repository':'test-owner/fixture-repo'}):
        assert api.request('/api/pages/unpublish',payload)[0] in (400,409)
    assert all(call[0]=='GET' for call in remote.calls)


def test_successful_existing_unpublish_clears_only_publication_fields(api,tmp_path):
    remote=Remote(); configure(api,remote)
    root=prototype(tmp_path/'local'); pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    before=(root/'.prototype/prd.json').read_bytes()
    registry=api.namespace['load_external_registry']()
    registry['projects'][pid].update(github_remote_id='a',github_url='https://test-owner.github.io/fixture-repo/projects/a/',
                                    github_publish_mode='review',github_published_at='2026-10-21',github_repository='test-owner/fixture-repo')
    api.namespace['save_external_registry'](registry)
    assert api.request('/api/ext/unpublish',{'extId':pid})[0]==200
    updated=api.namespace['load_external_registry']()['projects'][pid]
    assert not any(key in updated for key in ('github_url','github_publish_mode','github_published_at','github_repository'))
    assert (root/'index.html').exists() and (root/'.prototype/prd.json').read_bytes()==before


def test_legacy_unpublish_updates_existing_record_without_creating_a_project(api,tmp_path):
    remote=Remote(); configure(api,remote)
    root=prototype(tmp_path/'projects'/'a')
    record=root/'record.json'; record.write_text(json.dumps({'github_url':'old','projectName':'保留'}),encoding='utf-8')
    api.namespace.update(PROJECTS_DIR=str(root.parent),PROJECTS_FILE=str(tmp_path/'projects.json'))
    api.namespace['CustomHandler'].get_current_user=lambda self:None
    assert api.request('/api/github/unpublish',{'projectId':'a'})[0]==200
    assert json.loads(record.read_text(encoding='utf-8'))=={'projectName':'保留'}


def test_post_commit_verification_failure_preserves_local_record(api,tmp_path):
    remote=Remote(); configure(api,remote)
    patch=remote.patch
    def lose_read(*args,**kwargs):
        result=patch(*args,**kwargs);remote.fail='/git/ref/heads/main';return result
    remote.patch=lose_read
    root=prototype(tmp_path/'local');pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    registry=api.namespace['load_external_registry']()
    registry['projects'][pid].update(github_remote_id='a',github_url='https://test-owner.github.io/fixture-repo/projects/a/')
    api.namespace['save_external_registry'](registry)
    assert api.request('/api/ext/unpublish',{'extId':pid})[0]==502
    assert api.namespace['load_external_registry']()['projects'][pid]['github_url']=='https://test-owner.github.io/fixture-repo/projects/a/'


def test_remote_historical_ai_project_keeps_owner_check_after_local_registry_removed(api):
    remote=Remote();configure(api,remote)
    api.namespace['db']=SimpleNamespace(get_project_owner=lambda project:7,can_user_access_project=lambda project,user:False)
    api.namespace['CustomHandler'].get_current_user=lambda self:{'id':8}
    assert api.request('/api/pages/unpublish',{'projectId':'b','repository':'test-owner/fixture-repo','expectedHead':'head-old'})[0]==403
    assert all(call[0]=='GET' for call in remote.calls)


def test_current_project_rejects_unpublishing_against_a_different_configured_repository(api,tmp_path):
    remote=Remote();configure(api,remote)
    root=prototype(tmp_path/'local');pid=api.request('/api/external/add',{'path':str(root)})[1]['projectId']
    registry=api.namespace['load_external_registry']()
    registry['projects'][pid].update(github_remote_id='a',github_url='https://old-owner.github.io/old-repo/projects/a/')
    api.namespace['save_external_registry'](registry)
    assert api.request('/api/ext/unpublish',{'extId':pid})[0]==409
    assert all(call[0]=='GET' for call in remote.calls)
    assert api.namespace['load_external_registry']()['projects'][pid]['github_url']
