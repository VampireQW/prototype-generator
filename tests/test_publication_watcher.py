"""静态站版本轮询的真实 JS 回归；不启动额外浏览器。"""
import json
from pathlib import Path
import shutil
import subprocess

SOURCE=Path(__file__).resolve().parents[1]/'src/publication-updates.js'


def test_polling_update_noop_visibility_rollback_and_no_credentials():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const events={},tasks=new Map(),changes=[],calls=[];let seq=0,hidden=false,next;
const current={schemaVersion:1,releaseId:'rel-'+ '1'.repeat(16),sequence:1,contentVersion:'a'.repeat(64),mode:'review',projectId:'p'};
const global={location:{protocol:'https:',href:'https://fixture.test/project/index.html#p=home'},
 document:{get hidden(){return hidden},addEventListener:(t,f)=>events[t]=f,removeEventListener:t=>delete events[t]},
 addEventListener:(t,f)=>events[t]=f,removeEventListener:t=>delete events[t],
 setTimeout:(fn,ms)=>{tasks.set(++seq,{fn,ms});return seq},clearTimeout:id=>tasks.delete(id),
 fetch:async(url,options)=>{calls.push({url,options});if(next instanceof Error)throw next;return {ok:true,json:async()=>next}}};
const context={window:global,URL,URLSearchParams,Date,Promise,console};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
const U=global.PublicationUpdates;
(async()=>{
 next={...current,sequence:2,releaseId:'rel-'+ '2'.repeat(16),contentVersion:'b'.repeat(64)};
 const watcher=U.createWatcher({current,onUpdate:v=>changes.push(v)});watcher.start();await watcher.check();
 assert.equal(changes.length,1);assert.equal(calls[0].options.credentials,'omit');assert.equal(calls[0].options.cache,'no-store');
 assert(calls[0].url.startsWith('https://fixture.test/project/prototype-release.json?'));
 await watcher.check();assert.equal(changes.length,1,'same version should not repeat');
 next={...current,sequence:1,contentVersion:'c'.repeat(64)};await watcher.check();assert.equal(changes.length,1,'older manifest ignored');
 hidden=true;const count=calls.length;await watcher.check();assert.equal(calls.length,count);hidden=false;
 next={...current,sequence:3};await watcher.check();assert.equal(changes.length,1,'same content redeploy ignored');
 next={...current,sequence:4,releaseId:'rel-'+ '4'.repeat(16),contentVersion:'c'.repeat(64)};events.focus();await watcher.check();assert.equal(changes.length,2);
 next=new Error('offline');await watcher.check();assert([...tasks.values()].some(t=>t.ms===60000),'network backoff');
 watcher.stop();const stopped=calls.length;await watcher.check();assert.equal(calls.length,stopped);
 assert.equal(U.safeRelative('../x'),false);assert.equal(U.safeRelative('%2e%2e/x'),false);assert.equal(U.safeRelative('https://evil.test/a'),false);
 const target={pageId:'home',stateId:'default',anchor:{protoId:'save',revealSteps:[{selector:'#delete'}]}};
 const parsed=U.readTarget('#'+U.targetHash(target));assert(!('revealSteps' in parsed.anchor),'URL must not inject click actions');
 console.log('watcher verified');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result=subprocess.run([shutil.which('node') or r'D:\software\nodejs\node.exe','-e',script,str(SOURCE)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_offline_package_never_polls():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');let calls=0;
const w={location:{protocol:'file:',href:'file:///D:/export/index.html'},fetch:async()=>calls++,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window:w,URL,URLSearchParams,Promise,Date});
const current={schemaVersion:1,releaseId:'rel-'+ '1'.repeat(16),sequence:1,contentVersion:'a'.repeat(64),mode:'review'};
const watcher=w.PublicationUpdates.createWatcher({current,onUpdate(){throw Error('not allowed')}});watcher.start();watcher.check().then(()=>{assert.equal(calls,0);watcher.stop()});
'''
    result=subprocess.run([shutil.which('node') or r'D:\software\nodejs\node.exe','-e',script,str(SOURCE)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
