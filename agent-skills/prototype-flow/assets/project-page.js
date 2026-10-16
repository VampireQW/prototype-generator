(function(){
 'use strict';
 window.addEventListener('message',async e=>{
  if(e.source!==window.parent || !e.data?.__protoProject)return;
  if(e.data.type==='host' && e.data.host==='launcher')document.documentElement.dataset.protoHost='launcher';
  if(e.data.type==='enterState' && typeof e.data.stateId==='string'){
   try{await window.PrototypeBridge?.enter?.(e.data.stateId);}catch(_){}
  }
 });
 new MutationObserver(()=>window.parent.postMessage({__protoProject:1,type:'state',stateId:document.documentElement.dataset.protoState || 'default'},'*'))
  .observe(document.documentElement,{attributes:true,attributeFilter:['data-proto-state']});
})();
