import io, json, os, unittest
from types import SimpleNamespace
from unittest.mock import patch
import atticus, foreground_openai
from pathlib import Path
from unittest.mock import Mock
import foreground_control as c

class ControlPolicyTests(unittest.TestCase):
 def setUp(self):
  self.app={'bundle_id':'com.example.fixture','path':'/Applications/Fixture.app','pid':41,'started':'123.0'}
  self.lookup=Mock(return_value=self.app);self.approve=Mock(return_value='y');self.launch=Mock(return_value={'status':'unverified','text':'requested'});self.focus=Mock(return_value={'status':'verified','text':'focused'});self.click=Mock();self.cancelled=Mock(return_value=False)
 def run_control(self,req):return c.handle(req,self.lookup,self.approve,self.launch,self.focus,self.click,self.cancelled)
 def test_invalid_or_unknown_never_resolves_or_acts(self):
  for value in (None,{}, {'action':'shell','bundle_id':'com.example.fixture'}, {'action':'open_app','bundle_id':'../bad'}, {'action':'click','bundle_id':'com.example.fixture','target':'42'}, {'action':'open_app','bundle_id':'com.example.fixture','command':'evil'}):self.assertEqual(self.run_control(value)['status'],'blocked')
  self.lookup.assert_not_called();self.approve.assert_not_called();self.launch.assert_not_called();self.click.assert_not_called()
 def test_open_and_focus_require_approval_and_unchanged_identity(self):
  req={'action':'open_app','bundle_id':'com.example.fixture'};self.approve.return_value='n';self.assertEqual(self.run_control(req)['status'],'cancelled');self.launch.assert_not_called()
  self.approve.return_value='y';self.lookup.side_effect=[self.app,{**self.app,'path':'/Applications/Changed.app'}];self.assertEqual(self.run_control(req)['status'],'cancelled');self.launch.assert_not_called()
  self.lookup.side_effect=None;self.lookup.return_value=self.app;self.assertEqual(self.run_control(req)['status'],'unverified');self.launch.assert_called_once_with(self.app)
  self.assertEqual(self.run_control({'action':'focus_app','bundle_id':'com.example.fixture'})['status'],'verified');self.focus.assert_called_once_with(self.app)
 def test_click_requires_inspection_and_bound_target_approval(self):
  req={'action':'click','bundle_id':'com.example.fixture','target':'Continue'}
  self.approve.return_value='n';self.assertEqual(self.run_control(req)['status'],'cancelled');self.click.assert_not_called()
  self.approve.return_value='y';base={'args':['click','Continue'],'labels':['Continue'],'pid':41,'windowID':'73','window':'Fixture window','at':['frame'],'secure':False,'risky':True}
  def action(bundle,target,authorize):
   self.assertFalse(authorize({**base,'windowID':''}));self.assertFalse(authorize({**base,'pid':42}));self.assertFalse(authorize({**base,'secure':True}));self.assertFalse(authorize({**base,'labels':['Delete']}));self.assertTrue(authorize(base));return {'status':'unverified','text':'press dispatched'}
  self.click.side_effect=action;self.assertEqual(self.run_control(req)['status'],'unverified');self.assertIn('window 73',self.approve.call_args.args[0]['cmd']);self.assertIn('potentially consequential',self.approve.call_args.args[0]['q'])
 def test_cancellation_after_approval_prevents_action(self):
  self.cancelled.side_effect=[False,True];self.assertEqual(self.run_control({'action':'open_app','bundle_id':'com.example.fixture'})['status'],'cancelled');self.launch.assert_not_called()
 def test_opt_in_activates_only_narrow_tool_and_keeps_builtin_tools_disabled(self):
  events=[json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'Fixture'}],'usage':{}}})+'\n']
  proc=SimpleNamespace(stdin=Mock(),stdout=io.StringIO(''.join(events)),returncode=0,wait=lambda:0,poll=lambda:0,pid=1);popen=Mock(return_value=proc)
  prefs=lambda k,d:{'client':'pi','foregroundProvider':'openai','foregroundAppControl':True,'foregroundSavedDestinations':False,'foregroundModel':'gpt-6.1-terra'}.get(k,d)
  with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'relay'),patch.object(atticus.signal,'signal'),patch.object(atticus.atexit,'register'),patch.object(atticus.subprocess,'Popen',popen),patch.object(atticus.keychain_store.ProviderKeyStore,'get',return_value='fixture-key'),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}):atticus.run_pi('fixture')
  args=popen.call_args.args[0];self.assertIn('--no-builtin-tools',args);self.assertNotIn('--no-tools',args);self.assertEqual(args.count('--extension'),1);self.assertNotIn('fixture-key',str(args))

 def test_sources_disable_mouse_fallback_and_strip_credentials(self):
  root=Path(__file__).resolve().parents[1];native=(root/'Atticus.swift').read_text();src=(root/'atticus.py').read_text();section=src.split('FOREGROUND_CONTROL_TOOL =',1)[1].split('def foreground_control_request',1)[0]
  self.assertIn('This control has no supported Accessibility press',native);self.assertNotIn('OPENAI_API_KEY',section);self.assertNotIn('...process.env',section);self.assertIn("pref('foregroundAppControl', False) is True",src)

