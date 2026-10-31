'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync('ui/remote-phone.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function response(value){return {ok:true,json:async()=>value};}
function harness(){
 const elements={};for(const id of ['state','pair','device','connect','taskArea','task','review','preview','send','stop'])elements[id]={value:'',textContent:'',disabled:false,hidden:false};
 const calls=[],timers=[];let counter=0;
 const ctx={document:{getElementById:id=>elements[id]},location:{hash:'#fixture',pathname:'/'},history:{replaceState(){}},crypto:{randomUUID:()=> (++counter===1?'12345678-1234-4123-8123-123456789abc':'22345678-1234-4123-8123-123456789abc')},setTimeout:fn=>timers.push(fn),fetch:(path,opts)=>{const d=deferred();calls.push({path,body:JSON.parse(opts.body),...d});return d.promise;}};
 vm.runInNewContext(script,ctx);return {elements,calls,timers};
}
async function pair(h){h.elements.device.value='phone';const p=h.elements.connect.onclick();h.calls[0].resolve(response({token:'t',csrf:'c'}));await p;}
async function deferredSubmit(){
 const h=harness(),e=h.elements,c=h.calls;await pair(h);
 e.task.value='task A';e.review.onclick();const pending=e.send.onclick();const idA=c[1].body.id;assert.equal(c[1].body.task,'task A');
 e.task.value='task B';e.task.oninput();e.review.onclick();await e.send.onclick();assert.equal(c.filter(x=>x.path==='/task').length,1);
 const stopping=e.stop.onclick();assert.equal(c[2].path,'/stop');assert.equal(c[2].body.id,idA);c[2].resolve(response({id:idA,status:'cancelling'}));await stopping;const stopped=e.state.textContent;
 c[1].resolve(response({id:idA,status:'submitted'}));await pending;assert.equal(e.state.textContent,stopped);assert.equal(h.timers.length,0);assert.equal(e.send.disabled,true);assert.equal(e.task.disabled,true);
}
async function deferredPoll(){
 const h=harness(),e=h.elements,c=h.calls;await pair(h);e.task.value='task A';e.review.onclick();const pending=e.send.onclick();const idA=c[1].body.id;
 c[1].resolve(response({id:idA,status:'submitted'}));await pending;assert.equal(c[2].path,'/status');assert.equal(c[2].body.id,idA);
 const stopping=e.stop.onclick();assert.equal(c[3].path,'/stop');assert.equal(c[3].body.id,idA);c[3].resolve(response({id:idA,status:'cancelling'}));await stopping;const stopped=e.state.textContent;
 c[2].resolve(response({id:idA,status:'running'}));await Promise.resolve();await Promise.resolve();await Promise.resolve();assert.equal(e.state.textContent,stopped);assert.equal(h.timers.length,0);
}
(async()=>{await deferredSubmit();await deferredPoll();console.log('remote phone deferred-response regressions ok');})().catch(e=>{console.error(e);process.exitCode=1});
