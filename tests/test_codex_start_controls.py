"""Actual Agents controller logic on a synthetic DOM; no native window or provider."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CodexStartControls(unittest.TestCase):
 def run_js(self, body):
  node=shutil.which('node')
  if not node:self.skipTest('Node required for JavaScript controller fixtures')
  html=(ROOT/'ui/agents.html').read_text()
  actual=html[html.index('// CODEX CONTROLS:'):html.index('// END CODEX CONTROLS')]
  base=r'''
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const posts=[],elements=new Map(),ACTIVE=['running','needs-you','waiting-screen','queued'];let rows=[];
const $=id=>{if(!elements.has(id))elements.set(id,{value:'',checked:false,disabled:false,textContent:'',hidden:true,children:[],focus(){},append(...v){this.children.push(...v)}});return elements.get(id)};
const setText=(n,s)=>{n.textContent=s};const command=(action,id,more={})=>posts.push({action,id,...more});
const el=(tag,cls,text)=>({tag,cls,textContent:text,children:[],append(...v){this.children.push(...v)}});
const button=(text,fn)=>({textContent:text,onclick:fn,disabled:false});const showNamedStatus=s=>setText($('status'),s);
'''
  result=subprocess.run([node,'-e',base+actual+'\n'+body],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr[-2500:])

 def test_scope_confirmation_malformed_and_ambiguous_inputs(self):
  self.run_js(r'''
for(const args of [[null,'x',true],['/tmp','x',false],['~/project','x',true],['/','x',true],['/tmp\nother','x',true],['/tmp','',true],['/tmp','x'.repeat(4001),true]])assert.throws(()=>codexStartPayload(...args,[]));
const active={provider:'codex',folder:'/fixture',brief:'inspect',status:'running'};
assert.throws(()=>codexStartPayload('/fixture','inspect',true,[active]));
assert.throws(()=>codexStartPayload('','inspect',true,[active]));
assert.throws(()=>codexStartPayload('/fixture','inspect',true,[{...active,status:'stopped',cancelReviewRequired:true}]));
const automatic=codexStartPayload('','inspect',true,[]);assert.equal(automatic.folder,'');
const p=codexStartPayload(' /fixture ',' inspect ',true,[]);assert.equal(p.folder,'/fixture');assert.equal(p.task,'inspect');assert.match(p.requestId,/^[a-f0-9-]{36}$/);
assert.equal(posts.length,0);
''')

 def test_pending_recovery_requires_owner_review_and_never_retries(self):
  self.run_js(r'''
$('codex-folder').value='/fixture';$('codex-task').value='inspect';submitCodexTask();
reviewCodexPending();assert.ok(codexPending);assert.equal(posts.length,1);
$('codex-reviewed').checked=true;reviewCodexPending();assert.equal(codexPending,null);assert.equal(posts.length,1);
assert.equal(posts.length,1);
''')

 def test_native_cancel_unlocks_only_its_own_pending_request(self):
  self.run_js(r'''
$('codex-folder').value='/fixture';$('codex-task').value='inspect';submitCodexTask();
codexNativeCancelled('stale');assert.ok(codexPending);assert.equal($('codex-submit').disabled,true);
codexNativeCancelled(posts[0].requestId);assert.equal(codexPending,null);assert.equal($('codex-submit').disabled,false);assert.equal(posts.length,1);
''')

 def test_only_correlated_start_error_unlocks_and_displays_reason(self):
  self.run_js(r'''
$('codex-folder').value='';$('codex-task').value='inspect';submitCodexTask();
codexNativeError({id:'stale',error:'wrong'});assert.ok(codexPending);
codexNativeError({id:posts[0].requestId,error:'fixture unavailable'});assert.equal(codexPending,null);assert.equal($('codex-submit').disabled,false);assert.equal($('codex-start-status').textContent,'fixture unavailable');
''')

 def test_submit_once_then_wait_for_actual_record(self):
  self.run_js(r'''
$('codex-folder').value='/fixture';$('codex-task').value='<script>untrusted text</script>';
submitCodexTask();submitCodexTask();assert.equal(posts.length,1);assert.equal(posts[0].action,'codex-start');assert.equal(posts[0].task,'<script>untrusted text</script>');assert.equal($('codex-submit').disabled,true);
codexObserve([{provider:'codex',folder:'/other',brief:posts[0].task,created:Date.now()/1000}]);assert.ok(codexPending);
codexObserve([{provider:'codex',folder:'/fixture',brief:posts[0].task,created:0}]);assert.ok(codexPending);
codexObserve([{provider:'codex',folder:'/fixture',brief:posts[0].task,codexClientRequest:posts[0].requestId,created:Date.now()/1000}]);assert.equal(codexPending,null);assert.equal($('new-codex').disabled,false);assert.equal(posts.length,1);
''')

 def test_continue_rejects_inflight_review_and_repeated_actions(self):
  self.run_js(r'''
const r={id:'fixture-agent',provider:'codex',folder:'/fixture',status:'done'};
rows=[r];
for(const status of ['running','needs-you','queued','offered'])assert.equal(continueCodexTask({...r,status},'next'),false);
assert.equal(continueCodexTask({...r,cancelReviewRequired:true},'next'),false);
assert.equal(continueCodexTask({...r,cancelRequested:true},'next'),false);
assert.equal(continueCodexTask(r,''),false);assert.equal(continueCodexTask(r,'next'),true);assert.equal(continueCodexTask(r,'next'),false);
assert.deepEqual(posts,[{action:'followup',id:'fixture-agent',text:'next'}]);
const active={...r,status:'running'};rows=[active];codexObserve(rows);assert.equal(continueCodexTask(active,'next'),false);assert.equal(continueCodexTask(r,'late stale click'),false);
assert.equal(codexCanContinue({...r,status:'stopped',cancelReviewRequired:true}),false);
''')

 def test_cancellation_status_is_not_a_false_stopped_claim(self):
  self.run_js(r'''
const r={id:'fixture',provider:'codex',folder:'/fixture',status:'running',cancelRequested:true};
const pending=codexScopeCard(r);assert.ok(pending.children.some(x=>x.textContent==='Cancellation requested; no interruption has been confirmed.'));
const done=codexScopeCard({...r,status:'done',cancelRequested:false});assert.ok(done.children.some(x=>x.textContent?.includes('inspect the work')));
assert.equal(posts.length,0);
''')

 def test_full_module_syntax_and_real_form_bindings(self):
  html=(ROOT/'ui/agents.html').read_text();node=shutil.which('node')
  if not node:self.skipTest('Node unavailable')
  self.assertIn("$('codex-form').onsubmit=e=>{e.preventDefault();submitCodexTask();};",html)
  self.assertIn("$('codex-dismiss').onclick=()=>{$('codex-create').hidden=true;};",html)
  self.assertIn('You will review the project and task before Codex starts.',html)
  self.assertIn("command('choose-codex-folder','')",html)
  self.assertNotIn('id="codex-confirm"',html)
  swift=(ROOT/'Atticus.swift').read_text()
  chooser=swift.split('        case "choose-codex-folder":',1)[1].split('        case "codex-start":',1)[0]
  self.assertIn('picker.runModal() == .OK',chooser)
  self.assertNotIn('self.send(',chooser)
  module=html.split('<script type="module">',1)[1].split('</script>',1)[0]
  with tempfile.TemporaryDirectory(prefix='atticus-agents-syntax-') as d:
   p=Path(d,'agents.mjs');p.write_text(module)
   result=subprocess.run([node,'--check',str(p)],capture_output=True,text=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
