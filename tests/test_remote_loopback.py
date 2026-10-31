import http.client
import json
import threading
import unittest
from remote_gate import RemoteGate, RemoteError
from remote_loopback import LoopbackServer, Pairing

class Bridge:
 def valid_scope(self, scope): return True
 def submit(self, *args): return 'submitted'
 def cancel(self, ident): pass

class LoopbackTests(unittest.TestCase):
 def setUp(self):
  self.clock=[1.0]; self.origin='https://atlas.test'; self.pair=Pairing(self.origin,lambda:self.clock[0],100)
  self.token,self.csrf=self.pair.consume(self.pair.invitation)
  self.gate=RemoteGate(clock=lambda:self.clock[0]); self.gate.owner_enable(origin=self.origin,token=self.token,csrf=self.csrf,scope={'id':'fixture','revision':'1'},bridge=Bridge(),expires=100)
  self.server=LoopbackServer(self.gate,self.origin); self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join()
 def post(self, path, body, **changes):
  headers={'Host':'atlas.test','Origin':self.origin,'Content-Type':'application/json','X-Atlas-Token':self.token,'X-Atlas-CSRF':self.csrf};headers.update(changes)
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2);c.request('POST',path,json.dumps(body),headers);r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
 def test_one_use_invitation(self):
  with self.assertRaises(RemoteError): self.pair.consume(self.pair.invitation)
 def test_origin_host_csrf_rejected(self):
  for changes in ({'Host':'evil.test'},{'Origin':'https://evil.test'},{'X-Atlas-CSRF':'bad'}):
   self.assertEqual(self.post('/task',{'id':'a'*32,'task':'test'},**changes)[0],403)
 def test_expiry_and_replay(self):
  body={'id':'a'*32,'task':'test'}
  self.assertEqual(self.post('/task',body)[1]['status'],'submitted')
  self.assertEqual(self.post('/task',body)[1]['status'],'submitted')
  self.assertEqual(self.post('/task',dict(body,task='changed'))[0],403)
  self.clock[0]=101;self.assertEqual(self.post('/status',{'id':'a'*32})[0],403)
 def test_no_enable_endpoint(self): self.assertEqual(self.post('/enable',{})[0],403)
