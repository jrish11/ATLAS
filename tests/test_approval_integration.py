import json, os, select, shutil, socket, subprocess, tempfile, threading, unittest
from pathlib import Path
import approval_channel as channel
ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')
class ProcessIntegrationTests(unittest.TestCase):
 def run_helper(self, allowed):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ask=root/'ask';ask.mkdir();state=root/'state';state.mkdir();fake=root/'fake-app'
   (state/'settings.json').write_text(json.dumps({'foregroundKeepFocus':False}))
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
 @unittest.skipUnless(NODE,'node unavailable')
 def test_denial_closes_channel_for_sequential_real_helpers(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ask=root/'ask';ask.mkdir();state=root/'state';state.mkdir();fake=root/'fake-app'
   fake.write_text('#!/usr/bin/python3\nimport json\nprint(json.dumps({"bundle_id":"com.example.Fixture","path":"/Applications/Fixture.app","pid":7,"started":"123"}))\n');fake.chmod(0o700)
   script="""const {spawnSync}=require('node:child_process');const io=Array(199).fill('ignore');io[0]='pipe';io[1]='pipe';io[2]='pipe';io[198]=198;for(let i=0;i<2;i++){const r=spawnSync('/bin/sh',[process.env.ATTICUS_ME,'--foreground-control'],{input:JSON.stringify({action:'click',bundle_id:'com.example.Fixture',target:'Play'}),encoding:'utf8',env:process.env,stdio:io,timeout:5000});console.log(JSON.stringify({out:r.stdout.trim(),error:String(r.error||''),status:r.status}))}"""
   owner,child=socket.socketpair();self.addCleanup(owner.close);self.addCleanup(child.close)
   try:os.fstat(channel.TOOL_FD)
   except OSError:pass
   else:self.skipTest('reserved descriptor occupied')
   os.dup2(child.fileno(),channel.TOOL_FD,inheritable=False)
   ir,iw=os.pipe();orr,ow=os.pipe();native_in=os.fdopen(ir,'r');native_out=os.fdopen(ow,'w');self.addCleanup(native_in.close);self.addCleanup(native_out.close);self.addCleanup(os.close,iw);self.addCleanup(os.close,orr)
   denied=threading.Event()
   def latch():
    (ask/'declined').touch();denied.set()
   worker=threading.Thread(target=channel.native_broker,args=(owner,native_in,native_out,3),kwargs={'on_denied':latch},daemon=True);worker.start()
   env={'PATH':'/usr/bin:/bin','HOME':d,'ATTICUS_DIR':str(state),'ATTICUS_ASK':str(ask),'ATTICUS_APP':str(fake),'ATTICUS_ME':str(ROOT/'atticus.py'),'PYTHONPYCACHEPREFIX':str(root/'cache')}
   try:p=subprocess.Popen([NODE,'-e',script],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,pass_fds=(channel.TOOL_FD,))
   finally:os.close(channel.TOOL_FD);child.close()
   self.assertTrue(select.select([orr],[],[],5)[0]);question=os.read(orr,4096).decode();parts=question.strip().split('\t')[2].split(':')
   os.write(iw,(json.dumps({'id':parts[1],'revision':parts[2],'allow':False})+'\n').encode())
   try:out,err=p.communicate(timeout=15)
   except subprocess.TimeoutExpired:
    p.kill();p.communicate();self.fail('sequential helpers did not terminate')
   worker.join(2)
   self.assertEqual(p.returncode,0,err);self.assertTrue(denied.is_set());self.assertFalse(worker.is_alive())
   results=[json.loads(line) for line in out.splitlines()];self.assertEqual(len(results),2,repr((out,err)));self.assertTrue(all(not r['error'] for r in results),repr(results));rows=[json.loads(r['out']) for r in results];self.assertTrue(all(r['status']=='cancelled' for r in rows))
   self.assertFalse(select.select([orr],[],[],.1)[0], 'no second native approval')
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

class DenialAcrossToolsTests(unittest.TestCase):
 def test_denial_blocks_control_and_saved_destination_in_request_only(self):
  import atticus
  from unittest.mock import Mock,patch
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'declined').touch();approve=Mock(return_value='y')
   with patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d}),patch.object(atticus,'DIR',d),patch.object(atticus.approval_channel,'tool_approval',approve),patch.object(atticus.personal_commands,'resolve') as resolve:
    control=atticus.foreground_control_request({'action':'click','bundle_id':'com.example.Fixture','target':'Play'})
    saved=atticus.foreground_saved_tool({'name':'fixture'})
    self.assertEqual(control['status'],'cancelled');self.assertIn('cancelled',saved['text'])
    approve.assert_not_called();resolve.assert_not_called()
   (root/'declined').unlink()
   with patch.dict(os.environ,{'ATTICUS_ASK':d,'ATTICUS_DIR':d}),patch.object(atticus,'DIR',d),patch.object(atticus.personal_commands,'resolve',return_value=None) as resolve:
    atticus.foreground_saved_tool({'name':'fixture'});resolve.assert_called_once()

class DenialStatusTests(unittest.TestCase):
 def test_denial_stops_model_and_overrides_misleading_completion(self):
  import io
  from types import SimpleNamespace
  from unittest.mock import Mock,patch
  import atticus,foreground_openai
  events=[json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'Fixture completion'}],'usage':{}}})+'\n']
  proc=SimpleNamespace(stdin=Mock(),stdout=io.StringIO(''.join(events)),returncode=0,wait=lambda:0,poll=lambda:0,pid=12345)
  prefs=lambda k,d:{'client':'pi','foregroundProvider':'openai','foregroundAppControl':True,'foregroundSavedDestinations':False,'foregroundModel':'gpt-6.1-terra'}.get(k,d)
  def broker(sock,instream,outstream,timeout=60,on_denied=None):on_denied()
  with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'relay'),patch.object(atticus.signal,'signal'),patch.object(atticus.atexit,'register'),patch.object(atticus.subprocess,'Popen',return_value=proc),patch.object(atticus.keychain_store.ProviderKeyStore,'get',return_value='fixture-key'),patch.object(atticus.approval_channel,'native_broker',side_effect=broker),patch.object(atticus,'stop_claude') as stop,patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}):
   reply,_,_=atticus.run_pi('fixture')
  self.assertEqual(reply,'You declined the action, so I stopped this request.');self.assertFalse(atticus.run.ok);self.assertEqual(atticus.run.why,'cancelled');stop.assert_called_with(proc)
