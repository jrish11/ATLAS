"""Synthetic tests for the unintegrated cancellation patch; no real provider/UI."""
import importlib.util,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent;sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('atticus_cancel_candidate',ROOT/'atticus.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class FakeTimer:
 timers=[]
 def __init__(self,secs,fn):self.fn=fn;self.daemon=False;self.timers.append(self)
 def start(self):pass
 def fire(self):self.fn()
class FakeProvider:
 instances=[]; response={}
 def __init__(self,**kw):self.release=threading.Event();self.interrupted=threading.Event();self.closed=threading.Event();self.response=dict(self.response);self.instances.append(self)
 def run(self,*args):self.release.wait(3);return self.response
 def interrupt(self):self.interrupted.set()
 def close(self):self.closed.set();self.release.set()
class CancellationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.stack=[patch.object(a,'DIR',self.tmp.name),patch.object(a,'CODEX_AGENT_READY',True),patch.object(a,'pref',side_effect=lambda k,d:d),patch.object(a,'close_agent_window'),patch.object(a.codex_provider,'CodexProvider',FakeProvider),patch.object(a.threading,'Timer',FakeTimer)]
  for x in self.stack:x.start();self.addCleanup(x.stop)
  FakeTimer.timers=[];FakeProvider.instances=[]
  self.events=[];self.m=a.Agents(emit=self.events.append,launch=Mock());self.m.drain=Mock();self.addCleanup(self.m.close)
  self.row=self.m.new();self.row.update(provider='codex',status='running',brief='fixture',folder=self.tmp.name)
  self.m.rows[self.row['id']]=self.row;self.m.save(self.row)
 def wait(self,predicate):
  end=time.monotonic()+2
  while time.monotonic()<end:
   if predicate():return
   time.sleep(.01)
  self.fail('fixture worker timed out')
 def start_and_cancel(self):
  self.m.start_codex(self.row,'fixture');p=FakeProvider.instances[-1]
  self.m.command({'action':'stop','id':self.row['id']});self.assertTrue(p.interrupted.wait(1))
  self.assertTrue(self.row['cancelRequested']);self.assertEqual(self.row['status'],'running')
  self.m.command({'action':'stop','id':self.row['id']});self.assertEqual(len(FakeTimer.timers),1)
  self.m.command({'action':'start','id':self.row['id']});self.assertEqual(len(FakeProvider.instances),1)
  return p
 def test_terminal_outcomes_and_review_gate(self):
  for status,outcome in [('interrupted','interrupted'),('completed','completed_before_cancel'),('failed','failed'),(None,'unknown')]:
   with self.subTest(status=status):
    FakeProvider.response={'status':'stopped','result':'fixture','server_status':status}
    p=self.start_and_cancel();p.release.set();self.wait(lambda:self.row.get('cancelOutcome')==outcome)
    self.assertEqual(self.row['status'],'stopped');self.assertTrue(self.row['cancelReviewRequired'])
    self.m.command({'action':'start','id':self.row['id']});self.assertEqual(len(FakeProvider.instances),1)
    self.m.command({'action':'review-cancel','id':self.row['id'],'confirmed':False});self.assertTrue(self.row['cancelReviewRequired'])
    self.m.command({'action':'review-cancel','id':self.row['id'],'confirmed':True});self.assertFalse(self.row['cancelReviewRequired'])
    events=[json.loads(x) for x in Path(self.row['directory'],'log.jsonl').read_text().splitlines()]
    self.assertIn('codex-cancellation-requested',[x['event'] for x in events]);self.assertIn('codex-cancellation-outcome',[x['event'] for x in events]);self.assertIn('codex-cancellation-reviewed',[x['event'] for x in events])
    FakeProvider.instances=[];FakeTimer.timers=[];self.row.pop('cancelOutcome',None);self.row.update(status='running',cancelRequested=False,cancelReviewRequired=False)
 def test_pending_approval_is_cancelled_and_cannot_authorize_late(self):
  FakeProvider.response={'status':'stopped','server_status':'interrupted'}
  self.m.start_codex(self.row,'fixture');p=FakeProvider.instances[-1]
  pending={'token':'fixture-token','event':threading.Event(),'decision':'cancel'}
  self.row.update(status='needs-you',question={'_a':'fixture-token'});self.m.codex_approvals[self.row['id']]=pending
  self.m.command({'action':'stop','id':self.row['id']})
  self.assertTrue(pending['event'].is_set());self.assertEqual(pending['decision'],'cancel')
  self.m.command({'action':'answer','id':self.row['id'],'question':'fixture-token','answer':'y'})
  self.assertEqual(pending['decision'],'cancel');p.release.set();self.wait(lambda:self.row.get('cancelOutcome')=='interrupted')
 def test_timeout_and_late_completion_cannot_revive(self):
  FakeProvider.response={'status':'done','result':'late'};p=self.start_and_cancel();FakeTimer.timers[0].fire()
  self.assertEqual(self.row['cancelOutcome'],'timeout_unknown');self.assertTrue(self.row['cancelReviewRequired']);p.release.set()
  self.wait(lambda:p.closed.is_set());time.sleep(.03);self.assertEqual(self.row['status'],'stopped');self.assertEqual(self.row['cancelOutcome'],'timeout_unknown')
 def test_restart_with_pending_cancel_is_unknown_and_not_resumed(self):
  FakeProvider.response={'status':'done','result':'late'};p=self.start_and_cancel();identifier=self.row['id'];self.m.close()
  launches=Mock();m2=a.Agents(emit=lambda _:None,launch=launches);self.addCleanup(m2.close)
  row=m2.rows[identifier];self.assertEqual(row['cancelOutcome'],'restart_unknown');self.assertTrue(row['cancelReviewRequired'])
  m2.command({'action':'start','id':identifier});launches.assert_not_called();self.assertFalse(m2.codex_sessions)
if __name__=='__main__':unittest.main()
