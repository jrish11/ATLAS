"""Synthetic crash barriers; no owner data or native authorization."""
import os,tempfile,threading,unittest
from unittest.mock import Mock
from remote_gate import RemoteGate,RemoteError
from pathlib import Path
from remote_barrier import DurableBarrier,BarrierError

ID='12345678123441238123123456789abc'
class BarrierTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.b=DurableBarrier(str(self.root));self.addCleanup(self.b.close)
 def test_intent_survives_restart_and_needs_matching_reconciliation(self):
  self.b.reserve(ID,{'id':'project','revision':'1'});row=self.b.read()
  self.assertEqual(row['id'],ID);self.assertNotIn('project',str(row))
  other=DurableBarrier(str(self.root));self.addCleanup(other.close)
  self.assertEqual(other.read(),row)
  with self.assertRaises(BarrierError):other.reserve('22345678123441238123123456789abc',{})
  with self.assertRaises(BarrierError):other.clear('22345678123441238123123456789abc')
  other.clear(ID);self.assertIsNone(self.b.read())
 def test_symlink_fifo_and_malformed_receipts_fail_closed(self):
  p=self.root/'remote-pending.json'
  p.symlink_to('/tmp/missing-synthetic')
  with self.assertRaises(BarrierError):self.b.read()
  with self.assertRaises(BarrierError):self.b.reserve(ID,{})
  p.unlink();os.mkfifo(p)
  with self.assertRaises(BarrierError):self.b.read()
  p.unlink();p.write_text('{bad');p.chmod(0o600)
  with self.assertRaises(BarrierError):self.b.read()
  with self.assertRaises(BarrierError):self.b.reserve(ID,{})
 def test_gate_persists_before_dispatch_and_blocks_pair_after_restart(self):
  clock=lambda:10.;bridge=Mock();bridge.valid_scope.return_value=True
  bridge.submit.side_effect=lambda *args: self.assertEqual(self.b.read()['id'],ID) or 'submitted'
  scope={'id':'project','revision':'one'};auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  gate=RemoteGate(clock=clock,barrier=self.b);gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope=scope,bridge=bridge,expires=20)
  self.assertEqual(gate.request(**auth,body={'id':ID,'task':'synthetic'})['status'],'submitted')
  fresh=RemoteGate(clock=clock,barrier=self.b)
  with self.assertRaises(RemoteError):fresh.owner_enable(origin=auth['origin'],token='n'*32,csrf='m'*32,scope=scope,bridge=bridge,expires=20)
  self.assertTrue(gate.owner_result(ID,gate._generation,'completed'));self.assertIsNone(self.b.read())
  fresh.owner_enable(origin=auth['origin'],token='n'*32,csrf='m'*32,scope=scope,bridge=bridge,expires=20)
 def test_stop_during_slow_reservation_prevents_dispatch(self):
  entered=threading.Event();release=threading.Event();actual=self.b
  class SlowBarrier:
   def read(self):return actual.read()
   def reserve(self,*args):entered.set();release.wait(2);return actual.reserve(*args)
   def clear(self,*args):return actual.clear(*args)
  bridge=Mock();bridge.valid_scope.return_value=True
  auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  gate=RemoteGate(clock=lambda:10.,barrier=SlowBarrier());gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope={'id':'p','revision':'r'},bridge=bridge,expires=20)
  result=[];worker=threading.Thread(target=lambda:result.append(gate.request(**auth,body={'id':ID,'task':'synthetic'})));worker.start()
  self.assertTrue(entered.wait(1));self.assertEqual(gate.stop(**auth,ident=ID)['status'],'cancelling')
  release.set();worker.join(2);self.assertEqual(result[0]['status'],'cancelled');self.assertIsNone(self.b.read());bridge.submit.assert_not_called()
 def test_persistence_failure_never_dispatches(self):
  self.b.reserve(ID,{})
  bridge=Mock();bridge.valid_scope.return_value=True;gate=RemoteGate(clock=lambda:10.,barrier=self.b)
  with self.assertRaises(RemoteError):gate.owner_enable(origin='https://fixture.example',token='t'*32,csrf='c'*32,scope={'id':'p','revision':'r'},bridge=bridge,expires=20)
  bridge.submit.assert_not_called()
 def test_insecure_root_is_rejected(self):
  other=self.root/'broad';other.mkdir(mode=0o755);other.chmod(0o755)
  with self.assertRaises(BarrierError):DurableBarrier(str(other))
