import time,unittest
from types import SimpleNamespace
from unittest.mock import Mock
import approval_channel,foreground_control,personal_commands
class DeadlineDispatchTests(unittest.TestCase):
 def test_slow_app_lookup_cannot_extend_approval(self):
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':3,'started':'1'};calls=[]
  def lookup(_):
   calls.append(1)
   if len(calls)>1:time.sleep(.05)
   return app
  launch=Mock();decision=approval_channel.Approval('y',approval_channel.shared_clock()+.01,'fixture-revision')
  r=foreground_control.handle({'action':'open_app','bundle_id':app['bundle_id']},lookup,lambda _:decision,launch,Mock(),Mock(),lambda:False,verify_revision=lambda _: 'fixture-revision')
  self.assertEqual(r['status'],'cancelled');launch.assert_not_called()
 def test_saved_url_expiry_after_tab_search_prevents_new_open(self):
  row={'label':'Fixture','url':'https://example.com/','browser':'Safari'};ready=[True];calls=[]
  def runner(args,**kw):calls.append(args);ready[0]=False;return SimpleNamespace(returncode=0,stdout='absent')
  result=personal_commands.open_destination(row,runner=runner,authorize=lambda:ready[0]);self.assertIn('expired',result);self.assertEqual(len(calls),1)

 def test_replaced_app_executable_invalidates_revision(self):
  import tempfile,plistlib,os
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   bundle=Path(d,'Fixture.app');mac=bundle/'Contents'/'MacOS';mac.mkdir(parents=True);exe=mac/'Fixture';exe.write_bytes(b'original')
   with open(bundle/'Contents'/'Info.plist','wb') as f:plistlib.dump({'CFBundleIdentifier':'com.example.Fixture','CFBundleExecutable':'Fixture'},f)
   app={'bundle_id':'com.example.Fixture','path':os.path.realpath(bundle),'pid':3,'started':'1'};original=foreground_control.app_revision(app);self.assertTrue(original)
   calls=[]
   def lookup(_):
    calls.append(1)
    if len(calls)==2:exe.write_bytes(b'replacement')
    return app
   launch=Mock();decision=approval_channel.Approval('y',approval_channel.shared_clock()+10,original)
   r=foreground_control.handle({'action':'open_app','bundle_id':app['bundle_id']},lookup,lambda _:decision,launch,Mock(),Mock(),lambda:False)
   self.assertEqual(r['status'],'cancelled');launch.assert_not_called()

 def test_stop_closes_channel_during_lookup_and_cancels_dispatch(self):
  import socket
  from unittest.mock import patch
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':3,'started':'1'};calls=[]
  def lookup(_):
   calls.append(1)
   if len(calls)==2:b.shutdown(socket.SHUT_RDWR)
   return app
  launch=Mock();decision=approval_channel.Approval('y',approval_channel.shared_clock()+10,'fixture-revision')
  with patch.object(approval_channel,'TOOL_FD',a.fileno()):
   r=foreground_control.handle({'action':'open_app','bundle_id':app['bundle_id']},lookup,lambda _:decision,launch,Mock(),Mock(),lambda:False,verify_revision=lambda _: 'fixture-revision')
  self.assertEqual(r['status'],'cancelled');launch.assert_not_called()

 def test_manual_saved_url_disconnect_during_safari_search_blocks_open(self):
  import os,socket,tempfile
  from unittest.mock import patch
  import atticus
  row={'label':'Fixture','aliases':['fixture'],'url':'https://example.com/','browser':'Safari','confirmed':True}
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);calls=[];original=personal_commands.open_destination
  def runner(args,**kwargs):
   calls.append(args)
   if len(calls)==1:b.shutdown(socket.SHUT_RDWR)
   return SimpleNamespace(returncode=0,stdout='absent')
  def actual_policy(item,authorize):return original(item,runner=runner,authorize=authorize)
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d},clear=False), patch.object(approval_channel,'TOOL_FD',a.fileno()), patch.object(atticus,'autonomy_store',return_value=None), patch.object(atticus,'pref',return_value=False), patch.object(personal_commands,'resolve',return_value=row), patch.object(personal_commands,'open_destination',side_effect=actual_policy):
   result=atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _:approval_channel.Approval('y'))
  self.assertEqual(len(calls),1);self.assertIn('cancelled',result['text'])
 def test_manual_saved_url_live_channel_allows_fake_open(self):
  import os,socket,tempfile
  from unittest.mock import patch
  import atticus
  row={'label':'Fixture','aliases':['fixture'],'url':'https://example.com/','browser':'Safari','confirmed':True}
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);calls=[];original=personal_commands.open_destination
  def runner(args,**kwargs):calls.append(args);return SimpleNamespace(returncode=0,stdout='absent')
  def actual_policy(item,authorize):return original(item,runner=runner,authorize=authorize)
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d},clear=False), patch.object(approval_channel,'TOOL_FD',a.fileno()), patch.object(atticus,'autonomy_store',return_value=None), patch.object(atticus,'pref',return_value=False), patch.object(personal_commands,'resolve',return_value=row), patch.object(personal_commands,'open_destination',side_effect=actual_policy):
   result=atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _:approval_channel.Approval('y'))
  self.assertEqual(len(calls),2);self.assertIn('Requested',result['text'])
