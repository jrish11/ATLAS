"""Background app control policy fixtures; no OS app actions."""
import unittest
from unittest.mock import Mock,patch
import atticus,foreground_control

APP={'bundle_id':'com.example.fixture','path':'/Applications/Fixture.app','pid':42,'started':'100'}
class BackgroundControlTests(unittest.TestCase):
 def test_foreground_actions_pause_without_lookup_or_approval(self):
  lookup,approve,launch,focus,click=Mock(),Mock(),Mock(),Mock(),Mock()
  for action in ('open_app','focus_app'):
   result=foreground_control.handle({'action':action,'bundle_id':APP['bundle_id']},lookup,approve,launch,focus,click,lambda:False,background_only=True)
   self.assertEqual(result['status'],'needs_foreground')
  for call in (lookup,approve,launch,focus,click):call.assert_not_called()
 def test_background_named_press_rechecks_identity_and_cancellation(self):
  req={'action':'click','bundle_id':APP['bundle_id'],'target':'Continue'}
  check={'args':['click','Continue'],'labels':['Continue'],'pid':42,'windowID':'72','window':'Fixture','at':['frame'],'secure':False,'risky':False}
  for change in ('pid','cancel','none'):
   with self.subTest(change=change):
    calls=[];pressed=[];cancel=[False]
    def lookup(_):
     calls.append(1)
     if len(calls)==4 and change=='cancel':cancel[0]=True
     return {**APP,'started':'changed'} if len(calls)==4 and change=='pid' else APP
    def click(_,__,authorize):
     if authorize(check):pressed.append(True)
     return {'status':'unverified','text':'fixture'}
    foreground_control.handle(req,lookup,lambda _: 'y',Mock(),Mock(),click,lambda:cancel[0],background_only=True)
    self.assertEqual(bool(pressed),change=='none')
 def test_normal_handler_passes_default_and_explicit_setting(self):
  for value,expected in ((True,True),(False,False),(None,True)):
   with self.subTest(value=value),patch.object(atticus,'pref',return_value=value),patch.object(atticus.foreground_control,'handle',return_value={}) as h:
    atticus.foreground_control_request({});self.assertEqual(h.call_args.kwargs['background_only'],expected)
 def test_capability_map_and_media_actions_do_not_guess(self):
  for kind in ('volume','volume_delta','transport'):
   self.assertEqual(atticus.background_capability('media',kind),'background-safe')
  for kind in ('spotify_track','spotify_search','quit_music'):
   runner=Mock();self.assertEqual(atticus.background_capability('media',kind),'foreground-required')
   self.assertIn('foreground',atticus.direct_media_execute({'kind':kind},runner,background_only=True));runner.assert_not_called()
  for route in ('mouse','keyboard','clipboard','unknown'):
   self.assertEqual(atticus.background_capability(route),'unsupported')
  self.assertEqual(atticus.background_capability('saved_destination'),'foreground-required')
 def test_model_saved_destination_pauses_before_approval_or_dispatch(self):
  import tempfile,os
  row={'label':'Fixture','url':'https://example.com','confirmed':True,'browser':'Safari','aliases':['fixture']}
  with tempfile.TemporaryDirectory() as ask,patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':ask}),patch.object(atticus,'pref',return_value=True),patch.object(atticus.personal_commands,'resolve',return_value=row):
   approve=Mock();opener=Mock();result=atticus.foreground_saved_tool({'name':'Fixture'},approve=approve,open_action=opener)
   self.assertEqual(result['status'],'needs_foreground');approve.assert_not_called();opener.assert_not_called()
 def test_task_legacy_input_helpers_fail_closed(self):
  import os
  with patch.dict(os.environ,{'ATTICUS_ASK':'/fixture'}),patch.object(atticus,'pref',return_value=True):
   for action in ('--type','--play','--queue'):self.assertTrue(atticus.background_helper_blocked(action))
   self.assertFalse(atticus.background_helper_blocked('--read'))
  with patch.dict(os.environ,{'ATTICUS_ASK':'/fixture'}),patch.object(atticus,'pref',return_value=False):
   self.assertFalse(atticus.background_helper_blocked('--type'))
 def test_background_agent_cannot_open_saved_destination(self):
  import os
  row={'label':'Fixture','url':'https://example.com','confirmed':True,'browser':'Safari','aliases':['fixture']}
  with patch.dict(os.environ,{'ATTICUS_AGENT':'1'},clear=False),patch.object(atticus,'pref',return_value=True),patch.object(atticus.personal_commands,'resolve',return_value=row),patch.object(atticus.personal_commands,'open_destination') as opener:
   self.assertIn('foreground',atticus.fast('open fixture'));opener.assert_not_called()
 def test_model_hands_environment_blocks_pointer_and_clipboard_fallback(self):
  import os
  with patch.dict(os.environ,{'ATTICUS_ASK':'/fixture'}),patch.object(atticus,'pref',return_value=True),patch.object(atticus,'hands_pin',return_value=('72',True)):
   env,_=atticus.hands_env(['click','Continue'])
   self.assertEqual(env['ATTICUS_HANDS_WINDOW'],'72');self.assertEqual(env['ATTICUS_AX_ONLY'],'1');self.assertEqual(env['ATTICUS_BACKGROUND_ONLY'],'1');self.assertEqual(env['ATTICUS_FOCUS_REQUESTED'],'0')
 def test_setting_changes_during_app_approval_or_lookup_block_dispatch(self):
  for action in ('open_app','focus_app'):
   for flip in ('approval','lookup'):
    with self.subTest(action=action,flip=flip):
     state=[False];calls=[];launch=Mock();focus=Mock()
     def lookup(_):
      calls.append(1)
      if flip=='lookup' and len(calls)==2:state[0]=True
      return APP
     def approval(_):
      if flip=='approval':state[0]=True
      return 'y'
     result=foreground_control.handle({'action':action,'bundle_id':APP['bundle_id']},lookup,approval,launch,focus,Mock(),lambda:False,background_only=False,background_check=lambda:state[0])
     self.assertEqual(result['status'],'needs_foreground');launch.assert_not_called();focus.assert_not_called()
 def test_setting_change_during_click_approval_prevents_old_mode_press(self):
  state=[False];pressed=[];check={'args':['click','Continue'],'labels':['Continue'],'pid':42,'windowID':'72','window':'Fixture','at':['frame'],'secure':False,'risky':False}
  def approve(_):
   if len(pressed)==0:pressed.append('inspection');return 'y'
   state[0]=True;return 'y'
  def click(_,__,authorize):
   if authorize(check):pressed.append('press')
   return {'status':'unverified'}
  foreground_control.handle({'action':'click','bundle_id':APP['bundle_id'],'target':'Continue'},lambda _:APP,approve,Mock(),Mock(),click,lambda:False,background_only=False,background_check=lambda:state[0])
  self.assertEqual(pressed,['inspection'])
 def test_automatic_app_and_saved_destination_recheck_after_slow_lookup(self):
  import json,os,tempfile
  from types import SimpleNamespace
  row={'label':'Fixture','url':'https://example.com','confirmed':True,'browser':'Safari','aliases':['fixture']}
  for route in ('app','saved'):
   with self.subTest(route=route),tempfile.TemporaryDirectory() as ask:
    state=[False];calls=[];opened=Mock();store=Mock();store.stop_path=os.path.join(ask,'missing-stop')
    def dispatch(_action,_target,_clock,perform):perform();return True
    store.dispatch.side_effect=dispatch
    def resolve(*_):
     calls.append(1)
     if len(calls)==2:state[0]=True
     return row
    def run(*args,**kwargs):
     calls.append(1)
     if len(calls)==2:state[0]=True
     return SimpleNamespace(returncode=0,stdout=json.dumps(APP))
    with patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':ask}),patch.object(atticus,'pref',side_effect=lambda *_:state[0]),patch.object(atticus,'autonomy_store',return_value=store):
     if route=='app':
      with patch.object(atticus.subprocess,'run',side_effect=run):result=atticus.foreground_control_request({'action':'open_app','bundle_id':APP['bundle_id']})
      self.assertEqual(len(calls),2);self.assertEqual(result['status'],'cancelled')
     else:
      with patch.object(atticus.personal_commands,'resolve',side_effect=resolve):result=atticus.foreground_saved_tool({'name':'Fixture'},approve=Mock(),open_action=opened)
      self.assertEqual(len(calls),2);opened.assert_not_called();self.assertIn('setting changed',result['text'])
 def test_media_rechecks_setting_before_side_effect(self):
  from types import SimpleNamespace
  for intent in ({'kind':'spotify_search','query':'fixture'}, {'kind':'spotify_track','id':'a'*22}, {'kind':'quit_music'}):
   with self.subTest(intent=intent):
    values=iter((False,True));runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='requested'))
    self.assertIn('foreground',atticus.direct_media_execute(intent,runner,background_check=lambda:next(values)));runner.assert_not_called()
 def test_setting_change_in_either_direction_invalidates_old_click_scope(self):
  check={'args':['click','Continue'],'labels':['Continue'],'pid':42,'windowID':'72','window':'Fixture','at':['frame'],'secure':False,'risky':False}
  for initial in (True,False):
   with self.subTest(initial=initial):
    state=[initial];pressed=[];count=[]
    def approval(_):
     count.append(1)
     if len(count)==2:state[0]=not initial
     return 'y'
    def click(_,__,authorize):
     if authorize(check):pressed.append(True)
     return {'status':'unverified'}
    foreground_control.handle({'action':'click','bundle_id':APP['bundle_id'],'target':'Continue'},lambda _:APP,approval,Mock(),Mock(),click,lambda:False,background_only=initial,background_check=lambda:state[0])
    self.assertEqual(pressed,[])
 def test_setting_change_after_saved_approval_or_during_tab_search_blocks_open(self):
  import os,socket,tempfile
  from types import SimpleNamespace
  import approval_channel,personal_commands
  row={'label':'Fixture','url':'https://example.com','confirmed':True,'browser':'Safari','aliases':['fixture']}
  for flip in ('approval','search'):
   with self.subTest(flip=flip),tempfile.TemporaryDirectory() as ask:
    a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);state=[False];calls=[];original=personal_commands.open_destination
    def runner(args,**kwargs):
     calls.append(args)
     if flip=='search':state[0]=True
     return SimpleNamespace(returncode=0,stdout='absent')
    def actual(item,authorize):return original(item,runner=runner,authorize=authorize)
    def approve(_):
     if flip=='approval':state[0]=True
     return approval_channel.Approval('y')
    with patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':ask}),patch.object(atticus,'pref',side_effect=lambda *_:state[0]),patch.object(atticus,'autonomy_store',return_value=None),patch.object(personal_commands,'resolve',return_value=row),patch.object(personal_commands,'open_destination',side_effect=actual),patch.object(approval_channel,'TOOL_FD',a.fileno()):
     result=atticus.foreground_saved_tool({'name':'Fixture'},approve=approve)
    self.assertEqual(len(calls),0 if flip=='approval' else 1);self.assertNotIn('Requested',result['text'])
 def test_native_and_ui_guard_are_wired(self):
  from pathlib import Path
  root=Path(__file__).resolve().parents[1];native=(root/'Atticus.swift').read_text();ui=(root/'ui/settings.html').read_text()
  self.assertIn('backgroundWindowAllowed(expected:before.windowID',native)
  self.assertIn('targetsCurrent(input,before,a)',native);self.assertIn('try checkStopped()',native)
  self.assertIn('data-k="foregroundKeepFocus"',ui);self.assertIn('Explicit opens and other routes can still bring apps forward',ui)
