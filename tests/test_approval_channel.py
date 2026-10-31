import socket, unittest
from unittest.mock import patch
import approval_channel as c
class ChannelTests(unittest.TestCase):
 def setUp(self):
  self.a,self.b=socket.socketpair();self.addCleanup(self.a.close);self.addCleanup(self.b.close);self.clock=[10];self.requester=c.Requester(self.a,lambda:self.clock[0],shared=lambda:self.clock[0]);self.owner=c.Owner(self.b)
 def test_exact_target_and_one_shot(self):
  target={'action':'open_app','bundle_id':'com.example.fixture','revision':'abc'};self.requester.request(target,20);self.assertEqual(self.owner.receive(),target);self.owner.respond(True);self.assertTrue(self.requester.receive())
  with self.assertRaises(ValueError):self.requester.receive()
  with self.assertRaises(ValueError):self.owner.respond(True)
 def test_forged_target_or_id_rejected(self):
  self.requester.request({'target':'a'},20);self.owner.receive();msg=self.owner.pending;self.owner.pending=None;c._send(self.b,{'kind':'decision','id':'f'*64,'revision':msg['revision'],'allow':True});self.assertFalse(self.requester.receive())
 def test_expired_response_rejected(self):
  self.requester.request({'target':'a'},12);self.owner.receive();self.owner.respond(True);self.clock[0]=13;self.assertFalse(self.requester.receive())
 def test_channel_loss_and_cancellation_fail_closed(self):
  self.requester.request({'target':'a'},20);self.b.close();self.assertFalse(self.requester.receive())
 def test_replayed_request_rejected(self):
  self.requester.request({'target':'a'},20);self.owner.receive();old=self.owner.pending;self.owner.respond(False);self.assertFalse(self.requester.receive());c._send(self.a,old)
  with self.assertRaises(ValueError):self.owner.receive()
 def test_auto_deadline_is_bound_to_decision_and_checked_after_delay(self):
  self.requester.request({'target':'a'},20);self.owner.receive();self.owner.respond(True,expires=12,target_revision='fixture-revision')
  self.assertTrue(self.requester.receive());decision=c.Approval('y',self.requester.authorizationDeadline)
  with patch.object(c,'TOOL_FD',self.a.fileno()):
   self.assertTrue(c.authorized(decision,lambda:11));self.assertFalse(c.authorized(decision,lambda:13))
 def test_numeric_allow_is_rejected(self):
  self.requester.request({'target':'a'},20);self.owner.receive();m=self.owner.pending;self.owner.pending=None
  c._send(self.b,{'kind':'decision','id':m['id'],'revision':m['revision'],'allow':1});self.assertFalse(self.requester.receive())

 def test_closed_channel_revokes_prior_auto_decision(self):
  self.requester.request({'target':'a'},20);self.owner.receive();self.owner.respond(True,expires=19,target_revision='fixture-revision');self.assertTrue(self.requester.receive())
  decision=c.Approval('y',self.requester.authorizationDeadline);self.b.shutdown(socket.SHUT_RDWR)
  with patch.object(c,'TOOL_FD',self.a.fileno()): self.assertFalse(c.authorized(decision,lambda:11))
