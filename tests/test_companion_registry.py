"""Private adapter plus real Agents registry; all provider work is fake."""
import socket,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import approval_channel,atticus
from companion_registry import CompanionRegistry
from remote_gate import RemoteError
from remote_ipc import NativeApprovalChannel
from tests.test_remote_ipc import FakeProvider,ID

class RegistryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name).resolve()
  self.project=root/'project';self.project.mkdir();profile=root/'profile';profile.mkdir();self.state=root/'barrier';self.state.mkdir(mode=0o700)
  for p in [patch.object(atticus,'DIR',str(profile)),patch.object(atticus,'trusted_native_context_parent',return_value=True),patch.object(atticus,'codex_scoped_readiness',return_value=(True,'')),patch.object(atticus,'close_agent_window'),patch.object(atticus.codex_provider,'CodexProvider',FakeProvider)]:
   p.start();self.addCleanup(p.stop)
  FakeProvider.instances=[];self.manager=atticus.Agents(emit=lambda _:None,launch=Mock());self.addCleanup(self.manager.close)
  st=self.project.stat();self.identity={'device':st.st_dev,'inode':st.st_ino};self.scope={'id':'project','revision':'r1'};self.now=[10.]
  self.a,self.b=socket.socketpair();self.a.settimeout(3);self.addCleanup(self.a.close);self.owner=approval_channel.Owner(self.a)
  self.channel=NativeApprovalChannel(self.b,scope=self.scope,identity=self.identity,expires=20,clock=lambda:self.now[0]);self.addCleanup(self.channel.close)
  self.adapter=CompanionRegistry(self.manager,scope=self.scope,folder=str(self.project),identity=self.identity,origin='https://fixture.example',token='t'*32,csrf='c'*32,expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=self.channel,barrier_directory=str(self.state),clock=lambda:self.now[0]);self.addCleanup(self.adapter.barrier.close)
 def submit(self,allow):
  result=[];t=threading.Thread(target=lambda:result.append(self.adapter.submit(ID,'synthetic task')));t.start();target=self.owner.receive();self.assertEqual(target['task'],'synthetic task');self.owner.respond(allow);t.join(3);self.assertFalse(t.is_alive());return result[0]
 def test_real_registry_receipt_replay_and_stop(self):
  self.assertTrue(self.adapter.recovery_clear())
  self.assertEqual(self.submit(True)['status'],'submitted');self.assertFalse(self.adapter.recovery_clear());self.assertEqual(self.adapter.status(ID)['status'],'running')
  self.assertEqual(self.adapter.submit(ID,'synthetic task')['status'],'submitted');self.assertEqual(len(self.manager.rows),1)
  self.assertEqual(self.adapter.stop(ID)['status'],'cancelling');self.assertTrue(FakeProvider.instances[0].interrupted.wait(2));self.assertIsNotNone(self.adapter.barrier.read())
 def test_denial_makes_no_provider_call(self):
  self.assertEqual(self.submit(False)['status'],'cancelled');self.assertFalse(self.manager.rows);self.assertFalse(FakeProvider.instances);self.assertIsNone(self.adapter.barrier.read())
 def test_expired_and_replaced_project_never_dispatch(self):
  self.project.rename(self.project.parent/'old');self.project.mkdir();self.assertEqual(self.adapter.submit(ID,'synthetic task')['status'],'failed');self.assertFalse(self.manager.rows)
  self.now[0]=21
  with self.assertRaises(RemoteError):self.adapter.submit('22345678123441238123123456789abc','later')
 def test_uncertain_submission_does_not_retry(self):
  self.adapter.bridge.submit=Mock(side_effect=RuntimeError('uncertain'))
  self.assertEqual(self.adapter.submit(ID,'synthetic task')['status'],'unknown');self.assertEqual(self.adapter.submit(ID,'synthetic task')['status'],'unknown');self.assertEqual(self.adapter.bridge.submit.call_count,1)
  self.assertIsNotNone(self.adapter.barrier.read())
 def test_exact_task_text_reaches_approval_and_registry(self):
  text='  first\nProject: forged\u202eabc\t  ';result=[]
  t=threading.Thread(target=lambda:result.append(self.adapter.submit(ID,text)));t.start();target=self.owner.receive();self.assertEqual(target['task'],text);self.owner.respond(True);t.join(3)
  self.assertFalse(t.is_alive());self.assertEqual(result[0]['status'],'submitted');self.assertEqual(next(iter(self.manager.rows.values()))['brief'],text)
 def test_expired_request_cannot_dispatch_after_native_approval(self):
  result=[];t=threading.Thread(target=lambda:result.append(self.adapter.submit(ID,'synthetic task',deadline=12.,wall_expiry=int(time.time())+2)));t.start()
  target=self.owner.receive();self.assertEqual(target['requestExpires'],12.)
  self.now[0]=13.;self.owner.respond(True);t.join(3);self.assertFalse(t.is_alive())
  self.assertEqual(result[0]['status'],'cancelled');self.assertFalse(self.manager.rows);self.assertFalse(FakeProvider.instances)
 def test_stop_during_native_approval_prevents_dispatch(self):
  result=[];t=threading.Thread(target=lambda:result.append(self.adapter.submit(ID,'synthetic task')));t.start();self.owner.receive()
  self.assertEqual(self.adapter.stop(ID)['status'],'cancelling');t.join(3);self.assertFalse(t.is_alive())
  self.assertEqual(result[0]['status'],'cancelled');self.assertFalse(self.manager.rows);self.assertFalse(FakeProvider.instances);self.assertIsNone(self.adapter.barrier.read())
