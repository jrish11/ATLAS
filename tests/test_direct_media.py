"""Synthetic exact-request routing only; no real audio, application or provider."""
import io,json,os,subprocess,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import atticus

class DirectMediaTests(unittest.TestCase):
 def test_exact_intents_and_ambiguous_or_compound_refused(self):
  cases={'set volume to 30 percent':{'kind':'volume','value':30},'turn volume down':{'kind':'volume_delta','value':-10},'hey atlas turn volume down':{'kind':'volume_delta','value':-10},'hey atticus turn volume down':{'kind':'volume_delta','value':-10},'turn down the volume':{'kind':'volume_delta','value':-10},'increase volume by 20':{'kind':'volume_delta','value':20},'pause spotify':{'kind':'transport','action':'pause','app':'spotify'},'quit apple music':{'kind':'quit_music'},'play blue moon on spotify':{'kind':'spotify_search','query':'blue moon'}}
  for text,expected in cases.items():self.assertEqual(atticus.direct_media_intent(text),expected)
  for text in ('play spotify and quit music','turn it down','quit music then delete files','play something','play x\x00on spotify'):
   self.assertIsNone(atticus.direct_media_intent(text))
  self.assertEqual(atticus.direct_media_intent('set volume to 101')['kind'],'invalid_volume')
 def test_fixed_volume_and_no_retry_on_denied_automation(self):
  runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='30\n'))
  self.assertEqual(atticus.direct_media_execute({'kind':'volume','value':30},runner),'System volume is 30%.')
  args=runner.call_args.args[0];self.assertEqual(args[:2],['/usr/bin/osascript','-e']);self.assertIn('set volume output volume 30',args[2])
  runner=Mock(return_value=SimpleNamespace(returncode=1,stdout=''))
  self.assertIn('macOS permissions',atticus.direct_media_execute({'kind':'transport','app':'spotify','action':'pause'},runner));self.assertEqual(runner.call_count,1)
  runner=Mock(side_effect=subprocess.TimeoutExpired('fixture',10))
  self.assertIn('could not',atticus.direct_media_execute({'kind':'quit_music'},runner));self.assertEqual(runner.call_count,1)
 def test_exact_track_uses_one_fixed_command_and_verifies_identity(self):
  track='a'*22;intent=atticus.direct_media_intent('play spotify:track:'+track);self.assertEqual(intent,{'kind':'spotify_track','id':track})
  runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='playing|spotify:track:'+track))
  self.assertEqual(atticus.direct_media_execute(intent,runner),'Playing the requested Spotify track.');self.assertEqual(runner.call_count,1);self.assertEqual(runner.call_args.args[0][-1],'spotify:track:'+track)
  runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='playing|spotify:track:other'));self.assertIn('could not be verified',atticus.direct_media_execute(intent,runner))
 def test_spotify_search_is_bounded_encoded_and_never_claims_playback(self):
  runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=''))
  reply=atticus.direct_media_execute({'kind':'spotify_search','query':'blue moon'},runner)
  self.assertEqual(runner.call_args.args[0],['/usr/bin/open','spotify:search:blue%20moon']);self.assertIn('Select the track',reply)
  runner=Mock();self.assertIn('not supported',atticus.direct_media_execute({'kind':'transport','app':'spotify','action':'quit; attack'},runner));runner.assert_not_called()
 def test_foreground_requires_native_parent_and_confirmed_request(self):
  prefs=lambda k,d:{'client':'pi','foregroundProvider':'openai'}.get(k,d)
  for trusted,committed in ((False,True),(True,False),(True,True)):
   with self.subTest(trusted=trusted,committed=committed),patch.object(atticus.sys,'argv',['atticus.py','--wait']),patch.object(atticus.sys,'stdin',io.StringIO(json.dumps({'task':'set volume to 30'})+'\n')),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'trusted_native_context_parent',return_value=trusted),patch.object(atticus,'wait_commit',return_value=committed),patch.object(atticus,'direct_media_execute',return_value='System volume is 30%.') as action,patch.object(atticus.personal_commands,'resolve',return_value=None),patch.object(atticus,'run_pi',return_value=('fixture',0,0)) as provider,patch.object(atticus,'log_turn'),patch.object(atticus,'say'),patch.object(atticus.run,'ok',True,create=True):
    atticus.main()
    self.assertEqual(action.call_count,int(trusted and committed))
    self.assertEqual(provider.call_count,int(not trusted))
 def test_parent_loss_after_commit_stops_action(self):
  prefs=lambda k,d:{'client':'pi','foregroundProvider':'openai'}.get(k,d)
  with patch.object(atticus.sys,'argv',['atticus.py','--wait']),patch.object(atticus.sys,'stdin',io.StringIO(json.dumps({'task':'pause spotify'})+'\n')),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'trusted_native_context_parent',side_effect=[True,False]),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'direct_media_execute') as action,patch.object(atticus,'say'):
   atticus.main();action.assert_not_called()
if __name__=='__main__':unittest.main()