class ClickChannelRegressionTests(unittest.TestCase):
 def setUp(self):
  import socket
  self.a,self.b=socket.socketpair();self.addCleanup(self.a.close);self.addCleanup(self.b.close)
  self.app={'bundle_id':'com.example.fixture','path':'/Applications/Fixture.app','pid':41,'started':'123.0'}
  self.req={'action':'click','bundle_id':'com.example.fixture','target':'Submit'}
  self.check={'args':['click','Submit'],'labels':['Submit'],'pid':41,'windowID':'73','window':'Fixture','at':['frame'],'secure':False,'risky':True}
 def test_channel_closed_during_final_lookup_cannot_press(self):
  import approval_channel as ac, socket
  calls=[];pressed=[]
  def lookup(_):
   calls.append(1)
   if len(calls)==4:self.b.shutdown(socket.SHUT_RDWR)
   return self.app
  def click(_,__,authorize):
   if authorize(self.check):pressed.append(True)
   return {'status':'unverified','text':'fixture'}
  with patch.object(ac,'TOOL_FD',self.a.fileno()):
   c.handle(self.req,lookup,lambda _:ac.Approval('y'),Mock(),Mock(),click,lambda:False)
  self.assertEqual(len(calls),4);self.assertEqual(pressed,[])
 def test_scoped_decision_never_authorizes_inspection_or_press(self):
  import approval_channel as ac, time
  click=Mock();automatic=ac.Approval('y',ac.shared_clock()+10,'revision')
  expired=ac.Approval('y',ac.shared_clock()-1,'revision')
  r=c.handle(self.req,lambda _:self.app,lambda _:expired,Mock(),Mock(),click,lambda:False)
  self.assertEqual(r['status'],'cancelled');click.assert_not_called()
  r=c.handle(self.req,lambda _:self.app,lambda _:automatic,Mock(),Mock(),click,lambda:False)
  self.assertEqual(r['status'],'cancelled');click.assert_not_called()
  decisions=iter(['y',automatic]);pressed=[]
  def press(_,__,authorize):
   if authorize(self.check):pressed.append(True)
   return {'status':'unverified','text':'fixture'}
  c.handle(self.req,lambda _:self.app,lambda _:next(decisions),Mock(),Mock(),press,lambda:False)
  self.assertEqual(pressed,[])
 def test_channel_closed_during_inspection_lookup_prevents_inspection(self):
  import approval_channel as ac, socket
  calls=[];click=Mock()
  def lookup(_):
   calls.append(1)
   if len(calls)==2:self.b.shutdown(socket.SHUT_RDWR)
   return self.app
  with patch.object(ac,'TOOL_FD',self.a.fileno()):
   result=c.handle(self.req,lookup,lambda _:ac.Approval('y'),Mock(),Mock(),click,lambda:False)
  self.assertEqual(result['status'],'cancelled');click.assert_not_called()
 def test_target_changed_during_final_lookup_cannot_press(self):
  calls=[];pressed=[]
  def lookup(_):
   calls.append(1);return {**self.app,'started':'changed'} if len(calls)==4 else self.app
  def click(_,__,authorize):
   if authorize(self.check):pressed.append(True)
   return {'status':'unverified','text':'fixture'}
  c.handle(self.req,lookup,lambda _:'y',Mock(),Mock(),click,lambda:False)
  self.assertEqual(len(calls),4);self.assertEqual(pressed,[])
 def test_cancellation_during_final_lookup_cannot_press(self):
  calls=[];cancelled=[False];pressed=[]
  def lookup(_):
   calls.append(1)
   if len(calls)==4:cancelled[0]=True
   return self.app
  def click(_,__,authorize):
   if authorize(self.check):pressed.append(True)
   return {'status':'unverified','text':'fixture'}
  c.handle(self.req,lookup,lambda _:'y',Mock(),Mock(),click,lambda:cancelled[0])
  self.assertEqual(len(calls),4);self.assertEqual(pressed,[])
