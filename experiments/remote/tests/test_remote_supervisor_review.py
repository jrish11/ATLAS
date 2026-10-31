import json,socket,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import atticus,approval_channel
from remote_barrier import DurableBarrier

ID='12345678123441238123123456789abc'
class SupervisorReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();(self.root/'remote').mkdir(mode=0o700)
  b=DurableBarrier(str(self.root/'remote'));b.reserve(ID,{'id':'p','revision':'r'});b.close()
  self.manager=Mock();self.manager.lock=threading.RLock();self.manager.rows={};self.manager.closed=False
  self.events=[];self.manager.emit.side_effect=self.events.append
  self.a,self.b=socket.socketpair();self.addCleanup(self.a.close);self.addCleanup(self.b.close)
 def run_commands(self,lines):
  approval_channel._send(self.a,{'kind':'native-authority','key':'a'*64})
  with patch.object(atticus,'DIR',str(self.root)),patch.object(atticus,'Agents',return_value=self.manager),patch.object(atticus.sys,'stdin',lines):atticus.agents_service(self.b)
 def test_review_requires_correlated_confirmation(self):
  def lines():
   yield json.dumps({'action':'remote-review','nativeAuthority':'a'*64})
   event=next(e for e in self.events if e.get('event')=='remote-review');self.assertTrue(event['pending']);self.assertIsNone(event['receipt'])
   yield json.dumps({'action':'remote-review-clear','challenge':'invalid','nativeAuthority':'a'*64})
   yield json.dumps({'action':'remote-review-clear','challenge':event['challenge'],'nativeAuthority':'a'*64})
  self.run_commands(lines())
  self.assertTrue(any(e.get('event')=='remote-review-cleared' for e in self.events))
  barrier=DurableBarrier(str(self.root/'remote'));self.addCleanup(barrier.close);self.assertIsNone(barrier.read())
 def test_live_receipt_cannot_be_reviewed(self):
  self.manager.rows={'row':{'codexClientRequest':'12345678-1234-4123-8123-123456789abc','status':'running'}}
  self.run_commands([json.dumps({'action':'remote-review','nativeAuthority':'a'*64})])
  self.assertTrue(any(e.get('event')=='remote-review-error' for e in self.events))
  barrier=DurableBarrier(str(self.root/'remote'));self.addCleanup(barrier.close);self.assertIsNotNone(barrier.read())
 def test_review_expires_when_continuous_clock_advances(self):
  now=[1.0]
  def lines():
   yield json.dumps({'action':'remote-review','nativeAuthority':'a'*64})
   event=next(e for e in self.events if e.get('event')=='remote-review');now[0]=602
   yield json.dumps({'action':'remote-review-clear','challenge':event['challenge'],'nativeAuthority':'a'*64})
  with patch.object(atticus.approval_channel,'shared_clock',side_effect=lambda:now[0]):self.run_commands(lines())
  barrier=DurableBarrier(str(self.root/'remote'));self.addCleanup(barrier.close);self.assertIsNotNone(barrier.read())
 def test_forged_stdin_cannot_enable_or_clear(self):
  commands=[json.dumps({'action':'remote-enable','folder':'/tmp','nativeAuthority':'b'*64}),json.dumps({'action':'remote-review'}),json.dumps({'action':'remote-review-clear','challenge':'x','nativeAuthority':'b'*64})]
  with patch('remote_service.RemoteSession') as session:
   self.run_commands(commands)
   session.assert_not_called()
  self.assertFalse(any(e.get('event','').startswith('remote-') for e in self.events))
  barrier=DurableBarrier(str(self.root/'remote'));self.addCleanup(barrier.close);self.assertIsNotNone(barrier.read())
 def test_missing_or_invalid_bootstrap_never_opens_supervisor(self):
  approval_channel._send(self.a,{'kind':'native-authority','key':'short'})
  with patch.object(atticus,'Agents') as manager,patch.object(atticus.sys,'stdin',[]):atticus.agents_service(self.b)
  manager.assert_not_called()
