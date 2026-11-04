import base64
import copy
import json
from urllib.parse import urlsplit

import pytest
import github_pages as G
import publication_versions as V
from test_pages_manager import Remote, Response


class PublishingRemote(Remote):
    def __init__(self):
        super().__init__(); self.blobs={}

    def post(self,url,**kwargs):
        route=urlsplit(url).path.split('/repos/test-owner/fixture-repo')[-1]
        if route=='/git/blobs':
            self.calls.append(('POST',route,kwargs))
            raw=base64.b64decode(kwargs['json']['content']); sha=self.sha(raw)
            self.blobs[sha]=raw
            return Response({'sha':sha},201)
        result=super().post(url,**kwargs)
        if route=='/git/trees' and result.status_code==201:
            for row in kwargs['json']['tree']:
                if row.get('sha'):
                    self.pending[row['path']]=self.blobs.get(row['sha']) or next(v for v in self.files.values() if self.sha(v)==row['sha'])
        return result


def write(directory,name,raw):
    path=directory/name; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw if isinstance(raw,bytes) else raw.encode())


def test_atomic_publish_commits_all_files_once_and_keeps_other_projects(tmp_path):
    remote=PublishingRemote(); write(tmp_path,'index.html','new shell'); write(tmp_path,'proto/a.html','new page')
    result=G.publish_directory(remote,'test-owner','fixture-repo','main',tmp_path,'projects/a')
    assert remote.files['projects/a/index.html']==b'new shell'
    assert remote.files['projects/a/proto/a.html']==b'new page'
    assert remote.files['projects/b/deep/index.html']==b'beta'
    assert remote.files['other.txt']==b'keep'
    assert len([c for c in remote.calls if c[0]=='PATCH'])==1
    assert result['head']=='head-new'


def test_ref_conflict_never_exposes_partly_uploaded_release(tmp_path):
    remote=PublishingRemote(); before=copy.deepcopy(remote.files); remote.fail='race'
    write(tmp_path,'index.html','new shell');write(tmp_path,'a.png',b'\x89PNG')
    with pytest.raises(G.Conflict): G.publish_directory(remote,'test-owner','fixture-repo','main',tmp_path,'projects/a')
    assert remote.files==before


def test_managed_files_pruned_but_previous_prototype_and_unowned_files_preserved(tmp_path):
    remote=PublishingRemote()
    old={'schemaVersion':1,'releaseId':'rel-'+'1'*16,'contentVersion':'1'*64,'prototypeBase':'prototype-versions/'+'1'*24+'/',
         'managedFiles':['index.html','obsolete.txt','prototype-versions/'+'1'*24+'/index.html'],'history':[]}
    remote.files['projects/a/'+V.MANIFEST]=json.dumps(old).encode()
    remote.files['projects/a/obsolete.txt']=b'old'
    remote.files['projects/a/'+old['prototypeBase']+'index.html']=b'previous'
    new={'schemaVersion':1,'releaseId':'rel-'+'2'*16,'baseReleaseId':old['releaseId'],'contentVersion':'2'*64,
         'prototypeBase':'prototype-versions/'+'2'*24+'/','sequence':2,'publishedAt':'2026-11-03 16:00:00',
         'mode':'review','changesUrl':'prototype-changes/rel-'+'2'*16+'.json','summary':{'changes':1,'pages':1}}
    write(tmp_path,V.MANIFEST,json.dumps(new)); write(tmp_path,'index.html','new')
    write(tmp_path,new['prototypeBase']+'index.html','latest')
    G.publish_directory(remote,'test-owner','fixture-repo','main',tmp_path,'projects/a')
    assert 'projects/a/obsolete.txt' not in remote.files
    assert remote.files['projects/a/'+old['prototypeBase']+'index.html']==b'previous'
    assert remote.files['projects/a/assets/x.png']==b'image'
    manifest=json.loads(remote.files['projects/a/'+V.MANIFEST])
    assert old['prototypeBase']+'index.html' in manifest['managedFiles']


def test_stale_baseline_stops_before_upload(tmp_path):
    remote=PublishingRemote()
    remote.files['projects/a/'+V.MANIFEST]=json.dumps({'releaseId':'rel-'+'1'*16}).encode()
    write(tmp_path,V.MANIFEST,json.dumps({'baseReleaseId':'stale'}))
    with pytest.raises(G.Conflict): G.publish_directory(remote,'test-owner','fixture-repo','main',tmp_path,'projects/a')
    assert all(c[0]=='GET' for c in remote.calls)
