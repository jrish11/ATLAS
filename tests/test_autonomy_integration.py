import os, tempfile, unittest
from unittest.mock import Mock, patch
import atticus, autonomy_policy as a, foreground_control as c

class IntegrationTests(unittest.TestCase):
 def test_app_action_is_bound_to_target_and_revocation(self):
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':5,'started':'100'};target={'type':'app','id':app['bundle_id'],'revision':a.fingerprint({'bundle_id':app['bundle_id'],'path':app['path']})}
  with tempfile.TemporaryDirectory() as d:
   store=a.SessionStore(d,'a'*64);store.activate([target],10,110,True);called=[];approval=Mock(return_value='n')
   def auto(action,item):
    result=[]
    if store.dispatch(action,target,lambda:11,lambda:result.append({'status':'verified','text':'fixture'})): called.append(action);return result[0]
   def invoke():return c.handle({'action':'focus_app','bundle_id':app['bundle_id']},lambda _:app,approval,Mock(),Mock(),Mock(),lambda:False,auto)
   self.assertEqual(invoke()['status'],'verified');approval.assert_not_called();store.stop()
   self.assertEqual(invoke()['status'],'cancelled');self.assertEqual(called,['focus_app']);approval.assert_called_once()
 def test_destination_revision_and_stop_recheck(self):
  row={'label':'Fixture','aliases':['fixture'],'url':'https://example.com/','browser':'Safari','confirmed':True}; target={'type':'destination','id':'Fixture','revision':a.fingerprint(row)}
  with tempfile.TemporaryDirectory() as d:
   store=a.SessionStore(d,'a'*64);store.activate([target],10,110,True);opened=[]
   with patch.object(atticus,'autonomy_store',return_value=store),patch.object(atticus.personal_commands,'resolve',return_value=row),patch.object(atticus.time,'monotonic',return_value=11),patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d}):
    approve=Mock(return_value='n'); action=lambda r:opened.append(r) or 'opened'
    self.assertEqual(atticus.foreground_saved_tool({'name':'Fixture'},approve,action)['text'],'opened');approve.assert_not_called();store.stop()
    self.assertIn('not opened',atticus.foreground_saved_tool({'name':'Fixture'},approve,action)['text']);self.assertEqual(len(opened),1)

 def test_owner_controls_only_direct_native_child(self):
  with patch.dict(os.environ,{'ATTICUS_OWNER_PID':'123'},clear=False),patch.object(atticus.os,'getppid',return_value=456),patch.object(atticus,'autonomy_store') as store:
   self.assertIn('unavailable',atticus.autonomy_setup({'action':'stop'})['error']);store.assert_not_called()
 def test_pi_run_identifier_forwarded_without_owner_authority(self):
  import io,json
  from types import SimpleNamespace
  import foreground_openai
  events=[json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'Fixture'}],'usage':{}}})+'\n']
  proc=SimpleNamespace(stdin=Mock(),stdout=io.StringIO(''.join(events)),returncode=0,wait=lambda:0,poll=lambda:0,pid=1);popen=Mock(return_value=proc)
  prefs=lambda k,d:{'client':'pi','foregroundProvider':'openai','foregroundAppControl':True,'foregroundSavedDestinations':False,'foregroundModel':'gpt-6.1-terra'}.get(k,d)
  with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'relay'),patch.object(atticus.signal,'signal'),patch.object(atticus.atexit,'register'),patch.object(atticus.subprocess,'Popen',popen),patch.object(atticus.keychain_store.ProviderKeyStore,'get',return_value='fixture-key'),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper','ATTICUS_RUN_ID':'a'*64,'ATTICUS_OWNER_PID':'123'}):atticus.run_pi('fixture')
  env=popen.call_args.kwargs['env'];self.assertNotIn('ATTICUS_RUN_ID',env);self.assertNotIn('ATTICUS_OWNER_PID',env)

 def test_autonomy_disabled_even_with_forged_environment(self):
  with patch.dict(os.environ,{'ATTICUS_OWNER_PID':str(os.getppid()),'ATTICUS_RUN_ID':'a'*64},clear=False):
   self.assertIsNone(atticus.autonomy_store())
   self.assertIn('unavailable',atticus.autonomy_setup({'action':'activate','confirmed':True})['error'])

 def test_review_probe_forged_model_context_cannot_activate(self):
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'ATTICUS_OWNER_PID':str(os.getppid()),'ATTICUS_RUN_ID':'a'*64,'ATTICUS_ASK':d},clear=False), patch.object(atticus.autonomy_policy.SessionStore,'activate') as activate:
   result=atticus.autonomy_setup({'action':'activate','confirmed':True,'targets':[]})
   self.assertIn('unavailable',result['error']);activate.assert_not_called()
 def test_review_probe_expired_during_lookup_never_auto_dispatches(self):
  import json
  from types import SimpleNamespace
  app={'bundle_id':'com.example.Fixture','path':'/Applications/Fixture.app','pid':7,'started':'123'}
  clock=[11]
  def slow_lookup(*args,**kwargs): clock[0]=13; return SimpleNamespace(returncode=0,stdout=json.dumps(app))
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'ATTICUS_RUN_ID':'a'*64,'ATTICUS_ASK':d},clear=False), patch.object(atticus,'autonomy_store',wraps=atticus.autonomy_store) as store, patch.object(atticus.approval_channel,'tool_approval',return_value='n') as approve, patch.object(atticus.subprocess,'run',side_effect=slow_lookup) as execute:
   result=atticus.foreground_control_request({'action':'focus_app','bundle_id':app['bundle_id']})
   self.assertEqual(result['status'],'cancelled');self.assertEqual(execute.call_count,1);self.assertEqual(clock[0],13);store.assert_called_once();approve.assert_called_once()
