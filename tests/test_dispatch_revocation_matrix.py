import os,socket,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import approval_channel as ac,atticus,foreground_control as fc,personal_commands as pc

class DispatchMatrixTests(unittest.TestCase):
 def sockets(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);return a,b
 def decision(self,scoped):return ac.Approval('y',ac.shared_clock()+10,'revision') if scoped else ac.Approval('y')
 def test_app_open_focus_manual_and_scoped_stop_cancel_change_expiry(self):
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':7,'started':'123'}
  for action in ('open_app','focus_app'):
   for scoped in (False,True):
    for fault in ('disconnect','cancel','changed','expired','slow'):
     if fault in ('expired','slow') and not scoped:continue
     with self.subTest(action=action,scoped=scoped,fault=fault):
      a,b=self.sockets();calls=[];cancel=[False];performed=[];decision=self.decision(scoped)
      if fault=='expired':decision=ac.Approval('y',ac.shared_clock()-1,'revision')
      if fault=='slow':decision=ac.Approval('y',ac.shared_clock()+.01,'revision')
      def lookup(_):
       calls.append(1)
       if len(calls)==2:
        if fault=='slow':time.sleep(.03)
        if fault=='disconnect':b.shutdown(socket.SHUT_RDWR)
        if fault=='cancel':cancel[0]=True
        if fault=='changed':return {**app,'started':'changed'}
       return app
      with patch.object(ac,'TOOL_FD',a.fileno()):
       result=fc.handle({'action':action,'bundle_id':app['bundle_id']},lookup,lambda _:decision,lambda _:performed.append('open'),lambda _:performed.append('focus'),Mock(),lambda:cancel[0],verify_revision=lambda _:'revision')
      self.assertEqual(result['status'],'cancelled');self.assertEqual(performed,[])
 def test_inspect_and_press_manual_and_scoped_stop_cancel_change_expiry(self):
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':7,'started':'123'};req={'action':'click','bundle_id':app['bundle_id'],'target':'Submit'}
  check={'args':['click','Submit'],'labels':['Submit'],'pid':7,'windowID':'73','window':'Fixture','at':['frame'],'secure':False,'risky':True}
  for stage in ('inspection','press'):
   for scoped in (False,True):
    for fault in ('disconnect','cancel','changed','expired'):
     if fault=='expired' and not scoped:continue
     with self.subTest(stage=stage,scoped=scoped,fault=fault):
      a,b=self.sockets();calls=[];cancel=[False];inspected=[];pressed=[];decision=self.decision(scoped)
      if fault=='expired':decision=ac.Approval('y',ac.shared_clock()-1,'revision')
      if scoped:
       # Scoped grants never authorize inspection or press, independently of fault.
       lookup=lambda _:app
      else:
       def lookup(_):
        calls.append(1);trigger=2 if stage=='inspection' else 4
        if len(calls)==trigger:
         if fault=='disconnect':b.shutdown(socket.SHUT_RDWR)
         if fault=='cancel':cancel[0]=True
         if fault=='changed':return {**app,'started':'changed'}
        return app
      def click(_,__,authorize):
       inspected.append(True)
       if authorize(check):pressed.append(True)
       return {'status':'unverified','text':'fixture'}
      with patch.object(ac,'TOOL_FD',a.fileno()):fc.handle(req,lookup,lambda _:decision,Mock(),Mock(),click,lambda:cancel[0])
      self.assertEqual(pressed,[])
      if scoped or stage=='inspection':self.assertEqual(inspected,[])
 def test_saved_url_new_open_disconnect_cancel_change_expiry(self):
  row={'label':'Fixture','aliases':['fixture'],'url':'https://example.com/','browser':'Safari','confirmed':True}
  for scoped in (False,True):
   for fault in ('disconnect','cancel','changed','expired','slow'):
    if fault in ('expired','slow') and not scoped:continue
    with self.subTest(scoped=scoped,fault=fault),tempfile.TemporaryDirectory() as d:
     a,b=self.sockets();calls=[];resolves=[];changed=[False];original=pc.open_destination
     path=os.path.join(d,'destinations.json');Path(path).write_text('[]');revision=atticus.destination_store_revision(d)
     decision=ac.Approval('y',ac.shared_clock()+10,revision) if scoped else ac.Approval('y')
     if fault=='expired':decision=ac.Approval('y',ac.shared_clock()-1,revision)
     if fault=='slow':decision=ac.Approval('y',ac.shared_clock()+.01,revision)
     def resolve(*_):resolves.append(1);return {**row,'url':'https://changed.example/'} if changed[0] else row
     def runner(args,**kw):
      calls.append(args)
      if fault=='slow':time.sleep(.03)
      if fault=='disconnect':b.shutdown(socket.SHUT_RDWR)
      if fault=='cancel':open(os.path.join(d,'declined'),'w').close()
      if fault=='changed':changed[0]=True
      return SimpleNamespace(returncode=0,stdout='absent')
     def real_policy(item,authorize):return original(item,runner=runner,authorize=authorize)
     with patch.object(atticus,'DIR',d),patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d},clear=False),patch.object(ac,'TOOL_FD',a.fileno()),patch.object(atticus,'autonomy_store',return_value=None),patch.object(pc,'resolve',side_effect=resolve),patch.object(pc,'open_destination',side_effect=real_policy):
      result=atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _:decision)
     self.assertLessEqual(len(calls),1);self.assertNotIn('Requested',result['text'])
 def test_existing_tab_switch_already_dispatched_cannot_be_undone(self):
  row={'label':'Fixture','url':'https://example.com/','browser':'Safari'};live=[True];calls=[]
  def runner(args,**kw):calls.append(args);live[0]=False;return SimpleNamespace(returncode=0,stdout='switched')
  result=pc.open_destination(row,runner=runner,authorize=lambda:live[0])
  self.assertEqual(len(calls),1);self.assertIn('Requested switching',result)
 def test_saved_tab_switch_never_starts_after_disconnect(self):
  row={'label':'Fixture','aliases':['fixture'],'url':'https://example.com/','browser':'Safari','confirmed':True}
  for scoped in (False,True):
   with self.subTest(scoped=scoped),tempfile.TemporaryDirectory() as d:
    a,b=self.sockets();Path(d,'destinations.json').write_text('[]');revision=atticus.destination_store_revision(d);calls=[];original=pc.open_destination
    decision=ac.Approval('y',ac.shared_clock()+10,revision) if scoped else ac.Approval('y')
    def approve(_):b.shutdown(socket.SHUT_RDWR);return decision
    def runner(args,**kw):calls.append(args);return SimpleNamespace(returncode=0,stdout='switched')
    def real_policy(item,authorize):return original(item,runner=runner,authorize=authorize)
    with patch.object(atticus,'DIR',d),patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d},clear=False),patch.object(ac,'TOOL_FD',a.fileno()),patch.object(atticus,'autonomy_store',return_value=None),patch.object(pc,'resolve',return_value=row),patch.object(pc,'open_destination',side_effect=real_policy):
     result=atticus.foreground_saved_tool({'name':'Fixture'},approve=approve)
    self.assertEqual(calls,[]);self.assertNotIn('Requested',result['text'])
