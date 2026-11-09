const [base,debug]=process.argv.slice(2);
const tab=await(await fetch(`${debug}/json/new?${encodeURIComponent('about:blank')}`,{method:'PUT'})).json();
const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let seq=0;const pending=new Map(),errors=[];
ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function wait(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,70));}throw new Error('Timeout: '+expression+' · '+await evaluate("(typeof lastError!=='undefined'?lastError:'')+' · '+document.getElementById('sync-current').textContent"));}
async function click(id){await evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);}
function assert(value,message){if(!value)throw new Error(message);}
const pick=(id,value)=>evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change'));return el.value;})()`);
try {
 await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base});
 await wait("typeof state!=='undefined' && state && !catalogBusy() && [...document.getElementById('language').options].some(o=>o.value==='fr_ca')");
 await pick('component','regulations');
 await wait("!catalogBusy() && [...document.getElementById('language').options].some(o=>o.value==='fr_ca')");
 assert(await pick('language','fr_ca')==='fr_ca','Target language selectable');
 assert(await evaluate("[...document.getElementById('reference').options].map(o=>o.value).join(',')===',fr,es_419' && document.getElementById('reference').value==='fr'"),'fr-CA defaults to French and excludes the target');
 await pick('reference','');await pick('language','es_419');
 assert(await evaluate("document.getElementById('reference').value===''"),'Other targets default to None');
 await pick('language','fr_ca');
 assert(await evaluate("document.getElementById('reference').value===''"),'Explicit None overrides the default');
 assert(await pick('reference','fr')==='fr' && await evaluate("localStorage.getItem('wca-reference:fr_ca')==='fr'"),'Reference remembered per target');
 await evaluate("document.getElementById('manual-mode').checked=true;document.getElementById('manual-mode').dispatchEvent(new Event('change'));true");
 await click('sync');await wait("!syncing && state.workspace.reference?.language==='fr'");
 assert(await evaluate("!document.getElementById('reference-proposals').hidden && document.getElementById('reference-proposals').textContent==='Use French as proposals'"),'Reference proposals offered');
 await click('reference-proposals');await wait("state.workspace.ready && saving===0");
 await evaluate("act(()=>select(state.entries.find(e=>e.context==='meal').key))");
 await wait("current()?.context==='meal' && !document.getElementById('reference-panel').hidden");
 assert(await evaluate("(()=>{const m=document.querySelector('#reference-text mark.flag');return m && m.textContent==='Petit-déjeuner' && m.title.includes('Déjeuner');})()"),'Divergent glossary term is flagged');
 assert(await evaluate("document.getElementById('metadata').textContent.includes('Petit-déjeuner → Déjeuner')"),'Flags listed in details');
 assert(await evaluate("current().proposed[0]==='Petit-déjeuner à %s' && current().note.includes('Petit-déjeuner → Déjeuner') && state.counts.pending===2"),'Reference copied as pending proposals');
 assert(await evaluate("document.querySelector('.comparison h3').textContent==='Reference · fr'"),'Empty original is compared with the reference');
 assert(await evaluate("!document.getElementById('use-reference').hidden && document.getElementById('use-reference').textContent==='Use French U'"),'Use reference button shown');
 await evaluate("current().proposed=['Unwanted AI text'];true");
 await click('use-reference');await wait("editing && document.querySelector('.edit-form')?.value==='Petit-déjeuner à %s' && saving===0");
 assert(await evaluate("current().decision.status==='pending' && current().decision.draft[0]==='Petit-déjeuner à %s'"),'Reference becomes a pending draft, not an approval');
 await evaluate("const f=document.querySelector('.edit-form');f.value='Déjeuner à %s';f.dispatchEvent(new Event('input',{bubbles:true}));true");
 await wait('!dirty && saving===0');
 await click('accept');await wait("state.counts.edited===1 && saving===0");
 assert(await evaluate("[...document.querySelectorAll('.comparison .removed')].map(s=>s.textContent).join('').includes('Petit')"),'Diff against the reference shows removed words');
 await send('Page.reload');
 await wait("typeof state!=='undefined' && state && !catalogBusy() && document.getElementById('language').value==='fr_ca' && document.getElementById('reference').options.length>1");
 assert(await evaluate("document.getElementById('reference').value==='fr'"),'Reference restored after reload');
 assert(await evaluate("current()?.context==='meal' && state.entries[0].context!=='meal'"),'Reload resumes at the last entry, not the first');
 assert(await pick('language','es_419')==='es_419' && await evaluate("document.getElementById('reference').value===''"),'Other targets keep the English default');
 assert(errors.length===0,'Browser errors: '+errors.join('; '));
 console.log('OK reference: opt-in fr → fr-CA, flagged glossary terms, reference proposals, diff, edit and remembered choice.');
} finally {await fetch(`${debug}/json/close/${tab.id}`);ws.close();}
