"""Synthetic remote gate tests; no socket, credentials, network or provider."""
import threading,time,unittest
from pathlib import Path
from unittest.mock import Mock
from remote_gate import RemoteGate,RemoteError,valid_origin
import approval_channel

class RemoteGateTests(unittest.TestCase):
 def setUp(self):
  self.now=[100.0];self.g=RemoteGate(clock=lambda:self.now[0])
  self.bridge=Mock();self.bridge.valid_scope.return_value=True;self.bridge.submit.return_value=None
  self.auth={'host':'fixture.example','origin':'https://fixture.example','token':'t'*32,'csrf':'c'*32}
  self.scope={'id':'fixture-project','revision':'revision-1'}
 def enable(self):
  self.g.owner_enable(origin=self.auth['origin'],token=self.auth['token'],csrf=self.auth['csrf'],scope=self.scope,bridge=self.bridge,expires=200)
 def request(self,id='a'*32,task='inspect synthetic fixture',**auth):
  return self.g.request(**{**self.auth,**auth},body={'id':id,'task':task})
 def test_off_wrong_origin_host_credentials_and_unknown_fields(self):
  with self.assertRaises(RemoteError):self.request()
  self.enable()
  for update in ({'host':'evil.example'},{'origin':'https://evil.example'},{'origin':'null'},{'token':'x'*32},{'csrf':'wrong'},{'token':'é'*32}):
   with self.subTest(update=update),self.assertRaises(RemoteError):self.request(**update)
  with self.assertRaises(RemoteError):self.g.request(**self.auth,body={'id':'a'*32,'task':'fixture','scope':'/other'})
  self.bridge.submit.assert_not_called()
 def test_default_clock_includes_sleep_on_supported_mac(self):
  self.assertIs(RemoteGate()._clock,approval_channel.shared_clock)
 def test_bad_origin_variants(self):
  for origin in ('http://fixture.example','https://user@fixture.example','https://fixture.example/path','https://fixture.example:65536','https://FIXTURE.example','https://fixture.example?x=1'):
   self.assertFalse(valid_origin(origin),origin)
  self.assertTrue(valid_origin('https://fixture.example'))
 def test_replay_is_idempotent_one_active_and_no_scope_override(self):
  self.enable();first=self.request();self.assertEqual(first['status'],'submitted');self.assertEqual(self.request(),first)
  with self.assertRaises(RemoteError):self.request(task='different')
  with self.assertRaises(RemoteError):self.request(id='b'*32)
  self.assertEqual(self.bridge.submit.call_count,1);self.assertEqual(self.bridge.submit.call_args.args[2],self.scope)
 def test_scope_change_or_expiry_before_dispatch_fails_closed(self):
  self.enable();self.bridge.valid_scope.return_value=False
  self.assertEqual(self.request()['status'],'failed');self.bridge.submit.assert_not_called()
  self.bridge.valid_scope.side_effect=lambda scope:(self.now.__setitem__(0,201) or True)
  self.assertEqual(self.request(id='b'*32)['status'],'cancelled');self.bridge.submit.assert_not_called()
 def test_stop_during_slow_scope_check_prevents_dispatch(self):
  self.enable();entered=threading.Event();release=threading.Event();results=[]
  def slow(scope):entered.set();release.wait(2);return True
  self.bridge.valid_scope.side_effect=slow
  t=threading.Thread(target=lambda:results.append(self.request()),daemon=True);t.start();self.assertTrue(entered.wait(1))
  self.assertEqual(self.g.stop(**self.auth,ident='a'*32)['status'],'cancelling')
  release.set();t.join(2);self.assertEqual(results[0]['status'],'cancelled');self.bridge.submit.assert_not_called()
 def test_stop_during_queued_dispatch_sets_bridge_cancellation(self):
  self.enable();entered=threading.Event();release=threading.Event();dispatched=[];result=[]
  def submit(ident,task,scope,cancelled,expires):
   entered.set();release.wait(2)
   if not cancelled.is_set():dispatched.append(ident)
  self.bridge.submit.side_effect=submit
  t=threading.Thread(target=lambda:result.append(self.request()),daemon=True);t.start();self.assertTrue(entered.wait(1))
  self.assertEqual(self.g.stop(**self.auth,ident='a'*32)['status'],'cancelling')
  release.set();t.join(2);self.assertEqual(dispatched,[]);self.assertEqual(result[0]['status'],'cancelling')
 def test_revocation_invalidates_old_session_and_requires_fresh_pair(self):
  self.enable();self.g.owner_revoke()
  with self.assertRaises(RemoteError):self.request()
  with self.assertRaises(RemoteError):self.enable()
  self.auth['token']='n'*32;self.auth['csrf']='m'*32;self.enable();self.assertEqual(self.request()['status'],'submitted')

 def test_revoke_expiry_and_late_result(self):
  self.enable();self.request();generation=self.g._generation
  self.now[0]=201;self.assertTrue(self.g.expire_if_needed())
  end=time.monotonic()+1
  while self.bridge.cancel.call_count==0 and time.monotonic()<end:time.sleep(.001)
  self.bridge.cancel.assert_called_once_with('a'*32)
  self.assertTrue(self.g.owner_result('a'*32,generation,'completed'))
  with self.assertRaises(RemoteError):self.g.status(**self.auth,ident='a'*32)
 def test_stop_idempotent_and_cancel_failure_is_unknown(self):
  self.enable();self.request();self.assertEqual(self.g.stop(**self.auth,ident='a'*32)['status'],'cancelling');self.assertEqual(self.g.stop(**self.auth,ident='a'*32)['status'],'cancelling')
  end=time.monotonic()+1
  while self.bridge.cancel.call_count==0 and time.monotonic()<end:time.sleep(.001)
  self.bridge.cancel.assert_called_once()
 def test_bridge_failure_fails_closed_and_cannot_replay(self):
  self.enable();self.bridge.submit.side_effect=OSError('synthetic failure')
  self.assertEqual(self.request()['status'],'unknown');self.assertEqual(self.request()['status'],'unknown')
  self.assertEqual(self.bridge.submit.call_count,1)
 def test_cancel_failure_reports_unknown(self):
  self.enable();self.request();self.bridge.cancel.side_effect=OSError('synthetic failure')
  self.assertEqual(self.g.stop(**self.auth,ident='a'*32)['status'],'cancelling')
  end=time.monotonic()+1
  while self.g.status(**self.auth,ident='a'*32)['status']!='unknown' and time.monotonic()<end:time.sleep(.001)
  self.assertEqual(self.g.status(**self.auth,ident='a'*32)['status'],'unknown')
 def test_old_validation_cannot_clear_same_id_in_new_session(self):
  self.enable();entered=threading.Event();release=threading.Event();old=[]
  def slow(scope):entered.set();release.wait(2);return True
  self.bridge.valid_scope.side_effect=slow
  t=threading.Thread(target=lambda:old.append(self.request()),daemon=True);t.start();self.assertTrue(entered.wait(1))
  self.g.owner_revoke();self.auth['token']='n'*32;self.auth['csrf']='m'*32
  self.bridge.valid_scope.side_effect=None;self.bridge.valid_scope.return_value=True;self.enable()
  self.assertEqual(self.request()['status'],'submitted');release.set();t.join(2);self.assertEqual(old[0]['status'],'cancelled')
  with self.assertRaises(RemoteError):self.request(id='b'*32)
  self.assertEqual(self.bridge.submit.call_count,1)
 def test_uncertain_dispatch_blocks_retry_and_repair_until_owner_review(self):
  self.enable();sent=[]
  def delivered_then_lost(*args):sent.append(args[0]);raise OSError('lost reply')
  self.bridge.submit.side_effect=delivered_then_lost;generation=self.g._generation
  self.assertEqual(self.request()['status'],'unknown');self.assertEqual(sent,['a'*32])
  with self.assertRaises(RemoteError):self.request(id='b'*32)
  self.g.owner_revoke();self.auth['token']='n'*32;self.auth['csrf']='m'*32
  with self.assertRaises(RemoteError):self.enable()
  with self.assertRaises(RemoteError):self.g.owner_reconcile('a'*32,generation,confirmed=False,outcome='not_started')
  self.g.owner_reconcile('a'*32,generation,confirmed=True,outcome='completed')
  self.enable();self.assertEqual(sent,['a'*32])
 def test_expire_old_generation_cannot_revoke_replacement(self):
  self.enable();old=self.g._generation;self.g.owner_revoke();self.auth['token']='n'*32;self.auth['csrf']='m'*32;self.enable()
  self.assertFalse(self.g.owner_revoke(expected_generation=old));self.assertEqual(self.request()['status'],'submitted')
 def test_uncertain_callback_cannot_clear_newer_request(self):
  self.enable();generation=self.g._generation;self.request();self.assertTrue(self.g.owner_result('a'*32,generation,'unknown'))
  with self.assertRaises(RemoteError):self.request(id='b'*32)
  self.assertTrue(self.g.owner_result('a'*32,generation,'completed'));self.assertEqual(self.request(id='b'*32)['status'],'submitted')
 def test_late_cancel_error_cannot_overwrite_terminal_result(self):
  self.enable();self.request();generation=self.g._generation;entered=threading.Event();release=threading.Event();result=[]
  def slow_cancel(ident):entered.set();release.wait(2);raise OSError('late failure')
  self.bridge.cancel.side_effect=slow_cancel
  t=threading.Thread(target=lambda:result.append(self.g.stop(**self.auth,ident='a'*32)),daemon=True);t.start();self.assertTrue(entered.wait(1))
  self.assertTrue(self.g.owner_result('a'*32,generation,'cancelled'));release.set();t.join(2)
  self.assertEqual(result[0]['status'],'cancelling');self.assertEqual(self.g.status(**self.auth,ident='a'*32)['status'],'cancelled')
  self.assertEqual(self.request(id='b'*32)['status'],'submitted')
 def test_preview_has_no_network_or_enabled_dispatch(self):
  page=(Path(__file__).resolve().parents[1]/'ui/remote-preview.html').read_text()
  self.assertIn('development preview only',page);self.assertIn('type="button" disabled>Send',page);self.assertIn('type="button" disabled>Stop',page)
  self.assertIn(".textContent=document.getElementById('task').value",page);self.assertNotIn('fetch(',page);self.assertNotIn('WebSocket',page)
if __name__=='__main__':unittest.main()
