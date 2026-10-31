"""Owner-channel socketpair fixtures; no UI, network, credentials or model."""
import socket,threading,unittest
import approval_channel
from remote_ipc import NativeApprovalChannel

class NativeChannelTests(unittest.TestCase):
 def setUp(self):
  a,b=socket.socketpair();self.owner=approval_channel.Owner(a);self.sock=a
  self.clock=[1.];self.client=NativeApprovalChannel(b,scope={'id':'fixture','revision':'r'},identity={'device':1,'inode':2},expires=10,clock=lambda:self.clock[0]);self.addCleanup(self.client.close);self.addCleanup(self.sock.close)
 def request(self):
  result=[];thread=threading.Thread(target=lambda:result.append(self.client('synthetic task','/tmp/project')));thread.start();target=self.owner.receive();return thread,result,target
 def test_true_owner_decision_binds_complete_target(self):
  t,result,target=self.request();self.assertEqual(target,{'action':'remote-codex-task','task':'synthetic task','folder':'/tmp/project','scope':{'id':'fixture','revision':'r'},'identity':{'device':1,'inode':2},'expires':10})
  self.owner.respond(True);t.join(1);self.assertEqual(result,[True])
 def test_denial_and_expiry_fail_closed(self):
  t,result,_=self.request();self.owner.respond(False);t.join(1);self.assertEqual(result,[False])
  t,result,_=self.request();self.clock[0]=11;self.owner.respond(True);t.join(1);self.assertEqual(result,[False])
 def test_stop_closes_pending_approval(self):
  t,result,_=self.request();self.client.close();t.join(1);self.assertEqual(result,[False])
 def test_forged_revision_is_rejected(self):
  t,result,_=self.request();pending=self.owner.pending
  approval_channel._send(self.sock,{'kind':'decision','id':pending['id'],'revision':'0'*64,'allow':True})
  t.join(1);self.assertEqual(result,[False])
