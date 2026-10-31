import json, os, select, shutil, socket, subprocess, tempfile, threading, unittest
from pathlib import Path
import approval_channel as channel
ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')
class ProcessIntegrationTests(unittest.TestCase):
 def run_helper(self, allowed):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ask=root/'ask';ask.mkdir();state=root/'state';state.mkdir();fake=root/'fake-app'
   fake.write_text('#!/usr/bin/python3\nimport json,sys\nr={"bundle_id":"com.example.Fixture","path":"/Applications/Fixture.app","pid":7,"started":"123"}\nif len(sys.argv)>2:r["focused"]=True\nprint(json.dumps(r))\n');fake.chmod(0o700)
   src="""const {spawnSync}=require('node:child_process');const io=Array(199).fill('ignore');io[0]='pipe';io[1]='pipe';io[2]='pipe';io[198]=198;const r=spawnSync('/bin/sh',[process.env.ATTICUS_ME,'--foreground-control'],{input:JSON.stringify({action:'focus_app',bundle_id:'com.example.Fixture'}),encoding:'utf8',env:process.env,stdio:io,timeout:5000});process.stdout.write(r.stdout);process.stderr.write(r.stderr);process.exit(r.status||0);"""
   owner,child=socket.socketpair();self.addCleanup(owner.close);self.addCleanup(child.close)
   try:os.fstat(channel.TOOL_FD)
   except OSError:pass
   else:self.skipTest('reserved descriptor occupied')
   os.dup2(child.fileno(),channel.TOOL_FD,inheritable=False)
   ir,iw=os.pipe();orr,ow=os.pipe();native_in=os.fdopen(ir,'r');native_out=os.fdopen(ow,'w');self.addCleanup(native_in.close);self.addCleanup(native_out.close);self.addCleanup(os.close,iw);self.addCleanup(os.close,orr)
   worker=threading.Thread(target=channel.native_broker,args=(owner,native_in,native_out,3),daemon=True);worker.start()
   env={'PATH':'/usr/bin:/bin','HOME':d,'ATTICUS_DIR':str(state),'ATTICUS_ASK':str(ask),'ATTICUS_APP':str(fake),'ATTICUS_ME':str(ROOT/'atticus.py'),'PYTHONPYCACHEPREFIX':str(root/'cache')}
   try:p=subprocess.Popen([NODE,'-e',src],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,pass_fds=(channel.TOOL_FD,))
   finally:os.close(channel.TOOL_FD);child.close()
   ready,_,_=select.select([orr],[],[],5);self.assertTrue(ready,'no native approval request')
   question=os.read(orr,4096).decode();parts=question.strip().split('\t');self.assertIn('Focus this running app?',parts[0]);token=parts[2].split(':');self.assertEqual(token[0],'channel')
   answers=state/'answers';answers.mkdir();(answers/token[1]).write_text('y')
   self.assertIsNone(p.poll(),'file-based forged approval must not end the request')
   os.write(iw,(json.dumps({'id':token[1],'revision':token[2],'allow':allowed})+'\n').encode());out,err=p.communicate(timeout=5)
   self.assertEqual(p.returncode,0,err);self.assertEqual(json.loads(out)['status'],'verified' if allowed else 'cancelled');self.assertEqual((answers/token[1]).read_text(),'y')
 @unittest.skipUnless(NODE,'node unavailable')
 def test_real_helper_allow_and_deny_ignores_forged_file(self):
  self.run_helper(True);self.run_helper(False)
 def test_broker_rejects_forged_native_response(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  ir,iw=os.pipe();orr,ow=os.pipe();native_in=os.fdopen(ir,'r');native_out=os.fdopen(ow,'w');self.addCleanup(native_in.close);self.addCleanup(native_out.close);self.addCleanup(os.close,iw);self.addCleanup(os.close,orr)
  worker=threading.Thread(target=channel.native_broker,args=(a,native_in,native_out,2),daemon=True);worker.start()
  channel._send(b,{'kind':'hello'});greeting=channel._read(b);requester=channel.Requester(b,session=greeting['nonce']);requester.request({'q':'Fixture?','cmd':'safe target'},__import__('time').monotonic()+3)
  self.assertTrue(select.select([orr],[],[],2)[0]);question=os.read(orr,4096).decode();parts=question.strip().split('\t')[2].split(':')
  os.write(iw,(json.dumps({'id':'f'*64,'revision':parts[2],'allow':True})+'\n').encode())
  self.assertFalse(requester.receive());worker.join(2);self.assertFalse(worker.is_alive())
 def test_two_sequential_requests_share_run_but_not_request_ids(self):
  import time
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  ir,iw=os.pipe();orr,ow=os.pipe();native_in=os.fdopen(ir,'r');native_out=os.fdopen(ow,'w');self.addCleanup(native_in.close);self.addCleanup(native_out.close);self.addCleanup(os.close,iw);self.addCleanup(os.close,orr)
  worker=threading.Thread(target=channel.native_broker,args=(a,native_in,native_out,2),daemon=True);worker.start();sessions=[];ids=[]
  for n in range(2):
   channel._send(b,{'kind':'hello'});greeting=channel._read(b);sessions.append(greeting['nonce']);requester=channel.Requester(b,session=greeting['nonce']);requester.request({'q':'Fixture?','cmd':'target '+str(n)},time.monotonic()+3)
   self.assertTrue(select.select([orr],[],[],2)[0]);parts=os.read(orr,4096).decode().strip().split('\t')[2].split(':');ids.append(parts[1]);os.write(iw,(json.dumps({'id':parts[1],'revision':parts[2],'allow':True})+'\n').encode());self.assertTrue(requester.receive())
  self.assertEqual(sessions[0],sessions[1]);self.assertNotEqual(ids[0],ids[1])
 def test_scoped_native_response_carries_deadline_and_revision(self):
  import time
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  ir,iw=os.pipe();orr,ow=os.pipe();native_in=os.fdopen(ir,'r');native_out=os.fdopen(ow,'w');self.addCleanup(native_in.close);self.addCleanup(native_out.close);self.addCleanup(os.close,iw);self.addCleanup(os.close,orr)
  worker=threading.Thread(target=channel.native_broker,args=(a,native_in,native_out,2),daemon=True);worker.start();channel._send(b,{'kind':'hello'});greeting=channel._read(b)
  requester=channel.Requester(b,session=greeting['nonce']);requester.request({'q':'Fixture?','cmd':'target'},time.monotonic()+3)
  self.assertTrue(select.select([orr],[],[],2)[0]);parts=os.read(orr,4096).decode().strip().split('\t')[2].split(':');expiry=channel.shared_clock()+2
  response={'id':parts[1],'revision':parts[2],'allow':True,'expires':expiry,'targetRevision':'fixture-revision'}
  os.write(iw,(json.dumps(response)+'\n').encode());self.assertTrue(requester.receive());self.assertEqual(requester.authorizationDeadline,expiry);self.assertEqual(requester.authorizationRevision,'fixture-revision')
