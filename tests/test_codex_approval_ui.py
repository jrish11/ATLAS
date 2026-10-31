"""Offscreen real agents.html + synthetic supervisor: no app or model is launched."""
import json, os, shutil, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tests.test_shelf_page import HARNESS
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r'''
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const now=Date.now()/1000, id='a'.repeat(32), token='synthetic-token';
const row={id,title:'Synthetic approval',brief:'Fixture only',status:'needs-you',step:'Approval required',created:now,started:now,question:{q:'Allow this Codex action?',cmd:'fixture command',_a:token}};
agents.mode('view'); agents.list([row]); agents.select(id); await wait(50);
const card=document.querySelector('.pk'); if(!card) throw new Error('approval card missing');
const find=(root,label)=>[...root.querySelectorAll('button')].find(b=>b.textContent.trim()===label);
const allow=find(card,'Allow'), deny=find(card,'Don’t Allow');
if(!allow||!deny) throw new Error('approval buttons missing');
allow.click();allow.click();deny.click(); await wait(30);
const stop=find(document,'Stop');if(!stop)throw new Error('stop missing');stop.click();await wait(30);
agents.state({...row,status:'stopped',question:null,step:'Interrupted'});await wait(30);
allow.click();await wait(30);
return {cardPresent:!!card,token,agentId:id,afterRestartCard:!!document.querySelector('.pk')};
'''

