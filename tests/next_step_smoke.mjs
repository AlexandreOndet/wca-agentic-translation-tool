import {readFile, writeFile} from 'node:fs/promises';
const [base,debug]=process.argv.slice(2);
const tab=await(await fetch(`${debug}/json/new?${encodeURIComponent('about:blank')}`,{method:'PUT'})).json();
const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let seq=0;const pending=new Map(),errors=[];
ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function wait(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,70));}throw new Error('Timeout: '+expression);}
async function click(id){await evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);}
async function pick(id,value){await evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change'));})()`);}
function assert(value,message){if(!value)throw new Error(message);}
async function openSession(id){const revision=await evaluate('state.workspace.revision');await evaluate(`document.getElementById('sessions').value=${JSON.stringify(id)}`);await click('open-session');await wait(`state.workspace.active_id===${JSON.stringify(id)} && state.workspace.revision>${revision} && state.workspace.ready && !syncing`);}
async function download(){
 await click('next-download');await wait("document.getElementById('export-dialog').open && !document.getElementById('download').disabled");
 await evaluate("document.getElementById('confirm-warnings').checked=true");
 await click('download');await wait("!document.getElementById('export-dialog').open && !document.getElementById('next-step').hidden");
}
try {
 await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base});
 await wait("typeof state!=='undefined' && state && !catalogBusy() && !document.getElementById('sync').disabled");
 assert(await evaluate("document.getElementById('next-step').hidden"),'A new workspace has no completion reminder');
 await pick('component','regulations');await wait('!catalogBusy()');
 await evaluate("document.getElementById('manual-mode').checked=true;document.getElementById('manual-mode').dispatchEvent(new Event('change'))");
 await click('sync');await wait('!syncing && state.workspace.candidate_count===2 && !catalogBusy()');
 assert(await evaluate("!state.workspace.ready && document.getElementById('next-step').hidden"),'Downloaded keys are not a completed review');
 const session=await evaluate('state.workspace.active_id');
 const folder=await evaluate('state.workspace.folder');
 const work=JSON.parse(await readFile(`${folder}/work.json`,'utf8'));
 await writeFile(`${folder}/proposals.json`,JSON.stringify({version:1,session_id:work.session_id,base_sha256:work.base_sha256,entries:work.entries.map(e=>({key:e.key,target:e.context==='greeting'?['Hola revisada %s']:['Nueva clave'],note:''}))}));
 await click('load-proposals');await wait('state.workspace.ready && state.counts.pending===2');
 assert(await evaluate("document.getElementById('next-step').hidden"),'Unreviewed proposals do not show a completion reminder');
 await click('accept');await wait('state.counts.accepted===1 && saving===0');
 await click('accept');await wait("state.counts.accepted===2 && saving===0 && !document.getElementById('next-step').hidden");
 assert(await evaluate("document.activeElement.id==='next-download'"),'Finishing a review offers its download');
 await send('Page.navigate',{url:base});
 await wait("typeof state!=='undefined' && state && state.counts.accepted===2 && !catalogBusy()");
 assert(await evaluate("document.getElementById('next-step').hidden"),'An undismissed completed session restored on startup does not show old instructions');
 await openSession(session);await wait("!document.getElementById('next-step').hidden");
 await pick('component','payload');
 assert(await evaluate("document.getElementById('next-step').hidden"),'Changing component immediately hides the previous review reminder');
 await wait('!catalogBusy()');await pick('component','regulations');await wait('!catalogBusy()');
 assert(await evaluate("document.getElementById('next-step').hidden"),'Switching back does not revive a stale reminder');
 await openSession(session);await wait("!document.getElementById('next-step').hidden");
 await pick('language','fr');
 assert(await evaluate("document.getElementById('next-step').hidden"),'Changing target language immediately hides the previous reminder');
 await wait('!catalogBusy()');await pick('language','es_419');await wait('!catalogBusy()');
 await openSession(session);await wait("!document.getElementById('next-step').hidden");
 await download();
 assert(await evaluate("!document.getElementById('next-weblate').hidden && document.getElementById('next-weblate').href.endsWith('/regulations/es_419/') && document.getElementById('next-step-text').textContent.includes(\"If you haven't uploaded it yet\")"),'The upload reminder uses the active review and does not claim to know Weblate upload status');
 await click('ui-es');await wait("uiLanguage==='es' && document.getElementById('next-dismiss').textContent==='Ya lo subí'");
 assert(await evaluate("document.getElementById('next-step-text').textContent.includes('Si todavía no lo subiste')"),'Upload instructions and acknowledgement are translated');
 const revision=await evaluate('state.revision');
 await click('next-dismiss');
 assert(await evaluate(`document.getElementById('next-step').hidden && state.revision===${revision} && state.counts.accepted===2`),'Acknowledging upload only hides the reminder');
 await openSession(session);
 assert(await evaluate("document.getElementById('next-step').hidden"),'Acknowledgement persists when reopening the same revision');
 await send('Page.navigate',{url:base});
 await wait("typeof state!=='undefined' && state && state.counts.accepted===2 && !catalogBusy()");
 assert(await evaluate("document.getElementById('next-step').hidden"),'Restoring a completed session on startup does not show stale instructions');
 await openSession(session);
 assert(await evaluate("document.getElementById('next-step').hidden"),'Acknowledgement persists across a page reload');
 await click('pending');await wait('state.counts.pending===1 && saving===0');
 await click('accept');await wait("state.counts.accepted===2 && saving===0 && !document.getElementById('next-step').hidden");
 assert(await evaluate("document.getElementById('next-weblate').hidden"),'New decisions require a new download instead of using an old acknowledgement');
 await download();
 await evaluate("document.getElementById('manual-mode').checked=true;document.getElementById('manual-mode').dispatchEvent(new Event('change'))");
 await evaluate("window.originalSyncApi=api;api=async(path,...args)=>{if(path==='/api/sync')await new Promise(resolve=>window.releaseSync=resolve);return window.originalSyncApi(path,...args);};true");
 await click('sync');await wait("syncing && typeof window.releaseSync==='function'");
 assert(await evaluate("document.getElementById('next-step').hidden && state.counts.accepted===2"),'A new sync hides the old banner while the previous completed review is still in memory');
 await evaluate('window.releaseSync();true');
 await wait('!syncing && state.workspace.candidate_count===0 && !catalogBusy()');
 assert(await evaluate("document.getElementById('next-step').hidden"),'Syncing after a successful upload clears the reminder');
 await evaluate('api=window.originalSyncApi;true');
 await openSession(session);await wait("!document.getElementById('next-step').hidden");
 await evaluate("document.getElementById('manual-mode').checked=true;document.getElementById('manual-mode').dispatchEvent(new Event('change'))");
 await click('sync');await wait("!syncing && !document.getElementById('error').hidden && !catalogBusy()");
 assert(await evaluate(`state.workspace.active_id===${JSON.stringify(session)} && document.getElementById('next-step').hidden`),'A failed sync preserves the review without reviving its completion banner');
 await click('sync');await wait(`!syncing && state.workspace.active_id!==${JSON.stringify(session)} && !catalogBusy()`);
 assert(await evaluate("state.workspace.candidate_count===2 && !state.workspace.ready && document.getElementById('next-step').hidden"),'Retrying with untranslated keys never shows the previous completion banner');
 await openSession(session);await wait("!document.getElementById('next-step').hidden");
 await evaluate("window.originalSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new DOMException('Storage unavailable','SecurityError');};true");
 await click('next-dismiss');
 assert(await evaluate("document.getElementById('next-step').hidden"),'The reminder can still be closed when browser storage cannot be written');
 await evaluate('Storage.prototype.setItem=window.originalSetItem;true');
 assert(errors.length===0,'Browser errors: '+errors.join('; '));
 console.log('OK completion reminder: review lifecycle, component and language isolation, upload acknowledgement, reload, sync and retry.');
} finally {await fetch(`${debug}/json/close/${tab.id}`);ws.close();}
