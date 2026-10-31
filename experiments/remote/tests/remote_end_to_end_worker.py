"""Synthetic native child: real supervisor, remote adapter, registry and HTTP; fake Codex."""
import http.client,json,os,queue,socket,sys,threading
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atticus

class FakeProvider:
 instances=[]
 def __init__(self,**kwargs):
  self.release=threading.Event();self.interrupted=threading.Event();self.instances.append(self)
 def run(self,*args,**kwargs):
  self.release.wait(10);return {'status':'stopped','result':'synthetic','server_status':'interrupted'}
 def interrupt(self):self.interrupted.set();self.release.set()
 def close(self):self.release.set()

root=Path(sys.argv[1]);expiry=float(sys.argv[2]);result=Path(sys.argv[3]);mode=sys.argv[4] if len(sys.argv)>4 else 'allow';project=root/'project';profile=root/'profile'
owner_socket=socket.socket(fileno=os.dup(2))
null=os.open(os.devnull,os.O_WRONLY);os.dup2(null,2);os.close(null)
sys.stderr=open(root/'worker-error.log','w',buffering=1)
atticus.DIR=str(profile);atticus.trusted_native_context_parent=lambda:True;atticus.codex_scoped_readiness=lambda *args:(True,'');atticus.close_agent_window=lambda *a:None;atticus.codex_provider.CodexProvider=FakeProvider
manager=atticus.Agents(emit=lambda _:None,launch=Mock());atticus.Agents=lambda:manager
st=project.stat();origin='https://atlas.test';token='t'*32;csrf='c'*32
headers={'Host':'atlas.test','Origin':origin,'Content-Type':'application/json','X-Atlas-Token':token,'X-Atlas-CSRF':csrf}
commands=queue.Queue()
class Input:
 def __iter__(self):
  while True:
   line=commands.get()
   if line is None:return
   yield json.dumps(line)
 def fileno(self):return 0
sys.stdin=Input()
def phone(port):
 try:
  def post(path,body):
   c=http.client.HTTPConnection('127.0.0.1',port,timeout=8);c.request('POST',path,json.dumps(body),headers);r=c.getresponse();out=json.loads(r.read());c.close();return out
  paired=post('/pair',{'code':'i'*32,'device':'synthetic phone'})
  assert paired=={'token':token,'csrf':csrf}
  ident='12345678123441238123123456789abc'
  submitted=post('/task',{'id':ident,'task':'synthetic task'});status=post('/status',{'id':ident});stop=post('/stop',{'id':ident})
  interrupted=FakeProvider.instances[0].interrupted.wait(3)
  barrier=json.loads((profile/'remote'/'remote-pending.json').read_text())
  result.write_text(json.dumps({'submitted':submitted,'status':status,'stop':stop,'interrupted':interrupted,'rows':len(manager.rows),'barrier':barrier}))
 finally:
  commands.put({'action':'remote-stop','nativeAuthority':'a'*64});commands.put(None)
def emit(event):
 if event.get('event')=='remote-ready':threading.Thread(target=phone,args=(event['port'],),daemon=True).start()
 elif event.get('event')=='remote-error':
  result.write_text(json.dumps({'rejected':True,'rows':len(manager.rows),'providers':len(FakeProvider.instances)}));commands.put(None)
manager.emit=emit
commands.put({'action':'remote-enable','folder':str(project),'identity':{'device':st.st_dev,'inode':st.st_ino},'scope':{'id':'fixture','revision':'r1'},'origin':origin,'token':('x'*32 if mode=='forged' else token),'csrf':csrf,'expires':expiry,'invitation':'i'*32,'nativeAuthority':'a'*64})
atticus.agents_service(remote_owner=owner_socket)
