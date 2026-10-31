"""Synthetic private socket/real registry tests; no listener, account or model."""
import os,socket,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import approval_channel,atticus
from remote_gate import NotDispatched,RemoteGate,RemoteError,DispatchToken
from remote_ipc import NativeRegistryBridge,NativeApprovalChannel,serve_one

ID='12345678123441238123123456789abc'
class FakeProvider:
 instances=[]
 def __init__(self,**kwargs):
  self.release=threading.Event();self.interrupted=threading.Event();self.instances.append(self)
 def run(self,*args,**kwargs):
  self.release.wait(2)
  return {'status':'stopped','result':'synthetic','server_status':'interrupted'}
 def interrupt(self):self.interrupted.set();self.release.set()
 def close(self):self.release.set()

class RemotePrivateIPCTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup)
  root=Path(self.tmp.name).resolve();self.project=root/'project';self.project.mkdir();self.profile=root/'profile';self.profile.mkdir()
  self.patches=[patch.object(atticus,'DIR',str(self.profile)),patch.object(atticus,'trusted_native_context_parent',return_value=True),patch.object(atticus,'codex_scoped_readiness',return_value=(True,'')),patch.object(atticus,'close_agent_window'),patch.object(atticus.codex_provider,'CodexProvider',FakeProvider)]
  for p in self.patches:p.start();self.addCleanup(p.stop)
  FakeProvider.instances=[];self.events=[];self.manager=atticus.Agents(emit=self.events.append,launch=Mock());self.addCleanup(self.manager.close)
  st=self.project.stat();self.scope={'id':'fixture','revision':'revision-1'};self.identity={'device':st.st_dev,'inode':st.st_ino};self.now=[10.]
  self.confirm=Mock(return_value=True)
  self.bridge=NativeRegistryBridge(self.manager,scope=self.scope,folder=str(self.project),identity=self.identity,expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=self.confirm,clock=lambda:self.now[0])
 def test_private_owner_channel_drives_actual_registry_dispatch(self):
  a,b=socket.socketpair();self.addCleanup(a.close)
  channel=NativeApprovalChannel(b,scope=self.scope,identity=self.identity,expires=20,clock=lambda:self.now[0]);self.addCleanup(channel.close)
  self.bridge.owner_confirm=channel;answer=[]
  t=threading.Thread(target=lambda:answer.append(self.bridge.submit(ID,'synthetic task',self.scope,DispatchToken(),20)),daemon=True);t.start()
  owner=approval_channel.Owner(a);target=owner.receive();self.assertEqual(target['task'],'synthetic task');self.assertEqual(target['identity'],self.identity)
  self.assertFalse(self.manager.rows);owner.respond(True);t.join(2)
  self.assertEqual(answer,['submitted']);self.assertEqual(self.bridge.status(ID),'running')
 def test_private_socket_dispatches_once_and_persists_registry_receipt(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  worker=threading.Thread(target=serve_one,args=(a,self.bridge,DispatchToken()),daemon=True);worker.start()
  approval_channel._send(b,{'kind':'submit','id':ID,'task':'synthetic task'})
  self.assertEqual(approval_channel._read(b),{'status':'submitted'});worker.join(2);self.assertFalse(worker.is_alive())
  row=next(r for r in self.manager.rows.values() if r.get('codexClientRequest'))
  self.assertTrue((Path(row['directory'])/'state.json').is_file());self.assertEqual(row['folder'],str(self.project));self.assertEqual(self.bridge.status(ID),'running')
  row['cancelReviewRequired']=True;self.assertEqual(self.bridge.status(ID),'review-required');row.pop('cancelReviewRequired')
  self.bridge.submit(ID,'synthetic task',self.scope,DispatchToken(),20)
  self.assertEqual(len(self.manager.rows),1);self.assertEqual(self.confirm.call_count,1)
  self.bridge.cancel(ID);self.assertTrue(FakeProvider.instances[0].interrupted.wait(1))
 def test_gate_to_existing_registry_is_idempotent_and_stop_is_correlated(self):
  gate=RemoteGate(clock=lambda:self.now[0])
  auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope=self.scope,bridge=self.bridge,expires=20)
  payload={'id':ID,'task':'synthetic task'}
  self.assertEqual(gate.request(**auth,body=payload)['status'],'submitted')
  self.assertEqual(gate.request(**auth,body=payload)['status'],'submitted')
  self.assertEqual(len(self.manager.rows),1);self.assertEqual(self.confirm.call_count,1)
  self.assertEqual(gate.stop(**auth,ident=ID)['status'],'cancelling')
  self.assertTrue(FakeProvider.instances[0].interrupted.wait(1))
 def test_decline_is_not_reported_as_submitted(self):
  gate=RemoteGate(clock=lambda:self.now[0]);self.confirm.return_value=False
  auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope=self.scope,bridge=self.bridge,expires=20)
  self.assertEqual(gate.request(**auth,body={'id':ID,'task':'fixture'})['status'],'cancelled');self.assertFalse(self.manager.rows)
 def test_durable_registry_receipt_prevents_restart_redispatch(self):
  self.bridge.submit(ID,'synthetic task',self.scope,DispatchToken(),20)
  self.assertEqual(len(FakeProvider.instances),1);self.manager.close()
  restored=atticus.Agents(emit=lambda _:None,launch=Mock());self.addCleanup(restored.close)
  confirm=Mock(return_value=True)
  bridge=NativeRegistryBridge(restored,scope=self.scope,folder=str(self.project),identity=self.identity,expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=confirm,clock=lambda:self.now[0])
  gate=RemoteGate(clock=lambda:self.now[0]);auth={'host':'fixture.example','origin':'https://fixture.example','token':'n'*32,'csrf':'m'*32}
  gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope=self.scope,bridge=bridge,expires=20)
  result=gate.request(**auth,body={'id':ID,'task':'synthetic task'})
  self.assertEqual(result['status'],'unknown');self.assertEqual(len(restored.rows),1);self.assertEqual(len(FakeProvider.instances),1);confirm.assert_not_called()
  with self.assertRaises(RemoteError):gate.request(**auth,body={'id':'22345678123441238123123456789abc','task':'another'})
 def test_restart_can_inspect_and_stop_only_the_matching_durable_receipt(self):
  self.bridge.submit(ID,'synthetic task',self.scope,DispatchToken(),20)
  restarted=NativeRegistryBridge(self.manager,scope=self.scope,folder=str(self.project),identity=self.identity,expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=self.confirm,clock=lambda:self.now[0])
  self.assertEqual(restarted.status(ID),'running')
  wrong=NativeRegistryBridge(self.manager,scope=self.scope,folder=str(self.project),identity={'device':self.identity['device'],'inode':self.identity['inode']+1},expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=self.confirm,clock=lambda:self.now[0])
  self.assertEqual(wrong.status(ID),'unknown');wrong.cancel(ID)
  self.assertFalse(FakeProvider.instances[0].interrupted.is_set())
  restarted.cancel(ID);self.assertTrue(FakeProvider.instances[0].interrupted.wait(1))
 def test_ambiguous_duplicate_receipts_fail_closed(self):
  self.bridge.submit(ID,'synthetic task',self.scope,DispatchToken(),20)
  with self.manager.lock:
   row=next(iter(self.manager.rows.values()));duplicate=dict(row,id='another')
   self.manager.rows['another']=duplicate
  self.assertEqual(self.bridge.status(ID),'unknown');self.bridge.cancel(ID)
  self.assertFalse(FakeProvider.instances[0].interrupted.is_set())
  with self.manager.lock:self.manager.rows.pop('another')
 def test_stop_after_commit_returns_immediately_and_delivers_one_cancel(self):
  entered=threading.Event();release=threading.Event();stopped=threading.Event()
  class BlockingRegistry:
   def __init__(self):self.lock=threading.RLock();self.rows={};self.stop_count=0
   def command(self,data):
    if data['action']=='codex-start':
     entered.set();release.wait(2)
     with self.lock:self.rows['row']={'id':'row','provider':'codex','codexClientRequest':data['requestId'],'folder':data['folder'],'brief':data['task'],'codexProjectIdentity':data['folderIdentity'],'status':'running'}
    elif data['action']=='stop':self.stop_count+=1;stopped.set()
  manager=BlockingRegistry();bridge=NativeRegistryBridge(manager,scope=self.scope,folder=str(self.project),identity=self.identity,expires=20,verify_scope=atticus.codex_project_matches,owner_confirm=lambda *_:True,clock=lambda:self.now[0])
  gate=RemoteGate(clock=lambda:self.now[0]);auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  gate.owner_enable(origin=auth['origin'],token=auth['token'],csrf=auth['csrf'],scope=self.scope,bridge=bridge,expires=20);result=[]
  thread=threading.Thread(target=lambda:result.append(gate.request(**auth,body={'id':ID,'task':'fixture'})),daemon=True);thread.start();self.assertTrue(entered.wait(1))
  started=time.monotonic();self.assertEqual(gate.stop(**auth,ident=ID)['status'],'cancelling');self.assertLess(time.monotonic()-started,.5)
  release.set();thread.join(2);self.assertTrue(stopped.wait(1));self.assertEqual(manager.stop_count,1);self.assertEqual(result[0]['status'],'cancelling')
 def test_native_decline_or_changed_scope_never_dispatch(self):
  self.confirm.return_value=False
  with self.assertRaises(NotDispatched):self.bridge.submit(ID,'fixture',self.scope,DispatchToken(),20)
  self.assertFalse(self.manager.rows)
  self.confirm.return_value=True;self.project.rename(self.project.parent/'old');self.project.mkdir()
  with self.assertRaises(NotDispatched):self.bridge.submit(ID,'fixture',self.scope,DispatchToken(),20)
  self.assertFalse(self.manager.rows)
 def test_stop_and_expiry_during_native_review_prevent_dispatch(self):
  for reason in ('cancel','expiry'):
   with self.subTest(reason=reason):
    self.now[0]=10;entered=threading.Event();release=threading.Event();cancelled=DispatchToken();errors=[]
    def confirm(task,folder):entered.set();release.wait(2);return True
    self.bridge.owner_confirm=confirm
    def submit():
     try:self.bridge.submit(ID,'fixture',self.scope,cancelled,20)
     except Exception as e:errors.append(e)
    t=threading.Thread(target=submit,daemon=True);t.start();self.assertTrue(entered.wait(1))
    if reason=='cancel':cancelled.set();self.bridge.cancel(ID)
    else:self.now[0]=21
    release.set();t.join(2);self.assertFalse(t.is_alive());self.assertIsInstance(errors[0],NotDispatched);self.assertFalse(self.manager.rows)
 def test_unrecognized_frame_cannot_approve_or_change_scope(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  t=threading.Thread(target=serve_one,args=(a,self.bridge,DispatchToken()),daemon=True);t.start()
  approval_channel._send(b,{'kind':'submit','id':ID,'task':'fixture','confirmed':True})
  self.assertEqual(approval_channel._read(b),{'status':'invalid'});t.join(2);self.confirm.assert_not_called();self.assertFalse(self.manager.rows)
if __name__=='__main__':unittest.main()