class CodexApprovalUI(unittest.TestCase):
 @unittest.skipUnless(sys.platform=='darwin','requires macOS WebKit')
 def test_actual_page_posts_correlated_buttons_and_manager_rejects_duplicates(self):
  with tempfile.TemporaryDirectory(prefix='atticus-approval-ui-') as d:
   root=Path(d); page=root/'agents.html'; source=root/'harness.swift'; binary=root/'harness'
   page.write_text((ROOT/'ui/agents.html').read_text().replace('/*ORBS*/',(ROOT/'ui/orbs.js').read_text()))
   source.write_text(HARNESS)
   env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':d,'TMPDIR':d,'ATTICUS_DIR':str(root/'profile'),
        'ATTICUS_POSTHOG_KEY':'','CLANG_MODULE_CACHE_PATH':str(root/'clang'),'PYTHONPYCACHEPREFIX':str(root/'pycache')}
   built=subprocess.run(['swiftc',str(source),'-o',str(binary)],capture_output=True,text=True,env=env,timeout=90)
   self.assertEqual(built.returncode,0,built.stderr)
   try:run=subprocess.run([str(binary),str(page),SCRIPT],capture_output=True,text=True,timeout=20,env=env)
   except subprocess.TimeoutExpired:self.skipTest('offscreen WebKit host unavailable (timed out)')
   self.assertEqual(run.returncode,0,run.stdout + run.stderr)
   output=json.loads(run.stdout.strip().splitlines()[-1]);posts=output['posts'];result=output['result']
   self.assertFalse([p for p in posts if 'error' in p]);self.assertTrue(result['cardPresent']);self.assertFalse(result['afterRestartCard'])
   answers=[p for p in posts if p.get('action')=='answer'];stops=[p for p in posts if p.get('action')=='stop']
   self.assertEqual([x['answer'] for x in answers],['y','y','n','y'])
   self.assertTrue(all(x['id']==result['agentId'] and x['question']==result['token'] for x in answers))
   self.assertEqual(len(stops),1);self.assertEqual(stops[0]['id'],result['agentId'])
   self.check_real_manager(root, answers,stops[0],result)
 def test_dom_fixture_dispatches_actual_approval_logic_to_manager(self):
  # This executes the real page's approval/button/command definitions against
  # a minimal in-memory DOM. It does not claim to exercise WebKit or a window.
  html=(ROOT/'ui/agents.html').read_text()
  def line(prefix):return next(x for x in html.splitlines() if x.startswith(prefix))
  actual='\n'.join([line('const command='),line('const button='),line('const keyButton='),html[html.index('function setup('):html.index('function mini(')]])
  harness=r"""
const posts=[]; const post=x=>posts.push(x);
function el(tag,cls,text){return {tag,cls,textContent:text||'',children:[],dataset:{},classList:{add(){}},setAttribute(){},append(...x){this.children.push(...x)}}}
const icon=x=>el('svg',x);
"""+actual+r"""
const id='a'.repeat(32),token='synthetic-token';
const card=approval({id,question:{q:'Allow?',cmd:'fixture',_a:token}});
const actions=card.children.find(x=>x.cls==='actions');
const click=label=>actions.children.find(x=>x.textContent===label).onclick({stopPropagation(){}});
click('Allow');click('Allow');click('Don’t Allow');command('stop',id);click('Allow');
console.log(JSON.stringify({posts,agentId:id,token}));
"""
  with tempfile.TemporaryDirectory(prefix='atticus-approval-dom-') as d:
   env={'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':d,'ATTICUS_DIR':str(Path(d,'profile')),'ATTICUS_POSTHOG_KEY':''}
   node=shutil.which('node')
   if not node:self.skipTest('Node unavailable for DOM fixture')
   run=subprocess.run([node,'-e',harness],capture_output=True,text=True,env=env,timeout=10)
   self.assertEqual(run.returncode,0,run.stderr)
   result=json.loads(run.stdout);posts=result['posts'];answers=[x for x in posts if x['action']=='answer'];stops=[x for x in posts if x['action']=='stop']
   self.assertEqual([x['answer'] for x in answers],['y','y','n','y'])
   self.assertTrue(all(x['id']==result['agentId'] and x['question']==result['token'] for x in answers))
   self.check_real_manager(Path(d), answers,stops[0],result)

 def test_manager_denial_cancellation_and_restart_are_fail_closed(self):
  import atticus
  with tempfile.TemporaryDirectory(prefix='atticus-approval-manager-') as d, patch.object(atticus,'DIR',d), patch.object(atticus,'pref',side_effect=lambda k,default:default), patch.object(atticus,'close_agent_window'):
   manager=atticus.Agents(emit=lambda _:None,launch=Mock()); row=manager.new(); row.update(provider='codex',status='needs-you',question={'_a':'token-1'},brief='fixture')
   manager.rows[row['id']]=row; session=Mock(); manager.codex_sessions[row['id']]=session
   pending={'token':'token-1','event':threading.Event(),'decision':'cancel'};manager.codex_approvals[row['id']]=pending
   manager.command({'action':'answer','id':row['id'],'question':'wrong','answer':'y'})
   self.assertFalse(pending['event'].is_set());self.assertEqual(pending['decision'],'cancel')
   manager.command({'action':'answer','id':row['id'],'question':'token-1','answer':'n'})
   self.assertEqual(pending['decision'],'decline');self.assertTrue(pending['event'].is_set())
   pending2={'token':'token-2','event':threading.Event(),'decision':'cancel'}; row['question']={'_a':'token-2'};manager.codex_approvals[row['id']]=pending2
   manager.command({'action':'stop','id':row['id']})
   self.assertTrue(pending2['event'].is_set());self.assertEqual(pending2['decision'],'cancel');self.assertEqual(row['status'],'running');self.assertTrue(row['cancelRequested'])
   manager.codex_sessions.pop(row['id'],None);manager.finish_codex_cancellation(row,'interrupted')
   row.update(status='running',session='thread-1',question={'_a':'obsolete'});manager.save(row);manager.close()
   launches=Mock();restored=atticus.Agents(emit=lambda _:None,launch=launches);self.addCleanup(restored.close)
   self.assertEqual(restored.rows[row['id']]['status'],'stopped')
   restored.command({'action':'answer','id':row['id'],'question':'obsolete','answer':'y'})
   self.assertFalse(restored.codex_approvals);launches.assert_not_called()

 def check_real_manager(self, root, answers, stop, result):
  import atticus
  with patch.object(atticus,'DIR',str(root/'manager')),patch.object(atticus,'pref',side_effect=lambda k,d:d),patch.object(atticus,'close_agent_window'):
   manager=atticus.Agents(emit=lambda _:None, launch=lambda _:None)
   self.addCleanup(manager.close)
   row=manager.new();row.update(id=result['agentId'],provider='codex',status='needs-you',question={'_a':result['token']})
   manager.rows[row['id']]=row
   session=Mock();manager.codex_sessions[row['id']]=session
   pending={'token':result['token'],'event':threading.Event(),'decision':'cancel'};manager.codex_approvals[row['id']]=pending
   manager.command(answers[0]);self.assertEqual(pending['decision'],'accept');self.assertTrue(pending['event'].is_set())
   manager.command(answers[1]);manager.command(answers[2]);self.assertEqual(pending['decision'],'accept')
   manager.command(stop);self.assertEqual(row['status'],'running');self.assertTrue(row['cancelRequested'])
   manager.codex_sessions.pop(row['id'],None);manager.finish_codex_cancellation(row,'interrupted')
   session.interrupt.assert_called_once()
   manager.command(answers[3]);self.assertEqual(pending['decision'],'cancel');self.assertNotIn(row['id'],manager.codex_approvals)
if __name__=='__main__':unittest.main()
