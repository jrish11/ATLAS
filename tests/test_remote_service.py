"""Loopback integration against the real Agents registry and a fake provider."""
import http.client,json,os,socket,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import approval_channel,atticus
from remote_gate import RemoteError
from remote_service import RemoteSession
from tests.test_remote_ipc import FakeProvider, ID

class ServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name).resolve()
  self.project=root/'project';self.project.mkdir();self.profile=root/'profile';self.profile.mkdir();self.barrier=root/'barrier';self.barrier.mkdir(mode=0o700)
  for p in [patch.object(atticus,'DIR',str(self.profile)),patch.object(atticus,'trusted_native_context_parent',return_value=True),patch.object(atticus,'codex_scoped_readiness',return_value=(True,'')),patch.object(atticus,'close_agent_window'),patch.object(atticus.codex_provider,'CodexProvider',FakeProvider)]:
   p.start();self.addCleanup(p.stop)
  FakeProvider.instances=[];self.manager=atticus.Agents(emit=lambda _:None,launch=Mock());self.addCleanup(self.manager.close)
  self.now=[10.];self.scope={'id':'fixture','revision':'1'};st=self.project.stat();self.identity={'device':st.st_dev,'inode':st.st_ino};self.sessions=[]
  self.owner_sock,self.child_sock=socket.socketpair();self.addCleanup(self.owner_sock.close);self.owner_sock.settimeout(3);self.owner=approval_channel.Owner(self.owner_sock)
  self.session=self.make(self.child_sock);self.addCleanup(self.cleanup_sessions)
 def cleanup_sessions(self):
  for session in self.sessions:session.close();session.barrier.close()
 def make(self,sock,token='t'*32,invitation=None):
  s=RemoteSession(self.manager,owner_socket=sock,folder=str(self.project),identity=self.identity,scope=self.scope,origin='https://atlas.test',token=token,csrf='c'*32,expires=20,barrier_directory=str(self.barrier),verify_scope=atticus.codex_project_matches,clock=lambda:self.now[0],invitation=invitation);self.sessions.append(s);return s
 def post(self,path,body,token='t'*32):
  c=http.client.HTTPConnection('127.0.0.1',self.session.port,timeout=3);headers={'Host':'atlas.test','Origin':'https://atlas.test','Content-Type':'application/json','X-Atlas-Token':token,'X-Atlas-CSRF':'c'*32}
  c.request('POST',path,json.dumps(body),headers);r=c.getresponse();out=(r.status,json.loads(r.read()));c.close();return out
 def request_with_decision(self,allow):
  result=[];t=threading.Thread(target=lambda:result.append(self.post('/task',{'id':ID,'task':'synthetic'})));t.start()
  target=self.owner.receive();self.assertEqual(target['folder'],str(self.project));self.owner.respond(allow);t.join(3);self.assertFalse(t.is_alive());return result[0]
 def test_registry_replay_status_stop_and_restart_barrier(self):
  self.assertEqual(self.request_with_decision(True)[1]['status'],'submitted')
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[1]['status'],'submitted')
  self.assertEqual(len(self.manager.rows),1);self.assertEqual(self.post('/status',{'id':ID})[1]['status'],'running')
  self.assertEqual(self.post('/stop',{'id':ID})[1]['status'],'cancelling');self.assertTrue(FakeProvider.instances[0].interrupted.wait(2))
  self.session.close();a,b=socket.socketpair();self.addCleanup(a.close)
  with self.assertRaises(RemoteError):self.make(b,token='n'*32)
 def test_denial_does_not_dispatch(self):
  self.assertEqual(self.request_with_decision(False)[1]['status'],'cancelled');self.assertFalse(self.manager.rows)
 def test_replaced_project_does_not_dispatch(self):
  self.project.rename(self.project.parent/'old');self.project.mkdir()
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[1]['status'],'failed');self.assertFalse(self.manager.rows)
 def test_rotation_rejects_prior_credentials(self):
  self.session.close();a,b=socket.socketpair();self.addCleanup(a.close)
  self.session=self.make(b,token='n'*32)
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[0],403);self.assertFalse(self.manager.rows)
 def test_uncertain_dispatch_blocks_restart_without_retry(self):
  self.session.bridge.submit=Mock(side_effect=RuntimeError('uncertain'))
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[1]['status'],'unknown')
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[1]['status'],'unknown')
  self.assertEqual(self.session.bridge.submit.call_count,1)
  self.session.close();a,b=socket.socketpair();self.addCleanup(a.close)
  with self.assertRaises(RemoteError):self.make(b,token='n'*32)
 def test_expiry_revokes_and_stale_credentials_are_rejected(self):
  self.now[0]=21
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[0],403);self.assertFalse(self.manager.rows)
 def test_parent_channel_loss_revokes(self):
  self.owner_sock.close();self.assertTrue(self.session._closed.wait(2));self.assertFalse(self.manager.rows)
 def test_review_waits_for_inflight_dispatch_to_settle(self):
  entered=threading.Event();release=threading.Event()
  def uncertain(*args):entered.set();release.wait(3);raise RuntimeError('uncertain')
  self.session.bridge.submit=uncertain
  result=[];t=threading.Thread(target=lambda:result.append(self.post('/task',{'id':ID,'task':'synthetic'})));t.start()
  self.assertTrue(entered.wait(2));self.session.close();self.assertFalse(self.session.reviewable())
  release.set();t.join(3);self.assertFalse(t.is_alive());self.assertTrue(self.session.reviewable())
 def test_pairing_requires_native_approval_and_cannot_replay(self):
  self.session.close();a,b=socket.socketpair();self.addCleanup(a.close);a.settimeout(3);owner=approval_channel.Owner(a)
  self.session=self.make(b,invitation='i'*32)
  c=http.client.HTTPConnection('127.0.0.1',self.session.port,timeout=3);c.request('GET','/',headers={'Host':'atlas.test'});r=c.getresponse();self.assertEqual(r.status,200);self.assertIn(b'ATLAS Remote',r.read());c.close()
  c=http.client.HTTPConnection('127.0.0.1',self.session.port,timeout=3);c.request('GET','/',headers={'Host':'attacker.test'});r=c.getresponse();self.assertEqual(r.status,403);r.read();c.close()
  self.assertEqual(self.post('/task',{'id':ID,'task':'synthetic'})[0],403)
  results=[];t=threading.Thread(target=lambda:results.append(self.post('/pair',{'code':'i'*32,'device':'test phone'})));t.start()
  target=owner.receive();self.assertEqual(target['action'],'remote-pair');self.assertEqual(target['device'],'test phone');owner.respond(True);t.join(3)
  self.assertEqual(results[0],(200,{'token':'t'*32,'csrf':'c'*32}))
  self.assertEqual(self.post('/pair',{'code':'i'*32,'device':'test phone'})[0],403)
 def test_pairing_denial_releases_no_credentials(self):
  self.session.close();a,b=socket.socketpair();self.addCleanup(a.close);a.settimeout(3);owner=approval_channel.Owner(a)
  self.session=self.make(b,invitation='i'*32)
  results=[];t=threading.Thread(target=lambda:results.append(self.post('/pair',{'code':'i'*32,'device':'test phone'})));t.start()
  owner.receive();owner.respond(False);t.join(3)
  self.assertEqual(results[0][0],403);self.assertFalse(self.manager.rows)
